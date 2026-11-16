// OMNI_SAVE_IMAGE_V1: host tests for engine/entry/OmniSaveImage.h (written by apply_save_image.py), together with the
// real OmniMediaSection::validLink the shell feeds it.
//   g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry test_save_image.cpp -o t && ./t
#include "OmniSaveImage.h"
#include "OmniMediaSection.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

namespace OSVI = OmniSaveImage;

static OSVI::Route routeOf(const std::string& url, bool priv = false, bool on = true, bool dlTab = false, bool test = false)
{
    OSVI::Where w;
    w.privateTab = priv; w.downloadsOn = on; w.downloadsTab = dlTab; w.testMode = test;
    w.validLink = OmniMediaSection::validLink(url);
    return OSVI::route(url, w);
}

int main()
{
    using R = OSVI::Route;
    // route: the file-downloads rule
    CHECK(routeOf("https://example.com/a.png") == R::Downloads);
    CHECK(routeOf("http://example.com/x?id=3") == R::Downloads);
    CHECK(routeOf("https://example.com/a.png", true) == R::WebKit);          // private tab
    CHECK(routeOf("https://example.com/a.png", false, false) == R::WebKit);  // Media downloads off
    CHECK(routeOf("https://example.com/a.png", false, true, true) == R::WebKit);         // the Downloads tab
    CHECK(routeOf("https://example.com/a.png", false, true, false, true) == R::WebKit);  // self-test
    CHECK(routeOf("data:image/png;base64,iVBORw0KGgo=") == R::WebKit);
    CHECK(routeOf("blob:https://example.com/1234") == R::WebKit);
    CHECK(routeOf("ftp://example.com/a.png") == R::WebKit);
    CHECK(routeOf("https://user:pw@example.com/a.png") == R::WebKit);        // credentials
    CHECK(routeOf("https://example.com/a b.png") == R::WebKit);              // raw space
    CHECK(routeOf("") == R::WebKit);
    CHECK(routeOf("https://" + std::string(4100, 'a')) == R::WebKit);

    // offered
    CHECK(OSVI::offered("https://example.com/a.png"));
    CHECK(OSVI::offered("data:image/png;base64,AA=="));
    CHECK(!OSVI::offered("blob:https://example.com/1"));
    CHECK(!OSVI::offered("BLOB:https://example.com/1"));
    CHECK(!OSVI::offered(""));
    CHECK(OSVI::offered("blo"));

    // file names
    CHECK(OSVI::fileName("https://example.com/img/cat.jpg", "image") == "cat.jpg");
    CHECK(OSVI::fileName("https://example.com/img/cat.jpg?w=300#x", "image") == "cat.jpg");
    CHECK(OSVI::fileName("https://example.com/img/my%20cat.png", "image") == "my cat.png");
    CHECK(OSVI::fileName("https://example.com/a%2Fb.png", "image") == "a_b.png");        // decoded slash stays inside
    CHECK(OSVI::fileName("https://example.com/caf%C3%A9.png", "image") == "caf\xC3\xA9.png");
    CHECK(OSVI::fileName("https://example.com/", "file") == "example.com");
    CHECK(OSVI::fileName("https://example.com", "file") == "example.com");
    CHECK(OSVI::fileName("https://example.com:8080?q=1", "file") == "example.com_8080");
    CHECK(OSVI::fileName("https://example.com/dir/", "file") == "example.com");
    CHECK(OSVI::fileName("https://example.com/..%2e", "image") == "example.com");      // dots only -> host
    CHECK(OSVI::fileName("https://example.com/%00%0a.png", "image") == "__.png");
    CHECK(OSVI::fileName("https://example.com/%zz.png", "image") == "%zz.png");        // bad escapes kept
    CHECK(OSVI::fileName("https://example.com/a%", "image") == "a%");
    CHECK(OSVI::fileName("https://example.com/a%4", "image") == "a%4");
    CHECK(OSVI::fileName("", "image") == "image");
    CHECK(OSVI::fileName("https://example.com/download?id=7", "file") == "download");
    {
        const std::string longName(200, 'x');
        CHECK(OSVI::fileName("https://example.com/" + longName + ".png", "image").size() == 120);
    }

    // shown (notice) names
    CHECK(OSVI::shown("cat.jpg") == "cat.jpg");
    CHECK(OSVI::shown(std::string(60, 'a')) == std::string(60, 'a'));
    {
        const std::string s = OSVI::shown(std::string(30, 'a') + std::string(40, 'b'));
        CHECK(s == std::string(28, 'a') + "..." + std::string(28, 'b'));
    }
    {
        std::string u;   // 2-byte characters: never split
        for (int i = 0; i < 40; ++i) u += "\xC3\xA9";
        const std::string s = OSVI::shown(u);
        CHECK(s.size() <= 28 + 3 + 28);
        bool whole = true;
        const size_t dots = s.find("...");
        CHECK(dots != std::string::npos);
        for (size_t i = 0; i < s.size(); ++i) {
            const unsigned char c = s[i];
            if (c == 0xC3 && (i + 1 >= s.size() || (static_cast<unsigned char>(s[i + 1]) & 0xC0) != 0x80)) whole = false;
            if ((c & 0xC0) == 0x80 && (i == 0 || static_cast<unsigned char>(s[i - 1]) != 0xC3)) whole = false;
        }
        CHECK(whole);
    }

    // duplicate guard (only accepted hand-overs are noted; wraps with SDL_GetTicks)
    {
        OSVI::Recent r;
        CHECK(!r.repeat("https://a/x.png", 0));
        r.note("https://a/x.png", 1000);
        CHECK(r.repeat("https://a/x.png", 1000));
        CHECK(r.repeat("https://a/x.png", 3999));
        CHECK(!r.repeat("https://a/x.png", 4000));
        CHECK(!r.repeat("https://a/y.png", 1500));
        r.note("https://a/z.png", 0xFFFFFF00u);
        CHECK(r.repeat("https://a/z.png", 0x00000100u));   // 512 ms later, across the wrap
        CHECK(!r.repeat("https://a/z.png", 0x00000C00u));  // 3328 ms later
    }

    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
