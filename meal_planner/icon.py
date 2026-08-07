"""
App icon, drawn in pure Python.

The add-on has no image library, and its source folder is a Windows share that
can't reliably carry binary files, so the home-screen icon is rendered here and
cached in memory rather than shipped as a .png. One render per size and colour
per process, warmed in the background so no request ever waits for it.

The two colours are parameters, not constants: the icon follows whatever accent
that device picked in the app. The caller supplies actual colours rather than an
accent name, so the palette stays in style.css and adding an accent needs no
change here. See _serve_icon in server.py.

The drawing takes --accent-ink rather than always being white, for the same
reason the top bar does: in dark mode the accent is a light pastel, and white on
it reads at about 2:1.

Shapes are described in a 0..1 unit square, so any pixel size can be asked for.
The same drawing is the home-screen icon, the page favicon and the mark in the
top bar - one set of shapes, three uses, rather than an SVG copy of it that
would drift the first time either was edited.
"""

import math
import struct
import threading
import zlib

BG = (61, 131, 97)          # the default green accent, for callers with no choice
FG = (255, 255, 255)        # --accent-ink in the light theme

# 192 and 512 are what the manifest advertises; 64 is the favicon and the mark
# in the top bar, both of which are drawn at a size where the big ones would be
# wasteful to send.
SIZES = (64, 192, 512)

# Bump on any change to the shapes below. The icon URLs are stable, so this is
# the only thing that tells a browser holding a week-old copy to fetch again -
# it goes into the ETag. Nothing else changes when the drawing does.
REV = 4

# One entry is a few hundred KB, and the colour comes off a URL, so a device
# asking for nonsense must not be able to grow this without limit. Twelve
# accents x two themes x three sizes is 72; past that, start again.
MAX_CACHED = 96

_cache = {}
_lock = threading.Lock()


def parse_colour(text, fallback=BG):
    """An 'rrggbb' or '#rrggbb' string as an (r, g, b) tuple.

    Anything else gives the fallback: this is fed straight from a query string,
    so it has to treat junk as "no opinion" rather than as an error."""
    if not text:
        return fallback
    text = text.strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return fallback


# ------------------------------------------------------------------- shapes
# Each answers "is this point inside me?", so _sample can layer them.

def _rrect(x, y, x0, y0, x1, y1, r):
    """Rounded rectangle with corner radius r."""
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy <= r * r


def _stroke(x0, y0, x1, y1, w):
    """One stroke of the drawing: a line of width w with rounded ends.

    Returned as a tuple of everything _sample would otherwise recompute for
    every pixel - the direction, the reciprocal of its squared length, the
    squared half-width, and a bounding box. A 512px icon at 2x2 supersampling
    asks about a million points; working dx and dy out a million times over,
    on a Raspberry Pi, is the difference between one second and thirty."""
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    h = w / 2.0
    return (x0, y0, dx, dy,
            (1.0 / length2 if length2 else 0.0), h * h,
            min(x0, x1) - h, max(x0, x1) + h,
            min(y0, y1) - h, max(y0, y1) + h)


# The house, and a spoon and fork crossed inside it. Both pieces of cutlery lie
# on the same 45 degree diagonal, which is why S turns up throughout the fork:
# the tines run up-right along it and the handle down-left.
S = 0.70710678                                              # sin 45 = cos 45
_HEAD = (0.598, 0.492)                                      # where the tines meet

