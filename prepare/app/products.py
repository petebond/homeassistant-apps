"""Barcode lookup, the local product cache, and grouping products into "types".

Lookups go to Open Food Facts' UK site first (English names, UK products), then
its sister databases for things that aren't food: Open Beauty Facts (toiletries,
hand gel, wipes) and Open Pet Food Facts. Whatever is found - or typed in by hand
when nothing is - is kept in the local `products` table, so a second scan of the
same barcode is instant, works offline, and keeps the household's corrections.

Product data from those databases is (c) Open Food Facts contributors, ODbL.
Their API asks for a User-Agent naming the app, and allows about 15 product
reads a minute per address, so the cache matters when unpacking a big shop.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from . import db

log = logging.getLogger("prepare.products")

USER_AGENT = "Prepare/{version} (Home Assistant app; https://github.com/petebond/homeassistant-apps)"
FIELDS = ("code,product_name,product_name_en,generic_name,generic_name_en,brands,quantity,"
          "product_quantity,product_quantity_unit,categories_tags,image_front_small_url")
SOURCES = [
    ("off", "Open Food Facts", "https://uk.openfoodfacts.org/api/v2/product/{code}?fields=" + FIELDS),
    ("obf", "Open Beauty Facts", "https://uk.openbeautyfacts.org/api/v2/product/{code}?fields=" + FIELDS),
    ("opff", "Open Pet Food Facts", "https://uk.openpetfoodfacts.org/api/v2/product/{code}?fields=" + FIELDS),
]
SOURCE_NAMES = {k: n for k, n, _ in SOURCES} | {"manual": "added by hand", "local": "saved on this app"}

# UK supermarket own-label names and their sub-brands. Stripped from product names
# so "Tesco Chopped Tomatoes" and "Napolina Chopped Tomatoes" both come out as
# "Chopped tomatoes". Longest first, so "Tesco Finest" goes before "Tesco".
UK_OWN_LABELS = sorted([
    "tesco finest", "tesco everyday value", "tesco", "stockwell & co", "stockwell and co", "hearty food co",
    "sainsbury's taste the difference", "taste the difference", "sainsbury's", "sainsburys", "by sainsbury's",
    "asda extra special", "asda just essentials", "just essentials", "asda", "extra special",
    "morrisons the best", "morrisons savers", "morrisons", "the best",
    "waitrose essential", "waitrose duchy organic", "waitrose", "essential waitrose", "no.1",
    "m&s", "marks & spencer", "marks and spencer", "co-op irresistible", "co-op", "coop", "co op",
    "aldi", "everyday essentials", "specially selected", "lidl", "deluxe", "iceland", "ocado",
    "cook with m&s", "collection", "finest", "organic", "british",
], key=len, reverse=True)

# Words that describe the same thing differently, and packing liquids that don't change
# what it is for an emergency store: "Chopped Tomatoes in Tomato Juice" is chopped tomatoes.
DESCRIPTORS = re.compile(r"\b(italian|premium|classic|original|traditional|everyday|value|select|quality|plum|whole)\b(?=.*\w)", re.I)
PACKED_IN = re.compile(r"\s+in\s+(?:a\s+|an\s+)?(?:rich\s+|thick\s+|light\s+|natural\s+)?(tomato\s+juice|tomato\s+sauce|juice|natural\s+juice|water|spring\s+water|brine|"
                       r"sunflower\s+oil|olive\s+oil|oil|syrup|light\s+syrup|own\s+juice)\b.*$", re.I)
# Names UK shoppers use that the pack often doesn't: a tin of "Beanz in tomato sauce"
# is baked beans. Checked against the whole product name first.
UK_TYPES = [
    (re.compile(r"\bbean[sz]\b.*\btomato sauce\b|\bbaked bean", re.I), "Baked beans"),
]
# What part a food plays in a meal. Bases (pasta, rice) and toppings (sauces, curries)
# only make meals in pairs: 4 portions of pasta and a jar of sauce for 4 is 4 meals,
# not 8. Extras (biscuits, bars, milk) are worth having but aren't counted as meals.
ROLES = [
    ("meal", "A meal on its own", "soup, stew, beans, porridge, ready meals"),
    ("base", "Needs something with it", "pasta, rice, noodles, couscous"),
    ("topping", "Goes with something", "pasta sauce, curry, chilli, tuna"),
    ("extra", "Snack or extra", "biscuits, bars, fruit, milk - not counted as meals"),
]
ROLE_KEYS = [r[0] for r in ROLES]
ROLE_NAMES = {k: n for k, n, _ in ROLES}
# Checked in order; the first match wins. Prepared foods come first, so "spaghetti
# hoops" and "chicken noodle soup" are meals, not bases.
ROLE_RULES = [
    ("meal", r"\bsoups?\b|\bbroth\b|\bstew\b|casserole|hotpot|\bhoops\b|ravioli|macaroni cheese|mac (?:and|&|n) cheese|"
             r"\bbean[sz]\b|all[- ]day breakfast|ready meal|porridge|\bcereal\b(?! bar)|muesli|\bbreakfast\b|pot noodle|"
             r"\bpie\b|\bhash\b|\bdhal\b|\bdal\b|risotto|paella|savoury rice|rice pot|noodle pot|pasta pot"),
    ("extra", r"biscuit|cookie|cracker|crispbread|rice cake|crisps|chocolate|\bchoc\b|sweets|\bbars?\b|flapjack|granola|"
              r"nature valley|\bnuts?\b|raisins|dried fruit|pineapple|peach|pears?\b|apricot|fruit cocktail|mandarin|\bfruit\b|"
              r"\bmilk\b|almond|\boat drink|\bsoya\b|\bjuice\b|\bdrink\b|squash|cordial|\btea\b|coffee|cocoa|"
              r"pur[eé]e|stock cube|\bstock\b|gravy|\boil\b|vinegar|\bsalt\b|sugar|flour|\bherbs?\b|spice|seasoning|"
              r"\bjam\b|marmalade|honey|syrup|peanut butter|spread|custard|rice pudding|jelly|dessert"),
    ("topping", r"\bsauce\b|pesto|\bragu\b|bolognese|\bcurry\b|tikka|masala|korma|jalfrezi|balti|madras|rogan|"
                r"chilli|\btuna\b|salmon|sardines?|mackerel|pilchards|corned beef|\bspam\b|meatballs|\bchicken\b|"
                r"passata|chopped tomatoes|\btomatoes\b|stir[- ]fry"),
    ("base", r"\bpasta\b|spaghetti|fusilli|penne|macaroni|tagliatelle|linguine|farfalle|rigatoni|conchiglie|lasagne|"
             r"orzo|\bnoodles?\b|\brice\b|couscous|quinoa|bulgur|\bbread\b|tortilla|\bwraps?\b|pitta|naan|"
             r"potato|\bmash\b|polenta"),
]
_ROLE_RE = [(role, re.compile(rx, re.I)) for role, rx in ROLE_RULES]


def guess_role(name: str = "", generic: str = "") -> str:
    """A best guess from the product type and name; the household can always change it."""
    for text in (generic, name):
        for role, rx in _ROLE_RE:
            if text and rx.search(text):
                return role
    return "meal"


# Open Food Facts category words that make a type vaguer, not more specific.
VAGUE_TAG_WORDS = {"canned", "tinned", "common", "prepared", "products", "foods", "food", "based", "plant", "dried", "preserved"}
SPELLINGS = {r"\bbeanz\b": "beans", r"\btomatos\b": "tomatoes"}
SIZE_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:x\s*\d+(?:[.,]\d+)?\s*)?(?:kg|g|gr|grams?|ml|cl|l|ltr|litres?|liters?|oz|pk|pack|cans?|tins?)\b\.?", re.I)
MULTI_RE = re.compile(r"(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l|ltr|litres?|liters?)\b", re.I)
SINGLE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l|ltr|litres?|liters?)\b", re.I)


# ---------------------------------------------------------------- barcodes

def _check_digit_ok(code: str) -> bool:
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalise_barcode(raw: str) -> str | None:
    """Digits only; UPC-A (12) becomes EAN-13 with a leading 0. None if the check digit is wrong."""
    code = re.sub(r"\D", "", raw or "")
    if len(code) == 12:
        code = "0" + code
    if len(code) not in (8, 13, 14):
        return code if 6 <= len(code) <= 14 else None  # odd lengths: allow, but can't verify
    return code if _check_digit_ok(code) else None


# ---------------------------------------------------------------- quantities

def _to_litres(n: float, unit: str) -> float | None:
    unit = unit.lower()
    if unit in ("l", "ltr", "litre", "litres", "liter", "liters"):
        return n
    if unit == "ml":
        return n / 1000
    if unit == "cl":
        return n / 100
    return None


def parse_quantity(text: str) -> dict:
    """'6 x 500ml' -> {'count': 6, 'each': 500, 'unit': 'ml', 'litres': 3.0}."""
    text = (text or "").replace(",", ".")
    m = MULTI_RE.search(text)
    if m:
        count, each, unit = int(m.group(1)), float(m.group(2)), m.group(3)
    else:
        m = SINGLE_RE.search(text)
        if not m:
            return {"count": 1, "each": None, "unit": "", "litres": None}
        count, each, unit = 1, float(m.group(1)), m.group(2)
    litres = _to_litres(each, unit)
    return {"count": count, "each": each, "unit": unit.lower(), "litres": round(litres * count, 3) if litres is not None else None}


# ---------------------------------------------------------------- product types

COMPANY = re.compile(r"\b(ltd|limited|plc|llp|llc|inc|gmbh|s\.?a\.?|uk|foods?|group|company|brands?|international)\b\.?", re.I)


def pick_brand(brands: str, name: str = "") -> str:
    """Open Food Facts 'brands' can list the maker's company first ('H J Heinz Foods UK Ltd, Heinz').
    Prefer a brand that appears in the product name, then one that isn't a company, then tidy one up."""
    cands = [_clean(b) for b in (brands or "").split(",") if _clean(b)]
    if not cands:
        return ""
    for b in cands:
        if b.lower() in (name or "").lower():
            return b
    plain = [b for b in cands if not COMPANY.search(b)]
    if plain:
        return min(plain, key=len)
    tidy = _clean(COMPANY.sub(" ", cands[0]))
    tidy = re.sub(r"^(?:[A-Z]\.?\s+)+", "", tidy)  # leading initials: "H J Heinz" -> "Heinz"
    return tidy or cands[0]


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip(" -,.:;")


