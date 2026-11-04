// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniHwClient.h"
#include "OmniHwPlatform.h"
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <atomic> // OMNI_HOLEPUNCH_V3
#include <algorithm> // OMNI_HOLEPUNCH_V4
#include <mutex>
#include <csignal>
#include <dlfcn.h>
#include <pthread.h>
#ifndef OMNI_HW_NO_SWSCALE
extern "C" {
#include <libswscale/swscale.h>
}
#endif

namespace OmniMedia::Hw {
using Wire::Message;
using Wire::Type;

namespace {
// pts * from / to, rounded to nearest (ties away from zero), as FFmpeg's
// AV_ROUND_NEAR_INF does; INT64_MIN on overflow.
int64_t rescale(int64_t v, int fromNum, int fromDen, int toNum, int toDen)
{
    __int128 n = __int128(v) * fromNum * toDen, d = __int128(fromDen) * toNum;
    if (d <= 0) return INT64_MIN;
    __int128 q = (n >= 0 ? n + d / 2 : n - d / 2) / d;
    return (q > INT64_MAX || q < INT64_MIN + 1) ? INT64_MIN : int64_t(q);
}
constexpr int replyTimeoutMs = 3000;   // configure / flush round trips
constexpr int stallTimeoutMs = 3000;   // submitted work with no reply at all
}

Client::~Client()
{
    disconnect();
#ifndef OMNI_HW_NO_SWSCALE
    if (sws_) sws_freeContext(sws_);
#endif
}

bool Client::serviceAvailable()
{
    return flagEnabled() && !access((rendezvousDir() + "/service").c_str(), F_OK);
}

bool Client::fail(const std::string& why)
{
    if (!failed_) {
        error_ = why; failed_ = true;
        if (link_) link_->clientFailed_ = true;   // OMNI_HOLEPUNCH_V5
        fprintf(stderr, "OMNI HW CLIENT: %s\n", why.c_str()); fflush(stderr);
    }
    return false;
}

void Client::disconnect()
{
    if (link_) { link_->client_ = nullptr; link_.reset(); } // OMNI_HOLEPUNCH_V1: frames out there go inert
    if (fd_ >= 0) {
        Message m; m.type = Type::Close; sendMsg(m);
        close(fd_); fd_ = -1;   // the service sees EOF and recycles the channel
    }
    if (shm_) { munmap(shm_, shmSize_); shm_ = nullptr; }
}

// OMNI_HOLEPUNCH_V2: never block the WebProcess main thread on a service that stopped
// reading (a blocked send also kept the stall detector, which runs on this thread, from
// ever firing). Wait at most sendTimeoutMs for room, then give the stream up.
constexpr int sendTimeoutMs = 500;
bool Client::sendMsg(const Message& m)
{
    if (sendBroken_) return false;
    const char* p = reinterpret_cast<const char*>(&m);
    size_t left = sizeof m;
    const double deadline = nowMs() + sendTimeoutMs;
    while (left) {
        ssize_t n = send(fd_, p, left, MSG_DONTWAIT);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            pollfd pfd { fd_, POLLOUT, 0 };
            const int wait = int(deadline - nowMs());
            if (wait > 0 && poll(&pfd, 1, wait) >= 0) continue;
            sendBroken_ = true;
            return fail("decode service not reading (send blocked 500 ms)");
        }
        if (n <= 0) { sendBroken_ = true; return fail("service connection lost"); }
        p += n; left -= size_t(n);
    }
    return true;
}

// OMNI_HOLEPUNCH_V2: for messages that can simply be sent again later (rect updates).
bool Client::trySendMsg(const Message& m)
{
    if (sendBroken_) return false;
    ssize_t n;
    do n = send(fd_, &m, sizeof m, MSG_DONTWAIT); while (n < 0 && errno == EINTR);
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return false;   // nothing written
    if (n <= 0) { sendBroken_ = true; return fail("service connection lost"); }
    if (size_t(n) == sizeof m) return true;
    // Part of it went out: the rest must follow to keep the stream framed.
    Message rest = m;
    const char* p = reinterpret_cast<const char*>(&rest) + n;
    size_t left = sizeof m - size_t(n);
    const double deadline = nowMs() + sendTimeoutMs;
    while (left) {
        ssize_t k = send(fd_, p, left, MSG_DONTWAIT);
        if (k < 0 && errno == EINTR) continue;
        if (k < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            pollfd pfd { fd_, POLLOUT, 0 };
            const int wait = int(deadline - nowMs());
            if (wait > 0 && poll(&pfd, 1, wait) >= 0) continue;
            sendBroken_ = true;
            return fail("decode service not reading (send blocked 500 ms)");
        }
        if (k <= 0) { sendBroken_ = true; return fail("service connection lost"); }
        p += k; left -= size_t(k);
    }
    return true;
}

bool Client::tryConnect()
{
    const std::string dir = rendezvousDir();
    FILE* f = fopen((dir + "/service").c_str(), "r");
    if (!f) return fail("no decode service");
    char line[128]; long pid = 0;
    recycling_ = false;
    struct Entry { int index; uint32_t gen; int fd; };
    std::vector<Entry> entries;
    while (fgets(line, sizeof line, f)) {
        int i, fd; unsigned gen;
        if (sscanf(line, "pid %ld", &pid) == 1) continue;
        if (sscanf(line, "channel %d %u %d", &i, &gen, &fd) == 3) {
            if (fd >= 0) entries.push_back({ i, gen, fd });
            else recycling_ = true;   // in use; frees up when its client leaves
        }
    }
    fclose(f);
    if (pid <= 0) return fail("bad rendezvous file");
    servicePid_ = pid_t(pid);
    busy_ = false;
    for (auto& e : entries) {
        std::string claim = dir + "/claim-" + std::to_string(e.index);
        int c = open(claim.c_str(), O_CREAT | O_EXCL | O_WRONLY, 0644);
        if (c < 0) { busy_ = true; continue; }     // another client owns it
        char pidText[24]; int len = snprintf(pidText, sizeof pidText, "%d\n", int(getpid()));
        if (len > 0) (void)!write(c, pidText, size_t(len));
        close(c);
        int fd = omni_remote_dup(servicePid_, e.fd);
        if (fd < 0) { unlink(claim.c_str()); continue; }
        fd_ = fd; channel_ = e.index;
        Message hello; hello.type = Type::Hello;
        hello.a = uint32_t(getpid()); hello.b = e.gen; hello.c = Wire::version;
        Message ack;
        if (sendMsg(hello) && waitFor(Type::HelloAck, ack, replyTimeoutMs) && ack.status == 0) return true;
        close(fd_); fd_ = -1; failed_ = false; error_.clear();
        // The service frees the claim when it notices; never leave it behind ourselves.
        unlink(claim.c_str());
    }
    return false;   // all channels busy (or recycling): caller retries
}

