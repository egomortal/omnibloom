// OMNI_QUICK_ACTIONS_V1 host test: g++ -std=c++20 -I<entry> test_quick_actions.cpp <entry>/OmniPng.cpp -lpng -o t && ./t <scratch dir>
// Checks the pure header (host -> name, stamp, mkdir -p, unique path) and writes a PNG with the title's own
// omniWritePng (premultiplied BGRA -> RGB over white) for an outside decode check.
#include "OmniQuickActions.h"
#include "OmniPng.h"
#include <cstdio>
#include <cstdlib>
#include <set>
#include <vector>

static int fails = 0;
#define CHECK(c) do { if (!(c)) { ++fails; fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)
static void eq(const std::string& a, const std::string& b, int line)
{
    if (a != b) { ++fails; fprintf(stderr, "FAIL line %d: '%s' != '%s'\n", line, a.c_str(), b.c_str()); }
}
#define EQ(a, b) eq(a, b, __LINE__)

int main(int argc, char** argv)
{
    using namespace OmniQuickActions;
    EQ(hostForFile("https://www.Example.com/a/b?q=1"), "example.com");
    EQ(hostForFile("https://user:pw@sub.example.co.uk:8443/x"), "sub.example.co.uk");
    EQ(hostForFile("http://127.0.0.1:9000/downloads#url=x"), "127.0.0.1");
    EQ(hostForFile("http://[::1]:80/"), "1");   // ':' -> '-', leading '-' trimmed
    EQ(hostForFile("about:blank"), "page");
    EQ(hostForFile("data:text/html,<b>x</b>"), "page");
    EQ(hostForFile(""), "page");
    EQ(hostForFile("https://xn--bcher-kva.example/"), "xn--bcher-kva.example");
    EQ(hostForFile("https://a_b c/../x"), "a-b-c");
    EQ(hostForFile("https://../../etc/passwd"), "page");   // only "..": no path separators, no dot names
    CHECK(hostForFile("https://" + std::string(200, 'a') + ".com/").size() == 64);
    CHECK(hostForFile("https://ex/ample").find('/') == std::string::npos);

    struct tm t {};
    t.tm_year = 126; t.tm_mon = 10; t.tm_mday = 16; t.tm_hour = 9; t.tm_min = 5; t.tm_sec = 7;
    EQ(stamp(t), "20261116-090507");
    EQ(fileName("example.com", "20261116-090507"), "example.com-20261116-090507.png");
    EQ(fileName("example.com", "20261116-090507", 3), "example.com-20261116-090507-3.png");
    EQ(std::string(kShotDir), "/data/omni/downloads/media-worker/Saved/Screenshots");

    std::set<std::string> taken = { "/d/h-s.png", "/d/h-s-2.png" };
    EQ(uniquePath("/d", "h", "s", [&](const std::string& p) { return taken.count(p) > 0; }), "/d/h-s-3.png");
    EQ(uniquePath("/d", "h", "s", [](const std::string&) { return true; }), "");

    const std::string base = argc > 1 ? argv[1] : "/tmp/omni-qa-test";
    const std::string dir = base + "/downloads/media-worker/Saved/Screenshots";
    CHECK(makeDirs(dir));
    CHECK(makeDirs(dir));            // existing: still true
    CHECK(isDir(dir));
    CHECK(!makeDirs(""));
    {   // a file in the way
        const std::string f = base + "/afile";
        FILE* fp = fopen(f.c_str(), "w"); if (fp) fclose(fp);
        CHECK(!makeDirs(f + "/sub"));
    }
    const std::string p1 = uniquePath(dir, "example.com", "20261116-090507");
    EQ(p1, dir + "/example.com-20261116-090507.png");

    // 7x5 premultiplied BGRA: opaque red, opaque green, opaque blue, transparent (-> white), half-alpha black (-> 127).
    const int w = 7, h = 5, stride = w * 4 + 4;   // padded rows: the stride is honoured
    std::vector<unsigned char> px(size_t(stride) * h, 0xEE);
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            unsigned char* d = &px[size_t(y) * stride + x * 4];
            const int k = (x + y) % 5;
            const unsigned char v[5][4] = { { 0, 0, 255, 255 }, { 0, 255, 0, 255 }, { 255, 0, 0, 255 }, { 0, 0, 0, 0 }, { 0, 0, 0, 128 } };
            for (int c = 0; c < 4; ++c) d[c] = v[k][c];
        }
    CHECK(omniWritePng(p1.c_str(), px.data(), w, h, stride));
    CHECK(fileExists(p1));
    EQ(uniquePath(dir, "example.com", "20261116-090507"), dir + "/example.com-20261116-090507-2.png");
    printf("%s\n", p1.c_str());
    if (fails) { fprintf(stderr, "%d failure(s)\n", fails); return 1; }
    fprintf(stderr, "all quick-actions checks passed\n");
    return 0;
}
