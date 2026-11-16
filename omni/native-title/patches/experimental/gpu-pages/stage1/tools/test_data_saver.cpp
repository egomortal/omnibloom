// OMNI_DATA_SAVER_V1: host tests of the pure part (engine/entry/OmniDataSaver.h), with OMNI_AUTOPLAY_V1's decide().
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_data_saver.cpp -o t && ./t
#include "OmniDataSaver.h"
#include "OmniAutoplay.h"
#include <cstdio>
#include <cstring>
#include <map>
#include <string>

static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

namespace D = OmniDataSaver;
namespace A = OmniAutoplay;

static void fileFormat()
{
    D::Settings s;
    CHECK(!s.on && s.video && s.autoplay && !s.fonts && s.prefetch);   // defaults: off; fonts opt-in
    CHECK(D::parse("") == D::Settings());
    CHECK(D::parse("garbage\non\t1\n") == D::Settings());              // no header: defaults (off)
    CHECK(D::parse("omni-data-saver\t2\non\t1\n") == D::Settings());   // another version: defaults
    s.on = true; s.fonts = true; s.prefetch = false;
    const std::string text = D::serialize(s);
    CHECK(text == "omni-data-saver\t1\non\t1\nvideo\t1\nautoplay\t1\nfonts\t1\nprefetch\t0\n");
    CHECK(D::parse(text) == s);
    std::string crlf;
    for (char c : text) { if (c == '\n') crlf += '\r'; crlf += c; }
    CHECK(D::parse(crlf) == s);                                          // CRLF file
    D::Settings p = D::parse("omni-data-saver\t1\non\t1\nvideo\tyes\nfuture\t1\nautoplay\t0\nnotab\n");
    CHECK(p.on && p.video && !p.autoplay && !p.fonts && p.prefetch);     // bad value / unknown key / no tab skipped
    CHECK(D::parse("omni-data-saver\t1\non\t1") .on);                    // no final newline
}

static void effective()
{
    D::Settings s;   // off: no part acts, whatever the parts say
    s.fonts = true;
    CHECK(!D::videoCap(s) && !D::autoplayBlocked(s) && !D::fontsBlocked(s) && !D::prefetchOff(s));
    s.on = true;
    CHECK(D::videoCap(s) && D::autoplayBlocked(s) && D::fontsBlocked(s) && D::prefetchOff(s));
    s.video = false; s.autoplay = false;
    CHECK(!D::videoCap(s) && !D::autoplayBlocked(s));
    for (int id = D::kRowVideo; id <= D::kRowPrefetch; ++id) CHECK(D::part(s, id) && *D::partLabel(id) && *D::partDetail(id, true) && *D::partDetail(id, false));
    CHECK(!D::part(s, D::kRowMain) && !D::part(s, 830));
    CHECK(D::part(s, D::kRowFonts) == &s.fonts);
}

static void sizeCap()
{
    CHECK(D::dimension("1080") == 1080);
    CHECK(D::dimension(" \"720\" ") == 720);
    CHECK(D::dimension("") == 0 && D::dimension("12a") == 0 && D::dimension("-480") == 0 && D::dimension("4.5") == 0);
    CHECK(D::dimension("9999999") == 0);                  // absurd: ignored
    CHECK(!D::overCap(0, 0));
    CHECK(!D::overCap(854, 480) && !D::overCap(640, 360) && !D::overCap(426, 240));
    CHECK(D::overCap(1280, 720) && D::overCap(1920, 1080) && D::overCap(3840, 2160));
    CHECK(!D::overCap(480, 854));                         // portrait 480p passes
    CHECK(D::overCap(720, 1280) && D::overCap(1080, 1920)); // portrait 720p / 1080p (Shorts) capped
    CHECK(D::overCap(0, 720) && !D::overCap(0, 480));     // height only
    CHECK(D::overCap(1280, 0) && !D::overCap(854, 0));    // width only
    D::Recheck r;
    CHECK(r.due(0));
    r.set(1000, true);
    CHECK(!r.due(1000) && !r.due(2999) && r.due(3000) && r.due(500) /* clock went back */);
    CHECK(r.value);
}

