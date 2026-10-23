"""Backups: round trips, every past format, and refusing bad files without touching anything.

The files in tests/backups/ are real backups, one per format. Never edit or
delete them: they're how we know a household's old backup still restores.
"""
import json
import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("PREPARE_DATA", tempfile.mkdtemp())  # never the real /data, even at import
from app import backup, db  # noqa: E402

FIXTURES = Path(__file__).parent / "backups"


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "prepare.db")
    db.init()
    return tmp_path


def populate():
    db.execute("INSERT INTO members(name, type) VALUES ('Alex', 'adult')")
    mid = db.execute("INSERT INTO members(name, type, dietary) VALUES ('Sam', 'child', 'no nuts')")
    db.execute("INSERT INTO items(name, category, quantity, unit, best_before, brand, generic, barcode, added) "
               "VALUES ('Heinz Beanz', 'food', 4, 'meals', '2027-03-01', 'Heinz', 'Baked beans', '5000157024671', '2026-10-23')")
    db.execute("INSERT INTO medications(name, owner_id, expiry) VALUES ('Inhaler', ?, '2027-01-01')", (mid,))
    db.execute("INSERT INTO contacts(name, phone) VALUES ('Gran', '01747 000000')")
    db.execute("UPDATE categories SET amount=5, in_score=0 WHERE key='water'")
    db.execute("INSERT INTO products(barcode, name, brand, generic) VALUES ('5000157024671', 'Beanz', 'Heinz', 'Baked beans')")
    db.set_setting("household_name", "Test household")
    db.set_setting("warning_days", "21")


def comparable(data):
    t = {k: v for k, v in data["tables"].items() if k != "events"}
    t["settings"] = sorted((r for r in t["settings"] if r["key"] != "data_changed_at"), key=lambda r: r["key"])
    return t


def test_round_trip(fresh):
    populate()
    db.init()  # as on every start: fills in anything newer, e.g. food roles
    before = backup.export("test")
    raw = backup.dumps(before)
    db.DB_PATH.unlink()
    db.init()
    assert db.row("SELECT COUNT(*) n FROM items")["n"] == 0
    backup.restore(backup.parse(raw))
    after = backup.export("test")
    assert comparable(after) == comparable(before)
    # ids survive, so medication still belongs to the right person
    assert db.row("SELECT m.name FROM medications x JOIN members m ON m.id = x.owner_id")["name"] == "Sam"


def test_restore_replaces_everything(fresh):
    populate()
    raw = backup.dumps(backup.export("test"))
    db.execute("INSERT INTO items(name) VALUES ('Added later')")
    db.execute("DELETE FROM contacts")
    backup.restore(backup.parse(raw))
    assert [r["name"] for r in db.rows("SELECT name FROM items")] == ["Heinz Beanz"]
    assert db.row("SELECT name FROM contacts")["name"] == "Gran"


def test_every_format_still_restores(fresh):
    files = sorted(FIXTURES.glob("format-*.json"))
    have = {int(p.stem.split("-")[1]) for p in files}
    # Bumping backup.FORMAT means adding a real backup of the new format here.
    assert have == set(range(1, backup.FORMAT + 1)), f"tests/backups needs format-{backup.FORMAT}.json"
    for p in files:
        raw = p.read_bytes()
        data = backup.parse(raw)
        backup.restore(data)
        original = json.loads(raw)
        for table in ("items", "members", "medications", "plans", "contacts", "products"):
            assert db.row(f"SELECT COUNT(*) n FROM {table}")["n"] == len(original["tables"][table]), (p.name, table)
        s = db.settings()
        for row in original["tables"]["settings"]:
            if row["key"] not in backup.LOCAL_SETTINGS:
                assert s[row["key"]] == row["value"], (p.name, row["key"])


def test_new_and_unknown_columns(fresh):
    """Older files lack newer columns (defaults fill them); unknown ones are ignored."""
    data = backup.export("test")
    data["tables"]["items"] = [{"id": 1, "name": "Old-style item", "category": "food", "quantity": 2,
                                "column_from_the_future": "x"}]
    del data["tables"]["products"]  # a table the file predates is left alone
    db.execute("INSERT INTO products(barcode, name) VALUES ('1', 'kept')")
    backup.restore(backup.parse(backup.dumps(data)))
    item = db.row("SELECT * FROM items")
    assert item["name"] == "Old-style item" and item["status"] == "active" and item["brand"] is None
    assert db.row("SELECT name FROM products")["name"] == "kept"