bool Client::connect()
{
    // A channel freed by a stream that just closed is recycled by the service
    // within one poll interval; wait briefly rather than fall back at once.
    for (double end = nowMs() + (connectNoWait_ ? -1 : 2000);;) {   // OMNI_MSE_SWITCH_HANDOFF_V1: connectNoWait_: one try
        if (tryConnect()) return true;
        if (failed_) return false;
        // Nothing claimed and nothing reachable: the service is gone (e.g. a
        // stale rendezvous file). Fall back now instead of waiting.
        if (!busy_ && !recycling_) return fail("decode service unreachable");
        if (nowMs() > end) return fail("no free decode channel");
        usleep(20000);
    }
}

bool Client::configure(Codec codec, const DemuxTrack& track, bool bgra)
{
    disconnect();
    failed_ = drained_ = draining_ = opened_ = false; error_.clear(); ready_.clear(); outstanding_ = 0;
    randomAccess_ = true; skipRasl_ = false;
    ringReset(); v5_ = holeV5FlagEnabled();   // OMNI_HOLEPUNCH_V5
    codec_ = codec; track_ = track; bgra_ = bgra;
    std::string err;
    if (codec == Codec::H264 && !parseAvcC(track.extraData.data(), track.extraData.size(), nal_, err)) return fail("avcC: " + err);
    if (codec == Codec::HEVC && !parseHvcC(track.extraData.data(), track.extraData.size(), nal_, err)) return fail("hvcC: " + err);
    if (track.width <= 0 || track.height <= 0 || track.width > 3840 || track.height > 2160) return fail("dimensions outside hardware range");
    if (track.timeBase.numerator <= 0 || track.timeBase.denominator <= 0) return fail("time base");
    if (codec == Codec::VP9) nal_.colour = {};          // OMNI_HOLEPUNCH_COLOUR_V1: VP9's comes with its first keyframe
    colour_ = colourWord(nal_.colour, track.height);
    // VP9 bit depth is only known from the first keyframe: open lazily.
    if (codec == Codec::VP9) return true;
    return openStream(nal_.bitDepth);
}

bool Client::openStream(int bitDepth)
{
    if (!connect()) return false;
    Message cfg; cfg.type = Type::Configure;
    cfg.a = codec_ == Codec::H264 ? 0 : codec_ == Codec::HEVC ? 1 : 2;
    cfg.b = uint32_t(nal_.profile); cfg.c = uint32_t(bitDepth);
    cfg.d = uint32_t(track_.width); cfg.e = uint32_t(track_.height);
    cfg.f = colour_;   // OMNI_HOLEPUNCH_COLOUR_V1
    fprintf(stderr, "OMNI HW CLIENT: colour matrix %d (%s), %s range\n", colourMatrix(colour_, track_.height),
        nal_.colour.matrix >= 0 ? "signalled" : "default for the height", colourFullRange(colour_) ? "full" : "limited");
    fflush(stderr);
    Message reply;
    if (!sendMsg(cfg) || !waitFor(Type::Configured, reply, replyTimeoutMs)) return fail(error_.empty() ? "no Configured reply" : error_);
    if (reply.status) { char b[96]; snprintf(b, sizeof b, "service open failed rc=0x%08x at %s", unsigned(reply.status), reply.text); return fail(b); }
    int shmFd = omni_remote_dup(servicePid_, int(reply.a));
    if (shmFd < 0) return fail("could not duplicate shared memory");
    void* p = mmap(nullptr, reply.b, PROT_READ | PROT_WRITE, MAP_SHARED, shmFd, 0);
    close(shmFd);
    if (p == MAP_FAILED) return fail("could not map shared memory");
    shm_ = static_cast<uint8_t*>(p); shmSize_ = reply.b;
    slotOffset_ = reply.d; slotSize_ = reply.e; slotCount_ = reply.f;
    Message mapped; mapped.type = Type::ShmMapped;
    lastProgressMs_ = nowMs();
    opened_ = true;
    link_ = std::make_shared<HoleLink>(); // OMNI_HOLEPUNCH_V1
    link_->client_ = this;
    return sendMsg(mapped);
}

bool Client::waitFor(Type type, Message& out, int timeoutMs)
{
    double end = nowMs() + timeoutMs;
    for (;;) {
        pollfd pfd { fd_, POLLIN, 0 };
        int left = int(end - nowMs());
        if (left <= 0) return fail("service reply timeout");
        if (poll(&pfd, 1, left) <= 0) continue;
        char* p = reinterpret_cast<char*>(&partial_) + partialLen_;
        ssize_t n = recv(fd_, p, sizeof(Message) - partialLen_, 0);
        if (n <= 0) return fail("service connection lost");
        partialLen_ += size_t(n);
        if (partialLen_ < sizeof(Message)) continue;
        partialLen_ = 0;
        if (partial_.magic != Wire::magic) return fail("bad message");
        if (partial_.type == type) { out = partial_; return true; }
        if (!handle(partial_)) return false;
    }
}

