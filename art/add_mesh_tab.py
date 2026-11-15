#!/usr/bin/env python3
"""Replace the BLOOM tab in ../skins/TUI.json with the 3D-mesh design.

Layout (tab area 1280 x 628), four columns Grain / Scatter / Space / Mix:
  - bg_mesh.png         full-tab background (wordmark, column names, border)
  - mesh_<name>.png     240 x 240 film strip, 48 frames, bound to the macro itself
  - <value label>       the parameter's own value text
  - bar_touch.png       the value bar (bar_uni.png, 210 x 4, fills left to right 0-100) on
                        a 254 x 60 transparent frame, 127 frames. It is a film-strip Knob
                        with dragOrientation "Horizontal" inside a touch component, so a
                        left/right swipe on the bar edits the value; the bigger frame gives
                        the finger room. Tap banks the Q-Links, double-tap opens the editor.
  - the mesh picture    a plain film strip in a touch component (tap / double-tap as above,
                        no dragging)

Reuses the helpers in add_bloom_tab.py (same entry/strip/label/touch code and the same
text-only TUI.json edit, so the MPC's duplicate "version" keys survive).
Q-Links.json is unchanged (same four parameters).
Run:  python3 plugins/Grainbloom/art/add_mesh_tab.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_bloom_tab as base  # noqa: E402

MESH_FRAMES = 48
BAR_FRAMES = 127
TILE_X = [23, 334, 645, 956]   # tile left edge, tile width 298
PIC = 240
COLUMNS = [  # (param, picture strip, bar strip, component name, value overlay)
    # All four use the plain 0-100 editor: Grain/Scatter/Space display as 0..100 (50 = preset).
    (base.GRAIN,   "mesh_grain.png",   "bar_uni.png", "meshGrain",   "knob overlay"),
    (base.SCATTER, "mesh_scatter.png", "bar_uni.png", "meshScatter", "knob overlay"),
    (base.SPACE,   "mesh_space.png",   "bar_uni.png", "meshSpace",   "knob overlay"),
    (base.MIX,     "mesh_mix.png",     "bar_uni.png", "meshMix",     "knob overlay"),
]


BAR_W, BAR_H = 210, 4            # bar_uni.png frame
TOUCH_W, TOUCH_H = 254, 60       # bar_touch.png frame (the swipe area)
BAR_IN_X, BAR_IN_Y = 22, 18      # where the bar sits inside it
BAR_Y = 518                      # bar's y on the tab


def mesh_definition(pic, overlay):
    """Touch component (tap = Q-Link, double-tap = editor) showing the mesh film strip.
    No dragging here: the value is swiped on the bar below (bar_definition)."""
    d = base.touch_definition(overlay)
    img = {"version": 2, "imageType": "FilmStrip", "colour": "0", "image": pic,
           "numFrames": MESH_FRAMES, "handleName": "Data"}
    d["componentsData"] = [base.entry("picture", "Image", img, "0 0 %d %d" % (PIC, PIC))]
    return d


def bar_definition(overlay):
    """Touch component holding the value bar as a film-strip Knob: swipe left/right to edit."""
    d = base.touch_definition(overlay)
    knob = {"version": 3, "knobType": "FilmStrip", "filmStrip": "bar_touch.png",
            "numFrames": BAR_FRAMES, "invert": False, "dragOrientation": "Horizontal",
            "handleName": "Data"}
    d["componentsData"] = [base.entry("knob", "Knob", knob, "0 0 %d %d" % (TOUCH_W, TOUCH_H))]
    return d


def make_bar_touch():
    """bar_touch.png: every bar_uni.png frame centred on a transparent TOUCH_W x TOUCH_H frame."""
    from PIL import Image
    src = Image.open(os.path.join(base.SKINS, "bar_uni.png")).convert("RGBA")
    out = Image.new("RGBA", (TOUCH_W, TOUCH_H * BAR_FRAMES), (0, 0, 0, 0))
    for f in range(BAR_FRAMES):
        frame = src.crop((0, f * BAR_H, BAR_W, (f + 1) * BAR_H))
        out.paste(frame, (BAR_IN_X, f * TOUCH_H + BAR_IN_Y))
    out.save(os.path.join(base.SKINS, "bar_touch.png"), optimize=True)


def remove_definition(t, name):
    """Remove the {"key": name, "value": {...}} item (and its trailing comma) from the text."""
    k = t.find('"key": "%s"' % name)
    if k < 0:
        return t
    start = t.rfind("{", 0, k)
    depth, i, in_str = 0, start, False
    while True:
        ch = t[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    end = i + 1
    rest = t[end:].lstrip()
    if rest.startswith(","):
        end = t.index(",", end) + 1
    line_start = t.rfind("\n", 0, start)
    return t[:line_start] + t[end:]


def add_definitions():
    """(Re)write the four mesh picture components so they always match COLUMNS."""
    import json
    path = os.path.join(base.SKINS, "TUI.json")
    t = open(path, encoding="utf-8").read()
    for _, pic, _, name, overlay in COLUMNS:
        for key_name, value in ((name, mesh_definition(pic, overlay)),
                                (name + "Bar", bar_definition(overlay))):
            t = remove_definition(t, key_name)
            key = '"localComponentDefinitions": ['
            i = t.index(key) + len(key)
            item = json.dumps({"key": key_name, "value": value}, indent=4)
            t = t[:i] + "\n" + base.indent(item, 16) + "," + t[i:]
    open(path, "w", encoding="utf-8").write(t)
VALUE_STYLE = base.text_style(40.0, "ffe9edf5", style="Light",
                              just="horizontallyCentred verticallyCentred")


def mesh_tab():
    comps = []
    for (param, pic, bar, name, _), x in zip(COLUMNS, TILE_X):
        pic_rect = "%d %d %d %d" % (x + 29, 166, PIC, PIC)
        comps.append(base.entry("mesh %d" % param, name, {"version": 1, "handleName": "Data"},
                                pic_rect, remap=[{"key": "Data", "value": "Parameter %d" % param}],
                                focus="Yes", show="Hide"))
        comps.append(base.label("value p%d" % param, "Value", param,
                                "%d %d 298 56" % (x, 456), VALUE_STYLE))
        comps.append(base.entry("bar %d" % param, name + "Bar", {"version": 1, "handleName": "Data"},
                                "%d %d %d %d" % (x + 44 - BAR_IN_X, BAR_Y - BAR_IN_Y, TOUCH_W, TOUCH_H),
                                remap=[{"key": "Data", "value": "Parameter %d" % param}],
                                focus="Yes", show="Hide"))
    bg = {"version": 1, "colour": "ff0b0c10", "image": "bg_mesh.png"}
    root = {"version": 2, "actions": [],
            "backgroundData": {"version": 1, "focussed": bg, "unfocussed": dict(bg)},
            "ignoreMousePresses": False, "disableCoarseDataWheel": False,
            "componentsData": comps}
    return {"version": 1, "tabName": "BLOOM", "fnKeyIndex": 0, "fnKeySubIndex": 0,
            "componentDefinition": root, "qlinkBoundsData": []}


if __name__ == "__main__":
    base.bloom_tab = mesh_tab   # update_tui() writes whatever bloom_tab() returns
    make_bar_touch()
    base.update_tui()
    add_definitions()
    print("3D-mesh BLOOM tab written")
