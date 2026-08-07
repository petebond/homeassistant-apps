"""
Putting the kitchen display on a Google Cast screen, through Home Assistant.

Why through Home Assistant: casting is a protobuf conversation over TLS that
nothing in the standard library can hold, and this app has no dependencies to
spend on one. Home Assistant is already on the same network, already knows every
Cast device in the house, and - with the DashCast custom integration installed -
already knows how to put a web page on one. So this module is a thin client for
that. It asks Supervisor's proxy to the core API which displays exist, and asks
DashCast to load /kitchen on whichever one was chosen.

Two things it deliberately does not do:

- **It does not fight anyone for the screen.** A Nest Hub is also a photo frame,
  a timer and a speaker, and an add-on that re-cast every thirty seconds would
  take it away mid-song. The watcher only steps in when the display is idle or
  showing its ambient screen. Anything that is actually playing is left alone
  until it finishes. The same restraint applies to the casting hours set in the
  app (display.casting_open): outside them nothing is taken over, and the only
  screen ever handed back is one still showing our own page.
- **It never touches the network on a request thread.** Everything the app shows
  comes out of a cache the watcher fills, for the same reason ai.status() does:
  a display that has been unplugged must not turn into a blank page on a phone.

Nothing here is required for the planner to work. No Supervisor token (running
on a PC rather than as an add-on), no DashCast, no device chosen - each just
means casting reports itself as off, and the rest of the app carries on.
"""

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import display

# The Supervisor's proxy to the Home Assistant core API. The token is handed to
# the add-on by Supervisor itself, but only when config.yaml asks for
# `homeassistant_api: true` - so its absence is also the "not running as an
# add-on" signal.
CORE_API = "http://supervisor/core/api"
TOKEN = (os.environ.get("SUPERVISOR_TOKEN") or "").strip()

