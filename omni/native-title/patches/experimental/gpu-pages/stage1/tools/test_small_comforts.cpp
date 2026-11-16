// OMNI_SMALL_COMFORTS_V1 host test for engine/entry/OmniSmallComforts.h (written by apply_small_comforts.py).
// g++ -std=c++17 -Wall -Wextra -Werror -I <tree>/engine/entry test_small_comforts.cpp -o t && ./t
#include "OmniSmallComforts.h"
#include <cstdio>
#include <string>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniSmallComforts;
using Ev = SleepTimer::Event;

static void sleepTimer(uint32_t t0)
{
    SleepTimer s;
    char v[32];
    CHECK(!s.on()); CHECK(s.tick(t0) == Ev::None);
    s.value(t0, v, sizeof v); CHECK(std::string(v) == "Off");
    // the cycle: 15, 30, 60, 90, off
    CHECK(s.cycle(t0) == 15); CHECK(s.cycle(t0) == 30); CHECK(s.cycle(t0) == 60); CHECK(s.cycle(t0) == 90);
    CHECK(s.cycle(t0) == 0); CHECK(!s.on()); CHECK(s.cycle(t0) == 15);
    s.value(t0, v, sizeof v); CHECK(std::string(v) == "15 min left");
    s.value(t0 + 60000 + 1, v, sizeof v); CHECK(std::string(v) == "14 min left");
    // nothing until a minute before; the warning once; then the fire once, and off
    CHECK(s.tick(t0 + 1000) == Ev::None);
    CHECK(s.tick(t0 + 14 * 60000 - 1) == Ev::None);
    CHECK(s.tick(t0 + 14 * 60000) == Ev::Warn);
    CHECK(s.tick(t0 + 14 * 60000 + 10) == Ev::None);
    s.value(t0 + 14 * 60000 + 30000, v, sizeof v); CHECK(std::string(v) == "1 min left");
    CHECK(s.tick(t0 + 15 * 60000 - 1) == Ev::None);
    CHECK(s.tick(t0 + 15 * 60000) == Ev::Fire);
    CHECK(!s.on()); CHECK(s.tick(t0 + 15 * 60000 + 5) == Ev::None);
    // a late tick (the shell was busy): the fire wins over the warning
    s.set(30, t0);
    CHECK(s.on()); CHECK(s.minutes() == 30);
    CHECK(s.tick(t0 + 40 * 60000) == Ev::Fire); CHECK(!s.on());
    // restarting re-arms the warning
    s.set(15, t0); CHECK(s.tick(t0 + 14 * 60000 + 1) == Ev::Warn);
    s.set(15, t0 + 14 * 60000 + 1); CHECK(s.tick(t0 + 14 * 60000 + 2) == Ev::None);
    CHECK(s.tick(t0 + 28 * 60000 + 1) == Ev::Warn);
    s.set(42, t0); CHECK(!s.on());
    s.set(90, t0); CHECK(s.minutesLeft(t0) == 90); s.off(); CHECK(s.minutesLeft(t0) == 0); CHECK(s.tick(t0 + 99 * 60000) == Ev::None);
    char tiny[1] = { 'x' }; s.value(t0, tiny, 0); CHECK(tiny[0] == 'x');
}

static void batteryGauge()
{
    CHECK(batteryBars(kPowerUnknown) == -1); CHECK(batteryBars(kPowerEmpty) == 0); CHECK(batteryBars(kPowerLow) == 1);
    CHECK(batteryBars(kPowerMedium) == 2); CHECK(batteryBars(kPowerFull) == 3); CHECK(batteryBars(kPowerWired) == -1);
    CHECK(batteryBars(kPowerMax) == -1); CHECK(batteryBars(99) == -1);
    BatteryGauge g;
    int a = 1, b = 2;
    CHECK(g.bars() == -1);
    CHECK(g.due(5, &a));
    CHECK(g.update(5, &a, kPowerMedium)); CHECK(g.bars() == 2);
    CHECK(!g.due(6, &a)); CHECK(!g.due(5 + 29999, &a)); CHECK(g.due(5 + 30000, &a));
    CHECK(!g.update(5 + 30000, &a, kPowerMedium));   // same bars: no redraw
    CHECK(g.update(5 + 60000, &a, kPowerLow)); CHECK(g.bars() == 1);
    // another active controller: asked again, but not more often than every 2 s
    CHECK(!g.due(5 + 60000 + 1999, &b)); CHECK(g.due(5 + 60000 + 2000, &b));
    CHECK(g.update(5 + 62000, &b, kPowerWired)); CHECK(g.bars() == -1);
    CHECK(!g.update(5 + 92000, &b, kPowerUnknown));
    CHECK(!g.update(5 + 122000, nullptr, kPowerFull)); CHECK(g.bars() == -1);   // no controller: hidden
    // the tick counter wraps (49.7 days)
    BatteryGauge w;
    w.update(0xFFFFFF00u, &a, kPowerFull);
    CHECK(!w.due(0xFFFFFFF0u, &a)); CHECK(!w.due(100, &a)); CHECK(w.due(0xFFFFFF00u + 30000u, &a));
    CHECK(&battery() == &battery());
}

