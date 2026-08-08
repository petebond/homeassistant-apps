"""How a typed name becomes the name that gets shown.

One function, `title_case`, decides the spelling of every ingredient and every
line of the standing "Also needed" list. It runs on the way out of the file
rather than only when something is saved, which is what lets a name stored under
an older rule tidy itself up without anyone re-typing it - and is also why it
has to be conservative. Anything it gets wrong, it gets wrong on data that is
already there.

Three rules pull against each other, and the order they are applied in is the
whole design:

  1. A known initialism wins outright. "bbq sauce" is BBQ sauce however it was
     typed, because nobody holds shift while writing a shopping list.
  2. A short all-caps run is left alone. That is what keeps an acronym nobody
     thought to add to the list from being flattened into Title Case.
  3. A joining word stays small - unless it opens the name, where a lower case
     first letter just looks like a mistake.

Run: python3 tests/test_naming.py  (kept out of the image: Dockerfile copies *.py)
"""

import os
import sys
import tempfile

os.environ["SUPERVISOR_TOKEN"] = "test-token"
os.environ["MEAL_PLANNER_DATA_DIR"] = tempfile.mkdtemp(prefix="naming-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


def test_title_case():
    cases = [
        # The plain job.
        ("chopped TOMATOES", "Chopped Tomatoes"),
        ("cheddar", "Cheddar"),
        # Initialisms, however they were typed, and whatever they are carrying.
        ("bbq sauce", "BBQ Sauce"),
        ("BBQ sauce", "BBQ Sauce"),
        ("Bbq Sauce", "BBQ Sauce"),
        ("(bbq) sauce", "(BBQ) Sauce"),
        ("smoky bbq-glazed ribs", "Smoky BBQ-Glazed Ribs"),
        ("uht milk", "UHT Milk"),
        ("xl eggs", "XL Eggs"),
        # Joining words stay small, but never the first word.
        ("a bunch of coriander", "A Bunch of Coriander"),
        ("tin of chopped tomatoes", "Tin of Chopped Tomatoes"),
        ("salt and pepper", "Salt and Pepper"),
        ("chicken in black bean sauce", "Chicken in Black Bean Sauce"),
        ("the works", "The Works"),
        ("of", "Of"),
        # Both rules at once.
        ("a bottle of bbq sauce", "A Bottle of BBQ Sauce"),
        # Hyphens and slashes split words, so both halves get capitalised - but
        # a joining word inside a compound still goes small.
        ("semi-skimmed milk", "Semi-Skimmed Milk"),
        ("washing-up liquid", "Washing-Up Liquid"),
        ("salt/pepper", "Salt/Pepper"),
        ("out-of-date stock", "Out-of-Date Stock"),
        # Things that must survive untouched.
        ("2% milk", "2% Milk"),
        ("hershey's", "Hershey's"),
        ("", ""),
    ]
    for typed, want in cases:
        check("%r" % (typed,), server.title_case(typed), want)


def test_idempotent():
    """Run on the way out of the file, so it runs on its own output constantly.
    A rule that changed its mind on the second pass would rewrite the shopping
    list every time anyone opened it."""
    for typed in ["bbq sauce", "a bunch of coriander", "washing-up liquid",
                  "2% milk", "hershey's", "out-of-date stock", "xl eggs"]:
        once = server.title_case(typed)
        check("%r settles" % (typed,), server.title_case(once), once)


def test_ingredients_and_extras_agree():
    """The two lists sit one above the other on the Shopping tab. They went
    through different code paths for a long time, and the mismatch was the thing
    you actually noticed."""
    for typed in ["bbq sauce", "a bunch of coriander", "chopped tomatoes"]:
        ingredient = server.clean_ingredients(
            [{"item": typed, "qty": 1, "unit": "each"}])[0]["item"]
        extra = server.clean_extra({"item": typed})["item"]
        check("%r matches across both lists" % (typed,), extra, ingredient)


for test in [test_title_case, test_idempotent, test_ingredients_and_extras_agree]:
    test()

if FAILURES:
    print("FAILED (%d)\n" % len(FAILURES))
    for failure in FAILURES:
        print("  - " + failure)
    sys.exit(1)
print("naming: all good")
