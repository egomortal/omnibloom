// OMNI_SCREENSHOT_GALLERY_V1: host tests of the pure part (OmniShotGallery.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_screenshot_gallery.cpp -o t && ./t
#include "OmniShotGallery.h"
#include "OmniQuickActions.h"

#include <cstdio>
#include <set>

namespace G = OmniShotGallery;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static void names()
{
    // what the screenshot writer produces
    struct tm t {};
    t.tm_year = 2026 - 1900; t.tm_mon = 10; t.tm_mday = 16; t.tm_hour = 14; t.tm_min = 3; t.tm_sec = 9;
    const std::string when = OmniQuickActions::stamp(t);
    const std::string a = OmniQuickActions::fileName(OmniQuickActions::hostForFile("https://www.Example.com:8443/x"), when);
    const std::string b = OmniQuickActions::fileName("example.com", when, 2);
    G::Name n = G::parseName(a);
    CHECK(n.ok && n.host == "example.com" && n.stamp == "20261116140309" && n.n == 1);
    n = G::parseName(b);
    CHECK(n.ok && n.host == "example.com" && n.stamp == "20261116140309" && n.n == 2);
    n = G::parseName("my-site.co.uk-20260101-000000-99.PNG");
    CHECK(n.ok && n.host == "my-site.co.uk" && n.n == 99 && n.stamp == "20260101000000");
    n = G::parseName("page-20261116-140309.png");
    CHECK(n.ok && n.host == "page");
    // hosts that end in digits are not mistaken for -n
    n = G::parseName("10.0.0.2-20261116-140309.png");
    CHECK(n.ok && n.host == "10.0.0.2" && n.n == 1);
    CHECK(!G::parseName("example.com-20261116-140309-1.png").ok);     // -1 is never written
    CHECK(!G::parseName("example.com-20261116-140309-100.png").ok);   // three digits: not ours
    CHECK(!G::parseName("example.com-20261316-140309.png").ok);       // month 13
    CHECK(!G::parseName("example.com-20261116-250309.png").ok);       // hour 25
    CHECK(!G::parseName("-20261116-140309.png").ok);                  // no host
    CHECK(!G::parseName("20261116-140309.png").ok);
    CHECK(!G::parseName("Example.com-20261116-140309.png").ok);       // the writer lower-cases
    CHECK(!G::parseName("holiday.png").ok);
    CHECK(!G::parseName("example.com-20261116-140309.jpg").ok);
    CHECK(G::formatWhen("20261116140309") == "16 Nov 2026, 14:03");
    CHECK(G::formatWhen("20260105090000") == "5 Jan 2026, 09:00");
    CHECK(G::formatWhen("2026") == "");
    CHECK(G::stampOf(2026, 11, 16, 14, 3, 9) == "20261116140309");
    CHECK(G::stampOf(2026, 13, 16, 14, 3, 9) == "");
    CHECK(G::stampOf(-1, 1, 1, 0, 0, 0) == "");
    CHECK(G::listable("a.PNG") && !G::listable(".hidden.png") && !G::listable("x.png.part") && !G::listable(".png"));
}

static void listing()
{
    std::vector<G::File> f = {
        { "example.com-20261116-140309.png", 100, "20261116140310" },
        { "example.com-20261116-140309-2.png", 100, "20261116140310" },
        { "news.org-20261117-080000.png", 100, "20261117080001" },
        { "holiday.png", 100, "20261118120000" },          // no name stamp: its file time, newest
        { "page-20251231-235959.png", 100, "" },
        { "empty-20261116-140309.png", 0, "" },             // still being written / failed
        { ".hidden-20261116-140309.png", 10, "" },
        { "notes.txt", 10, "20990101000000" },
        { "odd.png", 10, "" },                              // no time at all: last
    };
    const auto s = G::list(f);
    CHECK(s.size() == 6);
    CHECK(s[0].name == "holiday.png" && s[0].host.empty() && s[0].when == "18 Nov 2026, 12:00");
    CHECK(s[1].name == "news.org-20261117-080000.png" && s[1].host == "news.org");
    CHECK(s[2].name == "example.com-20261116-140309-2.png");
    CHECK(s[3].name == "example.com-20261116-140309.png");
    CHECK(s[4].name == "page-20251231-235959.png" && s[4].host.empty() && s[4].when == "31 Dec 2025, 23:59");
    CHECK(s[5].name == "odd.png" && s[5].when.empty());
    CHECK(G::indexOf(s, "news.org-20261117-080000.png") == 1 && G::indexOf(s, "nope.png") == -1);
    CHECK(G::line1(s[1]) == "news.org" && G::line2(s[1]) == "17 Nov 2026, 08:00");
    CHECK(G::line1(s[0]) == "18 Nov 2026, 12:00" && G::line2(s[0]).empty());
    CHECK(G::line1(s[5]) == "odd.png");
    CHECK(G::viewerCaption(s[1], 1, 6) == "news.org   17 Nov 2026, 08:00   2 / 6");
    CHECK(G::viewerCaption(s[0], 0, 6) == "18 Nov 2026, 12:00   1 / 6");
    CHECK(G::askBody(s[1]).rfind("news.org, 17 Nov 2026, 08:00. It moves to the Downloads trash", 0) == 0);
    std::vector<G::File> many;
    for (int i = 0; i < int(G::kMaxList) + 10; ++i) many.push_back({ "s" + std::to_string(i) + ".png", 1, "" });
    CHECK(G::list(many).size() == G::kMaxList);
}

