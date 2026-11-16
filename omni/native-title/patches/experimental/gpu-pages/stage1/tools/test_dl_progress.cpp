// OMNI_DL_PROGRESS_V1: tests for engine/entry/OmniDlProgress.h (reply parsing, poll schedule, texts, top-bar layout).
// g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_dl_progress.cpp -o t && ./t
#include "OmniDlProgress.h"
#include <cstdio>
#include <string>
#include <vector>

namespace D = OmniDlProgress;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static void parsing()
{
    D::Status s = D::parse("{\"api_version\": 1, \"active\": 2, \"percent\": 45}");
    CHECK(s.ok && s.active == 2 && s.percent == 45);
    s = D::parse("{\"percent\":-1,\"active\":3,\"api_version\":1}");   // any order, compact
    CHECK(s.ok && s.active == 3 && s.percent == -1);
    s = D::parse("{\"api_version\": 1, \"active\": 0, \"percent\": 70}");   // nothing active: no percent
    CHECK(s.ok && s.active == 0 && s.percent == -1);
    s = D::parse(" {\"api_version\":1,\"x\":\"a\\\"b\\u00e9\",\"y\":true,\"z\":null,\"w\":1.5e3,\"active\":1,\"percent\":100}\n");
    CHECK(s.ok && s.active == 1 && s.percent == 100);   // unknown plain fields skipped
    CHECK(!D::parse("").ok);
    CHECK(!D::parse("{}").ok);
    CHECK(!D::parse("{\"api_version\":1,\"active\":2}").ok);                          // percent missing
    CHECK(!D::parse("{\"api_version\":2,\"active\":2,\"percent\":4}").ok);            // other version
    CHECK(!D::parse("{\"api_version\":1,\"active\":-1,\"percent\":4}").ok);
    CHECK(!D::parse("{\"api_version\":1,\"active\":2,\"percent\":101}").ok);
    CHECK(!D::parse("{\"api_version\":1,\"active\":2,\"percent\":-2}").ok);
    CHECK(!D::parse("{\"api_version\":1,\"active\":2.5,\"percent\":4}").ok);          // not an integer
    CHECK(!D::parse("{\"api_version\":1,\"active\":\"2\",\"percent\":4}").ok);
    CHECK(!D::parse("{\"api_version\":1,\"active\":2,\"active\":3,\"percent\":4}").ok); // duplicate
    CHECK(!D::parse("{\"api_version\":1,\"active\":2,\"percent\":4,}").ok);
    CHECK(!D::parse("{\"api_version\":1,\"active\":2,\"percent\":4} x").ok);
    CHECK(!D::parse("{\"api_version\":1,\"active\":2,\"percent\":4,\"jobs\":[1]}").ok);  // nested: not this route
    CHECK(!D::parse("{\"api_version\":1,\"active\":99999999999,\"percent\":4}").ok);
    CHECK(!D::parse("{\"api_version\":1,\"active\":2,\"percent\":4").ok);

    D::Status out;
    CHECK(D::classify(true, 200, "{\"api_version\":1,\"active\":2,\"percent\":45}", out) == D::Reply::Ok && out.active == 2);
    CHECK(D::classify(true, 403, "{\"error\":\"Forbidden\"}", out) == D::Reply::Missing && !out.ok);   // older worker
    CHECK(D::classify(true, 404, "", out) == D::Reply::Missing);
    CHECK(D::classify(true, 500, "", out) == D::Reply::Failed);
    CHECK(D::classify(true, 200, "<html>", out) == D::Reply::Failed);
    CHECK(D::classify(false, 0, "", out) == D::Reply::Failed);
    CHECK(D::request(8765) == "GET /api/active HTTP/1.0\r\nHost: 127.0.0.1:8765\r\nConnection: close\r\nAccept: application/json\r\n\r\n");
}

