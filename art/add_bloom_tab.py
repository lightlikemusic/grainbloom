#!/usr/bin/env python3
"""Make ../skins/TUI.json a single BLOOM tab with four macro knobs, and write the
matching ../skins/Q-Links.json for the MPC One's four Q-Links.

Layout (tab area 1280 x 628): four columns, Grain / Scatter / Space / Mix, left to right
(= the MPC One's Q-Links top to bottom). Each column has a picture that follows its knob
(film strips bound to the plugin's after-macro values) above the knob itself.

TUI.json keeps the generator's componentDefinitions (knob slots, overlays). Those
contain duplicate "version" keys that the MPC needs, so this script edits the text and
never round-trips the whole file through a JSON library.
Run after make_skin_art.py:  python3 plugins/Grainbloom/art/add_bloom_tab.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SKINS = os.path.join(HERE, "..", "skins")

# Parameter indices (must match src/Grainbloom.cpp)
(VOLUME, MODE, SIZE, DENSITY, SPREAD, PITCH, REVERSE, DRIFT, SYNC, DIVISION, FEEDBACK,
 LOWCUT, HIGHCUT, REVSIZE, REVAMOUNT, MIX, HOLD, WIDTH, ANIM,
 GRAIN, SCATTER, SPACE,
 SHOW_CORE, SHOW_PETALS, SHOW_HALO, SHOW_ECHO, SHOW_HAZE) = range(27)

BLOOM_FRAMES = 24     # must match make_skin_art.py
MOTION_FRAMES = 48    # must match make_skin_art.py

# Four columns, one per Q-Link (left to right = the MPC One's knobs top to bottom).
# Each column: a picture (PICTURE px square) above its knob slot (the SDK's 278 x 107 slot).
COLUMN_X = [23, 343, 663, 983]          # knob slot x; column centre = x + 139
PICTURE = 310
PICTURE_Y = 190          # centred in the space under the wordmark
# (param, knob component, picture layers bottom-to-top as (file, frames, bound param))
COLUMNS = [
    (GRAIN, "knobBi", [("bloom_motion.png", MOTION_FRAMES, ANIM),
                       ("bloom_petals.png", BLOOM_FRAMES, SHOW_PETALS),
                       ("bloom_core.png", BLOOM_FRAMES, SHOW_CORE)]),
    (SCATTER, "knobBi", [("bloom_motion.png", MOTION_FRAMES, ANIM),
                         ("bloom_spread.png", BLOOM_FRAMES, SHOW_HALO)]),
    (SPACE, "knobBi", [("bloom_haze.png", BLOOM_FRAMES, SHOW_HAZE),
                       ("bloom_motion.png", MOTION_FRAMES, ANIM),
                       ("bloom_echo.png", BLOOM_FRAMES, SHOW_ECHO)]),
    (MIX, "knobUni", [("bloom_motion.png", MOTION_FRAMES, ANIM),
                      ("bloom_mix.png", BLOOM_FRAMES, MIX)]),
]


def bounds(rect, focus="No", hide_unless=None, show="Show"):
    b = {"version": 2 if hide_unless else 1, "acceptsHWFocus": focus, "showWhenDataModelInvalid": show,
         "whenVisible": "Always", "boundsType": "Absolute", "bounds": rect}
    if hide_unless:
        b["additionalInvalidatingHandles"] = [hide_unless]
    return b


def entry(name, wtype, data, rect, remap=None, **kw):
    return {"version": 2,
            "componentData": {"version": 1, "name": name, "type": wtype, "data": data},
            "handle remapping": {"version": 1, "map": remap or []},
            "bounds": bounds(rect, **kw)}


def image(name, file, rect, hide_unless=None):
    return entry(name, "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": file},
                 rect, hide_unless=hide_unless)


def strip(name, file, frames, param, rect):
    return entry(name, "Image", {"version": 2, "imageType": "FilmStrip", "colour": "0", "image": file,
                                 "numFrames": frames, "handleName": "Parameter %d" % param}, rect)


def text_style(height, colour, style="Regular", just="left verticallyCentred", case="Original"):
    return {"version": 1, "font": {"version": 1, "name": "Titillium Web", "style": style, "height": height},
            "colour": colour, "justification": just, "case": case}


def label(name, kind, param, rect, style):
    return entry(name, "Label", {"version": 1, "textStyle": style, "type": kind,
                                 "handleName": "Parameter %d" % param}, rect)


# No knobs on screen: each picture is an invisible touch area instead. A tap banks the
# Q-Links to that control; a double tap (or Enter) opens the MPC's value editor.
TOUCH_DEFS = {"touchUni": "knob overlay", "touchBi": "knob overlay bipolar"}


def touch_definition(overlay):
    clear = {"version": 1, "colour": "0", "image": ""}
    return {"version": 2,
            "actions": [
                {"version": 1, "onAction": "Mouse Down", "handler": "Q-Link", "handleName": "Data", "additionalData": ""},
                {"version": 1, "onAction": "Double Click", "handler": "Show Overlay", "handleName": "Data", "additionalData": overlay},
                {"version": 1, "onAction": "Enter Pressed", "handler": "Show Overlay", "handleName": "Data", "additionalData": overlay}],
            "backgroundData": {"version": 1, "focussed": clear, "unfocussed": dict(clear)},
            "ignoreMousePresses": False, "disableCoarseDataWheel": False,
            "componentsData": []}


def touch_area(param, kind, rect):
    return entry("touch %d" % param, kind, {"version": 1, "handleName": "Data"}, rect,
                 remap=[{"key": "Data", "value": "Parameter %d" % param}], focus="Yes", show="Hide")


def bloom_tab():
    comps = []
    for (param, kind, layers), x in zip(COLUMNS, COLUMN_X):
        cx = x + 139
        rect = "%d %d %d %d" % (cx - PICTURE // 2, PICTURE_Y, PICTURE, PICTURE)
        for f, frames, bound in layers:
            # bloom_motion.png is bound to ~Anim: it moves by itself because the plugin advances
            # ~Anim and notifies the MPC (the firmware ignores "animated": true).
            comps.append(strip("%s p%d" % (f, param), f, frames, bound, rect))
        comps.append(touch_area(param, "touchUni" if kind == "knobUni" else "touchBi", rect))
    bg = {"version": 1, "colour": "ff120d24", "image": "bg_bloom.png"}
    root = {"version": 2, "actions": [],
            "backgroundData": {"version": 1, "focussed": bg, "unfocussed": dict(bg)},
            "ignoreMousePresses": False, "disableCoarseDataWheel": False,
            "componentsData": comps}
    # No Q-Link highlight: there is no knob row to frame.
    return {"version": 1, "tabName": "BLOOM", "fnKeyIndex": 0, "fnKeySubIndex": 0,
            "componentDefinition": root, "qlinkBoundsData": []}


def indent(text, spaces):
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.splitlines())


def array_span(t, start):
    """Index just past the ']' matching the '[' at t[start], skipping JSON strings."""
    depth, i, in_str = 0, start, False
    while i < len(t):
        ch = t[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced tabs array")


def update_tui():
    path = os.path.join(SKINS, "TUI.json")
    t = open(path, encoding="utf-8").read()
    key = '"tabs": '
    a = t.index(key) + len(key)
    b = array_span(t, a)
    tabs = "[\n" + indent(json.dumps(bloom_tab(), indent=4), 12) + "\n        ]"
    t = t[:a] + tabs + t[b:]
    # Add the touch-area component definitions once.
    for name, overlay in TOUCH_DEFS.items():
        if '"key": "%s"' % name in t:
            continue
        key = '"localComponentDefinitions": ['
        i = t.index(key) + len(key)
        item = json.dumps({"key": name, "value": touch_definition(overlay)}, indent=4)
        t = t[:i] + "\n" + indent(item, 16) + "," + t[i:]
    open(path, "w", encoding="utf-8").write(t)


def update_qlinks():
    # Physical knobs on a 16-knob MPC: 13 14 15 16 / 9 10 11 12 / 5 6 7 8 / 1 2 3 4.
    # The MPC One has one column of four, which banks the first column: 13, 9, 5, 1.
    screen = {"Q-Link %d" % i: -1 for i in range(1, 17)}
    for (p, _, _), ql in zip(COLUMNS, (13, 9, 5, 1)):
        screen["Q-Link %d" % ql] = p
    program = {"Q-Link %d" % i: -1 for i in range(1, 17)}
    for (p, _, _), ql in zip(COLUMNS, (1, 2, 3, 4)):
        program["Q-Link %d" % ql] = p
    q = {"version": 4,
         "info": {"version": 1, "type": "CompleteDescription"},
         "Screen Mode Q-Links": {"version": 4, "map": [
             {"Tab": 1, "SubTab": 1, "Bank Direction": "Column", "Q-Links": screen}]},
         "Program Mode Q-Links": program}
    path = os.path.join(SKINS, "Q-Links.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(q, f, indent=4)
        f.write("\n")


if __name__ == "__main__":
    update_tui()
    update_qlinks()
    print("BLOOM-only skin written")
