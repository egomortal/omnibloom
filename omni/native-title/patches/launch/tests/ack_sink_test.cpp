// OMNI_ACK_V1 split gate: compiles the SHIPPED sink (patches-child/ack-sink.inc) and checks that it splits
// the round trip into the shell's leg and the child's own, refuses nonsense, bounds its own output, and
// emits exactly the lines analyze_ack.py parses. --emit writes one real report for the harness round trip.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unistd.h>

static int checks = 0, failures = 0;
static void check(bool ok, const char* what)
{
    ++checks;
    if (!ok) { ++failures; printf("FAIL %s\n", what); }
}

#include "ack-sink.inc"

static std::string captured;
static int savedStderr = -1;
static char sinkPath[] = "/tmp/omni-ack-sink-XXXXXX";

static void capture()
{
    if (savedStderr < 0) {
        savedStderr = dup(2);
        const int fd = mkstemp(sinkPath);
        dup2(fd, 2);
        close(fd);
    } else {
        lseek(2, 0, SEEK_SET);
        (void)!ftruncate(2, 0);
    }
}

static std::string taken()
{
    fsync(2);
    FILE* f = fopen(sinkPath, "r");
    std::string out;
    if (f) {
        char b[4096];
        size_t n;
        while ((n = fread(b, 1, sizeof b, f)) > 0)
            out.append(b, n);
        fclose(f);
    }
    lseek(2, 0, SEEK_SET);
    (void)!ftruncate(2, 0);
    return out;
}

int main(int argc, char** argv)
{
    const bool emit = argc > 1 && !strcmp(argv[1], "--emit");
    if (emit) {
        // One real 5 s report, for the harness: 200 acks, the shell answering in 3 ms, the child's own
        // thread taking the rest, with two hitches.
        double t = 0;
        for (int i = 0; i < 200; ++i) {
            const double self = (i % 50 == 7) ? 900.0 : 8.0 + (i % 7);
            omniAckSplit(t, t + 3.0, t + 3.0 + self, unsigned(i % 3), uint64_t(i), uint64_t(i / 4), double(i) * 2);
            t += 26.0;
        }
        omniAckSplitReport(200, 50, 400);
        return 0;
    }

    capture();
    check(omniAckSplitOn(), "the flag file turns the split on");
    check(taken().find("OMNI ACK split on pid=") != std::string::npos, "it says so once, with the pid");

    // 1. a normal ack: both legs, no line (under 25 ms)
    omniAckSplit(100, 105, 112, 1, 0, 0, 0);
    check(taken().empty(), "a short round trip writes no line");
    check(omniAk.acks == 1 && omniAk.skew == 0, "it was counted and not called skewed");
    check(omniAk.shell.count == 1 && omniAk.self.count == 1, "both legs were recorded");
    check(std::fabs(omniAkMean(omniAk.shell) - 5.0) < 1e-9, "the shell's leg is ack-sent minus my send");
    check(std::fabs(omniAkMean(omniAk.self) - 7.0) < 1e-9, "my own leg is my handler minus ack-sent");
    check(std::fabs(omniAkMean(omniAk.total) - 12.0) < 1e-9, "the total is what the child already reports");

    // 2. a long one: one line, with the legs
    omniAckSplit(200, 205, 400, 2, 0, 0, 0);
    const std::string line = taken();
    check(line.find("OMNI ACK split n=2 total=200.0 shell=5.0 self=195.0 inflight=2") != std::string::npos,
        "a long round trip writes the split line");

    // 3. clocks that are not comparable: counted as skew, only the total kept
    const uint32_t shellBefore = omniAk.shell.count;
    omniAckSplit(300, 100, 330, 1, 0, 0, 0);     // the shell's stamp precedes my send
    omniAckSplit(400, 999, 430, 1, 0, 0, 0);     // the shell's stamp is after my handler
    omniAckSplit(500, 0, 530, 1, 0, 0, 0);       // no stamp at all
    check(omniAk.skew == 3, "three impossible splits are counted as skew");
    check(omniAk.shell.count == shellBefore, "no skewed leg is recorded");
    check(omniAk.total.count == 5, "but their totals are");
    (void)taken();

    // 4. nonsense is refused outright
    const uint32_t acks = omniAk.acks;
    omniAckSplit(100, 100, 50, 1, 0, 0, 0);      // a negative total
    omniAckSplit(0, 1, 1e12, 1, 0, 0, 0);        // a total no clock could produce
    check(omniAk.acks == acks, "a negative or absurd total is dropped");

    // 5. the histogram line, and the reset
    omniAckSplitReport(12, 3, 48);
    const std::string hist = taken();
    check(hist.find("OMNI ACK hist n=5") != std::string::npos, "the histogram counts the acks in the window");
    check(hist.find("skew=3") != std::string::npos, "it reports the skew");
    check(hist.find("inflightMax=2") != std::string::npos, "it reports the deepest queue");
    check(hist.find("paced=12/48 creditBlocked=3") != std::string::npos, "it reports the pacing counters");
    check(omniAk.acks == 0 && omniAk.skew == 0 && !omniAk.total.count, "the window is reset after a report");

    // 6. the line budget: at most 200 split lines, whatever the page does
    for (int i = 0; i < 400; ++i)
        omniAckSplit(0, 1, 500, 1, 0, 0, 0);
    (void)taken();
    check(omniAk.lines == 200, "the split lines stop at 200");

    // 7. the 5 s report period
    omniAckSplitReport(0, 0, 0);
    (void)taken();
    const uint32_t hists = omniAk.hists;
    omniAckSplit(0, 1, 2, 1, 0, 0, 0);
    omniAckSplit(1000, 1001, 1002, 1, 0, 0, 0);
    check(omniAk.hists == hists, "no report before 5 s of acks");
    omniAckSplit(6000, 6001, 6002, 1, 0, 0, 0);
    check(omniAk.hists == hists + 1, "one report after 5 s");
    (void)taken();

    if (savedStderr >= 0) { dup2(savedStderr, 2); unlink(sinkPath); }
    printf("ack_sink_test: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
