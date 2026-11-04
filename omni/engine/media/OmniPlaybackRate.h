// OMNI_PLAYBACK_RATE_V1: playbackRate for Omni's players. SPDX-License-Identifier: GPL-3.0-or-later
//
// Why: every player answered rate() = 1 and ignored setRate(): native HLS at playbackRate 1.5 ran
// at 1.05x (v90). This header holds what the three players (MSE, native HLS, plain files) share:
//   * Rate::effective(): the rate a player runs at for a requested one: 0.25 .. 2.0 (clamped;
//     <= 0: the clock stops). WebKit gets it through effectiveRate() and rateChanged().
//   * TimeStretch: pitch-preserving time stretching of 48 kHz stereo s16 (WSOLA: 1024-frame Hann
//     windows, 512-frame synthesis hop, the analysis hop = 512 x rate, each window placed within
//     +-384 frames of its nominal position where it best continues the previous one). Rate 1 is an
//     exact pass-through; the switches to and from it are seamless (the overlap is completed with
//     the input itself). Pure C++, no FFmpeg filter: the engine links no libavfilter (atempo).
//   * RateAudio: TimeStretch plus the last few seconds of unstretched input, so a rate change is
//     heard at once: the player clears its output (ring) and RateAudio feeds the stretcher again
//     from the playhead at the new rate (otherwise the ~3 s already queued would play at the old
//     rate first). Output chunks carry their media start and speed (media seconds per output
//     second) for AudioRing's clock (OmniAudioRing.h, OMNI_PLAYBACK_RATE_V1).
// Kill switch: /data/omni/playback-rate-disabled.flag (host: OMNI_PLAYBACK_RATE=0): rate 1 always,
// as before. Tested on the host (rate-test.cpp, against FFmpeg's atempo).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <unistd.h>
#include <vector>