DATA_DIR = os.environ.get("MEAL_PLANNER_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
CHOICE_FILE = os.path.join(DATA_DIR, "cast.json")

# Set in the add-on's Configuration panel. Devices named there pin the choice
# and the app's own picker goes read-only, so there is never a question of which
# of the two won. Comma separated, because a house can have more than one
# screen. Empty - the default - leaves the choice to the app.
PINNED = (os.environ.get("MEAL_PLANNER_CAST_DEVICE") or "").strip()
FIXED_URL = (os.environ.get("MEAL_PLANNER_CAST_URL") or "").strip()

# How often to look at the display, and the least time between two casts. The
# gap matters: a display that never reports DashCast back would otherwise be
# re-cast on every tick.
CHECK_EVERY = 60.0
MIN_BETWEEN_CASTS = 150.0
HTTP_TIMEOUT = 6.0

# After this many casts that the display never acknowledged, stop and say so.
# Something is wrong that trying again won't fix - the wrong kind of device, a
# URL it can't reach - and a quiet loop every minute is no way to find out.
MAX_UNACKNOWLEDGED = 3

# How many passes in a row must agree before bad news about a display is
# believed - both "there are no devices at all" and "this particular one isn't
# there any more".
#
# Adding or removing a device in the Google Home app reloads Home Assistant's
# Cast integration, and for a few seconds either side of that every answer here
# is wrong in the same direction: a template renders "no devices" perfectly
# successfully, and an entity that is about to be registered again 404s in the
# meantime. One such answer is not news. Two of them a minute apart is.
CONFIRM_PASSES = 2


class Gone(RuntimeError):
    """A chosen display that Home Assistant doesn't have any more.

    Its own class because it wants opposite handling from every other trouble
    here: an unplugged Hub or a restarting Home Assistant is temporary and worth
    retrying, but an entity that has been removed from the registry will 404
    every minute until somebody un-ticks it. That is not a reason to slow the
    watcher down for the displays that are working, so this is collected and
    reported rather than raised out of a pass."""

# DashCast's receiver application. The state machine below only needs to know
# "is this ours"; the id is the reliable half of that, the name the readable one.
DASHCAST_APP_ID = "84912283"
DASHCAST_APP_NAMES = ("dashcast", "dash cast")

# Apps that mean "nobody is using this screen". Backdrop is the photo frame a
# Nest Hub falls back to, and is by far the most common thing to take over from.
IDLE_APPS = ("", "backdrop", "default media receiver", "google cast backdrop")
IDLE_STATES = ("off", "idle", "standby", "unknown")

# Cast devices that can't show a web page. Speakers are Cast devices in every
# other respect and sit in the same list, so without this a kitchen with three
# Minis in it offers five "displays", three of which do nothing at all.
#
# Home Assistant's own answer comes first: the Cast integration marks audio
# devices and speaker groups with a device class. The model name from the device
# registry is the second opinion, and the useful one for a device that is
# switched off - a state can lose its attributes, but a registry entry doesn't
# go anywhere. What the device is *called* is deliberately not consulted: a Hub
# named "Kitchen Speaker" is still a screen.
AUDIO_ONLY_CLASSES = ("speaker", "receiver")
AUDIO_MODELS = ("mini", "audio", "home speaker", "homepod", "sonos", "soundbar",
                "google home", "nest audio", "nest mini", "group")
VIDEO_MODELS = ("hub", "display", "chromecast", "tv", "shield", "nest wifi point")

_lock = threading.Lock()
_state = {
    "checked": 0.0,        # when the watcher last managed to reach HA
    "devices": [],         # [{entityId, name, video, showing, state}]
    "known": {},           # entity id -> the last full record seen for it
    "guessed": False,      # whether `devices` came from the fallback sweep
    "empty": 0,            # consecutive passes that found nothing at all
    "misses": {},          # entity id -> consecutive passes it wasn't there
    "gone": [],            # chosen ids Home Assistant no longer has
    "showing": {},         # entity id -> what that display is showing now
    "castAt": {},          # entity id -> when we last asked it to load the page
    "unacknowledged": {},  # entity id -> casts it never reported back
    "error": "",           # last thing that went wrong, for the app to show
    "domain": "",          # dash_cast or dashcast, whichever is installed
    "haHost": None,        # what Home Assistant calls itself; None = not asked
    "open": True,          # whether the last pass was inside the casting hours
}

_url_source = None         # set by start(); returns the URL to cast


# --------------------------------------------------------------------------
# talking to Home Assistant
# --------------------------------------------------------------------------

def configured():
    """Whether there is any point trying. False on a PC, where there is no
    Supervisor and casting is somebody else's problem."""
    return bool(TOKEN)


def _call(path, payload=None, timeout=HTTP_TIMEOUT):
    """GET, or POST when there is a payload. Raises on anything but success -
    every caller here is inside the watcher thread, which turns exceptions into
    a message for the app rather than letting them out."""
    req = urllib.request.Request(
        CORE_API + path,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + TOKEN,
                 "Content-Type": "application/json"},
        method="GET" if payload is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = res.read().decode("utf-8", "replace")
    return json.loads(body) if body.strip() else None


def _service_domain():
    """Which DashCast is installed. AlexxIT's fork registers `dash_cast` and the
    original registers `dashcast`; both spell the service `load_url` and take
    the same fields, so either will do and the only question is which is there.

    Looked up once and remembered: an integration doesn't appear halfway through
    an evening, and this is on the path of every cast."""
    if _state["domain"]:
        return _state["domain"]
    services = _call("/services") or []
    names = set()
    for entry in services:
        if isinstance(entry, dict) and entry.get("domain"):
            names.add(entry["domain"])
    for candidate in ("dash_cast", "dashcast"):
        if candidate in names:
            _state["domain"] = candidate
            return candidate
    raise RuntimeError(
        "DashCast isn't installed in Home Assistant. Add AlexxIT/DashCast "
        "through HACS, restart Home Assistant, and this will find it.")


def _has_screen(device_class, model):
    """Whether this Cast device can show a web page at all.

    Home Assistant's device class is the first authority: the Cast integration
    marks audio devices and speaker groups as speakers. The model from the
    device registry settles the rest, and is the half that still works for a
    device that is switched off, since a registry entry keeps its model when a
    state has lost its attributes.

    Unknown is treated as a screen. Offering a speaker that quietly does nothing
    is a small annoyance; hiding the display someone is looking for is the bug
    this whole picker had a fortnight ago."""
    if str(device_class or "").lower() in AUDIO_ONLY_CLASSES:
        return False
    text = str(model or "").lower()
    if any(word in text for word in VIDEO_MODELS):
        return True
    return not any(word in text for word in AUDIO_MODELS)


# One question, asked of Home Assistant, about every entity the Cast integration
# owns. `device_attr` reads the device registry, which is why the model survives
# the device being off; `to_json` is what makes the answer parseable rather than
# a Python repr with single quotes in it.
_DEVICE_TEMPLATE = (
    "{% set out = namespace(rows=[]) %}"
    "{% for e in integration_entities('cast') %}"
    "{% set out.rows = out.rows + [{"
    "'entity_id': e,"
    "'name': state_attr(e, 'friendly_name') or e,"
    "'device_class': state_attr(e, 'device_class'),"
    "'model': device_attr(e, 'model'),"
    "'state': states(e),"
    "'app': state_attr(e, 'app_name')"
    "}] %}"
    "{% endfor %}"
    "{{ out.rows | to_json }}"
)


def _ask_ha_for_devices():
    """The Cast devices, as Home Assistant describes them.

    Asked with a template rather than assembled from /states, because the two
    things worth knowing about a display that is switched off - that it exists,
    and what model it is - are both missing from its state. Home Assistant
    leaves out attributes that are None, which is what once made an idle Hub
    invisible here.

    Returns None if the template can't be rendered, which is a different answer
    from an empty list: "Home Assistant wouldn't say" and "there are none" want
    opposite behaviour from the caller."""
    try:
        rows = _call("/template", {"template": _DEVICE_TEMPLATE})
    except Exception:                                  # noqa: BLE001
        return None
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except ValueError:
            return None
    return rows if isinstance(rows, list) else None


def _fetch_devices():
    """Every Cast device in the house, screens first, and whether the answer was
    guessed.

    Falls back to every media player Home Assistant has when the template can't
    be rendered - a list with a Sonos in it that DashCast will refuse is a
    nuisance, a list missing the display someone is looking for is a bug.

    But that sweep is a poor list: /states carries no model, and it omits
    device_class for anything switched off, so _has_screen has nothing to go on
    and calls almost everything a screen. Harmless as a cold start, wrong as a
    replacement for a list the Cast integration has already given us - which is
    exactly what it would be during the reload that adding or removing a device
    in the Google Home app causes. Hence the flag: the caller keeps the better
    answer when it has one."""
    rows = _ask_ha_for_devices()
    guessed = rows is None
    if rows is None:
        rows = []
        for entity in (_call("/states") or []):
            entity_id = entity.get("entity_id") or ""
            if not entity_id.startswith("media_player."):
                continue
            attrs = entity.get("attributes") or {}
            rows.append({"entity_id": entity_id,
                         "name": attrs.get("friendly_name") or entity_id,
                         "device_class": attrs.get("device_class"),
                         "model": None,
                         "state": entity.get("state"),
                         "app": attrs.get("app_name")})

    found = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entity_id = str(row.get("entity_id") or "")
        if not entity_id.startswith("media_player."):
            continue
        found.append({
            "entityId": entity_id,
            "name": str(row.get("name") or entity_id),
            "model": str(row.get("model") or ""),
            "video": _has_screen(row.get("device_class"), row.get("model")),
            "state": str(row.get("state") or ""),
            "showing": str(row.get("app") or ""),
        })
    found.sort(key=_order)
    return found, guessed


def _order(device):
    """Screens first, then alphabetically. Used for the fetched list and again
    when chosen-but-absent displays are folded back into it."""
    return (not device.get("video"), str(device.get("name") or "").lower())


def _forgotten(misses):
    """The entity ids that have missed enough passes in a row to be believed
    gone rather than merely slow. Call with _lock held."""
    return {key for key, count in misses.items() if count >= CONFIRM_PASSES}


def _remember_devices(devices, guessed, chosen):
    """Store what the last look found.

    Two things it declines to do, both for the same reason - the Cast
    integration reloading under it:

    - Replace a list that came from the integration with one swept out of
      /states. See _fetch_devices.
    - Empty the list on the strength of a single pass that found nothing.

    Also keeps the last full record of every device it has seen, so a display
    that is chosen but temporarily absent can still be shown by the name and
    model it had, rather than as a bare entity id."""
    with _lock:
        _state["checked"] = time.time()
        if guessed and _state["devices"] and not _state["guessed"]:
            return
        if devices:
            _state["empty"] = 0
        elif _state["devices"]:
            _state["empty"] += 1
            if _state["empty"] < CONFIRM_PASSES:
                return
            _state["empty"] = 0
        _state["devices"] = devices
        _state["guessed"] = guessed
        for device in devices:
            _state["known"][device["entityId"]] = dict(device)
        # Remembered for as long as it is either present or chosen; a device
        # that is neither is nobody's business.
        keep = set(chosen) | {d["entityId"] for d in devices}
        for key in [k for k in _state["known"] if k not in keep]:
            del _state["known"][key]


def ha_host():
    """The address Home Assistant tells people to use for itself, minus the
    port. Worth asking because it is nearly always the Pi's LAN address typed by
    the person who set the house up - and this add-on runs on the same machine,
    so the same address plus port 8080 reaches the planner.

    Cached until it answers: this is only consulted when no better address is
    known, and it must not become a call on every cast."""
    if _state["haHost"] is not None:
        return _state["haHost"]
    host = ""
    try:
        config = _call("/config") or {}
        for field in ("internal_url", "external_url"):
            value = str(config.get(field) or "")
            if value.startswith("http"):
                host = urllib.parse.urlsplit(value).hostname or ""
                if host:
                    break
    except Exception:                                  # noqa: BLE001
        return ""                                      # not cached: try again later
    _state["haHost"] = host
    return host


def _device_state(entity_id):
    try:
        entity = _call("/states/" + entity_id)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Removed from the Home, or renamed - a device taken out and put
            # back usually comes back as a new entity id and leaves this one
            # behind. "HTTP Error 404" in the app would send someone looking in
            # entirely the wrong place.
            raise Gone(
                "Home Assistant has no %s any more. Pick the display again."
                % entity_id) from None
        raise
    attrs = (entity or {}).get("attributes") or {}
    return {
        "state": str((entity or {}).get("state") or "").lower(),
        "appId": str(attrs.get("app_id") or ""),
        "appName": str(attrs.get("app_name") or ""),
    }


# --------------------------------------------------------------------------
# which display, and what to put on it
# --------------------------------------------------------------------------

def _split(text):
    """A comma separated list of entity ids, from the add-on option."""
    return [part.strip() for part in str(text or "").split(",") if part.strip()]


def _load_choice():
    """The displays chosen in the app. Reads the single-display shape too: this
    file was written by every version before the week could go on more than one
    screen, and there is no sense in making anyone choose again."""
    try:
        with open(CHOICE_FILE, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(saved, dict):
        return []
    if isinstance(saved.get("devices"), list):
        return [str(x).strip() for x in saved["devices"] if str(x).strip()]
    one = str(saved.get("device") or "").strip()
    return [one] if one else []


def _save_choice(entity_ids):
    tmp = CHOICE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"devices": list(entity_ids)}, fh)
    os.replace(tmp, CHOICE_FILE)


