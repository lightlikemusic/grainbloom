// Grainbloom - a granular micro-loop / texture effect for the MPC, by Lightlike.
//
// SPDX-License-Identifier: MIT
//
// Signal flow
// -----------
//   in ─┬───────────────────────────────────────────────────────────────┐ (dry)
//       └─(+ feedback)─► capture buffer (8 s, stereo; paused while Hold) │
//                            │                                          │
//                            ▼                                          │
//                     grain scheduler (Mode) ─► up to 32 grains         │
//                            │  each grain: start point, length,        │
//                            │  speed (pitch, reverse), pan, window     │
//                            ▼                                          │
//                     grain sum ─► Low Cut ─► High Cut ─┬─► feedback ───┘ (back into the buffer)
//                                                       ▼
//                                              + lush chorused plate/hall reverb (Room / Hall / Plate / Dark)
//                                                       ▼
//   out = (dry · (1 − Mix) + wet · Mix) · Volume
//
// Modes (how the scheduler picks grains)
//   Mosaic  – tempo-synced slices of the recent past, re-ordered, sometimes
//             reversed or jumped an octave. Spread = how far back it looks.
//   Cloud   – many short overlapping grains scattered in time and stereo.
//             Density = how many overlap; Spread = how far back they scatter.
//   Stutter – one slice repeated on the beat with hard edges, re-grabbed now
//             and then. Density = gate length; Spread = chance of a new slice.
//   Shimmer – like Cloud, but every grain is an octave up; with Feedback the
//             octaves stack into a rising wash.
//   Shatter – glitch: on each step a slice plays once, ratchets 2x or 4x, jumps
//             an octave, reverses or drops out. Density = more ratchets and fewer
//             drop-outs; Spread = how far back and how wild.
//   Arpeggio – one captured slice replayed as a stepped melody (root, fifths,
//             octaves) on the tempo grid, re-grabbed every cycle. Spread = range
//             (and random order near the top); Density = note length.
//   Cascade – multi-tap echo of slices: each step layers slices from 1-8 steps
//             back, each quieter and panned left/right. Repeats = number of echoes
//             and how slowly they fade; Density = echo length; Spread = octave
//             jumps on the later taps.
//
// CPU: grain work is per sample but cheap (table window + two linear reads per
// grain). Cloud/Shimmer at full density runs ~10 grains at once.

#include "mpc_plugin.h"
#include "dsp/math.h"
#include "dsp/delay_line.h"
#include "dsp/noise.h"
#include "dsp/onepole.h"
#include "dsp/smoother.h"
#include "dsp/tempo.h"

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <string>
#include <cmath>
#include <vector>

using namespace mpc::dsp;

