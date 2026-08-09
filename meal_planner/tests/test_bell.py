"""The dinner bell: what it will accept, and what it refuses to do.

The bell is the only thing in this app that reaches out and does something in
the house. Everything else writes a file and waits to be looked at; this makes
six speakers play a sound, over whatever anybody was listening to, and Cast has
no way to put that back. So the tests here are mostly about restraint:

  - it does not ring when it is switched off, when nothing is chosen, or when
    there is no Home Assistant to ring through
  - it does not ring twice in a row, because the button is at the height of a
    nine-year-old and the cooldown is the only thing between them and it
  - a ring where every speaker failed does not hold the cooldown against the
    next attempt, because the next thing anybody does is try again

And the upload, which is the one place a file off a phone reaches the disk:
what gets stored, what gets refused, and the rule that the bytes decide what a
file is rather than whatever the picker called it.

Run: python3 tests/test_bell.py  (kept out of the image: Dockerfile copies *.py)
"""

import json
import os
import shutil
import sys
import tempfile

DATA = tempfile.mkdtemp(prefix="bell-test-")
os.environ["MEAL_PLANNER_DATA_DIR"] = DATA
os.environ["SUPERVISOR_TOKEN"] = "test-token"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bell   # noqa: E402
import cast   # noqa: E402

FAILURES = []

# A minimal but real file of each kind, so the sniffer is tested on the bytes it
# will actually meet rather than on a string that happens to start with "RIFF".
MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 400
WAV = b"RIFF\x24\x08\x00\x00WAVEfmt " + b"\x00" * 400
OGG = b"OggS\x00\x02" + b"\x00" * 400
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 400
NOT_AUDIO = b"\x89PNG\r\n\x1a\n" + b"\x00" * 400


def check(label, got, want):
    if got != want:
        FAILURES.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


def check_raises(label, message_part, fn):
    try:
        fn()
    except Exception as exc:                           # noqa: BLE001
        if message_part.lower() not in str(exc).lower():
            FAILURES.append("%s\n     message was: %r\n     expected to mention: %r"
                            % (label, str(exc), message_part))
        return
    FAILURES.append("%s\n     nothing was raised" % label)


def stored_names():
    try:
        return sorted(os.listdir(bell.CHIME_DIR))
    except OSError:
        return []


def reset():
    for name in os.listdir(DATA):
        path = os.path.join(DATA, name)
        shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)
    with bell._lock:
        bell._state["rangAt"] = 0.0
        bell._state["error"] = ""
    bell.start(lambda: "http://192.168.1.42:8080")


# --------------------------------------------------------------- settings

def test_defaults():
    reset()
    settings = bell.load()
    check("off until somebody turns it on", settings["enabled"], False)
    check("no speakers to begin with", settings["devices"], [])
    check("the display's button is on by default", settings["showButton"], True)


def test_saves_are_partial():
    """The panel saves one switch at a time, so a patch must not blank the
    rest of the card."""
    reset()
    bell.save({"enabled": True, "devices": ["media_player.kitchen"]})
    bell.save({"showButton": False})
    settings = bell.load()
    check("still on", settings["enabled"], True)
    check("still has its speaker", settings["devices"], ["media_player.kitchen"])
    check("and took the new value", settings["showButton"], False)


def test_only_media_players():
    """The entity ids go to Home Assistant with our token on them, so anything
    that isn't a media player is dropped rather than passed on."""
    reset()
    saved = bell.save({"devices": ["media_player.kitchen", "light.hallway",
                                   "", "media_player.kitchen",
                                   "switch.kettle", "media_player.study"]})
    check("kept the speakers, once each, in order",
          saved["devices"], ["media_player.kitchen", "media_player.study"])


def test_chime_is_not_settable():
    """It is the name of a file on disk. Accepting it from a request body
    would make it a way to point the app at any file it can open."""
    reset()
    bell.save({"chime": "/etc/passwd", "enabled": True})
    check("the chime is still the built-in one", bell.status()["chime"], bell.BUILT_IN)