def targets():
    """The displays to cast to. The add-on option wins when it is set, which is
    the whole of the rule and is why the app can say so plainly rather than
    showing a picker that quietly does nothing."""
    return _split(PINNED) if PINNED else _load_choice()


def pinned():
    return bool(PINNED)


def choose(entity_ids):
    """Called from the app's picker. An empty list means stop casting."""
    if PINNED:
        raise ValueError(
            "The displays are set in the add-on's Configuration panel. "
            "Clear cast_device there to choose them here instead.")
    if isinstance(entity_ids, str):
        entity_ids = _split(entity_ids)
    if not isinstance(entity_ids, list):
        raise ValueError("Expected a list of displays.")

    wanted = []
    for entity_id in entity_ids:
        entity_id = str(entity_id).strip()
        if not entity_id:
            continue
        if not entity_id.startswith("media_player."):
            raise ValueError("That doesn't look like a Home Assistant media player.")
        if entity_id not in wanted:
            wanted.append(entity_id)

    _save_choice(wanted)
    with _lock:
        # A deliberate choice shouldn't have to wait out the rate limit, and a
        # display that had been given up on - or written off as removed -
        # deserves a fresh start.
        _state["unacknowledged"] = {}
        _state["castAt"] = {}
        _state["misses"] = {k: v for k, v in _state["misses"].items() if k in wanted}
        _state["gone"] = sorted(_forgotten(_state["misses"]))
        _state["error"] = ""
    kick()
    return wanted


