#!/usr/bin/env python3
"""OMNI_BUTTON_MAP_V1 (2026-11-16): Controller shortcuts - choose what a few browsing buttons do.

What the user sees
  - Browser settings > "Controller shortcuts..." (value "Default" or "2 changed"). Cross opens a panel:
        Triangle          Address bar
        Square            New tab
        R3                Close tab
        L3                Add this page to shortcuts
        Touchpad          Translate page
        L2 + Square       Copy the text, link or page address
        L2 + Triangle     Paste into the text box
        L2 + Cross        Options menu
        L2 + Circle       Browser settings
        Reset to defaults
    (Xbox labels: Y, X, RS, LS, Touchpad, LT + X ...). D-pad left / right steps through the actions, Cross opens the
    list (the current one highlighted, "Default" marked, "Also on Square" when another button has it), Triangle puts
    the highlighted button back to its default, "Reset to defaults" all of them. Each row's second line says what
    is wrong or different: "Also on R3", "Used by the add-on quick switch", "Default: New tab", "Tab switcher: Cross
    switches, Circle cancels" (a switcher opened without L2 has no L2 release to commit).
  - Actions: Address bar, New tab, Close tab, Back, Forward, Reload, Now playing, Screenshot, Find on page, Reader
    view, Bookmark this page, Show QR code, Magnifier (2x, 3x, off), Tab switcher, Options menu, Add this page to
    shortcuts, Translate page, Copy, Paste, Browser settings, Nothing. Each one calls the handler the Options menu /
    chords already use (omniFxBack, WKPageReload or omniFxStop, omniNpShow, omniPtScreenshot, omniFindStart,
    omniReaderStart, omniFxBookmarkToggleCurrent, omniQrShow, omniMagSet, the switcher strip, omniFxQuickMenuShow,
    omniShortcutAddCurrent, omniTranslateToggle, omniL2Copy, omniL2Paste, omniFxSettingsShow).
  - The bottom button bar while browsing names the chosen Triangle / Square actions (omniBrowseHints).
  - Saved in /data/omni/shortcuts-map.txt (omniIoQueue; "button<TAB>action" lines). Missing / unreadable file or
    unknown lines: today's buttons. Self-tests (omniTestMode) never read it.

Why one place is enough (checked in the patched tree, 2026-11-16)
  - button() runs, in order: pointer-Cross, Master Control / saved links / built-in pages / continue watching /
    overlays (omniOverlayButton: every panel, dialog, find bar, text select, QR, tab switcher strip), the keyboard
    (editing), YouTube TV mode (D-pad / Cross / Circle only), full-screen video keys, Create / Options, Display
    settings, and only then the browsing tail ("if (!active()) return;" ... Y / X / R1 / L1 / add-on / L3 / touchpad
    / R3 / D-pad). The remap is ONE call at the head of that tail, so panels, the keyboard, full-screen video, YouTube
    TV mode, the find bar's own Triangle / Square, text select and the switcher strip never see it.
  - L2 + Square / Triangle / Cross / Circle are decided in omniL2Chord after its context check (no panel, keyboard,
    settings or full screen) and after it has claimed the press (omniL2ChordUsed, omniL2Swallow): one call before its
    Square line. L2 + D-pad up / down (site zoom), L2 + L1 / R1 (switcher), L2 + R3 (screenshot, omniQaShotChord),
    L2 + L3 (magnifier, omniMagChord) stay fixed.
  - Defaults are today's mapping BY CONSTRUCTION: while a button is on its default, omniBmapBrowse / omniBmapL2
    return false and the original line in button() / omniL2Chord runs unchanged. A changed L3 / touchpad still lets
    the add-on quick switch (omniAdShortcut) go first, as today.
  - Not remappable (on purpose): Cross / Circle (click / back, also YouTube TV's Enter / Back and every panel's
    Choose / Back), L1 / R1 (omniShoulderChord: L1 + R1 opens Media downloads; L2 + L1 / R1 the switcher), D-pad
    (scroll; left / right already a Browser setting), Options / Create (always reach the menus), R2 / L2 alone.

Ids (grep of every apply_*.py and the tree, 2026-11-16): Browser settings row 842 (834-839, 845-899, 900+ taken),
panel kinds 7450 / 7451 (7310 ... 7491 used: 7440 tab memory view, 7460-7462 bookmarks), list rows 0-8 and 100.
Names: omniBmap*, namespace OmniButtonMap (alias OBMP). The script refuses a tree (or a sibling apply_*.py) that
already uses 842 / 7450 / 7451 / OBMP.

Controls guide: OmniControlsHelp.h's table is static. The shell defines omniBmapGuideText (action + note for a
guide row when its button is remapped, false otherwise) and registers it only when OmniControlsHelpShell.h defines
OMNI_CH_REMAP_HOOK and the pointer omniChRemap (that hook is apply_controls_help.py's job; without it the guide keeps
showing the defaults).

Pure part: engine/entry/OmniButtonMap.h (no SDL / WebKit): slots, actions, defaults, parse / serialize, stepping,
conflicts, texts, guide-row lookup. Tested by tools/test_button_map.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_button_map.cpp -o t && ./t
Shell side: engine/entry/OmniButtonMapShell.h, included from OmniBrowser.cpp right after OmniAddons.h.

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp        the OmniTabSwitcher.h include line (pure include after it, file scope);
                         omniBrowseHints' comment + head (declaration before, the remapped bar first);
                         button()'s head (declaration before it);
                         the browsing tail's "if (!active()) return;" + Cross line (the remap between them);
                         omniL2Chord's Square line (the remapped chord before it);
                         the OmniAddons.h include line (shell include after it).
  OmniBrowserSettings.h  omniPfSettingsInput's declaration, the pad-feedback row, its input line (ours after each).
Apply AFTER apply_l2_chords.py (base T), apply_pinned_tabs.py, apply_qr_share.py, apply_media_controls.py,
apply_pad_feedback.py, apply_magnifier.py, apply_find_plus.py and apply_tab_switcher.py (run it last).
usage: apply_button_map.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_BUTTON_MAP_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_BUTTON_MAP_V1: the pure part of "Controller shortcuts" (Browser settings): which action a few browsing buttons
// run. No SDL, no WebKit. The shell side is OmniButtonMapShell.h; the reasons are in tools/apply_button_map.py.
// Tested on the host with g++ (test_button_map.cpp).
#pragma once
#include <algorithm>
#include <cstddef>
#include <string>
#include <vector>

namespace OmniButtonMap {

constexpr const char* kFileName = "shortcuts-map.txt";   // under /data/omni/
constexpr int kSettingsRowId = 842;    // Browser settings row (834-839, 845-899 and 900+ are other patches')
constexpr int kListKind = 7450;        // OmniFxPanel::kind: the buttons
constexpr int kPickKind = 7451;        // ... and the action list for one button
constexpr int kResetRowId = 100;       // "Reset to defaults" (the button rows are 0 .. kSlotCount - 1)
constexpr size_t kMaxFileBytes = 4096;

// The remappable buttons, while browsing (a page, nothing open over it).
enum Slot : int { sTriangle, sSquare, sR3, sL3, sTouchpad, sL2Square, sL2Triangle, sL2Cross, sL2Circle, kSlotCount };
enum Action : int {
    aNone, aAddressBar, aNewTab, aCloseTab, aBack, aForward, aReload, aNowPlaying, aScreenshot, aFind, aReader,
    aBookmark, aQrShare, aMagnifier, aTabSwitcher, aOptionsMenu, aAddShortcut, aTranslate, aCopy, aPaste,
    aBrowserSettings, kActionCount
};

struct ActionInfo { const char* key; const char* label; const char* hint; };
inline const ActionInfo& action(int a)
{
    static const ActionInfo k[kActionCount] = {
        { "none", "Nothing", "" },
        { "address", "Address bar", "Address" },
        { "newtab", "New tab", "New tab" },
        { "closetab", "Close tab", "Close tab" },
        { "back", "Back", "Back" },
        { "forward", "Forward", "Forward" },
        { "reload", "Reload", "Reload" },
        { "nowplaying", "Now playing", "Now playing" },
        { "screenshot", "Screenshot", "Screenshot" },
        { "find", "Find on page", "Find" },
        { "reader", "Reader view", "Reader" },
        { "bookmark", "Bookmark this page", "Bookmark" },
        { "qr", "Show QR code", "QR code" },
        { "magnifier", "Magnifier: 2x, 3x, off", "Magnifier" },
        { "tabswitcher", "Tab switcher", "Switch tab" },
        { "options", "Options menu", "Options" },
        { "shortcut", "Add this page to shortcuts", "Add shortcut" },
        { "translate", "Translate page", "Translate" },
        { "copy", "Copy the text, link or page address", "Copy" },
        { "paste", "Paste into the text box", "Paste" },
        { "settings", "Browser settings", "Settings" },
    };
    return k[a >= 0 && a < kActionCount ? a : 0];
}
// The list's order: the browsing actions first, then the ones only today's defaults use, Nothing last.
inline const std::vector<int>& choices()
{
    static const std::vector<int> v = { aAddressBar, aNewTab, aCloseTab, aBack, aForward, aReload, aNowPlaying,
        aScreenshot, aFind, aReader, aBookmark, aQrShare, aMagnifier, aTabSwitcher, aOptionsMenu, aAddShortcut,
        aTranslate, aCopy, aPaste, aBrowserSettings, aNone };
    return v;
}

struct SlotInfo { const char* key; const char* ps; const char* xbox; int def; bool l2; };
inline const SlotInfo& slot(int s)
{
    // def: what the button does today (button()'s browsing tail, omniL2Chord). The defaults ARE today's mapping.
    static const SlotInfo k[kSlotCount] = {
        { "triangle", "Triangle", "Y", aAddressBar, false },
        { "square", "Square", "X", aNewTab, false },
        { "r3", "R3", "RS", aCloseTab, false },
        { "l3", "L3", "LS", aAddShortcut, false },
        { "touchpad", "Touchpad", "Touchpad", aTranslate, false },
        { "l2+square", "L2 + Square", "LT + X", aCopy, true },
        { "l2+triangle", "L2 + Triangle", "LT + Y", aPaste, true },
        { "l2+cross", "L2 + Cross", "LT + A", aOptionsMenu, true },
        { "l2+circle", "L2 + Circle", "LT + B", aBrowserSettings, true },
    };
    return k[s >= 0 && s < kSlotCount ? s : 0];
}
inline std::string slotName(int s, bool ps) { return ps ? slot(s).ps : slot(s).xbox; }

struct Map {
    int a[kSlotCount];
    bool operator==(const Map& o) const { return std::equal(a, a + kSlotCount, o.a); }
    bool operator!=(const Map& o) const { return !(*this == o); }
};
inline Map defaults()
{
    Map m {};
    for (int s = 0; s < kSlotCount; ++s) m.a[s] = slot(s).def;
    return m;
}
inline bool validAction(int a) { return a >= 0 && a < kActionCount; }
inline bool isDefault(const Map& m, int s) { return s >= 0 && s < kSlotCount && m.a[s] == slot(s).def; }
inline int changed(const Map& m)
{
    int n = 0;
    for (int s = 0; s < kSlotCount; ++s) n += isDefault(m, s) ? 0 : 1;
    return n;
}
inline std::string summary(const Map& m)
{
    const int n = changed(m);
    return n == 0 ? std::string("Default") : std::to_string(n) + " changed";
}
inline const char* hint(const Map& m, int s) { return action(m.a[s >= 0 && s < kSlotCount ? s : 0]).hint; }

// --- file ----------------------------------------------------------------------------------------------------------
inline std::string lowerTrim(const std::string& v)
{
    size_t b = v.find_first_not_of(" \t\r"), e = v.find_last_not_of(" \t\r");
    std::string s = b == std::string::npos ? std::string() : v.substr(b, e - b + 1);
    for (char& c : s) if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    return s;
}
inline int slotFromKey(const std::string& k)
{
    for (int s = 0; s < kSlotCount; ++s) if (k == slot(s).key) return s;
    return -1;
}
inline int actionFromKey(const std::string& k)
{
    for (int a = 0; a < kActionCount; ++a) if (k == action(a).key) return a;
    return -1;
}
// "button<TAB>action" lines ("=" works too); '#' comments, blank, unknown or broken lines are skipped, a later line
// wins. Only the first kMaxFileBytes count. Anything not named keeps its default.
inline Map parse(const std::string& text)
{
    Map m = defaults();
    const std::string t = text.substr(0, std::min(text.size(), kMaxFileBytes));
    size_t i = 0;
    while (i < t.size()) {
        size_t j = t.find('\n', i);
        if (j == std::string::npos) j = t.size();
        const std::string line = t.substr(i, j - i);
        i = j + 1;
        size_t sep = line.find('\t');
        if (sep == std::string::npos) sep = line.find('=');
        if (sep == std::string::npos || lowerTrim(line).rfind("#", 0) == 0) continue;
        const int s = slotFromKey(lowerTrim(line.substr(0, sep)));
        const int a = actionFromKey(lowerTrim(line.substr(sep + 1)));
        if (s >= 0 && a >= 0) m.a[s] = a;
    }
    return m;
}
inline std::string serialize(const Map& m)
{
    std::string out = "# Omni controller shortcuts: button<TAB>action (Browser settings > Controller shortcuts)\n";
    for (int s = 0; s < kSlotCount; ++s) out += std::string(slot(s).key) + "\t" + action(validAction(m.a[s]) ? m.a[s] : slot(s).def).key + "\n";
    return out;
}

// --- choosing ------------------------------------------------------------------------------------------------------
// D-pad left / right on a button row: the previous / next action in the list's order (wraps).
inline int stepAction(int a, int dir)
{
    const auto& c = choices();
    const int n = int(c.size());
    auto at = std::find(c.begin(), c.end(), a);
    const int i = at == c.end() ? 0 : int(at - c.begin());
    return c[size_t(((i + dir) % n + n) % n)];
}
inline int choiceIndex(int a)
{
    const auto& c = choices();
    auto at = std::find(c.begin(), c.end(), a);
    return at == c.end() ? 0 : int(at - c.begin());
}
// The first other button with this action ("" none / Nothing).
inline int otherSlot(const Map& m, int a, int except)
{
    if (a == aNone) return -1;
    for (int s = 0; s < kSlotCount; ++s) if (s != except && m.a[s] == a) return s;
    return -1;
}

// --- problems ------------------------------------------------------------------------------------------------------
enum Kind : int { kDuplicate, kAddonOwns, kNoAddressBar, kSwitcherNoL2 };
struct Conflict { int kind; int slot; int other; };
// addonSlot: sL3 / sTouchpad when an add-on quick switch uses that button (it goes first, as today), else -1.
inline std::vector<Conflict> conflicts(const Map& m, int addonSlot)
{
    std::vector<Conflict> out;
    for (int s = 0; s < kSlotCount; ++s) {
        const int o = otherSlot(m, m.a[s], s);
        if (o >= 0) out.push_back({ kDuplicate, s, o });
    }
    if (addonSlot == sL3 || addonSlot == sTouchpad) out.push_back({ kAddonOwns, addonSlot, -1 });
    bool address = false;
    for (int s = 0; s < kSlotCount; ++s) address |= m.a[s] == aAddressBar && s != addonSlot;
    if (!address) out.push_back({ kNoAddressBar, -1, -1 });
    for (int s = 0; s < kSlotCount; ++s)
        if (m.a[s] == aTabSwitcher && !slot(s).l2) out.push_back({ kSwitcherNoL2, s, -1 });
    return out;
}
inline std::string conflictText(const Conflict& c, bool ps)
{
    switch (c.kind) {
    case kDuplicate: return "Also on " + slotName(c.other, ps);
    case kAddonOwns: return "Used by the add-on quick switch (Options > Add-ons)";
    case kNoAddressBar: return std::string("No button opens the address bar: point at it and press ") + (ps ? "Cross" : "A");
    case kSwitcherNoL2: return ps ? "Tab switcher: Cross switches, Circle cancels" : "Tab switcher: A switches, B cancels";
    }
    return std::string();
}
// A button row's second line: its first problem, else "Default: ..." when changed, else nothing.
inline std::string slotDetail(const Map& m, int s, int addonSlot, bool ps)
{
    for (const Conflict& c : conflicts(m, addonSlot))
        if (c.slot == s) return conflictText(c, ps);
    if (!isDefault(m, s)) return "Default: " + std::string(action(slot(s).def).label);
    return std::string();
}
// The panel's note line: the problems that belong to no single button.
inline std::string panelNote(const Map& m, int addonSlot, bool ps)
{
    for (const Conflict& c : conflicts(m, addonSlot))
        if (c.slot < 0) return conflictText(c, ps);
    return ps ? "D-pad \xe2\x97\x80 \xe2\x96\xb6 change   Cross: the list   Triangle: this button's default"
              : "D-pad \xe2\x97\x80 \xe2\x96\xb6 change   A: the list   Y: this button's default";
}
// The action list's second line for action `a` while choosing for button `s`.
inline std::string usedBy(const Map& m, int a, int s, bool ps)
{
    const int o = otherSlot(m, a, s);
    return o >= 0 ? "Also on " + slotName(o, ps) : std::string();
}

// --- Controls guide ------------------------------------------------------------------------------------------------
// The guide row (OmniControlsHelp.h: its action text and `where`) that documents a remappable button's default, or -1.
inline int guideSlot(const char* rowAction, const char* where)
{
    if (!rowAction || !where) return -1;
    static const struct { const char* text; const char* wherePrefix; int s; } k[] = {
        { "Address bar", "button()", sTriangle },
        { "New tab", "button()", sSquare },
        { "Close tab", "button()", sR3 },
        { "Add this page to shortcuts", "button()", sL3 },
        { "Translate page", "button()", sTouchpad },
        { "Copy the text, link or page address", "omniL2Chord", sL2Square },
        { "Paste into the text box", "omniL2Chord", sL2Triangle },
        { "Options menu", "omniL2Chord", sL2Cross },
        { "Browser settings", "omniL2Chord", sL2Circle },
    };
    const std::string a = rowAction, w = where;
    for (const auto& e : k)
        if (a == e.text && w.rfind(e.wherePrefix, 0) == 0) return e.s;
    return -1;
}
// For such a row: what the button does now (false: on its default, the row stays as written).
inline bool guideText(const Map& m, int s, int addonSlot, std::string& outAction, std::string& outNote)
{
    if (s < 0 || s >= kSlotCount || isDefault(m, s)) return false;
    outAction = action(m.a[s]).label;
    outNote = s == addonSlot ? "Your choice (Browser settings > Controller shortcuts); the add-on quick switch comes first"
                             : "Your choice (Browser settings > Controller shortcuts)";
    return true;
}

} // namespace OmniButtonMap
'''

SHELL = r'''// OMNI_BUTTON_MAP_V1: "Controller shortcuts" (shell side). Included from OmniBrowser.cpp right after OmniAddons.h
// (inside its anonymous namespace: it reads the add-on quick-switch button). The pure part is OmniButtonMap.h; the
// reasons are in tools/apply_button_map.py. Main thread only. Hooks: button()'s browsing tail (omniBmapBrowse),
// omniL2Chord (omniBmapL2), omniBrowseHints (omniBmapBrowseHints), Browser settings (row OBMP::kSettingsRowId).
// A button on its default returns false everywhere: the original line runs, so the defaults are today's buttons.
#pragma once

namespace OBMP = OmniButtonMap;
static OBMP::Map omniBmap = OBMP::defaults();
static bool omniBmapLoaded = false;
static int omniBmapPickSlot = 0;
static void omniL2Copy();    // OMNI_L2_CHORDS_V1 (OmniBrowser.cpp, after this file)
static void omniL2Paste();

static void omniBmapLoad()
{
    if (omniBmapLoaded) return;
    omniBmapLoaded = true;
    if (omniTestMode()) return;   // self-tests keep today's buttons
    FILE* f = fopen(omniData(OBMP::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[1024];
    size_t n = 0;
    while (text.size() < OBMP::kMaxFileBytes && (n = fread(buf, 1, sizeof(buf), f)) > 0) text.append(buf, n);
    fclose(f);
    omniBmap = OBMP::parse(text);
    fprintf(stderr, "OMNI BUTTON MAP: %d button(s) changed\n", OBMP::changed(omniBmap)); fflush(stderr);
}
static void omniBmapSave() { omniIoQueue(omniData(OBMP::kFileName), OBMP::serialize(omniBmap), false); }
static int omniBmapAddonSlot()
{
    if (!omniAdReady || !omniAdQuick()) return -1;
    return omniAdState.shortcut == "l3" ? OBMP::sL3 : omniAdState.shortcut == "touchpad" ? OBMP::sTouchpad : -1;
}
static std::string omniBmapName(int s) { return OBMP::slotName(s, playStationIcons); }

// --- running an action (a page, nothing over it: button()'s browsing tail or omniL2Chord) --------------------------
static void omniBmapSwitcher()   // OMNI_TAB_SWITCHER_V1's strip, opened by a button: Cross switches, Circle cancels
{
    if (omniTsw.open || !omniTswBrowsing()) return;
    omniTswBuild();
    const int n = int(omniTsw.tabs.size());
    if (n < 2) { omniTsw.tabs.clear(); notice(OTSW::noOtherTabs()); return; }
    omniTsw.open = true;
    omniTsw.sel = OTSW::firstSel(n, true);
    omniTsw.first = OTSW::window(0, omniTsw.sel, n);
    if (omniL2Held) omniL2ChordUsed = true;   // from an L2 chord: letting go of L2 switches, as L2 + R1
    fprintf(stderr, "OMNI TAB SWITCHER: open, %d tabs (button map)\n", n); fflush(stderr);
}
static void omniBmapRun(int a)
{
    Tab* t = active();
    if (!t) return;
    switch (a) {
    case OBMP::aNone: break;
    case OBMP::aAddressBar: if (WKPageIsContentEditable(t->page)) editPage(); else editAddress(); break;
    case OBMP::aNewTab: if (newTab()) { if (!omniTestMode()) omniOpenNewTabPage(active()); address.clear(); editing = true; omniKbPageReset(); } break;
    case OBMP::aCloseTab: if (omniPtMayClose(*t)) closeTab(); break;
    case OBMP::aBack: omniFxBack(); break;
    case OBMP::aForward: omniFxForward(); break;
    case OBMP::aReload: if (t->loading) omniFxStop(); else WKPageReload(t->page); break;
    case OBMP::aNowPlaying: omniNpShow(); break;
    case OBMP::aScreenshot:   // omniQaShotChord's context
        if (pageEditing || omniFindBarOpen() || omniTestMode()) break;
        if (omniMediaDownloadsEnabled && omniSavedOwnedView() != OmniSavedView::None) break;
        omniPtScreenshot();
        break;
    case OBMP::aFind: omniFindStart(); break;
    case OBMP::aReader: omniReaderStart(); break;
    case OBMP::aBookmark: omniFxBookmarkToggleCurrent(); break;
    case OBMP::aQrShare: omniQrShow(); break;
    case OBMP::aMagnifier:   // omniMagChord's steps: off -> 2x -> 3x -> off
        if (!omniMagBrowsing()) break;
        if (!omniMagAvailable()) { omniMagZoom = OMAG::kOff; notice(OMAG::unavailableNotice()); }
        else omniMagSet(OMAG::nextZoom(omniMagZoom));
        break;
    case OBMP::aTabSwitcher: omniBmapSwitcher(); break;
    case OBMP::aOptionsMenu: omniFxQuickMenuShow(); break;
    case OBMP::aAddShortcut: omniShortcutAddCurrent(); break;
    case OBMP::aTranslate: omniTranslateToggle(); break;
    case OBMP::aCopy: omniL2Copy(); break;
    case OBMP::aPaste: omniL2Paste(); break;
    case OBMP::aBrowserSettings: omniFxSettingsShow(); break;
    default: break;
    }
    omniShellDirty = true;
}
static int omniBmapSlot(int button, bool l2)
{
    if (l2) {
        switch (button) {
        case SDL_CONTROLLER_BUTTON_X: return OBMP::sL2Square;
        case SDL_CONTROLLER_BUTTON_Y: return OBMP::sL2Triangle;
        case SDL_CONTROLLER_BUTTON_A: return OBMP::sL2Cross;
        case SDL_CONTROLLER_BUTTON_B: return OBMP::sL2Circle;
        default: return -1;
        }
    }
    switch (button) {
    case SDL_CONTROLLER_BUTTON_Y: return OBMP::sTriangle;
    case SDL_CONTROLLER_BUTTON_X: return OBMP::sSquare;
    case SDL_CONTROLLER_BUTTON_RIGHTSTICK: return OBMP::sR3;
    case SDL_CONTROLLER_BUTTON_LEFTSTICK: return OBMP::sL3;
    case SDL_CONTROLLER_BUTTON_TOUCHPAD: return OBMP::sTouchpad;
    default: return -1;
    }
}
// button()'s browsing tail, first. False: not ours, or on its default (the original line runs).
static bool omniBmapBrowse(int button)
{
    const int s = omniBmapSlot(button, false);
    if (s < 0) return false;
    omniBmapLoad();
    if (OBMP::isDefault(omniBmap, s)) return false;
    if ((s == OBMP::sL3 || s == OBMP::sTouchpad) && omniAdShortcut(button)) return true;   // the add-on quick switch first, as before
    fprintf(stderr, "OMNI BUTTON MAP: %s -> %s\n", OBMP::slot(s).key, OBMP::action(omniBmap.a[s]).key); fflush(stderr);
    omniBmapRun(omniBmap.a[s]);
    return true;
}
// omniL2Chord, after it claimed the press (Square / Triangle / Cross / Circle). False: on its default.
static bool omniBmapL2(int button)
{
    const int s = omniBmapSlot(button, true);
    if (s < 0) return false;
    omniBmapLoad();
    if (OBMP::isDefault(omniBmap, s)) return false;
    fprintf(stderr, "OMNI BUTTON MAP: %s -> %s\n", OBMP::slot(s).key, OBMP::action(omniBmap.a[s]).key); fflush(stderr);
    omniBmapRun(omniBmap.a[s]);
    return true;
}
// omniBrowseHints, first: the bottom bar with the chosen Triangle / Square actions (false: both on their defaults).
static bool omniBmapBrowseHints()
{
    omniBmapLoad();
    if (OBMP::isDefault(omniBmap, OBMP::sTriangle) && OBMP::isDefault(omniBmap, OBMP::sSquare)) return false;
    std::vector<OmniHint> left = { { 0, "Click" } };
    if (*OBMP::hint(omniBmap, OBMP::sTriangle)) left.push_back({ 3, OBMP::hint(omniBmap, OBMP::sTriangle) });
    if (*OBMP::hint(omniBmap, OBMP::sSquare)) left.push_back({ 2, OBMP::hint(omniBmap, OBMP::sSquare) });
    left.push_back({ omniHintShoulders, "Tabs" });
    left.push_back({ 1, "Back" });
    omniHints(left, { { omniHintMenu, "Menu" } });
    return true;
}

// --- Browser settings > Controller shortcuts -----------------------------------------------------------------------
static void omniBmapChanged()
{
    omniBmapSave();
    omniFxRefresh();
}
static void omniBmapPickBuild(OmniFxPanel& p)
{
    const int s = omniBmapPickSlot;
    for (int a : OBMP::choices()) {
        OmniFxRow r;
        r.id = a;
        r.label = OBMP::action(a).label;
        r.value = omniBmap.a[s] == a ? "Current" : OBMP::slot(s).def == a ? "Default" : "";
        r.detail = OBMP::usedBy(omniBmap, a, s, playStationIcons);
        p.rows.push_back(r);
    }
}
static bool omniBmapPickInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A || !OBMP::validAction(r.id)) return false;
    const int s = omniBmapPickSlot;
    omniBmap.a[s] = r.id;
    omniBmapSave();
    notice(omniBmapName(s) + ": " + OBMP::action(r.id).label);
    omniFxPop();   // back to the buttons (rebuilt)
    return true;
}
static void omniBmapPickShow(int s)
{
    omniBmapPickSlot = s;
    OmniFxPanel p;
    p.kind = OBMP::kPickKind; p.title = omniBmapName(s); p.subtitle = "While browsing a page"; p.w = 760; p.maxVisible = 9;
    p.build = omniBmapPickBuild; p.input = omniBmapPickInput;
    p.sel = OBMP::choiceIndex(omniBmap.a[s]);   // the highlight starts on the current action
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
static void omniBmapListBuild(OmniFxPanel& p)
{
    const int addon = omniBmapAddonSlot();
    for (int s = 0; s < OBMP::kSlotCount; ++s) {
        OmniFxRow r;
        r.id = s;
        r.label = omniBmapName(s);
        r.value = OBMP::action(omniBmap.a[s]).label;
        r.stepper = true;
        r.detail = OBMP::slotDetail(omniBmap, s, addon, playStationIcons);
        p.rows.push_back(r);
    }
    OmniFxRow z;
    z.id = OBMP::kResetRowId; z.label = "Reset to defaults"; z.enabled = OBMP::changed(omniBmap) > 0;
    p.rows.push_back(z);
    p.extra = OBMP::panelNote(omniBmap, addon, playStationIcons);
}
static bool omniBmapListInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id == OBMP::kResetRowId) {
        if (b != SDL_CONTROLLER_BUTTON_A) return false;
        omniBmap = OBMP::defaults();
        omniBmapChanged();
        notice("Controller shortcuts are back to the defaults");
        return true;
    }
    if (r.id < 0 || r.id >= OBMP::kSlotCount) return false;
    const int dir = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 : b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : 0;
    if (dir) { omniBmap.a[r.id] = OBMP::stepAction(omniBmap.a[r.id], dir); omniBmapChanged(); return true; }
    if (b == SDL_CONTROLLER_BUTTON_Y) {
        if (OBMP::isDefault(omniBmap, r.id)) return true;
        omniBmap.a[r.id] = OBMP::slot(r.id).def;
        omniBmapChanged();
        notice(omniBmapName(r.id) + ": " + OBMP::action(omniBmap.a[r.id]).label + " (default)");
        return true;
    }
    if (b == SDL_CONTROLLER_BUTTON_A) { omniBmapPickShow(r.id); return true; }
    return false;
}
static void omniBmapListShow()
{
    omniBmapLoad();
    OmniFxPanel p;
    p.kind = OBMP::kListKind; p.title = "Controller shortcuts"; p.subtitle = "While browsing a page"; p.w = 800; p.maxVisible = 10;
    p.build = omniBmapListBuild; p.input = omniBmapListInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
static void omniBmapSettingsRow(OmniFxPanel& p)
{
    omniBmapLoad();
    OmniFxRow r;
    r.id = OBMP::kSettingsRowId; r.label = "Controller shortcuts..."; r.value = OBMP::summary(omniBmap);
    p.rows.push_back(r);
}
static bool omniBmapSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniBmapListShow();
    return true;
}

// --- Controls guide ------------------------------------------------------------------------------------------------
// A guide row (its action text and `where`) whose button is remapped: what it does now. Registered only when
// OmniControlsHelpShell.h offers the hook (OMNI_CH_REMAP_HOOK + omniChRemap, apply_controls_help.py).
[[maybe_unused]] static bool omniBmapGuideText(const char* rowAction, const char* where, std::string& outAction, std::string& outNote)
{
    omniBmapLoad();
    return OBMP::guideText(omniBmap, OBMP::guideSlot(rowAction, where), omniBmapAddonSlot(), outAction, outNote);
}
#ifdef OMNI_CH_REMAP_HOOK
[[maybe_unused]] static const bool omniBmapGuideHooked = (omniChRemap = omniBmapGuideText, true);
#endif
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTabSwitcher.h" // OMNI_TAB_SWITCHER_V1: hold L2 + L1 / R1 tab strip (pure)\n',
         '#include "OmniTabSwitcher.h" // OMNI_TAB_SWITCHER_V1: hold L2 + L1 / R1 tab strip (pure)\n'
         '#include "OmniButtonMap.h" // OMNI_BUTTON_MAP_V1: Controller shortcuts (pure)\n'),
        ('// Browsing: what each button does today (button()). Edit here when a button\'s action changes.\n'
         'static void omniBrowseHints()\n{\n',
         'static bool omniBmapBrowseHints(); // OMNI_BUTTON_MAP_V1 (OmniButtonMapShell.h): the bar with a remapped Triangle / Square\n'
         '// Browsing: what each button does today (button()). Edit here when a button\'s action changes.\n'
         'static void omniBrowseHints()\n{\n'
         '    if (omniBmapBrowseHints()) return; // OMNI_BUTTON_MAP_V1\n'),
        ('void button(int button)\n{\n',
         'static bool omniBmapBrowse(int button); // OMNI_BUTTON_MAP_V1 (OmniButtonMapShell.h): Triangle / Square / R3 / L3 / touchpad\n'
         'void button(int button)\n{\n'),
        ('    if (!active()) return;\n    if (button == SDL_CONTROLLER_BUTTON_A) click();\n',
         '    if (!active()) return;\n'
         '    if (omniBmapBrowse(button)) return; // OMNI_BUTTON_MAP_V1: a remapped button (on its default: false, the lines below run)\n'
         '    if (button == SDL_CONTROLLER_BUTTON_A) click();\n'),
        ('    if (event.button == SDL_CONTROLLER_BUTTON_X) omniL2Copy();            // Square\n',
         '    if (omniBmapL2(event.button)) return true; // OMNI_BUTTON_MAP_V1: a remapped L2 chord (on its default: false)\n'
         '    if (event.button == SDL_CONTROLLER_BUTTON_X) omniL2Copy();            // Square\n'),
        ('#include "OmniAddons.h" // OMNI_ADDONS_V1\n',
         '#include "OmniAddons.h" // OMNI_ADDONS_V1\n'
         '#include "OmniButtonMapShell.h" // OMNI_BUTTON_MAP_V1 (after add-ons: it reads the quick-switch button)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniPfSettingsInput(int b);\n',
         'static bool omniPfSettingsInput(int b);\n'
         'static void omniBmapSettingsRow(OmniFxPanel& p); // OMNI_BUTTON_MAP_V1 (OmniButtonMapShell.h): "Controller shortcuts..."\n'
         'static bool omniBmapSettingsInput(int b);\n'),
        ('    omniPfSettingsRow(p); // OMNI_PAD_FEEDBACK_V1: Controller light & rumble (Off / On)\n',
         '    omniPfSettingsRow(p); // OMNI_PAD_FEEDBACK_V1: Controller light & rumble (Off / On)\n'
         '    omniBmapSettingsRow(p); // OMNI_BUTTON_MAP_V1: Controller shortcuts...\n'),
        ('    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n',
         '    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n'
         '    if (r.id == OmniButtonMap::kSettingsRowId) return omniBmapSettingsInput(b); // OMNI_BUTTON_MAP_V1\n'),
    ],
}

# Ids / names this patch takes: refused when something else already has them.
TAKEN = [r'\b842\b', r'\b7450\b', r'\b7451\b', r'\bOBMP\b', r'\bomniBmap', r'shortcuts-map\.txt']


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


def ids_free():
    """Before the first apply: no entry file and no other apply_*.py may use our ids / names."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS):
        return
    me = Path(__file__).resolve()
    places = [p for p in root.iterdir() if p.suffix in ('.h', '.cpp') and p.name not in ('OmniButtonMap.h', 'OmniButtonMapShell.h')]
    # Engine tree only, comments ignored: sibling apply_*.py files are not scanned (their notes name other patches'
    # ids and aliases; a hit there would also stop the title build, which runs every script from this folder).
    for p in places:
        s = cpp_code(p.read_bytes().decode('utf-8', 'replace'))
        for pat in (TAKEN[:3] if p.name in GUIDE else TAKEN):
            m = re.search(pat, s)
            if m:
                sys.exit('%s already uses %r (line %d): pick other ids' % (p.name, m.group(0), s.count('\n', 0, m.start()) + 1))


