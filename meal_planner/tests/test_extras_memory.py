"""What the "Also needed" box remembers, and the two ways a name leaves it.

The box is trained on everything ever typed into it. That is what makes "bak"
find baking paper in seven weeks, and it is also what makes a name typed wrong
once a name suggested forever - on the phone, and on the kitchen display, where
the suggestions are most of how anything gets added at all.

So there are now two ways a remembered name can go. Removed by hand from the
Settings tab, for the candle bought for one birthday. Or retired by a
correction: tapping "Coke Xero" on the list and fixing the spelling has to take
the misspelling out of the suggestions too, or the person who typed it wrong the
first time is offered it again the next time they start typing those letters.

The three things worth guarding here:

  - a rename keeps everything about the entry except the word. Quantity, unit,
    whether it is on order and when it was ordered. A spelling mistake is not a
    reason to lose the fact that a delivery is nine days late.
  - the corrected spelling inherits what the wrong one had been counted for, so
    a weekly staple doesn't drop to the bottom of the suggestions the day
    somebody fixes a letter in it.
  - a name another line on the list still goes by is not retired. Then it is a
    name in use, not a mistake.

Run: python3 tests/test_extras_memory.py  (kept out of the image: Dockerfile
copies *.py)
"""

import json
import os
import sys
import tempfile
import threading
from datetime import date
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

