"""The palette people wear, and the rules about who may wear what.

A person's colour is the app's only way of saying which name chip is whose. It
carries that on its own - there is no initial, no avatar, nothing else on a chip
but the name and the fill behind it - so two things have to hold, and neither is
obvious enough to leave to the picker in the browser:

  - every colour on offer can be read. The palette is deliberately bright, which
    is only safe because app.js works out black or white lettering per colour
    (inkOn). The contrast check below is that promise written down: if somebody
    adds a colour here that neither ink can sit on, this fails rather than
    shipping a chip nobody can read.
  - no two people share one. The picker greys out what is taken, but it is
    working from a copy of the household that another phone may have moved on
    from, so the server refuses the clash as well. A test for the picker would
    not have caught the two-phones case; this does.

Run: python3 tests/test_colors.py  (kept out of the image: Dockerfile copies
*.py)
"""

import json
import re
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

os.environ["SUPERVISOR_TOKEN"] = "test-token"
os.environ["MEAL_PLANNER_DATA_DIR"] = tempfile.mkdtemp(prefix="colors-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

FAILURES = []
HOST = ""

# What app.js uses when white would be hard work. Kept in step with DARK_INK
# there; the two only ever have to agree about which colours need it.
DARK_INK = (0x1b, 0x1a, 0x17)
WHITE = (0xff, 0xff, 0xff)

# The threshold inkOn() picks white at, and so the floor for the whole palette.
MIN_CONTRAST = 3.6


def check(label, got, want):
    if got != want:
        FAILURES.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


def ok(label, cond):
    if not cond:
        FAILURES.append(label)


# ------------------------------------------------------------------ contrast


def _channel(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_channel(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def rgb(hex_color):
    n = int(hex_color[1:], 16)
    return ((n >> 16) & 255, (n >> 8) & 255, n & 255)


# ---------------------------------------------------------------- difference
#
# Contrast is the wrong tool for "are these two people's chips telling apart".
# Pure red and pure blue sit at 1.4:1 and are not remotely alike; contrast is a
# question about ink on a background, and this is a question about two fills
# side by side. So this converts to Lab, where distance is roughly how different
# two colours look, and measures that instead.


def _lab(hex_color):
    def linear(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(x) for x in rgb(hex_color))
    # sRGB to XYZ, then normalised against D65 white.
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1.0 / 3) if t > 0.008856 else 7.787 * t + 16.0 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def difference(a, b):
    """CIE76 dE. Around 2 is "only side by side"; 40 is "not the same colour"."""
    return sum((p - q) ** 2 for p, q in zip(_lab(a), _lab(b))) ** 0.5


def ink_for(hex_color):
    """The same choice app.js makes: white unless white is hard work."""
    return WHITE if contrast(rgb(hex_color), WHITE) >= MIN_CONTRAST else DARK_INK


# --------------------------------------------------------------------- tests


def test_the_palette_is_well_formed():
    check("thirty-six colours, six rows of six", len(server.COLORS), 36)
    check("no colour is in the palette twice",
          len(set(server.COLORS)), len(server.COLORS))
    for c in server.COLORS:
        ok("%s is a lowercase six-digit hex" % c,
           bool(server._HEX_COLOR.match(c)))


def test_every_colour_can_be_read():
    """The bright half of this palette exists because the lettering follows the
    colour. If a colour is added that neither black nor white sits on, the chip
    is unreadable and nothing else in the app will say so."""
    for c in server.COLORS:
        got = contrast(rgb(c), ink_for(c))
        ok("%s is legible under the ink it gets (%.2f:1, floor %.1f)"
           % (c, got, MIN_CONTRAST), got >= MIN_CONTRAST)


def test_new_people_get_spread_out_colours():
    """COLOR_ORDER is the palette walked so consecutive people look different.
    A straight walk of the grid gives the first household three reds."""
    check("the order offers every colour",
          sorted(server.COLOR_ORDER), sorted(server.COLORS))
    check("and offers none of them twice",
          len(set(server.COLOR_ORDER)), len(server.COLOR_ORDER))

    people = []
    for _ in range(len(server.COLORS)):
        people.append({"id": "p_%d" % len(people),
                       "color": server.next_color(people)})
    check("a household filling the palette gets no duplicates",
          len({p["color"] for p in people}), len(server.COLORS))

    # Every household is somewhere in this sequence, so the whole of it has to
    # hold, not just the first few.
    handed_out = [p["color"] for p in people]
    for a, b in zip(handed_out, handed_out[1:]):
        ok("%s and %s don't look like the same colour (dE %.0f)"
           % (a, b, difference(a, b)), difference(a, b) >= 40)


def test_only_palette_colours_are_accepted():
    check("a palette colour passes",
          server.clean_color(server.COLORS[0]), server.COLORS[0])
    check("upper case is the same colour",
          server.clean_color(server.COLORS[0].upper()), server.COLORS[0])
    check("and so is one with spaces round it",
          server.clean_color("  " + server.COLORS[0] + " "), server.COLORS[0])

    for junk in (None, "", "red", "#fff", "#0055f", "#0055fff", "0055ff",
                 "#gggggg", "#123456", 0x0055ff, ["#0055ff"],
                 "#0055ff; background: url(x)"):
        check("%r is not a colour we offer" % (junk,),
              server.clean_color(junk), None)


def test_a_colour_two_people_want():
    """The check the picker cannot be trusted to have made, because the phone it
    is running on may be a minute behind the household."""
    people = [{"id": "p_a", "color": "#ff0000"},
              {"id": "p_b", "color": "#0000ff"}]

    ok("somebody else's colour is taken",
       server.color_taken(people, "#0000ff", "p_a"))
    ok("your own colour is not taken from you",
       not server.color_taken(people, "#ff0000", "p_a"))
    ok("a colour nobody has is free",
       not server.color_taken(people, "#ffff00", "p_a"))
    ok("a person not in the list is treated as new",
       server.color_taken(people, "#ff0000", "p_new"))


def test_a_person_with_no_colour_blocks_nothing():
    """Data written by a version that predates all of this, or hand-edited."""
    people = [{"id": "p_a"}, {"id": "p_b", "color": None}]
    for c in server.COLORS:
        ok("%s is still free beside a colourless person" % c,
           not server.color_taken(people, c, "p_new"))
    check("and they are the next in line for one",
          server.next_color(people), server.COLOR_ORDER[0])


# ------------------------------------------------------ the kitchen display
#
# The bell button is the one place an accent is used as a fill rather than as
# text or a rule, so it is the one place the accent needs lettering chosen for
# it. It had a fixed near-black, which was picked against the dark theme's
# accents - those are bright colours meant to glow on a dark screen. The light
# theme's twelve are the deep versions of the same names, and near-black on the
# light blue was 2:1: a button you cannot read from across the kitchen, which is
# the only distance it is ever read from.


def test_the_bell_button_can_be_read_on_every_accent():
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    # Imported under another name: this file already has a contrast() of its
    # own, which is the point of the second test below.
    import contrast as checker  # noqa: E402

    accents = checker.kitchen_accents()
    check("both themes' accents are found", len(accents), 24)

    for label, background, ink in accents:
        ok("%s has lettering chosen for it" % label, ink is not None)
        if ink is None:
            continue
        got = checker.ratio(background, ink)
        ok("%s: %s on %s is readable (%.2f:1)" % (label, ink, background, got),
           got >= 4.5)


def test_buttons_on_a_coloured_surface_declare_their_own_colour():
    """The star picker is filled with a person's colour, and everything on it is
    meant to inherit the lettering app.js chose for that colour: the numeral
    through `color: inherit`, the star through `currentColor`.

    A <button> does not inherit colour. The browser's own stylesheet gives it
    `buttontext`, which is black, and that wins over the picker's colour because
    it is set on the button rather than passed through it. So every button
    between the picker and its contents has to declare a colour of its own, or
    the chain breaks there and the contents come out black.

    This shipped. On the bright half of the palette black is what those get
    anyway, so it looked correct; on a deep blue the name chip said the name in
    white and her star picker came up in black.

    The check is on the stylesheet because it cannot be done in the browser
    tests: jsdom does not model the button rule, and reports the inherited
    colour whether or not it has been declared - so a computed-style test would
    have passed with the bug in place, which is worse than no test at all."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import contrast as checker  # noqa: E402

    for selector in (".star-btn", ".star-clear"):
        ok("%s declares a colour, so what is inside it inherits the picker's"
           % selector, checker.declares_colour("style.css", selector))

    # And the other half of the same fix: nothing on the picker goes back to a
    # hardcoded white, which is what ruled out the bright half of the palette.
    for selector in (".star-btn", ".star-clear", ".star-n",
                     ".star-pop.upward .star-clear"):
        body = checker.declarations("style.css", selector)
        ok("%s has no hardcoded white left in it" % selector,
           not re.search(r"#fff\b|#ffffff\b|\brgba?\(\s*255\s*,\s*255\s*,\s*255",
                         body))


def test_the_checker_agrees_with_the_app():
    """tools/contrast.py carries its own copy of the ink rule so it can be run
    on a colour that is not in the app yet. The two have to agree, or the tool
    is checking something the app does not do."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    # Imported under another name: this file already has a contrast() of its
    # own, which is the point of the second test below.
    import contrast as checker  # noqa: E402

    check("the same switch point", checker.INK_SWITCH, MIN_CONTRAST)
    check("the same dark ink", checker.rgb(checker.DARK_INK), DARK_INK)
    for c in server.COLORS:
        check("the same ink chosen for %s" % c,
              checker.rgb(checker.ink_on(c)), ink_for(c))
        ok("the same ratio for %s" % c,
           abs(checker.ratio(c, checker.ink_on(c))
               - contrast(rgb(c), ink_for(c))) < 0.001)


# ----------------------------------------------------------- the endpoint
#
# The rules above live in helpers, but what a phone actually meets is PUT
# /api/people/<id>, and that is where the decisions are made about a body with
# a name in it, a colour in it, both, or neither.


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(HOST + path, data=data, method=method,
                  headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlopen(req) as res:
            return res.status, json.loads(res.read().decode() or "{}")
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def add(name):
    status, person = call("POST", "/api/people", {"name": name})
    check("added %s" % name, status, 201)
    return person


def a_free_colour():
    """A colour nobody in the house has. Not simply "one that isn't hers": the
    default household already contains the guest slot, which is wearing one."""
    _, data = call("GET", "/api/data")
    taken = {p.get("color") for p in data["people"]}
    return next(c for c in server.COLORS if c not in taken)


def test_the_app_is_told_what_it_may_choose_from():
    status, data = call("GET", "/api/data")
    check("/api/data answers", status, 200)
    check("and carries the palette with it", data.get("palette"), server.COLORS)


def test_changing_a_colour():
    ann = add("Ann")
    free = a_free_colour()

    status, updated = call("PUT", "/api/people/" + ann["id"], {"color": free})
    check("a free colour is accepted", status, 200)
    check("and is what she is wearing", updated["color"], free)
    check("her name is untouched", updated["name"], "Ann")

    _, data = call("GET", "/api/data")
    check("and it survived the save",
          [p["color"] for p in data["people"] if p["id"] == ann["id"]], [free])


def test_a_name_on_its_own_still_works():
    """Rename is the older caller and sends no colour at all."""
    bob = add("Bob")
    status, updated = call("PUT", "/api/people/" + bob["id"], {"name": "Robert"})
    check("renaming still works", status, 200)
    check("the new name", updated["name"], "Robert")
    check("and the colour is left alone", updated["color"], bob["color"])


def test_both_at_once():
    cal = add("Cal")
    free = a_free_colour()
    status, updated = call("PUT", "/api/people/" + cal["id"],
                           {"name": "Callum", "color": free})
    check("both change together", (status, updated["name"], updated["color"]),
          (200, "Callum", free))


def test_what_is_refused():
    dee = add("Dee")
    eve = add("Eve")
    path = "/api/people/" + dee["id"]

    status, _ = call("PUT", path, {"color": eve["color"]})
    check("somebody else's colour is refused", status, 409)

    status, _ = call("PUT", path, {"color": "#123456"})
    check("a colour off the palette is refused", status, 400)

    status, _ = call("PUT", path, {"color": "not a colour"})
    check("so is a colour that isn't one", status, 400)

    status, _ = call("PUT", path, {})
    check("an empty body changes nothing", status, 400)

    status, _ = call("PUT", path, {"name": "   "})
    check("a blank name is still refused", status, 400)

    status, _ = call("PUT", "/api/people/p_nobody", {"color": "#ffff00"})
    check("and a person who isn't here is a 404", status, 404)

    # After all that, she is exactly as she was.
    _, data = call("GET", "/api/data")
    kept = [p for p in data["people"] if p["id"] == dee["id"]][0]
    check("nothing was half-applied", (kept["name"], kept["color"]),
          ("Dee", dee["color"]))


def test_keeping_your_own_colour():
    """The picker doesn't send this - it closes instead - but a second phone
    can, and "the colour you already have is taken" would be a silly refusal."""
    fay = add("Fay")
    status, updated = call("PUT", "/api/people/" + fay["id"],
                           {"color": fay["color"]})
    check("your own colour is not a clash", status, 200)
    check("and you keep it", updated["color"], fay["color"])


# ------------------------------------------------------- the household order
#
# The order people are kept in is the order their names are drawn in
# everywhere: the chips on a week card, the eating toggles, the rating pills,
# the kitchen display. Before it was reorderable it was arrival order and
# nothing read it, so a sitting's `eaters` - the order people were tapped -
# was what the week card used. That gave the same two people at the same table
# a different order on Tuesday than on Wednesday.


def test_the_guest_slot_stays_at_the_end():
    """ensure_guest() adds it as soon as there is one real person, and everyone
    after that is appended behind it. A house of five had it sitting second."""
    ann = add("Ann")
    bob = add("Bob")
    _, data = call("GET", "/api/data")
    order = [p["id"] for p in data["people"]]
    check("the guest is last after adding people", order[-1], server.GUEST_ID)
    check("and the people are in the order they arrived",
          order[:2], [ann["id"], bob["id"]])


def test_reordering():
    ann, bob, cal = add("Ann"), add("Bob"), add("Cal")
    ids = [cal["id"], ann["id"], bob["id"], server.GUEST_ID]

    status, people = call("POST", "/api/people/order", {"ids": ids})
    check("the new order is accepted", status, 200)
    check("and is what comes back", [p["id"] for p in people], ids)

    _, data = call("GET", "/api/data")
    check("and it survived the save",
          [p["id"] for p in data["people"]], ids)


def test_the_guest_cannot_be_moved_off_the_end():
    ann, bob = add("Ann"), add("Bob")
    status, people = call("POST", "/api/people/order",
                          {"ids": [server.GUEST_ID, ann["id"], bob["id"]]})
    check("an order with the guest first is still accepted", status, 200)
    check("but the guest is put back on the end",
          [p["id"] for p in people], [ann["id"], bob["id"], server.GUEST_ID])


def test_an_order_that_no_longer_fits_the_household():
    """Two phones in Settings at once. The one holding the older list must not
    be able to drop whoever the other one added."""
    ann, bob = add("Ann"), add("Bob")

    for bad, why in (
            ([ann["id"]], "a list missing people"),
            ([ann["id"], bob["id"], server.GUEST_ID, "p_nobody"],
             "a list with somebody who isn't here"),
            ([ann["id"], ann["id"], server.GUEST_ID], "a list with a repeat"),
            ("not a list", "something that isn't a list"),
            ([1, 2, 3], "a list of things that aren't ids")):
        status, _ = call("POST", "/api/people/order", {"ids": bad})
        ok("%s is refused (got %d)" % (why, status), status == 400)

    _, data = call("GET", "/api/data")
    check("and the household is untouched",
          [p["id"] for p in data["people"]],
          [ann["id"], bob["id"], server.GUEST_ID])


def test_the_kitchen_display_reads_the_household_order():
    """The display is read at a glance from across a room, so a name that moves
    between days is a name you have to read rather than recognise."""
    ann, bob, cal = add("Ann"), add("Bob"), add("Cal")

    # Tapped in the reverse of the household's order.
    data = server.load_data()
    key = server.monday_of(server.date.today()).isoformat()
    data["weeks"][key] = server.blank_week()
    data["weeks"][key]["mon"]["sittings"] = [
        server.new_sitting(eaters=[cal["id"], ann["id"], bob["id"]])]
    server.save_data(data)

    view = server.kitchen_view(server.load_data(), key)
    monday = [d for d in view["days"] if d["day"] == "mon"][0]
    check("the display lists them in household order",
          monday["meals"][0]["eaters"], ["Ann", "Bob", "Cal"])

    # And it follows the order when that changes.
    call("POST", "/api/people/order",
         {"ids": [cal["id"], bob["id"], ann["id"], server.GUEST_ID]})
    view = server.kitchen_view(server.load_data(), key)
    monday = [d for d in view["days"] if d["day"] == "mon"][0]
    check("and follows it when it changes",
          monday["meals"][0]["eaters"], ["Cal", "Bob", "Ann"])


def serve():
    global HOST
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    HOST = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def reset():
    server.save_data(json.loads(json.dumps(server.DEFAULT_DATA)))


for test in [test_the_palette_is_well_formed,
             test_every_colour_can_be_read,
             test_new_people_get_spread_out_colours,
             test_only_palette_colours_are_accepted,
             test_a_colour_two_people_want,
             test_a_person_with_no_colour_blocks_nothing,
             test_the_bell_button_can_be_read_on_every_accent,
             test_buttons_on_a_coloured_surface_declare_their_own_colour,
             test_the_checker_agrees_with_the_app]:
    test()

httpd = serve()
for test in [test_the_app_is_told_what_it_may_choose_from,
             test_changing_a_colour,
             test_a_name_on_its_own_still_works,
             test_both_at_once,
             test_what_is_refused,
             test_keeping_your_own_colour,
             test_the_guest_slot_stays_at_the_end,
             test_reordering,
             test_the_guest_cannot_be_moved_off_the_end,
             test_an_order_that_no_longer_fits_the_household,
             test_the_kitchen_display_reads_the_household_order]:
    reset()
    test()
httpd.shutdown()

if FAILURES:
    print("FAILED (%d)\n" % len(FAILURES))
    for failure in FAILURES:
        print("  - " + failure)
    sys.exit(1)
print("colours: all good")