namespace {

// Parameter order is permanent once people save projects. Append new ones at the end.
enum ParamIndex
{
    kVolume = 0,   // dB, master output (param 0 is nudged by the host on load: harmless)
    kMode,         // Mosaic / Cloud / Stutter / Shimmer
    kSize,         // ms, grain length (and the slice length in Mosaic/Stutter when Sync is off)
    kDensity,      // %, overlap (Cloud/Shimmer), slice overlap (Mosaic), gate length (Stutter)
    kSpread,       // %, how far back in time grains are taken from / chance of a new slice
    kPitch,        // semitones added to every grain
    kReverse,      // %, chance a grain plays backwards
    kDrift,        // cents, random detune per grain
    kSync,         // Mosaic/Stutter slice length follows the MPC tempo
    kDivision,     // slice length when synced
    kFeedback,     // %, wet signal fed back into the capture buffer
    kLowCut,       // Hz, high-pass on the wet signal
    kHighCut,      // Hz, low-pass on the wet signal
    kRevSize,      // %, reverb room size / decay
    kRevAmount,    // %, reverb level on the wet signal
    kMix,          // %, dry/wet
    kHold,         // freeze: stop recording, keep playing grains from what is captured
    kWidth,        // %, random stereo placement of grains
    kAnim,         // read-only animation clock for the BLOOM screen (0..1, loops). Not automatable;
                   // the plugin writes it itself so film strips bound to it animate on the MPC.
    kGrainMacro,   // -100..+100 %, bends Size (x1/4..x4) and Density around the preset
    kScatterMacro, // -100..+100 %, bends Spread, Reverse, Drift and Width
    kSpaceMacro,   // -100..+100 %, bends Feedback, Rev Amount and Rev Size
    // Read-only "after the macros" values for the BLOOM picture (0..1, plugin-written).
    kShowCore, kShowPetals, kShowHalo, kShowEcho, kShowHaze,
    kRevType,      // Room / Hall / Plate / Dark: voicing of the built-in reverb (appended later;
                   // default Hall, so older projects load with Hall)
    kRepeats,      // %, Cascade only: number of echoes (1..8) and how slowly they fade
    kNumParams
};

enum Mode { kMosaic = 0, kCloud, kStutter, kShimmer, kShatter, kArpeggio, kCascade, kNumModes };
enum RevType { kRoom = 0, kHall, kPlate, kDark };

constexpr float kBufferSeconds = 8.0f;
constexpr int   kNumShow = 5;   // kShowCore .. kShowHaze
constexpr int   kMaxGrains     = 32;
constexpr int   kWindowSize    = 1024;

// ---------------------------------------------------------------------------
// One grain: reads the capture buffer at its own speed under a window.
// ---------------------------------------------------------------------------
struct Grain
{
    bool   active = false;
    double pos = 0.0;      // absolute read position in the buffer (wrapped on read)
    float  rate = 1.0f;    // samples per output sample; negative = reverse
    int    length = 0;     // samples
    int    age = 0;
    float  invLength = 0.0f;
    float  gainL = 1.0f, gainR = 1.0f;
    bool   hardEdges = false;
    float  fadeSamples = 1.0f;
};

// ---------------------------------------------------------------------------
// Lush reverb: a dense, slowly chorused "figure-eight" tank in the style of the classic
// late-70s / early-80s digital studio reverbs.
//
// Topology from the published paper J. Dattorro, "Effect Design Part 1: Reverberator and
// Other Filters", J. Audio Eng. Soc. 45(9), 1997 (written independently from that paper;
// no code copied). Additions here: per-type voicing, pre-delay, a bass-decay multiplier.
//
//   in (L+R)/2 -> pre-delay -> bandwidth low-pass -> 4 input diffusers (allpasses)
//        |
//        +--> left tank:  chorused allpass -> delay -> damping + decay (bass x) -> allpass -> delay -> x decay --+
//        |                                                                                                    |
//        +--> right tank: chorused allpass -> delay -> damping + decay (bass x) -> allpass -> delay -> x decay --+
//   each tank feeds the other (figure eight); the stereo output is a sum of taps inside both tanks.
//
// Why it sounds smooth: the input diffusers turn every grain into a dense smear before it reaches
// the tank, and the two chorused allpasses keep the tank's resonances moving, so no single
// pitch rings (the "metallic"/spring sound of a plain delay network).
// Rev Size sets the reverb time and damping only; the delay lengths stay fixed within a type, so moving
// Space never bends the tail's pitch.
// ---------------------------------------------------------------------------
class LushReverb
{
public:
    void prepare(double sampleRate)
    {
        sr_ = sampleRate;
        k_ = (float)(sampleRate / kDesignRate);
        const float kMax = k_ * kMaxScale;
        const int mod = (int)(kMaxModDepth * k_) + 4;
        for (int i = 0; i < 4; ++i) inAp_[i].prepare((int)(kInAp[i] * kMax) + 4);
        for (int s = 0; s < 2; ++s)
        {
            modAp_[s].prepare((int)(kModAp[s] * kMax) + mod);
            delA_[s].prepare((int)(kDelA[s] * kMax) + 4);
            ap2_[s].prepare((int)(kAp2[s] * kMax) + 4);
            delB_[s].prepare((int)(kDelB[s] * kMax) + 4);
        }
        pre_.prepare((int)(0.05 * sampleRate) + 4);
        scale_.setTime(150.0f, sampleRate);
        decay_.setTime(80.0f, sampleRate);
        bassLp_[0].setCutoff(350.0f, sampleRate);
        bassLp_[1].setCutoff(350.0f, sampleRate);
        reset();
    }
    void reset()
    {
        for (auto& a : inAp_) a.reset();
        for (int s = 0; s < 2; ++s)
        {
            modAp_[s].reset(); delA_[s].reset(); ap2_[s].reset(); delB_[s].reset();
            damp_[s].reset(); bassLp_[s].reset(); end_[s] = 0.0f;
        }
        pre_.reset();
        bandwidth_.reset();
        scale_.snap(scale_.target() > 0.0f ? scale_.target() : 1.0f);
        decay_.snap(decay_.target());
        lfoC_ = 1.0f; lfoS_ = 0.0f;
    }
    // size01: 0..1 from Rev Size (+ Space). type: RevType. Call once per block.
    void setSize(float size01, int type, double sampleRate)
    {
        struct Voice {
            float scale;            // tank length (room size) for this type
            float preMs;            // pre-delay
            float bandwidthHz;      // input low-pass
            float rtLo, rtHi;       // reverb time (s, 60 dB) over the Rev Size range
            float dampLo, dampHi;   // tank damping (Hz) over the Rev Size range (tail darkens as it grows)
            float bass;             // low-frequency reverb time multiplier (>1 = longer, warmer bass tail)
            float modDepth;         // chorus depth (samples at the design rate)
            float modHz;            // chorus rate
        };
        static const Voice kVoices[4] = {
            {0.45f,  4.0f,  9500.0f, 0.30f, 1.2f,  9000.0f, 6000.0f, 1.00f,  5.0f, 0.90f},  // Room
            {1.00f, 18.0f,  7500.0f, 1.00f, 5.0f,  7000.0f, 3800.0f, 1.25f, 12.0f, 0.55f},  // Hall
            {0.72f,  0.0f, 13000.0f, 0.60f, 3.5f, 13000.0f, 8000.0f, 0.90f,  8.0f, 1.10f},  // Plate
            {1.10f, 28.0f,  4200.0f, 1.50f, 7.0f,  3200.0f, 1600.0f, 1.35f, 14.0f, 0.40f},  // Dark
        };
        const Voice& v = kVoices[type < 0 ? 0 : (type > 3 ? 3 : type)];
        size01 = size01 < 0.0f ? 0.0f : (size01 > 1.0f ? 1.0f : size01);
        scale_.setTarget(v.scale);
        // One trip round the figure eight passes four decay gains and lasts kLoopSeconds * scale,
        // so for a reverb time rt: gain = 10^(-60 dB / 20 / 4 * loop / rt).
        const float rt = v.rtLo * std::pow(v.rtHi / v.rtLo, size01);
        const float loop = kLoopSeconds * v.scale;
        decay_.setTarget(std::pow(10.0f, -0.75f * loop / rt));
        lowDecay_ = std::pow(10.0f, -0.75f * loop / (rt * v.bass));
        if (lowDecay_ > 0.98f) lowDecay_ = 0.98f;
        preSamples_ = v.preMs * 0.001f * (float)sampleRate;
        bandwidth_.setCutoff(v.bandwidthHz, sampleRate);
        const float dampHz = v.dampLo + (v.dampHi - v.dampLo) * size01;
        damp_[0].setCutoff(dampHz, sampleRate);
        damp_[1].setCutoff(dampHz, sampleRate);
        modDepth_ = v.modDepth * k_;
        const float w = 2.0f * 3.14159265f * v.modHz / (float)sampleRate;
        lfoCw_ = std::cos(w);
        lfoSw_ = std::sin(w);
    }
    void process(float inL, float inR, float& outL, float& outR)
    {
        const float k = k_ * scale_.process();
        const float decay = decay_.process();
        const float lowDecay = lowDecay_;

        // Quadrature LFO by rotation (no per-sample sin); the 1.5 - 0.5 r^2 step keeps it at unit size.
        const float c = lfoC_ * lfoCw_ - lfoS_ * lfoSw_;
        const float s = lfoS_ * lfoCw_ + lfoC_ * lfoSw_;
        const float r = 1.5f - 0.5f * (c * c + s * s);
        lfoC_ = c * r; lfoS_ = s * r;

        // Input: mono sum, pre-delay, bandwidth, diffusion.
        pre_.write(0.5f * (inL + inR) + 1.0e-20f);   // tiny offset keeps the tank out of denormals
        float x = bandwidth_.process(preSamples_ >= 1.0f ? pre_.readLinear(preSamples_) : pre_.readInt(1));
        for (int i = 0; i < 4; ++i) x = allpass(inAp_[i], x, kInAp[i] * k, kInG[i]);

        // Tank: each side takes the input plus the other side's end.
        float tankIn[2] = { x + end_[1], x + end_[0] };
        const float lfo[2] = { lfoS_, lfoC_ };
        for (int sd = 0; sd < 2; ++sd)
        {
            float t = allpass(modAp_[sd], tankIn[sd], kModAp[sd] * k + modDepth_ * lfo[sd], -0.70f);
            delA_[sd].write(t);
            t = damp_[sd].process(delA_[sd].readLinear(kDelA[sd] * k));
            const float low = bassLp_[sd].process(t);
            t = t * decay + low * (lowDecay - decay);
            t = allpass(ap2_[sd], t, kAp2[sd] * k, 0.50f);
            delB_[sd].write(t);
            end_[sd] = delB_[sd].readLinear(kDelB[sd] * k) * decay;
        }

        // Output taps (positions from the paper, scaled with the tank).
        auto tap = [k](const mpc::dsp::DelayLine& d, float n) { return d.readInt((int)(n * k)); };
        const float yl =   tap(delA_[1], 266.0f) + tap(delA_[1], 2974.0f) - tap(ap2_[1], 1913.0f)
                         + tap(delB_[1], 1996.0f) - tap(delA_[0], 1990.0f) - tap(ap2_[0], 187.0f)
                         - tap(delB_[0], 1066.0f);
        const float yr =   tap(delA_[0], 353.0f) + tap(delA_[0], 3627.0f) - tap(ap2_[0], 1228.0f)
                         + tap(delB_[0], 2673.0f) - tap(delA_[1], 2111.0f) - tap(ap2_[1], 335.0f)
                         - tap(delB_[1], 121.0f);
        outL = kOutGain * yl;
        outR = kOutGain * yr;
    }

private:
    // Lattice allpass on a DelayLine: w = x + g*v, y = v - g*w (v = w delayed).
    static float allpass(mpc::dsp::DelayLine& d, float x, float delay, float g)
    {
        const float v = d.readLinear(delay);
        const float w = x + g * v;
        d.write(w);
        return v - g * w;
    }