def known_generics() -> list[str]:
    """Product types already in use, most used first."""
    rows = db.rows("SELECT generic, COUNT(*) n FROM items WHERE generic IS NOT NULL AND generic != '' GROUP BY lower(generic) ORDER BY n DESC")
    rows += db.rows("SELECT generic, 0 n FROM products WHERE generic IS NOT NULL AND generic != ''")
    seen, out = set(), []
    for r in rows:
        k = r["generic"].lower()
        if k not in seen:
            seen.add(k)
            out.append(r["generic"])
    return out


def match_known(name: str) -> str:
    for g in known_generics():
        if g.lower() == name.lower():
            return g
    return name


def suggest_generic(name: str, brands: str = "", category_tags: list[str] | None = None, generic_name: str = "") -> str:
    """What this product is, without the brand or size: 'Napolina Chopped Tomatoes 400g' -> 'Chopped tomatoes'."""
    for pattern, uk_type in UK_TYPES:
        if pattern.search(name or ""):
            return match_known(uk_type)
    text = " " + (name or "") + " "
    for brand in [b.strip() for b in (brands or "").split(",") if b.strip()] + UK_OWN_LABELS:
        text = re.sub(r"(?i)(?<![\w'])" + re.escape(brand) + r"(?![\w'])", " ", text)
    text = SIZE_RE.sub(" ", text)
    text = re.sub(r"\(.*?\)", " ", text)
    text = PACKED_IN.sub("", _clean(text))
    for pattern, repl in SPELLINGS.items():
        text = re.sub(pattern, repl, text, flags=re.I)
    cleaned = _clean(DESCRIPTORS.sub(" ", text))
    # Reuse a type the household already has if this product is one of them,
    # so every brand of chopped tomatoes lands in the same group.
    lowered = cleaned.lower()
    for g in sorted(known_generics(), key=len, reverse=True):
        gl = g.lower()
        if gl and (gl == lowered or re.search(r"\b" + re.escape(gl) + r"\b", lowered)):
            return g
    if not cleaned and generic_name:
        cleaned = _clean(generic_name)
    # A more specific Open Food Facts category that says the same thing wins:
    # "Beans" with the category "en:baked-beans" becomes "Baked beans".
    words = set(cleaned.lower().split())
    for tag in reversed([t for t in (category_tags or []) if t.startswith("en:")][-4:]):
        human = tag[3:].replace("-", " ")
        if words and words < set(human.split()) and len(human.split()) <= 4 and not (set(human.split()) & VAGUE_TAG_WORDS):
            cleaned = human
            break
    if not cleaned and category_tags:
        tag = category_tags[-1].split(":", 1)[-1].replace("-", " ")
        cleaned = tag
    return cleaned[:1].upper() + cleaned[1:].lower() if cleaned else ""


