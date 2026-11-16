#!/usr/bin/env python3
"""OMNI_VIDEO_ENHANCE_V1 (2026-11-16), shell side: Browser settings > "Video upscaling": Off (default) / Smooth / Sharp.

What the user sees
  Browser settings, after "Background audio":
      "Video upscaling"   Off      detail: "Video shown larger than its own size: nearest pixel (as before)"
                          Smooth   detail: "Sharper bicubic enlargement, smooth colour, no halos"
                          Sharp    detail: "Smooth plus extra detail; best for 720p and lower"
  Cross or D-pad right steps forward (Off > Smooth > Sharp > Off), D-pad left steps back; a notice confirms. It applies
  to the next video picture (no restart). Only video shown LARGER than its own size changes (e.g. 1080p on a 4K TV,
  720p full screen); 1:1, smaller, HDR and CPU-converted video are unchanged.

How
  The work is in the video module (apply_video_enhance_media.py: OmniGpuVideo + the V10 conversion shader). The shell
  saves the level in /data/omni/video-enhance.txt and hands it over with omni_gpu_video_set_enhance(level) (a weak
  symbol: a title without the media patch just keeps nearest-pixel). omniVenTick (from omniF3Tick, after omniNlTick)
  pushes the saved level once at start; the row pushes each change.

Pure part: engine/entry/OmniVideoEnhance.h (texts, file format, steps). Tested by tools/test_video_enhance_shell.cpp:
    g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry test_video_enhance_shell.cpp -o t && ./t
Shell side: engine/entry/OmniVideoEnhanceShell.h (included from OmniFeatures3.h after OmniBgAudioShell.h).
Ids: Browser settings row 8463; alias OVEN, prefix omniVen (unused in every apply_*.py and the tree, 2026-11-16).
Anchors (exactly once each):
  entry/OmniBrowser.cpp        the OmniBgAudio.h include line.
  entry/OmniBrowserSettings.h  "static bool omniBgaSettingsInput(int b);" (declarations after it); the
                               omniBgaSettingsRow(p) line (row after it); the omniBgaRowId input line (ours before it).
  entry/OmniFeatures3.h        the OmniBgAudioShell.h include line; omniF3Tick's omniNlTick line (omniVenTick after it).
Apply AFTER apply_bg_audio.py and apply_night_light.py (their lines are anchors).
usage: apply_video_enhance.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_VIDEO_ENHANCE_V1'
if len(sys.argv) != 2:
    sys.exit('usage: apply_video_enhance.py <engine tree>')
root = Path(sys.argv[1]) / 'engine'
TAKEN = (r'(?<![\w.])8463(?![\w.])', r'\bOVEN\b', r'\bomniVen[A-Z]', r'\bOmniVideoEnhance')

PURE = r'''// OMNI_VIDEO_ENHANCE_V1: the pure part of Browser settings > "Video upscaling" (no SDL, no WebKit). The shell side is
// OmniVideoEnhanceShell.h; the reasons are in tools/apply_video_enhance.py. Tested on the host (test_video_enhance_shell.cpp).
#pragma once
#include <cstdio>
#include <cstdlib>

// The video module's setter (engine/media/OmniGpuVideo.cpp, apply_video_enhance_media.py). Weak: absent = nullptr.
extern "C" void omni_gpu_video_set_enhance(int level) __attribute__((weak));

namespace OmniVideoEnhance {

constexpr const char* kPath = "/data/omni/video-enhance.txt";   // one line: 0, 1 or 2
constexpr int kRowId = 8463;   // Browser settings row
constexpr int kLevels = 3;

inline int clampLevel(int v) { return v < 0 ? 0 : v >= kLevels ? kLevels - 1 : v; }
inline int step(int level, int dir) { return (clampLevel(level) + (dir < 0 ? kLevels - 1 : 1)) % kLevels; }
// The file's first number; anything else (missing, empty, junk) is Off.
inline int parse(const char* text)
{
    if (!text) return 0;
    while (*text == ' ' || *text == '\t') ++text;
    if (*text < '0' || *text > '9') return 0;
    return clampLevel(int(strtol(text, nullptr, 10)));
}
inline const char* settingLabel() { return "Video upscaling"; }
inline const char* settingValue(int level)
{
    static const char* const v[kLevels] = { "Off", "Smooth", "Sharp" };
    return v[clampLevel(level)];
}
inline const char* settingDetail(int level)
{
    static const char* const d[kLevels] = { "Video shown larger than its own size: nearest pixel (as before)",
                                            "Sharper bicubic enlargement, smooth colour, no halos",
                                            "Smooth plus extra detail; best for 720p and lower" };
    return d[clampLevel(level)];
}
inline const char* changedNotice(int level)
{
    static const char* const n[kLevels] = { "Video upscaling off", "Video upscaling: Smooth (video shown larger than its size)",
                                            "Video upscaling: Sharp (video shown larger than its size)" };
    return n[clampLevel(level)];
}
inline const char* failedNotice() { return "Video upscaling: couldn't save the setting"; }

}
'''

SHELL = r'''// OMNI_VIDEO_ENHANCE_V1: Browser settings > "Video upscaling" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace) after OmniBgAudioShell.h. Pure part: OmniVideoEnhance.h. Main thread only.
#pragma once

namespace OVEN = OmniVideoEnhance;
static_assert(OVEN::kRowId == omniVenRowId, "OMNI_VIDEO_ENHANCE_V1: row id");

static int omniVenLevel = -1;        // -1: not read yet
static bool omniVenPushed = false;   // the saved level reached the video module

static int omniVenGet()
{
    if (omniVenLevel < 0) {
        char b[16] = { 0 };
        if (FILE* f = fopen(OVEN::kPath, "r")) { if (!fgets(b, sizeof b, f)) b[0] = 0; fclose(f); }
        omniVenLevel = OVEN::parse(b);
    }
    return omniVenLevel;
}
static void omniVenPush()
{
    if (omni_gpu_video_set_enhance) omni_gpu_video_set_enhance(omniVenGet());
    omniVenPushed = true;
}
// From omniF3Tick: once, at start (one comparison afterwards).
static void omniVenTick(uint32_t)
{
    if (omniVenPushed) return;
    omniVenPush();
    fprintf(stderr, "OMNI VIDEOENHANCE: level %d at start%s\n", omniVenGet(), omni_gpu_video_set_enhance ? "" : " (no video module support)");
    fflush(stderr);
}
static void omniVenSettingsRow(OmniFxPanel& p)
{
    const int level = omniVenGet();
    OmniFxRow r; r.id = omniVenRowId; r.label = OVEN::settingLabel(); r.value = OVEN::settingValue(level);
    r.stepper = true; r.detail = OVEN::settingDetail(level);
    p.rows.push_back(r);
}
static bool omniVenSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const int level = OVEN::step(omniVenGet(), b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 : 1);
    bool ok = false;
    if (FILE* f = fopen(OVEN::kPath, "w")) { ok = fprintf(f, "%d\n", level) > 0; ok = (fclose(f) == 0) && ok; }
    omniVenLevel = level;   // applies now even if saving failed (said so)
    omniVenPush();
    notice(ok ? OVEN::changedNotice(level) : OVEN::failedNotice());
    fprintf(stderr, "OMNI VIDEOENHANCE: level %d%s\n", level, ok ? "" : " (save failed)");
    fflush(stderr);
    return true;
}
'''

EDITS = {
    'entry/OmniBrowser.cpp': [
        ('#include "OmniBgAudio.h" // OMNI_BG_AUDIO_V1: Background audio setting (pure)\n',
         '#include "OmniBgAudio.h" // OMNI_BG_AUDIO_V1: Background audio setting (pure)\n'
         '#include "OmniVideoEnhance.h" // OMNI_VIDEO_ENHANCE_V1: Video upscaling setting (pure)\n'),
    ],
    'entry/OmniBrowserSettings.h': [
        ('static bool omniBgaSettingsInput(int b);\n',
         'static bool omniBgaSettingsInput(int b);\n'
         'constexpr int omniVenRowId = 8463; // OMNI_VIDEO_ENHANCE_V1 (OmniVideoEnhanceShell.h): Video upscaling\n'
         'static void omniVenSettingsRow(OmniFxPanel& p);\n'
         'static bool omniVenSettingsInput(int b);\n'),
        ('    omniBgaSettingsRow(p); // OMNI_BG_AUDIO_V1: Background audio (Off / Keep playing audio)\n',
         '    omniBgaSettingsRow(p); // OMNI_BG_AUDIO_V1: Background audio (Off / Keep playing audio)\n'
         '    omniVenSettingsRow(p); // OMNI_VIDEO_ENHANCE_V1: Video upscaling (Off / Smooth / Sharp)\n'),
        ('    if (r.id == omniBgaRowId) return omniBgaSettingsInput(b); // OMNI_BG_AUDIO_V1\n',
         '    if (r.id == omniVenRowId) return omniVenSettingsInput(b); // OMNI_VIDEO_ENHANCE_V1\n'
         '    if (r.id == omniBgaRowId) return omniBgaSettingsInput(b); // OMNI_BG_AUDIO_V1\n'),
    ],
    'entry/OmniFeatures3.h': [
        ('#include "OmniBgAudioShell.h" // OMNI_BG_AUDIO_V1\n',
         '#include "OmniBgAudioShell.h" // OMNI_BG_AUDIO_V1\n'
         '#include "OmniVideoEnhanceShell.h" // OMNI_VIDEO_ENHANCE_V1\n'),
        ('    omniNlTick(now);    // OMNI_NIGHT_LIGHT_V1: schedule check every second, the 2 s fade\n',
         '    omniNlTick(now);    // OMNI_NIGHT_LIGHT_V1: schedule check every second, the 2 s fade\n'
         '    omniVenTick(now);   // OMNI_VIDEO_ENHANCE_V1: the saved Video upscaling level to the video module, once\n'),
    ],
}


def variants(old0, s):
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


GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before the first apply: no engine file and no other apply_*.py may use our row id / names."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS):
        return
    me = Path(__file__).resolve()
    places = [p for p in (root / 'entry').iterdir()
              if p.suffix in ('.h', '.cpp', '.inc') and p.name not in ('OmniVideoEnhance.h', 'OmniVideoEnhanceShell.h')]
    places += [p for p in me.parent.glob('apply_*.py') if p.resolve() != me and p.name not in ('apply_controls_help.py', 'apply_video_enhance_media.py')
               and MARK not in p.read_text(encoding='utf-8', errors='replace')]   # guide / dependent patches
    for p in places:
        s = p.read_bytes().decode('utf-8', 'replace')
        s = code_only(s) if p.suffix == '.py' else cpp_code(s)
        for pat in (TAKEN[1:] if p.suffix == '.py' else TAKEN[:1] if p.name in GUIDE else TAKEN):
            m = re.search(pat, s)
            if m:
                sys.exit('%s already uses %r (line %d): pick other ids' % (p.name, m.group(0), s.count('\n', 0, m.start()) + 1))


def main():
    for f, need, tool in (('entry/OmniBrowserSettings.h', 'OMNI_BG_AUDIO_V1', 'apply_bg_audio.py'),
                          ('entry/OmniFeatures3.h', 'OMNI_BG_AUDIO_V1', 'apply_bg_audio.py'),
                          ('entry/OmniFeatures3.h', 'OMNI_NIGHT_LIGHT_V1', 'apply_night_light.py')):
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    ids_free()
    for name, edits in EDITS.items():
        check(name, edits)
    msgs = [write_new('entry/OmniVideoEnhance.h', PURE, 'entry/OmniBgAudio.h'),
            write_new('entry/OmniVideoEnhanceShell.h', SHELL, 'entry/OmniBgAudioShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
