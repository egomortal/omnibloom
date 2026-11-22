// OMNI_ACK_V1 (title / UI process) -----------------------------------------------------------------------
// The page cannot produce a frame until this process answers DisplayDidRefresh: the WebProcess sends
// DrawingAreaProxy::Update, sets m_isWaitingForDidUpdate, and will not display again until the ack comes
// back. Measured on four s3.4d runs from the child's own counters: mean round trip 144-169 ms, max
// 1.43-2.57 s, which caps page frames at about 6/s while a page loads.
//
// Upstream answers the ack AFTER copying the update into the backing store and reporting the damage, and in
// one case does not answer at all (a geometry round trip in flight whose size matches: the update is
// incorporated and no DisplayDidRefresh is sent, so a page that was waiting stays waiting until something
// else forces an update). This takes the ack off the shell's own work:
//   * the ack is sent BEFORE incorporateUpdate(), so neither the backing-store copy nor setViewNeedsDisplay
//     is inside the round trip;
//   * the ack is sent for EVERY Update, so a page can never be left waiting for a swallowed ack;
//   * the DisplayDidRefresh timestamp is taken at dispatch, which is what the child's own split
//     ("OMNI ACK split") uses to separate the shell's leg from its own.
// It cannot make the ack earlier than the moment this process dispatches the Update: that is this thread's
// run loop, the same one that runs tick(). What the shell can do is answer the instant it looks, and the
// child half of OMNI_ACK_V1 stops the page waiting for it at all.
//
// Acking before the copy is safe on this port: the WebProcess allocates a FRESH ShareableBitmap for every
// update (DrawingAreaCoordinatedGraphics::display -> ShareableBitmap::create, ~0.04 ms per frame measured),
// so an early ack cannot let it repaint pixels this process has not read yet, and the connection keeps
// messages ordered, so the next Update is still incorporated after this one.
//
// Kill switch: /data/omni/ack-off.flag restores the upstream order exactly (checked once, raw access()).
// Diagnostics: only with /data/omni/jank.flag, the same flag the jank pass uses.
#ifndef OMNI_ACK_TITLE_STDLIB
#define OMNI_ACK_TITLE_STDLIB 1
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#endif
#ifndef OMNI_ACK_OFF_FLAG_PATH
#define OMNI_ACK_OFF_FLAG_PATH "/data/omni/ack-off.flag"
#endif
#ifndef OMNI_ACK_DIAG_FLAG_PATH
#define OMNI_ACK_DIAG_FLAG_PATH "/data/omni/jank.flag"
#endif

static bool omniAckV1On()
{
    static const bool on = ::access(OMNI_ACK_OFF_FLAG_PATH, F_OK) != 0;
    return on;
}

static bool omniAckDiagnosticsOn()
{
    static const bool on = ::access(OMNI_ACK_DIAG_FLAG_PATH, F_OK) == 0;
    return on;
}

namespace {
struct OmniAckShellStats {
    uint64_t updates, acks, swallowFixed, stale, exits;
    double incorporateTotal, incorporateMax;
    double gapTotal, gapMax;
    unsigned lines;
    MonotonicTime lastUpdate;
};
OmniAckShellStats omniAckShell;
}

// One Update dispatched: how long the work AFTER the ack took, and how far apart the updates are.
static void omniAckShellUpdate(MonotonicTime ackedAt, bool swallowFixed, bool stale, bool exitUpdate = false)
{
    ++omniAckShell.updates;
    ++omniAckShell.acks;
    if (swallowFixed)
        ++omniAckShell.swallowFixed;
    if (stale)
        ++omniAckShell.stale;
    if (exitUpdate)
        ++omniAckShell.exits;
    const MonotonicTime now = MonotonicTime::now();
    const double work = (now - ackedAt).seconds() * 1000;
    if (work >= 0 && work < 1e6) {
        omniAckShell.incorporateTotal += work;
        if (work > omniAckShell.incorporateMax)
            omniAckShell.incorporateMax = work;
    }
    if (omniAckShell.lastUpdate) {
        const double gap = (now - omniAckShell.lastUpdate).seconds() * 1000;
        if (gap >= 0 && gap < 1e6) {
            omniAckShell.gapTotal += gap;
            if (gap > omniAckShell.gapMax)
                omniAckShell.gapMax = gap;
        }
    }
    omniAckShell.lastUpdate = now;
    if (!omniAckDiagnosticsOn() || omniAckShell.updates % 30 || omniAckShell.lines >= 200)
        return;
    ++omniAckShell.lines;
    const double n = double(omniAckShell.updates);
    fprintf(stderr, "OMNI ACK shell: updates=%llu acks=%llu swallowFixed=%llu stale=%llu exits=%llu"
        " afterAck mean=%.3f max=%.3f ms | between updates mean=%.1f max=%.1f ms\n",
        static_cast<unsigned long long>(omniAckShell.updates), static_cast<unsigned long long>(omniAckShell.acks),
        static_cast<unsigned long long>(omniAckShell.swallowFixed), static_cast<unsigned long long>(omniAckShell.stale),
        static_cast<unsigned long long>(omniAckShell.exits),
        omniAckShell.incorporateTotal / n, omniAckShell.incorporateMax,
        omniAckShell.updates > 1 ? omniAckShell.gapTotal / (n - 1) : 0.0, omniAckShell.gapMax);
    fflush(stderr);
}
