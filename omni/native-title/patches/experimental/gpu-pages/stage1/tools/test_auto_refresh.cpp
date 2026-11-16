// OMNI_AUTO_REFRESH_V1: host tests of OmniAutoRefresh.h (intervals, site store, timer, countdown, skip rules, scripts,
// chip layout).   g++ -std=c++20 -Wall -Wextra -I<tools> test_auto_refresh.cpp -o t && ./t [probe.js]
// With an argument the composed probe script is written there (node can check that it parses / runs).
#include "OmniAutoRefresh.h"
#include "OmniTabSleep.h"
#include <cstdio>
#include <cstring>

namespace OARF = OmniAutoRefresh;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static OARF::Facts goodTab()
{
    OARF::Facts f; f.web = true; f.shown = false; return f;
}

int main(int argc, char** argv)
{
    // --- intervals / texts ----------------------------------------------------------------------------------------
    CHECK(OARF::kStepCount == 6);
    const int want[] = { 0, 30, 60, 300, 900, 1800 };
    for (int i = 0; i < 6; ++i) CHECK(OARF::steps()[i] == want[i]);
    CHECK(OARF::validSeconds(300) && !OARF::validSeconds(120) && !OARF::validSeconds(-30));
    CHECK(OARF::choiceLabel(0) == "Off" && OARF::choiceLabel(30) == "30 s" && OARF::choiceLabel(60) == "1 min");
    CHECK(OARF::choiceLabel(1800) == "30 min" && OARF::rowValue(900) == "Every 15 min" && OARF::rowValue(0) == "Off");
    CHECK(OARF::setNotice(0) == "Auto-refresh off");
    CHECK(OARF::siteNotice("example.com", 300) == "Always for example.com: every 5 min");

    // --- site key -----------------------------------------------------------------------------------------------
    CHECK(OARF::siteKey("https://www.Example.COM/scores?x=1") == "example.com");
    CHECK(OARF::siteKey("http://example.com:8080/a") == "example.com");
    CHECK(OARF::siteKey("https://user:pw@status.example.org./") == "status.example.org");
    CHECK(OARF::siteKey("https://[::1]:8443/x") == "[::1]");
    CHECK(OARF::siteKey("omni://pages/start").empty() && OARF::siteKey("about:blank").empty() && OARF::siteKey("file:///a").empty());
    CHECK(OARF::siteKey("https://www./") == "www");      // "www." alone: no empty key
    CHECK(OARF::siteKey("https://a\tb/").empty());

    // --- site store ------------------------------------------------------------------------------------------------
    OARF::Sites s;
    CHECK(s.set("example.com", 300) && s.get("example.com") == 300);
    CHECK(!s.set("example.com", 300));                 // unchanged
    CHECK(!s.set("example.com", 120));                 // not a step
    CHECK(s.set("b.org", 30) && s.set("example.com", 60));
    CHECK(s.list.back().first == "example.com");       // changed: newest
    CHECK(OARF::serialize(s) == "b.org\t30\nexample.com\t60\n");
    CHECK(s.set("b.org", 0) && s.get("b.org") == 0 && !s.set("b.org", 0));
    {
        OARF::Sites p = OARF::parseSites("a.com\t30\r\nWWW.B.com\t60\nc.com\t45\nd.com\tx\n\t30\ne.com\t1800\nf.com\t0\ng.com\t300\ng.com\t900\n");
        CHECK(p.get("a.com") == 30 && p.get("e.com") == 1800 && p.get("g.com") == 900);
        CHECK(p.get("WWW.B.com") == 0 && p.get("b.com") == 0);   // not a key siteKey makes: dropped
        CHECK(p.get("c.com") == 0 && p.get("d.com") == 0 && p.get("f.com") == 0);
        CHECK(OARF::parseSites(OARF::serialize(p)).list == p.list);
    }
    {
        OARF::Sites big;
        for (int i = 0; i < 230; ++i) big.set("s" + std::to_string(i) + ".com", 60);
        CHECK(big.list.size() == OARF::kMaxSites && big.get("s0.com") == 0 && big.get("s229.com") == 60);
    }

    // --- timer / countdown (wrap-safe) -------------------------------------------------------------------------------
    OARF::Timer t;
    CHECK(!t.on() && !t.isDue(123) && t.remainingMs(5) == 0);
    t.set(300, 1000);
    CHECK(t.on() && t.due == 301000 && !t.isDue(300999) && t.isDue(301000) && t.remainingMs(1000) == 300000);
    CHECK(OARF::countdown(t.remainingMs(1000)) == "5:00");
    CHECK(OARF::countdown(252000) == "4:12" && OARF::countdown(251001) == "4:12" && OARF::countdown(30000) == "0:30");
    CHECK(OARF::countdown(1) == "0:01" && OARF::countdown(0) == "0:00" && OARF::countdown(1800000) == "30:00");
    t.set(120, 1000); CHECK(!t.on());                   // not a step: off
    t.set(30, 0xFFFFF000u);                             // across the 32-bit wrap
    CHECK(!t.isDue(0xFFFFFFFFu) && !t.isDue(20000) && t.isDue(0xFFFFF000u + 30000u) && t.remainingMs(0xFFFFF000u) == 30000);
    t.restart(5000); CHECK(t.due == 35000);

    // --- skip rules ------------------------------------------------------------------------------------------------
    CHECK(OARF::decide(goodTab()) == OARF::kGo);
    { auto f = goodTab(); f.web = false; CHECK(OARF::decide(f) == OARF::kNever); }        // omni:// etc.
    { auto f = goodTab(); f.reader = true; CHECK(OARF::decide(f) == OARF::kNever); }
    { auto f = goodTab(); f.mediaApp = true; CHECK(OARF::decide(f) == OARF::kNever); }
    { auto f = goodTab(); f.asleep = true; f.loading = true; CHECK(OARF::decide(f) == OARF::kAsleep); }   // never woken
    { auto f = goodTab(); f.loading = true; CHECK(OARF::decide(f) == OARF::kLoading); }
    { auto f = goodTab(); f.crashed = true; CHECK(OARF::decide(f) == OARF::kCrashed); }
    { auto f = goodTab(); f.post = true; CHECK(OARF::decide(f) == OARF::kPost); }
    { auto f = goodTab(); f.offline = true; CHECK(OARF::decide(f) == OARF::kOffline); }
    { auto f = goodTab(); f.media = true; CHECK(OARF::decide(f) == OARF::kMedia); }
    { auto f = goodTab(); f.typing = true; CHECK(OARF::decide(f) == OARF::kGo); }                // background tab: typing elsewhere
    { auto f = goodTab(); f.shown = true; f.typing = true; CHECK(OARF::decide(f) == OARF::kTyping); }
    { auto f = goodTab(); f.shown = true; f.sinceInputMs = 19999; CHECK(OARF::decide(f) == OARF::kRecentInput); }
    { auto f = goodTab(); f.shown = true; f.sinceInputMs = 20000; CHECK(OARF::decide(f) == OARF::kGo); }
    { auto f = goodTab(); f.sinceInputMs = 5; CHECK(OARF::decide(f) == OARF::kGo); }             // background: input irrelevant
    for (int r = OARF::kGo; r <= OARF::kNoAnswer; ++r) CHECK(std::strcmp(OARF::reasonText(OARF::Reason(r)), "?") != 0);
    { OARF::Timer on; on.set(60, 0); auto f = goodTab(); CHECK(OARF::chipShown(on, f)); f.web = false; CHECK(!OARF::chipShown(on, f));
      f = goodTab(); f.media = true; CHECK(OARF::chipShown(on, f)); CHECK(!OARF::chipShown(OARF::Timer(), goodTab())); }

    // --- probe answer / scripts ----------------------------------------------------------------------------------------
    { auto a = OARF::parseAnswer("c,0,3400", false); CHECK(a.ok && a.clean && a.x == 0 && a.y == 3400); }
    { auto a = OARF::parseAnswer("d,12,40", false); CHECK(a.ok && !a.clean && a.x == 12); }
    { auto a = OARF::parseAnswer("c,-3,-9", false); CHECK(a.ok && a.clean && a.x == 0 && a.y == 0); }
    CHECK(!OARF::parseAnswer("c,0,3400", true).ok && !OARF::parseAnswer("c", false).ok && !OARF::parseAnswer("", false).ok);
    CHECK(!OARF::parseAnswer("cc,1,2", false).ok && !OARF::parseAnswer("c,1,x", false).ok && !OARF::parseAnswer("x,1,2", false).ok);
    CHECK(!OARF::parseAnswer("c,1,", false).clean && !OARF::parseAnswer("c,1,2,3", false).ok);
    CHECK(!OARF::wantsRestore(0) && !OARF::wantsRestore(40) && OARF::wantsRestore(41));
    const std::string js = OARF::probeScript(OmniTabSleep::kProbeScript);
    CHECK(js.find(OmniTabSleep::kProbeScript) != std::string::npos);
    CHECK(js.rfind("(function(){", 0) == 0 && js.size() > 4 && js.compare(js.size() - 4, 4, "})()") == 0);   // never trimmed
    CHECK(OARF::restoreScript(5, 3400).find("})(5,3400)") != std::string::npos && OARF::restoreScript(-1, -2).find("})(0,0)") != std::string::npos);
    if (argc > 1) {
        if (FILE* f = std::fopen(argv[1], "w")) {
            std::fprintf(f, "%s\n%s\n", js.c_str(), OARF::restoreScript(0, 100).c_str());
            std::fclose(f);
        }
    }

    // --- chip layout ---------------------------------------------------------------------------------------------------
    { auto c = OARF::chipLayout(1155.f, 30.f); CHECK(c.mode == 2 && c.w == 16.f + 3.f + 30.f && c.textMax == int(1276.f - 1155.f - 19.f)); }
    { auto c = OARF::chipLayout(1250.f, 30.f); CHECK(c.mode == 1 && c.w == 16.f); }
    { auto c = OARF::chipLayout(1265.f, 30.f); CHECK(c.mode == 0); }

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
