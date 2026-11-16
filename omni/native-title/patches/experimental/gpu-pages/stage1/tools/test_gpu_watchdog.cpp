// Host test for OMNI_GPU_WATCHDOG_V1 (stage1/src/ogp-s1-watchdog.h): the timer, the trip decision and the flag files.
// wsl -d Ubuntu-24.04 -- bash -c 'cd "/path/to/workspace/outputs/omni-gpu-pages/stage1" &&
//   g++ -std=c++20 -O1 -Wall -Wextra -pthread -fsanitize=address,undefined tools/test_gpu_watchdog.cpp -o /tmp/test_gpu_watchdog && /tmp/test_gpu_watchdog'
#include "../src/ogp-s1-watchdog.h"
#include <string>
#include <thread>
#include <vector>

static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniGpuWatchdog;

static std::string slurp(const char* path) { char b[8192]; readSmall(path, b, sizeof b); return b; }
static bool exists(const char* path) { return !access(path, F_OK); }

static void testParse()
{
    CHECK(parseLimitMs(nullptr) == 1500);
    CHECK(parseLimitMs("") == 1500);
    CHECK(parseLimitMs("garbage") == 1500);
    CHECK(parseLimitMs("2000\n") == 2000);
    CHECK(parseLimitMs("  1800 ms") == 1800);
    CHECK(parseLimitMs("0") == 0);
    CHECK(parseLimitMs("off") == 0);
    CHECK(parseLimitMs("10") == kMinMs);
    CHECK(parseLimitMs("-5") == kMinMs);
    CHECK(parseLimitMs("999999") == kMaxMs);
    CHECK(parseLimitMs("99999999999999999999999") == 1500);   // overflow: the default
    CHECK(frameLimitMs(1500) == 3000 && frameLimitMs(2000) == 4000 && frameLimitMs(0) == 0);
    CHECK(pollMs(1500) == 250 && pollMs(250) == 62 && pollMs(100) == 50);
}

static void testWatch()
{
    Watch w;
    uint32_t what = 0; double pending = 0;
    CHECK(!w.check(1000, 1500, &what, &pending));                  // nothing pending
    int a = w.begin(kWait, kWhatReadback, 1000);
    CHECK(a >= 0);
    CHECK(!w.check(2499, 1500, &what, &pending));                  // 1499 ms: not yet
    CHECK(!w.check(2500, 1500, &what, &pending));                  // exactly the limit: not yet
    w.end(a);
    CHECK(!w.check(9000, 1500, &what, &pending));                  // ended in time: never trips
    // a frame gets the looser limit
    int f = w.begin(kFrame, kWhatFrame, 10000);
    CHECK(!w.check(12000, 1500, &what, &pending));                 // 2 s into a frame: fine (limit 3 s)
    CHECK(w.check(13001, 1500, &what, &pending));                  // 3.001 s: trips
    CHECK(what == kWhatFrame && pending > 3000 && pending < 3002);
    CHECK(!w.check(20000, 1500, &what, &pending));                 // trips once per process
    w.end(f);

    Watch w2;
    int s1 = w2.begin(kWait, kWhatAsyncFence, 100), s2 = w2.begin(kWait, kWhatTileDiff, 500);
    CHECK(s1 >= 0 && s2 >= 0 && s1 != s2);
    CHECK(w2.check(1700, 1500, &what, &pending) && what == kWhatAsyncFence);   // the older one is overdue first
    Watch w3;
    CHECK(!w3.check(1e9, 0, &what, &pending));                     // limit 0: off
    int x = w3.begin(kWait, kWhatOther, 1);
    CHECK(!w3.check(1e9, 0, &what, &pending));
    w3.end(x);
    // the table: kSlots at once, the next is unwatched (-1), end(-1) is harmless
    Watch w4;
    std::vector<int> slots;
    for (int i = 0; i < Watch::kSlots; ++i) slots.push_back(w4.begin(kWait, kWhatOther, 1));
    CHECK(w4.begin(kWait, kWhatOther, 1) == -1);
    w4.end(-1);
    w4.end(slots[3]);
    CHECK(w4.begin(kWait, kWhatOther, 1) == slots[3]);
}

static void testThreads()   // many compositor threads begin/end while a watchdog polls: no false trip, no lost slot
{
    Watch w;
    std::atomic<bool> stop { false };
    std::atomic<int> trips { 0 };
    std::thread dog([&] {
        uint32_t what; double pending;
        while (!stop.load()) { if (w.check(100.0, 1500, &what, &pending)) ++trips; }   // "now" 100 ms: never overdue
    });
    std::vector<std::thread> workers;
    for (int t = 0; t < 8; ++t)
        workers.emplace_back([&] { for (int i = 0; i < 20000; ++i) { int s = w.begin(kWait, kWhatReadback, 50.0); w.end(s); } });
    for (auto& t : workers) t.join();
    stop = true; dog.join();
    CHECK(trips.load() == 0);
    int free = 0;
    for (int i = 0; i < Watch::kSlots; ++i) free += !w.busy[i].load();
    CHECK(free == Watch::kSlots);
}

