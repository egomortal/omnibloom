// OMNI_NIGHT_LIGHT_V1: host tests of the pure part (engine/entry/OmniNightLight.h).
// g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_night_light.cpp -o t && ./t
#include "OmniNightLight.h"
#include <cstdio>
#include <cstring>

namespace NL = OmniNightLight;
static int fails = 0, passes = 0;
#define CHECK(c) do { if (c) ++passes; else { ++fails; printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static bool eq(float a, float b) { return std::fabs(a - b) < 1e-5f; }

int main()
{
    // defaults
    NL::Settings d;
    CHECK(d.mode == NL::kOff && d.level == 3 && d.start == 21 * 60 && d.end == 7 * 60 && d.last == NL::kOn);

    // hh:mm
    int m = -1;
    CHECK(NL::parseHhmm("21:00", m) && m == 1260);
    CHECK(NL::parseHhmm("7:30", m) && m == 450);
    CHECK(NL::parseHhmm("07", m) && m == 420);
    CHECK(!NL::parseHhmm("24:00", m) && !NL::parseHhmm("21:60", m) && !NL::parseHhmm("", m) && !NL::parseHhmm("2100", m)
          && !NL::parseHhmm("21:0", m) && !NL::parseHhmm("-1", m) && !NL::parseHhmm("21:00x", m));
    CHECK(NL::hhmm(0) == "00:00" && NL::hhmm(1439) == "23:59" && NL::hhmm(1440) == "00:00" && NL::hhmm(-60) == "23:00");

    // file round trip, CRLF, junk
    NL::Settings s; s.mode = NL::kScheduled; s.last = NL::kScheduled; s.level = 5; s.start = 22 * 60 + 30; s.end = 6 * 60;
    NL::Settings r = NL::parse(NL::serialize(s));
    CHECK(r.mode == s.mode && r.last == s.last && r.level == 5 && r.start == s.start && r.end == s.end);
    r = NL::parse("mode\ton\r\nwarmth\t9\r\nstart\tbad\r\nend\t06:00\r\nlast\toff\r\nnoise\n\tx\n");
    CHECK(r.mode == NL::kOn && r.level == 3 && r.start == 1260 && r.end == 360 && r.last == NL::kOn);
    CHECK(NL::parse("").mode == NL::kOff);
    CHECK(NL::serialize(NL::Settings()) == "# Omni night light (OMNI_NIGHT_LIGHT_V1)\nmode\toff\nlast\ton\nwarmth\t3\nstart\t21:00\nend\t07:00\n");

    // schedule, wrapping past midnight (21:00-07:00)
    CHECK(NL::inWindow(21 * 60, 1260, 420) && NL::inWindow(23 * 60 + 59, 1260, 420) && NL::inWindow(0, 1260, 420)
          && NL::inWindow(6 * 60 + 59, 1260, 420));
    CHECK(!NL::inWindow(7 * 60, 1260, 420) && !NL::inWindow(12 * 60, 1260, 420) && !NL::inWindow(20 * 60 + 59, 1260, 420));
    // not wrapping (13:00-15:00), empty (start == end), out-of-range inputs normalised
    CHECK(NL::inWindow(13 * 60, 780, 900) && !NL::inWindow(15 * 60, 780, 900) && !NL::inWindow(12 * 60, 780, 900));
    CHECK(!NL::inWindow(0, 600, 600) && !NL::inWindow(600, 600, 600));
    CHECK(NL::inWindow(1440 + 22 * 60, 1260, 420) && NL::inWindow(-60, 1260, 420));
    NL::Settings sc; sc.mode = NL::kScheduled;
    CHECK(NL::wantTint(sc, 22 * 60) && !NL::wantTint(sc, 12 * 60));
    sc.mode = NL::kOn; CHECK(NL::wantTint(sc, 12 * 60));
    sc.mode = NL::kOff; CHECK(!NL::wantTint(sc, 22 * 60));

    // local minute
    CHECK(NL::localMinute(0, 0) == 0);
    CHECK(NL::localMinute(86400LL * 20000 + 3600 * 23 + 60 * 15, 0) == 23 * 60 + 15);
    CHECK(NL::localMinute(86400LL * 20000 + 3600 * 23, 2 * 3600) == 60);        // UTC+2 crosses midnight
    CHECK(NL::localMinute(86400LL * 20000 + 3600, -5 * 3600) == 20 * 60);       // UTC-5, previous day
    CHECK(NL::localMinute(-60, 0) == 1439);                                     // before 1970
    CHECK(NL::localMinute(86400LL * 20000, 5 * 3600 + 1800) == 330);            // UTC+5:30

    // tz-offset.json
    int tz = 0;
    CHECK(NL::parseTzOffsetJson("{\"utcOffsetMinutes\": -300}", tz) && tz == -300);
    CHECK(NL::parseTzOffsetJson("{ \"x\":1, \"utcOffsetMinutes\" :\n 330 }", tz) && tz == 330);
    CHECK(NL::parseTzOffsetJson("{\"utcOffsetMinutes\":0}", tz) && tz == 0);
    CHECK(!NL::parseTzOffsetJson("{\"utcOffsetMinutes\": 1000}", tz) && !NL::parseTzOffsetJson("{\"utcOffsetMinutes\": 1.5}", tz)
          && !NL::parseTzOffsetJson("{\"utcOffsetMinutes\": \"60\"}", tz) && !NL::parseTzOffsetJson("{}", tz)
          && !NL::parseTzOffsetJson("{\"utcOffsetMinutes\": }", tz) && !NL::parseTzOffsetJson("{\"utcOffsetMinutes\": 123456}", tz));
    CHECK(NL::chooseOffsetSeconds(3600, true, -300) == 3600);   // libc knows: it wins
    CHECK(NL::chooseOffsetSeconds(0, true, -300) == -18000);    // libc says UTC: the file
    CHECK(NL::chooseOffsetSeconds(0, false, -300) == 0);

    // matrices: identity, warmth order (blue falls fastest, green slightly, red kept), clamp
    CHECK(NL::isIdentity(NL::identity()) && !NL::isIdentity(NL::warmthMatrix(1)));
    for (int l = 1; l <= 5; ++l) {
        const NL::Mat w = NL::warmthMatrix(l);
        CHECK(eq(w.m[0], 1.0f) && w.m[4] < 1.0f && w.m[8] < w.m[4] && 1.0f - w.m[8] > 2 * (1.0f - w.m[4]));
        CHECK(w.m[1] == 0 && w.m[2] == 0 && w.m[3] == 0 && w.m[5] == 0 && w.m[6] == 0 && w.m[7] == 0);
        if (l > 1) { const NL::Mat p = NL::warmthMatrix(l - 1); CHECK(w.m[4] < p.m[4] && w.m[8] < p.m[8]); }
    }
    CHECK(NL::near(NL::warmthMatrix(0), NL::warmthMatrix(1), 0) && NL::near(NL::warmthMatrix(9), NL::warmthMatrix(5), 0));
    NL::Settings on; on.mode = NL::kOn; on.level = 4;
    CHECK(NL::near(NL::target(on, 600), NL::warmthMatrix(4), 0) && NL::isIdentity(NL::target(NL::Settings(), 600)));

    // CPU reference pixel
    uint8_t pr = 255, pg = 255, pb = 255; NL::applyPixel(NL::warmthMatrix(5), pr, pg, pb);
    CHECK(pr == 255 && pg == 189 && pb == 92);   // 0.74 * 255 = 188.7, 0.36 * 255 = 91.8
    pr = 10; pg = 20; pb = 30; NL::applyPixel(NL::identity(), pr, pg, pb);
    CHECK(pr == 10 && pg == 20 && pb == 30);
    NL::Mat big = NL::identity(); big.m[0] = 2; big.m[1] = 1; pr = 200; pg = 200; pb = 0; NL::applyPixel(big, pr, pg, pb);
    CHECK(pr == 255 && pg == 200 && pb == 0);   // clamped

    // fade: 2 s smoothstep, retarget from the current value, wrap-safe ticks
    NL::Fade f; f.snap(NL::identity());
    CHECK(NL::isIdentity(f.value(123)) && !f.running(123));
    const NL::Mat w5 = NL::warmthMatrix(5);
    f.retarget(w5, 1000);
    CHECK(f.running(1000) && NL::isIdentity(f.value(1000)));
    const NL::Mat mid = f.value(2000);
    CHECK(eq(mid.m[8], 1.0f + (0.36f - 1.0f) * 0.5f) && eq(mid.m[4], 1.0f + (0.74f - 1.0f) * 0.5f));
    CHECK(f.value(1500).m[8] > mid.m[8] && f.value(2500).m[8] < mid.m[8]);
    CHECK(NL::near(f.value(3000), w5, 0) && !f.running(3000) && NL::near(f.value(900000), w5, 0));
    f.retarget(w5, 5000); CHECK(!f.running(5000));              // same target: nothing
    f.retarget(NL::identity(), 10000);                          // fade out from the full tint
    f.retarget(NL::warmthMatrix(5), 11000);                     // reversed half way: starts from the current value
    CHECK(f.running(11000) && eq(f.value(11000).m[8], 1.0f + (0.36f - 1.0f) * 0.5f));
    CHECK(NL::near(f.value(13000), w5, 0));
    NL::Fade fw; fw.snap(NL::identity()); fw.retarget(w5, 0xFFFFFC18u);   // 1 s before the 32-bit wrap
    CHECK(fw.running(0x00000000u) && fw.running(500) && !fw.running(1000) && NL::near(fw.value(1000), w5, 0));
    CHECK(NL::ease(0) == 0 && NL::ease(1) == 1 && eq(NL::ease(0.5f), 0.5f) && NL::ease(-1) == 0 && NL::ease(2) == 1);
    // a 2 s fade sends a bounded number of matrices (kSendEps steps): at most one per 1/2048 of blue
    {
        NL::Fade g; g.snap(NL::identity()); g.retarget(w5, 0);
        NL::Mat last = NL::identity(); int sent = 0;
        for (uint32_t t = 0; t <= 2100; t += 16) { NL::Mat v = g.value(t); if (!NL::near(v, last, NL::kSendEps)) { last = v; ++sent; } }
        CHECK(sent > 60 && sent <= 132 && NL::near(last, w5, NL::kSendEps));
    }

    // controls
    CHECK(NL::cycleMode(NL::kOff, 1) == NL::kOn && NL::cycleMode(NL::kOn, 1) == NL::kScheduled && NL::cycleMode(NL::kScheduled, 1) == NL::kOff);
    CHECK(NL::cycleMode(NL::kOff, -1) == NL::kScheduled && NL::cycleMode(NL::kScheduled, -1) == NL::kOn);
    CHECK(NL::stepHour(1260, 1) == 1320 && NL::stepHour(1380, 1) == 0 && NL::stepHour(0, -1) == 1380 && NL::stepHour(450, 1) == 480);
    NL::Settings q; q.mode = NL::kScheduled; q.last = NL::kScheduled;
    q = NL::quickToggle(q); CHECK(q.mode == NL::kOff && q.last == NL::kScheduled);
    q = NL::quickToggle(q); CHECK(q.mode == NL::kScheduled);
    NL::Settings q2; q2 = NL::quickToggle(q2); CHECK(q2.mode == NL::kOn && q2.last == NL::kOn);
    q2 = NL::setMode(q2, NL::kScheduled); q2 = NL::setMode(q2, NL::kOff); CHECK(q2.last == NL::kScheduled);

    // texts
    NL::Settings t; t.mode = NL::kScheduled;
    CHECK(NL::modeValue(t, 22 * 60) == "Scheduled (on now)" && NL::modeValue(t, 12 * 60) == "Scheduled (off now)");
    CHECK(NL::modeDetail(t, 22 * 60 + 14, true) == "On now, until 07:00 (console time 22:14)");
    CHECK(NL::modeDetail(t, 12 * 60, true) == "Off now, starts at 21:00 (console time 12:00)");
    t.end = t.start; CHECK(NL::modeDetail(t, 12 * 60, true) == "From and until are the same time: never on");
    CHECK(NL::modeDetail(t, 0, false).find("GPU display output") != std::string::npos);
    CHECK(NL::levelValue(3) == "3 of 5" && NL::levelValue(7) == "5 of 5");
    NL::Settings u; u.mode = NL::kScheduled;
    CHECK(NL::tileValue(u, 22 * 60) == "Scheduled, on" && NL::tileValue(NL::Settings(), 0) == "Off");
    CHECK(NL::toggleNotice(u, 22 * 60, true) == "Night light on until 07:00" && NL::toggleNotice(u, 9 * 60, true) == "Night light scheduled from 21:00");
    u.mode = NL::kOn; CHECK(NL::toggleNotice(u, 0, false) == "Night light on (needs Omni's GPU display output)");
    CHECK(NL::toggleNotice(NL::Settings(), 0, false) == "Night light off");

    printf("%d passed, %d failed\n", passes, fails);
    return fails ? 1 : 0;
}
