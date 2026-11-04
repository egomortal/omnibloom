// HLS playlists (RFC 8216) for Omni's native HLS player (OMNI_HLS_NATIVE_V1).
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Pure C++17: no I/O, no WebKit, no FFmpeg. Master playlists (EXT-X-STREAM-INF variants,
// EXT-X-MEDIA audio renditions) and media playlists (EXTINF, EXT-X-BYTERANGE, EXT-X-MAP,
// EXT-X-KEY, EXT-X-DISCONTINUITY, EXT-X-MEDIA-SEQUENCE, EXT-X-DISCONTINUITY-SEQUENCE,
// EXT-X-TARGETDURATION, EXT-X-ENDLIST, EXT-X-PLAYLIST-TYPE, EXT-X-START). Unknown tags are
// ignored, as the RFC requires (4.1); low-latency parts (EXT-X-PART) are ignored: the full
// segments they belong to are listed too.
#pragma once
#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace OmniMedia::Hls {

// Attribute list (RFC 8216 4.2): KEY=value pairs, quoted strings may contain commas.
std::map<std::string, std::string> parseAttributes(std::string_view);

struct Variant {
    uint64_t bandwidth = 0, averageBandwidth = 0;
    int width = 0, height = 0;
    double frameRate = 0;
    std::string codecs, uri, audioGroup;
};
struct Rendition {   // EXT-X-MEDIA TYPE=AUDIO
    std::string groupId, name, language, uri;   // uri empty: the audio is in the variant's segments
    bool isDefault = false, autoSelect = false;
};
struct Master {
    std::vector<Variant> variants;
    std::vector<Rendition> audio;
    bool independentSegments = false;
};

struct Key {
    enum class Method { None, Aes128, SampleAes, Other } method = Method::None;
    std::string uri;
    bool hasIv = false;
    uint8_t iv[16] = {};
};
struct InitSection { std::string uri; int64_t offset = -1, length = -1; };   // EXT-X-MAP
struct Segment {
    double duration = 0;
    std::string uri;
    int64_t offset = -1, length = -1;     // EXT-X-BYTERANGE (offset resolved), -1 = whole resource
    uint64_t sequence = 0;                // media sequence number
    uint64_t discontinuity = 0;           // discontinuity sequence number
    int key = -1;                         // index into Media::keys, -1 = clear
    int map = -1;                         // index into Media::maps, -1 = none (MPEG-TS / packed audio)
    double start = 0;                     // sum of the earlier EXTINF durations in this playlist
};
struct Media {
    double targetDuration = 0;
    uint64_t mediaSequence = 0, discontinuitySequence = 0;
    bool endList = false;
    std::string playlistType;             // "", "VOD", "EVENT"
    double startOffset = 0; bool hasStart = false;   // EXT-X-START TIME-OFFSET
    std::vector<Segment> segments;
    std::vector<Key> keys;
    std::vector<InitSection> maps;
    double duration() const { return segments.empty() ? 0 : segments.back().start + segments.back().duration; }
    bool live() const { return !endList && playlistType != "VOD"; }
};

enum class PlaylistKind { Master, Media, Invalid };
// Which kind a document is (#EXTM3U first; EXT-X-STREAM-INF -> master; EXTINF -> media).
PlaylistKind classify(std::string_view text);
bool parseMaster(std::string_view text, Master&, std::string& error);
bool parseMedia(std::string_view text, Media&, std::string& error);

// RFC 3986 5.2 reference resolution (absolute, scheme-relative, absolute-path, relative path with
// dot segments, query-only). The player uses WebKit's URL instead; this is the host tests' resolver
// and the fallback.
std::string resolve(const std::string& base, const std::string& reference);

// MIME types that mean "an HLS playlist" (RFC 8216 4 + the legacy names players still send).
bool isHlsMimeType(std::string_view lowercaseType);

}
