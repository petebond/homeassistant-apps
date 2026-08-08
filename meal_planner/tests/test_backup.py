"""Backup and restore: the round trip, and everything it refuses.

This is the one part of the app that deletes things, and the case it exists for
is the one where the safety net is already gone - the app has been uninstalled
and the zip in the downloads folder is all there is. So the tests here care less
about the happy path than about the ways a restore could quietly take something
with it:

  - the private CA. tls.py creates it once and never regenerates it, because
    regenerating it breaks the trust installed on every phone in the house with
    no symptom beyond "the app stopped loading". A round trip that loses certs/
    or leaves the key world-readable has done exactly that.
  - a zip that escapes the data directory. Nothing this writes needs an absolute
    path or a .. segment, so both are refused rather than normalised.
  - a half-applied restore. If the file turns out to be wrong, the current data
    must still be there afterwards.

Run: python3 tests/test_backup.py  (kept out of the image: Dockerfile copies *.py)
"""

import io
import json
import os
import shutil
import stat
import sys
import tempfile
import zipfile

os.environ["SUPERVISOR_TOKEN"] = "test-token"
DATA = tempfile.mkdtemp(prefix="backup-test-")
os.environ["MEAL_PLANNER_DATA_DIR"] = DATA
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup  # noqa: E402

FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


def check_raises(label, message_part, fn):
    try:
        fn()
    except backup.BackupError as exc:
        if message_part.lower() not in str(exc).lower():
            FAILURES.append("%s\n     message was: %r\n     expected to mention: %r"
                            % (label, str(exc), message_part))
        return
    except Exception as exc:
        FAILURES.append("%s\n     raised %s instead of BackupError: %s"
                        % (label, type(exc).__name__, exc))
        return
    FAILURES.append("%s\n     nothing was raised" % label)


SAMPLE = {
    "meals": [{"id": "m_1", "name": "Fish pie"}, {"id": "m_2", "name": "Dal"}],
    "people": [{"id": "p_1", "name": "Pete"}],
    "weeks": {"2026-08-03": {"mon": {"mealId": "m_1"}}},
    "extras": [{"id": "e_1", "item": "foil", "state": "need"}],
}


def seed():
    for name in os.listdir(DATA):
        path = os.path.join(DATA, name)
        shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)

    with open(os.path.join(DATA, "data.json"), "w", encoding="utf-8") as fh:
        json.dump(SAMPLE, fh)
    with open(os.path.join(DATA, "cast.json"), "w", encoding="utf-8") as fh:
        json.dump({"devices": ["media_player.kitchen"]}, fh)
    with open(os.path.join(DATA, "display.json"), "w", encoding="utf-8") as fh:
        json.dump({"accent": "sage", "scale": 110}, fh)

    os.makedirs(os.path.join(DATA, "images"), exist_ok=True)
    for name in ("meal-20260801-a.jpg", "meal-20260802-b.jpg"):
        with open(os.path.join(DATA, "images", name), "wb") as fh:
            fh.write(b"\xff\xd8\xff not really a jpeg")

    certs = os.path.join(DATA, "certs")
    os.makedirs(certs, exist_ok=True)
    with open(os.path.join(certs, "ca.crt"), "w") as fh:
        fh.write("-----BEGIN CERTIFICATE-----\nca\n")
    with open(os.path.join(certs, "ca.key"), "w") as fh:
        fh.write("-----BEGIN EC PRIVATE KEY-----\nsecret\n")
    os.chmod(os.path.join(certs, "ca.key"), 0o600)
    with open(os.path.join(certs, "learned.hosts"), "w") as fh:
        fh.write("meal-planner.local\n192.168.1.42\n")


def read(*parts):
    with open(os.path.join(DATA, *parts), "rb") as fh:
        return fh.read()


