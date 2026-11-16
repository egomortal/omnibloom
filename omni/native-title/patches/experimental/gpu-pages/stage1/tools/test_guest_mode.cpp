// OMNI_GUEST_MODE_V1: host tests for the pure part (OmniGuestMode.h).
//   g++ -std=c++20 -Wall -Wextra -I<dir with OmniGuestMode.h> test_guest_mode.cpp -o t && ./t
#include "OmniGuestMode.h"
#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <vector>

static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

namespace G = OmniGuestMode;

static void machine()
{
    G::Machine m;
    CHECK(m.phase() == G::Phase::Owner && !m.active() && m.canEnter() && !m.canLeave());
    CHECK(!m.finishEnter() && !m.beginLeave() && !m.finishLeave());       // nothing out of order
    CHECK(m.beginEnter());
    CHECK(m.active() && !m.canEnter() && !m.canLeave());                  // Entering: rules hold, no second enter
    CHECK(!m.beginEnter() && !m.beginLeave());
    CHECK(m.finishEnter() && m.phase() == G::Phase::Guest && m.sessions() == 1);
    CHECK(m.active() && m.canLeave() && !m.canEnter());
    CHECK(!m.finishEnter() && !m.finishLeave());
    CHECK(m.beginLeave() && m.active() && !m.canLeave());                 // Leaving: rules still hold
    CHECK(!m.beginLeave() && !m.beginEnter());
    CHECK(m.finishLeave() && !m.active() && m.canEnter());
    CHECK(m.beginEnter() && m.abortEnter() && !m.active() && m.sessions() == 1);   // aborted: not counted
    CHECK(!m.abortEnter());
    CHECK(m.beginEnter() && m.finishEnter() && m.sessions() == 2);
    // the global flag follows the shared machine
    CHECK(!omniGuest());
    CHECK(G::state().beginEnter() && omniGuest());
    CHECK(G::state().finishEnter() && omniGuest());
    CHECK(G::state().beginLeave() && omniGuest());
    CHECK(G::state().finishLeave() && !omniGuest());
}

static void allowlist()
{
    const std::string d = "/data/omni/";
    // owner stores: refused
    for (const char* n : { "history.txt", "bookmarks.txt", "session.txt", "sessions.txt", "kb-words.txt", "apps.json",
                           "start-page.json", "site-zoom.txt", "site-ua.txt", "site-permissions.txt", "autoplay.txt",
                           "https-only.txt", "popup-allow.txt", "site-tweaks.txt", "site-volume.txt", "quick-access.txt",
                           "browser-settings.txt", "autofill.txt", "ui-theme-prev.txt", "kb-layout.txt", "x.tmp",
                           "jsc-jit-off.flag", "pending", ".pending" })
        CHECK(!G::writeAllowed(d + n, d));
    // sub folders and odd spellings inside the folder: refused
    CHECK(!G::writeAllowed("/data/omni/addons/state.json", d));
    CHECK(!G::writeAllowed("/data/omni/reading-list/x.html", d));
    CHECK(!G::writeAllowed("/data/omni/../omni/history.txt", d));
    CHECK(!G::writeAllowed("/data/omni/sub/display-startup.pending", d));
    CHECK(!G::writeAllowed("/data/omni/..", d));
    CHECK(!G::writeAllowed("/data/omni/", d));
    CHECK(!G::writeAllowed("/data/omni", d));
    CHECK(!G::writeAllowed("/data//omni/history.txt", d));
    CHECK(!G::writeAllowed("/data/./omni/history.txt", d));
    CHECK(!G::writeAllowed("/data/x/../omni/history.txt", d));
    // markers: allowed
    CHECK(G::writeAllowed("/data/omni/display-startup.pending", d));
    CHECK(G::writeAllowed("/data/omni/jank-mark.txt", d));
    CHECK(G::writeAllowed("/data/omni/crash-20261116.txt", d));
    CHECK(G::writeAllowed("/data/omni/crash.log", d));
    CHECK(G::writeAllowed("/data/omni/gpu-reset.pending", d));
    CHECK(!G::writeAllowed("/data/omni/crash-", d));
    // r2: the parental file (PIN-gated changes, wrong-PIN count / lockout) and the startup crash marker
    CHECK(G::writeAllowed("/data/omni/parental.txt", d));
    CHECK(G::writeAllowed("/data/omni/running.txt", d));
    CHECK(!G::writeAllowed("/data/omni/sub/parental.txt", d));
    CHECK(!G::writeAllowed("/data/omni/startup.txt", d));
    CHECK(!G::writeAllowed("/data/omni/highlights.txt", d));
    CHECK(!G::writeAllowed("/data/omni/ui-bars.txt", d));
    CHECK(!G::writeAllowed("/data/omni/shortcuts.txt", d));
    CHECK(!G::writeAllowed("/data/omni/ublock-allowlist.txt", d));
    CHECK(!G::writeAllowed("/data/omni/reader-auto.txt", d));
    // outside the data folder: not an owner store
    CHECK(G::writeAllowed("/data/omnibus/history.txt", d));
    CHECK(G::writeAllowed("/tmp/x.txt", d));
    CHECK(G::writeAllowed("/data/other/file", d));
    // a data folder given without its slash, and a test folder
    CHECK(!G::writeAllowed("/data/omni/history.txt", "/data/omni"));
    CHECK(G::writeAllowed("/data/omni/display-startup.pending", "/data/omni"));
    CHECK(!G::writeAllowed("/tmp/omni-test/history.txt", "/tmp/omni-test/"));
    CHECK(G::writeAllowed("/data/omni/history.txt", "/tmp/omni-test/"));
}

