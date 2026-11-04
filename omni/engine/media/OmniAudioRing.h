// OMNI_HOLEPUNCH_V5: the player's PCM output ring. SPDX-License-Identifier: GPL-3.0-or-later
//
// Why: the WebProcess main thread of a youtube.com watch page is busy for 1-2.5 s at a time
// (YouTube's script runs in JSC's interpreter there). V4 fed SDL's audio queue only 0.15 s
// ahead of the playhead, from the player tick on that thread, so every such stall ran the
// queue dry. Here the tick writes up to ~3 s ahead into this ring and SDL's audio thread
// (the device callback) plays from it on its own: a stall of up to ~3 s is not heard.
//
// One producer (the player, main thread) and one consumer (the callback). Lock-free indices;
// clear() needs the consumer stopped (SDL_LockAudioDevice). Interleaved stereo s16, 48 kHz.
// The volume is applied as the samples are played, so it takes effect at once (V4 applied it
// when queueing, 0.15 s ahead; with 3 s queued that would lag by seconds).
// Pure C++ (no SDL), tested on the host by player-sim-test.
//
// OMNI_AUDIO_RELAY_V1: the state the two sides share (indices, gain, counters) lives in one
// Shared block, so a ring can also sit in shared memory with its consumer in another process:
// the UI process's audio relay (OmniAudioRelay.h) mixes the WebProcess players' rings in its
// own SDL callback. Then clear() is a request the consumer carries out at its next callback
// (the producer counts from the requested point at once), the consumer plays the ring only
// while `playing` is set (SDL_PauseAudioDevice's part), and it publishes its device buffer
// (deviceFrames) and a heartbeat (consumerBeatUs). CLOCK_MONOTONIC (steady_clock) is the same
// clock in both processes, so heard() works unchanged on the producer's side.
#pragma once
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <memory>
#include <new>
#include <vector>

namespace OmniMedia {

class AudioRing {
public:
    static constexpr int rate = 48000, channels = 2;
    // OMNI_AUDIO_RELAY_V1: everything both sides touch. Lock-free atomics only (address-free on
    // x86-64), so the block works in memory shared between processes.
    struct Shared {
        static constexpr uint32_t magicValue = 0x4f4d5247;   // "OMRG"
        static constexpr uint32_t versionValue = 1;
        uint32_t magic = magicValue, version = versionValue, capacityFrames = 0, headerBytes = 0;
        std::atomic<uint64_t> written { 0 }, read { 0 };
        std::atomic<int64_t> lastReadUs { 0 };
        std::atomic<float> gain { 1.0f };
        std::atomic<uint32_t> armed { 0 }, ending { 0 }, starving { 0 };
        std::atomic<uint64_t> underruns { 0 }, underrunFrames { 0 }, callbackBytes { 0 }, callbackCalls { 0 };
        std::atomic<int32_t> outPeak { 0 };
        std::atomic<uint32_t> playing { 0 };                // producer: play this ring (remote consumer)
        std::atomic<uint64_t> clearTarget { 0 }, clearSeq { 0 }, clearAck { 0 };   // clear() requests
        std::atomic<int64_t> consumerBeatUs { 0 };          // consumer: last callback (its device runs)
        std::atomic<uint32_t> deviceFrames { 0 };           // consumer: its device's buffer, frames
    };
    static constexpr size_t headerBytes() { return (sizeof(Shared) + 255) / 256 * 256; }
    static constexpr size_t sharedBytes(size_t frames) { return headerBytes() + frames * channels * sizeof(int16_t); }
    // A Shared block + ring at `memory` (sharedBytes(frames), zeroed or not): the creator's side.
    static Shared* initShared(void* memory, size_t frames)
    {
        auto* shared = new (memory) Shared();
        shared->capacityFrames = uint32_t(frames); shared->headerBytes = uint32_t(headerBytes());
        memset(static_cast<uint8_t*>(memory) + headerBytes(), 0, frames * channels * sizeof(int16_t));
        return shared;
    }
    // Checks a mapped block before a view is made on it.
    static bool validShared(const void* memory, size_t bytes)
    {
        if (bytes < headerBytes()) return false;
        const auto* shared = static_cast<const Shared*>(memory);
        return shared->magic == Shared::magicValue && shared->version == Shared::versionValue && shared->headerBytes == headerBytes()
            && shared->capacityFrames && sharedBytes(shared->capacityFrames) <= bytes;
    }
    explicit AudioRing(size_t frames) : own_(new Shared()), buffer_(frames * channels), s_(own_.get()), data_(buffer_.data()), capacity_(frames)
    {
        own_->capacityFrames = uint32_t(frames); own_->headerBytes = uint32_t(headerBytes());
    }
    // OMNI_AUDIO_RELAY_V1: a view of a block made by initShared (memory stays the caller's).
    // remoteConsumer: the consumer runs in another process (clear() becomes a request).
    AudioRing(void* memory, bool remoteConsumer)
        : s_(static_cast<Shared*>(memory)), data_(reinterpret_cast<int16_t*>(static_cast<uint8_t*>(memory) + headerBytes())),
          capacity_(static_cast<Shared*>(memory)->capacityFrames), remote_(remoteConsumer) { }
    AudioRing(const AudioRing&) = delete;
    AudioRing& operator=(const AudioRing&) = delete;
    Shared& shared() { return *s_; }

