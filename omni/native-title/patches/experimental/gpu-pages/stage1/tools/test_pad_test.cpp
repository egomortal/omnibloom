// OMNI_PAD_TEST_V1: host tests of engine/entry/OmniPadTest.h (written by apply_pad_test.py).
// g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_pad_test.cpp -o t && ./t
#include "OmniPadTest.h"
#include <cstdio>
#include <cstdlib>

namespace P = OmniPadTest;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

int main()
{
    // page address
    CHECK(P::isPage("omni://pages/controller/index.html"));
    CHECK(P::isPage("omni://pages/controller/index.html#x"));
    CHECK(!P::isPage("omni://pages/controllers/index.html"));
    CHECK(!P::isPage("https://example.com/omni://pages/controller/"));
    CHECK(!P::isPage("omni://pages/"));

    // JSON: numbers only, clamped
    P::Snap s;
    s.pad = true; s.buttons = (1u << 0) | (1u << 20);
    s.axes[0] = -32768; s.axes[1] = 32767; s.axes[4] = 99999; s.axes[5] = -5;
    s.touch[0] = true; s.tx[0] = 250; s.ty[0] = 2000;
    s.battery = 9; s.dz = 7;
    for (int i = 0; i < P::kSizes; ++i) { s.dzl[i] = 1400 + i; s.dzr[i] = 0; }
    s.holdMs = 400;
    const std::string j = P::json(s);
    CHECK(j == "{\"v\":1,\"pad\":1,\"b\":1048577,\"ax\":[-32768,32767,0,0,32767,-5],\"tp\":[[1,250,1000],[0,0,0]],\"bat\":4,\"dz\":3,"
               "\"dzl\":[1400,1401,1402,1403],\"dzr\":[1,1,1,1],\"hold\":400}");
    CHECK(j.find_first_not_of("{}[]\":,-0123456789abdhloprtvxz") == std::string::npos);
    const std::string sc = P::script(s);
    CHECK(sc.find("window.omniPadTest") != std::string::npos && sc.find(j) != std::string::npos);
    CHECK(P::json(P::Snap()).find("\"pad\":0") != std::string::npos);

    // equality drives "changed"
    P::Snap a, b;
    CHECK(a == b);
    b.axes[3] = 1; CHECK(a != b); b = a;
    b.tx[1] = 3; CHECK(a != b); b = a;
    b.dzr[2] = 3; CHECK(a != b); b = a;
    b.holdMs = 100; CHECK(a != b);

    // pusher: first push at once; <= 30 a second under constant change; heartbeat; a lost answer
    P::Pusher p;
    CHECK(p.due(0, false));
    int pushes = 0;
    for (uint32_t t = 1000; t < 2000; ++t) {   // every millisecond a change, every answer immediate
        if (p.due(t, true)) { p.sent(t); p.answered(); ++pushes; }
    }
    CHECK(pushes <= 30 && pushes >= 29);
    p.reset(); p.sent(0); p.answered();
    CHECK(!p.due(500, false)); CHECK(p.due(1000, false));            // heartbeat
    CHECK(!p.due(20, true)); CHECK(p.due(34, true));                  // min interval
    p.reset(); p.sent(0);                                             // no answer yet
    CHECK(!p.due(100, true)); CHECK(!p.due(499, true)); CHECK(p.due(500, true));
    p.answered(); CHECK(p.due(40, true));
    CHECK(uint32_t(1000 / P::kPushMinMs) <= 30);

    // leave hold: 1 s of Circle on one pad; release swallowed after; other pads ignored
    P::LeaveHold h;
    h.edge(0, true, 100);
    CHECK(!h.due(1099)); CHECK(h.due(1100));
    CHECK(h.heldMs(100) == 0); CHECK(h.heldMs(450) == 300); CHECK(h.heldMs(5000) == 1000);
    h.edge(1, true, 500); h.edge(1, false, 600);                     // another pad: no effect
    CHECK(h.due(1100));
    h.fired();
    CHECK(h.draining() && !h.due(2000) && h.heldMs(2000) == 0);
    CHECK(!h.swallowAfter(1, P::kCircle, false));                    // another pad's Circle passes
    CHECK(!h.swallowAfter(0, P::kCross, false));                     // other buttons pass
    CHECK(h.swallowAfter(0, P::kCircle, false));                     // the hold's release: swallowed, done
    CHECK(!h.draining() && !h.swallowAfter(0, P::kCircle, false));
    h.edge(0, true, 0); h.edge(0, false, 500);                       // a short press: nothing
    CHECK(!h.due(5000));
    h.edge(2, true, 0); h.fired(); h.edge(2, false, 10);             // released while still on the page: drain ends
    CHECK(!h.draining());

    // gate: everything is the page's but Options
    CHECK(P::swallow(P::kButtonEvent, P::kCross));
    CHECK(P::swallow(P::kButtonEvent, P::kCircle));
    CHECK(P::swallow(P::kButtonEvent, P::kTouchpad));
    CHECK(!P::swallow(P::kButtonEvent, P::kOptions));
    CHECK(P::swallow(P::kAxisEvent, -1) && P::swallow(P::kTouchEvent, -1));
    CHECK(!P::swallow(P::kOtherEvent, -1));

    CHECK(std::string(P::leftNotice(true)).find("Circle") != std::string::npos);
    CHECK(std::string(P::leftNotice(false)).find("(held B)") != std::string::npos);

    std::printf("test_pad_test: %d checks, %d failed\n", checks, fails);
    return fails ? EXIT_FAILURE : EXIT_SUCCESS;
}
