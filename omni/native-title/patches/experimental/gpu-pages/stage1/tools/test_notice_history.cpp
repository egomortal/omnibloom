// OMNI_NOTICE_HISTORY_V1: host tests of the pure part (OmniNoticeHistory.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<tools> test_notice_history.cpp -o t && ./t
#include "OmniNoticeHistory.h"
#include <cstdio>

namespace N = OmniNoticeHistory;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

int main()
{
    // noise filter: per-keypress steps and progress texts (the real texts of the tree)
    CHECK(N::noisy(""));
    CHECK(N::noisy("Ready"));
    CHECK(N::noisy("Zoom 110% on example.com"));
    CHECK(N::noisy("Zoom reset to 100% on example.com"));
    CHECK(N::noisy("Zoom is at its largest (300%)"));
    CHECK(N::noisy("Volume: 40 %"));
    CHECK(N::noisy("Speed: 1.25x"));
    CHECK(N::noisy("Magnifier 2x  (L3 + R3: 3x, Circle: close)"));
    CHECK(N::noisy("Downloading a.zip: 40% of 3.0 MB"));
    CHECK(N::noisy("Downloading a.zip to /data/omni/downloads/"));
    CHECK(N::noisy("Copying from the USB drive: 42%"));
    CHECK(N::noisy("Copying to the USB drive: 7%"));
    CHECK(N::noisy("Saving screenshot..."));
    CHECK(N::noisy("Reader view\xe2\x80\xa6"));
    CHECK(N::noisy("Press Options \xe2\x86\x92 Controls for all shortcuts"));
    CHECK(!N::noisy("Copied"));
    CHECK(!N::noisy("Sleep timer: paused playback"));
    CHECK(!N::noisy("Back online. Reloading the page"));
    CHECK(!N::noisy("Downloaded a.zip to /data/omni/downloads/"));
    CHECK(!N::noisy("Download failed: a.zip"));
    CHECK(!N::noisy("Pop-up blocked. Options: Open it / Always allow for this site"));
    CHECK(!N::noisy("Zoo"));                  // shorter than a prefix
    CHECK(!N::noisy("Volume remembered for example.com"));

    // actions
    CHECK(N::actionFor("Sent to Downloads: clip.mp4") == N::kMediaDownloads);
    CHECK(N::actionFor("Sent to Downloads") == N::kMediaDownloads);
    CHECK(N::actionFor("Downloaded: My video (and 2 more)") == N::kMediaDownloads);
    CHECK(N::actionFor("Downloaded a.zip to /data/omni/downloads/") == N::kFileDownloads);
    CHECK(N::actionFor("Download failed: a.zip") == N::kFileDownloads);
    CHECK(N::actionFor("Pop-up blocked by uBlock (ad). Options: Open anyway") == N::kBlockedPopups);
    CHECK(N::actionFor("Pop-up blocked (site set to Block). Options: Open it") == N::kBlockedPopups);
    CHECK(N::actionFor("Pop-up blocked. To open it: Options > Site settings > Site permissions") == N::kBlockedPopups);
    CHECK(N::actionFor("Screenshot saved (Downloads > Saved > Screenshots)") == N::kScreenshots);
    CHECK(N::actionFor("Couldn't save the screenshot (x)") == N::kNone);
    CHECK(N::actionFor("Copied") == N::kNone);
    CHECK(N::actionFor("Sleep timer: paused playback") == N::kNone);
    CHECK(std::string(N::actionHint(N::kNone)).empty());
    CHECK(std::string(N::actionHint(N::kBlockedPopups)) == "Open Blocked pop-ups");

    // clip
    CHECK(N::clip("a\nb\tc\rd") == "a b c d");
    {
        std::string s(N::kTextMax - 1, 'a');
        s += "\xc3\xa9\xc3\xa9";               // the cut lands inside the first "é"
        const std::string c = N::clip(s);
        CHECK(c.size() == N::kTextMax - 1 && c.back() == 'a');
        std::string t(N::kTextMax - 2, 'a');
        t += "\xc3\xa9zz";                     // "é" ends exactly at the limit: kept
        CHECK(N::clip(t).size() == N::kTextMax && N::clip(t).compare(N::kTextMax - 2, 2, "\xc3\xa9") == 0);
        std::string u(N::kTextMax - 1, 'a');
        u += "\xe2\x97\x8f";                   // a 3-byte character across the limit
        CHECK(N::clip(u).size() == N::kTextMax - 1);
        CHECK(N::clip(std::string(N::kTextMax + 50, 'b')).size() == N::kTextMax);
    }

    // history: add, noisy refused, newest first, unread, dedupe within 5 s
    N::History h;
    CHECK(h.empty() && h.unread() == 0);
    CHECK(!h.add("Zoom 120% on a.com", 1000));
    CHECK(!h.add("Ready", 1000));
    CHECK(h.empty());
    CHECK(h.add("Copied", 1000));
    CHECK(h.add("Sent to Downloads: x.mp4", 2000));
    CHECK(h.size() == 2 && h.entries()[0].text == "Sent to Downloads: x.mp4" && h.entries()[0].action == N::kMediaDownloads);
    CHECK(h.unread() == 2);
    h.markRead();
    CHECK(h.unread() == 0);
    CHECK(h.add("Copied", 5900));             // 4.9 s after the first: counted, moved to the top
    CHECK(h.size() == 2 && h.entries()[0].text == "Copied" && h.entries()[0].count == 2 && h.entries()[0].at == 5900);
    CHECK(h.unread() == 1);
    CHECK(h.add("Copied", 10900));            // exactly 5 s after the last raise: still the same entry
    CHECK(h.size() == 2 && h.entries()[0].count == 3);
    CHECK(h.add("Copied", 15901));            // 5.001 s later: a new entry
    CHECK(h.size() == 3 && h.entries()[0].count == 1 && h.entries()[1].count == 3);
    // the cap: 30, oldest dropped
    for (int i = 0; i < 40; ++i) h.add("Notice " + std::to_string(i), 20000 + uint32_t(i) * 6000);
    CHECK(h.size() == N::kMax);
    CHECK(h.entries().front().text == "Notice 39" && h.entries().back().text == "Notice 10");
    CHECK(h.unread() == N::kMax);
    // find by seq, clear
    const uint64_t seq = h.entries()[3].seq;
    CHECK(h.find(seq) && h.find(seq)->text == "Notice 36");
    CHECK(!h.find(999999));
    h.clear();
    CHECK(h.empty() && h.unread() == 0);
    CHECK(h.add("After clear", 400000) && h.unread() == 1);
    // tick wrap-around: dedupe works across the 32-bit wrap
    N::History w;
    CHECK(w.add("Copied", 0xffffff00u));
    CHECK(w.add("Copied", 0x00000100u));      // 512 ms later
    CHECK(w.size() == 1 && w.entries()[0].count == 2);

    // the toast path
    N::StatusWatch s;
    CHECK(s.changed("Ready", 0));             // first look: a change (the shell drops "Ready" as noisy)
    CHECK(!s.changed("Ready", 0));
    CHECK(s.changed("Tab limit reached", 0)); // set without notice()
    CHECK(!s.changed("Tab limit reached", 7000));   // the toast gave it 6 s: not a new notice
    CHECK(!s.changed("Tab limit reached", 7000));
    CHECK(s.changed("Tab limit reached", 9000));    // set again with a later deadline
    CHECK(!s.changed("Tab limit reached", 3001));   // ended early (popup notice: now + 1)
    s.sync("Copied", 12000);                  // notice() recorded it itself
    CHECK(!s.changed("Copied", 12000));
    CHECK(s.changed("Ready", 0));
    CHECK(s.changed("Copied", 20000));

    // texts
    CHECK(N::ago(10000, 10000) == "just now");
    CHECK(N::ago(19999, 10000) == "just now");
    CHECK(N::ago(20000, 10000) == "10 s ago");
    CHECK(N::ago(70000, 10000) == "1 min ago");
    CHECK(N::ago(10000 + 59u * 60000 + 59000, 10000) == "59 min ago");
    CHECK(N::ago(10000 + 3600000, 10000) == "1 h ago");
    CHECK(N::ago(10000 + 2 * 3600000 + 5 * 60000, 10000) == "2 h 5 min ago");
    CHECK(N::ago(0x00000500u, 0xfffffb00u) == "just now");   // across the wrap
    {
        N::Entry e; e.text = "Copied"; e.at = 1000; e.count = 2;
        CHECK(N::rowValue(e, 121000) == "x2  2 min ago");
        e.count = 1;
        CHECK(N::rowValue(e, 1000) == "just now");
    }
    CHECK(N::quickLabel(3) == "Notices (3)");
    CHECK(N::quickValue(0).empty());
    CHECK(N::quickValue(2) == "\xe2\x97\x8f 2 new");

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