def guess_category(source: str, tags: list[str], name: str) -> str:
    t = " ".join(tags or []).lower() + " " + (name or "").lower()
    if source == "opff" or "pet-food" in t or "dog food" in t or "cat food" in t:
        return "pet"
    if any(k in t for k in ("baby-food", "infant", "baby-milk", "follow-on", "nappies", "baby wipes")):
        return "baby"
    if any(k in t for k in ("en:waters", "spring-water", "mineral-water", "bottled water", "still water", "spring water")):
        return "water"
    if source == "obf" or any(k in t for k in ("soap", "sanitiser", "sanitizer", "toilet", "toothpaste", "shampoo")):
        if "sanitis" in t or "sanitiz" in t or "hand gel" in t:
            return "sanitiser"
        if "wipe" in t:
            return "wipes"
        return "bathroom"
    if any(k in t for k in ("battery", "batteries")):
        return "batteries"
    return "food"


def pack_amount(category: str, q: dict) -> float:
    """How much one scanned pack counts for, in the category's unit."""
    if category == "water" and q.get("litres"):
        return q["litres"]
    if category == "food":
        return float(q.get("count") or 1)  # a 4-pack of tins = 4 meals until the household says otherwise
    return 1.0


# ---------------------------------------------------------------- lookup

def _fetch(url: str, version: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT.format(version=version), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fake_fetch(url: str, version: str) -> dict | None:
    """Development only: PREPARE_FAKE_LOOKUPS=path/to/fixtures.json answers lookups offline."""
    import os
    fixtures = json.loads(open(os.environ["PREPARE_FAKE_LOOKUPS"]).read())
    for key, data in fixtures.items():
        if key in url:
            return data
    raise urllib.error.HTTPError(url, 404, "not found", {}, None)


import os as _os  # noqa: E402
fetch = _fake_fetch if _os.environ.get("PREPARE_FAKE_LOOKUPS") else _fetch  # tests replace this too


def lookup(raw: str, version: str = "0") -> dict:
    """Everything the scan form needs for one barcode."""
    code = normalise_barcode(raw)
    if not code:
        return {"ok": False, "error": "That doesn't look like a valid barcode. Try again or type it in."}
    saved = db.row("SELECT * FROM products WHERE barcode=?", (code,))
    if saved:
        return {"ok": True, "found": True, "barcode": code, "source": saved["source"], "source_name": SOURCE_NAMES.get(saved["source"], saved["source"]),
                "saved": True, "role": saved.get("role") or guess_role(saved["name"] or "", saved["generic"] or ""),
                **{k: saved[k] for k in ("name", "brand", "generic", "category", "pack_amount", "quantity_text", "image_url")}}
    errors = []
    for key, label, url in SOURCES:
        try:
            data = fetch(url.format(code=code), version)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            errors.append(f"{label}: busy ({exc.code})" if exc.code in (429, 503) else f"{label}: error {exc.code}")
            continue
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"{label}: unreachable")
            log.info("Lookup %s at %s failed: %s", code, label, exc)
            continue
        if not data or data.get("status") != 1 or not data.get("product"):
            continue
        p = data["product"]
        name = _clean(p.get("product_name_en") or p.get("product_name") or p.get("generic_name_en") or p.get("generic_name") or "")
        brand = pick_brand(p.get("brands") or "", name)
        tags = p.get("categories_tags") or []
        qtext = _clean(p.get("quantity") or (f"{p.get('product_quantity')} {p.get('product_quantity_unit') or ''}" if p.get("product_quantity") else ""))
        category = guess_category(key, tags, name)
        q = parse_quantity(qtext)
        display = name if not brand or brand.lower() in name.lower() else f"{brand} {name}"
        generic = suggest_generic(name, (p.get("brands") or "") + "," + brand, tags, p.get("generic_name_en") or p.get("generic_name") or "")
        return {"ok": True, "found": True, "barcode": code, "source": key, "source_name": label, "saved": False,
                "name": _clean(f"{display} {qtext}" if qtext and qtext.lower() not in display.lower() else display),
                "brand": brand, "generic": generic, "role": guess_role(name, generic),
                "category": category, "pack_amount": pack_amount(category, q), "quantity_text": qtext,
                "image_url": p.get("image_front_small_url") or ""}
    return {"ok": True, "found": False, "barcode": code, "errors": errors,
            "message": ("Couldn't reach the product databases (" + "; ".join(errors) + "). Fill it in; it'll be remembered.")
                       if errors else "Not in Open Food Facts yet. Fill it in once and this app will remember it."}


