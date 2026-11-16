// OMNI_STARTUP_CHOICE_V1: host tests for engine/entry/OmniStartupChoice.h (written by apply_startup_choice.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_startup_choice.cpp -o t && ./t
#include "OmniStartupChoice.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniStartupChoice;

static const std::string A = "https://www.example.com/watch?v=1", B = "https://news.example.org/";

// One run: the marker it leaves (crash: kept; clean: none), as the shell writes it.
static Marker runMarker(const Verdict& v, const std::string& shown, long long logAtStart, const std::string& held = std::string())
{
    Marker m; m.active = shown; m.streakUrl = v.streakUrl; m.streak = v.streak; m.held = held; m.crashLog = logAtStart;
    return m;
}
static Verdict next(const Marker& left, long long logNow)
{
    Marker m;
    const bool ok = parseMarker(serializeMarker(left), m);   // through the file, as at the next start
    CHECK(ok);
    return verdict(true, m, logNow);
}

int main()
{
    // --- settings file ---
    CHECK(kDefault == kContinue);
    {
        Settings d = parseSettings("");
        CHECK(d.choice == kContinue && d.session.empty());
        Settings s; s.choice = kSavedSession; s.session = "Evening\tTV\nshows";
        const Settings r = parseSettings(serializeSettings(s));
        CHECK(r.choice == kSavedSession && r.session == "Evening TV shows");
        CHECK(parseSettings("omni-startup\t1\r\nchoice\t2\r\n").choice == kHomePage);   // CRLF
        CHECK(parseSettings("omni-startup\t1\nchoice\t7\n").choice == kContinue);        // out of range
        CHECK(parseSettings("omni-startup\t1\nchoice\t-1\n").choice == kContinue);
        CHECK(parseSettings("omni-startup\t1\nchoice\tx\n").choice == kContinue);
        CHECK(parseSettings("garbage\nchoice\t1\n").choice == kContinue);                // no header
        CHECK(parseSettings("omni-startup\t1\nchoice\t1\nfuture\tline\n").choice == kStartPage);
    }
    // --- marker file ---
    {
        Marker m; m.active = A; m.streakUrl = A; m.streak = 2; m.held = A; m.crashLog = 1234;
        Marker r;
        CHECK(parseMarker(serializeMarker(m), r));
        CHECK(r.active == A && r.streakUrl == A && r.streak == 2 && r.held == A && r.crashLog == 1234);
        CHECK(!parseMarker("", r) && r.crashLog == -1 && r.streak == 0);
        CHECK(!parseMarker("hello\n", r));
        CHECK(parseMarker("omni-running\t1\n", r) && r.active.empty() && r.crashLog == -1);
        CHECK(parseMarker("omni-running\t1\nstreak\tx\thttps://a/\n", r) && r.streak == 0);
        CHECK(parseMarker("omni-running\t1\nstreak\t3\tjavascript:alert(1)\n", r) && r.streak == 0 && r.streakUrl.empty());
        CHECK(parseMarker("omni-running\t1\nstreak\t500\thttps://a/\n", r) && r.streak == kStreakMax);
        CHECK(parseMarker("omni-running\t1\ncrashlog\t-5\n", r) && r.crashLog == -1);
        Marker e; e.active = kPrivate;
        CHECK(serializeMarker(e).find("active\tprivate\n") != std::string::npos);
        CHECK(serializeMarker(Marker()) == "omni-running\t1\n");
        Marker t; t.active = "https://a/\tb\nc";                      // one line per field
        CHECK(parseMarker(serializeMarker(t), r) && r.active == "https://a/ b c");
    }
    // --- crash rule ---
    {
        Verdict clean = verdict(false, Marker(), 999);
        CHECK(!clean.unclean && !clean.hold && clean.streak == 0 && clean.streakUrl.empty());

        // crash 1 with A shown (crash.log grew) -> streak 1, not held
        Verdict v1 = verdict(true, runMarker(Verdict(), A, 100), 180);
        CHECK(v1.unclean && v1.counted && v1.blamed == A && v1.streak == 1 && v1.streakUrl == A && !v1.hold);
        // crash 2 in a row with A shown -> held
        Verdict v2 = next(runMarker(v1, A, 180), 260);
        CHECK(v2.streak == 2 && v2.hold && v2.blamed == A);
        // held run, never loaded, Omni crashes again with A (unloaded) shown: no new count, still held
        Verdict v3 = next(runMarker(v2, A, 260, A), 300);
        CHECK(v3.streak == 2 && v3.hold);
        // user loaded it (held cleared) and it crashed again: 3, held
        Verdict v4 = next(runMarker(v3, A, 300), 400);
        CHECK(v4.streak == 3 && v4.hold);
        // a clean exit forgets everything
        CHECK(!verdict(false, runMarker(v4, A, 400), 500).hold);

        // crash with A, then crash with B: B starts at 1, A not held
        Verdict w2 = next(runMarker(v1, B, 180), 200);
        CHECK(w2.streak == 1 && w2.streakUrl == B && !w2.hold);
        // then crash with A again: restarts at 1 (not "in a row")
        Verdict w3 = next(runMarker(w2, A, 200), 220);
        CHECK(w3.streak == 1 && w3.streakUrl == A && !w3.hold);

        // killed / power loss (crash.log did not grow): unclean, but no count and the streak stays
        Verdict k1 = next(runMarker(v1, A, 180), 180);
        CHECK(k1.unclean && !k1.counted && k1.streak == 1 && k1.streakUrl == A && !k1.hold);
        // closing from the system menu twice on the same page never holds it
        Verdict k2 = next(runMarker(k1, A, 180), 180);
        CHECK(!k2.hold && k2.streak == 1);
        // ... and a real crash after the kill continues the streak
        Verdict k3 = next(runMarker(k2, A, 180), 240);
        CHECK(k3.hold && k3.streak == 2);
        // an earlier streak survives a kill with another page shown, and is not that page's
        Verdict k4 = next(runMarker(v2, B, 260), 260);
        CHECK(!k4.hold && k4.streakUrl == A && k4.streak == 2 && k4.blamed == B);

        // a private tab or the start page shown: nobody blamed, never held
        Verdict p1 = next(runMarker(v2, kPrivate, 260), 400);
        CHECK(p1.unclean && p1.counted && p1.blamed.empty() && !p1.hold && p1.streakUrl == A && p1.streak == 2);
        Verdict p2 = next(runMarker(v2, "", 260), 400);
        CHECK(p2.blamed.empty() && !p2.hold);
        // unknown crash.log size (old / damaged marker): not counted
        Marker u; u.active = A; u.streakUrl = A; u.streak = 1;
        Verdict uv = verdict(true, u, 10);
        CHECK(uv.unclean && !uv.counted && uv.streak == 1 && !uv.hold);
        // a damaged marker file still means "didn't close properly"
        Marker junk; parseMarker("\x01\x02", junk);
        CHECK(verdict(true, junk, 0).unclean);
        // crash.log replaced by a smaller file: not a crash report
        CHECK(!next(runMarker(v1, A, 500), 100).counted);
    }
    // --- choice -> plan ---
    {
        Settings s;
        Plan p = plan(s, "", -1, true, 3);
        CHECK(p.open == Plan::kLast && !p.prompt);                       // Continue never prompts
        s.choice = kStartPage;
        p = plan(s, "https://home.example/", -1, false, 3);
        CHECK(p.open == Plan::kNewTab && !p.prompt);                     // clean exit: no prompt
        p = plan(s, "", -1, true, 3);
        CHECK(p.open == Plan::kNewTab && p.prompt && p.restorable == 3);
        p = plan(s, "", -1, true, 0);
        CHECK(!p.prompt);                                                 // nothing to restore
        s.choice = kHomePage;
        p = plan(s, "https://home.example/", -1, true, 2);
        CHECK(p.open == Plan::kHome && p.prompt && !p.missingHome);
        p = plan(s, "", -1, false, 2);
        CHECK(p.open == Plan::kNewTab && p.missingHome);
        p = plan(s, "omni://pages/start", -1, false, 2);
        CHECK(p.open == Plan::kNewTab && p.missingHome);
        s.choice = kSavedSession; s.session = "Evening";
        p = plan(s, "", 2, true, 1);
        CHECK(p.open == Plan::kSession && p.prompt);
        p = plan(s, "", -1, false, 1);
        CHECK(p.open == Plan::kNewTab && p.missingSession);
        CHECK(restorable({ "newtab", A, "newtab", B, "about:blank" }) == 2);
        CHECK(restorable({}) == 0);
    }
    // --- stepper ---
    {
        CHECK(step(kContinue, 1, true) == kStartPage);
        CHECK(step(kHomePage, 1, true) == kSavedSession);
        CHECK(step(kHomePage, 1, false) == kContinue);                    // no sessions: skipped
        CHECK(step(kContinue, -1, false) == kHomePage);
        CHECK(step(kContinue, -1, true) == kSavedSession);
        CHECK(step(kSavedSession, 1, true) == kContinue);
        CHECK(step(kStartPage, 0, true) == kStartPage);
        Choice c = kContinue;
        for (int i = 0; i < 8; ++i) { c = step(c, 1, false); CHECK(c != kSavedSession); }
    }
    // --- texts ---
    {
        Settings s;
        CHECK(valueText(s, false, false) == "Continue where you left off");
        s.choice = kStartPage; CHECK(valueText(s, false, false) == "Open the start page");
        s.choice = kHomePage; CHECK(valueText(s, false, true) == "Open my home page");
        CHECK(valueText(s, false, false) == "Open my home page (not set)");
        s.choice = kSavedSession; s.session = "Evening";
        CHECK(valueText(s, true, false) == "Open a saved session: Evening");
        CHECK(valueText(s, false, false) == "Open a saved session (pick)");
        CHECK(std::string(promptTitle()) == "Omni didn't close properly.");
        CHECK(promptBody(3) == "Restore your 3 tabs?");
        CHECK(promptBody(1) == "Restore your tab?");
        CHECK(std::string(restoreLabel()) == "Restore" && std::string(notNowLabel()) == "Not now");
        CHECK(std::string(holdNotice()) == "This page may have crashed Omni \xe2\x80\x94 tap to load");
        CHECK(hostOf(A) == "example.com");
        CHECK(hostOf("https://user:pw@www.a.b:8080/x") == "a.b:8080");
        CHECK(holdBody(A).find("example.com was open the last 2 times") == 0);
        Plan p; p.missingHome = true;
        CHECK(startNotice(p, "", 1) == "No home page set: opened the start page");
        Plan q; q.open = Plan::kSession;
        CHECK(startNotice(q, "Evening", 3) == "Opened \"Evening\": 3 tabs");
        CHECK(startNotice(Plan(), "", 1).empty());
        CHECK(pickedNotice("Evening") == "On start: open \"Evening\"");
    }
    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
