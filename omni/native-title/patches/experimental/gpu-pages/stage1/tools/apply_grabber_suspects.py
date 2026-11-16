#!/usr/bin/env python3
"""OMNI_GRABBER_SUSPECTS_V1 (2026-11-16, owner: "is there any we potentially miss"). The network grabber
(engine/entry/OmniNetGrabber.h) recognises a stream playlist only by its name (.m3u8/.mpd, "m3u8" in the address) or
its declared type. It missed:
  1. playlists at plain addresses ("/api/stream/abc") served as a generic file (octet-stream, text/plain);
  2. playlists whose file name says something else (".png", ".txt", ".html") with a generic type;
  3. real playlists past the 4th on busy pages (ads load theirs first).
Omni only sees a response's headers, never its body, so it can't tell. It now keeps such responses as SUSPECTS
(generic or text type, not a known media/segment file, not a stream piece, 100 B..400 KiB when the size is known) and
offers up to 4 of them as low-score playlist rows (score 45, "resource-timing") when no real playlist was seen. The
Downloads app checks every row anyway (probe.py reads the first bytes: "#EXTM3U" / "<MPD"), and shows a suspect only
once that check confirms it (app.js OMNI_GRABBER_SUSPECTS_V1). Suspects whose address looks like a playlist
(playlist, master, index, manifest, hls, dash, stream, m3u) are offered first; then the earliest ones (a player fetches
its playlist before the stream pieces). Up to 6 real playlists are offered (was 4). Nothing is decrypted or decoded.
usage: apply_grabber_suspects.py <engine tree>"""
import sys
from pathlib import Path

MARK = 'OMNI_GRABBER_SUSPECTS_V1'
p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniNetGrabber.h'
raw = p.read_bytes()
nl = '\r\n' if b'\r\n' in raw else '\n'
s = raw.decode('utf-8').replace('\r\n', '\n')
if MARK in s:
    print('already ' + MARK)
    sys.exit(0)