def test_zip_holds_everything():
    seed()
    names = set(zipfile.ZipFile(io.BytesIO(backup.make_zip())).namelist())
    for want in ("data.json", "cast.json", "display.json",
                 "images/meal-20260801-a.jpg",
                 "certs/ca.crt", "certs/ca.key", "certs/learned.hosts",
                 backup.MANIFEST_NAME):
        check("zip contains " + want, want in names, True)

    with open(os.path.join(DATA, "data.json.backup-20260801"), "w") as fh:
        fh.write("{}")
    names = set(zipfile.ZipFile(io.BytesIO(backup.make_zip())).namelist())
    check("daily snapshots stay out",
          any(n.startswith("data.json.backup-") for n in names), False)


def test_manifest():
    seed()
    zf = zipfile.ZipFile(io.BytesIO(backup.make_zip()))
    manifest = json.loads(zf.read(backup.MANIFEST_NAME))
    check("app", manifest["app"], "home-meal-planner")
    check("format", manifest["format"], backup.FORMAT)
    check("certs flagged", manifest["includesCerts"], True)
    check("meal count", manifest["contents"]["meals"], 2)
    check("photo count", manifest["contents"]["images"], 2)


def test_certs_can_be_left_out():
    seed()
    names = set(zipfile.ZipFile(io.BytesIO(backup.make_zip(include_certs=False))).namelist())
    check("no certs", any(n.startswith("certs/") for n in names), False)
    check("still has data", "data.json" in names, True)


def test_round_trip():
    seed()
    raw = backup.make_zip()
    original_data = read("data.json")
    original_key = read("certs", "ca.key")
    original_photo = read("images", "meal-20260801-a.jpg")

    for name in os.listdir(DATA):
        path = os.path.join(DATA, name)
        shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)

    result = backup.restore(raw)

    check("data.json back", read("data.json"), original_data)
    check("photo back", read("images", "meal-20260801-a.jpg"), original_photo)
    check("ca key back", read("certs", "ca.key"), original_key)
    check("learned hosts back",
          read("certs", "learned.hosts"), b"meal-planner.local\n192.168.1.42\n")
    check("display settings back",
          json.loads(read("display.json"))["accent"], "sage")
    check("restart asked for", result["restartNeeded"], True)
    check("counts reported", result["contents"]["meals"], 2)

    if os.name != "nt":
        mode = stat.S_IMODE(os.stat(os.path.join(DATA, "certs", "ca.key")).st_mode)
        check("ca key stays private", mode, 0o600)


def test_restore_saves_an_undo():
    seed()
    old = backup.make_zip()

    with open(os.path.join(DATA, "data.json"), "w", encoding="utf-8") as fh:
        json.dump({"meals": [{"id": "m_9", "name": "Toast"}], "people": []}, fh)
    incoming = backup.make_zip()

    with open(os.path.join(DATA, "data.json"), "wb") as fh:
        fh.write(zipfile.ZipFile(io.BytesIO(old)).read("data.json"))
    result = backup.restore(incoming)

    check("restored the incoming one",
          [m["name"] for m in json.loads(read("data.json"))["meals"]], ["Toast"])
    check("undo named", result["undo"].startswith(backup.UNDO_PREFIX), True)

    undo = os.path.join(DATA, result["undo"])
    with open(undo, "rb") as fh:
        backup.restore(fh.read())
    check("undo puts the old data back",
          [m["name"] for m in json.loads(read("data.json"))["meals"]],
          ["Fish pie", "Dal"])


def test_only_keeps_a_couple_of_undos():
    seed()
    raw = backup.make_zip()
    for _ in range(backup.UNDO_KEEP + 3):
        backup.restore(raw)
    kept = [n for n in os.listdir(DATA) if n.startswith(backup.UNDO_PREFIX)]
    check("undos pruned", len(kept) <= backup.UNDO_KEEP, True)


