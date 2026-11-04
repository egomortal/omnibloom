// OMNI_PROGRESSIVE_V1: progressive playback of large MP4/WebM files. SPDX-License-Identifier: GPL-3.0-or-later
//
// Why: the plain <video src="file.mp4"> player downloaded the whole file into memory first and
// refused anything over 32 MiB (OmniMedia::VideoDecoder::maxInputBytes): Google's 158 MB
// BigBuckBunny.mp4 failed with MEDIA_ERR_SRC_NOT_SUPPORTED after ~0.5 s (v90).
//
// What:
//   * RangeCache: the file as a bounded cache of 256 KiB blocks (16 MiB in all, least recently
//     used blocks go first), filled by HTTP range requests of 1 MiB, one at a time, through the
//     player's PlatformMediaResourceLoader (the element's loader: cookies, CORS mode, the network
//     process and content blocking apply as before). It reads ahead up to 6 MiB past the
//     decoder's read position; a read elsewhere (seek; moov at the end of the file) gets its own
//     request at once (the request in flight is cancelled when it does not cover it).
//     A server that ignores Range (200 with the whole body) gets today's behaviour: the whole
//     file in memory, at most 32 MiB.
//   * Pipeline: FFmpeg (OmniMedia::VideoDecoder over the cache) on its own thread, so a read that
//     waits for the network blocks only that thread; it queues up to 3 decoded frames and 2 s of
//     PCM for the player's main-thread tick. It starts as soon as the first response is in:
//     playback starts once the moov and the first samples are.
// Memory: cache 16 MiB + 3 frames (<= 1080p RGBA, 8.3 MB each) + 2 s of PCM + FFmpeg's index.
// OMNI_PROGRESSIVE_HOLEPUNCH_V1: packet mode (requestPackets): no frames; up to 240 video packets
// (24 MiB at most) for the player's hardware decoder instead.
// Kill switch of packet mode: /data/omni/progressive-holepunch-disabled.flag (the player's).
// Kill switch: /data/omni/media-progressive-disabled.flag (host: OMNI_MEDIA_PROGRESSIVE=0):
// the old whole-file player. Pure C++ + FFmpeg; tested on the host (progressive-test.cpp).
#pragma once
#include "OmniVideoDecoder.h"
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