    static constexpr double kDesignRate = 29761.0;   // the paper's sample rate; lengths below are at this rate
    static constexpr float  kMaxScale = 1.15f;       // largest type scale (Dark) with some headroom
    static constexpr float  kMaxModDepth = 16.0f;
    static constexpr float  kOutGain = 0.52f;   // about the old reverb's level
    static constexpr float  kLoopSeconds = (672.0f + 4453.0f + 1800.0f + 3720.0f + 908.0f + 4217.0f + 2656.0f + 3163.0f) / 29761.0f;
    static constexpr float kInAp[4]  = {142.0f, 107.0f, 379.0f, 277.0f};
    static constexpr float kInG[4]   = {0.75f, 0.75f, 0.625f, 0.625f};
    static constexpr float kModAp[2] = {672.0f, 908.0f};
    static constexpr float kDelA[2]  = {4453.0f, 4217.0f};
    static constexpr float kAp2[2]   = {1800.0f, 2656.0f};
    static constexpr float kDelB[2]  = {3720.0f, 3163.0f};

    mpc::dsp::DelayLine inAp_[4], modAp_[2], delA_[2], ap2_[2], delB_[2], pre_;
    mpc::dsp::OnePoleLP bandwidth_, damp_[2], bassLp_[2];
    mpc::dsp::Smoother scale_, decay_;
    float end_[2] = {0.0f, 0.0f};
    float lowDecay_ = 0.5f, preSamples_ = 0.0f, modDepth_ = 0.0f;
    float lfoC_ = 1.0f, lfoS_ = 0.0f, lfoCw_ = 1.0f, lfoSw_ = 0.0f;
    float k_ = 1.0f;
    double sr_ = 44100.0;
};
constexpr float LushReverb::kInAp[4];
constexpr float LushReverb::kInG[4];
constexpr float LushReverb::kModAp[2];
constexpr float LushReverb::kDelA[2];
constexpr float LushReverb::kAp2[2];
constexpr float LushReverb::kDelB[2];

} // namespace

class Grainbloom : public mpc::Plugin
{
public:
    static mpc::PluginInfo makeInfo()
    {
        mpc::PluginInfo i;
        i.name = "Grainbloom";
        i.vendor = "Lightlike";
        i.uniqueId = MPC_FOURCC('L', 'w', 'W', '1');   // == "uid" in plugin.json; never change
        i.version = 1000;
        i.isInstrument = false;
        i.numInputs = 2;
        i.numOutputs = 2;
        i.tailSamples = 0;   // unknown: depends on Feedback, reverb and Hold
        return i;
    }