def kick():
    """Run a watcher pass now, in the background. Picking a display should put
    the week on it while you are still looking at the phone, but not by making
    the phone wait on Home Assistant to answer."""
    if not configured():
        return
    threading.Thread(target=_safe_tick, daemon=True, name="cast-kick").start()


def url():
    """The address to put on the screen. The Nest Hub has to fetch this itself,
    so it must be an address on the LAN - not localhost, and not the container's
    own 172.x address, which is the one this process would otherwise think it
    had (see cover_host in server.py)."""
    if FIXED_URL:
        return FIXED_URL
    return _url_source() if _url_source else ""


# --------------------------------------------------------------------------
# casting
# --------------------------------------------------------------------------

def cast_now(entity_id):
    """Ask DashCast to load the kitchen display on one screen. Returns the URL
    sent."""
    if not entity_id:
        raise RuntimeError("No display chosen.")
    page = url()
    if not page:
        raise RuntimeError("Couldn't work out an address for the kitchen display.")
    _call("/services/%s/load_url" % _service_domain(), {
        "entity_id": entity_id,
        "url": page,
        # The kitchen page is our own and frames itself happily, but DashCast's
        # non-forced path relies on an iframe and has been the difference
        # between a blank screen and a working one on more than one Nest Hub.
        "force": True,
    })
    with _lock:
        _state["castAt"][entity_id] = time.time()
        _state["unacknowledged"][entity_id] = \
            _state["unacknowledged"].get(entity_id, 0) + 1
    return page