    // ---- producer (player thread) ----
    size_t capacityFrames() const { return capacity_; }
    size_t fillFrames() const { return size_t(s_->written.load(std::memory_order_acquire) - effectiveRead()); }
    size_t roomFrames() const { return capacity_ - std::min(capacity_, fillFrames()); }
    // All or nothing: false (nothing written) when the ring lacks room. mediaStart: seconds of
    // the first frame (the ring keeps where each contiguous run of media starts).
    // OMNI_PLAYBACK_RATE_V1: speed = media seconds per second of these frames (time-stretched
    // audio at playbackRate: OmniPlaybackRate.h); a new run starts where it changes.
    bool write(const int16_t* pcm, size_t frames, double mediaStart, double speed = 1)
    {
        if (!frames) return true;
        if (frames > roomFrames()) return false;
        const uint64_t w = s_->written.load(std::memory_order_relaxed);
        if (runs_.empty() || std::fabs(mediaStart - endMedia_) > 0.5 / rate || runs_.back().speed != speed) runs_.push_back({ w, mediaStart, speed });
        size_t at = size_t(w % capacity_), left = frames;
        const int16_t* src = pcm;
        while (left) {
            const size_t n = std::min(left, capacity_ - at);
            memcpy(&data_[at * channels], src, n * channels * sizeof(int16_t));
            src += n * channels; left -= n; at = (at + n) % capacity_;
        }
        endMedia_ = mediaStart + double(frames) / rate * speed;
        for (size_t i = 0; i < frames * channels; i++) inPeak_ = std::max(inPeak_, std::abs(int(pcm[i])));   // OMNI_HOLEPUNCH_V5_REV3
        s_->written.store(w + frames, std::memory_order_release);
        return true;
    }
    bool hasMedia() const { return !runs_.empty(); }
    double endMedia() const { return endMedia_; }   // media time just after the last frame written
    // Media time being heard now: the frame the device read last, minus what the device holds
    // (deviceFrames, e.g. SDL's buffer), plus the time since that read (at most deviceFrames).
    // NaN when nothing was written since the last clear(), or before the device read anything.
    double heard(double deviceFrames, bool advancing)
    {
        if (clearPending()) return NAN;   // OMNI_AUDIO_RELAY_V1: the consumer has not carried out a clear() yet
        const uint64_t read = s_->read.load(std::memory_order_acquire);
        const int64_t lastUs = s_->lastReadUs.load(std::memory_order_acquire);
        if (runs_.empty() || !lastUs || read <= runs_.front().frame) return NAN;
        while (runs_.size() > 1 && runs_[1].frame <= read) runs_.pop_front();
        double since = advancing ? double(nowUs() - lastUs) / 1e6 : 0;
        since = std::clamp(since, 0.0, deviceFrames / rate);
        return runs_.front().media + ((double(read - runs_.front().frame) - deviceFrames) / rate + since) * runs_.front().speed; // OMNI_PLAYBACK_RATE_V1
    }
    // Consumer stopped (SDL_LockAudioDevice, or the device closed/paused before its thread ran).
    // OMNI_AUDIO_RELAY_V1: with a remote consumer, a request it carries out at its next callback;
    // this side counts from the requested point at once.
    void clear()
    {
        runs_.clear(); endMedia_ = 0;
        if (remote_) {
            s_->clearTarget.store(s_->written.load(std::memory_order_relaxed), std::memory_order_release);
            s_->clearSeq.fetch_add(1, std::memory_order_acq_rel);
            return;
        }
        s_->read.store(s_->written.load(std::memory_order_relaxed), std::memory_order_release);
        s_->lastReadUs.store(0, std::memory_order_release);
        s_->armed.store(0, std::memory_order_release);
        s_->starving.store(0, std::memory_order_relaxed);   // the consumer is stopped (see above)
    }
    void setGain(float gain) { s_->gain.store(std::isfinite(gain) ? std::clamp(gain, 0.0f, 1.0f) : 0.0f, std::memory_order_relaxed); }
    // The device may starve from here on without it counting as an underrun (end of the stream).
    void setEnding(bool ending) { s_->ending.store(ending, std::memory_order_release); }
    uint64_t underruns() const { return s_->underruns.load(std::memory_order_acquire); }
    uint64_t underrunFrames() const { return s_->underrunFrames.load(std::memory_order_acquire); }
    // OMNI_AUDIO_RELAY_V1: a remote consumer plays this ring only while it is set.
    void setPlaying(bool playing) { s_->playing.store(playing, std::memory_order_release); }
    bool playingSet() const { return s_->playing.load(std::memory_order_acquire) != 0; }

