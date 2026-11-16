// OMNI_HISTORY_PLUS_V1 host test: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_history_plus.cpp -o t && ./t
// Checks the pure header: history.txt line parse / format (and that the bytes it writes still load with the loader of
// older builds, copied below), sites, search words, local days and their labels, the grouped rows, D-pad / day / page
// moves, and the range and site deletes.
#include "OmniHistoryPlus.h"
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace H = OmniHistoryPlus;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); } } while (0)

struct Visit { long long time; std::string url, title; };

// The loader of every build before this one (omniHistoryLoad in OmniBrowser.cpp), over a string instead of a FILE.
static std::vector<Visit> oldLoad(const std::string& data)
{
    std::vector<Visit> out;
    size_t at = 0;
    while (at < data.size()) {
        size_t nl = data.find('\n', at);
        std::string s = data.substr(at, nl == std::string::npos ? std::string::npos : nl + 1 - at);
        at = nl == std::string::npos ? data.size() : nl + 1;
        if (s.size() > 4095) s.resize(4095);   // fgets(line, 4096)
        while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
        const size_t a = s.find('\t'), b = a == std::string::npos ? a : s.find('\t', a + 1);
        if (b == std::string::npos) continue;
        Visit v { atoll(s.substr(0, a).c_str()), s.substr(a + 1, b - a - 1), s.substr(b + 1) };
        if (v.url.rfind("https://", 0) == 0 || v.url.rfind("http://", 0) == 0) out.push_back(v);
    }
    return out;
}

