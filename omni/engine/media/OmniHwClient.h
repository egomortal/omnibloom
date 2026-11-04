// WebProcess side of hardware decoding: talks to the UI-process service.
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Mirrors PacketDecoder's contract (submit / receive / drain / flush) so the
// MSE source does not change. Any failure is reported as an error and the
// owning PacketDecoder switches the stream to FFmpeg software decoding.
#pragma once
#include "OmniHwBitstream.h"
#include "OmniHwProtocol.h"
#include "OmniPacketDecoder.h"
#include <deque>
#include <memory> // OMNI_HOLEPUNCH_V1
#include <cmath>  // OMNI_HOLEPUNCH_V4
#include <optional>
#include <string>
#include <vector>

struct SwsContext;

namespace OmniMedia::Hw {

class Client;

// ---- OMNI_HOLEPUNCH_V4: the player's playback clock for shell-side pacing -----------------
// While the shell paces a video, decoded frames go from the decoder straight into the
// service's queue and the shell shows each one at the vblank its time is due by this clock.
struct HoleClockState {
    bool paced = false;         // the service queues and shows this video's frames
    bool playing = false;       // the clock runs (not paused, not seeking, data buffered here)
    bool snapshot = false;      // send the frame on screen back once (FrameSnapshot)
    double position = 0;        // seconds, valid now (the master clock: audio when it plays)
    double rate = 1;
    uint32_t generation = 0;    // changes with every seek/flush
    double discardBefore = -1;  // seconds; frames before it are never shown (seek target); < 0 none
    int64_t traceReleaseUs = 0, tracePrintedUs = 0, traceFlushedUs = 0, traceAfterHoldUs = 0, traceBeforeRingUs = 0;
    int64_t tracePumpStartUs = 0, tracePumpEndUs = 0, traceHoleStartUs = 0, traceClockBuildUs = 0; // V135 measurement only
    double limit = HUGE_VAL;    // seconds; the clock stops there (end of the buffered range)
};

// When to send the clock: on every change, when the position strays from the last update's
// extrapolation by more than toleranceMs, and every periodMs while paced. Pure logic.
class HoleClockSender {
public:
    static constexpr double periodMs = 250, toleranceMs = 4;
    bool due(const HoleClockState& s, double nowMs) const
    {
        if (!sent_) return s.paced;   // nothing to say before pacing starts
        if (s.paced != last_.paced || s.playing != last_.playing || s.rate != last_.rate || s.generation != last_.generation || s.snapshot)
            return true;
        if (!s.paced) return false;   // "pacing off" was said once
        if ((s.discardBefore >= 0) != (last_.discardBefore >= 0) || std::fabs(s.discardBefore - last_.discardBefore) > 1e-6) return true;
        const double near = s.position + 1;   // a limit change matters only when the clock can reach it soon
        if (s.limit != last_.limit && (s.limit < near || last_.limit < near)) return true;
        const double expect = std::min(last_.position + (last_.playing ? (nowMs - lastMs_) / 1000 * last_.rate : 0), last_.limit);
        if (std::fabs(s.position - expect) * 1000 > toleranceMs) return true;
        return nowMs - lastMs_ >= periodMs;
    }
    void sent(const HoleClockState& s, double nowMs) { last_ = s; last_.snapshot = false; lastMs_ = nowMs; sent_ = true; ++updates; }
    uint64_t updates = 0;
private:
    HoleClockState last_;
    double lastMs_ = 0;
    bool sent_ = false;
};

// Audio is the master clock: the player's wall-clock playhead plus a filtered offset to where
// the audio output really is (end of the queued audio minus what is still queued and the
// device buffer). The offset follows with a ~1 s time constant, jumps when it is off by more
// than 0.5 s, and holds while no audio plays or the queue ran dry. Pure logic.
class HoleAudioClock {
public:
    double master(double position, std::optional<double> audio, double nowMs)
    {
        if (audio && std::isfinite(*audio)) {
            const double error = *audio - position;
            if (!have_ || std::fabs(error - offset_) > 0.5) offset_ = error;
            else offset_ += (error - offset_) * std::clamp((nowMs - lastMs_) / 1000, 0.0, 1.0);
            have_ = true;
            lastMs_ = nowMs;
        }
        return position + (have_ ? offset_ : 0);
    }
    void reset() { have_ = false; offset_ = 0; }
    double offset() const { return have_ ? offset_ : 0; }
private:
    bool have_ = false;
    double offset_ = 0, lastMs_ = 0;
};

// ---- OMNI_HOLEPUNCH_V1 ------------------------------------------------------------------
// Hole-punch: the shell (UI process) shows the video *under* the page. The player paints a
// transparent hole where the video is, and per due frame tells the decode service "show
// this slot at this rect" (Present). The service thread converts the slot straight to the
// on-screen size and frees it; the shell blends the page over the newest picture.
//
// HoleLink: shared by a Client and the frames it hands out. After the client disconnects
// every call is a no-op (the service frees the stream's slots and the plane itself when
// the channel closes).
class HoleLink {
public:
    struct Rect {
        int x = 0, y = 0, w = 0, h = 0;   // view pixels
        bool operator==(const Rect& o) const { return x == o.x && y == o.y && w == o.w && h == o.h; }
        bool operator!=(const Rect& o) const { return !(*this == o); }
    };
    bool alive() const { return client_ != nullptr; }
    // OMNI_HOLEPUNCH_V5: the stream failed (the PacketDecoder falls back to software), as opposed to
    // a client closed by a reconfiguration or a seek. Stays set after the client is gone.
    bool clientFailed() const { return clientFailed_; }
    // OMNI_HOLEPUNCH_V2: what the shell confirmed and what this process holds, for the
    // player's safety net and its stall log.
    uint64_t shownCount() const { return shown_; }       // HoleShown acks
    unsigned heldFrames() const { return held_; }        // HoleFrames not yet presented or dropped
    uint64_t presents = 0, presentFailures = 0, rectDrops = 0;
    struct Stats { size_t ready = 0; unsigned outstanding = 0; double lastMessageAgoMs = -1; bool failed = false; };
    Stats stats() const;
    // The service's answer to the last claim/present: 1 the shell shows this video,
    // -1 refused (reason()), 0 no answer yet (or hidden since).
    int state() const { return state_; }
    const char* reason() const { return reason_; }
    // Present(keep): ask for the shell's video plane, or move the video there. No picture.
    // OMNI_HOLEPUNCH_V2: never waits; false (counted in rectDrops) when the socket is
    // full, and the caller sends it again next tick.
    bool claim(const Rect&);
    // Present(hide): give the plane back.
    bool hide();
    // OMNI_HOLEPUNCH_V2: read what the service sent (acks, frames) without decoding.
    void pump();
    // OMNI_HOLEPUNCH_V4: shell-side pacing.
    struct Pacing {
        int state = 0;                 // 1 the shell paces this video, -1 refused (reason), 0 not asked / off
        uint64_t shown = 0, dropped = 0, late = 0, decoded = 0;   // decoded: frames decoded while pacing
        unsigned waiting = 0, capacity = 0;
        uint32_t startupFlags = 0, startupGeneration = 0; // V133 readiness report, scoped to clock generation
        unsigned aheadMs = 0;          // OMNI_HOLEPUNCH_V5_REV2: decoded media queued ahead of the clock
        int64_t mediaUs = INT64_MIN;   // media time of the frame on screen
        double atMs = 0;               // when the last report arrived (0: none)
        char reason[48] = {};
    };
    bool pacingAvailable() const { return pacingAvailable_; }   // the service offered pacing with its acceptance
    const Pacing& pacing() const { return pacing_; }
    double pacingReportAgeMs() const;   // since the last report arrived (0 before the first)
    // The clock (position valid now). Never waits: false when the socket is full (sent next tick).
    bool sendClock(const HoleClockState&);
    // A FrameSnapshot the service sent (converted like any frame), once.
    bool takeSnapshot(DecodedOutput& out);
    // OMNI_MSE_SWITCH_HANDOFF_V1: the player is about to send "pacing off" for a video nobody sees: the shell
    // stops pacing at once (and sends no report for it), so this stream goes back to V4's in-flight depth
    // now, not at the hide 250 ms later (meanwhile seconds of access units went out and came back as
    // converted pictures). A report
    // the shell sent before it read "pacing off" does not turn it back on; the next paced clock does.
    void pacingStopped() { if (pacing_.state == 1) pacing_.state = 0; pacingStopped_ = true; }
private:
    friend class Client;
    friend class HoleFrame;
    Client* client_ = nullptr;
    int state_ = 0;
    char reason_[48] = {};
    uint64_t shown_ = 0;   // OMNI_HOLEPUNCH_V2
    unsigned held_ = 0;
    bool pacingAvailable_ = false, snapshotReady_ = false;   // OMNI_HOLEPUNCH_V4
    bool clientFailed_ = false;                              // OMNI_HOLEPUNCH_V5
    bool pacingStopped_ = false;                             // OMNI_MSE_SWITCH_HANDOFF_V1: pacingStopped() until a paced clock
    Pacing pacing_;
    DecodedOutput snapshot_;
};

// A decoded picture still in its shared output slot. Exactly one of two things ends the
// slot's use by this process: present() hands it to the service (which reads it once,
// on its own thread, and frees it), or the destructor sends Release. convert() (the
// normal RGBA/BGRA conversion, for the paint path) may run before either.
class HoleFrame {
public:
    HoleFrame(std::shared_ptr<HoleLink> link, const Wire::Message& frame) : link_(std::move(link)), frame_(frame) { if (link_) link_->held_++; }
    ~HoleFrame();
    HoleFrame(const HoleFrame&) = delete;
    HoleFrame& operator=(const HoleFrame&) = delete;
    bool convert(DecodedOutput&);
    bool present(const HoleLink::Rect&);
    const std::shared_ptr<HoleLink>& link() const { return link_; }
    uint32_t slot() const { return frame_.a; }
private:
    std::shared_ptr<HoleLink> link_;
    Wire::Message frame_;
    bool handedOff_ = false;
};

// When a player shows its video through a hole. Pure logic (no WebKit, no I/O) so it is
// tested on the host; the player feeds it once per tick, after pumping, and carries out
// the returned actions in the order they are listed.
class HolePunchController {
public:
    using Rect = HoleLink::Rect;
    static constexpr double hideGraceMs = 250;   // keep the plane while the page repaints the video
    static constexpr double retryMs = 3000;      // ask again after a refusal (e.g. another video)
    struct Input {
        double nowMs = 0;
        bool eligible = false;  // flag on, page visible, rendered, no opacity/filter/mask/
                                // clip-path/blend/reflection on the way up, not rotated
        Rect rect;              // video paint rect in view pixels (when eligible)
        bool onScreen = false;  // rect intersects the view
        const void* link = nullptr;  // the current HoleLink (identity), null when none/dead
        int linkState = 0;      // HoleLink::state()
        bool frameDue = false;  // a hole frame became due this tick
        uint64_t shownCount = 0; // OMNI_HOLEPUNCH_V2: HoleLink::shownCount()
        bool playing = false;    // OMNI_HOLEPUNCH_V2: the playback position advanced this tick
        // OMNI_HOLEPUNCH_V4: shell-side pacing (HoleLink::pacing()).
        bool pacing = false;     // pace this video: allowed, offered by the service, not refused
        uint64_t pacedShown = 0, pacedDecoded = 0;
        unsigned pacedWaiting = 0;
        double pacingReportAgeMs = 0;
        uint32_t generation = 0; // seek/flush generation: nothing is due across a seek
        bool pacedDeep = false;  // OMNI_HOLEPUNCH_V5: the shell's queue holds seconds (decoding pauses
                                 // while it is full: frames waiting count as progress)
        bool pacedReported = false; // OMNI_MSE_SWITCH_HANDOFF_V1: pacedShown/pacedDecoded come from a report
                                    // (HoleLink::pacing().state == 1; pacedShown is the plane's total)
    };
    struct Actions {
        bool claim = false;      // link->claim(rect)
        bool present = false;    // dueFrame->present(rect)
        bool paintDue = false;   // the due frame is not shown by the shell: convert and paint it
        bool moveRect = false;   // link->claim(rect): the rect changed
        bool hide = false;       // link->hide()
        bool enterHole = false;  // paint() starts clearing its rect: repaint once
        bool leaveHole = false;  // paint() draws frames again: repaint once
        bool decoderHoles = false; // PacketDecoder::setHolePunch for the following frames
        bool bail = false;       // OMNI_HOLEPUNCH_V2: the safety net tripped this tick (bailReason())
        bool pace = false;       // OMNI_HOLEPUNCH_V4: send the clock with paced on (off: once, without)
        bool snapshot = false;   // OMNI_HOLEPUNCH_V4: a paced hole ended: ask for the frame on screen
    };
    // OMNI_HOLEPUNCH_V2 safety net. While the hole shows, give up for the rest of this load
    // (paint path) when: the shell confirms no picture within confirmMs of the first present;
    // presented frames get no confirmation for stallMs; presents keep failing for stallMs;
    // or no frame becomes due for stallMs while playing.
    static constexpr double confirmMs = 500, stallMs = 1000;
    void claimNotSent() { claimed_ = false; }                 // claim did not go out: ask next tick
    // OMNI_MSE_SWITCH_HANDOFF_V1 (the player sets it from SwitchHandoff::enabled()): a new stream
    // (a configuration change closed the old one, and with it the service gave the plane back)
    // starts afresh. A hide still pending for the old stream is not sent to the new one: it
    // crossed the new stream's claim, the plane went back right after it was taken, and the late
    // answer left the link "shown" without it (pacing refused for good). A safety net tripped on
    // the old stream does not keep the new one on the paint path (rearms counts it). A refusal of the
    // new stream's first claim ("another video is shown": the old stream's close and the new claim
    // came in on two channels, the claim first) is asked again after 50 ms, not 3 s. The hole starts
    // when the shell shows one of the new stream's pictures: pacedShown is the plane's total, so its
    // baseline is the first report's (before it the player paints the new stream's first frames).
    void setSwitchHandoff(bool on) { switchHandoff_ = on; }
    static constexpr double newStreamRetryMs = 50, newStreamMs = 1000;
    uint64_t rearms = 0;
    void rectNotSent() { sent_ = Rect { -1, -1, -1, -1 }; }   // send the rect again next tick
    void presentResult(bool ok, double nowMs)
    {
        if (ok) { lastPresentOkMs_ = nowMs; failuresSinceOk_ = 0; }
        else { ++failuresSinceOk_; ++presentFailures; }
    }
    const char* bailReason() const { return bailReason_; }
    // OMNI_HOLEPUNCH_V4: while paced, the safety net works on the shell's own reports. Give up
    // (paint path) when: queued frames are not shown within confirmMs of the first one; no
    // report arrives for stallMs; frames wait but none is shown for stallMs while playing; or
    // nothing is decoded for stallMs while playing. A gap in this player's own ticks, a seek
    // or a pause restarts the windows.
    Actions tick(const Input& in)
    {
        Actions a;
        if (paced_ && ((lastTickMs_ && in.nowMs - lastTickMs_ > stallMs) || in.generation != lastGeneration_ || !in.playing)) {
            lastShownChangeMs_ = lastDecodedChangeMs_ = in.nowMs;   // OMNI_HOLEPUNCH_V4
            if (firstDecodedMs_) firstDecodedMs_ = in.nowMs;
        }
        lastTickMs_ = in.nowMs; lastGeneration_ = in.generation;
        if (active_ && !bailReason_ && paced_) {   // OMNI_HOLEPUNCH_V4 safety net
            if (in.pacedShown != lastShown_) { lastShown_ = in.pacedShown; lastShownChangeMs_ = in.nowMs; }
            if (in.pacedDecoded != lastDecoded_ || (in.pacedDeep && in.pacedWaiting)) { lastDecoded_ = in.pacedDecoded; lastDecodedChangeMs_ = in.nowMs; }   // V5: pacedDeep
            if (in.pacingReportAgeMs > stallMs) bailReason_ = "no pacing report from the shell for 1 s";
            else if (in.pacedWaiting && in.nowMs - lastShownChangeMs_ > stallMs) bailReason_ = "the shell showed none of its queued frames for 1 s while playing";
            else if (in.nowMs - lastDecodedChangeMs_ > stallMs) bailReason_ = "no frame decoded for the shell for 1 s while playing";
            a.bail = bailReason_ != nullptr;
        } else if (active_ && !bailReason_) {   // OMNI_HOLEPUNCH_V2 safety net
            if (in.shownCount != lastShown_) { lastShown_ = in.shownCount; lastShownChangeMs_ = in.nowMs; presentsSinceShown_ = 0; }
            if (in.frameDue || !in.playing) lastDueOrIdleMs_ = in.nowMs;
            if (in.shownCount == shownAtEnter_ && in.nowMs - enterAtMs_ > confirmMs)
                bailReason_ = "the shell confirmed no frame within 500 ms";
            else if (presentsSinceShown_ && in.nowMs - firstUnshownMs_ > stallMs)
                bailReason_ = "frames presented, none confirmed by the shell for 1 s";
            else if (failuresSinceOk_ && in.nowMs - lastPresentOkMs_ > stallMs)
                bailReason_ = "presents failing for 1 s";
            else if (in.nowMs - lastDueOrIdleMs_ > stallMs)
                bailReason_ = "no frame became due for 1 s while playing";
            a.bail = bailReason_ != nullptr;
        }
        const bool newStream = switchHandoff_ && in.link != link_;   // OMNI_MSE_SWITCH_HANDOFF_V1
        if (newStream && in.link && bailReason_) { bailReason_ = nullptr; ++rearms; }
        if (newStream) newStreamAtMs_ = in.link ? in.nowMs : 0;
        const bool want = in.eligible && in.onScreen && !bailReason_;
        if (in.link != link_) { link_ = in.link; claimed_ = false; }
        const bool accepted = in.link && in.linkState == 1;
        if (in.linkState == -1 && lastState_ != -1) ++refusals;
        lastState_ = in.linkState;
        if (paced_ && (!want || !accepted || !in.pacing)) {   // OMNI_HOLEPUNCH_V4: pacing ends
            paced_ = false;
            a.snapshot = active_;
            if (active_ && want && accepted) { a.leaveHole = true; active_ = false; ++leaves; }   // refused: V3 presents next
        }
        if (!want || !accepted) {
            if (active_) { a.leaveHole = true; active_ = false; ++leaves; hidePending_ = true; hideAt_ = in.nowMs + hideGraceMs; }
            else if (!want && claimed_ && !hidePending_) { hidePending_ = true; hideAt_ = in.nowMs; }
        }
        if (newStream) hidePending_ = false;   // OMNI_MSE_SWITCH_HANDOFF_V1: the old stream's plane went with it
        if (hidePending_ && want && accepted) hidePending_ = false;   // wanted again in time
        if (hidePending_ && in.nowMs >= hideAt_) { hidePending_ = false; claimed_ = false; a.hide = in.link != nullptr; }
        const double retry = switchHandoff_ && newStreamAtMs_ && in.nowMs - newStreamAtMs_ < newStreamMs ? newStreamRetryMs : retryMs;   // OMNI_MSE_SWITCH_HANDOFF_V1
        if (want && in.link && !accepted && !a.hide
            && (!claimed_ || (in.linkState == -1 && in.nowMs - claimAt_ >= retry))) {
            a.claim = true; claimed_ = true; claimAt_ = in.nowMs; sent_ = in.rect; ++claims;
        }
        if (want && accepted && !a.hide && in.pacing && !bailReason_) {   // OMNI_HOLEPUNCH_V4: the shell paces
            a.pace = true;
            if (!paced_) {
                paced_ = true;
                shownAtPace_ = in.pacedShown; decodedAtPace_ = in.pacedDecoded; firstDecodedMs_ = 0;
                paceBaseline_ = !switchHandoff_ || in.pacedReported;   // OMNI_MSE_SWITCH_HANDOFF_V1
            } else if (!paceBaseline_ && in.pacedReported) {
                shownAtPace_ = in.pacedShown; decodedAtPace_ = in.pacedDecoded; paceBaseline_ = true;
            }
            if (paceBaseline_ && !firstDecodedMs_ && in.pacedDecoded != decodedAtPace_) firstDecodedMs_ = in.nowMs;
            if (paceBaseline_ && !active_ && in.pacedShown != shownAtPace_) {
                a.enterHole = true; active_ = true;
                lastShownChangeMs_ = lastDecodedChangeMs_ = in.nowMs;
                lastShown_ = in.pacedShown; lastDecoded_ = in.pacedDecoded;
            } else if (!active_ && firstDecodedMs_ && in.nowMs - firstDecodedMs_ > confirmMs) {
                bailReason_ = "the shell showed none of its queued frames within 500 ms";
                a.bail = true;
            }
            if (!a.bail && in.rect != sent_) { a.moveRect = true; sent_ = in.rect; ++rectUpdates; }   // the shell draws without us
        } else if (want && accepted && !a.hide) {
            if (in.frameDue) {
                a.present = true; sent_ = in.rect; ++presented;
                if (!active_) {
                    a.enterHole = true; active_ = true;
                    // OMNI_HOLEPUNCH_V2: the safety-net clocks start with the hole.
                    enterAtMs_ = lastShownChangeMs_ = lastPresentOkMs_ = lastDueOrIdleMs_ = in.nowMs;
                    shownAtEnter_ = lastShown_ = in.shownCount;
                    presentsSinceShown_ = failuresSinceOk_ = 0;
                }
                if (!presentsSinceShown_++) firstUnshownMs_ = in.nowMs;   // oldest unconfirmed present
            } else if (active_ && in.rect != sent_) {
                a.moveRect = true; sent_ = in.rect; ++rectUpdates;
            }
        }
        a.paintDue = in.frameDue && !a.present;
        presenting_ = want && accepted && !a.hide && !paced_;   // OMNI_HOLEPUNCH_V4: paced frames never reach the player
        a.decoderHoles = want;
        return a;
    }
    bool holeActive() const { return active_; }      // paint() clears its rect
    bool presenting() const { return presenting_; }  // consume() keeps due hole frames for present
    bool claimed() const { return claimed_; }
    bool paced() const { return paced_; }   // OMNI_HOLEPUNCH_V4: the shell paces this video now
    uint64_t presented = 0, rectUpdates = 0, claims = 0, refusals = 0, leaves = 0;
    uint64_t presentFailures = 0;   // OMNI_HOLEPUNCH_V2
private:
    const char* bailReason_ = nullptr;   // OMNI_HOLEPUNCH_V2
    double enterAtMs_ = 0, lastShownChangeMs_ = 0, lastPresentOkMs_ = 0, lastDueOrIdleMs_ = 0, firstUnshownMs_ = 0;
    uint64_t shownAtEnter_ = 0, lastShown_ = 0, presentsSinceShown_ = 0, failuresSinceOk_ = 0;
    // OMNI_HOLEPUNCH_V4
    bool paced_ = false;
    double lastTickMs_ = 0, lastDecodedChangeMs_ = 0, firstDecodedMs_ = 0;
    uint64_t shownAtPace_ = 0, decodedAtPace_ = 0, lastDecoded_ = 0;
    uint32_t lastGeneration_ = 0;
    const void* link_ = nullptr;
    bool active_ = false, claimed_ = false, hidePending_ = false, presenting_ = false;
    bool switchHandoff_ = false, paceBaseline_ = true;   // OMNI_MSE_SWITCH_HANDOFF_V1
    double newStreamAtMs_ = 0;
    double claimAt_ = 0, hideAt_ = 0;
    int lastState_ = 0;
    Rect sent_;
};

// ---- OMNI_HOLEPUNCH_V3: WebProcess main-thread watchdog --------------------------------
// While a hole is shown, the player calls holeWatchdogTick() from every tick (main thread).
// A helper thread checks that the tick keeps running; if it stops for stallMs, it logs the
// last snapshot and asks the main thread, with SIGWINCH, to write its own stack as image
// offsets (async-signal-safe: arithmetic, bounded stack reads and write(2) only). At most
// three reports per process, one per stall. holeWatchdogTick(nullptr) when the hole goes.
struct HoleWatchSnapshot {
    double positionSeconds = 0, lastPresentedSeconds = 0;
    uint64_t presented = 0, shown = 0;
    unsigned held = 0, clientReady = 0, outstanding = 0;
    bool due = false, paused = false;
};
void holeWatchdogTick(const HoleWatchSnapshot*);
constexpr double holeWatchdogStallMs = 2000;
// Tests: reports written so far.
unsigned holeWatchdogReports();

class Client {
public:
    enum class Submit { Accepted, NeedOutput, Error };
    enum class Receive { Output, NeedInput, End, Error };