bool Client::pumpMessages(int waitMs)
{
    if (fd_ < 0) return fail("not connected");
    // OMNI_HOLEPUNCH_V3: this thread was away (a long main-thread block) for over 1 s: the
    // service may have been waiting on frames we hold. Restart the stall window instead of
    // blaming the service for our absence.
    const double now = nowMs();
    if (lastPumpMs_ && now - lastPumpMs_ > 1000) lastProgressMs_ = now;
    lastPumpMs_ = now;
    for (bool first = true;; first = false) {
        pollfd pfd { fd_, POLLIN, 0 };
        int r = poll(&pfd, 1, first ? waitMs : 0);
        if (r <= 0) return true;
        char* p = reinterpret_cast<char*>(&partial_) + partialLen_;
        ssize_t n = recv(fd_, p, sizeof(Message) - partialLen_, MSG_DONTWAIT);
        if (n < 0 && (errno == EAGAIN || errno == EINTR)) return true;
        if (n <= 0) return fail("service connection lost");
        partialLen_ += size_t(n);
        if (partialLen_ < sizeof(Message)) continue;
        partialLen_ = 0;
        if (partial_.magic != Wire::magic) return fail("bad message");
        lastProgressMs_ = nowMs();
        if (!handle(partial_)) return false;
    }
}

bool Client::handle(const Message& m)
{
    switch (m.type) {
    case Type::Consumed:   // OMNI_HOLEPUNCH_V5: cumulative
        ringConsumed(m.a);
        return true;
    case Type::Frame: {
        if (m.f & Wire::FrameSnapshot) {   // OMNI_HOLEPUNCH_V4: the shell's frame on screen, for the paint path
            DecodedOutput out;
            const bool ok = link_ && m.a < slotCount_ && convert(m, out);
            Message rel; rel.type = Type::Release; rel.a = m.a;
            if (!sendMsg(rel)) return false;
            if (ok) { link_->snapshot_ = std::move(out); link_->snapshotReady_ = true; }
            return true;
        }
        if (holePunch_ && !raw_ && link_ && m.a < slotCount_) {
            // OMNI_HOLEPUNCH_V1: no conversion; the picture stays in its slot until the
            // player presents it, converts it, or drops it (HoleFrame).
            DecodedOutput out;
            out.timeBase = track_.timeBase;
            out.hasTimestamp = m.pts != INT64_MIN;
            out.timestamp = out.hasTimestamp ? m.pts : 0;
            out.nonDisplaying = (m.f & Wire::FrameNonDisplaying) != 0;
            out.kind = DecodedOutput::Kind::Video;
            out.width = out.sourceWidth = track_.width; out.height = out.sourceHeight = track_.height;
            out.opaque = true; out.bgra = bgra_;
            out.hole = std::make_shared<HoleFrame>(link_, m);
            ready_.push_back(std::move(out));
            return true;
        }
        DecodedOutput out;
        bool ok = convert(m, out);
        Message rel; rel.type = Type::Release; rel.a = m.a;
        if (!sendMsg(rel)) return false;   // release before anything can fail later
        if (!ok) return fail("frame conversion failed");
        ready_.push_back(std::move(out));
        return true;
    }
    case Type::Drained: drained_ = true; draining_ = false; return true;
    case Type::HoleShown:   // OMNI_HOLEPUNCH_V2
        if (link_) link_->shown_ = m.a;
        return true;
    case Type::HoleState:   // OMNI_HOLEPUNCH_V1
        if (link_) {
            const int state = m.status == 0 ? 1 : -1;
            if (state != link_->state_ || strncmp(link_->reason_, m.text, sizeof link_->reason_)) {
                fprintf(stderr, "OMNI HOLEPUNCH: player channel %d %s (%.47s)\n", channel_, state == 1 ? "shown by the shell" : "refused", m.text);
                fflush(stderr);
            }
            link_->state_ = state;
            snprintf(link_->reason_, sizeof link_->reason_, "%s", m.text);
            link_->pacingAvailable_ = state == 1 && (m.a & 1);   // OMNI_HOLEPUNCH_V4
            if (state != 1) link_->pacing_ = {};
        }
        return true;
    case Type::HolePacing:   // OMNI_HOLEPUNCH_V4
        if (link_) {
            auto& p = link_->pacing_;
            int state = m.status == 0 ? 1 : -1;
            if (state == 1 && link_->pacingStopped_) state = 0;   // OMNI_MSE_SWITCH_HANDOFF_V1: sent before the shell read "pacing off"
            if (state != p.state && state) {
                fprintf(stderr, "OMNI HOLEPUNCH: player channel %d %s (%.47s)\n", channel_, state == 1 ? "paced by the shell" : "not paced by the shell", m.text);
                fflush(stderr);
            }
            p.state = state;
            p.shown = m.a; p.dropped = m.b; p.late = m.c; p.waiting = m.d; p.decoded = m.e; p.capacity = m.f;
            memcpy(&p.startupFlags, m.text + 16, sizeof p.startupFlags);
            memcpy(&p.startupGeneration, m.text + 20, sizeof p.startupGeneration);
            p.aheadMs = m.g;   // OMNI_HOLEPUNCH_V5_REV2
            p.mediaUs = m.pts; p.atMs = nowMs();
            snprintf(p.reason, sizeof p.reason, "%s", m.text);
        }
        return true;
    case Type::Error: { char b[96]; snprintf(b, sizeof b, "service error rc=0x%08x at %s", unsigned(m.status), m.text); return fail(b); }
    default: return true;
    }
}