static void paging()
{
    G::Pager p; p.count = 0;
    CHECK(p.pages() == 1 && p.onPage() == 0 && !p.move(1, 0) && !p.move(0, 1) && !p.pageBy(1));
    CHECK(G::corner(p).empty());
    p.count = 30; p.sel = 0;   // pages: 0..11, 12..23, 24..29
    CHECK(p.pages() == 3 && p.page() == 0 && p.onPage() == 12);
    CHECK(G::corner(p) == "30 screenshots   Page 1 of 3");
    CHECK(!p.move(-1, 0) && !p.move(0, -1));
    CHECK(p.move(1, 0) && p.sel == 1);
    CHECK(p.move(0, 1) && p.sel == 5);
    p.sel = 11;
    CHECK(p.move(1, 0) && p.sel == 12 && p.page() == 1);       // right across the page end
    CHECK(p.move(-1, 0) && p.sel == 11 && p.page() == 0);
    p.sel = 9;
    CHECK(p.move(0, 1) && p.sel == 13 && p.page() == 1);       // down from the last row: next page
    CHECK(p.pageBy(1) && p.sel == 25 && p.page() == 2 && p.onPage() == 6);
    CHECK(!p.pageBy(1) && p.sel == 25);
    p.sel = 21;
    CHECK(p.pageBy(1) && p.sel == 29);                          // the next page is shorter: its last shot
    CHECK(p.pageBy(-1) && p.sel == 17 && p.pageBy(-1) && p.sel == 5 && !p.pageBy(-1));
    p.sel = 26;                                                  // row 6 of 7 (26..27 | 28..29)
    CHECK(p.move(0, 1) && p.sel == 29);                          // shorter last row: the last shot
    CHECK(!p.move(0, 1) && !p.move(1, 0));
    CHECK(p.onCurrentPage(24) && p.onCurrentPage(29) && !p.onCurrentPage(23));
    p.count = 1; p.sel = 0;
    CHECK(G::corner(p) == "1 screenshot");
    p.count = 5; p.sel = 9; p.clamp();
    CHECK(p.sel == 4);
    p.count = 0; p.clamp();
    CHECK(p.sel == 0);
}

