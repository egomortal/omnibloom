// OMNI_REDUCE_MOTION_V1: host test of the pure part (OmniReduceMotion.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_reduce_motion.cpp -o t && ./t [<tree>/engine/entry]
// With the tree's entry folder it also checks the durations against the tree: before apply_reduce_motion.py the original
// call sites carry exactly the numbers OmniReduceMotion.h names; after it every site uses ORMO and no original is left.
#include "OmniReduceMotion.h"
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

namespace R = OmniReduceMotion;
static int failures = 0, checks = 0;
static void expect(bool ok, const char* what)
{
    ++checks;
    if (!ok) { ++failures; std::printf("FAIL: %s\n", what); }
}
static bool near(float a, float b, float eps = 1e-5f) { return std::fabs(a - b) <= eps; }

// OmniScrollPlus::alpha, copied (the tree check below compares the constants it uses).
static uint8_t scrollAlpha(uint32_t since)
{
    const uint32_t hold = 700, fade = 300;
    if (since <= hold) return 255;
    if (since >= hold + fade) return 0;
    return uint8_t(255 - (255 * (since - hold)) / fade);
}

static void testMapping()
{
    const uint32_t all[] = { R::kBarSlideMs, R::kPointerSnapMs, R::kProgressFillMs, R::kProgressFinishMs, R::kProgressFadeMs,
        R::kToastInMs, R::kToastOutMs, R::kPanelFadeMs, R::kNightLightMs, R::kScrollbarFadeMs, 0, 1, 79, 80, 81, 100000 };
    for (uint32_t d : all) {
        expect(R::ms(false, R::Kind::Move, d) == d && R::ms(false, R::Kind::Fade, d) == d, "Off: every duration unchanged");
        expect(R::ms(true, R::Kind::Move, d) == 0, "On: movement is instant");
        expect(R::ms(true, R::Kind::Fade, d) <= R::kMaxFadeMs && R::ms(true, R::Kind::Fade, d) == std::min(d, 80u),
               "On: fades at most 80 ms (shorter ones kept)");
        expect(R::instant(true, R::Kind::Move, d) && R::instant(false, R::Kind::Move, d) == (d == 0), "instant()");
    }
    static_assert(R::ms(true, R::Kind::Fade, 150) == 80 && R::ms(true, R::Kind::Move, 220) == 0, "constexpr mapping");
    expect(R::kMaxFadeMs == 80, "the fade ceiling is 80 ms");
}

static void testHelpersMatchOriginals()
{
    // Off: each helper gives exactly what the original expression gave.
    for (int dt = 0; dt <= 100; ++dt) {
        const float f = float(dt);
        expect(near(R::tickStep(f, R::ms(false, R::Kind::Move, 220)), f / 220.f), "bar slide step = dt / 220");
        expect(near(R::tickStep(f, R::ms(false, R::Kind::Move, 160)), std::min(1.f, f / 160.f)), "progress fill = min(1, dt / 160)");
        expect(near(R::tickStep(f, R::ms(false, R::Kind::Move, 80)), std::min(1.f, f / 80.f)), "progress run-out = min(1, dt / 80)");
        expect(near(R::tickStep(f, R::ms(false, R::Kind::Fade, 260)), f / 260.f), "progress fade = dt / 260");
        expect(R::tickStep(f, R::ms(true, R::Kind::Move, 220)) == 1.f, "reduced bar slide: the whole way in one tick");
        expect(R::tickStep(f, R::ms(true, R::Kind::Fade, 260)) >= std::min(1.f, f / 80.f) - 1e-6f, "reduced progress fade: 80 ms");
    }
    for (uint32_t e = 0; e <= 400; e += 5) {
        expect(near(R::progress(e, R::ms(false, R::Kind::Move, 110)), std::min(1.f, e / 110.f)), "pointer snap = min(1, e / 110)");
        expect(R::progress(e, R::ms(true, R::Kind::Move, 110)) == 1.f, "reduced pointer snap: there at once");
        expect(near(R::toastIn(false, e), std::min(1.f, e / 180.f)), "toast in = min(1, e / 180)");
        expect(R::toastIn(true, e) == std::min(1.f, e / 80.f), "reduced toast in: 80 ms");
        // the panel fade, as omniPanelT computed it
        float orig = 1;
        if (e < 150) { const float u = 1 - e / float(150); orig = 1 - u * u * u; }
        expect(near(R::panelFade(false, e, 150), orig), "panel fade = 1 - (1 - t)^3 over 150 ms");
        expect((R::panelFade(true, e, 150) == 1.f) == (e >= 80), "reduced panel fade: done at 80 ms, not before");
    }
    for (int r = -500; r <= 500; r += 5) {
        expect(near(std::min(1.f, R::toastOut(false, r)), std::min(1.f, std::max(0.f, r / 320.f))), "toast out = max(0, r / 320)");
        expect(R::toastOut(true, r) == (r <= 0 ? 0.f : std::min(1.f, r / 80.f)), "reduced toast out: 80 ms");
    }
    expect(R::toastRise(false) == 12.f && R::toastRise(true) == 0.f, "toast rise 12 px, none reduced");
    expect(R::progress(5, 0) == 1.f && R::tickStep(0.f, 0) == 1.f, "zero duration is done");
}