def test_partial_backup_leaves_the_rest_alone():
    seed()
    thin = io.BytesIO()
    with zipfile.ZipFile(thin, "w") as zf:
        zf.writestr("data.json", json.dumps({"meals": [], "people": []}))
        zf.writestr(backup.MANIFEST_NAME, json.dumps(
            {"app": "home-meal-planner", "format": 1, "version": "1.0.0"}))
    result = backup.restore(thin.getvalue())
    check("display untouched", json.loads(read("display.json"))["accent"], "sage")
    check("photos untouched", os.path.isfile(
        os.path.join(DATA, "images", "meal-20260801-a.jpg")), True)
    check("no restart needed", result["restartNeeded"], False)


def _zip(members, manifest=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, payload in members.items():
            zf.writestr(name, payload)
        if manifest is not None:
            zf.writestr(backup.MANIFEST_NAME, json.dumps(manifest))
    return buf.getvalue()


def test_refusals():
    seed()
    good_manifest = {"app": "home-meal-planner", "format": 1, "version": "1.0.0"}
    good_data = json.dumps({"meals": [], "people": []})

    check_raises("not a zip", "zip file",
                 lambda: backup.inspect(b"this is a jpeg, honestly"))

    check_raises("no manifest", "isn't a Home Meal Planner backup",
                 lambda: backup.inspect(_zip({"data.json": good_data})))

    check_raises("someone else's backup", "different app",
                 lambda: backup.inspect(_zip({"data.json": good_data},
                                             {"app": "some-other-app", "format": 1})))

    check_raises("from the future", "newer version",
                 lambda: backup.inspect(_zip({"data.json": good_data},
                                             {"app": "home-meal-planner",
                                              "format": backup.FORMAT + 1})))

    check_raises("no meal data", "no meal data",
                 lambda: backup.inspect(_zip({"cast.json": "{}"}, good_manifest)))

    check_raises("meal data isn't json", "unreadable",
                 lambda: backup.inspect(_zip({"data.json": "{{{"}, good_manifest)))

    check_raises("meal data is the wrong shape", "right shape",
                 lambda: backup.inspect(_zip({"data.json": '{"meals": "lots"}'},
                                             good_manifest)))

    check_raises("escapes upwards", "won't write to",
                 lambda: backup.inspect(_zip(
                     {"data.json": good_data, "../../etc/passwd": "x"},
                     good_manifest)))
    check_raises("absolute path", "won't write to",
                 lambda: backup.inspect(_zip(
                     {"data.json": good_data, "/etc/passwd": "x"},
                     good_manifest)))


def test_a_refused_file_changes_nothing():
    seed()
    before = read("data.json")
    for bad in (b"not a zip at all",
                _zip({"data.json": '{"meals": []}'}),
                _zip({"cast.json": "{}"}, {"app": "home-meal-planner", "format": 1})):
        try:
            backup.restore(bad)
        except backup.BackupError:
            pass
    check("data survived every refusal", read("data.json"), before)
    check("photos survived", os.path.isfile(
        os.path.join(DATA, "images", "meal-20260801-a.jpg")), True)
    check("no undo left behind",
          [n for n in os.listdir(DATA) if n.startswith(backup.UNDO_PREFIX)], [])


def test_inspect_reports_contents():
    seed()
    found = backup.inspect(backup.make_zip())
    check("meals", found["actual"]["meals"], 2)
    check("people", found["actual"]["people"], 1)
    check("images", found["actual"]["images"], 2)
    check("certs", found["actual"]["certs"], True)


for test in [test_zip_holds_everything, test_manifest, test_certs_can_be_left_out,
             test_round_trip, test_restore_saves_an_undo,
             test_only_keeps_a_couple_of_undos,
             test_partial_backup_leaves_the_rest_alone,
             test_refusals, test_a_refused_file_changes_nothing,
             test_inspect_reports_contents]:
    test()

shutil.rmtree(DATA, ignore_errors=True)

if FAILURES:
    print("FAILED (%d)\n" % len(FAILURES))
    for failure in FAILURES:
        print("  - " + failure)
    sys.exit(1)
print("backup: all good")