static void pixels()
{
    G::Size s = G::fit(1920, 1000, 240, 135);
    CHECK(s.w == 240 && s.h == 125);
    s = G::fit(1000, 2000, 240, 135);
    CHECK(s.h == 135 && s.w == 67);
    s = G::fit(100, 50, 240, 135);
    CHECK(s.w == 240 && s.h == 120);
    s = G::fit(100, 50, 240, 135, false);
    CHECK(s.w == 100 && s.h == 50);
    s = G::fit(5000, 1, 240, 135);
    CHECK(s.w == 240 && s.h == 1);
    s = G::fit(0, 10, 240, 135);
    CHECK(s.w == 0 && s.h == 0);
    // box filter: a 4 x 2 RGB image (left half red, right half blue) -> 2 x 1
    std::vector<uint8_t> rgb = { 255,0,0, 255,0,0, 0,0,255, 0,0,255,  255,0,0, 255,0,0, 0,0,255, 0,0,255 };
    G::Pack abgr;   // R at 0, G at 8, B at 16 (the console canvas)
    uint32_t out[2] = {};
    G::scale(rgb.data(), 4, 2, 12, out, 2, 1, abgr);
    CHECK(out[0] == 0xff0000ffu && out[1] == 0xffff0000u);
    G::Pack argb; argb.rs = 16; argb.gs = 8; argb.bs = 0;
    G::scale(rgb.data(), 4, 2, 12, out, 1, 1, argb);
    CHECK(out[0] == (0xff000000u | (128u << 16) | 128u));       // 50 % red, 50 % blue (rounded)
    // upscale: every target pixel takes one source pixel
    uint32_t big[16] = {};
    G::scale(rgb.data(), 4, 2, 12, big, 8, 2, abgr);
    CHECK(big[0] == 0xff0000ffu && big[3] == 0xff0000ffu && big[4] == 0xffff0000u && big[15] == 0xffff0000u);
    // stride with padding
    std::vector<uint8_t> padded = { 10,20,30, 0,0,  40,50,60, 0,0 };
    uint32_t one = 0;
    G::scale(padded.data(), 1, 2, 5, &one, 1, 1, abgr);
    CHECK(one == (0xff000000u | (45u << 16) | (35u << 8) | 25u));
    // PNG header
    const uint8_t hdr[24] = { 0x89,'P','N','G','\r','\n',0x1a,'\n', 0,0,0,13, 'I','H','D','R', 0,0,7,0x80, 0,0,3,0xe8 };
    uint32_t w = 0, h = 0;
    CHECK(G::pngSize(hdr, 24, w, h) && w == 1920 && h == 1000);
    CHECK(!G::pngSize(hdr, 23, w, h));
    uint8_t bad[24]; for (int i = 0; i < 24; ++i) bad[i] = hdr[i];
    bad[1] = 'J';
    CHECK(!G::pngSize(bad, 24, w, h));
    CHECK(G::decodeSizeOk(1920, 1000) && G::decodeSizeOk(4096, 4096) && !G::decodeSizeOk(8193, 10) && !G::decodeSizeOk(8192, 8192) && !G::decodeSizeOk(0, 5));
    CHECK(G::viewMiB(1920, 1000) == 13);
}

static void budget()
{
    G::Budget b(1000);
    std::vector<std::string> ev;
    auto none = [](const std::string&) { return false; };
    CHECK(b.admit("a", 400, none, ev) && b.admit("b", 400, none, ev) && ev.empty() && b.total() == 800);
    b.touch("a");                                       // b is now the least recently used
    CHECK(b.admit("c", 400, none, ev) && ev.size() == 1 && ev[0] == "b" && b.total() == 800 && b.has("a") && !b.has("b"));
    ev.clear();
    auto keepAC = [](const std::string& k) { return k == "a" || k == "c"; };
    CHECK(!b.admit("d", 400, keepAC, ev) && ev.empty() && !b.has("d") && b.total() == 800);   // the page is kept
    CHECK(!b.admit("e", 1001, none, ev));
    CHECK(b.admit("a", 100, none, ev) && b.total() == 500 && b.size() == 2);                  // replaced, not doubled
    b.remove("c"); b.remove("zzz");
    CHECK(b.total() == 100 && b.size() == 1);
    b.clear();
    CHECK(b.total() == 0 && b.size() == 0);
    // the real cap holds a 4K page of thumbnails (720 x 405 canvas px each at displayScale 3)
    G::Budget real;
    const size_t thumb4k = size_t(720) * 405 * 4;
    int kept = 0;
    for (int i = 0; i < G::kPerPage; ++i) kept += real.admit("t" + std::to_string(i), thumb4k, none, ev);
    CHECK(kept == G::kPerPage && real.total() <= G::kCacheBytes);
}

static void trash()
{
    CHECK(G::trashDir(OmniQuickActions::kShotDir) == "/data/omni/downloads/media-worker/Saved/.trash/Screenshots");
    CHECK(G::trashDir("/a/b/") == "/a/.trash/b");
    CHECK(G::trashDir("nofolder").empty());
    std::set<std::string> taken = { "/t/x.png", "/t/x (2).png" };
    auto exists = [&](const std::string& p) { return taken.count(p) != 0; };
    CHECK(G::trashPath("/t", "y.png", exists) == "/t/y.png");
    CHECK(G::trashPath("/t", "x.png", exists) == "/t/x (3).png");
    CHECK(G::trashPath("/t", "noext", exists) == "/t/noext");
    auto all = [](const std::string&) { return true; };
    CHECK(G::trashPath("/t", "x.png", all).empty());
}

int main()
{
    names();
    listing();
    paging();
    pixels();
    budget();
    trash();
    CHECK(G::emptyBody(true).find("L2 + R3") != std::string::npos && G::emptyBody(false).find("LT + RS") != std::string::npos);
    printf("%s: %d checks, %d failures\n", failures ? "FAILED" : "ok", checks, failures);
    return failures ? 1 : 0;
}
