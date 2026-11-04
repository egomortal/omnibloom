// Native HLS session for Omni's plain media player (OMNI_HLS_NATIVE_V1).
// SPDX-License-Identifier: GPL-3.0-or-later
//
// What Safari does for <video src="...m3u8">, without WebKit types so the host tests drive it:
//   * master playlist -> variant choice (first playable, then by measured throughput with a
//     safety margin and hysteresis; switches at segment boundaries), alternate audio renditions
//     (EXT-X-MEDIA TYPE=AUDIO with a URI) loaded as a second playlist;
//   * media playlists: VOD and EVENT/live (start 3 target durations from the live edge, refresh
//     every target duration, follow the media sequence, jump forward when the window passed us);
//   * segments: MPEG-TS, packed AAC, fMP4 (EXT-X-MAP), byte ranges, AES-128 (keys fetched like
//     everything else, cached per URI), discontinuities;
//   * one presentation timeline in seconds: media timestamps plus an offset per discontinuity
//     sequence (shared by all variants and renditions, as RFC 8216 6.2.4 requires them to be
//     aligned), 33-bit PTS wrap handled;
//   * output: demux packets per kind (video / audio) in decode order, each tagged with a decoder
//     configuration id (a variant switch or a new SPS gives a new one, as an MSE init does).
// All I/O goes through Fetcher, which the player implements with WebKit's media resource loader
// (cookies, CORS mode, uBlock and the network process apply as to any media load).
#pragma once
#include "OmniHlsPlaylist.h"
#include "OmniHlsSegment.h"
#include "OmniMP4Demuxer.h"
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <unistd.h>
#include <vector>

