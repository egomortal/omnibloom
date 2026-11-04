// OMNI_NET_GRABBER_V1: network-observed media for the "Media downloads" grabber.
//
// The page-side snapshot (OmniLinkSnapshot.h) cannot see into cross-origin
// iframes. The UI process can: WKPageResourceLoadClient reports every
// response the page (all frames) receives. This header holds the pure,
// std-only parts so they can be unit-tested off-console:
//   classify()  - is this response an HLS/DASH manifest, a whole media file,
//                 or neither (segments, byte ranges, init pieces, blob:/data:)?
//   Ring        - a small per-tab memory of observed media (16 manifests +
//                 16 media files), cleared on main-frame commit.
//   merge()     - folds the ring into the snapshot's candidate rows.
// No logging, no I/O, no WebKit types. Only string checks; the only
// allocation per response is the URL copy the caller already made, plus one
// stored string when (rarely) a response actually matches.
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace OmniNetGrabber {

enum class Kind : uint8_t { None, Manifest, Media };

constexpr std::size_t maxUrlChars = 4096;      // same as the wire / worker URL limit
constexpr std::size_t manifestCapacity = 16, mediaCapacity = 16;
constexpr std::size_t maxManifestRows = 4, maxMediaRows = 3, maxRows = 8;
constexpr int scorePrimaryManifest = 95, scoreManifest = 90, scoreMedia = 75; // all in the wire's score set
constexpr const char* evidenceCode = "resource-timing"; // already accepted by validateWire and the worker

inline char lower(char c) { return (c >= 'A' && c <= 'Z') ? char(c - 'A' + 'a') : c; }
inline bool startsWithNoCase(std::string_view s, std::string_view prefix)
{
    if (s.size() < prefix.size()) return false;
    for (std::size_t i = 0; i < prefix.size(); ++i) if (lower(s[i]) != prefix[i]) return false;
    return true;
}
inline bool equalsNoCase(std::string_view s, std::string_view t) { return s.size() == t.size() && startsWithNoCase(s, t); }
inline bool containsNoCase(std::string_view s, std::string_view needle)
{
    if (needle.empty()) return true;
    if (s.size() < needle.size()) return false;
    for (std::size_t i = 0; i + needle.size() <= s.size(); ++i)
        if (startsWithNoCase(s.substr(i), needle)) return true;
    return false;
}
inline bool oneOfNoCase(std::string_view s, std::initializer_list<std::string_view> list)
{
    for (auto item : list) if (equalsNoCase(s, item)) return true;
    return false;
}

// "Video/MP4; codecs=..." -> "video/mp4" view (case is compared without folding).
inline std::string_view mimeEssence(std::string_view mime)
{
    auto semi = mime.find(';');
    if (semi != std::string_view::npos) mime = mime.substr(0, semi);
    while (!mime.empty() && (mime.back() == ' ' || mime.back() == '\t')) mime.remove_suffix(1);
    while (!mime.empty() && (mime.front() == ' ' || mime.front() == '\t')) mime.remove_prefix(1);
    return mime;
}

struct UrlParts { std::string_view path, query, file, ext; };
// Only for http(s) URLs without whitespace. path excludes the authority.
inline bool split(std::string_view url, UrlParts& parts)
{
    std::size_t scheme = startsWithNoCase(url, "https://") ? 8 : startsWithNoCase(url, "http://") ? 7 : 0;
    if (!scheme || url.size() > maxUrlChars) return false;
    for (unsigned char c : url) if (c <= 32 || c == 127 || c == '\\') return false;
    auto end = url.find('#'); if (end != std::string_view::npos) url = url.substr(0, end);
    auto pathStart = url.find_first_of("/?", scheme);
    std::string_view authority = url.substr(scheme, pathStart == std::string_view::npos ? std::string_view::npos : pathStart - scheme);
    if (authority.empty() || authority.find('@') != std::string_view::npos) return false;
    std::string_view rest = pathStart == std::string_view::npos ? std::string_view { } : url.substr(pathStart);
    auto q = rest.find('?');
    parts.path = q == std::string_view::npos ? rest : rest.substr(0, q);
    parts.query = q == std::string_view::npos ? std::string_view { } : rest.substr(q + 1);
    auto slash = parts.path.rfind('/');
    parts.file = slash == std::string_view::npos ? parts.path : parts.path.substr(slash + 1);
    auto dot = parts.file.rfind('.');
    parts.ext = dot == std::string_view::npos ? std::string_view { } : parts.file.substr(dot + 1);
    return true;
}

// A query parameter NAME (exact, case-insensitive) present, e.g. "range" in "a=1&range=0-99".
inline bool hasParam(std::string_view query, std::string_view name)
{
    std::size_t at = 0;
    while (at <= query.size()) {
        auto amp = query.find('&', at);
        auto pair = query.substr(at, amp == std::string_view::npos ? std::string_view::npos : amp - at);
        auto eq = pair.find('=');
        if (equalsNoCase(pair.substr(0, eq), name)) return true;
        if (amp == std::string_view::npos) break;
        at = amp + 1;
    }
    return false;
}

inline bool manifestMime(std::string_view m)
{
    return oneOfNoCase(m, { "application/vnd.apple.mpegurl", "application/x-mpegurl", "audio/mpegurl", "audio/x-mpegurl",
        "application/mpegurl", "video/mpegurl", "video/x-mpegurl", "application/dash+xml", "video/vnd.mpeg.dash.mpd" });
}
inline bool segmentMime(std::string_view m)
{
    return oneOfNoCase(m, { "video/mp2t", "audio/mp2t", "video/iso.segment", "audio/iso.segment", "video/vnd.dlna.mpeg-tts" });
}
// MIME types a manifest URL hint (no .m3u8/.mpd extension) may legitimately carry.
inline bool neutralMime(std::string_view m)
{
    return m.empty() || oneOfNoCase(m, { "application/octet-stream", "binary/octet-stream", "text/plain", "application/x-binary" });
}
// Responses that are certainly not media bodies (error pages, API JSON, scripts, images).
inline bool foreignMime(std::string_view m)
{
    return startsWithNoCase(m, "text/html") || startsWithNoCase(m, "application/json") || startsWithNoCase(m, "image/")
        || containsNoCase(m, "javascript") || startsWithNoCase(m, "text/css") || startsWithNoCase(m, "font/")
        || startsWithNoCase(m, "application/xhtml");
}
inline bool segmentExt(std::string_view e) { return oneOfNoCase(e, { "ts", "m4s", "cmfv", "cmfa", "cmft", "m2ts", "vtt", "webvtt", "key" }); }
inline bool mediaExt(std::string_view e)
{
    return oneOfNoCase(e, { "mp4", "m4v", "webm", "mov", "mkv", "mp3", "m4a", "aac", "ogg", "oga", "ogv", "opus", "flac", "wav" });
}
inline bool manifestExt(std::string_view e) { return oneOfNoCase(e, { "m3u8", "mpd" }); }
// Extension-less hints: /manifest(format=m3u8-aapl), ?format=mpd, /playlist.m3u8/..., /master.mpd?...
inline bool manifestHint(std::string_view path, std::string_view query)
{
    if (containsNoCase(path, "m3u8") || containsNoCase(query, "m3u8")) return true;
    if (containsNoCase(path, "format=mpd") || containsNoCase(query, "format=mpd")) return true;
    for (std::size_t i = path.find('.'); i != std::string_view::npos; i = path.find('.', i + 1)) {
        if (!startsWithNoCase(path.substr(i), ".mpd")) continue;
        if (i + 4 == path.size() || path[i + 4] == '/') return true;
    }
    return false;
}
// "seg" matches "seg-12.mp4", "seg12.mp4", "seg_1.m4a", "seg.mp4" but not "segway.mp4".
inline bool wordPrefix(std::string_view file, std::string_view word)
{
    if (!startsWithNoCase(file, word)) return false;
    if (file.size() == word.size()) return true;
    const char next = lower(file[word.size()]);
    return !(next >= 'a' && next <= 'z');
}
// Pieces of a stream rather than a whole file.
inline bool pieceUrl(const UrlParts& p)
{
    if (hasParam(p.query, "range") || hasParam(p.query, "bytes") || hasParam(p.query, "byterange")) return true;
    if (containsNoCase(p.path, "/range/") || containsNoCase(p.path, "/bytes/")) return true;
    // init.mp4, init-v1-a1.mp4, init_0.m4s, seg-12-v1.mp4, chunk_3.m4a, fragment5.mp4, frag-3.mp4
    return wordPrefix(p.file, "init") || wordPrefix(p.file, "seg") || wordPrefix(p.file, "segment") || wordPrefix(p.file, "chunk")
        || wordPrefix(p.file, "frag") || wordPrefix(p.file, "fragment");
}

// Pre-filter before the caller copies the MIME type: non-http(s) URLs and
// common static assets (scripts, styles, images, fonts, documents).
inline bool staticAsset(std::string_view url)
{
    UrlParts p;
    if (!split(url, p)) return true;
    return oneOfNoCase(p.ext, { "js", "mjs", "css", "png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "ico", "woff", "woff2",
        "ttf", "otf", "json", "html", "htm", "php", "map", "wasm", "xml" }) && !manifestHint(p.path, p.query);
}

// status: HTTP status (0 = unknown / non-HTTP). expectedLength: Content-Length (<= 0 unknown).
inline Kind classify(std::string_view url, std::string_view mimeRaw, int status, long long expectedLength)
{
    UrlParts p;
    if (!split(url, p)) return Kind::None;                       // blob:, data:, file:, about:, junk
    if (status && (status < 200 || status >= 300)) return Kind::None; // errors, redirects, 304
    const auto mime = mimeEssence(mimeRaw);
    if (manifestExt(p.ext)) return startsWithNoCase(mime, "text/html") || startsWithNoCase(mime, "image/") ? Kind::None : Kind::Manifest;
    if (manifestMime(mime)) return Kind::Manifest;
    if (segmentExt(p.ext) || segmentMime(mime)) return Kind::None;
    if (manifestHint(p.path, p.query) && !pieceUrl(p)) {
        if (neutralMime(mime)) return Kind::Manifest;
        if (foreignMime(mime)) return Kind::None;
    }
    const bool avMime = startsWithNoCase(mime, "video/") || startsWithNoCase(mime, "audio/");
    if (!avMime && !(mediaExt(p.ext) && (neutralMime(mime) || startsWithNoCase(mime, "application/mp4")))) return Kind::None;
    if (pieceUrl(p)) return Kind::None;
    // Click/notification sounds and tiny previews: a whole (200) body under 32 KiB.
    if ((status == 200 || status == 0) && expectedLength > 0 && expectedLength < 32 * 1024) return Kind::None;
    return Kind::Media;
}

struct Entry { std::string url; uint32_t epoch = 0; uint32_t order = 0; };

// Per-tab memory. Manifests keep the EARLIEST ones (the first fetched is
// usually the master playlist; variants and live refreshes come later and
// repeat the same URL). Media files keep the MOST RECENT ones (the file
// playing now). A same-document navigation (SPA video change) bumps the epoch
// so the newest epoch's manifests rank first and older epochs are evicted first.
struct Ring {
    std::vector<Entry> manifests, media;
    uint32_t epoch = 0, order = 0;

    void clear() { manifests.clear(); media.clear(); epoch = 0; order = 0; }
    void newEpoch() { ++epoch; }
    static bool has(const std::vector<Entry>& list, std::string_view url)
    {
        for (const auto& e : list) if (e.url.size() == url.size() && e.url == url) return true;
        return false;
    }
    // Returns true when stored.
    bool record(Kind kind, std::string_view url)
    {
        if (kind == Kind::None || url.empty() || url.size() > maxUrlChars) return false;
        auto& list = kind == Kind::Manifest ? manifests : media;
        // OMNI_C52_FIX1: a URL seen as both a manifest and a media file is kept as the manifest only,
        // so the merged wire never carries the same "u" twice (validateWire rejects duplicates).
        if (kind == Kind::Media && has(manifests, url)) return false;
        if (has(list, url)) {
            if (kind == Kind::Media) // refresh recency of a re-fetched file
                for (auto& e : list) if (e.url == url) { e.order = ++order; e.epoch = epoch; }
            return false;
        }
        if (kind == Kind::Manifest && list.size() >= manifestCapacity) {
            // Evict the oldest entry of an OLDER epoch; within the current epoch keep the earliest.
            auto victim = list.end();
            for (auto it = list.begin(); it != list.end(); ++it)
                if (it->epoch < epoch && (victim == list.end() || it->order < victim->order)) victim = it;
            if (victim == list.end()) return false;
            list.erase(victim);
        }
        if (kind == Kind::Media && list.size() >= mediaCapacity) {
            auto victim = std::min_element(list.begin(), list.end(), [](const Entry& a, const Entry& b) { return a.order < b.order; });
            list.erase(victim);
        }
        list.push_back({ std::string(url), epoch, ++order });
        if (kind == Kind::Manifest) // OMNI_C52_FIX1: stored as a manifest: drop any media entry for the same URL
            media.erase(std::remove_if(media.begin(), media.end(), [&](const Entry& e) { return e.url == url; }), media.end());
        return true;
    }
};

struct Row { std::string u, k; int s = 0; std::vector<std::string> e; bool network = false; };

// Network rows ranked: manifests (newest epoch first, earliest-fetched first
// within an epoch; the very first one is the primary at 95, the rest 90),
// then - only when no manifest exists anywhere - media files, newest first, at 75.
// `valid` filters URLs the wire would reject (the caller passes validHttp).
template<typename Valid>
inline std::vector<Row> networkRows(const Ring& ring, bool snapshotHasManifest, Valid&& valid)
{
    std::vector<Row> rows;
    std::vector<const Entry*> m;
    for (const auto& e : ring.manifests) if (valid(e.url)) m.push_back(&e);
    std::stable_sort(m.begin(), m.end(), [](const Entry* a, const Entry* b) { return a->epoch != b->epoch ? a->epoch > b->epoch : a->order < b->order; });
    for (std::size_t i = 0; i < m.size() && rows.size() < maxManifestRows; ++i)
        rows.push_back({ m[i]->url, "manifest", rows.empty() ? scorePrimaryManifest : scoreManifest, { evidenceCode }, true });
    if (!rows.empty() || snapshotHasManifest) return rows;
    std::vector<const Entry*> f;
    for (const auto& e : ring.media) if (valid(e.url) && !Ring::has(ring.manifests, e.url)) f.push_back(&e); // OMNI_C52_FIX1
    std::stable_sort(f.begin(), f.end(), [](const Entry* a, const Entry* b) { return a->order > b->order; });
    for (std::size_t i = 0; i < f.size() && rows.size() < maxMediaRows; ++i)
        rows.push_back({ f[i]->url, "media-url", scoreMedia, { evidenceCode }, true });
    return rows;
}

// Snapshot rows that mark a protected (EME) page: never add network rows there.
inline bool snapshotIsProtected(const std::vector<Row>& snapshot)
{
    for (const auto& r : snapshot) for (const auto& code : r.e) if (code == "encrypted-media-page-fallback") return true;
    return false;
}

// Merge: dedupe network rows into snapshot rows by exact URL (raise the score,
// adopt the network kind when it ranks higher, add the evidence code), then
// order by score with network rows first on ties, and cap at maxRows.
// `truncated` is set when rows were dropped.
template<typename Valid>
inline std::vector<Row> merge(const std::vector<Row>& snapshot, const Ring& ring, Valid&& valid, bool& truncated)
{
    if (snapshotIsProtected(snapshot)) return snapshot;
    bool snapshotHasManifest = false;
    for (const auto& r : snapshot) if (r.k == "manifest") snapshotHasManifest = true;
    auto net = networkRows(ring, snapshotHasManifest, valid);
    if (net.empty()) return snapshot;
    std::vector<Row> out;
    std::vector<Row> rest = snapshot;
    std::vector<std::string> seen; // OMNI_C52_FIX1: one row per URL (the first, higher-ranked network row wins)
    for (auto& n : net) {
        if (std::find(seen.begin(), seen.end(), n.u) != seen.end()) continue;
        seen.push_back(n.u);
        bool merged = false;
        for (auto& r : rest) {
            if (r.u != n.u) continue;
            if (r.k == "source-page") break; // the page URL itself: never relabel it
            if (n.s > r.s) { r.s = n.s; r.k = n.k; }
            if (std::find(r.e.begin(), r.e.end(), n.e[0]) == r.e.end() && r.e.size() < 4) r.e.push_back(n.e[0]);
            r.network = true; merged = true; break;
        }
        if (!merged) {
            bool pageUrl = false;
            for (const auto& r : rest) if (r.u == n.u) pageUrl = true;
            if (!pageUrl) out.push_back(n);
        }
    }
    for (auto& r : rest) out.push_back(r);
    std::stable_sort(out.begin(), out.end(), [](const Row& a, const Row& b) { return a.s != b.s ? a.s > b.s : (a.network && !b.network); });
    if (out.size() > maxRows) { out.resize(maxRows); truncated = true; }
    return out;
}

// URL a "share" grab should prefill: the first row when it is a manifest or a media file and the page
// is not protected; otherwise the page URL itself.
inline std::string topCandidate(const std::vector<Row>& rows, const std::string& page)
{
    if (rows.empty() || snapshotIsProtected(rows)) return page;
    const auto& first = rows.front();
    return (first.k == "manifest" || first.k == "media-url") && !first.u.empty() ? first.u : page;
}

// OMNI_NET_GRABBER_TEST_V1: "host/path" of a URL for the self-test log (no scheme, query or fragment), bounded.
inline std::string logHostPath(std::string_view url, std::size_t limit = 120)
{
    auto scheme = url.find("://");
    if (scheme != std::string_view::npos) url = url.substr(scheme + 3);
    auto cut = url.find_first_of("?#");
    if (cut != std::string_view::npos) url = url.substr(0, cut);
    std::string out;
    for (char c : url.substr(0, limit)) out += (static_cast<unsigned char>(c) < 33 || c == 127) ? '_' : c;
    return out;
}

} // namespace OmniNetGrabber
