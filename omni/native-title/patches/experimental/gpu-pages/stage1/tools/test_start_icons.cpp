// OMNI_START_ICONS_V1: host tests of the pure part (engine/entry/OmniStartIcons.h) and of the "icon" fields it adds to
// the start page's data (OmniCw::pageJson, OmniStartCustom::pageJson, OmniWebApps::pageJson) in a patched tree.
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_start_icons.cpp -o t && ./t [vectors.tsv]
// With an argument, "<url>\t<key>" lines are written there: test_start_icons_js.cjs checks start-icons.js against them.
#include "OmniStartIcons.h"
#include "OmniContinueWatching.h"
#include "OmniStartCustom.h"
#include "OmniWebApps.h"
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace I = OmniStartIcons;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)
static bool has(const std::string& s, const std::string& x) { return s.find(x) != std::string::npos; }
static std::string be(uint32_t v) { std::string s(4, '\0'); s[0] = char(v >> 24); s[1] = char(v >> 16); s[2] = char(v >> 8); s[3] = char(v); return s; }
static std::vector<uint8_t> png(uint32_t w = 32, uint32_t h = 32)
{
    std::string s = "\x89PNG\r\n\x1a\n";
    s += be(13) + "IHDR" + be(w) + be(h) + char(8) + char(6) + '\0' + '\0' + '\0' + be(0x12345678) + be(0) + "IEND" + be(0xae426082);
    return std::vector<uint8_t>(s.begin(), s.end());
}

// Addresses whose keys start-icons.js must reproduce exactly (hostKey corners: case, www., port, credentials, IPv6,
// trailing dots, backslash, odd characters, non-http).
static const char* const kUrls[] = {
    "https://www.youtube.com/tv", "https://youtube.com/", "HTTPS://WWW.Example.COM:8443/x?y#z", "http://user:pw@tv.example.org:8443/x#y",
    "https://www.com/", "https://www.", "https://www.a.b/", "https://[::1]:8080/", "https://[2001:DB8::1]/x", "https://[::g]/",
    "https://example.com./", "https://example.com\\evil.com/", "https://a@b@c.example/", "https://exa mple.com/", "ftp://example.com/",
    "javascript:alert(1)", "https://", "https://xn--bcher-kva.example/", "https://under_score.example/", "https://\xC3\xA9t\xC3\xA9.fr/",
    "https://example.com?q=@x.org", "http://localhost:3000/", "https://192.168.0.1/admin", "https://a.b.c.d.e.f.g.example.co.uk/p",
};