// Runs a poller over [from, to) in 100 ms ticks; reply(now) answers each poll. Returns the poll times.
template <class F>
static std::vector<uint32_t> run(D::Poller& p, uint32_t from, uint32_t to, F reply)
{
    std::vector<uint32_t> at;
    for (uint32_t now = from; now != to; now += 100)
        if (p.want(now, false)) { p.started(now); at.push_back(now); D::Status s; const D::Reply r = reply(now, s); p.finished(r, s); }
    return at;
}
static D::Reply refused(uint32_t, D::Status&) { return D::Reply::NotRunning; }

static void schedule()
{
    {   // idle worker: one check 5 s after start, refused, then nothing at all
        D::Poller p;
        const auto at = run(p, 1000, 61000, refused);
        CHECK(at.size() == 1 && at[0] == 6000);
        CHECK(!p.visible());
    }
    {   // a worker busy from before Omni started: polled every 2 s while active, stops when it is done
        D::Poller p;
        int left = 4;
        const auto at = run(p, 0, 60000, [&](uint32_t, D::Status& s) {
            s = { true, left > 0 ? 2 : 0, left > 0 ? 50 : -1 }; --left; return D::Reply::Ok; });
        CHECK(at.size() == 5);
        for (size_t i = 1; i < at.size(); ++i) CHECK(at[i] - at[i - 1] == 2000);
        CHECK(!p.visible() && p.active() == 0);
    }
    {   // hand-over: polls for 10 s (every 2 s), nothing after when nothing runs
        D::Poller p;
        run(p, 0, 7000, refused);   // startup check done
        p.handedOver(20000);
        const auto at = run(p, 20000, 60000, [](uint32_t, D::Status& s) { s = { true, 0, -1 }; return D::Reply::Ok; });
        CHECK(at.size() == 5 && at.front() == 20000 && at.back() == 28000);
    }
    {   // hand-over, then a job appears: polling goes on past the window until it ends
        D::Poller p;
        run(p, 0, 7000, refused);
        p.handedOver(10000);
        const auto at = run(p, 10000, 80000, [](uint32_t now, D::Status& s) {
            const bool on = now >= 14000 && now < 40000;
            s = { true, on ? 1 : 0, on ? int((now - 14000) / 260) : -1 }; return D::Reply::Ok; });
        CHECK(!at.empty() && at.back() == 40000);   // the first poll that saw it done
        CHECK(!p.visible());
    }
    {   // the 2 s gap holds across a hand-over
        D::Poller p;
        run(p, 0, 5100, refused);   // polled at 5000
        p.handedOver(5500);
        CHECK(!p.want(6900, false));
        CHECK(p.want(7000, false));
        CHECK(!p.want(7000, true));   // one at a time
    }
    {   // hand-over before the startup check: asked at once
        D::Poller p;
        CHECK(!p.want(0, false));
        p.handedOver(1000);
        CHECK(p.want(1000, false));
    }
    {   // older worker (403 / 404): stops at once, asked again only after the next hand-over
        D::Poller p;
        p.want(0, false);
        p.handedOver(0);
        auto at = run(p, 0, 30000, [](uint32_t, D::Status&) { return D::Reply::Missing; });
        CHECK(at.size() == 1);
        p.handedOver(40000);
        at = run(p, 40000, 70000, [](uint32_t, D::Status&) { return D::Reply::Missing; });
        CHECK(at.size() == 1);
    }
    {   // failures: the indicator stays through two, goes after three in a row
        D::Poller p;
        run(p, 0, 5100, [](uint32_t, D::Status& s) { s = { true, 2, 10 }; return D::Reply::Ok; });
        CHECK(p.visible());
        int n = 0;
        const auto at = run(p, 5100, 60000, [&](uint32_t, D::Status&) { ++n; return D::Reply::Failed; });
        CHECK(n == 3 && at.size() == 3 && !p.visible());
    }
    {   // a failure between good answers resets the count
        D::Poller p;
        int i = 0;
        run(p, 0, 40000, [&](uint32_t, D::Status& s) {
            ++i; if (i % 3 == 0) return D::Reply::Failed; s = { true, 1, 5 }; return D::Reply::Ok; });
        CHECK(p.visible());
    }
    {   // worker stops (refused) while jobs ran: indicator off, polling stops
        D::Poller p;
        int i = 0;
        const auto at = run(p, 0, 60000, [&](uint32_t, D::Status& s) {
            if (++i < 3) { s = { true, 1, 30 }; return D::Reply::Ok; } return D::Reply::NotRunning; });
        CHECK(at.size() == 3 && !p.visible());
    }
    {   // finished(): true only when what is shown changes
        D::Poller p;
        CHECK(p.finished(D::Reply::Ok, { true, 2, 45 }));
        CHECK(!p.finished(D::Reply::Ok, { true, 2, 45 }));
        CHECK(p.finished(D::Reply::Ok, { true, 2, 46 }));
        CHECK(!p.finished(D::Reply::Failed, {}));
        CHECK(p.reset() && !p.visible());
        CHECK(!p.reset());
    }
    {   // reset (Media downloads off) forgets a hand-over and the startup check
        D::Poller p;
        p.want(0, false);
        p.handedOver(0);
        p.reset();
        CHECK(run(p, 0, 60000, refused).empty());
    }
    {   // SDL tick wrap
        D::Poller p;
        const uint32_t t0 = 0xFFFFF000u;
        p.want(t0, false);
        p.handedOver(t0);
        const auto at = run(p, t0, t0 + 30000, [](uint32_t, D::Status& s) { s = { true, 0, -1 }; return D::Reply::Ok; });
        CHECK(at.size() == 5);
    }
}