def _release(entity_id):
    """Hand a screen back at the end of the casting hours.

    Only ever called about a display that is showing our own page: a Hub that
    somebody has put music on, or that is back on its photos already, is not
    ours to switch off. `media_player.turn_off` is how a Cast app is quit, and
    on a Nest Hub it drops back to the ambient screen rather than going dark.

    The bookkeeping is cleared with it, so the moment the window opens again
    the next tick casts rather than sitting out the rate limit."""
    _call("/services/media_player/turn_off", {"entity_id": entity_id})
    with _lock:
        _state["castAt"].pop(entity_id, None)
        _state["unacknowledged"][entity_id] = 0
    sys.stderr.write("[meal-planner] casting hours over - gave %s back\n" % entity_id)


def _name_of(entity_id):
    """The friendly name, for a message someone has to read. Falls back to the
    entity id, which is at least unambiguous."""
    with _lock:
        for device in _state["devices"]:
            if device["entityId"] == entity_id:
                return device["name"]
    return entity_id


def _visit(entity_id, open_now=True):
    """Look at one screen and put the week on it if it is free.

    Raises if something is wrong with this particular display; the caller keeps
    going round the others, because one Hub unplugged in a spare room is no
    reason to stop feeding the one in the kitchen."""
    now = _device_state(entity_id)
    app = now["appName"].lower()
    ours = now["appId"] == DASHCAST_APP_ID or app in DASHCAST_APP_NAMES

    with _lock:
        _state["showing"][entity_id] = now["appName"] or now["state"]
        if ours:
            _state["unacknowledged"][entity_id] = 0
        recently_cast = (time.time() - _state["castAt"].get(entity_id, 0.0)
                         < MIN_BETWEEN_CASTS)
        given_up = _state["unacknowledged"].get(entity_id, 0) >= MAX_UNACKNOWLEDGED

    if not open_now:
        # Outside the casting hours. Tidy our own page away and then leave the
        # screen entirely alone - including the "never came up" counter, which
        # would otherwise fill with casts that were never attempted.
        if ours:
            _release(entity_id)
        return

    if ours or recently_cast:
        return
    if now["state"] == "unavailable":
        return                      # unplugged, or off the network: nothing to do
    if not (now["state"] in IDLE_STATES or app in IDLE_APPS):
        return                      # somebody is watching or listening to something
    if given_up:
        # Checked last, so this only ever fires about a screen that was free and
        # could have taken the page - not about one that was busy anyway.
        raise RuntimeError(
            "Sent the week to %s %d times and it never came up. Check that it "
            "can reach %s, and that it is a screen rather than a speaker."
            % (_name_of(entity_id), MAX_UNACKNOWLEDGED, url()))

    sent = cast_now(entity_id)
    sys.stderr.write("[meal-planner] cast the kitchen display to %s (%s)\n"
                     % (entity_id, sent))


