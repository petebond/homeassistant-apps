"""Food roles: pasta and sauce make meals together, and the spreadsheet view."""
import os
import tempfile

import pytest

os.environ.setdefault("PREPARE_DATA", tempfile.mkdtemp())  # never the real /data, even at import
from app import backup, db, logic, products  # noqa: E402


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "prepare.db")
    db.init()
    return tmp_path


def add(name, qty, role=None, category="food", generic="", unit="meals", best_before=None):
    return db.execute("INSERT INTO items(name, category, quantity, unit, role, generic, best_before) VALUES (?,?,?,?,?,?,?)",
                      (name, category, qty, unit, role, generic, best_before))


@pytest.mark.parametrize("generic, role", [
    ("Basmati white rice", "base"), ("Fusilli 100% durum wheat", "base"), ("Egg noodles", "base"),
    ("Tomato and garlic pasta sauce", "topping"), ("Chicken tikka masala", "topping"), ("Skip jack tuna steaks", "topping"),
    ("Passata", "topping"), ("Chicken in white sauce", "topping"),
    ("Tomato soup", "meal"), ("Aromatic chicken noodle soup", "meal"), ("Spaghetti hoops", "meal"), ("Baked beans", "meal"),
    ("Scottish porridge oats", "meal"), ("Breakfast honey & nut with choc chips", "meal"), ("Corned beef hash", "meal"),
    ("Bourbon biscuits", "extra"), ("Strawberry fruit & grain bars", "extra"), ("Long life almond unsweetened", "extra"),
    ("Tomato purée double concentrate", "extra"), ("Tropical gold pineapple", "extra"), ("Rice pudding", "extra"),
])
def test_guess_role(generic, role):
    assert products.guess_role("", generic) == role


def test_pasta_and_sauce_make_meals_together(fresh):
    add("Pasta sauce for 4", 4, "topping")
    add("Pasta, 10 portions", 10, "base")
    f = logic.food_meals(db.rows("SELECT * FROM items"))
    assert f["meals"] == 4 and f["spare_base"] == 6 and f["spare_topping"] == 0
    add("Tomato soup", 2, "meal")
    add("Biscuits", 5, "extra")
    food = next(c for c in logic.readiness()["categories"] if c["key"] == "food")
    assert food["held"] == 6 and food["food"]["extra"] == 5


def test_expired_halves_dont_pair(fresh):
    add("Old sauce", 4, "topping", best_before="2000-01-01")
    add("Pasta", 10, "base")
    food = next(c for c in logic.readiness()["categories"] if c["key"] == "food")
    assert food["held"] == 0 and food["food"]["spare_base"] == 10


def test_existing_food_gets_sensible_roles(fresh):
    """Items from before 0.5 (no role) are sorted on start; meals become portions for halves."""
    rice = add("Asda Basmati white rice", 28, generic="Basmati white rice")
    soup = add("Asda Tomato soup", 4, generic="Tomato soup")
    torch = add("Torch", 1, category="torch", unit="torches")
    db.init()
    r = {i["id"]: i for i in db.rows("SELECT * FROM items")}
    assert (r[rice]["role"], r[rice]["unit"]) == ("base", "portions")
    assert (r[soup]["role"], r[soup]["unit"]) == ("meal", "meals")
    assert r[torch]["role"] is None and r[torch]["unit"] == "torches"
    # the household's own choice is never overwritten
    db.execute("UPDATE items SET role='meal', unit='meals' WHERE id=?", (rice,))
    db.init()
    assert db.row("SELECT role FROM items WHERE id=?", (rice,))["role"] == "meal"


def test_old_backups_get_roles(fresh):
    """A 0.4 backup has no roles; after restoring, food has them."""
    data = backup.parse((__import__("pathlib").Path(__file__).parent / "backups" / "format-1.json").read_bytes())
    backup.restore(data)
    food = db.rows("SELECT role FROM items WHERE category='food'")
    assert food and all(i["role"] in products.ROLE_KEYS for i in food)


def test_round_trip_keeps_roles(fresh):
    add("Pasta", 10, "base", unit="portions")
    raw = backup.dumps(backup.export("t"))
    db.execute("DELETE FROM items")
    backup.restore(backup.parse(raw))
    assert db.row("SELECT role FROM items")["role"] == "base"


@pytest.fixture
def client(fresh):
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