def test_survives_a_corrupt_file():
    reset()
    with open(bell.SETTINGS_FILE, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json")
    check("falls back to the defaults", bell.load(), dict(bell.DEFAULTS))


# ------------------------------------------------------------------ chime

def test_built_in_is_there():
    """The switch has to work the moment it is turned on. An enable that does
    nothing until you have found an mp3 is an enable that gets written off as
    broken."""
    path, ctype = bell.chime_file()
    check("the built-in chime is in the image", os.path.isfile(path), True)
    check("and is served as audio", ctype, "audio/wav")
    check("with nothing uploaded, it is what plays",
          bell.chime_path(), bell.BUILT_IN)


def test_upload_and_replace():
    reset()
    first = bell.save_chime("gong.mp3", MP3)
    check("stored under a name of our own making", first.startswith("chime-"), True)
    check("keeping the kind of file it is", first.endswith(".mp3"), True)
    check("and it is what plays now", bell.chime_path(), "/chime/" + first)

    second = bell.save_chime("bell.wav", WAV)
    check("one chime at a time",
          sorted(os.listdir(bell.CHIME_DIR)), [second])

    path, ctype = bell.chime_file()
    check("served from the upload", os.path.basename(path), second)
    check("as the right type", ctype, "audio/wav")

    bell.clear_chime()
    check("and deleting it falls back to the built-in",
          bell.chime_path(), bell.BUILT_IN)


def test_the_bytes_decide():
    """A phone's file picker names a file whatever it likes. A wav that is
    really an mp3 plays perfectly well once it is called what it is."""
    reset()
    name = bell.save_chime("definitely-a-bell.wav", MP3)
    check("stored as what it actually is", name.endswith(".mp3"), True)

    reset()
    name = bell.save_chime("no-extension-at-all", OGG)
    check("a file with no extension is still recognised",
          name.endswith(".ogg"), True)

    reset()
    name = bell.save_chime("clip.m4a", M4A)
    check("m4a too", name.endswith(".m4a"), True)


def test_upload_refusals():
    reset()
    check_raises("a photo", "doesn't look like a sound",
                 lambda: bell.save_chime("chime.png", NOT_AUDIO))
    check_raises("nothing at all", "no file",
                 lambda: bell.save_chime("chime.mp3", b""))
    check_raises("a few bytes", "empty",
                 lambda: bell.save_chime("chime.mp3", b"hi"))
    check_raises("an album", "too big",
                 lambda: bell.save_chime("chime.mp3",
                                         b"ID3" + b"\x00" * bell.MAX_CHIME))
    check("nothing was stored", stored_names(), [])

    # And a refusal after a good upload leaves the good one alone: the failure
    # case here is a household with no chime because they tried a photo.
    keep = bell.save_chime("bell.wav", WAV)
    check_raises("a photo, after a real one", "doesn't look like a sound",
                 lambda: bell.save_chime("chime.png", NOT_AUDIO))
    check("the sound that worked is still there", stored_names(), [keep])


def test_chime_url_is_plain_http():
    """A Cast speaker fetches this itself and has never been told to trust this
    app's certificate authority. https here is a speaker that downloads nothing
    and says nothing about why."""
    reset()
    bell.start(lambda: "http://192.168.1.42:8080")
    check("http, on the LAN, at the chime",
          bell.chime_url(), "http://192.168.1.42:8080" + bell.BUILT_IN)

    bell.start(lambda: "")
    check_raises("no address to offer", "couldn't work out its own address",
                 bell.chime_url)


# ----------------------------------------------------------------- ringing

class FakeHA(object):
    """Stands in for Home Assistant. Records what it was asked to do, and can
    be told to fail."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, domain, service, payload, timeout=None):
        self.calls.append((domain, service, payload))
        if self.fail:
            raise RuntimeError("that speaker isn't answering")
        return None


def with_ha(fake, fn):
    real = cast.call_service
    cast.call_service = fake
    try:
        return fn()
    finally:
        cast.call_service = real


def test_refuses_to_ring():
    reset()
    check_raises("switched off", "switched off", bell.ring)

    bell.save({"enabled": True})
    check_raises("nowhere to ring", "no speakers chosen", bell.ring)


def test_rings():
    reset()
    bell.save({"enabled": True,
               "devices": ["media_player.kitchen", "media_player.landing"]})
    fake = FakeHA()
    result = with_ha(fake, bell.ring)

    check("it rang", result["ok"], True)
    check("on both speakers", sorted(result["rang"]),
          ["media_player.kitchen", "media_player.landing"])
    check("nothing failed", result["failed"], [])
    check("two calls, one each", len(fake.calls), 2)

    domain, service, payload = fake.calls[0]
    check("through the media player", (domain, service),
          ("media_player", "play_media"))
    check("as music", payload["media_content_type"], "music")
    check("fetching the chime over http",
          payload["media_content_id"].startswith("http://"), True)


def test_the_cooldown():
    reset()
    bell.save({"enabled": True, "devices": ["media_player.kitchen"]})
    fake = FakeHA()
    with_ha(fake, bell.ring)
    check_raises("pressed twice", "just rung", lambda: with_ha(fake, bell.ring))
    check("and the second press rang nothing", len(fake.calls), 1)


def test_a_ring_that_failed_can_be_retried():
    """The cooldown is for the child pressing the button, not for the person
    trying to work out why nothing happened."""
    reset()
    bell.save({"enabled": True, "devices": ["media_player.kitchen"]})
    fake = FakeHA(fail=True)
    result = with_ha(fake, bell.ring)

    check("nothing rang", result["ok"], False)
    check("and it says which one and why",
          result["failed"][0]["entityId"], "media_player.kitchen")

    # Straight away, with no wait.
    again = with_ha(FakeHA(), bell.ring)
    check("a second go is allowed", again["ok"], True)


def test_one_dead_speaker_doesnt_stop_the_rest():
    reset()
    bell.save({"enabled": True,
               "devices": ["media_player.kitchen", "media_player.attic"]})

    class HalfDead(FakeHA):
        def __call__(self, domain, service, payload, timeout=None):
            self.calls.append((domain, service, payload))
            if payload["entity_id"].endswith("attic"):
                raise RuntimeError("not answering")

    result = with_ha(HalfDead(), bell.ring)
    check("the kitchen still rang", result["rang"], ["media_player.kitchen"])
    check("and the attic is reported", len(result["failed"]), 1)
    check("which counts as a ring", result["ok"], True)


def test_status():
    reset()
    check("not ready with nothing set up", bell.status()["ready"], False)
    bell.save({"enabled": True, "devices": ["media_player.kitchen"]})
    ready = bell.status()
    check("ready once it is on and pointed somewhere", ready["ready"], True)
    check("and says it is using the built-in sound", ready["builtIn"], True)


for test in [test_defaults, test_saves_are_partial, test_only_media_players,
             test_chime_is_not_settable, test_survives_a_corrupt_file,
             test_built_in_is_there, test_upload_and_replace,
             test_the_bytes_decide, test_upload_refusals,
             test_chime_url_is_plain_http,
             test_refuses_to_ring, test_rings, test_the_cooldown,
             test_a_ring_that_failed_can_be_retried,
             test_one_dead_speaker_doesnt_stop_the_rest, test_status]:
    test()

shutil.rmtree(DATA, ignore_errors=True)

if FAILURES:
    print("FAILED (%d)\n" % len(FAILURES))
    for failure in FAILURES:
        print("  - " + failure)
    sys.exit(1)
print("bell: all good")
