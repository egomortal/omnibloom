#!/usr/bin/env python3
"""OMNI_QR_SHARE_V1 (2026-11-16): "Show QR code" for the current page, so a phone can scan the TV and open it.

What the user sees
  - Hold Cross on a page (the page context menu): a new row "Show QR code" right after "Copy page address"
    (disabled on omni:// / about: / new-tab pages: a phone can't open those).
  - It closes the menu and opens a centred panel: "Scan to open this page on your phone", a large QR code on white
    (white whatever the theme; 4-module quiet zone; whole-pixel modules, about 60% of the screen height), the
    shortened address under it ("example.com/path...end"), and "Tracking parameters removed" when any were.
    Circle (or Options) closes; every other button is taken by the panel; a mouse click off the panel closes it.
  - The code holds the page address minus tracking parameters (utm_* of any name, fbclid, gclid, si; names compared
    without case; everything else, its order, encoding and the #fragment kept as they were).
  - Private tabs: allowed. Nothing is written anywhere; the code exists only while the panel is open.
  - An address over 666 bytes (version 20, level M) gets a notice instead.
  The address bar has no action list (only the bookmark star), so there is no second entry point there.

Encoder: engine/entry/OmniQrShare.h, written for Omni (no third-party code): byte mode, level M, versions 1-20,
the mask chosen by the standard penalty score (rules 1-4, lowest index on ties). No SDL / WebKit types.
Tested by tools/test_qr_share.cpp: every mask forced matches python-qrcode 8.2 bit for bit (44 inputs, versions
1-20 at both edges of each version), the codes it chooses decode with OpenCV (tools/test_qr_share_ref.py).
  /tmp/qrvenv/bin/python -I test_qr_share_ref.py refs refs.txt
  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_qr_share.cpp -o t && ./t refs.txt mine.txt
  /tmp/qrvenv/bin/python -I test_qr_share_ref.py decode mine.txt
Shell side: engine/entry/OmniQrShareShell.h (included from OmniFeatures3.h after OmniSiteClearShell.h): the
context row + action, the panel, its own overlay layer (registered like OmniFeatures.h's, above the panels).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp     apply_site_clear.py's WKDictionary include line: the pure include goes after it.
  OmniContextMenu.h   apply_pinned_tabs.py's omniPtContextAction declaration (our two declarations after it),
                      the "Copy page address" row (our row after it), apply_pinned_tabs.py's dispatch line
                      (our dispatch after it).
  OmniFeatures3.h     the OmniSiteClearShell.h include line (our shell include after it).
Apply AFTER apply_site_clear.py and apply_pinned_tabs.py (their lines are anchors).
usage: apply_qr_share.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_QR_SHARE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_QR_SHARE_V1: the pure part of "Show QR code" (no SDL, no WebKit): a compact QR Code encoder (byte mode,
// error correction level M, versions 1-20, mask chosen by the standard penalty score; written for Omni from
// ISO/IEC 18004), the address cleaner (drops utm_*, fbclid, gclid, si from the query) and the panel layout.
// Tested by tools/test_qr_share.cpp against python-qrcode matrices (all 8 masks) and an OpenCV decode of its own
// codes (tools/test_qr_share_ref.py).
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <vector>

namespace OmniQr {

constexpr int kMinVersion = 1, kMaxVersion = 20;
constexpr int kQuiet = 4;                                  // quiet zone, modules on each side
// Error correction level M, by version (index 0 unused).
constexpr int kEccPerBlock[kMaxVersion + 1] = { -1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26 };
constexpr int kBlocks[kMaxVersion + 1] = { -1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16 };

struct Code {
    int version = 0, size = 0, mask = -1;
    std::vector<uint8_t> dark;                             // size * size, row major (1: dark module)
    bool at(int x, int y) const { return x >= 0 && y >= 0 && x < size && y < size && dark[size_t(y) * size + x]; }
};

inline int rawModules(int ver)                             // data + ECC modules of a version (function patterns excluded)
{
    int r = (16 * ver + 128) * ver + 64;
    if (ver >= 2) {
        const int align = ver / 7 + 2;
        r -= (25 * align - 10) * align - 55;
        if (ver >= 7) r -= 36;
    }
    return r;
}
inline int dataCodewords(int ver) { return rawModules(ver) / 8 - kEccPerBlock[ver] * kBlocks[ver]; }
// Most bytes one code of `ver` holds in byte mode (mode 4 bits + count 8 / 16 bits).
inline int byteCapacity(int ver) { return (dataCodewords(ver) * 8 - 4 - (ver < 10 ? 8 : 16)) / 8; }
inline int maxBytes() { return byteCapacity(kMaxVersion); }   // 666

namespace detail {
inline uint8_t gfMul(uint8_t a, uint8_t b)
{
    int z = 0;
    for (int i = 7; i >= 0; --i) {
        z = (z << 1) ^ ((z >> 7) * 0x11D);
        z ^= ((b >> i) & 1) * a;
    }
    return uint8_t(z);
}
inline std::vector<uint8_t> rsDivisor(int degree)
{
    std::vector<uint8_t> r(static_cast<size_t>(degree), 0);
    r[size_t(degree) - 1] = 1;
    uint8_t root = 1;
    for (int i = 0; i < degree; ++i) {
        for (int j = 0; j < degree; ++j) {
            r[size_t(j)] = gfMul(r[size_t(j)], root);
            if (j + 1 < degree) r[size_t(j)] ^= r[size_t(j) + 1];
        }
        root = gfMul(root, 0x02);
    }
    return r;
}
inline std::vector<uint8_t> rsRemainder(const std::vector<uint8_t>& data, const std::vector<uint8_t>& div)
{
    std::vector<uint8_t> r(div.size(), 0);
    for (uint8_t b : data) {
        const uint8_t f = uint8_t(b ^ r[0]);
        r.erase(r.begin());
        r.push_back(0);
        for (size_t i = 0; i < r.size(); ++i) r[i] ^= gfMul(div[i], f);
    }
    return r;
}
inline std::vector<int> alignPositions(int ver)
{
    if (ver == 1) return {};
    const int n = ver / 7 + 2, size = ver * 4 + 17;
    const int step = (ver * 4 + n * 2 + 1) / (n * 2 - 2) * 2;
    std::vector<int> r(static_cast<size_t>(n), 0);
    r[0] = 6;
    for (int i = n - 1, pos = size - 7; i >= 1; --i, pos -= step) r[size_t(i)] = pos;
    return r;
}
inline bool maskBit(int mask, int x, int y)
{
    switch (mask) {
    case 0: return (x + y) % 2 == 0;
    case 1: return y % 2 == 0;
    case 2: return x % 3 == 0;
    case 3: return (x + y) % 3 == 0;
    case 4: return (x / 3 + y / 2) % 2 == 0;
    case 5: return x * y % 2 + x * y % 3 == 0;
    case 6: return (x * y % 2 + x * y % 3) % 2 == 0;
    default: return ((x + y) % 2 + x * y % 3) % 2 == 0;
    }
}

struct Grid {
    int size;
    std::vector<uint8_t> dark, fn;                         // fn: function module (finder, timing, alignment, format, version)
    explicit Grid(int s) : size(s), dark(size_t(s) * s, 0), fn(size_t(s) * s, 0) {}
    void setFn(int x, int y, bool d) { const size_t i = size_t(y) * size + x; dark[i] = d; fn[i] = 1; }
    bool get(int x, int y) const { return dark[size_t(y) * size + x] != 0; }
};
inline void drawFormat(Grid& g, int mask)
{
    const int data = (0 << 3) | mask;                      // level M = 00
    int rem = data;
    for (int i = 0; i < 10; ++i) rem = (rem << 1) ^ ((rem >> 9) * 0x537);
    const int bits = ((data << 10) | rem) ^ 0x5412;
    auto bit = [&](int i) { return ((bits >> i) & 1) != 0; };
    const int s = g.size;
    for (int i = 0; i <= 5; ++i) g.setFn(8, i, bit(i));
    g.setFn(8, 7, bit(6));
    g.setFn(8, 8, bit(7));
    g.setFn(7, 8, bit(8));
    for (int i = 9; i < 15; ++i) g.setFn(14 - i, 8, bit(i));
    for (int i = 0; i < 8; ++i) g.setFn(s - 1 - i, 8, bit(i));
    for (int i = 8; i < 15; ++i) g.setFn(8, s - 15 + i, bit(i));
    g.setFn(8, s - 8, true);                               // the dark module
}
inline void drawFunction(Grid& g, int ver)
{
    const int s = g.size;
    for (int i = 0; i < s; ++i) { g.setFn(6, i, i % 2 == 0); g.setFn(i, 6, i % 2 == 0); }
    const int fc[3][2] = { { 3, 3 }, { s - 4, 3 }, { 3, s - 4 } };
    for (auto& c : fc)
        for (int dy = -4; dy <= 4; ++dy)
            for (int dx = -4; dx <= 4; ++dx) {
                const int d = std::max(std::abs(dx), std::abs(dy)), x = c[0] + dx, y = c[1] + dy;
                if (x >= 0 && x < s && y >= 0 && y < s) g.setFn(x, y, d != 2 && d != 4);
            }
    const std::vector<int> al = alignPositions(ver);
    const int n = int(al.size());
    for (int i = 0; i < n; ++i)
        for (int j = 0; j < n; ++j) {
            if ((i == 0 && j == 0) || (i == 0 && j == n - 1) || (i == n - 1 && j == 0)) continue;
            for (int dy = -2; dy <= 2; ++dy)
                for (int dx = -2; dx <= 2; ++dx) g.setFn(al[size_t(i)] + dx, al[size_t(j)] + dy, std::max(std::abs(dx), std::abs(dy)) != 1);
        }
    drawFormat(g, 0);                                      // reserves the format area; redrawn with the chosen mask
    if (ver >= 7) {
        int rem = ver;
        for (int i = 0; i < 12; ++i) rem = (rem << 1) ^ ((rem >> 11) * 0x1F25);
        const long bits = long(ver) << 12 | rem;
        for (int i = 0; i < 18; ++i) {
            const bool b = ((bits >> i) & 1) != 0;
            const int a = s - 11 + i % 3, c = i / 3;
            g.setFn(a, c, b);
            g.setFn(c, a, b);
        }
    }
}
// Finder-like run patterns (rule 3), as in the reference penalty: runs are kept newest first.
inline void addRun(int run, int* h, int size)
{
    if (h[0] == 0) run += size;                            // light border before the first run
    for (int i = 6; i > 0; --i) h[i] = h[i - 1];
    h[0] = run;
}
inline int countPatterns(const int* h)
{
    const int n = h[1];
    const bool core = n > 0 && h[2] == n && h[3] == n * 3 && h[4] == n && h[5] == n;
    return (core && h[0] >= n * 4 && h[6] >= n ? 1 : 0) + (core && h[6] >= n * 4 && h[0] >= n ? 1 : 0);
}
inline int terminateCount(bool color, int run, int* h, int size)
{
    if (color) { addRun(run, h, size); run = 0; }
    run += size;
    addRun(run, h, size);
    return countPatterns(h);
}
} // namespace detail

// The standard penalty score of a finished matrix (lower is better).
inline long penalty(const Code& c)
{
    const int s = c.size;
    long r = 0;
    for (int pass = 0; pass < 2; ++pass)
        for (int a = 0; a < s; ++a) {
            bool color = false;
            int run = 0, h[7] = { 0, 0, 0, 0, 0, 0, 0 };
            for (int b = 0; b < s; ++b) {
                const bool m = pass == 0 ? c.at(b, a) : c.at(a, b);
                if (m == color) {
                    ++run;
                    if (run == 5) r += 3; else if (run > 5) ++r;
                } else {
                    detail::addRun(run, h, s);
                    if (!color) r += detail::countPatterns(h) * 40;
                    color = m;
                    run = 1;
                }
            }
            r += detail::terminateCount(color, run, h, s) * 40;
        }
    for (int y = 0; y + 1 < s; ++y)
        for (int x = 0; x + 1 < s; ++x) {
            const bool m = c.at(x, y);
            if (m == c.at(x + 1, y) && m == c.at(x, y + 1) && m == c.at(x + 1, y + 1)) r += 3;
        }
    long darkCount = 0;
    for (uint8_t d : c.dark) darkCount += d;
    const long total = long(s) * s;
    const long k = (std::labs(darkCount * 20 - total * 10) + total - 1) / total - 1;
    return r + k * 10;
}

// Encodes `bytes` (byte mode, level M) in the smallest version from minVersion that fits. forceMask 0-7 skips the
// penalty choice (tests). False: empty, or longer than maxBytes().
inline bool encode(const std::string& bytes, Code& out, int forceMask = -1, int minVersion = kMinVersion)
{
    out = Code();
    if (bytes.empty()) return false;
    const int len = int(bytes.size());
    int ver = std::max(kMinVersion, minVersion);
    while (ver <= kMaxVersion && byteCapacity(ver) < len) ++ver;
    if (ver > kMaxVersion) return false;

    // data codewords
    std::vector<uint8_t> bits;
    auto put = [&](uint32_t v, int n) { for (int i = n - 1; i >= 0; --i) bits.push_back(uint8_t((v >> i) & 1)); };
    put(4, 4);
    put(uint32_t(len), ver < 10 ? 8 : 16);
    for (unsigned char ch : bytes) put(ch, 8);
    const size_t capBits = size_t(dataCodewords(ver)) * 8;
    put(0, int(std::min<size_t>(4, capBits - bits.size())));
    put(0, int((8 - bits.size() % 8) % 8));
    for (uint8_t pad = 0xEC; bits.size() < capBits; pad ^= 0xEC ^ 0x11) put(pad, 8);
    std::vector<uint8_t> data(bits.size() / 8, uint8_t(0));
    for (size_t i = 0; i < bits.size(); ++i) data[i >> 3] |= uint8_t(bits[i] << (7 - (i & 7)));

    // blocks + error correction, interleaved
    const int nBlocks = kBlocks[ver], ecc = kEccPerBlock[ver], raw = rawModules(ver) / 8;
    const int nShort = nBlocks - raw % nBlocks, shortLen = raw / nBlocks;
    const std::vector<uint8_t> div = detail::rsDivisor(ecc);
    std::vector<std::vector<uint8_t>> blocks;
    for (int i = 0, k = 0; i < nBlocks; ++i) {
        const int dl = shortLen - ecc + (i < nShort ? 0 : 1);
        std::vector<uint8_t> dat(data.begin() + k, data.begin() + k + dl);
        k += dl;
        const std::vector<uint8_t> e = detail::rsRemainder(dat, div);
        if (i < nShort) dat.push_back(0);                  // placeholder: short blocks line up with long ones
        dat.insert(dat.end(), e.begin(), e.end());
        blocks.push_back(std::move(dat));
    }
    std::vector<uint8_t> all;
    for (size_t i = 0; i < blocks[0].size(); ++i)
        for (int j = 0; j < nBlocks; ++j)
            if (int(i) != shortLen - ecc || j >= nShort) all.push_back(blocks[size_t(j)][i]);

    // modules
    const int s = ver * 4 + 17;
    detail::Grid g(s);
    detail::drawFunction(g, ver);
    size_t i = 0;
    for (int right = s - 1; right >= 1; right -= 2) {
        if (right == 6) right = 5;
        for (int v = 0; v < s; ++v)
            for (int j = 0; j < 2; ++j) {
                const int x = right - j;
                const bool up = ((right + 1) & 2) == 0;
                const int y = up ? s - 1 - v : v;
                const size_t at = size_t(y) * s + x;
                if (!g.fn[at] && i < all.size() * 8) { g.dark[at] = (all[i >> 3] >> (7 - (i & 7))) & 1; ++i; }
            }
    }

    auto masked = [&](int mask) {
        detail::Grid m = g;
        for (int y = 0; y < s; ++y)
            for (int x = 0; x < s; ++x) {
                const size_t at = size_t(y) * s + x;
                if (!m.fn[at] && detail::maskBit(mask, x, y)) m.dark[at] ^= 1;
            }
        detail::drawFormat(m, mask);
        Code c;
        c.version = ver; c.size = s; c.mask = mask; c.dark = std::move(m.dark);
        return c;
    };
    if (forceMask >= 0 && forceMask < 8) { out = masked(forceMask); return true; }
    long best = -1;
    for (int mask = 0; mask < 8; ++mask) {
        Code c = masked(mask);
        const long p = penalty(c);
        if (best < 0 || p < best) { best = p; out = std::move(c); }
    }
    return true;
}

// --- the address ------------------------------------------------------------------------------------------------
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
// Tracking parameters dropped from the shared address: utm_* (any), fbclid, gclid, si (case-insensitive names).
inline bool trackingKey(const std::string& key)
{
    std::string k;
    for (char c : key) k += lower(c);
    return k.compare(0, 4, "utm_") == 0 || k == "fbclid" || k == "gclid" || k == "si";
}
// The page address without tracking parameters; everything else (order, encoding, fragment) is kept as it was.
inline std::string cleanURL(const std::string& url)
{
    const size_t hash = url.find('#');
    const size_t q = url.find('?');
    if (q == std::string::npos || (hash != std::string::npos && q > hash)) return url;   // no query ("#a?b" is fragment)
    const std::string query = url.substr(q + 1, hash == std::string::npos ? std::string::npos : hash - q - 1);
    const std::string frag = hash == std::string::npos ? std::string() : url.substr(hash);
    std::string kept;
    size_t a = 0;
    while (a <= query.size()) {
        size_t b = query.find('&', a);
        if (b == std::string::npos) b = query.size();
        const std::string part = query.substr(a, b - a);
        if (!part.empty()) {
            const size_t eq = part.find('=');
            if (!trackingKey(part.substr(0, eq))) { if (!kept.empty()) kept += '&'; kept += part; }
        }
        a = b + 1;
    }
    return url.substr(0, q) + (kept.empty() ? std::string() : "?" + kept) + frag;
}
// Only web pages are shared (a phone can't open omni:// or about: pages).
inline bool shareable(const std::string& url)
{
    auto starts = [&](const char* p) { size_t i = 0; for (; p[i]; ++i) if (i >= url.size() || lower(url[i]) != p[i]) return false; return url.size() > i; };
    return starts("https://") || starts("http://");
}
// The address shown under the code: no scheme, no "www.", no trailing slash; long ones keep the start and the end
// ("example.com/a/very/long...end-of-path"), at most maxChars bytes, never cutting a UTF-8 sequence.
inline std::string shownURL(const std::string& url, size_t maxChars = 72)
{
    std::string u = url;
    for (const char* p : { "https://", "http://" }) {
        const std::string ps(p);
        if (u.size() >= ps.size()) { std::string head; for (size_t i = 0; i < ps.size(); ++i) head += lower(u[i]); if (head == ps) { u = u.substr(ps.size()); break; } }
    }
    if (u.size() >= 4 && lower(u[0]) == 'w' && lower(u[1]) == 'w' && lower(u[2]) == 'w' && u[3] == '.') u = u.substr(4);
    while (!u.empty() && u.back() == '/') u.pop_back();
    if (maxChars < 8 || u.size() <= maxChars) return u;
    const size_t keep = maxChars - 3, tailLen = keep / 3;
    size_t headEnd = keep - tailLen, tailStart = u.size() - tailLen;
    while (headEnd > 0 && (static_cast<unsigned char>(u[headEnd]) & 0xC0) == 0x80) --headEnd;
    while (tailStart < u.size() && (static_cast<unsigned char>(u[tailStart]) & 0xC0) == 0x80) ++tailStart;
    return u.substr(0, headEnd) + "..." + u.substr(tailStart);
}

// --- the panel's code square (physical pixels) --------------------------------------------------------------------
struct Square { int module = 0, side = 0; };               // module size and the whole white square (quiet zone included)
// The largest whole-pixel module that fits the code and its quiet zone into `fraction` of the screen height.
inline Square square(int codeSize, int screenH, double fraction = 0.6)
{
    Square q;
    const int modules = codeSize + 2 * kQuiet;
    if (codeSize <= 0 || screenH <= 0) return q;
    q.module = std::max(1, int(screenH * fraction) / modules);
    q.side = q.module * modules;
    return q;
}

} // namespace OmniQr
'''

SHELL = r'''// OMNI_QR_SHARE_V1: "Show QR code" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniSiteClearShell.h). The pure part (encoder, address cleaner, square size) is OmniQrShare.h.
// Hold Cross on a page > "Show QR code": a centred panel with the page address as a QR code (tracking parameters
// dropped), the address under it; Circle (or Options) closes. Private tabs too: nothing is stored anywhere, the code
// lives in this panel only. Main thread only.
#pragma once

namespace OQR = OmniQr;

constexpr int omniQrContextId = 975;               // hold-Cross page menu row (pinned tabs use 960)
struct OmniQrState {
    bool open = false;
    OQR::Code code;
    std::string shown;                             // the address under the code (shortened)
    bool trimmed = false;                          // tracking parameters were dropped
};
static OmniQrState omniQr;

static void omniQrClose() { omniQr = OmniQrState(); omniShellDirty = true; }
static void omniQrShow()
{
    Tab* t = active();
    if (!t) return;
    if (!OQR::shareable(t->url)) { notice("Only web pages can be shown as a QR code"); return; }
    const std::string url = OQR::cleanURL(t->url);
    OQR::Code code;
    if (!OQR::encode(url, code)) {
        notice("This address is too long for a QR code (" + std::to_string(url.size()) + " characters, at most " + std::to_string(OQR::maxBytes()) + ")");
        return;
    }
    omniFxCloseAll();
    omniQr.code = std::move(code);
    omniQr.shown = OQR::shownURL(url);
    omniQr.trimmed = url != t->url;
    omniQr.open = true;
    omniShellDirty = true;
}

// --- hold-Cross page menu ------------------------------------------------------------------------------------------
static void omniQrContextRow(OmniFxPanel& p)
{
    Tab* t = active();
    OmniFxRow r; r.id = omniQrContextId; r.label = "Show QR code"; r.enabled = t && OQR::shareable(t->url);
    p.rows.push_back(r);
}
static bool omniQrContextAction(int id)
{
    if (id != omniQrContextId) return false;
    omniQrShow();
    return true;
}

// --- the panel: title, the code on white (quiet zone included, whole-pixel modules, ~60% of the screen height),
// the address; drawn above the page and the other panels ------------------------------------------------------------
struct OmniQrGeom { int x, y, w, h, qr; };          // layout px; qr: the square's layout size
static OmniQrGeom omniQrGeometry(const OQR::Square& sq)
{
    OmniQrGeom g {};
    g.qr = int(sq.side / displayScale + 0.999);
    g.w = std::max(g.qr + 64, 620);
    g.h = 64 + g.qr + (omniQr.trimmed ? 88 : 64);
    g.x = (width - g.w) / 2;
    g.y = std::max(8, (height - bottom - g.h) / 2);
    return g;
}
static void omniQrDraw()
{
    if (!omniQr.open || omniQr.code.size <= 0) return;
    const OmniTheme& T = omniTheme();
    const OQR::Square sq = OQR::square(omniQr.code.size, canvas->h);
    const OmniQrGeom g = omniQrGeometry(sq);
    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, 150);
    omniShadow(g.x, g.y, g.w, g.h, omniRadius + 2, 22, 160, 6);
    fillRounded(g.x, g.y, g.w, g.h, omniRadius + 2, T.panel);
    omniLabel("Scan to open this page on your phone", g.x + g.w / 2.f, g.y + 34, omniBodyBold, T.ink, 1, g.w - 48);
    // the code: white whatever the theme, dark modules as horizontal runs (physical pixels, so modules stay crisp)
    const int px = physical(g.x + g.w / 2) - sq.side / 2, py = physical(g.y + 60);
    omniRectPx({ px, py, sq.side, sq.side }, { 255, 255, 255, 255 });
    const int m = sq.module, q0 = OQR::kQuiet * m, n = omniQr.code.size;
    for (int y = 0; y < n; ++y)
        for (int x = 0; x < n;) {
            if (!omniQr.code.at(x, y)) { ++x; continue; }
            int run = 1;
            while (x + run < n && omniQr.code.at(x + run, y)) ++run;
            omniRectPx({ px + q0 + x * m, py + q0 + y * m, run * m, m }, { 0, 0, 0, 255 });
            x += run;
        }
    const int below = g.y + 60 + g.qr;
    omniLabel(omniQr.shown, g.x + g.w / 2.f, below + 30, omniSmall, T.ink, 1, g.w - 48);
    if (omniQr.trimmed) omniLabel("Tracking parameters removed", g.x + g.w / 2.f, below + 56, omniSmall, T.inkFaint, 1, g.w - 48);
    omniPanelHints({ { 1, "Close" } }, nullptr);
}
static bool omniQrButton(int b)
{
    if (b == SDL_CONTROLLER_BUTTON_B || b == SDL_CONTROLLER_BUTTON_BACK || b == SDL_CONTROLLER_BUTTON_START) omniQrClose();
    return true;                                   // the panel takes every button while it is open
}
static bool omniQrClick(int x, int y)
{
    // a mouse click off the panel closes it (like the menus); Cross at the pointer does nothing (Circle closes)
    const OmniQrGeom g = omniQrGeometry(OQR::square(omniQr.code.size, canvas->h));
    if ((x < g.x || x >= g.x + g.w || y < g.y || y >= g.y + g.h) && !omniPtrCross.inCross) omniQrClose();
    return true;
}
[[maybe_unused]] static const bool omniQrLayers = [] {
    omniOverlayLayers().push_back({ [] { return omniQr.open; }, omniQrButton, omniQrClick, [](double) { return true; }, omniQrDraw, true });
    return true;
}();
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include <WebKit/WKDictionary.h> // OMNI_SITE_CLEAR_V1: the page script\'s (empty) argument list\n',
         '#include <WebKit/WKDictionary.h> // OMNI_SITE_CLEAR_V1: the page script\'s (empty) argument list\n'
         '#include "OmniQrShare.h" // OMNI_QR_SHARE_V1: Show QR code (pure encoder)\n'),
    ],
    'OmniContextMenu.h': [
        ('static bool omniPtContextAction(int id);\n',
         'static bool omniPtContextAction(int id);\n'
         'static void omniQrContextRow(OmniFxPanel& p); // OMNI_QR_SHARE_V1 (OmniQrShareShell.h)\n'
         'static bool omniQrContextAction(int id);\n'),
        ('        add(omniCxCopyPage, "Copy page address", web);\n',
         '        add(omniCxCopyPage, "Copy page address", web);\n'
         '        omniQrContextRow(p); // OMNI_QR_SHARE_V1: Show QR code\n'),
        ('    if (omniPtContextAction(r.id)) return true; // OMNI_PINNED_TABS_V1\n',
         '    if (omniPtContextAction(r.id)) return true; // OMNI_PINNED_TABS_V1\n'
         '    if (omniQrContextAction(r.id)) return true; // OMNI_QR_SHARE_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniQrShareShell.h" // OMNI_QR_SHARE_V1\n'),
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
    for need, who in (('OMNI_SITE_CLEAR_V1', 'apply_site_clear.py'), ('OMNI_PINNED_TABS_V1', 'apply_pinned_tabs.py')):
        if need not in (root / ('OmniFeatures3.h' if need == 'OMNI_SITE_CLEAR_V1' else 'OmniContextMenu.h')).read_bytes().decode('utf-8'):
            sys.exit('%s missing: %s first' % (need, who))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniQrShare.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniQrShareShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
