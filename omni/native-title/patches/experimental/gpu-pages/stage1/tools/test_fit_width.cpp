// OMNI_FIT_WIDTH_V1: host tests for engine/entry/OmniFitWidth.h (written by apply_fit_width.py).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_fit_width.cpp -o t && ./t
//   ./t --emit <file>   writes the page script for node --check <file>
#include "OmniFitWidth.h"
#include <cstdio>
#include <cstring>
#include <fstream>

namespace OFW = OmniFitWidth;
static int fails = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); ++fails; } } while (0)

static OFW::Measure M(double v, double c, double s) { OFW::Measure m; m.ok = true; m.view = v; m.content = c; m.scroll = s; return m; }

int main(int argc, char** argv)
{
    if (argc == 3 && !std::strcmp(argv[1], "--emit")) {
        std::ofstream(argv[2]) << OFW::script() << "\n";
        return 0;
    }
    // parse
    OFW::Measure p = OFW::parse("{\"v\":1280,\"c\":960,\"s\":1280}");
    CHECK(p.ok && p.view == 1280 && p.content == 960 && p.scroll == 1280);
    CHECK(!OFW::parse("").ok);
    CHECK(!OFW::parse("{\"v\":0,\"c\":1,\"s\":1}").ok);
    CHECK(!OFW::parse("{\"v\":1280,\"c\":960}").ok);
    CHECK(!OFW::parse("{\"v\":x,\"c\":960,\"s\":1}").ok);

    // 960 px centred site in a 1280 px view at 100 %: 1280/960 = 1.333 -> 125 %
    OFW::Fit f = OFW::choose(M(1280, 960, 1280), 100);
    CHECK(f.kind == OFW::Kind::Fits && f.percent == 125);
    CHECK(OFW::notice(f) == "Zoom 125% (fits the screen)");
    // measured at 125 % (view now 1024 CSS px): still 125 (idempotent)
    f = OFW::choose(M(1024, 960, 1024), 125);
    CHECK(f.kind == OFW::Kind::Fits && f.percent == 125);
    // exact fit within the 0.5 % slack: 1280 / 853.4 = 1.49994 -> 150
    f = OFW::choose(M(1280, 853.4, 1280), 100);
    CHECK(f.percent == 150);
    // just over the slack: 1280 / 860 * 100 = 148.8 -> 125
    f = OFW::choose(M(1280, 860, 1280), 100);
    CHECK(f.percent == 125);
    // very narrow page: capped at 200 %, "largest"
    f = OFW::choose(M(1920, 600, 1920), 100);
    CHECK(f.kind == OFW::Kind::Largest && f.percent == 200);
    CHECK(OFW::notice(f) == "Zoom 200% (the largest; the page is still narrower than the screen)");
    // 200 % fits exactly: Fits, not Largest
    f = OFW::choose(M(1920, 960, 1920), 100);
    CHECK(f.kind == OFW::Kind::Fits && f.percent == 200);
    // page that scrolls sideways at 100 %: 1600 content in 1280 -> 80 %
    f = OFW::choose(M(1280, 1200, 1600), 100);
    CHECK(f.kind == OFW::Kind::Fits && f.percent == 80);
    // far too wide: 50 %, still wide
    f = OFW::choose(M(1280, 0, 4000), 100);
    CHECK(f.kind == OFW::Kind::StillWide && f.percent == 50);
    CHECK(OFW::notice(f) == "Zoom 50% (the smallest; the page is still wider than the screen)");
    // fluid page: nothing to do
    f = OFW::choose(M(1280, 1280, 1280), 110);
    CHECK(f.kind == OFW::Kind::Fills && f.percent == 110);
    CHECK(OFW::notice(f) == "This page already fills the screen width (zoom 110%)");
    f = OFW::choose(M(1280, 0, 1280), 100);   // nothing measurable
    CHECK(f.kind == OFW::Kind::Fills);
    // a default zoom between steps (133 %): measured there; result is a step
    f = OFW::choose(M(962, 700, 962), 133);
    CHECK(f.kind == OFW::Kind::Fits && f.percent == 175);   // 133 * 962 / 700 = 182.8
    // bad inputs
    CHECK(OFW::choose(OFW::Measure(), 100).kind == OFW::Kind::Unknown);
    CHECK(OFW::choose(M(1280, 960, 1280), 0).kind == OFW::Kind::Unknown);
    CHECK(OFW::notice(OFW::Fit()) == "Couldn't measure this page");
    // every result is a site-zoom step within its limits
    for (double c = 100; c < 5000; c += 37) {
        const OFW::Fit g = OFW::choose(M(1280, c, c > 1280 ? c : 1280), 100);
        if (g.kind == OFW::Kind::Fills) continue;
        bool step = false;
        for (int s : OmniSiteZoom::kSteps) step |= s == g.percent;
        CHECK(step && g.percent >= OmniSiteZoom::kMin && g.percent <= OmniSiteZoom::kMax);
    }
    // the script is one whole expression (nothing to cut or append)
    const std::string js = OFW::script();
    CHECK(js.compare(0, 11, "(function()") == 0 && js.compare(js.size() - 4, 4, "})()") == 0);
    std::printf(fails ? "%d FAILED\n" : "all fit-width tests passed\n", fails);
    return fails ? 1 : 0;
}
