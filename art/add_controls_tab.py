#!/usr/bin/env python3
"""Write both tabs of ../skins/TUI.json (BLOOM mesh tab + CONTROLS tab) and the Q-Link map.

CONTROLS tab (tab area 1280 x 628): three columns, one Q-Link bank each (the MPC One's
four knobs, top to bottom; the fourth knob is unused on this tab):

    SOUND          TIME           TONE
    Mode           Hold           Low Cut
    Reverb         Sync           High Cut
    Pitch          Division       Volume
                   Repeats        (Repeats only while Mode = Cascade)

Mode, Reverb and Division are "choiceText", styled like the MPC's own choice fields: a grey
capitalised name, and below it a rounded dark box (choice_box.png) with the current choice in
green; a red outline (choice_focus.png) shows while it is selected. Tap banks the Q-Links;
the Q-Link / data wheel step through the choices. There is no double-tap list: the MPC's
MenuOverlay opened empty (one blank row) for these plugin parameters on an MPC One running
3.10.1, both with the shared "Data" overlay and with one bound to "Parameter N" directly. Tap banks the Q-Links, double-tap / Enter opens the
MPC's choice list, and the Q-Link / data wheel step through the choices. The rest use the SDK kit components already in TUI.json
(toggle, knobBi, knobUni). Also makes bg_controls.png from bg_mesh.png: same frame, the BLOOM
column names replaced by SOUND / TIME / TONE drawn in matching spaced capitals (fixed-text
Labels did not show on the MPC, so the headers are part of the image, as on BLOOM).

The choice list ("menu overlay") is set to take hardware focus and to have a transparent
background, as in the SDK's complete example (docs/ui-reference.md section 9); with the
generator's settings (no focus, opaque background) the list opened empty on an MPC One.

Run after add_mesh_tab.py's helpers exist (it imports them; it does not need to be run first):
    python3 plugins/Grainbloom/art/add_controls_tab.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_bloom_tab as base  # noqa: E402
import add_mesh_tab as mesh   # noqa: E402

REVTYPE = 27   # must match kRevType in src/Grainbloom.cpp
REPEATS = 28   # kRepeats
CASCADE = 6    # index of Cascade in the Mode list
NUM_MODES = 7

COL_X = [60, 380, 700]          # slot left edges (slot 278 x 107); all left of the Q-Link sidebar
ROW_Y = [108, 223, 338, 453]   # four rows; the 4th is only used by Repeats
HEADER_Y = 60
CYAN = "ff40d6ea"
COLUMNS = [  # (header, [(param, component)] top to bottom)
    ("SOUND", [(base.MODE, "choiceText %d" % base.MODE), (REVTYPE, "choiceText %d" % REVTYPE), (base.PITCH, "knobBi")]),
    ("TIME",  [(base.HOLD, "toggle"), (base.SYNC, "toggle"), (base.DIVISION, "choiceText %d" % base.DIVISION),
               (REPEATS, "knobUni")]),   # Repeats: shown only while Mode = Cascade (see VISIBLE)
    ("TONE",  [(base.LOWCUT, "knobUni"), (base.HIGHCUT, "knobUni"), (base.VOLUME, "knobUni")]),
]
# Controls that only appear for one choice of another parameter: param -> (choice, of, handle)
VISIBLE = {REPEATS: "IndexedEnabling/%d/%d/Parameter %d" % (CASCADE, NUM_MODES, base.MODE)}
HEADER_STYLE = base.text_style(30.0, "ffe9edf5", style="SemiBold",
                               just="horizontallyCentred verticallyCentred", case="Upper Case")
# Choice names for parameters the skin did not list yet (must match the plugin's choices).
REPLACEMENTS = {REVTYPE: ["Room", "Hall", "Plate", "Dark"],
                base.MODE: ["Collage", "Cloud", "Stutter", "Shimmer", "Shatter", "Arpeggio", "Cascade"]}


def fixed_text(name, text, rect, style):
    return base.entry(name, "Label", {"version": 1, "textStyle": style, "type": "Text",
                                      "handleName": "Invalid", "text": text}, rect)


def slot(param, comp, x, y):
    hide = VISIBLE.get(param)
    return base.entry("%s %d" % (comp, param), comp, {"version": 1, "handleName": "Data"},
                      "%d %d 278 107" % (x, y),
                      remap=[{"key": "Data", "value": "Parameter %d" % param}], focus="Yes",
                      hide_unless=hide, show="Hide" if hide else "Show")


def controls_tab():
    comps = []
    for (_, controls), x in zip(COLUMNS, COL_X):   # headers are drawn into bg_controls.png
        for (param, comp), y in zip(controls, ROW_Y):
            comps.append(slot(param, comp, x, y))
    bg = {"version": 1, "colour": "ff0b0c10", "image": "bg_controls.png"}
    root = {"version": 2, "actions": [],
            "backgroundData": {"version": 1, "focussed": bg, "unfocussed": dict(bg)},
            "ignoreMousePresses": False, "disableCoarseDataWheel": False,
            "componentsData": comps}
    bounds = ["%d %d 298 %d" % (x - 10, ROW_Y[0] - 10, ROW_Y[-1] + 107 + 10 - (ROW_Y[0] - 10))
              for x in COL_X]
    return {"version": 1, "tabName": "CONTROLS", "fnKeyIndex": 1, "fnKeySubIndex": 0,
            "componentDefinition": root, "qlinkBoundsData": bounds}


BOX = (15, 44, 248, 58)     # choice box inside the 278 x 107 slot


def choice_text_definition(param):
    """278 x 107 slot: grey capitalised name, then a rounded box with the choice in green.
    Tap banks the Q-Links; no overlay (see the module docstring)."""
    def act(on, handler, extra="", handle="Data"):
        return {"version": 1, "onAction": on, "handler": handler, "handleName": handle,
                "additionalData": extra}
    clear = {"version": 1, "colour": "0", "image": ""}
    x, y, w, h = BOX
    box = "%d %d %d %d" % BOX
    focus = base.image("focus", "choice_focus.png", box)
    focus["bounds"]["whenVisible"] = "WhenFocussed"
    name = base.text_style(28.0, "ff8e8e94", style="Bold",
                           just="horizontallyCentred verticallyCentred", case="Upper Case")
    value = base.text_style(34.0, "ff6fe07c", just="horizontallyCentred verticallyCentred")
    return {"version": 2,
            "actions": [act("Mouse Down", "Q-Link")],
            "backgroundData": {"version": 1, "focussed": clear, "unfocussed": dict(clear)},
            "ignoreMousePresses": False, "disableCoarseDataWheel": False,
            "componentsData": [
                base.entry("name", "Label", {"version": 1, "textStyle": name, "type": "Name",
                                             "handleName": "Data"}, "15 2 248 40"),
                base.image("box", "choice_box.png", box),
                focus,
                base.entry("value", "Label", {"version": 1, "textStyle": value, "type": "Value",
                                              "handleName": "Data"}, "%d %d %d %d" % (x + 10, y, w - 20, h)),
            ]}


def make_choice_art():
    """choice_box.png: dark rounded field; choice_focus.png: red outline drawn around it."""
    from PIL import Image, ImageDraw
    ss, (_, _, w, h) = 4, BOX
    def draw(fn, paint):
        im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        paint(ImageDraw.Draw(im))
        im.resize((w, h), Image.LANCZOS).save(os.path.join(base.SKINS, fn), optimize=True)
    inset = 5
    draw("choice_box.png", lambda d: d.rounded_rectangle(
        [inset * ss, inset * ss, (w - inset) * ss, (h - inset) * ss], radius=8 * ss,
        fill=(58, 57, 63, 255), outline=(40, 40, 45, 255), width=ss))
    draw("choice_focus.png", lambda d: d.rounded_rectangle(
        [ss, ss, (w - 1) * ss, (h - 1) * ss], radius=11 * ss,
        outline=(214, 44, 74, 255), width=int(1.6 * ss)))


def fix_menu_overlay(t):
    """In the "menu overlay" definition: transparent background, list takes hardware focus.
    Text edit only (the MenuOverlay data has duplicate "version" keys the MPC needs)."""
    k = t.index('"key": "menu overlay"')
    end = t.index('"key": ', k + 10) if '"key": ' in t[k + 10:] else len(t)
    seg = t[k:end]
    seg = seg.replace('"colour": "ff120d24"', '"colour": "0"')
    seg = seg.replace('"acceptsHWFocus": "No"', '"acceptsHWFocus": "Yes"')
    return t[:k] + seg + t[end:]


def add_skin_entries():
    """Add Reverb's choice names, fix the choice list overlay, remove the old custom dropdown."""
    path = os.path.join(base.SKINS, "TUI.json")
    t = open(path, encoding="utf-8").read()
    t = mesh.remove_definition(t, "dropdown")
    t = fix_menu_overlay(t)
    t = mesh.remove_definition(t, "choiceText")
    for _, controls in COLUMNS:
        for param, comp in controls:
            if not comp.startswith("choiceText"):
                continue
            t = mesh.remove_definition(t, "menu overlay %d" % param)   # from the earlier attempt
            for name, item in ((comp, json.dumps({"key": comp, "value": choice_text_definition(param)}, indent=4)),):
                t = mesh.remove_definition(t, name)
                key = '"localComponentDefinitions": ['
                i = t.index(key) + len(key)
                t = t[:i] + "\n" + base.indent(item, 16) + "," + t[i:]
    for param, names in REPLACEMENTS.items():
        t = mesh.remove_definition(t, "Parameter %d" % param)
        key = '"replacementStrings": ['
        i = t.index(key) + len(key)
        item = json.dumps({"key": "Parameter %d" % param, "value": names}, indent=4)
        t = t[:i] + "\n" + base.indent(item, 12) + "," + t[i:]
    open(path, "w", encoding="utf-8").write(t)


