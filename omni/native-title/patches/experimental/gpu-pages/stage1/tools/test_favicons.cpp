// OMNI_FAVICONS_V1: host tests of the pure part (engine/entry/OmniFavicons.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_favicons.cpp -o t && ./t [script.js]
// With an argument, the capture script (an async function body) is written there for test_favicons_js.mjs.
#include "OmniFavicons.h"
#include <climits>
#include <cstdio>
#include <cstring>
#include <fstream>

namespace F = OmniFavicons;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static std::string be(uint32_t v) { std::string s(4, '\0'); s[0] = char(v >> 24); s[1] = char(v >> 16); s[2] = char(v >> 8); s[3] = char(v); return s; }
// A PNG header as the page's canvas makes it (IHDR + IEND; libpng does the real decode on the console).
static std::string fakePng(uint32_t w = 32, uint32_t h = 32, int depth = 8, int type = 6, size_t pad = 0)
{
    std::string s = "\x89PNG\r\n\x1a\n";
    s += be(13) + "IHDR" + be(w) + be(h) + char(depth) + char(type) + '\0' + '\0' + '\0' + be(0x12345678);
    if (pad) s += be(uint32_t(pad)) + "IDAT" + std::string(pad, 'x') + be(0);
    s += be(0) + "IEND" + be(0xae426082);
    return s;
}

