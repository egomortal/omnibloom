#!/usr/bin/env python3
"""OMNI_COLOUR_FILTER_V1 (2026-11-16): "Colour filter" for colour-vision deficiency, over everything Omni shows.

What the user sees
  - Browser settings, right after the Night light rows:
        "Colour filter"   Off / Protanopia / Deuteranopia / Tritanopia / Greyscale / Invert   D-pad left/right or Cross
    The detail line says what the filter does, or, when the title's GPU present is not running, that it needs it (the
    choice is still saved).
  - Options > Quick toggles: a "Colour filter" tile (value = the filter). Cross turns it Off, or back to the last
    filter that was not Off (Deuteranopia by default, the most common deficiency).
  - Applied at once (no fade); saved in /data/omni/colour-filter.txt (omniIoQueue): filter, last.

The matrices (OmniColourFilter.h, row-major 3x4 affine maps over the canvas's stored, gamma-encoded RGB)
  Protanopia / Deuteranopia / Tritanopia: CORRECTION (daltonization), not simulation. The simulation matrices are
  Machado, Oliveira & Fernandes 2009 ("A Physiologically-based Model for Simulation of Color Vision Deficiency",
  IEEE TVCG 15(6)), severity 1.0; the correction is Fidaner, Lin & Ozguven's daltonize (2005): the information the
  viewer loses, err = c - S c, is shifted into the channels they still see, out = c + E err, so M = I + E (I - S) with
  E = [[0,0,0],[0.7,1,0],[0.7,0,1]] (protan, deutan) and [[1,0,0.7],[0,1,0.7],[0,0,0]] (tritan). S's rows sum to 1, so
  white, black and greys are kept. Machado's matrices are defined for linear RGB; here they are applied to the stored
  (gamma-encoded) values, the space Night light's pass already works in (one pass, no transfer-function math) -- an
  approximation, as in most browser-side daltonizers.
  Greyscale: Rec. 709 luma (0.2126, 0.7152, 0.0722) on the encoded values (luma Y' is defined on R'G'B').
  Invert: simple 1 - x per channel (offset row); NOT hue- or luminance-preserving ("smart invert" would need a hue
  rotation and still not keep luminance; kept simple).

Where it is applied: the title's GPU present (tools/apply_colour_filter_present.py) folds the filter into Night light's
one compute pass over the composed canvas: M = N F, o = N f (filter first, the warmth over it). One dispatch for both;
none while both are off. High contrast theme: the filter applies on top of it. HDR10 video runs are untouched (as Night
light), and so is everything when the GPU present is not running (SDL's CPU present).

Pure part: engine/entry/OmniColourFilter.h (no SDL / WebKit / Vulkan): settings file, matrices, CPU reference, texts.
Tested by tools/test_colour_filter.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_colour_filter.cpp
The present pass: tools/test_colour_filter_present.cpp (lavapipe).
Shell side: engine/entry/OmniColourFilterShell.h (included from OmniFeatures3.h after OmniNightLightShell.h);
omniCfTick from omniF3Tick (after omniNlTick): sends the matrix at start and after each change (one compare otherwise).

Row ids (unused in every apply_*.py and the engine tree; 940-943 + 945 Night light, 946 Performance overlay tile):
Browser settings 944 (omniCfRowId), quick tile 947 (omniCfQuickId); both dispatched next to Night light's, before the
">= 900" features-2 lines.
Anchors (exactly once each, all lines apply_night_light.py adds; MARK makes each file idempotent):
  OmniBrowser.cpp        the omni_gpu_present_night_ready weak declaration.
  OmniBrowserSettings.h  the omniNlSettingsInput declaration; the omniNlSettingsRows(p) row line; the Night light
                         dispatch line of omniFxSettingsInput.
  OmniQuickMenu.h        the omniNlQuickAction declaration; the omniNlQuickTiles(p) line; the omniNlQuickId group case;
                         the omniNlQuickAction(r.id) line of omniFxQuickInput.
  OmniFeatures3.h        the OmniNightLightShell.h include; the omniNlTick line of omniF3Tick.
Apply AFTER apply_night_light.py. Recipe: after apply_web_apps.py (the last feature line before apply_zerocopy_shell.py).
usage: apply_colour_filter.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_COLOUR_FILTER_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_COLOUR_FILTER_V1: the pure part of "Colour filter" (no SDL, no WebKit, no Vulkan): the settings file, the
// matrices, a CPU reference of the pass, and the texts. The shell side is OmniColourFilterShell.h; the filter itself is
// folded into Night light's GPU present pass (tools/apply_colour_filter_present.py). Sources of the matrices: see
// tools/apply_colour_filter.py. Tested on the host with g++ (tools/test_colour_filter.cpp).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>

namespace OmniColourFilter {

constexpr const char* kFileName = "colour-filter.txt";
constexpr long kMaxFileBytes = 1024;

enum Filter { kOff = 0, kProtanopia, kDeuteranopia, kTritanopia, kGreyscale, kInvert, kCount };

struct Settings {
    Filter filter = kOff;
    Filter last = kDeuteranopia;   // what the quick toggle turns back on (never kOff)
};

inline const char* name(Filter f)
{
    switch (f) {
    case kProtanopia: return "Protanopia";
    case kDeuteranopia: return "Deuteranopia";
    case kTritanopia: return "Tritanopia";
    case kGreyscale: return "Greyscale";
    case kInvert: return "Invert";
    default: return "Off";
    }
}
inline const char* key(Filter f)
{
    switch (f) {
    case kProtanopia: return "protanopia";
    case kDeuteranopia: return "deuteranopia";
    case kTritanopia: return "tritanopia";
    case kGreyscale: return "greyscale";
    case kInvert: return "invert";
    default: return "off";
    }
}
inline bool fromKey(const std::string& s, Filter& out)
{
    for (int i = 0; i < kCount; ++i)
        if (s == key(Filter(i))) { out = Filter(i); return true; }
    return false;
}

inline std::string serialize(const Settings& s)
{
    return std::string("# Omni colour filter (OMNI_COLOUR_FILTER_V1)\nfilter\t") + key(s.filter) + "\nlast\t"
        + key(s.last == kOff ? kDeuteranopia : s.last) + "\n";
}
// Unknown keys, bad values and comments are ignored (each bad value keeps its default).
inline Settings parse(const std::string& text)
{
    Settings s;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t e = text.find('\n', pos);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(pos, e - pos);
        pos = e + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line[0] == '#') continue;
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        const std::string k = line.substr(0, tab), v = line.substr(tab + 1);
        Filter f;
        if (k == "filter" && fromKey(v, f)) s.filter = f;
        else if (k == "last" && fromKey(v, f) && f != kOff) s.last = f;
    }
    return s;
}

// --- matrices ---------------------------------------------------------------------------------------------------
// Row-major 3x4 affine map: out_i = m[4i] r + m[4i+1] g + m[4i+2] b + m[4i+3], on the stored (gamma-encoded) values.
struct Affine { float m[12]; };
struct M3 { double a[3][3]; };

// Simulation of dichromacy, Machado, Oliveira & Fernandes 2009, severity 1.0 (their published table).
constexpr M3 kSimProtan { { { 0.152286, 1.052583, -0.204868 }, { 0.114503, 0.786281, 0.099216 }, { -0.003882, -0.048116, 1.051998 } } };
constexpr M3 kSimDeutan { { { 0.367322, 0.860646, -0.227968 }, { 0.280085, 0.672501, 0.047413 }, { -0.011820, 0.042940, 0.968881 } } };
constexpr M3 kSimTritan { { { 1.255528, -0.076749, -0.178779 }, { -0.078411, 0.930809, 0.147602 }, { 0.004733, 0.691367, 0.303900 } } };
// Daltonize error shift (Fidaner, Lin & Ozguven 2005): where the lost information goes.
constexpr M3 kShiftRedGreen { { { 0, 0, 0 }, { 0.7, 1, 0 }, { 0.7, 0, 1 } } };
constexpr M3 kShiftBlueYellow { { { 1, 0, 0.7 }, { 0, 1, 0.7 }, { 0, 0, 0 } } };
// Rec. 709 luma weights.
constexpr double kLumaR = 0.2126, kLumaG = 0.7152, kLumaB = 0.0722;

inline const M3* simulation(Filter f)
{
    return f == kProtanopia ? &kSimProtan : f == kDeuteranopia ? &kSimDeutan : f == kTritanopia ? &kSimTritan : nullptr;
}
// Correction: M = I + E (I - S).
inline M3 daltonize(const M3& sim, const M3& shift)
{
    M3 o {};
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 3; ++j) {
            double v = i == j ? 1.0 : 0.0;
            for (int k = 0; k < 3; ++k) v += shift.a[i][k] * ((k == j ? 1.0 : 0.0) - sim.a[k][j]);
            o.a[i][j] = v;
        }
    return o;
}
inline Affine affine(const M3& m, double offset = 0)
{
    Affine o {};
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) o.m[i * 4 + j] = float(m.a[i][j]);
        o.m[i * 4 + 3] = float(offset);
    }
    return o;
}
inline Affine identity() { return affine(M3 { { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } } }); }
// The filter's map (Off: identity; the shell sends nothing for Off).
inline Affine matrix(Filter f)
{
    switch (f) {
    case kProtanopia: return affine(daltonize(kSimProtan, kShiftRedGreen));
    case kDeuteranopia: return affine(daltonize(kSimDeutan, kShiftRedGreen));
    case kTritanopia: return affine(daltonize(kSimTritan, kShiftBlueYellow));
    case kGreyscale: {
        const M3 g { { { kLumaR, kLumaG, kLumaB }, { kLumaR, kLumaG, kLumaB }, { kLumaR, kLumaG, kLumaB } } };
        return affine(g);
    }
    case kInvert: return affine(M3 { { { -1, 0, 0 }, { 0, -1, 0 }, { 0, 0, -1 } } }, 1.0);
    default: return identity();
    }
}
// What the present computes when Night light (n: 3x3, row-major) is on too: out = n (F c + f).
inline Affine compose(const float* n, const Affine& f)
{
    Affine o {};
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j)
            o.m[i * 4 + j] = n[i * 3] * f.m[j] + n[i * 3 + 1] * f.m[4 + j] + n[i * 3 + 2] * f.m[8 + j];
        o.m[i * 4 + 3] = n[i * 3] * f.m[3] + n[i * 3 + 1] * f.m[7] + n[i * 3 + 2] * f.m[11];
    }
    return o;
}
// CPU reference of omni_colour_matrix.comp for one 8-bit pixel.
inline void applyPixel(const Affine& a, uint8_t& r, uint8_t& g, uint8_t& b)
{
    const float c[3] = { r / 255.0f, g / 255.0f, b / 255.0f };
    uint8_t o[3];
    for (int i = 0; i < 3; ++i) {
        const float v = a.m[i * 4] * c[0] + a.m[i * 4 + 1] * c[1] + a.m[i * 4 + 2] * c[2] + a.m[i * 4 + 3];
        o[i] = uint8_t(std::lround(std::clamp(v, 0.0f, 1.0f) * 255.0f));
    }
    r = o[0]; g = o[1]; b = o[2];
}

// --- controls -------------------------------------------------------------------------------------------------
inline Filter cycle(Filter f, int dir) { return Filter((int(f) + (dir < 0 ? kCount - 1 : 1)) % kCount); }
inline Settings setFilter(Settings s, Filter f) { s.filter = f; if (f != kOff) s.last = f; return s; }
// The quick tile: Off <-> the last filter that was not Off.
inline Settings quickToggle(Settings s) { return setFilter(s, s.filter == kOff ? (s.last == kOff ? kDeuteranopia : s.last) : kOff); }

// --- texts ------------------------------------------------------------------------------------------------------
inline std::string detail(Filter f, bool available)
{
    if (!available) return "Needs Omni's GPU display output, which is not running. Saved; it applies when that output is on";
    switch (f) {
    case kProtanopia: return "Corrects for red blindness: reds are shifted so they stand apart from greens";
    case kDeuteranopia: return "Corrects for green blindness: greens are shifted so they stand apart from reds";
    case kTritanopia: return "Corrects for blue blindness: blues are shifted so they stand apart from yellows";
    case kGreyscale: return "Shows everything in shades of grey";
    case kInvert: return "Inverts every colour: light pages become dark";
    default: return "Helps tell colours apart. Works with Night light and High contrast";
    }
}
inline std::string toggleNotice(const Settings& s, bool available)
{
    std::string t = s.filter == kOff ? std::string("Colour filter off") : std::string("Colour filter: ") + name(s.filter);
    if (s.filter != kOff && !available) t += " (needs Omni's GPU display output)";
    return t;
}

} // namespace OmniColourFilter
'''

SHELL = r'''// OMNI_COLOUR_FILTER_V1: "Colour filter" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniNightLightShell.h). The pure part is OmniColourFilter.h; the filter is folded into Night light's
// GPU present pass (omni_gpu_present_colour_filter, declared weak at file scope in OmniBrowser.cpp); the reasons are in
// tools/apply_colour_filter.py. Main thread only; the file is written by omniIoQueue.
#pragma once

namespace OCF = OmniColourFilter;
static OCF::Settings omniCf;
static bool omniCfLoaded = false;
static int omniCfSentFilter = -1;   // the filter the present has (-1: nothing sent yet)

static void omniCfLoad()
{
    if (omniCfLoaded) return;
    omniCfLoaded = true;
    FILE* f = fopen(omniData(OCF::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[512];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OCF::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniCf = OCF::parse(text);
}
static void omniCfWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OCF::kFileName), OCF::serialize(omniCf), false);
}
static bool omniCfAvailable()
{
    return omni_gpu_present_colour_filter_ready && omni_gpu_present_colour_filter && omni_gpu_present_colour_filter_ready() == 1;
}

// From omniF3Tick (every pass): one comparison unless the filter changed (or at start).
static void omniCfTick(uint32_t)
{
    if (!omni_gpu_present_colour_filter) return;   // a title without the pass
    omniCfLoad();
    if (omniCfSentFilter == int(omniCf.filter)) return;
    if (omniCf.filter == OCF::kOff) omni_gpu_present_colour_filter(nullptr);   // nothing recorded (unless Night light is on)
    else omni_gpu_present_colour_filter(OCF::matrix(omniCf.filter).m);
    omniCfSentFilter = int(omniCf.filter);
    omniShellDirty = true;   // present a frame with the new filter
}

// --- Browser settings row -----------------------------------------------------------------------------------------
static void omniCfSettingsRows(OmniFxPanel& p)
{
    omniCfLoad();
    OmniFxRow r; r.id = omniCfRowId; r.label = "Colour filter"; r.value = OCF::name(omniCf.filter); r.stepper = true;
    r.detail = OCF::detail(omniCf.filter, omniCfAvailable());
    p.rows.push_back(r);
}
static bool omniCfSettingsInput(int id, int b)
{
    if (id != omniCfRowId) return false;
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    if (b != SDL_CONTROLLER_BUTTON_A && !left && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    omniCfLoad();
    omniCf = OCF::setFilter(omniCf, OCF::cycle(omniCf.filter, left ? -1 : 1));
    omniCfWrite();
    if (omniCf.filter != OCF::kOff && !omniCfAvailable()) notice(OCF::toggleNotice(omniCf, false));
    return true;
}

// --- Options > Quick toggles tile ---------------------------------------------------------------------------------
static void omniCfQuickTiles(OmniFxPanel& p)
{
    omniCfLoad();
    OmniFxRow r; r.id = omniCfQuickId; r.label = "Colour filter"; r.value = OCF::name(omniCf.filter);
    p.rows.push_back(r);
}
static bool omniCfQuickAction(int id)
{
    if (id != omniCfQuickId) return false;
    omniCfLoad();
    omniCf = OCF::quickToggle(omniCf);
    omniCfWrite();
    notice(OCF::toggleNotice(omniCf, omniCfAvailable()));
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('extern "C" int omni_gpu_present_night_ready(void) __attribute__((weak));\n',
         'extern "C" int omni_gpu_present_night_ready(void) __attribute__((weak));\n'
         '#include "OmniColourFilter.h" // OMNI_COLOUR_FILTER_V1: Colour filter matrices, colour-filter.txt (pure)\n'
         '// OMNI_COLOUR_FILTER_V1: folded into Night light\'s present pass (tools/apply_colour_filter_present.py); absent in other titles.\n'
         'extern "C" int omni_gpu_present_colour_filter(const float* m) __attribute__((weak));\n'
         'extern "C" int omni_gpu_present_colour_filter_ready(void) __attribute__((weak));\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniNlSettingsInput(int id, int b);\n',
         'static bool omniNlSettingsInput(int id, int b);\n'
         'constexpr int omniCfRowId = 944; // OMNI_COLOUR_FILTER_V1 (OmniColourFilterShell.h)\n'
         'static void omniCfSettingsRows(OmniFxPanel& p);\n'
         'static bool omniCfSettingsInput(int id, int b);\n'),
        ('    omniNlSettingsRows(p); // OMNI_NIGHT_LIGHT_V1: Night light, warmth, from, until\n',
         '    omniNlSettingsRows(p); // OMNI_NIGHT_LIGHT_V1: Night light, warmth, from, until\n'
         '    omniCfSettingsRows(p); // OMNI_COLOUR_FILTER_V1: Colour filter\n'),
        ('    if (r.id >= omniNlRowMode && r.id <= omniNlRowEnd) return omniNlSettingsInput(r.id, b); // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n',
         '    if (r.id >= omniNlRowMode && r.id <= omniNlRowEnd) return omniNlSettingsInput(r.id, b); // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n'
         '    if (r.id == omniCfRowId) return omniCfSettingsInput(r.id, b); // OMNI_COLOUR_FILTER_V1 (before the >= 900 rows)\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniNlQuickAction(int id);\n',
         'static bool omniNlQuickAction(int id);\n'
         'constexpr int omniCfQuickId = 947; // OMNI_COLOUR_FILTER_V1 (OmniColourFilterShell.h): Quick toggles tile\n'
         'static void omniCfQuickTiles(OmniFxPanel& p);\n'
         'static bool omniCfQuickAction(int id);\n'),
        ('    omniNlQuickTiles(p); // OMNI_NIGHT_LIGHT_V1: Night light\n',
         '    omniNlQuickTiles(p); // OMNI_NIGHT_LIGHT_V1: Night light\n'
         '    omniCfQuickTiles(p); // OMNI_COLOUR_FILTER_V1: Colour filter\n'),
        ('    case omniNlQuickId: return 2; // OMNI_NIGHT_LIGHT_V1: Quick toggles\n',
         '    case omniNlQuickId: return 2; // OMNI_NIGHT_LIGHT_V1: Quick toggles\n'
         '    case omniCfQuickId: return 2; // OMNI_COLOUR_FILTER_V1: Quick toggles\n'),
        ('    if (omniNlQuickAction(r.id)) return true; // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n',
         '    if (omniNlQuickAction(r.id)) return true; // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n'
         '    if (omniCfQuickAction(r.id)) return true; // OMNI_COLOUR_FILTER_V1 (before the >= 900 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniNightLightShell.h" // OMNI_NIGHT_LIGHT_V1\n',
         '#include "OmniNightLightShell.h" // OMNI_NIGHT_LIGHT_V1\n'
         '#include "OmniColourFilterShell.h" // OMNI_COLOUR_FILTER_V1\n'),
        ('    omniNlTick(now);    // OMNI_NIGHT_LIGHT_V1: schedule check every second, the 2 s fade\n',
         '    omniNlTick(now);    // OMNI_NIGHT_LIGHT_V1: schedule check every second, the 2 s fade\n'
         '    omniCfTick(now);    // OMNI_COLOUR_FILTER_V1: sends the filter at start and after a change\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    if 'OMNI_NIGHT_LIGHT_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_NIGHT_LIGHT_V1 missing: apply_night_light.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniColourFilter.h', PURE, 'OmniNightLight.h'),
            write_new('OmniColourFilterShell.h', SHELL, 'OmniNightLightShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