    Grainbloom() : mpc::Plugin(makeInfo())
    {
        using namespace mpc;
        addParam(floatParam("volume",   "Volume", -24.0f, 6.0f, 0.0f, "dB", 1));
        addParam(choiceParam("mode",    "Mode", {"Mosaic", "Cloud", "Stutter", "Shimmer",
                                               "Shatter", "Arpeggio", "Cascade"}, kMosaic));   // new modes appended
        addParam(logParam  ("size",     "Size", 10.0f, 1000.0f, 120.0f, "ms", 0));
        addParam(floatParam("density",  "Density", 0.0f, 100.0f, 50.0f, "%", 0));
        addParam(floatParam("spread",   "Spread", 0.0f, 100.0f, 40.0f, "%", 0));
        addParam(intParam  ("pitch",    "Pitch", -24, 24, 0, "st"));
        addParam(floatParam("reverse",  "Reverse", 0.0f, 100.0f, 25.0f, "%", 0));
        addParam(floatParam("drift",    "Drift", 0.0f, 50.0f, 5.0f, "ct", 0));
        addParam(boolParam ("sync",     "Sync", true));
        addParam(choiceParam("division","Division", divisionNames(), kDivisionEighth));
        addParam(floatParam("feedback", "Feedback", 0.0f, 95.0f, 20.0f, "%", 0));
        addParam(logParam  ("lowcut",   "Low Cut", 20.0f, 2000.0f, 40.0f, "Hz", 0));
        addParam(logParam  ("highcut",  "High Cut", 500.0f, 18000.0f, 12000.0f, "Hz", 0));
        addParam(floatParam("revsize",  "Rev Size", 0.0f, 100.0f, 50.0f, "%", 0));
        addParam(floatParam("revamount","Rev Amount", 0.0f, 100.0f, 25.0f, "%", 0));
        addParam(floatParam("mix",      "Mix", 0.0f, 100.0f, 50.0f, "%", 0));
        addParam(boolParam ("hold",     "Hold", false));
        addParam(floatParam("width",    "Width", 0.0f, 100.0f, 70.0f, "%", 0));
        {
            Param anim = floatParam("anim", "~Anim", 0.0f, 1.0f, 0.0f, "", 2);
            anim.automatable = false;
            addParam(anim);
        }
        addParam(floatParam("grain",    "Grain", -100.0f, 100.0f, 0.0f, "%", 0));
        addParam(floatParam("scatter",  "Scatter", -100.0f, 100.0f, 0.0f, "%", 0));
        addParam(floatParam("space",    "Space", -100.0f, 100.0f, 0.0f, "%", 0));
        for (const char* id : {"show_core", "show_petals", "show_halo", "show_echo", "show_haze"})
        {
            Param show = floatParam(id, id + 5, 0.0f, 1.0f, 0.0f, "", 2);   // name "core", "petals"...
            show.name = std::string("~") + (id + 5);
            show.automatable = false;
            addParam(show);
        }
        addParam(choiceParam("revtype", "Reverb", {"Room", "Hall", "Plate", "Dark"}, kHall));
        addParam(floatParam("repeats", "Repeats", 0.0f, 100.0f, 40.0f, "%", 0));
        if (numParams() != kNumParams) mpc::log("Grainbloom: parameter count mismatch");

        // Built-in programs. Values in parameter order:
        // Volume, Mode, Size, Density, Spread, Pitch, Reverse, Drift, Sync, Division,
        // Feedback, LowCut, HighCut, RevSize, RevAmount, Mix, Hold, Width, (~Anim), Grain, Scatter, Space,
        // (5 read-only picture values), Reverb type, Repeats
        // The macros are 0 in every preset: 0 = the preset exactly as stored.
        addProgram("Init Mosaic",       {0, kMosaic,  112, 48, 53.5,   0, 35.8,  11.8, 1, kDivisionEighth,     36.2,  40, 12000, 64.4, 43, 50, 0,  80.8, 0, 5, -27, -36,  0, 0, 0, 0, 0, kHall, 40});
        addProgram("Glass Cloud",       {0, kCloud,   131.7, 55.2, 62.5,   0, 12, 16.2, 1, kDivisionEighth,     32.7,  80,  9000, 72.4, 43, 60, 0,  92, 0, 37, -5, -6,  0, 0, 0, 0, 0, kPlate, 40});
        addProgram("Tape Stutter",      {0, kStutter,  77.8, 59.2, 62.5,   0,  26,  16.2, 1, kDivisionSixteenth,   32.9,  40, 14000, 59.2, 46.5, 70, 0,  66, 0, 2, -65, -73,  0, 0, 0, 0, 0, kRoom, 40});
        addProgram("Octave Bloom",     {-2, kShimmer, 179.6, 45.2, 63.5,   0,  10.8,  14.8, 1, kDivisionEighth,     43.8, 120,  8000, 70, 37.5, 60, 0,  90.8, 0, 37, -27, 25,  0, 0, 0, 0, 0, kHall, 40});
        addProgram("Reverse Rain",      {0, kCloud,    67.3, 71.6, 52.5,   0, 68, 6.2, 1, kDivisionEighth,     30.3,  60, 10000, 69.2, 46.5, 55, 0, 78, 0, 21, 55, -23,  0, 0, 0, 0, 0, kPlate, 40});
        addProgram("Half-Speed Haze",   {0, kCloud,   242.8, 35.6, 47.5, -12, 36, 13.8, 1, kDivisionEighth,     25.9,  40,  6000, 75.8, 46, 55, 0,  86, 0, 36, -15, -2,  0, 0, 0, 0, 0, kDark, 40});
        addProgram("Broken Sixteenths", {0, kMosaic,  139.8, 34.4, 82.5,   0, 52,  1.2, 1, kDivisionSixteenth,  38.4,  60, 15000, 55.2, 46.5, 65, 0,  62, 0, -11, -5, -63,  0, 0, 0, 0, 0, kRoom, 40});
        addProgram("Endless Pad",       {0, kCloud,   142.1, 64, 66.5,   0, 17.2, 10.2, 1, kDivisionEighth,     41.1,  40,  9000, 73.2, 39, 80, 0, 97.2, 0, 65, 7, 42,  0, 0, 0, 0, 0, kHall, 40});
        // Added with the Shatter / Arpeggio / Cascade modes (appended so program numbers stay put).
        addProgram("Glass Shards",      {0, kShatter, 105.9, 51.4, 65,   0, 42,  7.5, 1, kDivisionSixteenth,  38.4,  60, 15000, 55.2, 46.5, 70, 0,  72, 0, 9, -30, -63,  0, 0, 0, 0, 0, kRoom, 40});
        addProgram("Crystal Arp",       {0, kArpeggio,100.2, 54.8, 72.5,   0,  18,  16.2, 1, kDivisionSixteenth,  33.6, 120, 12000, 67.6, 44.5, 70, 0,  68, 0, 13, -45, -19,  0, 0, 0, 0, 0, kPlate, 40});
        addProgram("Falling Echoes",    {0, kCascade, 89.7, 61.6, 53.5,   0, 20.8,  14.8, 1, 9 /* 1/8D */,        32.7,  80,  9000, 72.4, 43, 55, 0,  90.8, 0, 21, -27, -6,  0, 0, 0, 0, 0, kHall, 55});
        addProgram("Data Storm",        {0, kShatter,  59, 76.2, 90,   0, 45,  0, 1, 2 /* 1/32 */,        44.7,  80, 16000, 51.4, 43, 75, 0,  90, 0, 22, 0, -66,  0, 0, 0, 0, 0, kRoom, 40});
        addProgram("Skip Beat",         {0, kShatter, 156.2, 27.6, 58.5,   0, 37.8,  14.2, 1, kDivisionEighth,      36.5,  60, 14000, 58, 45, 60, 0,  62.8, 0, -19, -57, -70,  0, 0, 0, 0, 0, kRoom, 40});
        addProgram("Night Ladder",      {0, kArpeggio,75.9, 71.8, 59, -12,  19.2,  16, 1, kDivisionEighth,     26.9,  60,  5000, 77.8, 46, 65, 0,  79.2, 0, 33, -48, 18,  0, 0, 0, 0, 0, kDark, 40});
        addProgram("Glass Spiral",      {0, kArpeggio,118.3, 44.6, 92.5,   0, 8, 8.8, 1, 3 /* 1/16T */,       37.8, 200, 16000, 68, 42.5, 70, 0,  83, 0, 1, 5, 5,  0, 0, 0, 0, 0, kPlate, 40});
        addProgram("Ping Pong Steps",   {0, kCascade, 125.1, 41.2, 15,   0,  0,  0, 1, kDivisionEighth,     38.4, 100, 14000, 55.2, 46.5, 45, 0, 100, 0, -3, 0, -63,  0, 0, 0, 0, 0, kRoom, 30});
        addProgram("Endless Stairs",    {0, kCascade, 80.3, 68.4, 61.5,   0, 21.2, 12.8, 1, 12 /* 1/4D */,       38.8,  60,  7000, 75, 37.5, 65, 0,  91.2, 0, 29, -3, 25,  0, 0, 0, 0, 0, kDark, 90});

        // Hann window table (constructor: allowed to allocate).
        window_.resize(kWindowSize + 1);
        for (int i = 0; i <= kWindowSize; ++i)
            window_[(size_t)i] = 0.5f - 0.5f * std::cos(kTwoPi * (float)i / (float)kWindowSize);
    }