int main(int argc, char** argv)
{
    // --- host keys
    CHECK(F::hostKey("https://www.Example.com/a?b#c") == "example.com");
    CHECK(F::hostKey("http://example.com:8080/") == "example.com");
    CHECK(F::hostKey("HTTPS://user:pw@Sub.Example.COM./x") == "sub.example.com");
    CHECK(F::hostKey("https://www.com/") == "www.com");            // "www." kept when nothing would be left
    CHECK(F::hostKey("https://www.co.uk/") == "co.uk");
    CHECK(F::hostKey("https://[::1]:8443/x") == "[::1]");
    CHECK(F::hostKey("https://[::1/x").empty());
    CHECK(F::hostKey("https://a b.com/").empty());
    CHECK(F::hostKey("omni://pages/start/").empty());
    CHECK(F::hostKey("data:text/html,hi").empty());
    CHECK(F::hostKey("about:blank").empty());
    CHECK(F::hostKey("https:///x").empty());
    CHECK(F::hostKey("https://evil.com\\@good.com/").empty() || F::hostKey("https://evil.com\\@good.com/") == "evil.com");
    CHECK(F::hostKey("https://good.com@evil.com/") == "evil.com");
    CHECK(F::hostKey("https://" + std::string(254, 'a') + "/").empty());
    // --- file names
    const std::string n = F::fileName("example.com");
    CHECK(n.size() == 20 && F::isIconFileName(n));
    CHECK(n == F::fileName(F::hostKey("https://www.example.com/")));
    CHECK(n != F::fileName("example.org"));
    CHECK(n.find("example") == std::string::npos);
    CHECK(F::fileName("").empty());
    CHECK(F::fnv1a64("") == 14695981039346656037ULL);
    CHECK(F::fnv1a64("a") == 0xaf63dc4c8601ec8cULL);
    CHECK(!F::isIconFileName("0123456789abcdeF.png"));
    CHECK(!F::isIconFileName("0123456789abcdef.png.tmp"));
    CHECK(!F::isIconFileName("../3456789abcdef.png"));
    CHECK(F::isIconFileName("0123456789abcdef.png"));
    // --- refresh
    CHECK(F::needsCapture(false, 0, 1000));
    CHECK(!F::needsCapture(true, 1000, 1000 + F::kRefreshSecs - 1));
    CHECK(F::needsCapture(true, 1000, 1000 + F::kRefreshSecs));
    CHECK(F::needsCapture(true, 1000 + 2 * 86400, 1000));      // clock went back
    // --- index (LRU)
    {
        F::Index ix;
        for (int i = 0; i < 300; ++i) ix.put("f" + std::to_string(i), 1000, 100 + i);
        CHECK(ix.count() == 300 && ix.bytes() == 300000);
        CHECK(ix.evict("f0").empty());
        ix.put("new", 1000, 50);                                  // oldest stamp, but just written: kept
        auto gone = ix.evict("new");
        CHECK(gone.size() == 1 && gone[0] == "f0");
        CHECK(ix.count() == 300 && ix.has("new") && !ix.has("f0"));
        ix.touch("f1", 10000);                                    // drawn: now the newest
        ix.put("x", 1000, 9000);
        gone = ix.evict("x");
        CHECK(gone.size() == 1 && gone[0] == "new");
        ix.put("x", 1500, 9000);                                  // replaced: bytes follow
        CHECK(ix.bytes() == 300500);
        ix.touch("x", 5);                                         // never moves back
        CHECK(ix.stamp("x") == 9000);
        CHECK(ix.remove("x") && !ix.remove("x"));
        // byte cap
        F::Index b;
        for (int i = 0; i < 10; ++i) b.put("b" + std::to_string(i), 300000, i);
        gone = b.evict("b9");
        CHECK(b.bytes() <= F::kMaxBytes && gone.size() == 4 && gone[0] == "b0" && gone[3] == "b3");
        // a single file over the cap that must be kept: no endless loop
        F::Index c;
        c.put("big", F::kMaxBytes + 1, 1);
        CHECK(c.evict("big").empty() && c.has("big"));
        // removeSince
        F::Index r;
        r.put("a", 1, 100); r.put("b", 1, 200); r.put("c", 1, 300);
        gone = r.removeSince(200);
        CHECK(gone.size() == 2 && r.has("a") && !r.has("b") && !r.has("c"));
        CHECK(r.removeSince(LLONG_MIN).size() == 1 && r.count() == 0 && r.bytes() == 0);
    }
    // --- base64
    {
        std::string out;
        CHECK(F::base64Encode("") == "" && F::base64Encode("f") == "Zg==" && F::base64Encode("fo") == "Zm8=" && F::base64Encode("foo") == "Zm9v");
        CHECK(F::base64Decode("Zm9vYmE=", out) && out == "fooba");
        CHECK(F::base64Decode("Zm9vYg==", out) && out == "foob");
        CHECK(F::base64Decode("", out) && out.empty());
        CHECK(!F::base64Decode("Zm9", out));
        CHECK(!F::base64Decode("Zm=v", out));
        CHECK(!F::base64Decode("Z===", out));
        CHECK(!F::base64Decode("Zm9v\n", out));
        CHECK(!F::base64Decode("Zm 9", out));
        std::string all;
        for (int i = 0; i < 256; ++i) all += char(i);
        CHECK(F::base64Decode(F::base64Encode(all), out) && out == all);
    }
    // --- PNG header
    CHECK(F::isPng32(fakePng()));
    CHECK(F::isPng32(fakePng(32, 32, 8, 2)) && F::isPng32(fakePng(32, 32, 8, 3)));
    CHECK(!F::isPng32(fakePng(16, 16)));
    CHECK(!F::isPng32(fakePng(32, 32, 16)));
    CHECK(!F::isPng32(fakePng(32, 32, 8, 5)));
    CHECK(!F::isPng32(fakePng(32, 32, 8, 6, F::kMaxPngBytes)));
    CHECK(!F::isPng32(fakePng().substr(0, 40)));
    {
        std::string p = fakePng(); p[1] = 'Q';
        CHECK(!F::isPng32(p));
        CHECK(F::dataUrl(p).empty());
        CHECK(F::dataUrl(fakePng()) == "data:image/png;base64," + F::base64Encode(fakePng()));
    }
    // --- answers
    {
        const std::string png = fakePng(32, 32, 8, 6, 100);
        const std::string url = "data:image/png;base64," + F::base64Encode(png);
        F::Answer a = F::parseAnswer("omni-fav;www.Example.com;png;" + url);
        CHECK(a.ok && a.host == "example.com" && a.png == png);
        a = F::parseAnswer("omni-fav;[::1];png;" + url);
        CHECK(a.ok && a.host == "[::1]");
        a = F::parseAnswer("omni-fav;example.com;none;tainted");
        CHECK(!a.ok && a.host == "example.com" && a.why == "tainted");
        CHECK(!F::parseAnswer("omni-fav;example.com;png;data:image/jpeg;base64,AAAA").ok);
        CHECK(!F::parseAnswer("omni-fav;example.com;png;data:image/png;base64,@@@@").ok);
        CHECK(!F::parseAnswer("omni-fav;example.com;png;data:image/png;base64," + F::base64Encode(fakePng(64, 64))).ok);
        CHECK(!F::parseAnswer("omni-fav;bad host;png;" + url).ok);
        CHECK(!F::parseAnswer("omni-fav;;png;" + url).ok);
        CHECK(!F::parseAnswer("omni-favx;example.com;png;" + url).ok);
        CHECK(!F::parseAnswer("").ok);
        CHECK(!F::parseAnswer("omni-fav;example.com").ok);
        CHECK(!F::parseAnswer("omni-fav;example.com;png;data:image/png;base64," + F::base64Encode(fakePng(32, 32, 8, 6, F::kMaxPngBytes))).ok);
        CHECK(F::parseAnswer(std::string(F::kMaxAnswer + 1, 'a')).why == "too big");
        // the largest PNG accepted still fits in an answer
        const std::string maxPng = fakePng(32, 32, 8, 6, F::kMaxPngBytes - fakePng().size() - 12);
        CHECK(maxPng.size() == F::kMaxPngBytes && F::isPng32(maxPng));
        CHECK(F::parseAnswer("omni-fav;" + std::string(200, 'a') + ".com;png;data:image/png;base64," + F::base64Encode(maxPng)).ok);
    }
    // --- scaling
    {
        std::vector<uint8_t> src(32 * 32 * 4);
        for (size_t i = 0; i < src.size(); i += 4) { src[i] = 200; src[i + 1] = 100; src[i + 2] = 50; src[i + 3] = 255; }
        for (int px : { 18, 22, 27, 32, 40, 48, 60 }) {
            std::vector<uint8_t> dst(size_t(px) * px * 4, 7);
            F::scaleRgba(src.data(), 32, 32, dst.data(), px, px);
            bool same = true;
            for (size_t i = 0; i < dst.size(); i += 4) same = same && dst[i] == 200 && dst[i + 1] == 100 && dst[i + 2] == 50 && dst[i + 3] == 255;
            CHECK(same);
        }
        // a transparent half keeps its colour out of the opaque half (premultiplied filtering)
        for (int y = 0; y < 32; ++y) for (int x = 0; x < 16; ++x) { uint8_t* p = &src[(size_t(y) * 32 + x) * 4]; p[0] = 0; p[1] = 255; p[2] = 0; p[3] = 0; }
        std::vector<uint8_t> d(22 * 22 * 4);
        F::scaleRgba(src.data(), 32, 32, d.data(), 22, 22);
        bool clean = true;
        for (size_t i = 0; i < d.size(); i += 4) if (d[i + 3] > 0) clean = clean && d[i] == 200 && d[i + 1] == 100 && d[i + 2] == 50;
        CHECK(clean);
        CHECK(d[3] == 0 && d[(21) * 4 + 3] == 255);
        // up-scaling (60 px from 32): edges and middle sane
        std::vector<uint8_t> u(60 * 60 * 4);
        F::scaleRgba(src.data(), 32, 32, u.data(), 60, 60);
        CHECK(u[3] == 0 && u[59 * 4 + 3] == 255 && u[59 * 4] == 200);
        // 1 x 1 and degenerate sizes: no crash
        uint8_t one[4] = { 0, 0, 0, 0 };
        F::scaleRgba(src.data(), 32, 32, one, 1, 1);
        CHECK(one[3] > 100 && one[3] < 160);
        F::scaleRgba(src.data(), 0, 32, one, 1, 1);
    }
    // --- the script
    {
        const std::string s = F::captureScript();
        CHECK(s.find("const tag = \"omni-fav\", px = 32,") == 0);
        CHECK(s.find("return await race(") != std::string::npos);
        CHECK(s.find("fetch(") == std::string::npos && s.find("XMLHttpRequest") == std::string::npos);   // the page's <img> only
        CHECK(s.find("crossOrigin = \"anonymous\"") != std::string::npos);
        CHECK(s.back() == '\n');
        if (argc > 1) { std::ofstream(argv[1], std::ios::binary) << s; std::printf("script written to %s (%zu bytes)\n", argv[1], s.size()); }
    }
    std::printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