_STROKES = [
    _stroke(0.100, 0.470, 0.500, 0.118, 0.072),             # roof, left slope
    _stroke(0.500, 0.118, 0.900, 0.470, 0.072),             # roof, right slope
    # Three strokes, not a rectangle: the wall tops have to stop under the roof
    # rather than closing across the middle of the house.
    _stroke(0.175, 0.450, 0.175, 0.845, 0.064),             # left wall
    _stroke(0.175, 0.845, 0.825, 0.845, 0.064),             # floor
    _stroke(0.825, 0.450, 0.825, 0.845, 0.064),             # right wall
    _stroke(0.402, 0.506, 0.663, 0.767, 0.058),             # spoon handle
    _stroke(0.568, 0.462, 0.628, 0.522, 0.095),             # fork neck
    _stroke(0.598, 0.510, 0.337, 0.767, 0.058),             # fork handle
] + [
    _stroke(_HEAD[0] + off * S, _HEAD[1] + off * S,         # three tines
            _HEAD[0] + off * S + 0.160 * S,
            _HEAD[1] + off * S - 0.160 * S, 0.032)
    for off in (-0.058, 0.0, 0.058)
]

# The chimney, the one part that isn't a stroke.
_CHIMNEY = (0.695, 0.145, 0.795, 0.345, 0.014)

# The spoon's bowl: centre, then the semi-axis ALONG the handle and the one
# ACROSS it, in that order. The rotation puts the first of those on the
# diagonal the handle runs down, so a bowl longer than it is wide needs the
# larger number first - the other way round gives a bowl lying across its own
# spoon. Held as sin/cos rather than an angle to keep trigonometry out of the
# pixel loop.
_BOWL = (0.358, 0.462, 0.112, 0.072,
         math.cos(-math.pi / 4.0), math.sin(-math.pi / 4.0))

# Nothing is drawn outside this, so most of the border is answered by four
# comparisons instead of thirteen shapes.
_INK = (0.05, 0.95, 0.06, 0.90)


def _sample(x, y, bg, fg):
    """Colour at a point in the unit square. Two tones only - this ends up at
    16px in a browser tab, where anything subtler is mud."""
    if x < _INK[0] or x > _INK[1] or y < _INK[2] or y > _INK[3]:
        return bg

    for (x0, y0, dx, dy, inv, r2, bx0, bx1, by0, by1) in _STROKES:
        if x < bx0 or x > bx1 or y < by0 or y > by1:
            continue
        t = ((x - x0) * dx + (y - y0) * dy) * inv
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        ex = x - (x0 + t * dx)
        ey = y - (y0 + t * dy)
        if ex * ex + ey * ey <= r2:
            return fg

    cx0, cy0, cx1, cy1, r = _CHIMNEY
    if cx0 <= x <= cx1 and cy0 <= y <= cy1 and _rrect(x, y, cx0, cy0, cx1, cy1, r):
        return fg

    bx, by, along, across, bc, bs = _BOWL
    ux, uy = x - bx, y - by
    ax = (ux * bc - uy * bs) / along
    cx = (ux * bs + uy * bc) / across
    if ax * ax + cx * cx <= 1.0:
        return fg

    return bg


# -------------------------------------------------------------------- render

def _rows(size, bg, fg, ss=None):
    """Pixel rows, supersampled ss x ss and averaged so edges aren't jagged.

    This is pure Python on a Raspberry Pi, so the sample count matters: 3x3 at
    512px is a couple of million calls. Large icons get 2x2 instead, where a
    pixel is small enough relative to the shapes that the difference isn't
    visible."""
    if ss is None:
        ss = 3 if size <= 256 else 2
    step = 1.0 / (size * ss)
    half = step / 2.0
    n = float(ss * ss)
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = 0
            for sy in range(ss):
                y = (py * ss + sy) * step + half
                for sx in range(ss):
                    c = _sample((px * ss + sx) * step + half, y, bg, fg)
                    r += c[0]
                    g += c[1]
                    b += c[2]
            row += bytes((int(r / n), int(g / n), int(b / n)))
        yield row


