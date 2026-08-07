"""
How the kitchen display looks.

The display is a cast screen with no keyboard, no mouse worth the name, and a
touch layer the Nest Hub only half means. Nobody is going to set it up from the
screen itself, and the app's own appearance panel is no help either: that is per
device, kept in the browser's localStorage, and the Hub is not a device anyone
opens the app on. So these settings live on the server, are edited from the app
on a phone, and are picked up by the display on its next poll - a minute at the
outside, with nothing to re-cast.

Kept in /data/display.json rather than in data.json: it is a preference, not
part of the meal plan, and it has no business being in the diff of a week's
backup. Everything is validated on the way in, because a bad value here doesn't
show up as an error - it shows up as a wall display that has gone black in a
kitchen nobody is standing in.
"""

import json
import os
import re
import threading
from datetime import datetime

DATA_DIR = os.environ.get("MEAL_PLANNER_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(DATA_DIR, "display.json")

# The same twelve the app offers, and they have to stay the same twelve: the
# shades live in kitchen.css under html[data-accent="..."]. One added here and
# not there is a display that quietly falls back to green.
ACCENTS = ("green", "olive", "teal", "blue", "indigo", "plum",
           "rose", "rust", "amber", "cocoa", "slate", "charcoal")

THEMES = ("dark", "light")

# Percent. Below 70 the far side of the room can't read it and above 140 a
# Nest Hub is showing about four words, so there is no point offering more.
MIN_SCALE, MAX_SCALE = 70, 140

# How dim "dimmed" is, as a percentage of full brightness. Not zero: a display
# that goes completely black at night looks broken, and the point is to stop it
# lighting the room, not to turn it off.
MIN_DIM, MAX_DIM = 10, 90

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

DEFAULTS = {
    "accent": "green",
    "theme": "dark",           # a Hub in a kitchen is on all evening
    "scale": 100,
    "showCook": True,
    "showClock": True,
    "showDate": True,
    "showWeek": True,          # the seven-day strip along the bottom
    "showPhotos": True,
    "showEmpty": True,         # say "nothing planned" rather than leaving a gap
    "dim": False,
    "dimFrom": "22:00",
    "dimTo": "06:30",
    "dimLevel": 45,

    # When the display stops looking at today and starts looking at tomorrow.
    # Midnight - the default - is the calendar answer and the one every version
    # before this one gave. Anything earlier suits a house where the evening
    # meal is over well before bedtime and the useful question after that is
    # what happens next, not what already happened.
    "rollover": "00:00",

    # The hours during which the week is allowed onto a Cast screen. Off by
    # default, which means all day, as it always was. See cast.py: this is a
    # window for *taking* the screen, and the only thing it ever gives back is
    # a screen already showing our own page.
    "castWindow": False,
    "castFrom": "07:00",
    "castTo": "23:00",
}

_lock = threading.Lock()


def _clamp(value, low, high, fallback):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def clean(raw, base=None):
    """A complete, valid settings dict from whatever was passed in.

    Anything missing falls back to `base` (the settings as they are now, when
    this is a partial update from the app) and then to the defaults. Anything
    unrecognised is dropped rather than stored - this file is read by the
    display on every poll, and it should only ever contain what is understood."""
    base = dict(DEFAULTS, **(base or {}))
    raw = raw if isinstance(raw, dict) else {}
    out = {}

    accent = str(raw.get("accent", base["accent"]))
    out["accent"] = accent if accent in ACCENTS else base["accent"]

    theme = str(raw.get("theme", base["theme"]))
    out["theme"] = theme if theme in THEMES else base["theme"]

    out["scale"] = _clamp(raw.get("scale", base["scale"]), MIN_SCALE, MAX_SCALE, base["scale"])
    out["dimLevel"] = _clamp(raw.get("dimLevel", base["dimLevel"]), MIN_DIM, MAX_DIM,
                             base["dimLevel"])

    for flag in ("showCook", "showClock", "showDate", "showWeek", "showPhotos",
                 "showEmpty", "dim", "castWindow"):
        out[flag] = bool(raw.get(flag, base[flag]))

    for field in ("dimFrom", "dimTo", "rollover", "castFrom", "castTo"):
        value = str(raw.get(field, base[field])).strip()
        out[field] = value if _TIME.match(value) else base[field]

    return out


# --------------------------------------------------------------------------
# what the times mean
# --------------------------------------------------------------------------
#
# Both of these are asked several times a minute by different threads - the
# watcher in cast.py, and every /api/kitchen poll - so they take the settings
# they were given rather than reading the file again, and take `now` as an
# argument so they can be tested without waiting for an evening.

def _minutes(text):
    match = _TIME.match(str(text or "").strip())
    return int(match.group(1)) * 60 + int(match.group(2)) if match else -1


def day_shift(settings=None, now=None):
    """How many days past the calendar date the display should be showing: 0
    or 1.

    Rollover at midnight is the same as no rollover, and is written that way
    rather than as a flag - "00:00" is exactly when the calendar turns over, so
    the general case gives the right answer for free."""
    settings = settings if isinstance(settings, dict) else load()
    at = _minutes(settings.get("rollover"))
    if at <= 0:
        return 0
    now = now or datetime.now()
    return 1 if (now.hour * 60 + now.minute) >= at else 0


def casting_open(settings=None, now=None):
    """Whether the week is allowed onto a Cast screen at this moment.

    A window that wraps midnight - 16:00 to 01:00, for a house that eats late -
    can't ask for "after the start AND before the end"; one that doesn't wrap
    must. Equal times mean all day: a zero-length window is nobody's intention,
    and a picker that can silently turn casting off altogether is a support
    call waiting to happen."""
    settings = settings if isinstance(settings, dict) else load()
    if not settings.get("castWindow"):
        return True
    start, end = _minutes(settings.get("castFrom")), _minutes(settings.get("castTo"))
    if start < 0 or end < 0 or start == end:
        return True
    now = now or datetime.now()
    minute = now.hour * 60 + now.minute
    return (start <= minute < end) if start < end else (minute >= start or minute < end)


def load():
    """Current settings. A missing or unreadable file is not an error: it means
    nobody has changed anything, which is what the defaults are for."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
    except (OSError, ValueError):
        return dict(DEFAULTS)
    return clean(stored)


def save(patch):
    """Merge a change from the app over what is stored, and write it back.
    Returns the settings as they now are."""
    with _lock:
        current = load()
        merged = clean(patch, current)
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2, sort_keys=True)
        os.replace(tmp, SETTINGS_FILE)
        return merged
