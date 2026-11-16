// OMNI_TAB_AUTOCLOSE_V1 tests: g++ -std=c++20 -Wall -Wextra -Werror -I. test_tab_autoclose.cpp -o t && ./t
#include "OmniTabAutoClose.h"
#include <cstdio>

namespace X = OmniTabAutoClose;
static int fails = 0;
#define CHECK(c) do { if (!(c)) { ++fails; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static X::Cand cand(long long shown, bool current = false, bool pinned = false, bool sound = false, bool keep = false)
{
    X::Cand c; c.shown = shown; c.current = current; c.pinned = pinned; c.sound = sound; c.keep = keep;
    return c;
}

int main()
{
    const long long now = 1763251200;   // 2025-11-16
    const long long D = X::kDay;

    // settings
    CHECK(X::parse("").days == 0 && !X::parse("").asked);
    CHECK(X::parse("days\t14\r\nasked\t1\n").days == 14 && X::parse("days\t14\nasked\t1\n").asked);
    CHECK(X::parse("days\t8\n").days == 7 && X::parse("days\t25\n").days == 30 && X::parse("days\t999999\n").days == 30);
    CHECK(X::parse("days\t-7\n").days == 0 && X::parse("days\tx\n").days == 0 && X::parse("days\t1234567\n").days == 0);
    X::Settings s; s.days = 30; s.asked = true;
    CHECK(X::serialize(s) == "days\t30\nasked\t1\n");
    CHECK(X::parse(X::serialize(s)).days == 30 && X::parse(X::serialize(s)).asked);
    CHECK(X::stepDays(0, 1, false) == 7 && X::stepDays(7, 1, false) == 14 && X::stepDays(14, 1, false) == 30);
    CHECK(X::stepDays(30, 1, false) == 30 && X::stepDays(30, 1, true) == 0 && X::stepDays(0, -1, false) == 0);
    CHECK(X::stepDays(14, -1, false) == 7);

    // clock safety
    CHECK(!X::clockValid(0) && !X::clockValid(X::kMinValid - 1) && X::clockValid(X::kMinValid));
    CHECK(X::usable(now - 40 * D, now) && X::usable(now + 60, now) && !X::usable(now + 3600, now));
    CHECK(!X::usable(X::kMinValid - 1, now) && !X::usable(0, now) && !X::usable(-5, now));
    CHECK(X::normalize(0, now) == now);                      // unknown: counts as shown now
    CHECK(X::normalize(now + 10 * D, now) == now);           // future (clock went back): ignored
    CHECK(X::normalize(946684800, now) == now);              // 2000: ignored
    CHECK(X::normalize(now + 60, now) == now);               // slightly ahead: at most now
    CHECK(X::normalize(now - 3 * D, now) == now - 3 * D);
    CHECK(!X::unusedFor(now + 30 * D, now, 7));
    CHECK(!X::unusedFor(946684800, now, 7));                 // a pre-2024 stamp is never "old"
    CHECK(X::unusedFor(now - 7 * D, now, 7) && !X::unusedFor(now - 7 * D + 1, now, 7));
    // a console clock reset to 2000: nothing is decided at all
    CHECK(X::decide(cand(946000000), 946684800, 7) == X::kOff);
    CHECK(X::pick({ cand(0, true), cand(946000000), cand(1) }, 946684800, 7).empty());

    // selection rules
    CHECK(X::decide(cand(now - 40 * D), now, 0) == X::kOff);
    CHECK(X::decide(cand(now - 40 * D, true), now, 7) == X::kCurrent);
    CHECK(X::decide(cand(now - 40 * D, false, true), now, 7) == X::kPinned);
    CHECK(X::decide(cand(now - 40 * D, false, false, true), now, 7) == X::kSound);
    CHECK(X::decide(cand(now - 40 * D, false, false, false, true), now, 7) == X::kKeep);
    CHECK(X::decide(cand(now - 6 * D), now, 7) == X::kRecent);
    CHECK(X::decide(cand(now - 8 * D), now, 7) == X::kClose);
    CHECK(X::decide(cand(now - 8 * D), now, 14) == X::kRecent);
    CHECK(X::decide(cand(now - 31 * D), now, 30) == X::kClose);
    {
        std::vector<X::Cand> cs = { cand(now, true), cand(now - 9 * D), cand(now - 20 * D, false, true), cand(now - 30 * D),
                                    cand(now - 2 * D), cand(now - 50 * D, false, false, true), cand(now - 8 * D, false, false, false, true),
                                    cand(now + 99 * D), cand(0) };
        const std::vector<int> p = X::pick(cs, now, 7);
        CHECK(p.size() == 2 && p[0] == 3 && p[1] == 1);      // oldest first; pinned, sound, private, future, unknown stay
    }
    {   // never the last tab: no shown tab in the list (not expected): the newest stays
        const std::vector<int> p = X::pick({ cand(now - 30 * D), cand(now - 10 * D), cand(now - 20 * D) }, now, 7);
        CHECK(p.size() == 2 && p[0] == 0 && p[1] == 2);
        CHECK(X::pick({ cand(now - 30 * D) }, now, 7).empty());
        CHECK(X::pick({}, now, 7).empty());
        CHECK(X::pick({ cand(now - 30 * D, true) }, now, 7).empty());
    }

    // timer: first check 30 s after start, then hourly; put off: a minute; wrap-safe
    {
        X::Timer t;
        CHECK(!t.due(1000));
        CHECK(!t.due(1000 + X::kStartDelayMs - 1) && t.due(1000 + X::kStartDelayMs));
        const uint32_t a = 1000 + X::kStartDelayMs;
        CHECK(!t.due(a + X::kCheckMs - 1) && t.due(a + X::kCheckMs));
        t.postpone(5000000);
        CHECK(!t.due(5000000 + X::kRetryMs - 1) && t.due(5000000 + X::kRetryMs));
        X::Timer w; w.restart(0xFFFFF000u);
        CHECK(!w.due(0x00000010u) && w.due(0xFFFFF000u + X::kStartDelayMs));
    }

    // session lines
    {
        const uint32_t h = X::hashOf("https://example.com/");
        CHECK(X::hashOf("") == 2166136261u && h != X::hashOf("https://example.com"));
        const std::string l = X::sessionLine(3, now, h);
        CHECK(l == "shown\t3\t" + std::to_string(now) + "\t" + X::hex8(h) + "\n");
        X::Mark m;
        CHECK(X::parseLine(l, m) && m.index == 3 && m.seconds == now && m.hash == h);
        CHECK(X::parseLine("shown\t0\t1763251200\t0000abcd\r\n", m) && m.index == 0 && m.hash == 0xabcdu);
        CHECK(!X::parseLine("tab\thttps://a/\tA", m) && !X::parseLine("pinned\t0", m) && !X::parseLine("shownx\t1\t2\t00000000", m));
        CHECK(X::parseLine("shown\t1\t2", m) && m.index == -1);                   // ours but malformed: skipped
        CHECK(X::parseLine("shown\t1\t2\tABCDEF01", m) && m.index == -1);         // upper-case hex is not ours
        CHECK(X::parseLine("shown\t-1\t2\t00000000", m) && m.index == -1);
        CHECK(X::parseLine("shown\t1\t9999999999999\t00000000", m) && m.index == -1);
        CHECK(X::sessionLine(-1, now, h).empty() && X::sessionLine(0, 0, h).empty());
        CHECK(X::hex8(0x1u) == "00000001" && X::hex8(0xffffffffu) == "ffffffff");
    }

    // texts
    CHECK(X::closedNotice(1) == "Closed 1 unused tab" && X::closedNotice(3) == "Closed 3 unused tabs");
    CHECK(X::daysValue(0) == "Off" && X::daysValue(14) == "14 days");
    CHECK(X::askTitle(7) == "Close tabs unused for 7 days?");

    std::printf(fails ? "%d FAILED\n" : "all tab autoclose tests passed\n", fails);
    return fails ? 1 : 0;
}
