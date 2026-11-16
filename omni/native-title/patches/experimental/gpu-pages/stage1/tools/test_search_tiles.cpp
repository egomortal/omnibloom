// OMNI_SEARCH_TILES_V1 host test for engine/entry/OmniSearchTiles.h (written by apply_search_tiles.py).
// g++ -std=c++17 -Wall -Wextra -Werror -I <tree>/engine/entry test_search_tiles.cpp -o t && ./t
#include "OmniSearchTiles.h"
#include <cstdio>
#include <string>
#include <unistd.h>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniSearchTiles;

struct V { long long time; std::string url, title; };

static std::string go(const std::string& input, const std::vector<Engine>& e = builtins())
{
    Match m;
    return match(input, e, m) ? m.url : std::string("-");
}

int main()
{
    // encoding: UTF-8 bytes, space %20, reserved characters escaped, unreserved kept
    CHECK(encode("lofi beats") == "lofi%20beats");
    CHECK(encode("a+b&c=d/e?f#g%h") == "a%2Bb%26c%3Dd%2Fe%3Ff%23g%25h");
    CHECK(encode("-_.~AZaz09") == "-_.~AZaz09");
    CHECK(encode("caf\xC3\xA9") == "caf%C3%A9");
    CHECK(encode("\xE6\x97\xA5\xE6\x9C\xAC") == "%E6%97%A5%E6%9C%AC");
    CHECK(encode("\"<>'") == "%22%3C%3E%27");
    CHECK(encode("") == "");

    // matching
    CHECK(go("yt lofi beats") == "https://www.youtube.com/results?search_query=lofi%20beats");
    CHECK(go("  yt   lofi beats  ") == "https://www.youtube.com/results?search_query=lofi%20beats");
    CHECK(go("YT lofi") == "https://www.youtube.com/results?search_query=lofi");
    CHECK(go("w C++ (language)") == "https://en.wikipedia.org/w/index.php?search=C%2B%2B%20%28language%29");
    CHECK(go("r ps5 homebrew") == "https://www.reddit.com/search/?q=ps5%20homebrew");
    CHECK(go("g a&b") == "https://www.google.com/search?q=a%26b");
    CHECK(go("d privacy") == "https://duckduckgo.com/?q=privacy");
    CHECK(go("a usb cable") == "https://www.amazon.com/s?k=usb%20cable");
    CHECK(go("m caf\xC3\xA9 paris") == "https://www.google.com/maps/search/?api=1&query=caf%C3%A9%20paris");
    CHECK(go("yt") == "-");                 // no query
    CHECK(go("yt ") == "-");
    CHECK(go("yt\t ") == "-");
    CHECK(go("ytlofi") == "-");             // not followed by a space
    CHECK(go("youtube lofi") == "-");       // not a known prefix
    CHECK(go("y lofi") == "-");
    CHECK(go("lofi yt") == "-");
    CHECK(go("example.com") == "-");
    CHECK(go("https://yt.com/x y") == "-"); // an address
    CHECK(go("yt://x y") == "-");
    CHECK(go("about:blank x") == "-");
    CHECK(go("javascript:alert(1) x") == "-");
    CHECK(go("g how does https:// work") == "https://www.google.com/search?q=how%20does%20https%3A%2F%2F%20work");
    CHECK(go("") == "-");
    {
        Match m;
        CHECK(match("yt lofi beats", builtins(), m));
        CHECK(m.name == "YouTube" && m.query == "lofi beats");
    }
    CHECK(looksLikeUrl("example.com") && looksLikeUrl("localhost:8080") && looksLikeUrl("HTTPS://x") && looksLikeUrl("data:text/html,x"));
    CHECK(!looksLikeUrl("yt lofi beats") && !looksLikeUrl("hello") && !looksLikeUrl("what is 3.5 kg"));

    // template validation
    CHECK(validTemplate("https://www.youtube.com/results?search_query=%s"));
    CHECK(validTemplate("https://example.com/s/%s"));
    CHECK(validTemplate("https://example.com:8443/?q=%s&lang=en%2Dus"));
    CHECK(validTemplate("HTTPS://Example.COM/?q=%s"));
    for (const auto& e : builtins()) CHECK(validTemplate(e.tmpl) && validPrefix(e.prefix));
    CHECK(!validTemplate("http://example.com/?q=%s"));            // https only
    CHECK(!validTemplate("javascript:alert(%s)"));
    CHECK(!validTemplate("https://example.com/?q="));             // no %s
    CHECK(!validTemplate("https://example.com"));
    CHECK(!validTemplate("https://%s.example.com/"));             // %s in the host
    CHECK(!validTemplate("https://user:pw@example.com/?q=%s"));   // credentials
    CHECK(!validTemplate("https://example.com/?q=%s&x=%zz"));     // stray %
    CHECK(!validTemplate("https://example.com/?q=%s%"));
    CHECK(!validTemplate("https://exa mple.com/?q=%s"));
    CHECK(!validTemplate("https://example.com/?q=%s\"onload"));
    CHECK(!validTemplate("https://localhost/?q=%s"));             // no dot: not a public host
    CHECK(!validTemplate("https://.example.com/?q=%s"));
    CHECK(!validTemplate("https://ex_ample.com/?q=%s"));
    CHECK(!validTemplate("https://example.com:/?q=%s"));
    CHECK(!validTemplate("https://example.com:80a/?q=%s"));
    CHECK(!validTemplate("https://ex\xC3\xA9.com/?q=%s"));         // non-ASCII
    CHECK(!validTemplate("https://example.com/" + std::string(1100, 'a') + "%s"));
    CHECK(validPrefix("!yt") && validPrefix("gh") && validPrefix("w2"));
    CHECK(!validPrefix("") && !validPrefix("Y") && !validPrefix("a b") && !validPrefix("a.b") && !validPrefix(std::string(17, 'a')));

    // file parsing
    {
        int bad = -1;
        auto list = parseFile("\xEF\xBB\xBF# my shortcuts\r\n"
                              "gh\thttps://github.com/search?q=%s\r\n"
                              "\r\n"
                              "YT\thttps://www.youtube.com/results?search_query=%s\tTube\r\n"
                              "yt\thttps://example.com/?q=%s\r\n"           // duplicate prefix
                              "bad\thttp://example.com/?q=%s\r\n"           // not https
                              "x y\thttps://example.com/?q=%s\r\n"          // invalid prefix
                              "nourl\r\n"
                              "w   https://en.wikipedia.org/w/index.php?search=%s\n"
                              "so\thttps://stackoverflow.com/search?q=%s", &bad);
        CHECK(list.size() == 4);
        CHECK(bad == 4);
        CHECK(list.size() == 4 && list[0].prefix == "gh" && list[0].name == "github.com");
        CHECK(list.size() == 4 && list[1].prefix == "yt" && list[1].name == "Tube");
        CHECK(list.size() == 4 && list[2].prefix == "w" && list[2].name == "Wikipedia");   // known host: built-in name
        CHECK(list.size() == 4 && list[3].prefix == "so" && list[3].name == "stackoverflow.com");
        CHECK(go("gh webkit", list) == "https://github.com/search?q=webkit");
        CHECK(go("g webkit", list) == "-");      // not in the user's list
        std::string many;
        for (int i = 0; i < 40; ++i) many += "p" + std::to_string(i) + "\thttps://example.com/?q=%s\n";
        auto capped = parseFile(many, &bad);
        CHECK(capped.size() == kMaxEngines && bad == 10);
        CHECK(parseFile("", &bad).empty() && bad == 0);
        CHECK(parseFile("# only comments\n", &bad).empty());
        auto two = parseFile("t\thttps://example.com/?a=%s&b=%s\n");
        CHECK(go("t x y", two) == "https://example.com/?a=x%20y&b=x%20y");
    }

    // the store: built-ins when the file is missing; the file when present; re-read when it changes
    {
        char path[] = "/tmp/omni-st-XXXXXX";
        const int fd = mkstemp(path);
        CHECK(fd >= 0);
        close(fd);
        unlink(path);
        Store st;
        CHECK(st.get(path).size() == builtins().size());
        FILE* f = fopen(path, "w");
        fputs("gh\thttps://github.com/search?q=%s\n", f);
        fclose(f);
        CHECK(st.get(path).size() == 1 && st.get(path)[0].prefix == "gh");
        f = fopen(path, "w");
        fputs("gh\thttps://github.com/search?q=%s\nso\thttps://stackoverflow.com/search?q=%s\nbad\n", f);
        fclose(f);
        CHECK(st.get(path).size() == 2 && st.rejected() == 1);   // size changed: re-read
        f = fopen(path, "w");
        fclose(f);
        CHECK(st.get(path).empty());                             // empty file: no shortcuts
        unlink(path);
        CHECK(st.get(path).size() == builtins().size());
    }

    // hosts
    CHECK(hostOf("https://www.YouTube.com/watch?v=1") == "youtube.com");
    CHECK(hostOf("http://user:pw@Example.com:8080/x") == "example.com");
    CHECK(hostOf("https://www.com/") == "www.com");
    CHECK(hostOf("https://example.com./") == "example.com");
    CHECK(hostOf("https://[::1]:8080/") == "[::1]");
    CHECK(hostOf("ftp://example.com/") == "" && hostOf("data:text/html,x") == "" && hostOf("example.com") == "");
    CHECK(localHost("127.0.0.1") && localHost("localhost") && localHost("[::1]") && localHost("app.localhost") && !localHost("example.com"));
    {
        bool root = false;
        CHECK(siteRoot("https://www.Example.com/a/b?c", &root) == "https://www.example.com/" && !root);
        CHECK(siteRoot("https://example.com", &root) == "https://example.com/" && root);
        CHECK(siteRoot("https://example.com/", &root) == "https://example.com/" && root);
        CHECK(siteRoot("http://u@example.com:81/?q", &root) == "http://example.com:81/" && !root);
    }

    // most visited
    {
        const long long now = 1800000000, day = 86400;
        std::vector<V> h = {
            { now - 40 * day, "https://old.example/", "Old" },                    // outside 30 days
            { now - 40 * day, "https://old.example/a", "Old" },
            { now - 40 * day, "https://old.example/b", "Old" },
            { now - 5 * day, "https://www.youtube.com/", "YouTube" },
            { now - 4 * day, "https://www.youtube.com/watch?v=1", "Some video" },
            { now - 3 * day, "https://m.youtube.com/watch?v=2", "Other video" },  // other host
            { now - 2 * day, "https://www.youtube.com/watch?v=3", "Video 3" },
            { now - 6 * day, "https://news.example/a", "Story A" },
            { now - 1 * day, "https://news.example/b", "Story B" },
            { now - 1 * day, "http://127.0.0.1:8123/downloads", "Downloads" },   // local
            { now - 1 * day, "https://saved.example/x", "Saved" },               // in shortcuts
            { now - 1 * day, "https://saved.example/y", "Saved" },
            { now - 1 * day, "https://saved.example/z", "Saved" },
            { now - 7 * day, "https://wiki.example/", "Wiki" },
            { now - 7 * day, "https://wiki.example/x", "Wiki X" },
            { now - 8 * day, "https://one.example/p", "One" },
            { now - 1 * day, "https://two.example/p", "Two" },
            { 0, "https://untimed.example/", "Untimed" },                        // no time while others have one
            { now - 1, "data:text/html,x", "x" },
        };
        auto s = mostVisited(h, now, { "https://saved.example/", "news.example" }, 19);
        CHECK(s.size() == 5);
        if (s.size() == 5) {
            CHECK(s[0].host == "youtube.com" && s[0].visits == 3 && s[0].url == "https://www.youtube.com/" && s[0].title == "YouTube");
            CHECK(s[1].host == "wiki.example" && s[1].visits == 2 && s[1].title == "Wiki");
            CHECK(s[2].host == "two.example" && s[2].title == "two.example");   // 1 visit, newer than one.example
            CHECK(s[3].host == "m.youtube.com");
            CHECK(s[4].host == "one.example");
        }
        CHECK(mostVisited(h, now, {}, 2).size() == 2);
        CHECK(mostVisited(h, now, {}, 19).size() == 7);   // news.example and saved.example back in
        CHECK(mostVisited(std::vector<V>(), now, {}, 19).empty());
        // no timestamps at all: every visit counts
        std::vector<V> old = { { 0, "https://a.example/", "A" }, { 0, "https://b.example/1", "B" }, { 0, "https://b.example/2", "B" } };
        auto o = mostVisited(old, now, {}, 19);
        CHECK(o.size() == 2 && o[0].host == "b.example" && o[1].title == "A");
    }

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