    // ---- OMNI_HOLEPUNCH_V5_REV3: proof of what the device was given ----
    // What the callback handed the device (bytes, calls) and the largest |sample| in it and in what
    // was written, since the last take (0: digital silence). The callback's own peak is after the gain.
    uint64_t callbackBytes() const { return s_->callbackBytes.load(std::memory_order_acquire); }
    uint64_t callbackCalls() const { return s_->callbackCalls.load(std::memory_order_acquire); }
    int takeOutPeak() { return s_->outPeak.exchange(0, std::memory_order_acq_rel); }
    int takeInPeak() { const int p = inPeak_; inPeak_ = 0; return p; }   // producer only
    float gain() const { return s_->gain.load(std::memory_order_relaxed); }
    // The device callback (SDL_AudioCallback's signature without SDL: userdata = the ring, len in
    // bytes of interleaved stereo s16). The device must be opened with exactly that format.
    static void deviceCallback(void* ring, uint8_t* stream, int len)
    {
        auto* self = static_cast<AudioRing*>(ring);
        const size_t bytes = size_t(len > 0 ? len : 0);
        self->read(reinterpret_cast<int16_t*>(stream), bytes / (channels * sizeof(int16_t)));
        if (bytes % (channels * sizeof(int16_t))) memset(stream + bytes - bytes % (channels * sizeof(int16_t)), 0, bytes % (channels * sizeof(int16_t)));
        const int16_t* out = reinterpret_cast<const int16_t*>(stream);
        int peak = 0;
        for (size_t i = 0; i < bytes / sizeof(int16_t); i++) peak = std::max(peak, std::abs(int(out[i])));
        if (peak > self->s_->outPeak.load(std::memory_order_relaxed)) self->s_->outPeak.store(peak, std::memory_order_release);   // one consumer
        self->s_->callbackBytes.fetch_add(bytes, std::memory_order_acq_rel);
        self->s_->callbackCalls.fetch_add(1, std::memory_order_acq_rel);
    }

