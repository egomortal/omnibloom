// OMNI_TAB_VOLUME_V1: host tests for engine/entry/OmniTabVolume.h (the pure part of per-tab volume).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_volume.cpp -o t && ./t
#include "OmniTabVolume.h"
#include <cstdio>
#include <string>

namespace V = OmniTabVolume;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

int main()
{
    // steps
    CHECK(V::clampPct(-5) == 0 && V::clampPct(0) == 0 && V::clampPct(100) == 100 && V::clampPct(250) == 100);
    CHECK(V::clampPct(44) == 40 && V::clampPct(45) == 50 && V::clampPct(70) == 70);
    CHECK(V::step(100, 1) == 100 && V::step(100, -1) == 90 && V::step(0, -1) == 0 && V::step(0, 1) == 10);
    CHECK(V::step(70, 0) == 70 && V::step(73, 1) == 80);
    int p = 100, n = 0;
    while (p > 0) { p = V::step(p, -1); ++n; }
    CHECK(n == 10);   // 100 -> 0 in ten presses
    CHECK(V::gain(70) > 0.699f && V::gain(70) < 0.701f && V::gain(0) == 0.0f && V::gain(100) == 1.0f && V::gain(130) == 1.0f);
    CHECK(V::label(70) == "70%" && V::label(0) == "0%" && V::label(100) == "100%");
    CHECK(V::notice(30) == "Volume: 30%");
    CHECK(std::string(V::rememberValue(true)) == "On" && std::string(V::rememberValue(false)) == "Off");
    CHECK(V::rememberDetail("", false) == "Only for web sites");
    CHECK(V::rememberDetail("example.com", false).find("example.com") != std::string::npos);
    CHECK(V::rememberDetail("example.com", true).find("Private") == 0);
    CHECK(V::kRowVolume != V::kRowRemember && V::kRowVolume != 40 && V::kRowVolume != 41 && V::kRowRemember > 8);

    // resolve: own value > site > 100
    CHECK(V::resolve(V::kUnset, false, 0) == 100);
    CHECK(V::resolve(V::kUnset, true, 30) == 30);
    CHECK(V::resolve(60, true, 30) == 60);
    CHECK(V::resolve(0, true, 30) == 0);   // 0 % is a value, not "unset"

    // site keys
    CHECK(V::validSite("example.com") && V::validSite("[::1]"));
    CHECK(!V::validSite("") && !V::validSite("a b") && !V::validSite("a\tb") && !V::validSite("a\nb"));
    CHECK(!V::validSite(std::string(254, 'a')) && V::validSite(std::string(253, 'a')));

    // Sites
    V::Sites s;
    int out = -1;
    CHECK(s.empty() && !s.get("a.com", out) && out == -1);
    CHECK(s.set("a.com", 33) && s.get("a.com", out) && out == 30);
    CHECK(!s.set("bad site", 10) && s.size() == 1);
    CHECK(s.erase("a.com") && !s.erase("a.com") && s.empty());
    for (size_t i = 0; i < V::kMaxSites; ++i) CHECK(s.set("s" + std::to_string(i) + ".com", 50));
    CHECK(s.size() == V::kMaxSites && !s.set("new.com", 50) && s.set("s0.com", 20) && s.size() == V::kMaxSites);

    // file format: round trip, CRLF, bad lines, wrong header
    V::Sites f;
    f.set("music.example", 20); f.set("video.example", 0); f.set("loud.example", 100);
    const std::string text = V::serialize(f);
    CHECK(text == "omni-site-volume-1\nloud.example\t100\nmusic.example\t20\nvideo.example\t0\n");
    V::Sites g = V::parse(text);
    CHECK(g.size() == 3 && g.get("video.example", out) && out == 0 && g.get("music.example", out) && out == 20);
    V::Sites h = V::parse("omni-site-volume-1\r\na.com\t40\r\nb.com\t101\nc.com\t-1\nd.com\tx\ne.com\t\nnotab\nf.com\t1000\ng.com\t55\n\n");
    CHECK(h.size() == 2 && h.get("a.com", out) && out == 40 && h.get("g.com", out) && out == 60);
    CHECK(V::parse("something-else\na.com\t40\n").empty());
    CHECK(V::parse("").empty() && V::parse("omni-site-volume-1").empty());
    CHECK(V::serialize(V::Sites()) == "omni-site-volume-1\n");

    // setVolume: the tab always, the site only while remembered
    V::Sites r;
    int tabPct = V::kUnset;
    CHECK(V::setVolume(r, "x.com", tabPct, 70) == 70 && tabPct == 70 && r.empty());
    r.set("x.com", 50);
    V::setVolume(r, "x.com", tabPct, 20);
    CHECK(tabPct == 20 && r.get("x.com", out) && out == 20);
    V::setVolume(r, "", tabPct, 90);
    CHECK(tabPct == 90 && r.size() == 1);

    // toggleRemember
    V::Sites t;
    int tp = V::kUnset;
    CHECK(V::toggleRemember(t, "", tp) == V::Remember::kNoSite && t.empty());
    CHECK(V::toggleRemember(t, "y.com", tp) == V::Remember::kOn && t.get("y.com", out) && out == 100 && tp == V::kUnset);
    tp = 40;
    CHECK(V::toggleRemember(t, "y.com", tp) == V::Remember::kOff && t.empty() && tp == 40);
    CHECK(V::toggleRemember(t, "y.com", tp) == V::Remember::kOn && t.get("y.com", out) && out == 40);
    int follower = V::kUnset;   // a tab that followed the site value keeps it when the site is forgotten
    CHECK(V::toggleRemember(t, "y.com", follower) == V::Remember::kOff && follower == 40);
    V::Sites full;
    for (size_t i = 0; i < V::kMaxSites; ++i) full.set("f" + std::to_string(i) + ".com", 50);
    int fp = 30;
    CHECK(V::toggleRemember(full, "other.com", fp) == V::Remember::kFull && !full.has("other.com"));
    CHECK(V::rememberNotice(V::Remember::kOn, "y.com", false) == "Volume remembered for y.com");
    CHECK(V::rememberNotice(V::Remember::kOn, "y.com", true) == "Volume remembered for y.com (until Omni closes)");
    CHECK(V::rememberNotice(V::Remember::kOff, "y.com", false) == "Volume for y.com forgotten");
    CHECK(V::rememberNotice(V::Remember::kFull, "y.com", false) == "Too many sites remembered");

    // private isolation (the shell keeps two Sites; nothing crosses)
    V::Sites saved, priv;
    int a = V::kUnset, b = V::kUnset;
    V::toggleRemember(priv, "z.com", a);
    V::setVolume(priv, "z.com", a, 10);
    CHECK(priv.has("z.com") && !saved.has("z.com") && V::serialize(saved) == "omni-site-volume-1\n");
    CHECK(V::resolve(b, saved.get("z.com", out), out) == 100);

    // apply decision
    int page1 = 0, page2 = 0;
    CHECK(!V::needsApply(nullptr, -1, nullptr, 50, true));
    CHECK(V::needsApply(nullptr, -1, &page1, 50, false));
    CHECK(!V::needsApply(&page1, 50, &page1, 50, false) && V::needsApply(&page1, 50, &page1, 50, true));
    CHECK(V::needsApply(&page1, 50, &page2, 50, false) && V::needsApply(&page1, 50, &page1, 60, false));
    CHECK(V::untouched(false, 100) && !V::untouched(true, 100) && !V::untouched(false, 90));

    // poll (500 ms, wrap-safe)
    V::Poll poll;
    CHECK(poll.due(1000) && !poll.due(1200) && !poll.due(1499) && poll.due(1500));
    V::Poll wrap;
    CHECK(wrap.due(0xFFFFFF00u) && !wrap.due(0xFFFFFFF0u) && wrap.due(0xFFFFFF00u + 500u));

    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
