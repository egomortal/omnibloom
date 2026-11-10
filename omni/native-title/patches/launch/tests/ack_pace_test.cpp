// OMNI_ACK_V1 child gate: compiles the SHIPPED policy (patches-child/ack-policy.inc, written by
// apply_ack_child.py) and drives it through a model of the three patched call sites - scheduleDisplay(),
// display() and displayDidRefresh() - with a virtual clock, so the claims are numbers:
//   * with the kill switch, one update in flight and one frame per round trip, exactly as upstream;
//   * with the fix, the page's frames are paced by the display period and never faster than it;
//   * a shell that never answers can hold at most `credits` updates (nothing is unbounded);
//   * the round trip stops dividing the frame rate: production is credits/roundTrip, not 1/roundTrip.
// Run once per policy: the policy is read from the environment once per process, as on the console.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static int checks = 0, failures = 0;
static void check(bool ok, const char* what)
{
    ++checks;
    if (!ok) { ++failures; printf("FAIL %s\n", what); }
}
static void checkNear(double got, double want, double tolerance, const char* what)
{
    ++checks;
    if (!(std::fabs(got - want) <= tolerance)) {
        ++failures;
        printf("FAIL %s (got %.3f, want %.3f +-%.3f)\n", what, got, want, tolerance);
    }
}

#include "ack-policy.inc"

// ---- a model of the patched call sites --------------------------------------------------------------
struct Page {
    OmniAckPolicy policy;
    double now { 0 };
    unsigned inFlight { 0 };
    double lastDisplay { -1 };        // < 0: never displayed
    bool timerActive { false };
    double timerAt { 0 };
    bool scheduledWhileWaiting { false };
    bool waitingForDidUpdate { false };
    bool suspended { false };
    double paintMs { 1 };
    double ackLatencyMs { 0 };        // < 0: the shell never answers
    unsigned frames { 0 }, paced { 0 }, creditBlocked { 0 }, inFlightMax { 0 };
    std::vector<double> sentAt, acksDue;
    std::vector<double> frameAt;

    void scheduleDisplay()
    {
        if (policy.credits) {
            const double since = lastDisplay >= 0 ? now - lastDisplay : -1.0;
            double delay = 0;
            switch (omniAckSchedule(policy, inFlight, suspended, timerActive, since, &delay)) {
            case OmniAckDisplayNow:
                timerActive = true; timerAt = now; return;
            case OmniAckDisplayAfter:
                ++paced; timerActive = true; timerAt = now + delay; return;
            case OmniAckAlreadyScheduled:
                return;
            case OmniAckWaitForAck:
                if (!suspended) { scheduledWhileWaiting = true; ++creditBlocked; }
                return;
            }
            return;
        }
        if (waitingForDidUpdate) { scheduledWhileWaiting = true; return; }
        if (suspended) return;
        if (timerActive) return;
        timerActive = true; timerAt = now;
    }

    void display()   // the display timer fired: paint, then send the Update
    {
        timerActive = false;
        now += paintMs;
        ++frames;
        frameAt.push_back(now);
        waitingForDidUpdate = true;
        scheduledWhileWaiting = false;
        if (policy.credits) {
            ++inFlight;
            lastDisplay = now;
            if (inFlight > inFlightMax) inFlightMax = inFlight;
            if (ackLatencyMs >= 0) acksDue.push_back(now + ackLatencyMs);
        } else if (ackLatencyMs >= 0)
            acksDue.push_back(now + ackLatencyMs);
    }

    void displayDidRefresh()
    {
        waitingForDidUpdate = false;
        if (policy.credits) {
            if (inFlight) --inFlight;
            if (inFlight) waitingForDidUpdate = true;
            if (!scheduledWhileWaiting) return;
            scheduledWhileWaiting = false;
            scheduleDisplay();
            return;
        }
        if (!scheduledWhileWaiting) return;
        scheduledWhileWaiting = false;
        display();
    }

    // The page always has something new to show (a loading page), the clock moves in 0.5 ms steps.
    void run(double forMs)
    {
        const double end = now + forMs;
        while (now < end) {
            if (!acksDue.empty() && acksDue.front() <= now) {
                acksDue.erase(acksDue.begin());
                displayDidRefresh();
                continue;
            }
            if (timerActive && timerAt <= now) { display(); continue; }
            scheduleDisplay();                      // an invalidation
            now += 0.5;
        }
    }
};

static double fps(Page& p, double forMs)
{
    p.run(forMs);
    return double(p.frames) * 1000.0 / forMs;
}

// The invariant the pacing exists for: two frames are never closer together than one display period.
static double minGap(const Page& p)
{
    double smallest = 1e9;
    for (size_t i = 1; i < p.frameAt.size(); ++i)
        smallest = std::fmin(smallest, p.frameAt[i] - p.frameAt[i - 1]);
    return p.frameAt.size() > 1 ? smallest : 1e9;
}