namespace OmniMedia::Progressive {

bool enabled();

struct Limits {
    size_t blockBytes = 256 * 1024;
    size_t cacheBytes = 16 * 1024 * 1024;
    size_t chunkBytes = 1024 * 1024;        // one range request
    size_t readAheadBytes = 6 * 1024 * 1024;
    size_t wholeFileBytes = 32 * 1024 * 1024;   // no Range support: today's limit
    size_t maxFrames = 3;
    double maxPcmSeconds = 2;
    size_t maxPackets = 240;                    // OMNI_PROGRESSIVE_HOLEPUNCH_V1: packet mode
    size_t maxPacketBytes = 24 * 1024 * 1024;
};

// "bytes 0-1048575/158008374" -> start, total (-1 when "*" or malformed).
bool parseContentRange(const std::string& value, int64_t& start, int64_t& end, int64_t& total);

class RangeCache final : public ByteSource {
public:
    explicit RangeCache(Limits limits = { }) : limits_(limits) { }
    // ---- main thread ------------------------------------------------------------------------
    struct Request { int64_t offset = 0, length = 0; };
    // The first request (before anything is known): the first chunk; it is then in flight.
    Request firstRequest()
    {
        std::lock_guard<std::mutex> l(lock_);
        inFlight_ = true; reqOffset_ = 0; reqLength_ = int64_t(limits_.chunkBytes); reqReceived_ = 0; ++requests_;
        return { 0, reqLength_ };
    }
    // What to fetch next while nothing is in flight; nullopt: nothing needed now.
    std::optional<Request> nextRequest();
    // The request in flight no longer helps (the reader waits elsewhere): cancel it, then
    // call cancelled().
    bool shouldCancel() const;
    void cancelled();
    // The response to the request in flight. status 206: start/total from Content-Range;
    // 200: the whole file (contentLength -1 when unknown). False (why says it) when it cannot be
    // used: the cache then fails, readers get an error.
    bool response(int status, int64_t rangeStart, int64_t total, int64_t contentLength, const std::string& validator, std::string& why);
    void data(const uint8_t*, size_t);
    void finished();               // the request in flight completed (all its bytes came)
    void fail(const std::string& why);
    void abort();                  // stop: every read returns an error at once
    bool ranges() const { return ranges_; }
    bool whole() const { return whole_; }
    bool wholeComplete() const { std::lock_guard<std::mutex> l(lock_); return whole_ && wholeDone_; }
    bool known() const { return total_ >= 0 || whole_; }
    bool inFlight() const { std::lock_guard<std::mutex> l(lock_); return inFlight_; }
    bool readerWaiting() const { std::lock_guard<std::mutex> l(lock_); return waiting_; }
    std::string error() const { std::lock_guard<std::mutex> l(lock_); return error_; }
    // Stats.
    size_t cachedBytes() const { std::lock_guard<std::mutex> l(lock_); return cached_; }
    size_t peakCachedBytes() const { std::lock_guard<std::mutex> l(lock_); return peak_; }
    uint64_t requests() const { std::lock_guard<std::mutex> l(lock_); return requests_; }
    uint64_t receivedBytes() const { std::lock_guard<std::mutex> l(lock_); return received_; }
    int64_t readPosition() const { std::lock_guard<std::mutex> l(lock_); return readPos_; }
    int64_t contiguousFrom(int64_t offset) const;
    // ---- decoder thread (ByteSource) --------------------------------------------------------
    int64_t size() const final { std::lock_guard<std::mutex> l(lock_); return total_; }
    int read(int64_t offset, uint8_t* buffer, int length, double& waitedSeconds) final;

private:
    struct Block { std::vector<uint8_t> bytes; size_t filled = 0; uint64_t used = 0; };
    bool haveLocked(int64_t offset) const;
    void evictLocked();
    int64_t blockEnd(int64_t index) const;
    Limits limits_;
    mutable std::mutex lock_;
    std::condition_variable cv_;
    std::map<int64_t, Block> blocks_;     // block index -> bytes (filled from its start)
    int64_t total_ = -1;
    bool ranges_ = false, whole_ = false, wholeDone_ = false;
    std::string validator_;
    bool inFlight_ = false, waiting_ = false, aborted_ = false;
    int64_t reqOffset_ = 0, reqLength_ = 0, reqReceived_ = 0;
    int64_t readPos_ = 0, wantOffset_ = -1;
    size_t cached_ = 0, peak_ = 0;
    uint64_t clock_ = 0, requests_ = 0, received_ = 0;
    std::string error_;
};

// FFmpeg on its own thread over a RangeCache.
class Pipeline {
public:
    Pipeline(std::shared_ptr<RangeCache> cache, Limits limits = { });
    ~Pipeline();
    Pipeline(const Pipeline&) = delete;
    Pipeline& operator=(const Pipeline&) = delete;
    // OMNI_PROGRESSIVE_HOLEPUNCH_V1: before start(): open with VideoDecoder::openSourcePackets.
    void requestPackets(bool on) { wantPackets_ = on; }
    void start();
    enum class State { Opening, Ready, Failed };
    State state() const { return state_.load(); }
    std::string error() const { std::lock_guard<std::mutex> l(lock_); return error_; }
    double duration() const { return duration_.load(); }
    bool hasAudio() const { return hasAudio_.load(); }
    // Frames in presentation order (after the last seek).
    bool frontTime(double& seconds) const;
    bool popFrame(VideoFrame& out);
    // OMNI_PROGRESSIVE_HOLEPUNCH_V1: valid once Ready. Packet mode: video packets in decode order
    // (after the last seek) instead of frames.
    bool packetMode() const { return packetMode_.load(); }
    DemuxTrack videoTrack() const { std::lock_guard<std::mutex> l(lock_); return track_; }
    bool popPacket(DemuxPacket& out);
    size_t queuedPackets() const { std::lock_guard<std::mutex> l(lock_); return seekPending_ ? 0 : packets_.size(); }
    bool demuxEnded() const { std::lock_guard<std::mutex> l(lock_); return decoderEnded_ && packets_.empty() && !seekPending_; }
    size_t queuedFrames() const { std::lock_guard<std::mutex> l(lock_); return frames_.size(); }
    // All queued PCM (48 kHz stereo s16) and the media time of its first frame.
    bool takePcm(std::vector<int16_t>& out, double& mediaStart);
    void seek(double seconds);     // asynchronous; frames/PCM from before it are dropped
    bool seeking() const { std::lock_guard<std::mutex> l(lock_); return seekPending_; }
    bool ended() const;            // the decoder reached the end and every frame was taken
    size_t peakQueuedBytes() const { std::lock_guard<std::mutex> l(lock_); return peakQueued_; }
private:
    void run();
    std::shared_ptr<RangeCache> cache_;
    Limits limits_;
    std::thread thread_;
    mutable std::mutex lock_;
    std::condition_variable cv_;
    std::atomic<State> state_ { State::Opening };
    std::atomic<double> duration_ { 0 };
    std::atomic<bool> hasAudio_ { false }, stop_ { false };
    std::string error_;
    std::deque<VideoFrame> frames_;
    bool wantPackets_ = false;                      // OMNI_PROGRESSIVE_HOLEPUNCH_V1
    std::atomic<bool> packetMode_ { false };
    DemuxTrack track_;
    std::deque<DemuxPacket> packets_;
    size_t packetBytes_ = 0;
    std::vector<int16_t> pcm_;
    double pcmMedia_ = 0, pcmNext_ = 0;
    bool decoderEnded_ = false, seekPending_ = false;
    double seekTo_ = 0;
    size_t peakQueued_ = 0;
};

}