static void doneFile()
{
    // parse
    auto e = parseDone("a1\tFirst video\nbad line\n\tno id\nb-2_\tSecond\r\n../x\tbad id\nc3\t  \n");
    CHECK(e.size() == 3);
    CHECK(e[0].id == "a1" && e[0].title == "First video");
    CHECK(e[1].id == "b-2_" && e[1].title == "Second");
    CHECK(e[2].id == "c3" && e[2].title == "a download");
    CHECK(parseDone("").empty()); CHECK(parseDone("x").empty());
    CHECK(parseDone("x\tA\x01" "B\x7f" "C")[0].title == "A B C");
    CHECK(parseDone(std::string(65, 'a') + "\tlong id").empty());
    CHECK(parseDone("d\tone\nd\ttwo\n").size() == 1 && parseDone("d\tone\nd\ttwo\n")[0].title == "two");
    std::string many;
    for (int i = 0; i < 12; ++i) many += "id" + std::to_string(i) + "\tT" + std::to_string(i) + "\n";
    auto m = parseDone(many);
    CHECK(m.size() == kDoneMaxEntries); CHECK(m.front().id == "id4"); CHECK(m.back().id == "id11");
    const std::string longTitle(200, 'x');
    CHECK(parseDone("k\t" + longTitle)[0].title.size() == kDoneMaxTitle);
    std::string utf = "k\t" + std::string(76, 'y') + "\xc3\xa9\xc3\xa9\xc3\xa9";   // 82 bytes: cut before the 2-byte e-acute
    const std::string t = parseDone(utf)[0].title;
    CHECK(t.size() <= kDoneMaxTitle); CHECK(t.compare(t.size() - 3, 3, "...") == 0);
    CHECK((static_cast<unsigned char>(t[t.size() - 4]) & 0xC0) != 0xC0);   // no lead byte left without its tail
    CHECK(clipUtf8("abc", 3) == "abc"); CHECK(clipUtf8("abcd", 3) == "...");
    std::string huge(5000, 'z'); huge += "\nlate\tafter the cap\n";
    CHECK(parseDone(huge).empty());

    // stamps
    DoneTracker d;
    FileStamp none, s1 { true, 100, 20, 7 }, s2 { true, 100, 20, 8 };
    CHECK(d.restamp(none)); CHECK(!d.restamp(none)); CHECK(d.restamp(s1)); CHECK(!d.restamp(s1)); CHECK(d.restamp(s2));
    // the first read only primes: what was there at start is never announced
    DoneTracker t1;
    CHECK(t1.take(parseDone("old\tOld one\n"), true).empty());
    CHECK(t1.take(parseDone("old\tOld one\n"), true).empty());
    CHECK(t1.take(parseDone("old\tOld one\nnew\tNew one\n"), true) == "Downloaded: New one");
    CHECK(t1.take(parseDone("old\tOld one\nnew\tNew one\n"), true).empty());   // once
    CHECK(t1.take(parseDone("new\tNew one\nx\tX\ny\tY\n"), true) == "Downloaded: Y (and 1 more)");
    // on the Downloads tab: recorded, not announced (and not later either)
    CHECK(t1.take(parseDone("z\tZ\n"), false).empty());
    CHECK(t1.take(parseDone("z\tZ\n"), true).empty());
    // no file at start, then one: the first finished download is announced
    DoneTracker t2;
    CHECK(t2.take({}, true).empty());
    CHECK(t2.take(parseDone("j1\tMy file.pdf\n"), true) == "Downloaded: My file.pdf");
    // a restarted worker rewrites the file with only its new job: old ids are still known, the new one is announced
    CHECK(t2.take(parseDone("j2\tAfter restart\n"), true) == "Downloaded: After restart");
    // the seen list is bounded
    DoneTracker t3;
    t3.take({}, true);
    for (int i = 0; i < 100; ++i) CHECK(!t3.take(parseDone("n" + std::to_string(i) + "\tN\n"), true).empty());
}

int main()
{
    sleepTimer(1000);
    sleepTimer(0xFFFFFFFFu - 20u * 60000u);   // across the 32-bit tick wrap
    batteryGauge();
    doneFile();
    std::printf("%d/%d checks passed\n", checks - fails, checks);
    return fails ? 1 : 0;
}
