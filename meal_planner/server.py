#!/usr/bin/env python3
"""
Home Meal Planner - a small, dependency-free web app for planning family meals.

Run:  python server.py
Then open the address it prints on any device on your home network.
"""

import base64
import html
import json
import math
import os
import re
import shutil
import socket
import ssl
import sys
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import backup
import bell
import cast
import display
import icon
import tls

PORT = int(os.environ.get("MEAL_PLANNER_PORT", "8080"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# HTTPS runs alongside plain http, never instead of it: the Nest Hub can't be
# given a private certificate authority, so /kitchen has to stay on http.
# Everything phone-facing wants https, because offline caching needs it.
HTTPS_PORT = int(os.environ.get("MEAL_PLANNER_HTTPS_PORT", "0") or 0)
CERT_HOSTS = [h.strip() for h in
              (os.environ.get("MEAL_PLANNER_CERT_HOSTS") or "").split(",") if h.strip()]

# Where the meal plan and photos are kept. Defaults to sitting next to the
# code, which is what you want when running from a folder on a PC. Containers
# (the Home Assistant add-on) set MEAL_PLANNER_DATA_DIR to a persistent volume,
# because anything written inside the image itself is lost on every update.
DATA_DIR = os.environ.get("MEAL_PLANNER_DATA_DIR") or BASE_DIR
DATA_FILE = os.path.join(DATA_DIR, "data.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")   # photos taken with the app live here
CERT_DIR = os.path.join(DATA_DIR, "certs")      # private CA + server certificate

os.makedirs(DATA_DIR, exist_ok=True)

_lock = threading.Lock()

DEFAULT_DATA = {
    "people": [],
    "meals": [],
    "weeks": {},
    # Things to buy that no recipe will ever mention: baking paper, foil, a
    # birthday candle. One standing list, not one per week - a thing you still
    # need on Sunday is a thing you still need on Monday, and a list that
    # emptied itself every seven days was quietly losing them.
    "extras": [],
    # Every extra ever typed, so the next one can be finished for you. Keyed by
    # a normalised form of the name; the value keeps the spelling as first
    # written.
    "extraNames": {},
}

# One line of shopping, not an essay.
MAX_EXTRA = 80
# The whole standing list, not one week of it. Higher than the old per-week
# ceiling because nothing expires it any more.
MAX_EXTRAS = 100

# How many remembered names to keep, and to offer. Two hundred covers years of
# a household's odds and ends, and is still a small thing to send with a list.
MAX_KNOWN_EXTRAS = 200

COLORS = [
    "#e07a5f", "#3d8361", "#5b7db1", "#c9a227", "#8e6fb0",
    "#d1698a", "#4aa3a3", "#b5651d", "#6b8e23", "#7a6ff0",
]

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return json.loads(json.dumps(DEFAULT_DATA))
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        # Corrupt file: back it up rather than lose it, and start clean.
        try:
            os.replace(DATA_FILE, DATA_FILE + ".corrupt")
        except OSError:
            pass
        return json.loads(json.dumps(DEFAULT_DATA))
    for key, default in DEFAULT_DATA.items():
        data.setdefault(key, json.loads(json.dumps(default)))
    for meal in data["meals"]:
        migrate_meal(meal)
    migrate_weeks(data)
    migrate_extras(data)
    ensure_guest(data)
    return data


def save_data(data):
    """Atomic-ish write: temp file then replace, so a crash can't truncate."""
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, DATA_FILE)


def mutate(fn):
    """Run fn(data) under a lock, re-reading from disk first so that
    simultaneous edits from different devices don't clobber each other."""
    with _lock:
        data = load_data()
        result = fn(data)
        save_data(data)
        return result


# --------------------------------------------------------------------------
# backups
#
# A dated copy of data.json is kept in the data directory so a bad edit is
# always recoverable without reaching for a full Home Assistant backup restore.
# This used to live in run.sh, but that only fired when the container started -
# an add-on that runs untouched for weeks made no new backups in between. It now
# runs on a timer inside the process, so it happens every day the app is up.
# --------------------------------------------------------------------------

BACKUP_PREFIX = "data.json.backup-"
BACKUP_KEEP = 7


def _prune_backups():
    try:
        names = [n for n in os.listdir(DATA_DIR) if n.startswith(BACKUP_PREFIX)]
    except OSError:
        return
    # The names end in YYYYMMDD, so a plain sort is chronological; drop all but
    # the newest BACKUP_KEEP.
    for name in sorted(names)[:-BACKUP_KEEP]:
        try:
            os.remove(os.path.join(DATA_DIR, name))
        except OSError:
            pass


def daily_backup():
    """Snapshot data.json at most once per calendar day, keeping the last week.

    Keyed on the dated filename, so calling it repeatedly is harmless and a
    restart never produces a duplicate. save_data() replaces the file
    atomically, so copying it without the lock still yields a whole snapshot."""
    if not os.path.exists(DATA_FILE):
        return
    dest = os.path.join(DATA_DIR, BACKUP_PREFIX + datetime.now().strftime("%Y%m%d"))
    if os.path.exists(dest):
        return
    try:
        shutil.copy2(DATA_FILE, dest)
    except OSError:
        return
    _prune_backups()


def _backup_loop():
    """Back up now, then re-check hourly. The once-a-day filename guard means the
    hourly tick makes a fresh snapshot shortly after each midnight and no more."""
    while True:
        try:
            daily_backup()
        except Exception:
            pass
        time.sleep(3600)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def new_id(prefix):
    return prefix + "_" + uuid.uuid4().hex[:10]


def monday_of(d):
    return d - timedelta(days=d.weekday())


def parse_week_key(value):
    """Accept any yyyy-mm-dd and snap it to that week's Monday."""
    if not value or not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return monday_of(date.today()).isoformat()
    y, m, dd = (int(x) for x in value.split("-"))
    try:
        return monday_of(date(y, m, dd)).isoformat()
    except ValueError:
        return monday_of(date.today()).isoformat()


def date_of(week_key, day):
    """The actual date a day of a stored week falls on. Week keys are always a
    Monday, so the day's position in DAYS is its offset."""
    try:
        monday = date(*(int(x) for x in week_key.split("-")))
    except (TypeError, ValueError):
        monday = monday_of(date.today())
    return monday + timedelta(days=DAYS.index(day) if day in DAYS else 0)


def blank_day():
    """A day has ONE cook and a list of 'sittings' - separate meals eaten that
    day by different groups. Whoever is cooking cooks everything that evening."""
    return {"cookId": None, "sittings": []}


def blank_week():
    return {day: blank_day() for day in DAYS}


def new_sitting(meal_id=None, eaters=None, note="", guests=0):
    return {
        "id": new_id("s"),
        "mealId": meal_id,
        "eaters": list(eaters or []),
        # How many extra mouths the guest slot stands for at this meal. Only
        # means anything while the guest is in `eaters`; see clamp_guests.
        "guests": clean_guests(guests),
        "note": note or "",
        # What the people who ate it thought: person id -> 1 to 5 stars.
        # Kept on the sitting, not on the meal, because the same recipe cooked
        # in March and again in August is two different dinners to rate - and
        # a meal deleted from the library shouldn't take the household's
        # opinion of the night they ate it with it.
        "ratings": {},
    }


MAX_STARS = 5


def drop_ratings(sitting):
    """Keep the ratings on a sitting to the people it still says ate it."""
    ratings = sitting.get("ratings")
    if not isinstance(ratings, dict):
        return
    eaters = set(sitting.get("eaters") or [])
    for pid in [p for p in ratings if p not in eaters]:
        del ratings[pid]


def clean_ratings(value, valid=None):
    """Ratings as they are allowed to be stored: whole stars from 1 to 5,
    against people who exist. Anything else is dropped rather than clamped -
    a rating nobody can account for is worse than no rating."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for pid, stars in value.items():
        if not isinstance(pid, str) or (valid is not None and pid not in valid):
            continue
        try:
            stars = int(stars)
        except (TypeError, ValueError):
            continue
        if 1 <= stars <= MAX_STARS:
            out[pid] = stars
    return out


# --------------------------------------------------------------------------
# guests
# --------------------------------------------------------------------------
#
# "Guest(s)" is a person in the household list with a number attached, rather
# than a number tucked away on the meal. It is on the toggles with everybody
# else, it takes a colour and a chip like everybody else, and the one thing it
# does differently is stand for more than one mouth.
#
# The count lives on the sitting rather than on the person, because six for
# dinner on Saturday says nothing about Tuesday.

GUEST_NAME = "Guest(s)"
MAX_GUESTS = 30          # a household planner, not a wedding caterer

# A fixed id, not a generated one. The slot is created on the way out of
# load_data, which runs on reads as well as writes, so a fresh uuid each time
# would give the guest a different id on every request - and a week saved
# against yesterday's id would quietly stop feeding anyone.
GUEST_ID = "p_guest"


def clean_guests(value):
    try:
        return max(0, min(MAX_GUESTS, int(value)))
    except (TypeError, ValueError):
        return 0


def guest_id(data):
    """The guest slot's person id, or None if there isn't one."""
    for person in data.get("people", []):
        if person.get("guest"):
            return person["id"]
    return None


def ensure_guest(data):
    """Make sure the household has its guest slot. Created on the way through
    rather than by a migration step, so it is there for a meal plan restored
    from an old backup as much as for a new one.

    Not created for a brand new, empty household: an app that opens on "you
    have one person, Guest(s)" is a puzzle, not a feature. It appears with the
    first real person."""
    people = data.setdefault("people", [])
    if not people or any(p.get("guest") for p in people):
        return data
    people.append({
        "id": GUEST_ID,
        "name": GUEST_NAME,
        "color": next_color(people),
        "guest": True,
    })
    return data


def head_count(sitting, guest, valid=None):
    """How many mouths a sitting feeds: everyone marked, with the guest slot
    counting for as many as it says. This is the number every quantity in the
    app is scaled by.

    `valid` is the set of people who still exist, so someone removed from the
    household doesn't go on being fed by a week planned before they left."""
    eaters = [e for e in (sitting.get("eaters") or [])
              if valid is None or e in valid]
    count = len([e for e in eaters if e != guest])
    if guest and guest in eaters:
        # A guest slot that is on but says nothing is one guest. Zero would
        # make an eater who feeds nobody, which is only ever a mistake.
        count += max(1, clean_guests(sitting.get("guests")))
    return count


def day_head_count(sittings, guest, valid=None):
    """How many people a whole day feeds - the number that goes beside the cook.

    Not the sum of the sittings' head counts. A day with two meals on it is one
    cook feeding a household twice, and someone who is marked for both is still
    one person; summing would tell the kitchen display that Tuesday feeds eleven
    when four people live here.

    So: distinct named people across the day, plus the guest slot counted once,
    at the largest number any single meal puts on it. Guests are anonymous, so
    there is no way to tell "the same two visitors at lunch and dinner" from
    "two at lunch and two more at dinner" - and of the two readings, the one
    that never double-counts is the one that can't produce a silly number.

    On a day with one meal, which is nearly every day, this is exactly
    head_count() of that meal. That equality is the point: the figure beside the
    cook and the figure the ingredients were scaled by must not disagree."""
    named, guests = set(), 0
    for sitting in sittings or []:
        # Type-checked rather than trusted. Unlike head_count(), which is only
        # ever handed a sitting the app just built, this one is given whatever
        # a day in data.json turned out to be - including shapes written by
        # versions that predate sittings entirely.
        if not isinstance(sitting, dict):
            continue
        raw = sitting.get("eaters")
        if not isinstance(raw, list):
            continue
        eaters = [e for e in raw if isinstance(e, str)
                  and (valid is None or e in valid)]
        named.update(e for e in eaters if e != guest)
        if guest and guest in eaters:
            guests = max(guests, max(1, clean_guests(sitting.get("guests"))))
    return len(named) + guests


def migrate_day(cell):
    """Upgrade a day saved by an older version. Two older shapes exist:
    a single meal on the day itself, and a list of meals each with its own
    cook. Both fold down to one cook for the day."""
    if not isinstance(cell, dict):
        return blank_day()

    if isinstance(cell.get("sittings"), list):
        cook = cell.get("cookId")
        out = []
        for sitting in cell["sittings"]:
            if not isinstance(sitting, dict):
                continue
            # A cook recorded against an individual meal becomes the day's cook.
            if cook is None and sitting.get("cookId"):
                cook = sitting["cookId"]
            out.append({
                "id": sitting.get("id") or new_id("s"),
                "mealId": sitting.get("mealId"),
                "eaters": [e for e in (sitting.get("eaters") or []) if isinstance(e, str)],
                "guests": clean_guests(sitting.get("guests")),
                "note": sitting.get("note") or "",
                # Absent on every week planned before 1.13.0, which is most of
                # them. An empty dict reads the same as "nobody has said yet".
                "ratings": clean_ratings(sitting.get("ratings")),
            })
        return {"cookId": cook, "sittings": out}

    # Oldest shape: mealId / cookId / eaters / note directly on the day.
    if cell.get("mealId") or cell.get("cookId") or cell.get("eaters") or cell.get("note"):
        return {"cookId": cell.get("cookId"),
                "sittings": [new_sitting(cell.get("mealId"), cell.get("eaters"),
                                         cell.get("note"))]}
    return blank_day()


def migrate_weeks(data):
    for key, week in list((data.get("weeks") or {}).items()):
        if not isinstance(week, dict):
            data["weeks"][key] = blank_week()
            continue
        for day in DAYS:
            week[day] = migrate_day(week.get(day))
        # Drop any stray keys that aren't real days.
        for stray in [k for k in week if k not in DAYS]:
            del week[stray]
    return data


DAY_NAMES = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
             "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}


# --------------------------------------------------------------------------
# extras - the things on the list that aren't food
# --------------------------------------------------------------------------
#
# Baking paper, foil, a bottle of washing-up liquid. One standing list that
# outlives the week you happen to be looking at: a thing you still need on
# Sunday is a thing you still need on Monday, and the old per-week store was
# silently dropping anything that wasn't bought in time.
#
# An entry leaves the list in one of two ways. Bought in a shop, it is gone the
# moment you say so - "Got it" deletes it. Ordered for delivery, it sits in an
# ordered group until the van turns up ("Arrived", also a delete) or doesn't
# ("Didn't arrive", which puts it back where it came from). Nothing is on a
# timer: an order that never came is exactly the thing you want the list to
# keep nagging about, and an order that came is one you told it about.
#
# Quantity is parsed off the front of what you type and stored on its own. That
# is not a nicety: the suggestions are trained on what has been typed before,
# and if "3 cucumbers" went in whole then "cucumber", "2 cucumbers" and
# "3 cucumbers" would be three competing entries and none of them right the
# week you want four.

# Plural endings worth undoing before two spellings of the same thing become
# two remembered entries. Order matters - longest suffix first.
_PLURALS = [("ies", "y"), ("ches", "ch"), ("shes", "sh"), ("sses", "ss"),
            ("xes", "x"), ("oes", "o"), ("s", "")]


def extra_key(name):
    """The form two spellings of one thing have to agree on: no case, no
    padding, no trailing punctuation, and singular. Only ever a lookup key -
    what gets shown is the Title Cased name, never this."""
    key = re.sub(r"\s+", " ", (name or "").strip().lower()).strip(" .,;:!?")
    for ending, replacement in _PLURALS:
        # "glass" is not the plural of "glas". Leave a doubled s alone and let
        # the "sses" rule above catch the real plural.
        if ending == "s" and key.endswith("ss"):
            break
        # Don't strip a word down to nothing. Three letters left for a bare s,
        # so "gas" and "bus" keep theirs; the longer endings can't fire on
        # anything that short anyway.
        least = 3 if ending == "s" else 2
        if key.endswith(ending) and len(key) - len(ending) >= least:
            return key[:-len(ending)] + replacement
    return key


def parse_extra(text):
    """Split "3 cucumbers" into (3, "each", "cucumbers") and "500g mince" into
    (500, "g", "mince").

    A word is only taken as a unit if the shopping list already knows it, so
    "2 chicken breasts" keeps its chicken: guessing wrong here turns a thing you
    can read into a thing you can't. Anything without a leading number is left
    exactly as typed, which is what keeps "a bunch of coriander" intact."""
    original = clean_str(text, MAX_EXTRA)
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*(.*)$", original)
    if not m:
        return 1.0, "each", original

    qty = float(m.group(1).replace(",", "."))
    rest = re.sub(r"^[x*]\s*", "", m.group(2).strip(), flags=re.I)

    unit = "each"
    um = re.match(r"^([A-Za-z]+)\.?\s+(.*)$|^([A-Za-z]+)\.?$", rest)
    if um:
        word = (um.group(1) or um.group(3) or "").lower()
        tail = (um.group(2) or "").strip()
        singular = word[:-1] if word.endswith("s") and word[:-1] in UNITS else word
        if singular in UNITS and not tail:
            # "500g" and nothing to weigh. A unit on its own names nothing, so
            # take the whole thing as typed and let them look at it.
            return 1.0, "each", original
        if singular in UNITS and tail:
            unit = singular
            # "3 packs of nappies" is three packs of nappies, not three packs
            # of "of nappies".
            rest = re.sub(r"^of\s+", "", tail, flags=re.I)

    name = clean_str(rest, MAX_EXTRA)
    if not name:
        # "500g" and nothing else. Whatever they meant, it wasn't a quantity of
        # nothing, so take the lot as the name.
        return 1.0, "each", original
    if qty <= 0:
        qty = 1.0
    return qty, unit, name


def remember_extra(data, name):
    """Keep the name for next time.

    Deliberately not forgotten when the thing is ticked off: bought is the
    opposite of irrelevant, and the whole point is that "bak" finds baking paper
    again in seven weeks. Counted, so the things this house really does buy come
    up before the one-off that was typed wrong in March.

    Keyed on the normalised name, so "Cucumber", "cucumbers" and "3 cucumbers"
    all land on the one entry. Stored Title Cased, so the suggestion reads the
    same as the line it will become - and so "bbq sauce" is remembered as
    "BBQ Sauce" however it was typed the first time."""
    names = data.setdefault("extraNames", {})
    if not isinstance(names, dict):
        names = data["extraNames"] = {}
    slot = extra_key(name)
    if not slot:
        return None
    name = title_case(name)
    entry = names.get(slot)
    if not isinstance(entry, dict):
        entry = names[slot] = {"item": name, "used": 0}
    entry["used"] = int(entry.get("used") or 0) + 1
    entry["at"] = date.today().isoformat()

    # Trim the tail: least used first, oldest of those first.
    if len(names) > MAX_KNOWN_EXTRAS:
        ordered = sorted(names.items(),
                         key=lambda kv: (int(kv[1].get("used") or 0), kv[1].get("at") or ""))
        for gone, _ in ordered[:len(names) - MAX_KNOWN_EXTRAS]:
            del names[gone]
    return entry


def known_extras(data):
    """The remembered names, most useful first: what gets typed most, then what
    was typed most recently. That order is the suggestion order.

    Bare names, never quantities - the number belongs to the shop you are going
    to today, not to the thing itself."""
    names = data.get("extraNames")
    if not isinstance(names, dict):
        return []
    usable = [v for v in names.values()
              if isinstance(v, dict) and clean_str(v.get("item"), MAX_EXTRA)]
    # Two passes rather than one clever key: dates are strings and can't be
    # negated, and Python's sort is stable, so the second pass keeps the first
    # one's order within each count.
    usable.sort(key=lambda v: v.get("at") or "", reverse=True)
    usable.sort(key=lambda v: -int(v.get("used") or 0))
    # Title Cased here too, so a name remembered before this existed suggests
    # itself in the spelling it will actually be added as.
    return [title_case(clean_str(v["item"], MAX_EXTRA))
            for v in usable[:MAX_KNOWN_EXTRAS]]


def clean_extra(entry):
    """One stored record, made safe to send. Never raises on a file written by
    hand: anything unreadable in a field falls back to the harmless value."""
    if not isinstance(entry, dict):
        return None
    # Title Cased on the way out, the same as an ingredient. Done here on the
    # read rather than only when something is added, so a line typed before this
    # existed tidies itself up the first time the list is looked at.
    name = title_case(clean_str(entry.get("item"), MAX_EXTRA))
    if not name:
        return None
    try:
        qty = float(entry.get("qty") or 1)
    except (TypeError, ValueError):
        qty = 1.0
    if qty <= 0:
        qty = 1.0
    unit = entry.get("unit") if entry.get("unit") in UNITS else "each"
    state = "ordered" if entry.get("state") == "ordered" else "need"
    return {
        "id": str(entry.get("id") or new_id("x")),
        "item": name,
        "qty": qty,
        "unit": unit,
        "state": state,
        # Only meaningful while ordered, and what the age on the row counts
        # from. Kept rather than cleared when something comes back to the
        # list, so "ordered on the 3rd, never came" survives the round trip.
        "orderedAt": clean_str(entry.get("orderedAt"), 32),
    }


def extras_list(data):
    """The standing list: still needed first in the order they were added, then
    the ordered ones, newest order at the top of that group."""
    stored = data.get("extras")
    if not isinstance(stored, list):
        return []
    out = []
    for entry in stored:
        cleaned = clean_extra(entry)
        if cleaned:
            out.append(cleaned)
    need = [e for e in out if e["state"] != "ordered"]
    ordered = [e for e in out if e["state"] == "ordered"]
    ordered.sort(key=lambda e: e.get("orderedAt") or "", reverse=True)
    return need + ordered


def find_extra(data, extra_id):
    for entry in data.get("extras") or []:
        if isinstance(entry, dict) and entry.get("id") == extra_id:
            return entry
    return None


def migrate_extras(data):
    """The old shape was {week key: [{id, item}]} - a separate little list for
    every Monday, thrown away when the week rolled over. Fold them all into the
    one standing list, newest week first, and merge the repeats: something
    written down three weeks running was the same thing wanted three times, not
    three things."""
    stored = data.get("extras")
    if isinstance(stored, list):
        return
    if not isinstance(stored, dict):
        data["extras"] = []
        return

    merged = []
    seen = {}
    for _, week in sorted(stored.items(), reverse=True):
        if not isinstance(week, list):
            continue
        for entry in week:
            if not isinstance(entry, dict):
                continue
            qty, unit, name = parse_extra(entry.get("item"))
            slot = extra_key(name)
            if not slot:
                continue
            if slot in seen:
                # Same thing on two weeks' lists. Keep the one record; don't
                # add the quantities, because two weeks apart they were two
                # separate askings, not a bigger ask.
                continue
            record = {"id": str(entry.get("id") or new_id("x")), "item": name,
                      "qty": qty, "unit": unit, "state": "need", "orderedAt": ""}
            seen[slot] = record
            merged.append(record)
    data["extras"] = merged[:MAX_EXTRAS]

    # The remembered names were keyed by raw lowercased text, so anything typed
    # with a number in front is sitting under the wrong key. Rebuild them.
    names = data.get("extraNames")
    if isinstance(names, dict):
        rebuilt = {}
        for value in names.values():
            if not isinstance(value, dict):
                continue
            _, _, name = parse_extra(value.get("item"))
            slot = extra_key(name)
            if not slot:
                continue
            existing = rebuilt.get(slot)
            if existing:
                existing["used"] = int(existing.get("used") or 0) + int(value.get("used") or 0)
                if (value.get("at") or "") > (existing.get("at") or ""):
                    existing["at"] = value.get("at")
                continue
            rebuilt[slot] = {"item": name, "used": int(value.get("used") or 0),
                             "at": value.get("at") or ""}
        data["extraNames"] = rebuilt


def kitchen_view(data, key, rolling=False, span=7):
    """Flatten some days into plain names and dates - no ids to look up.
    Used by the kitchen display and by Home Assistant.

    Normally that is the calendar week beginning at `key`, Monday to Sunday.
    With `rolling`, it is `span` days beginning today instead, which is what the
    kitchen display asks for: half a Monday-to-Sunday strip is spent on meals
    the house has already eaten, and a display on a wall is only ever asked
    what's next.

    A rolling window runs off the end of one stored week and into the next, so
    the day's plan is looked up per date rather than out of a single week.

    "Today" here is the display's today, which the rollover setting can move on
    to tomorrow before midnight: by nine in the evening the meal has been eaten
    and the useful question is what happens next. That shift applies only to
    the rolling window - the kitchen display, and nothing else. The calendar
    week keeps the calendar's answer, because a Home Assistant sensor or a
    shopping list that started talking about tomorrow at teatime would be a
    bug in every other part of the house."""
    people = {p["id"]: p["name"] for p in data["people"]}
    meals = {m["id"]: m for m in data["meals"]}
    settings = display.load()
    # Read here rather than in the payload literal so a bell.json that has gone
    # missing costs the display its button and nothing else. This feed is what
    # keeps the kitchen screen alive; nothing optional on it may be fatal.
    try:
        bell_settings = bell.load()
        bell_ready = bool(bell_settings["enabled"] and bell_settings["devices"]
                          and cast.configured())
        bell_button = bool(bell_settings["showButton"])
    except Exception:                                  # noqa: BLE001
        bell_ready, bell_button = False, False
    calendar_today = date.today()
    shift = timedelta(days=display.day_shift(settings)) if rolling else timedelta(0)
    today = (calendar_today + shift).isoformat()
    guest = guest_id(data)
    # The guest slot is never "not eating" - it isn't anybody until a meal says
    # how many of them there are.
    household = [p for p in data["people"] if not p.get("guest")]

    if rolling:
        # Nothing, or nonsense, means the default week. Otherwise anything from
        # a day to a fortnight: a strip with twenty columns on it is unreadable
        # from across a kitchen, which is the only place this is ever seen.
        span = max(1, min(14, int(span or 7)))
        start = calendar_today + shift
    else:
        span = len(DAYS)
        start = date.fromisoformat(key)

    days = []
    for i in range(span):
        on = start + timedelta(days=i)
        day_date = on.isoformat()
        day = DAYS[on.weekday()]
        week = data["weeks"].get(monday_of(on).isoformat(), blank_week())
        cell = week.get(day) or {}
        sittings = cell.get("sittings", [])
        entries, fed = [], set()

        for sitting in sittings:
            meal = meals.get(sitting.get("mealId"))
            marked = [e for e in sitting.get("eaters", []) if e in people]
            fed.update(marked)
            heads = head_count(sitting, guest, set(people))
            # The guest slot reads as what it stands for: "Alex, Sam, Jo and
            # 2 guests", not a fourth name that turns out to be five people.
            eaters = [people[e] for e in marked if e != guest]
            if guest and guest in marked:
                extra = max(1, clean_guests(sitting.get("guests")))
                eaters.append("%d guest%s" % (extra, "" if extra == 1 else "s"))
            if not meal and not eaters:
                continue          # a blank block someone hasn't filled in yet
            entries.append({
                "meal": meal["name"] if meal else None,
                "eaters": eaters,
                # What the eaters add up to. The names can't be counted for it
                # any more, now that one of them may stand for six.
                "headCount": heads,
                "guests": max(0, heads - len([e for e in marked if e != guest])),
                "note": sitting.get("note") or "",
                "tags": (meal or {}).get("tags", []),
                "image": (meal or {}).get("image") or None,
                # For the card's flip side: the ingredients this meal needs,
                # already scaled to the number sitting down to eat it.
                "serves": (meal or {}).get("serves"),
                "ingredients": meal_ingredient_lines(meal, heads) if meal else [],
            })

        days.append({
            "date": day_date,
            "day": day,
            "name": DAY_NAMES[day],
            "isToday": day_date == today,
            "cook": people.get(cell.get("cookId")),
            # How many the cook is cooking for. Sent even when nobody is
            # marked - zero is the display's cue to say nothing rather than
            # "for 0 people", and that decision belongs to the screen.
            "headCount": day_head_count(sittings, guest, set(people)),
            "meals": entries,
            "notEating": ([p["name"] for p in household if p["id"] not in fed]
                          if entries else []),
        })

    todays = [d for d in days if d["isToday"]]
    return {
        "week": monday_of(start).isoformat() if rolling else key,
        "from": days[0]["date"] if days else today,
        "rolling": bool(rolling),
        "today": today,
        # The real date, alongside the one the display is calling today. Only
        # ever different after the rollover time, and worth sending: a screen
        # showing Thursday on a Wednesday evening is either the setting working
        # or the Pi's clock being wrong, and there is no telling which from a
        # feed that reports one date.
        "date": calendar_today.isoformat(),
        # Sent with the plan rather than fetched separately: the display polls
        # this once a minute, and one call it already makes beats a second one
        # for the sake of a dozen small settings. It is also how a change made
        # on a phone reaches the Hub without anything being re-cast.
        "display": settings,
        # Whether to draw the "Dinner time!" button, and nothing else about the
        # bell: which speakers it rings is the app's business, not the Hub's.
        # Two booleans on a feed the display already asks for once a minute,
        # rather than a second endpoint for a button that is usually hidden.
        "bell": {"ready": bell_ready, "showButton": bell_button},
        "generated": datetime.now().isoformat(timespec="seconds"),
        "household": [p["name"] for p in data["people"]],
        "days": days,
        "todayMeals": todays[0]["meals"] if todays else [],
        "todayCook": todays[0]["cook"] if todays else None,
        "todayNotEating": todays[0]["notEating"] if todays else [],
    }


def round_up(qty, unit):
    """Round to something you can actually put in a trolley. Deliberately
    generous - over-buying a little beats being short mid-recipe."""
    if unit in WHOLE_UNITS:
        return float(math.ceil(qty - 0.001))
    if unit == "g":
        step = 10 if qty < 200 else (25 if qty < 1000 else 50)
        return float(int(math.ceil((qty - 0.001) / step) * step))
    if unit == "ml":
        step = 10 if qty < 200 else (50 if qty < 1000 else 100)
        return float(int(math.ceil((qty - 0.001) / step) * step))
    if unit in ("tbsp", "tsp"):
        return math.ceil((qty - 0.001) * 2) / 2.0      # nearest half spoon
    return round(qty, 2)


def pretty_qty(qty, unit):
    """'3 onions', '450g mince', '1.5 tbsp oil'."""
    if unit in ("g", "ml"):
        return "%g%s" % (qty, unit)
    # Spoons are stored as teaspoons; show tablespoons once there are enough.
    if unit == "tsp" and qty >= 3:
        tbsp = qty / 3.0
        return "%g tbsp" % (round(tbsp * 2) / 2.0)
    text = "%g" % qty
    if unit == "each":
        return text
    plural = unit
    if qty != 1 and unit in ("tin", "pack", "clove", "handful", "pinch",
                             "sprig", "bunch", "slice"):
        plural = unit + "s"
    return "%s %s" % (text, plural)


def meal_ingredient_lines(meal, eaters):
    """The ingredients for one meal, scaled straight from the recipe's own
    serving figure to however many are actually eating it - factor is
    eaters / serves (e.g. a meal that serves 4, eaten by 3, gives 0.75 of
    each line). Unlike the shopping list this is NOT rounded up to trolley
    quantities: it's what actually goes in the pan, so 0.75 stays 0.75.
    Returns [] when there's nothing to scale (no ingredients, no serves,
    or nobody eating)."""
    ings = meal.get("ingredients") or []
    serves = meal.get("serves")
    if not ings or not serves or eaters <= 0:
        return []
    factor = float(eaters) / float(serves)
    lines = []
    for ing in ings:
        unit = ing.get("unit") or ""
        qty = float(ing.get("qty") or 0) * factor
        # Whole grams and millilitres read better than long decimals in a pan.
        if unit in ("g", "ml"):
            qty = round(qty)
        lines.append({
            "qty": pretty_qty(qty, unit),
            "item": ing.get("item", ""),
            "note": ing.get("note") or "",
            "staple": bool(ing.get("staple")),
        })
    return lines


def shopping_list(data, key):
    """Everything the week's meals need, scaled by how many are eating each
    one, then summed so each item appears on a single line."""
    meals = {m["id"]: m for m in data["meals"]}
    people = {p["id"] for p in data["people"]}
    week = data["weeks"].get(key, blank_week())
    start = date.fromisoformat(key)
    guest = guest_id(data)

    totals = {}          # (item lowered, unit) -> record
    missing = []
    planned = 0

    for i, day in enumerate(DAYS):
        cell = week.get(day) or {}
        for sitting in cell.get("sittings", []):
            meal = meals.get(sitting.get("mealId"))
            if not meal:
                continue
            # Guests are shopped for like anyone else - that is the point of
            # them. Six for dinner is six portions whether or not three of them
            # live here.
            eaters = head_count(sitting, guest, people)
            if eaters == 0:
                continue                       # nobody eating it, so don't shop for it
            planned += 1

            serves = meal.get("serves")
            if not meal.get("ingredients") or not serves:
                missing.append({
                    "meal": meal["name"],
                    "mealId": meal["id"],
                    "day": DAY_NAMES[day],
                    "date": (start + timedelta(days=i)).isoformat(),
                    "eaters": eaters,
                    "why": ("no ingredients listed" if not meal.get("ingredients")
                            else "doesn't say how many it serves"),
                })
                continue

            factor = float(eaters) / float(serves)
            for ing in meal["ingredients"]:
                unit = ing["unit"]
                qty = ing["qty"] * factor
                # Fold kg into g and litres into ml so they add up.
                if unit in UNIT_BASE:
                    unit, mult = UNIT_BASE[unit]
                    qty *= mult
                slot = (ing["item"].strip().lower(), unit)
                rec = totals.get(slot)
                if rec is None:
                    rec = totals[slot] = {
                        "item": ing["item"].strip(),
                        "unit": unit,
                        "exact": 0.0,
                        "staple": ing.get("staple", False),
                        "meals": [],
                    }
                rec["exact"] += qty
                # An item is only a cupboard staple if every recipe treats it as one.
                rec["staple"] = rec["staple"] and ing.get("staple", False)
                label = "%s (%s)" % (meal["name"], DAY_NAMES[day][:3])
                if label not in rec["meals"]:
                    rec["meals"].append(label)

    items, staples = [], []
    for rec in totals.values():
        qty = round_up(rec["exact"], rec["unit"])
        entry = {
            "item": rec["item"],
            "qty": qty,
            "unit": rec["unit"],
            "text": pretty_qty(qty, rec["unit"]),
            "exact": round(rec["exact"], 2),
            "rounded": abs(qty - rec["exact"]) > 0.01,
            "meals": rec["meals"],
        }
        (staples if rec["staple"] else items).append(entry)

    items.sort(key=lambda x: x["item"].lower())
    staples.sort(key=lambda x: x["item"].lower())

    return {
        "week": key,
        "weekEnd": (start + timedelta(days=6)).isoformat(),
        "generated": datetime.now().isoformat(timespec="seconds"),
        "items": items,
        "staples": staples,
        # Sent with the list rather than fetched separately: it is the same
        # page and one round trip. The same standing list whichever week is on
        # screen - it is not part of the plan and never was.
        "extras": extras_list(data),
        # Everything ever typed into that box, for the suggestions under it.
        "knownExtras": known_extras(data),
        "missing": missing,
        "mealsPlanned": planned,
        "mealsCounted": planned - len(missing),
    }


def find_sitting(week, day, sitting_id):
    for sitting in week.get(day, {}).get("sittings", []):
        if sitting["id"] == sitting_id:
            return sitting
    return None


def clean_str(value, limit=200):
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


# Words are split on spaces plus the punctuation you actually get inside an
# ingredient name, so "semi-skimmed milk" and "salt/pepper" both come out right.
_WORD_SPLIT = re.compile(r"([\s\-/&]+)")

# Initialisms nobody bothers to shift-key when they are typing a shopping list.
# The all-caps rule below only *keeps* capitals that were already there, so
# without this "bbq sauce" comes out as "Bbq Sauce". Keyed on the letters alone
# so "bbq", "BBQ" and "(bbq)" all match. Keep this list short - every entry is a
# word that can no longer be spelled any other way.
_INITIALISMS = {
    "bbq": "BBQ",
    "uht": "UHT",
    "xl": "XL",
    "msg": "MSG",
    "ipa": "IPA",
    "pb": "PB",
}

_LETTER_RUN = re.compile(r"[A-Za-z]+")

# Joining words that look wrong with a capital in the middle of a name: "A Bunch
# Of Coriander" reads like a shop sign. Lowercased unless they open the name, so
# "Of" stays "of" but "Of The Day" still starts with a capital.
_SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on",
                "or", "per", "the", "to", "with"}


