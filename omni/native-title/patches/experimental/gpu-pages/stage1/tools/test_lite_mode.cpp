// OMNI_LITE_MODE_V1 host tests: g++ -std=c++20 -Wall -Wextra -Werror -I. test_lite_mode.cpp -o t && ./t
#include "OmniLiteMode.h"
#include <cstdio>

namespace OL = OmniLiteMode;
static int fails = 0;
#define CHECK(c) do { if (!(c)) { ++fails; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static OL::Cand tab(bool loaded, uint32_t shownAt)
{
    OL::Cand c; c.loaded = loaded; c.free = loaded; c.shownAt = shownAt; return c;
}

int main()
{
    // settings
    CHECK(!OL::parse("").on);
    CHECK(OL::parse("on\t1\n").on);
    CHECK(OL::parse("on\t1\r\n").on);
    CHECK(!OL::parse("on\t0\n").on);
    CHECK(!OL::parse("on\tyes\n").on);
    CHECK(OL::parse(OL::serialize(OL::Settings{ true })).on);
    CHECK(OL::serialize(OL::Settings{}) == "on\t0\n");

    // 3 or fewer loaded: nothing
    {
        std::vector<OL::Cand> t = { tab(true, 10), tab(true, 20), tab(true, 30), tab(false, 0) };
        t[2].current = true;
        CHECK(OL::pick(t, 100).empty());
    }
    // 5 loaded: the 2 least recently shown go, the never-shown one first
    {
        std::vector<OL::Cand> t = { tab(true, 50), tab(true, 0), tab(true, 10), tab(true, 90), tab(true, 70) };
        t[3].current = true;
        const std::vector<int> p = OL::pick(t, 100);
        CHECK(p.size() == 2 && p[0] == 1 && p[1] == 2);
    }
    // never the current, pinned, audible, kept/private or not-free tabs; fewer when not enough may go
    {
        std::vector<OL::Cand> t = { tab(true, 1), tab(true, 2), tab(true, 3), tab(true, 4), tab(true, 5), tab(true, 6) };
        t[0].current = true; t[1].pinned = true; t[2].audible = true; t[3].keep = true; t[4].free = false;
        const std::vector<int> p = OL::pick(t, 100);
        CHECK(p.size() == 1 && p[0] == 5);
    }
    // at most kMaxPerCheck per check; the rest at the next check
    {
        std::vector<OL::Cand> t;
        for (uint32_t i = 0; i < 8; ++i) t.push_back(tab(true, 100 + i));
        t[7].current = true;
        std::vector<int> p = OL::pick(t, 1000);
        CHECK(p.size() == 2 && p[0] == 0 && p[1] == 1);
        for (int i : p) t[size_t(i)].loaded = false;
        p = OL::pick(t, 1001);
        CHECK(p.size() == 2 && p[0] == 2 && p[1] == 3);
        for (int i : p) t[size_t(i)].loaded = false;
        p = OL::pick(t, 1002);
        CHECK(p.size() == 1 && p[0] == 4);
        for (int i : p) t[size_t(i)].loaded = false;
        CHECK(OL::pick(t, 1003).empty());
    }
    // wrap-safe last-shown order (SDL ticks wrapped: 0xFFFFFF00 is older than 0x10)
    {
        std::vector<OL::Cand> t = { tab(true, 0x10), tab(true, 0xFFFFFF00u), tab(true, 0x20), tab(true, 0x30), tab(true, 0x40) };
        t[4].current = true;
        const std::vector<int> p = OL::pick(t, 0x50);
        CHECK(p.size() == 2 && p[0] == 1 && p[1] == 0);
    }
    // unloaded tabs are not counted and never picked
    {
        std::vector<OL::Cand> t = { tab(false, 0), tab(false, 1), tab(true, 2), tab(true, 3), tab(true, 4), tab(true, 5) };
        t[5].current = true;
        const std::vector<int> p = OL::pick(t, 10);
        CHECK(p.size() == 1 && p[0] == 2);
    }
    CHECK(OL::checkDue(5, 0));
    CHECK(!OL::checkDue(500, 1));
    CHECK(OL::checkDue(1001, 1));
    CHECK(OL::checkDue(5, 0xFFFFFC00u));   // wrap

    // text cache budget: Off is the normal budget; On is half, at least 8 MiB, never above normal
    const size_t MiB = size_t(1) << 20;
    CHECK(OL::textBudget(48 * MiB, false) == 48 * MiB);
    CHECK(OL::textBudget(48 * MiB, true) == 24 * MiB);
    CHECK(OL::textBudget(16 * MiB, true) == 8 * MiB);
    CHECK(OL::textBudget(4 * MiB, true) == 4 * MiB);
    CHECK(OL::textBudget(OL::textBudget(48 * MiB, true), false) == 24 * MiB);   // Off restores whatever it is given

    // restore logic of the spare-engine flags: On sets a live flag aside, Off puts back exactly what was set aside
    CHECK(OL::flagStep(true, true, false) == OL::kStash);
    CHECK(OL::flagStep(true, false, false) == OL::kKeep);    // no flag: nothing to do, nothing to restore later
    CHECK(OL::flagStep(true, false, true) == OL::kKeep);     // already set aside (restart while On)
    CHECK(OL::flagStep(true, true, true) == OL::kStash);     // made again while On: set aside again
    CHECK(OL::flagStep(false, false, true) == OL::kRestore);
    CHECK(OL::flagStep(false, false, false) == OL::kKeep);
    CHECK(OL::flagStep(false, true, false) == OL::kKeep);
    CHECK(OL::flagStep(false, true, true) == OL::kDropStash); // the user's live flag wins
    // round trip on a simulated file system: Off -> On -> Off gives back the starting state, for every start
    for (int start = 0; start < 2; ++start) {
        bool live = start == 1, stash = false;
        auto run = [&](bool on) {
            switch (OL::flagStep(on, live, stash)) {
            case OL::kStash: stash = true; live = false; break;
            case OL::kRestore: live = true; stash = false; break;
            case OL::kDropStash: stash = false; break;
            case OL::kKeep: break;
            }
        };
        run(true);
        CHECK(!live);
        run(true);   // applying On twice changes nothing more
        CHECK(!live && stash == (start == 1));
        run(false);
        CHECK(live == (start == 1) && !stash);
        run(false);
        CHECK(live == (start == 1) && !stash);
    }
    CHECK(OL::kSpareFlagCount == 2 && std::string(OL::spareFlags()[0]) == "spare-reserve.flag");

    // texts
    CHECK(std::string(OL::value(true)) == "On" && std::string(OL::value(false)) == "Off");
    CHECK(std::string(OL::notice(true)) != OL::notice(false));
    CHECK(std::string(OL::label()) == "Lite mode");

    if (fails) { std::printf("%d failed\n", fails); return 1; }
    std::printf("test_lite_mode: all passed\n");
    return 0;
}