// NV12 / low-aligned 16-bit two-plane -> RGBA or BGRA, same layout the
// software PacketDecoder produces, so the player draws it unchanged.
bool Client::convert(const Message& m, DecodedOutput& out)
{
    if (m.a >= slotCount_) return false;
    const int w = track_.width, h = track_.height;
    const bool tenBit = m.e > 8;
    const size_t pitch = m.d, coded = m.c;
    if (int(m.b) < w || coded < size_t(h) || pitch * coded * 3 / 2 > slotSize_ || pitch < size_t(w) * (tenBit ? 2 : 1)) return false;
    uint8_t* y = shm_ + slotOffset_ + size_t(m.a) * slotSize_;
    const uint8_t* uv = y + pitch * coded;
    out.timeBase = track_.timeBase;
    out.hasTimestamp = m.pts != INT64_MIN;
    out.timestamp = out.hasTimestamp ? m.pts : 0;
    out.nonDisplaying = (m.f & Wire::FrameNonDisplaying) != 0;
    out.kind = DecodedOutput::Kind::Video;
    out.width = w; out.height = h; out.opaque = true;
    if (raw_) {
        const size_t row = size_t(w) * (tenBit ? 2 : 1);
        out.rgba.resize(row * size_t(h) * 3 / 2);
        uint8_t* d = out.rgba.data();
        for (int r = 0; r < h; r++, d += row) memcpy(d, y + pitch * size_t(r), row);
        for (int r = 0; r < h / 2; r++, d += row) memcpy(d, uv + pitch * size_t(r), row);
        return true;
    }
#ifdef OMNI_HW_NO_SWSCALE
    return false;
#else
    // De-interleave UV into planar U and V so swscale takes the same
    // planar 4:2:0 path as the software decoder: identical RGB output.
    // 10-bit samples are low-aligned, exactly yuv420p10le's layout.
    const int cw = w / 2, ch = h / 2;
    const size_t bps = tenBit ? 2 : 1, planeBytes = size_t(cw) * ch * bps;
    scratch_.resize(planeBytes * 2 + 64);   // OMNI_HOLEPUNCH_COLOUR_V1: swscale's SIMD reads up to 8 samples past a row
    uint8_t* u = scratch_.data();
    uint8_t* v = u + planeBytes;
    for (int row = 0; row < ch; row++) {
        const uint8_t* s = uv + pitch * size_t(row);
        if (tenBit) {
            const uint16_t* s16 = reinterpret_cast<const uint16_t*>(s);
            uint16_t* du = reinterpret_cast<uint16_t*>(u) + size_t(row) * cw;
            uint16_t* dv = reinterpret_cast<uint16_t*>(v) + size_t(row) * cw;
            for (int i = 0; i < cw; i++) { du[i] = s16[2 * i]; dv[i] = s16[2 * i + 1]; }
        } else {
            uint8_t* du = u + size_t(row) * cw;
            uint8_t* dv = v + size_t(row) * cw;
            for (int i = 0; i < cw; i++) { du[i] = s[2 * i]; dv[i] = s[2 * i + 1]; }
        }
    }
    // OMNI_VIDEO_TARGET_V1: convert and scale to the shown size in one pass.
    int ow = w, oh = h;
    videoOutputSize(w, h, targetWidth_, targetHeight_, ow, oh);
    if ((ow != loggedWidth_ || oh != loggedHeight_) && sizeLogs_ < 8) {
        ++sizeLogs_; loggedWidth_ = ow; loggedHeight_ = oh;
        fprintf(stderr, "OMNI HW CLIENT: output %dx%d -> %dx%d (target %dx%d)\n", w, h, ow, oh, targetWidth_, targetHeight_);
        fflush(stderr);
    }
    // OMNI_HOLEPUNCH_COLOUR_V1: the stream's matrix and range (swscale defaults to BT.601
    // limited), set once per context; and a destination stride of whole 16-pixel groups:
    // swscale's unscaled 4:2:0 -> RGB path leaves the last width % 8 pixels of every row
    // unwritten when the stride is exactly width * 4. Rows are packed again afterwards.
    const int srcFormat = tenBit ? AV_PIX_FMT_YUV420P10LE : AV_PIX_FMT_YUV420P, dstFormat = bgra_ ? AV_PIX_FMT_BGRA : AV_PIX_FMT_RGBA;
    const int key[7] = { w, h, srcFormat, ow, oh, dstFormat, int(colour_) };
    if (!sws_ || memcmp(key, swsKey_, sizeof key)) {
        if (sws_) sws_freeContext(sws_);
        sws_ = sws_getContext(w, h, AVPixelFormat(srcFormat), ow, oh, AVPixelFormat(dstFormat), SWS_BILINEAR, nullptr, nullptr, nullptr);
        if (!sws_) { memset(swsKey_, 0, sizeof swsKey_); return false; }
        sws_setColorspaceDetails(sws_, sws_getCoefficients(colourMatrix(colour_, h)), colourFullRange(colour_),
            sws_getCoefficients(SWS_CS_DEFAULT), 1, 0, 1 << 16, 1 << 16);
        memcpy(swsKey_, key, sizeof key);
    }
    out.width = ow; out.height = oh; out.sourceWidth = w; out.sourceHeight = h;
    const size_t row = size_t(ow) * 4, stride = (size_t(ow) + 15) / 16 * 16 * 4;
    out.rgba.resize(stride * size_t(oh));
    const uint8_t* src[4] = { y, u, v, nullptr };
    int srcStride[4] = { int(pitch), int(size_t(cw) * bps), int(size_t(cw) * bps), 0 };
    uint8_t* dst[4] = { out.rgba.data(), nullptr, nullptr, nullptr };
    int dstStride[4] = { int(stride), 0, 0, 0 };
    if (sws_scale(sws_, src, srcStride, 0, h, dst, dstStride) != oh) return false;
    if (stride != row) {
        for (int r = 1; r < oh; r++) memmove(out.rgba.data() + size_t(r) * row, out.rgba.data() + size_t(r) * stride, row);
        out.rgba.resize(row * size_t(oh));
    }
    out.bgra = bgra_;
    return true;
#endif
}

// ---- OMNI_HOLEPUNCH_V5: the input ring -----------------------------------------------------
// Access units are written back to back into the shared input region and wrap to its start
// when the rest of the region is too small. The service consumes them in submission order, so
// the free space is everything outside [oldest in flight, end of the newest).
bool Client::ringPlace(size_t size, uint32_t head, uint32_t tail, bool empty, uint32_t& offset) const
{
    const size_t ring = Wire::inputRingBytes;
    if (!size || size > Wire::inputMaxAu) return false;
    if (empty) { offset = 0; return size <= ring; }
    if (head > tail) {                                    // used: [tail, head)
        if (ring - head >= size) { offset = head; return true; }
        if (tail >= size) { offset = 0; return true; }    // wrap
        return false;
    }
    if (tail - head >= size) { offset = head; return true; }   // wrapped: free is [head, tail)
    return false;
}