int main()
{
    const OmniAckPolicy shipped = omniAckPolicy();
    const char* pace = getenv("OMNI_ACK_PACE");
    const bool wantOff = pace && !strcmp(pace, "0");
    const char* credits = getenv("OMNI_ACK_CREDITS");
    const char* hz = getenv("OMNI_ACK_HZ");

    // 1. the environment is read exactly as documented
    if (wantOff)
        check(shipped.credits == 0, "OMNI_ACK_PACE=0 turns the pacing off");
    else {
        const long c = credits ? strtol(credits, nullptr, 10) : 2;
        const long want = (c >= 1 && c <= 4) ? c : 2;
        check(shipped.credits == unsigned(want), "OMNI_ACK_CREDITS is honoured, absurd values refused");
        const long h = hz ? strtol(hz, nullptr, 10) : 0;
        const double wantPeriod = (h >= 20 && h <= 144) ? 1000.0 / double(h) : 1001.0 / 60;
        checkNear(shipped.periodMs, wantPeriod, 1e-9, "OMNI_ACK_HZ is honoured, absurd values refused");
    }

    const OmniAckPolicy off { 0, 1001.0 / 60 };
    const OmniAckPolicy on { 2, 1001.0 / 60 };

    // 2. the upstream gate: one frame per round trip, whatever the round trip is
    for (double latency : { 150.0, 16.7 }) {
        Page p; p.policy = off; p.paintMs = 1; p.ackLatencyMs = latency;
        const double got = fps(p, 3000);
        checkNear(got, 1000.0 / (latency + 1), 1.2, "upstream: one frame per round trip");
        check(p.inFlightMax <= 1, "upstream: never more than one update in flight");
    }

    // 3. the fix: the 150 ms round trip no longer divides the frame rate
    {
        Page p; p.policy = on; p.paintMs = 1; p.ackLatencyMs = 150;
        const double got = fps(p, 3000);
        checkNear(got, 2 * 1000.0 / (150 + 1), 1.5, "with credits=2 a 150 ms round trip gives twice the frames");
        check(p.inFlightMax == 2, "at most the credit limit is in flight");
        check(p.creditBlocked > 0, "past the credits the page waits, as upstream does");
        check(minGap(p) >= on.periodMs - 0.6, "frames are never closer than one display period");
    }

    // 4. the fix: frame production is bounded by the display period, not by the shell
    for (double latency : { 0.0, 5.0, 16.7 }) {
        Page p; p.policy = on; p.paintMs = 1; p.ackLatencyMs = latency;
        const double got = fps(p, 3000);
        check(got <= 1000.0 / on.periodMs + 0.5, "never faster than the display refresh");
        check(got > 55.0, "with a fast shell the page runs at the display refresh");
        check(minGap(p) >= on.periodMs - 0.6, "frames are never closer than one display period");
    }

    // 5. and the floor is what bounds it: without it the same loop would paint far more often
    {
        Page p; p.policy = off; p.paintMs = 1; p.ackLatencyMs = 0;
        const double got = fps(p, 1000);
        check(got > 200.0, "upstream has no refresh floor at all (it relies on the round trip)");
    }

    // 6. a shell that never answers: bounded, and the page is not wedged for ever when it comes back
    {
        Page p; p.policy = on; p.paintMs = 1; p.ackLatencyMs = -1;
        p.run(2000);
        check(p.frames == 2, "a wedged shell can hold exactly the credit limit, no more");
        check(p.inFlight == 2 && p.scheduledWhileWaiting, "the pending frame is remembered");
        p.acksDue.push_back(p.now);
        p.ackLatencyMs = 16.7;
        const unsigned before = p.frames;
        p.run(1000);
        check(p.frames > before + 10, "when the acks come back, frames resume");
    }
    {
        Page p; p.policy = off; p.paintMs = 1; p.ackLatencyMs = -1;
        p.run(2000);
        check(p.frames == 1, "upstream: a wedged shell stops the page after one frame");
    }

    // 7. a long paint is still a long frame, and the pacing never makes it longer
    {
        Page p; p.policy = on; p.paintMs = 40; p.ackLatencyMs = 150;
        const double got = fps(p, 4000);
        checkNear(got, 2 * 1000.0 / 190.0, 1.5, "the credits overlap the round trip with the next paint");
        check(minGap(p) >= 40.0, "a 40 ms paint, not the pacing, sets the frame interval");
    }

    // 8. the policy function's edges
    {
        double delay = -1;
        check(omniAckSchedule(off, 0, false, false, 100, &delay) == OmniAckWaitForAck, "credits=0: the caller takes the upstream path");
        check(omniAckSchedule(on, 0, true, false, 100, &delay) == OmniAckWaitForAck, "painting suspended: nothing is scheduled");
        check(omniAckSchedule(on, 2, false, false, 100, &delay) == OmniAckWaitForAck, "out of credits: wait for an ack");
        check(omniAckSchedule(on, 1, false, true, 100, &delay) == OmniAckAlreadyScheduled, "a display is already pending");
        check(omniAckSchedule(on, 1, false, false, -1, &delay) == OmniAckDisplayNow, "a clock that never ran: display now");
        check(omniAckSchedule(on, 1, false, false, -5, &delay) == OmniAckDisplayNow, "a clock that went backwards: display now");
        check(omniAckSchedule(on, 1, false, false, 1e9, &delay) == OmniAckDisplayNow, "long past the period: display now");
        delay = -1;
        check(omniAckSchedule(on, 0, false, false, on.periodMs - 10.0, &delay) == OmniAckDisplayAfter, "inside the period: pace it");
        checkNear(delay, 10.0, 1e-9, "the delay is the rest of the display period");
        delay = -1;
        check(omniAckSchedule(on, 0, false, false, on.periodMs, &delay) == OmniAckDisplayNow, "exactly one period: display now");
        checkNear(delay, 0.0, 1e-9, "no delay is asked for when displaying now");
    }

    printf("ack_pace_test (credits=%u period=%.3f): %d checks, %d failures\n",
        shipped.credits, shipped.periodMs, checks, failures);
    return failures ? 1 : 0;
}