    void prepare(double sampleRate, int /*maxBlockSize*/) override
    {
        int size = 1;
        const int want = (int)(sampleRate * kBufferSeconds);
        while (size < want) size <<= 1;
        bufL_.assign((size_t)size, 0.0f);
        bufR_.assign((size_t)size, 0.0f);
        mask_ = size - 1;
        bufSize_ = size;
        reverb_.prepare(sampleRate);
        mix_.setTime(30.0f, sampleRate);
        volume_.setTime(30.0f, sampleRate);
        feedback_.setTime(30.0f, sampleRate);
        revAmount_.setTime(30.0f, sampleRate);
    }

    void reset() override
    {
        std::fill(bufL_.begin(), bufL_.end(), 0.0f);
        std::fill(bufR_.begin(), bufR_.end(), 0.0f);
        write_ = 0;
        recorded_ = 0;
        for (Grain& g : grains_) g.active = false;
        samplesToNext_ = 0.0;
        stutterAnchor_ = -1.0;
        shatterLeft_ = 0;
        arpStep_ = 0;
        arpAnchor_ = -1.0;
        lastFbL_ = lastFbR_ = 0.0f;
        // reset() also runs right after a preset or saved state is loaded. The framework sets the
        // values silently, and the MPC only redraws controls it is told about, so report every
        // user setting at the end of the next process() call. (The read-only picture values are
        // left alone: they follow the sound by themselves, and the mesh screen does not use them.)
        reportAllPending_.store(true, std::memory_order_release);
        lowCutL_.reset(); lowCutR_.reset(); highCutL_.reset(); highCutR_.reset();
        reverb_.reset();
        mix_.snap(get(kMix) * 0.01f);
        volume_.snap(dbToGain(get(kVolume)));
        feedback_.snap(get(kFeedback) * 0.01f);
        revAmount_.snap(get(kRevAmount) * 0.01f);
    }

    // Grain, Scatter and Space are stored as -100..+100 (0 = the preset as stored), but shown
    // as 0..100 with 50 in the middle, so the value reads like the left-to-right bar. The stored
    // range stays the same so existing projects and automation load unchanged.
    bool formatValue(int index, float plainValue, std::string& out) override
    {
        if (index != kGrainMacro && index != kScatterMacro && index != kSpaceMacro) return false;
        char buf[16];
        std::snprintf(buf, sizeof(buf), "%d", (int)std::lround((plainValue + 100.0f) * 0.5f));
        out = buf;
        return true;
    }