namespace OmniMedia::Hls {

// ---- switches ------------------------------------------------------------------------------
// Native HLS on by default; kill switch /data/omni/hls-native-disabled.flag (host: OMNI_HLS_NATIVE=0/1).
inline bool nativeEnabled()
{
    if (const char* env = getenv("OMNI_HLS_NATIVE")) return env[0] == '1';
#ifdef __PROSPERO__
    return access("/data/omni/hls-native-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
// canPlayType("application/vnd.apple.mpegurl") answers "maybe" (Safari's answer) while native HLS
// is on. OMNI_HLS_RELAY_V1: by default, now that the player's audio goes through the UI-process
// relay; kill switch /data/omni/hls-native-advertise-disabled.flag (host: OMNI_HLS_ADVERTISE=0)
// makes it "" again, so pages that ask first choose hls.js + MSE. Loads (<video src>, <source
// type=...>) are accepted either way while native HLS is on.
inline bool nativeAdvertised()
{
    if (const char* env = getenv("OMNI_HLS_ADVERTISE")) return env[0] == '1';
#ifdef __PROSPERO__
    return access("/data/omni/hls-native-advertise-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
// One RFC 6381 codec of a variant's CODECS attribute, or of a type's codecs parameter: H.264
// (avc1, to the level the decoders take), AAC, Opus (fMP4), HEVC (hvc1/hev1, hardware only).
// Subtitle/caption codecs (wvtt, stpp) are ignored: they never reach a decoder.
bool codecPlayable(const std::string& codec, bool hardware);
// A variant: every codec playable (empty CODECS: assumed avc1 + mp4a) and its RESOLUTION within
// the decoders' limits (1920x1080 for H.264, 3840x2160 for HEVC).
bool variantPlayable(const Variant&, bool hardware);

class Fetcher {
public:
    virtual ~Fetcher() = default;
    // GET `url` (bytes [offset, offset + length) when length > 0). The result must come back
    // through Session::fetched(id, ...) later, never from inside fetch().
    virtual void fetch(uint64_t id, const std::string& url, int64_t offset, int64_t length) = 0;
    virtual void cancel(uint64_t id) = 0;
};

enum class Kind { Video, Audio };

struct Options {
    double forwardSeconds = 30;               // media fetched ahead of the playhead
    size_t forwardBytes = 48 * 1024 * 1024;   // and at most this much queued
    double safety = 0.75;                     // use this share of the measured throughput
    double upSwitchBuffer = 8;                // seconds buffered before switching up
    // A variant the decoders can take (codecs, size); default: every variant.
    std::function<bool(const Variant&)> playable;
    // URL resolution (the player passes WebKit's URL; default: Hls::resolve).
    std::function<std::string(const std::string&, const std::string&)> resolve;
    std::function<void(const std::string&)> log;
};

class Session {
public:
    Session(Fetcher&, Options = {});
    ~Session();
    Session(const Session&) = delete;
    Session& operator=(const Session&) = delete;

    void start(const std::string& url);
    // A fetch finished. `ok` false: network/HTTP failure. `finalUrl`: after redirects (the base
    // for relative URIs in a playlist). `seconds`: time from request to the last byte.
    void fetched(uint64_t id, bool ok, std::vector<uint8_t>&& bytes, const std::string& finalUrl, double seconds);
    // Drives playlist refreshes and segment fetches. `now`: a monotonic clock in seconds.
    void tick(double now, double playhead);
    // Seek within the seekable range: queues are dropped, fetching restarts at the segment that
    // holds `seconds`; video before it comes out as nonDisplaying, audio before it is dropped.
    bool seek(double seconds);

    bool next(Kind, DemuxPacket&);           // pops the next packet of that kind
    const DemuxPacket* peek(Kind) const;
    const DemuxTrack* configuration(Kind, uint32_t id) const;

    bool failed() const { return !error_.empty(); }
    const std::string& error() const { return error_; }
    bool ready() const;                      // tracks known and packets queued for each
    bool hasVideo() const { return hasVideo_; }
    bool hasAudio() const { return hasAudio_; }
    bool live() const;
    double duration() const;                 // VOD: playlist duration; live: +inf
    double seekableStart() const;
    double seekableEnd() const;
    double bufferedEnd() const;              // the smaller of the kinds' queued ends
    double startPosition() const { return startPosition_; }   // where playback should begin
    bool ended() const;                      // everything fetched and queued (ENDLIST)
    int variant() const { return variant_; }
    double bandwidthEstimate() const { return estimate_; }
    unsigned switches() const { return switches_; }
    size_t queuedBytes() const;
    const Master& master() const { return master_; }

private:
    struct Loader;
    struct Pending;
    void fail(const std::string&);
    void say(const std::string&) const;
    std::string resolve(const std::string& base, const std::string& ref) const;
    uint64_t request(const std::string& url, int64_t offset, int64_t length);
    void playlistLoaded(Loader&, const std::string& text, const std::string& finalUrl);
    void scheduleLoader(Loader&, double now, double playhead);
    void position(Loader&);
    void startSegment(Loader&, size_t index);
    void continueSegment(Loader&);
    void segmentLoaded(Loader&, std::vector<uint8_t>&& bytes, double seconds);
    void chooseVariant(double playhead, bool initial);
    void switchTo(int variant);
    double queuedEnd(Kind) const;
    bool kindNeeded(const Loader&, Kind) const;

    Fetcher& fetcher_;
    Options options_;
    std::string error_;
    std::string masterUrl_;
    Master master_;
    bool isMaster_ = false;
    int variant_ = -1, pendingVariant_ = -1;
    std::unique_ptr<Loader> main_, audio_;
    uint64_t nextId_ = 1;
    uint64_t masterRequest_ = 0;
    std::map<std::string, std::vector<uint8_t>> keys_;     // AES-128 key URI -> key
    std::map<std::string, std::vector<uint8_t>> inits_;    // EXT-X-MAP URI + range -> bytes
    std::map<uint64_t, double> offsets_;                   // discontinuity sequence -> seconds
    std::deque<DemuxPacket> queue_[2];
    size_t queuedBytes_[2] = { 0, 0 };
    double queuedEnd_[2] = { 0, 0 };
    std::vector<DemuxTrack> configs_[2];
    bool hasVideo_ = false, hasAudio_ = false;
    double estimate_ = 0, fast_ = 0, slow_ = 0;            // bits per second
    double lastNow_ = 0, lastPlayhead_ = 0;
    double seekTarget_ = -1;
    double startPosition_ = 0;
    unsigned switches_ = 0;
};

}
