#!/usr/bin/env python3
"""OMNI_BG_AUDIO_V1 (2026-11-16): Browser settings > "Background audio": Off (default) / Keep playing audio.

What the user sees
  Browser settings, after "Captions":
      "Background audio"   Off                  detail: "On: sound plays on in other tabs (uses more memory)"
                           Keep playing audio   detail: "Video sound plays on in other tabs; uses more memory"
  Cross or D-pad left / right toggles; a notice confirms. It applies at once (within 2 s), no restart:
    Off (today's behaviour): leaving a tab drops its video plane at once; 1.5 s later a video there that uses the
      hardware decoder is paused and its decoder released (OMNI_TAB_MEDIA_RELEASE_V1). Audio-only media
      (<audio>, music sites without video) is never touched and already plays on.
    Keep playing audio: a video that is PLAYING AUDIBLY (has sound, not muted, volume above 0) when its tab goes to
      the background keeps playing: sound only, no picture, and it keeps its hardware decoder (one of the 4 decode
      channels, ~117 MiB of shell memory each: hence "uses more memory"). Paused, ended, muted or silent videos
      are still released after 1.5 s as before. Played again while hidden (Now playing, the page itself), a
      released video now opens its decoder again and plays on in the background (before: paused again at once);
      if no decode channel is free it is paused again and the next play tries again (at most once a second).
  Interplay (no shell changes needed, checked in the patched tree):
    - tab sound badge (OMNI_TAB_AUDIO_V1): WKPageGetMediaState of every tab, so a background tab playing shows the
      speaker; per-tab mute (WKPageSetMuted) makes the video inaudible, so it is paused + released after 1.5 s.
    - Now playing (OMNI_MEDIA_CONTROLS_V1): picks among all tabs by media state; play / pause / next reach a
      background tab by script. Pause there releases the decoder (memory back); Play opens it again (above).
    - sleep timer (OMNI_SMALL_COMFORTS_V1 / OMNI_SLEEP_TIMER_V1): omniSleepPauseAll scripts every tab, then mutes
      leftovers; a paused hidden video is then released.
    - per-tab volume (OMNI_TAB_VOLUME_V1): sets the elements' volume by script; volume 0 counts as inaudible.
    - tab unloading (OmniTabMemory.h): a tab whose media state says playing is never unloaded.

How
  The page processes already read /data/omni/tab-media-keep-audible.flag: OmniMedia::TabMedia::keepAudible()
  (engine/media/OmniTabMediaRelease.h, header-only, used by OmniProgressivePlayer / OmniMSEPlayer / OmniHlsPlayer in
  the web process), re-read at most every 2 s, asked only when a hidden playing audible video passes the 1.5 s
  grace. So the setting is just that flag: present = Keep playing audio. The shell creates / removes it (no IPC).
  The shell never read the flag before (grep of the patched tree: only OmniTabMediaRelease.h names it).
  OmniTabMediaRelease.h (TT tree, engine/media; the eboot workspace has no copy: only OmniHwService / OmniHdr* /
  OmniVideoStats there, so no "media" mode / $NE recipe line): Gate::tick() becomes a call of the new
  Gate::decide(..., on, keep) with enabled() / keepAudible() passed in as callables (still asked only when needed;
  host tests pass their own), and the hidden + released + playing case answers Reacquire instead of Repause when
  audible and keepAudible() (retryAt gates a failed try). With the flag absent every answer is unchanged.

Pure part: engine/entry/OmniBgAudio.h (texts, flag name, row id). Tested with the Gate by tools/test_bg_audio.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry -I<tree>/engine/media test_bg_audio.cpp -o t && ./t <tree>
Shell side: engine/entry/OmniBgAudioShell.h (included from OmniFeatures3.h after OmniPadFeedbackShell.h).
Storage: /data/omni/tab-media-keep-audible.flag (present = On). Ids: Browser settings row 835; alias OBGA, prefix
omniBga (grep of every apply_*.py and the tree, 2026-11-16: 834, 836-839, 845-899, 900+ and the button map's row taken; checked again
before the first apply: refuses if another file uses them).

Anchors (exactly once each; MARK makes each file idempotent):
  entry/OmniBrowser.cpp        the OmniPadFeedback.h include line (pure include after it).
  entry/OmniBrowserSettings.h  "static bool omniPfSettingsInput(int b);" (declarations after it); the
                               omniCcsSettingsRow(p) line (row after it); the omniPfRowId input line (ours before it).
  entry/OmniFeatures3.h        the OmniPadFeedbackShell.h include line.
  media/OmniTabMediaRelease.h  the "...tab-media-keep-audible.flag exists;" comment line; Gate::tick's head with its
                               "if (visible) {" line; the "if (isReleased) return paused ? ..." line; the grace line
                               with the keepAudible line after it.
Apply AFTER apply_pad_feedback.py and apply_caption_style.py (their lines are anchors); last in the recipe is fine.
usage: apply_bg_audio.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_BG_AUDIO_V1'
if len(sys.argv) != 2:
    sys.exit('usage: apply_bg_audio.py <engine tree>')
root = Path(sys.argv[1]) / 'engine'
TAKEN = (r'(?<![\w.])835(?![\w.])', r'\bOBGA\b', r'\bomniBga[A-Z]', r'\bOmniBgAudio')

PURE = r'''// OMNI_BG_AUDIO_V1: the pure part of Browser settings > "Background audio" (no SDL, no WebKit). The shell side is
// OmniBgAudioShell.h; the reasons are in tools/apply_bg_audio.py. Tested on the host with g++ (test_bg_audio.cpp).
// The page processes read the flag themselves (../media/OmniTabMediaRelease.h, keepAudible(): at most every 2 s).
#pragma once

namespace OmniBgAudio {

constexpr const char* kFlagName = "tab-media-keep-audible.flag";   // in /data/omni; present: Keep playing audio
constexpr const char* kFlagPath = "/data/omni/tab-media-keep-audible.flag";   // what OmniTabMediaRelease.h reads
constexpr int kRowId = 835;              // Browser settings row
constexpr unsigned kApplyMs = 2000;      // the page processes see a change within this

inline const char* settingLabel() { return "Background audio"; }
inline const char* settingValue(bool on) { return on ? "Keep playing audio" : "Off"; }
inline const char* settingDetail(bool on)
{
    return on ? "Video sound plays on in other tabs; uses more memory" : "On: sound plays on in other tabs (uses more memory)";
}
inline const char* toggledNotice(bool on)
{
    return on ? "Background audio on: video in other tabs keeps playing its sound (uses more memory)"
              : "Background audio off: video in other tabs pauses";
}
inline const char* failedNotice() { return "Background audio: couldn't save the setting"; }

}
'''

SHELL = r'''// OMNI_BG_AUDIO_V1: Browser settings > "Background audio" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace) after OmniPadFeedbackShell.h. The pure part is OmniBgAudio.h; the reasons are
// in tools/apply_bg_audio.py. Main thread only. The flag is the only state: the page processes read it themselves
// (OmniTabMediaRelease.h, every <= 2 s), so the row reads it too (one stat per settings build), nothing is cached.
#pragma once

namespace OBGA = OmniBgAudio;
static_assert(OBGA::kRowId == omniBgaRowId, "OMNI_BG_AUDIO_V1: row id");

static bool omniBgaOn() { return access(omniData(OBGA::kFlagName).c_str(), F_OK) == 0; }

static void omniBgaSettingsRow(OmniFxPanel& p)
{
    const bool on = omniBgaOn();
    OmniFxRow r; r.id = omniBgaRowId; r.label = OBGA::settingLabel(); r.value = OBGA::settingValue(on);
    r.stepper = true; r.detail = OBGA::settingDetail(on);
    p.rows.push_back(r);
}
static bool omniBgaSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string flag = omniData(OBGA::kFlagName);
    const bool on = !omniBgaOn();
    if (on) { if (FILE* f = fopen(flag.c_str(), "w")) { fputs("1\n", f); fclose(f); } }
    else unlink(flag.c_str());
    const bool ok = omniBgaOn() == on;
    notice(ok ? OBGA::toggledNotice(on) : OBGA::failedNotice());
    fprintf(stderr, "OMNI BGAUDIO: setting %s%s\n", on ? "keep playing audio" : "off", ok ? "" : " (flag write failed)");
    fflush(stderr);
    return true;
}
'''

EDITS = {
    'entry/OmniBrowser.cpp': [
        ('#include "OmniPadFeedback.h" // OMNI_PAD_FEEDBACK_V1: Controller light & rumble (pure)\n',
         '#include "OmniPadFeedback.h" // OMNI_PAD_FEEDBACK_V1: Controller light & rumble (pure)\n'
         '#include "OmniBgAudio.h" // OMNI_BG_AUDIO_V1: Background audio setting (pure)\n'),
    ],
    'entry/OmniBrowserSettings.h': [
        ('static bool omniPfSettingsInput(int b);\n',
         'static bool omniPfSettingsInput(int b);\n'
         'constexpr int omniBgaRowId = 835; // OMNI_BG_AUDIO_V1 (OmniBgAudioShell.h): Background audio\n'
         'static void omniBgaSettingsRow(OmniFxPanel& p);\n'
         'static bool omniBgaSettingsInput(int b);\n'),
        ('    omniCcsSettingsRow(p); // OMNI_CAPTION_STYLE_V1: Captions (opens its panel)\n',
         '    omniCcsSettingsRow(p); // OMNI_CAPTION_STYLE_V1: Captions (opens its panel)\n'
         '    omniBgaSettingsRow(p); // OMNI_BG_AUDIO_V1: Background audio (Off / Keep playing audio)\n'),
        ('    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n',
         '    if (r.id == omniBgaRowId) return omniBgaSettingsInput(b); // OMNI_BG_AUDIO_V1\n'
         '    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n'),
    ],
    'entry/OmniFeatures3.h': [
        ('#include "OmniPadFeedbackShell.h" // OMNI_PAD_FEEDBACK_V1\n',
         '#include "OmniPadFeedbackShell.h" // OMNI_PAD_FEEDBACK_V1\n'
         '#include "OmniBgAudioShell.h" // OMNI_BG_AUDIO_V1\n'),
    ],
    'media/OmniTabMediaRelease.h': [
        ('//     it plays audibly and /data/omni/tab-media-keep-audible.flag exists;\n',
         '//     it plays audibly and /data/omni/tab-media-keep-audible.flag exists;\n'
         '//     OMNI_BG_AUDIO_V1: that flag is Browser settings > "Background audio" (entry/OmniBgAudio.h). With it, a\n'
         '//     released video played again while hidden (Now playing, the page) opens its stream again and plays on.\n'),
        ('    Act tick(double now, bool visible, bool hwVideo, bool paused, bool audible)\n'
         '    {\n'
         '        if (visible) {\n',
         '    Act tick(double now, bool visible, bool hwVideo, bool paused, bool audible)\n'
         '    {\n'
         '        return decide(now, visible, hwVideo, paused, audible, [] { return enabled(); }, [] { return keepAudible(); });\n'
         '    }\n'
         '    // OMNI_BG_AUDIO_V1: tick() with the two switches passed in (host tests); each is still asked only when needed.\n'
         '    template<typename On, typename Keep>\n'
         '    Act decide(double now, bool visible, bool hwVideo, bool paused, bool audible, On on, Keep keep)\n'
         '    {\n'
         '        if (visible) {\n'),
        ('        if (isReleased) return paused ? Act::None : Act::Repause;\n',
         '        if (isReleased) {\n'
         '            if (paused) return Act::None;\n'
         '            // OMNI_BG_AUDIO_V1: played again while hidden with "Background audio" on: open the stream again and\n'
         '            // play on hidden. A failed try (no free channel: retryLater) pauses it again until the next play.\n'
         '            if (audible && keep()) return now >= retryAt ? Act::Reacquire : Act::Repause;\n'
         '            return Act::Repause;\n'
         '        }\n'),
        ('        if (!hwVideo || exempt || now - hiddenSince < graceMs || !enabled()) return Act::None;\n'
         '        if (!paused && audible && keepAudible()) return Act::None;\n',
         '        if (!hwVideo || exempt || now - hiddenSince < graceMs || !on()) return Act::None;\n'
         '        if (!paused && audible && keep()) return Act::None; // OMNI_BG_AUDIO_V1: on() / keep() = enabled() / keepAudible()\n'),
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


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
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
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
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
    places = [p for d in ('entry', 'media') for p in (root / d).iterdir()
              if p.suffix in ('.h', '.cpp', '.inc') and p.name not in ('OmniBgAudio.h', 'OmniBgAudioShell.h')]
    places += [p for p in me.parent.glob('apply_*.py') if p.resolve() != me and p.name != 'apply_controls_help.py'
        and MARK not in p.read_text(encoding='utf-8', errors='replace')]   # OMNI_SIBLING_SKIP: guide / dependent patches
    for p in places:
        s = p.read_bytes().decode('utf-8', 'replace')
        if p.suffix == '.py':   # sibling script: names in its code only; the row id counts in the engine tree only
            s = code_only(s)
        else:
            s = cpp_code(s)
        for pat in (TAKEN[1:] if p.suffix == '.py' else TAKEN[:1] if p.name in GUIDE else TAKEN):
            m = re.search(pat, s)
            if m:
                sys.exit('%s already uses %r (line %d): pick other ids' % (p.name, m.group(0), s.count('\n', 0, m.start()) + 1))


def main():
    for f, need, tool in (('entry/OmniBrowserSettings.h', 'OMNI_PAD_FEEDBACK_V1', 'apply_pad_feedback.py'),
                          ('entry/OmniBrowserSettings.h', 'OMNI_CAPTION_STYLE_V1', 'apply_caption_style.py'),
                          ('entry/OmniFeatures3.h', 'OMNI_PAD_FEEDBACK_V1', 'apply_pad_feedback.py'),
                          ('media/OmniTabMediaRelease.h', 'OMNI_TAB_MEDIA_RELEASE_V1', 'the tab media release base')):
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('entry/OmniBgAudio.h', PURE, 'entry/OmniPadFeedback.h'),
            write_new('entry/OmniBgAudioShell.h', SHELL, 'entry/OmniPadFeedbackShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
