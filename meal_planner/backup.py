"""
Backup and restore: everything the household has put into the planner, in one
zip file.

Why this exists: the app's own files come from the repository and can always be
reinstalled, but /data cannot - the meals, the plan, the photos taken in the
kitchen, and the private certificate authority every phone in the house has been
told to trust. Home Assistant's whole-system backup covers /data too, but
restoring one is an all-or-nothing operation on the entire machine, which is far
too big a hammer for "I want to reinstall the app from the repository and keep
my meals".

So: a Download button that produces a single file, and a Restore that takes one
back. The round trip is deliberately dull - replace what is there, having first
put the old contents somewhere recoverable.

A word about certs/. It is in the backup on purpose. tls.py's CA is created once
and never regenerated, because regenerating it silently breaks the trust already
installed on every phone. A reinstall without the old certs/ would do exactly
that. Carrying it through the round trip means a reinstalled app comes back with
the same CA and the phones never notice. It also means the zip contains a
private key, which is why nothing here ever puts one on a network - see
server.py, where /api/backup is a plain download over the LAN, same as the
photos.
"""

import io
import json
import os
import re
import shutil
import time
import zipfile
from datetime import datetime

# Same rule the other modules use, so a test can point all of them at a tmpdir
# by setting one variable.
DATA_DIR = (os.environ.get("MEAL_PLANNER_DATA_DIR")
            or os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Bumped only if the layout inside the zip changes in a way an older restore
# could not cope with. A backup carrying a higher number than this copy knows
# about is refused rather than half-applied.
FORMAT = 1

MANIFEST_NAME = "meal-planner-backup.json"

# Single files taken as they are. data.json is the planner itself; the rest are
# settings that belong to the house rather than to a phone, so a restored app
# should come back with the same kitchen display, the same look and the same
# speakers on the dinner bell.
FILES = ("data.json", "cast.json", "display.json", "bell.json")

# data.json carries the star ratings, because they are kept on the sittings
# inside the weeks rather than in a file of their own - so they have been in
# every backup since they existed, and copying the file whole is what keeps
# that true without anyone having to remember. _data_counts() says so out loud
# on the restore screen, which is the only place the question ever gets asked.

# Whole folders. images/ is the photos; certs/ is the private CA, the server
# certificate and learned.hosts, which together are what keeps https working
# without setting every phone up again; chime/ is the sound somebody chose for
# the dinner bell, which is small, theirs, and not in the repository.
DIRS = ("images", "certs", "chime")

# The daily snapshots server.py keeps are deliberately left out: they are a
# local undo for a bad edit, not something worth carrying to a new install, and
# they would multiply the size of the zip for no benefit.

# Guards. The first two stop a hostile or corrupt zip from filling the disk; the
# third is the ceiling on what the server will accept off the wire.
MAX_MEMBERS = 20000
MAX_UNPACKED = 2_000_000_000        # 2 GB of photos would already be absurd
MAX_UPLOAD = 500_000_000

UNDO_PREFIX = "restore-undo-"
UNDO_KEEP = 2


class BackupError(Exception):
    """Something about the file is wrong. The message is written to be shown to
    whoever pressed the button, so it says what to do rather than what failed."""


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def app_version():
    """The app version, read off config.yaml. Recorded in the manifest so a zip
    found in a downloads folder in two years can be identified. Never fatal: the
    version is a label, not something the restore depends on."""
    try:
        with open(os.path.join(BASE_DIR, "config.yaml"), "r", encoding="utf-8") as fh:
            for line in fh:
                match = re.match(r'^version:\s*"?([^"\s]+)"?', line)
                if match:
                    return match.group(1)
    except OSError:
        pass
    return "unknown"


def _walk(root):
    """(absolute path, path relative to root) for every file under root."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            yield full, os.path.relpath(full, root).replace(os.sep, "/")


def _safe_member(name):
    """True if a name inside the zip is one we are willing to write.

    Absolute paths and .. segments are the classic way a zip escapes the folder
    it is being unpacked into. Nothing this code writes ever needs either, so
    both are refused outright rather than normalised and hoped about."""
    if not name or name.startswith("/") or name.startswith("\\"):
        return False
    if ":" in name.split("/")[0]:            # C:\ and friends
        return False
    parts = name.replace("\\", "/").split("/")
    return ".." not in parts and "" not in parts[:-1]


def _data_counts(data):
    """What a data.json holds, as numbers a person would recognise.

    One function for both ends of the round trip: the live count on the backup
    card and the count read out of a zip on the restore screen. Two versions of
    this would eventually disagree, and the one place a disagreement would show
    up is the screen that asks "replace all of this with all of that".

    Written to survive anything, because half of its callers are handed a file
    off the wire: every level is type-checked and a shape it doesn't recognise
    contributes nothing rather than raising.

    `weeks` counts weeks with something actually planned in them, not keys in
    the dict - an empty week gets written the moment somebody looks at one.
    `ratings` counts individual stars given, one per person per sitting, which
    is the number that grows as the household uses the thing."""
    out = {"meals": 0, "people": 0, "weeks": 0, "ratings": 0}
    if not isinstance(data, dict):
        return out
    if isinstance(data.get("meals"), list):
        out["meals"] = len(data["meals"])
    if isinstance(data.get("people"), list):
        out["people"] = len(data["people"])

    weeks = data.get("weeks")
    if not isinstance(weeks, dict):
        return out
    for week in weeks.values():
        if not isinstance(week, dict):
            continue
        used = False
        for cell in week.values():
            if not isinstance(cell, dict):
                continue
            sittings = cell.get("sittings")
            if not isinstance(sittings, list):
                continue
            for sitting in sittings:
                if not isinstance(sitting, dict):
                    continue
                # A block with a meal or somebody eating counts as planned. A
                # bare id with nothing on it is a row someone opened and left.
                if sitting.get("mealId") or sitting.get("eaters"):
                    used = True
                ratings = sitting.get("ratings")
                if isinstance(ratings, dict):
                    out["ratings"] += len(ratings)
        if used:
            out["weeks"] += 1
    return out


def _counts():
    """A few numbers for the manifest, so the restore screen can say what is in
    the file before replacing anything with it."""
    out = {"meals": 0, "people": 0, "weeks": 0, "ratings": 0, "images": 0}
    try:
        with open(os.path.join(DATA_DIR, "data.json"), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        out.update(_data_counts(data))
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    images = os.path.join(DATA_DIR, "images")
    if os.path.isdir(images):
        out["images"] = sum(1 for _ in _walk(images))
    return out


def suggested_name():
    return "meal-planner-backup-%s.zip" % datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# making one
# --------------------------------------------------------------------------

def make_zip(include_certs=True):
    """The whole data directory's worth of your things, as zip bytes.

    Built in memory rather than streamed to a temp file: the photos are the only
    thing with any size to them and a household's worth runs to tens of
    megabytes, which is nothing next to what the app already holds in RAM while
    serving them. Doing it this way means the response has a Content-Length, so
    a phone shows a progress bar instead of a spinner."""
    buf = io.BytesIO()
    manifest = {
        "format": FORMAT,
        "app": "home-meal-planner",
        "version": app_version(),
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "includesCerts": False,
        "contents": _counts(),
    }

    # ZIP_DEFLATED throughout. JSON compresses to a fraction of itself; the JPEGs
    # do not compress at all, but deflate on already-compressed data costs a few
    # per cent of CPU and no size, which on a Pi is a fair trade for one file.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name in FILES:
            path = os.path.join(DATA_DIR, name)
            if os.path.isfile(path):
                zf.write(path, name)
        for folder in DIRS:
            if folder == "certs" and not include_certs:
                continue
            root = os.path.join(DATA_DIR, folder)
            if not os.path.isdir(root):
                continue
            wrote = False
            for full, rel in _walk(root):
                zf.write(full, "%s/%s" % (folder, rel))
                wrote = True
            if folder == "certs" and wrote:
                manifest["includesCerts"] = True

        # Written last so it reflects what actually went in.
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n")

    return buf.getvalue()


# --------------------------------------------------------------------------
# reading one back
# --------------------------------------------------------------------------

def _open(raw):
    if len(raw) > MAX_UPLOAD:
        raise BackupError("That file is too big to be a planner backup.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, OSError):
        raise BackupError("That isn't a zip file, or it didn't finish "
                          "downloading. Try the download again.")
    if zf.testzip() is not None:
        raise BackupError("That zip is damaged. Try the download again.")
    return zf


def inspect(raw):
    """What a zip says it holds, without touching anything on disk.

    Separate from restore() so the confirmation step can name what is about to
    replace the current data - "142 meals, 96 photos, made on 3 August" is a
    much better thing to say yes to than "are you sure"."""
    zf = _open(raw)
    names = zf.namelist()

    if len(names) > MAX_MEMBERS:
        raise BackupError("That zip has far more files in it than a planner "
                          "backup ever would.")
    total = sum(info.file_size for info in zf.infolist())
    if total > MAX_UNPACKED:
        raise BackupError("That zip unpacks to more than this app will write. "
                          "It doesn't look like a planner backup.")
    for name in names:
        if not _safe_member(name):
            raise BackupError("That zip contains a file path this app won't "
                              "write to. It hasn't been touched.")

    if MANIFEST_NAME not in names:
        raise BackupError("That zip has no %s in it, so it isn't a Home Meal "
                          "Planner backup." % MANIFEST_NAME)
    try:
        manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise BackupError("The backup's own description couldn't be read, so "
                          "nothing has been changed.")
    if not isinstance(manifest, dict) or manifest.get("app") != "home-meal-planner":
        raise BackupError("That backup was made by a different app.")
    if int(manifest.get("format") or 0) > FORMAT:
        raise BackupError(
            "That backup was made by a newer version of the planner (format %s, "
            "this one reads %s). Update the app and try again."
            % (manifest.get("format"), FORMAT))

    if "data.json" not in names:
        raise BackupError("That backup has no meal data in it.")
    try:
        data = json.loads(zf.read("data.json").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise BackupError("The meal data inside that backup is unreadable, so "
                          "nothing has been changed.")
    if not isinstance(data, dict) or not isinstance(data.get("meals"), list):
        raise BackupError("The meal data inside that backup isn't the right "
                          "shape, so nothing has been changed.")

    # Counted out of the zip's own data.json rather than read off its manifest.
    # The manifest is what the writing app said; this is what is actually in
    # there, and the confirmation screen should only ever promise the second.
    # It is also how a backup written before these numbers existed still gets
    # described in full.
    manifest["_names"] = names
    manifest["actual"] = dict(_data_counts(data), **{
        "images": sum(1 for n in names if n.startswith("images/")),
        "certs": any(n.startswith("certs/") for n in names),
        "bytes": len(raw),
    })
    return manifest


def _snapshot_undo():
    """Zip up what is there now, before it stops being there.

    Restore is the one action in the app that throws things away, and the most
    likely mistake is restoring the wrong file. This makes that mistake
    recoverable from the same screen: the undo is itself a valid backup, so it
    goes back in through the same door it came out of."""
    path = os.path.join(DATA_DIR, UNDO_PREFIX + time.strftime("%Y%m%d-%H%M%S") + ".zip")
    try:
        with open(path, "wb") as fh:
            fh.write(make_zip())
    except OSError as exc:
        raise BackupError("Couldn't save a copy of the current data first, so "
                          "the restore was stopped: %s" % exc)
    _prune_undo()
    return os.path.basename(path)


def _prune_undo():
    try:
        names = sorted(n for n in os.listdir(DATA_DIR)
                       if n.startswith(UNDO_PREFIX) and n.endswith(".zip"))
    except OSError:
        return
    for name in names[:-UNDO_KEEP]:
        try:
            os.remove(os.path.join(DATA_DIR, name))
        except OSError:
            pass


def undo_files():
    """The undo snapshots on disk, newest first, for the screen to offer."""
    try:
        names = sorted((n for n in os.listdir(DATA_DIR)
                        if n.startswith(UNDO_PREFIX) and n.endswith(".zip")),
                       reverse=True)
    except OSError:
        return []
    out = []
    for name in names:
        try:
            st = os.stat(os.path.join(DATA_DIR, name))
        except OSError:
            continue
        out.append({"name": name, "bytes": st.st_size,
                    "at": datetime.fromtimestamp(st.st_mtime)
                          .isoformat(timespec="seconds")})
    return out


def _write_atomic(path, payload):
    tmp = path + ".restoring"
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _replace_dir(zf, folder, names):
    """Swap a whole folder for the version in the zip.

    Unpacked alongside first and only moved into place once every file is
    written, so an interruption halfway leaves the existing folder untouched
    rather than half-replaced. The old one is moved aside rather than deleted
    outright, and only removed once the new one is in place."""
    root = os.path.join(DATA_DIR, folder)
    staging = os.path.join(DATA_DIR, "." + folder + ".restoring")
    old = os.path.join(DATA_DIR, "." + folder + ".replaced")
    for path in (staging, old):
        shutil.rmtree(path, ignore_errors=True)

    os.makedirs(staging, exist_ok=True)
    prefix = folder + "/"
    for name in names:
        if not name.startswith(prefix) or name.endswith("/"):
            continue
        target = os.path.join(staging, *name[len(prefix):].split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(name) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 256)

    if os.path.isdir(root):
        os.replace(root, old)
    os.replace(staging, root)
    shutil.rmtree(old, ignore_errors=True)

    # The CA key is the one thing in here that must not be world-readable, and
    # zip carries no permissions worth trusting. tls.py sets this on creation;
    # a restore has to set it again.
    if folder == "certs":
        for name in ("ca.key", "server.key"):
            path = os.path.join(root, name)
            if os.path.isfile(path):
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass


def restore(raw):
    """Replace the current data with the contents of a backup zip.

    Wholesale, on purpose: the case this is built for is "uninstall, reinstall
    from the repository, put my data back", and a merge would leave the result
    depending on what the fresh install happened to seed itself with. Anything
    the zip does not carry is left alone rather than deleted, so an older backup
    made before, say, display.json existed does not wipe the display settings.

    Returns a summary for the screen, including which parts landed and whether a
    restart is needed for them to take effect."""
    manifest = inspect(raw)
    names = manifest.pop("_names")
    zf = _open(raw)

    undo = _snapshot_undo()

    restored = []
    for name in FILES:
        if name in names:
            _write_atomic(os.path.join(DATA_DIR, name), zf.read(name))
            restored.append(name)
    for folder in DIRS:
        if any(n.startswith(folder + "/") for n in names):
            _replace_dir(zf, folder, names)
            restored.append(folder + "/")

    return {
        "ok": True,
        "restored": restored,
        "undo": undo,
        "contents": manifest.get("actual", {}),
        "from": {"version": manifest.get("version"),
                 "createdAt": manifest.get("createdAt")},
        # data.json, cast.json, display.json and the photos are all read from
        # disk on demand, so they are live the moment they land. The certificate
        # is the exception: it was loaded into an SSL context when the server
        # started and stays there until it starts again.
        "restartNeeded": "certs/" in restored,
    }
