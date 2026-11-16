// OMNI_SITE_MUTE_V1: host tests of the pure part (engine/entry/OmniSiteMute.h, written by apply_site_mute.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_site_mute.cpp -o t && ./t
#include "OmniSiteMute.h"
#include <cstdio>
#include <string>

namespace M = OmniSiteMute;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

// The tab as the shell keeps it: the per-tab state plus Tab::omniTaMuted, acting on decisions as omniSmuDo does.
struct FakeTab {
    M::TabMute s;
    bool muted = false;
    M::Act last = M::kNothing;
    void apply(M::Act a) { last = a; if (a == M::kMute) muted = true; else if (a == M::kUnmute) muted = false; }
    void commit(const std::string& key, bool siteMuted) { apply(M::committed(s, key, siteMuted, muted)); }
    void change(const std::string& key, bool siteMuted) { apply(M::changed(s, key, siteMuted, muted)); }
};

int main()
{
    // --- host key -------------------------------------------------------------------------------------------------
    CHECK(M::hostKey("https://WWW.Example.com:8443/x?y#z") == "example.com");
    CHECK(M::hostKey("http://news.example.co.uk/") == "news.example.co.uk");
    CHECK(M::hostKey("https://www.com/") == "www.com");
    CHECK(M::hostKey("https://user:pw@www.example.com/") == "example.com");
    CHECK(M::hostKey("https://[::1]:8080/") == "::1");
    CHECK(M::hostKey("https://example.com./") == "example.com");
    CHECK(M::hostKey("omni://pages/start") == "");
    CHECK(M::hostKey("about:blank") == "");
    CHECK(M::hostKey("") == "");
    CHECK(M::hostKey("https://a..b/") == "");
    CHECK(M::hostKey("https://ex ample.com/") == "");
    CHECK(M::hostKey("https://" + std::string(254, 'a') + "/") == "");
    CHECK(M::validKey("example.com") && M::validKey("::1"));
    CHECK(!M::validKey("www.example.com") && !M::validKey("Example.com") && !M::validKey("a/b") && !M::validKey(""));

    // --- store ----------------------------------------------------------------------------------------------------
    M::Store st;
    M::Session ss;
    bool full = true;
    CHECK(M::setSite(st, ss, "example.com", true, false, &full) && !full);
    CHECK(!M::setSite(st, ss, "example.com", true, false));             // already there: nothing to write
    CHECK(M::serialize(st) == "omni-site-mute\t1\nsite\texample.com\n");
    M::Store back = M::parse("omni-site-mute\t1\r\nsite\texample.com\r\nsite\tWWW.bad.com\r\njunk\r\nsite\t::1\r\n");
    CHECK(back.sites.size() == 2 && back.sites.count("example.com") && back.sites.count("::1"));
    CHECK(M::parse("other\t1\nsite\texample.com\n").sites.empty());
    CHECK(M::parse("").sites.empty());
    CHECK(M::parse(M::serialize(st)).sites == st.sites);
    {
        M::Store big;
        M::Session x;
        for (size_t i = 0; i < M::kMaxSites; ++i) CHECK(M::setSite(big, x, "s" + std::to_string(i) + ".com", true, false));
        bool f = false;
        CHECK(!M::setSite(big, x, "one-more.com", true, false, &f) && f);
        CHECK(M::setSite(big, x, "s0.com", false, false));
        std::string text = "omni-site-mute\t1\n";
        for (size_t i = 0; i < M::kMaxSites + 20; ++i) text += "site\tt" + std::to_string(i) + ".com\n";
        CHECK(M::parse(text).sites.size() == M::kMaxSites);
    }

    // --- private session: never saved, never seen by normal tabs ---------------------------------------------------
    CHECK(M::enabled(st, ss, "example.com", false) && M::enabled(st, ss, "example.com", true));
    CHECK(!M::setSite(st, ss, "noisy.com", true, true));                 // private: nothing to write
    CHECK(M::enabled(st, ss, "noisy.com", true) && !M::enabled(st, ss, "noisy.com", false));
    CHECK(!st.sites.count("noisy.com"));
    CHECK(!M::setSite(st, ss, "example.com", false, true));              // a saved site allowed in private only
    CHECK(!M::enabled(st, ss, "example.com", true) && M::enabled(st, ss, "example.com", false));
    CHECK(M::serialize(st).find("noisy") == std::string::npos);
    CHECK(!M::setSite(st, ss, "example.com", true, true));
    CHECK(M::enabled(st, ss, "example.com", true) && !ss.off.count("example.com") && !ss.on.count("example.com"));
    ss.clear();
    CHECK(!M::enabled(st, ss, "noisy.com", true));
    CHECK(!M::enabled(st, ss, "", false) && !M::setSite(st, ss, "", true, false));

    // --- one tab --------------------------------------------------------------------------------------------------
    {   // entering a muted site mutes; leaving it gives the sound back
        FakeTab t;
        t.commit("plain.com", false); CHECK(t.last == M::kNothing && !t.muted);
        t.commit("loud.com", true);   CHECK(t.last == M::kMute && t.muted && t.s.by == "loud.com");
        t.commit("loud.com", true);   CHECK(t.last == M::kNothing && t.muted);      // same site, next page
        t.commit("plain.com", false); CHECK(t.last == M::kUnmute && !t.muted && t.s.by.empty());
        t.commit("", false);          CHECK(t.last == M::kNothing && !t.muted);
        t.commit("loud.com", true);   CHECK(t.last == M::kMute);
        t.commit("", false);          CHECK(t.last == M::kUnmute && !t.muted);      // new-tab page: sound back too
    }
    {   // unmuting by hand overrides for that tab (and that site) only
        FakeTab t, other;
        t.commit("loud.com", true); other.commit("loud.com", true);
        CHECK(t.muted && other.muted);
        t.muted = false;                                                             // Tabs panel Triangle
        t.commit("loud.com", true);   CHECK(t.last == M::kNothing && !t.muted && t.s.keep == "loud.com");
        t.commit("plain.com", false); CHECK(t.last == M::kNothing && !t.muted);
        t.commit("loud.com", true);   CHECK(t.last == M::kNothing && !t.muted);      // still this tab's choice
        other.commit("loud.com", true); CHECK(other.muted);                          // the other tab is not affected
        FakeTab fresh; fresh.commit("loud.com", true); CHECK(fresh.muted);           // nor a new one
        t.commit("other-loud.com", true); CHECK(t.last == M::kMute && t.muted);      // another muted site still mutes
        t.commit("loud.com", true);   CHECK(t.last == M::kUnmute && !t.muted);       // back where it was unmuted
    }
    {   // a tab the user muted stays muted: the setting never unmutes what it did not mute
        FakeTab t;
        t.muted = true;
        t.commit("loud.com", true);   CHECK(t.last == M::kNothing && t.muted && t.s.by.empty());
        t.commit("plain.com", false); CHECK(t.last == M::kNothing && t.muted);
    }
    {   // muted site to muted site: ours moves along, then leaving unmutes
        FakeTab t;
        t.commit("a.com", true);  CHECK(t.muted && t.s.by == "a.com");
        t.commit("b.com", true);  CHECK(t.last == M::kNothing && t.s.by == "b.com");
        t.commit("c.com", false); CHECK(t.last == M::kUnmute && !t.muted);
    }
    {   // the setting changes while the tab shows the site
        FakeTab t;
        t.commit("loud.com", false);
        t.change("loud.com", true);   CHECK(t.last == M::kMute && t.muted && t.s.by == "loud.com");
        t.change("loud.com", false);  CHECK(t.last == M::kUnmute && !t.muted);
        t.muted = true;                                                              // muted by the user
        t.change("loud.com", true);   CHECK(t.last == M::kNothing && t.muted && t.s.by.empty());
        t.change("loud.com", false);  CHECK(t.last == M::kNothing && t.muted);       // the user's mute stays
        t.muted = false;
        t.change("loud.com", true);   CHECK(t.last == M::kMute);
        t.muted = false;                                                             // unmuted by hand: override
        t.commit("loud.com", true);   CHECK(!t.muted && t.s.keep == "loud.com");
        t.change("loud.com", true);   CHECK(t.last == M::kMute && t.muted && t.s.keep.empty());   // asked again: ends it
        t.muted = false;
        t.change("loud.com", false);  CHECK(t.last == M::kNothing && t.s.keep.empty() && t.s.by.empty());
        t.change("", true);           CHECK(t.last == M::kNothing);
    }

    // --- texts ----------------------------------------------------------------------------------------------------
    CHECK(M::siteValue(false, false) == "Allow" && M::siteValue(false, true) == "Allow");
    CHECK(M::siteValue(true, false) == "Always mute");
    CHECK(M::siteValue(true, true) == "Always mute (this private session)");
    CHECK(M::siteNotice("example.com", true, false, false) == "Sound always muted on example.com");
    CHECK(M::siteNotice("example.com", false, true, false) == "Sound allowed on example.com, this private session only");
    CHECK(M::siteNotice("example.com", true, false, true) == "The always-mute list is full (500 sites)");
    CHECK(M::mutedNotice("example.com") == "Muted: example.com is set to Always mute");
    CHECK(M::kSiteRowId == 776 && std::string(M::kFileName) == "site-mute.txt");

    std::printf("%s: %d checks, %d failures\n", failures ? "FAILED" : "ok", checks, failures);
    return failures ? 1 : 0;
}
