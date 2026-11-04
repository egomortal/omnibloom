// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <limits>
#include <vector>
#include <unistd.h>
#include "../media/OmniPlaybackRate.h" // OMNI_PERF_C_V4: ClockAudio wraps RateAudio

namespace Omni {
// Time supplies exact comparison/subtraction, isFinite(), and zeroTime().
// Keep the decode clock independent: only the public presentation clock is
// gated until the caller has drained both decoded output and device queues.
template<typename Time>
Time mseReportedTime(Time position, Time duration, bool drained, Time epsilon)
{
    if (!drained && duration.isFinite() && duration > Time::zeroTime())
        return std::min(position, std::max(Time::zeroTime(), duration - epsilon));
    return position;
}

// ---- OMNI_PERF_C_V4: the media clock locked to the display ------------------------------------
// Why: 60.000 fps content on the console's 59.940 Hz output has 0.06 pictures a second too many:
// the shell must drop one every ~16.7 s (rateMismatch: 37 of the 50 drops of a 10-minute 4K HDR run,
// candidate 39). Speed work cannot remove them. Here the player runs its clock at
// display / content (60000/1001 / 60 = 0.999001) for content whose rate is within 0.25 % of the
// display's (60, 30, 24 = 2.5 vblanks, 120, ...): every picture gets its vblank(s), none is repeated
// or dropped for cadence.
//  * The audio follows by resampling (LockResampler, below): a 0.1 % pitch change (1.7 cents, far under
//    what anyone hears; film-to-TV 4 % speedups are a 70-cent shift) with no time-stretch artefacts and
//    no extra latency. At a page playbackRate other than 1 the time-stretcher (OmniPlaybackRate.h)
//    already runs; it then takes rate x lock and the resampler is not used.
//  * The ring's runs carry the speed (media s per output s), so AudioRing::heard() and with it the
//    playhead (audio is the master) and the shell's clock follow it exactly: A/V sync is unchanged.
//  * The page sees playbackRate 1 (rate(), effectiveRate()); currentTime runs 0.1 % slower than the
//    wall clock (3.6 s an hour), which no stall detection notices (they look for no progress).
// The display rate: /data/omni/display-hz.txt (host: OMNI_DISPLAY_HZ) when present, else 60000/1001
// (the console's 60 Hz modes, "display 59.940 Hz" in every pacing log). The player's pacing report
// does not carry the measured rate (it lives in the service, WS-B).
// Kill switch: /data/omni/display-resample-disabled.flag (host: OMNI_DISPLAY_RESAMPLE=0): lock 1, as before.
namespace DisplayLock {
constexpr double maxCorrection = 0.0025;   // at most 0.25 % from the content's own rate
inline bool enabled()
{
    if (const char* env = getenv("OMNI_DISPLAY_RESAMPLE")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/display-resample-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
inline double parseHz(const char* text)
{
    if (!text) return 0;
    char* end = nullptr;
    const double hz = strtod(text, &end);
    return end != text && std::isfinite(hz) && hz >= 23 && hz <= 241 ? hz : 0;
}
inline double displayHz()
{
    static const double hz = [] {
        if (double v = parseHz(getenv("OMNI_DISPLAY_HZ")); v > 0) return v;
#ifdef __PROSPERO__
        if (FILE* f = fopen("/data/omni/display-hz.txt", "r")) {
            char line[32] = {};
            const bool got = fgets(line, sizeof line, f) != nullptr;
            fclose(f);
            if (double v = got ? parseHz(line) : 0; v > 0) return v;
        }
#endif
        return 60000.0 / 1001;
    }();
    return hz;
}
// The nominal rate a measured one is (within 0.04 %), 0 when it is none of them.
inline double nominalFps(double measured)
{
    static const double table[] = { 24000.0 / 1001, 24, 25, 30000.0 / 1001, 30, 48, 50, 60000.0 / 1001, 60, 100, 120000.0 / 1001, 120 };
    if (!(measured > 0) || !std::isfinite(measured)) return 0;
    double best = 0, bestErr = 1;
    for (double t : table) if (double e = std::fabs(measured / t - 1); e < bestErr) { bestErr = e; best = t; }
    return bestErr <= 0.0004 ? best : 0;
}
// The clock factor for content at `fps` on a display at `hz`: (hz / k) / fps for the vblanks per
// picture k that fits best, when that is a correction of at most maxCorrection; else 1.
inline double factor(double fps, double hz)
{
    if (!(fps > 0) || !(hz > 0)) return 1;
    static const double vblanksPerPicture[] = { 0.5, 1, 2, 2.5, 3, 4, 5 };
    double best = 1, bestErr = std::numeric_limits<double>::infinity();
    for (double k : vblanksPerPicture) {
        const double r = hz / k / fps;
        if (double e = std::fabs(r - 1); e < bestErr) { bestErr = e; best = r; }
    }
    return bestErr < 1e-6 || bestErr > maxCorrection ? 1 : best;
}
}

// The content's frame rate from its presentation timestamps (decode order, any timebase): the mean
// of the steps between sorted timestamps of the last `window` pictures, without gaps (seek, missing
// pictures: steps over 1.5x the median) and duplicates (under 0.5x). Snapped to a nominal rate
// (DisplayLock::nominalFps) once the timestamps' precision allows it (millisecond WebM timestamps:
// 5 s of pictures; 90 kHz MP4: under a second). fps() 0: not known (yet), or not nominal.
class FrameRateEstimator {
public:
    static constexpr size_t window = 600, every = 30, minimum = 48;
    void reset() { pts_.clear(); since_ = 0; fps_ = measured_ = 0; }
    // pts in seconds; quantum: the timebase's tick in seconds.
    void push(double pts, double quantum)
    {
        if (!std::isfinite(pts)) return;
        pts_.push_back(pts);
        if (pts_.size() > window) pts_.pop_front();
        if (std::isfinite(quantum) && quantum > 0) quantum_ = quantum;
        if (++since_ >= every) { since_ = 0; compute(); }
    }
    double fps() const { return fps_; }
    double measured() const { return measured_; }
private:
    void compute()
    {
        if (pts_.size() < minimum) return;
        std::vector<double> s(pts_.begin(), pts_.end());
        std::sort(s.begin(), s.end());
        std::vector<double> d;
        d.reserve(s.size());
        for (size_t i = 1; i < s.size(); i++) d.push_back(s[i] - s[i - 1]);
        std::vector<double> m = d;
        std::nth_element(m.begin(), m.begin() + std::ptrdiff_t(m.size() / 2), m.end());
        const double median = m[m.size() / 2];
        if (!(median > 0)) return;
        double span = 0; size_t n = 0, runs = 1;
        bool inRun = true;
        for (double v : d) {
            if (v >= 0.5 * median && v <= 1.5 * median) { span += v; n++; if (!inRun) { runs++; inRun = true; } }
            else inRun = false;
        }
        if (n + 1 < minimum || !(span > 0)) return;
        // Each contiguous run's span is exact to within one tick (half a tick of rounding at either end).
        if (quantum_ * double(runs) / span > 0.0002) return;   // not precise enough yet: keep the last answer
        measured_ = double(n) / span;
        fps_ = DisplayLock::nominalFps(measured_);
    }
    std::deque<double> pts_;
    size_t since_ = 0;
    double quantum_ = 1e-6, fps_ = 0, measured_ = 0;
};

// Band-limited resampling of 48 kHz stereo s16 by a factor near 1: output frame k is the input at
// media position start + k x step (step = media seconds per output second, the clock factor). 32-tap
// Kaiser-windowed sinc (beta 8.6, cutoff 0.95 of Nyquist), 256 phases with linear interpolation
// between them (error under -90 dB below 16 kHz); about 3 M multiply-adds a second. Centred kernel:
// no media delay. A jump of more than 2 ms in the input's media time starts over (as TimeStretch).
class LockResampler {
public:
    static constexpr int rate48k = 48000, channels = 2, half = 16, taps = 2 * half, phases = 256;
    LockResampler()
    {
        constexpr double beta = 8.6, cutoff = 0.95;
        auto bessel0 = [](double x) { double sum = 1, term = 1; for (int k = 1; k < 40; k++) { term *= (x / (2 * k)) * (x / (2 * k)); sum += term; } return sum; };
        const double norm = bessel0(beta);
        table_.resize(size_t(phases + 1) * taps);
        for (int p = 0; p <= phases; p++) {
            const double frac = double(p) / phases;
            double sum = 0;
            for (int k = 0; k < taps; k++) {
                const double t = double(k - half + 1) - frac;   // tap position - output position, in input frames
                const double x = t / half;
                const double w = std::fabs(x) >= 1 ? 0 : bessel0(beta * std::sqrt(1 - x * x)) / norm;
                const double a = M_PI * cutoff * t;
                const double h = cutoff * (std::fabs(a) < 1e-12 ? 1 : std::sin(a) / a) * w;
                table_[size_t(p) * taps + k] = float(h); sum += h;
            }
            for (int k = 0; k < taps; k++) table_[size_t(p) * taps + k] = float(table_[size_t(p) * taps + k] / sum);   // unity DC gain
        }
        reset();
    }
    void reset() { in_.clear(); base_ = 0; have_ = false; ended_ = false; ipos_ = 0; frac_ = 0; media0_ = 0; }
    void setStep(double step) { if (std::isfinite(step) && step > 0.5 && step < 2) step_ = step; }
    double step() const { return step_; }
    bool active() const { return have_; }
    // `history` (half frames, interleaved, the input just before `media`): no ramp from silence when
    // the resampler takes over from a pass-through.
    void seed(const int16_t* history, size_t frames, double media)
    {
        reset();
        have_ = true; media0_ = media; base_ = -half; ipos_ = 0; frac_ = 0;
        in_.assign(size_t(half) * channels, 0.0f);
        const size_t n = std::min<size_t>(frames, half);
        for (size_t i = 0; i < n * channels; i++) in_[(half - n) * channels + i] = float(history[i]);
    }
    void push(const int16_t* pcm, size_t frames, double media)
    {
        if (!frames) return;
        if (have_ && (ended_ || std::fabs(media - mediaAt(endFrame())) > 0.002)) reset();
        if (!have_) seed(nullptr, 0, media);
        const size_t at = in_.size();
        in_.resize(at + frames * channels);
        for (size_t i = 0; i < frames * channels; i++) in_[at + i] = float(pcm[i]);
    }
    // The input ended: the last frames come out (padded with silence).
    void endOfStream() { if (have_ && !ended_) { ended_ = true; in_.resize(in_.size() + size_t(half) * channels, 0.0f); } }
    bool ended() const { return ended_; }
    bool canProduce() const { return have_ && ipos_ + half < endFrame(); }
    size_t backlogFrames() const { return have_ ? size_t(std::max<int64_t>(0, endFrame() - ipos_)) : 0; }
    double nextInputMedia() const { return have_ ? mediaAt(endFrame()) : NAN; }
    // Up to maxFrames output frames from media `media` at `speed` (= step); 0 when more input is needed.
    size_t pull(int16_t* out, size_t maxFrames, double& media, double& speed)
    {
        if (!have_) return 0;
        media = media0_ + (double(ipos_) + frac_) / rate48k;
        speed = step_;
        size_t n = 0;
        while (n < maxFrames && ipos_ + half < endFrame()) {
            const double p = frac_ * phases;
            int pi = int(p); if (pi >= phases) pi = phases - 1;
            const float t = float(p - pi);
            const float* h0 = &table_[size_t(pi) * taps];
            const float* h1 = h0 + taps;
            const float* x = &in_[size_t(ipos_ - half + 1 - base_) * channels];
            float l = 0, r = 0;
            for (int k = 0; k < taps; k++) {
                const float c = h0[k] + t * (h1[k] - h0[k]);
                l += c * x[2 * k]; r += c * x[2 * k + 1];
            }
            out[2 * n] = OmniMedia::Rate::TimeStretch::clip(l);
            out[2 * n + 1] = OmniMedia::Rate::TimeStretch::clip(r);
            n++;
            frac_ += step_;
            const double whole = std::floor(frac_);
            ipos_ += int64_t(whole); frac_ -= whole;
        }
        const int64_t keep = ipos_ - half;   // the oldest frame still needed
        if (keep - base_ > 8192) { in_.erase(in_.begin(), in_.begin() + std::ptrdiff_t((keep - base_) * channels)); base_ = keep; }
        return n;
    }
private:
    double mediaAt(int64_t frame) const { return media0_ + double(frame) / rate48k; }
    int64_t endFrame() const { return base_ + int64_t(in_.size() / channels); }
    std::vector<float> table_;
    std::vector<float> in_;   // interleaved input from frame base_ on (frame 0 = media0_)
    int64_t base_ = 0, ipos_ = 0;
    double frac_ = 0, media0_ = 0, step_ = 1;
    bool have_ = false, ended_ = false;
};

// RateAudio (playbackRate, pitch kept) + the display lock. rate(): the page's rate. At rate 1 the
// stretcher passes the audio through and LockResampler applies the lock (once engaged it stays on,
// at step 1 when the lock goes back to 1: no switch artefact); at other rates the stretcher runs at
// rate x lock. Same interface as RateAudio for the players.
class ClockAudio {
public:
    void reset() { rate_.reset(); res_.reset(); haveTail_ = false; ended_ = false; }
    double rate() const { return user_; }
    double lock() const { return lock_; }
    void push(const int16_t* pcm, size_t frames, double mediaStart) { if (frames) ended_ = false; rate_.push(pcm, frames, mediaStart); }
    void endOfStream() { rate_.endOfStream(); ended_ = true; }
    size_t backlogFrames() const { return rate_.backlogFrames() + res_.backlogFrames(); }
    bool idle() const { return rate_.idle() && !res_.canProduce(); }
    bool setRate(double rate, double from)
    {
        user_ = rate; res_.reset(); haveTail_ = false;
        return rate_.setRate(inner(), from);
    }
    void setRateNoRefeed(double rate) { user_ = rate; rate_.setRateNoRefeed(inner()); }
    // A new clock factor for what comes next (what is queued keeps its speed: the ring's runs say it).
    void setLock(double lock)
    {
        lock_ = std::isfinite(lock) && lock > 0.9 && lock < 1.1 ? lock : 1;
        res_.setStep(lock_);
        if (user_ != 1) rate_.setRateNoRefeed(inner());
    }
    size_t pull(int16_t* out, size_t maxFrames, double& mediaStart, double& speed)
    {
        if (!maxFrames) return 0;
        const bool resample = user_ == 1 && (lock_ != 1 || res_.active());
        if (!resample) {
            const size_t n = rate_.pull(out, maxFrames, mediaStart, speed);
            keepTail(out, n, mediaStart, speed);
            return n;
        }
        if (!res_.active() && haveTail_) {
            // Taking over from the pass-through: the last frames it gave are the history (push()
            // starts over from silence when the next input does not continue them).
            res_.seed(tail_, size_t(tailFrames_), tailEnd_);
        }
        haveTail_ = false;
        const size_t want = size_t(std::ceil(double(maxFrames) * res_.step())) + LockResampler::half + 2;
        int16_t chunk[2048 * 2];
        for (int guard = 0; guard < 64 && res_.backlogFrames() < want; guard++) {
            double m = 0, s = 1;
            const size_t n = rate_.pull(chunk, std::min<size_t>({ size_t(2048), maxFrames, want - res_.backlogFrames() + 512 }), m, s);
            if (!n) break;
            if (s != 1) {   // a stretched chunk (finishing a stretch, rate 1 set without a refeed): out as it is
                res_.reset();
                std::copy(chunk, chunk + n * 2, out);
                mediaStart = m; speed = s;
                return n;   // n <= maxFrames (asked for at most that)
            }
            res_.push(chunk, n, m);
        }
        if (ended_ && rate_.idle() && !res_.ended()) res_.endOfStream();
        return res_.pull(out, maxFrames, mediaStart, speed);
    }
private:
    double inner() const { return user_ == 1 ? 1 : std::clamp(user_ * lock_, OmniMedia::Rate::minimum, OmniMedia::Rate::maximum); }
    void keepTail(const int16_t* out, size_t n, double media, double speed)
    {
        if (!n) return;
        if (speed != 1) { haveTail_ = false; return; }
        constexpr size_t h = LockResampler::half;
        int16_t joined[2 * h * 2];
        size_t have = 0;
        if (haveTail_ && std::fabs(media - tailEnd_) <= 0.5 / LockResampler::rate48k) { std::copy(tail_, tail_ + tailFrames_ * 2, joined); have = size_t(tailFrames_); }
        const size_t k = std::min(n, h);
        std::copy(out + (n - k) * 2, out + n * 2, joined + have * 2);
        have += k;
        const size_t keep = std::min(have, h);
        std::copy(joined + (have - keep) * 2, joined + have * 2, tail_);
        tailFrames_ = int(keep);
        tailEnd_ = media + double(n) / LockResampler::rate48k;
        haveTail_ = true;
    }
    OmniMedia::Rate::RateAudio rate_;
    LockResampler res_;
    double user_ = 1, lock_ = 1;
    bool ended_ = false;
    int16_t tail_[LockResampler::half * 2] = {};
    int tailFrames_ = 0;
    double tailEnd_ = 0;
    bool haveTail_ = false;
};
}