static void autoplay()
{
    A::Store user;   // the user's own choice: Allow, one site rule
    user.global = A::kAllow;
    user.sites["news.example"] = A::kNoSound;
    const std::map<std::string, A::Mode> none;
    // data saver off: exactly the user's store
    A::Decision d = A::decide(D::autoplayStore(user, false, A::kBlock), none, "https://www.other.example/", false);
    CHECK(d.mode == A::kAllow && d.source == A::kGlobal && !A::needsPolicy(d));
    // on: the global is "Block all"
    d = A::decide(D::autoplayStore(user, true, A::kBlock), none, "https://www.other.example/", false);
    CHECK(d.mode == A::kBlock && d.source == A::kGlobal && A::needsPolicy(d));
    // a site rule still wins
    d = A::decide(D::autoplayStore(user, true, A::kBlock), none, "https://www.news.example/a", false);
    CHECK(d.mode == A::kNoSound && d.source == A::kSite);
    // a private-tab session rule still wins in a private tab
    std::map<std::string, A::Mode> session; session["other.example"] = A::kAllow;
    d = A::decide(D::autoplayStore(user, true, A::kBlock), session, "https://other.example/", true);
    CHECK(d.mode == A::kAllow && d.source == A::kSite);
    // OMNI_AUTOPLAY_V1's built-in exception stays (YouTube starts the clicked video through autoplay)
    d = A::decide(D::autoplayStore(user, true, A::kBlock), none, "https://www.youtube.com/watch?v=x", false);
    CHECK(d.mode == A::kAllow && d.source == A::kBuiltIn);
    // the user's store is not changed (turning data saver off brings it back)
    CHECK(user.global == A::kAllow && user.sites.size() == 1);
    // the user's own "Block sound" is replaced while on, kept when off
    user.global = A::kNoSound;
    CHECK(D::autoplayStore(user, true, A::kBlock).global == A::kBlock);
    CHECK(D::autoplayStore(user, false, A::kBlock).global == A::kNoSound);
    CHECK(D::autoplayDetail("Allow").find("(Allow)") != std::string::npos);
}

static void texts()
{
    D::Settings s;
    CHECK(D::mainDetail(s, true).find("metered") != std::string::npos);
    s.on = true;
    CHECK(D::mainDetail(s, true) == "Video up to 480p, no autoplay, no link prefetch");
    CHECK(D::mainDetail(s, false) == "480p cap needs engine update, no autoplay, no link prefetch");
    s.video = false; s.fonts = true;
    CHECK(D::mainDetail(s, false) == "No autoplay, no web fonts, no link prefetch");
    s.autoplay = s.fonts = s.prefetch = false;
    CHECK(D::mainDetail(s, true) == "On, every part below is off");
    CHECK(D::mainNotice(D::Settings(), false, true) == "Data saver off: your own settings are back. Reloading");
    D::Settings on; on.on = true;
    CHECK(D::mainNotice(on, true, false) == "Data saver on: Video up to 480p, no autoplay, no link prefetch");
    CHECK(D::partNotice(D::kRowFonts, true) == "Data saver: block web fonts on (reload pages to apply)");
    CHECK(!strcmp(D::onOff(true), "On") && !strcmp(D::onOff(false), "Off"));
    // the video part without the engine cap: honest value / detail; other parts unchanged
    CHECK(D::partValue(on, D::kRowVideo, false) == "On (needs engine update)");
    CHECK(D::partValue(on, D::kRowVideo, true) == "On");
    D::Settings novid = on; novid.video = false;
    CHECK(D::partValue(novid, D::kRowVideo, false) == "Off");
    CHECK(D::partValue(on, D::kRowFonts, false) == "Off" && D::partValue(on, D::kRowPrefetch, false) == "On");
    CHECK(std::string(D::partDetail(D::kRowVideo, false)).find("needs engine update") != std::string::npos);
    CHECK(std::string(D::kCapFlag) == "/data/omni/data-saver-cap.flag");
}

static void topBar()
{
    // after the Downloads ring when it is drawn, else where the ring would start
    CHECK(D::startX(1160.f, 0, 0, 0) == 1160.f);
    CHECK(D::startX(1160.f, 2, 1170.f, 50.f) == 1170.f + 50.f + D::kBadgeGap);
    D::BadgeLayout b = D::badgeLayout(1160.f, 34.f);   // room 116: dot + text
    CHECK(b.mode == 2 && b.textMax == int(D::kTopBarRight - 1160.f - D::kDot - D::kTextGap));
    b = D::badgeLayout(1250.f, 34.f);                  // room 26: dot only
    CHECK(b.mode == 1);
    b = D::badgeLayout(1272.f, 34.f);                  // room 4: hidden
    CHECK(b.mode == 0);
}

static void fontRules()
{
    const std::string r = D::kFontRules;
    CHECK(r.front() == '[' && r.back() == ']');
    CHECK(r.find("\"resource-type\":[\"font\"]") != std::string::npos);
    CHECK(r.find("\"type\":\"block\"") != std::string::npos);
    CHECK(r.find("\"url-filter\":\"^omni:\"},\"action\":{\"type\":\"ignore-previous-rules\"}") != std::string::npos);
    int depth = 0; bool ok = true;
    for (char c : r) { if (c == '{' || c == '[') ++depth; if (c == '}' || c == ']') --depth; if (depth < 0) ok = false; }
    CHECK(ok && depth == 0);
}

int main()
{
    fileFormat();
    effective();
    sizeCap();
    autoplay();
    texts();
    topBar();
    fontRules();
    printf("%s: %d checks, %d failed\n", failures ? "FAILED" : "ok", checks, failures);
    return failures ? 1 : 0;
}
