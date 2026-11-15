#!/usr/bin/env python3
"""Render Grainbloom's custom skin artwork into ../skins/.

Run from anywhere:  python3 plugins/Grainbloom/art/make_skin_art.py
Needs Pillow. Everything is drawn procedurally with a fixed seed, so the output is
reproducible. Image sizes and frame counts must match what TUI.json expects:
  knob_uni.png / knob_bi.png   90 x 90 per frame, 127 frames stacked vertically
  fader_h_uni.png              248 x 36 per frame, 127 frames
  toggle_on/off.png            64 x 32
  seg4_on/off.png              58 x 40
  bg_grains.png / bg_space.png 1280 x 628 (a tab's content area)
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "skins")

# Palette ("cosmic bloom")
BG_TOP = (13, 10, 31)
BG_BOTTOM = (34, 14, 48)
PINK = (255, 110, 199)
CYAN = (94, 231, 255)
LAVENDER = (182, 156, 255)
INK = (24, 18, 44)

SS = 4  # supersampling factor for smooth edges

FONT_FILES = [
    "/System/Library/Fonts/Avenir Next.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
]


def font(size, index=0):
    for f in FONT_FILES:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size, index=index)
            except OSError:
                continue
    return ImageFont.load_default()


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(len(a)))


def gradient_colour(t):
    """Pink -> lavender -> cyan along t in 0..1."""
    if t < 0.5:
        return lerp(PINK, LAVENDER, t * 2.0)
    return lerp(LAVENDER, CYAN, (t - 0.5) * 2.0)


def glow(layer, radius):
    """Return layer composited with a blurred copy of itself (a soft glow)."""
    blurred = layer.filter(ImageFilter.GaussianBlur(radius))
    out = Image.alpha_composite(blurred, blurred)
    return Image.alpha_composite(out, layer)


# ---------------------------------------------------------------------------
# Knobs
# ---------------------------------------------------------------------------
def knob_frame(value, bipolar, size=90):
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = s / 2
    r_outer = s * 0.44
    r_track = s * 0.40
    r_body = s * 0.30
    width = int(s * 0.055)
    start, end = 135.0, 405.0  # PIL angles: 0 = 3 o'clock, clockwise; 270 deg sweep

    # Body: dark disc with a soft rim
    d.ellipse([c - r_body, c - r_body, c + r_body, c + r_body], fill=INK + (255,), outline=(70, 55, 110, 255), width=int(SS * 1.5))
    # Inner sheen
    d.ellipse([c - r_body * 0.82, c - r_body * 0.82, c + r_body * 0.82, c + r_body * 0.82], fill=(30, 23, 56, 255))

    # Track
    box = [c - r_track, c - r_track, c + r_track, c + r_track]
    d.arc(box, start, end, fill=(255, 255, 255, 38), width=width)

    # Value arc on its own layer so it can glow
    arc = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ad = ImageDraw.Draw(arc)
    if bipolar:
        mid = (start + end) / 2.0
        a0, a1 = sorted((mid, start + (end - start) * value))
    else:
        a0, a1 = start, start + (end - start) * value
    if a1 - a0 > 0.5:
        steps = max(2, int((a1 - a0) / 3))
        for k in range(steps):
            t0 = a0 + (a1 - a0) * k / steps
            t1 = a0 + (a1 - a0) * (k + 1) / steps + 0.6
            tt = ((t0 - start) / (end - start))
            ad.arc(box, t0, t1, fill=gradient_colour(tt) + (255,), width=width)
    arc = glow(arc, SS * 3)
    img = Image.alpha_composite(img, arc)
    d = ImageDraw.Draw(img)

    # Pointer: a glowing "grain" dot on the body edge
    ang = math.radians(start + (end - start) * value)
    pr = r_body * 0.68
    px, py = c + math.cos(ang) * pr, c + math.sin(ang) * pr
    dot = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dot)
    rr = s * 0.045
    col = gradient_colour(value)
    dd.ellipse([px - rr, py - rr, px + rr, py + rr], fill=col + (255,))
    dot = glow(dot, SS * 2)
    img = Image.alpha_composite(img, dot)
    d = ImageDraw.Draw(img)
    d.ellipse([px - rr * 0.45, py - rr * 0.45, px + rr * 0.45, py + rr * 0.45], fill=(255, 255, 255, 230))

    # Faint outer ring
    d.ellipse([c - r_outer - width * 0.6, c - r_outer - width * 0.6, c + r_outer + width * 0.6, c + r_outer + width * 0.6],
              outline=(255, 255, 255, 14), width=int(SS))
    return img.resize((size, size), Image.LANCZOS)


def film_strip(frames):
    w, h = frames[0].size
    strip = Image.new("RGBA", (w, h * len(frames)), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.paste(f, (0, i * h))
    return strip


# ---------------------------------------------------------------------------
# Fader (horizontal, unipolar)
# ---------------------------------------------------------------------------
def fader_frame(value, w=248, h=36):
    W, H = w * SS, h * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = H / 2
    th = H * 0.22
    x0, x1 = W * 0.04, W * 0.96
    d.rounded_rectangle([x0, cy - th / 2, x1, cy + th / 2], radius=th / 2, fill=(255, 255, 255, 34))
    xv = x0 + (x1 - x0) * value
    fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fill)
    if xv - x0 > th:
        steps = 48
        for k in range(steps):
            a = x0 + (xv - x0) * k / steps
            b = x0 + (xv - x0) * (k + 1) / steps + 1
            fd.rectangle([a, cy - th / 2, b, cy + th / 2], fill=gradient_colour((a - x0) / (x1 - x0)) + (255,))
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle([x0, cy - th / 2, xv, cy + th / 2], radius=th / 2, fill=255)
        fill.putalpha(Image.composite(fill.getchannel("A"), mask, mask))
    fill = glow(fill, SS * 3)
    img = Image.alpha_composite(img, fill)
    d = ImageDraw.Draw(img)
    # Handle: a glowing grain
    hr = H * 0.3
    hx = min(max(xv, x0 + hr), x1 - hr)
    handle = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hd = ImageDraw.Draw(handle)
    hd.ellipse([hx - hr, cy - hr, hx + hr, cy + hr], fill=gradient_colour(value) + (255,))
    handle = glow(handle, SS * 2)
    img = Image.alpha_composite(img, handle)
    d = ImageDraw.Draw(img)
    d.ellipse([hx - hr * 0.55, cy - hr * 0.55, hx + hr * 0.55, cy + hr * 0.55], fill=INK + (255,))
    d.ellipse([hx - hr * 0.25, cy - hr * 0.25, hx + hr * 0.25, cy + hr * 0.25], fill=(255, 255, 255, 235))
    return img.resize((w, h), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Toggle and segment buttons
# ---------------------------------------------------------------------------
def toggle(on, w=64, h=32):
    W, H = w * SS, h * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = SS * 2
    box = [pad, pad, W - pad, H - pad]
    if on:
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        for x in range(int(box[0]), int(box[2])):
            t = (x - box[0]) / (box[2] - box[0])
            gd.line([x, box[1], x, box[3]], fill=gradient_colour(t * 0.6) + (255,))
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).rounded_rectangle(box, radius=(H - 2 * pad) / 2, fill=255)
        g.putalpha(m)
        img = Image.alpha_composite(img, glow(g, SS * 2))
        d = ImageDraw.Draw(img)
        r = (H - 2 * pad) / 2 - SS * 2
        cx = box[2] - (H - 2 * pad) / 2
    else:
        d.rounded_rectangle(box, radius=(H - 2 * pad) / 2, fill=(255, 255, 255, 26), outline=(182, 156, 255, 90), width=SS)
        r = (H - 2 * pad) / 2 - SS * 2
        cx = box[0] + (H - 2 * pad) / 2
    cy = H / 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 240) if on else (120, 105, 160, 255))
    return img.resize((w, h), Image.LANCZOS)


def segment(on, w=58, h=40):
    W, H = w * SS, h * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = SS * 2
    box = [pad, pad, W - pad, H - pad]
    rad = SS * 7
    if on:
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        for y in range(int(box[1]), int(box[3])):
            t = (y - box[1]) / (box[3] - box[1])
            gd.line([box[0], y, box[2], y], fill=lerp(PINK, LAVENDER, t) + (255,))
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).rounded_rectangle(box, radius=rad, fill=255)
        g.putalpha(m)
        img = Image.alpha_composite(img, glow(g, SS * 2))
    else:
        d.rounded_rectangle(box, radius=rad, fill=(255, 255, 255, 22), outline=(182, 156, 255, 80), width=SS)
    return img.resize((w, h), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Page backgrounds
# ---------------------------------------------------------------------------
# Q-Link columns (x, width) from the generated qlinkBoundsData, and the slot grid rows.
COLUMNS = [(38, 248), (358, 248), (678, 248), (998, 248)]
ROW_Y = [45, 196, 346, 497]
ROW_H = 107


def background(name, used_rows_per_column, seed):
    W, H = 1280, 628
    rnd = random.Random(seed)
    img = Image.new("RGBA", (W, H), BG_TOP + (255,))
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([0, y, W, y], fill=lerp(BG_TOP, BG_BOTTOM, y / (H - 1)) + (255,))

    # Nebula blooms: big soft colour clouds
    neb = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    nd = ImageDraw.Draw(neb)
    for col, cx, cy, r, a in [(PINK, 1080, 560, 330, 70), (CYAN, 160, 120, 260, 40),
                              (LAVENDER, 640, 360, 420, 35), (PINK, 300, 600, 220, 40)]:
        nd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (a,))
    neb = neb.filter(ImageFilter.GaussianBlur(120))
    img = Image.alpha_composite(img, neb)

    # Bloom rings (concentric, very faint) around the wordmark area
    rings = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rings)
    for k in range(7):
        r = 90 + k * 46
        rd.ellipse([1060 - r, 560 - r, 1060 + r, 560 + r], outline=LAVENDER + (int(26 - k * 3),), width=2)
    img = Image.alpha_composite(img, rings)

    # Grain field: drifting particles, denser toward the bloom
    grains = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grains)
    for _ in range(900):
        if rnd.random() < 0.45:
            ang = rnd.random() * math.tau
            dist = abs(rnd.gauss(0, 260))
            x, y = 1060 + math.cos(ang) * dist, 560 + math.sin(ang) * dist * 0.75
        else:
            x, y = rnd.random() * W, rnd.random() * H
        if not (0 <= x < W and 0 <= y < H):
            continue
        r = rnd.choice([0.6, 0.8, 1.0, 1.2, 1.6, 2.2])
        col = gradient_colour(rnd.random())
        a = int(rnd.uniform(40, 170))
        gd.ellipse([x - r, y - r, x + r, y + r], fill=col + (a,))
    img = Image.alpha_composite(img, glow(grains, 2))

    # Glass panels behind each Q-Link column (only over the rows that hold controls)
    panels = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panels)
    for (x, w), rows in zip(COLUMNS, used_rows_per_column):
        if rows <= 0:
            continue
        y0 = ROW_Y[0] - 14
        y1 = ROW_Y[rows - 1] + ROW_H + 14
        pd.rounded_rectangle([x, y0, x + w, y1], radius=18, fill=(255, 255, 255, 13), outline=(182, 156, 255, 46), width=1)
        # thin accent line on top of each panel
        pd.line([x + 24, y0 + 1, x + w - 24, y0 + 1], fill=PINK + (110,), width=2)
    img = Image.alpha_composite(img, panels)

    # Wordmark, bottom left, in the empty lower area
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(text)
    big = font(64, index=0)
    small = font(18, index=0)
    title = "GRAINBLOOM"
    tx, ty = 46, 520
    # letter-spaced title with a gradient across letters
    x = tx
    for i, ch in enumerate(title):
        col = gradient_colour(i / (len(title) - 1))
        td.text((x, ty), ch, font=big, fill=col + (235,))
        x += td.textlength(ch, font=big) + 6
    td.text((tx + 4, ty - 26), "L I G H T L I K E", font=small, fill=(200, 190, 235, 170))
    td.text((x + 18, ty + 34), name, font=small, fill=(200, 190, 235, 120))
    img = Image.alpha_composite(img, glow(text, 6))
    return img.convert("RGB")


# ---------------------------------------------------------------------------
# BLOOM tab: layered picture of the current settings
# ---------------------------------------------------------------------------
# Every layer is a square transparent frame (BLOOM_PX) that the MPC scales up to the
# stage bounds in TUI.json. Soft, glowing art survives the upscale; keep frames small
# so the film strips stay light on memory.
BLOOM_PX = 256
BLOOM_FRAMES = 24


def _layer():
    s = BLOOM_PX * SS
    return Image.new("RGBA", (s, s), (0, 0, 0, 0)), s


def _finish(img, blur=0):
    if blur:
        img = glow(img, blur)
    return img.resize((BLOOM_PX, BLOOM_PX), Image.LANCZOS)


def bloom_core(v):
    """Size: the glowing heart of the bloom."""
    img, s = _layer()
    d = ImageDraw.Draw(img)
    c = s / 2
    r = s * (0.045 + 0.085 * v)
    for k in range(6, 0, -1):
        rr = r * (1 + k * 0.22)
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=lerp(PINK, LAVENDER, k / 6) + (int(26 + 8 * (6 - k)),))
    d.ellipse([c - r, c - r, c + r, c + r], fill=(255, 196, 232, 255))
    ri = r * 0.55
    d.ellipse([c - ri, c - ri, c + ri, c + ri], fill=(255, 245, 252, 255))
    return _finish(img, SS * 4)


def bloom_petals(v):
    """Density: number of petals, 3 .. 16."""
    img, s = _layer()
    c = s / 2
    n = 3 + int(round(13 * v))
    petal_len = s * 0.30
    petal_w = s * (0.11 - 0.045 * v)
    for i in range(n):
        ang = i * 360.0 / n
        p = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        pd = ImageDraw.Draw(p)
        col = gradient_colour(i / max(1, n - 1))
        pd.ellipse([c - petal_w / 2, c - petal_len - s * 0.05, c + petal_w / 2, c - s * 0.05], fill=col + (150,))
        pd.ellipse([c - petal_w / 5, c - petal_len * 0.9 - s * 0.05, c + petal_w / 5, c - s * 0.1], fill=(255, 255, 255, 70))
        p = p.rotate(-ang, resample=Image.BICUBIC, center=(c, c))
        img = Image.alpha_composite(img, p)
    return _finish(img, SS * 3)


def bloom_spread(v):
    """Spread: a halo of grains that scatters wider."""
    img, s = _layer()
    d = ImageDraw.Draw(img)
    c = s / 2
    rnd = random.Random(1234)
    radius = s * (0.25 + 0.13 * v)
    jitter = s * (0.008 + 0.045 * v)
    count = 70 + int(90 * v)
    for i in range(count):
        ang = rnd.random() * math.tau
        rr = radius + rnd.gauss(0, 1) * jitter
        x, y = c + math.cos(ang) * rr, c + math.sin(ang) * rr
        g = rnd.choice([1.0, 1.4, 1.8, 2.4]) * SS
        d.ellipse([x - g, y - g, x + g, y + g], fill=gradient_colour(rnd.random()) + (int(rnd.uniform(120, 240)),))
    return _finish(img, SS * 2)


def bloom_echo(v):
    """Feedback: 0 .. 6 echo rings rippling outward."""
    img, s = _layer()
    d = ImageDraw.Draw(img)
    c = s / 2
    rings = int(round(6 * v))
    for k in range(rings):
        rr = s * (0.36 + k * 0.022)
        a = int(150 - k * 18)
        d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=lerp(LAVENDER, CYAN, k / 6) + (max(30, a),), width=int(SS * 1.5))
    return _finish(img, SS * 2)


def bloom_haze(v):
    """Rev Amount: a soft cloud of light behind everything."""
    img, s = _layer()
    d = ImageDraw.Draw(img)
    c = s / 2
    rr = s * (0.22 + 0.10 * v)
    d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=LAVENDER + (int(10 + 110 * v),))
    img = img.filter(ImageFilter.GaussianBlur(s * 0.05))
    return img.resize((BLOOM_PX, BLOOM_PX), Image.LANCZOS)


def bloom_pitch(v):
    """Pitch (-24..+24 st, centre = 0): a comet on an orbit, at the top when 0."""
    img, s = _layer()
    d = ImageDraw.Draw(img)
    c = s / 2
    orbit = s * 0.47
    # faint orbit track
    d.arc([c - orbit, c - orbit, c + orbit, c + orbit], 135, 405, fill=(255, 255, 255, 30), width=int(SS))
    # -24 at 7:30, 0 at 12:00, +24 at 4:30 (PIL angles: 0 = 3 o'clock, clockwise)
    ang = math.radians(135 + 270 * v)
    tail = 10
    for k in range(tail, -1, -1):
        a = ang - math.radians(k * (2.2 if v >= 0.5 else -2.2))
        x, y = c + math.cos(a) * orbit, c + math.sin(a) * orbit
        r = SS * (4.5 - 0.35 * k)
        col = CYAN if v > 0.5 else (PINK if v < 0.5 else (255, 255, 255))
        d.ellipse([x - r, y - r, x + r, y + r], fill=col + (int(255 * (1 - k / (tail + 1))),))
    return _finish(img, SS * 2)


def bloom_twinkle(i, n):
    """Looping sparkle (animated by the MPC, not tied to a setting)."""
    img, s = _layer()
    d = ImageDraw.Draw(img)
    c = s / 2
    rnd = random.Random(99)
    for k in range(26):
        ang = rnd.random() * math.tau
        rr = s * rnd.uniform(0.18, 0.49)
        x, y = c + math.cos(ang) * rr, c + math.sin(ang) * rr
        phase = rnd.random()
        a = 0.5 + 0.5 * math.cos(math.tau * (i / n + phase))
        a = a ** 3
        g = SS * rnd.uniform(1.2, 2.6) * (0.6 + 0.6 * a)
        d.ellipse([x - g, y - g, x + g, y + g], fill=(255, 255, 255, int(230 * a)))
    return _finish(img, SS * 2)


MOTION_FRAMES = 48


def bloom_motion(i, n=MOTION_FRAMES):
    """One frame of the looping motion layer, driven by the plugin's ~Anim clock.

    Seamless loop: every ring's pattern repeats k times around the circle and the
    ring turns exactly 360/k degrees per loop, so frame n == frame 0.
    """
    img, s = _layer()
    c = s / 2
    t = i / n

    # Breathing aura
    aura = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ad = ImageDraw.Draw(aura)
    breathe = 0.5 - 0.5 * math.cos(math.tau * t)
    ar = s * (0.20 + 0.04 * breathe)
    ad.ellipse([c - ar, c - ar, c + ar, c + ar], fill=PINK + (int(12 + 30 * breathe),))
    aura = aura.filter(ImageFilter.GaussianBlur(s * 0.05))
    img = Image.alpha_composite(img, aura)

    # Orbiting grain rings: (radius, repeats, grains per repeat, direction, seed)
    d = ImageDraw.Draw(img)
    for radius, k, per, direction, seed in ((0.44, 6, 4, 1, 1), (0.40, 4, 5, -1, 2), (0.47, 3, 6, 1, 3)):
        rnd = random.Random(seed)
        pattern = [(rnd.random(), rnd.uniform(1.0, 2.6), rnd.random(), rnd.uniform(-0.012, 0.012)) for _ in range(per)]
        turn = direction * t * math.tau / k
        for rep in range(k):
            for off, size, hue, dr in pattern:
                a = (rep + off) * math.tau / k + turn
                rr = s * (radius + dr)
                x, y = c + math.cos(a) * rr, c + math.sin(a) * rr
                g = SS * size
                d.ellipse([x - g, y - g, x + g, y + g], fill=gradient_colour(hue) + (200,))
    img = glow(img, SS * 2)

    # Twinkles on top (already loop over the same n)
    tw = bloom_twinkle(i, n).resize((s, s), Image.LANCZOS)
    img = Image.alpha_composite(img, tw)
    return img.resize((BLOOM_PX, BLOOM_PX), Image.LANCZOS)


def mode_emblem(mode):
    """Static backdrop per mode: Collage tiles, Cloud haze, Stutter bars, Shimmer sparks."""
    img, s = _layer()
    d = ImageDraw.Draw(img)
    c = s / 2
    rnd = random.Random(40 + mode)
    if mode == 0:  # Collage: a ring of tiles
        for ring, count in ((0.40, 22), (0.31, 16)):
            for i in range(count):
                a = math.tau * i / count + ring
                x, y = c + math.cos(a) * s * ring, c + math.sin(a) * s * ring
                h = s * 0.018
                t = Image.new("RGBA", (s, s), (0, 0, 0, 0))
                ImageDraw.Draw(t).rectangle([x - h, y - h, x + h, y + h], fill=gradient_colour(rnd.random()) + (90,))
                img = Image.alpha_composite(img, t.rotate(rnd.uniform(-20, 20), center=(x, y)))
    elif mode == 1:  # Cloud: soft blobs
        for _ in range(14):
            a = rnd.random() * math.tau
            rr = s * rnd.uniform(0.15, 0.40)
            x, y = c + math.cos(a) * rr, c + math.sin(a) * rr
            g = s * rnd.uniform(0.06, 0.12)
            d.ellipse([x - g, y - g, x + g, y + g], fill=gradient_colour(rnd.random()) + (50,))
        img = img.filter(ImageFilter.GaussianBlur(s * 0.03))
    elif mode == 2:  # Stutter: radial bars like a gated clock
        for i in range(32):
            a = math.tau * i / 32
            on = (i // 2) % 2 == 0
            r0, r1 = s * 0.33, s * (0.43 if on else 0.38)
            d.line([c + math.cos(a) * r0, c + math.sin(a) * r0, c + math.cos(a) * r1, c + math.sin(a) * r1],
                   fill=gradient_colour(i / 31) + (130 if on else 60,), width=int(SS * 3))
    else:  # Shimmer: upward sparks
        for _ in range(40):
            x = c + rnd.gauss(0, s * 0.18)
            y = c + rnd.uniform(-s * 0.42, s * 0.30)
            ln = s * rnd.uniform(0.02, 0.06)
            d.line([x, y, x, y - ln], fill=lerp(LAVENDER, CYAN, rnd.random()) + (int(rnd.uniform(70, 170)),), width=int(SS * 1.5))
            d.ellipse([x - SS * 1.5, y - ln - SS * 1.5, x + SS * 1.5, y - ln + SS * 1.5], fill=(255, 255, 255, 160))
    return _finish(img, SS * 3)


def mix_blend(v):
    """Mix: a crisp 'dry' ring and a glowing 'wet' bloom that slide together and merge."""
    img, s = _layer()
    c = s / 2
    r = s * 0.19
    off = s * 0.11 * (1.0 - v)
    # wet: glowing filled bloom, brighter with Mix
    wet = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wet)
    wx = c + off
    for k in range(5, 0, -1):
        rr = r * (1 + k * 0.22)
        wd.ellipse([wx - rr, c - rr, wx + rr, c + rr], fill=lerp(PINK, LAVENDER, k / 5) + (int((14 + 10 * (5 - k)) * (0.1 + 0.9 * v)),))
    wd.ellipse([wx - r, c - r, wx + r, c + r], fill=PINK + (int(35 + 220 * v),))
    wet = glow(wet, SS * 5)
    img = Image.alpha_composite(img, wet)
    # dry: a clean outline ring that fades as Mix goes up
    d = ImageDraw.Draw(img)
    dx = c - off
    a = int(235 * (1.0 - 0.75 * v))
    d.ellipse([dx - r, c - r, dx + r, c + r], outline=(225, 235, 255, a), width=int(SS * 2.2))
    # a few droplets travelling from dry to wet
    rnd = random.Random(5)
    for k in range(9):
        t = (k + 0.5) / 9
        x = dx + (wx - dx) * t
        y = c + math.sin(t * math.pi * 2 + k) * r * 0.5
        g = SS * (1.2 + 1.6 * rnd.random())
        d.ellipse([x - g, y - g, x + g, y + g], fill=gradient_colour(t) + (int(60 + 160 * v * (1 - abs(0.5 - t))),))
    return _finish(img, SS * 2)


def bloom_background():
    """BLOOM tab background: nebula, grain field and a small wordmark under the stage."""
    W, H = 1280, 628
    rnd = random.Random(3)
    img = Image.new("RGBA", (W, H), BG_TOP + (255,))
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([0, y, W, y], fill=lerp(BG_TOP, BG_BOTTOM, y / (H - 1)) + (255,))
    neb = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    nd = ImageDraw.Draw(neb)
    for col, cx, cy, r, a in [(LAVENDER, 640, 260, 420, 55), (PINK, 1000, 560, 260, 45), (CYAN, 240, 120, 240, 35)]:
        nd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (a,))
    img = Image.alpha_composite(img, neb.filter(ImageFilter.GaussianBlur(120)))
    grains = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grains)
    for _ in range(600):
        x, y = rnd.random() * W, rnd.random() * H
        r = rnd.choice([0.6, 0.8, 1.0, 1.3, 1.8])
        gd.ellipse([x - r, y - r, x + r, y + r], fill=gradient_colour(rnd.random()) + (int(rnd.uniform(30, 140)),))
    img = Image.alpha_composite(img, glow(grains, 2))
    # One continuous background (no per-column cards): the pictures and knobs float on it.
    # Wordmark centred along the top
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(text)
    big = font(30)
    small = font(12)
    title = "GRAINBLOOM"
    widths = [td.textlength(ch, font=big) + 5 for ch in title]
    sub = "L I G H T L I K E"
    sub_w = td.textlength(sub, font=small)
    total = sum(widths) + 18 + sub_w
    x = (W - total) / 2
    for i, ch in enumerate(title):
        td.text((x, 16), ch, font=big, fill=gradient_colour(i / (len(title) - 1)) + (230,))
        x += widths[i]
    td.text((x + 18, 31), sub, font=small, fill=(200, 190, 235, 150))
    img = Image.alpha_composite(img, glow(text, 5))
    return img.convert("RGB")


def main():
    os.makedirs(OUT, exist_ok=True)
    nb = BLOOM_FRAMES
    film_strip([bloom_haze(i / (nb - 1)) for i in range(nb)]).save(os.path.join(OUT, "bloom_haze.png"), optimize=True)
    film_strip([bloom_echo(i / (nb - 1)) for i in range(nb)]).save(os.path.join(OUT, "bloom_echo.png"), optimize=True)
    film_strip([bloom_spread(i / (nb - 1)) for i in range(nb)]).save(os.path.join(OUT, "bloom_spread.png"), optimize=True)
    film_strip([bloom_petals(i / (nb - 1)) for i in range(nb)]).save(os.path.join(OUT, "bloom_petals.png"), optimize=True)
    film_strip([bloom_core(i / (nb - 1)) for i in range(nb)]).save(os.path.join(OUT, "bloom_core.png"), optimize=True)
    film_strip([mix_blend(i / (nb - 1)) for i in range(nb)]).save(os.path.join(OUT, "bloom_mix.png"), optimize=True)
    film_strip([bloom_motion(i) for i in range(MOTION_FRAMES)]).save(os.path.join(OUT, "bloom_motion.png"), optimize=True)
    # Retired layers (pitch comet, mode emblems, old twinkle): remove so they are not shipped.
    for old in ["bloom_twinkle.png", "bloom_pitch.png"] + ["mode_%s.png" % m for m in ("mosaic", "cloud", "stutter", "shimmer")]:
        if os.path.exists(os.path.join(OUT, old)):
            os.remove(os.path.join(OUT, old))
    bloom_background().save(os.path.join(OUT, "bg_bloom.png"), optimize=True)
    n = 127
    film_strip([knob_frame(i / (n - 1), False) for i in range(n)]).save(os.path.join(OUT, "knob_uni.png"), optimize=True)
    film_strip([knob_frame(i / (n - 1), True) for i in range(n)]).save(os.path.join(OUT, "knob_bi.png"), optimize=True)
    film_strip([fader_frame(i / (n - 1)) for i in range(n)]).save(os.path.join(OUT, "fader_h_uni.png"), optimize=True)
    toggle(True).save(os.path.join(OUT, "toggle_on.png"))
    toggle(False).save(os.path.join(OUT, "toggle_off.png"))
    segment(True).save(os.path.join(OUT, "seg4_on.png"))
    segment(False).save(os.path.join(OUT, "seg4_off.png"))
    # The GRAINS and SPACE pages were retired (BLOOM-only skin); drop their old backgrounds.
    for old in ("bg_grains.png", "bg_space.png"):
        if os.path.exists(os.path.join(OUT, old)):
            os.remove(os.path.join(OUT, old))
    print("wrote art to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
