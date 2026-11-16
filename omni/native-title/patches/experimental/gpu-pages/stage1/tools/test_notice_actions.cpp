// OMNI_NOTICE_ACTIONS_V1: host tests of the pure part (OmniNoticeActions.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<tools> test_notice_actions.cpp -o t && ./t
#include "OmniNoticeActions.h"
#include <cstdio>

namespace A = OmniNoticeActions;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

int main()
{
    // which texts carry an action (the real texts of the tree)
    CHECK(A::actionFor("Downloaded: Big Buck Bunny", false) == A::kOpenDownloads);
    CHECK(A::actionFor("Downloaded: A (and 2 more)", false) == A::kOpenDownloads);
    CHECK(A::actionFor("Downloaded a.zip to /data/omni/downloads/", false) == A::kOpenFileDownloads);
    CHECK(A::actionFor("Downloaded", false) == A::kNone);
    CHECK(A::actionFor("Download failed: a.zip", false) == A::kNone);
    CHECK(A::actionFor("Downloading a.zip to /data/omni/downloads/", false) == A::kNone);
    CHECK(A::actionFor("Pop-up blocked. Options: Open it / Always allow for this site", true) == A::kAllowPopup);
    CHECK(A::actionFor("Pop-up blocked (site set to Block). Options: Open it", true) == A::kAllowPopup);
    CHECK(A::actionFor("Pop-up blocked by uBlock (ad). Options: Open anyway", true) == A::kNone);
    CHECK(A::actionFor("Pop-up blocked. Options: Open it / Always allow for this site", false) == A::kNone);   // not ours / other tab
    CHECK(A::actionFor("Copied", false) == A::kNone);
    CHECK(A::actionFor("", false) == A::kNone);
    CHECK(A::fromTab(A::kAllowPopup) && A::fromTab(A::kOpenFileDownloads) && !A::fromTab(A::kOpenDownloads));
    CHECK(std::string(A::label(A::kOpenDownloads)) == "Open");
    CHECK(std::string(A::label(A::kAllowPopup)) == "Allow once");
    CHECK(std::string(A::label(A::kNone)).empty());

    // arming, show time, hover hold (wrap-safe)
    CHECK(!A::armed(1000 + 599, 1000));
    CHECK(A::armed(1000 + 600, 1000));
    CHECK(A::armed(5u, 0xfffffff0u + 0) == false);                    // 21 ms across the wrap
    CHECK(A::armed(700u, 0xfffffff0u));                                // 716 ms across the wrap
    CHECK(A::showUntil(1000 + 3500, 1000) == 1000 + 8000);             // notice()'s 3.5 s grows to 8 s
    CHECK(A::showUntil(1000 + 9000, 1000) == 1000 + 9000);             // a later deadline stays
    CHECK(A::showUntil(0, 1000) == 1000 + 8000);
    CHECK(A::showUntil(0xfffffff0u + 8000, 0xfffffff0u) == 0xfffffff0u + 8000);
    CHECK(A::holdUntil(5000, 4000, 1000) == 5500);                     // 1 s left: held 1.5 s ahead
    CHECK(A::holdUntil(9000, 4000, 1000) == 9000);                     // enough left
    CHECK(A::holdUntil(0, 4000, 1000) == 0);                           // no deadline: untouched
    CHECK(A::holdUntil(32000, 31001, 1000) == 32000);                  // 30 s after it appeared: no more hold
    CHECK(A::holdUntil(31100, 31000, 1000) == 32500);                  // exactly at 30 s: still held

    // geometry
    {
        A::Rect pill { 400, 600, 300, 44 };
        A::Rect c = A::chipRect(pill, 140, 1280);
        CHECK(c.x == 708 && c.y == 600 && c.w == 140 && c.h == 44);
        A::Rect wide { 145, 600, 990, 44 };
        c = A::chipRect(wide, 140, 1280);
        CHECK(c.x == 145 + 990 - 140 && c.y == 600 - 44 - 8);
        CHECK(A::inside(pill, 400, 600) && A::inside(pill, 699.5f, 643.9f));
        CHECK(!A::inside(pill, 700, 620) && !A::inside(pill, 399.9f, 620) && !A::inside(pill, 500, 644));
        CHECK(!A::inside(A::Rect {}, 0, 0));
    }

    // the store: dedupe, keep 10 min, private records, matching a Recent notices entry
    {
        A::Store s;
        A::Record r; r.text = "Downloaded: X"; r.action = A::kOpenDownloads; r.at = 1000;
        s.add(r);
        A::Record none; none.text = "Copied"; none.at = 1000;
        s.add(none);                                                   // no action: not kept
        CHECK(s.size() == 1);
        r.at = 4000; s.add(r);                                         // again within 5 s: one record, newer stamp
        CHECK(s.size() == 1 && s.records().front().at == 4000);
        r.at = 10000; s.add(r);                                        // later: a second record
        CHECK(s.size() == 2);
        CHECK(s.match("Downloaded: X", 10050, 20000) == &s.records().front());
        CHECK(s.match("Downloaded: X", 4000, 20000) == &s.records()[1]);
        CHECK(s.match("Downloaded: X", 14000, 20000) == nullptr);     // neither within 3 s
        CHECK(s.match("Downloaded: Y", 10000, 20000) == nullptr);
        CHECK(s.match("Downloaded: X", 10000, 10000 + A::kKeepMs) != nullptr);
        CHECK(s.match("Downloaded: X", 10000, 10001 + A::kKeepMs) == nullptr);   // 10 min: the action is gone
        s.prune(4000 + A::kKeepMs + 1);
        CHECK(s.size() == 1 && s.records().front().at == 10000);
        s.prune(10000 + A::kKeepMs + 1);
        CHECK(s.size() == 0);

        A::Record p; p.text = "Pop-up blocked. Options: Open it / Always allow for this site"; p.action = A::kAllowPopup;
        p.at = 50000; p.tab = 7; p.priv = true; p.url = "https://example.com/pop";
        s.add(p);
        A::Record q = p; q.tab = 8; q.priv = false; q.at = 60000; q.text = "Pop-up blocked (site set to Block). Options: Open it";
        s.add(q);
        CHECK(s.match(p.text, 50000, 60000) == nullptr);              // private: never offered in Recent notices
        CHECK(s.match(q.text, 60000, 61000) != nullptr);
        CHECK(s.dropClosedPrivate([](uintptr_t t) { return t == 7; }) == 0);   // the private tab is still open
        CHECK(s.size() == 2);
        CHECK(s.dropClosedPrivate([](uintptr_t) { return false; }) == 1);      // it closed: its record goes, q stays
        CHECK(s.size() == 1 && s.records().front().tab == 8);
        s.remove(s.match(q.text, 60000, 61000));
        CHECK(s.size() == 0);
        s.remove(nullptr);
        for (uint32_t i = 0; i < 40; ++i) { A::Record m; m.text = "Downloaded: " + std::to_string(i); m.action = A::kOpenDownloads; m.at = i * 10; s.add(m); }
        CHECK(s.size() == A::kMaxKept && s.records().front().text == "Downloaded: 39");
    }

    // the watch
    {
        A::Watch w;
        CHECK(w.changed("Downloaded: X", 4500));
        CHECK(!w.changed("Downloaded: X", 4500));
        CHECK(w.changed("Downloaded: X", 9000));                       // raised again (later deadline)
        w.sync("Downloaded: X", 12000);                                // the shell moved the deadline itself
        CHECK(!w.changed("Downloaded: X", 12000));
        CHECK(!w.changed("Downloaded: X", 11000));                     // ended early: not new
        CHECK(w.changed("Ready", 0));
    }

    // texts
    CHECK(A::historyDetail(A::kAllowPopup, 1000, 1000) == "Allow this pop-up once (10 min left)");
    CHECK(A::historyDetail(A::kOpenDownloads, 1000, 1000 + 61000) == "Open Downloads (9 min left)");
    CHECK(A::historyDetail(A::kOpenFileDownloads, 1000, 1000 + A::kKeepMs - 1) == "Open file downloads (1 min left)");
    CHECK(A::historyDetail(A::kOpenDownloads, 1000, 1000 + A::kKeepMs) == "Open Downloads (0 min left)");
    CHECK(A::historyDetail(A::kNone, 1000, 1000).empty());

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
