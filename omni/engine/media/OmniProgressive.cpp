// OMNI_PROGRESSIVE_V1: see OmniProgressive.h. SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniProgressive.h"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <unistd.h>

namespace OmniMedia::Progressive {

bool enabled()
{
    if (const char* env = getenv("OMNI_MEDIA_PROGRESSIVE")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/media-progressive-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}

bool parseContentRange(const std::string& value, int64_t& start, int64_t& end, int64_t& total)
{
    start = end = total = -1;
    long long a = 0, b = 0, t = 0;
    char unit[8] {};
    if (sscanf(value.c_str(), " %7[a-zA-Z] %lld-%lld/%lld", unit, &a, &b, &t) == 4 && !strcasecmp(unit, "bytes") && a >= 0 && b >= a && t > b) {
        start = a; end = b; total = t;
        return true;
    }
    return false;
}

// ---- RangeCache ---------------------------------------------------------------------------------
int64_t RangeCache::blockEnd(int64_t index) const
{
    const int64_t end = (index + 1) * int64_t(limits_.blockBytes);
    return total_ >= 0 ? std::min(end, total_) : end;
}

bool RangeCache::haveLocked(int64_t offset) const
{
    auto it = blocks_.find(offset / int64_t(limits_.blockBytes));
    return it != blocks_.end() && int64_t(it->second.filled) > offset - it->first * int64_t(limits_.blockBytes);
}

int64_t RangeCache::contiguousFrom(int64_t offset) const
{
    std::lock_guard<std::mutex> l(lock_);
    const int64_t bs = int64_t(limits_.blockBytes);
    int64_t at = offset;
    for (;;) {
        auto it = blocks_.find(at / bs);
        if (it == blocks_.end()) break;
        const int64_t filledEnd = it->first * bs + int64_t(it->second.filled);
        if (filledEnd <= at) break;
        at = filledEnd;
        if (filledEnd < blockEnd(it->first)) break;
    }
    return at - offset;
}

std::optional<RangeCache::Request> RangeCache::nextRequest()
{
    std::lock_guard<std::mutex> l(lock_);
    if (!ranges_ || inFlight_ || aborted_ || !error_.empty() || total_ <= 0) return std::nullopt;
    const int64_t bs = int64_t(limits_.blockBytes);
    // The first byte missing at or after `from`, block-aligned (or where a partial block stops).
    auto missing = [&](int64_t from, int64_t limit) -> int64_t {
        for (int64_t at = from; at < limit;) {
            const int64_t index = at / bs;
            auto it = blocks_.find(index);
            if (it == blocks_.end()) return index * bs;
            const int64_t filledEnd = index * bs + int64_t(it->second.filled);
            if (filledEnd < blockEnd(index)) return filledEnd;
            at = blockEnd(index);
        }
        return -1;
    };
    int64_t start = -1;
    if (waiting_ && wantOffset_ >= 0 && wantOffset_ < total_ && !haveLocked(wantOffset_)) start = missing(wantOffset_, total_);
    if (start < 0) start = missing(readPos_, std::min(total_, readPos_ + int64_t(limits_.readAheadBytes)));
    if (start < 0) return std::nullopt;
    int64_t length = std::min(int64_t(limits_.chunkBytes), total_ - start);
    // Stop where cached data starts again.
    auto next = blocks_.upper_bound(start / bs);
    if (next != blocks_.end() && next->second.filled) length = std::min(length, next->first * bs - start);
    if (length <= 0) return std::nullopt;
    inFlight_ = true; reqOffset_ = start; reqLength_ = length; reqReceived_ = 0;
    ++requests_;
    return Request { start, length };
}

bool RangeCache::shouldCancel() const
{
    std::lock_guard<std::mutex> l(lock_);
    if (!inFlight_ || !ranges_ || !waiting_ || wantOffset_ < 0 || haveLocked(wantOffset_)) return false;
    const int64_t next = reqOffset_ + reqReceived_, end = reqOffset_ + reqLength_;
    // The reader waits where this request is not going (or only after more than a block of other bytes).
    return wantOffset_ < next || wantOffset_ >= end || wantOffset_ - next > int64_t(limits_.blockBytes);
}

void RangeCache::cancelled()
{
    std::lock_guard<std::mutex> l(lock_);
    inFlight_ = false;
}

bool RangeCache::response(int status, int64_t rangeStart, int64_t total, int64_t contentLength, const std::string& validator, std::string& why)
{
    std::lock_guard<std::mutex> l(lock_);
    const bool first = total_ < 0 && !whole_ && !ranges_;
    if (first && status == 206) {
        if (total <= 0 || rangeStart != reqOffset_) { why = "unusable Content-Range"; error_ = why; cv_.notify_all(); return false; }
        ranges_ = true; total_ = total; validator_ = validator;
        return true;
    }
    if (first && status == 200) {
        if (contentLength > int64_t(limits_.wholeFileBytes)) {
            why = "the server ignores Range requests and the file is over " + std::to_string(limits_.wholeFileBytes >> 20) + " MiB";
            error_ = why; cv_.notify_all(); return false;
        }
        whole_ = true; total_ = contentLength >= 0 ? contentLength : -1;
        reqOffset_ = 0; reqReceived_ = 0; reqLength_ = contentLength >= 0 ? contentLength : int64_t(limits_.wholeFileBytes);
        return true;
    }
    if (ranges_ && status == 206 && total == total_ && rangeStart == reqOffset_ && (validator_.empty() || validator.empty() || validator == validator_)) return true;
    why = ranges_ && status == 206 && total == total_ && rangeStart == reqOffset_ ? "the file changed on the server (ETag)"
        : ranges_ && status == 206 ? "the server answered another range or size" : "the server stopped honouring Range";
    error_ = why; cv_.notify_all();
    return false;
}

void RangeCache::data(const uint8_t* bytes, size_t length)
{
    std::lock_guard<std::mutex> l(lock_);
    if (aborted_ || !error_.empty() || (!ranges_ && !whole_)) return;
    received_ += length;
    if (whole_ && reqReceived_ + int64_t(length) > int64_t(limits_.wholeFileBytes)) {
        error_ = "the server ignores Range requests and the file is over " + std::to_string(limits_.wholeFileBytes >> 20) + " MiB";
        cv_.notify_all(); return;
    }
    const int64_t bs = int64_t(limits_.blockBytes);
    int64_t at = reqOffset_ + reqReceived_;
    if (ranges_) length = size_t(std::min<int64_t>(int64_t(length), reqOffset_ + reqLength_ - at));   // never past the range
    reqReceived_ += int64_t(length);
    while (length) {
        const int64_t index = at / bs, within = at - index * bs;
        Block& b = blocks_[index];
        const int64_t capacity = whole_ && total_ < 0 ? bs : blockEnd(index) - index * bs;
        if (b.bytes.size() != size_t(capacity)) b.bytes.resize(size_t(capacity));
        const size_t n = size_t(std::min<int64_t>(int64_t(length), capacity - within));
        if (within == int64_t(b.filled)) { memcpy(b.bytes.data() + within, bytes, n); b.filled += n; cached_ += n; }
        else if (within > int64_t(b.filled)) { /* a gap: cannot happen (requests start where a block stops) */ }
        b.used = ++clock_;
        bytes += n; length -= n; at += int64_t(n);
    }
    peak_ = std::max(peak_, cached_);
    if (ranges_) evictLocked();
    cv_.notify_all();
}

void RangeCache::evictLocked()
{
    const int64_t bs = int64_t(limits_.blockBytes);
    const int64_t writing = (reqOffset_ + reqReceived_) / bs, reading = readPos_ / bs;
    while (cached_ > limits_.cacheBytes) {
        auto victim = blocks_.end();
        for (auto it = blocks_.begin(); it != blocks_.end(); ++it) {
            if (it->first == writing || it->first == reading) continue;
            if (victim == blocks_.end() || it->second.used < victim->second.used) victim = it;
        }
        if (victim == blocks_.end()) break;
        cached_ -= victim->second.filled;
        blocks_.erase(victim);
    }
}

void RangeCache::finished()
{
    std::lock_guard<std::mutex> l(lock_);
    inFlight_ = false;
    if (whole_) { wholeDone_ = true; if (total_ < 0) total_ = reqReceived_; }
    cv_.notify_all();
}

void RangeCache::fail(const std::string& why)
{
    std::lock_guard<std::mutex> l(lock_);
    if (error_.empty()) error_ = why;
    inFlight_ = false;
    cv_.notify_all();
}

void RangeCache::abort()
{
    std::lock_guard<std::mutex> l(lock_);
    aborted_ = true;
    cv_.notify_all();
}

int RangeCache::read(int64_t offset, uint8_t* buffer, int length, double& waitedSeconds)
{
    if (length <= 0 || offset < 0) return -1;
    std::unique_lock<std::mutex> l(lock_);
    const int64_t bs = int64_t(limits_.blockBytes);
    for (;;) {
        if (aborted_ || !error_.empty()) { waiting_ = false; return -1; }
        if (total_ >= 0 && offset >= total_) { waiting_ = false; return 0; }
        if (haveLocked(offset)) {
            int copied = 0;
            int64_t at = offset;
            while (copied < length) {
                auto it = blocks_.find(at / bs);
                if (it == blocks_.end()) break;
                const int64_t within = at - it->first * bs;
                if (within >= int64_t(it->second.filled)) break;
                const int n = int(std::min<int64_t>(length - copied, int64_t(it->second.filled) - within));
                memcpy(buffer + copied, it->second.bytes.data() + within, size_t(n));
                it->second.used = ++clock_;
                copied += n; at += n;
            }
            waiting_ = false;
            readPos_ = at;
            return copied;
        }
        if (whole_ && wholeDone_) { waiting_ = false; return 0; }
        waiting_ = true; wantOffset_ = offset; readPos_ = offset;
        const auto start = std::chrono::steady_clock::now();
        cv_.wait_for(l, std::chrono::milliseconds(100));
        waitedSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    }
}

// ---- Pipeline -----------------------------------------------------------------------------------
Pipeline::Pipeline(std::shared_ptr<RangeCache> cache, Limits limits) : cache_(std::move(cache)), limits_(limits) { }

Pipeline::~Pipeline()
{
    stop_ = true;
    cache_->abort();
    { std::lock_guard<std::mutex> l(lock_); cv_.notify_all(); }
    if (thread_.joinable()) thread_.join();
}

void Pipeline::start()
{
    thread_ = std::thread([this] { run(); });
}

bool Pipeline::frontTime(double& seconds) const
{
    std::lock_guard<std::mutex> l(lock_);
    if (frames_.empty() || seekPending_) return false;
    seconds = frames_.front().seconds;
    return true;
}

bool Pipeline::popFrame(VideoFrame& out)
{
    std::lock_guard<std::mutex> l(lock_);
    if (frames_.empty() || seekPending_) return false;
    out = std::move(frames_.front());
    frames_.pop_front();
    cv_.notify_all();
    return true;
}

bool Pipeline::popPacket(DemuxPacket& out)   // OMNI_PROGRESSIVE_HOLEPUNCH_V1
{
    std::lock_guard<std::mutex> l(lock_);
    if (packets_.empty() || seekPending_) return false;
    out = std::move(packets_.front());
    packets_.pop_front();
    packetBytes_ -= std::min(packetBytes_, out.bytes.size());
    cv_.notify_all();
    return true;
}

bool Pipeline::takePcm(std::vector<int16_t>& out, double& mediaStart)
{
    std::lock_guard<std::mutex> l(lock_);
    if (pcm_.empty() || seekPending_) return false;
    out.swap(pcm_); pcm_.clear();
    mediaStart = pcmMedia_;
    cv_.notify_all();
    return true;
}

void Pipeline::seek(double seconds)
{
    std::lock_guard<std::mutex> l(lock_);
    seekPending_ = true; seekTo_ = seconds;
    frames_.clear(); pcm_.clear();
    packets_.clear(); packetBytes_ = 0; // OMNI_PROGRESSIVE_HOLEPUNCH_V1
    decoderEnded_ = false;
    cv_.notify_all();
}

bool Pipeline::ended() const
{
    std::lock_guard<std::mutex> l(lock_);
    return decoderEnded_ && frames_.empty() && pcm_.empty() && packets_.empty() && !seekPending_; // OMNI_PROGRESSIVE_HOLEPUNCH_V1: + packets
}

void Pipeline::run()
{
    VideoDecoder decoder;
    if (!(wantPackets_ ? decoder.openSourcePackets(cache_) : decoder.openSource(cache_))) { // OMNI_PROGRESSIVE_HOLEPUNCH_V1
        std::lock_guard<std::mutex> l(lock_);
        error_ = cache_->error().empty() ? decoder.error() : cache_->error();
        state_ = State::Failed;
        return;
    }
    duration_ = decoder.duration();
    hasAudio_ = decoder.hasAudio();
    if (decoder.packetMode()) { std::lock_guard<std::mutex> l(lock_); track_ = decoder.videoTrack(); packetMode_ = true; } // OMNI_PROGRESSIVE_HOLEPUNCH_V1
    const bool packets = packetMode_.load();
    state_ = State::Ready;
    VideoFrame frame;
    for (;;) {
        double seekTo = -1;
        {
            std::unique_lock<std::mutex> l(lock_);
            auto room = [&] {
                if (packets) return packets_.size() < limits_.maxPackets && packetBytes_ < limits_.maxPacketBytes && double(pcm_.size() / 2) / 48000 < limits_.maxPcmSeconds; // OMNI_PROGRESSIVE_HOLEPUNCH_V1
                return frames_.size() < limits_.maxFrames && double(pcm_.size() / 2) / 48000 < limits_.maxPcmSeconds;
            };
            cv_.wait(l, [&] { return stop_ || seekPending_ || (!decoderEnded_ && room()); });
            if (stop_) return;
            if (seekPending_) seekTo = seekTo_;
        }
        if (seekTo >= 0) {
            const bool ok = decoder.seek(std::min(seekTo, std::max(0.0, decoder.duration())));
            std::lock_guard<std::mutex> l(lock_);
            if (stop_) return;
            if (seekTo_ != seekTo) continue;   // another seek came meanwhile
            seekPending_ = false;
            frames_.clear(); pcm_.clear(); pcmNext_ = seekTo;
            packets_.clear(); packetBytes_ = 0; // OMNI_PROGRESSIVE_HOLEPUNCH_V1
            decoderEnded_ = !ok && seekTo >= decoder.duration();
            if (!ok && !decoderEnded_) { error_ = cache_->error().empty() ? "seek failed" : cache_->error(); state_ = State::Failed; return; }
            continue;
        }
        DemuxPacket packet; // OMNI_PROGRESSIVE_HOLEPUNCH_V1
        const auto result = packets ? decoder.nextPacket(packet) : decoder.next(frame);
        auto pcm = decoder.takeAudio();
        std::lock_guard<std::mutex> l(lock_);
        if (stop_) return;
        if (seekPending_) continue;   // a seek came while decoding: this output is from before it
        if (!pcm.empty()) {
            if (pcm_.empty()) pcmMedia_ = pcmNext_;
            pcm_.insert(pcm_.end(), pcm.begin(), pcm.end());
            pcmNext_ += double(pcm.size() / 2) / 48000;
        }
        if (result == VideoDecoder::Result::Frame && packets) { packetBytes_ += packet.bytes.size(); packets_.push_back(std::move(packet)); } // OMNI_PROGRESSIVE_HOLEPUNCH_V1
        else if (result == VideoDecoder::Result::Frame) frames_.push_back(std::move(frame));
        else if (result == VideoDecoder::Result::End) decoderEnded_ = true;
        else if (result == VideoDecoder::Result::Error) {
            error_ = !cache_->error().empty() ? cache_->error() : decoder.error();
            state_ = State::Failed;
            return;
        }
        size_t queued = pcm_.size() * sizeof(int16_t) + packetBytes_; // OMNI_PROGRESSIVE_HOLEPUNCH_V1: + packets
        for (auto& f : frames_) queued += f.rgba.size();
        peakQueued_ = std::max(peakQueued_, queued);
    }
}

}