int main()
{
    // --- lines ---
    Visit v {};
    CHECK(H::parseLine("1700000000\thttps://example.com/a\tExample A\n", v));
    CHECK(v.time == 1700000000 && v.url == "https://example.com/a" && v.title == "Example A");
    CHECK(H::parseLine("5\thttp://x.org/\t\r\n", v) && v.title.empty() && v.url == "http://x.org/");
    CHECK(H::parseLine("5\thttp://x.org/\ta\tb", v) && v.title == "a\tb");   // everything after the second TAB
    CHECK(!H::parseLine("5\tomni://pages/start\tStart", v));                 // web addresses only
    CHECK(!H::parseLine("5\thttps://no-title", v));
    CHECK(!H::parseLine("", v));
    std::vector<Visit> hist { { 100, "https://a.com/1", "One" }, { 200, "http://www.B.com:8080/x?q=1", "Two" }, { 300, "https://a.com/2", "" } };
    const std::string data = H::serialize(hist);
    CHECK(data == "100\thttps://a.com/1\tOne\n200\thttp://www.B.com:8080/x?q=1\tTwo\n300\thttps://a.com/2\t\n");
    const auto back = oldLoad(data);
    CHECK(back.size() == 3);
    for (size_t i = 0; i < back.size() && i < hist.size(); ++i)
        CHECK(back[i].time == hist[i].time && back[i].url == hist[i].url && back[i].title == hist[i].title);
    CHECK(oldLoad(H::serialize(std::vector<Visit> {})).empty());   // "Clear all": the empty file older builds read as empty

    // --- sites ---
    CHECK(H::hostOf("https://www.Example.COM/path") == "example.com");
    CHECK(H::hostOf("http://user:pw@host.net:81/a") == "host.net");
    CHECK(H::hostOf("https://[::1]:8443/") == "[::1]");
    CHECK(H::hostOf("https://www./") == "www.");
    CHECK(H::hostOf("https://m.youtube.com?x") == "m.youtube.com");
    CHECK(H::hostOf("no scheme") == "");

    // --- search ---
    CHECK((H::words("  Foo   bAR ") == std::vector<std::string> { "foo", "bar" }));
    CHECK(H::words("   ").empty());
    const Visit yt { 1, "https://www.youtube.com/watch?v=1", "Lofi Beats - YouTube" };
    CHECK(H::matches(yt, H::words("")));
    CHECK(H::matches(yt, H::words("lofi")));
    CHECK(H::matches(yt, H::words("YOUTUBE.com")));
    CHECK(H::matches(yt, H::words("beats youtube")));
    CHECK(!H::matches(yt, H::words("beats vimeo")));
    CHECK(!H::matches(yt, H::words("watch")));   // the path is not searched: title and site only

    // --- days (2026-11-16 is a Monday) ---
    const long long mon = 20773;   // days since 1970-01-01 for 2026-11-16
    const H::Civil c = H::civil(mon);
    CHECK(c.year == 2026 && c.month == 11 && c.day == 16 && c.weekday == 1);
    CHECK(H::civil(0).year == 1970 && H::civil(0).weekday == 4);
    CHECK(H::civil(-1).year == 1969 && H::civil(-1).month == 12 && H::civil(-1).day == 31);
    CHECK(H::dayKey(0, 0) == 0 && H::dayKey(86399, 0) == 0 && H::dayKey(86400, 0) == 1 && H::dayKey(-1, 0) == -1);
    const long long noonUtc = mon * 86400 + 12 * 3600;
    CHECK(H::dayKey(noonUtc, 0) == mon);
    CHECK(H::dayKey(mon * 86400 + 3600, -2 * 3600) == mon - 1);    // 01:00 UTC is still Sunday at UTC-2
    CHECK(H::dayKey(mon * 86400 - 3600, 9 * 3600) == mon);         // 23:00 UTC Sunday is Monday in Tokyo
    CHECK(H::dayLabel(mon, mon) == "Today");
    CHECK(H::dayLabel(mon - 1, mon) == "Yesterday");
    CHECK(H::dayLabel(mon - 2, mon) == "Saturday, 14 November");
    CHECK(H::dayLabel(mon - 6, mon) == "Tuesday, 10 November");
    CHECK(H::dayLabel(mon - 7, mon) == "9 November");
    CHECK(H::dayLabel(mon - 365, mon) == "16 November 2025");
    CHECK(H::dayLabel(mon + 1, mon) == "17 November");             // a clock running ahead: a date, never "Tomorrow"
    CHECK(H::timeLabel(noonUtc, noonUtc + 5, 0) == "just now");
    CHECK(H::timeLabel(noonUtc, noonUtc + 600, 0) == "10 min ago");
    CHECK(H::timeLabel(noonUtc, noonUtc + 7200, 0) == "12:00");
    CHECK(H::timeLabel(noonUtc, noonUtc + 7200, 3600 + 1800) == "13:30");
    CHECK(H::timeLabel(noonUtc + 60, noonUtc, 0) == "12:01");      // in the future: the clock

    // --- rows ---
    std::vector<Visit> h;
    const long long now = noonUtc;
    h.push_back({ now - 3 * 86400, "https://old.org/", "Old page" });            // Friday
    h.push_back({ now - 86400 - 60, "https://www.news.com/a", "News A" });       // Yesterday
    h.push_back({ now - 86400, "https://news.com/b", "News B" });                 // Yesterday
    h.push_back({ now - 7200, "https://shop.net/", "Shop" });                    // Today 10:00
    h.push_back({ now - 1800, "https://www.news.com/c", "News C" });             // Today 11:30
    h.push_back({ now - 3600 * 5, "https://late.io/", "Clock set back" });       // Today 07:00, out of order
    size_t matched = 0;
    auto rows = H::buildRows(h, "", 0, &matched);
    CHECK(matched == 6);
    // Clear, [Today] C, Shop, Late, [Yesterday] B, A, [Fri] Old
    CHECK(rows.size() == 10);
    CHECK(rows[0].kind == H::RowClear);
    CHECK(rows[1].kind == H::RowDay && rows[1].day == mon);
    CHECK(rows[2].kind == H::RowVisit && rows[2].index == 4);
    CHECK(rows[3].index == 3 && rows[4].index == 5);
    CHECK(rows[5].kind == H::RowDay && rows[5].day == mon - 1);
    CHECK(rows[6].index == 2 && rows[7].index == 1);
    CHECK(rows[8].kind == H::RowDay && rows[8].day == mon - 3);
    CHECK(rows[9].index == 0);
    CHECK(H::firstVisit(rows) == 2);
    auto found = H::buildRows(h, "NEWS", 0, &matched);
    CHECK(matched == 3 && found.size() == 1 + 2 + 3);   // Clear, Today, C, Yesterday, B, A
    CHECK(found[2].index == 4 && found[4].index == 2 && found[5].index == 1);
    auto none = H::buildRows(h, "zzz", 0, &matched);
    CHECK(matched == 0 && none.size() == 1 && H::firstVisit(none) == 0);
    CHECK(H::buildRows(std::vector<Visit> {}, "", 0).size() == 1);

    // --- moves ---
    CHECK(H::step(rows, 0, 1) == 2);      // over the "Today" heading
    CHECK(H::step(rows, 2, -1) == 0);
    CHECK(H::step(rows, 4, 1) == 6);      // over "Yesterday"
    CHECK(H::step(rows, 9, 1) == 9);      // the end
    CHECK(H::step(rows, 0, -1) == 0);
    CHECK(H::step(rows, 2, 9) == 9);      // a page down, clamped
    CHECK(H::step(rows, 9, -9) == 0);
    CHECK(H::step(rows, 7, 1) == 9);      // onto a heading going down: the next visit
    CHECK(H::snap(rows, 8, -1) == 7);
    CHECK(H::dayJump(rows, 0, 1) == 2);   // Clear -> Today's first
    CHECK(H::dayJump(rows, 2, 1) == 6);   // Today -> Yesterday
    CHECK(H::dayJump(rows, 6, 1) == 9);
    CHECK(H::dayJump(rows, 9, 1) == 9);   // the last day: stays at the end
    CHECK(H::dayJump(rows, 4, -1) == 2);  // later visit -> this day's first
    CHECK(H::dayJump(rows, 6, -1) == 2);  // a day's first -> the previous day's first
    CHECK(H::dayJump(rows, 2, -1) == 0);  // the first day -> Clear history
    CHECK(H::dayJump(rows, 0, -1) == 0);
    CHECK(H::pageCount(10, 9) == 2 && H::pageCount(1, 9) == 1 && H::pageCount(0, 9) == 1 && H::pageCount(18, 9) == 2);
    CHECK(H::scrollFor(rows, 2, 0, 4) == 0);
    CHECK(H::scrollFor(rows, 6, 0, 4) == 3);   // 6 at the bottom of 4 rows
    CHECK(H::scrollFor(rows, 6, 6, 4) == 5);   // scrolling up onto a day's first shows its heading
    CHECK(H::scrollFor(rows, 9, 0, 9) == 1);   // clamped to the end
    CHECK(H::scrollFor(rows, 0, 5, 4) == 0);

    // --- deletes ---
    CHECK(H::rangeStart(H::LastHour, now, 0) == now - 3600);
    CHECK(H::rangeStart(H::Today, now, 0) == mon * 86400);
    CHECK(H::rangeStart(H::Today, now, 3600) == mon * 86400 - 3600);
    CHECK(H::rangeStart(H::AllTime, now, 0) == LLONG_MIN);
    CHECK(H::countSince(h, H::rangeStart(H::LastHour, now, 0)) == 1);
    CHECK(H::countSince(h, H::rangeStart(H::Today, now, 0)) == 3);
    CHECK(H::countSince(h, H::rangeStart(H::Today, now, 13 * 3600)) == 1);    // at UTC+13 it is 01:00: only the 11:30 UTC visit
    CHECK(H::countSince(h, H::rangeStart(H::Today, now, -13 * 3600)) == 3);   // at UTC-13 it is 23:00 Sunday: B (24 h ago) is out
    CHECK(H::countSince(h, H::rangeStart(H::AllTime, now, 0)) == 6);
    CHECK(H::countHost(h, "news.com") == 3 && H::countHost(h, "") == 0);
    {
        auto x = h;
        CHECK(H::eraseSince(x, H::rangeStart(H::LastHour, now, 0)) == 1 && x.size() == 5);
        CHECK(H::eraseSince(x, H::rangeStart(H::Today, now, 0)) == 2 && x.size() == 3);
        CHECK(x[0].url == "https://old.org/" && x[2].url == "https://news.com/b");   // order kept
        CHECK(H::eraseHost(x, "news.com") == 2 && x.size() == 1);
        CHECK(H::eraseHost(x, "") == 0);
        CHECK(H::eraseSince(x, LLONG_MIN) == 1 && x.empty());
        CHECK(H::serialize(x).empty());
    }
    {
        auto x = h;
        CHECK(H::eraseHost(x, H::hostOf("https://www.news.com/zzz")) == 3);
        const auto again = oldLoad(H::serialize(x));
        CHECK(again.size() == 3 && again[0].url == "https://old.org/" && again[1].url == "https://shop.net/" && again[2].url == "https://late.io/");
    }
    CHECK(H::visits(1) == "1 visit" && H::visits(2) == "2 visits" && H::visits(0) == "0 visits");
    CHECK(std::string(H::rangeName(H::LastHour)) == "Last hour" && std::string(H::rangeName(H::Today)) == "Today" && std::string(H::rangeName(H::AllTime)) == "All time");

    printf("%s: %d checks, %d failed\n", failures ? "FAIL" : "PASS", checks, failures);
    return failures ? 1 : 0;
}
