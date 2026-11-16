// OMNI_SEEK_PAUSE_V1: host tests of the pure hold-to-seek schedule and the pause-everything chord (OmniSeekPause.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_seek_pause.cpp -o t && ./t      (run in tools/, or -I<tree>/engine/entry)
#include "OmniSeekPause.h"
#include <cstdio>
#include <cstring>
#include <string>

namespace S = OmniSeekPause;
namespace V = OmniVideoKeys;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

static bool sameKey(const V::Key& a, const V::Key& b)
{
    auto eq = [](const char* x, const char* y) { return (!x && !y) || (x && y && std::strcmp(x, y) == 0); };
    return eq(a.text, b.text) && eq(a.identifier, b.identifier) && a.keysym == b.keysym;
}

// Simulates a hold of holdMs from press time t0: the repeats a shell ticking every tickMs sends (answers instant).
static int simulate(uint32_t t0, uint32_t holdMs, bool big, int dir, uint32_t tickMs, int* repeats)
{
    S::Hold h;
    h.begin(t0, dir, big, 7, S::kFirstMs);
    int n = 0;
    for (uint32_t dt = 0; dt <= holdMs; dt += tickMs) {
        const uint32_t now = t0 + dt;
        if (h.due(now)) { h.take(now, S::kRateMs); ++n; }
    }
    if (repeats) *repeats = n;
    return h.total;
}

