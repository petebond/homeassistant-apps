"""How many people a meal, and a day, are cooking for.

Two numbers that must agree with each other and with a third one on a phone:

  - head_count() scales every ingredient quantity in the app. It is what the
    shopping list was built from.
  - day_head_count() is the figure beside the cook, on the week cards and on
    the kitchen display's info panel.
  - dayHeadCount() in static/app.js is the same sum done in the browser,
    because the week view has the sittings already and shouldn't ask.

The rule that ties them together is the one worth testing: on a day with one
meal, which is nearly every day, the day's count and the meal's count are the
same number. A screen that says "Cooking: Han, for 5 people" above a card whose
ingredients were scaled for four is worse than a screen that says neither.

The rest is the guest slot, which is why none of this is just len(eaters): it
is one entry in the list standing for up to thirty mouths, it is counted once
across a whole day however many meals it appears at, and a slot that is on but
says nothing is one guest rather than none.

Run: python3 tests/test_head_count.py  (kept out of the image: Dockerfile
copies *.py)
"""

import os
import sys
import tempfile

os.environ["SUPERVISOR_TOKEN"] = "test-token"
os.environ["MEAL_PLANNER_DATA_DIR"] = tempfile.mkdtemp(prefix="heads-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

FAILURES = []

GUEST = "p_guest"
PEOPLE = {"p_a", "p_b", "p_c", GUEST}


def check(label, got, want):
    if got != want:
        FAILURES.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


def sitting(eaters, guests=0):
    return {"id": "s_x", "mealId": "m_1", "eaters": list(eaters),
            "guests": guests, "note": "", "ratings": {}}


def day(*sittings):
    return server.day_head_count(list(sittings), GUEST, PEOPLE)


def test_one_meal_agrees_with_head_count():
    """The equality the whole feature rests on."""
    for eaters, guests in ((["p_a"], 0),
                           (["p_a", "p_b"], 0),
                           (["p_a", GUEST], 3),
                           (["p_a", "p_b", "p_c", GUEST], 1),
                           ([GUEST], 6),
                           ([], 0)):
        one = sitting(eaters, guests)
        check("a day of one meal counts the same as the meal (%r, %d guests)"
              % (eaters, guests),
              day(one), server.head_count(one, GUEST, PEOPLE))


def test_the_empty_cases():
    check("nothing planned feeds nobody", day(), 0)
    check("a meal nobody is marked for feeds nobody", day(sitting([])), 0)
    check("a day of blank sittings feeds nobody",
          day(sitting([]), sitting([])), 0)


def test_two_meals_do_not_double_count():
    """A cook feeding the same household twice is not feeding it twice over."""
    check("somebody at both meals is still one person",
          day(sitting(["p_a", "p_b"]), sitting(["p_a", "p_b"])), 2)
    check("different people at each meal add up",
          day(sitting(["p_a"]), sitting(["p_b", "p_c"])), 3)
    check("overlapping meals count the union",
          day(sitting(["p_a", "p_b"]), sitting(["p_b", "p_c"])), 3)


def test_the_guest_slot():
    check("a guest slot that is on but says nothing is one guest",
          day(sitting(["p_a", GUEST], 0)), 2)
    check("a guest count with nobody on the slot doesn't feed anyone",
          day(sitting(["p_a"], 4)), 1)
    check("guests are counted once across the day, at the largest number",
          day(sitting(["p_a", GUEST], 2), sitting(["p_a", GUEST], 5)), 6)
    check("guests at only one of the day's meals still count",
          day(sitting(["p_a"]), sitting(["p_a", GUEST], 3)), 4)


def test_people_who_have_left():
    """A week planned before somebody moved out shouldn't go on feeding them -
    the same rule head_count() follows, and for the same reason: the number is
    read months after the plan was made."""
    check("an unknown eater is not fed",
          server.day_head_count([sitting(["p_a", "p_gone"])], GUEST, PEOPLE), 1)
    check("with no roll call, everybody named counts",
          server.day_head_count([sitting(["p_a", "p_gone"])], GUEST, None), 2)


def test_survives_rubbish():
    """It is handed whatever is in data.json, including shapes written by
    versions that predate all of this."""
    for junk in (None, [], [None], [{}], [{"eaters": None}], [{"eaters": "p_a"}]):
        got = server.day_head_count(junk, GUEST, PEOPLE)
        check("nothing counted from %r" % (junk,), got, 0)


for test in [test_one_meal_agrees_with_head_count, test_the_empty_cases,
             test_two_meals_do_not_double_count, test_the_guest_slot,
             test_people_who_have_left, test_survives_rubbish]:
    test()

if FAILURES:
    print("FAILED (%d)\n" % len(FAILURES))
    for failure in FAILURES:
        print("  - " + failure)
    sys.exit(1)
print("head count: all good")