    void process(mpc::ProcessContext& ctx) override
    {
        if (bufSize_ == 0) return;
        const double sr = ctx.sampleRate;

        // ----- per block: parameters -----------------------------------------
        const int   mode     = clamp(getInt(kMode), 0, kNumModes - 1);
        const bool  hold     = getBool(kHold);

        // Macros: 0 = the preset as stored; +-100 % bends a group of settings up or down.
        const float mGrain   = get(kGrainMacro) * 0.01f;
        const float mScatter = get(kScatterMacro) * 0.01f;
        const float mSpace   = get(kSpaceMacro) * 0.01f;
        const float sizeMs   = clamp(get(kSize) * std::pow(4.0f, mGrain), 10.0f, 1000.0f);
        const float density  = clamp(get(kDensity) * 0.01f + 0.4f * mGrain, 0.0f, 1.0f);
        const float spread   = clamp(get(kSpread) * 0.01f + 0.5f * mScatter, 0.0f, 1.0f);
        effReverse_ = clamp(get(kReverse) * 0.01f + 0.4f * mScatter, 0.0f, 1.0f);
        effDrift_   = clamp(get(kDrift) + 25.0f * mScatter, 0.0f, 50.0f);
        effWidth_   = clamp(get(kWidth) * 0.01f + 0.4f * mScatter, 0.0f, 1.0f);
        const float fbAmt    = clamp(get(kFeedback) * 0.01f + 0.45f * mSpace, 0.0f, 0.95f);
        const float revAmt   = clamp(get(kRevAmount) * 0.01f + 0.5f * mSpace, 0.0f, 1.0f);
        const float revSize  = clamp(get(kRevSize) * 0.01f + 0.4f * mSpace, 0.0f, 1.0f);
        const float sizeSamp = clamp(msToSamples(sizeMs, sr), 64.0f, (float)sr * 2.0f);

        // Slice length for the rhythmic modes: tempo division when synced, else Size.
        const bool  synced    = getBool(kSync);
        const float divBeats  = divisionBeats(getInt(kDivision));
        float stepSamp = synced ? beatsToSamples(divBeats, ctx.transport.bpm, sr) : sizeSamp;
        stepSamp = clamp(stepSamp, 64.0f, (float)sr * 2.0f);

        // Snap the rhythmic grid to the song position while the MPC is playing.
        // (Shatter only snaps between its ratchet bursts.)
        const bool gridMode = mode == kMosaic || mode == kStutter || mode == kArpeggio ||
                              mode == kCascade || (mode == kShatter && shatterLeft_ == 0);
        if (gridMode && synced && ctx.transport.playing && ctx.transport.ppqValid)
        {
            const float phase = ppqPhase(ctx.transport.ppqPos, divBeats);
            samplesToNext_ = (double)((1.0f - phase) * stepSamp);
            if (phase < 1.0e-4f) samplesToNext_ = 0.0;
        }

        mix_.setTarget(get(kMix) * 0.01f);
        volume_.setTarget(dbToGain(get(kVolume)));
        feedback_.setTarget(hold ? 0.0f : fbAmt);
        revAmount_.setTarget(revAmt);
        lowCutL_.setCutoff(get(kLowCut), sr);   lowCutR_.setCutoff(get(kLowCut), sr);
        highCutL_.setCutoff(get(kHighCut), sr); highCutR_.setCutoff(get(kHighCut), sr);
        reverb_.setSize(revSize, getInt(kRevType), sr);

        // Expected number of overlapping grains, used to keep the level steady.
        float overlap;
        switch (mode)
        {
            case kCloud: case kShimmer: overlap = 1.0f + density * 7.0f; break;
            case kMosaic:               overlap = 1.0f + density;        break;
            default:                    overlap = 1.0f;                  break;
        }
        const float grainGain = (mode == kCloud || mode == kShimmer) ? 1.4f / std::sqrt(overlap) : 1.0f;

        const float* inL = ctx.inputs[0];
        const float* inR = ctx.numInputs > 1 ? ctx.inputs[1] : ctx.inputs[0];
        float* outL = ctx.outputs[0];
        float* outR = ctx.numOutputs > 1 ? ctx.outputs[1] : ctx.outputs[0];

        // ----- per sample ------------------------------------------------------
        for (int i = 0; i < ctx.numFrames; ++i)
        {
            const float dryL = inL[i], dryR = inR[i];

            // 1. Record (input + feedback) unless Hold is on.
            if (!hold)
            {
                bufL_[(size_t)(write_ & mask_)] = dryL + lastFbL_;
                bufR_[(size_t)(write_ & mask_)] = dryR + lastFbR_;
                ++write_;
                if (recorded_ < bufSize_) ++recorded_;
            }

            // 2. Start new grains when it is time.
            samplesToNext_ -= 1.0;
            if (samplesToNext_ <= 0.0 && recorded_ > 256)
            {
                double interval;
                if (mode == kCloud || mode == kShimmer)
                {
                    interval = (double)(sizeSamp / overlap) * (0.5 + rng_.nextFloat());   // jittered
                    spawnScatterGrain(mode, sizeSamp, spread, grainGain);
                }
                else if (mode == kShatter)
                {
                    interval = (double)spawnShatterGrain(stepSamp, density, spread, sr);
                }
                else
                {
                    interval = (double)stepSamp;
                    if (mode == kMosaic)        spawnMosaicGrain(stepSamp, density, spread);
                    else if (mode == kArpeggio) spawnArpGrain(stepSamp, density, spread, sr);
                    else if (mode == kCascade)  spawnCascadeGrains(stepSamp, density, spread, get(kRepeats) * 0.01f);
                    else                        spawnStutterGrain(stepSamp, density, spread, sr);
                }
                samplesToNext_ += interval < 32.0 ? 32.0 : interval;
            }

            // 3. Sum the active grains.
            float wetL = 0.0f, wetR = 0.0f;
            for (Grain& g : grains_)
            {
                if (!g.active) continue;
                const float t = (float)g.age * g.invLength;
                float w;
                if (g.hardEdges)
                {
                    const float edge = (float)std::min(g.age, g.length - g.age);
                    w = edge >= g.fadeSamples ? 1.0f : edge / g.fadeSamples;
                }
                else
                {
                    const float x = t * (float)kWindowSize;
                    const int   xi = (int)x;
                    w = window_[(size_t)xi] + (x - (float)xi) * (window_[(size_t)xi + 1] - window_[(size_t)xi]);
                }
                float sL, sR;
                readBuffer(g.pos, sL, sR);
                wetL += sL * w * g.gainL;
                wetR += sR * w * g.gainR;
                g.pos += (double)g.rate;
                if (++g.age >= g.length) g.active = false;
            }

            // 4. Tone, feedback, reverb.
            wetL = highCutL_.process(lowCutL_.process(wetL));
            wetR = highCutR_.process(lowCutR_.process(wetR));
            const float fb = feedback_.process();
            lastFbL_ = softClip(wetL * fb);
            lastFbR_ = softClip(wetR * fb);

            float revL, revR;
            reverb_.process(wetL, wetR, revL, revR);
            const float ra = revAmount_.process();
            wetL = wetL * (1.0f - 0.5f * ra) + revL * ra;
            wetR = wetR * (1.0f - 0.5f * ra) + revR * ra;

            // 5. Mix and output (soft clip keeps stacked grains from overloading).
            const float mix = mix_.process();
            const float vol = volume_.process();
            outL[i] = softClip(sanitize((dryL + (wetL - dryL) * mix) * vol));
            outR[i] = softClip(sanitize((dryR + (wetR - dryR) * mix) * vol));
        }

        // ----- BLOOM screen animation clock ------------------------------------
        // Loops every ~5-13 s (faster with more Density), slows right down on Hold.
        // Written only when it has moved a visible step (at most ~30 times a second), and the
        // host is told each time: the MPC screen does not redraw for a value the plugin changes
        // silently. The MPC's host queues audioMasterAutomate, so calling it here is safe.
        const float loopsPerSecond = (hold ? 0.25f : 1.0f) * (0.6f + 0.8f * density) / 8.0f;
        animPhase_ += (double)ctx.numFrames / sr * (double)loopsPerSecond;
        animPhase_ -= std::floor(animPhase_);
        animSinceSend_ += ctx.numFrames;
        if (std::fabs((float)animPhase_ - lastAnimSent_) >= 1.0f / 96.0f &&
            (double)animSinceSend_ >= sr / 30.0)
        {
            animSinceSend_ = 0;
            lastAnimSent_ = (float)animPhase_;
            setNormalised(kAnim, lastAnimSent_);
            notifyHostParameterChanged(kAnim);
        }

        // ----- After a preset/state load: tell the MPC every setting changed ---------
        if (reportAllPending_.exchange(false, std::memory_order_acq_rel))
        {
            for (int k = 0; k < kNumParams; ++k)
                if (k != kAnim && (k < kShowCore || k > kShowHaze)) notifyHostParameterChanged(k);
        }

        // ----- BLOOM picture: publish the after-macro values -------------------
        // Only when one has moved a visible step (the strips have 24 frames).
        const float show[kNumShow] = {
            param(kSize).toNormalised(sizeMs),
            density,
            spread,
            fbAmt / 0.95f,
            revAmt };
        showSinceSend_ += ctx.numFrames;
        for (int k = 0; k < kNumShow && (double)showSinceSend_ >= sr / 30.0; ++k)
        {
            if (std::fabs(show[k] - lastShow_[k]) >= 1.0f / 48.0f || (show[k] != lastShow_[k] && (show[k] == 0.0f || show[k] == 1.0f)))
            {
                lastShow_[k] = show[k];
                setNormalised(kShowCore + k, show[k]);
                notifyHostParameterChanged(kShowCore + k);
            }
        }
        if ((double)showSinceSend_ >= sr / 30.0) showSinceSend_ = 0;
    }

private:
    // Linear-interpolated stereo read at an absolute buffer position.
    void readBuffer(double pos, float& l, float& r) const
    {
        const double fl = std::floor(pos);
        const long long i0 = (long long)fl;
        const float f = (float)(pos - fl);
        const size_t a = (size_t)(i0 & mask_), b = (size_t)((i0 + 1) & mask_);
        l = bufL_[a] + f * (bufL_[b] - bufL_[a]);
        r = bufR_[a] + f * (bufR_[b] - bufR_[a]);
    }

