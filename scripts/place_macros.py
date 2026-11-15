#!/usr/bin/env python3
"""Give every built-in preset its own Grain / Scatter / Space knob positions (BLOOM tab),
without changing how the preset sounds.

The macros bend a group of hidden settings around their stored values (see process() in
src/Grainbloom.cpp). This script, for each addProgram(...) line:
  1. works out the preset's effective sound (stored values + current macro positions),
  2. places each macro where that sound sits on its range
       Grain   <- grain length (log scale) and density
       Scatter <- spread, reverse chance, drift, stereo width
       Space   <- feedback, reverb amount, reverb size
  3. rewrites the stored values so stored + new macro = the same effective sound.
If a compensated value would fall outside its range, the macro is moved toward the middle
until it fits. Safe to run again. Run from the repository root:
    python3 plugins/Grainbloom/scripts/place_macros.py
"""
import math
import os
import re

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "Grainbloom.cpp")

# Value positions in an addProgram list (parameter order in src/Grainbloom.cpp).
SIZE, DENS, SPREAD, REVERSE, DRIFT, FB, REVSIZE, REVAMT, WIDTH = 2, 3, 4, 6, 7, 10, 13, 14, 17
GRAIN, SCATTER, SPACE = 19, 20, 21

clamp = lambda v, lo, hi: max(lo, min(hi, v))


def effective(v):
    g, sc, sp = v[GRAIN] / 100, v[SCATTER] / 100, v[SPACE] / 100
    return {
        "size": clamp(v[SIZE] * 4 ** g, 10, 1000),
        "dens": clamp(v[DENS] / 100 + 0.4 * g, 0, 1),
        "spread": clamp(v[SPREAD] / 100 + 0.5 * sc, 0, 1),
        "rev": clamp(v[REVERSE] / 100 + 0.4 * sc, 0, 1),
        "drift": clamp(v[DRIFT] + 25 * sc, 0, 50),
        "width": clamp(v[WIDTH] / 100 + 0.4 * sc, 0, 1),
        "fb": clamp(v[FB] / 100 + 0.45 * sp, 0, 0.95),
        "ramt": clamp(v[REVAMT] / 100 + 0.5 * sp, 0, 1),
        "rsize": clamp(v[REVSIZE] / 100 + 0.4 * sp, 0, 1),
    }


def place(target, inverse):
    """Largest |m| from target toward 0 whose compensated stored values are all in range."""
    m = clamp(target, -0.9, 0.9)
    step = 0.05 if m > 0 else -0.05
    while abs(m) > 1e-9:
        stored = inverse(m)
        if stored is not None:
            return m, stored
        m -= step
        if (step > 0 and m < 0) or (step < 0 and m > 0):
            break
    return 0.0, inverse(0.0)


def in_range(pairs):
    return all(lo - 1e-6 <= val <= hi + 1e-6 for val, lo, hi in pairs)