struct SiteStore { std::map<std::string, int> saved, session; bool loaded = false; };

static void stash()
{
    std::vector<std::pair<std::string, std::string>> history = { { "https://a/", "A" }, { "https://b/", "B" } };
    std::map<std::string, int> session = { { "x.com", 1 } };
    SiteStore zoom; zoom.saved["a.com"] = 125; zoom.loaded = true;
    std::string clip = "owner secret";
    std::set<std::string> hosts = { "m.example.com" };
    G::Stash s;
    CHECK(s.empty());
    s.take(history);
    s.take(session);
    s.take(clip);
    s.keep(zoom);
    s.keep(hosts);
    CHECK(s.size() == 5);
    // guest view: taken stores are empty, kept ones are copies
    CHECK(history.empty() && session.empty() && clip.empty());
    CHECK(zoom.loaded && zoom.saved.at("a.com") == 125 && hosts.count("m.example.com"));
    // the guest changes everything
    history.push_back({ "https://guest/", "G" });
    session["guest.com"] = 2;
    clip = "guest text";
    zoom.saved["a.com"] = 300; zoom.saved["guest.com"] = 50; zoom.session["g"] = 1;
    hosts.insert("guest.example");
    s.restore();
    CHECK(s.empty());
    CHECK(history.size() == 2 && history[0].first == "https://a/" && history[1].second == "B");
    CHECK(session.size() == 1 && session.at("x.com") == 1);
    CHECK(clip == "owner secret");
    CHECK(zoom.saved.size() == 1 && zoom.saved.at("a.com") == 125 && zoom.session.empty() && zoom.loaded);
    CHECK(hosts.size() == 1 && hosts.count("m.example.com"));
    // a second session starts clean again
    s.take(history);
    CHECK(history.empty());
    s.restore();
    CHECK(history.size() == 2);
    s.restore();   // nothing stashed: no change
    CHECK(history.size() == 2);
    // restore order: newest first (the same store stashed twice ends with the first saved value)
    int v = 1;
    s.keep(v); v = 2; s.take(v); v = 3;
    s.restore();
    CHECK(v == 1);
}

static void session()
{
    const std::string text = "omni-session\t1\r\n"
                             "tab\thttps://a.example/\tA\n"
                             "pinned\t0\n"
                             "tab\tnewtab\tNew tab\n"
                             "tab\tjavascript:alert(1)\tX\n"          // not a web address: dropped (as omniEverydayStart)
                             "group\t2\t1\t3\t0\tWork\n"
                             "tab\thttp://b.example/x\n"              // no title
                             "selected\t2\n";
    G::SavedTabs s = G::parseSession(text, 10);
    CHECK(s.tabs.size() == 3);
    CHECK(s.tabs[0].first == "https://a.example/" && s.tabs[0].second == "A");
    CHECK(s.tabs[1].first == "newtab");
    CHECK(s.tabs[2].first == "http://b.example/x" && s.tabs[2].second.empty());
    CHECK(s.selected == 2);
    CHECK(s.extra.size() == 2 && s.extra[0] == "pinned\t0" && s.extra[1] == "group\t2\t1\t3\t0\tWork");
    G::SavedTabs two = G::parseSession(text, 2);
    CHECK(two.tabs.size() == 2 && two.extra.size() == 2);
    G::SavedTabs none = G::parseSession("", 4);
    CHECK(none.tabs.empty() && none.extra.empty() && none.selected == 0);
    G::SavedTabs odd = G::parseSession("selected\t99999999999\ntab\thttps://x/", 4);   // no final newline; huge index capped
    CHECK(odd.tabs.size() == 1 && odd.selected >= 0 && odd.selected < 1000000);
}

static void texts()
{
    CHECK(!G::parentalLockedNotice().empty() && G::parentalLockedNotice().size() < 140 && !G::parentalLockedValue().empty());
    CHECK(G::enterBody().find("Private tabs close") != std::string::npos);
    CHECK(G::rowLabel(false) == "Guest mode" && G::rowLabel(true) == "Leave guest mode");
    CHECK(!G::rowValue(false).empty() && !G::rowValue(true).empty());
    CHECK(G::enterBody().find("Your tabs will be restored when you leave guest mode") != std::string::npos);
    CHECK(G::leaveBody().find("deleted") != std::string::npos);
    CHECK(G::blockedNotice("Passwords") == "Passwords isn't available in guest mode");
    CHECK(std::string(G::kBadge) == "GUEST");
    for (const std::string& t : { G::enterTitle(), G::leaveTitle(), G::enteredNotice(), G::leftNotice(), G::downloadNotice(), G::unavailableNotice() })
        CHECK(!t.empty() && t.find('\n') == std::string::npos && t.size() < 140);
}

int main()
{
    machine();
    allowlist();
    stash();
    session();
    texts();
    std::printf("%s: %d checks, %d failures\n", failures ? "FAILED" : "ok", checks, failures);
    return failures ? 1 : 0;
}