bool Client::ringFits(const size_t* sizes, size_t count) const
{
    uint32_t head = ringHead_, tail = inFlight_.empty() ? 0 : inFlight_.front().start;
    bool empty = inFlight_.empty();
    for (size_t i = 0; i < count; i++) {
        uint32_t offset;
        if (!ringPlace(sizes[i], head, tail, empty, offset)) return false;
        if (empty) { tail = offset; empty = false; }
        head = uint32_t(offset + sizes[i]);
    }
    return true;
}

void Client::ringConsumed(uint32_t total)
{
    uint32_t n = total - consumed_;
    if (n > inFlight_.size()) n = uint32_t(inFlight_.size());   // never more than were sent
    for (uint32_t i = 0; i < n; i++) inFlight_.pop_front();
    consumed_ = total;
    if (inFlight_.empty()) { ringHead_ = 0; inFlightMaxPts_ = INT64_MIN; }
    outstanding_ = unsigned(inFlight_.size());
    if (n) blocked_ = false;
}

void Client::ringReset()
{
    inFlight_.clear(); ringHead_ = 0; consumed_ = 0; inFlightMaxPts_ = INT64_MIN;
    outstanding_ = 0; blocked_ = false;
}

// While the shell paces this video: up to ~3.5 s of access units (and Wire::inputMaxInFlight),
// so the service decodes on through a stall of this process's main thread. Otherwise V4's depth.
unsigned Client::inFlightLimit() const
{
    const bool deep = v5_ && link_ && link_->pacing_.state == 1;
    return deep ? Wire::inputMaxInFlight : Wire::inputInFlightV4;
}

double Client::inFlightSeconds() const
{
    if (inFlight_.empty() || inFlightMaxPts_ == INT64_MIN || track_.timeBase.denominator <= 0) return 0;
    return double(inFlightMaxPts_ - inFlight_.front().pts) * track_.timeBase.numerator / track_.timeBase.denominator;
}

bool Client::sendAu(const uint8_t* data, size_t size, int64_t pts, uint32_t flags)
{
    if (size > Wire::inputMaxAu) return fail("access unit larger than the decoder input buffer");
    uint32_t offset;
    if (!ringPlace(size, ringHead_, inFlight_.empty() ? 0 : inFlight_.front().start, inFlight_.empty(), offset))
        return fail("internal: no room in the input ring");
    memcpy(shm_ + offset, data, size);
    inFlight_.push_back({ offset, uint32_t(offset + size), pts });
    ringHead_ = uint32_t(offset + size);
    inFlightMaxPts_ = std::max(inFlightMaxPts_, pts);
    outstanding_ = unsigned(inFlight_.size());
    Message m; m.type = Type::Submit; m.a = offset; m.b = uint32_t(size); m.c = flags; m.pts = pts;
    return sendMsg(m);
}

Client::Submit Client::submit(const DemuxPacket& packet)
{
    if (failed_) return Submit::Error;
    if (!opened_) {
        int profile = 0, depth = 8;
        if (codec_ != Codec::VP9 || !vp9KeyFrameInfo(packet.bytes.data(), packet.bytes.size(), profile, depth)) { fail("stream must start with a keyframe"); return Submit::Error; }
        if (depth > 10) { fail("12-bit VP9 has no hardware route"); return Submit::Error; }
        nal_.profile = profile;
        VideoColour vc;   // OMNI_HOLEPUNCH_COLOUR_V1
        if (vp9KeyFrameColour(packet.bytes.data(), packet.bytes.size(), vc)) { nal_.colour = vc; colour_ = colourWord(vc, track_.height); }
        if (!openStream(depth)) return Submit::Error;
    }
    // OMNI_HOLEPUNCH_V5: at the in-flight limit and the socket read less than 1 ms ago: the pump
    // asks again at once (up to 8 x budget times per tick); answer without a syscall.
    if (blocked_ && nowMs() - blockedPollMs_ < 1) return Submit::NeedOutput;
    if (!pumpMessages(0)) return Submit::Error;
    if (draining_ || drained_) { fail("submit after drain"); return Submit::Error; }
    // Same timestamp rule as the software decoder: rescale to the track time
    // base, rounding to nearest.
    if (packet.timeBase.numerator <= 0 || packet.timeBase.denominator <= 0 || packet.bytes.empty()) { fail("invalid packet"); return Submit::Error; }
    const int64_t pts = rescale(packet.pts, packet.timeBase.numerator, packet.timeBase.denominator,
                                track_.timeBase.numerator, track_.timeBase.denominator);
    if (pts == INT64_MIN) { fail("timestamp overflow"); return Submit::Error; }
    uint32_t base = (packet.nonDisplaying ? Wire::NonDisplaying : 0) | (packet.keyFrame ? Wire::KeyFrame : 0);
    std::string err;
    if (codec_ == Codec::VP9) {
        if (!splitVp9(packet.bytes.data(), packet.bytes.size(), vp9_, err)) { fail("VP9: " + err); return Submit::Error; }
    } else {
        vp9_.clear();
        // OMNI_HOLEPUNCH_V5: the in-flight limits before the conversion and the RASL
        // state (the pump retries a packet that got NeedOutput, many times per tick).
        if (outstanding_ + 1 > inFlightLimit() || (inFlightLimit() > Wire::inputInFlightV4 && inFlightSeconds() > 3.5)) {
            if (nowMs() - lastProgressMs_ > stallTimeoutMs) { fail("decode service stalled"); return Submit::Error; }
            blocked_ = true; blockedPollMs_ = nowMs();
            return Submit::NeedOutput;
        }
        if (codec_ == Codec::HEVC) {
            int type = hevcFirstVclType(nal_, packet.bytes.data(), packet.bytes.size());
            if (randomAccess_ && type >= 16 && type <= 23) {          // the IRAP decoding starts at
                skipRasl_ = type <= 21;                               // BLA (16-18) or CRA (21)
                randomAccess_ = false;
            } else if (skipRasl_ && (type == 8 || type == 9)) {
                return Submit::Accepted;   // RASL: undecodable here; never shown by software either
            } else if (type >= 0 && type != 8 && type != 9) {
                skipRasl_ = false;
            }
        }
        // MP4 samples with an avcC/hvcC are always length-prefixed (ISO 14496-15).
        // Never guess from the first bytes: a 256-511 byte first NAL unit has a
        // length prefix of 00 00 01 xx, indistinguishable from a start code.
        if (!lengthPrefixedToAnnexB(codec_, nal_, packet.bytes.data(), packet.bytes.size(), packet.keyFrame, au_, err)) { fail("bitstream: " + err); return Submit::Error; }
    }
    const size_t parts = codec_ == Codec::VP9 ? vp9_.size() : 1;
    // OMNI_HOLEPUNCH_V5: in-flight count and media span (paced: ~3.5 s), and room in the ring.
    size_t sizes[8] = {};
    const size_t sized = std::min<size_t>(parts, 8);
    for (size_t i = 0; i < sized; i++) sizes[i] = codec_ == Codec::VP9 ? vp9_[i].size : au_.size();
    if (outstanding_ + parts > inFlightLimit() || (inFlightLimit() > Wire::inputInFlightV4 && inFlightSeconds() > 3.5)
        || parts > 8 || !ringFits(sizes, sized)) {
        if (nowMs() - lastProgressMs_ > stallTimeoutMs) { fail("decode service stalled"); return Submit::Error; }
        if (parts > 8 || (inFlight_.empty() && !ringFits(sizes, sized))) { fail("access unit does not fit the input ring"); return Submit::Error; }
        blocked_ = true; blockedPollMs_ = nowMs();
        return Submit::NeedOutput;   // the pump calls receive(), which reads Consumed
    }
    if (codec_ == Codec::VP9) {
        for (auto& f : vp9_)
            if (!sendAu(packet.bytes.data() + f.offset, f.size, pts, base | (f.shown ? 0 : Wire::Hidden))) return Submit::Error;
    } else if (!sendAu(au_.data(), au_.size(), pts, base)) {
        return Submit::Error;
    }
    lastProgressMs_ = nowMs();
    blocked_ = false;   // OMNI_HOLEPUNCH_V5
    return Submit::Accepted;
}

