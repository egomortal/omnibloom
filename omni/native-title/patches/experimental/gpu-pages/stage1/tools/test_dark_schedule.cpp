// OMNI_DARK_SCHEDULE_V1: host test of the pure part (engine/entry/OmniDarkSchedule.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_dark_schedule.cpp -o t && ./t
#include "OmniDarkSchedule.h"
#include <cstdio>
#include <string>

namespace ODSC = OmniDarkSchedule;
namespace ONL = OmniNightLight;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define EQ(a, b) do { ++checks; const std::string x_ = (a), y_ = (b); if (x_ != y_) { ++fails; printf("FAIL %s:%d: \"%s\" != \"%s\"\n", __FILE__, __LINE__, x_.c_str(), y_.c_str()); } } while (0)

int main()
{
    // choices / effective style
    for (int v = -1; v <= 4; ++v) CHECK(ODSC::validChoice(v) == (v >= 0 && v <= 3));
    CHECK(ODSC::effective(0, true) == 0 && ODSC::effective(1, true) == 1 && ODSC::effective(2, false) == 2);
    CHECK(ODSC::effective(3, true) == 2 && ODSC::effective(3, false) == 0);
    CHECK(ODSC::effective(9, true) == 2 && ODSC::effective(-5, true) == 0);   // clamped
    // cycling: Off -> Natural -> Forced -> Schedule -> Off, and back
    CHECK(ODSC::step(0, 1) == 1 && ODSC::step(1, 1) == 2 && ODSC::step(2, 1) == 3 && ODSC::step(3, 1) == 0);
    CHECK(ODSC::step(0, -1) == 3 && ODSC::step(3, -1) == 2 && ODSC::step(1, -1) == 0);

    // the window is Night light's (wraps past midnight; start == end never)
    ONL::Settings s;   // 21:00-07:00 default, mode Off: the window still counts
    CHECK(s.mode == ONL::kOff);
    CHECK(ODSC::nightNow(s, 21 * 60) && ODSC::nightNow(s, 23 * 60 + 59) && ODSC::nightNow(s, 0) && ODSC::nightNow(s, 6 * 60 + 59));
    CHECK(!ODSC::nightNow(s, 7 * 60) && !ODSC::nightNow(s, 12 * 60) && !ODSC::nightNow(s, 20 * 60 + 59));
    s.start = 8 * 60; s.end = 17 * 60;   // daytime window, no wrap
    CHECK(ODSC::nightNow(s, 8 * 60) && ODSC::nightNow(s, 16 * 60 + 59) && !ODSC::nightNow(s, 17 * 60) && !ODSC::nightNow(s, 7 * 60));
    s.start = s.end = 22 * 60;
    for (int m = 0; m < 24 * 60; m += 7) CHECK(!ODSC::nightNow(s, m));
    // with the night light's own clock (UTC + offset): 22:30 UTC, +02:00 -> 00:30 local: night
    ONL::Settings d;
    CHECK(ODSC::nightNow(d, ONL::localMinute(22LL * 3600 + 30 * 60, 2 * 3600)));
    CHECK(ODSC::nightNow(d, ONL::localMinute(10LL * 3600, -5 * 3600)));    // 10:00 UTC at -05:00 = 05:00 local: night
    CHECK(!ODSC::nightNow(d, ONL::localMinute(10LL * 3600, 2 * 3600)));    // 12:00 local: day

    // boundary detection: the first sample only records
    ODSC::Edge e;
    CHECK(!e.changed(false));
    CHECK(!e.changed(false));
    CHECK(e.changed(true));
    CHECK(!e.changed(true));
    CHECK(e.changed(false));
    e.reset();
    CHECK(!e.changed(true));

    // texts
    EQ(ODSC::choiceName(0), "Off"); EQ(ODSC::choiceName(1), "Natural"); EQ(ODSC::choiceName(2), "Forced");
    EQ(ODSC::choiceName(3), "Night light schedule");
    EQ(ODSC::choiceValue(2, true), "Forced");
    EQ(ODSC::choiceValue(3, true), "Night light schedule (dark now)");
    EQ(ODSC::choiceValue(3, false), "Night light schedule (light now)");
    EQ(ODSC::detail(21 * 60, 7 * 60, 23 * 60 + 14, true), "Dark 21:00-07:00: on now, until 07:00 (console time 23:14)");
    EQ(ODSC::detail(21 * 60, 7 * 60, 12 * 60, false),
        "Dark 21:00-07:00: off now, starts at 21:00 (console time 12:00); set the hours with Night light: Scheduled");
    EQ(ODSC::detail(60, 60, 0, true), "Night light from and until are the same time: never dark");
    EQ(ODSC::setNotice(0, false, 0, 0), "Dark mode: Off");
    EQ(ODSC::setNotice(1, false, 0, 0), "Dark mode: Natural (sites with a dark theme use it)");
    EQ(ODSC::setNotice(2, false, 0, 0), "Dark mode: Forced (every page dark)");
    EQ(ODSC::setNotice(3, true, 21 * 60, 7 * 60), "Dark mode: Night light schedule (every page dark 21:00-07:00, on now)");
    EQ(ODSC::setNotice(3, false, 21 * 60, 7 * 60), "Dark mode: Night light schedule (every page dark 21:00-07:00, off now)");
    EQ(ODSC::setNotice(3, false, 5, 5), "Dark mode: Night light schedule (from and until are the same time: never dark)");
    EQ(ODSC::edgeNotice(true, 21 * 60, 7 * 60), "Dark pages on until 07:00 (night light schedule)");
    EQ(ODSC::edgeNotice(false, 21 * 60, 7 * 60 + 30), "Dark pages off until 21:00 (night light schedule)");
    EQ(ODSC::siteDefault(0, true), "Default (off)"); EQ(ODSC::siteDefault(1, true), "Default (natural)");
    EQ(ODSC::siteDefault(2, false), "Default (forced)");
    EQ(ODSC::siteDefault(3, true), "Default (schedule, dark now)"); EQ(ODSC::siteDefault(3, false), "Default (schedule, light now)");

    // per-site priority as omniDkWant / omniDkForced compute it, with the effective style
    auto want = [](int site, int choice, bool night) { const int g = ODSC::effective(choice, night); return site < 0 ? g > 0 : site == 1; };
    auto forced = [](int site, int choice, bool night) { const int g = ODSC::effective(choice, night); return site == 1 || (site < 0 && g == 2); };
    CHECK(want(-1, 3, true) && forced(-1, 3, true));
    CHECK(!want(-1, 3, false) && !forced(-1, 3, false));
    CHECK(!want(0, 3, true) && !forced(0, 3, true));     // Never dark beats the night
    CHECK(want(1, 3, false) && forced(1, 3, false));     // Always dark beats the day

    printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