static void testScrollbarClock()
{
    for (uint32_t e = 0; e <= 2000; ++e)
        expect(R::fadeClock(e, 700, 300, false) == e, "Off: the position bar's clock unchanged");
    uint8_t last = 255;
    for (uint32_t e = 0; e <= 2000; ++e) {
        const uint8_t a = scrollAlpha(R::fadeClock(e, 700, 300, true));
        expect(a <= last, "reduced position bar: never comes back while fading");
        last = a;
        if (e <= 700) expect(a == 255, "reduced: still shown for the 700 ms hold");
        if (e >= 780) expect(a == 0, "reduced: gone 80 ms after the hold");
    }
    expect(scrollAlpha(R::fadeClock(740, 700, 300, true)) > 100 && scrollAlpha(R::fadeClock(740, 700, 300, true)) < 155,
           "reduced: half way at 40 ms");
    expect(R::fadeClock(0xFFFFFFF0u, 700, 300, true) == 1000, "no overflow on a huge elapsed time");
    expect(R::fadeClock(900, 700, 0, true) == 900, "a zero fade stays as it was");
}

static void testFile()
{
    expect(R::parse("on\n") && R::parse("on") && R::parse(" on\r\n") && R::parse("\non\n"), "on");
    expect(!R::parse("off\n") && !R::parse("") && !R::parse("onx") && !R::parse("o") && !R::parse("ON"), "off / garbage");
    expect(R::parse(R::serialize(true)) && !R::parse(R::serialize(false)), "round trip");
    expect(std::string(R::rowValue(true)) == "On" && std::string(R::rowValue(false)) == "Off", "row value");
    expect(R::kRowId == 849 && std::string(R::kRowLabel) == "Reduce motion" && std::string(R::kFileName) == "reduce-motion.txt",
           "row id, label, file");
    expect(std::string(R::noticeText(true)) == "Reduce motion on", "notice");
}

static void testCss()
{
    const std::string c = R::kPageCss;
    for (const char* need : { "*,*::before,*::after{", "animation-duration:0.01ms!important", "animation-iteration-count:1!important",
                              "transition-duration:0.01ms!important", "scroll-behavior:auto!important" })
        expect(c.find(need) != std::string::npos, need);
    int depth = 0, opens = 0;
    for (char ch : c) { if (ch == '{') { ++depth; ++opens; } if (ch == '}') --depth; expect(depth >= 0 && depth <= 1, "braces"); }
    expect(depth == 0 && opens == 1 && c.back() == '}', "one rule, balanced");
    expect(c.find('<') == std::string::npos && c.find('"') == std::string::npos && c.find('\\') == std::string::npos
           && c.find('\n') == std::string::npos, "plain CSS, safe as a C string and a sheet");
}

