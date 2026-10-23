"""SQLite storage. One file in the App's /data folder, so HA backups include it."""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

DATA_DIR = Path(os.environ.get("PREPARE_DATA", "/data"))  # /data = the HA App's data folder
DB_PATH = DATA_DIR / "prepare.db"
SEED_DIR = Path(__file__).parent / "seed"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS members (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'adult',
  dietary TEXT DEFAULT '', notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS categories (
  key TEXT PRIMARY KEY, name TEXT, unit TEXT, basis TEXT, amount REAL,
  in_score INTEGER, guidance TEXT, sort INTEGER, grp TEXT);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT, quantity REAL DEFAULT 1,
  unit TEXT DEFAULT '', location TEXT DEFAULT '', best_before TEXT,
  perishable INTEGER DEFAULT 0, notes TEXT DEFAULT '', added TEXT,
  status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS medications (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, strength TEXT DEFAULT '', dose TEXT DEFAULT '',
  quantity TEXT DEFAULT '', expiry TEXT, owner_id INTEGER, repeat_due TEXT,
  notes TEXT DEFAULT '', status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY, scenario TEXT NOT NULL, steps TEXT DEFAULT '',
  meeting_point TEXT DEFAULT '', roles TEXT DEFAULT '', grab_bag TEXT DEFAULT '',
  notes TEXT DEFAULT '', info_url TEXT DEFAULT '', last_reviewed TEXT, sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT DEFAULT '', phone TEXT DEFAULT '',
  phone2 TEXT DEFAULT '', notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS products (
  barcode TEXT PRIMARY KEY, name TEXT, brand TEXT, generic TEXT, category TEXT,
  pack_amount REAL, quantity_text TEXT, source TEXT, image_url TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, ts TEXT, action TEXT, detail TEXT);
"""

DEFAULT_SETTINGS = {
    "warning_days": "30",
    "target_days": "3",
    "review_months": "6",
    "repeat_warning_days": "7",
    "household_name": "",
    "address": "",
    "meeting_near": "",
    "meeting_far": "",
    "radio_stations": "",
    "energy_supplier": "",
    "water_supplier": "",
    "insurance": "",
    "backup_plan": "",
    "neighbours": "",
    "grab_bag": "",
    "pack_last_printed": "",
    "data_changed_at": "",
    "kit_last_checked": "",
}

# Household details shown on the Household page and printed in the pack.
HOUSEHOLD_FIELDS = [
    ("household_name", "Household name", "text"),
    ("address", "Address (for 999 calls)", "textarea"),
    ("meeting_near", "Meeting point near home", "text"),
    ("meeting_far", "Meeting point away from the area (e.g. family member's home)", "text"),
    ("radio_stations", "Local radio stations and FM frequencies", "textarea"),
    ("energy_supplier", "Energy supplier / account no. (power cuts: call 105)", "textarea"),
    ("water_supplier", "Water supplier / account no.", "textarea"),
    ("insurance", "Insurance details (home, contents, policy numbers)", "textarea"),
    ("backup_plan", "Backup plan for anyone needing extra support or who can't be reached by phone", "textarea"),
    ("neighbours", "Neighbours to check on / who check on us", "textarea"),
    ("grab_bag", "Grab bag: where it is and what's in it", "textarea"),
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with connect() as c:
        c.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        seed = yaml.safe_load((SEED_DIR / "categories.yaml").read_text())
        # 0.1.x databases predate checklist groups: add the column, then fill it from the seed.
        if "grp" not in [r[1] for r in c.execute("PRAGMA table_info(categories)")]:
            c.execute("ALTER TABLE categories ADD COLUMN grp TEXT")
        # 0.3: scanned products carry a barcode, a brand, and a product type ("generic")
        # that groups different brands of the same thing.
        item_cols = [r[1] for r in c.execute("PRAGMA table_info(items)")]
        for col in ("barcode", "brand", "generic", "role"):
            if col not in item_cols:
                c.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT")
        # 0.5: food plays a part in a meal - meal / base / topping / extra (products.ROLES).
        if "role" not in [r[1] for r in c.execute("PRAGMA table_info(products)")]:
            c.execute("ALTER TABLE products ADD COLUMN role TEXT")
        # Seed categories the database doesn't have yet: all of them on a new install,
        # and any added in a later version (also after restoring an older backup).
        # Existing ones keep the household's own targets.
        for i, cat in enumerate(seed["categories"]):
            c.execute(
                "INSERT OR IGNORE INTO categories(key, name, unit, basis, amount, in_score, guidance, sort, grp) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (cat["key"], cat["name"], cat["unit"], cat["basis"], cat["amount"],
                 1 if cat.get("in_score", True) else 0, cat.get("guidance", ""), i, cat.get("group", "")),
            )
        for cat in seed["categories"]:
            c.execute("UPDATE categories SET grp=? WHERE key=? AND grp IS NULL", (cat.get("group", ""), cat["key"]))
        if c.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 0:
            seed = yaml.safe_load((SEED_DIR / "plans.yaml").read_text())
            for i, p in enumerate(seed["plans"]):
                c.execute(
                    "INSERT INTO plans(scenario, steps, info_url, sort) VALUES (?,?,?,?)",
                    (p["scenario"], p["steps"].strip(), p.get("info_url", ""), i),
                )


    from . import products  # products imports db, so import here, once the tables exist
    products.assign_roles()


def checklist_groups() -> list[dict]:
    """The Be Ready checklist sections, in checklist order."""
    return yaml.safe_load((SEED_DIR / "categories.yaml").read_text())["groups"]


def general_actions() -> list[str]:
    return yaml.safe_load((SEED_DIR / "plans.yaml").read_text())["general_actions"]


def settings() -> dict:
    with connect() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}


def set_setting(key: str, value: str) -> None:
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, value))


def log(action: str, detail: str = "") -> None:
    with connect() as c:
        c.execute("INSERT INTO events(ts, action, detail) VALUES (?,?,?)", (now_iso(), action, detail))


def mark_changed() -> None:
    set_setting("data_changed_at", now_iso())


def rows(sql: str, args=()) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute(sql, args)]


def row(sql: str, args=()) -> dict | None:
    r = rows(sql, args)
    return r[0] if r else None


def execute(sql: str, args=()) -> int:
    with connect() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid
