// OMNI_SCROLL_PLUS_V1: host tests for engine/entry/OmniScrollPlus.h (pure: no SDL, no WebKit).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_scroll_plus.cpp -o t && ./t
#include "OmniScrollPlus.h"
#include <cstdio>
#include <string>

namespace S = OmniScrollPlus;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
static bool near(double a, double b, double eps = 1e-4) { return a - b < eps && b - a < eps; }

static void speedCurve()
{
    // Normal is exactly the old v * 55 (both signs, small and full tilt).
    for (float v : { -1.f, -0.6f, -0.2137f, 0.f, 0.05f, 0.33f, 0.8f, 1.f }) CHECK(S::stickAmount(v, S::kNormal) == v * 55.f);
    CHECK(S::stickAmount(0.f, S::kSlow) == 0.f && S::stickAmount(0.f, S::kFast) == 0.f);
    // Sign follows the stick; odd symmetry.
    for (int s = 0; s < S::kSpeedCount; ++s)
        for (float v : { 0.1f, 0.5f, 1.f }) { CHECK(S::stickAmount(v, s) > 0); CHECK(near(S::stickAmount(-v, s), -S::stickAmount(v, s))); }
    // Monotonic in |v| for every speed.
    for (int s = 0; s < S::kSpeedCount; ++s) {
        float prev = 0;
        for (int i = 1; i <= 100; ++i) { const float a = S::stickAmount(i / 100.f, s); CHECK(a > prev); prev = a; }
    }
    // Full tilt: Slow < Normal < Fast; Slow gentler everywhere; Fast stays fine near the centre (not above 1.2x Normal).
    CHECK(S::stickAmount(1.f, S::kSlow) < S::stickAmount(1.f, S::kNormal));
    CHECK(S::stickAmount(1.f, S::kNormal) < S::stickAmount(1.f, S::kFast));
    CHECK(near(S::stickAmount(1.f, S::kSlow), 38.f) && near(S::stickAmount(1.f, S::kFast), 95.f));
    for (int i = 1; i <= 100; ++i) CHECK(S::stickAmount(i / 100.f, S::kSlow) < S::stickAmount(i / 100.f, S::kNormal));
    for (float v : { 0.1f, 0.2f, 0.3f }) CHECK(S::stickAmount(v, S::kFast) <= 1.2f * S::stickAmount(v, S::kNormal));
    // Out-of-range input is clamped for Slow / Fast; out-of-range speeds use the nearest; NaN gives 0.
    CHECK(near(S::stickAmount(1.5f, S::kFast), 95.f));
    CHECK(S::stickAmount(0.5f, -3) == S::stickAmount(0.5f, S::kSlow));
    CHECK(S::stickAmount(0.5f, 9) == S::stickAmount(0.5f, S::kFast));
    CHECK(S::stickAmount(std::nanf(""), S::kFast) == 0.f);
    // D-pad: Normal stays 140.
    CHECK(S::dpadStep(S::kNormal) == 140 && S::dpadStep(S::kSlow) < 140 && S::dpadStep(S::kFast) > 140);
    CHECK(S::dpadStep(-1) == S::dpadStep(S::kSlow) && S::dpadStep(7) == S::dpadStep(S::kFast));
    CHECK(std::string(S::speedName(0)) == "Slow" && std::string(S::speedName(1)) == "Normal" && std::string(S::speedName(2)) == "Fast");
    CHECK(std::string(S::speedName(99)) == "Fast" && std::string(S::speedName(-1)) == "Slow");
}

static void settingsFile()
{
    S::Settings d = S::parse("");
    CHECK(d.speed == S::kNormal && d.smooth == -1);
    CHECK(S::serialize(d) == "speed\t1\n");   // never chosen: no smooth line (WebKit's default is left alone)
    S::Settings s = S::parse("speed\t2\r\nsmooth\t1\r\n");
    CHECK(s.speed == 2 && s.smooth == 1);
    CHECK(S::serialize(s) == "speed\t2\nsmooth\t1\n");
    S::Settings r = S::parse(S::serialize(s));
    CHECK(r.speed == s.speed && r.smooth == s.smooth);
    // Junk is ignored, values stay in range.
    S::Settings j = S::parse("speed\t7\nsmooth\t2\nspeed\t-1\nspeed\tx\nfoo\t1\nsmooth\t\nsmooth 1\nspeed\t0000\n");
    CHECK(j.speed == S::kNormal && j.smooth == -1);
    CHECK(S::parse("smooth\t0").smooth == 0 && S::parse("speed\t0").speed == 0);
    // Steps: left / right clamp, Cross wraps.
    S::Settings t; t.speed = S::kFast;
    CHECK(S::stepSpeed(t, 1).speed == S::kFast && S::stepSpeed(t, -1).speed == S::kNormal && S::stepSpeed(t, 0).speed == S::kSlow);
    t.speed = S::kSlow;
    CHECK(S::stepSpeed(t, -1).speed == S::kSlow && S::stepSpeed(t, 0).speed == S::kNormal);
}

static void gesture()
{
    S::Gesture g;
    CHECK(g.update(0.f, 0) == S::aNone);
    CHECK(g.update(-0.5f, 10) == S::aNone);            // under the flick threshold
    CHECK(g.update(-0.6f, 20) == S::aPageUp);           // pushed up: one screen up
    CHECK(g.update(-0.9f, 100) == S::aNone);            // still pushed: nothing yet
    CHECK(g.update(-0.9f, 20 + S::kHoldMs - 1) == S::aNone);
    CHECK(g.update(-0.9f, 20 + S::kHoldMs) == S::aTop); // kept pushed: to the top, once
    CHECK(g.update(-1.f, 5000) == S::aNone);
    CHECK(g.update(-0.4f, 5010) == S::aNone);           // between rearm and flick: still the same push
    CHECK(g.update(-0.2f, 5020) == S::aNone);           // let go
    CHECK(g.update(-0.7f, 5030) == S::aPageUp);         // a second push pages again
    CHECK(g.update(0.f, 5040) == S::aNone);
    CHECK(g.update(0.8f, 5050) == S::aPageDown);
    CHECK(g.update(0.8f, 5050 + S::kHoldMs) == S::aBottom);
    // A push the other way straight through the centre (one sample) pages that way.
    S::Gesture h;
    CHECK(h.update(0.9f, 0) == S::aPageDown);
    CHECK(h.update(-0.9f, 30) == S::aPageUp);
    // A hold that eases under the flick threshold (but above rearm) does not jump to the end.
    S::Gesture e;
    CHECK(e.update(0.7f, 0) == S::aPageDown);
    CHECK(e.update(0.4f, S::kHoldMs + 10) == S::aNone);
    CHECK(e.update(0.7f, S::kHoldMs + 20) == S::aBottom);   // pushed again past the flick: the hold counts from the page step
    // Tick wrap (SDL ticks after ~49 days).
    S::Gesture w;
    CHECK(w.update(0.9f, 0xFFFFFF00u) == S::aPageDown);
    CHECK(w.update(0.9f, 0xFFFFFF00u + S::kHoldMs) == S::aBottom);
    w.reset();
    CHECK(w.dir == 0 && !w.jumped);
    CHECK(S::mode(S::aPageUp) == -1 && S::mode(S::aPageDown) == 1 && S::mode(S::aTop) == -2 && S::mode(S::aBottom) == 2 && S::mode(S::aNone) == 0);
}

static int count(const std::string& s, const std::string& what)
{
    int n = 0;
    for (size_t i = s.find(what); i != std::string::npos; i = s.find(what, i + 1)) ++n;
    return n;
}
static void scripts()
{
    const std::string a = S::jumpScript(1, 640.5, 300.0, true);
    CHECK(a.rfind("(function(X,Y,M,S){try{", 0) == 0);
    const std::string tail = "})(640.5,300.0,1,1)";
    CHECK(a.size() > tail.size() && a.compare(a.size() - tail.size(), tail.size(), tail) == 0);   // arguments last, nothing after
    CHECK(a.find("ch*0.875") != std::string::npos);
    CHECK(a.find("behavior:S?'smooth':'instant'") != std::string::npos);
    CHECK(count(a, "(") == count(a, ")") && count(a, "{") == count(a, "}") && count(a, "[") == count(a, "]"));
    CHECK(count(a, "'") % 2 == 0);
    CHECK(a.find('"') == std::string::npos && a.find('\n') == std::string::npos && a.find('\\') == std::string::npos);
    const std::string b = S::jumpScript(-2, -5.0, 1e9, false);
    CHECK(b.find("})(-5.0,1000000000.0,-2,0)") != std::string::npos);
    CHECK(S::jumpScript(9, 0, 0, false).find(",2,0)") != std::string::npos);          // mode clamped
    CHECK(S::jumpScript(1, std::nan(""), INFINITY, false).find("})(0.0,0.0,1,0)") != std::string::npos);   // never NaN in a script
    const std::string m = S::metricsScript();
    CHECK(count(m, "(") == count(m, ")") && count(m, "{") == count(m, "}") && count(m, "'") % 2 == 0);
    CHECK(m.find("innerHeight") != std::string::npos);
}