    Grain* freeGrain()
    {
        for (Grain& g : grains_) if (!g.active) return &g;
        // All busy: steal the oldest relative to its length.
        Grain* best = &grains_[0];
        float bestT = -1.0f;
        for (Grain& g : grains_) { const float t = (float)g.age * g.invLength; if (t > bestT) { bestT = t; best = &g; } }
        return best;
    }

    // Speed for a grain: Pitch + extra semitones + random Drift; reversed by chance.
    float grainRate(float extraSemis)
    {
        const float driftCents = effDrift_ * rng_.nextBipolar();
        float rate = semitonesToRatio((float)getInt(kPitch) + extraSemis + driftCents * 0.01f);
        if (rng_.nextFloat() < effReverse_) rate = -rate;
        return rate;
    }

    // Absolute start position "delay" samples behind the write head, made safe so a
    // forward grain faster than real time never overtakes the write head.
    double startFor(float rate, int length, float extraBack) const
    {
        const float minBack = (rate > 1.0f ? (rate - 1.0f) * (float)length : 0.0f) + 64.0f;
        float back = minBack + extraBack;
        if (rate < 0.0f) back += 0.0f;   // reverse grains move away from the write head
        const float limit = (float)std::min(recorded_, (long long)bufSize_) - (float)length * std::fabs(rate) - 64.0f;
        if (back > limit) back = std::max(minBack, limit);
        return (double)write_ - (double)back;
    }

    void setPan(Grain& g)
    {
        const float pan = effWidth_ * rng_.nextBipolar();
        g.gainL = pan > 0.0f ? 1.0f - pan : 1.0f;
        g.gainR = pan < 0.0f ? 1.0f + pan : 1.0f;
    }

    void start(Grain& g, double pos, float rate, int length, bool hard, float fade, float gain)
    {
        g.active = true;
        g.pos = pos;
        g.rate = rate;
        g.length = length < 16 ? 16 : length;
        g.age = 0;
        g.invLength = 1.0f / (float)g.length;
        g.hardEdges = hard;
        g.fadeSamples = fade < 1.0f ? 1.0f : fade;
        setPan(g);
        g.gainL *= gain;
        g.gainR *= gain;
    }

    void spawnScatterGrain(int mode, float sizeSamp, float spread, float gain)
    {
        const float len = sizeSamp * (0.75f + 0.5f * rng_.nextFloat());
        const float rate = grainRate(mode == kShimmer ? 12.0f : 0.0f);
        const float scatter = spread * rng_.nextFloat() * 2.0f * (float)sampleRate();   // up to 2 s back
        Grain& g = *freeGrain();
        start(g, startFor(rate, (int)len, scatter), rate, (int)len, false, 1.0f, gain);
    }

    void spawnMosaicGrain(float stepSamp, float density, float spread)
    {
        const float len = stepSamp * (1.0f + density);   // overlap up to 2 slices
        float extra = 0.0f;
        const float r = rng_.nextFloat();
        if (r < spread * 0.35f) extra = 12.0f;
        else if (r < spread * 0.5f) extra = -12.0f;
        const float rate = grainRate(extra);
        const int slicesBack = 1 + (int)(rng_.nextFloat() * (1.0f + spread * 7.0f));
        Grain& g = *freeGrain();
        start(g, startFor(rate, (int)len, stepSamp * (float)slicesBack), rate, (int)len, false, 1.0f, 1.0f);
    }

    void spawnStutterGrain(float stepSamp, float density, float spread, double sr)
    {
        const float len = stepSamp * (0.3f + 0.7f * density);   // gate length
        const float rate = semitonesToRatio((float)getInt(kPitch));   // stutters keep a steady pitch
        // Grab a new slice at the start, or by chance (Spread), or when the old one is too old.
        const double oldest = (double)write_ - (double)std::min(recorded_, (long long)bufSize_) + 4.0 * stepSamp;
        if (stutterAnchor_ < 0.0 || rng_.nextFloat() < 0.1f + spread * 0.6f || stutterAnchor_ < oldest)
        {
            stutterAnchor_ = startFor(rate, (int)len, stepSamp);
            stutterReverse_ = rng_.nextFloat() < effReverse_;
        }
        const float fade = (float)(0.004 * sr);   // 4 ms edges
        Grain& g = *freeGrain();
        // A reversed stutter plays the same slice backwards from its end.
        const double pos = stutterReverse_ ? stutterAnchor_ + (double)len * rate : stutterAnchor_;
        start(g, pos, stutterReverse_ ? -rate : rate, (int)len, true, std::min(fade, len * 0.25f), 1.0f);
    }