int main(int argc, char** argv)
{
    // keys: OMNI_FAVICONS_V1's file names without ".png"
    CHECK(I::key("https://www.youtube.com/tv") == OmniFavicons::fileName("youtube.com").substr(0, 16));
    CHECK(I::key("https://youtube.com/") == I::key("https://WWW.YouTube.com:443/watch?v=1"));
    CHECK(I::validKey(I::key("https://example.com/")) && I::key("https://example.com/").size() == 16);
    CHECK(I::key("ftp://example.com/").empty() && I::key("javascript:alert(1)").empty() && I::key("").empty() && I::key("https://exa mple.com/").empty());
    CHECK(I::siteKey("example.com") == I::key("https://example.com/") && I::siteKey("www.example.com") == I::key("https://example.com/"));
    CHECK(I::siteKey("").empty() && I::siteKey("a/b").empty() && I::siteKey("a@b.com").empty() && I::siteKey("a b").empty() && I::siteKey("x?y").empty());
    CHECK(I::validKey("0123456789abcdef") && !I::validKey("0123456789ABCDEF") && !I::validKey("0123456789abcde") && !I::validKey("0123456789abcdef0")
          && !I::validKey("0123456789abcdeg") && !I::validKey(""));
    CHECK(I::field("0123456789abcdef") == ",\"icon\":\"0123456789abcdef\"" && I::field("").empty() && I::field("\"},{\"x\":1").empty());

    // the route's name check: exactly _user/icon/<16 lowercase hex>.png
    CHECK(I::fileFromRel("_user/icon/0123456789abcdef.png") == "0123456789abcdef.png");
    CHECK(I::fileFromRel("_user/icon/0123456789ABCDEF.png").empty());
    CHECK(I::fileFromRel("_user/icon/0123456789abcdef.PNG").empty());
    CHECK(I::fileFromRel("_user/icon/0123456789abcde.png").empty() && I::fileFromRel("_user/icon/0123456789abcdef0.png").empty());
    CHECK(I::fileFromRel("_user/icon/0123456789abcdef.png.png").empty() && I::fileFromRel("_user/icon/0123456789abcdef.pn").empty());
    CHECK(I::fileFromRel("_user/icon/x/0123456789abcdef.png").empty() && I::fileFromRel("_user/icon/../start-bg.png").empty());
    CHECK(I::fileFromRel("_user/icon/").empty() && I::fileFromRel("_user/icon/index.html").empty() && I::fileFromRel("_user/iconz/0123456789abcdef.png").empty());
    CHECK(I::fileFromRel("_user/icons/0123456789abcdef.png").empty() && I::fileFromRel("start/0123456789abcdef.png").empty());
    CHECK(I::fileFromRel(std::string("_user/icon/0123456789abcde\0.png", 31)).empty());
    // the requesting document
    CHECK(I::startPage("omni://pages/start/index.html") && I::startPage("omni://pages/start/index.html?x#y") && I::startPage("omni://pages/start/"));
    CHECK(!I::startPage("omni://pages/pdf/index.html") && !I::startPage("omni://pages/startx/") && !I::startPage("https://evil.example/omni://pages/start/")
          && !I::startPage(""));
    // the bytes: a 32 x 32 PNG only
    CHECK(I::isPng(png()) && !I::isPng(png(16, 16)) && !I::isPng(std::vector<uint8_t>()) && !I::isPng(std::vector<uint8_t>(64, 'x')));

    // Continue watching: "icon" from the page address (appended: the existing fields keep their order)
    {
        OmniCw::Entry a; a.key = "w:k1"; a.url = "https://www.example.com/v?a=1"; a.title = "Ep 1"; a.position = 1800; a.duration = 3600;
        OmniCw::Entry b; b.key = "w:k2"; b.url = "about:blank"; b.title = "B"; b.position = 600; b.duration = 1200;
        const std::string j = OmniCw::pageJson({ a, b }, -1, "h");
        CHECK(has(j, "\"left\":\"30 min left\",\"icon\":\"" + I::key(a.url) + "\"}"));
        CHECK(has(j, "\"k\":\"w:k2\"") && j.find("\"icon\"") == j.rfind("\"icon\""));   // no key for about:blank
    }
    // Start page customisation: reading entries from their site, closed tabs from their address
    {
        namespace S = OmniStartCustom;
        const std::vector<S::Reading> rl = { { "r1.html", "T", "a.com", "Today" }, { "r2.html", "", "", "" } };
        const std::vector<S::Closed> cl = { { "https://www.b.org/x", "B", "b.org" }, { "http://[::1]/", "L", "[::1]" } };
        const std::string j = S::pageJson(S::defaults(), false, true, rl, cl, "", "");
        CHECK(has(j, "{\"id\":\"r1.html\",\"t\":\"T\",\"s\":\"a.com\",\"d\":\"Today\",\"icon\":\"" + I::key("https://a.com/") + "\"}"));
        CHECK(has(j, "{\"id\":\"r2.html\",\"t\":\"Saved page\"") || has(j, "\"id\":\"r2.html\""));
        CHECK(has(j, "\"s\":\"b.org\",\"icon\":\"" + I::key("https://b.org/") + "\"}") && has(j, "\"icon\":\"" + I::key("http://[::1]/") + "\""));
        S::Json v;
        CHECK(S::parseJson(j, v) && v.t == S::Json::tObj && v.o["reading"].a.size() == 2 && v.o["closed"].a.size() == 2);
        CHECK(v.o["reading"].a[1].o.count("icon") == 0);   // no site: no key
        CHECK(!has(S::pageJson(S::defaults(), true, true, rl, cl, "", ""), "b.org"));   // private: still no closed tabs
    }
    // Web apps: the key only, still never an address
    {
        OmniWebApps::App a; a.id = "a0123456789ab"; a.name = "YouTube"; a.url = "https://www.youtube.com/tv"; a.theme = "#ff0000";
        const std::string j = OmniWebApps::pageJson({ a }, "h");
        CHECK(has(j, "\"l\":\"Y\",\"icon\":\"" + I::key(a.url) + "\"}") && !has(j, "https://") && !has(j, "youtube.com/tv"));
    }

    if (argc > 1) {
        std::ofstream out(argv[1], std::ios::binary);
        for (const char* u : kUrls) out << u << '\t' << I::key(u) << '\n';
        std::printf("vectors: %zu written to %s\n", sizeof kUrls / sizeof kUrls[0], argv[1]);
    }
    std::printf("%s: %d/%d checks passed\n", failures ? "FAILED" : "OK", checks - failures, checks);
    return failures ? 1 : 0;
}
