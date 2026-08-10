#!/usr/bin/env python3
"""Contrast checker for everything in this app that puts text on a colour.

    python3 tools/contrast.py              # audit the app as it stands
    python3 tools/contrast.py -v           # show every pairing, not just fails
    python3 tools/contrast.py '#2a5474'    # what should sit on this colour?
    python3 tools/contrast.py '#2a5474' '#10241a'   # ratio for one pairing

Why this exists rather than a website: the colours here are not written down in
one place. The person palette is a list in server.py, the kitchen accents are
twenty-four CSS variables split across two themes, and the lettering that goes
on them is decided in three different ways - a CSS variable, a hardcoded value,
and a function in app.js. Checking a colour in a browser tool tells you about
that colour; this tells you whether the app is actually going to put readable
text on it, which is the question.

The thresholds:

  4.5:1  normal text (WCAG AA)
  3.0:1  large or bold text - and the kitchen display is all of it
  3.6:1  what inkOn() in app.js switches from white to black at, and so the
         floor the person palette is held to

Exit code is 1 if anything fails, so it can go in a release check.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

AA_NORMAL = 4.5
AA_LARGE = 3.0
INK_SWITCH = 3.6          # must match DARK_INK/inkOn in static/app.js
DARK_INK = "#1b1a17"
WHITE = "#ffffff"


# ------------------------------------------------------------------ the maths

def _channel(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def rgb(color):
    """Accepts #rgb and #rrggbb, with or without the hash."""
    h = str(color).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or not re.match(r"^[0-9a-fA-F]{6}$", h):
        raise ValueError("not a hex colour: %r" % (color,))
    n = int(h, 16)
    return ((n >> 16) & 255, (n >> 8) & 255, n & 255)


def luminance(color):
    r, g, b = (_channel(x) for x in rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ink_on(color):
    """The choice app.js makes: white unless white would be hard work."""
    return WHITE if ratio(color, WHITE) >= INK_SWITCH else DARK_INK


# ------------------------------------------------------- reading the app's own

def person_palette():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    block = re.search(r"^COLORS = \[(.*?)\]", src, re.S | re.M)
    return re.findall(r"#[0-9a-f]{6}", block.group(1)) if block else []


def kitchen_accents():
    """The twelve accents in each theme, with the ink that theme puts on them.

    Returns [(label, background, ink)]. The light set is matched first and
    removed, because its selector contains the dark set's as a substring."""
    css = open(os.path.join(ROOT, "static", "kitchen.css"), encoding="utf-8").read()

    def ink_var(scope):
        m = re.search(r"%s\s*\{[^}]*?--k-accent-ink:\s*(#[0-9a-fA-F]{3,6})"
                      % scope, css, re.S)
        return m.group(1) if m else None

    light_ink, dark_ink = ink_var(r'html\[data-theme="light"\]'), ink_var(":root")

    light = re.findall(
        r'html\[data-theme="light"\]\[data-accent="(\w+)"\]\s*\{\s*'
        r"--k-accent:\s*(#[0-9a-fA-F]{6})", css)
    for name, color in light:
        css = css.replace('html[data-theme="light"][data-accent="%s"]' % name, "")
    dark = re.findall(
        r'html\[data-accent="(\w+)"\]\s*\{\s*--k-accent:\s*(#[0-9a-fA-F]{6})', css)

    out = []
    for name, color in dark:
        out.append(("kitchen dark / " + name, color, dark_ink))
    for name, color in light:
        out.append(("kitchen light / " + name, color, light_ink))
    return out


# --------------------------------------------------------------------- report

def audit(verbose=False):
    checks = []

    for color in person_palette():
        checks.append(("person chip " + color, color, ink_on(color), INK_SWITCH))

    for label, color, ink in kitchen_accents():
        if ink is None:
            checks.append((label + " (no --k-accent-ink found)", color, None, 0))
        else:
            # The kitchen display is large bold text read across a room, but
            # there is no reason to aim low when the colours are ours to pick.
            checks.append((label, color, ink, AA_NORMAL))

    failed = []
    for label, bg, ink, floor in checks:
        if ink is None:
            failed.append("%-30s  could not find its lettering colour" % label)
            continue
        got = ratio(bg, ink)
        mark = "ok " if got >= floor else "FAIL"
        if got < floor:
            failed.append("%-30s  %s on %s is %.2f:1, wants %.1f"
                          % (label, ink, bg, got, floor))
        if verbose or got < floor:
            print("  %s %-28s %s on %s  %5.2f:1" % (mark, label, ink, bg, got))

    print("\n%d pairings checked, %d below target." % (len(checks), len(failed)))
    if failed:
        print()
        for line in failed:
            print("  - " + line)
    return 0 if not failed else 1


def describe(color, against=None):
    if against:
        got = ratio(color, against)
        verdict = ("passes AA for any text" if got >= AA_NORMAL else
                   "passes AA for large text only" if got >= AA_LARGE else
                   "fails")
        print("%s on %s: %.2f:1 - %s" % (against, color, got, verdict))
        return 0 if got >= AA_LARGE else 1

    w, d = ratio(color, WHITE), ratio(color, DARK_INK)
    print("%s" % color)
    print("  white  %s  %5.2f:1" % (WHITE, w))
    print("  dark   %s  %5.2f:1" % (DARK_INK, d))
    print("  the app would use %s" % ink_on(color))
    if max(w, d) < AA_LARGE:
        print("  neither is readable on this - it is not a colour to put text on")
        return 1
    return 0


def main(argv):
    args = [a for a in argv if a != "-v"]
    if not args:
        return audit(verbose="-v" in argv)
    try:
        if len(args) == 1:
            return describe(args[0])
        return describe(args[0], args[1])
    except ValueError as exc:
        print(exc)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
