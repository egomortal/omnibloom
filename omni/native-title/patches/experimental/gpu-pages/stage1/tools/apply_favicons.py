#!/usr/bin/env python3
"""OMNI_FAVICONS_V1 (2026-11-16): real site icons (favicons) where Omni showed a coloured site letter.

What the user sees
  - Tab strips (4 or fewer tabs, more than 4, and the pinned strip): the site's icon left of the title (where the
    loading spinner / error dot sit while those show); a compact pinned tile shows the icon instead of its letter.
  - Tabs panel and Bookmarks: each tab / bookmark row has the icon where a row icon goes (a playing tab keeps its
    speaker); with no icon known, a small disc in the site's colour with its letter (the tab switcher's colour/letter).
  - History: the icon (else the letter disc) before each visit's title.
  - Tab search ("Switch to tab" rows in the address suggestions): the tab's icon instead of the tab glyph.
  - Tab switcher (L2 + R1): the square shows the icon on a light plate instead of the coloured letter tile.
  - The old new-tab page (omniNewTabHtml: the start page when the omni://pages bundle is off / missing): shortcut,
    suggested and recently-visited tiles show the icon (an <img> data URL) instead of the letter.
  Everywhere: no icon known -> exactly the letter as before. The omni://pages start page (pages bundle, start-custom.js)
  draws its own tiles from OSCU::pageJson; it is not changed here.

How the icon is obtained (checked in the engine's WebKit tree (s1/webkit), UIProcess/API/C and the PlayStation build)
  - WKIconDatabase / WKContextGetIconDatabase: still declared, but every function in WKIconDatabase.cpp and
    WKContextGetIconDatabase / WKContextSetIconDatabasePath have empty bodies (the icon database is gone).
  - WebKit's own link-icon loading (WebPageProxy::getLoadDecisionForIcons -> API::IconLoadingClient) has clients only
    in Cocoa (_WKIconLoadingDelegate) and glib (WebKitIconLoadingClient); the C API has no setter and no
    WKPageLoaderClient / WKPageNavigationClient icon callback exists. Without a client WebKit loads no link icons.
  - So the page is asked, once it has loaded (finished()), with a page script (WKPageCallAsyncJavaScriptWithoutUserGesture,
    the async-function call apply_site_clear.py uses): it picks the best <link rel~=icon> (size near 32, SVG / "any",
    then apple-touch-icon, then <origin>/favicon.ico), loads it as an <img> IN THE PAGE (the page's own WebKit
    networking: its session and cookies, HTTP cache, CSP img-src, uBlock / content blockers; a private tab's
    ephemeral session) and draws it into a 32 x 32 canvas; canvas.toDataURL("image/png") is the answer. Omni opens no
    connection, sends no request and parses no ICO / SVG / JPEG itself: WebKit's decoders turn every format into PNG.
    Canvas taint: a cross-origin icon is loaded with crossOrigin = "anonymous" (works when its server sends CORS
    headers: most CDNs do); a same-origin icon that redirected cross-origin is retried that way; a tainted canvas
    throws and the next candidate is tried. fetch(..., {mode: "no-cors"}) would be opaque: not used.
  - The answer carries location.hostname; it is used only when it equals the host that was asked about and the tab
    (if still open) still shows that host (a navigation in between can't file another site's icon). A page can only
    set its own host's icon (which it could anyway).
  - Native side: strict base64, a PNG header check (32 x 32, 8 bit) and libpng (png_image, already linked) decode it.
  - Once per host per session; none while the host's file is under a week old. At most 3 scripts out at once.

Cache: /data/omni/icons/<fnv1a64(host without www.)>.png (the host itself is never written), at most 300 files and
2 MB, least recently captured / used first out (mtime = capture time, bumped in memory when drawn); writes and
deletes go to the background writer (.tmp + rename). Private tabs: memory only, dropped once no private tab is left.
"Don't save history" on: memory only. History > Clear history (a range) / Clear browsing data (History) remove the
icons captured or used in that range (all time: all); History > Delete site removes that site's icon.
Drawing: 32 x 32 RGBA scaled per drawn size (area average down, bilinear up; premultiplied), blended with
omniBlendSurface; at most 4 icon files read from disk per frame.

Pure part: engine/entry/OmniFavicons.h (host key, file names, LRU index, base64, PNG header check, answer parsing,
scaling, the capture script). Tested by tools/test_favicons.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_favicons.cpp -o t && ./t <script.js>
and the capture script by tools/test_favicons_js.mjs (node, a mocked page): node test_favicons_js.mjs <script.js>
Shell side: engine/entry/OmniFaviconsShell.h (included from OmniFeatures3.h after OmniLinkPreviewShell.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp       the OmniClearRange.h include (pure include); the omniHltFinished declaration (declarations);
                        finished()'s omniHltFinished call; the <=4-tab strip's crash-dot line; the old new-tab page's
                        OMNI_SEARCH_TILES_V1 CSS line, tile() and suggested-tile <i> lines; History's title + address
                        lines; History "Clear history" / "Delete site" notices.
  OmniFeaturesPanel.h   OmniFxRow's prefix field; the list row's r.icon line.
  OmniTabsPage.h        omniWapTabRow(t, r) line.          OmniBookmarksShell.h   the bookmark row's r.detail line.
  OmniTabSearchShell.h  the tab glyph comment.             OmniTabSwitcherShell.h the tile letter line.
  OmniPinnedTabsShell.h the compact letter line; the crash-dot line.   OmniTabMemory.h  the crash-dot line.
  OmniClearRangeShell.h the History step's omniHpChanged line.         OmniFeatures3.h  the OmniLinkPreviewShell.h include.
Apply AFTER apply_link_preview.py, apply_clear_range.py, apply_tab_search.py, apply_tab_switcher.py,
apply_pinned_tabs.py, apply_history_plus.py, apply_bookmarks_manager.py, apply_settings_search.py, apply_web_apps.py,
apply_search_tiles.py, apply_highlights.py (their lines are anchors).
usage: apply_favicons.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_FAVICONS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_FAVICONS_V1: the pure part of the site icons (favicons) in the tab strip, Tabs panel, bookmarks, history, tab
// search / switcher and the old new-tab page (no SDL, no WebKit, no libpng). The shell side is OmniFaviconsShell.h; the
// reasons (why a page script, why no own networking) are in tools/apply_favicons.py. Tested on the host with g++
// (test_favicons.cpp) and node (test_favicons_js.mjs, the capture script).
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace OmniFavicons {

constexpr int kPx = 32;                              // every stored icon: 32 x 32 PNG (the page's canvas makes it)
constexpr size_t kMaxFiles = 300;                    // /data/omni/icons: at most this many files ...
constexpr uint64_t kMaxBytes = 2u * 1024u * 1024u;   // ... and this many bytes; least recently captured / used first out
constexpr size_t kMaxPngBytes = 16384;               // one icon (a 32 x 32 RGBA PNG is ~4 KB at worst)
constexpr size_t kMaxAnswer = 4 * kMaxPngBytes / 3 + 600;   // the page script's answer (data URL + host)
constexpr long long kRefreshSecs = 7LL * 86400;      // an icon on disk is captured again after a week (on a visit)
constexpr int kMaxInFlight = 3;                      // page scripts out at once
constexpr int kStepMs = 2500, kScriptMs = 6000;      // page script: per image, overall
constexpr int kMaxCandidates = 4;                    // <link> icons tried (then /favicon.ico)
constexpr const char* kAnswerTag = "omni-fav";
constexpr const char* kDirName = "icons/";           // under OMNI_DATA_DIR

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }

// --- hosts -------------------------------------------------------------------------------------------------------
// The cache key of a page: its host, lower case, no port / credentials / trailing dot, a leading "www." dropped
// (www.example.com and example.com share one icon). "" for anything but http(s) and for odd hosts.
inline std::string hostKey(const std::string& url)
{
    size_t p;
    auto starts = [&](const char* s) {
        size_t i = 0;
        for (; s[i]; ++i) if (i >= url.size() || lower(url[i]) != s[i]) return false;
        return true;
    };
    if (starts("https://")) p = 8;
    else if (starts("http://")) p = 7;
    else return std::string();
    size_t end = url.find_first_of("/?#\\", p);
    if (end == std::string::npos) end = url.size();
    const size_t at = url.rfind('@', end ? end - 1 : 0);
    if (at != std::string::npos && at >= p && at < end) p = at + 1;
    std::string host;
    if (p < end && url[p] == '[') {
        const size_t close = url.find(']', p);
        if (close == std::string::npos || close >= end) return std::string();
        host = url.substr(p + 1, close - p - 1);
        for (char c : host) if (!((c >= '0' && c <= '9') || (lower(c) >= 'a' && lower(c) <= 'f') || c == ':' || c == '.')) return std::string();
        if (host.empty()) return std::string();
        for (auto& c : host) c = lower(c);
        return "[" + host + "]";
    }
    const size_t colon = url.find(':', p);
    host = url.substr(p, (colon != std::string::npos && colon < end ? colon : end) - p);
    for (auto& c : host) c = lower(c);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || host.size() > 253) return std::string();
    for (char c : host) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_')) return std::string();
    if (host.compare(0, 4, "www.") == 0 && host.size() > 4 && host.find('.', 4) != std::string::npos) host = host.substr(4);
    return host;
}

// FNV-1a, 64 bit: the file name of a host's icon ("0123456789abcdef.png"); the host itself is never written.
inline uint64_t fnv1a64(const std::string& s)
{
    uint64_t h = 14695981039346656037ULL;
    for (unsigned char c : s) { h ^= c; h *= 1099511628211ULL; }
    return h;
}
inline std::string fileName(const std::string& key)
{
    if (key.empty()) return std::string();
    static const char* const hex = "0123456789abcdef";
    const uint64_t h = fnv1a64(key);
    std::string s(16, '0');
    for (int i = 0; i < 16; ++i) s[size_t(i)] = hex[(h >> (60 - 4 * i)) & 15];
    return s + ".png";
}
inline bool isIconFileName(const std::string& n)
{
    if (n.size() != 20 || n.compare(16, 4, ".png") != 0) return false;
    for (size_t i = 0; i < 16; ++i) if (!((n[i] >= '0' && n[i] <= '9') || (n[i] >= 'a' && n[i] <= 'f'))) return false;
    return true;
}

// Capture again? (unknown, a week old, or a clock that went backwards by more than a day)
inline bool needsCapture(bool known, long long stamp, long long now)
{
    return !known || now - stamp >= kRefreshSecs || stamp > now + 86400;
}

// --- the disk cache's index (LRU) ----------------------------------------------------------------------------------
// One entry per file: its size and stamp (the file's mtime = when it was captured; bumped in memory when drawn).
class Index {
public:
    struct File { uint64_t bytes = 0; long long stamp = 0; };
    bool has(const std::string& name) const { return files_.count(name) != 0; }
    long long stamp(const std::string& name) const { auto f = files_.find(name); return f == files_.end() ? 0 : f->second.stamp; }
    size_t count() const { return files_.size(); }
    uint64_t bytes() const { return bytes_; }
    void put(const std::string& name, uint64_t bytes, long long stamp)
    {
        remove(name);
        files_[name] = File { bytes, stamp };
        bytes_ += bytes;
    }
    void touch(const std::string& name, long long stamp)
    {
        auto f = files_.find(name);
        if (f != files_.end() && stamp > f->second.stamp) f->second.stamp = stamp;
    }
    bool remove(const std::string& name)
    {
        auto f = files_.find(name);
        if (f == files_.end()) return false;
        bytes_ -= f->second.bytes;
        files_.erase(f);
        return true;
    }
    // Over kMaxFiles / kMaxBytes: the oldest go (never `keep`, the one just written). Returns the names removed.
    std::vector<std::string> evict(const std::string& keep, size_t maxFiles = kMaxFiles, uint64_t maxBytes = kMaxBytes)
    {
        std::vector<std::string> out;
        while (files_.size() > maxFiles || bytes_ > maxBytes) {
            const std::string* oldest = nullptr;
            long long best = 0;
            for (const auto& [n, f] : files_) {
                if (n == keep) continue;
                if (!oldest || f.stamp < best || (f.stamp == best && n < *oldest)) { oldest = &n; best = f.stamp; }
            }
            if (!oldest) break;
            const std::string n = *oldest;
            remove(n);
            out.push_back(n);
        }
        return out;
    }
    // Clear browsing data / history by range: every icon captured (or used) at or after `start` goes.
    std::vector<std::string> removeSince(long long start)
    {
        std::vector<std::string> out;
        for (const auto& [n, f] : files_) if (f.stamp >= start) out.push_back(n);
        for (const auto& n : out) remove(n);
        return out;
    }
private:
    std::unordered_map<std::string, File> files_;
    uint64_t bytes_ = 0;
};

// --- PNG / base64 ----------------------------------------------------------------------------------------------------
inline uint32_t be32(const unsigned char* p) { return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3]; }
// A PNG whose header says kPx x kPx, 8 bits, a known colour type (libpng then decodes it for real).
inline bool isPng32(const std::string& b)
{
    static const unsigned char sig[8] = { 0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a };
    if (b.size() < 8 + 25 + 12 || b.size() > kMaxPngBytes) return false;
    const auto* u = reinterpret_cast<const unsigned char*>(b.data());
    for (int i = 0; i < 8; ++i) if (u[i] != sig[i]) return false;
    if (be32(u + 8) != 13 || b.compare(12, 4, "IHDR") != 0) return false;
    if (be32(u + 16) != uint32_t(kPx) || be32(u + 20) != uint32_t(kPx)) return false;
    const unsigned depth = u[24], type = u[25];
    if (depth != 8 || !(type == 0 || type == 2 || type == 3 || type == 4 || type == 6)) return false;
    return u[26] == 0 && u[27] == 0 && u[28] <= 1;
}
inline int b64val(unsigned char c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}
// Strict: length a multiple of 4, '=' only at the end (at most 2), nothing else.
inline bool base64Decode(const std::string& in, std::string& out)
{
    out.clear();
    if (in.size() % 4) return false;
    size_t pad = 0;
    while (pad < 2 && pad < in.size() && in[in.size() - 1 - pad] == '=') ++pad;
    out.reserve(in.size() / 4 * 3);
    for (size_t i = 0; i < in.size(); i += 4) {
        int v[4];
        for (int k = 0; k < 4; ++k) {
            const size_t at = i + size_t(k);
            if (at >= in.size() - pad) { v[k] = 0; continue; }
            v[k] = b64val(static_cast<unsigned char>(in[at]));
            if (v[k] < 0) return false;
        }
        const uint32_t n = uint32_t(v[0]) << 18 | uint32_t(v[1]) << 12 | uint32_t(v[2]) << 6 | uint32_t(v[3]);
        out += char((n >> 16) & 255);
        if (i + 2 < in.size() - pad) out += char((n >> 8) & 255);
        if (i + 3 < in.size() - pad) out += char(n & 255);
    }
    return true;
}
inline std::string base64Encode(const std::string& in)
{
    static const char* const t = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    out.reserve((in.size() + 2) / 3 * 4);
    for (size_t i = 0; i < in.size(); i += 3) {
        const uint32_t n = uint32_t(static_cast<unsigned char>(in[i])) << 16
            | (i + 1 < in.size() ? uint32_t(static_cast<unsigned char>(in[i + 1])) << 8 : 0)
            | (i + 2 < in.size() ? uint32_t(static_cast<unsigned char>(in[i + 2])) : 0);
        out += t[(n >> 18) & 63];
        out += t[(n >> 12) & 63];
        out += i + 1 < in.size() ? t[(n >> 6) & 63] : '=';
        out += i + 2 < in.size() ? t[n & 63] : '=';
    }
    return out;
}
// For the old new-tab page's <img src>: only a PNG this module validated.
inline std::string dataUrl(const std::string& png) { return isPng32(png) ? "data:image/png;base64," + base64Encode(png) : std::string(); }

// --- the page script's answer --------------------------------------------------------------------------------------
// "omni-fav;<location.hostname>;png;data:image/png;base64,...."  or  "omni-fav;<host>;none;<why>"
struct Answer {
    bool ok = false;        // a valid 32 x 32 PNG for `host`
    std::string host;       // hostKey of the page that answered
    std::string png;        // the PNG bytes
    std::string why;        // "none" reason (log only)
};
inline Answer parseAnswer(const std::string& text)
{
    Answer a;
    if (text.size() > kMaxAnswer) { a.why = "too big"; return a; }
    const std::string tag = std::string(kAnswerTag) + ";";
    if (text.compare(0, tag.size(), tag) != 0) { a.why = "no answer"; return a; }
    const size_t h1 = text.find(';', tag.size());
    if (h1 == std::string::npos) { a.why = "bad answer"; return a; }
    a.host = hostKey("https://" + text.substr(tag.size(), h1 - tag.size()) + "/");
    const size_t k1 = text.find(';', h1 + 1);
    if (k1 == std::string::npos || a.host.empty()) { a.why = "bad answer"; return a; }
    const std::string kind = text.substr(h1 + 1, k1 - h1 - 1), rest = text.substr(k1 + 1);
    if (kind != "png") { a.why = rest.substr(0, 40); return a; }
    static const std::string prefix = "data:image/png;base64,";
    if (rest.compare(0, prefix.size(), prefix) != 0) { a.why = "not a PNG data URL"; return a; }
    if (!base64Decode(rest.substr(prefix.size()), a.png) || !isPng32(a.png)) { a.png.clear(); a.why = "bad PNG"; return a; }
    a.ok = true;
    return a;
}

// --- scaling (straight alpha RGBA in and out; premultiplied while filtering) ---------------------------------------
// Down: area average (each source pixel weighted by its covered fraction). Up: bilinear. dst is dw * dh * 4 bytes.
inline void scaleRgba(const uint8_t* src, int sw, int sh, uint8_t* dst, int dw, int dh)
{
    if (sw <= 0 || sh <= 0 || dw <= 0 || dh <= 0) return;
    auto px = [&](int x, int y, double* acc, double w) {
        const uint8_t* p = src + (size_t(y) * size_t(sw) + size_t(x)) * 4;
        const double a = p[3] / 255.0;
        acc[0] += p[0] * a * w; acc[1] += p[1] * a * w; acc[2] += p[2] * a * w; acc[3] += p[3] * w;
    };
    for (int dy = 0; dy < dh; ++dy) {
        for (int dx = 0; dx < dw; ++dx) {
            double acc[4] = { 0, 0, 0, 0 }, total = 0;
            if (dw <= sw && dh <= sh) {
                const double x0 = double(dx) * sw / dw, x1 = double(dx + 1) * sw / dw;
                const double y0 = double(dy) * sh / dh, y1 = double(dy + 1) * sh / dh;
                for (int y = int(y0); y < sh && y < y1; ++y) {
                    const double wy = (y + 1 < y1 ? y + 1 : y1) - (y > y0 ? y : y0);
                    for (int x = int(x0); x < sw && x < x1; ++x) {
                        const double wx = (x + 1 < x1 ? x + 1 : x1) - (x > x0 ? x : x0);
                        if (wx > 0 && wy > 0) { px(x, y, acc, wx * wy); total += wx * wy; }
                    }
                }
            } else {
                double fx = (dx + 0.5) * sw / dw - 0.5, fy = (dy + 0.5) * sh / dh - 0.5;
                if (fx < 0) fx = 0;
                if (fy < 0) fy = 0;
                if (fx > sw - 1) fx = sw - 1;
                if (fy > sh - 1) fy = sh - 1;
                const int x0 = int(fx), y0 = int(fy), x1 = x0 + 1 < sw ? x0 + 1 : x0, y1 = y0 + 1 < sh ? y0 + 1 : y0;
                const double tx = fx - x0, ty = fy - y0;
                px(x0, y0, acc, (1 - tx) * (1 - ty)); px(x1, y0, acc, tx * (1 - ty));
                px(x0, y1, acc, (1 - tx) * ty);       px(x1, y1, acc, tx * ty);
                total = 1;
            }
            uint8_t* o = dst + (size_t(dy) * size_t(dw) + size_t(dx)) * 4;
            const double a = total > 0 ? acc[3] / total : 0;
            if (a < 0.5) { o[0] = o[1] = o[2] = o[3] = 0; continue; }
            for (int c = 0; c < 3; ++c) {
                const double v = acc[c] / total / (a / 255.0);
                o[c] = uint8_t(v < 0 ? 0 : v > 255 ? 255 : v + 0.5);
            }
            o[3] = uint8_t(a > 255 ? 255 : a + 0.5);
        }
    }
}

// --- the capture script ----------------------------------------------------------------------------------------------
// The body of an async function (WKPageCallAsyncJavaScriptWithoutUserGesture), run in the page after it loaded.
// Omni does no networking of its own: the page's own document loads the icon (an <img> in the page's context: the
// page's session, cookies, cache, CSP and content blockers; a private tab's ephemeral session), draws it into a
// 32 x 32 canvas and hands back canvas.toDataURL("image/png"). A canvas tainted by a cross-origin image throws: such an
// icon is tried again with crossOrigin = "anonymous" (works when its server sends CORS headers) and else skipped.
// ICO / SVG / JPEG / WebP all come back as PNG (WebKit's own decoders). Candidates: <link rel~=icon> (best size near
// 32 first), apple-touch-icon, then /favicon.ico of the page's origin.
inline std::string captureScript()
{
    std::string s = "const tag = \"" + std::string(kAnswerTag) + "\", px = " + std::to_string(kPx) + ", stepMs = " + std::to_string(kStepMs)
        + ", allMs = " + std::to_string(kScriptMs) + ", maxTries = " + std::to_string(kMaxCandidates) + ", maxLen = " + std::to_string(kMaxAnswer - 300) + ";\n";
    s += R"JS(const P = Promise, race = Promise.race.bind(Promise), later = setTimeout, host = location.hostname;
const toURL = HTMLCanvasElement.prototype.toDataURL;
const answer = (kind, rest) => tag + ";" + host + ";" + kind + ";" + rest;
const web = u => typeof u === "string" && /^(https?:|data:image\/)/i.test(u);
const sizeOf = l => {
  let best = 0;
  for (const t of String(l.getAttribute("sizes") || "").split(/\s+/)) {
    if (t.toLowerCase() === "any") return -1;
    const m = /^(\d{1,4})x(\d{1,4})$/i.exec(t);
    if (m) best = Math.max(best, Math.min(+m[1], +m[2]));
  }
  return best;
};
const rank = (l, touch) => {
  const s = sizeOf(l), svg = /svg/i.test(String(l.getAttribute("type") || "")) || /\.svg(\?|#|$)/i.test(l.href);
  if (touch) return 50;
  if (svg || s < 0) return 5;
  if (s === 0) return 10;
  if (s >= px && s <= 2 * px) return s - px;
  if (s > 2 * px) return 20 + s / 64;
  return 40 + (px - s);
};
const candidates = () => {
  const list = [];
  for (const l of Array.from(document.querySelectorAll("link[rel][href]")).slice(0, 64)) {
    const rel = String(l.getAttribute("rel") || "").toLowerCase().split(/\s+/);
    const touch = rel.includes("apple-touch-icon") || rel.includes("apple-touch-icon-precomposed");
    if (!touch && !rel.includes("icon")) continue;
    if (!web(l.href) || l.href.length > 4096) continue;
    list.push({ url: l.href, r: rank(l, touch) });
  }
  list.sort((a, b) => a.r - b.r);
  const urls = [];
  for (const c of list) if (!urls.includes(c.url) && urls.length < maxTries) urls.push(c.url);
  if (/^https?:$/.test(location.protocol)) {
    const fav = location.origin + "/favicon.ico";
    if (!urls.includes(fav)) urls.push(fav);
  }
  return urls;
};
const load = (url, cors) => new P(res => {
  const img = new Image();
  let done = false;
  const fin = ok => { if (done) return; done = true; res(ok ? img : null); };
  img.onload = () => fin(img.naturalWidth > 0 && img.naturalHeight > 0);
  img.onerror = () => fin(false);
  later(() => fin(false), stepMs);
  if (cors) img.crossOrigin = "anonymous";
  img.decoding = "sync";
  img.src = url;
});
const draw = img => {
  const c = document.createElement("canvas");
  c.width = px; c.height = px;
  const g = c.getContext("2d");
  if (!g) return "";
  g.imageSmoothingEnabled = true;
  g.imageSmoothingQuality = "high";
  const w = img.naturalWidth, h = img.naturalHeight, k = Math.min(px / w, px / h);
  const dw = Math.max(1, Math.round(w * k)), dh = Math.max(1, Math.round(h * k));
  g.drawImage(img, Math.floor((px - dw) / 2), Math.floor((px - dh) / 2), dw, dh);
  return toURL.call(c, "image/png");
};
const sameOrigin = u => { try { return new URL(u, location.href).origin === location.origin || /^data:/i.test(u); } catch (e) { return false; } };
const work = async () => {
  let why = "no icon";
  for (const url of candidates()) {
    for (const cors of sameOrigin(url) ? [false, true] : [true]) {
      const img = await load(url, cors);
      if (!img) { why = "not loaded"; break; }
      try {
        const d = draw(img);
        if (typeof d === "string" && d.startsWith("data:image/png;base64,") && d.length <= maxLen) return answer("png", d);
        why = "bad canvas";
        break;
      } catch (e) { why = "tainted"; }
    }
  }
  return answer("none", why);
};
return await race([work(), new P(r => later(() => r(answer("none", "timeout")), allMs))]);
)JS";
    return s;
}

} // namespace OmniFavicons
'''

SHELL = r'''// OMNI_FAVICONS_V1: site icons (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniLinkPreviewShell.h). The pure part is OmniFavicons.h; the reasons are in tools/apply_favicons.py.
// Main thread only, except the file writes / deletes, which go to the background writer (omniIoJobs).
//   capture: finished() -> omniFavFinished: one page script per host (none while one is fresh on disk), the page draws
//            its own icon into a 32 x 32 canvas; Omni opens no connection of its own.
//   store:   normal tabs -> memory + /data/omni/icons/<fnv64(host)>.png (300 files / 2 MB, LRU); private tabs and
//            "Don't save history" -> memory only (private icons are dropped once no private tab is left).
//   draw:    tab strips, Tabs panel / bookmark rows (OmniFxRow::favicon), History, tab search, tab switcher, the old
//            new-tab page; the letter stays wherever no icon is known.
#pragma once

namespace OFAV = OmniFavicons;

struct OmniFavIcon {
    std::string png;                  // the 32 x 32 PNG (validated)
    std::vector<uint8_t> rgba;        // decoded, straight alpha; empty: not decoded yet / undecodable
    bool bad = false;                 // libpng refused it
};
static std::unordered_map<std::string, OmniFavIcon> omniFavMem;      // file name -> icon (normal tabs)
static std::unordered_map<std::string, OmniFavIcon> omniFavPriv;     // file name -> icon (private tabs; never written)
static std::unordered_map<std::string, SDL_Surface*> omniFavScaled;  // "p|name|px" -> drawn size
static OFAV::Index omniFavIndex;                                       // the files in /data/omni/icons
static bool omniFavScanned = false;
static std::unordered_set<std::string> omniFavTried, omniFavTriedPriv;  // hosts captured / asked this session
static int omniFavInFlight = 0;
static uint32_t omniFavLoadTick = 0;
static int omniFavLoadBudget = 0;                                       // disk loads left in this frame

static std::string omniFavDir() { return omniData(OFAV::kDirName); }
static void omniFavDropScaled()
{
    for (auto& [k, s] : omniFavScaled) if (s) SDL_FreeSurface(s);
    omniFavScaled.clear();
}
// The background writer runs `run` after the writes queued before it.
static void omniFavIoRun(std::function<void()> run)
{
    {
        std::lock_guard<std::mutex> lock(omniIoLock);
        omniIoJobs.push_back({ std::string(), std::string(), true });
        omniIoJobs.back().run = std::move(run);
        if (!omniIoThread) omniIoThread = new std::thread(omniIoMain);
    }
    omniIoWake.notify_one();
}
static void omniFavUnlink(const std::vector<std::string>& names)
{
    if (names.empty()) return;
    const std::string dir = omniFavDir();
    omniFavIoRun([dir, names] { for (const auto& n : names) unlink((dir + n).c_str()); });
}
// The index of /data/omni/icons (once, on first need): file names, sizes, mtimes. Odd files are left alone; oversized
// icons and anything over the caps are deleted.
static void omniFavScan()
{
    if (omniFavScanned) return;
    omniFavScanned = true;
    const std::string dir = omniFavDir();
    mkdir(dir.c_str(), 0755);
    std::vector<std::string> drop;
    if (DIR* d = opendir(dir.c_str())) {
        int seen = 0;
        while (dirent* e = readdir(d)) {
            if (++seen > 2000) break;
            const std::string n = e->d_name;
            if (!OFAV::isIconFileName(n)) continue;
            struct stat st {};
            if (stat((dir + n).c_str(), &st) || !S_ISREG(st.st_mode)) continue;
            if (st.st_size <= 0 || size_t(st.st_size) > OFAV::kMaxPngBytes) { drop.push_back(n); continue; }
            omniFavIndex.put(n, uint64_t(st.st_size), (long long)st.st_mtime);
        }
        closedir(d);
    }
    for (auto& n : omniFavIndex.evict(std::string())) drop.push_back(n);
    omniFavUnlink(drop);
    fprintf(stderr, "OMNI FAVICONS: %zu icons, %llu bytes on disk%s\n", omniFavIndex.count(), (unsigned long long)omniFavIndex.bytes(),
            drop.empty() ? "" : " (some removed)"); fflush(stderr);
}
static bool omniFavDecode(OmniFavIcon& ic)
{
    if (!ic.rgba.empty()) return true;
    if (ic.bad || !OFAV::isPng32(ic.png)) { ic.bad = true; return false; }
    png_image image {};
    image.version = PNG_IMAGE_VERSION;
    bool ok = false;
    if (png_image_begin_read_from_memory(&image, ic.png.data(), ic.png.size()) && image.width == unsigned(OFAV::kPx) && image.height == unsigned(OFAV::kPx)) {
        image.format = PNG_FORMAT_RGBA;
        ic.rgba.assign(size_t(OFAV::kPx) * OFAV::kPx * 4, 0);
        ok = png_image_finish_read(&image, nullptr, ic.rgba.data(), OFAV::kPx * 4, nullptr) != 0;
    }
    png_image_free(&image);
    if (!ok) { ic.rgba.clear(); ic.bad = true; }
    return ok;
}
// Private icons live only while a private tab does.
static void omniFavPrivPrune()
{
    if (omniFavPriv.empty() && omniFavTriedPriv.empty()) return;
    for (auto& t : tabs) if (t->omniPrivate) return;
    omniFavPriv.clear();
    omniFavTriedPriv.clear();
    omniFavDropScaled();
}
// The icon for a page address (nullptr: none known / not loaded yet). Disk reads: a few per frame.
static OmniFavIcon* omniFavFind(const std::string& url, bool priv, std::string* nameOut = nullptr)
{
    const std::string name = OFAV::fileName(OFAV::hostKey(url));
    if (name.empty()) return nullptr;
    if (nameOut) *nameOut = name;
    if (priv) {
        omniFavPrivPrune();
        auto p = omniFavPriv.find(name);
        if (p != omniFavPriv.end()) return p->second.bad ? nullptr : &p->second;
    }
    auto m = omniFavMem.find(name);
    if (m != omniFavMem.end()) return m->second.bad ? nullptr : &m->second;
    omniFavScan();
    if (!omniFavIndex.has(name)) return nullptr;
    const uint32_t now = SDL_GetTicks();
    if (now - omniFavLoadTick >= 16) { omniFavLoadTick = now; omniFavLoadBudget = 4; }
    if (omniFavLoadBudget <= 0) { omniShellDirty = true; return nullptr; }   // next frame
    --omniFavLoadBudget;
    OmniFavIcon ic;
    if (FILE* f = fopen((omniFavDir() + name).c_str(), "rb")) {
        char buf[4096];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0 && ic.png.size() <= OFAV::kMaxPngBytes) ic.png.append(buf, n);
        fclose(f);
    }
    if (!OFAV::isPng32(ic.png)) {   // gone or damaged: forget it
        omniFavIndex.remove(name);
        omniFavUnlink({ name });
        return nullptr;
    }
    omniFavIndex.touch(name, (long long)time(nullptr));
    auto& slot = omniFavMem[name] = std::move(ic);
    return &slot;
}
// The icon at `px` physical pixels (cached per size).
static SDL_Surface* omniFavSurface(const std::string& url, bool priv, int px)
{
    if (px <= 0 || px > 512) return nullptr;
    std::string name;
    OmniFavIcon* ic = omniFavFind(url, priv, &name);
    if (!ic || !omniFavDecode(*ic)) return nullptr;
    const bool fromPriv = priv && omniFavPriv.count(name);
    const std::string key = std::string(fromPriv ? "p|" : "n|") + name + "|" + std::to_string(px);
    auto f = omniFavScaled.find(key);
    if (f != omniFavScaled.end()) return f->second;
    if (omniFavScaled.size() >= 128) omniFavDropScaled();
    SDL_Surface* s = SDL_CreateRGBSurfaceWithFormat(0, px, px, 32, SDL_PIXELFORMAT_RGBA32);
    if (s) {
        std::vector<uint8_t> out(size_t(px) * px * 4);
        OFAV::scaleRgba(ic->rgba.data(), OFAV::kPx, OFAV::kPx, out.data(), px, px);
        for (int y = 0; y < px; ++y) memcpy(static_cast<uint8_t*>(s->pixels) + size_t(y) * s->pitch, out.data() + size_t(y) * px * 4, size_t(px) * 4);
    }
    omniFavScaled[key] = s;
    return s;
}

// --- capture -------------------------------------------------------------------------------------------------------
struct OmniFavJob { WKRetainPtr<WKPageRef> page; std::string host, name; bool priv = false, disk = false; };
static std::string omniFavTabURL(const Tab& t)
{
    if (t.omniNewTabPage || t.omniPagesTab) return std::string();
    const std::string& u = !t.omniLazyURL.empty() ? t.omniLazyURL : t.url;
    return omniWebURL(u) ? u : std::string();
}
static void omniFavStore(OmniFavJob& j, std::string png)
{
    OmniFavIcon ic;
    ic.png = std::move(png);
    if (!omniFavDecode(ic)) { fprintf(stderr, "OMNI FAVICONS: %s: undecodable PNG\n", j.host.c_str()); fflush(stderr); return; }
    for (auto it = omniFavScaled.begin(); it != omniFavScaled.end();) {   // the old drawn sizes of this icon
        if (it->first.find(j.name) != std::string::npos) { if (it->second) SDL_FreeSurface(it->second); it = omniFavScaled.erase(it); }
        else ++it;
    }
    if (j.priv) { omniFavPriv[j.name] = std::move(ic); omniShellDirty = true; return; }
    const size_t bytes = ic.png.size();
    if (j.disk) {
        omniFavScan();
        omniFavIndex.put(j.name, bytes, (long long)time(nullptr));
        omniIoQueue(omniFavDir() + j.name, ic.png, false);   // .tmp + rename on the writer thread
        omniFavUnlink(omniFavIndex.evict(j.name));
    }
    omniFavMem[j.name] = std::move(ic);
    omniShellDirty = true;
    fprintf(stderr, "OMNI FAVICONS: %s: %zu-byte icon%s\n", j.host.c_str(), bytes, j.disk ? "" : " (memory only)"); fflush(stderr);
}
static void omniFavFinished(Tab& tab)
{
    if (omniTestMode() || tab.crashed) return;
    const std::string url = omniFavTabURL(tab);
    const std::string host = OFAV::hostKey(url), name = OFAV::fileName(host);
    if (name.empty()) return;
    const bool priv = tab.omniPrivate;
    if (priv) {
        omniFavPrivPrune();
        if (omniFavPriv.count(name) || omniFavTriedPriv.count(host)) return;
    } else {
        if (omniFavTried.count(host)) return;
        omniFavScan();
        if (!OFAV::needsCapture(omniFavIndex.has(name), omniFavIndex.stamp(name), (long long)time(nullptr))) return;
    }
    if (omniFavInFlight >= OFAV::kMaxInFlight) return;   // not marked: the next load of the host asks again
    auto& tried = priv ? omniFavTriedPriv : omniFavTried;
    if (tried.size() > 4000) tried.clear();
    tried.insert(host);
    auto* j = new OmniFavJob;
    j->page = tab.page;
    j->host = host;
    j->name = name;
    j->priv = priv;
    j->disk = !priv && !omniHkOff();   // "Don't save history": icons stay in memory too
    ++omniFavInFlight;
    static const std::string script = OFAV::captureScript();
    auto body = adoptWK(WKStringCreateWithUTF8CString(script.c_str()));
    auto args = adoptWK(WKDictionaryCreate(nullptr, nullptr, 0));   // an async function needs an argument list
    WKPageCallAsyncJavaScriptWithoutUserGesture(tab.page, body.get(), args.get(), nullptr, j, [](WKTypeRef result, WKErrorRef error, void* ctx) {
        std::unique_ptr<OmniFavJob> job(static_cast<OmniFavJob*>(ctx));
        --omniFavInFlight;
        if (!running) return;
        const OFAV::Answer a = OFAV::parseAnswer(omniFxResultString(result, error));
        // The answer must come from the host that was asked about, and the tab (if still open) must still show it:
        // a navigation between the call and the script would otherwise file another site's icon under this host.
        Tab* t = omniTabForPage(job->page.get());
        const bool same = a.host == job->host && (!t || OFAV::hostKey(omniFavTabURL(*t)) == job->host);
        if (!a.ok || !same) {
            fprintf(stderr, "OMNI FAVICONS: %s: no icon (%s)\n", job->host.c_str(), !same && a.ok ? "page changed" : a.why.c_str()); fflush(stderr);
            return;
        }
        if (job->priv && !(t && t->omniPrivate)) { bool any = false; for (auto& x : tabs) any = any || x->omniPrivate; if (!any) return; }
        omniFavStore(*job, a.png);
    });
}

// --- forgetting (history / Clear browsing data) ------------------------------------------------------------------
static void omniFavForgetHost(const std::string& host)
{
    const std::string name = OFAV::fileName(OFAV::hostKey("https://" + host + "/"));
    if (name.empty()) return;
    omniFavScan();
    omniFavMem.erase(name);
    omniFavTried.clear();
    omniFavDropScaled();
    if (omniFavIndex.remove(name)) omniFavUnlink({ name });
}
// History cleared from `start` (unix seconds; 0 / earlier: all time): the icons captured or used since then go.
static void omniFavHistoryCleared(long long start)
{
    omniFavScan();
    const std::vector<std::string> gone = omniFavIndex.removeSince(start);
    for (const auto& n : gone) omniFavMem.erase(n);
    if (start <= 0) omniFavMem.clear();
    omniFavTried.clear();
    omniFavDropScaled();
    omniFavUnlink(gone);
    fprintf(stderr, "OMNI FAVICONS: history cleared, %zu icons removed\n", gone.size()); fflush(stderr);
}

// --- drawing -------------------------------------------------------------------------------------------------------
// The icon centred on (cx, cy), `size` layout px square. false: none known (the caller draws its letter / glyph).
static bool omniFavDraw(const std::string& url, bool priv, float cx, float cy, int size)
{
    if (url.empty()) return false;
    const int px = physical(size);
    SDL_Surface* s = omniFavSurface(url, priv, px);
    if (!s) return false;
    const int x = int(cx * displayScale + 0.5) - px / 2, y = int(cy * displayScale + 0.5) - px / 2;
    if (!omniBlendSurface(s, x, y, 0, 255)) { SDL_Rect d { x, y, px, px }; SDL_BlitSurface(s, nullptr, canvas, &d); }
    return true;
}
// The tab switcher's square: a light plate with the icon (false: none known, the coloured letter tile stays).
static bool omniFavTile(const std::string& url, bool priv, int x, int y, int sq)
{
    if (url.empty() || !omniFavSurface(url, priv, physical(sq * 5 / 8))) return false;
    fillRounded(x, y, sq, sq, omniRadius + 2, { 246, 246, 248, 255 });
    return omniFavDraw(url, priv, x + sq / 2.f, y + sq / 2.f, sq * 5 / 8);
}
// A list row's mark centred on (x, cy): the site's icon, else a small disc in the site's colour with its letter (the
// tab switcher's colour and letter).
static void omniFavMark(const std::string& url, bool priv, const std::string& title0, int x, float cy)
{
    if (omniFavDraw(url, priv, float(x), cy, 22)) return;
    const size_t a = title0.find_first_not_of(' ');
    const std::string title = a == std::string::npos ? std::string() : title0.substr(a);
    const OTSW::Rgb c = OTSW::colour(OTSW::colourIndex(url, title));
    omniDisc(float(x), cy, 12.f, { c.r, c.g, c.b, 255 });
    omniLabel(OTSW::letter(url, title), float(x), cy, omniCaptionBold, { 255, 255, 255, 255 }, 1);
}
// A panel row with a page address (OmniFxRow::favicon): its mark where a row icon goes. false: not such a row.
static bool omniFavRow(const OmniFxRow& r, int x, float cy)
{
    if (r.favicon.empty()) return false;
    omniFavMark(r.favicon, r.faviconPriv, r.label, x, cy);
    return true;
}
// The old new-tab page's tile icon: <i class="f"><img></i> when known, else the letter as before.
static std::string omniFavTileHtml(const std::string& url, const std::string& letter)
{
    if (OmniFavIcon* ic = omniFavFind(url, false)) {
        const std::string d = OFAV::dataUrl(ic->png);
        if (!d.empty()) return "<i class=\"f\"><img alt=\"\" src=\"" + d + "\"></i>";
    }
    return "<i>" + omniHtmlEscape(letter) + "</i>";
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        (r'''#include "OmniClearRange.h" /* OMNI_CLEAR_RANGE_V1: Clear browsing data by time range and category (pure) */
''',
         r'''#include "OmniClearRange.h" /* OMNI_CLEAR_RANGE_V1: Clear browsing data by time range and category (pure) */
#include "OmniFavicons.h" /* OMNI_FAVICONS_V1: site icons (pure) */
'''),
        (r'''static void omniHltFinished(Tab& tab); // OMNI_HIGHLIGHTS_V1 (OmniHighlightsShell.h): re-apply saved highlights
''',
         r'''static void omniHltFinished(Tab& tab); // OMNI_HIGHLIGHTS_V1 (OmniHighlightsShell.h): re-apply saved highlights
/* OMNI_FAVICONS_V1 (OmniFaviconsShell.h): site icons: capture after a load, draw (false: none known), forget */
static void omniFavFinished(Tab& tab);
static std::string omniFavTabURL(const Tab& t);
static bool omniFavDraw(const std::string& url, bool priv, float cx, float cy, int size);
static bool omniFavTile(const std::string& url, bool priv, int x, int y, int sq);
static void omniFavMark(const std::string& url, bool priv, const std::string& title, int x, float cy);
static bool omniFavRow(const OmniFxRow& r, int x, float cy);
static std::string omniFavTileHtml(const std::string& url, const std::string& letter);
static void omniFavForgetHost(const std::string& host);
static void omniFavHistoryCleared(long long start);
'''),
        (r'''    omniHltFinished(tab); // OMNI_HIGHLIGHTS_V1: this page's saved highlights
''',
         r'''    omniHltFinished(tab); // OMNI_HIGHLIGHTS_V1: this page's saved highlights
    omniFavFinished(tab); // OMNI_FAVICONS_V1: the site's icon (a page script; once per host, none while cached)
'''),
        (r'''        else if (tab.crashed || !tab.message.empty()) { omniDisc(x + 21, 30, 4, tab.crashed ? omniBad : omniWarn); tx = x + 34; }
''',
         r'''        else if (tab.crashed || !tab.message.empty()) { omniDisc(x + 21, 30, 4, tab.crashed ? omniBad : omniWarn); tx = x + 34; }
        else if (omniFavDraw(omniFavTabURL(tab), tab.omniPrivate, x + 24.f, 30.f, 18)) tx = x + 38; /* OMNI_FAVICONS_V1: the site's icon */
'''),
        (r'''        "a.s{opacity:.55;background:transparent;outline:2px dashed var(--line);outline-offset:-2px}a.s:hover,a.s:focus{opacity:1;outline:2px solid var(--accent)}a.s i{background:var(--inkFaint)}" // OMNI_SEARCH_TILES_V1
''',
         r'''        "a.s{opacity:.55;background:transparent;outline:2px dashed var(--line);outline-offset:-2px}a.s:hover,a.s:focus{opacity:1;outline:2px solid var(--accent)}a.s i{background:var(--inkFaint)}" // OMNI_SEARCH_TILES_V1
        "a i.f{background:#fff}a i.f img{width:30px;height:30px}" /* OMNI_FAVICONS_V1: the site's icon instead of the letter */
'''),
        (r'''        h += "<a href=\"" + omniHtmlEscape(url) + "\"><i>" + omniHtmlEscape(letter) + "</i><span><b>" + omniHtmlEscape(title.empty() ? shown : title)
''',
         r'''        h += "<a href=\"" + omniHtmlEscape(url) + "\">" + omniFavTileHtml(url, letter) + "<span><b>" + omniHtmlEscape(title.empty() ? shown : title) /* OMNI_FAVICONS_V1 */
'''),
        (r'''            h += "<a class=\"s\" href=\"" + omniHtmlEscape(st.url) + "\" title=\"Suggested: often visited, not saved\"><i>" + omniHtmlEscape(letter)
                + "</i><span><b>" + omniHtmlEscape(st.title) + "</b><small>Suggested \xC2\xB7 " + omniHtmlEscape(st.host) + "</small></span></a>";
''',
         r'''            h += "<a class=\"s\" href=\"" + omniHtmlEscape(st.url) + "\" title=\"Suggested: often visited, not saved\">" + omniFavTileHtml(st.url, letter) /* OMNI_FAVICONS_V1 */
                + "<span><b>" + omniHtmlEscape(st.title) + "</b><small>Suggested \xC2\xB7 " + omniHtmlEscape(st.host) + "</small></span></a>";
'''),
        (r'''        const int w = omniLabel(v.title.empty() ? bare : v.title, omniHistoryX + 32, cy, omniBody, ink, 0, 560);
        omniLabel(bare, omniHistoryX + 48 + w, cy, omniSmall, dim, 0, std::max(0, omniHistoryW - 230 - w));
''',
         r'''        omniFavMark(v.url, false, v.title.empty() ? bare : v.title, omniHistoryX + 42, cy); /* OMNI_FAVICONS_V1: the site's icon, else its letter */
        const int w = omniLabel(v.title.empty() ? bare : v.title, omniHistoryX + 66, cy, omniBody, ink, 0, 526); /* OMNI_FAVICONS_V1: after the icon (was x + 32, 560) */
        omniLabel(bare, omniHistoryX + 82 + w, cy, omniSmall, dim, 0, std::max(0, omniHistoryW - 264 - w));
'''),
        (r'''        notice("History cleared: " + OHP::visits(removed) + " removed");
''',
         r'''        omniFavHistoryCleared(OHP::rangeStart(range, when, omniHpUtcOffset(when))); /* OMNI_FAVICONS_V1: their icons too */
        notice("History cleared: " + OHP::visits(removed) + " removed");
'''),
        (r'''        notice(host + ": " + OHP::visits(removed) + " removed from history");
''',
         r'''        omniFavForgetHost(host); /* OMNI_FAVICONS_V1: its icon too */
        notice(host + ": " + OHP::visits(removed) + " removed from history");
'''),
    ],
    'OmniFeaturesPanel.h': [
        (r'''    std::string prefix;            // OMNI_SETTINGS_SEARCH_V1: dim text before the label (a found setting's section)
''',
         r'''    std::string prefix;            // OMNI_SETTINGS_SEARCH_V1: dim text before the label (a found setting's section)
    std::string favicon;           // OMNI_FAVICONS_V1: a page address: the site's icon (else its letter) where icon goes
    bool faviconPriv = false;      // OMNI_FAVICONS_V1: a private tab's row (its icon is in memory only)
'''),
        (r'''            if (r.icon >= 0) { omniIcon(r.icon, g.x + 42, cy, ink); lx = g.x + 66; }
''',
         r'''            if (r.icon >= 0) { omniIcon(r.icon, g.x + 42, cy, ink); lx = g.x + 66; }
            else if (omniFavRow(r, g.x + 42, cy)) lx = g.x + 66; /* OMNI_FAVICONS_V1: the site's icon, else its letter */
'''),
    ],
    'OmniTabsPage.h': [
        (r'''        omniWapTabRow(t, r); // OMNI_WEB_APPS_V1: "App"
''',
         r'''        omniWapTabRow(t, r); // OMNI_WEB_APPS_V1: "App"
        r.favicon = omniFavTabURL(t); r.faviconPriv = t.omniPrivate; /* OMNI_FAVICONS_V1 */
'''),
    ],
    'OmniBookmarksShell.h': [
        (r'''            r.detail = (omniBmQuery.empty() || e.folder.empty() ? std::string() : e.folder + " \xc2\xb7 ") + omniShownURL(e.url);
''',
         r'''            r.detail = (omniBmQuery.empty() || e.folder.empty() ? std::string() : e.folder + " \xc2\xb7 ") + omniShownURL(e.url);
            r.favicon = omniWebURL(e.url) ? e.url : std::string(); /* OMNI_FAVICONS_V1 */
'''),
    ],
    'OmniTabSearchShell.h': [
        (r'''    // a tab: a nub on the top-left of an outlined page (2 px line)
''',
         r'''    if (s.omniTqKind == OTQ::kSwitch && omniFavDraw(s.url, s.omniTqPrivate, x + 11.f, cy, 22)) return 30; /* OMNI_FAVICONS_V1: the tab's site icon */
    // a tab: a nub on the top-left of an outlined page (2 px line)
'''),
    ],
    'OmniTabSwitcherShell.h': [
        (r'''        omniLabel(t->omniNewTabPage ? std::string("+") : OTSW::letter(site, t->title), sx + sq / 2.f, sy + sq / 2.f, omniTitle, { 255, 255, 255, 255 }, 1);
''',
         r'''        if (t->omniNewTabPage || !omniFavTile(site, t->omniPrivate, sx, sy, sq)) /* OMNI_FAVICONS_V1: the site's icon on a light plate, else the letter */
        omniLabel(t->omniNewTabPage ? std::string("+") : OTSW::letter(site, t->title), sx + sq / 2.f, sy + sq / 2.f, omniTitle, { 255, 255, 255, 255 }, 1);
'''),
    ],
    'OmniPinnedTabsShell.h': [
        (r'''            else omniLabel(OPT::initial(omniPtURL(tab), tab.title), s.x + 37, 30, omniSmall, ink, 1);
''',
         r'''            else if (!omniFavDraw(omniFavTabURL(tab), tab.omniPrivate, s.x + 37.f, 30.f, 18)) /* OMNI_FAVICONS_V1: the site's icon, else the letter */
                omniLabel(OPT::initial(omniPtURL(tab), tab.title), s.x + 37, 30, omniSmall, ink, 1);
'''),
        (r'''        else if (tab.crashed || !tab.message.empty()) { omniDisc(s.x + 17, 30, 4, tab.crashed ? omniBad : omniWarn); tx = s.x + 28; }
''',
         r'''        else if (tab.crashed || !tab.message.empty()) { omniDisc(s.x + 17, 30, 4, tab.crashed ? omniBad : omniWarn); tx = s.x + 28; }
        else if (omniFavDraw(omniFavTabURL(tab), tab.omniPrivate, s.x + 20.f, 30.f, 18)) tx = s.x + 34; /* OMNI_FAVICONS_V1: the site's icon */
'''),
    ],
    'OmniTabMemory.h': [
        (r'''        else if (tab.crashed || !tab.message.empty()) { omniDisc(x + 17, 30, 4, tab.crashed ? omniBad : omniWarn); tx = x + 28; }
''',
         r'''        else if (tab.crashed || !tab.message.empty()) { omniDisc(x + 17, 30, 4, tab.crashed ? omniBad : omniWarn); tx = x + 28; }
        else if (omniFavDraw(omniFavTabURL(tab), tab.omniPrivate, x + 20.f, 30.f, 18)) tx = x + 34; /* OMNI_FAVICONS_V1: the site's icon */
'''),
    ],
    'OmniClearRangeShell.h': [
        (r'''        if (j->res.visits) omniHpChanged();   // history.txt rewrite, suggestions, most visited
''',
         r'''        if (j->res.visits) omniHpChanged();   // history.txt rewrite, suggestions, most visited
        omniFavHistoryCleared(start); /* OMNI_FAVICONS_V1: the site icons captured / used in the range */
'''),
    ],
    'OmniFeatures3.h': [
        (r'''#include "OmniLinkPreviewShell.h" // OMNI_LINK_PREVIEW_V1
''',
         r'''#include "OmniLinkPreviewShell.h" // OMNI_LINK_PREVIEW_V1
#include "OmniFaviconsShell.h" // OMNI_FAVICONS_V1: site icons (capture, cache, drawing; after the strips and panels it draws in)
'''),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    if 'OMNI_LINK_PREVIEW_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_LINK_PREVIEW_V1 missing: apply_link_preview.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniFavicons.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniFaviconsShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