def title_case(text):
    """'chopped TOMATOES' -> 'Chopped Tomatoes'. Capitalises the first letter
    of every word and lowercases the rest, but leaves anything that looks like
    an acronym or a measurement alone ('BBQ sauce', '2% milk', "hershey's"),
    and keeps joining words small ('A Bunch of Coriander')."""
    parts = _WORD_SPLIT.split(text)
    out = []
    opening = True          # is the next word the first one in the name?
    for part in parts:
        if not part or _WORD_SPLIT.match(part):
            out.append(part)                       # a separator - keep as typed
            continue
        first, opening = opening, False
        letters = [c for c in part if c.isalpha()]
        # A known initialism, however it was typed. Substituted into the word so
        # any punctuation riding along with it ("bbq," or "(bbq)") survives.
        canonical = _INITIALISMS.get("".join(letters).lower())
        if canonical:
            out.append(_LETTER_RUN.sub(canonical, part, count=1))
            continue
        # Short all-caps runs are almost always acronyms (BBQ, UHT, XL).
        if letters and len(letters) <= 4 and all(c.isupper() for c in letters):
            out.append(part)
            continue
        # A joining word, and not the one the name opens with.
        if not first and "".join(letters).lower() in _SMALL_WORDS:
            out.append(part.lower())
            continue
        lowered = part.lower()
        for i, c in enumerate(lowered):
            if c.isalpha():
                out.append(lowered[:i] + c.upper() + lowered[i + 1:])
                break
        else:
            out.append(lowered)                    # no letters at all ("2%")
    return "".join(out)