Client::Submit Client::drain()
{
    if (failed_) return Submit::Error;
    if (!opened_) { drained_ = true; return Submit::Accepted; }
    if (draining_ || drained_) return Submit::Accepted;
    Message m; m.type = Type::Drain;
    if (!sendMsg(m)) return Submit::Error;
    draining_ = true; lastProgressMs_ = nowMs();
    return Submit::Accepted;
}

Client::Receive Client::receive(DecodedOutput& out)
{
    out = {};
    if (failed_) return Receive::Error;
    if (!opened_) return drained_ ? Receive::End : Receive::NeedInput;
    // OMNI_HOLEPUNCH_V5: see submit(): nothing new can have been read within the last 1 ms.
    if (blocked_ && ready_.empty() && !draining_ && nowMs() - blockedPollMs_ < 1) return Receive::NeedInput;
    if (!pumpMessages(0)) return Receive::Error;
    if (!ready_.empty()) { out = std::move(ready_.front()); ready_.pop_front(); return Receive::Output; }
    if (drained_) return Receive::End;
    if ((outstanding_ || draining_) && nowMs() - lastProgressMs_ > stallTimeoutMs) { fail("decode service stalled"); return Receive::Error; }
    return Receive::NeedInput;
}

void Client::flush()
{
    ready_.clear(); drained_ = draining_ = false;
    randomAccess_ = true; skipRasl_ = false;
    if (fd_ < 0 || failed_) return;
    Message m; m.type = Type::Flush;
    Message reply;
    // Frames before Flushed are converted, released and dropped by waitFor/handle.
    if (sendMsg(m) && waitFor(Type::Flushed, reply, replyTimeoutMs)) {
        ready_.clear();
        if (reply.status) fail("service reset failed");
    }
    ringReset();   // OMNI_HOLEPUNCH_V5: Flushed follows every Consumed for earlier submits; both sides count from 0
    lastProgressMs_ = nowMs();
}

// ---- OMNI_HOLEPUNCH_V1 ------------------------------------------------------------------
bool Client::holePunchAllowed()
{
#ifdef OMNI_HW_NO_SWSCALE
    return false;   // the paint path of a hole frame needs convert()
#else
    return flagEnabled() && holePunchFlagEnabled();
#endif
}

bool Client::holePacingAllowed()   // OMNI_HOLEPUNCH_V4
{
    return holePunchAllowed() && holePacingFlagEnabled();
}

