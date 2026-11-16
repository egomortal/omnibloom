// OMNI_YOUTUBE_TV_V1 host test for engine/entry/OmniYoutubeTv.h (written by apply_youtube_tv.py).
// g++ -std=c++17 -Wall -Wextra -Werror -I <tree>/engine/entry test_youtube_tv.cpp -o t && ./t
#include "OmniYoutubeTv.h"
#include <cstdio>
#include <cstring>
#include <string>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define EQ(a, b) do { ++checks; const std::string x_ = (a), y_ = (b); if (x_ != y_) { ++fails; std::printf("FAIL %s:%d: %s\n  got  [%s]\n  want [%s]\n", __FILE__, __LINE__, #a, x_.c_str(), y_.c_str()); } } while (0)

using namespace OmniYoutubeTv;
static const std::string kTv = "https://www.youtube.com/tv";

static void urls()
{
    // home pages
    EQ(tvUrlFor("https://www.youtube.com/"), kTv);
    EQ(tvUrlFor("https://www.youtube.com"), kTv);
    EQ(tvUrlFor("http://youtube.com/"), kTv);
    EQ(tvUrlFor("https://m.youtube.com/?app=m"), kTv);
    EQ(tvUrlFor("HTTPS://WWW.YouTube.COM/"), kTv);
    EQ(tvUrlFor("https://www.youtube.com./"), kTv);
    EQ(tvUrlFor("https://www.youtube.com:443/#x"), kTv);
    // watch pages
    EQ(tvUrlFor("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), kTv + "#/watch?v=dQw4w9WgXcQ");
    EQ(tvUrlFor("https://www.youtube.com/watch?feature=share&v=dQw4w9WgXcQ&pp=ygU"), kTv + "#/watch?v=dQw4w9WgXcQ");
    EQ(tvUrlFor("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=1m30s"), kTv + "#/watch?v=dQw4w9WgXcQ&t=90");
    EQ(tvUrlFor("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42"), kTv + "#/watch?v=dQw4w9WgXcQ&t=42");
    EQ(tvUrlFor("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s"), kTv + "#/watch?v=dQw4w9WgXcQ");
    EQ(tvUrlFor("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=junk"), kTv + "#/watch?v=dQw4w9WgXcQ");
    EQ(tvUrlFor("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG"),
       kTv + "#/watch?v=dQw4w9WgXcQ&list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG");
    EQ(tvUrlFor("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=bad%20list"), kTv + "#/watch?v=dQw4w9WgXcQ");
    EQ(tvUrlFor("https://www.youtube.com/watch?v=dQw4w9WgXcQ#comments"), kTv + "#/watch?v=dQw4w9WgXcQ");
    EQ(tvUrlFor("https://www.youtube.com/watch/?v=dQw4w9WgXcQ"), kTv + "#/watch?v=dQw4w9WgXcQ");
    EQ(tvUrlFor("https://www.youtube.com/watch?v=short"), "");          // not a video id: leave the page alone
    EQ(tvUrlFor("https://www.youtube.com/watch?v=dQw4w9WgXcQ1"), "");
    EQ(tvUrlFor("https://www.youtube.com/watch?v=dQw4w9WgX%3D"), "");
    EQ(tvUrlFor("https://www.youtube.com/watch"), "");
    // shorts, live, youtu.be
    EQ(tvUrlFor("https://www.youtube.com/shorts/abcdefghijk"), kTv + "#/watch?v=abcdefghijk");
    EQ(tvUrlFor("https://www.youtube.com/shorts/abcdefghijk/?feature=share"), kTv + "#/watch?v=abcdefghijk");
    EQ(tvUrlFor("https://www.youtube.com/live/abc-efg_ijk?si=x"), kTv + "#/watch?v=abc-efg_ijk");
    EQ(tvUrlFor("https://youtu.be/dQw4w9WgXcQ?t=75"), kTv + "#/watch?v=dQw4w9WgXcQ&t=75");
    EQ(tvUrlFor("https://youtu.be/dQw4w9WgXcQ?si=abc&t=1h0m5s"), kTv + "#/watch?v=dQw4w9WgXcQ&t=3605");
    EQ(tvUrlFor("https://youtu.be/"), "");
    EQ(tvUrlFor("https://youtu.be/notanid"), "");
    // other YouTube pages open as usual
    EQ(tvUrlFor("https://www.youtube.com/results?search_query=cats"), "");
    EQ(tvUrlFor("https://www.youtube.com/@channel"), "");
    EQ(tvUrlFor("https://www.youtube.com/feed/subscriptions"), "");
    EQ(tvUrlFor("https://www.youtube.com/embed/dQw4w9WgXcQ"), "");
    EQ(tvUrlFor("https://www.youtube.com/watchlater"), "");
    // the TV app itself: never redirected (no loop)
    EQ(tvUrlFor("https://www.youtube.com/tv"), "");
    EQ(tvUrlFor("https://www.youtube.com/tv#/watch?v=dQw4w9WgXcQ"), "");
    EQ(tvUrlFor("https://www.youtube.com/tv/"), "");
    EQ(tvUrlFor(kTv + "#/watch?v=dQw4w9WgXcQ&t=90"), "");
    // other sites, look-alikes, other schemes
    EQ(tvUrlFor("https://music.youtube.com/watch?v=dQw4w9WgXcQ"), "");
    EQ(tvUrlFor("https://tv.youtube.com/"), "");
    EQ(tvUrlFor("https://notyoutube.com/watch?v=dQw4w9WgXcQ"), "");
    EQ(tvUrlFor("https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ"), "");
    EQ(tvUrlFor("https://evil.example/?u=https://www.youtube.com/"), "");
    EQ(tvUrlFor("https://www.youtube.com@evil.example/"), "");
    EQ(tvUrlFor("https://user@www.youtube.com/watch?v=dQw4w9WgXcQ"), kTv + "#/watch?v=dQw4w9WgXcQ");
    EQ(tvUrlFor("ftp://www.youtube.com/"), "");
    EQ(tvUrlFor("javascript:alert(1)//www.youtube.com/"), "");
    EQ(tvUrlFor("about:blank"), "");
    EQ(tvUrlFor(""), "");
    EQ(tvUrlFor("www.youtube.com/watch?v=dQw4w9WgXcQ"), "");   // the shell always hands full URLs
    // every mapped URL is the TV app (so the TV user agent applies to it and it is not mapped again)
    for (const char* u : { "https://www.youtube.com/", "https://youtu.be/dQw4w9WgXcQ?t=5", "https://www.youtube.com/shorts/abcdefghijk" }) {
        CHECK(isTvUrl(tvUrlFor(u)));
        EQ(tvUrlFor(tvUrlFor(u)), "");
    }
    // isTvUrl
    CHECK(isTvUrl("https://www.youtube.com/tv"));
    CHECK(isTvUrl("https://www.youtube.com/tv#/browse?c=FEtopics"));
    CHECK(isTvUrl("https://www.youtube.com/tv?env_forceFullAnimation=1#/"));
    CHECK(isTvUrl("https://youtube.com/tv/"));
    CHECK(isTvUrl("http://m.youtube.com/tv/x"));
    CHECK(!isTvUrl("https://www.youtube.com/tvshows"));
    CHECK(!isTvUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ#/tv"));
    CHECK(!isTvUrl("https://tv.youtube.com/"));
    CHECK(!isTvUrl("https://example.com/tv"));
    CHECK(!isTvUrl("https://www.youtube.com/"));
    CHECK(!isTvUrl(""));
}

static void times()
{
    CHECK(startSeconds("90") == 90); CHECK(startSeconds("90s") == 90); CHECK(startSeconds("1m30s") == 90);
    CHECK(startSeconds("1h2m3s") == 3723); CHECK(startSeconds("2m") == 120); CHECK(startSeconds("0") == 0);
    CHECK(startSeconds("") == -1); CHECK(startSeconds("s") == -1); CHECK(startSeconds("1m30") == -1);
    CHECK(startSeconds("1x") == -1); CHECK(startSeconds("-5") == -1); CHECK(startSeconds("99999999999") == -1);
    CHECK(startSeconds("25h") == -1); CHECK(startSeconds("1h1h") == 7200);
}

static void userAgents()
{
    const std::string safari = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15";
    EQ(withOmniToken(safari, "0.5.3", true), safari + " Omni/0.5.3");
    EQ(withOmniToken(safari, "0.5.3", false), safari);
    EQ(withOmniToken(safari + " Omni/0.5.2", "0.5.3", true), safari + " Omni/0.5.2");   // never twice
    EQ(withOmniToken(safari, "", true), safari);
    EQ(withOmniToken(safari, "0.5 3", true), safari);
    EQ(withOmniToken(safari, "1.0.0-rc1_b", true), safari + " Omni/1.0.0-rc1_b");
    EQ(withOmniToken(safari, std::string(33, '1'), true), safari);
    EQ(withOmniToken(safari, OMNI_UA_VERSION, true), safari + " Omni/" OMNI_UA_VERSION);
    CHECK(validVersion(OMNI_UA_VERSION));
    // the TV user agent: Cobalt form, names Omni, printable, a valid file line too
    std::string tv = tvUserAgent("0.5.3");
    CHECK(tv.rfind("Mozilla/5.0 (", 0) == 0);
    CHECK(tv.find(" Cobalt/") != std::string::npos);
    CHECK(tv.find("(unlike Gecko)") != std::string::npos);
    CHECK(tv.find("Starboard/") != std::string::npos);
    CHECK(tv.find("Omni_PS5_2020/0.5.3 (Sony, PS5, Wired)") != std::string::npos);
    CHECK(tv.find("Safari") == std::string::npos);   // a Safari token makes YouTube send the desktop site
    std::string line = tv + "\r\n";
    CHECK(cleanUaLine(line)); EQ(line, tv);
    // file lines
    std::string a = "  short \n"; CHECK(!cleanUaLine(a));
    std::string b = std::string(401, 'x'); CHECK(!cleanUaLine(b));
    std::string c = "Mozilla/5.0 (PS4; Leanback Shell) Gecko/20100101 Firefox/65.0 LeanbackShell/01.00.01.75 Sony PS4/ (PS4, , no, CH)\n";
    CHECK(cleanUaLine(c)); CHECK(c.back() == ')');
    std::string d = "Mozilla/5.0 \x01 control character inside"; CHECK(!cleanUaLine(d));
    std::string e = "Mozilla/5.0 (X11) caf\xc3\xa9 non-ASCII text"; CHECK(!cleanUaLine(e));
}

static void mode()
{
    CHECK(modeIsTv("tv")); CHECK(modeIsTv("tv\n")); CHECK(modeIsTv("  TV \r\n")); CHECK(modeIsTv("Tv"));
    CHECK(!modeIsTv("")); CHECK(!modeIsTv("normal\n")); CHECK(!modeIsTv("tvx")); CHECK(!modeIsTv("t v")); CHECK(!modeIsTv("1"));
}

static void keys()
{
    CHECK(std::strcmp(keyFor(Pad::Up).identifier, "Up") == 0 && keyFor(Pad::Up).keysym == 0xff52 && !keyFor(Pad::Up).text);
    CHECK(std::strcmp(keyFor(Pad::Down).identifier, "Down") == 0 && keyFor(Pad::Down).keysym == 0xff54);
    CHECK(std::strcmp(keyFor(Pad::Left).identifier, "Left") == 0 && keyFor(Pad::Left).keysym == 0xff51);
    CHECK(std::strcmp(keyFor(Pad::Right).identifier, "Right") == 0 && keyFor(Pad::Right).keysym == 0xff53);
    CHECK(std::strcmp(keyFor(Pad::Cross).identifier, "Enter") == 0 && keyFor(Pad::Cross).keysym == 0xff0d && std::strcmp(keyFor(Pad::Cross).text, "\r") == 0);
    CHECK(std::strcmp(keyFor(Pad::Circle).identifier, "U+001B") == 0 && keyFor(Pad::Circle).keysym == 0xff1b);
}

static void parts()
{
    UrlParts p;
    CHECK(splitUrl("https://User@WWW.Example.com:8080/a/b?x=1&y#frag?no", p));
    EQ(p.scheme, "https"); EQ(p.host, "www.example.com"); EQ(p.path, "/a/b"); EQ(p.query, "x=1&y"); EQ(p.fragment, "frag?no");
    CHECK(splitUrl("https://h#f?q", p)); EQ(p.path, ""); EQ(p.query, ""); EQ(p.fragment, "f?q");
    CHECK(!splitUrl("no scheme", p)); CHECK(!splitUrl("://x", p));
    EQ(queryValue("a=1&v=XYZ&v=2", "v"), "XYZ"); EQ(queryValue("vv=1", "v"), ""); EQ(queryValue("", "v"), ""); EQ(queryValue("v", "v"), "");
}

int main()
{
    urls(); times(); userAgents(); mode(); keys(); parts();
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "OK", checks, fails);
    return fails ? 1 : 0;
}