def clean_links(value):
    """A meal can point at more than one page - a recipe, or the pack pages for
    each shop-bought component. Returns a list of {label, url}."""
    if not isinstance(value, list):
        return []
    out = []
    for entry in value[:6]:
        if isinstance(entry, str):
            entry = {"url": entry}
        if not isinstance(entry, dict):
            continue
        url = clean_str(entry.get("url"), 500)
        if not url.startswith("http://") and not url.startswith("https://"):
            continue
        label = clean_str(entry.get("label"), 40) or "Open recipe"
        out.append({"label": label, "url": url})
    return out


def sync_links(meal):
    """Keep the old single `link` field pointing at the first link, so anything
    still reading it carries on working."""
    links = meal.get("links") or []
    meal["link"] = links[0]["url"] if links else ""
    return meal


# Units the shopping list understands. Anything else is kept but never
# combined with a different unit, which is the safe thing to do.
UNITS = ["each", "g", "kg", "ml", "l", "tbsp", "tsp", "tin", "pack",
         "clove", "handful", "pinch", "sprig", "bunch", "slice"]

# Units where a fraction of one makes no sense in a shop.
WHOLE_UNITS = {"each", "tin", "pack", "clove", "slice", "bunch", "sprig"}

# Bigger units get folded into their base so quantities can be added up.
# Spoons are one family, so 1 tbsp from one recipe and 2 tsp from another
# become a single line rather than two.
UNIT_BASE = {"kg": ("g", 1000.0), "l": ("ml", 1000.0), "tbsp": ("tsp", 3.0)}