int main()
{
    // --- the step schedule: 10 s for the first second, then 30 s, then 1 minute; R2: always 1 minute ---
    CHECK(S::stepSeconds(0, false) == 10);
    CHECK(S::stepSeconds(999, false) == 10);
    CHECK(S::stepSeconds(1000, false) == 30);
    CHECK(S::stepSeconds(2999, false) == 30);
    CHECK(S::stepSeconds(3000, false) == 60);
    CHECK(S::stepSeconds(600000, false) == 60);
    CHECK(S::stepSeconds(0, true) == 60 && S::stepSeconds(1500, true) == 60);
    // never shrinks while the hold goes on
    for (uint32_t ms = 0, prev = 0; ms < 10000; ms += 50) {
        const uint32_t s = uint32_t(S::stepSeconds(ms, false));
        CHECK(s >= prev);
        prev = s;
    }

    // --- the hold: the press's own step counts, the first repeat waits kFirstMs, then every kRateMs ---
    {
        S::Hold h;
        CHECK(!h.on && !h.due(0));
        h.begin(1000, 1, false, 42, S::kFirstMs);
        CHECK(h.on && h.dir == 1 && !h.big && h.tab == 42 && h.total == 10);
        CHECK(!h.due(1000) && !h.due(1499) && h.due(1500));
        CHECK(h.take(1500, S::kRateMs) == 10 && h.total == 20 && h.next == 1750);
        CHECK(!h.due(1749) && h.due(1750));
        CHECK(h.take(2000, S::kRateMs) == 30 && h.total == 50);   // held 1000 ms: 30 s steps
        CHECK(h.take(4000, S::kRateMs) == 60 && h.total == 110);  // held 3000 ms: 1 minute steps
        h.stop();
        CHECK(!h.on && !h.due(999999));
        h.begin(0, -1, false, 1, S::kFirstMs);
        CHECK(h.dir == -1 && h.total == -10 && h.take(500, S::kRateMs) == -10 && h.total == -20);
        h.begin(0, -5, true, 1, S::kFirstMs);
        CHECK(h.dir == -1 && h.big && h.total == -60 && h.take(500, S::kRateMs) == -60 && h.total == -120);
        h.begin(0, 0, false, 1, S::kFirstMs);
        CHECK(h.dir == 1);
    }
    // timing across the SDL tick wrap
    {
        S::Hold h;
        const uint32_t t0 = 0xFFFFFF00u;
        h.begin(t0, 1, false, 1, S::kFirstMs);
        CHECK(!h.due(t0 + 100) && !h.due(t0 + 499) && h.due(t0 + 500));
        CHECK(h.take(t0 + 1200, S::kRateMs) == 30);
        CHECK(h.due(t0 + 1450) && !h.due(t0 + 1449));
    }
    // "No repeat" (Repeat delay): the shell passes ~12 days as the first wait: a plain press, never a repeat
    {
        S::Hold h;
        h.begin(5, 1, false, 1, 0x3FFFFFFFu);
        CHECK(!h.due(5 + 60000) && !h.due(5 + 3600000));
    }
    // a 2-hour video: far fewer presses than 40 x 10 s; with a 16 ms tick, 10 s of holding covers about 30 minutes
    {
        int n = 0;
        const int total = simulate(100, 10000, false, 1, 16, &n);
        CHECK(n >= 35 && n <= 40);
        CHECK(total >= 1800 && total <= 2600);
        int n2 = 0;
        CHECK(simulate(100, 400, false, 1, 16, &n2) == 10 && n2 == 0);   // a tap: the press alone
        CHECK(simulate(100, 1000, false, -1, 1, &n2) == -60 && n2 == 3); // -10 press, -10 at 500 ms, -10 at 750, -30 at 1000
        CHECK(simulate(100, 1000, true, 1, 1, &n2) == 240 && n2 == 3);   // R2: 1 minute each
    }

    // --- the repeat press: YouTube's own keys for 10 s, page seeks for 30 s / 1 minute ---
    {
        V::Press p = S::repeatPress(-1, 10, false);
        const V::Press l1 = V::plan(V::pL1, false);
        CHECK(p.act == l1.act && p.amount == -10 && p.flags == l1.flags && p.fallback == V::fbKey && sameKey(p.key, V::keyJ()));
        CHECK((p.flags & V::fYtKey) != 0);
        p = S::repeatPress(1, 10, false);
        CHECK(p.amount == 10 && sameKey(p.key, V::keyL()) && (p.flags & V::fYtKey));
        p = S::repeatPress(1, 30, false);
        CHECK(p.act == V::kSeek && p.amount == 30 && p.flags == 0 && p.fallback == V::fbKey && sameKey(p.key, V::keyL()));
        p = S::repeatPress(-1, 60, false);
        CHECK(p.act == V::kSeek && p.amount == -60 && p.flags == 0 && p.fallback == V::fbKey && sameKey(p.key, V::keyJ()));
        p = S::repeatPress(-1, 60, true);
        const V::Press big = V::plan(V::pL1, true);
        CHECK(p.act == big.act && p.amount == big.amount && p.flags == big.flags && p.fallback == V::fbNone && p.fallback == big.fallback);
        // the page script carries the step
        CHECK(V::script(S::repeatPress(1, 30, false)).find("(2,30,0)") != std::string::npos);
        CHECK(V::script(S::repeatPress(-1, 10, false)).find("(2,-10,1)") != std::string::npos);
    }

    // --- the OSD title ---
    CHECK(S::totalLabel(100) == "+1:40");
    CHECK(S::totalLabel(-725) == "-12:05");
    CHECK(S::totalLabel(3723) == "+1:02:03");
    CHECK(S::totalLabel(0) == "+0:00");
    CHECK(S::holdTitle("+30 s", 100) == "+30 s   held: +1:40");
    CHECK(S::holdTitle("-1 min", -240) == "-1 min   held: -4:00");
    CHECK(S::holdTitle("", 100).empty());
    CHECK(V::seekLabel(30) == "+30 s" && V::seekLabel(-60) == "-1 min");

    // --- E16: the chord ---
    {
        S::PauseChord c;
        CHECK(c.fire(1000));
        CHECK(!c.fire(1000) && !c.fire(1500) && !c.fire(1799));
        CHECK(c.fire(1800));
        S::PauseChord w;   // across the tick wrap
        CHECK(w.fire(0xFFFFFF00u) && !w.fire(0xFFFFFF00u + 700) && w.fire(0xFFFFFF00u + 800));
        S::PauseChord z;   // the very first chord at tick 0 fires
        CHECK(z.fire(0) && !z.fire(10));
        S::PauseChord b;   // a clock that went back (never in SDL, but no lock-out)
        CHECK(b.fire(5000) && b.fire(4000));
    }
    CHECK(std::string(S::chordNotice(2)) == "Paused everything");
    CHECK(std::string(S::chordNotice(0)) == "Nothing is playing");
    CHECK(std::string(S::leftoverNotice()).size() < 70);

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