    Client() = default;
    ~Client();
    Client(const Client&) = delete;
    Client& operator=(const Client&) = delete;

    // True when the flag is set and a service has published its rendezvous file.
    static bool serviceAvailable();

    bool configure(Codec, const DemuxTrack&, bool bgraOutput);
    Submit submit(const DemuxPacket&);
    Submit drain();
    Receive receive(DecodedOutput&);
    void flush();
    const std::string& error() const { return error_; }
    // Raw mode: DecodedOutput.rgba carries the visible picture as compact
    // NV12 (8-bit) or two-plane low-aligned 16-bit (10-bit) instead of
    // RGBA/BGRA. Used by the console probe; later by a GPU NV12 draw path.
    void setRawOutput(bool raw) { raw_ = raw; }
    // OMNI_VIDEO_TARGET_V1: converted frames come out at this size (0 = source size).
    void setTargetSize(int width, int height) { targetWidth_ = width; targetHeight_ = height; }
    // OMNI_HOLEPUNCH_V1: frames come out as DecodedOutput::hole (still in their slot).
    void setHolePunch(bool on) { holePunch_ = on; }
    // OMNI_HOLEPUNCH_V3: wait up to `ms` for the service's next message (Consumed/Frame) and
    // read what arrived; used only while the player is catching up.
    void waitForProgress(int ms) { if (fd_ >= 0 && !failed_ && ms > 0) pumpMessages(ms); }
    // Kill switch (/data/omni/holepunch-disabled.flag) and the hardware decode flag.
    static bool holePunchAllowed();
    // OMNI_HOLEPUNCH_V4: and shell-side pacing (kill switch holepunch-pacing-disabled.flag).
    static bool holePacingAllowed();
    // OMNI_MSE_SWITCH_HANDOFF_V1: this stream's link (null before the stream opened or after it closed).
    const HoleLink* holeLink() const { return link_.get(); }
    // OMNI_MSE_SWITCH_HANDOFF_V1: configure() takes a free channel or fails at once (default: waits up
    // to 2 s for one to be recycled). For a stream opened while another one of this track still plays.
    void setConnectNoWait(bool on) { connectNoWait_ = on; }

private:
    friend class HoleLink;   // OMNI_HOLEPUNCH_V1
    friend class HoleFrame;
    bool trySendMsg(const Wire::Message&);   // OMNI_HOLEPUNCH_V2: never waits; false when full
    bool sendBroken_ = false;                // OMNI_HOLEPUNCH_V2: the socket failed or timed out
    bool connect();
    bool tryConnect();
    bool openStream(int bitDepth);   // connect + Configure + map shared memory
    bool sendMsg(const Wire::Message&);
    // Reads every complete message available; waits up to `waitMs` for the first.
    bool pumpMessages(int waitMs);
    bool waitFor(Wire::Type, Wire::Message&, int timeoutMs);
    bool handle(const Wire::Message&);
    bool convert(const Wire::Message& frame, DecodedOutput&);
    bool fail(const std::string& why);
    bool sendAu(const uint8_t*, size_t, int64_t pts, uint32_t flags);
    void disconnect();
    // OMNI_HOLEPUNCH_V5: the input ring (Wire::inputRingBytes). Access units in flight, oldest
    // first; the service consumes them in order (cumulative Consumed).
    struct InFlight { uint32_t start = 0, end = 0; int64_t pts = 0; };
    bool ringPlace(size_t size, uint32_t head, uint32_t tail, bool empty, uint32_t& offset) const;
    bool ringFits(const size_t* sizes, size_t count) const;
    void ringConsumed(uint32_t total);
    void ringReset();
    unsigned inFlightLimit() const;
    double inFlightSeconds() const;