def clean_image(value):
    """A meal's picture: either a link to the recipe site's photo, or a path
    to a photo taken with the app and stored in the images folder."""
    v = clean_str(value, 500)
    if v.startswith("http://") or v.startswith("https://") or v.startswith("/images/"):
        return v
    return ""


def delete_meal_images(meal_id):
    if not os.path.isdir(IMAGES_DIR):
        return
    for name in os.listdir(IMAGES_DIR):
        if name.startswith(meal_id + "_"):
            try:
                os.remove(os.path.join(IMAGES_DIR, name))
            except OSError:
                pass


def decode_image(data_url):
    """Accept a data: URL or bare base64 and return raw bytes.

    Lived in the AI module until that came out, for the good reason that the
    photo estimate needed it too. It was always the ordinary upload path."""
    if not isinstance(data_url, str) or not data_url:
        raise RuntimeError("No photo was sent.")
    payload = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
    try:
        blob = base64.b64decode(payload, validate=False)
    except Exception:
        raise RuntimeError("That photo couldn't be read.")
    if len(blob) < 100:
        raise RuntimeError("That photo looks empty.")
    if len(blob) > 8 * 1024 * 1024:
        raise RuntimeError("That photo is too large.")
    return blob


def save_meal_image(meal_id, data_url):
    """Store an uploaded photo and return its serving path. The filename
    carries a timestamp so a replaced photo isn't hidden by browser caching."""
    blob = decode_image(data_url)             # validates size, raises RuntimeError
    os.makedirs(IMAGES_DIR, exist_ok=True)
    delete_meal_images(meal_id)               # one photo per meal
    name = "%s_%d.jpg" % (meal_id, int(datetime.now().timestamp()))
    with open(os.path.join(IMAGES_DIR, name), "wb") as fh:
        fh.write(blob)
    return "/images/" + name


def attach_image(meal_id, data_url):
    """Save the photo, then point the meal at it."""
    try:
        path = save_meal_image(meal_id, data_url)
    except RuntimeError:
        return None
    def set_img(data):
        for m in data["meals"]:
            if m["id"] == meal_id:
                m["image"] = path
                return m
        return None
    return mutate(set_img)


def clean_ingredients(value):
    """A recipe's ingredient list. Quantities are for the whole recipe, not
    per person - the shopping list scales them by how many are eating."""
    if not isinstance(value, list):
        return []
    out = []
    for entry in value[:60]:
        if not isinstance(entry, dict):
            continue
        # Stored in Title Case so every view - meal card, week flip side,
        # shopping list, kitchen display - reads the same however it was typed.
        item = title_case(clean_str(entry.get("item"), 80))
        if not item:
            continue
        try:
            qty = float(entry.get("qty"))
        except (TypeError, ValueError):
            qty = 0.0
        if qty != qty or qty < 0 or qty > 100000:
            qty = 0.0
        unit = clean_str(entry.get("unit"), 12).lower() or "each"
        if unit not in UNITS:
            unit = clean_str(entry.get("unit"), 12).lower() or "each"
        out.append({
            "item": item,
            "qty": round(qty, 3),
            "unit": unit,
            "staple": bool(entry.get("staple")),
            "note": clean_str(entry.get("note"), 80),
        })
    return out


def clean_serves(value, fallback=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return n if 1 <= n <= 50 else fallback


def migrate_meal(meal):
    if not isinstance(meal.get("links"), list):
        old = clean_str(meal.get("link"), 500)
        meal["links"] = ([{"label": "Open recipe", "url": old}]
                         if old.startswith("http") else [])
    else:
        meal["links"] = clean_links(meal["links"])
    meal.setdefault("macros", None)
    # Everything the estimates brought with them: how sure the guess claimed to
    # be, whether it was a guess at all, and the sentence it wrote about itself.
    # Nothing shows any of it now, and a meal from back then is not a different
    # kind of meal, so it is dropped as the file is read rather than carried
    # about for nobody. The numbers themselves are untouched.
    if isinstance(meal.get("macros"), dict):
        for gone in ("confidence", "source", "note"):
            meal["macros"].pop(gone, None)
    meal["ingredients"] = clean_ingredients(meal.get("ingredients"))
    meal["serves"] = clean_serves(meal.get("serves"))
    meal["image"] = clean_image(meal.get("image"))
    return sync_links(meal)


MACRO_LIMITS = {"calories": 5000, "protein": 500, "carbs": 500, "fat": 500}


def clean_macros(value):
    """Normalise a macro record. None means 'this meal has no nutrition info',
    which is perfectly valid - plenty of meals never get any."""
    if not isinstance(value, dict):
        return None
    out = {}
    for key, limit in MACRO_LIMITS.items():
        raw = value.get(key)
        if raw is None or raw == "":
            continue
        try:
            num = float(raw)
        except (TypeError, ValueError):
            continue
        if num != num or num < 0:
            continue
        out[key] = round(min(num, limit), 1)
    if "calories" not in out:
        return None
    for key in ("protein", "carbs", "fat"):
        out.setdefault(key, 0.0)

    # When they were last set. Nothing displays it, but it is the only record of
    # how old a figure is, and unlike the fields that came out with the
    # estimates it makes no claim that stopped being true.
    out["estimatedAt"] = clean_str(value.get("estimatedAt"), 40) or datetime.now().isoformat(timespec="seconds")
    return out


def next_color(people):
    used = {p.get("color") for p in people}
    for c in COLORS:
        if c not in used:
            return c
    return COLORS[len(people) % len(COLORS)]


_IPV4_HOST = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# The address a browser on the home network actually used to reach the planner,
# picked up from the Host header. This exists for casting: the Nest Hub has to
# fetch /kitchen itself, and lan_ip() inside a bridged container answers with the
# 172.30.x address Supervisor gave it, which is reachable from nothing else in
# the house. What a phone typed is known to work by definition.
SEEN_HOST = {"ip": "", "name": ""}

# Addresses that are true but useless to a device across the room.
_NOT_ROUTABLE = ("localhost", "127.0.0.1", "0.0.0.0")


def note_host(host_header):
    """Remember the address this request came in on. Called once per page load
    rather than per file, so it costs a split string and a compare."""
    host = (host_header or "").split(":")[0].strip().lower()
    if not host or host in _NOT_ROUTABLE or not usable_host(host):
        return
    if host.startswith("172.30.") or host.startswith("127."):
        return                      # Supervisor's own network, or loopback
    slot = "ip" if _IPV4_HOST.match(host) else "name"
    if SEEN_HOST[slot] != host:
        SEEN_HOST[slot] = host


def http_base():
    """The plain-http address this app is reachable at on the network, best
    guess first.

    An IPv4 a phone actually used beats everything: it is known to work from
    another device on this network. Home Assistant's own idea of its address
    comes next, because this add-on shares a machine with it. A hostname is
    third - a Nest Hub's mDNS is not something to rely on - and the container's
    own address is the last resort, and usually wrong.

    http and not https, always. Everything that asks for this address is a Cast
    device fetching something for itself - the kitchen page, the dinner chime -
    and none of them has been told to trust this app's certificate authority.
    A Nest Hub given an https URL it can't verify shows nothing and says
    nothing about why."""
    host = (SEEN_HOST["ip"] or cast.ha_host() or SEEN_HOST["name"] or lan_ip())
    return "http://%s:%d" % (host, PORT)


def kitchen_url():
    """The address to cast to the kitchen display."""
    return http_base() + "/kitchen"


def lan_ip():
    """Best-effort local network address (no traffic is actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# --------------------------------------------------------------------------
# request handling
# --------------------------------------------------------------------------

# Filled in by main() once the certificate exists. Empty means https is off.
# "hosts" is every name in the current certificate; "learned" is the subset
# picked up from real requests, which is what gets written to disk.
TLS_STATE = {"ca": None, "port": None, "fingerprint": "",
             "context": None, "hosts": [], "learned": []}
_tls_lock = threading.Lock()


# Addresses discovered by cover_host used to live only in memory, so every
# restart rebuilt the certificate from the startup list alone, silently dropped
# the real LAN address, and left already-set-up phones failing the handshake
# with no symptom beyond the app going quiet. They are remembered here instead.
LEARNED_HOSTS_FILE = os.path.join(CERT_DIR, "learned.hosts")
MAX_LEARNED_HOSTS = 12

# Hostname or IPv4, nothing else: no port, no IPv6, no path, no wildcard.
_HOST_OK = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
                      r"(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$")


def usable_host(host):
    """A Host header is client-controlled, and these end up both on disk and
    inside the certificate, so keep the shape strictly to what a phone on the
    LAN would actually send."""
    return bool(host) and len(host) <= 253 and bool(_HOST_OK.match(host))


def load_learned_hosts():
    """Addresses remembered from previous runs. Never fatal - a missing or
    unreadable file just means nothing has been learned yet."""
    try:
        with open(LEARNED_HOSTS_FILE, "r", encoding="utf-8") as fh:
            lines = [line.strip() for line in fh]
    except OSError:
        return []
    out = []
    for host in lines:
        if host and host not in out and usable_host(host):
            out.append(host)
    return out[:MAX_LEARNED_HOSTS]


def save_learned_hosts(hosts):
    """Temp file then replace, so a crash can't leave a half-written list."""
    try:
        os.makedirs(CERT_DIR, exist_ok=True)
        tmp = LEARNED_HOSTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(hosts[:MAX_LEARNED_HOSTS]) + "\n")
        os.replace(tmp, LEARNED_HOSTS_FILE)
    except OSError as exc:
        # The certificate is still correct for this run; only the memory of it
        # is lost, so carry on rather than taking https down over it.
        sys.stderr.write("meal-planner: could not remember certificate "
                         "addresses: %s\n" % exc)


