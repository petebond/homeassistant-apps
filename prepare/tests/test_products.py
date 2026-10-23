"""Unit tests for barcode, quantity and product-type handling (no network)."""
import os
import tempfile
import urllib.error

import pytest

os.environ.setdefault("PREPARE_DATA", tempfile.mkdtemp())
from app import db, products  # noqa: E402

db.init()


def test_barcodes():
    assert products.normalise_barcode("5000157024671") == "5000157024671"     # Heinz beans, EAN-13
    assert products.normalise_barcode("5000157024672") is None                # bad check digit
    assert products.normalise_barcode("036000291452") == "0036000291452"      # UPC-A -> EAN-13
    assert products.normalise_barcode("96385074") == "96385074"               # EAN-8
    assert products.normalise_barcode(" 5000157-024671 ") == "5000157024671"
    assert products.normalise_barcode("12") is None


@pytest.mark.parametrize("text,count,litres", [
    ("400g", 1, None), ("2L", 1, 2.0), ("6 x 500ml", 6, 3.0), ("4 x 400 g", 4, None),
    ("1.5 litre", 1, 1.5), ("12 × 330 ml", 12, 3.96), ("75cl", 1, 0.75), ("", 1, None),
])
def test_quantities(text, count, litres):
    q = products.parse_quantity(text)
    assert q["count"] == count and q["litres"] == litres


@pytest.mark.parametrize("name,brands,expected", [
    ("Napolina Chopped Tomatoes", "Napolina", "Chopped tomatoes"),
    ("Tesco Chopped Tomatoes 400G", "Tesco", "Chopped tomatoes"),
    ("Sainsbury's Chopped Tomatoes in Tomato Juice", "Sainsbury's", "Chopped tomatoes"),
    ("Princes Tuna Chunks in Spring Water", "Princes", "Tuna chunks"),
    ("Napolina Italian Chopped Tomatoes with Garlic", "Napolina", "Chopped tomatoes with garlic"),
    ("Heinz Baked Beanz In Tomato Sauce 415g", "Heinz", "Baked beans"),
    ("Tesco Finest Basmati Rice 1Kg", "Tesco", "Basmati rice"),
])
def test_generic_fresh(name, brands, expected):
    assert products.suggest_generic(name, brands) == expected


def test_generic_reuses_existing_type():
    db.execute("INSERT INTO items(name, category, quantity, generic, status) VALUES ('x','food',1,'Chopped tomatoes','active')")
    assert products.suggest_generic("Sainsbury's Chopped Tomatoes in Tomato Juice", "Sainsbury's") == "Chopped tomatoes"
    assert products.suggest_generic("Asda Italian Chopped Tomatoes With Garlic", "Asda") == "Chopped tomatoes"


def test_categories():
    assert products.guess_category("off", ["en:beverages", "en:waters", "en:spring-waters"], "Highland Spring") == "water"
    assert products.guess_category("off", ["en:canned-foods"], "Beans") == "food"
    assert products.guess_category("obf", [], "Carex hand sanitiser gel") == "sanitiser"
    assert products.guess_category("opff", [], "Pedigree") == "pet"


def test_lookup_found_then_cached(monkeypatch):
    calls = []

    def fake(url, version):
        calls.append(url)
        assert url.startswith("https://uk.openfoodfacts.org/api/v2/product/5000157024671")
        return {"status": 1, "product": {"product_name": "Baked Beanz", "brands": "Heinz", "quantity": "4 x 415 g",
                                         "categories_tags": ["en:canned-foods", "en:baked-beans"]}}
    monkeypatch.setattr(products, "fetch", fake)
    r = products.lookup("5000157024671")
    assert r["found"] and r["name"] == "Heinz Baked Beanz 4 x 415 g" and r["category"] == "food" and r["pack_amount"] == 4
    products.remember(r["barcode"], r["name"], r["brand"], "Baked beans", "food", 4, r["quantity_text"], r["source"])
    again = products.lookup("5000157024671")
    assert again["saved"] and again["generic"] == "Baked beans" and len(calls) == 1


def test_lookup_falls_through_and_reports_busy(monkeypatch):
    def fake(url, version):
        if "openfoodfacts" in url:
            raise urllib.error.HTTPError(url, 429, "slow down", {}, None)
        raise urllib.error.HTTPError(url, 404, "nope", {}, None)
    monkeypatch.setattr(products, "fetch", fake)
    r = products.lookup("96385074")
    assert not r["found"] and "busy" in r["message"]


def test_lookup_beauty_database(monkeypatch):
    def fake(url, version):
        if "openbeautyfacts" in url:
            return {"status": 1, "product": {"product_name": "Original Hand Sanitiser", "brands": "Carex", "quantity": "50ml"}}
        raise urllib.error.HTTPError(url, 404, "nope", {}, None)
    monkeypatch.setattr(products, "fetch", fake)
    r = products.lookup("0036000291452")
    assert r["source"] == "obf" and r["category"] == "sanitiser" and r["generic"] == "Hand sanitiser"


@pytest.mark.parametrize("brands,name,expected", [
    ("H J Heinz Foods UK Ltd", "Beanz in a rich tomato sauce", "Heinz"),
    ("H J Heinz Foods UK Ltd, Heinz", "Beanz", "Heinz"),
    ("Tesco", "Tesco Chopped Tomatoes", "Tesco"),
    ("Princes Ltd, Princes", "Tuna Chunks", "Princes"),
])
def test_pick_brand(brands, name, expected):
    assert products.pick_brand(brands, name) == expected


def test_real_heinz_record(monkeypatch):
    """Name, brand and size as Open Food Facts returned them for 5000157024671 (23 Oct 2026); categories illustrative."""
    monkeypatch.setattr(products, "fetch", lambda url, v: {"status": 1, "product": {
        "product_name": "Beanz in a rich tomato sauce", "brands": "H J Heinz Foods UK Ltd", "quantity": "415g",
        "categories_tags": ["en:plant-based-foods", "en:legumes", "en:canned-foods", "en:baked-beans"]}})
    db.execute("DELETE FROM products WHERE barcode='5000157024671'")
    r = products.lookup("5000157024671")
    assert r["brand"] == "Heinz" and r["name"] == "Heinz Beanz in a rich tomato sauce 415g", r
    assert r["generic"] == "Baked beans", r
