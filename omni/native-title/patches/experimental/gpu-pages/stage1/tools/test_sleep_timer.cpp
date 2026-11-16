// OMNI_SLEEP_TIMER_V1: tests of the pure part (OmniSleepTimer.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_sleep_timer.cpp -o t && ./t [fade.js]
// With an argument, writes fadeScript(0.5) and restoreScript() to that file (one per line) for a node syntax check.
#include "OmniSleepTimer.h"
#include <cmath>
#include <cstdio>
#include <fstream>

namespace ST = OmniSleepTimer;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static ST::Probe probe(int state, double pos, double dur, const char* src = "blob:a")
{
    ST::Probe p; p.ok = true; p.state = state; p.pos = pos; p.dur = dur; p.src = src; return p;
}

int main(int argc, char** argv)
{
    // fade curve
    CHECK(ST::fadeFactor(-1) == 1.0);
    CHECK(std::fabs(ST::fadeFactor(0) - 0.81) < 1e-9);
    CHECK(std::fabs(ST::fadeFactor(4) - 0.25) < 1e-9);
    CHECK(ST::fadeFactor(9) == 0.0 && ST::fadeFactor(20) == 0.0);
    for (int s = 0; s < ST::kFadeSteps - 1; ++s) CHECK(ST::fadeFactor(s + 1) < ST::fadeFactor(s));

    // labels
    CHECK(ST::choiceLabel(45) == "45 minutes");
    CHECK(ST::choiceLabel(ST::kEndOfVideo) == "At end of this video");
    CHECK(ST::choiceLabel(0) == "Off");
    CHECK(ST::startNotice(90) == "Sleep timer: playback stops in 90 min");
    CHECK(ST::startNotice(0) == "Sleep timer off");
    CHECK(ST::firedNotice() == "Sleep timer: playback stopped");

    // counting, warn, fade, fire (near the uint32 wrap)
    {
        ST::Timer t;
        const uint32_t t0 = 0xFFFFFFFFu - 5000u;
        CHECK(!t.startMinutes(20, t0) && !t.on());   // not a choice
        CHECK(t.startMinutes(45, t0) && t.on() && t.phase() == ST::Phase::Counting);
        CHECK(t.value(t0) == "45 min left" && t.badge(t0) == "zZ 45 min");
        ST::Step s = t.tick(t0);
        CHECK(s.event == ST::Event::None && s.redraw);
        CHECK(!t.tick(t0 + 1000).redraw);
        const uint32_t end = t0 + 45u * 60000u;
        CHECK(t.badge(end - 22u * 60000u - 1u) == "zZ 23 min");
        CHECK(t.tick(end - 22u * 60000u - 1u).redraw);
        CHECK(t.tick(end - 61000u).event == ST::Event::None);
        CHECK(t.tick(end - 60000u).event == ST::Event::Warn);
        CHECK(t.tick(end - 59000u).event == ST::Event::None);   // once
        CHECK(t.badge(end - 1u) == "zZ 1 min");
        s = t.tick(end);
        CHECK(s.event == ST::Event::Fade && std::fabs(s.factor - 0.81) < 1e-9 && t.phase() == ST::Phase::Fading);
        CHECK(t.badge(end) == "zZ ..." && t.value(end) == "Stopping...");
        CHECK(t.tick(end + 500).event == ST::Event::None);   // one script per second at most
        int fades = 1;
        double last = 0.81;
        for (uint32_t ms = end + 100; ms < end + 9999; ms += 100) {
            s = t.tick(ms);
            if (s.event == ST::Event::Fade) { ++fades; CHECK(s.factor < last); last = s.factor; }
            CHECK(s.event != ST::Event::Fire);
        }
        CHECK(fades == 10 && last == 0.0);
        s = t.tick(end + 10000);
        CHECK(s.event == ST::Event::Fire && !t.on() && s.redraw);
        CHECK(t.tick(end + 11000).event == ST::Event::None && t.value(end) == "Off" && t.badge(end).empty());
    }
    // a 15 min timer warns; switching choice restarts; off
    {
        ST::Timer t;
        t.startMinutes(15, 1000);
        t.startMinutes(30, 2000);
        CHECK(t.minutes() == 30 && t.minutesLeft(2000) == 30);
        t.off();
        CHECK(!t.on() && t.tick(99999999).event == ST::Event::None);
    }

    // end of video: probe cadence, answers
    {
        ST::Timer t;
        t.startEndOfVideo(77, 1000);
        CHECK(t.tab() == 77 && t.value(1000) == "End of video" && t.badge(1000) == "zZ end of video");
        CHECK(t.tick(1000).event == ST::Event::Probe && t.probeOut());
        CHECK(t.tick(1500).event == ST::Event::None);   // one probe out at a time
        CHECK(t.answer(probe(1, 10, 600), 1600) == ST::Verdict::Keep && !t.probeOut());
        CHECK(t.watchedSrc() == "blob:a");
        CHECK(t.tick(6599).event == ST::Event::None);
        CHECK(t.tick(6600).event == ST::Event::Probe);   // 5 s later
        CHECK(t.answer(probe(1, 597, 600), 6700) == ST::Verdict::Keep);
        CHECK(t.tick(9699).event == ST::Event::None);
        CHECK(t.tick(10200).event == ST::Event::Probe);   // sooner: 3 s left + 0.5 s
        CHECK(t.answer(probe(2, 599.5, 600), 10300) == ST::Verdict::Ended && !t.on());
    }
    {   // the next video began (autoplay): another src
        ST::Timer t; t.startEndOfVideo(1, 0); t.tick(0);
        t.answer(probe(1, 100, 600, "blob:a"), 10);
        t.tick(5010);
        CHECK(t.answer(probe(1, 2, 300, "blob:b"), 5020) == ST::Verdict::Ended);
    }
    {   // same src (MSE), new duration
        ST::Timer t; t.startEndOfVideo(1, 0); t.tick(0);
        t.answer(probe(1, 100, 600), 10);
        t.tick(5010);
        CHECK(t.answer(probe(1, 2, 240), 5020) == ST::Verdict::Ended);
    }
    {   // live stream: 60 min instead
        ST::Timer t; t.startEndOfVideo(1, 0); t.tick(0);
        CHECK(t.answer(probe(1, 100, ST::kLive), 10) == ST::Verdict::Live);
        CHECK(t.phase() == ST::Phase::Counting && t.minutes() == 60);
    }
    {   // no media twice
        ST::Timer t; t.startEndOfVideo(1, 0); t.tick(0);
        CHECK(t.answer(probe(0, -1, -1, ""), 10) == ST::Verdict::Keep);
        t.tick(5010);
        CHECK(t.answer(probe(0, -1, -1, ""), 5020) == ST::Verdict::Ended);
    }
    {   // no answers: three timeouts fire
        ST::Timer t; t.startEndOfVideo(1, 0);
        uint32_t now = 0; int probes = 0; bool fired = false;
        for (; now < 60000 && !fired; now += 100) {
            const ST::Step s = t.tick(now);
            if (s.event == ST::Event::Probe) ++probes;
            if (s.event == ST::Event::Fire) fired = true;
        }
        CHECK(fired && probes == 3 && !t.on());
    }
    {   // a stale answer (no probe out) is ignored; a paused video in the middle keeps watching
        ST::Timer t; t.startEndOfVideo(1, 0);
        CHECK(t.answer(probe(2, 600, 600), 0) == ST::Verdict::Keep && t.on());
        t.tick(0);
        CHECK(t.answer(probe(2, 30, 600), 10) == ST::Verdict::Keep && t.on());
    }

    // the page script
    {
        const std::string f = ST::fadeScript(0.5), r = ST::restoreScript();
        CHECK(f.find("})(0.500)") != std::string::npos);
        CHECK(r.find("})(-1)") != std::string::npos);
        CHECK(ST::fadeScript(7).find("})(1.000)") != std::string::npos);
        if (argc > 1) { std::ofstream o(argv[1]); o << f << ";\n" << r << ";\n"; }
    }
    std::printf("%d/%d checks passed\n", checks - failures, checks);
    return failures ? 1 : 0;
}