def cover_host(host_header):
    """Make sure the certificate covers the address this page was reached on.

    Necessary because the add-on runs in a bridged container: it sees a docker
    address (172.30.x.x), not the 192.168.x.x one typed into the phone, so the
    address guessed at startup is usually the wrong one. The setup page is
    fetched over plain http on exactly the address that will then be used over
    https - so that request is the moment to learn it.

    Returns True if the certificate was reissued."""
    if not TLS_STATE.get("context"):
        return False
    host = (host_header or "").rsplit(":", 1)[0].strip()
    if not host or host in TLS_STATE["hosts"] or not usable_host(host):
        return False                      # blank, malformed, or already covered
    with _tls_lock:
        if host in TLS_STATE["hosts"]:    # another thread got there first
            return False
        if len(TLS_STATE["learned"]) >= MAX_LEARNED_HOSTS:
            sys.stderr.write("meal-planner: already remembering %d certificate "
                             "addresses, ignoring %s\n" % (MAX_LEARNED_HOSTS, host))
            return False
        hosts = TLS_STATE["hosts"] + [host]
        try:
            crt, key, _ca = tls.ensure(CERT_DIR, hosts)
            # Reloaded on the live context. The listening socket consults it at
            # every handshake, so new connections pick this up without a restart
            # - and existing ones are unaffected.
            TLS_STATE["context"].load_cert_chain(crt, key)
        except (tls.TLSUnavailable, ssl.SSLError, OSError) as exc:
            sys.stderr.write("meal-planner: could not add %s to the certificate: %s\n"
                             % (host, exc))
            return False
        TLS_STATE["hosts"] = hosts
        # Written only after the certificate actually reissued, so a host that
        # openssl rejected is not remembered and retried on every restart.
        TLS_STATE["learned"] = TLS_STATE["learned"] + [host]
        save_learned_hosts(TLS_STATE["learned"])
        return True


def setup_page(host_header, user_agent):
    """HTML for /setup - how to trust this server's certificate on a phone."""
    host = (host_header or "").split(":")[0] or lan_ip()
    port = TLS_STATE.get("port") or HTTPS_PORT
    https_url = "https://%s:%s/" % (host, port)
    ua = (user_agent or "").lower()
    apple = ("iphone" in ua or "ipad" in ua
             or ("mac os" in ua and "safari" in ua and "chrome" not in ua))

    esc = html.escape
    ready = bool(TLS_STATE.get("ca"))

    apple_steps = """
      <li>Tap <b>Download the certificate</b> above. Safari says
          &ldquo;This website is trying to download a configuration
          profile&rdquo; &mdash; allow it.</li>
      <li>Open <b>Settings</b>. Near the top you should see
          <b>Profile Downloaded</b> &mdash; tap it, then <b>Install</b>
          (top right), enter your passcode, and <b>Install</b> again.</li>
      <li>This next step is the one people miss. Go to
          <b>Settings &rsaquo; General &rsaquo; About &rsaquo; Certificate
          Trust Settings</b> and turn <b>on</b> the switch next to
          &ldquo;Home Meal Planner Local CA&rdquo;.</li>"""

    android_steps = """
      <li>Tap <b>Download the certificate</b> above and let it save.</li>
      <li>Open <b>Settings</b> and search for <b>CA certificate</b>. The path is
          usually <b>Security &rsaquo; More security settings &rsaquo;
          Encryption &amp; credentials &rsaquo; Install a certificate &rsaquo;
          CA certificate</b>.</li>
      <li>Tap <b>Install anyway</b>, then pick the downloaded
          <code>ca.crt</code>.</li>
      <li>Android will show a standing notice that the network may be monitored.
          That is expected with any private certificate and is harmless here
          &mdash; this one only signs the meal planner.</li>"""

    first, second = (("On an iPhone or iPad", apple_steps),
                     ("On an Android phone", android_steps))
    if not apple:
        first, second = (("On an Android phone", android_steps),
                         ("On an iPhone or iPad", apple_steps))

    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meal Planner &mdash; set up offline access</title>
