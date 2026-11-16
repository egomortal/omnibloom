#!/usr/bin/env python3
"""OMNI_SCREENSHOT_GALLERY_V1 (2026-11-16): Options > More > Screenshots, a gallery of the page screenshots.

What the user sees
  - Options > More has a new "Screenshots" row (tile id OmniShotGallery::kTile = 467; omniMqGroup's default puts it
    in More). Cross closes the menu and opens the gallery:
        "Screenshots"                                        "40 screenshots   Page 2 of 4"
        a 4 x 3 grid of thumbnails (newest first), each with the page's host and "16 Nov 2026, 14:03" under it
        (only the date when the file name has no host: "page-..." from about: / data: pages, or a foreign file name,
        whose date is then the file's modification time).
    D-pad moves (left / right cross page ends, down from the last row goes to the next page), L1 / R1 page,
    right stick scrolls rows, the pointer (Cross at the pointer / mouse) selects then opens a tile.
    Cross: the screenshot full screen (fitted, nearest-pixel enlargement; host, date and "3 / 40" on top);
           D-pad left / right or L1 / R1: previous / next; Circle: back to the grid.
    Square (grid or full screen) asks once (the shell's own modal, Cancel focused):
        "Delete this screenshot?"
        "news.org, 17 Nov 2026, 08:00. It moves to the Downloads trash, where the Downloads app can restore it or
         delete it for good."
      "Delete" moves the file to <Saved>/.trash/Screenshots/ (name, then "name (2).png" .. "(999)" as
      files_library.py's _free does), notice "Screenshot moved to the Downloads trash".
    Circle / Create closes the gallery; Options closes it too.
    Empty folder: "No screenshots yet" / "Press L2 + R3 while browsing to save the page as a picture." (LT + RS with
    Xbox labels).
  - Triangle does nothing. "Send to Downloads library" has no hook to call because there is nothing to send:
    OMNI_QUICK_ACTIONS_V1 already writes the screenshots into /data/omni/downloads/media-worker/Saved/Screenshots,
    and <downloads folder>/Saved is the Downloads Library's console save root (omnibloom/downloads/worker/
    files_library.py roots()), so every screenshot is listed in Downloads > Library already. Delete uses that
    Library's own trash layout instead (.trash mirrors the root), so Library > Trash can restore it.

Where the screenshots are (checked in the tree): OmniPageTools.h omniPtScreenshot (L2 + R3, Options > Screenshot,
the page menu) -> OmniQuickActions::kShotDir = /data/omni/downloads/media-worker/Saved/Screenshots, file
"<host>-<yyyymmdd>-<hhmmss>.png" or "...-<n>.png" (n 2..99, same second), host lower case without "www." / port,
[a-z0-9.-] only, "page" when there is none; RGB PNG written by OmniPng.cpp (libpng), the page area only, at most
1920 px wide (half resolution at 4K). No sidecar: the host and the local time come from the name.

Decoding: libpng is already linked (OmniPng.cpp writes with it; OmniBrowser.cpp / OmniControllerIcons.h read icons
with the simplified png_image API, <png.h> already included). No stb_image in the tree, WebKit's image decoders are
not reachable from the shell; nothing is added. One worker thread (started on first open, then idle on a condition
variable) decodes with png_image_begin_read_from_file + png_image_finish_read(PNG_FORMAT_RGB, white background) and
box-filters straight into canvas pixels (the canvas's own R/G/B shifts, OmniPix), so the main thread only memcpy's.
  thumbnails: fitted into physical(240 x 135) (720 x 405 at 4K = 1.17 MB, 0.29 MB at 1080p); only the current page
    is asked for (queued jobs of a page left behind are dropped). Kept by OmniShotGallery::Budget, 24 MB cap, least
    recently drawn first, the current page never dropped (12 thumbnails fit at any scale up to 4K).
  full view: the 24-byte PNG header is read first (pngSize): over 8192 px a side / 16 Mpx, not a PNG, or
    omniTmQueryMiB() < 64 + viewMiB (RGB + canvas copy) -> "Couldn't open this screenshot" / a memory notice; then
    decoded at its own size (never larger than the canvas) and enlarged with nearest pixels when drawn. One at a time.
  Everything (thumbnails, full view, listing) is freed when the gallery closes; results that come back for a closed
  gallery or an earlier opening (generation omniSsGen) are freed in omniSsTick.
Drawing: the gallery is its own overlay layer (omniOverlayLayers, registered by a static initializer like
OmniFeatures.h's), shown while omniSsOpenFlag and no features panel is on top; the menu is closed when it opens.
Drawn with the panel helpers (omniShadow, fillRounded, omniLabel, omniPanelHints) in the panel colours.

Pure part: engine/entry/OmniShotGallery.h (no SDL / WebKit / libpng): file-name parse, newest-first listing, the
4 x 3 pager, fit, box downscale, PNG header size, cache budget, trash path, texts.
Tested by tools/test_screenshot_gallery.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_screenshot_gallery.cpp -o t && ./t
Shell side: engine/entry/OmniShotGalleryShell.h (included from OmniFeatures3.h after OmniSiteClearShell.h).

Anchors (exactly once each; MARK makes each file idempotent; every insert goes BEFORE or AFTER a whole line that the
other features of this batch don't replace):
  OmniBrowser.cpp     the OmniQuickActions.h include line: + the pure include after it.
  OmniQuickMenu.h     "static void omniFxQuickAllBuild(OmniFxPanel& p)": omniSsQuickAction declaration before it;
                      the omniQmApps row (s2 OMNI_HUB_CARDS_V1): the Screenshots row before it;
                      "    Tab* t = active();\\n    switch (r.id) {   // stay open": omniSsQuickAction call before it.
  OmniFeatures3.h     the OmniSiteClearShell.h include line: + the shell include after it;
                      the omniPtTick(); line of omniF3Tick: + omniSsTick(); after it.
Apply AFTER apply_quick_actions.py and apply_site_clear.py (their lines are anchors).
r2 (OMNI_SCREENSHOT_GALLERY_V1_R2, shell header only): the worker's mutex / condition variable / queues are never
destroyed (heap). A tree with r1 is upgraded in place: write_new rewrites OmniShotGalleryShell.h when its bytes differ.
usage: apply_screenshot_gallery.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_SCREENSHOT_GALLERY_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_SCREENSHOT_GALLERY_V1: the pure part of Options > More > Screenshots (no SDL, no WebKit, no libpng): the
// screenshot file names (OmniQuickActions::fileName), the newest-first listing, paging (4 x 3 per page), the fit and
// box-downscale of decoded pixels, the PNG header size check, the thumbnail cache budget, the Downloads-trash name
// and the texts. The shell side is OmniShotGalleryShell.h; the reasons are in tools/apply_screenshot_gallery.py.
// Tested on the host with g++ (test_screenshot_gallery.cpp).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace OmniShotGallery {

constexpr int kTile = 467;                       // Options tile id (More group; reading list 420/421, tab audio 440)
constexpr int kCols = 4, kRows = 3, kPerPage = kCols * kRows;
constexpr int kThumbW = 240, kThumbH = 135;      // layout px of a thumbnail box (physical() in the shell)
constexpr size_t kCacheBytes = size_t(24) << 20; // decoded thumbnails kept at most (canvas pixels, 4 bytes each)
constexpr size_t kMaxScan = 20000;               // directory entries looked at per listing
constexpr size_t kMaxList = 5000;                // newest screenshots shown
constexpr uint32_t kMaxSide = 8192;              // larger PNGs are not decoded
constexpr uint64_t kMaxPixels = uint64_t(16) << 20;   // 16 Mpx: 48 MB of RGB while decoding at most
constexpr int kTrashMax = 999;                   // "name (999).png" (files_library.py _free)

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline bool digits(const std::string& s, size_t at, size_t n)
{
    if (at + n > s.size()) return false;
    for (size_t i = at; i < at + n; ++i) if (s[i] < '0' || s[i] > '9') return false;
    return true;
}
inline int num(const std::string& s, size_t at, size_t n)
{
    int v = 0;
    for (size_t i = at; i < at + n; ++i) v = v * 10 + (s[i] - '0');
    return v;
}
inline bool hasPngExt(const std::string& name)
{
    if (name.size() < 5) return false;
    const size_t e = name.size() - 4;
    return name[e] == '.' && lower(name[e + 1]) == 'p' && lower(name[e + 2]) == 'n' && lower(name[e + 3]) == 'g';
}
// A file the gallery lists: "*.png" (any case), not hidden, no path separator.
inline bool listable(const std::string& name)
{
    return hasPngExt(name) && name[0] != '.' && name.find('/') == std::string::npos;
}

// "yyyymmddhhmmss" (14 digits) with a real calendar date and clock time.
inline bool validStamp(const std::string& s)
{
    if (s.size() != 14 || !digits(s, 0, 14)) return false;
    const int mo = num(s, 4, 2), d = num(s, 6, 2), h = num(s, 8, 2), mi = num(s, 10, 2), se = num(s, 12, 2);
    return num(s, 0, 4) >= 1970 && mo >= 1 && mo <= 12 && d >= 1 && d <= 31 && h <= 23 && mi <= 59 && se <= 60;
}
// Broken-down local time (struct tm fields as numbers: year 2026, month 1..12) -> "yyyymmddhhmmss"; "" when invalid.
inline std::string stampOf(int year, int month, int day, int hour, int minute, int second)
{
    if (year < 0 || year > 9999 || month < 0 || month > 99 || day < 0 || day > 99 || hour < 0 || hour > 99 || minute < 0
        || minute > 99 || second < 0 || second > 99) return std::string();
    char b[16];
    const int v[6] = { year, month, day, hour, minute, second };
    int at = 0;
    for (int i = 0; i < 6; ++i) {
        const int w = i == 0 ? 4 : 2;
        for (int k = w - 1, x = v[i]; k >= 0; --k, x /= 10) b[at + k] = char('0' + x % 10);
        at += w;
    }
    const std::string s(b, 14);
    return validStamp(s) ? s : std::string();
}

// --- file names: "<host>-<yyyymmdd>-<hhmmss>.png" or "...-<n>.png" (n 2..99) -------------------------------------
struct Name {
    bool ok = false;
    std::string host;    // as written ("page" when the page had none: about:, data:, file:)
    std::string stamp;   // yyyymmddhhmmss (local time when it was saved)
    int n = 1;           // the -n of a second screenshot in the same second
};
inline bool endsWithStamp(const std::string& s)
{
    return s.size() >= 16 && s[s.size() - 16] == '-' && digits(s, s.size() - 15, 8) && s[s.size() - 7] == '-' && digits(s, s.size() - 6, 6);
}
inline Name parseName(const std::string& file)
{
    Name r;
    if (!hasPngExt(file)) return r;
    std::string base = file.substr(0, file.size() - 4);
    int n = 1;
    const size_t dash = base.rfind('-');
    if (dash != std::string::npos && base.size() - dash - 1 >= 1 && base.size() - dash - 1 <= 2 && digits(base, dash + 1, base.size() - dash - 1)
        && endsWithStamp(base.substr(0, dash))) {
        n = num(base, dash + 1, base.size() - dash - 1);
        if (n < 2) return r;
        base.resize(dash);
    }
    if (!endsWithStamp(base)) return r;
    const std::string host = base.substr(0, base.size() - 16);
    if (host.empty() || host.size() > 64) return r;
    for (char c : host) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-')) return r;
    const std::string stamp = base.substr(base.size() - 15, 8) + base.substr(base.size() - 6, 6);
    if (!validStamp(stamp)) return r;
    r.ok = true; r.host = host; r.stamp = stamp; r.n = n;
    return r;
}

// "16 Nov 2026, 14:03" from yyyymmddhhmmss; "" when invalid.
inline std::string formatWhen(const std::string& stamp)
{
    if (!validStamp(stamp)) return std::string();
    static const char* const months[] = { "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec" };
    return std::to_string(num(stamp, 6, 2)) + " " + months[num(stamp, 4, 2) - 1] + " " + stamp.substr(0, 4) + ", " + stamp.substr(8, 2) + ":"
        + stamp.substr(10, 2);
}

// --- the listing -------------------------------------------------------------------------------------------------
struct File {
    std::string name;
    uint64_t size = 0;
    std::string mtimeStamp;   // the file's modification time as local yyyymmddhhmmss (stampOf), "" when unknown
};
struct Shot {
    std::string name;    // file name in the screenshot folder
    std::string host;    // the page's host from the name ("" when the name has none or says "page")
    std::string stamp;   // from the name, else the modification time
    std::string when;    // formatWhen(stamp)
    int n = 1;
};
// Newest first: by the time in the name (else the file's own time), then -n, then the name. Empty files, hidden files
// and other types are left out; at most kMaxList.
inline std::vector<Shot> list(const std::vector<File>& files)
{
    std::vector<Shot> out;
    for (const File& f : files) {
        if (!listable(f.name) || f.size == 0) continue;
        Shot s;
        s.name = f.name;
        const Name n = parseName(f.name);
        if (n.ok) { s.host = n.host == "page" ? std::string() : n.host; s.stamp = n.stamp; s.n = n.n; }
        else s.stamp = validStamp(f.mtimeStamp) ? f.mtimeStamp : std::string();
        s.when = formatWhen(s.stamp);
        out.push_back(std::move(s));
    }
    std::sort(out.begin(), out.end(), [](const Shot& a, const Shot& b) {
        if (a.stamp != b.stamp) return a.stamp > b.stamp;
        if (a.n != b.n) return a.n > b.n;
        return a.name > b.name;
    });
    if (out.size() > kMaxList) out.resize(kMaxList);
    return out;
}
inline int indexOf(const std::vector<Shot>& shots, const std::string& name)
{
    for (size_t i = 0; i < shots.size(); ++i) if (shots[i].name == name) return int(i);
    return -1;
}

// --- paging: 4 x 3 per page, newest first -------------------------------------------------------------------------
struct Pager {
    int count = 0, sel = 0;
    int page() const { return count > 0 ? sel / kPerPage : 0; }
    int pages() const { return count > 0 ? (count + kPerPage - 1) / kPerPage : 1; }
    int first() const { return page() * kPerPage; }
    int onPage() const { return count > 0 ? std::min(kPerPage, count - first()) : 0; }
    void clamp() { sel = count > 0 ? std::clamp(sel, 0, count - 1) : 0; }
    // D-pad: left / right one shot (across pages), up / down one grid row; down onto a shorter last row lands on the
    // last shot. True when the selection moved.
    bool move(int dx, int dy)
    {
        const int was = sel;
        if (count <= 0) return false;
        if (dx > 0 && sel + 1 < count) ++sel;
        else if (dx < 0 && sel > 0) --sel;
        else if (dy > 0) {
            if (sel + kCols < count) sel += kCols;
            else if ((count - 1) / kCols > sel / kCols) sel = count - 1;
        } else if (dy < 0 && sel >= kCols) sel -= kCols;
        return sel != was;
    }
    // L1 / R1: the same place on the previous / next page (the last shot when the next page is shorter).
    bool pageBy(int d)
    {
        const int p = std::clamp(page() + d, 0, pages() - 1);
        if (p == page() || count <= 0) return false;
        sel = std::min(count - 1, sel + (p - page()) * kPerPage);
        return true;
    }
    bool onCurrentPage(int index) const { return index >= first() && index < first() + onPage(); }
};

// --- pixels ------------------------------------------------------------------------------------------------------
struct Size { int w = 0, h = 0; };
// The largest size with the source's aspect inside the box (at least 1 x 1); upscale false: never larger than the source.
inline Size fit(int sw, int sh, int bw, int bh, bool upscale = true)
{
    Size s;
    if (sw <= 0 || sh <= 0 || bw <= 0 || bh <= 0) return s;
    if (!upscale && sw <= bw && sh <= bh) { s.w = sw; s.h = sh; return s; }
    if (uint64_t(sw) * bh >= uint64_t(sh) * bw) { s.w = bw; s.h = int(uint64_t(sh) * bw / sw); }
    else { s.h = bh; s.w = int(uint64_t(sw) * bh / sh); }
    s.w = std::max(1, s.w); s.h = std::max(1, s.h);
    return s;
}
// The canvas's channel positions (SDL_PixelFormat R/G/B shift, A mask), so the worker writes canvas pixels directly.
struct Pack { int rs = 0, gs = 8, bs = 16; uint32_t amask = 0xff000000u; };
inline uint32_t pack(const Pack& p, uint32_t r, uint32_t g, uint32_t b) { return (r << p.rs) | (g << p.gs) | (b << p.bs) | p.amask; }
// RGB (3 bytes per pixel, `stride` bytes per row) -> dw x dh packed pixels. Each target pixel is the average of the
// source pixels it covers (box filter; at least one), so a 1920 px page comes out smooth at 240 px.
inline void scale(const uint8_t* rgb, int sw, int sh, size_t stride, uint32_t* out, int dw, int dh, const Pack& p)
{
    if (!rgb || !out || sw <= 0 || sh <= 0 || dw <= 0 || dh <= 0) return;
    std::vector<int> x0(size_t(dw) + 1);
    for (int x = 0; x <= dw; ++x) x0[size_t(x)] = int(uint64_t(x) * sw / dw);
    for (int y = 0; y < dh; ++y) {
        const int ya = int(uint64_t(y) * sh / dh), yb = std::max(ya + 1, int(uint64_t(y + 1) * sh / dh));
        uint32_t* row = out + size_t(y) * dw;
        for (int x = 0; x < dw; ++x) {
            const int xa = x0[size_t(x)], xb = std::max(xa + 1, x0[size_t(x) + 1]);
            uint64_t r = 0, g = 0, b = 0;
            for (int yy = ya; yy < yb; ++yy) {
                const uint8_t* s = rgb + size_t(yy) * stride + size_t(xa) * 3;
                for (int xx = xa; xx < xb; ++xx, s += 3) { r += s[0]; g += s[1]; b += s[2]; }
            }
            const uint64_t n = uint64_t(yb - ya) * uint64_t(xb - xa), h = n / 2;
            row[x] = pack(p, uint32_t((r + h) / n), uint32_t((g + h) / n), uint32_t((b + h) / n));
        }
    }
}
// Width / height from the first 24 bytes of a PNG (signature + IHDR). False when it is not a PNG.
inline bool pngSize(const uint8_t* b, size_t n, uint32_t& w, uint32_t& h)
{
    static const uint8_t sig[8] = { 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n' };
    if (!b || n < 24) return false;
    for (int i = 0; i < 8; ++i) if (b[i] != sig[i]) return false;
    if (b[12] != 'I' || b[13] != 'H' || b[14] != 'D' || b[15] != 'R') return false;
    w = (uint32_t(b[16]) << 24) | (uint32_t(b[17]) << 16) | (uint32_t(b[18]) << 8) | b[19];
    h = (uint32_t(b[20]) << 24) | (uint32_t(b[21]) << 16) | (uint32_t(b[22]) << 8) | b[23];
    return true;
}
inline bool decodeSizeOk(uint32_t w, uint32_t h)
{
    return w > 0 && h > 0 && w <= kMaxSide && h <= kMaxSide && uint64_t(w) * h <= kMaxPixels;
}
// MiB a full-size view of a w x h PNG needs while it decodes (RGB buffer + canvas pixels), rounded up.
inline long long viewMiB(uint32_t w, uint32_t h) { return (long long)((uint64_t(w) * h * 7 + (1u << 20) - 1) >> 20); }

// --- thumbnail cache budget (least recently used first; the current page is kept) -----------------------------------
class Budget {
public:
    explicit Budget(size_t cap = kCacheBytes) : cap_(cap) {}
    size_t total() const { return total_; }
    size_t size() const { return map_.size(); }
    bool has(const std::string& key) const { return map_.count(key) != 0; }
    void touch(const std::string& key) { auto it = map_.find(key); if (it != map_.end()) it->second.use = ++tick_; }
    void remove(const std::string& key)
    {
        auto it = map_.find(key);
        if (it == map_.end()) return;
        total_ -= it->second.bytes;
        map_.erase(it);
    }
    void clear() { map_.clear(); total_ = 0; }
    // Adds `key` (replacing an older entry of the same key), first dropping the least recently used entries that
    // keep(key) does not protect. False (nothing added) when it cannot fit; `evicted` lists what was dropped.
    template <class Keep>
    bool admit(const std::string& key, size_t bytes, Keep keep, std::vector<std::string>& evicted)
    {
        remove(key);
        if (bytes > cap_) return false;
        while (total_ + bytes > cap_) {
            auto victim = map_.end();
            for (auto it = map_.begin(); it != map_.end(); ++it)
                if (!keep(it->first) && (victim == map_.end() || it->second.use < victim->second.use)) victim = it;
            if (victim == map_.end()) return false;
            evicted.push_back(victim->first);
            total_ -= victim->second.bytes;
            map_.erase(victim);
        }
        map_[key] = Entry { bytes, ++tick_ };
        total_ += bytes;
        return true;
    }
private:
    struct Entry { size_t bytes; uint64_t use; };
    std::unordered_map<std::string, Entry> map_;
    uint64_t tick_ = 0;
    size_t total_ = 0, cap_;
};

// --- Delete: into the Downloads app's trash ------------------------------------------------------------------------
// The screenshot folder is <Saved>/Screenshots, one of the Downloads Library's save roots. Its trash mirrors the root:
// <Saved>/.trash/Screenshots (files_library.py), so Downloads > Library > Trash lists, restores or deletes it.
inline std::string trashDir(const std::string& shotDir)
{
    std::string d = shotDir;
    while (d.size() > 1 && d.back() == '/') d.pop_back();
    const size_t slash = d.rfind('/');
    if (slash == std::string::npos || slash + 1 >= d.size()) return std::string();
    return d.substr(0, slash) + "/.trash/" + d.substr(slash + 1);
}
// dir/name, then dir/"stem (2).png" .. "(999)" (files_library.py _free: os.path.splitext); "" when all are taken.
template <class Exists>
inline std::string trashPath(const std::string& dir, const std::string& name, Exists exists)
{
    size_t dot = name.rfind('.');
    if (dot == std::string::npos || dot == 0) dot = name.size();
    const std::string stem = name.substr(0, dot), ext = name.substr(dot);
    for (int n = 1; n <= kTrashMax; ++n) {
        const std::string p = dir + "/" + (n == 1 ? name : stem + " (" + std::to_string(n) + ")" + ext);
        if (!exists(p)) return p;
    }
    return std::string();
}

// --- texts ---------------------------------------------------------------------------------------------------------
inline std::string countText(int n) { return n == 1 ? std::string("1 screenshot") : std::to_string(n) + " screenshots"; }
inline std::string corner(const Pager& p)
{
    if (p.count <= 0) return std::string();
    std::string s = countText(p.count);
    if (p.pages() > 1) s += "   Page " + std::to_string(p.page() + 1) + " of " + std::to_string(p.pages());
    return s;
}
// Tile caption: line 1 the host (or the date when there is no host), line 2 the date (or nothing).
inline std::string line1(const Shot& s) { return !s.host.empty() ? s.host : !s.when.empty() ? s.when : s.name; }
inline std::string line2(const Shot& s) { return !s.host.empty() ? s.when : std::string(); }
inline std::string viewerCaption(const Shot& s, int index, int count)
{
    std::string t;
    if (!s.host.empty()) t = s.host;
    if (!s.when.empty()) t += (t.empty() ? "" : "   ") + s.when;
    if (t.empty()) t = s.name;
    return t + "   " + std::to_string(index + 1) + " / " + std::to_string(count);
}
inline std::string askTitle() { return "Delete this screenshot?"; }
inline std::string askBody(const Shot& s)
{
    std::string what = s.host.empty() ? s.when : s.when.empty() ? s.host : s.host + ", " + s.when;
    if (what.empty()) what = s.name;
    return what + ". It moves to the Downloads trash, where the Downloads app can restore it or delete it for good.";
}
inline std::string emptyTitle() { return "No screenshots yet"; }
inline std::string emptyBody(bool playStation)
{
    return std::string("Press ") + (playStation ? "L2 + R3" : "LT + RS") + " while browsing to save the page as a picture.";
}

} // namespace OmniShotGallery
'''

SHELL = r'''// OMNI_SCREENSHOT_GALLERY_V1: Options > More > Screenshots (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniSiteClearShell.h). The pure part is OmniShotGallery.h; the reasons
// are in tools/apply_screenshot_gallery.py.
// A grid of the page screenshots (L2 + R3) in Downloads > Saved > Screenshots, newest first, 12 per page; Cross shows
// one full screen, Square moves it to the Downloads trash (asks first). PNGs are decoded by one worker thread with the
// libpng Omni already links (png_image), straight into canvas pixels: thumbnails fitted to their box (kept up to
// OSG::kCacheBytes, least recently used first, the current page never dropped), the full view at its own size (at most
// the canvas) and scaled when drawn. Everything is freed when the gallery closes. Main thread except omniSsWorker.
#pragma once

namespace OSG = OmniShotGallery;

struct OmniSsPixels {   // canvas pixels (malloc: the engine builds without exceptions, a failed allocation is a "no")
    uint32_t* px = nullptr;
    int w = 0, h = 0;
    OmniSsPixels() = default;
    OmniSsPixels(const OmniSsPixels&) = delete;
    OmniSsPixels& operator=(const OmniSsPixels&) = delete;
    OmniSsPixels(OmniSsPixels&& o) noexcept : px(o.px), w(o.w), h(o.h) { o.px = nullptr; o.w = o.h = 0; }
    OmniSsPixels& operator=(OmniSsPixels&& o) noexcept
    {
        if (this != &o) { free(px); px = o.px; w = o.w; h = o.h; o.px = nullptr; o.w = o.h = 0; }
        return *this;
    }
    ~OmniSsPixels() { free(px); }
    size_t bytes() const { return size_t(w) * size_t(h) * 4; }
};
struct OmniSsJob { std::string name; int boxW = 0, boxH = 0; bool full = false; uint32_t gen = 0; OSG::Pack pack; };
struct OmniSsResult { std::string name; bool full = false, ok = false; uint32_t gen = 0; OmniSsPixels img; };

// OMNI_SCREENSHOT_GALLERY_V1_R2: never destroyed (heap, as OmniBrowser.cpp's omniIoLock / omniIoJobs). The detached
// worker sleeps on omniSsCv, or is mid-decode, for the life of the process; as statics they were destroyed at exit under
// it (undefined behaviour, and a decode finishing then pushed into a dead deque). Not a quit flag + join: a join at
// shutdown would hold the exit for up to one 16 Mpx decode, and the process ends with _exit / LoadExec anyway.
static std::mutex& omniSsMu = *new std::mutex;
static std::condition_variable& omniSsCv = *new std::condition_variable;
static std::deque<OmniSsJob>& omniSsJobs = *new std::deque<OmniSsJob>;          // guarded by omniSsMu
static std::deque<OmniSsResult>& omniSsResults = *new std::deque<OmniSsResult>;    // guarded by omniSsMu
static bool omniSsWorkerUp = false;

static bool omniSsOpenFlag = false;
static uint32_t omniSsGen = 0;                     // bumped on open / close: older results are dropped
static std::vector<OSG::Shot> omniSsShots;
static OSG::Pager omniSsPager;
static std::unordered_map<std::string, OmniSsPixels> omniSsThumbs;
static OSG::Budget omniSsBudget;
static std::unordered_set<std::string> omniSsPending, omniSsFailed;   // thumbnails asked for / that would not decode
static int omniSsLastPage = -1;
static int omniSsView = -1;                        // the shot shown full screen, -1: the grid
static std::string omniSsViewName;
static OmniSsPixels omniSsFull;
static int omniSsFullState = 0;                    // 0 opening, 1 shown, 2 couldn't
static float omniSsScrollAcc = 0;

static std::string omniSsPath(const std::string& name) { return std::string(OmniQuickActions::kShotDir) + "/" + name; }

// --- the decode worker -------------------------------------------------------------------------------------------------
static bool omniSsDecode(const OmniSsJob& j, OmniSsPixels& out)
{
    png_image img {};
    img.version = PNG_IMAGE_VERSION;
    if (!png_image_begin_read_from_file(&img, omniSsPath(j.name).c_str())) { png_image_free(&img); return false; }
    const uint32_t w = img.width, h = img.height;
    if (!OSG::decodeSizeOk(w, h)) { png_image_free(&img); return false; }
    img.format = PNG_FORMAT_RGB;
    const size_t stride = size_t(w) * 3;
    uint8_t* rgb = static_cast<uint8_t*>(malloc(stride * h));
    if (!rgb) { png_image_free(&img); return false; }
    const png_color white { 255, 255, 255 };   // a PNG with transparency is shown over white, like the page was
    const bool ok = png_image_finish_read(&img, &white, rgb, png_int_32(stride), nullptr) != 0;
    png_image_free(&img);
    const OSG::Size s = OSG::fit(int(w), int(h), j.boxW, j.boxH, !j.full);
    if (ok && s.w > 0 && s.h > 0) out.px = static_cast<uint32_t*>(malloc(size_t(s.w) * size_t(s.h) * 4));
    if (out.px) { out.w = s.w; out.h = s.h; OSG::scale(rgb, int(w), int(h), stride, out.px, s.w, s.h, j.pack); }
    free(rgb);
    return out.px != nullptr;
}
static void omniSsWorker()
{
    for (;;) {
        OmniSsJob j;
        {
            std::unique_lock<std::mutex> lock(omniSsMu);
            omniSsCv.wait(lock, [] { return !omniSsJobs.empty(); });
            j = std::move(omniSsJobs.front());
            omniSsJobs.pop_front();
        }
        OmniSsResult r;
        r.name = j.name; r.full = j.full; r.gen = j.gen;
        r.ok = omniSsDecode(j, r.img);
        if (!r.ok) { fprintf(stderr, "OMNI SCREENSHOTS: couldn't decode %s\n", j.name.c_str()); fflush(stderr); }
        std::lock_guard<std::mutex> lock(omniSsMu);
        omniSsResults.push_back(std::move(r));
    }
}
static OSG::Pack omniSsPack()
{
    const OmniPix f = omniPix();
    OSG::Pack p;
    p.rs = f.rs; p.gs = f.gs; p.bs = f.bs; p.amask = f.amask;
    return p;
}

// --- listing and requests --------------------------------------------------------------------------------------------
static void omniSsScan()
{
    std::vector<OSG::File> files;
    if (DIR* d = opendir(OmniQuickActions::kShotDir)) {
        while (dirent* e = readdir(d)) {
            if (files.size() >= OSG::kMaxScan) break;
            const std::string name = e->d_name;
            if (!OSG::listable(name)) continue;
            struct stat st {};
            if (lstat(omniSsPath(name).c_str(), &st) != 0 || !S_ISREG(st.st_mode)) continue;   // no links, no folders
            const time_t mt = st.st_mtime;
            struct tm tmv {};
            localtime_r(&mt, &tmv);
            files.push_back({ name, uint64_t(st.st_size),
                OSG::stampOf(tmv.tm_year + 1900, tmv.tm_mon + 1, tmv.tm_mday, tmv.tm_hour, tmv.tm_min, tmv.tm_sec) });
        }
        closedir(d);
    }
    omniSsShots = OSG::list(files);
    omniSsPager.count = int(omniSsShots.size());
    omniSsPager.clamp();
}
static void omniSsRequestPage()
{
    const int page = omniSsPager.page();
    const OSG::Pack pack = omniSsPack();
    const int bw = physical(OSG::kThumbW), bh = physical(OSG::kThumbH);
    bool added = false;
    std::lock_guard<std::mutex> lock(omniSsMu);
    if (page != omniSsLastPage) {   // queued thumbnails of the page left behind are dropped (one being decoded comes back)
        for (auto it = omniSsJobs.begin(); it != omniSsJobs.end();) {
            if (!it->full) { omniSsPending.erase(it->name); it = omniSsJobs.erase(it); }
            else ++it;
        }
        omniSsLastPage = page;
    }
    for (int i = omniSsPager.first(); i < omniSsPager.first() + omniSsPager.onPage(); ++i) {
        const std::string& n = omniSsShots[size_t(i)].name;
        if (omniSsThumbs.count(n) || omniSsPending.count(n) || omniSsFailed.count(n)) continue;
        omniSsPending.insert(n);
        omniSsJobs.push_back({ n, bw, bh, false, omniSsGen, pack });
        added = true;
    }
    if (added) omniSsCv.notify_one();
}
static void omniSsDropFullJobs()
{
    std::lock_guard<std::mutex> lock(omniSsMu);
    for (auto it = omniSsJobs.begin(); it != omniSsJobs.end();) it = it->full ? omniSsJobs.erase(it) : std::next(it);
}
// Full screen: the header says how big it is first, so a huge or broken file (or too little memory) is refused before
// anything is decoded.
static void omniSsShow(int index)
{
    if (index < 0 || index >= int(omniSsShots.size())) return;
    omniSsView = index;
    omniSsPager.sel = index;
    omniSsViewName = omniSsShots[size_t(index)].name;
    omniSsFull = OmniSsPixels();
    omniSsFullState = 0;
    omniShellDirty = true;
    omniSsDropFullJobs();
    uint8_t head[24] = {};
    size_t got = 0;
    if (FILE* f = fopen(omniSsPath(omniSsViewName).c_str(), "rb")) { got = fread(head, 1, sizeof head, f); fclose(f); }
    uint32_t w = 0, h = 0;
    if (!OSG::pngSize(head, got, w, h) || !OSG::decodeSizeOk(w, h)) { omniSsFullState = 2; return; }
    const long long freeMiB = omniTmQueryMiB();
    if (freeMiB >= 0 && freeMiB < 64 + OSG::viewMiB(w, h)) {
        omniSsFullState = 2;
        notice("Not enough memory to open this screenshot right now");
        return;
    }
    std::lock_guard<std::mutex> lock(omniSsMu);
    omniSsJobs.push_front({ omniSsViewName, canvas->w, physical(height - bottom), true, omniSsGen, omniSsPack() });
    omniSsCv.notify_one();
}
static void omniSsCloseView()
{
    omniSsView = -1;
    omniSsFull = OmniSsPixels();
    omniSsFullState = 0;
    omniSsDropFullJobs();
    omniShellDirty = true;
}

// --- per pass (from omniF3Tick) ------------------------------------------------------------------------------------------
static void omniSsTick()
{
    std::deque<OmniSsResult> done;
    {
        std::lock_guard<std::mutex> lock(omniSsMu);
        if (omniSsResults.empty() && !omniSsOpenFlag) return;
        done.swap(omniSsResults);
    }
    if (!omniSsOpenFlag) return;   // results of a closed gallery are freed here
    std::unordered_set<std::string> keep;
    for (int i = omniSsPager.first(); i < omniSsPager.first() + omniSsPager.onPage(); ++i) keep.insert(omniSsShots[size_t(i)].name);
    for (OmniSsResult& r : done) {
        if (r.gen != omniSsGen) continue;
        if (r.full) {
            if (omniSsView >= 0 && r.name == omniSsViewName) { omniSsFull = std::move(r.img); omniSsFullState = r.ok ? 1 : 2; omniShellDirty = true; }
            continue;
        }
        omniSsPending.erase(r.name);
        if (!r.ok) { omniSsFailed.insert(r.name); omniShellDirty = true; continue; }
        if (!keep.count(r.name)) continue;   // the page changed meanwhile
        std::vector<std::string> evicted;
        if (!omniSsBudget.admit(r.name, r.img.bytes(), [&](const std::string& k) { return keep.count(k) != 0; }, evicted)) {
            omniSsFailed.insert(r.name);   // no room even after dropping every other page (never with 12 x 240 x 135)
            continue;
        }
        for (const std::string& e : evicted) omniSsThumbs.erase(e);
        omniSsThumbs[r.name] = std::move(r.img);
        omniShellDirty = true;
    }
    omniSsRequestPage();
}

// --- open / close / delete ------------------------------------------------------------------------------------------------
static void omniSsOpen()
{
    omniFxCloseAll();
    ++omniSsGen;
    omniSsOpenFlag = true;
    omniSsView = -1;
    omniSsPager = OSG::Pager();
    omniSsLastPage = -1;
    omniSsScrollAcc = 0;
    omniSsScan();
    if (!omniSsWorkerUp) { omniSsWorkerUp = true; std::thread(omniSsWorker).detach(); }
    omniSsRequestPage();
    fprintf(stderr, "OMNI SCREENSHOTS: gallery opened, %d in %s\n", omniSsPager.count, OmniQuickActions::kShotDir); fflush(stderr);
    omniShellDirty = true;
}
static void omniSsClose()
{
    omniSsOpenFlag = false;
    ++omniSsGen;
    {
        std::lock_guard<std::mutex> lock(omniSsMu);
        omniSsJobs.clear();
    }
    omniSsView = -1;
    omniSsFull = OmniSsPixels();
    omniSsThumbs.clear();
    omniSsBudget.clear();
    omniSsPending.clear();
    omniSsFailed.clear();
    std::vector<OSG::Shot>().swap(omniSsShots);
    omniSsPager = OSG::Pager();
    omniShellDirty = true;
}
// Into the Downloads app's trash (<Saved>/.trash/Screenshots), where Downloads > Library can restore or delete it.
static void omniSsDelete(const std::string& name)
{
    const std::string tdir = OSG::trashDir(OmniQuickActions::kShotDir);
    const std::string to = !tdir.empty() && OmniQuickActions::makeDirs(tdir)
        ? OSG::trashPath(tdir, name, [](const std::string& p) { struct stat st {}; return lstat(p.c_str(), &st) == 0; }) : std::string();
    if (to.empty() || rename(omniSsPath(name).c_str(), to.c_str()) != 0) {
        fprintf(stderr, "OMNI SCREENSHOTS: couldn't move %s to %s (errno %d)\n", name.c_str(), to.empty() ? tdir.c_str() : to.c_str(), errno);
        notice("Couldn't delete the screenshot");
        return;
    }
    fprintf(stderr, "OMNI SCREENSHOTS: %s -> %s\n", name.c_str(), to.c_str()); fflush(stderr);
    const int i = OSG::indexOf(omniSsShots, name);
    if (i >= 0) omniSsShots.erase(omniSsShots.begin() + i);
    omniSsBudget.remove(name);
    omniSsThumbs.erase(name);
    omniSsPending.erase(name);
    omniSsFailed.erase(name);
    omniSsPager.count = int(omniSsShots.size());
    if (i >= 0 && i < omniSsPager.sel) --omniSsPager.sel;
    omniSsPager.clamp();
    if (omniSsView >= 0) {
        if (omniSsShots.empty()) omniSsCloseView();
        else omniSsShow(std::min(omniSsView, int(omniSsShots.size()) - 1));
    }
    notice("Screenshot moved to the Downloads trash");
    omniShellDirty = true;
}
static void omniSsAskDelete(int index)
{
    if (index < 0 || index >= int(omniSsShots.size())) return;
    const OSG::Shot s = omniSsShots[size_t(index)];
    const uint32_t gen = omniSsGen;
    omniAsk(OSG::askTitle(), OSG::askBody(s), "Delete", [name = s.name, gen](bool ok) {
        if (ok && omniSsOpenFlag && gen == omniSsGen) omniSsDelete(name);
    });
}

// --- input ---------------------------------------------------------------------------------------------------------------
static bool omniSsButton(int b)
{
    if (b == SDL_CONTROLLER_BUTTON_START) { omniSsClose(); return true; }
    omniShellDirty = true;
    if (omniSsView >= 0) {   // full screen
        switch (b) {
        case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: omniSsCloseView(); break;
        case SDL_CONTROLLER_BUTTON_DPAD_LEFT: case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: if (omniSsView > 0) omniSsShow(omniSsView - 1); break;
        case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
            if (omniSsView + 1 < int(omniSsShots.size())) omniSsShow(omniSsView + 1);
            break;
        case SDL_CONTROLLER_BUTTON_X: omniSsAskDelete(omniSsView); break;   // Square
        default: break;
        }
        return true;
    }
    switch (b) {
    case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: omniSsClose(); break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniSsPager.move(-1, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniSsPager.move(1, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniSsPager.move(0, -1); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniSsPager.move(0, 1); break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: omniSsPager.pageBy(-1); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: omniSsPager.pageBy(1); break;
    case SDL_CONTROLLER_BUTTON_A: if (omniSsPager.count > 0) omniSsShow(omniSsPager.sel); break;   // Cross
    case SDL_CONTROLLER_BUTTON_X: if (omniSsPager.count > 0) omniSsAskDelete(omniSsPager.sel); break;   // Square
    default: break;   // Triangle: nothing (the screenshots are already in Downloads > Library, see the apply script)
    }
    if (omniSsOpenFlag) omniSsRequestPage();
    return true;
}

// --- drawing -------------------------------------------------------------------------------------------------------------
struct OmniSsGeom { int x, y, w, h, listY, tw, th, gap; };
static OmniSsGeom omniSsGeometry()
{
    OmniSsGeom g {};
    g.tw = OSG::kThumbW + 16; g.th = OSG::kThumbH + 56; g.gap = 10;
    g.w = 24 + OSG::kCols * g.tw + (OSG::kCols - 1) * g.gap;
    g.h = 64 + OSG::kRows * g.th + (OSG::kRows - 1) * g.gap + 12;
    g.x = (width - g.w) / 2;
    g.y = std::max(6, (height - bottom - g.h) / 2);
    g.listY = g.y + 64;
    return g;
}
static void omniSsTileXY(const OmniSsGeom& g, int k, int& tx, int& ty)
{
    tx = g.x + 12 + (k % OSG::kCols) * (g.tw + g.gap);
    ty = g.listY + (k / OSG::kCols) * (g.th + g.gap);
}
// Canvas pixels 1:1, centred in a physical box, clipped to the box and the canvas.
static void omniSsBlit(const OmniSsPixels& im, int bx, int by, int bw, int bh)
{
    if (!im.px) return;
    const int dx = bx + (bw - im.w) / 2, dy = by + (bh - im.h) / 2;
    const int x0 = std::max({ dx, bx, 0 }), x1 = std::min({ dx + im.w, bx + bw, canvas->w });
    const int y0 = std::max({ dy, by, 0 }), y1 = std::min({ dy + im.h, by + bh, canvas->h });
    if (x0 >= x1 || y0 >= y1) return;
    for (int y = y0; y < y1; ++y) memcpy(omniRow(y) + x0, im.px + size_t(y - dy) * im.w + (x0 - dx), size_t(x1 - x0) * 4);
}
// Fitted into a physical box (nearest pixel: the full view is never larger than the canvas, so this only enlarges).
static void omniSsBlitFit(const OmniSsPixels& im, int bx, int by, int bw, int bh)
{
    if (!im.px) return;
    const OSG::Size s = OSG::fit(im.w, im.h, bw, bh, true);
    if (s.w == im.w && s.h == im.h) { omniSsBlit(im, bx, by, bw, bh); return; }
    const int dx = bx + (bw - s.w) / 2, dy = by + (bh - s.h) / 2;
    const int x0 = std::max(dx, 0), x1 = std::min(dx + s.w, canvas->w), y0 = std::max(dy, 0), y1 = std::min(dy + s.h, canvas->h);
    if (x0 >= x1 || y0 >= y1) return;
    std::vector<int> xs(size_t(x1 - x0));
    for (int x = x0; x < x1; ++x) xs[size_t(x - x0)] = int(int64_t(x - dx) * im.w / s.w);
    for (int y = y0; y < y1; ++y) {
        const uint32_t* src = im.px + size_t(int64_t(y - dy) * im.h / s.h) * im.w;
        uint32_t* dst = omniRow(y) + x0;
        for (size_t k = 0; k < xs.size(); ++k) dst[k] = src[xs[k]];
    }
}
static void omniSsDrawViewer(const OmniTheme& T)
{
    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 });
    const int areaH = height - bottom;
    if (omniSsFullState == 1) omniSsBlitFit(omniSsFull, 0, 0, canvas->w, physical(areaH));
    else omniLabel(omniSsFullState == 2 ? "Couldn't open this screenshot" : "Opening...", width / 2.f, areaH / 2.f, omniBody, T.inkDim, 1);
    omniRectPx({ 0, 0, canvas->w, physical(40) }, { 0, 0, 0, 255 }, 150);
    if (omniSsView < int(omniSsShots.size()))
        omniLabel(OSG::viewerCaption(omniSsShots[size_t(omniSsView)], omniSsView, int(omniSsShots.size())), 20, 20, omniSmall, { 255, 255, 255, 255 }, 0, width - 40);
    omniPanelHints({ { omniHintDpadH, "Previous / next" }, { 2, "Delete" }, { 1, "Back" } }, nullptr);
}
static void omniSsDraw()
{
    const OmniTheme& T = omniTheme();
    if (omniSsView >= 0) { omniSsDrawViewer(T); return; }
    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, 110);
    const OmniSsGeom g = omniSsGeometry();
    omniShadow(g.x, g.y, g.w, g.h, omniRadius + 2, 22, 160, 6);
    fillRounded(g.x, g.y, g.w, g.h, omniRadius + 2, T.panel);
    const int cornerW = omniLabel(OSG::corner(omniSsPager), g.x + g.w - 28, g.y + 34, omniSmall, T.inkFaint, 2);
    omniLabel("Screenshots", g.x + 28, g.y + 34, omniBodyBold, T.ink, 0, g.w - 70 - cornerW);
    if (omniSsShots.empty()) {
        omniLabel(OSG::emptyTitle(), g.x + g.w / 2.f, g.listY + 230.f, omniBodyBold, T.ink, 1);
        omniLabel(OSG::emptyBody(playStationIcons), g.x + g.w / 2.f, g.listY + 266.f, omniSmall, T.inkDim, 1, g.w - 80);
        omniPanelHints({ { 1, "Back" } }, nullptr);
        return;
    }
    for (int k = 0; k < omniSsPager.onPage(); ++k) {
        const int i = omniSsPager.first() + k;
        const OSG::Shot& s = omniSsShots[size_t(i)];
        const bool sel = i == omniSsPager.sel;
        int tx = 0, ty = 0;
        omniSsTileXY(g, k, tx, ty);
        fillRounded(tx, ty, g.tw, g.th, omniRadius, sel ? T.accent : T.tab);
        const SDL_Rect box { physical(tx + 8), physical(ty + 8), physical(OSG::kThumbW), physical(OSG::kThumbH) };
        omniRectPx(box, { 0, 0, 0, 255 });
        auto it = omniSsThumbs.find(s.name);
        if (it != omniSsThumbs.end()) { omniSsBudget.touch(s.name); omniSsBlit(it->second, box.x, box.y, box.w, box.h); }
        else if (omniSsFailed.count(s.name)) omniLabel("Can't show it", tx + 8 + OSG::kThumbW / 2.f, ty + 8 + OSG::kThumbH / 2.f, omniSmall, T.inkFaint, 1);
        const SDL_Color ink = sel ? T.accentInk : T.ink, dim = sel ? T.accentInk : T.inkDim;
        omniLabel(OSG::line1(s), tx + 8, ty + 8 + OSG::kThumbH + 16.f, omniSmallBold, ink, 0, OSG::kThumbW);
        omniLabel(OSG::line2(s), tx + 8, ty + 8 + OSG::kThumbH + 36.f, omniCaption, dim, 0, OSG::kThumbW);
    }
    if (omniSsPager.pages() > 1) omniPanelHints({ { 0, "View" }, { 2, "Delete" }, { omniHintShoulders, "Page" }, { 1, "Back" } }, nullptr);
    else omniPanelHints({ { 0, "View" }, { 2, "Delete" }, { 1, "Back" } }, nullptr);
}

// --- pointer (Cross at the pointer, mouse) and right stick ------------------------------------------------------------------
static bool omniSsClick(int x, int y)
{
    if (omniSsView >= 0) return true;
    const OmniSsGeom g = omniSsGeometry();
    for (int k = 0; k < omniSsPager.onPage(); ++k) {
        int tx = 0, ty = 0;
        omniSsTileXY(g, k, tx, ty);
        if (x < tx || x >= tx + g.tw || y < ty || y >= ty + g.th) continue;
        const int i = omniSsPager.first() + k;
        if (i == omniSsPager.sel) omniSsShow(i); else omniSsPager.sel = i;
        break;
    }
    omniShellDirty = true;
    return true;
}
static bool omniSsScroll(double amount)
{
    if (omniSsView >= 0) return true;
    omniSsScrollAcc -= float(amount);
    while (omniSsScrollAcc >= 50) { omniSsScrollAcc -= 50; omniSsPager.move(0, 1); }
    while (omniSsScrollAcc <= -50) { omniSsScrollAcc += 50; omniSsPager.move(0, -1); }
    omniSsRequestPage();
    return true;
}

// Shown while no features panel is on top (a quick menu opened with Esc meanwhile is used first, then this comes back).
static bool omniSsShown() { return omniSsOpenFlag && omniFxStack.empty(); }
[[maybe_unused]] static const bool omniSsLayer = [] {
    omniOverlayLayers().push_back({ omniSsShown, omniSsButton, omniSsClick, omniSsScroll, omniSsDraw, true });
    return true;
}();

// --- Options > More > Screenshots ----------------------------------------------------------------------------------------
static bool omniSsQuickAction(int id)
{
    if (id != OSG::kTile) return false;
    omniSsOpen();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniQuickActions.h" // OMNI_QUICK_ACTIONS_V1: screenshot folder / file name (pure)\n',
         '#include "OmniQuickActions.h" // OMNI_QUICK_ACTIONS_V1: screenshot folder / file name (pure)\n'
         '#include "OmniShotGallery.h" // OMNI_SCREENSHOT_GALLERY_V1: Options > Screenshots listing / paging / cache (pure)\n'),
    ],
    'OmniQuickMenu.h': [
        ('static void omniFxQuickAllBuild(OmniFxPanel& p)\n',
         'static bool omniSsQuickAction(int id); // OMNI_SCREENSHOT_GALLERY_V1 (OmniShotGalleryShell.h)\n'
         'static void omniFxQuickAllBuild(OmniFxPanel& p)\n'),
        ('    add(omniQmApps, "Apps", true);   // s2 OMNI_HUB_CARDS_V1\n',
         '    add(OmniShotGallery::kTile, "Screenshots", true); // OMNI_SCREENSHOT_GALLERY_V1: the screenshot gallery (More)\n'
         '    add(omniQmApps, "Apps", true);   // s2 OMNI_HUB_CARDS_V1\n'),
        ('    Tab* t = active();\n    switch (r.id) {   // stay open\n',
         '    if (omniSsQuickAction(r.id)) return true; // OMNI_SCREENSHOT_GALLERY_V1: opens the gallery (closes the menu)\n'
         '    Tab* t = active();\n    switch (r.id) {   // stay open\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniShotGalleryShell.h" // OMNI_SCREENSHOT_GALLERY_V1\n'),
        ('    omniPtTick();\n',
         '    omniPtTick();\n'
         '    omniSsTick();       // OMNI_SCREENSHOT_GALLERY_V1: thumbnails / full view from the decode worker\n'),
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
    if 'OMNI_QUICK_ACTIONS_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: OMNI_QUICK_ACTIONS_V1 missing: apply_quick_actions.py first')
    if 'OMNI_SITE_CLEAR_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_SITE_CLEAR_V1 missing: apply_site_clear.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniShotGallery.h', PURE, 'OmniQuickActions.h'),
            write_new('OmniShotGalleryShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
