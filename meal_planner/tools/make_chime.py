"""Generates the built-in dinner chime, static/chime.wav.

Not part of the add-on: it runs once, the file it produces is committed, and
nothing is ever synthesised at runtime. The Dockerfile copies `*.py` from the
top of this folder, so tools/ never reaches the image - the same arrangement
tests/ has.

It is in the repository at all so the sound can be changed by somebody who
doesn't have the original. The alternative is a binary nobody can regenerate.

The sound is two strikes of a struck-metal bell. Struck metal is what makes it
carry across a kitchen: the partials are deliberately inharmonic - the ratios
below are roughly a tubular bell's, not a harmonic series - so it reads as a
bell rather than as a beep, and the high partials decay fastest, which is what
gives the strike its edge and the tail its hum.

Standard library only, same as everything else here.

Run: python3 tools/make_chime.py  (from the meal_planner folder)
"""

import math
import os
import struct
import wave

RATE = 22050
BITS = 32767

# Ratios to the fundamental, with how loud each starts and how fast it dies.
# The 2.76 and 5.43 are the inharmonic ones doing most of the work.
PARTIALS = [
    # ratio, amplitude, decay (bigger = shorter)
    (1.00, 1.00, 2.2),
    (2.00, 0.60, 3.0),
    (2.76, 0.45, 3.8),
    (4.07, 0.28, 5.0),
    (5.43, 0.18, 6.5),
    (8.10, 0.10, 9.0),
]

F0 = 587.33          # D5. High enough to cut through a kitchen, low enough not to nag.
STRIKES = (0.00, 0.62)
LENGTH = 2.6         # seconds, including the tail of the second strike
STRIKE_GAIN = (1.0, 0.85)


def sample(t):
    """One strike's worth of bell at time t, or silence before it is struck."""
    if t < 0:
        return 0.0
    total = 0.0
    for ratio, amp, decay in PARTIALS:
        total += amp * math.exp(-decay * t) * math.sin(2 * math.pi * F0 * ratio * t)
    # A very short attack ramp. Without it the waveform starts at full tilt and
    # the click that produces is audible on a good speaker.
    attack = min(1.0, t / 0.004)
    return total * attack


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(here, "static", "chime.wav")

    frames = []
    count = int(RATE * LENGTH)
    for i in range(count):
        t = i / RATE
        value = 0.0
        for start, gain in zip(STRIKES, STRIKE_GAIN):
            value += gain * sample(t - start)
        # Fade the last tenth of a second to nothing, so the file doesn't end on
        # a discontinuity that some players click on.
        tail = (count - i) / (RATE * 0.1)
        if tail < 1.0:
            value *= tail
        value = max(-1.0, min(1.0, value / 2.4))
        frames.append(struct.pack("<h", int(value * BITS)))

    with wave.open(out, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(b"".join(frames))

    print("wrote %s (%.0f kB)" % (out, os.path.getsize(out) / 1024.0))


if __name__ == "__main__":
    main()
