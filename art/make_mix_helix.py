#!/usr/bin/env python3
"""Draw ../skins/mesh_mix.png: the Mix picture as two strands that wind into a double helix.

Film strip, 240 x 240 frames, 48 frames stacked vertically, frame 0 = Mix 0 %.
  Mix 0 %   two separate, gently waving vertical strands: crisp white "dry" on the left,
            magenta "wet" on the right
  rising    the strands move together, twist around each other in 3D and base-pair rungs
            fade in between them; the dry strand takes on the wet colour
  Mix 100 % one glowing magenta double helix

Same look as the other mesh pictures: thin wireframe lines, small square nodes, soft glow,
depth shading (the far side of the helix is dimmer). Drawn 3x oversized, then reduced.
Run:  python3 plugins/Grainbloom/art/make_mix_helix.py
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "skins", "mesh_mix.png")

SIZE = 240
FRAMES = 48           # must match MESH_FRAMES in add_mesh_tab.py
SS = 3                # supersampling
S = SIZE * SS

DRY = (226, 246, 255)
WET = (255, 92, 204)
NODES = 22            # nodes per strand
TURNS = 1.6           # helix turns over the full height when fully mixed


def lerp(a, b, t):
    return a + (b - a) * t


def mix_col(c1, c2, t):
    return tuple(int(round(lerp(x, y, t))) for x, y in zip(c1, c2))


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def strand_points(v, side):
    """3D points (x, y, z) of one strand. side = 0 (dry) or 1 (wet)."""
    sep = 0.24 * (1.0 - smooth(v))              # half distance between the strand axes
    radius = lerp(0.03, 0.15, smooth(v))       # helix radius grows as they wind together
    turns = lerp(0.55, TURNS, smooth(v))
    spin = v * math.pi * 0.9                    # turns a little as Mix moves
    phase = spin + (math.pi if side else 0.0)
    axis = -sep if side == 0 else sep
    pts = []
    for i in range(NODES):
        u = i / (NODES - 1)
        y = lerp(-0.35, 0.35, u)
        a = phase + u * turns * 2 * math.pi
        pts.append((axis + radius * math.cos(a), y, radius * math.sin(a)))
    return pts


def project(p):
    x, y, z = p
    persp = 1.0 / (1.0 - 0.55 * z)              # nearer = slightly bigger
    return (S / 2 + x * S * persp, S / 2 + y * S * persp), z


def depth_alpha(z, lo=0.30):
    return lerp(lo, 1.0, max(0.0, min(1.0, (z + 0.17) / 0.34)))


def draw_frame(v):
    sharp = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ds, dg = ImageDraw.Draw(sharp), ImageDraw.Draw(glow)

    strands = [strand_points(v, 0), strand_points(v, 1)]
    colours = [mix_col(DRY, WET, smooth(v) ** 1.4), WET]
    wet_glow = lerp(0.35, 1.0, v)

    # Collect everything with a depth so the far side is drawn first.
    items = []   # (z, kind, data)
    for s, pts in enumerate(strands):
        proj = [project(p) for p in pts]
        for i in range(len(proj) - 1):
            (a, za), (b, zb) = proj[i], proj[i + 1]
            items.append(((za + zb) / 2, "seg", (a, b, colours[s], 1.0 if s == 0 else wet_glow, s)))
            # A second, offset rail makes each strand read as a thin ribbon, like the mesh.
            off = 0.012 * S
            items.append(((za + zb) / 2 - 0.01, "seg",
                          ((a[0] + off, a[1] + off * 0.4), (b[0] + off, b[1] + off * 0.4),
                           colours[s], 0.45, s)))
        for (pt, z) in proj:
            items.append((z, "node", (pt, colours[s], s)))
    # Base-pair rungs: fade in with Mix, every other node, with a node in the middle.
    rung = smooth((v - 0.15) / 0.6)
    if rung > 0:
        for i in range(0, NODES, 2):
            (a, za), (b, zb) = project(strands[0][i]), project(strands[1][i])
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            c = mix_col(colours[0], WET, 0.5)
            items.append(((za + zb) / 2 - 0.02, "rung", (a, b, mid, c, rung)))

    items.sort(key=lambda it: it[0])
    for z, kind, d in items:
        al = depth_alpha(z)
        if kind == "seg":
            a, b, col, strength, s = d
            alpha = int(255 * al * strength)
            ds.line([a, b], fill=col + (alpha,), width=SS)
            if s == 1 or v > 0.5:
                dg.line([a, b], fill=WET + (int(alpha * (wet_glow if s else v)),), width=7 * SS)
        elif kind == "node":
            pt, col, s = d
            r = 1.3 * SS * (0.8 + 0.4 * al)
            ds.rectangle([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r], fill=col + (int(255 * al),))
            if s == 1:
                dg.ellipse([pt[0] - 3 * r, pt[1] - 3 * r, pt[0] + 3 * r, pt[1] + 3 * r],
                           fill=WET + (int(80 * al * wet_glow),))
        else:
            a, b, mid, col, k = d
            alpha = int(200 * al * k)
            ds.line([a, b], fill=col + (alpha,), width=SS)
            r = 1.0 * SS
            ds.rectangle([mid[0] - r, mid[1] - r, mid[0] + r, mid[1] + r], fill=(255, 255, 255, int(alpha * 0.8)))
            dg.line([a, b], fill=WET + (int(alpha * 0.5),), width=5 * SS)

    # Overall wet aura that swells with Mix.
    aura = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(aura).ellipse([S * 0.28, S * 0.12, S * 0.72, S * 0.88],
                                 fill=WET + (int(70 * v ** 1.5),))
    aura = aura.filter(ImageFilter.GaussianBlur(28 * SS))
    glow = glow.filter(ImageFilter.GaussianBlur(6 * SS))

    frame = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    frame.alpha_composite(aura)
    frame.alpha_composite(glow)
    frame.alpha_composite(sharp)
    return frame.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    strip = Image.new("RGBA", (SIZE, SIZE * FRAMES), (0, 0, 0, 0))
    for f in range(FRAMES):
        strip.paste(draw_frame(f / (FRAMES - 1)), (0, f * SIZE))
    strip.save(OUT, optimize=True)
    print("wrote", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
