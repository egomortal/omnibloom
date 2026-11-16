// OMNI_GAME_MODE_V1: host tests for engine/entry/OmniGameMode.h (written by apply_game_mode.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_game_mode.cpp -o t && ./t
#include "OmniGameMode.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniGameMode;

static bool has(const std::string& s, const char* part) { return s.find(part) != std::string::npos; }

int main()
{
    // host keys
    CHECK(hostKey("https://www.Example.com/play?x=1") == "example.com");
    CHECK(hostKey("HTTP://Example.COM.:8080/") == "example.com");
    CHECK(hostKey("https://user:pw@games.example.com#top") == "games.example.com");
    CHECK(hostKey("https://www.com/") == "www.com");                   // "www." kept when no dot would remain
    CHECK(hostKey("https://[2001:DB8::1]:443/") == "2001:db8::1");
    CHECK(hostKey("https://192.0.2.7/") == "192.0.2.7");
    CHECK(hostKey("omni://start") == "" && hostKey("about:blank") == "" && hostKey("file:///x") == "");
    CHECK(hostKey("https://") == "" && hostKey("https://a..b/") == "" && hostKey("https://ex ample.com/") == "");
    CHECK(hostKey("https://[::1/") == "");
    CHECK(validKey("example.com") && validKey("2001:db8::1") && !validKey("www.example.com") && !validKey("Example.com")
          && !validKey("") && !validKey("a/b") && !validKey("example.com:80"));

    // per-site choice: normal tabs saved, private tabs session-only
    Store s; Session x; bool full = true;
    CHECK(!enabled(s, x, "example.com", false));
    CHECK(setSite(s, x, "example.com", true, false, &full) && !full);
    CHECK(!setSite(s, x, "example.com", true, false));                  // already on: nothing to write
    CHECK(enabled(s, x, "example.com", false) && enabled(s, x, "example.com", true));
    CHECK(!setSite(s, x, "example.com", false, true));                  // private off: never written
    CHECK(!enabled(s, x, "example.com", true) && enabled(s, x, "example.com", false));
    CHECK(!setSite(s, x, "play.test", true, true) && enabled(s, x, "play.test", true) && !enabled(s, x, "play.test", false));
    CHECK(s.sites.size() == 1 && s.sites.count("example.com"));
    CHECK(!setSite(s, x, "example.com", true, true) && enabled(s, x, "example.com", true));   // private back on
    CHECK(setSite(s, x, "example.com", false, false) && !enabled(s, x, "example.com", false));
    CHECK(!setSite(s, x, "", true, false) && !enabled(s, x, "", false));
    x.clear();
    CHECK(!enabled(s, x, "play.test", true));
    Store big;
    for (size_t i = 0; i < kMaxSites; ++i) big.sites.insert("s" + std::to_string(i) + ".example");
    CHECK(!setSite(big, x, "one.more", true, false, &full) && full && big.sites.size() == kMaxSites);

    // file
    Store w; w.hintSeen = true; w.sites = { "example.com", "2001:db8::1" };
    const std::string text = serialize(w);
    CHECK(text.compare(0, 16, "omni-game-sites\t") == 0 && has(text, "hint\tseen\n") && has(text, "site\texample.com\n"));
    const Store r = parse(text);
    CHECK(r.hintSeen && r.sites == w.sites);
    std::string crlf;
    for (char c : text) { if (c == '\n') crlf += '\r'; crlf += c; }
    CHECK(parse(crlf).sites == w.sites);
    const Store bad = parse("omni-game-sites\t1\nsite\tWWW.X.COM\nsite\twww.x.com\nsite\t\njunk\nsite\tgood.example\n");
    CHECK(bad.sites.size() == 1 && bad.sites.count("good.example") && !bad.hintSeen);
    CHECK(parse("something else\nsite\texample.com\n").sites.empty() && parse("").sites.empty());

    // exit chord: Options + Create on one pad, held 1 s
    ExitChord c;
    c.edge(3, kOptions, true, 1000);
    CHECK(!c.due(5000));                                               // Options alone never
    c.edge(3, kCreate, true, 1200);
    CHECK(!c.due(2199) && c.due(2200) && c.due(9000));
    c.edge(3, kCreate, false, 1500);
    CHECK(!c.due(9000));                                               // let go early: nothing
    c.edge(3, kCreate, true, 1600);
    CHECK(!c.due(2599) && c.due(2600));                                // the hold restarts
    c.reset();
    c.edge(1, kOptions, true, 0);
    c.edge(2, kCreate, true, 0);                                       // another pad: never combined
    CHECK(!c.due(5000) && c.held() == 1u);
    c.edge(1, kOptions, false, 10);
    c.edge(2, kCreate, true, 20);                                      // pad 1 let go: pad 2 can start the chord
    c.edge(2, kOptions, true, 30);
    CHECK(c.due(1030));
    c.reset();
    c.edge(4, kCreate, true, 0);
    c.edge(4, kOther, true, 0);                                        // other buttons don't matter
    c.edge(4, kOptions, true, 100);
    CHECK(!c.due(1099) && c.due(1100));
    c.fired();
    CHECK(c.draining() && !c.due(5000));
    CHECK(!c.swallowAfterExit(4, kOther, false, 1200));                // other buttons go to Omni again
    CHECK(!c.swallowAfterExit(5, kOptions, false, 1200));              // another pad's events too
    CHECK(c.swallowAfterExit(4, kOptions, false, 1200) && c.draining());
    CHECK(c.swallowAfterExit(4, kCreate, false, 1300) && !c.draining());
    CHECK(!c.swallowAfterExit(4, kCreate, true, 1400));                // drained: a new press is Omni's
    // wrap-safe timing
    ExitChord wrap;
    wrap.edge(0, kOptions, true, 0xFFFFFF00u);
    wrap.edge(0, kCreate, true, 0xFFFFFF00u);
    CHECK(!wrap.due(0xFFFFFF00u + 999u) && wrap.due(0xFFFFFF00u + 1000u));

    // texts
    CHECK(has(hintText(true, true), "hold Options + Create for 1 second"));
    CHECK(has(hintText(false, true), "Menu + View") && has(hintText(true, false), "Options + Create"));
    CHECK(leftNotice("example.com", true) == "Left game mode on example.com. Back to it: hold Cross > Game mode");
    CHECK(has(leftNotice("example.com", false), "hold A > Game mode"));
    CHECK(siteValue(false, false) == "Off" && siteValue(true, false) == "On for this site" && siteValue(true, true) == "On (this private session)");
    CHECK(siteNotice("example.com", true, false, false) == "Game mode on for example.com (when the menus close)");
    CHECK(has(siteNotice("example.com", false, true, false), "private session only") && has(siteNotice("x", true, false, true), "full"));
    CHECK(std::string(contextValue(false, false)) == "Off" && std::string(contextValue(true, true)) == "Paused" && std::string(contextValue(true, false)) == "On");
    CHECK(kSiteRowId == 770 && kContextId == 990 && kExitHoldMs == 1000);

    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