def test_forms_save_role(client):
    client.post("/items", data={"name": "Fusilli", "category": "food", "quantity": "18"})  # guessed
    client.post("/items", data={"name": "Tuna", "category": "food", "quantity": "6", "role": "meal"})  # chosen
    client.post("/items", data={"name": "Torch", "category": "torch", "quantity": "1", "role": "base"})  # ignored
    r = {i["name"]: i for i in db.rows("SELECT * FROM items")}
    assert (r["Fusilli"]["role"], r["Fusilli"]["unit"]) == ("base", "portions")
    assert (r["Tuna"]["role"], r["Tuna"]["unit"]) == ("meal", "meals")
    assert r["Torch"]["role"] is None
    assert 'value="base" checked' in client.get(f"/items/{r['Fusilli']['id']}").text


def test_scan_remembers_role(client):
    client.post("/scan/add", data={"barcode": "8005121000108", "name": "Napolina Fusilli", "generic": "Fusilli",
                                   "category": "food", "packs": "1", "pack_amount": "5", "role": "base"})
    assert client.get("/api/lookup/8005121000108").json()["role"] == "base"
    item = db.row("SELECT * FROM items")
    assert item["role"] == "base" and item["unit"] == "portions"


def test_sheet_edits_only_what_changed(client):
    a = add("Rice", 28, "base", unit="portions")
    b = add("Soup", 4, "meal")
    r = client.post("/items/sheet", data={f"c-{a}-quantity": "20", f"c-{a}-location": "Cupboard",
                                          f"c-{b}-name": "Soup", f"c-{b}-quantity": "4"})
    assert "1 item updated" in r.text
    rice = db.row("SELECT * FROM items WHERE id=?", (a,))
    assert rice["quantity"] == 20 and rice["location"] == "Cupboard" and rice["role"] == "base"


def test_sheet_role_and_category_keep_units_consistent(client):
    a = add("Tuna", 6, "topping", unit="portions")
    client.post("/items/sheet", data={f"c-{a}-role": "meal"})
    assert db.row("SELECT role, unit FROM items WHERE id=?", (a,)) == {"role": "meal", "unit": "meals"}
    client.post("/items/sheet", data={f"c-{a}-category": "pet"})
    row = db.row("SELECT category, role, unit FROM items WHERE id=?", (a,))
    assert row["category"] == "pet" and row["role"] is None and row["unit"] == "days"


def test_sheet_ignores_bad_input(client):
    a = add("Rice", 28, "base", unit="portions")
    client.post("/items/sheet", data={f"c-{a}-category": "nonsense", f"c-{a}-role": "nonsense", f"c-{a}-quantity": "-3",
                                      f"c-{a}-best_before": "not a date", "c-99999-name": "ghost", f"c-{a}-evil": "x"})
    row = db.row("SELECT * FROM items WHERE id=?", (a,))
    assert row["category"] == "food" and row["role"] == "base" and row["quantity"] == 0 and row["best_before"] is None


def test_bulk_actions(client):
    ids = [add(f"Thing {n}", 2, "meal") for n in range(3)]
    r = client.post("/items/bulk", data={"sel": [str(i) for i in ids[:2]], "action": "role", "value": "extra"})
    assert "2 items updated" in r.text
    assert [x["role"] for x in db.rows("SELECT role FROM items ORDER BY id")] == ["extra", "extra", "meal"]
    client.post("/items/bulk", data={"sel": [str(ids[0])], "action": "location", "value": "Loft"})
    assert db.row("SELECT location FROM items WHERE id=?", (ids[0],))["location"] == "Loft"
    client.post("/items/bulk", data={"sel": [str(ids[1])], "action": "used"})
    assert db.row("SELECT status FROM items WHERE id=?", (ids[1],))["status"] == "used"
    r = client.post("/items/bulk", data={"sel": [str(ids[2])], "action": "delete"})
    assert "1 item deleted" in r.text and not db.row("SELECT id FROM items WHERE id=?", (ids[2],))
    page = client.get("/items/sheet?show=all").text
    assert "Thing 1" in page and "Thing 2" not in page


def test_pages_explain_pairing(client):
    add("Pasta", 10, "base", unit="portions")
    add("Sauce", 4, "topping", unit="portions")
    assert "6 portions of pasta, rice etc." in client.get("/").text
    page = client.get("/items?group=food").text
    assert "<b>4 meals</b>" in page and "6 portions" in page
