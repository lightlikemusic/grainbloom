# Grainbloom

A granular micro-loop and texture effect for Akai MPC standalone hardware, by Lightlike.

Grainbloom keeps the last 8 seconds of whatever plays through it and turns it into
grains: short slices it re-orders, reverses, pitches, scatters across the stereo field
and smears into reverb. Put it on a track or a send and play into it.

## Requirements

- MPC OS **3.10.1 or later**.
- External plugins enabled on the MPC: **Preferences → Enhancements (Beta)** → turn on
  **Enable Enhancements** and **External Plugin Support**.

## Install

Copy the folder `Lightlike - VST - Grainbloom` into a folder named exactly
`VST2 Plugins` at the top of an internal drive, SD card or USB drive, then restart the MPC.
It appears under effect plugins as **Grainbloom** by Lightlike.

## Modes

| Mode | What it does |
|---|---|
| **Collage** | Tempo-synced slices of the recent past, played back out of order, sometimes reversed or jumped an octave. |
| **Cloud** | Many short overlapping grains scattered in time and across the stereo field: pads and smears. |
| **Stutter** | One slice repeated on the beat with hard edges, re-grabbed every so often. |
| **Shimmer** | Like Cloud, but every grain is an octave up. Turn up Feedback and the octaves stack. |
| **Shatter** | Glitch. On each step a slice plays once, ratchets 2× or 4×, jumps an octave, reverses or drops out. Density: more ratchets, fewer gaps. Spread: further back, wilder pitch. |
| **Arpeggio** | One captured slice replayed as a stepped melody of fifths and octaves on the tempo grid, re-grabbed every cycle. Spread: range (2–8 notes; shuffled near the top). Density: note length. |
| **Cascade** | Multi-tap echo of slices: each step layers slices from 1–8 steps back, quieter each time and panned left/right. **Repeats**: number of echoes and how slowly they fade. Density: echo length. Spread: octave jumps on later taps. Feedback: echoes of the echoes (long tails). |

Shatter, Arpeggio and Cascade were added later; they sit after Shimmer in the list, so projects
saved with the first four modes load unchanged. (Automation recorded on Mode before the update
may land on a different mode, because the list got longer.) The modes are original designs
inspired by multi-mode granular pedals, not copies of any product's algorithms.

## Screen and Q-Links

Two tabs. **BLOOM** is built for the MPC One's four Q-Link knobs:

| Q-Link (top to bottom) | Control | What it does |
|---|---|---|
| 1 | **Grain** (0…100 %) | Grain size ×¼…×4 and density, around the preset |
| 2 | **Scatter** (0…100 %) | Spread, reverse chance, drift and stereo width |
| 3 | **Space** (0…100 %) | Feedback, reverb amount and reverb size |
| 4 | **Mix** (0…100 %) | Dry/wet |

Each built-in preset sets its own Grain, Scatter and Space positions, placed where that preset's
sound sits (long grains = high Grain, wide and reversed = high Scatter, big reverb and feedback =
high Space), so BLOOM changes with the preset. Turn a knob down to take away, up to add. The
positions are worked out by `scripts/place_macros.py`, which also adjusts the hidden settings
so the presets sound the same as before. (Internally they are still
stored as −100…+100, so projects and automation from earlier versions load unchanged.) Everything else (Mode, Pitch, filters, Hold...) comes from the preset.

BLOOM shows no knobs: four 3D-mesh pictures, one per Q-Link, left to right, each with its
value and a bar that fills left to right. Drag up or down on a picture to change it, tap it
to bank the Q-Links to it, double-tap to type a value.

**CONTROLS** has everything else, in three columns. On the MPC One each column is one bank of
Q-Links (top to bottom; the fourth knob is Repeats in the TIME column and unused elsewhere):

| SOUND | TIME | TONE |
|---|---|---|
| Mode | Hold | Low Cut |
| Reverb (type) | Sync | High Cut |
| Pitch | Division | Volume |
| | Repeats (only shown in Cascade) | |

Mode, Reverb and Division are choice fields (name above a box showing the current choice).
Turn the Q-Link or the data wheel to step through the choices; there is no pop-up list,
because the MPC's list opens empty for plugin settings. Tap any control to bank the knobs to
its column.

## Parameters

**Sound parameters** (set by presets; not on screen)


| Control | Range | What it does |
|---|---|---|
| Size | 10–1000 ms | Grain length (Cloud/Shimmer), or slice length in Collage/Stutter when Sync is off |
| Density | 0–100 % | Cloud/Shimmer: how many grains overlap. Collage: slice overlap. Stutter: gate length |
| Spread | 0–100 % | How far back in time grains come from. Stutter: chance of grabbing a new slice. Collage: also the chance of octave jumps |
| Pitch | −24…+24 st | Transposes every grain |
| Reverse | 0–100 % | Chance that a grain plays backwards |
| Drift | 0–50 ct | Random detune per grain, for a chorus-like width |
| Width | 0–100 % | Random left/right placement of grains |
| Feedback | 0–95 % | Feeds the wet signal back into the 8-second buffer |
| Mode | Collage / Cloud / Stutter / Shimmer / Shatter / Arpeggio / Cascade | Grain behaviour (see above) |
| Sync | Off / On | Collage and Stutter slices follow the MPC tempo |
| Division | 1/64 … 2/1 | Slice length when Sync is on |
| Hold | Off / On | Freezes the buffer: stops recording and keeps playing grains from what is captured |
| Repeats | 0–100 % | Cascade only: number of echoes (1–8) and how slowly they fade. Shown on CONTROLS only while Mode is Cascade |