static void testDecision()
{
    const long today = 20261116, yesterday = 20261115;
    CHECK(tripsOn("", today) == 0);
    CHECK(tripsOn("20261116 1 engine 5\n20261115 2 engine 6\n20261116 3 title 7", today) == 2);
    Decision d = decide("", today, false);
    CHECK(!d.persist && !d.sameSession);
    d = decide("20261115 1 engine 5\n", today, false);             // yesterday's stall does not count
    CHECK(!d.persist);
    d = decide("20261116 1 engine 5\n", today, false);             // a second stall today, new session: persist
    CHECK(d.persist && d.earlierToday == 1);
    d = decide("20261116 1 engine 5\n", today, true);              // same session (already off): not counted again
    CHECK(!d.persist && d.sameSession);
    char kept[256];
    keepToday("20261115 1 a 1\n20261116 2 b 2\n20261114 3 c 3\n20261116 4 d 4", today, kept, sizeof kept);
    CHECK(std::string(kept) == "20261116 2 b 2\n20261116 4 d 4\n");
    keepToday("20261115 1 a 1\n", today, kept, sizeof kept);
    CHECK(std::string(kept).empty());
    (void)yesterday;
    char line[512];
    formatLine(line, sizeof line, Decision {}, "engine", 42, kWhatReadback, 1612, 1500, "exiting");
    CHECK(strstr(line, "OMNI GPU WATCHDOG: engine pid=42") && strstr(line, "pending 1612 ms (limit 1500 ms)") && strstr(line, "for this session"));
    CHECK(dayOf(0) == 19700101);
    CHECK(dayOf(86399) == 19700101 && dayOf(86400) == 19700102);
    CHECK(dayOf(951782400) == 20000229);                           // a leap day
    CHECK(dayOf(1794787200) == 20261116);                          // 2026-11-16 00:00:00 UTC
    CHECK(dayOf(1794787200 - 1) == 20261115);
}

static void testFiles()
{
    char base[] = "/tmp/ogp-wd-XXXXXX";
    CHECK(mkdtemp(base));
    Files f(base);
    const long day1 = 20261116, day2 = 20261117;
    char line[512];
    // limit file
    CHECK(readLimitMs(base) == 1500);
    CHECK(writeDurable(f.limit, "2000\n") && readLimitMs(base) == 2000);
    CHECK(writeDurable(f.limit, "off") && readLimitMs(base) == 0);
    // session 1, first stall of the day: session flag only
    sessionStart(base);
    Decision d = recordTrip(base, day1, 1000, "engine", 11, kWhatReadback, 1600, 1500, "exiting", line, sizeof line);
    CHECK(!d.persist && !d.sameSession);
    CHECK(exists(f.session) && sessionOff(base) && !exists(f.killSwitch));
    CHECK(slurp(f.history) == "20261116 1000 engine 11\n");
    char notice[300];
    CHECK(takeNotice(base, notice, sizeof notice) && strstr(notice, "for this session") && !exists(f.notice));
    CHECK(!takeNotice(base, notice, sizeof notice));               // taken once
    // a second page process trips on the same stall in the same session: no new line, no escalation
    d = recordTrip(base, day1, 1001, "engine", 12, kWhatAsyncFence, 1700, 1500, "exiting", line, sizeof line);
    CHECK(d.sameSession && !d.persist && !exists(f.killSwitch));
    CHECK(slurp(f.history) == "20261116 1000 engine 11\n");
    CHECK(strstr(line, "same stall"));
    // the title restarts: the session flag goes, the history stays
    sessionStart(base);
    CHECK(!sessionOff(base) && exists(f.history));
    // session 2, a second stall the same day: the persistent kill switch and the stronger notice
    d = recordTrip(base, day1, 5000, "title", 99, kWhatPresent, 1000, 1500, "page processes stopped", line, sizeof line);
    CHECK(d.persist);
    CHECK(exists(f.killSwitch) && strstr(slurp(f.killSwitch).c_str(), "20261116"));
    CHECK(takeNotice(base, notice, sizeof notice) && strstr(notice, "twice today"));
    CHECK(strstr(line, "until /data/omni/gpu-pages-stage1-off.flag is removed"));
    // next day, a new session (owner removed the kill switch): a single stall is session-only again; old day dropped
    unlink(f.killSwitch);
    sessionStart(base);
    d = recordTrip(base, day2, 90000, "engine", 13, kWhatFrame, 3100, 1500, "exiting", line, sizeof line);
    CHECK(!d.persist && !exists(f.killSwitch));
    CHECK(slurp(f.history) == "20261117 90000 engine 13\n");
    // no .tmp left behind
    char tmp[260]; snprintf(tmp, sizeof tmp, "%s.tmp", f.history);
    CHECK(!exists(tmp));
    std::string cmd = std::string("rm -rf ") + base;
    CHECK(system(cmd.c_str()) == 0);
}

int main()
{
    testParse();
    testWatch();
    testThreads();
    testDecision();
    testFiles();
    printf("test_gpu_watchdog: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
