// OMNI_SPATIAL_NAV_V1: host tests of the pure part (OmniSpatialNav.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<dir with OmniSpatialNav.h> test_spatial_nav.cpp -o t && ./t [core.js samples.js]
// With file names it also writes the page script's function (core.js) and one built call per mode (samples.js,
// separated by "//@@" lines) for node: test_spatial_nav_js.cjs runs them on fake DOM layouts.
#include "OmniSpatialNav.h"

#include <cstdio>
#include <cstring>
#include <string>

namespace OSPN = OmniSpatialNav;

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static bool near(double a, double b) { return a - b < 1e-6 && b - a < 1e-6; }

int main(int argc, char** argv)
{
    // --- setting ---
    CHECK(OSPN::parseMode("") == OSPN::kScroll);
    CHECK(OSPN::parseMode("mode\t1\n") == OSPN::kLinks);
    CHECK(OSPN::parseMode("mode\t1\r\n") == OSPN::kLinks);
    CHECK(OSPN::parseMode("junk\nmode\t0\n") == OSPN::kScroll);
    CHECK(OSPN::parseMode("mode\t2\n") == OSPN::kScroll);
    CHECK(OSPN::parseMode("mode 1\n") == OSPN::kScroll);
    CHECK(OSPN::serialize(OSPN::kLinks) == "mode\t1\n");
    CHECK(OSPN::serialize(OSPN::kScroll) == "mode\t0\n");
    CHECK(OSPN::parseMode(OSPN::serialize(OSPN::kLinks)) == OSPN::kLinks);
    CHECK(OSPN::stepMode(OSPN::kScroll, 1) == OSPN::kLinks);
    CHECK(OSPN::stepMode(OSPN::kLinks, 1) == OSPN::kLinks);     // no wrap
    CHECK(OSPN::stepMode(OSPN::kLinks, -1) == OSPN::kScroll);
    CHECK(OSPN::stepMode(OSPN::kScroll, -1) == OSPN::kScroll);
    CHECK(OSPN::stepMode(OSPN::kScroll, 0) == OSPN::kLinks);    // Cross toggles
    CHECK(OSPN::stepMode(OSPN::kLinks, 0) == OSPN::kScroll);
    CHECK(!std::strcmp(OSPN::modeName(OSPN::kScroll), "Scroll"));
    CHECK(!std::strcmp(OSPN::modeName(OSPN::kLinks), "Move between links"));
    CHECK(!std::strcmp(OSPN::modeName(99), "Move between links"));
    CHECK(OSPN::kRowId == 857);

    // --- ring look ---
    const OSPN::Rgb teal { 112, 228, 209 }, psBlue { 38, 135, 255 }, yellow { 255, 230, 0 }, violet { 170, 132, 255 }, navy { 20, 30, 90 };
    CHECK(OSPN::hex(teal) == "#70e4d1");
    CHECK(OSPN::hex(OSPN::Rgb { 0, 0, 0 }) == "#000000");
    CHECK(OSPN::hex(OSPN::Rgb { 255, 255, 255 }) == "#ffffff");
    CHECK(OSPN::hex(OSPN::halo(teal)) == "#000000");
    CHECK(OSPN::hex(OSPN::halo(yellow)) == "#000000");
    CHECK(OSPN::hex(OSPN::halo(navy)) == "#ffffff");
    CHECK(OSPN::hex(OSPN::halo(violet)) == "#000000");
    for (const OSPN::Rgb c : { teal, psBlue, yellow, violet, navy }) CHECK(OSPN::contrast(c, OSPN::halo(c)) >= 4.5);   // the halo always reads
    CHECK(near(OSPN::contrast(OSPN::Rgb { 0, 0, 0 }, OSPN::Rgb { 255, 255, 255 }), 21.0));
    CHECK(OSPN::ringWidth(false) == 4 && OSPN::ringWidth(true) == 6);

    // --- script ---
    const std::string core = OSPN::core();
    CHECK(core.rfind("(function(M,D,PX,PY,FP,C,H,W){try{", 0) == 0);
    CHECK(core.size() > 2 && core.compare(core.size() - 2, 2, "})") == 0);   // a whole function expression, never trimmed
    CHECK(core.find('\x08') == std::string::npos);
    CHECK(core.find("Symbol.for('omni.spatialnav.v1')") != std::string::npos);
    const std::string mv = OSPN::script('m', OSPN::kDown, 123.45, 67.0, true, teal, OSPN::halo(teal), 4);
    CHECK(mv.rfind(core, 0) == 0);
    CHECK(mv.substr(core.size()) == "('m',1,123.5,67.0,1,'#70e4d1','#000000',4)");   // 123.45 is 123.45000000000000284 in binary
    const std::string act = OSPN::script('a', 7, -1, -1, false, yellow, OSPN::halo(yellow), 6);
    CHECK(act.substr(core.size()) == "('a',3,-1.0,-1.0,0,'#ffe600','#000000',6)");
    const std::string hid = OSPN::script('h', -4, 1e300, std::nan(""), false, navy, OSPN::halo(navy), 99);
    CHECK(hid.substr(core.size()) == "('h',0,1000000.0,-1.0,0,'#141e5a','#ffffff',12)");
    CHECK(OSPN::script('x', 0, 0, 0, false, teal, teal, 4).substr(core.size(), 4) == "('m'");   // unknown mode: move

    // --- answers ---
    OSPN::Answer a = OSPN::parse("moved,10.5,20.0");
    CHECK(a.kind == OSPN::aMoved && near(a.x, 10.5) && near(a.y, 20.0));
    a = OSPN::parse("pt,-3.0,7.5");
    CHECK(a.kind == OSPN::aPoint && near(a.x, -3.0) && near(a.y, 7.5));
    CHECK(OSPN::parse("none").kind == OSPN::aNone);
    CHECK(OSPN::parse("hidden").kind == OSPN::aHidden);
    CHECK(OSPN::parse("field").kind == OSPN::aField);
    CHECK(OSPN::parse("clicked").kind == OSPN::aClicked);
    CHECK(OSPN::parse("err").kind == OSPN::aBad);
    CHECK(OSPN::parse("").kind == OSPN::aBad);
    CHECK(OSPN::parse("moved,1").kind == OSPN::aBad);
    CHECK(OSPN::parse("moved,a,b").kind == OSPN::aBad);
    CHECK(OSPN::parse("moved,1,2,3").kind == OSPN::aBad);
    CHECK(OSPN::parse("jump,1,2").kind == OSPN::aBad);
    CHECK(OSPN::parse("moved,1e5,2").kind == OSPN::aBad);
    CHECK(OSPN::parse("moved,,2").kind == OSPN::aBad);

    // --- coordinates (k = CSS px per layout px; page from y 112 to 1000, 1280 wide) ---
    OSPN::Pt p = OSPN::toLayout(200, 100, 2.0, 112, 1000, 1280);
    CHECK(near(p.x, 100) && near(p.y, 162));
    p = OSPN::toLayout(-50, -50, 1.5, 112, 1000, 1280);
    CHECK(near(p.x, 0) && near(p.y, 112));
    p = OSPN::toLayout(99999, 99999, 1.0, 112, 1000, 1280);
    CHECK(near(p.x, 1279) && near(p.y, 999));
    p = OSPN::toLayout(10, 10, 0, 112, 1000, 1280);   // a bad scale counts as 1
    CHECK(near(p.x, 10) && near(p.y, 122));

    // --- one in flight ---
    OSPN::Flight f;
    CHECK(f.send(OSPN::kDown, 1000));
    CHECK(!f.send(OSPN::kRight, 1100));
    CHECK(!f.send(OSPN::kUp, 1200));                // latest wins
    CHECK(f.done() == OSPN::kUp);
    CHECK(f.send(OSPN::kUp, 1300));
    CHECK(f.done() == -1);
    CHECK(f.send(OSPN::kLeft, 2000));
    CHECK(f.send(OSPN::kDown, 2000 + OSPN::kStaleMs));   // no answer for 1.5 s: no longer blocks
    CHECK(!f.send(OSPN::kLeft, 4000));
    f.reset();
    CHECK(f.send(OSPN::kLeft, 4001) && f.pending == -1);
    CHECK(f.send(OSPN::kUp, 0xffffff00u) && !f.send(OSPN::kDown, 0x10u));   // wraps
    CHECK(f.done() == OSPN::kDown);

    // --- the ring's life ---
    int t1 = 0, t2 = 0;
    CHECK(OSPN::check(false, &t1, &t2, true, false, false) == OSPN::kKeep);
    CHECK(OSPN::check(true, &t1, &t1, false, true, true) == OSPN::kKeep);
    CHECK(OSPN::check(true, &t1, &t1, false, true, false) == OSPN::kDropMode);
    CHECK(OSPN::check(true, &t1, &t2, false, true, true) == OSPN::kDropTab);
    CHECK(OSPN::check(true, &t1, nullptr, false, true, true) == OSPN::kDropTab);
    CHECK(OSPN::check(true, &t1, &t1, true, true, true) == OSPN::kDropPointer);
    CHECK(OSPN::check(true, &t1, &t1, false, false, true) == OSPN::kDropUrl);
    CHECK(OSPN::pointerHidden(true, false, true));
    CHECK(!OSPN::pointerHidden(true, true, true));
    CHECK(!OSPN::pointerHidden(true, false, false));
    CHECK(!OSPN::pointerHidden(false, false, true));
    CHECK(OSPN::crossTakes(true, true, false));
    CHECK(!OSPN::crossTakes(true, true, true));
    CHECK(!OSPN::crossTakes(true, false, false));
    CHECK(!OSPN::crossTakes(false, true, false));
    CHECK(OSPN::fromPointer(false, true));
    CHECK(OSPN::fromPointer(true, false));
    CHECK(!OSPN::fromPointer(true, true));

    if (argc >= 3) {
        if (FILE* out = std::fopen(argv[1], "wb")) { std::fputs(core.c_str(), out); std::fclose(out); }
        if (FILE* out = std::fopen(argv[2], "wb")) {
            for (const std::string& s : { mv, act, hid }) { std::fputs(s.c_str(), out); std::fputs("\n//@@\n", out); }   // the core has newlines
            std::fclose(out);
        }
    }
    std::printf("%s: %d checks, %d failures\n", fails ? "FAIL" : "OK", checks, fails);
    return fails ? 1 : 0;
}
