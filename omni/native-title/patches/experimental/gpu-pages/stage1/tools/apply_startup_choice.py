#!/usr/bin/env python3
"""OMNI_STARTUP_CHOICE_V1 (2026-11-16): Browser settings > "On start", and a prompt after Omni didn't close properly.

What existed (audited on the rc6 title chain, apply_ublock_frames.py .. apply_text_cache_cap.py)
  - omniEverydayStart (OMNI_EVERYDAY_V1 / OMNI_FEATURES_V3) ALWAYS restores session.txt: "tab\t<url>\t<title>" lines
    (up to the Tab limit), "pinned\t<n>" (OMNI_PINNED_TABS_V1), "group\t<n>\t..." (OMNI_TAB_GROUPS_V1) and
    "selected\t<n>". Tabs are created lazy (omniLazyURL); only the shown one loads (omniEverydayActivated), the others
    when first shown. Private and Media-section tabs are never written (omniSessionText), so never restored.
    Nothing restored -> one new-tab (start) page. So the current default is "Continue where you left off".
  - Home page (omniFxSet.home, Browser settings "Home page", omniFxHomeEdit) is only used by the Home action; it is
    not used at start.
  - There was no clean-exit flag: omniEverydayShutdown (session save + omniIoFlush) runs only on the normal quit
    path (running = false). A crash / power loss / kill just leaves session.txt as last saved (once a second).
    OmniCrash.h (OmniMain.cpp, title and child processes) appends to /data/omni/native/crash.log on a fatal signal
    only; nothing else writes that file.
  - Saved sessions (OMNI_TAB_SESSIONS_V1, sessions.txt, omniTsList / omniTsOpen) exist; omniTsOpen(s, replace)
    opens a session lazily, regroups it, and with replace closes the other unpinned tabs.

What the user sees
  - Browser settings, right after "Home page": "On start", a stepper:
        Continue where you left off  (default: exactly the old behaviour)
        Open the start page
        Open my home page            ("Open my home page (not set)" while no home page is set: the start page opens)
        Open a saved session: <name> (skipped by the D-pad while no session is saved)
    D-pad left/right / Cross step it; Cross on "Open a saved session" opens a picker of the saved sessions
    ("On start: open a saved session"; Cross chooses, Circle back); Triangle resets to Continue.
  - Omni writes /data/omni/running.txt at start and deletes it on a clean exit (omniEverydayShutdown, after the last
    session save is flushed). Found at the next start = Omni didn't close properly (crash, power loss, killed).
      * "On start" is not Continue: after the chosen page / session opened, a small prompt
            "Omni didn't close properly."   "Restore your N tabs?"   [Not now] [Restore]
        Restore opens last time's tabs (as a saved session would: lazily, groups and pins kept, the tab that was shown
        is shown; the start / home page tab makes way, a chosen saved session stays). Not now forgets them.
      * Continue: restored as always, except the tab that was shown when Omni crashed, if that address was the
        shown one at the last 2 crashes in a row: it is restored but not loaded; showing it says
            "This page may have crashed Omni - tap to load"   + a prompt [Not now] [Load]
        (Load: it loads as a normal first show; Not now: it stays unloaded, the prompt comes back when it is shown).
  - Private tabs are never restored (unchanged: they are never in session.txt; the marker records "private" for a
    private tab, never its address).

Crash count (OSTC::verdict, the pure part)
  running.txt: "omni-running\t1", "active\t<url | private>" (the shown tab, refreshed every second when it changes),
  "streak\t<n>\t<url>" (consecutive crashes with that address shown), "held\t<url>" (that address is held unloaded),
  "crashlog\t<bytes>" (crash.log's size when this run started).
  At start, marker present => unclean. It counts as a crash of the shown page only when crash.log grew since the run
  started (a fatal signal was reported); a kill or power loss (PS button > Close, unplugged) leaves the streak as it
  was, so closing Omni from the system menu on the same page never holds it. The streak goes up by one when the
  shown address is the streak's address (else restarts at 1); an address that was held (never loaded) gets no new
  count. Held when streak >= 2. A clean exit deletes the marker: the streak is forgotten.

Files
  new  OmniStartupChoice.h        pure (no SDL / WebKit): settings + marker parse/serialize, the crash rule, choice ->
                                  plan, texts. Tested by tools/test_startup_choice.cpp:
                                  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_startup_choice.cpp -o t && ./t
  new  OmniStartupChoiceShell.h   shell side (included from OmniFeatures3.h after OmniPadFeedbackShell.h)
  data /data/omni/startup.txt     "omni-startup\t1", "choice\t<0..3>", "session\t<name>"
       /data/omni/running.txt     the marker above

Anchors (exactly once each; MARK makes each file idempotent; CRLF/LF kept per file)
  OmniBrowser.cpp       the OmniPlaybackSpeed.h include line (apply_playback_speed.py's);
                        omniEverydayActivated's "if (!tab || tab->omniLazyURL.empty()) return;" line;
                        omniEverydayStart's "if (saved.empty()) saved.emplace_back(...)" line (before the restore
                        block) and its "Restored N tabs" notice line (after the whole block: the pinned / group
                        restore lines are NOT anchors, their order is being changed separately);
                        omniEverydayShutdown's "omniSessionSave(); omniIoFlush(); }" body.
  OmniFeatures3Decl.h   the "static bool omniTmSkipRestore = false, omniF3Restoring = false;" line.
  OmniBrowserSettings.h the omniPfSettingsRow / omniPfSettingsInput declarations (apply_pad_feedback.py's), the
                        "Home page" add(...) line, the omniPfRowId input line.
  OmniFeatures3.h       the OmniPadFeedbackShell.h include line, the omniOrTick line of omniF3Tick.
Ids: Browser settings row 878 (845-899 partly taken: 875 start custom, 876 web apps, 880 autoplay; 878 is in no
apply_*.py); picker rows 1 / 1000+ (own panel). Names: OSTC / omniStc* / OmniStartupChoice* (unused elsewhere).

Apply AFTER apply_pad_feedback.py, apply_offline_retry.py, apply_tab_sessions.py, apply_pinned_tabs.py,
apply_tab_groups.py and apply_playback_speed.py (their lines are anchors / their functions are used).
usage: apply_startup_choice.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_STARTUP_CHOICE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'
ROW_ID = 878

PURE = r'''// OMNI_STARTUP_CHOICE_V1: the pure part of Browser settings > "On start" and the "didn't close properly" prompt
// (no SDL, no WebKit). The shell side is OmniStartupChoiceShell.h; the reasons are in tools/apply_startup_choice.py.
// Tested on the host with g++ (tools/test_startup_choice.cpp).
#pragma once
#include <algorithm>
#include <string>
#include <vector>

namespace OmniStartupChoice {

enum Choice { kContinue = 0, kStartPage = 1, kHomePage = 2, kSavedSession = 3 };
constexpr int kChoices = 4;
constexpr Choice kDefault = kContinue;        // the behaviour before this setting existed
constexpr int kHoldAfter = 2;                 // crashes in a row with the same page shown
constexpr int kStreakMax = 99;
constexpr const char* kSettingsFile = "startup.txt";
constexpr const char* kMarkerFile = "running.txt";
constexpr const char* kSettingsHeader = "omni-startup\t1";
constexpr const char* kMarkerHeader = "omni-running\t1";
constexpr const char* kPrivate = "private";   // the marker's "active" for a private tab: never its address
constexpr size_t kUrlMax = 2048, kNameMax = 60, kFileMax = 64 << 10;

inline bool webUrl(const std::string& u) { return u.rfind("https://", 0) == 0 || u.rfind("http://", 0) == 0; }
inline std::string oneLine(std::string s, size_t max)
{
    for (auto& c : s) if (c == '\t' || c == '\n' || c == '\r') c = ' ';
    if (s.size() > max) { size_t cut = max; while (cut && (static_cast<unsigned char>(s[cut]) & 0xc0) == 0x80) --cut; s.resize(cut); }
    return s;
}
inline std::vector<std::string> lines(const std::string& text)
{
    std::vector<std::string> out;
    size_t at = 0;
    while (at < text.size() && at < kFileMax) {
        size_t e = text.find('\n', at);
        if (e == std::string::npos) e = text.size();
        std::string l = text.substr(at, e - at);
        while (!l.empty() && l.back() == '\r') l.pop_back();
        out.push_back(std::move(l));
        at = e + 1;
    }
    return out;
}
inline bool after(const std::string& line, const char* prefix, std::string& rest)
{
    const std::string p(prefix);
    if (line.rfind(p, 0) != 0) return false;
    rest = line.substr(p.size());
    return true;
}
inline bool number(const std::string& s, long long& v)   // decimal, optional '-', nothing else
{
    if (s.empty() || s.size() > 18) return false;
    size_t i = s[0] == '-' ? 1 : 0;
    if (i == s.size()) return false;
    long long n = 0;
    for (; i < s.size(); ++i) { if (s[i] < '0' || s[i] > '9') return false; n = n * 10 + (s[i] - '0'); }
    v = s[0] == '-' ? -n : n;
    return true;
}

// --- startup.txt ----------------------------------------------------------------------------------------------------
struct Settings { Choice choice = kDefault; std::string session; };
inline std::string serializeSettings(const Settings& s)
{
    return std::string(kSettingsHeader) + "\nchoice\t" + std::to_string(int(s.choice)) + "\nsession\t" + oneLine(s.session, kNameMax * 4) + "\n";
}
inline Settings parseSettings(const std::string& text)   // anything unreadable: the default
{
    Settings s;
    const std::vector<std::string> ls = lines(text);
    if (ls.empty() || ls[0] != kSettingsHeader) return s;
    for (size_t i = 1; i < ls.size(); ++i) {
        std::string rest;
        long long v = 0;
        if (after(ls[i], "choice\t", rest)) { if (number(rest, v) && v >= 0 && v < kChoices) s.choice = Choice(v); }
        else if (after(ls[i], "session\t", rest)) s.session = oneLine(rest, kNameMax * 4);
    }
    return s;
}

// --- running.txt (written at start, deleted on a clean exit) ---------------------------------------------------------
struct Marker {
    std::string active;        // the shown tab: its address, kPrivate, or empty (start page, nothing web)
    std::string streakUrl;     // the address shown at the last `streak` crashes in a row
    int streak = 0;
    std::string held;          // restored unloaded because of the streak (never loaded in that run)
    long long crashLog = -1;   // crash.log's size when the run started (-1: unknown)
};
inline std::string serializeMarker(const Marker& m)
{
    std::string s = std::string(kMarkerHeader) + "\n";
    if (!m.active.empty()) s += "active\t" + oneLine(m.active, kUrlMax) + "\n";
    if (m.streak > 0 && !m.streakUrl.empty()) s += "streak\t" + std::to_string(std::clamp(m.streak, 1, kStreakMax)) + "\t" + oneLine(m.streakUrl, kUrlMax) + "\n";
    if (!m.held.empty()) s += "held\t" + oneLine(m.held, kUrlMax) + "\n";
    if (m.crashLog >= 0) s += "crashlog\t" + std::to_string(m.crashLog) + "\n";
    return s;
}
inline bool parseMarker(const std::string& text, Marker& m)   // false: not a marker (m is the default then)
{
    m = Marker();
    const std::vector<std::string> ls = lines(text);
    if (ls.empty() || ls[0] != kMarkerHeader) return false;
    for (size_t i = 1; i < ls.size(); ++i) {
        std::string rest;
        long long v = 0;
        if (after(ls[i], "active\t", rest)) m.active = rest;
        else if (after(ls[i], "held\t", rest)) m.held = rest;
        else if (after(ls[i], "crashlog\t", rest)) { if (number(rest, v) && v >= 0) m.crashLog = v; }
        else if (after(ls[i], "streak\t", rest)) {
            const size_t t = rest.find('\t');
            if (t == std::string::npos || !number(rest.substr(0, t), v) || v < 1) continue;
            m.streak = int(std::min<long long>(v, kStreakMax));
            m.streakUrl = rest.substr(t + 1);
            if (!webUrl(m.streakUrl)) { m.streak = 0; m.streakUrl.clear(); }
        }
    }
    return true;
}

// The marker found at start (present: the file exists, whatever it holds) and crash.log's size now.
struct Verdict {
    bool unclean = false;      // Omni didn't close properly (crash, power loss, killed)
    bool counted = false;      // ... and a fatal signal was reported meanwhile (crash.log grew)
    std::string blamed;        // the web address that was shown then (empty: none, a private tab, the start page)
    std::string streakUrl;     // carried into this run's marker
    int streak = 0;
    bool hold = false;         // restore `blamed` without loading it
};
inline Verdict verdict(bool present, const Marker& m, long long crashLogNow)
{
    Verdict v;
    if (!present) return v;    // clean exit last time: the streak is forgotten
    v.unclean = true;
    v.counted = m.crashLog >= 0 && crashLogNow > m.crashLog;
    v.blamed = webUrl(m.active) ? m.active : std::string();
    v.streakUrl = m.streakUrl;
    v.streak = m.streakUrl.empty() ? 0 : std::clamp(m.streak, 0, kStreakMax);
    if (!v.blamed.empty() && v.blamed != m.held && v.counted) {   // a held page never loaded: no new evidence
        v.streak = std::min((v.streakUrl == v.blamed ? v.streak : 0) + 1, kStreakMax);
        v.streakUrl = v.blamed;
    }
    if (!v.streak) v.streakUrl.clear();
    v.hold = !v.blamed.empty() && v.streakUrl == v.blamed && v.streak >= kHoldAfter;
    return v;
}

// --- what opens at start ---------------------------------------------------------------------------------------------
struct Plan {
    enum Open { kLast, kNewTab, kHome, kSession } open = kLast;
    bool prompt = false;           // ask "Restore your N tabs?" afterwards
    int restorable = 0;            // N
    bool missingHome = false, missingSession = false;
};
inline int restorable(const std::vector<std::string>& urls) { int n = 0; for (auto& u : urls) if (webUrl(u)) ++n; return n; }
// sessionIndex: the chosen saved session in the list (-1: none / not found).
inline Plan plan(const Settings& s, const std::string& home, int sessionIndex, bool unclean, int restorableTabs)
{
    Plan p;
    switch (s.choice) {
    case kContinue: p.open = Plan::kLast; break;
    case kStartPage: p.open = Plan::kNewTab; break;
    case kHomePage: if (webUrl(home)) p.open = Plan::kHome; else { p.open = Plan::kNewTab; p.missingHome = true; } break;
    case kSavedSession: if (sessionIndex >= 0) p.open = Plan::kSession; else { p.open = Plan::kNewTab; p.missingSession = true; } break;
    }
    p.restorable = std::max(0, restorableTabs);
    p.prompt = unclean && s.choice != kContinue && p.restorable > 0;
    return p;
}
// D-pad step; "Open a saved session" only while one is saved.
inline Choice step(Choice c, int dir, bool haveSessions)
{
    if (!dir) return c;
    int n = int(c);
    for (int i = 0; i < kChoices; ++i) {
        n = (n + (dir > 0 ? 1 : -1) + kChoices) % kChoices;
        if (n != kSavedSession || haveSessions) return Choice(n);
    }
    return c;
}

// --- texts -----------------------------------------------------------------------------------------------------------
inline const char* rowLabel() { return "On start"; }
inline std::string valueText(const Settings& s, bool sessionExists, bool homeSet)
{
    switch (s.choice) {
    case kContinue: return "Continue where you left off";
    case kStartPage: return "Open the start page";
    case kHomePage: return homeSet ? "Open my home page" : "Open my home page (not set)";
    case kSavedSession:
        if (s.session.empty() || !sessionExists) return "Open a saved session (pick)";
        return "Open a saved session: " + s.session;
    }
    return "";
}
inline std::string tabsText(int n) { return std::to_string(n) + (n == 1 ? " tab" : " tabs"); }
inline const char* promptTitle() { return "Omni didn't close properly."; }
inline std::string promptBody(int n) { return n == 1 ? std::string("Restore your tab?") : "Restore your " + std::to_string(n) + " tabs?"; }
inline const char* restoreLabel() { return "Restore"; }
inline const char* notNowLabel() { return "Not now"; }
inline const char* holdNotice() { return "This page may have crashed Omni \xe2\x80\x94 tap to load"; }
inline const char* holdTitle() { return "This page may have crashed Omni"; }
inline std::string hostOf(const std::string& url)
{
    size_t a = url.find("://");
    a = a == std::string::npos ? 0 : a + 3;
    size_t e = url.find_first_of("/?#", a);
    std::string h = url.substr(a, e == std::string::npos ? std::string::npos : e - a);
    const size_t at = h.rfind('@');
    if (at != std::string::npos) h = h.substr(at + 1);
    return h.rfind("www.", 0) == 0 ? h.substr(4) : h;
}
inline std::string holdBody(const std::string& url)
{
    const std::string h = hostOf(url);
    return (h.empty() ? std::string("This page") : h) + " was open the last " + std::to_string(kHoldAfter)
        + " times Omni closed unexpectedly, so it wasn't loaded. Load it now?";
}
inline const char* loadLabel() { return "Load"; }
inline std::string startNotice(const Plan& p, const std::string& sessionName, int opened)
{
    if (p.missingHome) return "No home page set: opened the start page";
    if (p.missingSession) return "The saved session for start-up is gone: opened the start page";
    if (p.open == Plan::kSession) return "Opened \"" + sessionName + "\": " + tabsText(opened);
    return "";
}
inline std::string pickedNotice(const std::string& name) { return "On start: open \"" + name + "\""; }
inline std::string choiceNotice(const Settings& s) { return std::string("On start: ") + (s.choice == kContinue ? "continue where you left off" : s.choice == kStartPage ? "open the start page" : s.choice == kHomePage ? "open your home page" : "open a saved session"); }

} // namespace OmniStartupChoice
'''

SHELL = r'''// OMNI_STARTUP_CHOICE_V1: Browser settings > "On start" + the "didn't close properly" prompt (shell side). Included
// from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous namespace, after OmniPadFeedbackShell.h, so the pinned-tab,
// tab-group and saved-session shells are visible). The pure part is OmniStartupChoice.h; the reasons are in
// tools/apply_startup_choice.py. Main thread only.
#pragma once

namespace OSTC = OmniStartupChoice;
#ifndef OMNI_STC_CRASH_LOG
#define OMNI_STC_CRASH_LOG "/data/omni/native/crash.log"   // OmniCrash.h's OMNI_CRASH_LOG2_PATH: fatal signals only, append-only
#endif

static OSTC::Settings omniStcSet;
static bool omniStcLoaded = false;
static OSTC::Marker omniStcMark;                 // what running.txt holds in this run
static std::string omniStcWritten;               // its last written text
static bool omniStcLive = false;                 // the marker exists (normal start, not a self-test)
static OSTC::Plan omniStcPlan;
static bool omniStcPrompt = false;
static OmniTabSessions::Session omniStcPrev;     // last time's tabs, for "Restore"
static std::vector<std::string> omniStcPrevPinned;
static std::string omniStcPrevShown;
static std::string omniStcHoldUrl;               // restored, not loaded: it may have crashed Omni
static const void* omniStcHoldTab = nullptr;
static std::string omniStcStatus;                // the status line before omniEverydayStart's notice
static uint32_t omniStcStatusUntil = 0, omniStcCheckedAt = 0;
enum { omniStcPickEmpty = 1, omniStcPickFirst = 1000 };

static bool omniStcRead(const std::string& path, std::string& out)
{
    out.clear();
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return false;
    char buf[4096];
    size_t got;
    while ((got = fread(buf, 1, sizeof(buf), f)) > 0 && out.size() < OSTC::kFileMax) out.append(buf, got);
    fclose(f);
    return true;
}
static long long omniStcFileSize(const char* path)
{
    FILE* f = fopen(path, "rb");
    if (!f) return 0;
    long long n = fseek(f, 0, SEEK_END) == 0 ? (long long)ftell(f) : 0;
    fclose(f);
    return n < 0 ? 0 : n;
}
static void omniStcLoad()
{
    if (omniStcLoaded) return;
    omniStcLoaded = true;
    std::string text;
    if (omniStcRead(omniData(OSTC::kSettingsFile), text)) omniStcSet = OSTC::parseSettings(text);
}
static void omniStcSave()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OSTC::kSettingsFile), OSTC::serializeSettings(omniStcSet), false);
}
static std::string omniStcActiveKey()
{
    Tab* t = active();
    if (!t) return std::string();
    if (t->omniPrivate) return OSTC::kPrivate;
    if (omniMediaOwns(*t)) return std::string();
    const std::string u = omniPtURL(*t);
    return omniWebURL(u) ? u : std::string();
}
static void omniStcWriteMarker(bool now)
{
    std::string text = OSTC::serializeMarker(omniStcMark);
    if (text == omniStcWritten) return;
    omniStcWritten = text;
    if (!now) { omniIoQueue(omniData(OSTC::kMarkerFile), std::move(text), false); return; }
    if (FILE* f = fopen(omniData(OSTC::kMarkerFile).c_str(), "wb")) { fwrite(text.data(), 1, text.size(), f); fclose(f); }
}

// --- omniEverydayStart: before the tabs are made (`saved` / `sel` as read from session.txt) ---------------------------
static void omniStcBegin(std::vector<std::pair<std::string, std::string>>& saved, int& sel)
{
    omniStcLoad();
    omniFxLoad();
    std::string text;
    const bool present = omniStcRead(omniData(OSTC::kMarkerFile), text);
    OSTC::Marker m;
    OSTC::parseMarker(text, m);
    const long long logNow = omniStcFileSize(OMNI_STC_CRASH_LOG);
    const OSTC::Verdict v = OSTC::verdict(present, m, logNow);
    omniStcMark = OSTC::Marker();
    omniStcMark.streakUrl = v.streakUrl; omniStcMark.streak = v.streak; omniStcMark.crashLog = logNow;
    if (present) fprintf(stderr, "OMNI STARTUP: last run didn't close properly (%s); streak %d%s\n", v.counted ? "crash reported" : "no crash report: killed / power", v.streak, v.hold ? ", holding the shown page" : "");

    // last time's tabs (the prompt's Restore): web tabs only; their group and pinned marks
    omniStcPrev = OmniTabSessions::Session(); omniStcPrev.name = "last time";
    omniStcPrevPinned.clear(); omniStcPrevShown.clear();
    std::vector<std::string> urls;
    for (size_t i = 0; i < saved.size(); ++i) {
        urls.push_back(saved[i].first);
        if (!omniWebURL(saved[i].first)) continue;
        OmniTabSessions::Tab t; t.url = saved[i].first; t.title = saved[i].second;
        for (const OTG::Mark& k : omniTgRestoreMarks) if (k.index == int(i)) { t.group = OTG::payload(k.group, k.colour, k.collapsed, k.name); break; }
        omniStcPrev.tabs.push_back(std::move(t));
    }
    for (int i : omniPtRestoreIdx) if (i >= 0 && i < int(saved.size()) && omniWebURL(saved[size_t(i)].first)) omniStcPrevPinned.push_back(saved[size_t(i)].first);
    if (sel >= 0 && sel < int(saved.size())) omniStcPrevShown = saved[size_t(sel)].first;

    int si = -1;
    if (omniStcSet.choice == OSTC::kSavedSession) { omniTsLoad(); si = OmniTabSessions::find(omniTsList, omniStcSet.session); }
    omniStcPlan = OSTC::plan(omniStcSet, omniFxSet.home, si, v.unclean, OSTC::restorable(urls));
    if (omniStcPlan.open == OSTC::Plan::kLast) {   // Continue where you left off: as before
        omniStcPrev = OmniTabSessions::Session(); omniStcPrevPinned.clear();
        if (v.hold) { omniStcHoldUrl = v.blamed; fprintf(stderr, "OMNI STARTUP: %s restored unloaded (shown at %d crashes in a row)\n", OSTC::hostOf(v.blamed).c_str(), v.streak); }
        return;
    }
    omniPtRestoreIdx.clear();      // last time's pins and groups are not this start's tabs
    omniTgRestoreMarks.clear();
    saved.clear();
    sel = 0;
    if (omniStcPlan.open == OSTC::Plan::kHome) saved.emplace_back(omniFxSet.home, std::string());
    else if (omniStcPlan.open == OSTC::Plan::kSession) {
        const OmniTabSessions::Session& s = omniTsList[size_t(si)];
        for (const OmniTabSessions::Tab& t : s.tabs) {
            if (saved.size() >= size_t(omniF3TabLimit())) break;
            if (!omniWebURL(t.url)) continue;
            OTG::Mark k;
            if (!t.group.empty() && OTG::parsePayload(t.group, k)) { k.index = int(saved.size()); omniTgRestoreMarks.push_back(k); }
            saved.emplace_back(t.url, t.title);
        }
    }
    omniStcPrompt = omniStcPlan.prompt;
    omniStcStatus = status; omniStcStatusUntil = statusUntil;
}

// --- the prompts -----------------------------------------------------------------------------------------------------
static void omniStcLoadHeld()
{
    Tab* t = active();
    const void* held = omniStcHoldTab;
    omniStcHoldUrl.clear(); omniStcHoldTab = nullptr; omniStcMark.held.clear();
    if (t && t == held) omniEverydayActivated();   // its lazy address loads as a normal first show
    omniShellDirty = true;
}
static void omniStcAskLoad()
{
    Tab* t = active();
    if (!t || t != omniStcHoldTab || omniModalVisible()) return;
    auto m = std::make_unique<OmniModal>();
    m->kind = omniModalAsk; m->title = OSTC::holdTitle(); m->message = OSTC::holdBody(omniStcHoldUrl);
    m->okLabel = OSTC::loadLabel(); m->cancelLabel = OSTC::notNowLabel();
    m->ask = [](bool ok) { if (ok) omniStcLoadHeld(); };
    m->focus = 0;   // Not now first, as omniAsk
    omniModalPush(std::move(m));
}
static void omniStcRestorePrev()
{
    OmniTabSessions::Session s = std::move(omniStcPrev);
    omniStcPrev = OmniTabSessions::Session();
    if (s.tabs.empty()) return;
    omniTsOpen(s, omniStcPlan.open != OSTC::Plan::kSession);   // the start / home page tab makes way; a chosen session stays
    bool pinned = false;
    for (const std::string& u : omniStcPrevPinned) {
        if (omniPtCount() >= OPT::kMaxPinned) break;
        for (auto& t : tabs) if (!t->omniPrivate && !omniPtPinned(*t) && omniPtURL(*t) == u) { omniPtSet.push_back(t.get()); pinned = true; break; }
    }
    omniStcPrevPinned.clear();
    if (pinned) { omniPtSortFirst(); omniTgNormalize(); }
    if (!omniStcPrevShown.empty()) for (size_t i = 0; i < tabs.size(); ++i) if (omniPtURL(*tabs[i]) == omniStcPrevShown) { if (i != selected) activate(i); break; }
    omniStcPrevShown.clear();
    omniShellDirty = true;
}
static void omniStcAskRestore()
{
    const int n = int(omniStcPrev.tabs.size());
    if (n <= 0) return;
    auto m = std::make_unique<OmniModal>();
    m->kind = omniModalAsk; m->title = OSTC::promptTitle(); m->message = OSTC::promptBody(n);
    m->okLabel = OSTC::restoreLabel(); m->cancelLabel = OSTC::notNowLabel();
    m->ask = [](bool ok) { if (ok) omniStcRestorePrev(); else { omniStcPrev = OmniTabSessions::Session(); omniStcPrevPinned.clear(); omniStcPrevShown.clear(); } };
    m->focus = 0;
    omniModalPush(std::move(m));
}

// --- omniEverydayStart: after the whole restore block (tabs made, one shown) ------------------------------------------
static void omniStcStarted()
{
    if (omniTestMode()) return;
    omniStcLive = true;
    omniStcMark.active = omniStcActiveKey();
    omniStcMark.held = omniStcHoldTab ? omniStcHoldUrl : std::string();
    omniStcWriteMarker(true);   // at once: a crash in the first second still counts
    if (omniStcPlan.open != OSTC::Plan::kLast) {
        status = omniStcStatus; statusUntil = omniStcStatusUntil;   // not "Restored 1 tab from last time"
        const std::string n = OSTC::startNotice(omniStcPlan, omniStcSet.session, int(tabs.size()));
        if (!n.empty()) notice(n);
    }
    if (omniStcPrompt) { omniStcPrompt = false; omniStcAskRestore(); }
    else if (omniStcHoldTab) { notice(OSTC::holdNotice()); omniStcAskLoad(); }
}
// omniEverydayActivated, before a lazy tab loads: true = keep it unloaded.
static bool omniStcHeld(Tab& tab)
{
    if (omniStcHoldUrl.empty() || tab.omniLazyURL != omniStcHoldUrl) return false;
    if (omniStcHoldTab && omniStcHoldTab != &tab) return false;   // another tab with that address loads as usual
    omniStcHoldTab = &tab;
    omniShellDirty = true;
    if (omniStcLive) { notice(OSTC::holdNotice()); omniStcAskLoad(); }   // start-up: omniStcStarted asks
    return true;
}
static void omniStcTick(uint32_t now)
{
    if (!omniStcLive || now - omniStcCheckedAt < 1000) return;
    omniStcCheckedAt = now;
    if (omniStcHoldTab) {   // closed, or navigated elsewhere: nothing is held any more
        bool still = false;
        for (auto& t : tabs) if (t.get() == omniStcHoldTab && t->omniLazyURL == omniStcHoldUrl) { still = true; break; }
        if (!still) { omniStcHoldTab = nullptr; omniStcHoldUrl.clear(); }
    }
    omniStcMark.active = omniStcActiveKey();
    omniStcMark.held = omniStcHoldTab ? omniStcHoldUrl : std::string();
    omniStcWriteMarker(false);
}
// omniEverydayShutdown, after the last session save was flushed: a clean exit.
static void omniStcCleanExit()
{
    if (!omniStcLive) return;
    omniStcLive = false;
    unlink(omniData(OSTC::kMarkerFile).c_str());
}

// --- Browser settings > On start ---------------------------------------------------------------------------------------
static void omniStcPickBuild(OmniFxPanel& p)
{
    omniTsLoad(); omniStcLoad();
    if (omniTsList.empty()) {
        OmniFxRow r; r.id = omniStcPickEmpty; r.enabled = false;
        r.label = "No saved sessions"; r.detail = "Tabs > Save these tabs as a session";
        p.rows.push_back(r);
    }
    const time_t now = time(nullptr);
    for (size_t i = 0; i < omniTsList.size(); ++i) {
        const OmniTabSessions::Session& s = omniTsList[i];
        OmniFxRow r; r.id = omniStcPickFirst + int(i);
        r.label = s.name; r.detail = OmniTabSessions::sitesText(s, 48); r.value = OmniTabSessions::listValue(s, now);
        if (omniStcSet.choice == OSTC::kSavedSession && OmniTabSessions::sameName(s.name, omniStcSet.session)) r.icon = omniIconCheck;
        p.rows.push_back(r);
    }
}
static bool omniStcPickInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    const int i = r.id - omniStcPickFirst;
    if (r.id < omniStcPickFirst || i >= int(omniTsList.size())) return true;
    omniStcSet.choice = OSTC::kSavedSession; omniStcSet.session = omniTsList[size_t(i)].name;
    omniStcSave();
    notice(OSTC::pickedNotice(omniStcSet.session));
    omniFxPop();
    return true;
}
static void omniStcPickShow()
{
    omniTsLoad();
    OmniFxPanel p;
    p.title = "On start: open a saved session"; p.subtitle = "Private tabs are never saved";
    p.w = 980; p.maxVisible = 8;
    p.build = omniStcPickBuild; p.input = omniStcPickInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    const int at = OmniTabSessions::find(omniTsList, omniStcSet.session);
    if (at > 0) p.sel = at;
    omniFxPush(std::move(p));
}
static void omniStcSettingsRow(OmniFxPanel& p)
{
    omniStcLoad(); omniTsLoad();
    OmniFxRow r; r.id = omniStcRowId; r.label = OSTC::rowLabel(); r.stepper = true;
    r.value = OSTC::valueText(omniStcSet, OmniTabSessions::find(omniTsList, omniStcSet.session) >= 0, omniWebURL(omniFxSet.home));
    p.rows.push_back(r);
}
static bool omniStcSettingsInput(int b)
{
    omniStcLoad(); omniTsLoad();
    if (b == SDL_CONTROLLER_BUTTON_Y) {
        if (omniStcSet.choice == OSTC::kDefault) return true;
        omniStcSet.choice = OSTC::kDefault; omniStcSave(); notice(OSTC::choiceNotice(omniStcSet));
        return true;
    }
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    if (a && omniStcSet.choice == OSTC::kSavedSession) { omniStcPickShow(); return true; }
    const int dir = left ? -1 : (right || a) ? 1 : 0;
    if (!dir) return false;
    omniStcSet.choice = OSTC::step(omniStcSet.choice, dir, !omniTsList.empty());
    if (omniStcSet.choice == OSTC::kSavedSession && OmniTabSessions::find(omniTsList, omniStcSet.session) < 0) omniStcSet.session = omniTsList.empty() ? std::string() : omniTsList[0].name;
    omniStcSave();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniPlaybackSpeed.h" // OMNI_PLAYBACK_SPEED_V1: playback speed steps, memory, script (pure)\n',
         '#include "OmniPlaybackSpeed.h" // OMNI_PLAYBACK_SPEED_V1: playback speed steps, memory, script (pure)\n'
         '#include "OmniStartupChoice.h" // OMNI_STARTUP_CHOICE_V1: On start choice, running.txt crash marker (pure)\n'),
        ('    if (!tab || tab->omniLazyURL.empty()) return;\n',
         '    if (!tab || tab->omniLazyURL.empty()) return;\n'
         '    if (omniStcHeld(*tab)) return; // OMNI_STARTUP_CHOICE_V1: a page that may have crashed Omni stays unloaded\n'),
        ('    if (saved.empty()) saved.emplace_back("newtab", "New tab");\n',
         '    omniStcBegin(saved, sel); // OMNI_STARTUP_CHOICE_V1: On start choice, crash marker (may replace `saved`)\n'
         '    if (saved.empty()) saved.emplace_back("newtab", "New tab");\n'),
        ('    if (saved.size() > 1 || saved[0].first != "newtab") notice("Restored " + std::to_string(tabs.size()) + (tabs.size() == 1 ? " tab" : " tabs") + " from last time"); // OMNI_FEATURES_V3_FIX1: what actually opened\n',
         '    if (saved.size() > 1 || saved[0].first != "newtab") notice("Restored " + std::to_string(tabs.size()) + (tabs.size() == 1 ? " tab" : " tabs") + " from last time"); // OMNI_FEATURES_V3_FIX1: what actually opened\n'
         '    omniStcStarted(); // OMNI_STARTUP_CHOICE_V1: running.txt written; "Restore your N tabs?" / held page prompt\n'),
        ('    omniSessionSave();\n    omniIoFlush();\n}\n',
         '    omniSessionSave();\n    omniIoFlush();\n'
         '    omniStcCleanExit(); // OMNI_STARTUP_CHOICE_V1: clean exit: running.txt removed\n}\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static bool omniTmSkipRestore = false, omniF3Restoring = false;\n',
         'static bool omniTmSkipRestore = false, omniF3Restoring = false;\n'
         '// OMNI_STARTUP_CHOICE_V1 (OmniStartupChoiceShell.h): On start choice + crash marker\n'
         'static void omniStcBegin(std::vector<std::pair<std::string, std::string>>& saved, int& sel);   // omniEverydayStart, before the tabs\n'
         'static void omniStcStarted();                            // omniEverydayStart, after the restore\n'
         'static bool omniStcHeld(Tab& tab);                       // omniEverydayActivated: true = stays unloaded\n'
         'static void omniStcCleanExit();                          // omniEverydayShutdown\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static void omniPfSettingsRow(OmniFxPanel& p);\nstatic bool omniPfSettingsInput(int b);\n',
         'static void omniPfSettingsRow(OmniFxPanel& p);\nstatic bool omniPfSettingsInput(int b);\n'
         'constexpr int omniStcRowId = %d; // OMNI_STARTUP_CHOICE_V1: "On start" (OmniStartupChoiceShell.h)\n'
         'static void omniStcSettingsRow(OmniFxPanel& p);\n'
         'static bool omniStcSettingsInput(int b);\n' % ROW_ID),
        ('    add(omniFxSetHome, "Home page", omniFxSet.home.empty() ? std::string("New-tab page") : omniShownURL(omniFxSet.home), false);\n',
         '    add(omniFxSetHome, "Home page", omniFxSet.home.empty() ? std::string("New-tab page") : omniShownURL(omniFxSet.home), false);\n'
         '    omniStcSettingsRow(p); // OMNI_STARTUP_CHOICE_V1: On start\n'),
        ('    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n',
         '    if (r.id == omniStcRowId) return omniStcSettingsInput(b); // OMNI_STARTUP_CHOICE_V1\n'
         '    if (r.id == omniPfRowId) return omniPfSettingsInput(b); // OMNI_PAD_FEEDBACK_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniPadFeedbackShell.h" // OMNI_PAD_FEEDBACK_V1\n',
         '#include "OmniPadFeedbackShell.h" // OMNI_PAD_FEEDBACK_V1\n'
         '#include "OmniStartupChoiceShell.h" // OMNI_STARTUP_CHOICE_V1\n'),
        ('    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n',
         '    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n'
         '    omniStcTick(now);   // OMNI_STARTUP_CHOICE_V1: running.txt follows the shown tab (on a change, every second)\n'),
    ],
}

# Names this patch defines: refused when the tree already has them (another patch took them).
OWN_NAMES = ('OmniStartupChoice', 'omniStc', 'namespace OSTC', 'OSTC::', 'running.txt', 'startup.txt')


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def read(name):
    return (root / name).read_bytes().decode('utf-8')


def check(name, edits):
    s = read(name)
    if MARK in s:
        return
    code = cpp_code(s)
    for n in OWN_NAMES:
        if n in code:
            sys.exit('%s: %r already used by another patch: refusing' % (name, n))
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
    if name == 'OmniBrowserSettings.h':
        import re
        if re.search(r'=\s*%d\s*[;,]' % ROW_ID, code):
            sys.exit('%s: row id %d already taken' % (name, ROW_ID))


def patch(name, edits):
    p = root / name
    s = read(name)
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
    need = {'OmniFeatures3.h': ('OMNI_PAD_FEEDBACK_V1', 'OMNI_OFFLINE_RETRY_V1', 'OmniTabSessionsShell.h', 'OmniPinnedTabsShell.h', 'OmniTabGroupsShell.h'),
            'OmniBrowser.cpp': ('OMNI_PLAYBACK_SPEED_V1', 'OMNI_EVERYDAY_V1')}
    for name, marks in need.items():
        s = read(name)
        for m in marks:
            if m not in s:
                sys.exit('%s: %s missing: apply its patch first' % (name, m))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniStartupChoice.h', PURE, 'OmniTabSessions.h'),
            write_new('OmniStartupChoiceShell.h', SHELL, 'OmniTabSessionsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
