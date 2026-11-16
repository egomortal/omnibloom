#!/usr/bin/env python3
"""OMNI_HISTORY_KEEP_V1 (2026-11-16): automatic history retention.

What the user sees
  Browser settings > "Keep history"   < Forever | 3 months | 1 month | 1 week | 1 day | Don't save history >
      D-pad left / right steps (stops at both ends, so "Don't save history" is never reached by wrapping);
      Cross steps forward and wraps from "Don't save history" back to "Forever". Default Forever (no change from
      older builds). The row's small text says what the choice does, with the count when history is loaded:
          Forever       "Visits stay until you delete them"
          1 week        "Visits older than 1 week are deleted automatically (312 now)"
          Don't save    "New visits aren't saved. Cookies and site data are still kept"
      Stepping onto a time limit deletes nothing at once: the first prune runs 30 s after the LAST change
      (kChangeDelayMs), so D-padding past "1 day" on the way back to "Forever" loses nothing.
      Choosing "Don't save history" with visits saved asks once (Cancel focused, as every omniAsk):
          "Clear saved history too?"  "New visits won't be saved from now on. The 312 visits already saved stay
           until you clear them. Cookies, site data and open tabs are not affected."   [Clear history]
      The row is found by Search settings under Privacy ("history" is a Privacy phrase in OmniSettingsSearch.h).

How
  Setting: /data/omni/history-keep.txt, one token line ("forever" / "3m" / "1m" / "1w" / "1d" / "off"), written
  through omniIoQueue (full rewrite); read once, on first use (<= 256 bytes). Missing / unknown: Forever.
  Retention is by visit time: history.txt keeps "<unix time>\t<url>\t<title>\n" per visit, oldest first (a reload
  moves the last visit's time to the reload). 3 months = 90 days, 1 month = 30 days.
  Prune: at startup (the first omniF3Tick pass) and every hour while running (kPruneEveryMs), plus 30 s after a
  change of the setting. Each prune:
    - history not loaded yet (the usual startup case): nothing on the main thread but queueing one job; the
      writer thread (omniIoMain) reads history.txt, drops the lines older than the cutoff and rewrites it
      (.tmp + rename, like every other full write). The loader also drops them (omniHkLoaded at the end of
      omniHistoryLoad), so a load racing the job never shows them.
    - history loaded: the in-memory list is filtered (at most ~2200 entries, the existing omniHistoryMax cap) and
      the same file job is queued instead of omniHistoryRewrite(), so the serialization and the write stay on the
      writer thread; the History panel / suggestions / most-visited caches are refreshed like omniHpChanged does.
    The writer runs jobs in order, so appends queued before the prune are filtered with the rest; a full rewrite
    queued after it replaces it (omniIoQueue drops queued jobs of the same path) and carries the already filtered
    in-memory list.
  "Don't save history": omniHistoryAdd returns before doing anything (no new visit, no reload time update) -- like
  a private tab, for history only: cookies, site data, cache, session restore, Continue watching, tab back/forward
  lists are unchanged. Saved visits are not pruned in that mode (they stay until cleared).
  What derives from history and follows automatically: the History panel (OMNI_HISTORY_PLUS_V1), address
  suggestions and the start page's most-visited sites (omniSuggestFor / omniStSitesStale reset), and Clear
  browsing data's per-site cookie range (OMNI_CLEAR_RANGE_V1 picks sites from history, so after a prune it sees only
  sites visited inside the kept window -- correct: nothing older is in the range anyway). Tab search's "Reopen" rows
  come from omniFxClosed, not history, and are untouched.
  Reuse: the time filter is OmniClearRange's (OCLR::countSince counts the visits a prune keeps, the drop count is
  the rest); history.txt lines are parsed with OmniHistoryPlus's parseLine (the loader's rules). The erase itself
  keeps the opposite side of OCLR::eraseSince (which drops visits >= a start), so it is a 4-line eraseBefore here.

Pure part: engine/entry/OmniHistoryKeep.h (no SDL / WebKit): choices, tokens, cutoffs, prune plan, file-text prune,
row / notice / question texts, the tick schedule.
Tested by tools/test_history_keep.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_history_keep.cpp -o t && ./t
Shell side: engine/entry/OmniHistoryKeepShell.h, included from OmniBrowser.cpp after OmniClearRangeShell.h.
Row id 897 in Browser settings (unused; 895 is Offline retry, 900+ Features V2).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp        the OmniClearRange.h include line (pure include after it); the OmniIoJob struct line (a
                         `run` member: a job run on the writer thread); "lock.unlock();" + "if (job.append) {" of
                         omniIoMain (run jobs first); the "struct OmniVisit" line (forward declarations before
                         it); the end of omniHistoryLoad (fclose + omniHistoryMax trim + "}": omniHkLoaded() before
                         the brace); the head of omniHistoryAdd (Don't save: return); the OmniClearRangeShell.h
                         include line (shell include after it).
  OmniBrowserSettings.h  the omniOrRowId line (row id + declarations after it); the omniHoSettingsRows call
                         (row after it); the omniOrRowId input line (ours before it, so before the >= 300 rows).
  OmniFeatures3.h        the omniClrTick line of omniF3Tick (omniHkTick after it).
Apply AFTER apply_clear_range.py and apply_https_only.py / apply_offline_retry.py (their lines are anchors).
usage: apply_history_keep.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_HISTORY_KEEP_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_HISTORY_KEEP_V1: the pure part of Browser settings > Keep history (no SDL, no WebKit): the choices, their
// file tokens, cutoffs, the prune plan, pruning history.txt text, row / notice / question texts and the schedule.
// The time filter is OmniClearRange's (countSince); history.txt lines are read with OmniHistoryPlus's parseLine.
// Shell side: OmniHistoryKeepShell.h; reasons: tools/apply_history_keep.py. Tested by test_history_keep.cpp.
#pragma once
#include <climits>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
#include "OmniClearRange.h"
#include "OmniHistoryPlus.h"

namespace OmniHistoryKeep {

constexpr const char* kFile = "history-keep.txt";
constexpr uint32_t kPruneEveryMs = 3600u * 1000u;   // while running
constexpr uint32_t kChangeDelayMs = 30u * 1000u;     // after the last change of the setting
constexpr size_t kMaxFileBytes = 8u << 20;           // a history.txt larger than this is left alone (cap is ~2200 lines)

enum Keep { Forever, Months3, Month1, Week1, Day1, DontSave, KeepCount };
inline Keep clampKeep(int k) { return k >= 0 && k < KeepCount ? Keep(k) : Forever; }
inline const char* name(int k)
{
    static const char* const names[KeepCount] = { "Forever", "3 months", "1 month", "1 week", "1 day", "Don't save history" };
    return names[clampKeep(k)];
}
inline const char* token(int k)
{
    static const char* const tokens[KeepCount] = { "forever", "3m", "1m", "1w", "1d", "off" };
    return tokens[clampKeep(k)];
}
// The first non-empty line of history-keep.txt (spaces, tabs, CR trimmed); anything unknown is Forever.
inline Keep parse(const std::string& text)
{
    size_t i = 0;
    while (i < text.size()) {
        size_t e = text.find('\n', i);
        if (e == std::string::npos) e = text.size();
        size_t b = i, z = e;
        while (b < z && (text[b] == ' ' || text[b] == '\t' || text[b] == '\r')) ++b;
        while (z > b && (text[z - 1] == ' ' || text[z - 1] == '\t' || text[z - 1] == '\r')) --z;
        if (z > b) {
            const std::string t = text.substr(b, z - b);
            for (int k = 0; k < KeepCount; ++k) if (t == token(k)) return Keep(k);
            return Forever;
        }
        i = e + 1;
    }
    return Forever;
}
inline std::string serialize(int k) { return std::string(token(k)) + "\n"; }

inline bool records(int k) { return clampKeep(k) != DontSave; }
inline long long keepSeconds(int k)
{
    switch (clampKeep(k)) {
    case Months3: return 90LL * 86400;
    case Month1: return 30LL * 86400;
    case Week1: return 7LL * 86400;
    case Day1: return 86400;
    default: return 0;   // Forever, Don't save: nothing is pruned
    }
}
inline bool prunes(int k) { return keepSeconds(k) > 0; }
// Visits with time < cutoff go; LLONG_MIN: nothing goes.
inline long long cutoff(int k, long long now) { return prunes(k) ? now - keepSeconds(k) : LLONG_MIN; }

// D-pad: -1 / +1, stopping at both ends; Cross (wrap): +1, from Don't save back to Forever.
inline Keep step(int k, int dir, bool wrap)
{
    const int c = clampKeep(k);
    if (wrap) return Keep((c + 1) % KeepCount);
    const int n = c + (dir < 0 ? -1 : dir > 0 ? 1 : 0);
    return n < 0 ? Forever : n >= KeepCount ? DontSave : Keep(n);
}

// --- the prune -----------------------------------------------------------------------------------------------------
struct Plan { long long cutoff = LLONG_MIN; size_t keep = 0, drop = 0; };
template <class V> Plan plan(const std::vector<V>& h, int k, long long now)
{
    Plan p;
    p.cutoff = cutoff(k, now);
    p.keep = OmniClearRange::countSince(h, p.cutoff);   // the clear-range filter: time >= cutoff stays
    p.drop = h.size() - p.keep;
    return p;
}
// The mirror of OmniClearRange::eraseSince: drops the visits older than the cutoff, order kept.
template <class V> size_t eraseBefore(std::vector<V>& h, long long cut)
{
    if (cut == LLONG_MIN) return 0;
    const size_t before = h.size();
    std::vector<V> kept;
    kept.reserve(h.size());
    for (auto& v : h) if (v.time >= cut) kept.push_back(std::move(v));
    h.swap(kept);
    return before - h.size();
}
// history.txt text with the visits older than the cutoff removed (the writer thread runs this). A line goes only
// when OmniHistoryPlus::parseLine reads it as a visit (the loader's rules) and its time < cutoff; anything else
// (lines the loader skips, a last line without a newline) is kept byte for byte. *dropped: lines removed.
struct LineVisit { long long time = 0; std::string url, title; };
inline std::string pruneText(const std::string& text, long long cut, size_t* dropped = nullptr)
{
    size_t n = 0;
    std::string out;
    if (cut == LLONG_MIN) { if (dropped) *dropped = 0; return text; }
    out.reserve(text.size());
    size_t i = 0;
    while (i < text.size()) {
        size_t e = text.find('\n', i);
        e = e == std::string::npos ? text.size() : e + 1;
        LineVisit v;
        if (OmniHistoryPlus::parseLine(text.substr(i, e - i), v) && v.time < cut) ++n;
        else out.append(text, i, e - i);
        i = e;
    }
    if (dropped) *dropped = n;
    return out;
}

// --- schedule (SDL_GetTicks milliseconds, wrap-safe) ----------------------------------------------------------------
inline bool due(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }

// --- texts ---------------------------------------------------------------------------------------------------------
inline std::string lowerFirst(std::string s) { if (!s.empty() && s[0] >= 'A' && s[0] <= 'Z') s[0] = char(s[0] + 32); return s; }
// The small text under the row. drop: visits now older than the limit (shown when known and > 0).
inline std::string rowDetail(int k, size_t drop, bool known)
{
    const Keep c = clampKeep(k);
    if (c == Forever) return "Visits stay until you delete them";
    if (c == DontSave) return "New visits aren't saved. Cookies and site data are still kept";
    std::string s = std::string("Visits older than ") + name(c) + " are deleted automatically";
    if (known && drop) s += " (" + OmniHistoryPlus::visits(drop) + " now)";
    return s;
}
inline std::string changeNotice(int k)
{
    const Keep c = clampKeep(k);
    if (c == Forever) return "History is kept until you delete it";
    if (c == DontSave) return "History won't be saved (cookies and site data are still kept)";
    return std::string("History older than ") + name(c) + " will be deleted automatically";
}
inline std::string askTitle() { return "Clear saved history too?"; }
inline std::string askBody(size_t visits)
{
    return "New visits won't be saved from now on. The " + OmniHistoryPlus::visits(visits)
        + " already saved stay until you clear them. Cookies, site data and open tabs are not affected.";
}
inline std::string clearedNotice(size_t visits) { return "History cleared: " + OmniHistoryPlus::visits(visits) + " removed"; }

} // namespace OmniHistoryKeep
'''

SHELL = r'''// OMNI_HISTORY_KEEP_V1: Browser settings > Keep history (shell side). Included from OmniBrowser.cpp after
// OmniClearRangeShell.h (inside its anonymous namespace). The pure part is OmniHistoryKeep.h; reasons are in
// tools/apply_history_keep.py. Main thread, except the job omniHkQueuePrune hands to the writer thread.
#pragma once
namespace OHKP = OmniHistoryKeep;
static int omniHkSetting = -1;          // -1: history-keep.txt not read yet
static bool omniHkStarted = false;      // the startup prune was scheduled
static bool omniHkChangePending = false;   // the setting changed: the prune waits kChangeDelayMs after the last change
static uint32_t omniHkNextAt = 0;
static OHKP::Keep omniHkKeep()
{
    if (omniHkSetting < 0) {
        std::string text;
        if (FILE* f = fopen(omniData(OHKP::kFile).c_str(), "r")) {
            char buf[256];
            const size_t n = fread(buf, 1, sizeof(buf), f);
            text.assign(buf, n);
            fclose(f);
        }
        omniHkSetting = OHKP::parse(text);
    }
    return OHKP::clampKeep(omniHkSetting);
}
static bool omniHkOff() { return !OHKP::records(omniHkKeep()); }

// history.txt filtered on the writer thread: queued like any write, so it runs after the writes queued before it;
// a full rewrite queued later drops it (it carries the already filtered list).
static void omniHkQueuePrune(long long cut)
{
    const std::string path = omniData("history.txt");
    {
        std::lock_guard<std::mutex> lock(omniIoLock);
        omniIoJobs.push_back({ path, std::string(), true });
        omniIoJobs.back().run = [path, cut] {
            std::string text;
            bool tooBig = false;
            if (FILE* f = fopen(path.c_str(), "rb")) {
                char buf[16384];
                size_t n;
                while ((n = fread(buf, 1, sizeof(buf), f)) > 0) {
                    text.append(buf, n);
                    if (text.size() > OHKP::kMaxFileBytes) { tooBig = true; break; }
                }
                fclose(f);
            } else return;
            if (tooBig) { fprintf(stderr, "OMNI HISTORY KEEP: history.txt over %zu bytes, not pruned\n", OHKP::kMaxFileBytes); return; }
            size_t dropped = 0;
            const std::string out = OHKP::pruneText(text, cut, &dropped);
            if (!dropped) return;
            const std::string tmp = path + ".tmp";
            bool ok = false;
            if (FILE* f = fopen(tmp.c_str(), "w")) {
                ok = fwrite(out.data(), 1, out.size(), f) == out.size();
                ok = !fclose(f) && ok && !rename(tmp.c_str(), path.c_str());
            }
            fprintf(stderr, "OMNI HISTORY KEEP: history.txt %s, %zu visits older than %lld dropped\n", ok ? "pruned" : "write FAILED", dropped, cut);
        };
        if (!omniIoThread) omniIoThread = new std::thread(omniIoMain);
    }
    omniIoWake.notify_one();
}
// The end of omniHistoryLoad: the loaded list never shows visits past the limit (a prune job may still be queued).
static void omniHkLoaded()
{
    if (omniHkChangePending) return;   // just changed: the tick prunes after the delay
    const long long cut = OHKP::cutoff(omniHkKeep(), time(nullptr));
    if (OHKP::eraseBefore(omniHistory, cut)) omniHkQueuePrune(cut);
}
static void omniHkPrune()
{
    const long long cut = OHKP::cutoff(omniHkKeep(), time(nullptr));
    if (cut == LLONG_MIN) return;
    if (!omniHistoryLoaded) { omniHkQueuePrune(cut); return; }   // the file only; the loader drops the same visits
    const size_t n = OHKP::eraseBefore(omniHistory, cut);
    if (!n) return;
    omniHkQueuePrune(cut);   // instead of omniHistoryRewrite(): the text is built on the writer thread
    ++omniHpGen;             // what omniHpChanged() refreshes: History panel rows, suggestions, most visited
    omniSuggestFor = "\x01"; omniStSitesStale = true;
    omniHpRefresh();
    omniShellDirty = true;
    fprintf(stderr, "OMNI HISTORY KEEP: %zu visits older than %s dropped (%zu kept)\n", n, OHKP::name(omniHkKeep()), omniHistory.size());
}
static void omniHkTick(uint32_t now)   // from omniF3Tick
{
    if (omniTestMode()) return;
    if (!omniHkStarted) { omniHkStarted = true; omniHkNextAt = now; }   // the startup prune: this pass
    if (!OHKP::due(now, omniHkNextAt)) return;
    omniHkChangePending = false;
    omniHkNextAt = now + OHKP::kPruneEveryMs;
    omniHkPrune();
}

// --- Browser settings > Keep history --------------------------------------------------------------------------------
static void omniHkSettingsRow(OmniFxPanel& p)
{
    const OHKP::Keep k = omniHkKeep();
    OmniFxRow r;
    r.id = omniHkRowId; r.label = "Keep history"; r.value = OHKP::name(k); r.stepper = true;
    // The count only when history is already in memory (loading it here would prune before the change delay).
    const bool known = omniHistoryLoaded && OHKP::prunes(k);
    r.detail = OHKP::rowDetail(k, known ? OHKP::plan(omniHistory, k, time(nullptr)).drop : 0, known);
    p.rows.push_back(r);
}
static bool omniHkSettingsInput(int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    if (!left && !right && !a) return false;
    const OHKP::Keep was = omniHkKeep(), k = OHKP::step(was, left ? -1 : 1, a);
    if (k == was) return true;
    omniHkSetting = k;
    omniIoQueue(omniData(OHKP::kFile), OHKP::serialize(k), false);
    omniHkChangePending = true;
    omniHkNextAt = SDL_GetTicks() + OHKP::kChangeDelayMs;
    omniHkStarted = true;
    notice(OHKP::changeNotice(k));
    if (k == OHKP::DontSave) {
        omniHistoryLoad();   // nothing is pruned in this mode
        if (!omniHistory.empty())
            omniAsk(OHKP::askTitle(), OHKP::askBody(omniHistory.size()), "Clear history", [](bool ok) {
                if (!ok || !omniHkOff()) return;
                const size_t n = omniHistory.size();
                omniHistory.clear();
                omniHpChanged();   // an empty rewrite on the writer thread, suggestions, most visited
                notice(OHKP::clearedNotice(n));
                omniFxRefresh();
            });
    }
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniClearRange.h" /* OMNI_CLEAR_RANGE_V1: Clear browsing data by time range and category (pure) */\n',
         '#include "OmniClearRange.h" /* OMNI_CLEAR_RANGE_V1: Clear browsing data by time range and category (pure) */\n'
         '#include "OmniHistoryKeep.h" /* OMNI_HISTORY_KEEP_V1: Keep history for ... / Don\'t save history (pure) */\n'),
        ('struct OmniIoJob { std::string path, data; bool append; };\n',
         'struct OmniIoJob { std::string path, data; bool append; std::function<void()> run = {}; }; /* OMNI_HISTORY_KEEP_V1: run = a job for the writer thread */\n'),
        ('        lock.unlock();\n'
         '        if (job.append) {\n',
         '        lock.unlock();\n'
         '        if (job.run) job.run(); /* OMNI_HISTORY_KEEP_V1: history prune */\n'
         '        else if (job.append) {\n'),
        ('struct OmniVisit { long long time; std::string url, title; };\n',
         'static bool omniHkOff();              /* OMNI_HISTORY_KEEP_V1 (OmniHistoryKeepShell.h): Don\'t save history */\n'
         'static void omniHkLoaded();           /* OMNI_HISTORY_KEEP_V1: end of omniHistoryLoad */\n'
         'static void omniHkTick(uint32_t now); /* OMNI_HISTORY_KEEP_V1: from omniF3Tick */\n'
         'struct OmniVisit { long long time; std::string url, title; };\n'),
        ('    fclose(f);\n'
         '    if (omniHistory.size() > omniHistoryMax) omniHistory.erase(omniHistory.begin(), omniHistory.end() - omniHistoryMax);\n'
         '}\n',
         '    fclose(f);\n'
         '    if (omniHistory.size() > omniHistoryMax) omniHistory.erase(omniHistory.begin(), omniHistory.end() - omniHistoryMax);\n'
         '    omniHkLoaded(); /* OMNI_HISTORY_KEEP_V1: visits past the Keep history limit never show */\n'
         '}\n'),
        ('static void omniHistoryAdd(const std::string& url, const std::string& rawTitle)\n{\n',
         'static void omniHistoryAdd(const std::string& url, const std::string& rawTitle)\n{\n'
         '    if (omniHkOff()) return; /* OMNI_HISTORY_KEEP_V1: Don\'t save history (history only; cookies etc. as before) */\n'),
        ('#include "OmniClearRangeShell.h" /* OMNI_CLEAR_RANGE_V1 */\n',
         '#include "OmniClearRangeShell.h" /* OMNI_CLEAR_RANGE_V1 */\n'
         '#include "OmniHistoryKeepShell.h" /* OMNI_HISTORY_KEEP_V1 */\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniOrRowId = 895; // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h)\n',
         'constexpr int omniOrRowId = 895; // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h)\n'
         'constexpr int omniHkRowId = 897; /* OMNI_HISTORY_KEEP_V1 (OmniHistoryKeepShell.h) */\n'
         'static void omniHkSettingsRow(OmniFxPanel& p);\n'
         'static bool omniHkSettingsInput(int b);\n'),
        ('    omniHoSettingsRows(p); // OMNI_HTTPS_ONLY_V1: HTTPS-only mode, Ask sites not to sell or share my data\n',
         '    omniHoSettingsRows(p); // OMNI_HTTPS_ONLY_V1: HTTPS-only mode, Ask sites not to sell or share my data\n'
         '    omniHkSettingsRow(p); /* OMNI_HISTORY_KEEP_V1: Keep history */\n'),
        ('    if (r.id == omniOrRowId) return omniOrSettingsInput(b); // OMNI_OFFLINE_RETRY_V1 (before the >= 300 rows)\n',
         '    if (r.id == omniHkRowId) return omniHkSettingsInput(b); /* OMNI_HISTORY_KEEP_V1 (before the >= 300 rows) */\n'
         '    if (r.id == omniOrRowId) return omniOrSettingsInput(b); // OMNI_OFFLINE_RETRY_V1 (before the >= 300 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniClrTick(now);   /* OMNI_CLEAR_RANGE_V1: native timeout of Clear browsing data */\n',
         '    omniClrTick(now);   /* OMNI_CLEAR_RANGE_V1: native timeout of Clear browsing data */\n'
         '    omniHkTick(now);    /* OMNI_HISTORY_KEEP_V1: startup + hourly history prune */\n'),
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
    for need, by in (('OmniClearRangeShell.h', 'apply_clear_range.py'), ('OmniHistoryPlus.h', 'apply_history_plus.py'),
                     ('OmniOfflineRetryShell.h', 'apply_offline_retry.py'), ('OmniHttpsOnlyShell.h', 'apply_https_only.py')):
        if not (root / need).exists():
            sys.exit('%s missing: %s first' % (need, by))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniHistoryKeep.h', PURE, 'OmniClearRange.h'),
            write_new('OmniHistoryKeepShell.h', SHELL, 'OmniClearRangeShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
