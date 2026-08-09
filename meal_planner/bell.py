"""
The dinner bell: one button, and every speaker in the house says so.

Why it exists: calling everyone to the table means walking to the foot of the
stairs and shouting. The house already has speakers in it, Home Assistant
already knows about all of them, and this app already talks to Home Assistant
about the screen in the kitchen. Ringing them is the same conversation with a
different service on the end of it.

What it deliberately is not:

- **It is not the casting watcher.** cast.py goes to great lengths never to take
  a screen somebody is using, because it acts on its own every minute and an
  add-on that interrupts a song unasked is an add-on that gets uninstalled. The
  bell is the opposite case: somebody pressed a button and meant it, so it plays
  over whatever is on. It is worth being plain that Cast has no way to put back
  what it interrupted - a podcast stopped by the bell stays stopped - which is
  why nothing here rings on a timer, and why nothing ever will without being
  asked for.
- **It does not touch the volume.** Reading each speaker's level, setting ours
  and putting it back is three round trips per device and leaves the house loud
  for good if the app dies in the middle. The chime plays at whatever the
  speaker is already set to, which is the level the household chose.
- **It does not speak.** The sound is a file, so what it says is whatever
  somebody uploaded - a bell, a gong, or a recording of them shouting "dinner".
  Text to speech would add a dependency on a TTS provider being configured in
  Home Assistant, a second service call that has to be timed to land after the
  first, and a sentence in one fixed language.

The one genuinely awkward constraint is the address the chime is fetched from.
A Cast speaker downloads the file itself, and it has never been told to trust
this app's private certificate authority - so the URL it is given has to be
plain http, on the LAN, exactly like the kitchen page and the meal photos. See
`url_source` below and kitchen_url() in server.py, which is where that address
is worked out.
"""

import json
import os
import threading
import time

import cast

DATA_DIR = os.environ.get("MEAL_PLANNER_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(DATA_DIR, "bell.json")

# The uploaded chime lives in a folder of its own rather than loose in /data,
# so that "whatever is in here" is a complete answer to "what did they upload"
# and replacing it is a matter of emptying one directory.
CHIME_DIR = os.path.join(DATA_DIR, "chime")

# The fallback, shipped in the image. It means the switch works the moment it is
# turned on: an enable that does nothing until you have found an mp3 is an
# enable that gets turned on, tested, and written off as broken. Synthesised
# once by tools/make_chime.py, which is in the repository so the sound can be
# changed without the original.
BUILT_IN = "/chime.wav"

DEFAULTS = {
    "enabled": False,
    # Which speakers. Separate from cast.py's chosen displays on purpose: the
    # screen the week goes on and the speakers dinner is announced through are
    # different lists in most houses, and in the ones where they are the same
    # it is two ticks.
    "devices": [],
    # The button on the kitchen display itself. On when the bell is, because a
    # display in the kitchen is where somebody plating up is standing.
    "showButton": True,
}

# What an upload may be. Extension and magic bytes both, because the extension
# is whatever the phone's file picker put on it and the bytes are what the
# speaker will actually try to play.
AUDIO_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}

# Enough for a long gong, nowhere near enough for somebody to park an album in
# /data by mistake.
MAX_CHIME = 8_000_000
MIN_CHIME = 200

# A chime is a couple of seconds. This is not a rate limit for the sake of Home
# Assistant - it is for the nine-year-old who has discovered the button.
COOLDOWN = 12.0

# How long a ring is given before the app stops waiting and says what it knows.
# The speakers are called in parallel, so this is the slowest one, not the sum.
RING_DEADLINE = 8.0

_lock = threading.Lock()
_state = {"rangAt": 0.0, "error": ""}

# Set by server.main(): a callable returning the http base address on the LAN.
# A callable rather than a string because a Pi's address can change, and a bell
# that stopped working in March because the router handed out a new lease would
# be a miserable thing to debug.
_url_source = None


def start(url_source):
    global _url_source
    _url_source = url_source


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------