def _wide_rows(width, height, bg, fg, scale, ss=2):
    """Pixel rows for a rectangle with the drawing centred in it.

    The shapes are described in a unit square, so this is the same render with
    a different map from pixel to unit: the square is placed in the middle at
    `scale` of the shorter side, and everything outside it is background. Used
    for the Home Assistant add-on logo, which is a wide panel rather than the
    square the app's own icon is."""
    side = min(width, height) * scale
    x0 = (width - side) / 2.0
    y0 = (height - side) / 2.0
    step = 1.0 / ss
    half = step / 2.0
    n = float(ss * ss)
    for py in range(height):
        row = bytearray()
        for px in range(width):
            r = g = b = 0
            for sy in range(ss):
                y = ((py + (sy * step + half)) - y0) / side
                for sx in range(ss):
                    c = _sample(((px + (sx * step + half)) - x0) / side, y, bg, fg)
                    r += c[0]
                    g += c[1]
                    b += c[2]
            row += bytes((int(r / n), int(g / n), int(b / n)))
        yield row


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _encode(width, height, rows):
    raw = bytearray()
    for row in rows:
        raw += b"\x00" + row              # filter type 0 (None) on every scanline
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def banner(width=512, height=256, bg=BG, fg=FG, scale=0.82):
    """PNG bytes for a wide panel with the house drawn in the middle of it.

    Not cached: this is drawn by the --brand command below when the artwork
    changes, not by anything a browser asks for."""
    return _encode(width, height, _wide_rows(width, height, tuple(bg), tuple(fg), scale))


def png(size=512, bg=BG, fg=FG):
    """PNG bytes for a square icon of the given size. Cached per size+colours."""
    bg, fg = tuple(bg), tuple(fg)
    key = (size, bg, fg)
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit

    body = _encode(size, size, _rows(size, bg, fg))

    with _lock:
        if len(_cache) >= MAX_CACHED:
            _cache.clear()
        _cache[key] = body
    return body


def warm(bg=BG, fg=FG):
    """Render the advertised sizes in a colour, off the request path.

    Drawing 512x512 with 2x2 supersampling is a few seconds of pure Python on a
    Pi. Called at startup for the default green, and again by the manifest
    request whenever a device asks for an accent not yet drawn - the manifest is
    always fetched before the icons it names, so this is usually finished by the
    time the icon itself is asked for.

    Returns at once; already-cached colours cost nothing."""
    bg, fg = tuple(bg), tuple(fg)

    def run():
        for size in SIZES:
            try:
                png(size, bg, fg)
            except Exception:
                pass          # a missing icon must never take the app down
    threading.Thread(target=run, daemon=True, name="icon-warm").start()


# ------------------------------------------------------------------- branding
#
# Home Assistant shows an add-on's icon.png and logo.png from the add-on's own
# folder. They have to be real files - Supervisor reads the folder, not the
# running app, so there is nothing for the server to serve them from.
#
# They are still drawn from the shapes above rather than kept as artwork: one
# drawing, every use, so a change to the house doesn't leave a stale version of
# it in the add-on store. Rerun `python3 icon.py --brand .` in this folder after
# any change to the shapes, and commit what it writes.

BRAND_ICON = 128        # what Home Assistant asks for: a square, small
BRAND_LOGO = (512, 256)  # the wide panel across the top of the add-on page


def write_brand(folder, bg=BG, fg=FG):
    """Write icon.png and logo.png into an add-on folder. Returns their paths."""
    import os
    icon_path = os.path.join(folder, "icon.png")
    logo_path = os.path.join(folder, "logo.png")
    with open(icon_path, "wb") as fh:
        fh.write(png(BRAND_ICON, bg, fg))
    with open(logo_path, "wb") as fh:
        fh.write(banner(BRAND_LOGO[0], BRAND_LOGO[1], bg, fg))
    return icon_path, logo_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--brand":
        folder = sys.argv[2] if len(sys.argv) > 2 else "."
        for path in write_brand(folder):
            sys.stderr.write("wrote %s\n" % path)
    else:
        size = int(sys.argv[1]) if len(sys.argv) > 1 else 512
        bg = parse_colour(sys.argv[2] if len(sys.argv) > 2 else "")
        fg = parse_colour(sys.argv[3] if len(sys.argv) > 3 else "", FG)
        sys.stdout.buffer.write(png(size, bg, fg))