    // Shatter: one step = 1, 2 or 4 hard-edged hits of the same slice (or a drop-out).
    // Returns the time to the next hit.
    float spawnShatterGrain(float stepSamp, float density, float spread, double sr)
    {
        if (shatterLeft_ == 0)
        {
            // New step: choose ratchets, source slice, pitch, direction, drop-out.
            const float r = rng_.nextFloat();
            shatterHits_ = r < 0.15f + 0.35f * density ? (r < 0.05f + 0.15f * density ? 4 : 2) : 1;
            shatterLeft_ = shatterHits_;
            shatterMute_ = rng_.nextFloat() < 0.25f * (1.0f - density);
            float semis = 0.0f;
            const float p = rng_.nextFloat();
            if (p < spread * 0.25f) semis = 12.0f; else if (p < spread * 0.4f) semis = -12.0f;
            shatterRate_ = semitonesToRatio((float)getInt(kPitch) + semis);
            shatterReverse_ = rng_.nextFloat() < effReverse_;
            const int slicesBack = 1 + (int)(rng_.nextFloat() * (1.0f + spread * 7.0f));
            shatterAnchor_ = startFor(shatterRate_, (int)stepSamp, stepSamp * (float)slicesBack);
        }
        const float hit = stepSamp / (float)shatterHits_;
        --shatterLeft_;
        if (!shatterMute_)
        {
            const float len = hit * 0.92f;
            const float fade = std::min((float)(0.003 * sr), len * 0.25f);
            const double pos = shatterReverse_ ? shatterAnchor_ + (double)len * shatterRate_ : shatterAnchor_;
            Grain& g = *freeGrain();
            start(g, pos, shatterReverse_ ? -shatterRate_ : shatterRate_, (int)len, true, fade, 1.0f);
        }
        return hit;
    }

    // Arpeggio: the same slice, re-pitched step by step through a pattern of fifths and
    // octaves. Spread widens the range (2..8 notes) and, near the top, shuffles the order.
    void spawnArpGrain(float stepSamp, float density, float spread, double sr)
    {
        static const float kUp[5]     = {0.0f, 7.0f, 12.0f, 19.0f, 24.0f};
        static const float kUpDown[8] = {0.0f, 7.0f, 12.0f, 19.0f, 24.0f, 19.0f, 12.0f, 7.0f};
        const int notes = 2 + (int)(spread * 6.0f + 0.5f);           // 2..8
        if (arpStep_ >= notes || arpAnchor_ < 0.0) arpStep_ = 0;
        if (arpStep_ == 0)   // new cycle: capture a fresh slice
            arpAnchor_ = startFor(semitonesToRatio(24.0f + (float)getInt(kPitch)), (int)stepSamp, stepSamp);
        int idx = arpStep_;
        if (spread > 0.8f) idx = (int)(rng_.nextFloat() * (float)notes) % notes;
        // Up to 5 notes climb; 6-8 notes climb and come back down.
        const float rate = grainRate(notes <= 5 ? kUp[idx % 5] : kUpDown[idx % 8]);
        const float len = stepSamp * (0.35f + 0.6f * density);
        const float fade = std::min((float)(0.004 * sr), len * 0.25f);
        const double pos = rate < 0.0f ? arpAnchor_ + (double)len * -rate : arpAnchor_;
        Grain& g = *freeGrain();
        start(g, pos, rate, (int)len, true, fade, 0.9f);
        ++arpStep_;
    }

    // Cascade: echoes of slices from 1..8 steps back, quieter each time, panned alternately.
    // repeats (0..1) sets the number of echoes and how slowly they fade; density the length.
    void spawnCascadeGrains(float stepSamp, float density, float spread, float repeats)
    {
        const int taps = 1 + (int)(repeats * 7.0f + 0.5f);         // 1..8
        const float decay = 0.55f + 0.35f * repeats;                 // level kept per echo
        const float norm = 1.0f / std::sqrt(1.0f + 0.5f * (float)(taps - 1));
        for (int k = 1; k <= taps; ++k)
        {
            float semis = 0.0f;
            if (k > 1 && rng_.nextFloat() < spread * 0.6f) semis = (k % 2 == 0) ? 12.0f : -12.0f;
            const float rate = grainRate(semis);
            const float len = stepSamp * (0.5f + 0.6f * density);
            Grain& g = *freeGrain();
            start(g, startFor(rate, (int)len, stepSamp * (float)k), rate, (int)len, false, 1.0f,
                  norm * std::pow(decay, (float)(k - 1)));
            // Alternate sides, wider for later taps (on top of the random Width placement).
            const float side = (k % 2 == 0 ? 1.0f : -1.0f) * std::min(1.0f, 0.15f * (float)(k - 1)) * (0.4f + 0.6f * effWidth_);
            if (side > 0.0f) g.gainL *= 1.0f - side; else g.gainR *= 1.0f + side;
        }
    }

    // Capture buffer (allocated in prepare()).
    std::vector<float> bufL_, bufR_;
    int mask_ = 0, bufSize_ = 0;
    long long write_ = 0, recorded_ = 0;

    std::vector<float> window_;
    Grain grains_[kMaxGrains];
    Xorshift32 rng_{0x6C69676Bu};
    // Shatter / Arpeggio state
    int    shatterLeft_ = 0, shatterHits_ = 1;
    bool   shatterMute_ = false, shatterReverse_ = false;
    float  shatterRate_ = 1.0f;
    double shatterAnchor_ = 0.0;
    int    arpStep_ = 0;
    double arpAnchor_ = -1.0;
    double samplesToNext_ = 0.0;
    double stutterAnchor_ = -1.0;
    bool stutterReverse_ = false;

    // Effective (after-macro) values used by the grain helpers, set once per block.
    float effReverse_ = 0.0f, effDrift_ = 0.0f, effWidth_ = 0.0f;
    float lastShow_[kNumShow] = {-1.0f, -1.0f, -1.0f, -1.0f, -1.0f};
    std::atomic<bool> reportAllPending_{false};
    double animPhase_ = 0.0;
    float lastAnimSent_ = -1.0f;
    int   animSinceSend_ = 0;
    int   showSinceSend_ = 0;
    float lastFbL_ = 0.0f, lastFbR_ = 0.0f;
    OnePoleHP lowCutL_, lowCutR_;
    OnePoleLP highCutL_, highCutR_;
    LushReverb reverb_;
    Smoother mix_, volume_, feedback_, revAmount_;
};

MPC_PLUGIN_ENTRY(Grainbloom)