def clean(raw, base=None):
    """A complete, valid settings dict from whatever was passed in. Same shape
    of function as display.clean(), and for the same reason: this file is read
    on the path of a button press and should only ever hold what is understood.

    `chime` is not settable from outside. It is the name of a file on disk, set
    by the upload and cleared by the delete, and accepting it from a request
    body would make it a way to point the app at any file it can open."""
    base = dict(DEFAULTS, **(base or {}))
    raw = raw if isinstance(raw, dict) else {}
    out = {}

    for flag in ("enabled", "showButton"):
        out[flag] = bool(raw.get(flag, base[flag]))

    devices = raw.get("devices", base["devices"])
    if isinstance(devices, str):
        devices = [devices]
    wanted = []
    if isinstance(devices, list):
        for entity_id in devices[:40]:
            entity_id = str(entity_id).strip()
            # The same check the cast picker makes. Anything else is either a
            # mistake or somebody trying it on, and neither should reach Home
            # Assistant with our token on it.
            if entity_id.startswith("media_player.") and entity_id not in wanted:
                wanted.append(entity_id)
    out["devices"] = wanted
    return out


def load():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        saved = {}
    return clean(saved, DEFAULTS)


def save(patch):
    """Merge a partial update over what is stored and write it back. Partial
    because the panel saves one switch at a time."""
    current = load()
    merged = clean(patch, current)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(merged, fh)
    os.replace(tmp, SETTINGS_FILE)
    return merged


# --------------------------------------------------------------------------
# the sound
# --------------------------------------------------------------------------

class ChimeError(Exception):
    """Something about the uploaded file is wrong. The message is written to be
    read by whoever chose it, so it says what to do."""


def _stored():
    """The uploaded chime's filename, or "" for none. Read off the directory
    rather than out of the settings file: the folder holds one file and the
    folder is the truth, so there is no way for the two to disagree after a
    restore that carried one and not the other."""
    try:
        names = sorted(n for n in os.listdir(CHIME_DIR)
                       if os.path.splitext(n)[1].lower() in AUDIO_TYPES)
    except OSError:
        return ""
    return names[-1] if names else ""


def _sniff(blob):
    """What the bytes say they are, or "" if they say nothing recognisable.

    Not a full parse - just enough to catch the common wrong answer, which is
    a photo or a text file that has been given an audio extension somewhere
    along the way. A speaker handed one of those does nothing at all, and
    nothing at all is the hardest possible symptom to work back from."""
    if blob[:3] == b"ID3" or (len(blob) > 1 and blob[0] == 0xFF and (blob[1] & 0xE0) == 0xE0):
        return ".mp3"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WAVE":
        return ".wav"
    if blob[:4] == b"OggS":
        return ".ogg"
    if blob[4:8] == b"ftyp":
        return ".m4a"
    if blob[:4] == b"fLaC":
        return ".flac"
    if blob[:4] == b"ADIF" or blob[:2] == b"\xff\xf1" or blob[:2] == b"\xff\xf9":
        return ".aac"
    return ""


def save_chime(filename, blob):
    """Store an uploaded sound, replacing whatever was there. Returns its name.

    The name it is saved under is built here rather than taken from the upload:
    a filename off a phone can be anything at all, and this one has to be safe
    to put in a path and in a URL a Cast speaker will parse."""
    if not blob:
        raise ChimeError("No file arrived. Try choosing it again.")
    if len(blob) < MIN_CHIME:
        raise ChimeError("That file is empty.")
    if len(blob) > MAX_CHIME:
        raise ChimeError("That file is too big. A chime is a few seconds long; "
                         "this one is %.1f MB." % (len(blob) / 1_000_000.0))

    ext = os.path.splitext(str(filename or ""))[1].lower()
    found = _sniff(blob)
    if not found and ext not in AUDIO_TYPES:
        raise ChimeError("That doesn't look like a sound file. mp3, wav, ogg, "
                         "m4a and flac all work.")
    # The bytes win where they disagree with the name. A .wav that is really an
    # mp3 plays perfectly well once it is called what it is.
    ext = found or ext

    os.makedirs(CHIME_DIR, exist_ok=True)
    for name in os.listdir(CHIME_DIR):
        try:
            os.remove(os.path.join(CHIME_DIR, name))
        except OSError:
            pass

    # A timestamp, so a replaced chime can't be served out of a speaker's cache
    # or a browser's. Same trick the meal photos use.
    name = "chime-%d%s" % (int(time.time()), ext)
    tmp = os.path.join(CHIME_DIR, name + ".part")
    with open(tmp, "wb") as fh:
        fh.write(blob)
    os.replace(tmp, os.path.join(CHIME_DIR, name))
    return name


def clear_chime():
    """Throw the upload away and fall back to the built-in bell."""
    try:
        for name in os.listdir(CHIME_DIR):
            os.remove(os.path.join(CHIME_DIR, name))
    except OSError:
        pass


