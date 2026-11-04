// Native HLS session (OMNI_HLS_NATIVE_V1). SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniHlsSession.h"
#include "OmniMediaCaps.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>

namespace OmniMedia::Hls {
namespace {
constexpr int64_t kWrap = int64_t(1) << 33;   // MPEG-2 timestamps
constexpr size_t maxPlaylistBytes = 4 * 1024 * 1024;
constexpr size_t maxSegmentBytes = 32 * 1024 * 1024;
double seconds(int64_t v, DemuxTimeBase tb) { return double(v) * tb.numerator / tb.denominator; }
int64_t ticks(double s, DemuxTimeBase tb) { return int64_t(std::llround(s * tb.denominator / tb.numerator)); }
std::string fmt(const char* f, double a, double b = 0, double c = 0)
{
    char buf[256];
    snprintf(buf, sizeof buf, f, a, b, c);
    return buf;
}
}

struct Session::Pending {
    bool active = false;
    size_t index = 0;
    Segment segment;
    uint64_t keyRequest = 0, initRequest = 0, segmentRequest = 0;
    std::string keyUri, initKey;
    unsigned attempts = 0;
    double retryAt = 0;
    double started = 0;   // when the media request went out
};

struct Session::Loader {
    bool isMain = true;
    std::string url, base;                  // playlist URL; base for its relative URIs (after redirects)
    Media media;
    bool loaded = false, positioned = false, finished = false;
    uint64_t playlistRequest = 0;
    unsigned playlistFailures = 0;
    double nextRefresh = 0;
    uint64_t nextSeq = 0;
    std::map<uint64_t, double> starts;      // media sequence -> start on the session timeline
    Pending pending;
    int64_t lastPts90k = std::numeric_limits<int64_t>::min();
    double startOf(const Segment& s) const { auto it = starts.find(s.sequence); return it != starts.end() ? it->second : s.start; }
    int indexOf(uint64_t seq) const
    {
        if (media.segments.empty() || seq < media.segments.front().sequence) return -1;
        uint64_t i = seq - media.segments.front().sequence;
        return i < media.segments.size() ? int(i) : int(media.segments.size());
    }
    // The segment holding time t; segments.size() past the end, -1 when empty.
    int indexAt(double t) const
    {
        for (size_t i = 0; i < media.segments.size(); i++) {
            double s = startOf(media.segments[i]);
            if (t < s + media.segments[i].duration - 1e-3) return int(i);
        }
        return media.segments.empty() ? -1 : int(media.segments.size());
    }
    // The same, never past the last segment (start positions, seeks).
    int indexAtClamped(double t) const
    {
        int i = indexAt(t);
        return i < 0 ? -1 : std::min(i, int(media.segments.size()) - 1);
    }
};

bool codecPlayable(const std::string& raw, bool hardware)
{
    std::string codec;
    for (char c : raw) if (c != ' ' && c != '"') codec += c;
    const std::string low = Caps::lowered(codec);
    if (low.empty() || low == "wvtt" || low == "stpp" || low.rfind("stpp.", 0) == 0) return true;
    if (Caps::avc1Supported(codec) || Caps::aacSupported(codec)) return true;
    if (Caps::opusCodec(codec)) return true;   // fMP4 'Opus' (FFmpeg's native decoder)
    if (Caps::parseHevc(codec)) {
        auto h = Caps::parseHevc(codec);
        return hardware && hevcEnabled() && (h->profile == 1 || h->profile == 2) && h->level <= 153;
    }
    return false;
}
bool variantPlayable(const Variant& v, bool hardware)
{
    bool hevc = false;
    std::string list = v.codecs;
    for (size_t at = 0; !list.empty() && at <= list.size();) {
        size_t comma = list.find(',', at);
        std::string one;
        for (char c : list.substr(at, comma == std::string::npos ? std::string::npos : comma - at)) if (c != ' ') one += c;
        if (!codecPlayable(one, hardware)) return false;
        hevc = hevc || Caps::parseHevc(Caps::lowered(one)).has_value();
        if (comma == std::string::npos) break;
        at = comma + 1;
    }
    const int64_t maxPixels = hevc ? int64_t(3840) * 2160 : int64_t(1920) * 1080;
    return int64_t(v.width) * v.height <= maxPixels && v.width <= (hevc ? 3840 : 4096) && v.height <= (hevc ? 2160 : 4096);
}

Session::Session(Fetcher& f, Options o) : fetcher_(f), options_(std::move(o)) { }
Session::~Session()
{
    for (auto* l : { main_.get(), audio_.get() }) {
        if (!l) continue;
        for (auto id : { l->playlistRequest, l->pending.keyRequest, l->pending.initRequest, l->pending.segmentRequest })
            if (id) fetcher_.cancel(id);
    }
    if (masterRequest_) fetcher_.cancel(masterRequest_);
}

void Session::fail(const std::string& why)
{
    if (error_.empty()) { error_ = why; say("error: " + why); }
}
void Session::say(const std::string& s) const { if (options_.log) options_.log(s); }
std::string Session::resolve(const std::string& base, const std::string& ref) const
{
    return options_.resolve ? options_.resolve(base, ref) : Hls::resolve(base, ref);
}
uint64_t Session::request(const std::string& url, int64_t offset, int64_t length)
{
    uint64_t id = nextId_++;
    fetcher_.fetch(id, url, offset, length);
    return id;
}

void Session::start(const std::string& url)
{
    masterUrl_ = url;
    masterRequest_ = request(url, -1, -1);
}

bool Session::live() const { return main_ && main_->loaded && main_->media.live(); }
double Session::duration() const
{
    if (!main_ || !main_->loaded) return 0;
    return live() ? std::numeric_limits<double>::infinity() : main_->media.duration();
}
double Session::seekableStart() const
{
    if (!main_ || !main_->loaded || main_->media.segments.empty()) return 0;
    return main_->startOf(main_->media.segments.front());
}
double Session::seekableEnd() const
{
    if (!main_ || !main_->loaded || main_->media.segments.empty()) return 0;
    auto& last = main_->media.segments.back();
    double end = main_->startOf(last) + last.duration;
    return live() ? std::max(seekableStart(), end - 3 * main_->media.targetDuration) : end;
}
double Session::queuedEnd(Kind k) const { return queuedEnd_[k == Kind::Video ? 0 : 1]; }
double Session::bufferedEnd() const
{
    if (hasVideo_ && hasAudio_) return std::min(queuedEnd_[0], queuedEnd_[1]);
    return hasVideo_ ? queuedEnd_[0] : queuedEnd_[1];
}
size_t Session::queuedBytes() const { return queuedBytes_[0] + queuedBytes_[1]; }
bool Session::ready() const
{
    // Playable from the start position: every kind there will be has media queued past it (one
    // second, or less when the stream ends sooner).
    if (!hasVideo_ && !hasAudio_) return false;
    if (audio_ && !hasAudio_) return false;   // the rendition's first segment is still on its way
    return ended() || bufferedEnd() >= startPosition_ + 1.0;
}
bool Session::ended() const
{
    return main_ && main_->finished && !main_->pending.active && (!audio_ || (audio_->finished && !audio_->pending.active));
}
bool Session::next(Kind k, DemuxPacket& out)
{
    auto& q = queue_[k == Kind::Video ? 0 : 1];
    if (q.empty()) return false;
    out = std::move(q.front());
    q.pop_front();
    queuedBytes_[k == Kind::Video ? 0 : 1] -= out.bytes.size();
    return true;
}
const DemuxPacket* Session::peek(Kind k) const
{
    auto& q = queue_[k == Kind::Video ? 0 : 1];
    return q.empty() ? nullptr : &q.front();
}
const DemuxTrack* Session::configuration(Kind k, uint32_t id) const
{
    auto& c = configs_[k == Kind::Video ? 0 : 1];
    return id >= 1 && id <= c.size() ? &c[id - 1] : nullptr;
}

void Session::fetched(uint64_t id, bool ok, std::vector<uint8_t>&& bytes, const std::string& finalUrl, double secs)
{
    if (!error_.empty() || !id) return;
    if (id == masterRequest_) {
        masterRequest_ = 0;
        if (!ok) { fail("playlist could not be loaded"); return; }
        if (bytes.size() > maxPlaylistBytes) { fail("playlist too large"); return; }
        std::string text(bytes.begin(), bytes.end());
        const std::string base = finalUrl.empty() ? masterUrl_ : finalUrl;
        switch (classify(text)) {
        case PlaylistKind::Master: {
            std::string why;
            if (!parseMaster(text, master_, why)) { fail(why); return; }
            for (auto& v : master_.variants) v.uri = resolve(base, v.uri);
            for (auto& r : master_.audio) if (!r.uri.empty()) r.uri = resolve(base, r.uri);
            isMaster_ = true;
            chooseVariant(0, true);
            break;
        }
        case PlaylistKind::Media:
            main_ = std::make_unique<Loader>();
            main_->url = masterUrl_;
            playlistLoaded(*main_, text, base);
            break;
        case PlaylistKind::Invalid:
            fail("not an HLS playlist");
            break;
        }
        return;
    }
    for (auto* l : { main_.get(), audio_.get() }) {
        if (!l) continue;
        if (id == l->playlistRequest) {
            l->playlistRequest = 0;
            if (!ok || bytes.size() > maxPlaylistBytes) {
                if (++l->playlistFailures > 4) fail("media playlist could not be loaded");
                l->nextRefresh = lastNow_ + 1.0 * l->playlistFailures;
                return;
            }
            l->playlistFailures = 0;
            playlistLoaded(*l, std::string(bytes.begin(), bytes.end()), finalUrl.empty() ? l->url : finalUrl);
            return;
        }
        auto& p = l->pending;
        if (!p.active) continue;
        auto retry = [&](const char* what) {
            p.keyRequest = p.initRequest = p.segmentRequest = 0;
            if (++p.attempts >= 3) {
                if (l->media.live()) {   // skip it: the stream goes on
                    say(std::string("segment skipped after 3 failures (") + what + ")");
                    p.active = false;
                    l->nextSeq = p.segment.sequence + 1;
                } else fail(std::string("segment could not be loaded: ") + what);
                return;
            }
            p.retryAt = lastNow_ + 0.5 * p.attempts;
        };
        if (id == p.keyRequest) {
            p.keyRequest = 0;
            if (!ok || bytes.size() != 16) { retry("key"); return; }
            keys_[p.keyUri] = std::move(bytes);
            continueSegment(*l);
            return;
        }
        if (id == p.initRequest) {
            p.initRequest = 0;
            if (!ok || bytes.empty() || bytes.size() > 4 * 1024 * 1024) { retry("init section"); return; }
            inits_[p.initKey] = std::move(bytes);
            continueSegment(*l);
            return;
        }
        if (id == p.segmentRequest) {
            p.segmentRequest = 0;
            if (!ok || bytes.empty() || bytes.size() > maxSegmentBytes) { retry("media"); return; }
            segmentLoaded(*l, std::move(bytes), secs);
            return;
        }
    }
}

void Session::playlistLoaded(Loader& l, const std::string& text, const std::string& finalUrl)
{
    Media m;
    std::string why;
    if (classify(text) != PlaylistKind::Media || !parseMedia(text, m, why)) { fail("media playlist: " + (why.empty() ? std::string("not a media playlist") : why)); return; }
    l.base = finalUrl;
    for (auto& s : m.segments) s.uri = resolve(finalUrl, s.uri);
    for (auto& k : m.keys) if (!k.uri.empty()) k.uri = resolve(finalUrl, k.uri);
    for (auto& i : m.maps) i.uri = resolve(finalUrl, i.uri);
    for (auto& k : m.keys)
        if (k.method == Key::Method::SampleAes || k.method == Key::Method::Other) { fail("encrypted with SAMPLE-AES / unknown method (FairPlay or similar): not playable"); return; }
    // Timeline: keep every known segment where it was (live refresh, variant switch by sequence);
    // a playlist with nothing in common continues where the known timeline ended.
    const bool hadPlaylist = l.loaded;
    const uint64_t lastBefore = hadPlaylist && !l.media.segments.empty() ? l.media.segments.back().sequence : 0;
    double base = 0;
    bool anchored = false;
    for (auto& s : m.segments) {
        auto it = l.starts.find(s.sequence);
        if (it != l.starts.end()) { base = it->second - s.start; anchored = true; break; }
    }
    if (!anchored && hadPlaylist && !l.starts.empty() && !m.segments.empty()) {
        auto last = std::prev(l.starts.end());
        const auto lastSeg = std::find_if(l.media.segments.begin(), l.media.segments.end(), [&](const Segment& s) { return s.sequence == last->first; });
        base = last->second + (lastSeg != l.media.segments.end() ? lastSeg->duration : 0) - m.segments.front().start;
        say(fmt("playlist refresh shares no segment with the last one; continuing at %.3f s", base));
    }
    for (auto& s : m.segments) l.starts[s.sequence] = s.start + base;
    while (!m.segments.empty() && l.starts.size() > m.segments.size() + 64) l.starts.erase(l.starts.begin());
    const bool grew = !hadPlaylist || m.segments.empty() || m.segments.back().sequence != lastBefore;
    l.media = std::move(m);
    l.loaded = true;
    if (l.media.live()) l.nextRefresh = lastNow_ + (grew ? l.media.targetDuration : l.media.targetDuration / 2);
    if (!l.media.live() || l.media.endList) l.finished = false;

    if (l.isMain && pendingVariant_ >= 0) {   // a variant switch: continue where the queue ends
        variant_ = pendingVariant_;
        pendingVariant_ = -1;
        ++switches_;
        if (!l.media.live()) {
            int idx = l.indexAt(queuedEnd(hasVideo_ ? Kind::Video : Kind::Audio) + 0.05);
            if (idx >= int(l.media.segments.size())) l.nextSeq = l.media.segments.back().sequence + 1;   // all fetched
            else if (idx >= 0) l.nextSeq = l.media.segments[size_t(idx)].sequence;
        }
        say(fmt("variant %.0f (%.0f bit/s) from segment %.0f", variant_, double(master_.variants[size_t(variant_)].bandwidth), double(l.nextSeq)));
    }
    position(l);
}

// Where a loader starts: the main playlist at EXT-X-START, the live edge (RFC 8216 6.3.3: no
// closer than three target durations to the end) or the seek target; a rendition where the main
// playlist starts (same media sequence when live: renditions are sequence-aligned; else by time).
void Session::position(Loader& l)
{
    if (l.positioned || !l.loaded || l.media.segments.empty()) return;
    if (!l.isMain && (!main_ || !main_->positioned)) return;   // wait for the main playlist
    size_t idx = 0;
    if (l.isMain) {
        if (l.media.hasStart) {
            double t = l.media.startOffset >= 0 ? l.media.startOffset : l.media.duration() + l.media.startOffset;
            idx = size_t(std::max(0, l.indexAtClamped(std::max(0.0, t))));
        } else if (l.media.live()) {
            double fromEnd = 0;
            idx = l.media.segments.size();
            while (idx > 0 && fromEnd < 3 * l.media.targetDuration) fromEnd += l.media.segments[--idx].duration;
        }
        if (seekTarget_ >= 0) idx = size_t(std::max(0, l.indexAtClamped(seekTarget_)));
        startPosition_ = seekTarget_ >= 0 ? seekTarget_ : l.startOf(l.media.segments[idx]);
        say(std::string(l.media.live() ? "live" : "VOD") + " playlist, " + std::to_string(l.media.segments.size())
            + " segments, starting at segment " + std::to_string(l.media.segments[idx].sequence) + fmt(" (%.3f s)", startPosition_));
    } else {
        const int bySeq = l.indexOf(main_->nextSeq), byTime = l.indexAtClamped(startPosition_);
        idx = size_t(l.media.live() && bySeq >= 0 && bySeq < int(l.media.segments.size()) ? bySeq : std::max(0, byTime));
    }
    l.nextSeq = l.media.segments[idx].sequence;
    l.positioned = true;
}

void Session::chooseVariant(double playhead, bool initial)
{
    if (!isMaster_) return;
    std::vector<int> playable;
    for (size_t i = 0; i < master_.variants.size(); i++)
        if (!options_.playable || options_.playable(master_.variants[i])) playable.push_back(int(i));
    if (playable.empty()) { fail("no variant this player can decode"); return; }
    int choice;
    if (initial) {
        choice = playable.front();   // RFC 8216 6.3.1: the first listed variant starts
    } else {
        if (main_ && !main_->media.live() && main_->indexOf(main_->nextSeq) >= int(main_->media.segments.size())) return;   // all fetched
        std::sort(playable.begin(), playable.end(), [&](int a, int b) { return master_.variants[size_t(a)].bandwidth < master_.variants[size_t(b)].bandwidth; });
        choice = playable.front();
        for (int v : playable)
            if (double(master_.variants[size_t(v)].bandwidth) <= estimate_ * options_.safety) choice = v;
        const auto& cur = master_.variants[size_t(variant_)];
        const auto& next = master_.variants[size_t(choice)];
        const double ahead = queuedEnd(hasVideo_ ? Kind::Video : Kind::Audio) - playhead;
        // Build a buffer before going up; live cannot buffer more than the window allows.
        double need = std::min(options_.upSwitchBuffer, 0.8 * options_.forwardSeconds);
        if (live()) need = std::min(need, 2 * main_->media.targetDuration);
        if (next.bandwidth > cur.bandwidth && ahead < need) return;
        if (choice == variant_) return;
    }
    switchTo(choice);
}

void Session::switchTo(int v)
{
    const auto& var = master_.variants[size_t(v)];
    // The audio rendition of the variant's group (DEFAULT, else the first with a URI).
    const Rendition* rendition = nullptr;
    if (!var.audioGroup.empty())
        for (auto& r : master_.audio)
            if (r.groupId == var.audioGroup && !r.uri.empty() && (!rendition || (r.isDefault && !rendition->isDefault))) rendition = &r;
    if (!main_) {
        main_ = std::make_unique<Loader>();
        main_->url = var.uri;
        variant_ = v;
        main_->playlistRequest = request(var.uri, -1, -1);
        say(fmt("variant %.0f of %.0f (%.0f bit/s)", v, double(master_.variants.size()), double(var.bandwidth)));
    } else {
        if (main_->playlistRequest) fetcher_.cancel(main_->playlistRequest);
        main_->url = var.uri;
        pendingVariant_ = v;
        main_->playlistRequest = request(var.uri, -1, -1);
    }
    if (rendition && (!audio_ || audio_->url != rendition->uri)) {
        auto previous = std::move(audio_);
        audio_ = std::make_unique<Loader>();
        audio_->isMain = false;
        audio_->url = rendition->uri;
        if (previous) {   // keep its timeline; continue after what is queued
            for (auto id : { previous->playlistRequest, previous->pending.keyRequest, previous->pending.initRequest, previous->pending.segmentRequest })
                if (id) fetcher_.cancel(id);
            audio_->starts = previous->starts;
        }
        audio_->playlistRequest = request(rendition->uri, -1, -1);
    }
}

void Session::tick(double now, double playhead)
{
    lastNow_ = now;
    lastPlayhead_ = playhead;
    if (!error_.empty()) return;
    for (auto* l : { main_.get(), audio_.get() })
        if (l) scheduleLoader(*l, now, playhead);
}

bool Session::kindNeeded(const Loader& l, Kind k) const
{
    if (k == Kind::Audio && l.isMain && audio_) return false;   // the rendition carries the audio
    if (k == Kind::Video && !l.isMain) return false;
    return true;
}

void Session::scheduleLoader(Loader& l, double now, double playhead)
{
    if (!l.playlistRequest && (!l.loaded || (l.media.live() && now >= l.nextRefresh)))
        if (!l.loaded || !l.media.endList) l.playlistRequest = request(l.url, -1, -1);
    position(l);
    if (!l.loaded || !l.positioned) return;
    if (l.pending.active) {
        auto& p = l.pending;
        if (!p.keyRequest && !p.initRequest && !p.segmentRequest && now >= p.retryAt) continueSegment(l);
        // Emergency down-switch (as hls.js does): the main segment in flight takes longer than its
        // own duration and than what is left in the buffer, and a lower variant exists: drop the
        // request and fetch the same segment from the variant the observed rate can carry.
        if (l.isMain && isMaster_ && p.segmentRequest && pendingVariant_ < 0 && variant_ >= 0) {
            const double elapsed = now - p.started;
            const double ahead = queuedEnd(hasVideo_ ? Kind::Video : Kind::Audio) - playhead;
            const auto& cur = master_.variants[size_t(variant_)];
            int lower = -1;
            for (size_t i = 0; i < master_.variants.size(); i++) {
                const auto& v = master_.variants[i];
                if (v.bandwidth < cur.bandwidth && (!options_.playable || options_.playable(v)) && (lower < 0 || v.bandwidth > master_.variants[size_t(lower)].bandwidth)
                    && double(v.bandwidth) <= double(cur.bandwidth) * p.segment.duration / std::max(elapsed, 0.001) * options_.safety)
                    lower = int(i);
            }
            if (lower < 0)   // nothing fits the observed rate: the lowest playable one
                for (size_t i = 0; i < master_.variants.size(); i++)
                    if (master_.variants[i].bandwidth < cur.bandwidth && (!options_.playable || options_.playable(master_.variants[i]))
                        && (lower < 0 || master_.variants[i].bandwidth < master_.variants[size_t(lower)].bandwidth)) lower = int(i);
            if (lower >= 0 && elapsed > std::max(1.5 * p.segment.duration, 1.0) && elapsed > ahead) {
                fetcher_.cancel(p.segmentRequest);
                say(fmt("segment %.0f is taking %.1f s with %.1f s buffered: abandoned, down-switching", double(p.segment.sequence), elapsed, ahead));
                estimate_ = std::min(estimate_ > 0 ? estimate_ : 1e300, double(cur.bandwidth) * p.segment.duration / elapsed);
                l.nextSeq = p.segment.sequence;
                p = {};
                switchTo(lower);
            }
        }
        return;
    }
    if (l.isMain && pendingVariant_ >= 0) return;
    const Kind kind = l.isMain ? (hasVideo_ || !hasAudio_ ? Kind::Video : Kind::Audio) : Kind::Audio;
    const double end = l.isMain && !hasVideo_ && !hasAudio_ ? 0 : queuedEnd(kind);
    if (end - playhead >= options_.forwardSeconds || queuedBytes() >= options_.forwardBytes) return;
    int idx = l.indexOf(l.nextSeq);
    if (idx < 0) {   // the live window moved past us
        say(fmt("fell behind the live window (segment %.0f gone); jumping to %.0f", double(l.nextSeq), double(l.media.segments.front().sequence)));
        idx = 0;
        l.nextSeq = l.media.segments.front().sequence;
    }
    if (size_t(idx) >= l.media.segments.size()) {
        if (!l.media.live()) l.finished = true;
        return;   // live: wait for the refresh
    }
    startSegment(l, size_t(idx));
}

void Session::startSegment(Loader& l, size_t index)
{
    auto& p = l.pending;
    p = {};
    p.active = true;
    p.index = index;
    p.segment = l.media.segments[index];
    continueSegment(l);
}

void Session::continueSegment(Loader& l)
{
    auto& p = l.pending;
    const auto& s = p.segment;
    if (s.key >= 0 && size_t(s.key) < l.media.keys.size()) {
        p.keyUri = l.media.keys[size_t(s.key)].uri;
        if (!keys_.count(p.keyUri)) { p.keyRequest = request(p.keyUri, -1, -1); return; }
    }
    if (s.map >= 0 && size_t(s.map) < l.media.maps.size()) {
        const auto& m = l.media.maps[size_t(s.map)];
        p.initKey = m.uri + "#" + std::to_string(m.offset) + ":" + std::to_string(m.length);
        if (!inits_.count(p.initKey)) { p.initRequest = request(m.uri, m.offset, m.length); return; }
    }
    p.segmentRequest = request(s.uri, s.offset, s.length);
    p.started = lastNow_;
}

void Session::segmentLoaded(Loader& l, std::vector<uint8_t>&& bytes, double secs)
{
    auto& p = l.pending;
    const Segment seg = p.segment;
    p.active = false;
    l.nextSeq = seg.sequence + 1;
    if (seg.key >= 0) {
        const auto& k = l.media.keys[size_t(seg.key)];
        uint8_t iv[16] = {};
        if (k.hasIv) std::copy(k.iv, k.iv + 16, iv);
        else for (int i = 0; i < 8; i++) iv[15 - i] = uint8_t(seg.sequence >> (8 * i));   // RFC 8216 5.2
        if (!decryptAes128(bytes, keys_[p.keyUri].data(), iv)) { fail("AES-128 decryption failed (wrong key or IV)"); return; }
    }
    // Throughput (main playlist only; tiny segments say little): two moving averages weighted by
    // media duration (half-lives 3 s and 9 s, as hls.js does), the smaller one counts; a segment
    // that arrived slower than its variant's bitrate counts at once (the network dropped).
    if (l.isMain && secs > 0.02 && bytes.size() > 16 * 1024) {
        const double sample = double(bytes.size()) * 8 / secs;
        const double weight = std::max(0.1, seg.duration);
        if (fast_ <= 0) fast_ = slow_ = sample;
        else {
            const double af = std::pow(0.5, weight / 3), as = std::pow(0.5, weight / 9);
            fast_ = af * fast_ + (1 - af) * sample;
            slow_ = as * slow_ + (1 - as) * sample;
        }
        estimate_ = std::min(fast_, slow_);
        if (variant_ >= 0 && size_t(variant_) < master_.variants.size() && sample < double(master_.variants[size_t(variant_)].bandwidth))
            estimate_ = std::min(estimate_, sample);
    }
    Demuxed d;
    bool ok;
    switch (sniff(bytes)) {
    case Container::TransportStream: ok = demuxTransportStream(bytes, d); break;
    case Container::PackedAudio: ok = demuxPackedAudio(bytes, d); break;
    case Container::Fmp4: {
        auto it = inits_.find(p.initKey);
        if (seg.map < 0 || it == inits_.end()) { fail("fMP4 segment without EXT-X-MAP"); return; }
        ok = demuxFmp4(it->second, bytes, d);
        break;
    }
    default:
        fail("unknown segment format (not MPEG-TS, ADTS or fMP4)");
        return;
    }
    if (!ok) {
        if (l.media.live()) { say("segment " + std::to_string(seg.sequence) + " not demuxable (" + d.error + "); skipped"); return; }
        fail("segment " + std::to_string(seg.sequence) + ": " + d.error);
        return;
    }
    // ---- timeline -------------------------------------------------------------------------
    const double segStart = l.startOf(seg);
    std::map<int64_t, Kind> kindOf;
    for (auto& t : d.tracks) kindOf[t.id] = isVideoCodec(t.codec) ? Kind::Video : Kind::Audio;
    // 33-bit wrap (MPEG-TS / packed audio): bring the segment next to the previous one.
    if (!d.tracks.empty() && d.tracks.front().timeBase.denominator == 90000 && d.timestamped && !d.packets.empty()) {
        int64_t first = d.packets.front().dts;
        if (l.lastPts90k != std::numeric_limits<int64_t>::min()) {
            int64_t k = (l.lastPts90k - first + kWrap / 2) >= 0 ? (l.lastPts90k - first + kWrap / 2) / kWrap : -((first - l.lastPts90k + kWrap / 2 - 1) / kWrap);
            if (k)
                for (auto& pk : d.packets) { pk.pts += k * kWrap; pk.dts += k * kWrap; }
        }
        for (auto& pk : d.packets) l.lastPts90k = std::max(l.lastPts90k, pk.dts + pk.duration);
    }
    double firstTime = std::numeric_limits<double>::infinity();
    for (auto& pk : d.packets) {
        auto it = kindOf.find(pk.trackId);
        if (it == kindOf.end() || !kindNeeded(l, it->second)) continue;
        firstTime = std::min(firstTime, seconds(pk.pts, pk.timeBase));
    }
    if (!std::isfinite(firstTime)) return;   // nothing this loader needs
    double offset;
    if (!d.timestamped) {
        offset = segStart - firstTime;   // packed audio without a timestamp: the playlist time
    } else {
        auto known = offsets_.find(seg.discontinuity);
        if (known == offsets_.end()) {
            offset = segStart - firstTime;
            offsets_[seg.discontinuity] = offset;
        } else {
            offset = known->second;
            const double tolerance = std::max(4.0, 2 * l.media.targetDuration);
            if (l.isMain && std::fabs(firstTime + offset - segStart) > tolerance) {
                say(fmt("timestamps %.3f s away from the playlist time %.3f s: realigned", firstTime + offset - segStart, segStart));
                offset = segStart - firstTime;
                offsets_[seg.discontinuity] = offset;
            }
        }
    }
    // ---- configurations + queues ------------------------------------------------------------
    std::map<int64_t, uint32_t> configOf;
    for (auto t : d.tracks) {
        Kind k = kindOf[t.id];
        if (!kindNeeded(l, k)) continue;
        const int64_t originalId = t.id;
        t.id = k == Kind::Video ? 1 : 2;
        auto& c = configs_[k == Kind::Video ? 0 : 1];
        uint32_t id = 0;
        for (size_t i = 0; i < c.size() && !id; i++) if (sameDecoderConfiguration(c[i], t)) id = uint32_t(i + 1);
        if (!id) {
            if (c.size() >= 64) { fail("too many decoder configurations"); return; }
            c.push_back(t);
            id = uint32_t(c.size());
        }
        configOf[originalId] = id;
        (k == Kind::Video ? hasVideo_ : hasAudio_) = true;
    }
    for (auto& pk : d.packets) {
        auto it = kindOf.find(pk.trackId);
        if (it == kindOf.end() || !kindNeeded(l, it->second)) continue;
        const Kind k = it->second;
        const int q = k == Kind::Video ? 0 : 1;
        pk.configuration = configOf[pk.trackId];
        pk.trackId = k == Kind::Video ? 1 : 2;
        const int64_t shift = ticks(offset, pk.timeBase);
        pk.pts += shift; pk.dts += shift;
        const double start = seconds(pk.pts, pk.timeBase), end = start + seconds(pk.duration, pk.timeBase);
        // Audio already queued from the previous segment (a variant switch: each variant's encoder
        // cut its own AAC frames at the boundary): drop what lies entirely before the queued end.
        if (k == Kind::Audio && end <= queuedEnd_[1] + 1e-4) continue;
        if (seekTarget_ >= 0) {
            if (k == Kind::Audio && end <= seekTarget_) continue;   // before the seek target: never heard
            if (k == Kind::Video && end <= seekTarget_) pk.nonDisplaying = true;   // decoded for reference only
        }
        queuedEnd_[q] = std::max(queuedEnd_[q], end);
        queuedBytes_[q] += pk.bytes.size();
        queue_[q].push_back(std::move(pk));
    }
    if (l.isMain && isMaster_ && error_.empty()) chooseVariant(lastPlayhead_, false);
}

bool Session::seek(double t)
{
    if (!main_ || !main_->loaded) { seekTarget_ = t; return true; }
    t = std::clamp(t, seekableStart(), std::max(seekableStart(), live() ? seekableEnd() : duration()));
    for (auto* l : { main_.get(), audio_.get() }) {
        if (!l) continue;
        for (auto id : { l->pending.keyRequest, l->pending.initRequest, l->pending.segmentRequest })
            if (id) fetcher_.cancel(id);
        l->pending = {};
        l->finished = false;
        if (l->loaded && !l->media.segments.empty()) {
            int idx = l->indexAtClamped(t);
            l->nextSeq = l->media.segments[size_t(std::max(0, idx))].sequence;
        }
    }
    for (int q = 0; q < 2; q++) { queue_[q].clear(); queuedBytes_[q] = 0; queuedEnd_[q] = t; }
    seekTarget_ = t;
    say(fmt("seek to %.3f s", t));
    return true;
}

}