<style>
 body {{ font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        margin: 0 auto; padding: 1.5rem 1.2rem 4rem; max-width: 34rem; color: #23201c;
        background: #f6f4ef; }}
 h1 {{ font-size: 1.35rem; margin: 0 0 .3rem; }}
 h2 {{ font-size: 1.05rem; margin: 2rem 0 .5rem; }}
 .muted {{ color: #6f6a62; }}
 .btn {{ display: block; text-align: center; background: #3d8361; color: #fff;
        padding: .85rem 1rem; border-radius: 12px; text-decoration: none;
        font-weight: 600; margin: 1.2rem 0; }}
 .off {{ background: #b03a2e; }}
 ol {{ padding-left: 1.2rem; }} li {{ margin: .55rem 0; }}
 code, .url {{ background: #efece5; padding: .15rem .35rem; border-radius: 5px;
        font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .9em;
        word-break: break-all; }}
 .fp {{ font-size: .78rem; }}
 .note {{ background: #fff6e8; border: 1px solid #f0d9b0; color: #6b4f1d;
        padding: .7rem .9rem; border-radius: 10px; font-size: .9rem; }}
</style></head><body>

<h1>Reading the week when you're out</h1>
<p class="muted">To keep a copy of the meal plan on your phone, the browser
insists on a secure (https) address. Home networks have no public name, so the
meal planner signs its own certificate &mdash; and your phone needs to be told,
once, that it trusts it.</p>

{banner}

<h2>1. Install the certificate</h2>
<a class="btn{off}" href="/ca.crt">Download the certificate</a>

<h2>2. {first_title}</h2>
<ol>{first_steps}</ol>

<h2>3. Open the app at its secure address</h2>
<p>Once the certificate is trusted, use this from now on:</p>
<p class="url">{https_url}</p>
<p class="muted">Then add it to your home screen &mdash; Share &rsaquo; Add to
Home Screen on iPhone, or the &#8942; menu &rsaquo; Install app on Android.
Open it once while you're at home and the week will still be there when you're
not.</p>

<h2 class="muted">{second_title}</h2>
<ol class="muted">{second_steps}</ol>

<p class="note">The old address <span class="url">http://{host}:{http_port}/</span>
keeps working exactly as before, and the kitchen display still uses it.</p>

<p class="muted fp">Certificate fingerprint (SHA-256):<br><code>{fp}</code></p>

</body></html>""".format(
        banner=("" if ready else
                '<p class="note"><b>https is not switched on yet.</b> In Home '
                'Assistant, open the Meal Planner add-on &rsaquo; Configuration, '
                'turn on <code>https_enabled</code>, Save and Restart. Then come '
                'back to this page.</p>'),
        off=("" if ready else " off"),
        first_title=esc(first[0]), first_steps=first[1],
        second_title=esc(second[0]), second_steps=second[1],
        https_url=esc(https_url), host=esc(host), http_port=PORT,
        fp=esc(TLS_STATE.get("fingerprint") or "not generated yet"))


class Handler(BaseHTTPRequestHandler):
    server_version = "HomeMealPlanner/1.0"

    # HTTP/1.1 keeps the connection open between requests. Without this the
    # default is HTTP/1.0, which closes the socket after every response - so a
    # phone on wifi paid a fresh TCP handshake for the page, the stylesheet, the
    # script and each API call in turn. Every response below sets an accurate
    # Content-Length, which is what makes this safe.
    protocol_version = "HTTP/1.1"

    # Don't let an idle kept-alive connection hold its thread forever.
    timeout = 30

    # TCP_NODELAY. BaseHTTPRequestHandler writes the headers and the body as two
    # separate sends, which is exactly the pattern Nagle's algorithm holds back
    # waiting for an ACK - about 40ms added to every single response, measured.
    # Nothing here is bandwidth-bound, so there is no reason to coalesce.
    disable_nagle_algorithm = True

    def log_message(self, fmt, *args):
        if os.environ.get("MEAL_PLANNER_QUIET"):
            return
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- plumbing ---------------------------------------------------------

    def _send(self, code, body=b"", content_type="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _error(self, code, message):
        self._json({"error": message}, code)

    def _body(self):
        # Anything not read off the socket would be parsed as the start of the
        # next request now that connections are kept alive, so a body we refuse
        # to read has to take the connection down with it.
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.close_connection = True
            return None
        if length <= 0:
            return None
        if length > 12_000_000:                  # generous: meal photos come through here
            self.close_connection = True
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _raw_body(self, limit):
        """The request body as bytes, for the one endpoint that isn't JSON.

        Read in chunks rather than one rfile.read(length): a backup carrying a
        few hundred photos arrives over house wifi and a single read of the
        whole thing is a long time to sit inside one call with nothing to say
        about it. Same rule as _body() about unread bodies - anything left on
        the socket would be parsed as the next request, so refusing to read one
        has to close the connection."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.close_connection = True
            return None
        if length <= 0 or length > limit:
            self.close_connection = True
            return None
        chunks, seen = [], 0
        while seen < length:
            chunk = self.rfile.read(min(262144, length - seen))
            if not chunk:
                self.close_connection = True
                return None
            chunks.append(chunk)
            seen += len(chunk)
        return b"".join(chunks)

    # -- static files -----------------------------------------------------

    TYPES = {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml",
        ".json": "application/json; charset=utf-8",
        ".webmanifest": "application/manifest+json; charset=utf-8",
        ".png": "image/png",
        ".ico": "image/x-icon",
        # The built-in dinner chime. Fetched by a Cast speaker rather than by a
        # browser, and a speaker handed the wrong content type doesn't play it.
        ".wav": "audio/wav",
    }

    # Friendly URLs, so the kitchen display is easy to type or cast.
    ALIASES = {"/": "index.html", "": "index.html",
               "/kitchen": "kitchen.html", "/kitchen/": "kitchen.html",
               "/preview": "preview.html", "/preview/": "preview.html"}

    def _serve_file(self, target, content_type, cache):
        """Send a file with an ETag so unchanged assets return a cheap 304
        instead of re-transferring the body. `cache` is the Cache-Control value."""
        try:
            st = os.stat(target)
        except OSError:
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        etag = '"%x-%x"' % (st.st_size, int(st.st_mtime))
        inm = self.headers.get("If-None-Match")
        if inm and etag in [t.strip() for t in inm.split(",")]:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self.end_headers()
            return
        with open(target, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("ETag", etag)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # Home-screen icons, drawn by icon.py rather than stored as files.
    ICONS = {"/icon-64.png": 64, "/icon-192.png": 192, "/icon-512.png": 512}

    def _colour_param(self, name, fallback):
        """An 'rrggbb' colour off the query string.

        The accent is a per-device setting in localStorage, which the phone's
        OS never sees when it fetches the manifest or an icon - so the page
        puts the colour it resolved into the URL instead. Sending the colour
        rather than an accent name keeps the palette in style.css alone."""
        for part in (urlparse(self.path).query or "").split("&"):
            if part.startswith(name + "="):
                return icon.parse_colour(unquote(part[len(name) + 1:]), fallback)
        return fallback

    def _serve_icon(self, size):
        bg = self._colour_param("c", icon.BG)          # accent
        fg = self._colour_param("f", icon.FG)          # --accent-ink, the cutlery
        etag = '"icon%d-%d-%02x%02x%02x-%02x%02x%02x"' % ((icon.REV, size) + bg + fg)
        if etag in [t.strip() for t in (self.headers.get("If-None-Match") or "").split(",")]:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            return
        body = icon.png(size, bg, fg)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=604800")
        self.send_header("ETag", etag)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_manifest(self):
        """The web app manifest, tinted to match this device's accent.

        static/manifest.webmanifest is the template - everything but the
        colours is edited there. `c` is the accent (the status bar and the
        task-switcher card), `f` what sits on top of it, `b` the page
        background (the launch splash). All three are resolved from the
        stylesheet by the page, so this follows light/dark and any accent added
        to style.css without changes here.

        Note what this can and cannot do. A phone reads the manifest when the
        app is installed; changing accent afterwards repaints the home screen
        only when the OS next re-checks it. Android does that on its own within
        a day or so. iOS never does - there the icon is fixed at the moment it
        was added, and only re-adding it will change it."""
        accent = self._colour_param("c", icon.BG)
        ink = self._colour_param("f", icon.FG)
        page = self._colour_param("b", (246, 244, 239))     # --bg, light theme
        try:
            with open(os.path.join(STATIC_DIR, "manifest.webmanifest"), "rb") as fh:
                manifest = json.loads(fh.read().decode("utf-8"))
        except (OSError, ValueError):
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return

        tint = "%02x%02x%02x" % accent
        query = "?c=%s&f=%02x%02x%02x" % ((tint,) + ink)
        manifest["theme_color"] = "#" + tint
        manifest["background_color"] = "#%02x%02x%02x" % page
        for entry in manifest.get("icons", []):
            src = entry.get("src", "")
            if src.startswith("/icon-"):
                entry["src"] = src + query

        # The icons this manifest names are about to be fetched; start drawing
        # them now rather than when the request for them arrives.
        icon.warm(accent, ink)

        self._send(200, json.dumps(manifest, indent=2),
                   "application/manifest+json; charset=utf-8")

    def _serve_setup(self):
        """A page explaining how to trust this server's certificate.

        Deliberately self-contained, with no script and no external stylesheet:
        it has to be readable on a phone that cannot yet load the app."""
        host_header = self.headers.get("Host") or ""
        cover_host(host_header)     # learn the address the phone actually uses
        body = setup_page(host_header, self.headers.get("User-Agent") or "")
        self._send(200, body, "text/html; charset=utf-8")

    def _serve_ca(self):
        """The root certificate, for installing on a phone.

        Served over plain http on purpose - it is a public certificate, and the
        device fetching it has no way to trust https from us yet. No
        Content-Disposition: iOS wants to hand this straight to the profile
        installer, and an attachment header sends it to Files instead."""
        cover_host(self.headers.get("Host") or "")
        if not TLS_STATE.get("ca"):
            self._send(404, "No certificate has been generated. Turn on "
                            "https_enabled in the add-on configuration.",
                       "text/plain; charset=utf-8")
            return
        try:
            with open(TLS_STATE["ca"], "rb") as fh:
                body = fh.read()
        except OSError:
            self._send(404, "Certificate not readable.", "text/plain; charset=utf-8")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-x509-ca-cert")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_static(self, path):
        if path in ("/setup", "/setup/"):
            self._serve_setup()
            return

        if path in ("/ca.crt", "/ca.pem"):
            self._serve_ca()
            return

        if path in self.ICONS:
            self._serve_icon(self.ICONS[path])
            return

        if path == "/manifest.webmanifest":
            self._serve_manifest()
            return

        # The uploaded dinner chime. Served here rather than out of static/
        # because it lives in /data, and cached hard for the same reason the
        # photos are: the name carries a timestamp and is never rewritten, so a
        # speaker that has heard it once needn't fetch it again.
        if path.startswith("/chime/"):
            target, ctype = bell.chime_file()
            wanted = path[len("/chime/"):]
            if not wanted or os.path.basename(target) != wanted:
                self._send(404, "Not found", "text/plain; charset=utf-8")
                return
            self._serve_file(target, ctype, "public, max-age=31536000, immutable")
            return

        if path.startswith("/images/"):
            target = os.path.normpath(os.path.join(IMAGES_DIR, path[len("/images/"):]))
            if not target.startswith(IMAGES_DIR) or not os.path.isfile(target):
                self._send(404, "Not found", "text/plain; charset=utf-8")
                return
            # Photo filenames carry a timestamp and are never rewritten in place,
            # so they can be cached hard. This stops the Nest Hub re-pulling every
            # meal photo each time the kitchen display re-casts.
            self._serve_file(target, "image/jpeg",
                             "public, max-age=31536000, immutable")
            return
        rel = self.ALIASES.get(path) or path.lstrip("/")
        target = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not target.startswith(STATIC_DIR) or not os.path.isfile(target):
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        ext = os.path.splitext(target)[1].lower()
        ctype = self.TYPES.get(ext, "application/octet-stream")
        # HTML/JS/CSS change on deploy - and live, in dev mode - so revalidate
        # via the ETag rather than caching blind. Unchanged files come back as a
        # 304 with no body; an edited file gets a new ETag and is refetched.
        self._serve_file(target, ctype, "no-cache")

    # -- verbs ------------------------------------------------------------

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            self._api_get(path)
        else:
            self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        # Taken here rather than in _api_write because that reads the body as
        # JSON before it looks at the path, and these two are raw bytes - a zip
        # and a sound file.
        if path in ("/api/restore", "/api/restore/check"):
            self._restore(path.endswith("/check"))
            return
        if path == "/api/bell/chime":
            self._chime_upload()
            return
        self._api_write("POST", path)

    def _chime_upload(self):
        """Take an uploaded dinner chime. The filename comes on the query
        string because the body is the file itself - there is no form parser
        here and a single file has never needed one."""
        raw = self._raw_body(bell.MAX_CHIME)
        if raw is None:
            # _raw_body refuses an oversized body rather than reading it, so
            # this is the only place that can tell the difference between "too
            # big" and "empty", and it is worth telling.
            return self._error(400, "That file didn't arrive, or it was bigger "
                                    "than the %d MB this accepts."
                                    % (bell.MAX_CHIME // 1_000_000))
        name = ""
        for part in (urlparse(self.path).query or "").split("&"):
            if part.startswith("name="):
                name = unquote(part[5:])
        try:
            bell.save_chime(name, raw or b"")
        except bell.ChimeError as exc:
            return self._error(400, str(exc))
        except OSError as exc:
            return self._error(500, "Couldn't save that sound: %s" % exc)
        return self._json(bell.status())

    def _restore(self, check_only):
        """Put a backup zip back. `check_only` reports what is in the file
        without writing anything, which is what the confirmation step asks."""
        raw = self._raw_body(backup.MAX_UPLOAD)
        if not raw:
            return self._error(400, "No file arrived, or it was too big to accept.")
        try:
            if check_only:
                found = backup.inspect(raw)
                found.pop("_names", None)
                return self._json(found)
            with _lock:
                # Under the same lock every other write takes, so a phone saving
                # a meal at the moment the folders are swapped waits its turn
                # rather than writing into the folder being replaced.
                result = backup.restore(raw)
        except backup.BackupError as exc:
            return self._error(400, str(exc))
        except OSError as exc:
            return self._error(500, "The restore couldn't finish: %s" % exc)
        # The certificate is the only part that was read into memory at startup,
        # so it is the only part that needs the app restarting.
        return self._json(result)

    def do_PUT(self):
        self._api_write("PUT", urlparse(self.path).path)

    def do_DELETE(self):
        self._api_write("DELETE", urlparse(self.path).path)

    # -- API --------------------------------------------------------------

    def _api_get(self, path):
        if path == "/api/data":
            # Once per page load, and the cheapest place to learn the address
            # this house reaches the planner on. See kitchen_url().
            note_host(self.headers.get("Host") or "")
            with _lock:
                data = load_data()
            data["today"] = date.today().isoformat()
            data["thisWeek"] = monday_of(date.today()).isoformat()
            self._json(data)
            return
        if path.startswith("/api/shopping"):
            query = urlparse(self.path).query
            wanted = ""
            for part in query.split("&"):
                if part.startswith("week="):
                    wanted = part[5:]
            key = parse_week_key(wanted or monday_of(date.today()).isoformat())
            with _lock:
                data = load_data()
            self._json(shopping_list(data, key))
            return
        if path.startswith("/api/kitchen"):
            # Everything a display needs in one call, with names already looked
            # up. Also handy for Home Assistant templates.
            #
            # `from=today` gives the rolling window the kitchen display asks
            # for. The calendar week stays the default, because anything else
            # reading this - a Home Assistant sensor, say - was written against
            # that and shouldn't change under it.
            query = urlparse(self.path).query
            wanted, rolling, span = "", False, 7
            for part in query.split("&"):
                if part.startswith("week="):
                    wanted = part[5:]
                elif part == "from=today":
                    rolling = True
                elif part.startswith("days="):
                    try:
                        span = int(part[5:])
                    except ValueError:
                        span = 7
            key = parse_week_key(wanted or monday_of(date.today()).isoformat())
            with _lock:
                data = load_data()
            self._json(kitchen_view(data, key, rolling=rolling, span=span))
            return
        if path == "/api/display":
            self._json(display.load())
            return

        # ---- backup ----
        #
        # What the Household tab shows before anyone presses anything: how much
        # there is to back up, and which undo snapshots a previous restore left
        # behind. Cheap - it counts files, it doesn't build the zip.
        if path == "/api/backup/info":
            self._json({"contents": backup._counts(),
                        "version": backup.app_version(),
                        "undo": backup.undo_files(),
                        "suggestedName": backup.suggested_name()})
            return

        # The download itself. Built in one go so it goes out with a
        # Content-Length and the phone can show real progress; a household's
        # photos come to tens of megabytes, which is worth a progress bar.
        if path == "/api/backup":
            name = backup.suggested_name()
            query = urlparse(self.path).query or ""
            if "undo=" in query:
                # Re-downloading an undo snapshot, so it can be kept somewhere
                # safer than the app it is protecting.
                wanted = unquote(query.split("undo=", 1)[1].split("&")[0])
                if (not wanted.startswith(backup.UNDO_PREFIX)
                        or not wanted.endswith(".zip")
                        or "/" in wanted or "\\" in wanted):
                    return self._error(400, "Not a snapshot this app made.")
                source = os.path.join(DATA_DIR, wanted)
                if not os.path.isfile(source):
                    return self._error(404, "That snapshot has been cleared away.")
                with open(source, "rb") as fh:
                    body = fh.read()
                name = wanted
            else:
                try:
                    body = backup.make_zip()
                except OSError as exc:
                    return self._error(500, "Couldn't read the data to back it "
                                            "up: %s" % exc)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition",
                             'attachment; filename="%s"' % name)
            # Contains the private CA key. Never let anything keep a copy.
            self.send_header("Cache-Control", "no-store, private")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        if path == "/api/cast":
            # Served out of cast.py's cache, so it can't block on a display that
            # has been unplugged - except with ?refresh=1, which is a person
            # pressing a button and waiting for the answer.
            if "refresh=1" in (urlparse(self.path).query or ""):
                self._json(cast.refresh())
            else:
                self._json(cast.status())
            return
        if path == "/api/bell":
            self._json(bell.status())
            return
        if path.startswith("/api/week/"):
            key = parse_week_key(path[len("/api/week/"):])
            with _lock:
                data = load_data()
            self._json({"week": key, "days": data["weeks"].get(key, blank_week())})
            return
        self._error(404, "Unknown endpoint")

    def _api_write(self, method, path):
        body = self._body()

        # ---- kitchen display ----
        if path == "/api/display" and method == "POST":
            try:
                saved = display.save(body or {})
            except OSError as exc:
                return self._error(500, "Couldn't save that: %s" % exc)
            # Everything else here reaches the display on its next poll, within
            # the minute. The casting hours are the exception: they are acted on
            # by the watcher, so widening them at half past ten should put the
            # week up now rather than at the top of the next tick.
            if any(k in (body or {}) for k in ("castWindow", "castFrom", "castTo")):
                cast.kick()
            return self._json(saved)

        if path == "/api/cast" and method == "POST":
            body = body or {}
            # `devices` is the list; `device` is the one-screen shape an older
            # copy of the app still in a phone's cache would send.
            if isinstance(body.get("devices"), list):
                wanted = [clean_str(x, 120) for x in body["devices"][:20]]
            else:
                one = clean_str(body.get("device"), 120)
                wanted = [one] if one else []
            try:
                cast.choose([x for x in wanted if x])
            except ValueError as exc:
                return self._error(400, str(exc))
            except OSError as exc:
                return self._error(500, "Couldn't save that: %s" % exc)
            return self._json(cast.status())

        # ---- dinner bell ----
        if path == "/api/bell" and method == "POST":
            try:
                bell.save(body or {})
            except OSError as exc:
                return self._error(500, "Couldn't save that: %s" % exc)
            # status() rather than what save() returned: the panel wants the
            # chime and whether the bell is ready as well as the switches, and
            # one answer means it can't show a half-updated card.
            return self._json(bell.status())

        if path == "/api/bell/ring" and method == "POST":
            # The one write here that touches the network on a request thread.
            # See bell.ring(): somebody pressed a button and is standing there.
            try:
                return self._json(bell.ring())
            except RuntimeError as exc:
                return self._error(409, str(exc))

        if path == "/api/bell/chime" and method == "DELETE":
            bell.clear_chime()
            return self._json(bell.status())

        # ---- people ----
        if path == "/api/people" and method == "POST":
            name = clean_str((body or {}).get("name"), 60)
            if not name:
                return self._error(400, "A name is required")
            def add(data):
                person = {"id": new_id("p"), "name": name, "color": next_color(data["people"])}
                data["people"].append(person)
                return person
            return self._json(mutate(add), 201)

        m = re.match(r"^/api/people/([\w]+)$", path)
        if m and method == "PUT":
            pid, name = m.group(1), clean_str((body or {}).get("name"), 60)
            if not name:
                return self._error(400, "A name is required")
            def rename(data):
                for p in data["people"]:
                    if p["id"] == pid:
                        p["name"] = name
                        return p
                return None
            result = mutate(rename)
            return self._json(result) if result else self._error(404, "No such person")

        if m and method == "DELETE":
            pid = m.group(1)
            with _lock:
                current = load_data()
            if any(p["id"] == pid and p.get("guest") for p in current["people"]):
                return self._error(
                    409, "The guest slot can't be removed - leave it off the "
                         "meals where nobody is visiting. You can rename it.")

            def remove(data):
                before = len(data["people"])
                data["people"] = [p for p in data["people"] if p["id"] != pid]
                # Scrub them from every planned week too.
                for week in data["weeks"].values():
                    for day in week.values():
                        if day.get("cookId") == pid:
                            day["cookId"] = None
                        for sitting in day.get("sittings", []):
                            sitting["eaters"] = [e for e in sitting["eaters"] if e != pid]
                            # Their ratings go with them. Left behind they
                            # would keep pulling the library's averages around
                            # on behalf of somebody who no longer eats here,
                            # and with no name to explain the number.
                            if isinstance(sitting.get("ratings"), dict):
                                sitting["ratings"].pop(pid, None)
                return before != len(data["people"])
            return self._json({"ok": True}) if mutate(remove) else self._error(404, "No such person")

        # ---- meals ----
        if path == "/api/meals" and method == "POST":
            body = body or {}
            name = clean_str(body.get("name"), 120)
            if not name:
                return self._error(400, "A meal name is required")
            links = clean_links(body.get("links"))
            if not links:
                single = clean_str(body.get("link"), 500)
                if single.startswith("http"):
                    links = [{"label": "Open recipe", "url": single}]
            meal = sync_links({
                "id": new_id("m"),
                "name": name,
                "notes": clean_str(body.get("notes"), 2000),
                "links": links,
                "tags": [clean_str(t, 30) for t in (body.get("tags") or []) if clean_str(t, 30)][:8],
                "macros": clean_macros(body.get("macros")),
                "ingredients": clean_ingredients(body.get("ingredients")),
                "serves": clean_serves(body.get("serves")),
                "image": clean_image(body.get("image")),
            })
            def add(data):
                if any(x["name"].lower() == name.lower() for x in data["meals"]):
                    return None
                data["meals"].append(meal)
                data["meals"].sort(key=lambda x: x["name"].lower())
                return meal
            result = mutate(add)
            if result and body.get("imageData"):
                result = attach_image(result["id"], body["imageData"]) or result
            return self._json(result, 201) if result else self._error(409, "That meal is already in the library")

        if path == "/api/meals/import" and method == "POST":
            raw = (body or {}).get("text") or ""
            if not isinstance(raw, str):
                return self._error(400, "Nothing to import")
            lines = [clean_str(line, 120) for line in raw.splitlines()]
            def bulk(data):
                added, skipped = [], []
                existing = {x["name"].lower() for x in data["meals"]}
                for line in lines:
                    if not line:
                        continue
                    # "Name | tag, tag | notes" - extra fields optional
                    parts = [p.strip() for p in line.split("|")]
                    name = parts[0][:120]
                    if not name or name.lower() in existing:
                        if name:
                            skipped.append(name)
                        continue
                    tags = []
                    notes = ""
                    if len(parts) > 1:
                        tags = [t.strip()[:30] for t in parts[1].split(",") if t.strip()][:8]
                    if len(parts) > 2:
                        notes = parts[2][:2000]
                    data["meals"].append({
                        "id": new_id("m"), "name": name, "notes": notes,
                        "link": "", "links": [], "tags": tags, "macros": None,
                        "ingredients": [], "serves": None,
                    })
                    existing.add(name.lower())
                    added.append(name)
                data["meals"].sort(key=lambda x: x["name"].lower())
                return {"added": added, "skipped": skipped}
            return self._json(mutate(bulk))

        m = re.match(r"^/api/meals/([\w]+)$", path)
        if m and method == "PUT":
            mid, body = m.group(1), (body or {})
            name = clean_str(body.get("name"), 120)
            if not name:
                return self._error(400, "A meal name is required")
            def update(data):
                for meal in data["meals"]:
                    if meal["id"] == mid:
                        meal["name"] = name
                        meal["notes"] = clean_str(body.get("notes"), 2000)
                        if "links" in body:
                            meal["links"] = clean_links(body.get("links"))
                        elif "link" in body:
                            single = clean_str(body.get("link"), 500)
                            meal["links"] = ([{"label": "Open recipe", "url": single}]
                                             if single.startswith("http") else [])
                        sync_links(meal)
                        if "image" in body and not body.get("imageData"):
                            meal["image"] = clean_image(body.get("image"))
                        if "ingredients" in body:
                            meal["ingredients"] = clean_ingredients(body.get("ingredients"))
                        if "serves" in body:
                            meal["serves"] = clean_serves(body.get("serves"), meal.get("serves"))
                        meal["tags"] = [clean_str(t, 30) for t in (body.get("tags") or []) if clean_str(t, 30)][:8]
                        if "macros" in body:
                            meal["macros"] = clean_macros(body.get("macros"))
                        data["meals"].sort(key=lambda x: x["name"].lower())
                        return meal
                return None
            result = mutate(update)
            if result and body.get("imageData"):
                result = attach_image(mid, body["imageData"]) or result
            return self._json(result) if result else self._error(404, "No such meal")

        if m and method == "DELETE":
            mid = m.group(1)
            def remove(data):
                before = len(data["meals"])
                data["meals"] = [x for x in data["meals"] if x["id"] != mid]
                delete_meal_images(mid)
                for week in data["weeks"].values():
                    for day in week.values():
                        for sitting in day.get("sittings", []):
                            if sitting.get("mealId") == mid:
                                sitting["mealId"] = None
                return before != len(data["meals"])
            return self._json({"ok": True}) if mutate(remove) else self._error(404, "No such meal")

        # ---- the plan itself ----

        # Who's cooking this evening. One cook per day, whatever's being made.
        m = re.match(r"^/api/week/(\d{4}-\d{2}-\d{2})/(\w+)$", path)
        if m and method == "PUT":
            key, day = parse_week_key(m.group(1)), m.group(2)
            if day not in DAYS:
                return self._error(400, "Unknown day")
            body = body or {}
            if "cookId" not in body:
                return self._error(400, "Nothing to change")

            def set_cook(data):
                week = data["weeks"].setdefault(key, blank_week())
                for d in DAYS:
                    if not isinstance(week.get(d), dict) or "sittings" not in week[d]:
                        week[d] = blank_day()
                cook_id = body.get("cookId")
                valid = {p["id"] for p in data["people"]}
                week[day]["cookId"] = cook_id if cook_id in valid else None
                return week[day]
            return self._json(mutate(set_cook))

        # Add another meal to a day (e.g. the kids are having something else).
        # An optional mealId puts the meal on it straight away, which is what
        # "Add to date" in the meal library sends: a POST followed by a PUT
        # would leave an empty block sitting on that day if the second call
        # failed. Without it the block starts blank, as the planner's own
        # "+ Add a meal" button expects.
        m = re.match(r"^/api/week/(\d{4}-\d{2}-\d{2})/(\w+)/sittings$", path)
        if m and method == "POST":
            key, day = parse_week_key(m.group(1)), m.group(2)
            if day not in DAYS:
                return self._error(400, "Unknown day")
            wanted_meal = (body or {}).get("mealId")

            def add_sitting(data):
                week = data["weeks"].setdefault(key, blank_week())
                for d in DAYS:
                    week.setdefault(d, blank_day())
                meal_id = wanted_meal if wanted_meal in {x["id"] for x in data["meals"]} else None
                sitting = new_sitting(meal_id)
                week[day]["sittings"].append(sitting)
                return sitting
            return self._json(mutate(add_sitting), 201)

        m = re.match(r"^/api/week/(\d{4}-\d{2}-\d{2})/(\w+)/sittings/([\w]+)$", path)
        if m and method == "PUT":
            key, day, sid = parse_week_key(m.group(1)), m.group(2), m.group(3)
            if day not in DAYS:
                return self._error(400, "Unknown day")
            body = body or {}

            def set_sitting(data):
                week = data["weeks"].setdefault(key, blank_week())
                for d in DAYS:
                    week.setdefault(d, blank_day())
                sitting = find_sitting(week, day, sid)
                if sitting is None:
                    return None

                valid_people = {p["id"] for p in data["people"]}
                valid_meals = {x["id"] for x in data["meals"]}

                if "mealId" in body:
                    meal_id = body.get("mealId")
                    sitting["mealId"] = meal_id if meal_id in valid_meals else None
                if "cookId" in body:
                    # The cook belongs to the day, not the meal. Accept it here
                    # anyway so older callers don't silently lose it.
                    cook_id = body.get("cookId")
                    week[day]["cookId"] = cook_id if cook_id in valid_people else None
                if "note" in body:
                    sitting["note"] = clean_str(body.get("note"), 300)
                guest = guest_id(data)
                if "guests" in body:
                    sitting["guests"] = clean_guests(body.get("guests"))
                if "eaters" in body and isinstance(body.get("eaters"), list):
                    eaters = [e for e in body["eaters"] if e in valid_people]
                    sitting["eaters"] = eaters
                    # Nobody eats two dinners: adding someone here takes them
                    # off any other meal that day. Guests are the exception -
                    # two friends at the early sitting and four relatives at the
                    # late one are not the same people twice.
                    moved = [e for e in eaters if e != guest]
                    for other in week[day]["sittings"]:
                        if other["id"] != sid:
                            other["eaters"] = [e for e in other["eaters"] if e not in moved]
                            drop_ratings(other)
                    # Taken off the meal, taken off the ratings: four stars
                    # from somebody the plan now says wasn't there is a number
                    # with nothing behind it.
                    drop_ratings(sitting)

                # A guest slot that has been turned off keeps no number: it
                # would come back with the old count next time it was toggled
                # on, which is how six people get cooked for by accident.
                if guest and guest not in (sitting.get("eaters") or []):
                    sitting["guests"] = 0
                elif guest and not sitting.get("guests"):
                    sitting["guests"] = 1
                return sitting

            result = mutate(set_sitting)
            return self._json(result) if result else self._error(404, "No such meal on that day")

        if m and method == "DELETE":
            key, day, sid = parse_week_key(m.group(1)), m.group(2), m.group(3)
            if day not in DAYS:
                return self._error(400, "Unknown day")
            def remove_sitting(data):
                week = data["weeks"].get(key)
                if not week or day not in week:
                    return False
                before = len(week[day]["sittings"])
                week[day]["sittings"] = [s for s in week[day]["sittings"] if s["id"] != sid]
                return before != len(week[day]["sittings"])
            return (self._json({"ok": True}) if mutate(remove_sitting)
                    else self._error(404, "No such meal on that day"))

        # What somebody thought of it. One person, one meal, one to five stars,
        # and its own endpoint rather than a field on the sitting PUT: that
        # handler moves eaters between meals as a side effect, and a rating is
        # the one write that should never rearrange the plan it is describing.
        m = re.match(r"^/api/week/(\d{4}-\d{2}-\d{2})/(\w+)/sittings/([\w]+)/rating$",
                     path)
        if m and method == "PUT":
            key, day, sid = parse_week_key(m.group(1)), m.group(2), m.group(3)
            if day not in DAYS:
                return self._error(400, "Unknown day")
            body = body or {}
            pid = body.get("personId")

            # Nobody can say what tomorrow's dinner was like. The check is here
            # as well as in the browser because the browser's clock is the
            # phone's, and a tablet left on the wrong date shouldn't be able to
            # seed the library with opinions of meals that haven't happened.
            on = date_of(key, day)
            if on > date.today():
                return self._error(400, "That meal hasn't been eaten yet.")

            stars = body.get("stars")
            if stars in (None, 0, ""):
                stars = None
            else:
                try:
                    stars = int(stars)
                except (TypeError, ValueError):
                    return self._error(400, "A rating is a number of stars.")
                if not 1 <= stars <= MAX_STARS:
                    return self._error(400, "Ratings run from 1 to %d stars." % MAX_STARS)

            def set_rating(data):
                week = data["weeks"].get(key)
                if not week:
                    return None
                sitting = find_sitting(week, day, sid)
                if sitting is None:
                    return None
                person = next((p for p in data["people"] if p["id"] == pid), None)
                # The guest slot stands for a variable number of people, so a
                # single star count against it would be nobody's opinion in
                # particular. Guests eat; the household rates.
                if person is None or person.get("guest"):
                    return "no-person"
                if pid not in (sitting.get("eaters") or []):
                    return "not-eating"
                ratings = sitting.setdefault("ratings", {})
                if stars is None:
                    ratings.pop(pid, None)
                else:
                    ratings[pid] = stars
                return sitting

            result = mutate(set_rating)
            if result == "no-person":
                return self._error(400, "Only people in the household can rate a meal.")
            if result == "not-eating":
                return self._error(400, "Only the people who ate it can rate it.")
            return (self._json(result) if result
                    else self._error(404, "No such meal on that day"))

        m = re.match(r"^/api/week/(\d{4}-\d{2}-\d{2})/clear$", path)
        if m and method == "POST":
            key = parse_week_key(m.group(1))
            def clear(data):
                data["weeks"][key] = blank_week()
                return data["weeks"][key]
            return self._json(mutate(clear))

        # ---- the standing list of extras ----
        #
        # Every one of these answers with the whole list rather than a patch.
        # It is a short list, it is one round trip either way, and two phones in
        # the same kitchen ticking things off at once should both end up looking
        # at what the file actually says.
        if path == "/api/extras" and method == "POST":
            typed = clean_str((body or {}).get("item"), MAX_EXTRA)
            if not typed:
                return self._error(400, "Type what you need first")
            qty, unit, name = parse_extra(typed)

            def add_extra(data):
                stored = data.setdefault("extras", [])
                if not isinstance(stored, list):
                    stored = data["extras"] = []
                remember_extra(data, name)

                # Already on the list and not yet ordered? Then this is more of
                # it, not another line saying the same thing. Only when the
                # units agree - 2 tins and 500g of the same word are two
                # different asks and adding them would invent a number.
                slot = extra_key(name)
                for entry in stored:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("state") == "ordered":
                        continue
                    if extra_key(entry.get("item")) == slot and \
                            (entry.get("unit") or "each") == unit:
                        entry["qty"] = float(entry.get("qty") or 1) + qty
                        return clean_extra(entry)

                if len(stored) >= MAX_EXTRAS:
                    return None
                entry = {"id": new_id("x"), "item": name, "qty": qty,
                         "unit": unit, "state": "need", "orderedAt": ""}
                stored.append(entry)
                return clean_extra(entry)

            added = mutate(add_extra)
            if not added:
                return self._error(400, "That's a long list - tick a few off "
                                        "before adding more.")
            return self._json(added, 201)

        # Ordered, or back from an order that never came. Takes a list of ids
        # because you don't order one thing at a time: you do a shop, and then
        # you tell the list about all of it at once.
        if path == "/api/extras/state" and method == "POST":
            body = body or {}
            ids = [str(i) for i in (body.get("ids") or []) if str(i)]
            state = "ordered" if body.get("state") == "ordered" else "need"
            if not ids:
                return self._error(400, "Nothing was selected")

            def set_state(data):
                stamp = date.today().isoformat()
                for entry in data.get("extras") or []:
                    if not isinstance(entry, dict) or entry.get("id") not in ids:
                        continue
                    entry["state"] = state
                    if state == "ordered":
                        entry["orderedAt"] = stamp
                return extras_list(data)

            return self._json({"ok": True, "extras": mutate(set_state)})

        # Got it, or Arrived. Both mean the same thing to the list - it is in
        # the house now - so both are this, and both are a delete. A list of
        # things you have already bought is just a longer list.
        if path == "/api/extras/done" and method == "POST":
            ids = [str(i) for i in ((body or {}).get("ids") or []) if str(i)]
            if not ids:
                return self._error(400, "Nothing was selected")

            def drop_extras(data):
                stored = data.get("extras")
                if not isinstance(stored, list):
                    return []
                data["extras"] = [e for e in stored
                                  if not (isinstance(e, dict)
                                          and e.get("id") in ids)]
                return extras_list(data)

            return self._json({"ok": True, "extras": mutate(drop_extras)})

        # The stepper on the row, for when three cucumbers turns out to be two.
        if path == "/api/extras/qty" and method == "POST":
            body = body or {}
            extra_id = str(body.get("id") or "")
            try:
                qty = float(body.get("qty"))
            except (TypeError, ValueError):
                return self._error(400, "That isn't a number")

            def set_qty(data):
                entry = find_extra(data, extra_id)
                if not entry:
                    return None
                # Stepped down to nothing means none needed, which means it has
                # no business being on the list at all.
                if qty <= 0:
                    data["extras"] = [e for e in data["extras"]
                                      if not (isinstance(e, dict)
                                              and e.get("id") == extra_id)]
                else:
                    entry["qty"] = qty
                return extras_list(data)

            updated = mutate(set_qty)
            if updated is None:
                return self._error(404, "No such item on the list")
            return self._json({"ok": True, "extras": updated})

        # Copy a whole week's plan onto another week.
        if path == "/api/week/copy" and method == "POST":
            body = body or {}
            src, dst = parse_week_key(body.get("from")), parse_week_key(body.get("to"))
            def copy(data):
                # The plan only. There is nothing else on a week to copy: the
                # extras are one standing list now and belong to no week in
                # particular, so there is nothing here to bring along.
                source = data["weeks"].get(src, blank_week())
                clone = json.loads(json.dumps(source))
                # Fresh ids, so editing the copy can't disturb the original.
                for day in clone.values():
                    for sitting in day.get("sittings", []):
                        sitting["id"] = new_id("s")
                data["weeks"][dst] = clone
                return clone
            return self._json(mutate(copy))

        self._error(404, "Unknown endpoint")


def start_https(ip):
    """Bring up the TLS listener. Returns the server, or None if https is off
    or the certificate could not be made.

    Never fatal: a meal planner reachable over http beats one that refused to
    start because openssl was unhappy."""
    if not HTTPS_PORT:
        return None
    # Addresses learned on previous runs go in from the start, so a restart
    # keeps covering whatever phones were actually set up against. Without this
    # the list changes, tls.ensure reissues, and the LAN address falls out.
    learned = load_learned_hosts()
    hosts = ([ip, "127.0.0.1", "localhost", "homeassistant.local",
              "meal-planner.local"] + CERT_HOSTS + learned)
    try:
        crt, key, ca = tls.ensure(CERT_DIR, hosts)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(crt, key)
        server = ThreadingHTTPServer(("0.0.0.0", HTTPS_PORT), Handler)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    except (tls.TLSUnavailable, ssl.SSLError, OSError) as exc:
        print("  HTTPS: could not start - %s" % exc)
        print("    Plain http is unaffected. Offline viewing on phones needs")
        print("    https, so it stays switched off until this is fixed.")
        sys.stdout.flush()
        return None

    TLS_STATE["ca"] = ca
    TLS_STATE["port"] = HTTPS_PORT
    TLS_STATE["fingerprint"] = tls.fingerprint(ca)
    TLS_STATE["context"] = context
    TLS_STATE["hosts"] = hosts
    TLS_STATE["learned"] = learned
    return server


def main():
    os.chdir(BASE_DIR)
    threading.Thread(target=_backup_loop, daemon=True, name="daily-backup").start()
    icon.warm()          # draw the home-screen icons off the request path
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ip = lan_ip()
    secure = start_https(ip)
    print("")
    print("  Home Meal Planner is running.")
    print("")
    print("  On this computer:      http://localhost:%d" % PORT)
    print("  On phones / tablets:   http://%s:%d" % (ip, PORT))
    print("  Kitchen display:       http://%s:%d/kitchen" % (ip, PORT))
    if secure:
        print("")
        print("  Secure address:        https://%s:%d" % (ip, HTTPS_PORT))
        print("  Set a phone up at:     http://%s:%d/setup" % (ip, PORT))
        print("    Each phone installs the certificate from that page once.")
        print("    Until it does, https warns and offline viewing stays off.")
    print("")
    print("  Meals are saved to: %s" % DATA_FILE)

    # Started after the banner because it makes an HTTP call of its own on the
    # first tick, and nothing about the app should wait on Home Assistant.
    if cast.start(kitchen_url):
        chosen = cast.targets()
        if chosen:
            print("  Kitchen display: keeping %s on %s"
                  % (", ".join(chosen), kitchen_url()))
        else:
            print("  Kitchen display: no Cast device chosen yet (Settings tab).")

    # No thread and no network: the bell only ever acts when somebody presses
    # it. All this hands over is how to work out the address a speaker should
    # fetch the chime from.
    bell.start(http_base)
    ringers = bell.load()
    if cast.configured() and ringers["enabled"] and ringers["devices"]:
        print("  Dinner bell: ringing %s" % ", ".join(ringers["devices"]))

    print("")
    print("  Leave this window open. Press Ctrl+C to stop.")
    print("")
    sys.stdout.flush()

    # The https listener runs in a thread; http keeps the main one, so Ctrl+C
    # and the add-on's stop signal behave exactly as they did before.
    if secure:
        threading.Thread(target=secure.serve_forever, daemon=True,
                         name="https").start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()
        if secure:
            secure.shutdown()
            secure.server_close()


if __name__ == "__main__":
    main()
