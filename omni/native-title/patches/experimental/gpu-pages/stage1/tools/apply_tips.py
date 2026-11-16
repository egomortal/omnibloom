#!/usr/bin/env python3
"""OMNI_TIPS_V1 (2026-11-16): gentle one-time contextual tips, so people find the features that are already there.

What the user sees
  - The first time a context comes up, ONE small card sits above the bottom button bar (left side, over the page) for
    8 s:   "Tip   Hold L2 and tap R1 to switch tabs quickly; let go of L2 to jump   x"
    Pointer + Cross on the card closes it early. Each tip is shown once, ever; at most one tip per 10 minutes, none in
    the first minute after start (the Controls guide's own first-launch hint has that minute), never during
    full-screen / immersive video, never while typing (the keyboard or a page's text box), never over a panel, menu,
    dialog, Browser settings, History, the Controls guide or Media downloads, and not while a notice is up (a notice
    that comes up while a tip shows pushes the card up, above it).
  - A context counts for a short while after it ended ("fresh", per tip): a tip about the keyboard / full-screen
    video / the image viewer / the reading list shows right after it closed, never on top of it. A context that
    passes without a tip (rate limit, busy screen) is not "used up": it can arm the tip again next time.
  - Browser settings, after "Show controls guide":  "Show tips"  On / Off   and   "Reset tips"  ("3 seen"; Cross:
    every tip can show again, notice "Tips will show again").
  - Saved in /data/omni/tips-seen.txt (omniIoQueue): "omni-tips<TAB>1", "enabled<TAB>0|1", "seen<TAB><key>" lines;
    seen keys this build doesn't know are kept. Self-test modes (omniTestMode) read, write and show nothing.

The tips (trigger -> text; every button checked against the input code AND the Controls guide table, OmniControlsHelp.h
from apply_controls_help.py; tools/test_tips.cpp checks each tip's "facts" against that table):
  video      full-screen or immersive video seen; shown after it ends (60 s)
             "While a video plays, {Options} > Now playing has speed, volume and a sleep timer"
             (Options: button() -> omniFxQuickMenuShow; top level omniFxQuickBuild -> omniNpQuickRow "Now playing" while
             a tab plays; its panel rows omniSpNpRow "Speed", omniTvNpRows "Volume", omniStNpRow "Sleep timer").
             Without the speed / volume / sleep-timer shells: "... Now playing: pause, skip 10 s, mute".
  select     the pointer rested 1.5 s on plain page text (one read-only probe per rest: caretRangeFromPoint, not a
             link / control / editable) (15 s)
             "Hold {Cross} on text > Select text, then Copy, Search, QR code or Highlight"
             (hold Cross: omniFxButtonEvent page menu; omniTslContextRow "Select text"; omniTslActions Copy / Search /
             QR; "Highlight" only when OmniHighlightsShell.h exists).
  switcher   5 or more tabs open (30 s)
             "Hold {L2} and tap {R1} to switch tabs quickly; let go of {L2} to jump"
             (omniTswChord / OTSW::classify: L2 held + R1 opens next, release commits).
  image      the image viewer came up by itself (an image address); shown after it closes (60 s)
             "Hold {Cross} on any picture > View image: {R2} / {L2} zoom, {Square} saves"   (OMNI_IMAGE_VIEWER_V1:
             its page-menu row, R2 / L2 trigger zoom, Square: Save). Only with OmniImageViewerShell.h.
  reading    Options > Browse > Reading list was open; shown after it closes (60 s)
             with OmniReadingProgressShell.h: "Reading list pages remember how far you read ("40% read")"
             without: "Reading list: {Cross} opens the saved copy, {Triangle} the live page"   (omniRlInput)
  keyboard   the on-screen keyboard was open; shown after it closes (60 s)
             word chips on (omniKwChipsOn): "Keyboard: D-pad up from the top row picks a suggested word; hold {Cross}
             on a letter for accents"; chips off: "Keyboard: hold {Cross} on a letter for accents (e, n, u ...)"
             (omniKwButton; the accent popup of apply_kb_layouts.py: Cross held on a letter with variants)
  youtube    desktop / mobile YouTube shown (not /tv) while TV mode is off (60 s)
             "YouTube TV mode: {Create} > Browser settings > YouTube: TV mode"   (button() omniFxSettingsShow; row
             omniYtTvRowId "YouTube"). Skipped while TV mode is on.
  saver      a page still loading after 15 s, or the tab is offline (omniOrTabOffline) (120 s)
             "Slow connection? {Create} > Browser settings > Data saver uses less data"
             Only when OmniDataSaverShell.h exists and Data saver is off (else skipped, not marked seen).
  find       the find bar is open (not while typing into it) (30 s)
             "Find bar: {L1} / {R1} jump between matches, {Square} matches case, {Circle} closes"   (omniFindButton)
  magnifier  the shown site has a zoom of its own above 100 % (L2 + D-pad, site-zoom.txt) and the lens is available
             (omniMagAvailable) (60 s)    "{L2} + {L3} opens the magnifier (2x, 3x, off); it follows the pointer"
  translate  the page's <html lang> is not English (one read-only probe per shown address) (120 s)
             "Press {@} to translate this page (Google Translate)"; {@} = the button that runs "Translate page" NOW:
             with apply_button_map.py the first of its slots whose current action is translate (the add-on
             quick-switch slot excluded: it goes first); none -> the tip is skipped (not marked seen, no more probes).
             Without the button map: Touchpad (button() omniTranslateToggle), skipped when the add-on quick switch
             uses it. (The shell spells the button map's and the image viewer's names through token pasting: their
             apply scripts refuse a tree / tools folder where another file spells them.)
  qr         the same web page shown for 3 minutes (60 s)
             "Hold {Cross} on the page > Show QR code to open it on your phone"   (omniQrContextRow, page menu)
  Every other button named is not remappable (OmniButtonMap.h: Cross / Circle / L1 / R1 / D-pad / Options / Create,
  L2 + L1 / R1, L2 + L3, and every panel / keyboard / find bar / viewer key), so only "translate" needs the map.
  Tokens ({Cross}, {Options}, ...) become the PlayStation or Xbox names (playStationIcons), the Controls guide's names.

Language: with apply_ui_lang.py (OmniUiLangShell.h present: __has_include) the card's "Tip" and the tip TEMPLATE (with
its {tokens}) go through omniTr() before the tokens are expanded, so /data/omni/lang/<code>.txt can translate them
("Hold {L2} and tap {R1} ...<TAB>Manten {L2} ..."); the settings rows go through the panel's own omniTr. Without it:
English, same code (both compile).

Cost: omniTipTick runs from omniF3Tick but works at most every 250 ms, and only while a tip could show (enabled, past
the first minute, 10 min since the last one): then it reads flags the shell already has. Page scripts: at most one
tiny read-only probe per pointer rest (until "select" is seen) and one per shown address (until "translate" is seen or
has no button). While a card shows, the overlay layer makes frames whole draws (as every open layer does), for 8 s.

Pure part: engine/entry/OmniTips.h (no SDL / WebKit): tip table, facts, templates, token expansion, seen-set parse /
serialize, rate limit, arming / freshness, context gating, card layout, the two probe scripts and their answers.
Tested by tools/test_tips.cpp (also checks the facts against OmniControlsHelp.h and the translate default against
OmniButtonMap.h when present):
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tips.cpp -o t && ./t [probe.js]
Shell side: engine/entry/OmniTipsShell.h, included from OmniBrowser.cpp after OmniSiteListShell.h (so after
OmniButtonMapShell.h whichever of the two patches runs first).

Ids (grep of every apply_*.py and the tree, 2026-11-16): Browser settings rows 851 / 852, numbers of the 800s nobody
uses or names (850 is send link's, 855 site list's). Names: omniTip*, namespace OmniTips (alias OTIP), tips-seen.txt.
The script refuses a tree (or another apply_*.py) that already uses them.

Anchors (exactly once each; MARK makes each file idempotent; each file keeps its line endings):
  OmniBrowser.cpp        the OmniControlsHelp.h include (pure include after it);
                         the OmniSiteListShell.h include (shell include after it).
  OmniFeatures3.h        the OmniWebAppsShell.h include (omniTipTick declaration after it);
                         omniF3Tick's omniDlpTick line (omniTipTick(now) after it; the image viewer, clip history
                         and data saver insert after that line too, in any order).
  OmniBrowserSettings.h  omniChSettingsInput's declaration, the omniChSettingsRow call, its input line (ours after each).
Apply AFTER apply_controls_help.py, apply_site_list.py, apply_web_apps.py, apply_dl_progress.py and the features the
tips name (text select, find plus, tab switcher, media controls, magnifier, YouTube TV, reading list, offline retry,
keyboard words); best LAST (after apply_button_map.py / apply_image_viewer.py / apply_highlights.py). Optional, found
by __has_include: button map, image viewer, highlights, reading progress, data saver, UI language (apply_ui_lang.py
may run before or after: OmniTipsShell.h names OMNI_UI_LANG_V1, so its id scan passes over that file).
usage: apply_tips.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_TIPS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TIPS_V1: the pure part of the one-time contextual tips (no SDL, no WebKit). The shell side is OmniTipsShell.h;
// the reasons are in tools/apply_tips.py. Tested on the host with g++ (test_tips.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace OmniTips {

constexpr const char* kFileName = "tips-seen.txt";   // under /data/omni/
constexpr const char* kFileTag = "omni-tips\t1";
constexpr size_t kMaxFileBytes = 4096;
constexpr size_t kMaxOtherKeys = 64;                 // seen keys of tips this build doesn't know (kept)
constexpr int kShowRowId = 851;                      // Browser settings "Show tips" (850 send link, 855 site list)
constexpr int kResetRowId = 852;                     // ... "Reset tips"
constexpr uint32_t kShowMs = 8000;                   // a card stays up this long
constexpr uint32_t kGapMs = 600000;                  // at most one tip per 10 minutes
constexpr uint32_t kStartQuietMs = 60000;            // none in the first minute after start
constexpr uint32_t kTickMs = 250;                    // the shell looks at most this often
constexpr uint32_t kRestMs = 1500;                   // pointer still this long: one "is this text?" probe
constexpr uint32_t kSlowMs = 15000;                  // a load still running after this: a slow page
constexpr uint32_t kDwellMs = 180000;                // the same page this long: the QR tip
constexpr size_t kManyTabs = 5;                      // this many tabs: the switcher tip

enum Id : int { tVideo, tSelectText, tTabSwitcher, tImage, tReadingList, tKeyboard, tYoutubeTv, tDataSaver, tFindBar,
    tMagnifier, tTranslate, tQrShare, kCount };

// A row of the Controls guide (OmniControlsHelp.h) the tip's text relies on: its keys by their PlayStation names
// joined " + " (a pair as the guide names it, "L1 / R1"), "Hold" or not, and a piece of its action or note.
struct Fact { const char* keys; bool hold; const char* text; };
struct Info {
    const char* key;        // in tips-seen.txt
    const char* trigger;    // when it arms (documentation; the shell decides)
    uint32_t freshMs;       // shown at most this long after its context was last seen
    bool remap;             // {@}: the button that runs the action now (Controller shortcuts)
    Fact facts[3];          // checked by test_tips.cpp against the guide table ({nullptr}: none)
};
inline const Info& info(int id)
{
    static const Info k[kCount] = {
        { "video", "full-screen or immersive video (after it ends)", 60000, false,
          { { "Options", false, "Now playing" }, { "Options", false, "Sleep timer" }, { nullptr, false, nullptr } } },
        { "select-text", "the pointer rests on page text", 15000, false,
          { { "Cross", true, "Select text" }, { "Cross", false, "Select text: Copy, Search" }, { nullptr, false, nullptr } } },
        { "tab-switcher", "5 or more tabs", 30000, false,
          { { "L2 + L1 / R1", false, "Quick tab switcher" }, { nullptr, false, nullptr }, { nullptr, false, nullptr } } },
        { "image-viewer", "the image viewer opened by itself (after it closes)", 60000, false,
          { { "Cross", true, "View image" }, { "L2 / R2", false, "Zoom out / in" }, { "Square", false, "Save" } } },
        { "reading-list", "the Reading list was open (after it closes)", 60000, false,
          { { "Cross", false, "Open the saved copy" }, { "Triangle", false, "Open the live page" }, { nullptr, false, nullptr } } },
        { "keyboard", "the keyboard was open (after it closes)", 60000, false,
          { { "D-pad up", false, "Word suggestions" }, { "Cross", false, "Hold on a letter for accents" }, { nullptr, false, nullptr } } },
        { "youtube-tv", "YouTube (not the TV app) while TV mode is off", 60000, false,
          { { "Create", false, "Browser settings" }, { nullptr, false, nullptr }, { nullptr, false, nullptr } } },
        { "data-saver", "a slow page (15 s) or an offline tab, Data saver off", 120000, false,
          { { "Create", false, "Browser settings" }, { nullptr, false, nullptr }, { nullptr, false, nullptr } } },
        { "find-bar", "the find bar is open", 30000, false,
          { { "L1 / R1", false, "Find bar: previous / next match" }, { "Square", false, "Find bar: Match case" }, { "Circle", false, "Find bar: close" } } },
        { "magnifier", "a site zoomed above 100 % (lens available)", 60000, false,
          { { "L2 + L3", false, "Magnifier" }, { nullptr, false, nullptr }, { nullptr, false, nullptr } } },
        { "translate", "a page whose language is not English", 120000, true,
          { { "Touchpad", false, "Translate page" }, { nullptr, false, nullptr }, { nullptr, false, nullptr } } },
        { "qr-share", "the same web page for 3 minutes", 60000, false,
          { { "Cross", true, "Link or page menu" }, { nullptr, false, nullptr }, { nullptr, false, nullptr } } },
    };
    return k[id >= 0 && id < kCount ? id : 0];
}
inline int idFromKey(const std::string& key)
{
    for (int i = 0; i < kCount; ++i) if (key == info(i).key) return i;
    return -1;
}

// What the build / settings offer, for the texts that depend on it.
struct Variant {
    bool npExtras = true;          // Now playing has Speed, Volume and Sleep timer rows
    bool highlights = true;        // Select text has "Highlight" (OMNI_HIGHLIGHTS_V1)
    bool readingProgress = false;  // the Reading list shows "40% read" (OMNI_READING_PROGRESS_V1)
    bool wordChips = true;         // keyboard word suggestions are on
};
// The English template ({Cross} ... tokens; {@}: the remapped button). Translations replace the template as a whole.
inline const char* templ(int id, const Variant& v)
{
    switch (id) {
    case tVideo: return v.npExtras ? "While a video plays, {Options} > Now playing has speed, volume and a sleep timer"
                                   : "While a video plays, {Options} > Now playing: pause, skip 10 s, mute";
    case tSelectText: return v.highlights ? "Hold {Cross} on text > Select text, then Copy, Search, QR code or Highlight"
                                          : "Hold {Cross} on text > Select text, then Copy, Search or QR code";
    case tTabSwitcher: return "Hold {L2} and tap {R1} to switch tabs quickly; let go of {L2} to jump";
    case tImage: return "Hold {Cross} on any picture > View image: {R2} / {L2} zoom, {Square} saves";
    case tReadingList: return v.readingProgress ? "Reading list pages remember how far you read (\"40% read\")"
                                                : "Reading list: {Cross} opens the saved copy, {Triangle} the live page";
    case tKeyboard: return v.wordChips ? "Keyboard: D-pad up from the top row picks a suggested word; hold {Cross} on a letter for accents"
                                       : "Keyboard: hold {Cross} on a letter for accents (\xc3\xa9, \xc3\xb1, \xc3\xbc ...)";
    case tYoutubeTv: return "YouTube TV mode: {Create} > Browser settings > YouTube: TV mode";
    case tDataSaver: return "Slow connection? {Create} > Browser settings > Data saver uses less data";
    case tFindBar: return "Find bar: {L1} / {R1} jump between matches, {Square} matches case, {Circle} closes";
    case tMagnifier: return "{L2} + {L3} opens the magnifier (2x, 3x, off); it follows the pointer";
    case tTranslate: return "Press {@} to translate this page (Google Translate)";
    case tQrShare: return "Hold {Cross} on the page > Show QR code to open it on your phone";
    }
    return "";
}
inline const char* heading() { return "Tip"; }

// The PlayStation / Xbox names (the Controls guide's glyphName()).
inline const char* buttonName(const std::string& token, bool ps)
{
    static const struct { const char* token; const char* ps; const char* xbox; } k[] = {
        { "Cross", "Cross", "A" }, { "Circle", "Circle", "B" }, { "Square", "Square", "X" }, { "Triangle", "Triangle", "Y" },
        { "L1", "L1", "LB" }, { "R1", "R1", "RB" }, { "L2", "L2", "LT" }, { "R2", "R2", "RT" }, { "L3", "L3", "LS" },
        { "R3", "R3", "RS" }, { "Options", "Options", "Menu" }, { "Create", "Create", "View" } };
    for (const auto& e : k) if (token == e.token) return ps ? e.ps : e.xbox;
    return nullptr;
}
// {Cross} -> "Cross" / "A", {@} -> remapped (empty remapped: the whole text is empty, the tip is skipped).
// Unknown tokens stay as written.
inline std::string expand(const std::string& text, bool ps, const std::string& remapped = std::string())
{
    std::string out;
    out.reserve(text.size() + 16);
    for (size_t i = 0; i < text.size();) {
        if (text[i] == '{') {
            const size_t close = text.find('}', i + 1);
            if (close != std::string::npos && close - i <= 10) {
                const std::string token = text.substr(i + 1, close - i - 1);
                if (token == "@") {
                    if (remapped.empty()) return std::string();
                    out += remapped; i = close + 1; continue;
                }
                if (const char* n = buttonName(token, ps)) { out += n; i = close + 1; continue; }
            }
        }
        out += text[i++];
    }
    return out;
}

// --- the seen set ---------------------------------------------------------------------------------------------------
struct Store {
    bool enabled = true;
    unsigned seen = 0;                 // bit per Id
    std::vector<std::string> other;    // seen keys of tips this build doesn't have
    bool isSeen(int id) const { return id >= 0 && id < kCount && (seen >> id) & 1u; }
    void markSeen(int id) { if (id >= 0 && id < kCount) seen |= 1u << id; }
    int seenCount() const { int n = 0; for (int i = 0; i < kCount; ++i) n += isSeen(i) ? 1 : 0; return n; }
    void reset() { seen = 0; other.clear(); }
};
inline bool validKey(const std::string& k)
{
    if (k.empty() || k.size() > 32) return false;
    for (char c : k) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return false;
    return true;
}
inline std::string trim(const std::string& v)
{
    const size_t b = v.find_first_not_of(" \t\r"), e = v.find_last_not_of(" \t\r");
    return b == std::string::npos ? std::string() : v.substr(b, e - b + 1);
}
// "key<TAB>value" lines; the tag line, blank, '#', unknown or broken lines are skipped. Only the first kMaxFileBytes.
inline Store parse(const std::string& text0)
{
    Store s;
    const std::string text = text0.substr(0, text0.size() < kMaxFileBytes ? text0.size() : kMaxFileBytes);
    size_t i = 0;
    while (i < text.size()) {
        size_t j = text.find('\n', i);
        if (j == std::string::npos) j = text.size();
        const std::string line = text.substr(i, j - i);
        i = j + 1;
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        const std::string k = trim(line.substr(0, tab)), v = trim(line.substr(tab + 1));
        if (k == "enabled") { if (v == "0" || v == "1") s.enabled = v == "1"; }
        else if (k == "seen" && validKey(v)) {
            const int id = idFromKey(v);
            if (id >= 0) s.markSeen(id);
            else if (s.other.size() < kMaxOtherKeys) {
                bool dup = false;
                for (const auto& o : s.other) dup |= o == v;
                if (!dup) s.other.push_back(v);
            }
        }
    }
    return s;
}
inline std::string serialize(const Store& s)
{
    std::string out = std::string(kFileTag) + "\n";
    out += std::string("enabled\t") + (s.enabled ? "1" : "0") + "\n";
    for (int i = 0; i < kCount; ++i) if (s.isSeen(i)) out += std::string("seen\t") + info(i).key + "\n";
    for (const auto& o : s.other) out += "seen\t" + o + "\n";
    return out;
}

// --- when a tip may show ----------------------------------------------------------------------------------------------
struct Context {
    bool testMode = false;
    bool haveTab = false;      // a tab, not crashed
    bool fullscreen = false;   // full-screen or immersive video (page full screen)
    bool typing = false;       // the keyboard or a page's text box
    bool covered = false;      // a panel, menu, dialog, overlay, Browser settings, History, guide, Media downloads
    bool toast = false;        // a notice / page message is up
};
// A shown card stays only while this holds.
inline bool quiet(const Context& c) { return !c.testMode && c.haveTab && !c.fullscreen && !c.typing && !c.covered; }
// A new card starts only when also no notice is up.
inline bool mayStart(const Context& c) { return quiet(c) && !c.toast; }

struct Rate {
    bool started = false, shownOnce = false;
    uint32_t startedAt = 0, lastShownAt = 0;   // SDL_GetTicks() ms
};
inline void start(Rate& r, uint32_t now) { if (!r.started) { r.started = true; r.startedAt = now; } }
// Wrap-safe: the first minute is quiet, then one tip per kGapMs.
inline bool rateOk(const Rate& r, uint32_t now)
{
    if (!r.started || uint32_t(now - r.startedAt) < kStartQuietMs) return false;
    return !r.shownOnce || uint32_t(now - r.lastShownAt) >= kGapMs;
}
inline void shown(Rate& r, uint32_t now) { r.shownOnce = true; r.lastShownAt = now; }

// Contexts seen: when each tip was last armed. A context still on screen re-arms every look.
struct Arms {
    bool on[kCount] = {};
    uint32_t at[kCount] = {};
    void arm(int id, uint32_t now) { if (id >= 0 && id < kCount) { on[id] = true; at[id] = now; } }
    void clear(int id) { if (id >= 0 && id < kCount) on[id] = false; }
    void clearAll() { for (int i = 0; i < kCount; ++i) on[i] = false; }
    bool fresh(int id, uint32_t now) const { return on[id] && uint32_t(now - at[id]) <= info(id).freshMs; }
    void expire(uint32_t now) { for (int i = 0; i < kCount; ++i) if (on[i] && !fresh(i, now)) on[i] = false; }
    bool any() const { for (int i = 0; i < kCount; ++i) if (on[i]) return true; return false; }
    // The most recently armed tip that is fresh, not seen and available (bit per Id), or -1.
    int pick(uint32_t now, const Store& s, unsigned available) const
    {
        int best = -1;
        uint32_t bestAge = 0;
        for (int i = 0; i < kCount; ++i) {
            if (!fresh(i, now) || s.isSeen(i) || !((available >> i) & 1u)) continue;
            const uint32_t age = uint32_t(now - at[i]);
            if (best < 0 || age < bestAge) { best = i; bestAge = age; }
        }
        return best;
    }
};

// --- the card (layout px, 1280 x 720) --------------------------------------------------------------------------------
constexpr int kCardH = 48, kMarginX = 40, kPadX = 18, kGap = 12, kCloseW = 24, kMinW = 280, kAbove = 56;
struct Card { int x = 0, y = 0, w = 0, h = 0; };
// baseY: the bottom of the card (above the button bar, as the toast's base); toastUp: a notice sits there, go above it.
inline Card card(int headW, int textW, int screenW, int baseY, bool toastUp)
{
    Card c;
    int w = kPadX + headW + kGap + textW + kGap + kCloseW + kPadX;
    const int maxW = screenW - 2 * kMarginX;
    if (w > maxW) w = maxW;
    if (w < kMinW) w = kMinW;
    c.w = w; c.h = kCardH; c.x = kMarginX;
    c.y = baseY - kCardH - (toastUp ? kAbove : 0);
    if (c.y < 8) c.y = 8;
    return c;
}
// Room for the tip text after the heading (longer texts end in an ellipsis).
inline int textRoom(const Card& c, int headW) { const int r = c.w - 2 * kPadX - headW - 2 * kGap - kCloseW; return r > 40 ? r : 40; }
inline bool inside(const Card& c, int x, int y) { return x >= c.x && x < c.x + c.w && y >= c.y && y < c.y + c.h; }

// --- page probes (read-only, the main frame) -------------------------------------------------------------------------
// 'text' when (x, y) (CSS px of the viewport) is over plain text of some length (not a link, control, label or
// editable), else 'no'.
inline std::string textProbe(double x, double y)
{
    char tail[64];
    snprintf(tail, sizeof tail, "})(%.1f,%.1f)", x, y);
    return std::string("(function(X,Y){")
        + "try{var d=document;if(!d.caretRangeFromPoint)return'no';var r=d.caretRangeFromPoint(X,Y);if(!r)return'no';"
          "var n=r.startContainer;if(!n||n.nodeType!==3||n.data.replace(/\\s+/g,'').length<12)return'no';"
          "var e=n.parentElement;if(!e||e.closest('a,button,input,textarea,select,label,option,[contenteditable],[role=button],[role=link]'))return'no';"
          "var q=d.createRange();q.selectNodeContents(n);var s=q.getClientRects();"
          "for(var i=0;i<s.length;i++){var b=s[i];if(X>=b.left&&X<=b.right&&Y>=b.top&&Y<=b.bottom)return'text';}"
          "return'no';}catch(x){return'no';}"
        + tail;
}
inline bool isText(const std::string& answer) { return answer == "text"; }
// The document's language (<html lang>), at most 24 characters; '' when none.
inline const char* langProbe()
{
    return "(function(){try{return String(document.documentElement.lang||'').slice(0,24);}catch(x){return'';}})()";
}
// A language tag that is not English (and not "no language" / unknown).
inline bool foreignLang(const std::string& tag0)
{
    std::string t;
    for (char c : trim(tag0)) t += (c >= 'A' && c <= 'Z') ? char(c + ('a' - 'A')) : c;
    size_t n = 0;
    while (n < t.size() && t[n] >= 'a' && t[n] <= 'z') ++n;
    if (n < 2 || n > 3 || (n < t.size() && t[n] != '-' && t[n] != '_')) return false;
    const std::string primary = t.substr(0, n);
    return primary != "en" && primary != "und" && primary != "zxx" && primary != "mul" && primary != "mis";
}
// Desktop / mobile YouTube (www., m. or bare youtube.com, http(s)), not the TV app (/tv).
inline bool youtubeDesktop(const std::string& url)
{
    size_t p;
    if (url.compare(0, 8, "https://") == 0) p = 8;
    else if (url.compare(0, 7, "http://") == 0) p = 7;
    else return false;
    size_t end = url.find_first_of("/?#", p);
    if (end == std::string::npos) end = url.size();
    std::string host = url.substr(p, end - p);
    for (auto& c : host) if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    const size_t colon = host.find(':');
    if (colon != std::string::npos) host.resize(colon);
    if (host != "youtube.com" && host != "www.youtube.com" && host != "m.youtube.com") return false;
    const std::string path = end < url.size() && url[end] == '/' ? url.substr(end) : std::string("/");
    return !(path == "/tv" || path.compare(0, 4, "/tv/") == 0 || path.compare(0, 4, "/tv#") == 0 || path.compare(0, 4, "/tv?") == 0);
}

} // namespace OmniTips
'''

SHELL = r'''// OMNI_TIPS_V1: one-time contextual tips (shell side). Included from OmniBrowser.cpp after OmniSiteListShell.h (inside its
// anonymous namespace; after OmniButtonMapShell.h, whose current buttons the translate tip names). The pure part is
// OmniTips.h; the reasons are in tools/apply_tips.py. Main thread only. Hooks: omniF3Tick (omniTipTick), Browser
// settings (rows OTIP::kShowRowId / kResetRowId), an overlay layer that draws the card (it never blocks the page and
// takes no buttons; a pointer click on the card closes it).
#pragma once

namespace OTIP = OmniTips;

// Optional neighbours (each patch writes its header; the shell includes come before this file).
#if __has_include("OmniButtonMapShell.h")
#define OMNI_TIPS_BMAP 1
// The button map's names, pasted together: apply_button_map.py refuses a tree where another file spells them.
#define OMNI_TIPS_BM(x) omniBm##x
#else
#define OMNI_TIPS_BMAP 0
#endif
#if __has_include("OmniImageViewerShell.h")
#define OMNI_TIPS_IMV 1
// pasted for the same reason (apply_image_viewer.py's scan)
#define OMNI_TIPS_IMV_SHOWN() omniIm##vShown()
#else
#define OMNI_TIPS_IMV 0
#endif
// UI language (OMNI_UI_LANG_V1, apply_ui_lang.py): the template and the heading go through omniTr when it exists.
#if __has_include("OmniUiLangShell.h")
#define OMNI_TIP_TR(s) std::string(omniTr(s))
#else
#define OMNI_TIP_TR(s) std::string(s)
#endif
#if __has_include("OmniDataSaverShell.h")
#define OMNI_TIPS_SAVER 1
#else
#define OMNI_TIPS_SAVER 0
#endif
#if __has_include("OmniPlaybackSpeedShell.h") && __has_include("OmniTabVolumeShell.h") && __has_include("OmniSleepTimerShell.h")
#define OMNI_TIPS_NP_EXTRAS true
#else
#define OMNI_TIPS_NP_EXTRAS false
#endif
#if __has_include("OmniHighlightsShell.h")
#define OMNI_TIPS_HIGHLIGHTS true
#else
#define OMNI_TIPS_HIGHLIGHTS false
#endif
#if __has_include("OmniReadingProgressShell.h")
#define OMNI_TIPS_READING_PROGRESS true
#else
#define OMNI_TIPS_READING_PROGRESS false
#endif

static OTIP::Store omniTip;
static bool omniTipLoaded = false;
static OTIP::Arms omniTipArms;
static OTIP::Rate omniTipRate;
struct OmniTipCard { bool on = false; int id = -1; uint32_t since = 0; std::string head, text; };
static OmniTipCard omniTipNow;
static uint32_t omniTipLastTick = 0;
static float omniTipPx = -1, omniTipPy = -1;       // the pointer's resting place, since when, probed there
static uint32_t omniTipRestSince = 0;
static bool omniTipProbed = false;
static const void* omniTipLoadTab = nullptr;      // the active tab's load: which tab, since when
static bool omniTipWasLoading = false;
static uint32_t omniTipLoadSince = 0;
static const void* omniTipDwellTab = nullptr;     // the same page shown since
static std::string omniTipDwellUrl;
static uint32_t omniTipDwellSince = 0;
static std::string omniTipLangUrl;                // the last address asked for its language

static void omniTipLoad()
{
    if (omniTipLoaded) return;
    omniTipLoaded = true;
    if (omniTestMode()) return;   // self-tests: nothing read, written or shown
    FILE* f = fopen(omniData(OTIP::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[1024];
    size_t n = 0;
    while (text.size() < OTIP::kMaxFileBytes && (n = fread(buf, 1, sizeof(buf), f)) > 0) text.append(buf, n);
    fclose(f);
    omniTip = OTIP::parse(text);
    fprintf(stderr, "OMNI TIPS: %s, %d seen\n", omniTip.enabled ? "on" : "off", omniTip.seenCount()); fflush(stderr);
}
static void omniTipSave()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OTIP::kFileName), OTIP::serialize(omniTip), false);
}

// The button that runs "Translate page" now ("" none: the tip is skipped).
static std::string omniTipTranslateButton()
{
#if OMNI_TIPS_BMAP
    namespace BM = OmniButtonMap;
    OMNI_TIPS_BM(apLoad)();
    const int addon = OMNI_TIPS_BM(apAddonSlot)();   // the add-on quick switch goes first on that button
    for (int s = 0; s < BM::kSlotCount; ++s)
        if (s != addon && OMNI_TIPS_BM(ap).a[s] == BM::aTranslate) return BM::slotName(s, playStationIcons);
    return std::string();
#else
    if (omniAdReady && omniAdQuick() && omniAdState.shortcut == "touchpad") return std::string();
    return "Touchpad";   // button() omniTranslateToggle
#endif
}
static bool omniTipUsable(int id)
{
    switch (id) {
    case OTIP::tYoutubeTv: return !omniYtTvOn();
    case OTIP::tDataSaver:
#if OMNI_TIPS_SAVER
        omniDsvLoad();
        return !omniDsv.on;
#else
        return false;
#endif
    case OTIP::tMagnifier: return omniMagAvailable();
    case OTIP::tTranslate: return !omniTipTranslateButton().empty();
    default: return true;
    }
}
static unsigned omniTipAvailable()
{
    unsigned m = 0;
    for (int i = 0; i < OTIP::kCount; ++i) if (omniTipArms.on[i] && omniTipUsable(i)) m |= 1u << i;
    return m;
}
static std::string omniTipText(int id)
{
    OTIP::Variant v;
    v.npExtras = OMNI_TIPS_NP_EXTRAS;
    v.highlights = OMNI_TIPS_HIGHLIGHTS;
    v.readingProgress = OMNI_TIPS_READING_PROGRESS;
    v.wordChips = omniKwChipsOn();
    const std::string templ = OMNI_TIP_TR(std::string(OTIP::templ(id, v)));   // translated with its {tokens}
    return OTIP::expand(templ, playStationIcons, id == OTIP::tTranslate ? omniTipTranslateButton() : std::string());
}

static OTIP::Context omniTipContext()
{
    OTIP::Context c;
    Tab* t = active();
    c.testMode = omniTestMode();
    c.haveTab = t && !t->crashed;
    c.fullscreen = pageFullscreen || omniVideoImmersive;
    c.typing = editing || pageEditing;
    c.covered = settingsOpen || omniOverlayOpen() || !omniFxStack.empty() || omniHistoryOpenFlag || omniMenuOpenFlag
        || omniChOpenNow() || (omniMediaDownloadsEnabled && omniSavedOwnedView() != OmniSavedView::None);
    c.toast = status != "Ready" || (t && !t->message.empty());
    return c;
}
static bool omniTipToastUp() { return status != "Ready" || (active() && !active()->message.empty()); }

static void omniTipShow(int id, uint32_t now)
{
    const std::string text = omniTipText(id);
    omniTipArms.clear(id);
    if (text.empty()) return;   // no button for it now
    omniTip.markSeen(id);
    omniTipSave();
    OTIP::shown(omniTipRate, now);
    omniTipNow.on = true; omniTipNow.id = id; omniTipNow.since = now;
    omniTipNow.head = OMNI_TIP_TR(std::string(OTIP::heading()));
    omniTipNow.text = text;
    omniShellDirty = true;
    fprintf(stderr, "OMNI TIPS: shown %s\n", OTIP::info(id).key); fflush(stderr);
}
static void omniTipHide()
{
    if (!omniTipNow.on) return;
    omniTipNow = OmniTipCard();
    omniShellDirty = true;
}

// --- page probes -------------------------------------------------------------------------------------------------------
struct OmniTipQuery { const void* tab; std::string url; float px, py; };
static void omniTipTextProbe(Tab* t)
{
    const double k = omniFxCssPerLayout(t);
    auto src = adoptWK(WKStringCreateWithUTF8CString(OTIP::textProbe(pointerX * k, (pointerY - omniPageTop()) * k).c_str()));
    auto* q = new OmniTipQuery { t, t->url, pointerX, pointerY };
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), q, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniTipQuery> q(static_cast<OmniTipQuery*>(context));
        Tab* now = active();
        if (now != q->tab || now->url != q->url || pointerX != q->px || pointerY != q->py) return;   // moved on
        if (OTIP::isText(omniFxResultString(result, error))) omniTipArms.arm(OTIP::tSelectText, SDL_GetTicks());
    });
}
static void omniTipLangProbe(Tab* t)
{
    omniTipLangUrl = t->url;
    auto src = adoptWK(WKStringCreateWithUTF8CString(OTIP::langProbe()));
    auto* q = new OmniTipQuery { t, t->url, 0, 0 };
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), q, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniTipQuery> q(static_cast<OmniTipQuery*>(context));
        Tab* now = active();
        if (now != q->tab || now->url != q->url) return;
        if (OTIP::foreignLang(omniFxResultString(result, error))) omniTipArms.arm(OTIP::tTranslate, SDL_GetTicks());
    });
}

// --- contexts ------------------------------------------------------------------------------------------------------------
static void omniTipObserve(uint32_t now)
{
    auto want = [](int id) { return !omniTip.isSeen(id); };
    if (want(OTIP::tVideo) && (pageFullscreen || omniVideoImmersive)) omniTipArms.arm(OTIP::tVideo, now);
    if (want(OTIP::tTabSwitcher) && tabs.size() >= OTIP::kManyTabs) omniTipArms.arm(OTIP::tTabSwitcher, now);
#if OMNI_TIPS_IMV
    if (want(OTIP::tImage) && OMNI_TIPS_IMV_SHOWN()) omniTipArms.arm(OTIP::tImage, now);
#endif
    if (want(OTIP::tKeyboard) && editing) omniTipArms.arm(OTIP::tKeyboard, now);
    if (want(OTIP::tReadingList))
        for (const auto& p : omniFxStack) if (p.build == omniRlBuild) { omniTipArms.arm(OTIP::tReadingList, now); break; }
    Tab* t = active();
    if (!t || t->crashed || !t->page) return;
    // the active tab's load: slow after kSlowMs
    bool slow = false;
    if (t->loading) {
        if (omniTipLoadTab != t || !omniTipWasLoading) { omniTipLoadTab = t; omniTipLoadSince = now; }
        omniTipWasLoading = true;
        slow = uint32_t(now - omniTipLoadSince) >= OTIP::kSlowMs;
    } else { omniTipLoadTab = t; omniTipWasLoading = false; }
    const bool web = omniWebURL(t->url);
    if (want(OTIP::tDataSaver) && web && (slow || omniOrTabOffline(*t))) omniTipArms.arm(OTIP::tDataSaver, now);
    if (want(OTIP::tYoutubeTv) && OTIP::youtubeDesktop(t->url)) omniTipArms.arm(OTIP::tYoutubeTv, now);
    if (want(OTIP::tFindBar) && omniFindBarOpen()) omniTipArms.arm(OTIP::tFindBar, now);
    if (want(OTIP::tMagnifier) && web && omniMagAvailable() && omniSiteZoom.get(omniBlockerHostOf(t->url)) > 100) omniTipArms.arm(OTIP::tMagnifier, now);
    // the same web page for kDwellMs (QR code)
    if (want(OTIP::tQrShare) && web && !t->loading) {
        if (omniTipDwellTab != t || omniTipDwellUrl != t->url) { omniTipDwellTab = t; omniTipDwellUrl = t->url; omniTipDwellSince = now; }
        else if (uint32_t(now - omniTipDwellSince) >= OTIP::kDwellMs) omniTipArms.arm(OTIP::tQrShare, now);
    }
    // one language probe per shown address (only while the tip has a button)
    if (want(OTIP::tTranslate) && web && !t->loading && t->url != omniTipLangUrl && !omniIsTranslated(t->url) && !t->omniReader
        && !pageFullscreen && !omniTipTranslateButton().empty())
        omniTipLangProbe(t);
    // one text probe per pointer rest on a web page
    if (want(OTIP::tSelectText) && web && !t->loading && omniFxPointerOnPage()) {
        if (pointerX != omniTipPx || pointerY != omniTipPy) { omniTipPx = pointerX; omniTipPy = pointerY; omniTipRestSince = now; omniTipProbed = false; }
        else if (!omniTipProbed && uint32_t(now - omniTipRestSince) >= OTIP::kRestMs) { omniTipProbed = true; omniTipTextProbe(t); }
    }
}

static void omniTipTick(uint32_t now)
{
    if (uint32_t(now - omniTipLastTick) < OTIP::kTickMs) return;
    omniTipLastTick = now;
    if (omniTestMode()) return;
    omniTipLoad();
    OTIP::start(omniTipRate, now);
    if (omniTipNow.on) {   // one at a time; it goes after 8 s, or at once when the screen gets busy
        if (!omniTip.enabled || !OTIP::quiet(omniTipContext()) || uint32_t(now - omniTipNow.since) >= OTIP::kShowMs) omniTipHide();
        return;
    }
    if (!omniTip.enabled || !OTIP::rateOk(omniTipRate, now)) return;   // nothing could show: no looks, no probes
    omniTipObserve(now);
    omniTipArms.expire(now);
    if (!omniTipArms.any() || !OTIP::mayStart(omniTipContext())) return;
    const int id = omniTipArms.pick(now, omniTip, omniTipAvailable());
    if (id >= 0) omniTipShow(id, now);
}

// --- the card (an overlay layer that never blocks the page) ------------------------------------------------------------
static bool omniTipOpen() { return omniTipNow.on && !pageFullscreen && !editing && !pageEditing && !settingsOpen; }
static OTIP::Card omniTipCardNow(int& headW)
{
    headW = int(omniTextWidthPx(omniSmallBold, omniTipNow.head) / displayScale + 0.5);
    const int textW = int(omniTextWidthPx(omniSmall, omniTipNow.text) / displayScale + 0.5);
    const int base = std::min(omniPageBottom(), height - bottom) - 18;   // where the toast sits
    return OTIP::card(headW, textW, width, base, omniTipToastUp());
}
static void omniTipDraw()
{
    const OmniTheme& T = omniTheme();
    int headW = 0;
    const OTIP::Card k = omniTipCardNow(headW);
    omniShadow(k.x, k.y, k.w, k.h, omniRadius, 12, 110, 3);
    fillRounded(k.x, k.y, k.w, k.h, omniRadius, omniMix(T.raised, T.line, 0.35f));
    fillRounded(k.x, k.y + 10, 4, k.h - 20, 2, T.accent);
    const float cy = k.y + k.h / 2.f;
    const int hx = k.x + OTIP::kPadX;
    omniLabel(omniTipNow.head, float(hx), cy, omniSmallBold, T.accent);
    omniLabel(omniTipNow.text, float(hx + headW + OTIP::kGap), cy, omniSmall, T.ink, 0, OTIP::textRoom(k, headW));
    omniLabel("\xc3\x97", k.x + k.w - OTIP::kPadX - OTIP::kCloseW / 2.f, cy, omniSmall, T.inkDim, 1);   // x: a click closes it
}
static bool omniTipClick(int x, int y)
{
    int headW = 0;
    if (!OTIP::inside(omniTipCardNow(headW), x, y)) return false;
    omniTipHide();
    return true;
}

// --- Browser settings ------------------------------------------------------------------------------------------------------
static void omniTipSettingsRows(OmniFxPanel& p)
{
    omniTipLoad();
    OmniFxRow a;
    a.id = OTIP::kShowRowId; a.label = "Show tips"; a.value = omniTip.enabled ? "On" : "Off"; a.stepper = true;
    p.rows.push_back(a);
    OmniFxRow r;
    const int n = omniTip.seenCount();
    r.id = OTIP::kResetRowId; r.label = "Reset tips"; r.value = n ? std::to_string(n) + " seen" : std::string();
    p.rows.push_back(r);
}
static bool omniTipSettingsInput(int id, int b)
{
    omniTipLoad();
    if (id == OTIP::kShowRowId) {
        const bool a = b == SDL_CONTROLLER_BUTTON_A, side = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
        if (!a && !side) return false;
        omniTip.enabled = !omniTip.enabled;
        if (!omniTip.enabled) { omniTipHide(); omniTipArms.clearAll(); }
        omniTipSave();
        omniFxRefresh();
        return true;
    }
    if (id == OTIP::kResetRowId) {
        if (b != SDL_CONTROLLER_BUTTON_A) return false;
        omniTip.reset();
        omniTipArms.clearAll();
        omniTipLangUrl.clear();
        omniTipProbed = false;
        omniTipSave();
        notice("Tips will show again");
        omniFxRefresh();
        return true;
    }
    return false;
}

[[maybe_unused]] static const bool omniTipLayer = [] {
    omniOverlayLayers().push_back({ omniTipOpen, nullptr, omniTipClick, nullptr, omniTipDraw, false });   // never blocks the page
    return true;
}();
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniControlsHelp.h" // OMNI_CONTROLS_HELP_V1: the Controls guide: shortcut table, order, layout (pure)\n',
         '#include "OmniControlsHelp.h" // OMNI_CONTROLS_HELP_V1: the Controls guide: shortcut table, order, layout (pure)\n'
         '#include "OmniTips.h" // OMNI_TIPS_V1: one-time contextual tips (pure)\n'),
        ('#include "OmniSiteListShell.h" // OMNI_SITE_LIST_V1: Sites with custom settings (after every store it reads)\n',
         '#include "OmniSiteListShell.h" // OMNI_SITE_LIST_V1: Sites with custom settings (after every store it reads)\n'
         '#include "OmniTipsShell.h" // OMNI_TIPS_V1: one-time tips (after the controller shortcuts: the tips name the current buttons)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n',
         '#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n'
         'static void omniTipTick(uint32_t now); // OMNI_TIPS_V1 (OmniTipsShell.h, included from OmniBrowser.cpp after the controller shortcuts)\n'),
        ('    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n',
         '    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n'
         '    omniTipTick(now);   /* OMNI_TIPS_V1: contexts for the one-time tips (every 250 ms at most), the card\'s 8 s */\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniChSettingsInput(int b);\n',
         'static bool omniChSettingsInput(int b);\n'
         'static void omniTipSettingsRows(OmniFxPanel& p); // OMNI_TIPS_V1 (OmniTipsShell.h): "Show tips", "Reset tips"\n'
         'static bool omniTipSettingsInput(int id, int b);\n'),
        ('    omniChSettingsRow(p); // OMNI_CONTROLS_HELP_V1: Show controls guide\n',
         '    omniChSettingsRow(p); // OMNI_CONTROLS_HELP_V1: Show controls guide\n'
         '    omniTipSettingsRows(p); // OMNI_TIPS_V1: Show tips (On / Off), Reset tips\n'),
        ('    if (r.id == OmniControlsHelp::kSettingsRowId) return omniChSettingsInput(b); // OMNI_CONTROLS_HELP_V1\n',
         '    if (r.id == OmniControlsHelp::kSettingsRowId) return omniChSettingsInput(b); // OMNI_CONTROLS_HELP_V1\n'
         '    if (r.id == OmniTips::kShowRowId || r.id == OmniTips::kResetRowId) return omniTipSettingsInput(r.id, b); // OMNI_TIPS_V1\n'),
    ],
}

# Ids / names this patch takes: refused when something else already has them.
TAKEN = [r'\b851\b', r'\b852\b', r'\bOTIP\b', r'\bomniTip[A-Z]', r'tips-seen\.txt', r'\bOmniTips\b']
OWN = ('OmniTips.h', 'OmniTipsShell.h')

# What the shell calls: refused when a feature it names is missing.
NEEDS = [
    ('OmniBrowser.cpp', 'OMNI_CONTROLS_HELP_V1', 'apply_controls_help.py'),
    ('OmniBrowser.cpp', 'OMNI_SITE_LIST_V1', 'apply_site_list.py'),
    ('OmniBrowser.cpp', 'OMNI_KB_WORDS_V1', 'apply_kb_words.py'),
    ('OmniBrowser.cpp', 'OMNI_YOUTUBE_TV_V1', 'apply_youtube_tv.py'),
    ('OmniBrowser.cpp', 'OMNI_SITE_ZOOM_V1', 'apply_site_zoom.py'),
    ('OmniBrowser.cpp', 'OMNI_FIND_PLUS_V1', 'apply_find_plus.py'),
    ('OmniBrowser.cpp', 'OMNI_VIDEO_IMMERSIVE_V1', 'apply_video_immersive.py'),
    ('OmniFeatures3.h', 'OMNI_WEB_APPS_V1', 'apply_web_apps.py'),
    ('OmniFeatures3.h', 'OMNI_DL_PROGRESS_V1', 'apply_dl_progress.py'),
    ('OmniFeatures3.h', 'OMNI_READING_LIST_V1', 'apply_reading_list.py'),
    ('OmniFeatures3.h', 'OMNI_MAGNIFIER_V1', 'apply_magnifier.py'),
    ('OmniFeatures3.h', 'OMNI_OFFLINE_RETRY_V1', 'apply_offline_retry.py'),
    ('OmniFeatures3.h', 'OMNI_MEDIA_CONTROLS_V1', 'apply_media_controls.py'),
    ('OmniFeatures3.h', 'OMNI_TEXT_SELECT_V1', 'apply_text_select.py'),
    ('OmniFeatures3.h', 'OMNI_QR_SHARE_V1', 'apply_qr_share.py'),
    ('OmniFeatures3.h', 'OMNI_TAB_SWITCHER_V1', 'apply_tab_switcher.py'),
]


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
    """Before the first apply: no entry file and no other apply_*.py may use our ids / names."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS):
        return
    me = Path(__file__).resolve()
    places = [p for p in root.iterdir() if p.suffix in ('.h', '.cpp', '.inc') and p.name not in OWN]
    places += [p for p in me.parent.glob('apply_*.py') if p.resolve() != me and p.name != 'apply_controls_help.py'
        and MARK not in p.read_text(encoding='utf-8', errors='replace')]   # OMNI_SIBLING_SKIP: guide / dependent patches
    for p in places:
        s = p.read_bytes().decode('utf-8', 'replace')
        if p.suffix == '.py':   # sibling script: names in its code only; row ids count in the engine tree only
            s = code_only(s)
        else:
            s = cpp_code(s)
        for pat in (TAKEN[2:] if p.suffix == '.py' else TAKEN[:2] if p.name in GUIDE else TAKEN):
            m = re.search(pat, s)
            if m:
                sys.exit('%s already uses %r (line %d): pick other ids' % (p.name, m.group(0), s.count('\n', 0, m.start()) + 1))


def main():
    texts = {}
    for name, need, tool in NEEDS:
        if name not in texts:
            texts[name] = (root / name).read_bytes().decode('utf-8')
        if need not in texts[name]:
            sys.exit('%s missing in %s: %s first' % (need, name, tool))
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTips.h', PURE, 'OmniControlsHelp.h'),
            write_new('OmniTipsShell.h', SHELL, 'OmniControlsHelpShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