def chime_path():
    """The path the app serves the current chime at - the upload if there is
    one, the built-in otherwise."""
    name = _stored()
    return "/chime/" + name if name else BUILT_IN


def chime_file():
    """Where the current chime is on disk, and its content type, for the
    handler that serves it."""
    name = _stored()
    if name:
        return (os.path.join(CHIME_DIR, name),
                AUDIO_TYPES.get(os.path.splitext(name)[1].lower(),
                                "application/octet-stream"))
    return os.path.join(BASE_DIR, "static", "chime.wav"), "audio/wav"


def chime_url():
    """The address a speaker is told to fetch. http, never https: a Cast device
    has not been told to trust this app's certificate authority and will refuse
    the download without a word about why."""
    base = _url_source() if _url_source else ""
    if not base:
        raise RuntimeError(
            "The app couldn't work out its own address on the network, so it "
            "has nowhere to tell the speakers to fetch the chime from.")
    return base.rstrip("/") + chime_path()


# --------------------------------------------------------------------------
# ringing
# --------------------------------------------------------------------------

def _play(entity_id, url, results):
    try:
        cast.call_service("media_player", "play_media", {
            "entity_id": entity_id,
            "media_content_id": url,
            "media_content_type": "music",
        }, timeout=RING_DEADLINE)
        results[entity_id] = ""
    except Exception as exc:                           # noqa: BLE001
        results[entity_id] = str(exc).strip() or exc.__class__.__name__


def ring():
    """Play the chime on every chosen speaker, now.

    Done on the request thread, which is the one place in this app that is
    allowed - the same exception cast.refresh() takes, and for the same reason:
    somebody is standing there having just pressed a button, and "it is on its
    way" is not an answer they can act on. The speakers are called in parallel
    and the whole thing is bounded by RING_DEADLINE, so one speaker unplugged in
    a bedroom cannot make the kitchen wait.

    Returns what happened, per speaker. Raises RuntimeError with something worth
    reading for the cases where nothing was even attempted."""
    if not cast.configured():
        raise RuntimeError("The dinner bell needs Home Assistant, so it only "
                           "works when the planner is running as an add-on.")
    settings = load()
    if not settings["enabled"]:
        raise RuntimeError("The dinner bell is switched off.")
    targets = settings["devices"]
    if not targets:
        raise RuntimeError("No speakers chosen for the dinner bell yet.")

    with _lock:
        since = time.time() - _state["rangAt"]
        if since < COOLDOWN:
            raise RuntimeError("The bell has just rung. Give it a moment.")
        # Claimed before the calls rather than after, so two people pressing at
        # once get one ring between them rather than two overlapping ones.
        _state["rangAt"] = time.time()

    url = chime_url()
    results = {}
    threads = [threading.Thread(target=_play, args=(entity_id, url, results),
                                daemon=True, name="bell-" + entity_id)
               for entity_id in targets]
    for thread in threads:
        thread.start()
    deadline = time.time() + RING_DEADLINE
    for thread in threads:
        thread.join(max(0.0, deadline - time.time()))

    rang, failed = [], []
    for entity_id in targets:
        if entity_id not in results:
            failed.append({"entityId": entity_id,
                           "error": "Home Assistant didn't answer in time."})
        elif results[entity_id]:
            failed.append({"entityId": entity_id, "error": results[entity_id]})
        else:
            rang.append(entity_id)

    with _lock:
        # A ring where nothing worked shouldn't hold the cooldown against the
        # next attempt: the most likely next act is trying again.
        if not rang:
            _state["rangAt"] = 0.0
        _state["error"] = "" if rang else (failed[0]["error"] if failed else "")

    return {"ok": bool(rang), "rang": rang, "failed": failed,
            "url": url, "at": time.time()}


def status():
    """Everything the settings panel and the kitchen display need. Reads two
    small files and no network, so it is safe on any request thread."""
    settings = load()
    with _lock:
        rang_at, error = _state["rangAt"], _state["error"]
    uploaded = _stored()
    return dict(settings, **{
        "available": cast.configured(),
        # What the display asks before drawing its button: both switches on, and
        # somewhere for the sound to go.
        "ready": bool(settings["enabled"] and settings["devices"]
                      and cast.configured()),
        "chime": chime_path(),
        "chimeName": uploaded,
        "builtIn": not uploaded,
        "rangAt": rang_at,
        "error": error,
        "reason": "" if cast.configured() else
                  "The dinner bell needs Home Assistant, so it only works when "
                  "the planner is running as an add-on.",
    })
