// OMNI_IMAGE_VIEWER_V1: tests for the pure part (engine/entry/OmniImageViewer.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_image_viewer.cpp -o t && ./t [--emit DIR]
// --emit DIR writes the assembled page scripts (open / input / go / toggle / alive / close / probe) for
//   node --check and tools/test_image_viewer_js.cjs (which also runs them on a mock DOM).
#include "OmniImageViewer.h"
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>

namespace OIMV = OmniImageViewer;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
static bool near(double a, double b, double eps = 1e-3) { return std::fabs(a - b) <= eps; }
static size_t count(const std::string& s, const std::string& what)
{
    size_t n = 0;
    for (size_t p = s.find(what); p != std::string::npos; p = s.find(what, p + 1)) ++n;
    return n;
}

int main(int argc, char** argv)
{
    // addresses
    CHECK(OIMV::viewable("https://example.com/a.jpg"));
    CHECK(OIMV::viewable("HTTP://example.com/a.png"));
    CHECK(OIMV::viewable("file:///data/omni/x.png"));
    CHECK(OIMV::viewable("blob:https://example.com/1234"));
    CHECK(OIMV::viewable("data:image/png;base64,AAAA"));
    CHECK(!OIMV::viewable("data:text/html,<b>x</b>"));
    CHECK(!OIMV::viewable("javascript:alert(1)"));
    CHECK(!OIMV::viewable("about:blank"));
    CHECK(!OIMV::viewable(""));
    CHECK(!OIMV::viewable("data:image/png;base64," + std::string(OIMV::kMaxUrl, 'A')));
    CHECK(OIMV::probeWorthy("https://example.com/"));
    CHECK(!OIMV::probeWorthy("omni://pages/start"));
    CHECK(!OIMV::probeWorthy("about:blank"));
    CHECK(!OIMV::probeWorthy(""));

    // where it may open
    OIMV::Where w;
    CHECK(OIMV::canOpen(w));
    { auto x = w; x.testMode = true; CHECK(!OIMV::canOpen(x)); }
    { auto x = w; x.pagesTab = true; CHECK(!OIMV::canOpen(x)); }
    { auto x = w; x.downloadsTab = true; CHECK(!OIMV::canOpen(x)); }
    { auto x = w; x.crashed = true; CHECK(!OIMV::canOpen(x)); }
    { auto x = w; x.busy = true; CHECK(!OIMV::canOpen(x)); }

    // triggers: dead zone, full press = 4x per second, both pressed cancel
    CHECK(OIMV::triggerAmount(0) == 0.f);
    CHECK(OIMV::triggerAmount(OIMV::kTriggerDead) == 0.f);
    CHECK(OIMV::triggerAmount(32767) == 1.f);
    CHECK(OIMV::triggerAmount(40000) == 1.f);
    CHECK(near(OIMV::triggerZoom(0, 32767, 1.f), std::log(4.0)));
    CHECK(near(OIMV::triggerZoom(32767, 0, 0.5f), -std::log(4.0) / 2));
    CHECK(OIMV::triggerZoom(32767, 32767, 1.f) == 0.f);
    CHECK(OIMV::triggerZoom(2000, 0, 1.f) == 0.f);
    CHECK(OIMV::triggerZoom(0, 17883, 1.f) > 0.f && OIMV::triggerZoom(0, 17883, 1.f) < std::log(4.0));

    // left stick: radial dead zone, full deflection 1400 px/s, direction kept
    float dx = 1, dy = 1;
    OIMV::stickPan(3000, -3000, 0.2f, 1.f, dx, dy);
    CHECK(dx == 0 && dy == 0);
    OIMV::stickPan(32767, 0, 0.2f, 1.f, dx, dy);
    CHECK(near(dx, OIMV::kPanPerSecond, 1.0) && dy == 0);
    OIMV::stickPan(0, -32768, 0.2f, 0.5f, dx, dy);
    CHECK(dx == 0 && near(dy, -OIMV::kPanPerSecond / 2, 1.0));
    OIMV::stickPan(23170, 23170, 0.2f, 1.f, dx, dy);
    CHECK(near(dx, dy) && dx > 0 && near(std::hypot(dx, dy), OIMV::kPanPerSecond, 2.0));
    OIMV::stickPan(16384, 0, 0.2f, 1.f, dx, dy);
    CHECK(dx > 0 && dx < OIMV::kPanPerSecond * 0.25f);   // gentle near the middle (curve 1.8)
    OIMV::stickPan(32767, 0, 1.f, 1.f, dx, dy);
    CHECK(dx == 0 && dy == 0);

    // pending input: one script in flight, the rest adds up; an unanswered one stops holding back after kAnswerMs
    OIMV::Pending p;
    double z = 9, x = 9, y = 9;
    CHECK(!p.take(100, z, x, y));
    p.add(0.00001, 0.01, 0.01);
    CHECK(!p.any() && !p.take(100, z, x, y));
    p.clear();
    p.add(0.1, 5, -3);
    CHECK(p.take(100, z, x, y) && near(z, 0.1) && near(x, 5) && near(y, -3) && p.inflight);
    p.add(0.2, 1, 1);
    CHECK(!p.take(200, z, x, y));
    p.add(0.2, 1, 1);
    p.answered();
    CHECK(p.take(210, z, x, y) && near(z, 0.4) && near(x, 2) && near(y, 2));
    p.add(0, 7, 0);
    CHECK(!p.take(210 + OIMV::kAnswerMs - 1, z, x, y));
    CHECK(p.take(210 + OIMV::kAnswerMs, z, x, y) && near(x, 7));
    p.answered();
    p.add(50, 0, 0);
    CHECK(p.take(5000, z, x, y) && z == OIMV::kMaxStepZoom);
    p.answered();
    p.add(-50, 0, 0);
    CHECK(p.take(5001, z, x, y) && z == -OIMV::kMaxStepZoom);
    p.add(1, 1, 1);
    p.clear();
    CHECK(!p.inflight && !p.any());
    // wrapping clock
    OIMV::Pending q;
    q.add(1, 0, 0);
    CHECK(q.take(0xFFFFFF00u, z, x, y));
    q.add(1, 0, 0);
    CHECK(!q.take(0x00000100u, z, x, y));
    CHECK(q.take(0xFFFFFF00u + OIMV::kAnswerMs, z, x, y));

    // dismissed image pages
    OIMV::Dismissed d;
    int tabA = 0, tabB = 0;
    CHECK(!d.is(&tabA, "https://a/x.jpg"));
    d.note(&tabA, "https://a/x.jpg");
    CHECK(d.is(&tabA, "https://a/x.jpg"));
    CHECK(!d.is(&tabB, "https://a/x.jpg"));
    CHECK(!d.is(&tabA, "https://a/y.jpg"));
    d.clear();
    CHECK(!d.is(&tabA, "https://a/x.jpg") && !d.is(nullptr, ""));

    // caption and texts
    CHECK(OIMV::caption(2, 12, "https://example.com/pics/photo.jpg?w=200") == "3 / 12   photo.jpg");
    CHECK(OIMV::caption(0, 1, "https://example.com/pics/photo%20one.jpg") == "photo one.jpg");
    CHECK(OIMV::caption(0, 1, "https://example.com/") == "example.com");
    CHECK(OIMV::caption(0, 2, "data:image/png;base64,AAAA") == "1 / 2   Embedded image");
    CHECK(OIMV::caption(0, 1, "blob:https://example.com/123") == "Image");
    {
        const std::string c = OIMV::caption(0, 1, "https://e.com/" + std::string(100, 'a') + ".jpg");
        CHECK(c.size() == 28 + 3 + 28 && c.find("...") == 28);
    }
    CHECK(std::string(OIMV::zoomNote(true)).find("R2 / L2") == 0);
    CHECK(std::string(OIMV::zoomNote(false)).find("RT / LT") == 0);
    CHECK(std::string(OIMV::endNotice(0)).find("first") != std::string::npos);
    CHECK(std::string(OIMV::endNotice(5)).find("last") != std::string::npos);

    // JavaScript string literals
    CHECK(OIMV::jsQuote("abc") == "'abc'");
    CHECK(OIMV::jsQuote("a'b\"c\\d") == "'a\\'b\\\"c\\\\d'");
    CHECK(OIMV::jsQuote("x\ny\rz") == "'x\\ny\\rz'");
    CHECK(OIMV::jsQuote("</script>") == "'\\x3c/script\\x3e'");
    CHECK(OIMV::jsQuote(std::string("a\x01" "b")) == "'a\\x01b'");
    CHECK(OIMV::jsQuote("a\xE2\x80\xA8" "b\xE2\x80\xA9") == "'a\\u2028b\\u2029'");
    CHECK(OIMV::jsQuote("caf\xC3\xA9 \xE2\x82\xAC") == "'caf\xC3\xA9 \xE2\x82\xAC'");   // other UTF-8 as is

    // scripts
    const std::string open = OIMV::openScript("https://example.com/a'b.jpg", true);
    CHECK(open.rfind("(function(){(function(){var W=window;", 0) == 0);
    CHECK(count(open, OIMV::kLibrary) == 1);
    CHECK(open.find("v.open('https://example.com/a\\'b.jpg',1)") != std::string::npos);
    CHECK(open.size() >= 4 && open.compare(open.size() - 4, 4, "})()") == 0);
    CHECK(OIMV::openScript("https://e.com/x.png", false).find(",0)") != std::string::npos);
    CHECK(std::string(OIMV::kLibrary).find(")JS") == std::string::npos);
    // whole IIFEs (the newline keeps their last ')' out of the ")JS" delimiter), nothing trimmed
    CHECK(std::string(OIMV::kLibrary).compare(std::strlen(OIMV::kLibrary) - 5, 5, "})()\n") == 0);
    CHECK(std::string(OIMV::kProbe).compare(std::strlen(OIMV::kProbe) - 5, 5, "})()\n") == 0);
    CHECK(OIMV::inputScript(0.25, -12.5, 3) == "(function(){var v=window.__omniImv;return v&&v.v===1?v.input(0.25000,-12.50,3.00):'0';})()");
    CHECK(OIMV::goScript(-5).find("v.go(-1)") != std::string::npos);
    CHECK(OIMV::goScript(1).find("v.go(1)") != std::string::npos);
    CHECK(OIMV::toggleScript().find("v.toggle()") != std::string::npos);
    CHECK(OIMV::aliveScript().find("v.alive()") != std::string::npos);
    CHECK(OIMV::closeScript().find("v.close()") != std::string::npos);
    CHECK(OIMV::probeScript() == OIMV::kProbe);
    CHECK(OIMV::kContextId == 9760);

    if (argc == 3 && std::strcmp(argv[1], "--emit") == 0) {
        const std::string dir = argv[2];
        const std::string tricky = "https://example.com/p/a'b\"c\\d</script>\xE2\x80\xA8%20e.jpg";
        const std::pair<const char*, std::string> files[] = {
            { "open.js", OIMV::openScript(tricky, true) },
            { "open1.js", OIMV::openScript("https://example.com/one.png", false) },
            { "input.js", OIMV::inputScript(0.693147, 25, -10) },
            { "go.js", OIMV::goScript(1) },
            { "toggle.js", OIMV::toggleScript() },
            { "alive.js", OIMV::aliveScript() },
            { "close.js", OIMV::closeScript() },
            { "probe.js", OIMV::probeScript() },
            { "tricky.txt", tricky },
        };
        for (const auto& [name, text] : files) {
            std::ofstream(dir + "/" + name, std::ios::binary) << text;
        }
        printf("emitted %zu files to %s\n", sizeof(files) / sizeof(files[0]), dir.c_str());
    }
    printf("%s: %d checks, %d failures\n", failures ? "FAIL" : "PASS", checks, failures);
    return failures ? 1 : 0;
}