os.environ["SUPERVISOR_TOKEN"] = "test-token"
os.environ["MEAL_PLANNER_DATA_DIR"] = tempfile.mkdtemp(prefix="extras-memory-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


# ------------------------------------------------- the functions underneath

def test_history_shape():
    """What the Settings tab draws: the key it will send back to remove the
    row, the name as it is suggested, and enough to tell a staple from a
    one-off without having to remember March."""
    data = {"extraNames": {
        "foil": {"item": "Foil", "used": 9, "at": "2026-01-04"},
        "candle": {"item": "Candles", "used": 1, "at": "2026-08-01"},
        "bin bag": {"item": "Bin Bags", "used": 9, "at": "2026-08-10"},
        # Written by hand, or by a version that didn't set these.
        "junk": "not a record",
        "nameless": {"used": 4},
    }}
    rows = server.extras_history(data)
    # Most used first, then most recent - the suggestion order, so the thing
    # you are hunting for is where you last saw it offered.
    check("history order", [r["item"] for r in rows],
          ["Bin Bags", "Foil", "Candles"])
    check("history carries the key", rows[0]["key"], "bin bag")
    check("history carries the count", rows[0]["used"], 9)
    check("history carries the date", rows[0]["at"], "2026-08-10")
    # Unreadable records are dropped rather than crashing the section.
    check("junk dropped", len(rows), 3)


def test_forget():
    data = {"extraNames": {
        "foil": {"item": "Foil", "used": 3},
        "candle": {"item": "Candles", "used": 1},
    }}
    check("forgot one", server.forget_extras(data, ["candle"]), 1)
    check("the other stayed", sorted(data["extraNames"]), ["foil"])
    # A row drawn before a migration re-keyed the file sends the name it had.
    # It still has to remove itself.
    check("by name too", server.forget_extras(data, ["Foils"]), 1)
    check("nothing left", data["extraNames"], {})
    # Asking to forget something already gone is not an error: two phones, one
    # list, and the other one got there first.
    check("gone already", server.forget_extras(data, ["foil"]), 0)
    check("no memory at all", server.forget_extras({}, ["foil"]), 0)


def test_rename_remembered():
    today = date.today().isoformat()

    # The plain case: a misspelling typed three times, corrected once. The
    # count follows the correction, and the misspelling goes.
    data = {"extraNames": {"coke xero": {"item": "Coke Xero", "used": 3,
                                         "at": "2026-08-01"}}}
    server.rename_remembered(data, "Coke Xero", "Coke Zero", set())
    check("typo retired", "coke xero" in data["extraNames"], False)
    check("count carried", data["extraNames"]["coke zero"]["used"], 3)
    check("dated today", data["extraNames"]["coke zero"]["at"], today)
    check("stored Title Cased", data["extraNames"]["coke zero"]["item"],
          "Coke Zero")

    # Corrected onto something already remembered: the two were always one
    # thing, so the counts add up rather than one of them being thrown away.
    data = {"extraNames": {
        "coke xero": {"item": "Coke Xero", "used": 2},
        "coke zero": {"item": "Coke Zero", "used": 5, "at": "2026-07-01"},
    }}
    server.rename_remembered(data, "Coke Xero", "Coke Zero", set())
    check("merged counts", data["extraNames"]["coke zero"]["used"], 7)
    check("merged, typo gone", "coke xero" in data["extraNames"], False)

    # Another line on the list still calls it that. Then it is a name in use,
    # not a mistake, and the Settings tab is where that gets decided.
    data = {"extraNames": {"milk": {"item": "Milk", "used": 8}}}
    server.rename_remembered(data, "Milk", "Oat milk", {"milk"})
    check("name still in use survives", "milk" in data["extraNames"], True)
    check("original count untouched", data["extraNames"]["milk"]["used"], 8)
    # And the new name starts at one rather than inheriting a count it has no
    # claim to.
    check("new name starts at one", data["extraNames"]["oat milk"]["used"], 1)

    # Correcting the case, or a plural, normalises to the same key. Nothing to
    # retire, and nothing to lose.
    data = {"extraNames": {"cucumber": {"item": "Cucumber", "used": 4}}}
    server.rename_remembered(data, "cucumbers", "Cucumber", set())
    check("same key, count kept", data["extraNames"]["cucumber"]["used"], 4)
    check("same key, nothing else made", sorted(data["extraNames"]),
          ["cucumber"])

    # A file with no memory yet, and a rename onto nothing.
    data = {}
    server.rename_remembered(data, "Foil", "", set())
    check("empty new name does nothing", data.get("extraNames"), {})


# ------------------------------------------------------------- the endpoints
#
# The rename rules - what gets parsed off the front, when two lines merge -
# live in the request handler, so testing the functions underneath would test
# everything except the part that decides.

HOST = None


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(HOST + path, data=data, method=method,
                  headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlopen(req) as res:
            return res.status, json.loads(res.read().decode() or "{}")
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def add(text):
    _, entry = call("POST", "/api/extras", {"item": text})
    return entry


def only(extras, name):
    return [e for e in extras if e["item"] == name]


def test_rename_keeps_everything_else():
    entry = add("3 tins chopped tomatoes")
    call("POST", "/api/extras/state", {"ids": [entry["id"]], "state": "ordered"})

    code, res = call("POST", "/api/extras/rename",
                     {"id": entry["id"], "item": "Chopped Tomatos"})
    check("rename ok", code, 200)
    row = res["extras"][0]
    check("the word changed", row["item"], "Chopped Tomatos")
    check("quantity kept", row["qty"], 3.0)
    check("unit kept", row["unit"], "tin")
    # The whole point: a misspelling is not a reason to lose the fact that a
    # delivery is nine days late.
    check("still on order", row["state"], "ordered")
    check("ordered date kept", row["orderedAt"], date.today().isoformat())
    check("id kept", row["id"], entry["id"])


def test_rename_moves_the_suggestion():
    entry = add("Coke Xero")
    _, before = call("GET", "/api/extras/history")
    check("misspelling remembered",
          [r["item"] for r in before["history"]], ["Coke Xero"])

    _, res = call("POST", "/api/extras/rename",
                  {"id": entry["id"], "item": "Coke Zero"})
    check("suggestions corrected", res["knownExtras"], ["Coke Zero"])

    _, after = call("GET", "/api/extras/history")
    check("history corrected too",
          [r["item"] for r in after["history"]], ["Coke Zero"])


def test_rename_only_takes_a_number_if_one_was_typed():
    entry = add("500g mince")
    # A spelling correction leaves the quantity where the stepper left it.
    _, res = call("POST", "/api/extras/rename",
                  {"id": entry["id"], "item": "Beef mince"})
    row = res["extras"][0]
    check("bare name keeps the weight", (row["qty"], row["unit"]),
          (500.0, "g"))
    # Title Cased on the way out like every other line on this list.
    check("no digit stranded in the name", row["item"], "Beef Mince")

    # Typing a quantity over it plainly means to set both.
    _, res = call("POST", "/api/extras/rename",
                  {"id": entry["id"], "item": "750g beef mince"})
    row = res["extras"][0]
    check("a typed quantity is taken", (row["qty"], row["unit"]),
          (750.0, "g"))
    check("and stays out of the name", row["item"], "Beef Mince")


def test_rename_merges_onto_a_line_already_there():
    """Correcting "Coke Xero" on a list that already says "Coke Zero" leaves
    one row, not two. There was only ever one thing here."""
    right = add("2 Coke Zero")
    wrong = add("3 Coke Xero")
    _, res = call("POST", "/api/extras/rename",
                  {"id": wrong["id"], "item": "Coke Zero"})
    rows = only(res["extras"], "Coke Zero")
    check("one row afterwards", len(rows), 1)
    check("quantities added", rows[0]["qty"], 5.0)
    check("the surviving row is the one that was right", rows[0]["id"],
          right["id"])
    check("nothing else left", len(res["extras"]), 1)


def test_rename_does_not_merge_across_a_delivery():
    """One ordered and one not is two different states of affairs - one is in a
    van, the other is on a list - and folding them together would lose which is
    which."""
    ordered = add("2 Milk")
    call("POST", "/api/extras/state", {"ids": [ordered["id"]], "state": "ordered"})
    still = add("1 Mlk")
    _, res = call("POST", "/api/extras/rename",
                  {"id": still["id"], "item": "Milk"})
    check("both rows survive", len(res["extras"]), 2)
    check("states intact", sorted(e["state"] for e in res["extras"]),
          ["need", "ordered"])


def test_rename_leaves_a_name_another_line_uses():
    add("Milk")
    second = add("Mlk")
    _, res = call("POST", "/api/extras/rename",
                  {"id": second["id"], "item": "Oat milk"})
    # "Mlk" was only ever this line's, so it goes. "Milk" is another line's and
    # is nothing to do with this correction, so it stays.
    _, after = call("GET", "/api/extras/history")
    remembered = sorted(r["item"] for r in after["history"])
    check("the corrected line's own name retired", "Mlk" in remembered, False)
    check("the other line's name kept", "Milk" in remembered, True)
    check("the correction remembered", "Oat Milk" in remembered, True)
    check("two rows still", len(res["extras"]), 2)


def test_rename_refusals():
    code, res = call("POST", "/api/extras/rename",
                     {"id": "nope", "item": "Foil"})
    check("no such row", code, 404)
    entry = add("Foil")
    code, res = call("POST", "/api/extras/rename",
                     {"id": entry["id"], "item": "   "})
    check("nothing typed", code, 400)
    _, list_after = call("GET", "/api/shopping")
    check("and the row is untouched",
          [e["item"] for e in list_after["extras"]], ["Foil"])


def test_history_rename_fixes_both_places():
    """Correcting a remembered name from Settings is the same job the shopping
    row does, reached from the other end - so it fixes the word in both places.
    A correction you have to make twice is one that gets made once."""
    entry = add("2 Coke Xero")
    _, before = call("GET", "/api/extras/history")
    key = before["history"][0]["key"]

    code, res = call("POST", "/api/extras/history/rename",
                     {"key": key, "item": "Coke Zero"})
    check("rename ok", code, 200)
    check("the remembered name is corrected",
          [r["item"] for r in res["history"]], ["Coke Zero"])
    check("and so is the suggestion", res["knownExtras"], ["Coke Zero"])
    # The half that would otherwise have to be done again on the other tab.
    check("and the line on the list",
          [e["item"] for e in res["extras"]], ["Coke Zero"])
    check("which keeps everything else",
          (res["extras"][0]["qty"], res["extras"][0]["id"]), (2.0, entry["id"]))
    # The count follows the correction rather than resetting.
    check("count kept", res["history"][0]["used"], 1)


def test_history_rename_merges():
    """Corrected onto something already remembered, the counts add up - the two
    were always one thing and two ways of spelling it. And a list that now says
    the same thing twice folds into one row."""
    add("2 Coke Zero")
    add("3 Coke Xero")
    add("Coke Xero")            # asked for twice under the wrong spelling
    _, before = call("GET", "/api/extras/history")
    key = [r["key"] for r in before["history"] if r["item"] == "Coke Xero"][0]

    _, res = call("POST", "/api/extras/history/rename",
                  {"key": key, "item": "Coke Zero"})
    check("one remembered name afterwards", len(res["history"]), 1)
    check("with both counts", res["history"][0]["used"], 3)
    check("one row on the list", len(res["extras"]), 1)
    # 2 + 3, and the third add folded into the second at the time.
    check("quantities added", res["extras"][0]["qty"], 6.0)


def test_history_rename_does_not_merge_across_a_delivery():
    ordered = add("2 Mlk")
    call("POST", "/api/extras/state", {"ids": [ordered["id"]], "state": "ordered"})
    add("1 Milk")
    _, before = call("GET", "/api/extras/history")
    key = [r["key"] for r in before["history"] if r["item"] == "Mlk"][0]

    _, res = call("POST", "/api/extras/history/rename",
                  {"key": key, "item": "Milk"})
    check("both rows survive", len(res["extras"]), 2)
    check("states intact", sorted(e["state"] for e in res["extras"]),
          ["need", "ordered"])
    check("both now spelled right",
          sorted(e["item"] for e in res["extras"]), ["Milk", "Milk"])


def test_history_rename_leaves_other_names_alone():
    add("Foil")
    add("Mlk")
    _, before = call("GET", "/api/extras/history")
    key = [r["key"] for r in before["history"] if r["item"] == "Mlk"][0]
    _, res = call("POST", "/api/extras/history/rename",
                  {"key": key, "item": "Milk"})
    # A spelling correction, not a find and replace.
    check("the untouched line is untouched",
          sorted(e["item"] for e in res["extras"]), ["Foil", "Milk"])
    check("and its name is still remembered",
          "Foil" in [r["item"] for r in res["history"]], True)


def test_history_rename_case_only():
    """Same normalised key - a change of case, or a plural. Nothing to move,
    but the spelling on the record still becomes the one just typed."""
    add("bbq sauce")
    _, before = call("GET", "/api/extras/history")
    key = before["history"][0]["key"]
    _, res = call("POST", "/api/extras/history/rename",
                  {"key": key, "item": "Barbecue sauce"})
    check("renamed", [r["item"] for r in res["history"]], ["Barbecue Sauce"])
    check("one entry still", len(res["history"]), 1)
    check("count survives", res["history"][0]["used"], 1)


def test_history_rename_refusals():
    code, _ = call("POST", "/api/extras/history/rename",
                   {"key": "nope", "item": "Foil"})
    check("no such remembered name", code, 404)
    add("Foil")
    _, before = call("GET", "/api/extras/history")
    key = before["history"][0]["key"]
    code, _ = call("POST", "/api/extras/history/rename",
                   {"key": key, "item": "   "})
    check("nothing typed", code, 400)
    code, _ = call("POST", "/api/extras/history/rename", {"item": "Foil"})
    check("no key at all", code, 400)
    _, after = call("GET", "/api/extras/history")
    check("and nothing changed",
          [r["item"] for r in after["history"]], ["Foil"])


def test_forget_endpoint():
    add("Birthday Candles")
    add("Foil")
    _, before = call("GET", "/api/extras/history")
    key = [r["key"] for r in before["history"] if r["item"] == "Birthday Candles"][0]

    code, res = call("POST", "/api/extras/forget", {"keys": [key]})
    check("forget ok", code, 200)
    check("gone from history",
          [r["item"] for r in res["history"]], ["Foil"])
    check("gone from the suggestions", res["knownExtras"], ["Foil"])

    # Forgetting a name is about what gets offered next time. Something still
    # to be bought is still to be bought.
    _, shopping = call("GET", "/api/shopping")
    check("still on the list",
          sorted(e["item"] for e in shopping["extras"]),
          ["Birthday Candles", "Foil"])

    code, _ = call("POST", "/api/extras/forget", {"keys": []})
    check("nothing selected", code, 400)


def serve():
    global HOST
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    HOST = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def reset():
    server.save_data(json.loads(json.dumps(server.DEFAULT_DATA)))


for test in [test_history_shape, test_forget, test_rename_remembered]:
    test()

httpd = serve()

for test in [test_rename_keeps_everything_else, test_rename_moves_the_suggestion,
             test_rename_only_takes_a_number_if_one_was_typed,
             test_rename_merges_onto_a_line_already_there,
             test_rename_does_not_merge_across_a_delivery,
             test_rename_leaves_a_name_another_line_uses,
             test_rename_refusals,
             test_history_rename_fixes_both_places,
             test_history_rename_merges,
             test_history_rename_does_not_merge_across_a_delivery,
             test_history_rename_leaves_other_names_alone,
             test_history_rename_case_only,
             test_history_rename_refusals,
             test_forget_endpoint]:
    reset()
    test()

if FAILURES:
    print("FAILED (%d)\n" % len(FAILURES))
    for failure in FAILURES:
        print("  - " + failure)
    sys.exit(1)
print("extras memory: all good")
