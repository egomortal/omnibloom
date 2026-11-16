// OMNI_YT_AUTOCONTINUE_V1: host tests of the pure part (OmniYtAutoContinue.h).
// g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry test_yt_autocontinue.cpp -o t && ./t [script.js]
// With an argument, the page script is written there (node --check / test_yt_autocontinue_js.mjs can read it).
#include "OmniYtAutoContinue.h"
#include <cstdio>
#include <cstring>

namespace OYAC = OmniYtAutoContinue;
static int fails = 0;
#define CHECK(c) do { if (!(c)) { ++fails; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

int main(int argc, char** argv)
{
    // settings file
    CHECK(!OYAC::parse(""));
    CHECK(OYAC::parse("on"));
    CHECK(OYAC::parse(" ON\r\n"));
    CHECK(!OYAC::parse("off\n"));
    CHECK(!OYAC::parse("onn"));
    CHECK(!OYAC::parse("1"));
    CHECK(OYAC::parse(OYAC::serialize(true)));
    CHECK(!OYAC::parse(OYAC::serialize(false)));

    // hosts / URLs
    CHECK(OYAC::youtubeHost("youtube.com"));
    CHECK(OYAC::youtubeHost("www.youtube.com"));
    CHECK(OYAC::youtubeHost("Music.YouTube.com."));
    CHECK(OYAC::youtubeHost("m.youtube.com"));
    CHECK(!OYAC::youtubeHost("notyoutube.com"));
    CHECK(!OYAC::youtubeHost("youtube.com.evil.net"));
    CHECK(!OYAC::youtubeHost("youtube-nocookie.com"));
    CHECK(!OYAC::youtubeHost("www.youtube-nocookie.com"));
    CHECK(OYAC::eligible("https://www.youtube.com/watch?v=abc"));
    CHECK(OYAC::eligible("https://music.youtube.com/watch?v=abc&list=x"));
    CHECK(OYAC::eligible("http://youtube.com"));
    CHECK(OYAC::eligible("https://www.youtube.com/tvshows"));          // not TV mode
    CHECK(OYAC::eligible("https://www.youtube.com/watch?next=/tv"));
    CHECK(!OYAC::eligible("https://www.youtube.com/tv"));
    CHECK(!OYAC::eligible("https://www.youtube.com/tv#/watch?v=abc"));
    CHECK(!OYAC::eligible("https://www.youtube.com/tv/"));
    CHECK(!OYAC::eligible("https://www.youtube.com/tv?env=1"));
    CHECK(OYAC::where("https://www.youtube.com/tv").youtube);
    CHECK(OYAC::where("https://www.youtube.com/tv").tv);
    CHECK(!OYAC::eligible("https://www.youtube-nocookie.com/embed/x"));
    CHECK(!OYAC::eligible("https://example.com/?u=https://www.youtube.com/watch"));
    CHECK(!OYAC::eligible("https://user@evil.net/www.youtube.com"));
    CHECK(OYAC::eligible("https://www.youtube.com:443/watch?v=1"));
    CHECK(!OYAC::eligible("omni://start"));
    CHECK(!OYAC::eligible("about:blank"));
    CHECK(!OYAC::eligible(""));

    // answers
    CHECK(OYAC::parseAnswer("yt") == OYAC::kYouTube);
    CHECK(OYAC::parseAnswer("music") == OYAC::kMusic);
    CHECK(OYAC::parseAnswer("") == OYAC::kNone);
    CHECK(OYAC::parseAnswer("yt ") == OYAC::kNone);

    // timing (wrap-safe)
    CHECK(OYAC::reached(10, 10));
    CHECK(!OYAC::reached(9, 10));
    CHECK(OYAC::reached(5u, 0xfffffff0u));

    // texts
    CHECK(OYAC::rowValue(false, true) == "Off");
    CHECK(OYAC::rowValue(true, false) == "On");
    CHECK(OYAC::rowValue(true, true) == "On (held: sleep timer)");
    CHECK(OYAC::rowDetail(0).find("this session") == std::string::npos);
    CHECK(OYAC::rowDetail(1).find("1 time this session") != std::string::npos);
    CHECK(OYAC::rowDetail(3).find("3 times this session") != std::string::npos);
    CHECK(OYAC::toggleNotice(true, true).find("not saved") != std::string::npos);
    CHECK(OYAC::toggleNotice(false, false).find("not saved") == std::string::npos);
    CHECK(OYAC::kSiteRowId == 787);
    CHECK(std::strstr(OYAC::kScript, "yt-confirm-dialog-renderer") && std::strstr(OYAC::kScript, "ytmusic-you-there-renderer"));

    if (argc > 1) {
        FILE* f = std::fopen(argv[1], "wb");
        if (!f) { std::printf("cannot write %s\n", argv[1]); return 2; }
        std::fputs(OYAC::kScript, f);
        std::fclose(f);
    }
    std::printf(fails ? "%d FAILED\n" : "all passed\n", fails);
    return fails ? 1 : 0;
}