def test_new_kit_categories_appear_after_restore(fresh):
    data = backup.export("test")
    data["tables"]["categories"] = [c for c in data["tables"]["categories"] if c["key"] != "radio"]
    backup.restore(backup.parse(backup.dumps(data)))
    assert db.row("SELECT key FROM categories WHERE key='radio'")


@pytest.mark.parametrize("raw, message", [
    (b"not json", "isn't a JSON"),
    (b'{"kind": "something else"}', "isn't a Prepare backup"),
    (b'{"kind": "prepare-backup", "format": 99, "tables": {}}', "newer version"),
    (b'{"kind": "prepare-backup", "format": 1, "tables": {"items": "x"}}', "damaged"),
    (b'{"kind": "prepare-backup", "format": 1, "tables": {"items": [{"name": {"a": 1}}]}}', "damaged"),
])
def test_bad_files_are_refused(fresh, raw, message):
    with pytest.raises(backup.BackupError, match=message):
        backup.parse(raw)


def test_failed_restore_changes_nothing(fresh):
    populate()
    data = backup.export("test")
    data["tables"]["items"] = [{"id": 1, "name": "fine"}, {"id": 2, "category": "food"}]  # second has no name
    with pytest.raises(backup.BackupError, match="no name"):
        backup.restore(backup.parse(backup.dumps(data)))
    assert [r["name"] for r in db.rows("SELECT name FROM items")] == ["Heinz Beanz"]


def test_local_settings_are_not_carried(fresh):
    backup.mark_downloaded()
    data = backup.export("test")
    assert not {r["key"] for r in data["tables"]["settings"]} & backup.LOCAL_SETTINGS
    when = db.settings()["backup_downloaded_at"]
    data["tables"]["settings"].append({"key": "backup_downloaded_at", "value": "2000-01-01T00:00:00"})
    backup.restore(backup.parse(backup.dumps(data)))
    assert db.settings()["backup_downloaded_at"] == when


def test_upgrade_takes_backups(fresh):
    populate()
    assert backup.before_init("9.9.9") is not None  # never seen this version: an upgrade
    db.init()
    backup.after_init("9.9.9", "old")
    kinds = sorted((f["kind"], f["type"]) for f in backup.list_files())
    assert kinds == [("upgrade", "db"), ("upgrade", "json")]
    assert backup.before_init("9.9.9") is None  # same version again: nothing new
    backup.after_init("9.9.9", None)
    assert len(backup.list_files()) == 2


def test_daily_only_after_changes(fresh):
    assert backup.daily("t") is None  # nothing entered yet
    populate()
    db.mark_changed()
    assert backup.daily("t") is not None
    assert backup.daily("t") is None  # nothing changed since


def test_status_and_pruning(fresh):
    populate()
    assert backup.status()["due"] is True
    backup.mark_downloaded()
    assert backup.status()["due"] is False
    for _ in range(3):
        backup.save("manual", "t")
    names = [f["name"] for f in backup.list_files()]
    assert all(backup.FILE_RE.match(n) for n in names)
    assert backup.file_path("../prepare.db") is None


def test_pages(fresh):
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app)
    populate()
    assert "Download a backup" in c.get("/").text
    r = c.get("/backup/download")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "Download a backup" not in c.get("/").text
    assert c.get("/api/summary").json()["backup_due"] is False
    db.execute("DELETE FROM items")
    p = c.post("/backup/check", files={"file": ("b.json", r.content, "application/json")})
    assert "Restore this backup?" in p.text
    assert "<td>Items in stock</td><td>1</td><td>0</td>" in p.text
    done = c.post("/backup/restore", data={"confirm": "yes"})
    assert "Restored." in done.text
    assert db.row("SELECT name FROM items")["name"] == "Heinz Beanz"
    assert any(f["kind"] == "before-restore" for f in backup.list_files())
    assert "can" in c.post("/backup/check", files={"file": ("x.json", b"{", "application/json")}).text
