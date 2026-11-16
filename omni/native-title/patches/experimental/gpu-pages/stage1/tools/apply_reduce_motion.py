#!/usr/bin/env python3
"""OMNI_REDUCE_MOTION_V1 (2026-11-16): Browser settings > "Reduce motion" (accessibility). Default Off.

What the user sees
  Browser settings, after "High contrast" / "Large pointer":
      "Reduce motion"   Off / On      (D-pad / Cross toggle, Triangle resets to Off; saved in reduce-motion.txt)
  On: nothing of Omni's own moves, and pages are asked to stop animating:
    Omni's animations, as found in the patched tree, and what Reduce motion does with each
      auto-hiding bars (OMNI_STYLE_V1, omniChromeT, 220 ms slide)     instant (omniChromeT jumps to 0 / 1)
      toast pill (180 ms fade in + 12 px rise, 320 ms fade out)       80 ms cross-fades, no rise
      panel open fades (omniPanelT: settings, keyboard, menu,          80 ms cross-fade (was 150 ms; High contrast
        history, dialogs)                                             still has none)
      progress bar (160 ms catch-up, 80 ms run-out, 260 ms fade)      fill jumps to the load's progress, 80 ms fade
      pointer snap onto a link (OmniPointerFeel.h, 110 ms ease-out)   jumps to the link
      night light (OmniNightLight::Fade, 2 s colour sweep)            switches at once (a running fade is snapped)
      smooth scrolling (OMNI_SCROLL_PLUS_V1: WebKit's                 off while reduced (the saved choice is kept and
        ScrollAnimatorEnabled)                                        comes back when Reduce motion is turned off);
                                                                      its row then answers "stays off" instead
      scroll position bar (OMNI_SCROLL_PLUS_V1, 700 ms + 300 ms fade) 700 ms, then an 80 ms fade
    Not changed: the loading spinner in the tab (an arc turning once a second while a page loads: a status indicator,
    kept like other platforms keep theirs), the sleep timer's fade (audio volume, not motion), the magnifier and the
    quick tab switcher strip (neither animates: they follow the pointer / selection at once). No shimmer exists in
    the progress bar. The new-tab / start / Reader / repo pages have no motion in C++; their CSS is covered below.
  Pages (and Omni's own repo pages: start, Reader view, settings pages ...): WebKit keeps its reduced-motion switch
    inside WebCore only (Settings::forcedPrefersReducedMotionAccessibilityValue in Settings.yaml, not in the
    WebPreferences*.yaml that WKPreferences / WKPreferences...ForKeyForTesting reach), and this port's Theme answers
    "no preference" (Theme::userPrefersReducedMotion() default), so `prefers-reduced-motion: reduce` can't be made to
    match without a WebKit (WebProcess) change. Instead, the caption-style way: one global user style sheet
    (UserStyleLevel::User, all frames, all URLs, normal + private controllers, its own content world), removed again
    when Reduce motion is turned off; WebKit restyles open pages, no reload:
        *,*::before,*::after{animation-duration:0.01ms!important;animation-iteration-count:1!important;
                             transition-duration:0.01ms!important;scroll-behavior:auto!important}
    0.01 ms (not none) so animationend / transitionend still fire. Not covered: animations a page drives from script
    (requestAnimationFrame, Web Animations API timing set from JS), video, and pages' own @media
    (prefers-reduced-motion) blocks (they don't match, see above; the sheet does what most of them do).
  Test modes: always Off (self-tests measure the normal animations; the row says so).

Pure part: engine/entry/OmniReduceMotion.h (kept next to this script): the duration mapping (Move -> 0 ms, Fade ->
at most 80 ms, Off -> unchanged), the panel / toast / scroll-bar helpers, the page CSS, reduce-motion.txt.
Tested by tools/test_reduce_motion.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_reduce_motion.cpp -o t && ./t <tree>/engine/entry
(with the tree it also checks that the durations it names are the tree's, and that each patched site is there).
Shell side: engine/entry/OmniReduceMotionShell.h (included from OmniFeatures3.h after OmniCaptionStyleShell.h), the
namespace alias ORMO and the forward declaration of omniRmOn() next to omniChromeT (OmniBrowser.cpp), and the
one-line call sites below. omniRmOn() is cached (one file read, at first use): it runs every frame.

Anchors (each exactly once; MARK makes each file idempotent; CRLF / LF kept; whole lines only, so no `//` ever lands
after a line-prefix anchor):
  OmniBrowser.cpp       the OmniCaptionStyle.h include line           -> + #include "OmniReduceMotion.h"
                        static float omniChromeT ... line             -> + ORMO alias, omniRmOn() declaration
                        "const float step = dt / 220.f;"              -> replaced (bar slide)
                        the three omniProgress / omniProgressAlpha    -> replaced (fill, run-out, fade)
                          lines of omniStyleTick
                        omniPanelT's "if (dt >= omniPanelFadeMs)" + its two next lines -> replaced (panel fade)
                        the toast's "float a = ..." line, its two fade-out lines and "const int y = ..." -> replaced
  OmniPointerFeel.h     the "const float t = ... / 110.f" line         -> replaced (snap)
  OmniNightLightShell.h "const ONL::Mat m = omniNlFade.value(now);"   -> a snap line before it
  OmniBrowserSettings.h "static bool omniHcSettingsInput(int id, int b);" -> + declarations
                        the omniHcSettingsRows(p) line                -> + the row after it
                        the omniHcRowTheme dispatch line              -> + our dispatch before it (before the >= 300 rows)
  OmniFeatures3.h       the OmniCaptionStyleShell.h include line      -> + our shell
                        the omniCcsTick(); line of omniF3Tick         -> + omniRmTick();
  OmniBlocker.h         "bool omniCaptionCssSet(const std::string& css);" -> + omniReduceMotionCssSet
  OmniBlocker.cpp       "void omniAddonsRemove(const std::string& id)\\n{" -> the sheet function before it
  OmniSettingsSearch.h  the { "font", ... } synonym line              -> + "animation" -> Reduce motion before it
  OmniScrollPlusShell.h (only when OMNI_SCROLL_PLUS_V1 is in the tree) the WKPreferencesSetBoolValueForKeyForTesting
                        line (refuses "on" while reduced), "if (id != omniScpRowSmooth) return false;" (+ the
                        "stays off" answer), the three OSCP::alpha(now - omniScpShownAt) lines (replaced).
Row id 849 (ORMO::kRowId). Refused if "= 849" appears in any other apply_*.py next to this one or in the tree.
Alias ORMO; shell names omniRm*. Refused if the tree already uses them (without MARK).

Order: apply AFTER apply_caption_style.py, apply_site_css.py, apply_high_contrast.py, apply_night_light.py,
apply_settings_search.py (their lines are anchors) and after apply_scroll_plus.py when that is part of the build
(otherwise smooth scrolling and its position bar are not covered: re-running this script after apply_scroll_plus.py
adds them, the shell header is rewritten with the smooth-scrolling hooks). In build-omni-gpupages-rc6-title.sh: the
last of the "$TT" feature units, after apply_web_apps.py (and apply_scroll_plus.py), before apply_spare_defer.py.
usage: apply_reduce_motion.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_REDUCE_MOTION_V1'
MARK_SCP = 'OMNI_REDUCE_MOTION_V1_SCP'   # the scroll-plus part (its own mark: it can come later)
ROW_ID = 849
PURE_NAME = 'OmniReduceMotion.h'
SHELL_NAME = 'OmniReduceMotionShell.h'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

SHELL = r'''// OMNI_REDUCE_MOTION_V1: Browser settings > "Reduce motion" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniCaptionStyleShell.h). The pure part is OmniReduceMotion.h (alias ORMO,
// next to omniChromeT in OmniBrowser.cpp, where omniRmOn() is declared); the reasons are in tools/apply_reduce_motion.py.
// Main thread only; the file is written by omniIoQueue.
#pragma once

static bool omniRmLoaded = false, omniRmState = false, omniRmInstalled = false;
// Cached after the first call (one file read): omniStyleTick, the toast, the panels and the pointer ask every frame.
static bool omniRmOn()
{
    if (!omniRmLoaded) {
        omniRmLoaded = true;
        if (!omniTestMode()) {   // self-tests measure the normal animations
            if (FILE* f = fopen(omniData(ORMO::kFileName).c_str(), "rb")) {
                char buf[64];
                const size_t n = fread(buf, 1, sizeof buf, f);
                fclose(f);
                omniRmState = ORMO::parse(std::string(buf, n));
            }
        }
    }
    return omniRmState;
}
// Pages: the global user style sheet (OmniBlocker.cpp) in or out; WebKit restyles open pages, no reload.
static void omniRmApply()
{
    const bool on = omniRmOn();
    if (!omniReduceMotionCssSet(on ? ORMO::kPageCss : "")) fprintf(stderr, "OMNI REDUCE MOTION: controllers not ready\n");
@SMOOTH@
}
// From omniF3Tick (every pass): once the controllers exist, the saved choice reaches pages (nothing to do when Off).
static void omniRmTick()
{
    if (omniRmInstalled || !omniBlockerController()) return;
    omniRmInstalled = true;
    if (!omniRmOn()) return;
    omniRmApply();
    fprintf(stderr, "OMNI REDUCE MOTION: on\n");
}

// --- Browser settings row (ORMO::kRowId, declared in OmniBrowserSettings.h) ------------------------------------------
static void omniRmSettingsRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = ORMO::kRowId; r.label = ORMO::kRowLabel; r.value = ORMO::rowValue(omniRmOn()); r.stepper = true;
    r.detail = omniTestMode() ? std::string("Off in test modes") : std::string(ORMO::kRowDetail);
    p.rows.push_back(r);
}
static bool omniRmSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT && b != SDL_CONTROLLER_BUTTON_A
        && b != SDL_CONTROLLER_BUTTON_Y) return false;
    if (omniTestMode()) { notice("Reduce motion is off in test modes"); return true; }
    const bool on = b == SDL_CONTROLLER_BUTTON_Y ? false : !omniRmOn();   // Triangle: back to the default (Off)
    omniRmLoaded = true;
    omniRmState = on;
    omniRmInstalled = true;   // applied now; the tick has nothing left to do
    omniIoQueue(omniData(ORMO::kFileName), ORMO::serialize(on), false);
    omniRmApply();
    omniShellDirty = true;
    omniFxRefresh();
    notice(ORMO::noticeText(on));
    return true;
}
'''

SMOOTH_SCP = (
    '    // Smooth scrolling (OMNI_SCROLL_PLUS_V1): WebKit\'s ScrollAnimatorEnabled goes off while reduced (omniScpSmoothSet\n'
    '    // refuses "on" then); turned off again, the saved choice comes back (none saved: WebKit\'s default, off).\n'
    '    if (on) omniScpSmoothSet(false); else omniScpApplySmooth();')
SMOOTH_NONE = (
    '    // Smooth scrolling: no switch for it in this tree (WebKit\'s ScrollAnimatorEnabled stays at its default, off).\n'
    '    // Re-run apply_reduce_motion.py after apply_scroll_plus.py to cover that feature.')

BLOCKER_FN = r'''// OMNI_REDUCE_MOTION_V1: Browser settings > Reduce motion (OmniReduceMotionShell.h decides the CSS). One global user
// style sheet (UserStyleLevel::User: its !important beats the page's), every frame, every URL, both controllers, its
// own content world; css "" removes it. WebKit restyles open pages when a sheet is added or removed.
namespace {
RefPtr<API::UserStyleSheet> omniRmoSheet;
std::string omniRmoText;
}
bool omniReduceMotionCssSet(const std::string& css)
{
    if (!controller) return false;
    if (css == omniRmoText && (omniRmoSheet || css.empty())) return true;
    if (omniRmoSheet) {
        WebKit::toImpl(controller.get())->removeUserStyleSheet(*omniRmoSheet);
        if (privateController) WebKit::toImpl(privateController.get())->removeUserStyleSheet(*omniRmoSheet);
        omniRmoSheet = nullptr;
    }
    omniRmoText = css;
    if (css.empty()) return true;
    WebCore::UserStyleSheet sheet { addonString(css), WTF::URL { }, { }, { },
        WebCore::UserContentInjectedFrames::InjectInAllFrames,
        WebCore::UserContentMatchParentFrame::ForOpaqueOrigins, WebCore::UserStyleLevel::User };
    auto world = API::ContentWorld::sharedWorldWithName(addonString("omni-reduce-motion"));
    Ref<API::UserStyleSheet> userSheet = API::UserStyleSheet::create(WTF::move(sheet), world.get());
    WebKit::toImpl(controller.get())->addUserStyleSheet(userSheet.get());
    if (privateController) WebKit::toImpl(privateController.get())->addUserStyleSheet(userSheet.get());
    omniRmoSheet = userSheet.ptr();
    return true;
}
'''

RM = 'omniRmOn()'
EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniCaptionStyle.h" // OMNI_CAPTION_STYLE_V1: caption look (::cue user sheet), captions.txt (pure)\n',
         '#include "OmniCaptionStyle.h" // OMNI_CAPTION_STYLE_V1: caption look (::cue user sheet), captions.txt (pure)\n'
         '#include "OmniReduceMotion.h" // OMNI_REDUCE_MOTION_V1: Reduce motion durations, page sheet, reduce-motion.txt (pure)\n'),
        ('static float omniChromeT = 1, omniChromeShown = 1;   // animation time and eased amount shown, 0..1\n',
         'static float omniChromeT = 1, omniChromeShown = 1;   // animation time and eased amount shown, 0..1\n'
         'namespace ORMO = OmniReduceMotion; // OMNI_REDUCE_MOTION_V1\n'
         'static bool omniRmOn(); // OMNI_REDUCE_MOTION_V1: Browser settings > "Reduce motion" (OmniReduceMotionShell.h, cached)\n'),
        ('        const float step = dt / 220.f;\n',
         '        const float step = ORMO::tickStep(dt, ORMO::ms(' + RM + ', ORMO::Kind::Move, ORMO::kBarSlideMs)); // OMNI_REDUCE_MOTION_V1: was dt / 220.f (reduced: at once)\n'),
        ('        omniProgress = std::max(omniProgress, omniProgress + (target - omniProgress) * std::min(1.f, dt / 160.f));\n',
         '        omniProgress = std::max(omniProgress, omniProgress + (target - omniProgress) * ORMO::tickStep(dt, ORMO::ms(' + RM + ', ORMO::Kind::Move, ORMO::kProgressFillMs))); // OMNI_REDUCE_MOTION_V1: was min(1, dt / 160)\n'),
        ('        omniProgress += (1 - omniProgress) * std::min(1.f, dt / 80.f);\n',
         '        omniProgress += (1 - omniProgress) * ORMO::tickStep(dt, ORMO::ms(' + RM + ', ORMO::Kind::Move, ORMO::kProgressFinishMs)); // OMNI_REDUCE_MOTION_V1: was min(1, dt / 80)\n'),
        ('        if (now - omniProgressDoneAt > 200) omniProgressAlpha = std::max(0.f, omniProgressAlpha - dt / 260.f);\n',
         '        if (now - omniProgressDoneAt > 200) omniProgressAlpha = std::max(0.f, omniProgressAlpha - ORMO::tickStep(dt, ORMO::ms(' + RM + ', ORMO::Kind::Fade, ORMO::kProgressFadeMs))); // OMNI_REDUCE_MOTION_V1: was dt / 260\n'),
        ('    if (dt >= omniPanelFadeMs) return 1;\n'
         '    const float u = 1 - dt / float(omniPanelFadeMs);\n'
         '    return 1 - u * u * u;\n',
         '    return ORMO::panelFade(' + RM + ', dt, omniPanelFadeMs); // OMNI_REDUCE_MOTION_V1: 1 - (1 - t)^3 as before; reduced: 80 ms\n'),
        ('    float a = std::min(1.f, (now - omniToastSince) / 180.f);\n',
         '    float a = ORMO::toastIn(' + RM + ', now - omniToastSince); // OMNI_REDUCE_MOTION_V1: was min(1, (now - omniToastSince) / 180)\n'),
        ('    if (!error && statusUntil) a = std::min(a, std::max(0.f, int32_t(statusUntil - now) / 320.f));   // fades out as notice() ends\n',
         '    if (!error && statusUntil) a = std::min(a, ORMO::toastOut(' + RM + ', int32_t(statusUntil - now)));   // fades out as notice() ends (OMNI_REDUCE_MOTION_V1: was / 320)\n'),
        ('    if (error) a = std::min(a, std::max(0.f, int32_t(omniToastSince + omniToastErrorMs - now) / 320.f));   // OMNI_POLISH_V1: the tab keeps its dot\n',
         '    if (error) a = std::min(a, ORMO::toastOut(' + RM + ', int32_t(omniToastSince + omniToastErrorMs - now)));   // OMNI_POLISH_V1: the tab keeps its dot (OMNI_REDUCE_MOTION_V1: was / 320)\n'),
        ('    const int y = base - h + int((1 - a) * 12);\n',
         '    const int y = base - h + int((1 - a) * ORMO::toastRise(' + RM + ')); // OMNI_REDUCE_MOTION_V1: was (1 - a) * 12 (reduced: no rise)\n'),
    ],
    'OmniPointerFeel.h': [
        ('        const float t = std::min(1.f, (now - omniFxPtr.animStart) / 110.f), e = 1 - (1 - t) * (1 - t) * (1 - t);\n',
         '        const float t = ORMO::progress(now - omniFxPtr.animStart, ORMO::ms(' + RM + ', ORMO::Kind::Move, ORMO::kPointerSnapMs)), e = 1 - (1 - t) * (1 - t) * (1 - t); // OMNI_REDUCE_MOTION_V1: was / 110.f (reduced: jumps)\n'),
    ],
    'OmniNightLightShell.h': [
        ('    const ONL::Mat m = omniNlFade.value(now);\n',
         '    if (ORMO::instant(' + RM + ', ORMO::Kind::Move, ORMO::kNightLightMs) && omniNlFade.running(now)) omniNlFade.snap(omniNlFade.target()); // OMNI_REDUCE_MOTION_V1: no 2 s fade\n'
         '    const ONL::Mat m = omniNlFade.value(now);\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniHcSettingsInput(int id, int b);\n',
         'static bool omniHcSettingsInput(int id, int b);\n'
         'static void omniRmSettingsRow(OmniFxPanel& p); // OMNI_REDUCE_MOTION_V1: "Reduce motion" (OmniReduceMotionShell.h, row id ORMO::kRowId = 849)\n'
         'static bool omniRmSettingsInput(int b);\n'),
        ('    omniHcSettingsRows(p); // OMNI_HIGH_CONTRAST_V1: High contrast, Large pointer (next to the theme row)\n',
         '    omniHcSettingsRows(p); // OMNI_HIGH_CONTRAST_V1: High contrast, Large pointer (next to the theme row)\n'
         '    omniRmSettingsRow(p); // OMNI_REDUCE_MOTION_V1: Reduce motion (Off / On)\n'),
        ('    if (r.id == omniHcRowTheme || r.id == omniHcRowPointer) return omniHcSettingsInput(r.id, b); // OMNI_HIGH_CONTRAST_V1 (before the >= 300 rows)\n',
         '    if (r.id == ORMO::kRowId) return omniRmSettingsInput(b); // OMNI_REDUCE_MOTION_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniHcRowTheme || r.id == omniHcRowPointer) return omniHcSettingsInput(r.id, b); // OMNI_HIGH_CONTRAST_V1 (before the >= 300 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniCaptionStyleShell.h" // OMNI_CAPTION_STYLE_V1\n',
         '#include "OmniCaptionStyleShell.h" // OMNI_CAPTION_STYLE_V1\n'
         '#include "OmniReduceMotionShell.h" // OMNI_REDUCE_MOTION_V1 (after scroll plus: it calls its smooth-scrolling switch)\n'),
        ('    omniCcsTick();      // OMNI_CAPTION_STYLE_V1: saved caption look once the controllers exist; preview cleanup\n',
         '    omniCcsTick();      // OMNI_CAPTION_STYLE_V1: saved caption look once the controllers exist; preview cleanup\n'
         '    omniRmTick();       // OMNI_REDUCE_MOTION_V1: the page sheet once the controllers exist (when On)\n'),
    ],
    'OmniBlocker.h': [
        ('bool omniCaptionCssSet(const std::string& css);\n',
         'bool omniCaptionCssSet(const std::string& css);\n'
         '// OMNI_REDUCE_MOTION_V1: the one global "no CSS animations" user style sheet, all frames, all URLs, normal + private\n'
         '// controllers; css "" removes it. false: controllers not ready.\n'
         'bool omniReduceMotionCssSet(const std::string& css);\n'),
    ],
    'OmniBlocker.cpp': [
        ('void omniAddonsRemove(const std::string& id)\n{\n',
         BLOCKER_FN + 'void omniAddonsRemove(const std::string& id)\n{\n'),
    ],
    'OmniSettingsSearch.h': [
        ('        { "font", { "text size", "interface size", "zoom", nullptr } },\n',
         '        { "animation", { "reduce motion", "smooth scrolling", nullptr } }, // OMNI_REDUCE_MOTION_V1\n'
         '        { "font", { "text size", "interface size", "zoom", nullptr } },\n'),
    ],
}

SCP_ALPHA = 'OSCP::alpha(ORMO::fadeClock(now - omniScpShownAt, OSCP::kHoldShownMs, OSCP::kFadeMs, ' + RM + '))'
EDITS_SCP = {
    'OmniScrollPlusShell.h': [
        ('    WKPreferencesSetBoolValueForKeyForTesting(preferences.get(), on, omniScpSmoothKey().get());   // updates open pages too\n',
         '    if (on && ' + RM + ') on = false; // OMNI_REDUCE_MOTION_V1_SCP: no smooth scrolling while Reduce motion is on (the saved choice stays)\n'
         '    WKPreferencesSetBoolValueForKeyForTesting(preferences.get(), on, omniScpSmoothKey().get());   // updates open pages too\n'),
        ('    if (id != omniScpRowSmooth) return false;\n',
         '    if (id != omniScpRowSmooth) return false;\n'
         '    if (' + RM + ' && !reset) { notice("Smooth scrolling stays off while Reduce motion is on"); return true; } // OMNI_REDUCE_MOTION_V1_SCP\n'),
        ('        && !editing && !omniOverlayOpen() && OSCP::scrollable(omniScpMetrics) && OSCP::alpha(now - omniScpShownAt) > 0;\n',
         '        && !editing && !omniOverlayOpen() && OSCP::scrollable(omniScpMetrics) && ' + SCP_ALPHA + ' > 0; // OMNI_REDUCE_MOTION_V1_SCP: 80 ms fade when reduced\n'),
        ('    if (shown != omniScpVisible || (shown && OSCP::alpha(now - omniScpShownAt) < 255)) omniShellDirty = true;\n',
         '    if (shown != omniScpVisible || (shown && ' + SCP_ALPHA + ' < 255)) omniShellDirty = true; // OMNI_REDUCE_MOTION_V1_SCP\n'),
        ('    const uint8_t a = OSCP::alpha(now - omniScpShownAt);\n',
         '    const uint8_t a = ' + SCP_ALPHA + '; // OMNI_REDUCE_MOTION_V1_SCP\n'),
    ],
}


def read(name):
    return (root / name).read_bytes().decode('utf-8')


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits, mark=MARK):
    s = read(name)
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = read(name)
    if mark in s:
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


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def refuse_taken():
    """Row id 849, the alias and the shell names must be free (checked only before the first apply)."""
    # Engine tree only: sibling apply_*.py files are not scanned (their notes list other patches' ids; a numeric hit
    # there would stop the title build, which runs every script from this folder).
    taken = re.compile(r'=\s*%d\b' % ROW_ID)
    for f in sorted(root.glob('*.[ch]*')):
        if f.name in (PURE_NAME, SHELL_NAME):
            continue
        t = cpp_code(f.read_bytes().decode('utf-8', 'replace'))
        if taken.search(t):
            sys.exit('row id %d is already taken in the tree (%s)' % (ROW_ID, f.name))
        for name in (() if f.name in GUIDE else ('ORMO', 'omniRmOn', 'omniRmTick', 'omniRmSettings', 'omniReduceMotionCssSet')):
            if re.search(r'\b%s' % name, t):
                sys.exit('%s is already used by something else (%s)' % (name, f.name))


def main():
    need = {'OmniFeatures3.h': 'OMNI_CAPTION_STYLE_V1', 'OmniBlocker.cpp': 'OMNI_CAPTION_STYLE_V1',
            'OmniBrowserSettings.h': 'OMNI_HIGH_CONTRAST_V1', 'OmniNightLightShell.h': 'OMNI_NIGHT_LIGHT_V1',
            'OmniSettingsSearch.h': 'OMNI_SETTINGS_SEARCH_V1'}
    for name, mark in need.items():
        if not (root / name).exists() or mark not in read(name):
            sys.exit('%s: %s missing (apply_reduce_motion.py goes after the patch that adds it)' % (name, mark))
    scp = (root / 'OmniScrollPlusShell.h').exists() and 'OMNI_SCROLL_PLUS_V1' in read('OmniScrollPlusShell.h')
    if MARK not in read('OmniBrowser.cpp'):
        refuse_taken()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    if scp:
        for name, edits in EDITS_SCP.items():
            check(name, edits, MARK_SCP)
    pure = (HERE / PURE_NAME).read_bytes().decode('utf-8')
    shell = SHELL.replace('@SMOOTH@', SMOOTH_SCP if scp else SMOOTH_NONE)
    msgs = [write_new(PURE_NAME, pure, 'OmniCaptionStyle.h'), write_new(SHELL_NAME, shell, 'OmniCaptionStyleShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    if scp:
        msgs += [patch(name, edits, MARK_SCP).replace(': ', ' (scroll plus): ', 1) for name, edits in EDITS_SCP.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK
          + (' (+ scroll plus)' if scp else ' (no scroll plus in this tree: smooth scrolling not touched)'))


if __name__ == '__main__':
    main()
