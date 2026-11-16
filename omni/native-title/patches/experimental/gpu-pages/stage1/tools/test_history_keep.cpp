// OMNI_HISTORY_KEEP_V1 host test for OmniHistoryKeep.h (written by apply_history_keep.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_history_keep.cpp -o t && ./t
#include "OmniHistoryKeep.h"
#include <cstdio>

namespace K = OmniHistoryKeep;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

struct Visit { long long time; std::string url, title; };

int main()
{
    const long long now = 1793793600, day = 86400;

    // tokens / file
    CHECK(K::parse("") == K::Forever);
    CHECK(K::parse("garbage\n") == K::Forever);
    CHECK(K::parse("\n  1w \r\n") == K::Week1);
    CHECK(K::parse("off") == K::DontSave);
    for (int k = 0; k < K::KeepCount; ++k) CHECK(K::parse(K::serialize(k)) == k);
    CHECK(K::clampKeep(-1) == K::Forever && K::clampKeep(99) == K::Forever);
    CHECK(std::string(K::name(K::DontSave)) == "Don't save history");

    // cutoffs
    CHECK(K::cutoff(K::Forever, now) == LLONG_MIN);
    CHECK(K::cutoff(K::DontSave, now) == LLONG_MIN);
    CHECK(K::cutoff(K::Day1, now) == now - day);
    CHECK(K::cutoff(K::Week1, now) == now - 7 * day);
    CHECK(K::cutoff(K::Month1, now) == now - 30 * day);
    CHECK(K::cutoff(K::Months3, now) == now - 90 * day);
    CHECK(K::records(K::Forever) && K::records(K::Day1) && !K::records(K::DontSave));
    CHECK(!K::prunes(K::Forever) && !K::prunes(K::DontSave) && K::prunes(K::Months3));

    // steps: D-pad stops at the ends, Cross wraps forward
    CHECK(K::step(K::Forever, -1, false) == K::Forever);
    CHECK(K::step(K::Forever, 1, false) == K::Months3);
    CHECK(K::step(K::Day1, 1, false) == K::DontSave);
    CHECK(K::step(K::DontSave, 1, false) == K::DontSave);
    CHECK(K::step(K::DontSave, -1, false) == K::Day1);
    CHECK(K::step(K::DontSave, 1, true) == K::Forever);
    CHECK(K::step(K::Week1, -1, true) == K::Day1);   // Cross always forward

    // plan + erase (in memory)
    std::vector<Visit> h = {
        { now - 100 * day, "https://old.example/", "old" },
        { now - 8 * day, "https://week.example/", "8 days" },
        { now - 2 * day, "https://two.example/", "2 days" },
        { now - day, "https://edge.example/", "exactly 1 day" },   // == cutoff for 1 day: kept
        { now - 60, "https://new.example/", "a minute" },
    };
    K::Plan p = K::plan(h, K::Week1, now);
    CHECK(p.keep == 3 && p.drop == 2);
    p = K::plan(h, K::Forever, now);
    CHECK(p.keep == 5 && p.drop == 0);
    p = K::plan(h, K::DontSave, now);
    CHECK(p.drop == 0);
    p = K::plan(h, K::Months3, now);
    CHECK(p.drop == 1);
    {
        auto c = h;
        CHECK(K::eraseBefore(c, LLONG_MIN) == 0 && c.size() == 5);
        CHECK(K::eraseBefore(c, K::cutoff(K::Day1, now)) == 3);
        CHECK(c.size() == 2 && c[0].url == "https://edge.example/" && c[1].url == "https://new.example/");
        // agrees with the clear-range filter it mirrors
        auto d = h;
        const size_t recent = OmniClearRange::eraseSince(d, K::cutoff(K::Day1, now));
        CHECK(recent == 2 && d.size() == 3 && d[2].url == "https://two.example/");
    }
    {   // unordered times (clock change): by time, not position
        std::vector<Visit> u = { { now, "https://a/", "" }, { now - 10 * day, "https://b/", "" }, { now - 1, "https://c/", "" } };
        CHECK(K::eraseBefore(u, now - day) == 1 && u.size() == 2 && u[0].url == "https://a/" && u[1].url == "https://c/");
    }

    // the file text (writer thread)
    const std::string file = OmniHistoryPlus::serialize(h);
    size_t dropped = 99;
    std::string out = K::pruneText(file, K::cutoff(K::Week1, now), &dropped);
    CHECK(dropped == 2);
    {
        auto c = h;
        K::eraseBefore(c, K::cutoff(K::Week1, now));
        CHECK(out == OmniHistoryPlus::serialize(c));   // the file and the memory agree
    }
    CHECK(K::pruneText(file, LLONG_MIN, &dropped) == file && dropped == 0);
    CHECK(K::pruneText(out, K::cutoff(K::Week1, now), &dropped) == out && dropped == 0);   // idempotent
    CHECK(K::pruneText("", now, &dropped).empty() && dropped == 0);
    {   // lines the loader skips stay; CRLF lines and a last line without newline handled
        const std::string odd = "garbage\n"
                                "5\tomni://pages/\tnot web\n"
                                "10\thttps://old/\tx\r\n"
                                + std::to_string(now) + "\thttps://new/\ttitle\twith tab\r\n"
                                "20\thttp://old2/\t";
        out = K::pruneText(odd, now - day, &dropped);
        CHECK(dropped == 2);
        CHECK(out == "garbage\n5\tomni://pages/\tnot web\n" + std::to_string(now) + "\thttps://new/\ttitle\twith tab\r\n");
    }
    {   // loaded back with the loader's rules: only recent web visits
        std::vector<Visit> back;
        size_t i = 0;
        while (i < out.size()) {
            size_t e = out.find('\n', i);
            e = e == std::string::npos ? out.size() : e + 1;
            Visit v {};
            if (OmniHistoryPlus::parseLine(out.substr(i, e - i), v)) back.push_back(v);
            i = e;
        }
        CHECK(back.size() == 1 && back[0].title == "title\twith tab");
    }

    // schedule
    CHECK(K::due(100, 100) && K::due(101, 100) && !K::due(99, 100));
    CHECK(K::due(5u, 0xfffffff0u));          // across the 49-day wrap
    CHECK(!K::due(0xfffffff0u, 5u));
    CHECK(K::kPruneEveryMs == 3600000u && K::kChangeDelayMs == 30000u);

    // texts
    CHECK(K::rowDetail(K::Forever, 5, true) == "Visits stay until you delete them");
    CHECK(K::rowDetail(K::Week1, 312, true) == "Visits older than 1 week are deleted automatically (312 visits now)");
    CHECK(K::rowDetail(K::Day1, 1, true) == "Visits older than 1 day are deleted automatically (1 visit now)");
    CHECK(K::rowDetail(K::Week1, 0, true) == "Visits older than 1 week are deleted automatically");
    CHECK(K::rowDetail(K::Week1, 9, false) == "Visits older than 1 week are deleted automatically");
    CHECK(K::rowDetail(K::DontSave, 0, false).find("Cookies and site data are still kept") != std::string::npos);
    CHECK(K::changeNotice(K::Months3) == "History older than 3 months will be deleted automatically");
    CHECK(K::changeNotice(K::DontSave).find("cookies") != std::string::npos);
    CHECK(K::askBody(312).find("The 312 visits already saved") != std::string::npos);
    CHECK(K::clearedNotice(1) == "History cleared: 1 visit removed");

    std::printf("%s: %d/%d checks passed\n", fails ? "FAILED" : "ok", checks - fails, checks);
    return fails ? 1 : 0;
}