def _tick():
    """One pass of the watcher, over every chosen screen. Kept deliberately
    quiet: it runs every minute for as long as the add-on is up, so it logs when
    something changes, not when everything is fine."""
    chosen = targets()
    devices, guessed = _fetch_devices()
    # Read once for the whole pass, so two screens can't disagree about whether
    # the window is open because the clock ticked between them.
    open_now = display.casting_open()
    _remember_devices(devices, guessed, chosen)

    with _lock:
        _state["open"] = open_now
        # Anything Home Assistant lists again is not gone, whatever it did last
        # week - and this is read from the stored list rather than the one just
        # fetched, so a pass that was held back above doesn't resurrect it.
        present = {d["entityId"] for d in _state["devices"]}
        misses = _state["misses"]
        for key in [k for k in misses if k not in chosen or k in present]:
            del misses[key]
        vanished = _forgotten(misses)
        # Forget the bookkeeping for screens that are no longer chosen, so one
        # turned off and back on again next month starts with a clean slate.
        for book in ("showing", "castAt", "unacknowledged"):
            for key in [k for k in _state[book] if k not in chosen]:
                del _state[book][key]

    troubles, missed = [], []
    for entity_id in chosen:
        if entity_id in vanished:
            # Already written off. Asking again every minute only spends a
            # round trip to be told 404 a second time; the pass that finds it
            # in the device list again clears this.
            continue
        try:
            _visit(entity_id, open_now)
        except Gone:
            missed.append(entity_id)
        except Exception as exc:                       # noqa: BLE001
            troubles.append(str(exc).strip() or exc.__class__.__name__)

    with _lock:
        misses = _state["misses"]
        for entity_id in chosen:
            if entity_id in missed:
                misses[entity_id] = misses.get(entity_id, 0) + 1
            elif entity_id not in vanished:
                # It answered, so whatever it did last minute it is still here.
                misses.pop(entity_id, None)
        _state["gone"] = sorted(_forgotten(misses))

    if troubles:
        # One message, however many screens are sulking: the app shows a line,
        # not a log. Displays that have been removed are deliberately not in
        # here: they are reported as their own thing, and a problem that will
        # still be true next minute must not put the watcher into the back-off
        # that _loop applies to every other screen.
        raise RuntimeError(" ".join(troubles))


def _safe_tick():
    """One pass, with anything that went wrong turned into a message for the
    app: Home Assistant restarting, DashCast not installed, the display
    unplugged. Most of these fix themselves and none of them is worth taking the
    planner down for, so nothing propagates out of here.

    A display that has been removed from Home Assistant altogether is the
    exception and is not reported this way - it won't fix itself, and treating
    it as a failure would slow the watcher down for every other screen. See
    Gone, and `gone` in status().

    Returns whether it worked, which is what the loop paces itself by."""
    try:
        _tick()
        with _lock:
            _state["error"] = ""
        return True
    except Exception as exc:                           # noqa: BLE001 - deliberate
        message = str(exc).strip() or exc.__class__.__name__
        with _lock:
            if message != _state["error"]:             # once per new problem
                sys.stderr.write("[meal-planner] cast: %s\n" % message)
            _state["error"] = message
        return False


