#!/usr/bin/env python3
"""OMNI_SLEEP_END_V1 (2026-11-16): Sleep timer end action - what happens when the sleep timer's time is up.

What the user sees
  - The Sleep timer chooser (Options > "Sleep timer", Now playing > "Sleep timer"; OMNI_SLEEP_TIMER_V1) has a last row
        "When time is up"     Pause playback / Pause and dim the screen / Pause and close Omni
    D-pad left / right steps it, Cross steps forward (wraps); the chooser stays open. Its detail line says what the
    choice does. Saved in /data/omni/sleep-timer.txt ("end=pause|dim|close", omniIoQueue); read once, at the first
    use. The timer itself is still not kept across restarts (as before); only this choice is.
  - Time up (the countdown's 10 s fade or the end of the watched video) always pauses first (omniStFire, unchanged:
    pause script per tab + the mute of still-playing tabs), then:
      Pause:            nothing more (as today).
      Pause and dim:    the whole screen goes 80 % darker. Any controller button, key or mouse button removes it;
                        that press does nothing else (its release is swallowed too). Notice: "Welcome back".
                        The triggers (L2 / R2 are axes) and the sticks do not wake it.
      Pause and close:  notice "Sleep timer: closing Omni in 10 s. Press any button to stay"; any button within
                        those 10 s keeps Omni open ("Sleep timer: Omni stays open"). Then Omni quits through its
                        normal exit: running = false, the same path as Options > "Exit Omni" (OmniQuickMenu.h:
                        omniAsk(...) -> running = false). The shutdown block in tick() closes every page, stops
                        the audio relay and pad feedback, runs omniEverydayShutdown() (last session save +
                        omniIoFlush + OMNI_STARTUP_CHOICE_V1's clean-exit marker, so the tabs come back next time
                        and no "didn't close properly" prompt shows), stops the presenter, SDL_Quit, and then
                        sceSystemServiceLoadExec("exit", nullptr) (already imported at file scope), which returns
                        to the PS5 home screen. No process is killed.

How the dim is drawn (the cheapest correct place)
  - With the title's GPU present night pass ready (omniNlAvailable(), OMNI_NIGHT_LIGHT_V1): the pass's 3x3 matrix
    becomes 0.2 x the Night light's current matrix (identity when Night light is off). That darkens everything the
    present composes: shell, page (also the zero-copy page) and SDR video runs. On wake the Night light's own
    matrix goes back (or nullptr: no pass). Night light changes while dimmed (its fade / schedule) are followed:
    omniSeTick runs after omniNlTick in omniF3Tick and re-sends when the Night light sent something new.
  - Without it (older title / CPU present): the SDL canvas is darkened in place after everything else (pointer
    included) with omniDarkenPx (k = 51/256, 80 %), not omniRectPx (High contrast would make a translucent
    rectangle solid). The page rows of a zero-copy page are holes the GPU fills; darkening writes them opaque, so
    there the page area simply goes black. A layer in omniOverlayLayers() is "open" while dimmed: no regional
    draw is planned (the whole frame is darkened each draw) and no pointer event reaches the page.
  - Only drawn while dimmed; the screen is otherwise idle (playback is paused), so the cost is nil in practice.

Pure part: engine/entry/OmniSleepEnd.h (no SDL / WebKit): actions, settings file parse / serialize, row texts,
the dim matrix, the state (Idle / Dimmed / Closing) with wake and the close countdown.
Tested by tools/test_sleep_end.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_sleep_end.cpp
Shell side: engine/entry/OmniSleepEndShell.h, included from OmniFeatures3.h just before OmniSleepTimerShell.h
(after OmniNightLightShell.h: it uses omniNlAvailable / omniNlSent / omniNlLastSent).

Row id: 7336 (omniSeRowId, a row of the chooser panel omniStKind 7330).
Anchors (exactly once each; MARK makes each file idempotent; insert-before / insert-after):
  OmniBrowser.cpp           the OmniSleepTimer.h include line (pure include after it); the sleep timer's omniStDrawTopBar declaration (declarations after it); the
                            omniSleepWake(event.type) line of the event loop (the wake check after it); the
                            omniDrawPointer() line of the full draw (the software dim after it).
  OmniFeatures3.h           the OmniSleepTimerShell.h include line (shell include before it); the omniStTick(now)
                            line of omniF3Tick (omniSeTick after it).
  OmniSleepTimerShell.h     the "playback stopped" fprintf of omniStFire (the end action after it); the Off row of
                            omniStBuild (the "When time is up" row after it); the "!= SDL_CONTROLLER_BUTTON_A" line
                            of omniStInput (this row's input before it). apply_sleep_timer.py rewrites that header
                            when it differs, so run this AFTER it (it re-applies to that file then).
Apply AFTER apply_sleep_timer.py and apply_night_light.py.
usage: apply_sleep_end.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SLEEP_END_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

IDS = ('7336',)
NAMES = ('OmniSleepEnd', r'\bomniSe[A-Z_]\w*', r'\bOSE\b', r'sleep-timer\.txt', 'OMNI_SLEEP_END')

PURE = r'''// OMNI_SLEEP_END_V1: the pure part of the Sleep timer's end action (no SDL, no WebKit): Pause / Pause and dim /
// Pause and close Omni, its settings file, the dim matrix and the wake / close countdown. The shell side is
// OmniSleepEndShell.h; the reasons are in tools/apply_sleep_end.py. Times are SDL_GetTicks() milliseconds (uint32_t,
// compared wrap-safe). Tested with g++ (test_sleep_end.cpp).
#pragma once
#include <cstdint>
#include <string>

namespace OmniSleepEnd {

enum Action { kPause = 0, kDim = 1, kClose = 2 };
constexpr int kActions = 3;
constexpr const char* kFileName = "sleep-timer.txt";
constexpr long kMaxFileBytes = 4096;
constexpr uint32_t kCloseDelayMs = 10000;
constexpr float kDimKeep = 0.2f;          // 80 % darker
constexpr uint32_t kDimDarken = 205;      // omniDarkenPx: channels x (256 - 205) / 256 = x 0.199

inline bool reached(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }
inline int clampAction(int a) { return a == kDim || a == kClose ? a : kPause; }
inline int cycle(int a, int dir) { return ((clampAction(a) + (dir < 0 ? -1 : 1)) % kActions + kActions) % kActions; }

inline const char* key(int a) { return a == kDim ? "dim" : a == kClose ? "close" : "pause"; }
// "end=pause|dim|close" (one line; anything else, unknown keys or a broken file: Pause).
inline int parse(const std::string& text)
{
    int a = kPause;
    size_t at = 0;
    while (at <= text.size()) {
        size_t nl = text.find('\n', at);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(at, nl - at);
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ' || line.back() == '\t')) line.pop_back();
        if (line.rfind("end=", 0) == 0) {
            const std::string v = line.substr(4);
            a = v == "dim" ? kDim : v == "close" ? kClose : kPause;
        }
        at = nl + 1;
    }
    return a;
}
inline std::string serialize(int a) { return std::string("end=") + key(clampAction(a)) + "\n"; }

// --- texts -------------------------------------------------------------------------------------------------------
inline const char* rowLabel() { return "When time is up"; }
inline std::string value(int a)
{
    switch (clampAction(a)) {
    case kDim: return "Pause and dim the screen";
    case kClose: return "Pause and close Omni";
    default: return "Pause playback";
    }
}
inline std::string detail(int a)
{
    switch (clampAction(a)) {
    case kDim: return "Playback pauses and the screen goes dark. Any button brings it back";
    case kClose: return "Playback pauses, then Omni closes and the PS5 home screen shows. Your tabs are saved";
    default: return "Playback pauses in every tab";
    }
}
inline std::string closeNotice() { return "Sleep timer: closing Omni in " + std::to_string(kCloseDelayMs / 1000) + " s. Press any button to stay"; }
inline std::string stayNotice() { return "Sleep timer: Omni stays open"; }
inline std::string wakeNotice() { return "Welcome back"; }
inline std::string closingNotice() { return "Sleep timer: closing Omni"; }

// The present pass's matrix while dimmed: kDimKeep x the Night light's matrix (row-major 3x3).
inline void dimMatrix(const float* base, float* out)
{
    for (int i = 0; i < 9; ++i) out[i] = (base ? base[i] : (i % 4 == 0 ? 1.f : 0.f)) * kDimKeep;
}

// --- state -------------------------------------------------------------------------------------------------------
enum class Phase { Idle, Dimmed, Closing };
enum class Woke { None, Undimmed, Stayed };
class State {
public:
    Phase phase() const { return phase_; }
    bool active() const { return phase_ != Phase::Idle; }
    bool dimmed() const { return phase_ == Phase::Dimmed; }
    bool closing() const { return phase_ == Phase::Closing; }
    // Time is up (after the pause): what to do for action a.
    void fired(int a, uint32_t now)
    {
        a = clampAction(a);
        if (a == kDim) phase_ = Phase::Dimmed;
        else if (a == kClose) { phase_ = Phase::Closing; closeAt_ = now + kCloseDelayMs; }
        else phase_ = Phase::Idle;
    }
    // A button: the dim goes / the close is called off.
    Woke wake()
    {
        const Phase p = phase_;
        phase_ = Phase::Idle;
        return p == Phase::Dimmed ? Woke::Undimmed : p == Phase::Closing ? Woke::Stayed : Woke::None;
    }
    // True once, when the close countdown is over (the state is Idle then).
    bool closeDue(uint32_t now)
    {
        if (phase_ != Phase::Closing || !reached(now, closeAt_)) return false;
        phase_ = Phase::Idle;
        return true;
    }
    // Whole seconds left of the close countdown (rounded up), 0 otherwise.
    int closeSecondsLeft(uint32_t now) const
    {
        if (phase_ != Phase::Closing) return 0;
        const int32_t left = int32_t(closeAt_ - now);
        return left <= 0 ? 0 : int((uint32_t(left) + 999u) / 1000u);
    }

private:
    Phase phase_ = Phase::Idle;
    uint32_t closeAt_ = 0;
};

} // namespace OmniSleepEnd
'''

SHELL = r'''// OMNI_SLEEP_END_V1: the Sleep timer's end action (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniNightLightShell.h, just before OmniSleepTimerShell.h, which calls omniSeFired and
// omniSeRow / omniSeRowInput). The pure part is OmniSleepEnd.h; the reasons are in tools/apply_sleep_end.py.
// Main thread only; the choice is written by omniIoQueue. Closing Omni = running = false (the Exit Omni path).
#pragma once

namespace OSE = OmniSleepEnd;
constexpr int omniSeRowId = 7336;          // the chooser's "When time is up" row
static int omniSeAction = OSE::kPause;
static bool omniSeLoaded = false;
static OSE::State omniSeState;
static int omniSeSwallow = -1;             // the controller button whose release is swallowed (it woke the dim)
static bool omniSeGpuDim = false;          // the present pass carries the dim matrix
static bool omniSeNlSentSeen = false;      // the Night light's state when the dim matrix was sent
static ONL::Mat omniSeNlSeen = ONL::identity();

static void omniSeLoad()
{
    if (omniSeLoaded) return;
    omniSeLoaded = true;
    FILE* f = fopen(omniData(OSE::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[512];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OSE::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniSeAction = OSE::parse(text);
}
static void omniSeWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OSE::kFileName), OSE::serialize(omniSeAction), false);
}

// omniStFire, after the pause and its notice.
static void omniSeFired(uint32_t now)
{
    omniSeLoad();
    omniSeState.fired(omniSeAction, now);
    if (omniSeState.closing()) notice(OSE::closeNotice());
    fprintf(stderr, "OMNI SLEEP END: %s\n", OSE::key(omniSeAction)); fflush(stderr);
    omniShellDirty = true;
}

// Every SDL event (event loop, after omniSleepWake). True: the event is used up (it woke the dim / kept Omni open).
static bool omniSeEvent(const SDL_Event& e)
{
    if (e.type == SDL_CONTROLLERBUTTONUP && omniSeSwallow >= 0 && int(e.cbutton.button) == omniSeSwallow) { omniSeSwallow = -1; return true; }
    if (!omniSeState.active()) return false;
    if (e.type != SDL_CONTROLLERBUTTONDOWN && e.type != SDL_KEYDOWN && e.type != SDL_MOUSEBUTTONDOWN) return false;
    if (e.type == SDL_CONTROLLERBUTTONDOWN) omniSeSwallow = int(e.cbutton.button);
    const OSE::Woke w = omniSeState.wake();
    notice(w == OSE::Woke::Stayed ? OSE::stayNotice() : OSE::wakeNotice());
    omniShellDirty = true;
    return true;
}

// omniF3Tick, after omniStTick (and so after omniNlTick): the close countdown, the present pass's dim matrix.
static void omniSeTick(uint32_t now)
{
    if (omniSeState.closeDue(now)) {
        notice(OSE::closingNotice());
        fprintf(stderr, "OMNI SLEEP END: closing Omni (normal exit)\n"); fflush(stderr);
        running = false;   // the Exit Omni path: session saved, clean-exit marker, platform exit to the home screen
        return;
    }
    if (!omni_gpu_present_night) return;   // a title without the pass: the software dim (omniSeDraw)
    if (omniSeState.dimmed() && omniNlAvailable()) {
        const ONL::Mat base = omniNlSent ? omniNlLastSent : ONL::identity();
        if (omniSeGpuDim && omniSeNlSentSeen == omniNlSent && ONL::near(base, omniSeNlSeen, 0.f)) return;
        float m[9];
        OSE::dimMatrix(base.m, m);
        omni_gpu_present_night(m);
        omniSeGpuDim = true; omniSeNlSentSeen = omniNlSent; omniSeNlSeen = base;
        omniShellDirty = true;
    } else if (omniSeGpuDim) {
        omni_gpu_present_night(omniNlSent ? omniNlLastSent.m : nullptr);   // the Night light's own tint back (or no pass)
        omniSeGpuDim = false;
        omniShellDirty = true;
    }
}

// The full draw, last (after the pointer): the software dim when the present pass does not carry it.
static void omniSeDraw()
{
    if (!omniSeState.dimmed() || omniSeGpuDim || !canvas || !canvas->pixels) return;
    const OmniPix f = omniPix();
    if (!f.ok) { SDL_Rect r { 0, 0, canvas->w, canvas->h }; SDL_FillRect(canvas, &r, SDL_MapRGBA(canvas->format, 0, 0, 0, 255)); return; }
    for (int y = 0; y < canvas->h; ++y) {
        uint32_t* row = omniRow(y);
        for (int x = 0; x < canvas->w; ++x) omniDarkenPx(row[x], f.amask, OSE::kDimDarken);
    }
}
static bool omniSeDimOpen() { return omniSeState.dimmed(); }
[[maybe_unused]] static const bool omniSeLayer = [] {
    // open while dimmed: no regional draw, no pointer event reaches the page (the draw is omniSeDraw, after the pointer)
    omniOverlayLayers().push_back({ omniSeDimOpen, nullptr, nullptr, nullptr, nullptr, true });
    return true;
}();

// --- the chooser's row (OmniSleepTimerShell.h) ------------------------------------------------------------------------
static void omniSeRow(OmniFxPanel& p)
{
    omniSeLoad();
    OmniFxRow r; r.id = omniSeRowId; r.label = OSE::rowLabel(); r.value = OSE::value(omniSeAction); r.stepper = true;
    r.detail = OSE::detail(omniSeAction);
    p.rows.push_back(r);
}
static bool omniSeRowInput(int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    if (b != SDL_CONTROLLER_BUTTON_A && !left && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    omniSeLoad();
    omniSeAction = OSE::cycle(omniSeAction, left ? -1 : 1);
    omniSeWrite();
    omniShellDirty = true;
    return true;   // the chooser stays open (its rows are rebuilt)
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSleepTimer.h" // OMNI_SLEEP_TIMER_V1: Sleep timer chooser, fade, end of video (pure)\n',
         '#include "OmniSleepTimer.h" // OMNI_SLEEP_TIMER_V1: Sleep timer chooser, fade, end of video (pure)\n'
         '#include "OmniSleepEnd.h" // OMNI_SLEEP_END_V1: Sleep timer end action: pause / dim / close Omni (pure)\n'),
        ('static void omniStDrawTopBar(float x);        // OMNI_SLEEP_TIMER_V1: "zZ 23 min" in the top bar\n',
         'static void omniStDrawTopBar(float x);        // OMNI_SLEEP_TIMER_V1: "zZ 23 min" in the top bar\n'
         'static bool omniSeEvent(const SDL_Event& e);  // OMNI_SLEEP_END_V1 (OmniSleepEndShell.h): a button wakes the dim / keeps Omni open\n'
         'static void omniSeDraw();                     // OMNI_SLEEP_END_V1: the software dim, drawn last\n'),
        ('        omniSleepWake(event.type); // OMNI_SMALL_COMFORTS_V1: unmute tabs the sleep timer muted\n',
         '        omniSleepWake(event.type); // OMNI_SMALL_COMFORTS_V1: unmute tabs the sleep timer muted\n'
         '        if (omniSeEvent(event)) continue; // OMNI_SLEEP_END_V1: the press that ends the dim / the close countdown does nothing else\n'),
        ('    omniDrawPointer(); // OMNI_STYLE_V1: bigger pointer with a soft shadow\n',
         '    omniDrawPointer(); // OMNI_STYLE_V1: bigger pointer with a soft shadow\n'
         '    omniSeDraw(); // OMNI_SLEEP_END_V1: "Pause and dim the screen" without the present pass (over everything)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSleepTimerShell.h" // OMNI_SLEEP_TIMER_V1\n',
         '#include "OmniSleepEndShell.h" // OMNI_SLEEP_END_V1\n'
         '#include "OmniSleepTimerShell.h" // OMNI_SLEEP_TIMER_V1\n'),
        ('    omniStTick(now);    // OMNI_SLEEP_TIMER_V1: countdown, fade (1 script/s), end-of-video probe (every 5 s)\n',
         '    omniStTick(now);    // OMNI_SLEEP_TIMER_V1: countdown, fade (1 script/s), end-of-video probe (every 5 s)\n'
         '    omniSeTick(now);    // OMNI_SLEEP_END_V1: close countdown, the dim matrix (after omniNlTick)\n'),
    ],
    'OmniSleepTimerShell.h': [
        ('    fprintf(stderr, "OMNI SLEEP TIMER: playback stopped\\n"); fflush(stderr);\n',
         '    fprintf(stderr, "OMNI SLEEP TIMER: playback stopped\\n"); fflush(stderr);\n'
         '    omniSeFired(now); // OMNI_SLEEP_END_V1: then dim / close Omni (the "When time is up" choice)\n'),
        ('    add(omniStRowOff, OST::choiceLabel(0), omniSt.on(), std::string());\n',
         '    add(omniStRowOff, OST::choiceLabel(0), omniSt.on(), std::string());\n'
         '    omniSeRow(p); // OMNI_SLEEP_END_V1: "When time is up"\n'),
        ('    if (b != SDL_CONTROLLER_BUTTON_A) return false;\n',
         '    if (r.id == omniSeRowId) return omniSeRowInput(b); // OMNI_SLEEP_END_V1\n'
         '    if (b != SDL_CONTROLLER_BUTTON_A) return false;\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_SLEEP_TIMER_V1', 'sceSystemServiceLoadExec("exit", nullptr)', 'omniEverydayShutdown();'),
         'OmniFeatures3.h': ('OMNI_SLEEP_TIMER_V1', 'OMNI_NIGHT_LIGHT_V1'),
         'OmniNightLightShell.h': ('static bool omniNlAvailable()', 'static bool omniNlStarted = false, omniNlSent = false;',
                                   'static ONL::Mat omniNlLastSent'),
         'OmniSleepTimerShell.h': ('static void omniStFire(uint32_t now)',)}


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
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


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
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniSleepEnd.h', 'OmniSleepEndShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or name.search(c)
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def order_ok():
    """The shell uses the Night light's statics, and omniSeTick must run after omniNlTick."""
    f3 = (root / 'OmniFeatures3.h').read_bytes().decode('utf-8')
    nl_inc = f3.find('#include "OmniNightLightShell.h"')
    st_inc = f3.find('#include "OmniSleepTimerShell.h"')
    nl_tick = f3.find('    omniNlTick(now);')
    st_tick = f3.find('    omniStTick(now);')
    if min(nl_inc, st_inc, nl_tick, st_tick) < 0 or nl_inc > st_inc or nl_tick > st_tick:
        sys.exit('OmniFeatures3.h: OmniNightLightShell.h / omniNlTick must come before OmniSleepTimerShell.h / omniStTick(now)')


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first (apply_sleep_timer.py, apply_night_light.py)' % (fname, need))
    order_ok()
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    msgs = [write_new('OmniSleepEnd.h', PURE, 'OmniSleepTimer.h'),
            write_new('OmniSleepEndShell.h', SHELL, 'OmniSleepTimerShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
