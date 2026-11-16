// OMNI_PLAYBACK_SPEED_V1: tests of the pure part (OmniPlaybackSpeed.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_playback_speed.cpp -o t && ./t [dir]
// With a directory, writes the scripts there (speed-*.js) for node --check and test_playback_speed.cjs.
#include "OmniPlaybackSpeed.h"
#include <cstdio>
#include <fstream>

namespace OPS = OmniPlaybackSpeed;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

int main(int argc, char** argv)
{
    const std::string x = "\xC3\x97";
    // steps
    CHECK(OPS::kStepCount == 7 && OPS::kSteps[OPS::kNormal] == 1.0);
    CHECK(OPS::indexOf(1) == 2 && OPS::indexOf(0.5) == 0 && OPS::indexOf(2) == 6);
    CHECK(OPS::indexOf(0) == 2 && OPS::indexOf(-3) == 2 && OPS::indexOf(NAN) == 2 && OPS::indexOf(INFINITY) == 2);
    CHECK(OPS::indexOf(1.1) == 2 && OPS::indexOf(1.2) == 3 && OPS::indexOf(0.25) == 0 && OPS::indexOf(3) == 6);
    CHECK(OPS::step(1, 1) == 1.25 && OPS::step(1, -1) == 0.75);
    CHECK(OPS::step(2, 1) == 2 && OPS::step(0.5, -1) == 0.5);   // stops at the ends
    CHECK(OPS::cycle(1) == 1.25 && OPS::cycle(1.75) == 2 && OPS::cycle(2) == 0.5 && OPS::cycle(0.75) == 1);
    {   // seven presses of Cross come back
        double r = 1; for (int i = 0; i < 7; ++i) r = OPS::cycle(r);
        CHECK(r == 1);
    }
    CHECK(OPS::isNormal(1) && !OPS::isNormal(1.25));

    // labels
    CHECK(OPS::label(1) == "1" + x);
    CHECK(OPS::label(0.5) == "0.5" + x);
    CHECK(OPS::label(0.75) == "0.75" + x);
    CHECK(OPS::label(1.25) == "1.25" + x);
    CHECK(OPS::label(1.5) == "1.5" + x);
    CHECK(OPS::label(2) == "2" + x);
    CHECK(OPS::label(1.49) == "1.5" + x);
    CHECK(OPS::notice(1.75) == "Speed: 1.75" + x);
    CHECK(OPS::unavailableNotice() == "Speed not available for this video");

    // caps (mirrors OmniPlaybackRate.h / OmniHwPlatform.h)
    {
        OPS::Caps c = OPS::caps(nullptr, false, nullptr, false);
        CHECK(!c.rateOff && !c.mseOff);
        c = OPS::caps(nullptr, true, nullptr, false); CHECK(c.rateOff && !c.mseOff);
        c = OPS::caps("1", true, nullptr, false); CHECK(!c.rateOff);       // env wins
        c = OPS::caps("0", false, nullptr, false); CHECK(c.rateOff);
        c = OPS::caps(nullptr, false, nullptr, true); CHECK(!c.rateOff && c.mseOff);
        c = OPS::caps(nullptr, false, "1", true); CHECK(!c.mseOff);
        c = OPS::caps(nullptr, true, nullptr, true); CHECK(c.rateOff && !c.mseOff);   // rate off covers it
    }

    // memory keys
    CHECK(OPS::siteKey("youtube.com", false, 7) == "s:youtube.com");
    CHECK(OPS::siteKey("youtube.com", true, 7) == "p:youtube.com");
    CHECK(OPS::siteKey("", false, 7) == "t:7" && OPS::siteKey("", true, 9) == "t:9");
    {
        OPS::Memory m;
        CHECK(m.empty() && m.get("s:a") == 1);
        m.set("s:a", 1.5); CHECK(m.get("s:a") == 1.5 && !m.empty());
        m.set("s:a", 1.3); CHECK(m.get("s:a") == 1.25);   // normalized
        m.set("s:b", 0.5); CHECK(m.get("p:a") == 1 && m.size() == 2);
        m.set("s:a", 1); CHECK(m.get("s:a") == 1 && m.size() == 1);   // 1x is not kept
        m.set("", 2); CHECK(m.size() == 1);
        for (int i = 0; i < 400; ++i) m.set("s:x" + std::to_string(i), 2);
        CHECK(m.size() == OPS::Memory::kMax);
    }
    {
        OPS::Edges e;
        CHECK(e.started(1, true));          // first play
        CHECK(!e.started(1, true));         // another change while playing (mute, volume)
        CHECK(!e.started(1, false));
        CHECK(e.started(1, true));          // the next video began
        e.set(2, true);
        CHECK(!e.started(2, true));         // set while playing: no second apply
        CHECK(e.started(3, true) && !e.started(3, true));
    }

    // script
    {
        const std::string s = OPS::script(1.5, false);
        CHECK(s.rfind("(function(R,M){", 0) == 0);
        CHECK(s.size() > 20 && s.substr(s.size() - 8) == "(1.50,0)");
        CHECK(OPS::script(9, true).substr(OPS::script(9, true).size() - 8) == "(2.00,1)");
        CHECK(OPS::script(NAN, false).find("(1.00,0)") != std::string::npos);
        CHECK(s.find("preservesPitch=true") != std::string::npos && s.find("setPlaybackRate(R)") != std::string::npos);
        CHECK(s.find("</") == std::string::npos);
    }
    // answers
    {
        OPS::Answer a = OPS::parse("omni-sp1\n2\n0\n1\n2");
        CHECK(a.ok && a.set == 2 && a.skipped == 0 && a.youtube && a.found == 2 && OPS::applied(a));
        CHECK(OPS::resultNotice(a, 1.5) == "Speed: 1.5" + x);
        a = OPS::parse("omni-sp1\n0\n1\n0\n1");
        CHECK(a.ok && !OPS::applied(a) && OPS::resultNotice(a, 2) == "Speed not available for this video");
        a = OPS::parse("omni-sp1\n0\n0\n0\n0");
        CHECK(a.ok && OPS::resultNotice(a, 2) == "No video or audio found on this page");
        a = OPS::parse("omni-sp1\n0\n0\n1\n0");
        CHECK(OPS::applied(a));   // YouTube's API only
        CHECK(!OPS::parse("").ok && !OPS::parse("omni-np1\n1\n0\n0\n1").ok && !OPS::parse("omni-sp1\n1\n0\n0").ok);
        CHECK(!OPS::parse("omni-sp1\n1\n0\n0\n1\nextra").ok && !OPS::parse("omni-sp1\n-1\n0\n0\n1").ok);
        CHECK(!OPS::parse("omni-sp1\n1\n0\n2\n1").ok && !OPS::parse("omni-sp1\n1x\n0\n0\n1").ok);
        CHECK(OPS::resultNotice(OPS::Answer(), 1) == "The page didn't answer");
    }

    if (argc > 1) {
        const std::string dir = argv[1];
        std::ofstream(dir + "/speed-150.js") << OPS::script(1.5, false) << "\n";
        std::ofstream(dir + "/speed-200-nomse.js") << OPS::script(2, true) << "\n";
        std::ofstream(dir + "/speed-100-nomse.js") << OPS::script(1, true) << "\n";
    }
    std::printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