bool HoleLink::sendClock(const HoleClockState& s)   // OMNI_HOLEPUNCH_V4 (fields in OmniHwProtocol.h)
{
    if (!client_ || client_->fd_ < 0) return false;
    if (s.paced) pacingStopped_ = false;   // OMNI_MSE_SWITCH_HANDOFF_V1
    Message m; m.type = Type::HoleClock;
    m.a = (s.paced ? Wire::clockPaced : 0) | (s.playing ? Wire::clockPlaying : 0) | (s.snapshot ? Wire::clockSnapshot : 0)
        | (s.discardBefore >= 0 ? Wire::clockDiscard : 0) | (std::isfinite(s.limit) ? Wire::clockLimit : 0);
    m.b = s.generation;
    m.c = uint32_t(std::clamp(s.rate, 0.0, 65535.0) * 65536);
    const uint64_t anchor = uint64_t(nowMs() * 1000);
    m.d = uint32_t(anchor); m.e = uint32_t(anchor >> 32);
    m.f = uint32_t(client_->track_.timeBase.numerator); m.g = uint32_t(client_->track_.timeBase.denominator);
    m.pts = int64_t(std::llround(s.position * 1e6));
    const int64_t discard = s.discardBefore >= 0 ? int64_t(std::llround(s.discardBefore * 1e6)) : INT64_MIN;
    const int64_t limit = std::isfinite(s.limit) ? int64_t(std::llround(s.limit * 1e6)) : INT64_MAX;
    memcpy(m.text, &discard, sizeof discard);
    memcpy(m.text + 8, &limit, sizeof limit);
    // V136: eight signed microsecond offsets from the send anchor, still 32 spare bytes.
    const int64_t stages[] = { s.traceReleaseUs, s.tracePrintedUs, s.traceFlushedUs, s.traceAfterHoldUs,
        s.traceBeforeRingUs, s.tracePumpStartUs, s.tracePumpEndUs, s.traceClockBuildUs };
    int32_t offsets[8];
    for (unsigned i = 0; i < 8; ++i) offsets[i] = stages[i] ? int32_t(std::clamp<int64_t>(stages[i] - int64_t(anchor), INT32_MIN + 1, INT32_MAX)) : INT32_MIN;
    memcpy(m.text + 16, offsets, sizeof offsets);
    return client_->trySendMsg(m);
}

double HoleLink::pacingReportAgeMs() const   // OMNI_HOLEPUNCH_V4
{
    return pacing_.atMs ? nowMs() - pacing_.atMs : 0;
}

bool HoleLink::takeSnapshot(DecodedOutput& out)   // OMNI_HOLEPUNCH_V4
{
    if (!snapshotReady_) return false;
    snapshotReady_ = false;
    out = std::move(snapshot_);
    snapshot_ = {};
    return true;
}

bool HoleLink::claim(const Rect& r)
{
    if (!client_) return false;
    Message m; m.type = Type::Present; m.a = Wire::presentKeep;
    m.b = uint32_t(r.x); m.c = uint32_t(r.y); m.d = uint32_t(r.w); m.e = uint32_t(r.h);
    if (client_->trySendMsg(m)) return true;   // OMNI_HOLEPUNCH_V2: never wait for a rect
    ++rectDrops;
    return false;
}

void HoleLink::pump()   // OMNI_HOLEPUNCH_V2
{
    if (client_ && client_->fd_ >= 0 && !client_->failed_) client_->pumpMessages(0);
}

HoleLink::Stats HoleLink::stats() const   // OMNI_HOLEPUNCH_V2
{
    Stats s;
    if (!client_) return s;
    s.ready = client_->ready_.size();
    s.outstanding = client_->outstanding_;
    s.lastMessageAgoMs = nowMs() - client_->lastProgressMs_;
    s.failed = client_->failed_;
    return s;
}

bool HoleLink::hide()
{
    state_ = 0; reason_[0] = 0;
    pacingAvailable_ = false; pacing_ = {};   // OMNI_HOLEPUNCH_V4
    if (!client_) return false;
    Message m; m.type = Type::Present; m.a = Wire::presentHide;
    return client_->sendMsg(m);
}

HoleFrame::~HoleFrame()
{
    if (!handedOff_ && link_ && link_->held_) link_->held_--;   // OMNI_HOLEPUNCH_V2
    if (handedOff_ || !link_ || !link_->client_) return;   // presented, or the stream is gone
    Message rel; rel.type = Type::Release; rel.a = frame_.a;
    link_->client_->sendMsg(rel);
}

bool HoleFrame::convert(DecodedOutput& out)
{
    if (handedOff_ || !link_ || !link_->client_) return false;
    return link_->client_->convert(frame_, out);
}

bool HoleFrame::present(const HoleLink::Rect& r)
{
    if (handedOff_ || !link_ || !link_->client_) return false;
    handedOff_ = true;   // from here on the slot belongs to the service, even if sending fails
    if (link_->held_) link_->held_--;   // OMNI_HOLEPUNCH_V2
    Message m; m.type = Type::Present; m.a = frame_.a;
    m.b = uint32_t(r.x); m.c = uint32_t(r.y); m.d = uint32_t(r.w); m.e = uint32_t(r.h);
    m.pts = frame_.pts;
    const bool sent = link_->client_->sendMsg(m);
    ++(sent ? link_->presents : link_->presentFailures);
    return sent;
}

