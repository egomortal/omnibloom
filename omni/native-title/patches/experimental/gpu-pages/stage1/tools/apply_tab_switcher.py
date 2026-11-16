#!/usr/bin/env python3
"""OMNI_TAB_SWITCHER_V1 (2026-11-16): a quick tab switcher, like Alt-Tab, for the controller.

What the user sees
  - While browsing (a page, nothing over it), hold L2 and press R1 (LT + RB with Xbox labels): a strip of tiles
    comes up over the dimmed page, most recently used tab first:
        Switch tab                                                    2 of 6
        [G]           [Y]            [W]          ...
        GitHub        Lo-fi radio    Tea - Wik..
        This tab      youtube.com    wikipedia.org
    The highlight starts on the previous tab (R1) or the least recent one (L1). Keep L2 held: R1 / L1 or D-pad
    right / left move it (it wraps); let go of L2: that tab is shown (activate(); an unloaded tab reloads as usual).
    Cross switches at once, Circle closes the strip without switching. Quick L2 + R1, release = back to the last tab.
  - Each tile: a site-letter square (the site's name, "en.wikipedia.org" -> W; its colour is fixed per site), the
    title, then the site (or "This tab" / "Private"). Pinned tabs have a pin in the corner; a tab in a group has the
    group's colour as a bar along the tile's top (OMNI_PINNED_TABS_V1 / OMNI_TAB_GROUPS_V1). At most 7 tiles show;
    arrows mark more on either side.
  - Private: from a normal tab only normal tabs are offered; from a private tab private and normal ones
    (OmniTabSearch::visible, the "Switch to tab" rule). With nothing else to offer: "No other tabs to switch to".
  - Thumbnails: Omni keeps no per-tab snapshot (no snapshot / thumbnail in OmniTabsPage.h, OmniTabMemory.h or any
    other entry file; the Tabs panel and tab search draw text rows), so the tiles are site letters. Nothing is
    captured, so the strip costs nothing while closed and one panel draw per frame while open.

Why hold L2 + L1 / R1 (checked in the patched tree, 2026-11-16)
  - Controls guide table (OmniControlsHelp.h): L2 rows are L2 + Square / Triangle / Cross / Circle / D-pad up-down /
    R3 / L3 (Quick actions), L2 alone (Saved links), L2 / R2 (keyboard caret, editing only); no L2 + L1 / R1 row.
    L1 + R1 together is "Open Media downloads" (omniShoulderButton OpenSection), R2 is "Send this page to Media
    downloads" (omniSavedAxis Prefill), so L1 + R1 and R2 + shoulder are taken.
  - Handlers: omniL2Chord acts on X / Y / A / B / D-pad up-down only (returns false for the shoulders);
    omniQaShotChord reads the L2 axis with R3; omniMagChord with L3 (and Circle); omniKbTick reads L2 / R2 only while
    editing (the switcher is off while editing). No handler reads the L2 axis together with L1 / R1 (grep
    SDL_CONTROLLER_AXIS_TRIGGERLEFT / BUTTON_LEFTSHOULDER / BUTTON_RIGHTSHOULDER), so L2 + L1 / R1 used to fall
    through to plain L1 / R1 (previous / next tab), which this replaces with the MRU strip.
  - The L1 / R1 state machine (omniShoulderChord, Media downloads): the switcher takes BOTH edges of a shoulder press
    it used (a bit mask, as omniL2Swallow), so the machine never sees half a press; its after-drain reconcile()
    sees the held button, waits for neutral and never makes a click from polling (OmniShoulderChord.h). The L2
    release is not a saved-links tap (omniL2ChordUsed, as every L2 chord).
  - D-pad left / right only move the highlight while the strip is up (L2 + D-pad left / right is not a chord);
    D-pad up / down are swallowed while it is up (no site zoom under the strip).

Pure part: engine/entry/OmniTabSwitcher.h (no SDL / WebKit): MRU order, visibility, selection wrap, the visible
window, input decisions, site letter / colour, texts. Tested by tools/test_tab_switcher.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_switcher.cpp -o t && ./t
Shell side: engine/entry/OmniTabSwitcherShell.h (included from OmniFeatures3.h after OmniTabGroupsShell.h: it reads
omniTgModel and omniPtPinned). It registers its own overlay layer (drawn by omniOverlayDraw, blocks the page, takes
any button that reaches button() while up); MRU from OmniTabMemory's omniTmTabs[tab].shownAt.

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp  the OmniHistoryPlus.h include line (pure include after it, file scope);
                   omniL2Track's head (declarations before it);
                   omniL2Track's release lines (omniTswRelease between them);
                   omniL2Chord's definition head (the switcher's chord first).
  OmniFeatures3.h  the OmniTabGroupsShell.h include line (OmniTabSwitcherShell.h after it).
Apply AFTER apply_l2_chords.py (base T), apply_history_plus.py, apply_pinned_tabs.py, apply_tab_groups.py and apply_magnifier.py.
usage: apply_tab_switcher.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TAB_SWITCHER_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TAB_SWITCHER_V1: the pure part of the quick tab switcher (hold L2, L1 / R1 to choose, release to switch).
// No SDL, no WebKit. The shell side is OmniTabSwitcherShell.h; the reasons are in tools/apply_tab_switcher.py.
// Tested on the host with g++ (test_tab_switcher.cpp).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniTabSwitcher {

constexpr int kVisible = 7;      // tiles on screen at once (1280-px layout: 7 x 150 + gaps)
constexpr int kColours = 8;

// --- order ---------------------------------------------------------------------------------------------------------
struct Item {
    uint32_t shownAt = 0;   // OmniTabMemory's shownAt (SDL ticks when the tab was last the active one)
    bool seen = false;      // it has an OmniTabMemory entry (false: a background tab never shown)
    bool priv = false, current = false;
};
// Private tabs only from a private tab; normal tabs always (OmniTabSearch::visible's rule).
inline bool visible(bool itemPrivate, bool currentPrivate) { return !itemPrivate || currentPrivate; }
// Newer first; ticks wrap after ~49 days, so compare by difference (tabs are shown within days of each other).
inline bool newer(uint32_t a, uint32_t b) { return int32_t(a - b) > 0; }
// Positions in `items` in strip order: the current tab, then the most recently shown, never-shown tabs last (tab order).
inline std::vector<int> order(const std::vector<Item>& items)
{
    bool curPriv = false;
    for (const Item& it : items) if (it.current) curPriv = it.priv;
    std::vector<int> out, rest;
    for (size_t i = 0; i < items.size(); ++i) {
        if (items[i].current) out.push_back(int(i));
        else if (visible(items[i].priv, curPriv)) rest.push_back(int(i));
    }
    if (out.size() > 1) out.resize(1);
    std::stable_sort(rest.begin(), rest.end(), [&items](int a, int b) {
        const Item& x = items[size_t(a)];
        const Item& y = items[size_t(b)];
        if (x.seen != y.seen) return x.seen;
        return x.seen && newer(x.shownAt, y.shownAt);
    });
    out.insert(out.end(), rest.begin(), rest.end());
    return out;
}

// --- selection -----------------------------------------------------------------------------------------------------
inline int step(int sel, int n, int delta) { return n <= 0 ? 0 : ((sel + delta) % n + n) % n; }
// Where the highlight starts: R1 the previous tab (1), L1 the least recent one (n - 1).
inline int firstSel(int n, bool forward) { return n <= 1 ? 0 : forward ? 1 : n - 1; }
// The first tile shown so that `sel` is on screen (moving as little as possible).
inline int window(int first, int sel, int n, int vis = kVisible)
{
    if (n <= vis) return 0;
    if (sel < first) first = sel;
    else if (sel >= first + vis) first = sel - vis + 1;
    return std::clamp(first, 0, n - vis);
}
inline std::string counter(int sel, int n) { return std::to_string(sel + 1) + " of " + std::to_string(n); }

// --- input ---------------------------------------------------------------------------------------------------------
enum Button { bOther, bL1, bR1, bLeft, bRight, bUp, bDown, bCross, bCircle };
enum Act { aPass, aOpenNext, aOpenPrev, aNext, aPrev, aCommit, aCancel, aSwallow };
// A button press. Closed: only L2 held + L1 / R1 while browsing opens it. Open: it takes every press.
inline Act classify(Button b, bool open, bool l2Held, bool browsing)
{
    if (!open) {
        if (!l2Held || !browsing) return aPass;
        return b == bR1 ? aOpenNext : b == bL1 ? aOpenPrev : aPass;
    }
    switch (b) {
    case bL1: case bLeft: return aPrev;
    case bR1: case bRight: return aNext;
    case bCross: return aCommit;
    case bCircle: return aCancel;
    default: return aSwallow;
    }
}
// Buttons whose press was ours: their release is kept from everything else too.
struct Swallow {
    unsigned bits = 0;
    static unsigned bit(int button) { return button >= 0 && button < 32 ? 1u << button : 0; }
    void take(int button) { bits |= bit(button); }
    bool release(int button) { const unsigned b = bit(button); if (!(bits & b)) return false; bits &= ~b; return true; }
};

// --- tiles ---------------------------------------------------------------------------------------------------------
inline std::string lower(std::string s)
{
    for (char& c : s) if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    return s;
}
// Lowercased host of an http(s) address without www. and port ("" for anything else).
inline std::string hostOf(const std::string& url)
{
    std::string s = lower(url);
    size_t p = 0;
    if (s.compare(0, 8, "https://") == 0) p = 8;
    else if (s.compare(0, 7, "http://") == 0) p = 7;
    else return std::string();
    const size_t end = s.find_first_of("/?#", p);
    s = s.substr(p, end == std::string::npos ? std::string::npos : end - p);
    const size_t at = s.rfind('@');
    if (at != std::string::npos) s.erase(0, at + 1);
    if (!s.empty() && s[0] == '[') return s.substr(0, s.find(']') + 1);   // IPv6 literal
    s = s.substr(0, s.find(':'));
    if (s.compare(0, 4, "www.") == 0) s.erase(0, 4);
    return s;
}
inline bool numericHost(const std::string& h)
{
    if (h.empty()) return false;
    if (h[0] == '[') return true;
    for (char c : h) if (!((c >= '0' && c <= '9') || c == '.')) return false;
    return true;
}
// The site's name: "en.wikipedia.org" -> "wikipedia", "bbc.co.uk" -> "bbc", "m.youtube.com" -> "youtube".
inline std::string siteName(const std::string& host)
{
    if (host.empty() || numericHost(host)) return host;
    std::vector<std::string> l;
    size_t i = 0;
    while (i <= host.size()) {
        const size_t j = host.find('.', i);
        const size_t e = j == std::string::npos ? host.size() : j;
        if (e > i) l.push_back(host.substr(i, e - i));
        i = e + 1;
    }
    if (l.size() > 1) l.pop_back();   // the top-level domain
    static const char* const generic[] = { "co", "com", "org", "net", "gov", "ac", "edu", "ne", "or", "go" };
    if (l.size() > 1 && std::find(std::begin(generic), std::end(generic), l.back()) != std::end(generic)) l.pop_back();
    return l.empty() ? host : l.back();
}
inline bool asciiAlnum(unsigned char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
inline std::string upper1(unsigned char c) { return std::string(1, char(c >= 'a' && c <= 'z' ? c - ('a' - 'A') : c)); }
// The tile's letter: the site name's first letter / digit, else the title's (its first character when it has no
// ASCII letter, kept whole as UTF-8), else "?".
inline std::string letter(const std::string& url, const std::string& title)
{
    for (unsigned char c : siteName(hostOf(url))) if (asciiAlnum(c)) return upper1(c);
    for (unsigned char c : title) if (asciiAlnum(c)) return upper1(c);
    size_t a = title.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "?";
    const unsigned char c = static_cast<unsigned char>(title[a]);
    size_t len = c >= 0xF0 ? 4 : c >= 0xE0 ? 3 : c >= 0xC0 ? 2 : 1;
    if (a + len > title.size()) len = 1;
    return title.substr(a, len);
}
struct Rgb { uint8_t r, g, b; };
// The same site always gets the same colour (FNV-1a of its name, or of the title when there is no site).
inline int colourIndex(const std::string& url, const std::string& title)
{
    const std::string host = hostOf(url);
    const std::string key = host.empty() ? lower(title) : siteName(host);
    uint32_t h = 2166136261u;
    for (unsigned char c : key) { h ^= c; h *= 16777619u; }
    return int(h % uint32_t(kColours));
}
inline Rgb colour(int i)
{
    static const Rgb k[kColours] = { { 52, 110, 206 }, { 196, 64, 52 }, { 191, 122, 0 }, { 22, 135, 78 },
                                     { 150, 62, 168 }, { 0, 138, 156 }, { 205, 86, 48 }, { 84, 96, 178 } };
    return k[((i % kColours) + kColours) % kColours];
}
// The title line: the tab's title, else its site, else "New tab".
inline std::string shownTitle(const std::string& title, const std::string& url)
{
    if (title.find_first_not_of(" \t\r\n") != std::string::npos) return title;
    const std::string h = hostOf(url);
    return h.empty() ? "New tab" : h;
}
// The dim line under the title: "This tab" / "Private" before the site, joined with " · ".
inline std::string caption(const std::string& url, bool priv, bool current)
{
    std::string s = current ? "This tab" : "";
    if (priv) s += s.empty() ? "Private" : " \xC2\xB7 Private";
    const std::string h = hostOf(url);
    if (!h.empty()) s += s.empty() ? h : " \xC2\xB7 " + h;
    return s;
}
inline const char* releaseHint(bool playStation) { return playStation ? "Release L2 to switch" : "Release LT to switch"; }
inline const char* noOtherTabs() { return "No other tabs to switch to"; }

} // namespace OmniTabSwitcher
'''

SHELL = r'''// OMNI_TAB_SWITCHER_V1: the quick tab switcher strip (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniTabGroupsShell.h). The pure part is OmniTabSwitcher.h; the reasons
// are in tools/apply_tab_switcher.py. Main thread only. Hooks: omniL2Chord (presses, first), omniL2Track (L2 let go).
#pragma once

namespace OTSW = OmniTabSwitcher;

struct OmniTswState {
    bool open = false;
    std::vector<const void*> tabs;   // strip order (Tab pointers; checked against `tabs` before every use)
    int sel = 0, first = 0;
    OTSW::Swallow swallow;           // presses that were ours: their releases are kept from the page and the shell
};
static OmniTswState omniTsw;

static std::string omniTswURL(const Tab& t) { return !t.omniLazyURL.empty() ? t.omniLazyURL : t.url; }
static Tab* omniTswTab(const void* p) { for (auto& t : tabs) if (t.get() == p) return t.get(); return nullptr; }
// The context the strip opens in: a page, nothing over it (as the L2 chords and the magnifier).
static bool omniTswBrowsing()
{
    return active() && !editing && !pageEditing && !settingsOpen && !pageFullscreen && !omniOverlayOpen() && !omniFindBarOpen() && !omniTestMode();
}
static OTSW::Button omniTswButton(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return OTSW::bL1;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return OTSW::bR1;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: return OTSW::bLeft;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: return OTSW::bRight;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: return OTSW::bUp;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: return OTSW::bDown;
    case SDL_CONTROLLER_BUTTON_A: return OTSW::bCross;
    case SDL_CONTROLLER_BUTTON_B: return OTSW::bCircle;
    default: return OTSW::bOther;
    }
}
// The strip's tabs, most recently shown first (OmniTabMemory's shownAt).
static void omniTswBuild()
{
    std::vector<OTSW::Item> items;
    const Tab* cur = active();
    for (auto& t : tabs) {
        OTSW::Item it;
        auto f = omniTmTabs.find(t.get());
        it.seen = f != omniTmTabs.end();
        it.shownAt = it.seen ? f->second.shownAt : 0;
        it.priv = t->omniPrivate;
        it.current = t.get() == cur;
        items.push_back(it);
    }
    omniTsw.tabs.clear();
    for (int i : OTSW::order(items)) omniTsw.tabs.push_back(tabs[size_t(i)].get());
}
// Tabs closed while the strip is up (a page can close itself) leave it; the highlight stays on its tab.
static void omniTswPrune()
{
    const int n0 = int(omniTsw.tabs.size());
    const void* keep = omniTsw.sel >= 0 && omniTsw.sel < n0 ? omniTsw.tabs[size_t(omniTsw.sel)] : nullptr;
    omniTsw.tabs.erase(std::remove_if(omniTsw.tabs.begin(), omniTsw.tabs.end(), [](const void* p) { return !omniTswTab(p); }), omniTsw.tabs.end());
    const int n = int(omniTsw.tabs.size());
    if (n == n0) return;
    auto at = std::find(omniTsw.tabs.begin(), omniTsw.tabs.end(), keep);
    omniTsw.sel = at != omniTsw.tabs.end() ? int(at - omniTsw.tabs.begin()) : std::clamp(omniTsw.sel, 0, std::max(0, n - 1));
    omniTsw.first = OTSW::window(omniTsw.first, omniTsw.sel, n);
}
static void omniTswClose(const char* why)
{
    if (!omniTsw.open) return;
    omniTsw.open = false;
    omniTsw.tabs.clear();
    omniShellDirty = true;
    fprintf(stderr, "OMNI TAB SWITCHER: closed (%s)\n", why); fflush(stderr);
}
static void omniTswCommit()
{
    if (!omniTsw.open) return;
    omniTswPrune();
    const void* want = omniTsw.sel >= 0 && omniTsw.sel < int(omniTsw.tabs.size()) ? omniTsw.tabs[size_t(omniTsw.sel)] : nullptr;
    omniTswClose("switch");
    if (!want || want == active() || editing || settingsOpen || pageFullscreen) return;   // the context changed under it: stay
    for (size_t i = 0; i < tabs.size(); ++i) {
        if (tabs[i].get() != want) continue;
        fprintf(stderr, "OMNI TAB SWITCHER: switch to tab %zu of %zu\n", i, tabs.size()); fflush(stderr);
        activate(i);
        omniShellDirty = true;
        return;
    }
}
static void omniTswMove(int delta)
{
    omniTswPrune();
    const int n = int(omniTsw.tabs.size());
    if (n == 0) { omniTswClose("no tabs"); return; }
    omniTsw.sel = OTSW::step(omniTsw.sel, n, delta);
    omniTsw.first = OTSW::window(omniTsw.first, omniTsw.sel, n);
    omniShellDirty = true;
}
// omniL2Track: L2 let go (after omniL2Held went false): the highlighted tab is shown.
static void omniTswRelease() { if (omniTsw.open) omniTswCommit(); }
// omniL2Chord, first: L2 held + R1 / L1 opens the strip; while it is up it takes every press. Both edges of a press it
// used are kept (omniShoulderChord never sees half a shoulder press).
static bool omniTswChord(const SDL_ControllerButtonEvent& event)
{
    if (event.type == SDL_CONTROLLERBUTTONUP) return omniTsw.swallow.release(event.button);
    if (event.type != SDL_CONTROLLERBUTTONDOWN || !OTSW::Swallow::bit(event.button)) return false;
    if (omniTsw.open) {   // a dialog / full screen came up under the strip: it goes, the press goes on
        omniTsw.open = false;   // (our own layer is not counted by omniOverlayOpen())
        const bool other = omniOverlayOpen() || !active() || editing || settingsOpen || pageFullscreen;
        omniTsw.open = true;
        if (other) omniTswClose("context");
    }
    const OTSW::Act a = OTSW::classify(omniTswButton(event.button), omniTsw.open, omniL2Held, !omniTsw.open && omniTswBrowsing());
    if (a == OTSW::aPass) return false;
    omniTsw.swallow.take(event.button);
    omniL2ChordUsed = true;   // the L2 release is not a saved-links tap (OMNI_L2_CHORDS_V1)
    switch (a) {
    case OTSW::aOpenNext: case OTSW::aOpenPrev: {
        omniTswBuild();
        const int n = int(omniTsw.tabs.size());
        if (n < 2) { omniTsw.tabs.clear(); notice(OTSW::noOtherTabs()); omniShellDirty = true; break; }
        omniTsw.open = true;
        omniTsw.sel = OTSW::firstSel(n, a == OTSW::aOpenNext);
        omniTsw.first = OTSW::window(0, omniTsw.sel, n);
        omniShellDirty = true;
        fprintf(stderr, "OMNI TAB SWITCHER: open, %d tabs\n", n); fflush(stderr);
        break;
    }
    case OTSW::aNext: omniTswMove(1); break;
    case OTSW::aPrev: omniTswMove(-1); break;
    case OTSW::aCommit: omniTswCommit(); break;
    case OTSW::aCancel: omniTswClose("cancel"); break;
    default: break;
    }
    return true;
}
static void omniTswPin(int cx, int cy, SDL_Color c)   // a push pin: head + needle
{
    omniDisc(cx, cy, 6.f, c);
    fillRounded(cx - 1, cy + 4, 3, 9, 1, c);
}
static void omniTswDraw()
{
    if (!omniTsw.open) return;
    if (!controller || !SDL_GameControllerGetAttached(controller)) { omniTswClose("pad gone"); return; }
    omniTswPrune();
    const int n = int(omniTsw.tabs.size());
    if (n == 0) { omniTswClose("no tabs"); return; }
    const OmniTheme& T = omniTheme();
    const int vis = std::min(n, OTSW::kVisible), tw = 150, th = 148, gap = 14, pad = 26;
    const int w = vis * tw + (vis - 1) * gap + 2 * pad, h = 62 + th + pad;
    const int x0 = (width - w) / 2, y0 = std::max(8, (height - h) / 2 - 30);
    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, 110);
    omniShadow(x0, y0, w, h, omniRadius + 2, 22, 160, 6);
    fillRounded(x0, y0, w, h, omniRadius + 2, T.panel);
    omniLabel("Switch tab", x0 + pad, y0 + 32, omniBodyBold, T.ink);
    omniLabel(OTSW::counter(omniTsw.sel, n), x0 + w - pad, y0 + 32, omniSmall, T.inkFaint, 2);
    const Tab* cur = active();
    for (int k = 0; k < vis; ++k) {
        const int i = omniTsw.first + k;
        if (i >= n) break;
        const Tab* t = omniTswTab(omniTsw.tabs[size_t(i)]);
        if (!t) continue;
        const int x = x0 + pad + k * (tw + gap), y = y0 + 58;
        const bool sel = i == omniTsw.sel;
        if (sel) fillRounded(x - 4, y - 4, tw + 8, th + 8, omniRadius + 3, T.accent);
        fillRounded(x, y, tw, th, omniRadius + 1, sel ? T.raised : T.tab);
        const std::string url = omniTswURL(*t);
        const std::string site = omniWebURL(url) && !t->omniNewTabPage && !t->omniPagesTab ? url : std::string();
        const int gpos = OTG::indexOf(omniTgModel, OTG::groupOf(omniTgModel, t));   // OMNI_TAB_GROUPS_V1: the group's colour
        if (gpos >= 0 && gpos < int(omniTgModel.groups.size())) {
            const OTG::Rgb g = OTG::colour(omniTgModel.groups[size_t(gpos)].colour);
            fillRounded(x + 14, y + 6, tw - 28, 5, 2, { g.r, g.g, g.b, 255 });
        }
        const OTSW::Rgb c = OTSW::colour(OTSW::colourIndex(site, t->title));
        const int sq = 62, sx = x + (tw - sq) / 2, sy = y + 16;
        fillRounded(sx, sy, sq, sq, omniRadius + 2, { c.r, c.g, c.b, 255 });
        omniLabel(t->omniNewTabPage ? std::string("+") : OTSW::letter(site, t->title), sx + sq / 2.f, sy + sq / 2.f, omniTitle, { 255, 255, 255, 255 }, 1);
        if (omniPtPinned(*t)) omniTswPin(x + tw - 18, y + 18, sel ? T.ink : T.inkDim);   // OMNI_PINNED_TABS_V1
        omniLabel(OTSW::shownTitle(t->title, site), x + tw / 2.f, y + 100, omniSmallBold, T.ink, 1, tw - 16);
        omniLabel(OTSW::caption(site, t->omniPrivate, t == cur), x + tw / 2.f, y + 126, omniCaption, T.inkDim, 1, tw - 16);
    }
    const float my = y0 + 58 + th / 2.f;
    if (omniTsw.first > 0) omniIcon(omniIconBack, x0 + 12.f, my, T.inkDim);
    if (omniTsw.first + vis < n) omniIcon(omniIconForward, x0 + w - 12.f, my, T.inkDim);
    omniPanelHints({ { omniHintShoulders, "Choose" }, { 0, "Switch" }, { 1, "Cancel" } }, OTSW::releaseHint(playStationIcons));
}
static bool omniTswShown() { return omniTsw.open; }
static bool omniTswLayerButton(int) { return true; }   // a press that still reaches button() while the strip is up
static bool omniTswClick(int, int) { return true; }
[[maybe_unused]] static const bool omniTswLayers = [] {
    omniOverlayLayers().push_back({ omniTswShown, omniTswLayerButton, omniTswClick, [](double) { return true; }, omniTswDraw, true });
    return true;
}();
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHistoryPlus.h" // OMNI_HISTORY_PLUS_V1: history search, day groups, range deletes (pure)\n',
         '#include "OmniHistoryPlus.h" // OMNI_HISTORY_PLUS_V1: history search, day groups, range deletes (pure)\n'
         '#include "OmniTabSwitcher.h" // OMNI_TAB_SWITCHER_V1: hold L2 + L1 / R1 tab strip (pure)\n'),
        ('static void omniL2Track(const SDL_ControllerAxisEvent& event)\n{\n',
         'static void omniTswRelease(); // OMNI_TAB_SWITCHER_V1 (OmniTabSwitcherShell.h): L2 let go: show the chosen tab\n'
         'static bool omniTswChord(const SDL_ControllerButtonEvent& event); // OMNI_TAB_SWITCHER_V1: L2 + L1 / R1 strip\n'
         'static void omniL2Track(const SDL_ControllerAxisEvent& event)\n{\n'),
        ('        omniL2Held = false;\n'
         '        if (omniL2Pending && !omniL2ChordUsed) omniSavedL2();   // a plain tap: saved links, on release\n',
         '        omniL2Held = false;\n'
         '        omniTswRelease(); // OMNI_TAB_SWITCHER_V1: the strip was up: switch to its tab\n'
         '        if (omniL2Pending && !omniL2ChordUsed) omniSavedL2();   // a plain tap: saved links, on release\n'),
        ('static bool omniL2Chord(const SDL_ControllerButtonEvent& event)\n{\n',
         'static bool omniL2Chord(const SDL_ControllerButtonEvent& event)\n{\n'
         '    if (omniTswChord(event)) return true; // OMNI_TAB_SWITCHER_V1: L2 + L1 / R1, and every press while the strip is up\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTabGroupsShell.h" // OMNI_TAB_GROUPS_V1\n',
         '#include "OmniTabGroupsShell.h" // OMNI_TAB_GROUPS_V1\n'
         '#include "OmniTabSwitcherShell.h" // OMNI_TAB_SWITCHER_V1 (after tab groups and pinned tabs: it reads both)\n'),
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
    f3 = (root / 'OmniFeatures3.h').read_bytes().decode('utf-8')
    for need, tool in (('OMNI_TAB_GROUPS_V1', 'apply_tab_groups.py'), ('OMNI_PINNED_TABS_V1', 'apply_pinned_tabs.py')):
        if need not in f3:
            sys.exit('OmniFeatures3.h: %s missing: %s first' % (need, tool))
    ob = (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8')
    if 'omniL2Track' not in ob or 'OMNI_L2_CHORDS_V1' not in ob:
        sys.exit('OmniBrowser.cpp: OMNI_L2_CHORDS_V1 missing: apply_l2_chords.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTabSwitcher.h', PURE, 'OmniTabGroups.h'),
            write_new('OmniTabSwitcherShell.h', SHELL, 'OmniTabGroupsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
