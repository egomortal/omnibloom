// OMNI_ACK_V1 title gate: compiles the SHIPPED update()/exitAcceleratedCompositingMode() bodies
// (patches-eboot/ack-update.inc, written by apply_ack_title.py) and the shipped helpers (src/ack-title.inc)
// against stubs, and checks the one property the fix exists for: the page's ack does not wait for this
// process's work with the update.
//   run once with the kill-switch file absent  -> OMNI_ACK_V1 order
//   run once with it present (argv[1] = "off") -> the upstream order, unchanged
// Both runs are needed: the flag is read once per process, as it is on the console.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

static int checks = 0, failures = 0;
static void check(bool ok, const char* what)
{
    ++checks;
    if (!ok) { ++failures; printf("FAIL %s\n", what); }
}

// ---- stubs ------------------------------------------------------------------------------------------
static double gClockMs = 1000.0;

class Seconds {
public:
    explicit Seconds(double s) : m_s(s) { }
    double seconds() const { return m_s; }
    double milliseconds() const { return m_s * 1000; }
private:
    double m_s;
};

class MonotonicTime {
public:
    MonotonicTime() = default;
    static MonotonicTime now() { MonotonicTime t; t.m_ms = gClockMs; return t; }
    Seconds operator-(const MonotonicTime& other) const { return Seconds((m_ms - other.m_ms) / 1000); }
    explicit operator bool() const { return m_ms != 0; }
    double ms() const { return m_ms; }
private:
    double m_ms { 0 };
};

struct IntSize {
    int w { 0 }, h { 0 };
    bool operator!=(const IntSize& o) const { return w != o.w || h != o.h; }
};

struct UpdateInfo {
    IntSize viewSize;
    int id { 0 };
};

namespace WTF { template<typename T> T&& move(T& v) { return static_cast<T&&>(v); } }

// what the shell did, in order
static std::vector<std::string> gLog;
static double gAckAt = -1, gIncorporateAt = -1;
static double gIncorporateCostMs = 0;

namespace Messages { namespace DrawingArea {
struct DisplayDidRefresh { explicit DisplayDidRefresh(MonotonicTime t) : at(t) { } MonotonicTime at; };
} }

class DrawingAreaProxyCoordinatedGraphics {
public:
    void update(uint64_t, UpdateInfo&&);
    void exitAcceleratedCompositingMode(uint64_t, UpdateInfo&&);

    bool m_isWaitingForDidUpdateGeometry { false };
    IntSize m_lastSentSize;
    int m_incorporated { 0 };

private:
    void send(Messages::DrawingArea::DisplayDidRefresh&& m)
    {
        gLog.push_back("ack");
        gAckAt = m.at.ms();
    }
    void incorporateUpdate(UpdateInfo&&)
    {
        gLog.push_back("incorporate");
        gIncorporateAt = gClockMs;
        ++m_incorporated;
        gClockMs += gIncorporateCostMs;   // the backing-store copy + setViewNeedsDisplay
    }
    void exitAcceleratedCompositingMode() { gLog.push_back("exit"); }
};

#include "ack-title.inc"
#include "ack-update.inc"

// ---- the test ---------------------------------------------------------------------------------------
static void reset()
{
    gLog.clear();
    gAckAt = gIncorporateAt = -1;
}

int main(int argc, char** argv)
{
    const bool killSwitch = argc > 1 && !strcmp(argv[1], "off");
    const bool on = omniAckV1On();
    check(on == !killSwitch, "the kill-switch file decides the policy");

    // 1. a normal update, with a 500 ms backing-store copy: the ack must not be behind it
    gIncorporateCostMs = 500;
    DrawingAreaProxyCoordinatedGraphics area;
    reset();
    const double arrived = gClockMs;
    UpdateInfo one; one.viewSize = { 1920, 1080 }; one.id = 1;
    area.update(0, WTF::move(one));
    check(gLog.size() == 2, "one ack and one incorporate");
    check(area.m_incorporated == 1, "the update was incorporated");
    if (on) {
        check(gLog[0] == "ack" && gLog[1] == "incorporate", "OMNI_ACK_V1: ack first, then the copy");
        check(gAckAt - arrived < 1.0, "the ack timestamp is taken before the copy");
    } else {
        check(gLog[0] == "incorporate" && gLog[1] == "ack", "upstream: copy first, then the ack");
        check(gAckAt - arrived >= 500.0, "upstream: the ack is 500 ms behind a slow copy");
    }

    // 2. the case upstream answers with nothing: a geometry round trip in flight whose size matches
    reset();
    area.m_isWaitingForDidUpdateGeometry = true;
    area.m_lastSentSize = { 1920, 1080 };
    UpdateInfo two; two.viewSize = { 1920, 1080 }; two.id = 2;
    area.update(0, WTF::move(two));
    const bool acked = gLog.size() && gLog[0] == "ack";
    if (on)
        check(acked && area.m_incorporated == 2, "OMNI_ACK_V1: the swallowed ack is answered, update kept");
    else
        check(!acked && area.m_incorporated == 2, "upstream: no ack at all for this update");

    // 3. an update for a size this process no longer wants: acked, dropped, in both policies
    reset();
    area.m_lastSentSize = { 1280, 720 };
    UpdateInfo three; three.viewSize = { 1920, 1080 }; three.id = 3;
    const int before = area.m_incorporated;
    area.update(0, WTF::move(three));
    check(gLog.size() == 1 && gLog[0] == "ack", "a stale-size update is acked and not incorporated");
    check(area.m_incorporated == before, "a stale-size update is dropped");
    area.m_isWaitingForDidUpdateGeometry = false;

    // 4. leaving accelerated compositing: the child waits for this one too
    reset();
    UpdateInfo four; four.viewSize = { 1920, 1080 }; four.id = 4;
    area.exitAcceleratedCompositingMode(0, WTF::move(four));
    const bool exitAcked = gLog.size() > 1 && gLog[1] == "ack";
    if (on) {
        check(gLog.size() == 3 && gLog[0] == "exit" && exitAcked && gLog[2] == "incorporate",
            "OMNI_ACK_V1: the exit update is acked before the copy");
    } else {
        check(gLog.size() == 2 && gLog[0] == "exit" && gLog[1] == "incorporate",
            "upstream: the exit update is never acked");
    }

    // 5. a fast copy: the ack is still first, and the shell's own stats add up
    gIncorporateCostMs = 0.2;
    reset();
    for (int i = 0; i < 40; ++i) {
        UpdateInfo u; u.viewSize = { 1920, 1080 }; u.id = 100 + i;
        gClockMs += 16.7;
        area.update(0, WTF::move(u));
    }
    if (on) {
        check(omniAckShell.updates == 44, "every update is counted");
        check(omniAckShell.acks == omniAckShell.updates, "every update was answered");
        check(omniAckShell.swallowFixed == 1, "exactly the one swallowed case was fixed");
        check(omniAckShell.exits == 1, "the exit-compositing update is counted on its own");
        check(omniAckShell.stale == 1, "exactly one stale-size update");
        check(omniAckShell.incorporateMax >= 500.0, "the 500 ms copy is in the shell's own stats");
    } else
        check(omniAckShell.updates == 0, "upstream path records nothing");

    printf("ack_order_test (%s): %d checks, %d failures\n", on ? "OMNI_ACK_V1" : "kill switch", checks, failures);
    return failures ? 1 : 0;
}