// ---- OMNI_HOLEPUNCH_V3: main-thread watchdog (see OmniHwClient.h) ----------------------
}
extern "C" __attribute__((weak)) char etext;   // end of code, from the linker (0 if absent)
namespace OmniMedia::Hw {
namespace {
#if defined(__clang__)
#define OMNI_NO_SANITIZE __attribute__((no_sanitize("address", "thread", "undefined")))
#else
#define OMNI_NO_SANITIZE __attribute__((no_sanitize_address, no_sanitize("thread", "undefined")))
#endif
struct Watch {
    std::atomic<bool> started { false }, active { false }, handled { false };
    std::atomic<uint64_t> tickMs { 0 }, reports { 0 };
    std::mutex snapLock;     // the last tick's snapshot (held only while copying)
    HoleWatchSnapshot snap;
    pthread_t mainThread {};
    uintptr_t imageBase = 0, codeStart = 0, codeEnd = 0, stackTop = 0;
    int (*virtualQuery)(const void*, int, void*, size_t) = nullptr;
};
Watch watch;

char* hex(char* p, uintptr_t v)
{
    *p++ = '0'; *p++ = 'x';
    for (int shift = 60; shift >= 0; shift -= 4) *p++ = "0123456789abcdef"[(v >> shift) & 15];
    *p++ = ' ';
    return p;
}
void put(const char* text, char*& p) { while (*text) *p++ = *text++; }

// Runs on the main thread, on its own stack (no SA_ONSTACK): the kernel's signal frame, with
// the interrupted instruction pointer, and the interrupted frames lie just above this frame.
OMNI_NO_SANITIZE __attribute__((noinline)) void mainStackSignal(int)
{
    const int savedErrno = errno;
    volatile uintptr_t marker = 0;
    const uintptr_t sp = reinterpret_cast<uintptr_t>(&marker) & ~uintptr_t(7);
    uintptr_t end = sp + 64 * 1024;
    if (watch.stackTop > sp && watch.stackTop < end) end = watch.stackTop;
    if (watch.virtualQuery) {
        struct { uintptr_t start, end, offset; int prot, type; unsigned char flags; char name[32]; } region {};
        if (!watch.virtualQuery(reinterpret_cast<const void*>(sp), 0, &region, sizeof region) && region.end > sp && region.end < end)
            end = region.end;
    }
    if (!watch.stackTop && !watch.virtualQuery && end > sp + 16 * 1024) end = sp + 16 * 1024;
    char line[600];
    char* p = line;
    put("OMNI HOLEPUNCH: watchdog main thread stack (image offsets, innermost first): ", p);
    int found = 0;
    for (uintptr_t at = sp; at + 8 <= end && found < 64; at += 8) {
        const uintptr_t v = *reinterpret_cast<const uintptr_t*>(at);
        if (v <= watch.codeStart || v >= watch.codeEnd) continue;
        p = hex(p, v - watch.imageBase);
        if (++found % 8 == 0) {
            *p++ = '\n'; (void)!write(2, line, size_t(p - line)); p = line;
            put("OMNI HOLEPUNCH: watchdog main thread stack (cont.): ", p);
        }
    }
    if (found % 8 || !found) { if (!found) put("(nothing in the code range)", p); *p++ = '\n'; (void)!write(2, line, size_t(p - line)); }
    watch.handled.store(true);
    errno = savedErrno;
}

void* watchMain(void*)
{
    bool reportedThisStall = false;
    uint64_t lastSeen = 0;
    for (;;) {
        usleep(250 * 1000);
        const uint64_t tick = watch.tickMs.load();
        if (tick != lastSeen) { lastSeen = tick; reportedThisStall = false; }
        if (!watch.active.load() || reportedThisStall || watch.reports.load() >= 3) continue;
        const double gap = nowMs() - double(tick);
        if (gap < holeWatchdogStallMs) continue;
        reportedThisStall = true;
        HoleWatchSnapshot s;
        if (watch.snapLock.try_lock()) { s = watch.snap; watch.snapLock.unlock(); }
        fprintf(stderr, "OMNI HOLEPUNCH: watchdog: player tick stalled %.0f ms with the hole on; last tick: position=%.3f lastPresented=%.3f presented=%llu shown=%llu held=%u clientReady=%u submitsOutstanding=%u due=%d paused=%d\n",
            gap, s.positionSeconds, s.lastPresentedSeconds, (unsigned long long)s.presented, (unsigned long long)s.shown,
            s.held, s.clientReady, s.outstanding, s.due, s.paused);
        fflush(stderr);
        watch.handled.store(false);
        watch.reports.fetch_add(1);
        if (pthread_kill(watch.mainThread, SIGWINCH)) { fprintf(stderr, "OMNI HOLEPUNCH: watchdog: could not signal the main thread\n"); fflush(stderr); continue; }
        for (int i = 0; i < 50 && !watch.handled.load(); i++) usleep(10 * 1000);
        if (!watch.handled.load()) { fprintf(stderr, "OMNI HOLEPUNCH: watchdog: main thread did not run the stack handler within 500 ms (signal blocked?)\n"); fflush(stderr); }
    }
    return nullptr;
}

void watchStart()
{
    watch.mainThread = pthread_self();
    Dl_info image {};
    if (dladdr(reinterpret_cast<void*>(&watchStart), &image)) watch.imageBase = reinterpret_cast<uintptr_t>(image.dli_fbase);
    const uintptr_t textEnd = reinterpret_cast<uintptr_t>(&etext);
    watch.codeStart = watch.imageBase;
    watch.codeEnd = textEnd > watch.imageBase ? textEnd : watch.imageBase + (256u << 20);
    watch.virtualQuery = reinterpret_cast<int (*)(const void*, int, void*, size_t)>(dlsym(RTLD_DEFAULT, "sceKernelVirtualQuery"));
#if defined(__linux__)
    pthread_attr_t attr;
    if (!pthread_getattr_np(pthread_self(), &attr)) {
        void* base = nullptr; size_t size = 0;
        if (!pthread_attr_getstack(&attr, &base, &size)) watch.stackTop = reinterpret_cast<uintptr_t>(base) + size;
        pthread_attr_destroy(&attr);
    }
#endif
    struct sigaction action {};
    sigemptyset(&action.sa_mask);
    action.sa_handler = mainStackSignal;
    action.sa_flags = SA_RESTART;
    sigaction(SIGWINCH, &action, nullptr);
    pthread_attr_t threadAttr; pthread_attr_init(&threadAttr);
    pthread_attr_setstacksize(&threadAttr, 128 * 1024);
    pthread_attr_setdetachstate(&threadAttr, PTHREAD_CREATE_DETACHED);
    pthread_t thread;
    const int e = pthread_create(&thread, &threadAttr, watchMain, nullptr);
    pthread_attr_destroy(&threadAttr);
    fprintf(stderr, "OMNI HOLEPUNCH: watchdog %s (stall %.0f ms, image base %p, code to %p)\n", e ? "could not start" : "started",
        holeWatchdogStallMs, reinterpret_cast<void*>(watch.imageBase), reinterpret_cast<void*>(watch.codeEnd));
    fflush(stderr);
}
}

void holeWatchdogTick(const HoleWatchSnapshot* s)
{
    if (!s) { watch.active.store(false); return; }
    if (!watch.started.exchange(true)) watchStart();
    { std::lock_guard<std::mutex> l(watch.snapLock); watch.snap = *s; }
    watch.tickMs.store(uint64_t(nowMs()));
    watch.active.store(true);
}

unsigned holeWatchdogReports() { return unsigned(watch.reports.load()); }

}
