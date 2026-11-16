// OMNI_TAB_SESSIONS_V1: host tests for OmniTabSessions.h (pure part of named tab sessions).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_sessions.cpp -o t && ./t
#include "OmniTabSessions.h"
#include <cstdio>
#include <cstdlib>

namespace TS = OmniTabSessions;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static TS::Session mk(const char* name, int n, long long at = 1000)
{
    TS::Session s; s.name = name; s.savedAt = at;
    for (int i = 0; i < n; ++i) s.tabs.push_back({ "https://site" + std::to_string(i) + ".com/p", "Title " + std::to_string(i) });
    return s;
}

int main()
{
    setenv("TZ", "UTC", 1); tzset();
    const time_t nov16 = 1794830400;   // 2026-11-16 12:00 UTC (Monday)

    // --- round trip --------------------------------------------------------------------------------------------
    {
        std::vector<TS::Session> l { mk("Movie night", 3, 111), mk("Research", 2, 222) };
        l[0].tabs[1].title = "tab\there\nnewline";
        const std::string text = TS::serialize(l);
        CHECK(text.rfind("omni-sessions\t1\n", 0) == 0);
        const auto back = TS::parse(text);
        CHECK(back.size() == 2);
        CHECK(back[0].name == "Movie night" && back[0].savedAt == 111 && back[0].tabs.size() == 3);
        CHECK(back[0].tabs[1].title == "tab here newline");
        CHECK(back[1].name == "Research" && back[1].tabs[1].url == "https://site1.com/p");
        CHECK(TS::serialize(back) == TS::serialize(TS::parse(TS::serialize(back))));
    }
    // --- tolerant parse ----------------------------------------------------------------------------------------
    {
        const std::string text =
            "omni-sessions\t1\r\n"
            "tab\thttps://orphan.com/\tno session yet\n"
            "session\t5\tEmpty\n"
            "session\t6\t\n"
            "tab\tjavascript:alert(1)\tbad\n"
            "tab\tfile:///etc/passwd\tbad\n"
            "tab\thttp://ok.com/\n"
            "garbage line\n"
            "session\t7\tdup\n"
            "tab\thttps://a.com/\tA\r\n"
            "session\t8\tDUP\n"
            "tab\thttps://b.com/\tB\n";
        const auto l = TS::parse(text);
        CHECK(l.size() == 3);                                  // "Empty" (no tabs) dropped
        CHECK(l[0].name == "Session" && l[0].savedAt == 6 && l[0].tabs.size() == 1 && l[0].tabs[0].url == "http://ok.com/" && l[0].tabs[0].title.empty());
        CHECK(l[1].name == "dup" && l[1].tabs[0].title == "A");   // \r stripped
        CHECK(l[2].name == "DUP (2)");                         // names stay unique (case-insensitive)
        CHECK(TS::parse("").empty() && TS::parse("session\t1\tx").empty());
        CHECK(TS::parse("session\t1\tx\ntab\thttps://x.com/\tX").size() == 1);   // no final newline
    }
    // --- caps -------------------------------------------------------------------------------------------------
    {
        std::string text = "omni-sessions\t1\n";
        for (int s = 0; s < 40; ++s) {
            text += "session\t" + std::to_string(s) + "\tS" + std::to_string(s) + "\n";
            for (int t = 0; t < 25; ++t) text += "tab\thttps://h" + std::to_string(t) + ".com/\tT\n";
        }
        text += "session\t1\t" + std::string(200, 'n') + "\ntab\thttps://" + std::string(3000, 'u') + "/\tlong\ntab\thttps://ok/\t" + std::string(500, 't') + "\n";
        const auto l = TS::parse(text);
        CHECK(int(l.size()) == TS::kMaxSessions);
        CHECK(int(l[0].tabs.size()) == TS::kMaxTabs);
        std::vector<TS::Session> big;
        for (int s = 0; s < 35; ++s) big.push_back(mk(("B" + std::to_string(s)).c_str(), 20));
        const auto again = TS::parse(TS::serialize(big));
        CHECK(int(again.size()) == TS::kMaxSessions && int(again[0].tabs.size()) == TS::kMaxTabs);
        std::string t2 = "session\t1\t" + std::string(200, 'n') + "\ntab\thttps://" + std::string(3000, 'u') + "/\tlong\ntab\thttps://ok/\t" + std::string(500, 't') + "\n";
        const auto l2 = TS::parse(t2);
        CHECK(l2.size() == 1 && l2[0].name.size() == TS::kNameMax && l2[0].tabs.size() == 1 && l2[0].tabs[0].title.size() == TS::kTitleMax);
    }
    // --- collect: private / media / non-web / duplicates / limit ------------------------------------------------
    {
        std::vector<TS::Candidate> c {
            { "https://a.com/", "A", false, false }, { "https://secret.com/", "S", true, false },
            { "https://media.local/", "M", false, true }, { "omni://pages/start", "Start", false, false },
            { "", "New tab", false, false }, { "https://a.com/", "A again", false, false },
            { "http://b.com/", "B\tb", false, false },
        };
        auto t = TS::collect(c, 8);
        CHECK(t.size() == 2 && t[0].url == "https://a.com/" && t[1].url == "http://b.com/" && t[1].title == "B b");
        std::vector<TS::Candidate> many;
        for (int i = 0; i < 20; ++i) many.push_back({ "https://x" + std::to_string(i) + ".com/", "", false, false });
        CHECK(TS::collect(many, 4).size() == 4);
        CHECK(int(TS::collect(many, 99).size()) == TS::kMaxTabs);
        CHECK(TS::collect({ { "https://p.com/", "", true, false } }, 8).empty());
    }
    // --- naming ------------------------------------------------------------------------------------------------
    {
        CHECK(TS::shortDate(nov16) == "16 Nov 2026");
        CHECK(TS::defaultName(nov16) == "Session 16 Nov 2026");
        std::vector<TS::Session> l { mk("Session 16 Nov 2026", 1), mk("Session 16 Nov 2026 (2)", 1) };
        CHECK(TS::uniqueName(l, TS::defaultName(nov16)) == "Session 16 Nov 2026 (3)");
        CHECK(TS::uniqueName(l, "Movie night") == "Movie night");
        CHECK(TS::uniqueName(l, "session 16 nov 2026", 0) == "session 16 nov 2026");   // its own name is fine
        CHECK(TS::cleanName("   ", "Fallback") == "Fallback");
        CHECK(TS::cleanName("  Movie\tnight \n", "x") == "Movie night");
        const std::string longUtf8 = std::string(59, 'a') + "\xc3\xa9\xc3\xa9";   // the cut must not split é
        CHECK(TS::cleanName(longUtf8, "x") == std::string(59, 'a'));
        std::vector<TS::Session> full { mk(std::string(TS::kNameMax, 'z').c_str(), 1) };
        const std::string u = TS::uniqueName(full, std::string(TS::kNameMax, 'z'));
        CHECK(u.size() == TS::kNameMax && u.substr(u.size() - 4) == " (2)");
    }
    // --- save / update / full / rename / remove ----------------------------------------------------------------
    {
        std::vector<TS::Session> l;
        CHECK(TS::save(l, "A", {}, 1) == TS::kEmpty && l.empty());
        CHECK(TS::save(l, "Movie night", mk("", 2).tabs, 10) == TS::kAdded);
        CHECK(TS::save(l, "Research", mk("", 3).tabs, 20) == TS::kAdded);
        CHECK(l[0].name == "Research");                                     // newest first
        CHECK(TS::save(l, "movie NIGHT", mk("", 5).tabs, 30) == TS::kUpdated);
        CHECK(l.size() == 2 && l[0].name == "movie NIGHT" && l[0].tabs.size() == 5 && l[0].savedAt == 30);
        for (int i = 0; i < 40; ++i) TS::save(l, "S" + std::to_string(i), mk("", 1).tabs, 100 + i);
        CHECK(int(l.size()) == TS::kMaxSessions);
        CHECK(TS::save(l, "One more", mk("", 1).tabs, 999) == TS::kFull && int(l.size()) == TS::kMaxSessions);
        CHECK(TS::save(l, "S27", mk("", 4).tabs, 1000) == TS::kUpdated && l[0].name == "S27" && l[0].tabs.size() == 4);
        std::vector<TS::Session> r { mk("A", 1), mk("B", 1) };
        CHECK(TS::rename(r, 0, "Movie night") && r[0].name == "Movie night");
        CHECK(TS::rename(r, 1, "movie night") && r[1].name == "movie night (2)");
        CHECK(!TS::rename(r, 0, "   ") && r[0].name == "Movie night");
        CHECK(TS::rename(r, 0, "Movie night") && r[0].name == "Movie night");   // unchanged is fine
        CHECK(!TS::rename(r, 5, "x") && !TS::remove(r, -1));
        CHECK(TS::remove(r, 0) && r.size() == 1 && r[0].name == "movie night (2)");
        CHECK(TS::find(r, " MOVIE NIGHT (2) ") == 0 && TS::find(r, "nope") == -1);
    }
    // --- open plan ---------------------------------------------------------------------------------------------
    {
        const TS::Session s = mk("S", 10);
        // replace: limit 8, 3 open (one private): opens 8, closes 3, 2 over
        auto p = TS::plan(s, { "https://site0.com/p", "https://other.com/" }, 3, 8, true);
        CHECK(p.open.size() == 8 && p.closes == 3 && p.overLimit == 2 && p.alreadyOpen == 0 && p.open[0] == 0 && p.open[7] == 7);
        CHECK(TS::planValue(p, true) == "Opens 8, closes 3 (2 over the limit)");
        // add: site0 is open; room 5
        p = TS::plan(s, { "https://site0.com/p", "https://other.com/" }, 3, 8, false);
        CHECK(p.open.size() == 5 && p.alreadyOpen == 1 && p.overLimit == 4 && p.closes == 0 && p.open[0] == 1);
        CHECK(TS::planValue(p, false) == "Opens 5 (4 over the limit)");
        // add when full
        p = TS::plan(s, {}, 8, 8, false);
        CHECK(p.open.empty() && p.overLimit == 10 && TS::planValue(p, false) == "Tab limit reached");
        // add when everything is open
        const TS::Session small = mk("T", 2);
        p = TS::plan(small, { "https://site0.com/p", "https://site1.com/p" }, 2, 8, false);
        CHECK(p.open.empty() && p.alreadyOpen == 2 && TS::planValue(p, false) == "All open already");
        // a duplicate inside the session counts once
        TS::Session d = mk("D", 2); d.tabs.push_back(d.tabs[0]);
        p = TS::plan(d, {}, 1, 8, true);
        CHECK(p.open.size() == 2 && p.alreadyOpen == 1);
        // over the limit already (limit lowered): add opens nothing, replace opens up to the limit
        p = TS::plan(s, {}, 12, 8, false);
        CHECK(p.open.empty());
        p = TS::plan(s, {}, 12, 4, true);
        CHECK(p.open.size() == 4 && p.closes == 12);
    }
    // --- texts -------------------------------------------------------------------------------------------------
    {
        CHECK(TS::tabsText(1) == "1 tab" && TS::tabsText(3) == "3 tabs");
        CHECK(TS::host("https://www.youtube.com/watch?v=1") == "youtube.com");
        CHECK(TS::host("http://user@imdb.com:8080#x") == "imdb.com:8080");
        TS::Session s;
        for (const char* u : { "https://www.youtube.com/a", "https://youtube.com/b", "https://imdb.com/", "https://netflix.com/",
                               "https://a-very-long-host-name.example.org/" })
            s.tabs.push_back({ u, "" });
        CHECK(TS::sitesText(s, 100) == "youtube.com, imdb.com, netflix.com, a-very-long-host-name.example.org");
        CHECK(TS::sitesText(s, 30) == "youtube.com, imdb.com +2");
        CHECK(TS::sitesText(s, 3) == "youtube.com +3");                 // the first site always shows
        CHECK(TS::whenText(nov16 - 3600, nov16) == "Today 11:00");
        CHECK(TS::whenText(nov16 - 86400, nov16) == "Yesterday");
        CHECK(TS::whenText(nov16 - 5 * 86400, nov16) == "11 Nov");
        CHECK(TS::whenText(nov16 - 400 * 86400, nov16) == "12 Oct 2025");
        TS::Session m = mk("M", 5, (long long)(nov16 - 5 * 86400));
        CHECK(TS::listValue(m, nov16) == "5 tabs \xc2\xb7 11 Nov");
        CHECK(TS::savedNotice(TS::kAdded, "Movie night", 5) == "Saved 5 tabs as \"Movie night\"");
        CHECK(TS::savedNotice(TS::kUpdated, "R", 1) == "Updated \"R\" (1 tab)");
        CHECK(TS::savedNotice(TS::kFull, "x", 1).find("30 sessions") == 0);
        CHECK(TS::openedNotice("Movie night", 3, 1, 2) == "Opened \"Movie night\": 3 tabs, 1 already open, 2 over the tab limit");
        CHECK(TS::openedNotice("R", 0, 2, 0) == "Nothing opened from \"R\", 2 already open");
    }
    printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