def _loop():
    fails = 0
    while True:
        fails = 0 if _safe_tick() else fails + 1
        # Back off while it is failing - up to five minutes - so a display that
        # has been unplugged for the winter isn't a line in the log every
        # minute until spring.
        time.sleep(CHECK_EVERY * min(fails + 1, 5))


def start(url_source):
    """Begin watching, if there is anything to watch with. `url_source` is a
    callable returning the address to cast, asked each time rather than once, so
    a Pi that changes address doesn't keep casting the old one."""
    global _url_source
    _url_source = url_source
    if not configured():
        return False
    threading.Thread(target=_loop, daemon=True, name="cast-watch").start()
    return True


def _with_absentees(devices, chosen, known, gone):
    """The device list, plus any chosen display that isn't in it.

    A chosen display can be missing for two quite different reasons, and the
    picker has to be able to tell them apart. Switched off at the wall it is
    still an entity, still listed, and only its state says so - that one is not
    here. Removed from the Home it is not an entity at all, and the only honest
    thing to show is the row it used to have, marked, with the choice of letting
    it go. Dropping it silently would be worse: un-ticking something you can no
    longer see is not a fix anyone can find."""
    listed = {d["entityId"] for d in devices}
    for entity_id in chosen:
        if entity_id in listed:
            continue
        record = dict(known.get(entity_id) or
                      {"entityId": entity_id, "name": entity_id, "model": "",
                       "video": True, "state": "", "showing": ""})
        record["missing"] = True
        record["gone"] = entity_id in gone
        devices.append(record)
    devices.sort(key=_order)
    return devices


def status():
    """Everything the app's picker needs, entirely out of memory - no HTTP on a
    request thread, ever."""
    with _lock:
        devices = list(_state["devices"])
        known = dict(_state["known"])
        guessed = _state["guessed"]
        gone = list(_state["gone"])
        checked = _state["checked"]
        error = _state["error"]
        showing = dict(_state["showing"])
    if not configured():
        return {"available": False, "devices": [], "targets": [], "pinned": False,
                "url": url(), "showing": {}, "error": "", "open": True,
                "gone": [], "guessed": False,
                "reason": "Casting needs Home Assistant, so it only works when the "
                          "planner is running as an add-on."}
    chosen = targets()
    return {
        "available": True,
        "devices": _with_absentees(devices, chosen, known, gone),
        "targets": chosen,
        "pinned": pinned(),
        "url": url(),
        "showing": showing,
        "error": error,
        # Chosen displays Home Assistant doesn't have any more, so the app can
        # offer to forget them rather than leaving a row that never comes back.
        "gone": gone,
        # Whether the list was swept out of /states rather than given by the
        # Cast integration, which is worth saying out loud: it is the answer
        # that calls a Sonos a screen.
        "guessed": guessed,
        # Asked afresh rather than reported from the last pass, so the app says
        # "waiting until 07:00" the moment the hours are changed rather than at
        # the next tick, a minute later.
        "open": display.casting_open(),
        # A picker with nothing in it needs to say whether that means "no
        # displays" or "haven't looked yet".
        "checked": bool(checked),
        "reason": "",
    }


def refresh():
    """Look now rather than at the next tick - what the app's Refresh button
    calls. Deliberately the only thing here that touches the network from a
    request thread, because somebody is sitting there waiting for it."""
    try:
        devices, guessed = _fetch_devices()
    except Exception as exc:                           # noqa: BLE001
        with _lock:
            _state["error"] = str(exc).strip() or exc.__class__.__name__
        return status()
    chosen = targets()
    # Through the same gate as the watcher, not around it. This button is most
    # likely to be pressed in the minute after somebody changed their Google
    # Home, which is precisely when Home Assistant is least able to answer -
    # and emptying the picker in front of the person who just pressed it is the
    # worst possible moment to do it.
    _remember_devices(devices, guessed, chosen)
    with _lock:
        present = {d["entityId"] for d in _state["devices"]}
        misses = _state["misses"]
        for key in [k for k in misses if k not in chosen or k in present]:
            del misses[key]
        _state["gone"] = sorted(_forgotten(misses))
        _state["error"] = ""
    return status()
