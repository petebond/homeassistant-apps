"""What the Cast picker does while Home Assistant is changing under it.

Adding or removing a display in the Google Home app reloads Home Assistant's
Cast integration, and for a minute either side of that the answers this module
gets back are wrong in three particular ways. Each one used to show up in the
app as a confused list; each one has a test here.

Run: python3 tests/test_cast_churn.py  (kept out of the image: Dockerfile copies *.py)
"""

import os
import sys
import tempfile

os.environ["SUPERVISOR_TOKEN"] = "test-token"
os.environ["MEAL_PLANNER_DATA_DIR"] = tempfile.mkdtemp(prefix="cast-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cast  # noqa: E402

HUB = "media_player.kitchen_display"
NEW_HUB = "media_player.kitchen_display_2"
SPEAKER = "media_player.bathroom_mini"


def row(entity_id, name, model="Nest Hub", state="off", app=None):
    return {"entity_id": entity_id, "name": name, "device_class": None,
            "model": model, "state": state, "app": app}


def reset(devices=(), chosen=()):
    """A watcher that has just started, with `devices` in the house."""
    cast._state.update({
        "checked": 0.0, "devices": [], "known": {}, "guessed": False,
        "empty": 0, "misses": {}, "gone": [], "showing": {}, "castAt": {},
        "unacknowledged": {}, "error": "", "domain": "dash_cast",
        "haHost": "", "open": True,
    })
    cast._url_source = lambda: "http://10.0.0.5:8080/kitchen"
    cast._save_choice(list(chosen))
    set_house(devices)


HOUSE = {"rows": [], "template_fails": False, "states": [], "casts": []}


def set_house(rows, template_fails=False, states=None):
    HOUSE["rows"] = list(rows)
    HOUSE["template_fails"] = template_fails
    HOUSE["states"] = list(states if states is not None else rows)


def fake_call(path, payload=None, timeout=None):
    if path == "/template":
        if HOUSE["template_fails"]:
            raise RuntimeError("Cast integration is reloading")
        return HOUSE["rows"]
    if path == "/states":
        return [{"entity_id": r["entity_id"],
                 "state": r["state"],
                 "attributes": {"friendly_name": r["name"]}}
                for r in HOUSE["states"]]
    if path.startswith("/states/"):
        entity_id = path[len("/states/"):]
        for r in HOUSE["rows"]:
            if r["entity_id"] == entity_id:
                return {"state": r["state"],
                        "attributes": {"app_name": r["app"], "app_id": ""}}
        import urllib.error
        raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
    if "load_url" in path:
        HOUSE["casts"].append(payload["entity_id"])
        return None
    if path.startswith("/services/media_player/"):
        return None
    return None


cast._call = fake_call

FAILURES = []


def check(label, got, want):
    if got == want:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s\n         got  %r\n         want %r" % (label, got, want))
        FAILURES.append(label)


def ids(status):
    return [d["entityId"] for d in status["devices"]]


# --------------------------------------------------------------------------
print("a reloading Cast integration doesn't empty the picker")
# --------------------------------------------------------------------------
reset([row(HUB, "Kitchen display")], chosen=[HUB])
cast._tick()
check("the Hub is listed", ids(cast.status()), [HUB])

# The reload: the template renders perfectly well and says there is nothing.
set_house([])
cast._safe_tick()
check("one empty pass is not believed", ids(cast.status()), [HUB])
check("and one 404 doesn't write the Hub off", cast.status()["gone"], [])

# Two in a row, though, means they really have been taken away.
cast._safe_tick()
check("two empty passes are", ids(cast.status()), [HUB])   # still chosen, so still shown
check("but the Hub is now missing", cast.status()["devices"][0]["missing"], True)

# ...and it comes back.
set_house([row(HUB, "Kitchen display")])
cast._safe_tick()
check("recovered", [d.get("missing", False) for d in cast.status()["devices"]], [False])

# --------------------------------------------------------------------------
print("\na fallback sweep doesn't replace a good list")
# --------------------------------------------------------------------------
reset([row(HUB, "Kitchen display"), row(SPEAKER, "Bathroom", model="Nest Mini")],
      chosen=[HUB])
cast._tick()
before = cast.status()
check("the speaker is known to be a speaker",
      [d["video"] for d in before["devices"]], [True, False])
check("not a guess", before["guessed"], False)

# Now the template stops working and /states offers every media player, with no
# model on any of them - the answer that used to call the Sonos a screen.
set_house([row(HUB, "Kitchen display"),
           row(SPEAKER, "Bathroom", model="Nest Mini"),
           row("media_player.lounge_sonos", "Lounge", model="Sonos One"),
           row("media_player.spotify_pete", "Spotify", model=None)],
          template_fails=True)
cast._safe_tick()
after = cast.status()
check("the swept list is ignored", ids(after), ids(before))
check("still not a guess", after["guessed"], False)

# But on a cold start it is better than nothing.
reset(chosen=[])
set_house([row(HUB, "Kitchen display")], template_fails=True)
cast._tick()
check("used when there is nothing better", ids(cast.status()), [HUB])
check("and says so", cast.status()["guessed"], True)

# --------------------------------------------------------------------------
print("\na display removed from the Home is reported, not retried forever")
# --------------------------------------------------------------------------
reset([row(HUB, "Kitchen display")], chosen=[HUB])
cast._tick()
check("chosen and present", cast.status()["gone"], [])

# Taken out of the Google Home and put back: a new entity id, the old one gone.
set_house([row(NEW_HUB, "Kitchen display")])
cast._safe_tick()
check("one 404 is not enough to write it off", cast.status()["gone"], [])
cast._safe_tick()
status = cast.status()
check("the old id is reported gone", status["gone"], [HUB])
check("both rows are shown", sorted(ids(status)), sorted([HUB, NEW_HUB]))
check("the gone row keeps its old name",
      [d["name"] for d in status["devices"] if d["entityId"] == HUB], ["Kitchen display"])
check("and is flagged for the picker",
      [d["gone"] for d in status["devices"] if d["entityId"] == HUB], [True])

# The whole point: a removed display must not put the watcher into back-off,
# because that would slow every working screen down with it.
check("a removed display is not a failure", cast._safe_tick(), True)
check("and leaves no error banner", cast.status()["error"], "")

# Nor should it cost a round trip every minute.
calls = []
real = cast._device_state
cast._device_state = lambda e: calls.append(e) or real(e)
cast._safe_tick()
cast._device_state = real
check("it is not asked about again", calls, [])

# Forgetting it is what the app's button does.
cast.choose([NEW_HUB])
check("forgotten", cast.status()["gone"], [])
check("and the new one is chosen", cast.status()["targets"], [NEW_HUB])

# A display that comes back under its old id is picked up again.
reset([row(HUB, "Kitchen display")], chosen=[HUB])
cast._tick()
set_house([])
cast._safe_tick()
cast._safe_tick()
cast._safe_tick()          # now gone: 404 from _device_state
check("gone after it stops answering", cast.status()["gone"], [HUB])
set_house([row(HUB, "Kitchen display")])
cast._safe_tick()
check("no longer gone once it is listed again", cast.status()["gone"], [])

# --------------------------------------------------------------------------
print("\nan ordinary trouble still backs off")
# --------------------------------------------------------------------------
reset([row(HUB, "Kitchen display", state="playing", app="YouTube")], chosen=[HUB])
cast._tick()
original = cast._visit
cast._visit = lambda e, o=True: (_ for _ in ()).throw(RuntimeError("Hub is sulking"))
check("a real problem is a failure", cast._safe_tick(), False)
check("and says so", cast.status()["error"], "Hub is sulking")
cast._visit = original

print("\n%s" % ("all good" if not FAILURES else "%d FAILED" % len(FAILURES)))
sys.exit(1 if FAILURES else 0)
