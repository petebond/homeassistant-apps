"""The standing "Also needed" list: what it stores, and what it does with what
you type into it.

Three things here are easy to get wrong and expensive to notice late.

Quantity has to come off the front of the text, because the suggestions are
trained on what has been typed before: if "3 cucumbers" went into the history
whole then "cucumber", "2 cucumbers" and "3 cucumbers" would be three competing
entries and none of them right the week you want four. But it must only come
off when it really is a quantity - "2 chicken breasts" is not two chickens.

Plural collapsing has to agree in both directions, or the very thing it exists
to prevent happens anyway.

And the migration runs once, on a real file, against data that has been
accumulating per week for months. It gets one go.

Run: python3 tests/test_extras.py  (kept out of the image: Dockerfile copies *.py)
"""

import os
import sys
import tempfile

os.environ["SUPERVISOR_TOKEN"] = "test-token"
os.environ["MEAL_PLANNER_DATA_DIR"] = tempfile.mkdtemp(prefix="extras-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


# ---------------------------------------------------------------- parsing

def test_parsing():
    cases = [
        # Plain counts.
        ("3 cucumbers", (3.0, "each", "cucumbers")),
        ("12 eggs", (12.0, "each", "eggs")),
        # Weights and volumes, with and without the space.
        ("500g mince", (500.0, "g", "mince")),
        ("2 kg potatoes", (2.0, "kg", "potatoes")),
        ("1l milk", (1.0, "l", "milk")),
        # Units the shopping list already knows, plural, and with an "of".
        ("2 tins chopped tomatoes", (2.0, "tin", "chopped tomatoes")),
        ("3 x tins chopped tomatoes", (3.0, "tin", "chopped tomatoes")),
        ("3 packs of nappies", (3.0, "pack", "nappies")),
        # A word that isn't a unit stays part of the name. This is the one
        # that matters: guessing wrong turns a readable line into a puzzle.
        ("2 chicken breasts", (2.0, "each", "chicken breasts")),
        # No leading number at all - left exactly as typed.
        ("baking paper", (1.0, "each", "baking paper")),
        ("a bunch of coriander", (1.0, "each", "a bunch of coriander")),
        # A quantity of nothing is not a quantity.
        ("500g", (1.0, "each", "500g")),
        ("2 kg", (1.0, "each", "2 kg")),
        # Zero of something is a typo, not an instruction.
        ("0 cucumbers", (1.0, "each", "cucumbers")),
        # Decimals, however they were typed.
        ("2.5 kg spuds", (2.5, "kg", "spuds")),
    ]
    for text, want in cases:
        check("parse_extra(%r)" % text, server.parse_extra(text), want)


def test_plurals():
    # Both spellings have to land on the same key, whichever was typed first.
    pairs = [("cucumbers", "cucumber"), ("tomatoes", "tomato"),
             ("nappies", "nappy"), ("bin bags", "bin bag"),
             ("peaches", "peach"), ("dishes", "dish"),
             ("glasses", "glass")]
    for plural, singular in pairs:
        check("%r and %r agree" % (plural, singular),
              server.extra_key(plural), server.extra_key(singular))

    # "glass" is not the plural of "glas". A word ending in a doubled s is
    # left alone, or the two spellings above stop agreeing.
    check("glass stays whole", server.extra_key("glass"), "glass")
    # Case and stray punctuation are not a second entry.
    check("case and padding", server.extra_key("  Baking Paper. "),
          server.extra_key("baking paper"))
    # Too short to have a plural stripped off it.
    check("short words survive", server.extra_key("gas"), "gas")


# ---------------------------------------------------------------- migration

def test_migration():
    """The old shape: a separate little list per week, thrown away when the
    week rolled over."""
    data = {
        "extras": {
            "2026-07-27": [{"id": "x1", "item": "baking paper"},
                           {"id": "x2", "item": "3 cucumbers"}],
            "2026-08-03": [{"id": "x3", "item": "Cucumbers"},
                           {"id": "x4", "item": "500g mince"}],
        },
        "extraNames": {
            "3 cucumbers": {"item": "3 cucumbers", "used": 2, "at": "2026-07-27"},
            "cucumbers": {"item": "Cucumbers", "used": 1, "at": "2026-08-03"},
            "baking paper": {"item": "baking paper", "used": 5, "at": "2026-07-27"},
        },
    }
    server.migrate_extras(data)

    items = [(e["item"], e["qty"], e["unit"], e["state"]) for e in data["extras"]]
    # Newest week first, and the cucumbers written down two weeks running are
    # one line, not two: two weeks apart they were two separate askings.
    check("migrated list", items, [
        ("Cucumbers", 1.0, "each", "need"),
        ("mince", 500.0, "g", "need"),
        ("baking paper", 1.0, "each", "need"),
    ])

    # The history was keyed on raw text, so everything typed with a number in
    # front was under the wrong key. Rebuilt and merged, counts added up.
    names = data["extraNames"]
    check("history keys", sorted(names), ["baking paper", "cucumber"])
    check("counts merged", names["cucumber"]["used"], 3)
    check("name has no quantity in it", names["cucumber"]["item"], "cucumbers")

    # Idempotent: a list is already the new shape and must survive untouched.
    before = [dict(e) for e in data["extras"]]
    server.migrate_extras(data)
    check("second run changes nothing", data["extras"], before)


def test_migration_survives_rubbish():
    """The file can be edited by hand, and has been."""
    for junk in [None, [], "nonsense", {"2026-08-03": "not a list"},
                 {"2026-08-03": [None, {}, {"item": ""}]}]:
        data = {"extras": junk, "extraNames": {}}
        server.migrate_extras(data)
        check("junk %r reads as a list" % (junk,),
              isinstance(data["extras"], list), True)


# ---------------------------------------------------------------- records

def test_clean_extra():
    # Missing everything except a name. The name comes back Title Cased: this
    # list sits directly above the shopping list, where every line is, and it is
    # done on the read so a line stored before that was true tidies itself up.
    got = server.clean_extra({"item": "foil"})
    check("defaults", (got["item"], got["qty"], got["unit"], got["state"]),
          ("Foil", 1.0, "each", "need"))
    # However it was typed, and whatever punctuation it was carrying.
    check("initialism", server.clean_extra({"item": "bbq sauce"})["item"],
          "BBQ Sauce")
    check("joining word stays small",
          server.clean_extra({"item": "a bunch of coriander"})["item"],
          "A Bunch of Coriander")
    # A unit the shopping list doesn't know falls back rather than propagating.
    check("unknown unit", server.clean_extra(
        {"item": "foil", "unit": "furlong"})["unit"], "each")
    # A quantity that isn't a number, and one that is nonsense.
    check("qty not a number", server.clean_extra(
        {"item": "foil", "qty": "lots"})["qty"], 1.0)
    check("negative qty", server.clean_extra(
        {"item": "foil", "qty": -3})["qty"], 1.0)
    # Nameless records are dropped entirely.
    check("no name", server.clean_extra({"qty": 3}), None)
    check("not a record", server.clean_extra("foil"), None)


def test_ordering():
    """Still needed first, in the order they were added. Ordered ones after,
    newest order at the top of that group - that is the group you have just
    put something into, and the one you are looking for."""
    data = {"extras": [
        {"id": "a", "item": "foil", "state": "ordered", "orderedAt": "2026-08-01"},
        {"id": "b", "item": "bin bags", "state": "need"},
        {"id": "c", "item": "candles", "state": "ordered", "orderedAt": "2026-08-05"},
        {"id": "d", "item": "cling film", "state": "need"},
    ]}
    check("order", [e["id"] for e in server.extras_list(data)],
          ["b", "d", "c", "a"])


for test in [test_parsing, test_plurals, test_migration,
             test_migration_survives_rubbish, test_clean_extra, test_ordering]:
    test()

if FAILURES:
    print("FAILED (%d)\n" % len(FAILURES))
    for failure in FAILURES:
        print("  - " + failure)
    sys.exit(1)
print("extras: all good")