    // ---- consumer (device callback) ----
    // Fills `frames` frames; silence where the ring has none. Running dry after data played (and
    // before setEnding) counts as one underrun until data plays again (OMNI_HOLEPUNCH_V5_REV2: per
    // episode; rev 1 counted every short callback); underrunFrames counts the silence.
    void read(int16_t* out, size_t frames)
    {
        applyClear();   // OMNI_AUDIO_RELAY_V1
        const uint64_t r = s_->read.load(std::memory_order_relaxed);
        const uint64_t w = s_->written.load(std::memory_order_acquire);
        // OMNI_AUDIO_RELAY_V1: the producer is another process: never trust its index further than
        // the ring holds (a broken writer can only make this ring silent, not read out of bounds).
        const uint64_t avail = w >= r ? std::min<uint64_t>(w - r, capacity_) : 0;
        const size_t n = size_t(std::min<uint64_t>(avail, frames));
        float gain = s_->gain.load(std::memory_order_relaxed);
        if (!(gain >= 0.0f && gain <= 1.0f)) gain = 0;   // OMNI_AUDIO_RELAY_V1: written by another process
        size_t at = size_t(r % capacity_), done = 0;
        while (done < n) {
            const size_t k = std::min(n - done, capacity_ - at);
            const int16_t* src = &data_[at * channels];
            int16_t* dst = out + done * channels;
            if (gain == 1.0f) memcpy(dst, src, k * channels * sizeof(int16_t));
            else for (size_t i = 0; i < k * channels; i++) dst[i] = int16_t(src[i] * gain);
            done += k; at = (at + k) % capacity_;
        }
        if (n < frames) {
            memset(out + n * channels, 0, (frames - n) * channels * sizeof(int16_t));
            if (s_->armed.load(std::memory_order_relaxed) && !s_->ending.load(std::memory_order_acquire)) {
                if (!s_->starving.load(std::memory_order_relaxed)) s_->underruns.fetch_add(1, std::memory_order_acq_rel);
                s_->starving.store(1, std::memory_order_relaxed);
                s_->underrunFrames.fetch_add(frames - n, std::memory_order_acq_rel);
            }
        } else s_->starving.store(0, std::memory_order_relaxed);
        if (n) s_->armed.store(1, std::memory_order_relaxed);
        s_->read.store(r + n, std::memory_order_release);
        s_->lastReadUs.store(nowUs(), std::memory_order_release);
    }
    // OMNI_AUDIO_RELAY_V1: a remote consumer carries out the producer's clear() requests (also while
    // the ring is not played) and says it is alive.
    void applyClear()
    {
        const uint64_t seq = s_->clearSeq.load(std::memory_order_acquire);
        if (seq == s_->clearAck.load(std::memory_order_relaxed)) return;
        const uint64_t target = s_->clearTarget.load(std::memory_order_acquire);
        if (target <= s_->written.load(std::memory_order_acquire)) s_->read.store(target, std::memory_order_release);
        s_->lastReadUs.store(0, std::memory_order_release);
        s_->armed.store(0, std::memory_order_relaxed);
        s_->starving.store(0, std::memory_order_relaxed);
        s_->clearAck.store(seq, std::memory_order_release);
    }
    void consumerBeat(uint32_t deviceFrames)
    {
        s_->deviceFrames.store(deviceFrames, std::memory_order_relaxed);
        s_->consumerBeatUs.store(nowUs(), std::memory_order_release);
    }
    // Producer: the consumer called back within maxAgeUs (its device runs).
    bool consumerAlive(int64_t maxAgeUs) const
    {
        const int64_t beat = s_->consumerBeatUs.load(std::memory_order_acquire);
        return beat && nowUs() - beat <= maxAgeUs;
    }
    uint32_t consumerDeviceFrames() const { return s_->deviceFrames.load(std::memory_order_relaxed); }
    static int64_t nowUs() { return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }

private:
    bool clearPending() const { return s_->clearSeq.load(std::memory_order_acquire) != s_->clearAck.load(std::memory_order_acquire); }
    uint64_t effectiveRead() const   // OMNI_AUDIO_RELAY_V1: a requested clear counts at once
    {
        return clearPending() ? s_->clearTarget.load(std::memory_order_acquire) : s_->read.load(std::memory_order_acquire);
    }
    struct Run { uint64_t frame; double media; double speed = 1; };   // producer only (OMNI_PLAYBACK_RATE_V1: speed)
    std::unique_ptr<Shared> own_;     // OMNI_AUDIO_RELAY_V1: null for a view of shared memory
    std::vector<int16_t> buffer_;
    Shared* s_;
    int16_t* data_;
    const size_t capacity_;
    const bool remote_ = false;
    int inPeak_ = 0;   // producer only
    std::deque<Run> runs_;
    double endMedia_ = 0;
};

}
