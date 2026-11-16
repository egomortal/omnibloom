// OMNI_YT_MEDIA_STOP_V1: host tests of the pure part (engine/entry/OmniYtMediaStop.h written by apply_yt_media_stop.py).
//   g++ -std=c++17 -Wall -Wextra -I<patched tree>/engine/entry test_yt_media_stop.cpp -o t && ./t
#include "OmniYtMediaStop.h"
#include <cstdio>

namespace Y = OmniYtMediaStop;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

// feeds one answer per second: media(k) for k = 0..secs-1 (nullptr-like: t < 0 = no answer); returns the stop reason and second
struct Run { Y::Reason r = Y::None; unsigned at = 0; };
template <class F> static Run play(const Y::Config& c, unsigned secs, F media)
{
    Y::State s;
    for (unsigned k = 0; k < secs; ++k) {
        double t; bool ad;
        if (media(k, t, ad)) Y::observe(s, k * 1000u, t, ad);
        const auto r = Y::decide(c, s, k * 1000u);
        if (r != Y::None) return {r, k};
    }
    return {};
}

int main()
{
    // ---- parse
    auto c = Y::parse("70 8 150");
    CHECK(c.on && c.mediaS == 70 && c.stallS == 8 && c.capS == 150);
    c = Y::parse("70,8,150\n"); CHECK(c.on && c.capS == 150);
    c = Y::parse(" 70, 8 ,150\r\n"); CHECK(c.on && c.stallS == 8);
    CHECK(!Y::parse("").on);
    CHECK(!Y::parse("70 8").on);
    CHECK(!Y::parse("70 8 150 4").on);
    CHECK(!Y::parse("70 8 150x").on);
    CHECK(!Y::parse("-70 8 150").on);
    CHECK(!Y::parse("70.5 8 150").on);
    CHECK(!Y::parse("0 8 150").on);
    CHECK(!Y::parse("70 1 150").on);
    CHECK(!Y::parse("70 8 361").on);
    CHECK(!Y::parse("70 8 9").on);
    CHECK(!Y::parse("150 8 150").on);          // media must be below the cap
    CHECK(!Y::parse("999999999999 8 150").on);
    CHECK(Y::parse("300 120 360").on && Y::parse("1 2 10").on);

    // ---- parseAnswer
    double t = -1; bool ad = true;
    CHECK(Y::parseAnswer("63.214 0", t, ad) && t > 63.2 && t < 63.3 && !ad);
    CHECK(Y::parseAnswer("4.000 1", t, ad) && t == 4.0 && ad);
    CHECK(!Y::parseAnswer("", t, ad));
    CHECK(!Y::parseAnswer("4.0", t, ad));
    CHECK(!Y::parseAnswer("4.0 2", t, ad));
    CHECK(!Y::parseAnswer("4.0 10", t, ad));
    CHECK(!Y::parseAnswer("x 0", t, ad));
    CHECK(!Y::parseAnswer("-1 0", t, ad));
    CHECK(!Y::parseAnswer("nan 0", t, ad));

    // ---- off = never decides (the caller keeps its wall window)
    Y::State s0; Y::observe(s0, 1000, 500.0, false);
    CHECK(Y::decide(Y::Config(), s0, 999000) == Y::None);

    const auto cfg = Y::parse("70 8 150");
    // startup 25 s with no video, then plays through: stops at media 70 (k = 25 + 70)
    auto r = play(cfg, 400, [](unsigned k, double& t, bool& a) { if (k < 25) return false; t = k - 25; a = false; return true; });
    CHECK(r.r == Y::Media && r.at == 95);
    // startup: the element sits at 0 for 30 s waiting for GenerateIT: no stall stop before the main video started
    r = play(cfg, 400, [](unsigned k, double& t, bool& a) { t = k < 30 ? 0.0 : k - 30; a = false; return true; });
    CHECK(r.r == Y::Media && r.at == 100);
    // the ~60 s cut: media freezes at 60.0, stall stop 8 s after the last progress
    r = play(cfg, 400, [](unsigned k, double& t, bool& a) { t = k < 10 ? 0.0 : (k - 10 < 60 ? k - 10 : 60.0); a = false; return true; });
    CHECK(r.r == Y::Stall && r.at == 70 + 8);
    // slow progress (0.04 s / s) is no progress: it is measured from the anchor, not sample to sample
    r = play(cfg, 400, [](unsigned k, double& t, bool& a) { t = k < 50 ? k : 50 + (k - 50) * 0.04; a = false; return true; });
    CHECK(r.r == Y::Stall);
    // a pre-roll ad of 20 media s, even one past 70 s, never counts: then the content from 0
    r = play(Y::parse("70 8 300"), 400, [](unsigned k, double& t, bool& a) { if (k < 5) return false; if (k < 85) { t = k - 5; a = true; return true; } t = k - 85; a = false; return true; });
    CHECK(r.r == Y::Media && r.at == 85 + 70);
    // an ad never trips the stall rule, even if its time does not move; after the ad the stall clock restarts
    r = play(cfg, 400, [](unsigned k, double& t, bool& a) { if (k < 40) { t = k; a = false; return true; } if (k < 60) { t = 3.0; a = true; return true; } t = 40.0; a = false; return true; });
    CHECK(r.r == Y::Stall && r.at == 60 + 8);
    // never starts (no video at all, or stuck at 0): the wall cap
    r = play(cfg, 400, [](unsigned, double&, bool&) { return false; });
    CHECK(r.r == Y::Cap && r.at == 150);
    r = play(cfg, 400, [](unsigned, double& t, bool& a) { t = 0; a = false; return true; });
    CHECK(r.r == Y::Cap && r.at == 150);
    // the page stops answering mid-play: stall from the last progress (the native clock runs on)
    r = play(cfg, 400, [](unsigned k, double& t, bool& a) { if (k > 30) return false; t = k; a = false; return true; });
    CHECK(r.r == Y::Stall && r.at == 30 + 8);
    // a guard-style reload: back to 5 s and on; the jump back is progress, playback goes on to 70
    r = play(cfg, 400, [](unsigned k, double& t, bool& a) { t = k < 20 ? k : (k < 23 ? 0.0 : 5.0 + (k - 23)); a = false; return true; });
    CHECK(r.r == Y::Media && r.at == 23 + 65);
    // a resume position already past the media goal stops at the first main answer
    r = play(cfg, 400, [](unsigned k, double& t, bool& a) { if (k < 3) return false; t = 75.0 + k; a = false; return true; });
    CHECK(r.r == Y::Media && r.at == 3);

    CHECK(std::string(Y::name(Y::Stall)) == "stall" && std::string(Y::name(Y::None)) == "none");
    CHECK(Y::printable("70 8\n150\x01") == "70 8 150");
    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