static std::string slurp(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    std::stringstream s; s << f.rdbuf();
    return s.str();
}
static int count(const std::string& s, const std::string& what)
{
    int n = 0;
    for (size_t p = s.find(what); p != std::string::npos; p = s.find(what, p + what.size())) ++n;
    return n;
}

static void testTree(const std::string& dir)
{
    const std::string browser = slurp(dir + "/OmniBrowser.cpp"), pointer = slurp(dir + "/OmniPointerFeel.h"),
        night = slurp(dir + "/OmniNightLight.h"), nightShell = slurp(dir + "/OmniNightLightShell.h"),
        scroll = slurp(dir + "/OmniScrollPlus.h"), scrollShell = slurp(dir + "/OmniScrollPlusShell.h");
    expect(!browser.empty() && !pointer.empty() && !night.empty(), "tree files found");
    expect(count(browser, "constexpr uint32_t omniPanelFadeMs = 150;") == 1, "tree: omniPanelFadeMs = kPanelFadeMs (150)");
    expect(count(night, "constexpr uint32_t kFadeMs = 2000;") == 1, "tree: night light fade = kNightLightMs (2000)");
    if (!scroll.empty()) expect(count(scroll, "constexpr uint32_t kHoldShownMs = 700, kFadeMs = 300;") == 1, "tree: scroll bar 700 + 300");
    const bool patched = browser.find("OMNI_REDUCE_MOTION_V1") != std::string::npos;
    std::printf("tree: %s%s\n", patched ? "patched" : "not patched yet", scroll.empty() ? " (no scroll plus)" : "");
    if (!patched) {   // the originals carry the numbers this header names
        expect(count(browser, "const float step = dt / 220.f;") == 1, "tree: bar slide 220");
        expect(count(browser, "std::min(1.f, dt / 160.f)") == 1 && count(browser, "std::min(1.f, dt / 80.f)") == 1
               && count(browser, "omniProgressAlpha - dt / 260.f") == 1, "tree: progress 160 / 80 / 260");
        expect(count(browser, "(now - omniToastSince) / 180.f") == 1 && count(browser, "/ 320.f));") == 2
               && count(browser, "int((1 - a) * 12)") == 1, "tree: toast 180 / 320 / 12 px");
        expect(count(pointer, "(now - omniFxPtr.animStart) / 110.f") == 1, "tree: pointer snap 110");
        return;
    }
    for (const char* site : { "ORMO::kBarSlideMs", "ORMO::kProgressFillMs", "ORMO::kProgressFinishMs", "ORMO::kProgressFadeMs",
                              "ORMO::panelFade(", "ORMO::toastIn(", "ORMO::toastRise(", "namespace ORMO = OmniReduceMotion;",
                              "static bool omniRmOn();", "#include \"OmniReduceMotion.h\"" })
        expect(count(browser, site) == 1, site);
    expect(count(browser, "ORMO::toastOut(") == 2, "both toast fade-outs");
    expect(count(browser, "dt / 220.f;") == 0 && count(browser, "dt / 260.f);") == 0 && count(browser, "/ 180.f);") == 0
           && count(browser, "/ 320.f));") == 0 && count(browser, "(1 - a) * 12)") == 0, "no original left in OmniBrowser.cpp");
    expect(count(pointer, "ORMO::kPointerSnapMs") == 1 && count(pointer, "/ 110.f)") == 0, "pointer snap site");
    expect(count(nightShell, "ORMO::kNightLightMs") == 1, "night light site");
    if (!scrollShell.empty()) {
        expect(count(scrollShell, "ORMO::fadeClock(") == 3 && count(scrollShell, "OSCP::alpha(now - omniScpShownAt)") == 0, "scroll bar sites");
        expect(count(scrollShell, "if (on && omniRmOn()) on = false;") == 1, "smooth scrolling refused while reduced");
    }
}

int main(int argc, char** argv)
{
    testMapping();
    testHelpersMatchOriginals();
    testScrollbarClock();
    testFile();
    testCss();
    if (argc > 1) testTree(argv[1]);
    std::printf("%s: %d checks, %d failures\n", failures ? "FAILED" : "ok", checks, failures);
    return failures ? 1 : 0;
}