static void metrics()
{
    S::Metrics m = S::parseMetrics("w,1200,5000,720");
    CHECK(m.valid && m.document && m.top == 1200 && m.height == 5000 && m.client == 720 && S::scrollable(m));
    S::Metrics e = S::parseMetrics("e,0,300,300");
    CHECK(e.valid && !e.document && !S::scrollable(e));                     // fits: no bar
    CHECK(S::parseMetrics("w,9999,5000,720").top == 5000 - 720);           // clamped to the end
    CHECK(S::parseMetrics("w,-40,5000,720").top == 0);                      // rubber-banding above the top
    for (const char* bad : { "", "w", "w,1,2", "x,1,2,3", "w,1,2,0", "w,a,2,3", "w,1,,3", "w,1.5,2,3", "w,1,-2,3", "w;1,2,3", "w,1,2,3,4" })
        CHECK(!S::parseMetrics(bad).valid);
    CHECK(!S::scrollable(S::Metrics()));
}

static void barGeometry()
{
    S::Metrics m = S::parseMetrics("w,0,7200,720");   // 10 screens
    S::Bar b = S::bar(m, 112, 668, 1280);
    CHECK(b.shown && b.x == 1280 - S::kBarMargin - S::kBarW && b.trackY == 122 && b.trackH == 536);
    CHECK(b.thumbH == 54 && b.thumbY == b.trackY);                           // 536 * 0.1 = 53.6 -> 54, at the top
    m = S::parseMetrics("w,6480,7200,720");                                 // at the bottom
    b = S::bar(m, 112, 668, 1280);
    CHECK(b.thumbY + b.thumbH == b.trackY + b.trackH);
    m = S::parseMetrics("w,3240,7200,720");                                 // half way
    b = S::bar(m, 112, 668, 1280);
    CHECK(b.thumbY == b.trackY + (b.trackH - b.thumbH) / 2 || b.thumbY == b.trackY + (b.trackH - b.thumbH + 1) / 2);
    m = S::parseMetrics("w,0,1000000,720");                                 // very long page: minimum thumb
    b = S::bar(m, 0, 720, 1280);
    CHECK(b.thumbH == S::kMinThumb);
    // Every position keeps the thumb inside the track.
    for (int top = 0; top <= 100000; top += 997) {
        const S::Bar k = S::bar(S::parseMetrics("w," + std::to_string(top) + ",100720,720"), 52, 700, 1280);
        CHECK(k.shown && k.thumbY >= k.trackY && k.thumbY + k.thumbH <= k.trackY + k.trackH);
    }
    CHECK(!S::bar(S::parseMetrics("w,0,720,720"), 0, 720, 1280).shown);     // nothing to scroll
    CHECK(!S::bar(S::parseMetrics("w,0,7200,720"), 300, 330, 1280).shown);  // no room
    CHECK(!S::bar(S::Metrics(), 0, 720, 1280).shown);
}

static void fade()
{
    CHECK(S::alpha(0) == 255 && S::alpha(S::kHoldShownMs) == 255);
    CHECK(S::alpha(S::kHoldShownMs + S::kFadeMs) == 0 && S::alpha(5000) == 0);
    CHECK(S::kHoldShownMs + S::kFadeMs == 1000);                            // gone 1 s after the last scroll
    int prev = 256;
    for (uint32_t t = 0; t <= 1100; t += 10) { const int a = S::alpha(t); CHECK(a <= prev); prev = a; }
    const int mid = S::alpha(S::kHoldShownMs + S::kFadeMs / 2);
    CHECK(mid > 100 && mid < 155);
    CHECK(S::scaled(200, 255) == 200 && S::scaled(200, 0) == 0 && S::scaled(255, 128) == 128);
}

static void throttle()
{
    S::Throttle q;
    CHECK(q.want(1000));                         // first: at once
    CHECK(!q.want(1010) && q.pending);           // in flight: remembered
    CHECK(!q.due(1050));                         // still in flight
    q.answered();
    CHECK(!q.due(1080));                         // gap not passed
    CHECK(q.due(1090) && !q.pending);            // the remembered scroll is asked for
    CHECK(!q.due(1300));                         // nothing more without a new scroll (no polling)
    q.answered();
    CHECK(q.want(1300));
    CHECK(!q.want(1301));
    CHECK(!q.due(1302));
    CHECK(q.due(1300 + S::kStaleMs) );           // a query that never came back no longer blocks
    q.reset();
    CHECK(!q.inFlight && !q.pending);
    S::Throttle w;                               // tick wrap
    CHECK(w.want(0xFFFFFFF0u));
    w.answered();
    CHECK(!w.want(0xFFFFFFF0u + 10) && w.due(0xFFFFFFF0u + S::kQueryGapMs));
    CHECK(!S::userScrolling(5000, 0, false));
    CHECK(S::userScrolling(5000, 4500, true) && S::userScrolling(5000, 5000 - S::kUserWindowMs, true));
    CHECK(!S::userScrolling(5000, 5000 - S::kUserWindowMs - 1, true));
}

int main()
{
    speedCurve();
    settingsFile();
    gesture();
    scripts();
    metrics();
    barGeometry();
    fade();
    throttle();
    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