def remember(code: str, name: str, brand: str, generic: str, category: str, amount: float, quantity_text: str, source: str,
             image_url: str = "", role: str | None = None) -> None:
    """Save (or correct) what this barcode is, so the next scan needs no typing."""
    if not code:
        return
    db.execute(
        "INSERT INTO products(barcode, name, brand, generic, category, pack_amount, quantity_text, source, image_url, updated, role) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(barcode) DO UPDATE SET name=excluded.name, brand=excluded.brand, "
        "generic=excluded.generic, category=excluded.category, pack_amount=excluded.pack_amount, "
        "quantity_text=excluded.quantity_text, updated=excluded.updated, role=COALESCE(excluded.role, products.role)",
        (code, name, brand, generic, category, amount, quantity_text, source or "manual", image_url, db.now_iso(), role),
    )


def food_unit(role: str | None, unit: str) -> str:
    """Meals for whole meals; portions for halves of a meal and extras."""
    if role in ("base", "topping", "extra") and unit in ("", "meals", "meal"):
        return "portions"
    if role == "meal" and unit in ("", "portions", "portion"):
        return "meals"
    return unit


def assign_roles() -> int:
    """Give every food item and remembered food barcode without a role a sensible one.

    Runs on every start (and after a restore), so items from before 0.5 and from older
    backups get a role; anything the household has set is never touched."""
    n = 0
    for i in db.rows("SELECT id, name, generic, unit, barcode FROM items WHERE category='food' AND (role IS NULL OR role='')"):
        saved = db.row("SELECT role FROM products WHERE barcode=? AND role IS NOT NULL AND role != ''", (i["barcode"],)) if i["barcode"] else None
        role = saved["role"] if saved else guess_role(i["name"] or "", i["generic"] or "")
        db.execute("UPDATE items SET role=?, unit=? WHERE id=?", (role, food_unit(role, i["unit"] or ""), i["id"]))
        n += 1
    for p in db.rows("SELECT barcode, name, generic FROM products WHERE category='food' AND (role IS NULL OR role='')"):
        item = db.row("SELECT role FROM items WHERE barcode=? AND role IS NOT NULL ORDER BY id DESC", (p["barcode"],))
        db.execute("UPDATE products SET role=? WHERE barcode=?",
                   (item["role"] if item else guess_role(p["name"] or "", p["generic"] or ""), p["barcode"]))
    return n
