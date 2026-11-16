// OMNI_AUTO_FULLSCREEN_V1: host tests of engine/entry/OmniAutoFullscreen.h (written by apply_auto_fullscreen.py).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_auto_fullscreen.cpp -o t && ./t [script.js]
// With an argument, the page script is written there wrapped in an async function (node --check / the .mjs test).
#include "OmniAutoFullscreen.h"
#include <cstdio>
#include <fstream>

namespace A = OmniAutoFullscreen;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static A::Input in(uintptr_t tab, const std::string& url, bool playing, bool fullscreen = false, bool on = true)
{
    A::Input i; i.tab = tab; i.url = url; i.playing = playing; i.fullscreen = fullscreen; i.on = on;
    return i;
}

int main(int argc, char** argv)
{
    // --- host keys ---
    CHECK(A::hostKey("https://User@WWW.Example.COM:8443/a?b#c") == "example.com");
    CHECK(A::hostKey("HTTP://www.example.com.") == "example.com");
    CHECK(A::hostKey("https://www.com/") == "www.com");
    CHECK(A::hostKey("http://[::1]:8080/x") == "::1");
    CHECK(A::hostKey("http://[::1]x/") == "");
    CHECK(A::hostKey("omni://settings") == "");
    CHECK(A::hostKey("about:blank") == "");
    CHECK(A::hostKey("https://exa mple.com/") == "");
    CHECK(A::hostKey("https:///path") == "");
    CHECK(A::hostKey("https://vimeo.com") == "vimeo.com");

    // --- YouTube TV ---
    CHECK(A::tvUrl("https://www.youtube.com/tv"));
    CHECK(A::tvUrl("https://www.youtube.com/tv#/watch?v=abc"));
    CHECK(A::tvUrl("https://youtube.com/tv/"));
    CHECK(A::tvUrl("https://m.youtube.com/TV?x=1"));
    CHECK(!A::tvUrl("https://www.youtube.com/watch?v=abc"));
    CHECK(!A::tvUrl("https://www.youtube.com/tvshows"));
    CHECK(!A::tvUrl("https://notyoutube.com/tv"));
    CHECK(!A::tvUrl("https://youtube.com.evil.net/tv"));

    // --- store ---
    A::Store s;
    A::Session sess;
    bool now = false;
    CHECK(A::toggle(s, sess, "example.com", false, now) && now && A::saved(s, "example.com"));
    CHECK(A::enabled(s, sess, "example.com", false) && A::enabled(s, sess, "example.com", true));
    CHECK(A::toggle(s, sess, "example.com", true, now) && !now);          // private: session off, saved stays on
    CHECK(A::saved(s, "example.com") && !A::enabled(s, sess, "example.com", true) && A::enabled(s, sess, "example.com", false));
    CHECK(A::toggle(s, sess, "example.com", true, now) && now && sess.empty());   // back to the saved choice: no session row
    CHECK(A::toggle(s, sess, "private.net", true, now) && now && !A::saved(s, "private.net") && !A::enabled(s, sess, "private.net", false));
    CHECK(!A::toggle(s, sess, "", false, now));
    s.sites.insert("::1");
    const std::string text = A::serialize(s);
    CHECK(text == "omni-site-autofs\t1\nfullscreen\t::1\nfullscreen\texample.com\n");
    const A::Store back = A::parse(text + "fullscreen\twww.example.org\nfullscreen\tbad/host\nother\tx.com\r\nfullscreen\tCASE.com\nfullscreen\tok.com\r\n");
    CHECK(back.sites.size() == 3 && back.sites.count("::1") && back.sites.count("example.com") && back.sites.count("ok.com"));
    A::Store full;
    for (size_t i = 0; i < A::kMaxSites; ++i) full.sites.insert("s" + std::to_string(i) + ".com");
    CHECK(!A::setSite(full, "new.com", true) && A::setSite(full, "s1.com", true) && A::setSite(full, "s1.com", false));
    CHECK(A::serialize(full).size() < size_t(A::kMaxFileBytes));

    // --- answers ---
    CHECK(A::parseAnswer("omni-autofs;ok") == A::Answer::Ok);
    CHECK(A::parseAnswer("omni-autofs;sent") == A::Answer::Sent);
    CHECK(A::parseAnswer("omni-autofs;already") == A::Answer::Already);
    CHECK(A::parseAnswer("omni-autofs;novideo") == A::Answer::NoVideo);
    CHECK(A::parseAnswer("omni-autofs;fail:NotAllowedError") == A::Answer::Failed);
    CHECK(A::parseAnswer("") == A::Answer::None && A::parseAnswer("omni-autofs;okay") == A::Answer::None);

    // --- tracker: start -> request -> ok -> fullscreen -> pause 10 s -> exit ---
    const std::string u = "https://vimeo.com/1";
    {
        A::Tracker t;
        CHECK(t.step(in(1, u, false), 0) == A::Act::None);
        CHECK(t.step(in(1, u, true), 250) == A::Act::Request && t.phase == A::Phase::Asking);
        const unsigned g = t.gen;
        CHECK(t.answered(A::Answer::Ok, 1, g + 1, 300) == A::Act::None && t.phase == A::Phase::Asking);   // stale gen
        CHECK(t.answered(A::Answer::Ok, 2, g, 300) == A::Act::None && t.phase == A::Phase::Asking);       // other tab
        CHECK(t.answered(A::Answer::Ok, 1, g, 300) == A::Act::None && t.phase == A::Phase::Full);
        CHECK(t.step(in(1, u, true), 500) == A::Act::None);                     // fullscreen not there yet: grace
        CHECK(t.step(in(1, u, true, true), 750) == A::Act::None && t.seenFull);
        CHECK(t.step(in(1, u, false, true), 1000) == A::Act::None);             // paused
        CHECK(t.step(in(1, u, true, true), 5000) == A::Act::None);              // resumed within 10 s: nothing new
        CHECK(t.step(in(1, u, false, true), 6000) == A::Act::None);
        CHECK(t.step(in(1, u, false, true), 15999) == A::Act::None);
        CHECK(t.step(in(1, u, false, true), 16000) == A::Act::Exit && t.phase == A::Phase::Idle);
        CHECK(t.step(in(1, u, false, false), 16250) == A::Act::None);
        CHECK(t.step(in(1, u, true, false), 20000) == A::Act::Request);         // played again: once more
    }
    // --- the user leaves Omni's fullscreen by hand: not again on that address; another address: again ---
    {
        A::Tracker t;
        t.step(in(1, u, false), 0);
        CHECK(t.step(in(1, u, true), 250) == A::Act::Request);
        t.answered(A::Answer::Ok, 1, t.gen, 260);
        t.step(in(1, u, true, true), 500);
        CHECK(t.step(in(1, u, true, false), 750) == A::Act::None && t.phase == A::Phase::Idle && t.declined == u);
        CHECK(t.step(in(1, u, false), 1000) == A::Act::None);
        CHECK(t.step(in(1, u, true), 1250) == A::Act::None);                    // same page: respected
        CHECK(t.step(in(1, "https://vimeo.com/2", false), 1500) == A::Act::None && t.declined.empty());
        CHECK(t.step(in(1, "https://vimeo.com/2", true), 1750) == A::Act::Request);
    }
    // --- fallbacks: no video / refused / no answer / fullscreen never arrives ---
    {
        A::Tracker t;
        t.step(in(1, u, false), 0);
        t.step(in(1, u, true), 250);
        CHECK(t.answered(A::Answer::NoVideo, 1, t.gen, 300) == A::Act::StartBars && t.barsFor(1) && !t.barsFor(2) && !t.barsFor(0));
        CHECK(t.step(in(1, u, false), 1000) == A::Act::None && t.barsFor(1));
        CHECK(t.step(in(1, u, true), 3000) == A::Act::None && t.barsFor(1));       // resumed: still the same playback
        CHECK(t.step(in(1, u, false), 4000) == A::Act::None);
        CHECK(t.step(in(1, u, false), 14000) == A::Act::EndBars && t.idle());
    }
    {
        A::Tracker t;
        t.step(in(1, u, false), 0);
        t.step(in(1, u, true), 250);
        CHECK(t.answered(A::Answer::Failed, 1, t.gen, 300) == A::Act::StartBars);
        CHECK(t.step(in(1, u, true, true), 500) == A::Act::EndBars && t.idle());  // the page went fullscreen itself
    }
    {
        A::Tracker t;
        t.step(in(1, u, false), 0);
        t.step(in(1, u, true), 250);
        const unsigned g = t.gen;
        CHECK(t.step(in(1, u, true), 4249) == A::Act::None);
        CHECK(t.step(in(1, u, true), 4250) == A::Act::StartBars);
        CHECK(t.answered(A::Answer::Ok, 1, g, 4300) == A::Act::None && t.phase == A::Phase::Bars);   // too late: dropped
    }
    {
        A::Tracker t;
        t.step(in(1, u, false), 0);
        t.step(in(1, u, true), 250);
        t.answered(A::Answer::Sent, 1, t.gen, 300);
        CHECK(t.step(in(1, u, true), 2299) == A::Act::None);
        CHECK(t.step(in(1, u, true), 2300) == A::Act::StartBars);
    }
    {
        A::Tracker t;
        t.step(in(1, u, false), 0);
        t.step(in(1, u, true), 250);
        CHECK(t.answered(A::Answer::Already, 1, t.gen, 300) == A::Act::None && t.idle());
    }
    // --- never: off, excluded, busy, already fullscreen, background / switched tabs ---
    {
        A::Tracker t;
        t.step(in(1, u, false, false, false), 0);
        CHECK(t.step(in(1, u, true, false, false), 250) == A::Act::None);       // site not set
        A::Input x = in(1, u, false); x.excluded = true;
        t.step(x, 500);
        x.playing = true;
        CHECK(t.step(x, 750) == A::Act::None);                                   // YouTube TV / game mode
        A::Tracker b;
        b.step(in(1, u, false), 0);
        A::Input busy = in(1, u, true); busy.busy = true;
        CHECK(b.step(busy, 250) == A::Act::None);                                // a panel is open: this start skipped
        CHECK(b.step(in(1, u, true), 500) == A::Act::None);                      // no edge any more
        A::Tracker f;
        f.step(in(1, u, false, true), 0);
        CHECK(f.step(in(1, u, true, true), 250) == A::Act::None);                // the page is fullscreen already
        A::Tracker s2;
        CHECK(s2.step(in(1, u, true), 0) == A::Act::None);                       // first sight: playing already, no edge
        CHECK(s2.step(in(2, u, true), 250) == A::Act::None);                     // switched to a playing tab: no edge
        CHECK(s2.step(in(2, u, false), 500) == A::Act::None);
        CHECK(s2.step(in(2, u, true), 750) == A::Act::Request);
        const unsigned g = s2.gen;
        CHECK(s2.step(in(1, u, true), 800) == A::Act::None);                     // tab switch while asking
        CHECK(s2.answered(A::Answer::NoVideo, 2, g, 900) == A::Act::None && s2.idle());
    }
    // --- bars end when the tab is left or the site turned off ---
    {
        A::Tracker t;
        t.step(in(1, u, false), 0);
        t.step(in(1, u, true), 250);
        t.answered(A::Answer::NoVideo, 1, t.gen, 300);
        CHECK(t.step(in(2, u, true), 500) == A::Act::EndBars && !t.barsFor(2));
        A::Tracker o;
        o.step(in(1, u, false), 0);
        o.step(in(1, u, true), 250);
        o.answered(A::Answer::NoVideo, 1, o.gen, 300);
        CHECK(o.step(in(1, u, true, false, false), 500) == A::Act::EndBars && o.idle());
    }
    // --- timers wrap ---
    {
        A::Tracker t;
        const uint32_t base = 0xFFFFF000u;
        t.step(in(1, u, false), base);
        t.step(in(1, u, true), base + 100);
        t.answered(A::Answer::NoVideo, 1, t.gen, base + 200);
        t.step(in(1, u, false), base + 300);
        CHECK(t.step(in(1, u, false), base + 300 + A::kLeaveMs - 1) == A::Act::None);
        CHECK(t.step(in(1, u, false), base + 300 + A::kLeaveMs) == A::Act::EndBars);
    }

    // --- texts and the script ---
    CHECK(A::rowValue(true) == "Fullscreen when playing" && A::rowValue(false) == "Normal");
    CHECK(A::siteNotice("example.com", true, true, false) == "Video on example.com: fullscreen when playing (this session only)");
    CHECK(A::siteNotice("example.com", false, false, false) == "Video on example.com: normal");
    const std::string js = A::pageScript();
    CHECK(js.find("const waitMs = 2500;") != std::string::npos && js.find("const tag = \"omni-autofs;\";") != std::string::npos);
    CHECK(js.find("requestFullscreen") < js.find("await"));                       // the request comes before any await
    CHECK(js.size() > 10 && js.substr(js.size() - 4) == "});\n");                 // the end is intact
    if (argc > 1) {
        std::ofstream f(argv[1], std::ios::binary);
        f << "export async function run(document, setTimeout) {\n" << js << "}\n";
    }
    std::printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