static void texts()
{
    CHECK(D::label(2, 45) == "2 \xe2\x86\x93 45%");
    CHECK(D::label(1, 0) == "1 \xe2\x86\x93 0%");
    CHECK(D::label(3, -1) == "3 \xe2\x86\x93");
    CHECK(D::label(150, 100) == "99+ \xe2\x86\x93 100%");
    CHECK(D::label(0, 50).empty());
    CHECK(D::quickLabel(2) == "Downloads (2 active)");
    CHECK(D::quickLabel(1) == "Downloads (1 active)");
    CHECK(D::quickValue(45) == "45%" && D::quickValue(-1).empty());
}

static void layout()
{
    // battery shown (base 1155), nothing else: starts at base
    CHECK(D::startX(1155, 0, 0, 0, 0, 0) == 1155.f);
    // the sleep timer 60 px wide: after it + 12
    CHECK(D::startX(1155, 60, 0, 0, 0, 0) == 1227.f);
    // the offline badge with its text (at offX, text at offX + 12, 45 px): after its text + 12
    CHECK(D::startX(1155, 0, 2, 1155, 45, 100) == 1155.f + 12 + 45 + 12);
    CHECK(D::startX(1155, 0, 2, 1155, 45, 30) == 1155.f + 12 + 30 + 12);   // text clipped to its room
    CHECK(D::startX(1155, 60, 1, 1227, 45, 0) == 1227.f + 7 + 12);         // dot only
    // room for ring + text
    D::BadgeLayout b = D::badgeLayout(1155, 50);
    CHECK(b.mode == 2 && b.x == 1155.f && b.w == 14 + 5 + 50 && b.textMax == int(1276 - 1155 - 19));
    b = D::badgeLayout(1240, 50);   // 36 px left: ring only
    CHECK(b.mode == 1 && b.w == 14);
    b = D::badgeLayout(1270, 50);   // no room
    CHECK(b.mode == 0);
    CHECK(!D::hit(b, 1272));
    b = D::badgeLayout(1155, 50);
    CHECK(D::hit(b, 1150) && D::hit(b, 1155 + 69 + 5) && !D::hit(b, 1149) && !D::hit(b, 1230));
    CHECK(D::kQuickRowId == 8480);
}

int main()
{
    parsing();
    schedule();
    texts();
    layout();
    std::printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