| Control | Range | What it does |
|---|---|---|
| Low Cut | 20–2000 Hz | High-pass filter on the grains |
| High Cut | 500–18000 Hz | Low-pass filter on the grains |
| Rev Size | 0–100 % | Reverb time (decay) of the built-in reverb; the tail also darkens as it grows |
| Rev Amount | 0–100 % | How much reverb is added to the grains |
| Reverb | Room / Hall / Plate / Dark | Reverb voicing (reverb time at Rev Size 0 → 100 %). Room: small and close, 0.3–1.2 s. Hall: big, warm and chorused, 1–5 s. Plate: bright and dense, no pre-delay, 0.6–3.5 s. Dark: huge and muffled, 1.5–7 s |
| Mix | 0–100 % | Dry/wet balance |
| Volume | −24…+6 dB | Output level |

**Hidden**

| Control | What it does |
|---|---|
| ~Anim | Read-only animation clock for the screen's motion. Grainbloom advances it by itself (faster with density, almost still on Hold) and tells the MPC about each step. |
| ~core, ~petals, ~halo, ~echo, ~haze | Read-only after-macro values that drive the BLOOM picture. |

None of these are automatable or affect the sound.

## Built-in programs

Init Collage · Glass Cloud · Tape Stutter · Octave Bloom · Reverse Rain · Half Speed ·
Broken Sixteenths · Endless Pad

Shatter: Glass Shards · Data Storm (wild 1/32 chops) · Skip Beat (sparse 1/8 hits with gaps)

Arpeggio: Crystal Arp · Night Ladder (an octave down, long dark notes) · Glass Spiral
(1/16 triplets, wide shuffled range, plate)

Cascade: Falling Echoes · Ping Pong Steps (short tight 1/8 echoes) · Endless Stairs (dotted
1/4, many slow-fading repeats into a dark reverb)

## Tips

- On a send/return, set Mix to 100 %.
- Hold is great for freezing a chord into a pad: play it, press Hold, then move Size, Pitch and Spread.
- With Sync on, Collage and Stutter lock to the song position while the MPC is playing.
- Feedback above ~70 % in Shimmer builds up slowly. Pull Low Cut up if it gets muddy.

## What it does not do (yet)

- No looper with overdub/undo.
- No MIDI control of modes (effects receive no MIDI on the MPC); use Q-Links or automation instead.
- Hold only stops recording. It does not capture an exact loop length.

## Reverb

A dense, slowly chorused stereo reverb in the style of the classic early-80s digital studio
halls and plates: four input diffusers smear each grain before it enters a two-sided
"figure-eight" tank, whose two chorused allpasses keep its resonances moving so nothing rings
or flutters. Each type sets the tank size, pre-delay, input bandwidth, damping, a longer bass
decay and the chorus depth and rate. Rev Size changes the decay and damping only, never the
tank's delay lengths, so moving Space does not bend the tail's pitch.

It replaced a smaller 4-line reverb (Nov 2026) that sounded like a spring: few, separate
echoes. Saved projects keep their settings but sound different (smoother, a little longer).

## CPU

On a desktop CPU it uses well under 1 % of one core in the heaviest setting (Shimmer at full
density). On a 32-bit MPC (One, Live, X) expect a few percent per instance.

## Build

Grainbloom is built with the MPC Plugin SDK (MIT). Clone or copy this repository into the
SDK's `plugins/` folder as `plugins/Grainbloom`, then from the SDK root:

```
python tools/build.py plugins/Grainbloom
python tools/package.py plugins/Grainbloom
```

## Skin

The UI is a hand-made skin in `skins/` (the build copies it as-is; `ui.json` is no longer
used). To change it:

```
python3 plugins/Grainbloom/art/make_skin_art.py   # redraws every image in skins/
python3 plugins/Grainbloom/art/add_controls_tab.py   # rewrites both tabs and the Q-Link map
python3 tools/build.py plugins/Grainbloom
```

`skins/TUI.json` keeps the knob and overlay components the SDK generator wrote. The tabs
are written by `add_controls_tab.py`, which uses the BLOOM layout in `add_mesh_tab.py` and
the shared helpers in `add_bloom_tab.py`. The Mix picture (a double helix whose two
strands wind together as Mix goes up) is drawn by `art/make_mix_helix.py`; the original torus
version is kept in `art/backup_mesh/`, as is the original `bg_mesh.png` with its teal frame (removed Nov 2026). The other mesh pictures, `bg_mesh.png` and the bars
are not drawn by these scripts; `bg_controls.png` is made from `bg_mesh.png`, with the SOUND / TIME / TONE headers drawn in (fixed-text Labels do not show on the MPC). Note that
`add_mesh_tab.py` only adds its four picture components (`meshGrain`...) if they are
missing, so delete them from TUI.json first if you change them.

Animation on the MPC: an `Image` film strip with `"animated": true` does not move on the
hardware, and a parameter the plugin changes silently does not redraw either. What works
is a parameter the plugin advances itself **and** reports with `audioMasterAutomate`
(`notifyHostParameterChanged`), throttled to about 30 updates a second.

## Licence

MIT. All DSP is original to this project. The reverb's tank layout (delay lengths, output tap
positions, diffusion coefficients) follows the published paper: J. Dattorro, "Effect Design
Part 1: Reverberator and Other Filters", J. Audio Eng. Soc. 45(9), 1997; the code was written
from the paper. No code or data from any commercial reverb is used.