HEADER_FONT = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
HEADER_CAP = 18        # capital height in px, measured from BLOOM's "GRAIN" in bg_mesh.png
HEADER_TRACK = 0.26    # extra space after each letter, in ems (GRAIN measures 93 px wide)
HEADER_CY = 96         # vertical centre of the BLOOM column names
HEADER_RGB = (233, 237, 245)


def draw_headers(im):
    """Draw the column names into the background, in the same spaced capitals as BLOOM's
    (bg_mesh.png has those baked in; the MPC does not draw fixed-text Labels in this skin)."""
    from PIL import Image, ImageDraw, ImageFont
    ss = 4
    probe = ImageFont.truetype(HEADER_FONT, 100)
    cap = probe.getbbox("H")
    size = 100.0 * HEADER_CAP / (cap[3] - cap[1])
    font = ImageFont.truetype(HEADER_FONT, int(round(size * ss)))
    track = HEADER_TRACK * size * ss
    layer = Image.new("RGBA", (im.width * ss, im.height * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    top = font.getbbox("H")[1]
    for (header, _), x in zip(COLUMNS, COL_X):
        widths = [d.textlength(ch, font=font) for ch in header]
        total = sum(widths) + track * (len(header) - 1)
        cx, y = (x + 139) * ss, (HEADER_CY - HEADER_CAP / 2.0) * ss - top
        pos = cx - total / 2.0
        for ch, w in zip(header, widths):
            d.text((pos, y), ch, font=font, fill=HEADER_RGB + (255,))
            pos += w + track
    layer = layer.resize(im.size, Image.LANCZOS)
    out = im.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


PANEL_ALPHA = 0.03       # each column's panel: white at 3 % opacity
PANEL_TOP, PANEL_BOTTOM = 68, 566   # header to below the 4th row, inside the frame (50..575)
PANEL_PAD, PANEL_RADIUS = 10, 14    # same 10 px margin as the Q-Link focus rectangle


def draw_panels(im):
    """A very faint rounded white panel behind each column (header included)."""
    from PIL import Image, ImageDraw
    ss = 4
    layer = Image.new("RGBA", (im.width * ss, im.height * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(round(255 * PANEL_ALPHA))
    for x in COL_X:
        d.rounded_rectangle([(x - PANEL_PAD) * ss, PANEL_TOP * ss,
                             (x + 278 + PANEL_PAD) * ss, PANEL_BOTTOM * ss],
                            radius=PANEL_RADIUS * ss, fill=(255, 255, 255, a))
    layer = layer.resize(im.size, Image.LANCZOS)
    out = im.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def make_background():
    from PIL import Image
    im = Image.open(os.path.join(base.SKINS, "bg_mesh.png")).convert("RGB")
    # Cover the BLOOM column names (y ~70-125) with the empty band just below them.
    band = im.crop((20, 130, 1260, 185))
    im.paste(band, (20, 70))
    im = draw_panels(im)
    im = draw_headers(im)
    im.save(os.path.join(base.SKINS, "bg_controls.png"), optimize=True)


def write_tabs():
    path = os.path.join(base.SKINS, "TUI.json")
    t = open(path, encoding="utf-8").read()
    key = '"tabs": '
    a = t.index(key) + len(key)
    b = base.array_span(t, a)
    tabs = ",\n".join(base.indent(json.dumps(tab, indent=4), 12)
                      for tab in (mesh.mesh_tab(), controls_tab()))
    t = t[:a] + "[\n" + tabs + "\n        ]" + t[b:]
    open(path, "w", encoding="utf-8").write(t)


def write_qlinks():
    path = os.path.join(base.SKINS, "Q-Links.json")
    q = json.load(open(path, encoding="utf-8"))
    screen = {"Q-Link %d" % i: -1 for i in range(1, 17)}
    for c, (_, controls) in enumerate(COLUMNS):
        for r, (param, _) in enumerate(controls):
            screen["Q-Link %d" % (13 + c - 4 * r)] = param
    q["Screen Mode Q-Links"]["map"] = [m for m in q["Screen Mode Q-Links"]["map"] if m["Tab"] == 1]
    q["Screen Mode Q-Links"]["map"].append(
        {"Tab": 2, "SubTab": 1, "Bank Direction": "Column", "Q-Links": screen})
    # Program mode: the four macros first (as before), then everything on this tab.
    order = [base.GRAIN, base.SCATTER, base.SPACE, base.MIX] + \
            [p for _, controls in COLUMNS for p, _ in controls]
    q["Program Mode Q-Links"] = {"Q-Link %d" % (i + 1): (order[i] if i < len(order) else -1)
                                 for i in range(16)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(q, f, indent=4)
        f.write("\n")


if __name__ == "__main__":
    make_background()
    make_choice_art()
    mesh.make_bar_touch()
    old = os.path.join(base.SKINS, "dropdown_box.png")
    if os.path.exists(old):
        os.remove(old)
    write_tabs()
    add_skin_entries()
    mesh.add_definitions()
    write_qlinks()
    print("BLOOM + CONTROLS tabs written")
