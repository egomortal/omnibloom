// OMNI_UBLOCK_FRAMES_V1 host test for engine/entry/OmniUBlockFrames.h (written by apply_ublock_frames.py).
// g++ -std=c++17 -Wall -Wextra -Werror -I <tree>/engine/entry test_ublock_frames.cpp -o t && ./t [always-generic.js [lite.js]]
// With always-generic.js: also checks the real highly generic list and prints the subframe script's size
// (and writes it to lite.js, for the browser check in test_ublock_frames.cjs).
#include "OmniUBlockFrames.h"
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniUBlockFrames;

static bool has(const std::vector<std::string>& v, const std::string& s) { for (auto& x : v) if (x == s) return true; return false; }

int main(int argc, char** argv)
{
    // ---- host keys: a frame is keyed by its own host
    CHECK(hostKey("https://player.vimeo.com/video/1?h=2") == "player.vimeo.com");
    CHECK(hostKey("https://WWW.YouTube-NoCookie.com/embed/x") == "www.youtube-nocookie.com");   // www. kept: rules match parents
    CHECK(hostKey("http://user:pw@ads.example.net:8080/x") == "ads.example.net");
    CHECK(hostKey("https://example.com./") == "example.com");
    CHECK(hostKey("https://example.com") == "example.com");
    CHECK(hostKey("https://example.com?x=1") == "example.com");
    CHECK(hostKey("https://example.com#a") == "example.com");
    CHECK(hostKey("https://a@b@c.example/") == "c.example");
    CHECK(hostKey("https://xn--bcher-kva.de/") == "xn--bcher-kva.de");
    CHECK(hostKey("https://127.0.0.1:9/") == "127.0.0.1");
    CHECK(hostKey("https://[::1]/").empty());
    CHECK(hostKey("about:blank").empty());          // matched by WebKit through the parent document
    CHECK(hostKey("about:srcdoc").empty());
    CHECK(hostKey("blob:https://a.example/123").empty());
    CHECK(hostKey("data:text/html,<p>").empty());
    CHECK(hostKey("javascript:alert(1)").empty());
    CHECK(hostKey("ftp://a.example/").empty());
    CHECK(hostKey("HTTPS://a.example/").empty());   // WebKit hands lower-case schemes; anything else gets no rules
    CHECK(hostKey("https://").empty());
    CHECK(hostKey("https:///path").empty());
    CHECK(hostKey("https://exa_mple.com/").empty());
    CHECK(hostKey("https://ex\xc3\xa4mple.com/").empty());
    CHECK(hostKey("https://" + std::string(254, 'a') + "/").empty());
    CHECK(hostKey("https://" + std::string(253, 'a') + "/").size() == 253);

    // ---- registration cap: 48 total, 16 frame-only, least recently used first, the new host never
    {
        std::vector<Registered> live;
        for (int i = 0; i < 48; ++i) live.push_back({ "top" + std::to_string(i), static_cast<unsigned long long>(i + 1), false });
        CHECK(evictions(live, "top0", 48, 16).empty());                    // at the cap: nothing
        live.push_back({ "f1", 100, true });                               // 49th: one frame-only, over the total cap
        auto out = evictions(live, "f1", 48, 16);
        CHECK(out.size() == 1 && out[0] == "top0");                        // the oldest page host, not the new frame host
        out = evictions(live, "top0", 48, 16);
        CHECK(out.size() == 1 && out[0] == "top1");                        // the kept host is skipped
    }
    {
        // 20 frame-only hosts and 10 page hosts: the 4 oldest frame-only hosts go, page hosts stay
        std::vector<Registered> live;
        for (int i = 0; i < 10; ++i) live.push_back({ "page" + std::to_string(i), static_cast<unsigned long long>(i + 1), false });
        for (int i = 0; i < 20; ++i) live.push_back({ "frame" + std::to_string(i), static_cast<unsigned long long>(100 + i), true });
        auto out = evictions(live, "frame19", 48, 16);
        CHECK(out.size() == 4);
        CHECK(has(out, "frame0") && has(out, "frame1") && has(out, "frame2") && has(out, "frame3"));
        CHECK(!has(out, "page0"));
        // kill switch: frame-only cap = total cap -> the old behaviour (nothing over 48)
        CHECK(evictions(live, "frame19", 48, 48).empty());
        // the kept host is frame-only and the oldest: the next oldest frame-only hosts go instead
        live[10].used = 0;   // frame0 oldest of all
        out = evictions(live, "frame0", 48, 16);
        CHECK(out.size() == 4 && !has(out, "frame0") && has(out, "frame4"));
    }
    {
        // both caps at once: 40 page hosts + 18 frame-only (58): 2 frame-only for their cap, then 8 more by age
        std::vector<Registered> live;
        for (int i = 0; i < 40; ++i) live.push_back({ "p" + std::to_string(i), static_cast<unsigned long long>(1000 + i), false });
        for (int i = 0; i < 18; ++i) live.push_back({ "f" + std::to_string(i), static_cast<unsigned long long>(1 + i), true });
        auto out = evictions(live, "p39", 48, 16);
        CHECK(out.size() == 10);
        size_t frames = 0; for (auto& h : out) if (h[0] == 'f') ++frames;
        CHECK(frames == 10);                                               // the frame hosts are all older here
        size_t left = 58 - out.size(), leftFrames = 18 - frames;
        CHECK(left == 48 && leftFrames <= 16);
    }
    {
        // the old loop's case: one kept host and nothing else over the cap
        std::vector<Registered> live { { "only", 1, true } };
        CHECK(evictions(live, "only", 0, 0).empty());
        CHECK(evictions({ }, "x", 48, 16).empty());
    }
    {
        // simulate a long session through the real policy: never more than 48 / 16 registered
        std::vector<Registered> live;
        unsigned long long clock = 0;
        bool ok = true;
        for (int step = 0; step < 2000; ++step) {
            const bool frame = step % 3 != 0;
            std::string host = (frame ? "ad" : "site") + std::to_string((step * 7919) % (frame ? 97 : 61));
            bool found = false;
            for (auto& r : live) if (r.host == host) { r.used = ++clock; if (!frame) r.frameOnly = false; found = true; }
            if (!found) live.push_back({ host, ++clock, frame });
            for (auto& v : evictions(live, host, 48, 16))
                for (size_t i = 0; i < live.size(); ++i) if (live[i].host == v) { live.erase(live.begin() + i); break; }
            size_t f = 0; for (auto& r : live) if (r.frameOnly) ++f;
            bool kept = false; for (auto& r : live) if (r.host == host) kept = true;
            if (live.size() > 48 || f > 16 || !kept) ok = false;
        }
        CHECK(ok);
    }

    // ---- non-ASCII kept out of the script (8-bit string in JavaScriptCore)
    {
        std::string out;
        CHECK(asciiLiteral("\"a\\\"b\"", out) && out == "\"a\\\"b\"");
        CHECK(asciiLiteral("\xd1\x81", out) && out == "\\u0441");                   // Cyrillic es
        CHECK(asciiLiteral("x\xe2\x82\xac", out) && out == "x\\u20ac");             // euro sign
        CHECK(asciiLiteral("\xf0\x9f\x98\x80", out) && out == "\\ud83d\\ude00");    // astral: surrogate pair
        CHECK(!asciiLiteral("\xd1", out));                                          // cut
        CHECK(!asciiLiteral("\xff", out));
    }

    // ---- the subframe generic script
    {
        const std::string src = "const x = 1;\nconst omniHighly = \"div[a=\\\"1\\\"],\\n.ad-\xd1\x81lot\";\nconst y = 2;\n";
        std::string s = highlyGenericScript(src, "[\"trusted.example\"]");
        CHECK(!s.empty());
        CHECK(s.find("const H = \"div[a=\\\"1\\\"],\\n.ad-\\u0441lot\";") != std::string::npos);
        CHECK(s.find("const ALLOW = [\"trusted.example\"];") != std::string::npos);
        CHECK(s.find("window.top === window") != std::string::npos);
        CHECK(s.find("self.omniGenericOff === true") != std::string::npos);
        CHECK(s.find("omniGenericExc") != std::string::npos);
        bool ascii = true; for (unsigned char c : s) if (c >= 0x80) ascii = false;
        CHECK(ascii);
        CHECK(highlyGenericScript(src, "").find("const ALLOW = [];") != std::string::npos);
        CHECK(highlyGenericScript("no list here", "[]").empty());
        CHECK(highlyGenericScript("const omniHighly = \"\";", "[]").empty());
        CHECK(highlyGenericScript("const omniHighly = \"abc", "[]").empty());            // unterminated
        CHECK(highlyGenericScript("const omniHighly = \"ab\nc\";", "[]").empty());       // not one line
    }

    if (argc >= 2) {
        std::ifstream in(argv[1], std::ios::binary);
        std::stringstream buffer; buffer << in.rdbuf();
        const std::string generic = buffer.str();
        CHECK(!generic.empty());
        const std::string lite = highlyGenericScript(generic, "[]");
        CHECK(!lite.empty());
        CHECK(lite.size() * 20 < generic.size());   // far smaller than the generic script it stands in for
        std::printf("subframe generic: %zu B from a %zu B always-generic.js\n", lite.size(), generic.size());
        if (argc >= 3) std::ofstream(argv[2], std::ios::binary) << lite;
    }

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