namespace OmniMedia::Rate {

constexpr double minimum = 0.25, maximum = 2.0;

inline bool enabled()
{
    if (const char* env = getenv("OMNI_PLAYBACK_RATE")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/playback-rate-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
// The rate a player runs at when `requested` is asked for (0: the clock stops).
inline double effective(double requested)
{
    if (!enabled()) return 1;
    if (!std::isfinite(requested) || requested <= 0) return 0;
    return std::clamp(requested, minimum, maximum);
}

class TimeStretch {
public:
    static constexpr int rate48k = 48000, channels = 2;
    static constexpr int window = 1024, hop = 512, search = 384;

    TimeStretch() { for (int n = 0; n < window; n++) w_[n] = float(0.5 - 0.5 * std::cos(2 * M_PI * n / window)); reset(); }
    void reset()
    {
        in_.clear(); inBase_ = 0; haveMedia_ = false; media0_ = 0;
        stretching_ = false; rawPos_ = 0; prevStart_ = 0; nominal_ = 0;
        std::fill(std::begin(acc_), std::end(acc_), 0.0f);
        outMedia_ = 0; ended_ = false;
    }
    double rate() const { return rate_; }
    void setRate(double r) { rate_ = std::clamp(r, minimum, maximum); }
    // Contiguous input (a jump of more than 2 ms in media time starts over).
    void push(const int16_t* pcm, size_t frames, double mediaStart)
    {
        if (!frames) return;
        if (haveMedia_ && std::fabs(mediaStart - mediaAt(inBase_ + int64_t(in_.size() / channels))) > 0.002) reset();
        if (!haveMedia_) { haveMedia_ = true; media0_ = mediaStart; inBase_ = 0; rawPos_ = 0; outMedia_ = mediaStart; }
        const size_t at = in_.size();
        in_.resize(at + frames * channels);
        for (size_t i = 0; i < frames * channels; i++) in_[at + i] = float(pcm[i]);
    }
    // The stream ended: what is held back is emitted (padded with silence) by the next pulls.
    void endOfStream() { if (haveMedia_ && !ended_ && stretching_) { ended_ = true; in_.resize(in_.size() + size_t(window + search + hop) * channels, 0.0f); } }
    // Nothing can be pulled now (more input is needed; or everything came out).
    bool idle() const
    {
        if (!haveMedia_) return true;
        if (!stretching_) return rawPos_ >= endFrame();
        return endFrame() < int64_t(std::llround(nominal_)) + search + window || endFrame() < prevStart_ + 2 * hop;
    }
    // Input frames pushed and not yet turned into output.
    size_t backlogFrames() const
    {
        const int64_t end = inBase_ + int64_t(in_.size() / channels);
        const int64_t consumed = stretching_ ? int64_t(nominal_) : rawPos_;
        return size_t(std::max<int64_t>(0, end - consumed));
    }
    // Up to `maxFrames` output frames with one media start and speed (media s per output s);
    // 0 when more input is needed.
    size_t pull(int16_t* out, size_t maxFrames, double& mediaStart, double& speed)
    {
        if (!haveMedia_ || !maxFrames) return 0;
        const bool want = std::fabs(rate_ - 1.0) > 1e-9;
        if (want && !stretching_) startStretch();
        if (!want && stretching_) { if (size_t n = finishStretch(out, maxFrames, mediaStart, speed)) return n; if (stretching_) return 0; }
        if (!stretching_) {   // pass-through
            const int64_t avail = inBase_ + int64_t(in_.size() / channels) - rawPos_;
            const size_t n = size_t(std::min<int64_t>(avail, int64_t(maxFrames)));
            if (!n) return 0;
            const float* src = &in_[size_t(rawPos_ - inBase_) * channels];
            for (size_t i = 0; i < n * channels; i++) out[i] = clip(src[i]);
            mediaStart = mediaAt(rawPos_); speed = 1;
            rawPos_ += int64_t(n);
            trim(rawPos_);
            return n;
        }
        // WSOLA, whole hops only.
        size_t done = 0;
        mediaStart = outMedia_; speed = rate_;
        while (done + hop <= maxFrames && step(out + done * channels)) done += hop;
        return done;
    }
    // Pure helpers, also used by the tests.
    static int16_t clip(float v) { return int16_t(std::clamp(std::lrintf(v), -32768L, 32767L)); }

private:
    double mediaAt(int64_t frame) const { return media0_ + double(frame) / rate48k; }
    float* at(int64_t frame) { return &in_[size_t(frame - inBase_) * channels]; }
    int64_t endFrame() const { return inBase_ + int64_t(in_.size() / channels); }
    void trim(int64_t keepFrom)
    {
        const int64_t drop = keepFrom - inBase_;
        if (drop > 8192) { in_.erase(in_.begin(), in_.begin() + std::ptrdiff_t(drop * channels)); inBase_ += drop; }
    }
    // From pass-through at rawPos_: a virtual previous window that started a hop earlier, so the
    // first output hop is the input itself at rate 1 and continues it otherwise.
    void startStretch()
    {
        stretching_ = true;
        prevStart_ = rawPos_ - hop;
        nominal_ = double(prevStart_) + hop * rate_;
        accFromInput_ = true;   // acc_ is filled from the input once it is there (step)
        outMedia_ = mediaAt(rawPos_);
    }
    // Back to pass-through: the pending half window plus the rising half of the input at the
    // natural continuation is the input itself; pass-through goes on right after it.
    size_t finishStretch(int16_t* out, size_t maxFrames, double& mediaStart, double& speed)
    {
        const int64_t from = prevStart_ + hop;
        if (maxFrames < size_t(hop) || endFrame() < from + hop) return 0;   // more room / input first
        mediaStart = outMedia_; speed = 1;
        if (accFromInput_) { for (int i = 0; i < hop * channels; i++) out[i] = clip(at(from)[i]); }
        else {
            const float* x = at(from);
            for (int n = 0; n < hop; n++) for (int c = 0; c < channels; c++) out[n * channels + c] = clip(acc_[n * channels + c] + w_[n] * x[n * channels + c]);
        }
        stretching_ = false; rawPos_ = from + hop;
        return hop;
    }
    // One output hop; false when the input does not reach far enough yet.
    bool step(int16_t* out)
    {
        const int64_t natural = prevStart_ + hop;               // where the previous window continues
        const int64_t nominal = int64_t(std::llround(nominal_));
        const int64_t lo = std::max(nominal - search, inBase_), hi = nominal + search;
        if (endFrame() < hi + window || endFrame() < natural + hop) return false;
        if (accFromInput_) {   // the virtual previous window: its falling half is the input at `natural`
            const float* x = at(natural);
            for (int n = 0; n < hop; n++) for (int c = 0; c < channels; c++) acc_[n * channels + c] = w_[n + hop] * x[n * channels + c];
            accFromInput_ = false;
        }
        const int64_t start = best(natural, lo, hi);
        const float* x = at(start);
        for (int n = 0; n < hop; n++) for (int c = 0; c < channels; c++) {
            const int i = n * channels + c;
            out[i] = clip(acc_[i] + w_[n] * x[i]);
            acc_[i] = w_[n + hop] * x[(n + hop) * channels + c];
        }
        prevStart_ = start;
        nominal_ += hop * rate_;
        outMedia_ += hop * rate_ / rate48k;
        trim(std::min<int64_t>(int64_t(nominal_) - search, prevStart_ + hop) - 1);
        return true;
    }
    // The window start in [lo, hi] whose first half best matches the natural continuation
    // (normalised cross-correlation of the mid signal; coarse every 4th frame, then +-3).
    int64_t best(int64_t natural, int64_t lo, int64_t hi)
    {
        const float* t = at(natural);
        auto score = [&](int64_t s) {
            const float* x = at(s);
            double dot = 0, energy = 1e-9;
            for (int n = 0; n < hop; n += 2) {
                const double a = double(t[n * channels]) + t[n * channels + 1], b = double(x[n * channels]) + x[n * channels + 1];
                dot += a * b; energy += b * b;
            }
            return dot / std::sqrt(energy);
        };
        int64_t bestAt = std::clamp(int64_t(std::llround(nominal_)), lo, hi);
        double bestScore = score(bestAt);
        for (int64_t s = lo; s <= hi; s += 4) if (double v = score(s); v > bestScore) { bestScore = v; bestAt = s; }
        for (int64_t s = std::max(lo, bestAt - 3); s <= std::min(hi, bestAt + 3); s++) if (double v = score(s); v > bestScore) { bestScore = v; bestAt = s; }
        return bestAt;
    }
    float w_[window];
    std::vector<float> in_;          // interleaved input from inBase_ on
    int64_t inBase_ = 0;
    bool haveMedia_ = false, stretching_ = false, accFromInput_ = false, ended_ = false;
    double media0_ = 0;              // media time of input frame 0
    int64_t rawPos_ = 0;             // pass-through: next input frame to emit
    int64_t prevStart_ = 0;          // WSOLA: start of the previous window
    double nominal_ = 0;             // WSOLA: nominal start of the next window (input frames)
    float acc_[hop * channels];      // WSOLA: falling half of the previous window
    double outMedia_ = 0;            // WSOLA: media time of the next output hop
    double rate_ = 1;
};

// TimeStretch + a short history of unstretched input (instant rate changes).
class RateAudio {
public:
    static constexpr double historySeconds = 8;
    void reset() { stretch_.reset(); history_.clear(); historyFrames_ = 0; }
    double rate() const { return stretch_.rate(); }
    void push(const int16_t* pcm, size_t frames, double mediaStart)
    {
        if (!frames) return;
        Chunk c; c.media = mediaStart; c.pcm.assign(pcm, pcm + frames * 2);
        history_.push_back(std::move(c)); historyFrames_ += frames;
        while (history_.size() > 1 && double(historyFrames_ - history_.front().pcm.size() / 2) / 48000 > historySeconds) {
            historyFrames_ -= history_.front().pcm.size() / 2; history_.pop_front();
        }
        stretch_.push(pcm, frames, mediaStart);
    }
    void endOfStream() { stretch_.endOfStream(); }
    size_t backlogFrames() const { return stretch_.backlogFrames(); }
    bool idle() const { return stretch_.idle(); }
    size_t pull(int16_t* out, size_t maxFrames, double& mediaStart, double& speed) { return stretch_.pull(out, maxFrames, mediaStart, speed); }
    // A new rate, heard from media time `from` on: the stretcher starts over there from the
    // history (the caller has cleared what it queued). False when the history does not reach
    // back to `from` (then the new rate applies to what comes next).
    bool setRate(double rate, double from)
    {
        if (std::fabs(rate - stretch_.rate()) < 1e-9) return true;
        bool ok = false;
        stretch_.reset();
        stretch_.setRate(rate);
        for (auto& c : history_) {
            const double end = c.media + double(c.pcm.size() / 2) / 48000;
            if (end <= from) continue;
            size_t skip = c.media < from ? std::min(c.pcm.size() / 2, size_t(std::llround((from - c.media) * 48000))) : 0;
            if (c.media <= from + 0.001) ok = true;
            stretch_.push(c.pcm.data() + skip * 2, c.pcm.size() / 2 - skip, c.media + double(skip) / 48000);
        }
        return ok;
    }
    void setRateNoRefeed(double rate) { stretch_.setRate(rate); }
private:
    struct Chunk { double media = 0; std::vector<int16_t> pcm; };
    TimeStretch stretch_;
    std::deque<Chunk> history_;
    size_t historyFrames_ = 0;
};

}
