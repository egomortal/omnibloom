// HLS playlists (OMNI_HLS_NATIVE_V1). SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniHlsPlaylist.h"
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <cstring>

namespace OmniMedia::Hls {
namespace {
std::string_view trim(std::string_view s)
{
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t' || s.front() == '\r')) s.remove_prefix(1);
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t' || s.back() == '\r')) s.remove_suffix(1);
    return s;
}
std::vector<std::string_view> lines(std::string_view text)
{
    std::vector<std::string_view> out;
    if (text.size() >= 3 && !memcmp(text.data(), "\xEF\xBB\xBF", 3)) text.remove_prefix(3);   // UTF-8 BOM
    size_t at = 0;
    while (at <= text.size()) {
        size_t end = text.find('\n', at);
        if (end == std::string_view::npos) end = text.size();
        auto line = trim(text.substr(at, end - at));
        if (!line.empty()) out.push_back(line);
        at = end + 1;
    }
    return out;
}
bool startsWith(std::string_view s, std::string_view p) { return s.substr(0, p.size()) == p; }
bool toDouble(std::string_view s, double& v)
{
    std::string t(s);
    char* end = nullptr;
    v = std::strtod(t.c_str(), &end);
    return end != t.c_str() && v >= 0 && v < 1e9;
}
bool toU64(std::string_view s, uint64_t& v)
{
    if (s.empty() || s.size() > 19) return false;
    v = 0;
    for (char c : s) {
        if (c < '0' || c > '9') return false;
        v = v * 10 + uint64_t(c - '0');
    }
    return true;
}
// "n[@o]" (EXT-X-BYTERANGE and EXT-X-MAP BYTERANGE).
bool byteRange(std::string_view s, int64_t& length, int64_t& offset)
{
    auto at = s.find('@');
    uint64_t n = 0, o = 0;
    if (!toU64(s.substr(0, at), n) || n == 0 || n > (1ull << 40)) return false;
    length = int64_t(n);
    offset = -1;
    if (at != std::string_view::npos) {
        if (!toU64(s.substr(at + 1), o) || o > (1ull << 50)) return false;
        offset = int64_t(o);
    }
    return true;
}
int hex(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }
}

std::map<std::string, std::string> parseAttributes(std::string_view s)
{
    std::map<std::string, std::string> out;
    size_t at = 0;
    while (at < s.size()) {
        while (at < s.size() && (s[at] == ' ' || s[at] == ',')) ++at;
        size_t eq = s.find('=', at);
        if (eq == std::string_view::npos) break;
        std::string key(trim(s.substr(at, eq - at)));
        at = eq + 1;
        std::string value;
        if (at < s.size() && s[at] == '"') {
            size_t close = s.find('"', at + 1);
            if (close == std::string_view::npos) close = s.size();
            value = std::string(s.substr(at + 1, close - at - 1));
            at = close + 1;
            while (at < s.size() && s[at] != ',') ++at;
        } else {
            size_t comma = s.find(',', at);
            if (comma == std::string_view::npos) comma = s.size();
            value = std::string(trim(s.substr(at, comma - at)));
            at = comma;
        }
        if (!key.empty()) out[key] = value;
    }
    return out;
}

PlaylistKind classify(std::string_view text)
{
    auto ls = lines(text);
    if (ls.empty() || !startsWith(ls[0], "#EXTM3U")) return PlaylistKind::Invalid;
    for (auto l : ls) {
        if (startsWith(l, "#EXT-X-STREAM-INF")) return PlaylistKind::Master;
        if (startsWith(l, "#EXTINF") || startsWith(l, "#EXT-X-TARGETDURATION")) return PlaylistKind::Media;
    }
    return PlaylistKind::Invalid;
}

bool parseMaster(std::string_view text, Master& m, std::string& error)
{
    m = {};
    auto ls = lines(text);
    if (ls.empty() || !startsWith(ls[0], "#EXTM3U")) { error = "not an M3U8 playlist"; return false; }
    for (size_t i = 1; i < ls.size(); i++) {
        auto l = ls[i];
        if (startsWith(l, "#EXT-X-STREAM-INF:")) {
            auto a = parseAttributes(l.substr(18));
            Variant v;
            uint64_t n;
            if (toU64(a["BANDWIDTH"], n)) v.bandwidth = n;
            if (toU64(a["AVERAGE-BANDWIDTH"], n)) v.averageBandwidth = n;
            auto& res = a["RESOLUTION"];
            if (auto x = res.find('x'); x != std::string::npos) { v.width = std::atoi(res.c_str()); v.height = std::atoi(res.c_str() + x + 1); }
            toDouble(a["FRAME-RATE"], v.frameRate);
            v.codecs = a["CODECS"];
            v.audioGroup = a["AUDIO"];
            // The URI is the next line that is not a tag (comments and other tags may sit between).
            while (++i < ls.size() && ls[i][0] == '#') { }
            if (i >= ls.size()) break;
            v.uri = std::string(ls[i]);
            if (!v.bandwidth) { error = "variant without BANDWIDTH"; return false; }
            m.variants.push_back(std::move(v));
        } else if (startsWith(l, "#EXT-X-MEDIA:")) {
            auto a = parseAttributes(l.substr(13));
            if (a["TYPE"] != "AUDIO") continue;
            Rendition r;
            r.groupId = a["GROUP-ID"]; r.name = a["NAME"]; r.language = a["LANGUAGE"]; r.uri = a["URI"];
            r.isDefault = a["DEFAULT"] == "YES"; r.autoSelect = a["AUTOSELECT"] == "YES";
            m.audio.push_back(std::move(r));
        } else if (startsWith(l, "#EXT-X-INDEPENDENT-SEGMENTS")) {
            m.independentSegments = true;
        }
    }
    if (m.variants.empty()) { error = "master playlist without variants"; return false; }
    return true;
}

bool parseMedia(std::string_view text, Media& m, std::string& error)
{
    m = {};
    auto ls = lines(text);
    if (ls.empty() || !startsWith(ls[0], "#EXTM3U")) { error = "not an M3U8 playlist"; return false; }
    double duration = -1;
    int64_t rangeLength = -1, rangeOffset = -1;
    bool discontinuity = false, haveSequence = false, haveDiscontinuitySequence = false;
    uint64_t sequence = 0, discontinuitySeq = 0;
    int key = -1, map = -1;
    std::string lastRangeUri;
    int64_t lastRangeEnd = 0;
    double start = 0;
    for (size_t i = 1; i < ls.size(); i++) {
        auto l = ls[i];
        if (l[0] != '#') {
            if (duration < 0) { error = "segment without EXTINF"; return false; }
            Segment s;
            s.duration = duration; s.uri = std::string(l);
            if (!haveSequence) { haveSequence = true; sequence = m.mediaSequence; }
            if (!haveDiscontinuitySequence) { haveDiscontinuitySequence = true; discontinuitySeq = m.discontinuitySequence; }
            if (discontinuity) ++discontinuitySeq;
            s.sequence = sequence++;
            s.discontinuity = discontinuitySeq;
            s.key = key; s.map = map; s.start = start;
            if (rangeLength > 0) {
                // RFC 8216 4.3.2.2: without @o the sub-range starts where the previous one of the same
                // resource ended.
                if (rangeOffset < 0) {
                    if (lastRangeUri != s.uri) { error = "EXT-X-BYTERANGE without offset and no previous range"; return false; }
                    rangeOffset = lastRangeEnd;
                }
                s.offset = rangeOffset; s.length = rangeLength;
                lastRangeUri = s.uri; lastRangeEnd = rangeOffset + rangeLength;
            }
            start += duration;
            m.segments.push_back(std::move(s));
            duration = -1; rangeLength = rangeOffset = -1; discontinuity = false;
            continue;
        }
        if (startsWith(l, "#EXTINF:")) {
            auto v = l.substr(8);
            v = v.substr(0, v.find(','));
            if (!toDouble(v, duration)) { error = "bad EXTINF"; return false; }
        } else if (startsWith(l, "#EXT-X-TARGETDURATION:")) {
            toDouble(l.substr(22), m.targetDuration);
        } else if (startsWith(l, "#EXT-X-MEDIA-SEQUENCE:")) {
            toU64(trim(l.substr(22)), m.mediaSequence);
        } else if (startsWith(l, "#EXT-X-DISCONTINUITY-SEQUENCE:")) {
            toU64(trim(l.substr(30)), m.discontinuitySequence);
        } else if (startsWith(l, "#EXT-X-DISCONTINUITY")) {
            discontinuity = true;
        } else if (startsWith(l, "#EXT-X-ENDLIST")) {
            m.endList = true;
        } else if (startsWith(l, "#EXT-X-PLAYLIST-TYPE:")) {
            m.playlistType = std::string(trim(l.substr(21)));
        } else if (startsWith(l, "#EXT-X-BYTERANGE:")) {
            if (!byteRange(trim(l.substr(17)), rangeLength, rangeOffset)) { error = "bad EXT-X-BYTERANGE"; return false; }
        } else if (startsWith(l, "#EXT-X-START:")) {
            auto a = parseAttributes(l.substr(13));
            std::string t = a["TIME-OFFSET"];
            char* end = nullptr;
            double v = std::strtod(t.c_str(), &end);
            if (end != t.c_str()) { m.startOffset = v; m.hasStart = true; }
        } else if (startsWith(l, "#EXT-X-KEY:")) {
            auto a = parseAttributes(l.substr(11));
            Key k;
            const auto& method = a["METHOD"];
            k.method = method == "NONE" ? Key::Method::None : method == "AES-128" ? Key::Method::Aes128
                : method == "SAMPLE-AES" || method == "SAMPLE-AES-CTR" ? Key::Method::SampleAes : Key::Method::Other;
            k.uri = a["URI"];
            if (a.count("IV")) {
                auto iv = a["IV"];
                if (iv.size() < 3 || (iv[0] != '0') || (iv[1] != 'x' && iv[1] != 'X')) { error = "bad IV"; return false; }
                std::string digits = iv.substr(2);
                if (digits.size() > 32) { error = "bad IV"; return false; }
                digits = std::string(32 - digits.size(), '0') + digits;
                for (int b = 0; b < 16; b++) {
                    int hi = hex(digits[size_t(2 * b)]), lo = hex(digits[size_t(2 * b + 1)]);
                    if (hi < 0 || lo < 0) { error = "bad IV"; return false; }
                    k.iv[b] = uint8_t(hi << 4 | lo);
                }
                k.hasIv = true;
            }
            if (k.method == Key::Method::None) key = -1;
            else { m.keys.push_back(std::move(k)); key = int(m.keys.size()) - 1; }
        } else if (startsWith(l, "#EXT-X-MAP:")) {
            auto a = parseAttributes(l.substr(11));
            InitSection s;
            s.uri = a["URI"];
            if (s.uri.empty()) { error = "EXT-X-MAP without URI"; return false; }
            if (a.count("BYTERANGE") && !byteRange(a["BYTERANGE"], s.length, s.offset)) { error = "bad EXT-X-MAP BYTERANGE"; return false; }
            if (s.length > 0 && s.offset < 0) s.offset = 0;
            m.maps.push_back(std::move(s));
            map = int(m.maps.size()) - 1;
        }
    }
    if (m.segments.empty() && m.endList) { error = "media playlist without segments"; return false; }
    if (m.targetDuration <= 0) {
        for (auto& s : m.segments) m.targetDuration = std::max(m.targetDuration, s.duration);
        if (m.targetDuration <= 0) m.targetDuration = 6;
    }
    return true;
}

std::string resolve(const std::string& base, const std::string& ref)
{
    auto schemeEnd = [](const std::string& s) -> size_t {
        for (size_t i = 0; i < s.size(); i++) {
            char c = s[i];
            if (c == ':') return i > 0 ? i : std::string::npos;
            if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '+' || c == '-' || c == '.')) return std::string::npos;
        }
        return std::string::npos;
    };
    if (schemeEnd(ref) != std::string::npos) return ref;
    size_t sc = schemeEnd(base);
    if (sc == std::string::npos) return ref;
    std::string scheme = base.substr(0, sc + 1);
    if (ref.substr(0, 2) == "//") return scheme + ref;
    size_t authorityStart = base.compare(sc + 1, 2, "//") == 0 ? sc + 3 : sc + 1;
    size_t pathStart = base.find('/', authorityStart);
    size_t queryStart = base.find_first_of("?#", authorityStart);
    if (pathStart != std::string::npos && queryStart != std::string::npos && queryStart < pathStart) pathStart = std::string::npos;
    std::string authority = base.substr(0, pathStart == std::string::npos ? std::min(queryStart, base.size()) : pathStart);
    std::string path = pathStart == std::string::npos ? "/" : base.substr(pathStart, (queryStart == std::string::npos ? base.size() : queryStart) - pathStart);
    std::string query = queryStart != std::string::npos && base[queryStart] == '?' ? base.substr(queryStart, base.find('#', queryStart) - queryStart) : "";
    if (ref.empty()) return authority + path + query;
    if (ref[0] == '#') return authority + path + query + ref;
    if (ref[0] == '?') return authority + path + ref;
    std::string refPath = ref, refRest;
    if (auto q = ref.find_first_of("?#"); q != std::string::npos) { refPath = ref.substr(0, q); refRest = ref.substr(q); }
    std::string merged = refPath[0] == '/' ? refPath : path.substr(0, path.rfind('/') + 1) + refPath;
    // remove_dot_segments (RFC 3986 5.2.4)
    std::vector<std::string> out;
    size_t at = 0;
    bool trailing = false;
    while (at <= merged.size()) {
        size_t slash = merged.find('/', at);
        if (slash == std::string::npos) slash = merged.size();
        std::string seg = merged.substr(at, slash - at);
        trailing = slash == merged.size() && (seg == "." || seg == "..");
        if (seg == "..") { if (!out.empty()) out.pop_back(); }
        else if (seg != "." && !(seg.empty() && at > 0 && slash < merged.size())) out.push_back(seg);
        at = slash + 1;
    }
    std::string result;
    for (size_t i = 0; i < out.size(); i++) result += (i ? "/" : "") + out[i];
    if (result.empty() || result[0] != '/') result = "/" + result;
    if (trailing && result.back() != '/') result += "/";
    return authority + result + refRest;
}

bool isHlsMimeType(std::string_view t)
{
    return t == "application/vnd.apple.mpegurl" || t == "application/x-mpegurl" || t == "application/mpegurl"
        || t == "audio/mpegurl" || t == "audio/x-mpegurl";
}

}