    int fd_ = -1, channel_ = -1;
    pid_t servicePid_ = 0;
    uint8_t* shm_ = nullptr; size_t shmSize_ = 0;
    uint32_t slotOffset_ = 0, slotSize_ = 0, slotCount_ = 0;
    std::deque<InFlight> inFlight_;           // OMNI_HOLEPUNCH_V5
    uint32_t ringHead_ = 0;                   // next free byte (when the ring is not empty)
    uint32_t consumed_ = 0;                   // Submits the service consumed (cumulative)
    int64_t inFlightMaxPts_ = INT64_MIN;      // newest pts in flight (B-frames: the largest)
    bool v5_ = true;                          // holeV5FlagEnabled() at configure
    bool blocked_ = false;                    // the last submit hit the in-flight limit
    double blockedPollMs_ = 0;                // and when this client last read its socket then
    Codec codec_ = Codec::H264;
    NalConfig nal_;
    DemuxTrack track_;
    bool bgra_ = false, raw_ = false;
    int targetWidth_ = 0, targetHeight_ = 0, loggedWidth_ = 0, loggedHeight_ = 0, sizeLogs_ = 0;
    bool drained_ = false, draining_ = false, failed_ = false, opened_ = false;
    std::deque<DecodedOutput> ready_;
    std::vector<uint8_t> scratch_;
    std::vector<uint8_t> au_;
    std::vector<Vp9Frame> vp9_;
    size_t partialLen_ = 0;
    Wire::Message partial_;
    unsigned outstanding_ = 0;
    bool busy_ = false, recycling_ = false;   // connect(): retry only while channels are in use
    bool randomAccess_ = true;        // next IRAP starts decoding (configure/flush)
    bool skipRasl_ = false;           // dropping RASL pictures of that IRAP        // submitted AUs not yet Consumed
    double lastProgressMs_ = 0;
    double lastPumpMs_ = 0;   // OMNI_HOLEPUNCH_V3: when this client last read its socket
    [[maybe_unused]] SwsContext* sws_ = nullptr;   // unused when built without swscale
    // OMNI_HOLEPUNCH_COLOUR_V1: the conversion's colour (Configure.f) and what sws_ was made for.
    uint32_t colour_ = 0;
    [[maybe_unused]] int swsKey_[7] = {};
    std::string error_;
    bool connectNoWait_ = false;          // OMNI_MSE_SWITCH_HANDOFF_V1
    bool holePunch_ = false;              // OMNI_HOLEPUNCH_V1
    std::shared_ptr<HoleLink> link_;      // per opened stream; detached on disconnect
};

}