EDITS = [
    ('enum class Kind : uint8_t { None, Manifest, Media };',
     'enum class Kind : uint8_t { None, Manifest, Media, Suspect }; // ' + MARK + ': Suspect = maybe a playlist (checked by Downloads)'),
    ('constexpr std::size_t maxManifestRows = 4, maxMediaRows = 3, maxRows = 8;',
     'constexpr std::size_t maxManifestRows = 6, maxMediaRows = 3, maxRows = 8; // ' + MARK + ': 6 playlists (was 4)\n'
     'constexpr std::size_t suspectCapacity = 24, maxSuspectRows = 4;\n'
     'constexpr int scoreSuspect = 45; // in the wire\'s score set; Downloads shows such a row only after its check confirms it'),
    # the pre-filter no longer drops images and pages by their name: a playlist may be named like one
    ('''    return oneOfNoCase(p.ext, { "js", "mjs", "css", "png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "ico", "woff", "woff2",
        "ttf", "otf", "json", "html", "htm", "php", "map", "wasm", "xml" }) && !manifestHint(p.path, p.query);''',
     '''    // OMNI_GRABBER_SUSPECTS_V1: only files that are never a playlist in disguise; images, pages, scripts and data go on
    // to classify(), which drops them by their real type (image/, text/html, javascript, json).
    return oneOfNoCase(p.ext, { "woff", "woff2", "ttf", "otf", "map", "wasm", "svg", "ico", "avif" }) && !manifestHint(p.path, p.query);'''),
    ('''    const bool avMime = startsWithNoCase(mime, "video/") || startsWithNoCase(mime, "audio/");
    if (!avMime && !(mediaExt(p.ext) && (neutralMime(mime) || startsWithNoCase(mime, "application/mp4")))) return Kind::None;''',
     '''    const bool avMime = startsWithNoCase(mime, "video/") || startsWithNoCase(mime, "audio/");
    if (!avMime && !(mediaExt(p.ext) && (neutralMime(mime) || startsWithNoCase(mime, "application/mp4")))) {
        // OMNI_GRABBER_SUSPECTS_V1: a generic or plain-text body that is not a known media file or stream piece, and
        // small like a playlist, may be one under another name. Downloads reads its first bytes before showing it.
        if (neutralMime(mime) && !mediaExt(p.ext) && !pieceUrl(p)
            && (expectedLength <= 0 || (expectedLength >= 100 && expectedLength <= 400 * 1024)))
            return Kind::Suspect;
        return Kind::None;
    }'''),
    ('''    std::vector<Entry> manifests, media;
    uint32_t epoch = 0, order = 0;''',
     '''    std::vector<Entry> manifests, media;
    std::vector<Entry> suspects; // OMNI_GRABBER_SUSPECTS_V1: earliest of the newest epoch kept
    uint32_t epoch = 0, order = 0;'''),
    ('    void clear() { manifests.clear(); media.clear(); epoch = 0; order = 0; }',
     '    void clear() { manifests.clear(); media.clear(); suspects.clear(); epoch = 0; order = 0; }'),
    ('''        if (kind == Kind::None || url.empty() || url.size() > maxUrlChars) return false;
        auto& list = kind == Kind::Manifest ? manifests : media;''',
     '''        if (kind == Kind::None || url.empty() || url.size() > maxUrlChars) return false;
        if (kind == Kind::Suspect) { // OMNI_GRABBER_SUSPECTS_V1
            if (has(suspects, url) || has(manifests, url) || has(media, url)) return false;
            if (suspects.size() >= suspectCapacity) {
                auto victim = suspects.end();
                for (auto it = suspects.begin(); it != suspects.end(); ++it)
                    if (it->epoch < epoch && (victim == suspects.end() || it->order < victim->order)) victim = it;
                if (victim == suspects.end()) return false; // the current page's earliest suspects stay
                suspects.erase(victim);
            }
            suspects.push_back({ std::string(url), epoch, ++order });
            return true;
        }
        auto& list = kind == Kind::Manifest ? manifests : media;'''),
    ('''    for (std::size_t i = 0; i < f.size() && rows.size() < maxMediaRows; ++i)
        rows.push_back({ f[i]->url, "media-url", scoreMedia, { evidenceCode }, true });
    return rows;
}''',
     '''    for (std::size_t i = 0; i < f.size() && rows.size() < maxMediaRows; ++i)
        rows.push_back({ f[i]->url, "media-url", scoreMedia, { evidenceCode }, true });
    // OMNI_GRABBER_SUSPECTS_V1: no playlist seen by name or type: offer the likeliest suspects (newest page first;
    // playlist-like addresses, then the earliest fetched). Downloads confirms each by its content before showing it.
    std::vector<const Entry*> q;
    for (const auto& e : ring.suspects)
        if (valid(e.url) && !Ring::has(ring.manifests, e.url) && !Ring::has(ring.media, e.url)) q.push_back(&e);
    auto likely = [](const Entry* e) {
        UrlParts u;
        if (!split(e->url, u)) return false;
        for (const char* w : { "playlist", "master", "index", "manifest", "hls", "dash", "stream", "m3u" })
            if (containsNoCase(u.path, w) || containsNoCase(u.query, w)) return true;
        return false;
    };
    std::stable_sort(q.begin(), q.end(), [&](const Entry* a, const Entry* b) {
        if (a->epoch != b->epoch) return a->epoch > b->epoch;
        const bool la = likely(a), lb = likely(b);
        return la != lb ? la : a->order < b->order;
    });
    for (std::size_t i = 0, n = 0; i < q.size() && n < maxSuspectRows; ++i, ++n)
        rows.push_back({ q[i]->url, "manifest", scoreSuspect, { evidenceCode }, true });
    return rows;
}'''),
]
for old, new in EDITS:
    if s.count(old) != 1:
        sys.exit('OmniNetGrabber.h: anchor found %d times: %r' % (s.count(old), old[:80]))
    s = s.replace(old, new, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied ' + MARK)
