// OMNI_TEXT_CACHE_CAP_V1 tests: g++ -std=c++20 -Wall -Wextra -I<dir of OmniTextCacheCap.h> test_text_cache_cap.cpp -o t && ./t
#include "OmniTextCacheCap.h"
#include <cstdio>
#include <set>
#include <string>

static int failures = 0;
#define CHECK(c) do { if (!(c)) { ++failures; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

struct Fake { int id; };
static std::set<int> live;   // ids of values not yet dropped
static int dropped = 0;
static auto drop = [](Fake* f) { if (f) { CHECK(live.erase(f->id) == 1); ++dropped; delete f; } };
static Fake* make(int id) { live.insert(id); return new Fake { id }; }

int main()
{
    using namespace OmniTextCacheCap;
    // budget
    CHECK(budgetFor(3840, 2160) == 48 * kMiB);
    CHECK(budgetFor(1920, 1080) == 16 * kMiB);   // 12 MiB -> min
    CHECK(budgetFor(1280, 720) == 16 * kMiB);
    CHECK(budgetFor(0, 0) == 16 * kMiB);
    CHECK(budgetFor(-5, 100) == 16 * kMiB);
    CHECK(budgetFor(7680, 4320) == 192 * kMiB);
    CHECK(budgetFor(3840, 1080) == 24 * kMiB);
    CHECK(surfaceBytes(100, 10) == 4000);
    CHECK(surfaceBytes(100, 10, 416) == 4160);
    CHECK(surfaceBytes(0, 10) == 0);

    // many small entries: the entry cap (256) binds, LRU order kept
    {
        Lru<Fake*> c(48 * kMiB);
        for (int i = 0; i < 1000; ++i) {
            const std::string k = "k" + std::to_string(i);
            CHECK(!c.find(k));
            c.put(k, make(i), 1000, drop);
            if (i == 10) { CHECK(c.find("k0")); }   // touch k0: survives past k1..k10
        }
        CHECK(c.size() == kMaxEntries);
        CHECK(c.bytes() == kMaxEntries * 1000);
        CHECK(live.size() == kMaxEntries);
        CHECK(c.stats().evictions == 1000 - kMaxEntries);
        CHECK(c.find("k999") && (*c.find("k999"))->id == 999);
        CHECK(!c.find("k0"));   // touched at 10, still old by now
        c.clear(drop);
        CHECK(live.empty() && c.bytes() == 0 && c.size() == 0);
    }
    // touched entry outlives untouched older ones
    {
        Lru<Fake*> c(10 * 1000, 100);
        for (int i = 0; i < 10; ++i) c.put("a" + std::to_string(i), make(i), 1000, drop);
        CHECK(c.bytes() == 10000 && c.size() == 10);
        CHECK(c.find("a0"));
        c.put("b", make(100), 1000, drop);   // evicts a1 (a0 was touched)
        CHECK(c.contains("a0") && !c.contains("a1") && c.contains("b"));
        CHECK(c.oldestKey() == "a2");
        CHECK(c.bytes() <= c.budget());
        c.clear(drop);
    }
    // byte cap binds before the entry cap
    {
        Lru<Fake*> c(16 * kMiB);
        const size_t big = 800 * 1024;   // a wide 4K label
        for (int i = 0; i < 200; ++i) {
            c.put("w" + std::to_string(i), make(i), big, drop);
            CHECK(c.bytes() <= 16 * kMiB);
        }
        CHECK(c.size() == 16 * kMiB / big);
        CHECK(c.stats().peakBytes <= 16 * kMiB);
        CHECK(live.size() == c.size());
        c.clear(drop);
    }
    // one huge entry larger than the budget: kept alone (the caller blits it now), dropped on the next insert
    {
        Lru<Fake*> c(1000 * 10);
        for (int i = 0; i < 5; ++i) c.put("s" + std::to_string(i), make(i), 1000, drop);
        c.put("huge", make(50), 50000, drop);
        CHECK(c.size() == 1 && c.contains("huge") && c.bytes() == 50000);
        CHECK(live.size() == 1 && live.count(50));
        Fake** h = c.find("huge");
        CHECK(h && (*h)->id == 50);
        c.put("next", make(51), 1000, drop);
        CHECK(c.size() == 1 && c.contains("next") && !c.contains("huge"));
        CHECK(live.size() == 1 && live.count(51));
        c.put("huge2", make(52), 50000, drop);
        c.put("huge3", make(53), 50000, drop);
        CHECK(c.size() == 1 && c.contains("huge3") && live.size() == 1);
        c.clear(drop);
    }
    // budget changes: lower evicts at once (oldest first), higher keeps everything
    {
        Lru<Fake*> c(100000);
        for (int i = 0; i < 50; ++i) c.put("t" + std::to_string(i), make(i), 1000, drop);
        CHECK(c.size() == 50);
        c.setBudget(20000, drop);
        CHECK(c.size() == 20 && c.bytes() == 20000 && c.contains("t49") && c.contains("t30") && !c.contains("t29"));
        c.setBudget(1000000, drop);
        CHECK(c.size() == 20);
        for (int i = 50; i < 100; ++i) c.put("t" + std::to_string(i), make(i), 1000, drop);
        CHECK(c.size() == 70);
        c.setBudget(0, drop);   // everything goes
        CHECK(c.size() == 0 && c.bytes() == 0 && live.empty());
        c.setBudget(5000, drop);
        c.put("x", make(1), 1000, drop);
        CHECK(c.size() == 1);
        c.clear(drop);
    }
    // replacing a key drops the old value and re-accounts bytes
    {
        Lru<Fake*> c(100000);
        c.put("r", make(1), 1000, drop);
        c.put("r", make(2), 3000, drop);
        CHECK(c.size() == 1 && c.bytes() == 3000 && live.size() == 1 && live.count(2));
        c.clear(drop);
    }
    // hits / misses / null values
    {
        Lru<Fake*> c;
        CHECK(!c.find("nope"));
        c.put("n", nullptr, 0, drop);
        CHECK(c.find("n") && *c.find("n") == nullptr);
        const Stats& s = c.stats();
        CHECK(s.misses == 1 && s.hits == 2 && s.entries == 1 && s.budget == kBudgetMin);
        c.clear(drop);
    }
    CHECK(live.empty());
    std::printf("%s (%d failures, %d dropped)\n", failures ? "FAILED" : "ok", failures, dropped);
    return failures ? 1 : 0;
}