def convert(values):
    v = [float(x) for x in values]
    e = effective(v)

    # Grain
    t = 0.6 * math.log(e["size"] / 10) / math.log(100) + 0.4 * e["dens"]
    def inv_g(m):
        size, dens = e["size"] / 4 ** m, (e["dens"] - 0.4 * m) * 100
        return (size, dens) if in_range([(size, 10, 1000), (dens, 0, 100)]) else None
    mg, (size, dens) = place(2 * t - 1, inv_g)

    # Scatter
    t = (e["spread"] + e["rev"] + e["drift"] / 50 + e["width"]) / 4
    def inv_s(m):
        spread, rev = (e["spread"] - 0.5 * m) * 100, (e["rev"] - 0.4 * m) * 100
        drift, width = e["drift"] - 25 * m, (e["width"] - 0.4 * m) * 100
        ok = in_range([(spread, 0, 100), (rev, 0, 100), (drift, 0, 50), (width, 0, 100)])
        return (spread, rev, drift, width) if ok else None
    ms, (spread, rev, drift, width) = place(2 * t - 1, inv_s)

    # Space
    t = (e["fb"] / 0.95 + e["ramt"] + e["rsize"]) / 3
    def inv_p(m):
        fb, ramt, rsize = (e["fb"] - 0.45 * m) * 100, (e["ramt"] - 0.5 * m) * 100, (e["rsize"] - 0.4 * m) * 100
        return (fb, ramt, rsize) if in_range([(fb, 0, 95), (ramt, 0, 100), (rsize, 0, 100)]) else None
    mp, (fb, ramt, rsize) = place(2 * t - 1, inv_p)

    out = {SIZE: size, DENS: dens, SPREAD: spread, REVERSE: rev, DRIFT: drift, WIDTH: width,
           FB: fb, REVAMT: ramt, REVSIZE: rsize,
           GRAIN: round(mg * 100), SCATTER: round(ms * 100), SPACE: round(mp * 100)}
    # Re-derive the stored values for the rounded macros so the sound stays exact.
    v2 = list(v)
    for k, val in out.items():
        v2[k] = val
    for k in (GRAIN, SCATTER, SPACE):
        v2[k] = out[k]
    g, sc, sp = v2[GRAIN] / 100, v2[SCATTER] / 100, v2[SPACE] / 100
    v2[SIZE] = e["size"] / 4 ** g
    v2[DENS] = (e["dens"] - 0.4 * g) * 100
    v2[SPREAD] = (e["spread"] - 0.5 * sc) * 100
    v2[REVERSE] = (e["rev"] - 0.4 * sc) * 100
    v2[DRIFT] = e["drift"] - 25 * sc
    v2[WIDTH] = (e["width"] - 0.4 * sc) * 100
    v2[FB] = (e["fb"] - 0.45 * sp) * 100
    v2[REVAMT] = (e["ramt"] - 0.5 * sp) * 100
    v2[REVSIZE] = (e["rsize"] - 0.4 * sp) * 100
    for k, lo, hi in ((SIZE, 10, 1000), (DENS, 0, 100), (SPREAD, 0, 100), (REVERSE, 0, 100),
                      (DRIFT, 0, 50), (WIDTH, 0, 100), (FB, 0, 95), (REVAMT, 0, 100), (REVSIZE, 0, 100)):
        v2[k] = clamp(v2[k], lo, hi)
    drift_check = effective(v2)
    worst = max(abs(drift_check[k] - e[k]) / (1000 if k == "size" else (50 if k == "drift" else 1))
                for k in e)
    return v2, worst


def fmt(x):
    x = round(x, 1)
    return ("%d" % x) if x == int(x) else ("%.1f" % x)


def main():
    s = open(SRC, encoding="utf-8").read()
    pat = re.compile(r'(addProgram\("([^"]+)",\s*\{)([^}]*)(\}\);)')

    def repl(m):
        tokens = m.group(3).split(",")
        plain = [re.sub(r"/\*.*?\*/", "", t).strip() for t in tokens]
        nums = {}
        for i in (SIZE, DENS, SPREAD, REVERSE, DRIFT, FB, REVSIZE, REVAMT, WIDTH, GRAIN, SCATTER, SPACE):
            nums[i] = float(plain[i])
        full = [0.0] * len(plain)
        for i, val in nums.items():
            full[i] = val
        new, worst = convert(full)
        for i in nums:
            lead = re.match(r"\s*", tokens[i]).group(0)
            tokens[i] = lead + fmt(new[i])
        print("%-18s Grain %4d  Scatter %4d  Space %4d   (on screen %d / %d / %d %%; sound change %.4f)"
              % (m.group(2), new[GRAIN], new[SCATTER], new[SPACE],
                 (new[GRAIN] + 100) / 2, (new[SCATTER] + 100) / 2, (new[SPACE] + 100) / 2, worst))
        return m.group(1) + ",".join(tokens) + m.group(4)

    s = pat.sub(repl, s)
    open(SRC, "w", encoding="utf-8").write(s)


if __name__ == "__main__":
    main()
