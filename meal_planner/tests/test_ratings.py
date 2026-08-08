"""Star ratings: who is allowed to give one, when, and what happens to it when
the plan underneath it changes.

The rating is the first thing in this app whose value comes from being
trustworthy rather than from being convenient. A shopping quantity that is
slightly wrong is a mild annoyance in a shop; a library that says nobody likes
fish pie, because a rating was left behind by somebody who never ate it, is a
meal that quietly stops being cooked. So the rules worth testing are the ones
that keep a stored rating attached to a real person who really was at a real
meal:

  - only the household rates, not the guest slot, which stands for a varying
    number of visitors and so is nobody in particular
  - only people the sitting says ate it
  - only meals that have happened, checked on the server as well as in the
    browser, because the browser's clock is a phone's and a tablet left on the
    wrong date shouldn't be able to rate next Thursday
  - a rating disappears with the eater, whether they are taken off the meal or
    out of the household entirely

Run: python3 tests/test_ratings.py  (kept out of the image: Dockerfile copies *.py)
"""

import json
import os
import sys
import tempfile
import threading
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

os.environ["SUPERVISOR_TOKEN"] = "test-token"
os.environ["MEAL_PLANNER_DATA_DIR"] = tempfile.mkdtemp(prefix="ratings-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


# ------------------------------------------------------------ the helpers

def test_clean_ratings():
    valid = {"p_a", "p_b"}
    cases = [
        # What a browser sends, and what an older file holds.
        ({"p_a": 5, "p_b": 1}, {"p_a": 5, "p_b": 1}),
        ({}, {}),
        (None, {}),
        ("four stars", {}),
        # Out of range in either direction is dropped, not clamped: a 9 is a
        # bug somewhere, and storing it as a 5 hides the bug behind an opinion
        # nobody expressed.
        ({"p_a": 0}, {}),
        ({"p_a": 6}, {}),
        ({"p_a": -3}, {}),
        # Strings survive a round trip through anything that stringifies JSON.
        ({"p_a": "4"}, {"p_a": 4}),
        ({"p_a": "lovely"}, {}),
        # Somebody who has left the household.
        ({"p_gone": 5}, {}),
    ]
    for value, want in cases:
        check("clean_ratings(%r)" % (value,),
              server.clean_ratings(value, valid), want)

    # Without a list of who exists, only the stars are checked - which is what
    # the migration on load needs, since it runs before people are read.
    check("clean_ratings with no roll call",
          server.clean_ratings({"p_gone": 4}), {"p_gone": 4})


def test_drop_ratings():
    sitting = {"eaters": ["p_a"], "ratings": {"p_a": 4, "p_b": 2}}
    server.drop_ratings(sitting)
    check("only eaters keep their rating", sitting["ratings"], {"p_a": 4})

    # Nothing to do, and nothing to blow up on.
    bare = {"eaters": ["p_a"]}
    server.drop_ratings(bare)
    check("a sitting with no ratings is left alone", bare, {"eaters": ["p_a"]})


def test_date_of():
    # 2026-08-03 is a Monday.
    check("monday", server.date_of("2026-08-03", "mon"), date(2026, 8, 3))
    check("sunday", server.date_of("2026-08-03", "sun"), date(2026, 8, 9))
    check("thursday", server.date_of("2026-08-03", "thu"), date(2026, 8, 6))
    # Rubbish in doesn't raise: the caller is a request handler, and a 500 for
    # a malformed date is worse than treating it as this week.
    check("a day that isn't one", server.date_of("2026-08-03", "someday"),
          date(2026, 8, 3))


def test_migration_adds_the_field():
    """Every week planned before 1.13.0 has no ratings at all. They have to
    read as "nobody has said yet", not as an error and not as a zero."""
    data = {"weeks": {"2026-08-03": {"mon": {"cookId": None, "sittings": [
        {"id": "s1", "mealId": "m1", "eaters": ["p_a"], "note": ""},
    ]}}}}
    server.migrate_weeks(data)
    sitting = data["weeks"]["2026-08-03"]["mon"]["sittings"][0]
    check("an old sitting gains an empty ratings dict", sitting["ratings"], {})

    # And a file somebody has edited by hand keeps only what makes sense.
    data = {"weeks": {"2026-08-03": {"tue": {"sittings": [
        {"id": "s1", "mealId": "m1", "eaters": ["p_a"],
         "ratings": {"p_a": 5, "p_b": 99}},
    ]}}}}
    server.migrate_weeks(data)
    check("nonsense stars don't survive a load",
          data["weeks"]["2026-08-03"]["tue"]["sittings"][0]["ratings"],
          {"p_a": 5})


# ------------------------------------------------------- the endpoint

HOST = None


def call(method, path, body=None):
    """One API call against a real server on a real socket. The rating rules
    live in the request handler, so testing the functions underneath would test
    everything except the part that decides."""
    data = json.dumps(body).encode() if body is not None else None
    req = Request(HOST + path, data=data, method=method,
                  headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlopen(req) as res:
            return res.status, json.loads(res.read().decode() or "{}")
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def monday(offset_weeks=0):
    today = date.today()
    return (today - timedelta(days=today.weekday())
            + timedelta(weeks=offset_weeks)).isoformat()


def day_name(on):
    return server.DAYS[on.weekday()]


def setup_house():
    """A household, a meal, and that meal planned for today."""
    _, alice = call("POST", "/api/people", {"name": "Alice"})
    _, bob = call("POST", "/api/people", {"name": "Bob"})
    _, meal = call("POST", "/api/meals", {"name": "Fish pie"})
    today = date.today()
    day = day_name(today)
    _, sitting = call("POST", "/api/week/%s/%s/sittings" % (monday(), day),
                      {"mealId": meal["id"]})
    call("PUT", "/api/week/%s/%s/sittings/%s" % (monday(), day, sitting["id"]),
         {"eaters": [alice["id"], bob["id"]]})
    return alice, bob, meal, day, sitting["id"]


def test_endpoint():
    alice, bob, meal, day, sid = setup_house()
    at = "/api/week/%s/%s/sittings/%s/rating" % (monday(), day, sid)

    status, out = call("PUT", at, {"personId": alice["id"], "stars": 5})
    check("a rating is accepted", status, 200)
    check("and comes back on the sitting", out.get("ratings"), {alice["id"]: 5})

    status, out = call("PUT", at, {"personId": bob["id"], "stars": 2})
    check("two people, two ratings", out.get("ratings"),
          {alice["id"]: 5, bob["id"]: 2})

    # Changing your mind overwrites rather than accumulates.
    call("PUT", at, {"personId": alice["id"], "stars": 3})
    _, out = call("PUT", at, {"personId": bob["id"], "stars": 2})
    check("a second rating replaces the first", out["ratings"][alice["id"]], 3)

    # Clearing takes the person out of the dict entirely, so "unrated" and
    # "rated zero" can never be confused in the library's averages.
    _, out = call("PUT", at, {"personId": alice["id"], "stars": None})
    check("cleared, not zeroed", out.get("ratings"), {bob["id"]: 2})

    # Zero stars is not a rating anyone can give - the picker starts at one -
    # so it is read as "take mine off" rather than refused. Null does the same;
    # the two exist because a browser cache holding an older app.js may send
    # either, and neither should be able to store a 0 the averages would then
    # have to reason about.
    call("PUT", at, {"personId": alice["id"], "stars": 4})
    _, out = call("PUT", at, {"personId": alice["id"], "stars": 0})
    check("zero clears rather than storing a nought",
          out.get("ratings"), {bob["id"]: 2})

    for bad in [6, -1, "lots"]:
        status, _ = call("PUT", at, {"personId": bob["id"], "stars": bad})
        check("%r is refused" % (bad,), status, 400)
    _, out = call("PUT", at, {"personId": bob["id"], "stars": 2})
    check("and changed nothing", out["ratings"], {bob["id"]: 2})


def test_only_the_people_who_ate_it():
    alice, bob, meal, day, sid = setup_house()
    at = "/api/week/%s/%s/sittings/%s/rating" % (monday(), day, sid)

    # Alice only. Bob is in the household but not at this meal.
    call("PUT", "/api/week/%s/%s/sittings/%s" % (monday(), day, sid),
         {"eaters": [alice["id"]]})

    status, out = call("PUT", at, {"personId": bob["id"], "stars": 5})
    check("someone who wasn't there can't rate it", status, 400)

    status, out = call("PUT", at, {"personId": server.GUEST_ID, "stars": 5})
    check("nor can the guest slot", status, 400)

    status, out = call("PUT", at, {"personId": "p_nobody", "stars": 5})
    check("nor can a stranger", status, 400)

    status, out = call("PUT", at, {"personId": alice["id"], "stars": 4})
    check("the person who did eat it can", status, 200)


def test_not_before_it_has_been_eaten():
    alice, bob, meal, day, sid = setup_house()

    # Same meal, but on a day next week.
    later = monday(1)
    _, future = call("POST", "/api/week/%s/wed/sittings" % later,
                     {"mealId": meal["id"]})
    call("PUT", "/api/week/%s/wed/sittings/%s" % (later, future["id"]),
         {"eaters": [alice["id"]]})

    status, _ = call("PUT", "/api/week/%s/wed/sittings/%s/rating"
                            % (later, future["id"]),
                     {"personId": alice["id"], "stars": 5})
    check("tomorrow's dinner can't be rated today", status, 400)

    # Yesterday's can. (Not "today's" - that is what the other tests use, and
    # the boundary worth pinning is the one either side of it.)
    before = date.today() - timedelta(days=8)
    key = server.monday_of(before).isoformat()
    _, past = call("POST", "/api/week/%s/%s/sittings" % (key, day_name(before)),
                   {"mealId": meal["id"]})
    call("PUT", "/api/week/%s/%s/sittings/%s" % (key, day_name(before), past["id"]),
         {"eaters": [alice["id"]]})
    status, _ = call("PUT", "/api/week/%s/%s/sittings/%s/rating"
                            % (key, day_name(before), past["id"]),
                     {"personId": alice["id"], "stars": 5})
    check("last week's can", status, 200)


def test_a_rating_follows_its_eater():
    alice, bob, meal, day, sid = setup_house()
    at = "/api/week/%s/%s/sittings/%s/rating" % (monday(), day, sid)
    call("PUT", at, {"personId": alice["id"], "stars": 5})
    call("PUT", at, {"personId": bob["id"], "stars": 1})

    # Bob is taken off the meal. His opinion of it goes with him: a 1 star from
    # somebody the plan now says wasn't there is a number with nothing behind
    # it, and it would go on dragging the library's average down.
    _, out = call("PUT", "/api/week/%s/%s/sittings/%s" % (monday(), day, sid),
                  {"eaters": [alice["id"]]})
    check("taken off the meal, taken off the ratings",
          out.get("ratings"), {alice["id"]: 5})

    # And leaving the household clears the rest.
    call("DELETE", "/api/people/" + alice["id"])
    _, week = call("GET", "/api/week/" + monday())
    left = week["days"][day]["sittings"][0]["ratings"]
    check("a person removed takes their ratings with them", left, {})


def serve():
    global HOST
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    HOST = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def reset():
    """Each endpoint test starts from an empty house: they add people, and a
    household that accumulated across tests would make the guest slot and the
    "everyone" cases depend on what ran first."""
    server.save_data(json.loads(json.dumps(server.DEFAULT_DATA)))


httpd = serve()

for test in [test_clean_ratings, test_drop_ratings, test_date_of,
             test_migration_adds_the_field]:
    test()

for test in [test_endpoint, test_only_the_people_who_ate_it,
             test_not_before_it_has_been_eaten, test_a_rating_follows_its_eater]:
    reset()
    test()

httpd.shutdown()

if FAILURES:
    print("FAILED (%d)\n" % len(FAILURES))
    for failure in FAILURES:
        print("  - " + failure)
    sys.exit(1)
print("ratings: all good")
