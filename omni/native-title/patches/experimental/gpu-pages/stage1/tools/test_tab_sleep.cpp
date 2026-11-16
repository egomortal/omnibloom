// OMNI_TAB_SLEEP_V1: host tests of OmniTabSleep.h (eligibility, order, rate limit, settings, texts).
//   g++ -std=c++20 -Wall -Wextra -I<tools> test_tab_sleep.cpp -o t && ./t
#include "OmniTabSleep.h"
#include <cstdio>
#include <cstring>

namespace OTSP = OmniTabSleep;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static OTSP::Cand idleTab(uint32_t idleSince)
{
    OTSP::Cand c; c.free = true; c.idleSince = idleSince; return c;
}

int main()
{
    const uint32_t MIN = 60000;
    OTSP::Settings s;   // defaults: 30 min, pinned excluded
    CHECK(s.minutes == 30 && !s.pinned);
    const uint32_t now = 100 * MIN;

    // --- eligibility ---------------------------------------------------------------------------------------------
    OTSP::Cand c = idleTab(now - 31 * MIN);
    CHECK(OTSP::decide(c, now, s, false) == OTSP::kProbe);
    c.verdict = OTSP::kClean; CHECK(OTSP::decide(c, now, s, false) == OTSP::kSleep);
    c.verdict = OTSP::kDirty; CHECK(OTSP::decide(c, now, s, false) == OTSP::kUnsaved);
    c.verdict = OTSP::kProbing; CHECK(OTSP::decide(c, now, s, false) == OTSP::kWaiting);
    c.verdict = OTSP::kClean;
    CHECK(OTSP::decide(c, now, s, true) == OTSP::kDownloads);                       // a download / hand-over: wait
    { OTSP::Cand d = c; d.idleSince = now - 29 * MIN; CHECK(OTSP::decide(d, now, s, false) == OTSP::kRecent); }
    { OTSP::Cand d = c; d.idleSince = now - 30 * MIN; CHECK(OTSP::decide(d, now, s, false) == OTSP::kSleep); }   // exactly N min
    { OTSP::Cand d = c; d.free = false; CHECK(OTSP::decide(d, now, s, false) == OTSP::kNotFree); }   // active / playing / loading ...
    { OTSP::Cand d = c; d.sound = true; CHECK(OTSP::decide(d, now, s, false) == OTSP::kSound); }     // background audio
    { OTSP::Cand d = c; d.priv = true; CHECK(OTSP::decide(d, now, s, false) == OTSP::kPrivate); }
    { OTSP::Cand d = c; d.kept = true; CHECK(OTSP::decide(d, now, s, false) == OTSP::kKept); }
    { OTSP::Cand d = c; d.kept = true; d.pinned = true; OTSP::Settings p = s; p.pinned = true;
      CHECK(OTSP::decide(d, now, p, false) == OTSP::kKept); }                                       // kept beats "include pinned"
    { OTSP::Cand d = c; d.pinned = true; CHECK(OTSP::decide(d, now, s, false) == OTSP::kPinned);
      OTSP::Settings p = s; p.pinned = true; CHECK(OTSP::decide(d, now, p, false) == OTSP::kSleep); }
    { OTSP::Settings off = s; off.minutes = 0; CHECK(OTSP::decide(c, now, off, false) == OTSP::kOff); }
    { OTSP::Settings ten = s; ten.minutes = 10; OTSP::Cand d = c; d.idleSince = now - 11 * MIN; CHECK(OTSP::decide(d, now, ten, false) == OTSP::kSleep); }
    { OTSP::Settings h = s; h.minutes = 60; OTSP::Cand d = c; d.idleSince = now - 59 * MIN; CHECK(OTSP::decide(d, now, h, false) == OTSP::kRecent); }
    // wrap-safe idle time across the 49-day SDL_GetTicks wrap
    { OTSP::Cand d = c; d.idleSince = 0xFFFFFFFFu - 10 * MIN; CHECK(OTSP::decide(d, 21 * MIN, s, false) == OTSP::kSleep);
      d.idleSince = 0xFFFFFFFFu - 5 * MIN; CHECK(OTSP::decide(d, 20 * MIN, s, false) == OTSP::kRecent); }

    // --- order and the per-check cap ------------------------------------------------------------------------------
    {
        std::vector<OTSP::Cand> t(6);
        t[0] = idleTab(now - 40 * MIN);                        // plain, idle 40
        t[1] = idleTab(now - 90 * MIN); t[1].pinned = true;    // pinned, idle 90 (excluded by default)
        t[2] = idleTab(now - 35 * MIN); t[2].collapsed = true; // collapsed group: first
        t[3] = idleTab(now - 80 * MIN);                        // plain, idle 80: before t[0]
        t[4] = idleTab(now - 5 * MIN);                         // recent
        t[5] = idleTab(now - 99 * MIN); t[5].free = false;     // the shown tab / playing
        std::vector<int> go = OTSP::pick(t, now, s, false);
        CHECK(go.size() == 2 && go[0] == 2 && go[1] == 3);
        go = OTSP::pick(t, now, s, false, 10);
        CHECK(go.size() == 3 && go[0] == 2 && go[1] == 3 && go[2] == 0);
        OTSP::Settings p = s; p.pinned = true;
        go = OTSP::pick(t, now, p, false, 10);
        CHECK(go.size() == 4 && go.back() == 1);               // pinned last even when idle longest
        CHECK(OTSP::pick(t, now, s, true).empty());            // downloads busy: nothing
        OTSP::Settings off = s; off.minutes = 0;
        CHECK(OTSP::pick(t, now, off, false).empty());
        t[2].verdict = OTSP::kDirty; t[3].verdict = OTSP::kProbing;
        go = OTSP::pick(t, now, s, false);
        CHECK(go.size() == 1 && go[0] == 0);                   // unsaved / waiting tabs are skipped, not counted
        CHECK(OTSP::pick(t, now, s, false, 0).empty());
    }

    // --- rate limit -------------------------------------------------------------------------------------------------
    {
        uint32_t last = 0; bool primed = false;
        CHECK(!OTSP::checkDue(5000, last, primed) && primed && last == 5000);   // first pass arms only
        CHECK(!OTSP::checkDue(5000 + MIN - 1, last, primed));
        CHECK(OTSP::checkDue(5000 + MIN, last, primed));
        last = 0xFFFFFFFFu - 1000; CHECK(!OTSP::checkDue(1000, last, primed)); CHECK(OTSP::checkDue(MIN, last, primed));
        CHECK(!OTSP::probeTimedOut(1000 + 29999, 1000) && OTSP::probeTimedOut(1000 + 30000, 1000));
        CHECK(OTSP::kMaxPerCheck == 2 && OTSP::kCheckMs == MIN);
    }

    // --- verdicts -----------------------------------------------------------------------------------------------------
    CHECK(OTSP::verdictOf("c", false) == OTSP::kClean);
    CHECK(OTSP::verdictOf("d", false) == OTSP::kDirty);
    CHECK(OTSP::verdictOf("c", true) == OTSP::kDirty);
    CHECK(OTSP::verdictOf("", false) == OTSP::kDirty);

    // --- settings ---------------------------------------------------------------------------------------------------
    CHECK(OTSP::parse("").minutes == 30 && !OTSP::parse("").pinned);
    CHECK(OTSP::parse("minutes\t10\npinned\t1\n").minutes == 10 && OTSP::parse("minutes\t10\npinned\t1\n").pinned);
    CHECK(OTSP::parse("minutes\t0\r\n").minutes == 0);
    CHECK(OTSP::parse("minutes\t45\n").minutes == 30 || OTSP::parse("minutes\t45\n").minutes == 60);
    CHECK(OTSP::parse("minutes\t999\n").minutes == 60);
    CHECK(OTSP::parse("minutes\t-5\n").minutes == 30);          // junk ignored
    CHECK(OTSP::parse("minutes\tabc\nnoise\n").minutes == 30);
    for (int m : { 0, 10, 30, 60 }) for (bool pin : { false, true }) {
        OTSP::Settings x; x.minutes = m; x.pinned = pin;
        const OTSP::Settings y = OTSP::parse(OTSP::serialize(x));
        CHECK(y.minutes == m && y.pinned == pin);
    }
    CHECK(OTSP::stepMinutes(30, 1, false) == 60 && OTSP::stepMinutes(60, 1, false) == 60);
    CHECK(OTSP::stepMinutes(60, 1, true) == 0 && OTSP::stepMinutes(0, 1, true) == 10);
    CHECK(OTSP::stepMinutes(0, -1, false) == 0 && OTSP::stepMinutes(10, -1, false) == 0 && OTSP::stepMinutes(30, -1, false) == 10);

    // --- texts ------------------------------------------------------------------------------------------------------
    CHECK(OTSP::minutesValue(0) == "Off" && OTSP::minutesValue(30) == "After 30 min");
    CHECK(std::strcmp(OTSP::kAsleepValue, "Asleep") == 0);
    CHECK(std::string(OTSP::kUnloadWhy) != "shell memory low" && std::string(OTSP::kUnloadWhy) != "new tab refused");   // never takes "Keep loaded" tabs
    CHECK(OTSP::kRowMinutes >= 300 && OTSP::kRowMinutes < 900 && OTSP::kRowPinned == OTSP::kRowMinutes + 1);
    // the page script: one expression, balanced, returns 'c' / 'd'; no value is read out of the page
    {
        const std::string js = OTSP::kProbeScript;
        int paren = 0, brace = 0;
        for (char ch : js) { paren += ch == '(' ? 1 : ch == ')' ? -1 : 0; brace += ch == '{' ? 1 : ch == '}' ? -1 : 0; }
        CHECK(paren == 0 && brace == 0);
        CHECK(js.rfind("(function(){", 0) == 0 && js.substr(js.size() - 4) == "})()");
        CHECK(js.find("return 'c'") == std::string::npos && js.find("?'d':'c'") != std::string::npos);
        CHECK(js.find("onbeforeunload") != std::string::npos && js.find("defaultValue") != std::string::npos);
        CHECK(js.find("postMessage") == std::string::npos && js.find("fetch(") == std::string::npos);
    }

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