def main():
    ob = (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8')
    f3 = (root / 'OmniFeatures3.h').read_bytes().decode('utf-8')
    bs = (root / 'OmniBrowserSettings.h').read_bytes().decode('utf-8')
    for text, need, tool in ((ob, 'OMNI_L2_CHORDS_V1', 'apply_l2_chords.py (base T)'), (ob, 'OMNI_TAB_SWITCHER_V1', 'apply_tab_switcher.py'),
                             (ob, 'OMNI_FIND_PLUS_V1', 'apply_find_plus.py'), (f3, 'OMNI_MAGNIFIER_V1', 'apply_magnifier.py'),
                             (f3, 'OMNI_QR_SHARE_V1', 'apply_qr_share.py'), (f3, 'OMNI_MEDIA_CONTROLS_V1', 'apply_media_controls.py'),
                             (f3, 'OMNI_PINNED_TABS_V1', 'apply_pinned_tabs.py'), (bs, 'OMNI_PAD_FEEDBACK_V1', 'apply_pad_feedback.py')):
        if need not in text:
            sys.exit('%s missing: %s first' % (need, tool))
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniButtonMap.h', PURE, 'OmniTabSwitcher.h'),
            write_new('OmniButtonMapShell.h', SHELL, 'OmniTabSwitcherShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
