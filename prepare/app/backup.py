"""Backups: one JSON file holding everything the household has entered.

THE COMPATIBILITY RULE - read this before changing db.SCHEMA or what a column means
-------------------------------------------------------------------------------------
1. Every backup Prepare has ever written must restore into every later version.
2. Each backup records FORMAT. Adding a table or a column needs nothing here:
   restore fills missing columns with their defaults and ignores columns it
   doesn't know. Anything else - renaming or dropping a column, changing what
   a value means, splitting a table - bumps FORMAT and adds a step to
   MIGRATIONS that turns format N-1 data into format N.
3. tests/backups/ keeps one real backup per format (format-1.json, ...).
   tests/test_backup.py restores every one of them and fails if the file for
   the current FORMAT is missing. Never edit or delete those files.
4. If a change ever can't be written as a migration, raise MIN_RESTORABLE to
   the new FORMAT. Older files are then refused with a clear message, and the
   app asks the household to download a new backup straight away.

What's in a backup: every table the household fills in (inventory, household
members, medication, plans, contacts, kit targets, settings and household
details, remembered barcodes and product types, the activity log). What isn't:
the https certificates (made again on start) and the light/dark choice, which
each phone keeps for itself.
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from . import db

FORMAT = 1
MIN_RESTORABLE = 1
KIND = "prepare-backup"

# Restore order. Every table here is replaced as a whole by what's in the file.
TABLES = ["settings", "members", "categories", "items", "medications", "plans", "contacts", "products", "events"]

# Settings that describe this installation's own backups, not the household.
# They're left out of backups and never overwritten by a restore.
LOCAL_SETTINGS = {"backup_last_at", "backup_last_kind", "backup_downloaded_at", "backup_downloaded_format",
                  "app_version_seen"}

# MIGRATIONS[n] turns format n data into format n+1, in place. Keep every step forever.
MIGRATIONS: dict = {
    # 1: lambda data: ...,   # example: rename items.where -> items.location
}

KEEP = {"daily": 14, "upgrade": 6, "before-restore": 6, "manual": 10}
FILE_RE = re.compile(r"^prepare-(daily|upgrade|before-restore|manual)-\d{8}-\d{6}(-[A-Za-z0-9.-]+)?\.(json|db)$")
MAX_UPLOAD = 25 * 1024 * 1024


class BackupError(ValueError):
    """Something the household can read and act on."""


def backup_dir() -> Path:
    d = db.DATA_DIR / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tables_present(c: sqlite3.Connection) -> set[str]:
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(c: sqlite3.Connection, table: str) -> dict[str, dict]:
    return {r[1]: {"notnull": r[3], "default": r[4], "pk": r[5]} for r in c.execute(f"PRAGMA table_info({table})")}


# ---------- export ----------

def export(app_version: str) -> dict:
    out: dict = {"kind": KIND, "format": FORMAT, "app_version": app_version, "created": db.now_iso(),
                 "counts": {}, "tables": {}}
    with db.connect() as c:
        present = _tables_present(c)
        for t in TABLES:
            if t not in present:
                continue
            rows = [dict(r) for r in c.execute(f"SELECT * FROM {t}")]
            if t == "settings":
                rows = [r for r in rows if r["key"] not in LOCAL_SETTINGS]
            out["tables"][t] = rows
            out["counts"][t] = len(rows)
    return out


def dumps(data: dict) -> bytes:
    return json.dumps(data, indent=1, ensure_ascii=False, default=str).encode("utf-8")


# ---------- reading a file ----------

def parse(raw: bytes) -> dict:
    """Read and check a backup file; returns it migrated to the current FORMAT. Never touches the database."""
    if len(raw) > MAX_UPLOAD:
        raise BackupError("That file is too big to be a Prepare backup.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BackupError("That isn't a Prepare backup: it isn't a JSON file.") from None
    if not isinstance(data, dict) or data.get("kind") != KIND:
        raise BackupError("That isn't a Prepare backup.")
    fmt = data.get("format")
    if not isinstance(fmt, int) or fmt < 1:
        raise BackupError("That backup doesn't say which format it uses, so it can't be read safely.")
    if fmt > FORMAT:
        raise BackupError(f"That backup was made by a newer version of Prepare ({data.get('app_version', '?')}). "
                          "Update the app, then restore it.")
    if fmt < MIN_RESTORABLE:
        raise BackupError(f"That backup is from Prepare {data.get('app_version', '?')}, before a change this version "
                          "can't convert. Restore it with that version, then take a new backup.")
    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise BackupError("That backup is damaged: it has no data in it.")
    for t, rows in tables.items():
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise BackupError(f"That backup is damaged: '{t}' isn't a list of records.")
        for r in rows:
            for v in r.values():
                if v is not None and not isinstance(v, (str, int, float, bool)):
                    raise BackupError(f"That backup is damaged: '{t}' has a value that isn't plain text or a number.")
    while data["format"] < FORMAT:
        MIGRATIONS[data["format"]](data)
        data["format"] += 1
    return data


def summary(data: dict) -> dict:
    t = data.get("tables", {})
    active = [i for i in t.get("items", []) if i.get("status", "active") == "active"]
    s = {r.get("key"): r.get("value") for r in t.get("settings", [])}
    return {
        "created": data.get("created", ""),
        "app_version": data.get("app_version", "?"),
        "format": data.get("format"),
        "household_name": s.get("household_name") or "",
        "stock": len(active),
        "items_all": len(t.get("items", [])),
        "members": len(t.get("members", [])),
        "medications": len([m for m in t.get("medications", []) if m.get("status", "active") == "active"]),
        "plans": len(t.get("plans", [])),
        "contacts": len(t.get("contacts", [])),
        "products": len(t.get("products", [])),
    }


def current_summary(app_version: str) -> dict:
    return summary(export(app_version))


# ---------- restore ----------

def restore(data: dict) -> dict:
    """Replace the household's data with a parsed backup. All or nothing.

    Tables the backup doesn't have (added in a later version) are left alone.
    Settings are merged: keys in the file win, others keep their current value."""
    with db.connect() as c:  # one transaction: any error rolls the whole restore back
        present = _tables_present(c)
        for t in TABLES:
            if t not in data["tables"] or t not in present:
                continue
            cols = _columns(c, t)
            rows = data["tables"][t]
            if t == "settings":
                for r in rows:
                    k = r.get("key")
                    if isinstance(k, str) and k not in LOCAL_SETTINGS:
                        v = r.get("value")
                        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
                                  (k, "" if v is None else str(v)))
                continue
            c.execute(f"DELETE FROM {t}")
            for r in rows:
                use = [k for k in r if k in cols]
                missing = [k for k, info in cols.items() if info["notnull"] and info["default"] is None
                           and not info["pk"] and r.get(k) is None]
                if missing:
                    raise BackupError(f"That backup is damaged: a record in '{t}' has no {missing[0]}.")
                if not use:
                    continue
                c.execute(f"INSERT INTO {t}({', '.join(use)}) VALUES ({', '.join('?' * len(use))})",
                          [r[k] for k in use])
    db.init()  # anything newer than the backup: default settings, new kit categories
    return summary(data)


# ---------- files kept on Home Assistant ----------

def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def save(kind: str, app_version: str, note: str = "") -> Path:
    data = export(app_version)
    suffix = f"-{note}" if note else ""
    path = backup_dir() / f"prepare-{kind}-{_stamp()}{suffix}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(dumps(data))
    tmp.replace(path)
    db.set_setting("backup_last_at", data["created"])
    db.set_setting("backup_last_kind", kind)
    prune()
    return path


def copy_database(note: str) -> Path | None:
    """A straight copy of the database file, taken before an upgrade changes it."""
    if not db.DB_PATH.exists():
        return None
    path = backup_dir() / f"prepare-upgrade-{_stamp()}-{note}.db"
    src = sqlite3.connect(db.DB_PATH)
    dst = sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return path


def prune() -> None:
    files: dict[str, list[Path]] = {}
    for p in backup_dir().iterdir():
        m = FILE_RE.match(p.name)
        if m:
            files.setdefault(m.group(1), []).append(p)
    for kind, paths in files.items():
        keep = KEEP.get(kind, 10)
        # .db copies sit beside their .json partner, so allow twice as many upgrade files.
        if kind == "upgrade":
            keep *= 2
        for p in sorted(paths, key=lambda x: x.name, reverse=True)[keep:]:
            p.unlink(missing_ok=True)


def list_files() -> list[dict]:
    out = []
    for p in backup_dir().iterdir():
        m = FILE_RE.match(p.name)
        if not m:
            continue
        st = p.stat()
        out.append({"name": p.name, "kind": m.group(1), "type": m.group(3), "bytes": st.st_size,
                    "when": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    out.sort(key=lambda f: f["when"], reverse=True)
    return out


def file_path(name: str) -> Path | None:
    if not FILE_RE.match(name or ""):
        return None
    p = backup_dir() / name
    return p if p.is_file() else None


# ---------- when to back up ----------

def has_data() -> bool:
    """True once the household has entered anything worth keeping."""
    if not db.DB_PATH.exists():
        return False
    try:
        with db.connect() as c:
            present = _tables_present(c)
            return any(c.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone()
                       for t in ("items", "members", "medications", "contacts") if t in present)
    except sqlite3.Error:
        return False


def before_init(app_version: str) -> str | None:
    """Called before db.init() runs migrations. Returns the previous version if this start is an upgrade."""
    if not db.DB_PATH.exists():
        return None
    try:
        with db.connect() as c:
            row = c.execute("SELECT value FROM settings WHERE key='app_version_seen'").fetchone()
    except sqlite3.Error:
        row = None
    seen = row[0] if row else ""
    if seen == app_version:
        return None
    if has_data():
        copy_database(f"from-{seen or 'old'}")
    return seen or "old"


def after_init(app_version: str, upgraded_from: str | None) -> None:
    """Called once db.init() has brought the database up to date."""
    if upgraded_from is not None and has_data():
        save("upgrade", app_version, f"to-{app_version}")
    db.set_setting("app_version_seen", app_version)
    daily(app_version)


def daily(app_version: str) -> Path | None:
    """At most one automatic backup a day, and only when something has changed since the last one."""
    s = db.settings()
    last, changed = s.get("backup_last_at") or "", s.get("data_changed_at") or ""
    if not has_data():
        return None
    if last and (changed <= last or datetime.fromisoformat(last) > datetime.now() - timedelta(hours=20)):
        return None
    return save("daily", app_version)


def status() -> dict:
    """For the dashboard and the HA integration: is there a recent backup off this machine?"""
    s = db.settings()
    downloaded = s.get("backup_downloaded_at") or ""
    fmt = int(s.get("backup_downloaded_format") or 0)
    changed = s.get("data_changed_at") or ""
    stale = bool(downloaded) and datetime.fromisoformat(downloaded) < datetime.now() - timedelta(days=30)
    too_old = bool(downloaded) and fmt < MIN_RESTORABLE
    data = has_data()
    return {
        "last_at": s.get("backup_last_at") or "",
        "downloaded_at": downloaded,
        "too_old": too_old,
        "never": data and not downloaded,
        # Due: never downloaded, the downloaded copy can't be restored any more,
        # or it's over a month old and things have changed since.
        "due": data and (not downloaded or too_old or (stale and changed > downloaded)),
    }


def mark_downloaded() -> None:
    db.set_setting("backup_downloaded_at", db.now_iso())
    db.set_setting("backup_downloaded_format", str(FORMAT))
