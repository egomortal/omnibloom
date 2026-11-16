#!/usr/bin/env python3
"""OMNI_DATA_SAVER_V1 (2026-11-16): "Data saver" for slow or metered connections (hotel Wi-Fi, phone hotspot).

What the user sees
  - Browser settings, after "Reload pages when back online": a row "Data saver"  Off / On  (Cross, left / right).
    While it is on, four more rows (each On / Off, Cross / left / right), saved with it:
        "Data saver: video up to 480p"     default On
        "Data saver: block autoplay"       default On
        "Data saver: block web fonts"      default Off (icon fonts then show as words or boxes: opt in)
        "Data saver: no link prefetch"     default On
    Turning the main row on or off reloads the current web page (the same as "Autoplay on this site" does); the parts
    say "reload pages to apply" (they act on the next load).
  - The top bar shows a small accent dot + "Saver" while it is on, right of the battery, the sleep timer's "zZ",
    offline retry's "Offline" and the Downloads ring (whichever are shown); only the dot when the bar is short of room.
  - Nothing the user chose elsewhere is changed: autoplay.txt and every other file stay as they are, so turning data
    saver off brings the user's own choices back by itself.
  - Stored in /data/omni/data-saver.txt (omniIoQueue; "omni-data-saver\t1" then key<TAB>0/1 lines). Self-test modes:
    nothing is read, written or applied.

What each part really does in this port (no page scripts anywhere)
  1. Video up to 480p. NOT /data/omni/video-quality.txt: that file is the MSE player's frame *scaling filter*
     (default / low / none / direct, read once per process in OmniMSEPlayer.cpp) and has no resolution in it; Omni has no
     resolution setting to reuse. So the cap is new, inside the Omni MSE engine (web process, OmniMSEPlayer.cpp).
     WHICH BINARY: web processes run from the engine CHILD (/data/omni/native/omni-engine-child.elf, OmniMain.cpp kSelf),
     which the title recipe (build-omni-gpupages-rc6-title.sh) does NOT rebuild; it ninjas OmniEngine in tree A only
     to link the title (UI process). So the cap is a SEPARATE script, apply_data_saver_mse.py, for the next child
     build; this script (title side: settings, badge, autoplay, fonts, prefetch) works alone. A child with the cap
     creates /data/omni/data-saver-cap.flag when a web process starts (OmniDataSaver::kCapFlag); until the shell sees
     that file the video part says "Needs engine update" and the main row's subtitle says so. What the cap does:
       - MediaSource.isTypeSupported / canPlayType with width= / height= parameters (the Cobalt / YouTube TV probes,
         e.g. 'video/webm; codecs="vp9"; width=1920; height=1080') answer "not supported" above 480p (short side > 480;
         only width given: > 854; only height: > 480). A type without size parameters is answered as before.
       - navigator.mediaCapabilities.decodingInfo (OMNI_MEDIACAPS_V1's factory) answers supported:false for a video
         configuration above that size.
     The web process reads data-saver.txt itself, at most every 2 s (a mutex-guarded cache), so a change applies from
     the next probe; a page that already chose its ladder keeps it until reloaded. Sites that do not probe sizes
     (desktop YouTube picks by player size x devicePixelRatio) are NOT capped; appends above 480p are still played
     (refusing them would break playback). Omni's native HLS player (<video src=.m3u8>) and progressive files are not
     capped: the HLS variant filter has no way to fall back when every variant is above 480p.
  2. Block autoplay. OMNI_AUTOPLAY_V1's global policy is taken as "Block all" while data saver (and this part) is on:
     omniApUse decides with a copy of the store whose global is kBlock. Per-site rules (and private-tab session rules)
     still win exactly as before, and OMNI_AUTOPLAY_V1's built-in exception stays (YouTube / Twitch / Vimeo /
     Dailymotion / localhost keep autoplay when the global is not Allow, because their players start the clicked video
     through autoplay). The Browser settings "Autoplay" row shows "Block all (Data saver)" meanwhile.
  3. Web fonts: feasible and cheap. OmniBlocker.cpp already compiles WebKit content rule lists
     (WKUserContentExtensionStore); a second, two-rule list ("omni-data-saver-fonts-v1": block resource-type font,
     then ignore-previous-rules for omni: built-in pages) is compiled once per launch on first use (same store
     directory) and added to both controllers (normal + private) through ucAddFilter. ucRemoveAllFilters (blocker on /
     off, the native uBlock switch-over) re-adds it while it is wanted. Applies to loads after the change.
     "Large images over N KB": NOT feasible here. Content rules have no size trigger (url-filter, resource-type,
     if/unless-domain, load-type only), the native uBlock engine matches URLs, and blocking all images breaks pages.
     "Media prefetch": content rules have no prefetch trigger (a prefetch load is resource-type "other", shared with
     beacons and more), so not done there; see 4.
  4. Link prefetch / preconnect: in this WebKit, LinkPrefetchEnabled is already false by default, LinkPreconnect is
     off (ENABLE(SERVER_PRECONNECT) is set only for Cocoa / GLib) and WKPreferencesSetDNSPrefetchingEnabled is an
     empty stub. What is still on is SpeculationRulesPrefetchEnabled (default true: <script type=speculationrules> and
     the Speculation-Rules header, used by Google Search result pages). This part turns that off with
     WKPreferencesSetExperimentalFeatureForKey(preferences, false, "SpeculationRulesPrefetchEnabled") on the one
     shared WKPreferences (normal and private tabs); off again -> true (WebKit's default; Omni never set it before).
     Rel=preload (needed resources) is left alone.

Ids (unused before this, checked over every tools/apply_*.py and the tree): Browser settings rows 825 (Data saver),
826-829 (its parts). The script refuses to patch if any of them is already used.

Pure part: engine/entry/OmniDataSaver.h (no SDL / WebKit): settings file, effective parts, the size cap, the autoplay
store override, texts, top-bar layout, the font rule list, the 2 s recheck. Tested by tools/test_data_saver.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_data_saver.cpp -o t && ./t
Shell side: engine/entry/OmniDataSaverShell.h (included from OmniFeatures3.h after OmniDlProgressShell.h).

Anchors (whole lines, exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp        the OmniSiteClear.h include (pure include after it); omniDlpHandedOver's declaration
                         (declarations after it); the omniDlpDrawTopBar call in omniDrawTopBar (badge after it).
  OmniBrowserSettings.h  omniOrRowId's line (declarations after it); the add(omniOrRowId, ...) row (rows after it);
                         the omniPfRowId input line (input before it, before the >= 300 / >= 900 rows).
  OmniFeatures3.h        the OmniDlProgressShell.h include line; the omniDlpTick(now) line of omniF3Tick.
  OmniAutoplayShell.h    omniApUse's OAP::decide line (replaced: decides with the data-saver store); the Autoplay row's
                         r.detail line (override after it).
  (OmniMSEPlayer.cpp: apply_data_saver_mse.py, child build only.)
  OmniBlocker.h          omniBlockerFailed's declaration.
  OmniBlocker.cpp        "void ucRemoveAllFilters()" (forward declaration before it); its private-controller line
                         (re-add after it); "void (*completion)(bool) = nullptr;" (state after it); the
                         omniBlockerFailed definition (omniBlockerSetDataSaverFonts after it).
Apply AFTER apply_autoplay.py, apply_offline_retry.py, apply_pad_feedback.py, apply_site_clear.py and
apply_dl_progress.py (their lines are anchors).
usage: apply_data_saver.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_DATA_SAVER_V1'
IDS = (825, 826, 827, 828, 829)
root = Path(sys.argv[1] if len(sys.argv) > 1 else '.') / 'engine' / 'entry'
tools = Path(__file__).resolve().parent

PURE = r'''// OMNI_DATA_SAVER_V1: "Data saver", the pure part (no SDL, no WebKit). Settings file, effective parts, the video
// size cap, the autoplay store override, texts, top-bar layout and the font rule list. Shell side: OmniDataSaverShell.h;
// the engine child's web process (OmniMSEPlayer.cpp, apply_data_saver_mse.py) reads the same file for the cap. The reasons are in tools/apply_data_saver.py.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

namespace OmniDataSaver {

constexpr const char* kFileName = "data-saver.txt";
constexpr const char* kPath = "/data/omni/data-saver.txt";   // the web process reads this (no omniData there)
constexpr const char* kHeader = "omni-data-saver\t1";
constexpr long kMaxFileBytes = 4096;
constexpr int kRowMain = 825, kRowVideo = 826, kRowAutoplay = 827, kRowFonts = 828, kRowPrefetch = 829;
constexpr unsigned kMaxShort = 480, kMaxWide = 854;          // "480p": short side 480 (854 x 480 landscape)
constexpr uint64_t kRecheckMs = 2000;                         // web process: re-read the file at most this often
// Created by a web process of an engine child that has the cap (apply_data_saver_mse.py); the shell only reads it.
constexpr const char* kCapFlag = "/data/omni/data-saver-cap.flag";
constexpr const char* kSpeculationKey = "SpeculationRulesPrefetchEnabled";
constexpr const char* kFontRulesId = "omni-data-saver-fonts-v1";
// Block every font load; built-in omni: pages keep theirs.
constexpr const char* kFontRules =
    "[{\"trigger\":{\"url-filter\":\".*\",\"resource-type\":[\"font\"]},\"action\":{\"type\":\"block\"}},"
    "{\"trigger\":{\"url-filter\":\"^omni:\"},\"action\":{\"type\":\"ignore-previous-rules\"}}]";
constexpr const char* kBadge = "Saver";

struct Settings {
    bool on = false;
    bool video = true, autoplay = true, fonts = false, prefetch = true;   // the parts (used only while on)
    bool operator==(const Settings& o) const
    {
        return on == o.on && video == o.video && autoplay == o.autoplay && fonts == o.fonts && prefetch == o.prefetch;
    }
};

// --- effective parts --------------------------------------------------------------------------------------------------
inline bool videoCap(const Settings& s) { return s.on && s.video; }
inline bool autoplayBlocked(const Settings& s) { return s.on && s.autoplay; }
inline bool fontsBlocked(const Settings& s) { return s.on && s.fonts; }
inline bool prefetchOff(const Settings& s) { return s.on && s.prefetch; }

// --- file --------------------------------------------------------------------------------------------------------------
inline std::string serialize(const Settings& s)
{
    auto b = [](bool v) { return v ? "1" : "0"; };
    return std::string(kHeader) + "\non\t" + b(s.on) + "\nvideo\t" + b(s.video) + "\nautoplay\t" + b(s.autoplay)
        + "\nfonts\t" + b(s.fonts) + "\nprefetch\t" + b(s.prefetch) + "\n";
}
// Unknown keys and bad values are skipped (defaults stay); no header (or another version): all defaults (off).
inline Settings parse(const std::string& text)
{
    Settings s;
    size_t at = 0;
    bool first = true;
    while (at < text.size()) {
        size_t end = text.find('\n', at);
        if (end == std::string::npos) end = text.size();
        std::string line = text.substr(at, end - at);
        at = end + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (first) {
            if (line != kHeader) return Settings();
            first = false;
            continue;
        }
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        const std::string key = line.substr(0, tab), value = line.substr(tab + 1);
        if (value != "0" && value != "1") continue;
        const bool v = value == "1";
        if (key == "on") s.on = v;
        else if (key == "video") s.video = v;
        else if (key == "autoplay") s.autoplay = v;
        else if (key == "fonts") s.fonts = v;
        else if (key == "prefetch") s.prefetch = v;
    }
    return s;
}

// --- the video size cap -------------------------------------------------------------------------------------------------
// A width= / height= parameter value of a media type ("1080", " \"1080\" "): 0 when absent or not a plain number.
inline unsigned dimension(const std::string& s0)
{
    size_t a = 0, b = s0.size();
    while (a < b && (s0[a] == ' ' || s0[a] == '"')) ++a;
    while (b > a && (s0[b - 1] == ' ' || s0[b - 1] == '"')) --b;
    if (a == b || b - a > 6) return 0;
    unsigned v = 0;
    for (size_t i = a; i < b; ++i) {
        if (s0[i] < '0' || s0[i] > '9') return 0;
        v = v * 10 + unsigned(s0[i] - '0');
    }
    return v;
}
// Above "480p"? Both known: the short side (portrait 480 x 854 passes). One known: height > 480 / width > 854.
inline bool overCap(unsigned w, unsigned h)
{
    if (w && h) return (w < h ? w : h) > kMaxShort;
    if (h) return h > kMaxShort;
    if (w) return w > kMaxWide;
    return false;
}
// The web process's re-read schedule (milliseconds of any monotonic clock).
struct Recheck {
    bool valid = false, value = false;
    uint64_t at = 0;
    bool due(uint64_t now) const { return !valid || now < at || now - at >= kRecheckMs; }
    void set(uint64_t now, bool v) { valid = true; value = v; at = now; }
};

// --- autoplay (OMNI_AUTOPLAY_V1) ----------------------------------------------------------------------------------------
// The store omniApUse decides with: the user's own, with the global choice taken as blockAll while blocked. Site rules
// (and private-tab session rules) are untouched, so they still win; nothing is written back.
template <class Store, class Mode> inline Store autoplayStore(const Store& user, bool blocked, Mode blockAll)
{
    Store s = user;
    if (blocked) s.global = blockAll;
    return s;
}
constexpr const char* kAutoplayValue = "Block all (Data saver)";
inline std::string autoplayDetail(const std::string& userChoice)
{
    return "Data saver blocks autoplay. Your choice (" + userChoice + ") returns when Data saver is off; site rules still apply.";
}

// --- texts ---------------------------------------------------------------------------------------------------------------
inline const char* onOff(bool v) { return v ? "On" : "Off"; }
// capReady: the engine child has the 480p cap (kCapFlag seen). Without it the video part is named as waiting.
inline std::string mainDetail(const Settings& s, bool capReady)
{
    if (!s.on) return "For slow or metered connections (hotel Wi-Fi, phone hotspot)";
    std::string t;
    auto add = [&](bool v, const char* what) { if (!v) return; if (!t.empty()) t += ", "; t += what; };
    add(s.video, capReady ? "video up to 480p" : "480p cap needs engine update");
    add(s.autoplay, "no autoplay");
    add(s.fonts, "no web fonts");
    add(s.prefetch, "no link prefetch");
    if (t.empty()) return "On, every part below is off";
    if (t[0] >= 'a' && t[0] <= 'z') t[0] = char(t[0] - 'a' + 'A');
    return t;
}
inline const char* partLabel(int id)
{
    switch (id) {
    case kRowVideo: return "Data saver: video up to 480p";
    case kRowAutoplay: return "Data saver: block autoplay";
    case kRowFonts: return "Data saver: block web fonts";
    case kRowPrefetch: return "Data saver: no link prefetch";
    default: return "";
    }
}
inline const char* partDetail(int id, bool capReady)
{
    switch (id) {
    case kRowVideo: return capReady ? "Sites that ask the player for sizes get 480p at most"
                                    : "480p cap: needs engine update (this engine has no cap yet; the choice is kept)";
    case kRowAutoplay: return "Autoplay works as \"Block all\"; site rules still win";
    case kRowFonts: return "Pages use built-in fonts; some icons may show as words";
    case kRowPrefetch: return "Pages can't load the next page ahead of time";
    default: return "";
    }
}
// The value shown for a part ("On" / "Off"; the video part without the cap: "On (needs engine update)").
inline std::string partValue(const Settings& s, int id, bool capReady)
{
    const bool v = id == kRowVideo ? s.video : id == kRowAutoplay ? s.autoplay : id == kRowFonts ? s.fonts : s.prefetch;
    if (id == kRowVideo && v && !capReady) return "On (needs engine update)";
    return onOff(v);
}
inline bool* part(Settings& s, int id)
{
    switch (id) {
    case kRowVideo: return &s.video;
    case kRowAutoplay: return &s.autoplay;
    case kRowFonts: return &s.fonts;
    case kRowPrefetch: return &s.prefetch;
    default: return nullptr;
    }
}
inline std::string mainNotice(const Settings& s, bool capReady, bool reloading)
{
    if (!s.on) return std::string("Data saver off: your own settings are back") + (reloading ? ". Reloading" : "");
    return "Data saver on: " + mainDetail(s, capReady) + (reloading ? ". Reloading" : "");
}
inline std::string partNotice(int id, bool v)
{
    return std::string(partLabel(id)) + " " + (v ? "on" : "off") + " (reload pages to apply)";
}

// --- top bar: right of the battery, the sleep timer, the offline badge and the Downloads ring ----------------------------
constexpr float kTopBarRight = 1276.f, kBadgeGap = 12.f, kDot = 7.f, kTextGap = 5.f;
// chainX: where the Downloads ring would start (OmniDlProgress::startX); the ring as drawn (mode 0: not shown).
inline float startX(float chainX, int dlpMode, float dlpX, float dlpW) { return dlpMode ? dlpX + dlpW + kBadgeGap : chainX; }
struct BadgeLayout { float x = 0; int mode = 0; int textMax = 0; };   // mode 0 hidden, 1 dot, 2 dot + text
inline BadgeLayout badgeLayout(float x, float textW)
{
    BadgeLayout b;
    b.x = x;
    const float room = kTopBarRight - x;
    if (room >= kDot + kTextGap + textW) { b.mode = 2; b.textMax = int(room - kDot - kTextGap); }
    else if (room >= kDot) b.mode = 1;
    return b;
}

} // namespace OmniDataSaver
'''

SHELL = r'''// OMNI_DATA_SAVER_V1: "Data saver", shell side. Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniDlProgressShell.h, whose ring its badge sits right of). The pure part is OmniDataSaver.h; the
// reasons are in tools/apply_data_saver.py. Main thread only; the file is written by omniIoQueue.
#pragma once

namespace ODSV = OmniDataSaver;
static ODSV::Settings omniDsv;
static bool omniDsvLoaded = false;
static bool omniDsvStarted = false;        // the saved setting was applied (first omniF3Tick with the controllers)
static bool omniDsvPrefTouched = false;    // SpeculationRulesPrefetchEnabled was set by us (restore it when off)

static void omniDsvLoad()
{
    if (omniDsvLoaded) return;
    omniDsvLoaded = true;
    if (omniTestMode()) return;
    FILE* f = fopen(omniData(ODSV::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[1024];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < ODSV::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniDsv = ODSV::parse(text);
}
static void omniDsvWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(ODSV::kFileName), ODSV::serialize(omniDsv), false);
}
// Read by omniApUse and the Autoplay row (OmniAutoplayShell.h).
static bool omniDsvAutoplayBlocked() { omniDsvLoad(); return ODSV::autoplayBlocked(omniDsv); }
// The engine child has the 480p cap (its web processes create the flag; checked when the rows are built).
static bool omniDsvCapReady() { return access(ODSV::kCapFlag, F_OK) == 0; }
// Speculation-rules prefetch and the font rule list follow the setting (video and autoplay are read where they act).
static void omniDsvApply()
{
    const bool off = ODSV::prefetchOff(omniDsv);
    if (preferences && (off || omniDsvPrefTouched)) {
        auto key = adoptWK(WKStringCreateWithUTF8CString(ODSV::kSpeculationKey));
        WKPreferencesSetExperimentalFeatureForKey(preferences.get(), !off, key.get());
        omniDsvPrefTouched = true;
    }
    omniBlockerSetDataSaverFonts(ODSV::fontsBlocked(omniDsv));
}
static void omniDsvTick()
{
    if (omniDsvStarted || !omniBlockerController()) return;
    omniDsvStarted = true;
    if (omniTestMode()) return;
    omniDsvLoad();
    if (omniDsv.on) omniDsvApply();
}

// --- top bar: a dot + "Saver" right of the Downloads ring (and the badges before it) -------------------------------------
static void omniDsvDrawTopBar(float base)
{
    if (!omniDsvLoaded || !omniDsv.on) return;
    const OmniTheme& T = omniTheme();
    // where the Downloads ring starts, computed exactly as omniDlpDrawTopBar does
    const float sleepW = omniSt.on() ? float(omniTextWidthPx(omniCaption, omniSt.badge(SDL_GetTicks())) / displayScale) : 0.f;
    int offMode = 0, offTextMax = 0;
    float offX = 0, offTextW = 0;
    if (omniOrWatch.indicator()) {
        offTextW = float(omniTextWidthPx(omniCaptionBold, OOR::kBadge) / displayScale);
        const OOR::BadgeLayout o = OOR::badgeLayout(base, sleepW, offTextW);
        offMode = o.mode; offX = o.x; offTextMax = o.textMax;
    }
    const float chainX = ODLP::startX(base, sleepW, offMode, offX, offTextW, offTextMax);
    const float x = ODSV::startX(chainX, omniDlpDrawn.mode, omniDlpDrawn.x, omniDlpDrawn.w);
    const float textW = float(omniTextWidthPx(omniCaptionBold, ODSV::kBadge) / displayScale);
    const ODSV::BadgeLayout b = ODSV::badgeLayout(x, textW);
    if (!b.mode) return;
    omniDisc(b.x + ODSV::kDot / 2, 30, ODSV::kDot / 2, T.accent);
    if (b.mode == 2) omniLabel(ODSV::kBadge, b.x + ODSV::kDot + ODSV::kTextGap, 30, omniCaptionBold, T.inkDim, 0, b.textMax);
}

// --- Browser settings: "Data saver" and, while on, its four parts -------------------------------------------------------
static void omniDsvSettingsRows(OmniFxPanel& p)
{
    omniDsvLoad();
    OmniFxRow r; r.id = ODSV::kRowMain; r.label = "Data saver"; r.value = ODSV::onOff(omniDsv.on); r.stepper = true;
    const bool cap = omniDsvCapReady();
    r.detail = ODSV::mainDetail(omniDsv, cap);
    p.rows.push_back(r);
    if (!omniDsv.on) return;
    for (int id = ODSV::kRowVideo; id <= ODSV::kRowPrefetch; ++id) {
        OmniFxRow s; s.id = id; s.label = ODSV::partLabel(id); s.value = ODSV::partValue(omniDsv, id, cap); s.stepper = true;
        s.detail = ODSV::partDetail(id, cap);
        p.rows.push_back(s);
    }
}
static bool omniDsvSettingsInput(int id, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    omniDsvLoad();
    if (id == ODSV::kRowMain) {
        omniDsv.on = !omniDsv.on;
        omniDsvWrite();
        omniDsvApply();
        Tab* t = active();
        const bool reload = t && omniWebURL(t->url);
        notice(ODSV::mainNotice(omniDsv, omniDsvCapReady(), reload));
        if (reload) WKPageReload(t->page);
        return true;
    }
    bool* v = ODSV::part(omniDsv, id);
    if (!v) return false;
    *v = !*v;
    omniDsvWrite();
    omniDsvApply();
    notice(ODSV::partNotice(id, *v));
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n',
         '#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n'
         '#include "OmniDataSaver.h" // OMNI_DATA_SAVER_V1: Data saver (pure)\n'),
        ('static void omniDlpHandedOver();              // OMNI_DL_PROGRESS_V1: watch the Downloads app for the next 10 s\n',
         'static void omniDlpHandedOver();              // OMNI_DL_PROGRESS_V1: watch the Downloads app for the next 10 s\n'
         'static void omniDsvDrawTopBar(float x);       // OMNI_DATA_SAVER_V1 (OmniDataSaverShell.h): "Saver" in the top bar\n'
         'static bool omniDsvAutoplayBlocked();         // OMNI_DATA_SAVER_V1: Autoplay works as "Block all" (omniApUse)\n'),
        ('    omniDlpDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_DL_PROGRESS_V1: Downloads progress while jobs run\n',
         '    omniDlpDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_DL_PROGRESS_V1: Downloads progress while jobs run\n'
         '    omniDsvDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_DATA_SAVER_V1: "Saver" while data saver is on\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniOrRowId = 895; // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h)\n',
         'constexpr int omniOrRowId = 895; // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h)\n'
         'static void omniDsvSettingsRows(OmniFxPanel& p); // OMNI_DATA_SAVER_V1 (OmniDataSaverShell.h): rows 825-829\n'
         'static bool omniDsvSettingsInput(int id, int b);\n'),
        ('    add(omniOrRowId, "Reload pages when back online", omniOrOn() ? "On" : "Off", true); // OMNI_OFFLINE_RETRY_V1\n',
         '    add(omniOrRowId, "Reload pages when back online", omniOrOn() ? "On" : "Off", true); // OMNI_OFFLINE_RETRY_V1\n'
         '    omniDsvSettingsRows(p); // OMNI_DATA_SAVER_V1: Data saver (+ its four parts while on)\n'),
        ('    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n',
         '    if (r.id >= OmniDataSaver::kRowMain && r.id <= OmniDataSaver::kRowPrefetch) return omniDsvSettingsInput(r.id, b); // OMNI_DATA_SAVER_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniDlProgressShell.h" // OMNI_DL_PROGRESS_V1 (after offline retry: its badge sits right of that one)\n',
         '#include "OmniDlProgressShell.h" // OMNI_DL_PROGRESS_V1 (after offline retry: its badge sits right of that one)\n'
         '#include "OmniDataSaverShell.h" // OMNI_DATA_SAVER_V1 (after Downloads progress: its badge sits right of that one)\n'),
        ('    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n',
         '    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n'
         '    omniDsvTick();      // OMNI_DATA_SAVER_V1: applies the saved setting once the content controllers exist\n'),
    ],
    'OmniAutoplayShell.h': [
        ('        const OAP::Decision d = OAP::decide(omniApStore, omniApSession, u, tab && tab->omniPrivate);\n',
         '        const OAP::Decision d = OAP::decide(OmniDataSaver::autoplayStore(omniApStore, omniDsvAutoplayBlocked(), OAP::kBlock), omniApSession, u, tab && tab->omniPrivate); // OMNI_DATA_SAVER_V1: global "Block all" while data saver is on\n'),
        ('    r.detail = OAP::globalDetail(omniApStore.global);\n',
         '    r.detail = OAP::globalDetail(omniApStore.global);\n'
         '    if (omniDsvAutoplayBlocked()) { r.detail = OmniDataSaver::autoplayDetail(r.value); r.value = OmniDataSaver::kAutoplayValue; } // OMNI_DATA_SAVER_V1\n'),
    ],
    'OmniBlocker.h': [
        ('bool omniBlockerFailed();\n',
         'bool omniBlockerFailed();\n'
         'void omniBlockerSetDataSaverFonts(bool block); // OMNI_DATA_SAVER_V1: the font content rule (normal + private tabs)\n'),
    ],
    'OmniBlocker.cpp': [
        ('void ucRemoveAllFilters()\n',
         'void saverReadd();   // OMNI_DATA_SAVER_V1 (defined below)\n'
         'void ucRemoveAllFilters()\n'),
        ('    if (privateController) WKUserContentControllerRemoveAllUserContentFilters(privateController.get());\n',
         '    if (privateController) WKUserContentControllerRemoveAllUserContentFilters(privateController.get());\n'
         '    saverReadd();   // OMNI_DATA_SAVER_V1: the font rule survives a filter reset\n'),
        ('void (*completion)(bool) = nullptr;\n',
         'void (*completion)(bool) = nullptr;\n'
         '// OMNI_DATA_SAVER_V1: data saver\'s "block web fonts" rule list (compiled once per launch on first use).\n'
         'WKRetainPtr<WKUserContentFilterRef> saverFilter;\n'
         'bool saverWanted = false, saverCompiling = false;\n'
         'void saverReadd()\n'
         '{\n'
         '    if (saverWanted && saverFilter) ucAddFilter(saverFilter.get());\n'
         '}\n'),
        ('bool omniBlockerFailed() { return enabled && nativeFailed; }\n',
         'bool omniBlockerFailed() { return enabled && nativeFailed; }\n'
         'void omniBlockerSetDataSaverFonts(bool block) // OMNI_DATA_SAVER_V1\n'
         '{\n'
         '    if (!controller || block == saverWanted) return;\n'
         '    saverWanted = block;\n'
         '    if (!block) {   // no single-filter removal in the C API: reset, then the host list as omniBlockerSetEnabled has it\n'
         '        ucRemoveAllFilters();\n'
         '        if (enabled && !nativeReady && filter) ucAddFilter(filter.get());\n'
         '        return;\n'
         '    }\n'
         '    if (saverFilter) { ucAddFilter(saverFilter.get()); return; }\n'
         '    if (saverCompiling) return;\n'
         '    if (!store) {\n'
         '        mkdir("/data/omni/content-rules", 0777);\n'
         '        store = adoptWK(WKUserContentExtensionStoreCreate(adoptWK(WKStringCreateWithUTF8CString("/data/omni/content-rules")).get()));\n'
         '        if (!store) return;\n'
         '    }\n'
         '    saverCompiling = true;\n'
         '    auto identifier = adoptWK(WKStringCreateWithUTF8CString("omni-data-saver-fonts-v1"));\n'
         '    auto json = adoptWK(WKStringCreateWithUTF8CString("[{\\"trigger\\":{\\"url-filter\\":\\".*\\",\\"resource-type\\":[\\"font\\"]},\\"action\\":{\\"type\\":\\"block\\"}},"\n'
         '        "{\\"trigger\\":{\\"url-filter\\":\\"^omni:\\"},\\"action\\":{\\"type\\":\\"ignore-previous-rules\\"}}]"));   // = OmniDataSaver::kFontRules\n'
         '    WKUserContentExtensionStoreCompile(store.get(), identifier.get(), json.get(), nullptr,\n'
         '        [](WKUserContentFilterRef result, WKUserContentExtensionStoreResult code, void*) {\n'
         '            saverCompiling = false;\n'
         '            if (code == kWKUserContentExtensionStoreSuccess && result) saverFilter = adoptWK(result);\n'
         '            fprintf(stderr, "browser: data saver font rule compile result=%u\\n", code);\n'
         '            fflush(stderr);\n'
         '            if (saverWanted && saverFilter) ucAddFilter(saverFilter.get());\n'
         '        });\n'
         '}\n'),
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


def ids_free():
    """Refuse when another feature already uses one of our row ids (as an id: '= 825', '== 825', '825,' in a list)."""
    # Engine tree only: sibling apply_*.py files are not scanned (their notes list other patches' ids; a numeric hit
    # there would stop the title build, which runs every script from this folder).
    pat = re.compile(r'(?:==?|\bcase)\s*(%s)\b' % '|'.join(str(i) for i in IDS))
    for f in sorted(root.iterdir()):
        if f.suffix not in ('.h', '.cpp', '.inc') or f.name.startswith('OmniDataSaver'):
            continue
        s = f.read_bytes().decode('utf-8', errors='replace')
        if MARK in s:
            continue
        m = pat.search(cpp_code(s))
        if m:
            sys.exit('id %s is already used in %s: pick other ids' % (m.group(1), f.name))


def main():
    f3 = (root / 'OmniFeatures3.h').read_bytes().decode('utf-8')
    for need, tool in (('OMNI_AUTOPLAY_V1', 'apply_autoplay.py'), ('OMNI_OFFLINE_RETRY_V1', 'apply_offline_retry.py'),
                       ('OMNI_DL_PROGRESS_V1', 'apply_dl_progress.py'), ('OMNI_SITE_CLEAR_V1', 'apply_site_clear.py')):
        if need not in f3:
            sys.exit('OmniFeatures3.h: %s missing: %s first' % (need, tool))
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniDataSaver.h', PURE, 'OmniOfflineRetry.h'),
            write_new('OmniDataSaverShell.h', SHELL, 'OmniDlProgressShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


if __name__ == '__main__':
    main()
