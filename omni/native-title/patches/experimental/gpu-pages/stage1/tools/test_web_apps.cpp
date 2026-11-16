// OMNI_WEB_APPS_V1: host tests for OmniWebApps.h (the pure part of "Open as app" / Apps on the start page).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_web_apps.cpp -o t && ./t [script.js]
// With an argument it also writes the page script there (tools/test_web_apps_js.cjs runs it in node).
#include "OmniWebApps.h"
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace W = OmniWebApps;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static W::App app(const std::string& url, const std::string& name = "X") { W::App a; a.url = url; a.name = name; return a; }

int main(int argc, char** argv)
{
    // origins
    CHECK(W::originOf("https://www.YouTube.com/tv").text == "https://www.youtube.com");
    CHECK(W::originOf("https://example.com:443/x").text == "https://example.com");
    CHECK(W::originOf("http://example.com:8080").text == "http://example.com:8080");
    CHECK(W::originOf("http://[::1]:3000/a").text == "http://[::1]:3000");
    CHECK(!W::originOf("https://user@example.com/").ok);
    CHECK(!W::originOf("ftp://example.com/").ok);
    CHECK(!W::originOf("javascript:alert(1)").ok);
    CHECK(!W::originOf("https://exa mple.com/").ok);
    CHECK(!W::originOf("https://example.com:99999/").ok);
    CHECK(!W::originOf("https:///x").ok);
    CHECK(W::sameOrigin("https://www.youtube.com/tv", "https://WWW.youtube.com:443/watch?v=1"));
    CHECK(!W::sameOrigin("https://youtube.com/", "https://www.youtube.com/"));
    CHECK(!W::sameOrigin("http://twitch.tv/", "https://twitch.tv/"));
    CHECK(W::shownHost("https://www.YouTube.com/tv") == "youtube.com");
    CHECK(W::validWebUrl("https://app.plex.tv/desktop/#!/"));
    CHECK(!W::validWebUrl("https://a.com/\"onload"));
    CHECK(!W::validWebUrl("https://a.com/<x>"));
    CHECK(!W::validWebUrl("https://a.com/ x"));
    CHECK(!W::validWebUrl("data:image/png;base64,AAAA"));
    CHECK(!W::validWebUrl("https://a.com/" + std::string(3000, 'a')));
    CHECK(W::noFragment("https://a.com/x#y") == "https://a.com/x");

    // texts / colours
    CHECK(W::cleanText("  Hello\n\tWorld  ", 40) == "Hello World");
    CHECK(W::cleanText(std::string(50, 'a'), 40).size() == 40);
    CHECK(W::cleanText("\xC3\xA9\xC3\xA9\xC3\xA9", 5) == "\xC3\xA9\xC3\xA9");   // never half a character
    CHECK(W::validTheme("#FFF") == "#ffffff");
    CHECK(W::validTheme(" #12aB3c ") == "#12ab3c");
    CHECK(W::validTheme("red").empty() && W::validTheme("#12345").empty() && W::validTheme("#gggggg").empty());
    CHECK(W::validTheme("#fff;background:url(x)").empty());
    CHECK(W::inkFor("#ffffff") == "#111111" && W::inkFor("#000000") == "#ffffff" && W::inkFor("#ff0000") == "#ffffff");
    CHECK(W::letter("youTube") == "Y" && W::letter("") == "?" && W::letter("\xC3\xA9t\xC3\xA9") == "\xC3\xA9");
    CHECK(W::fallbackColour("a000000000001").size() == 7);

    // ids, add, caps
    std::vector<W::App> apps;
    CHECK(W::add(apps, app("https://www.youtube.com/tv", "YouTube")) == W::kAdded);
    CHECK(W::validId(apps[0].id));
    CHECK(W::add(apps, app("https://www.youtube.com/tv#x", "YouTube TV")) == W::kUpdated);   // same start address
    CHECK(apps.size() == 1 && apps[0].name == "YouTube TV");
    CHECK(W::add(apps, app("javascript:1")) == W::kInvalid);
    CHECK(W::add(apps, app("https://user@evil.com/")) == W::kInvalid);
    for (int i = 0; i < 20; ++i) W::add(apps, app("https://site" + std::to_string(i) + ".example/"));
    CHECK(apps.size() == W::kMaxApps);
    CHECK(W::add(apps, app("https://more.example/")) == W::kFull);
    CHECK(W::add(apps, app("https://site0.example/", "Renamed")) == W::kUpdated);         // updating works when full
    for (size_t i = 0; i < apps.size(); ++i) for (size_t j = i + 1; j < apps.size(); ++j) CHECK(apps[i].id != apps[j].id);
    CHECK(W::findOrigin(apps, "https://www.youtube.com/watch?v=1") == 0);
    CHECK(W::findUrl(apps, "https://www.youtube.com/tv#a") == 0);
    const std::string second = apps[1].id;
    CHECK(W::move(apps, second, -1) && apps[0].id == second);
    CHECK(!W::move(apps, second, -1));
    CHECK(W::remove(apps, second) && apps.size() == W::kMaxApps - 1 && W::find(apps, second) < 0);
    CHECK(!W::remove(apps, "a000000000000"));

    // apps.json round trip and hostile files
    std::vector<W::App> back;
    CHECK(W::parse(W::serialize(apps), back));
    CHECK(back.size() == apps.size());
    for (size_t i = 0; i < back.size() && i < apps.size(); ++i)
        CHECK(back[i].id == apps[i].id && back[i].url == apps[i].url && back[i].name == apps[i].name);
    CHECK(!W::parse("not json", back) && back.empty());
    CHECK(!W::parse(std::string(W::kMaxFile + 1, ' '), back));
    CHECK(W::parse("{\"v\":1}", back) && back.empty());
    CHECK(W::parse("{\"v\":1,\"apps\":[{\"id\":\"bad\",\"name\":\"A\\u0000B\",\"url\":\"https://a.com/\",\"icon\":\"javascript:x\",\"theme\":\"#ABC\",\"cookie\":\"s=1\"},"
                   "{\"id\":\"a000000000001\",\"url\":\"https://a.com/\"},{\"url\":\"file:///etc/passwd\"},{\"url\":\"https://b.com/\",\"name\":\"\"}, 7]}", back));
    CHECK(back.size() == 2);
    if (back.size() == 2) {
        CHECK(W::validId(back[0].id) && back[0].name == "A B" && back[0].icon.empty() && back[0].theme == "#aabbcc");
        CHECK(back[1].name == "b.com");
    }
    {
        std::string many = "{\"apps\":[";
        for (int i = 0; i < 30; ++i) many += (i ? "," : "") + std::string("{\"url\":\"https://s") + std::to_string(i) + ".example/\"}";
        CHECK(W::parse(many + "]}", back) && back.size() == W::kMaxApps);
    }
    CHECK(W::serialize(back).find("cookie") == std::string::npos);

    // the page's answer
    const std::string page = "https://www.youtube.com/watch?v=abc#t=1";
    W::Found f = W::fromPage("{\"title\":\"Video - YouTube\",\"fav\":\"https://www.youtube.com/favicon.ico\",\"tc\":\"#000\",\"name\":\"YouTube\","
                             "\"short\":\"YouTube\",\"start\":\"https://www.youtube.com/?feature=ytca\",\"icon\":\"https://www.youtube.com/img/192.png\",\"theme\":\"#ff0000\",\"m\":1}",
                             page, "tab");
    CHECK(f.ok && f.manifest && f.app.name == "YouTube" && f.app.url == "https://www.youtube.com/?feature=ytca");
    CHECK(f.app.icon == "https://www.youtube.com/img/192.png" && f.app.theme == "#ff0000");
    f = W::fromPage("{\"name\":\"A very long application name for TV screens\",\"short\":\"Short\",\"start\":\"https://evil.example/\",\"m\":1}", page, "tab");
    CHECK(f.ok && f.app.name == "Short" && f.app.url == "https://www.youtube.com/watch?v=abc");   // cross-origin start_url ignored
    f = W::fromPage("{\"start\":\"https://www.youtube.com.evil.example/\",\"title\":\"T\",\"tc\":\"#123\"}", page, "tab");
    CHECK(f.ok && !f.manifest && f.app.name == "T" && f.app.theme == "#112233" && f.app.url == "https://www.youtube.com/watch?v=abc");
    f = W::fromPage("", page, "Tab title");
    CHECK(f.ok && f.app.name == "Tab title" && f.app.icon.empty());
    f = W::fromPage("garbage{", page, "");
    CHECK(f.ok && f.app.name == "youtube.com");
    f = W::fromPage("{\"icon\":\"javascript:alert(1)\",\"fav\":\"https://x.com/f.png\"}", page, "");
    CHECK(f.ok && f.app.icon == "https://x.com/f.png");
    CHECK(!W::fromPage("{}", "omni://pages/start/", "").ok);
    CHECK(!W::fromPage("{}", "about:blank", "").ok);
    CHECK(!W::fromPage("{\"m\":1}", "https://user@site.com/", "").ok);

    // start-page JSON: safe inside a script, no start addresses
    std::vector<W::App> s;
    W::add(s, app("https://www.twitch.tv/", "</script><b>Twitch\xE2\x80\xA8"));
    const std::string pj = W::pageJson(s, "\xC3\x97 Open");
    CHECK(pj.find("</script>") == std::string::npos && pj.find("\\u003c/script>") != std::string::npos);
    CHECK(pj.find("\xE2\x80\xA8") == std::string::npos && pj.find("\\u2028") != std::string::npos);
    CHECK(pj.find("https://") == std::string::npos && pj.find("\"h\":\"twitch.tv\"") != std::string::npos);
    CHECK(pj.find("\"max\":12") != std::string::npos);

    // texts / timeout
    CHECK(W::addNotice(W::kFull, "X").find("12") != std::string::npos);
    CHECK(W::summary(0) == "None yet" && W::summary(3) == "3 of 12");
    CHECK(!W::expired(100, 4099) && W::expired(100, 4100) && W::expired(0xfffff000u, 0x00000c00u + 1000));
    CHECK(W::pageScript().find(")JS") == std::string::npos);

    // OMNI_WEB_APPS_V1_R2: a file that does not parse is kept as <name>.bad-<unix time>, at most 3
    CHECK(W::badName("apps.json", 1763300000) == "apps.json.bad-1763300000" && W::badName("apps.json", -5) == "apps.json.bad-0");
    CHECK(W::badTime("apps.json.bad-1763300000", "apps.json") == 1763300000 && W::badTime("apps.json.bad-0", "apps.json") == 0);
    CHECK(W::badTime("apps.json.bad-", "apps.json") == -1 && W::badTime("apps.json.bad-12x", "apps.json") == -1 && W::badTime("apps.json", "apps.json") == -1);
    CHECK(W::badTime("start-page.json.bad-12", "apps.json") == -1 && W::badTime("apps.json.bad-1234567890123456789", "apps.json") == -1 && W::badTime("apps.json.tmp", "apps.json") == -1);
    {
        const std::vector<std::string> dir = { "apps.json", "apps.json.bad-100", "apps.jsonx.bad-1", "apps.json.bad-400", "apps.json.bad-300", "apps.json.bad-x", "apps.json.bad-200", ".", ".." };
        const std::vector<std::string> drop = W::badToDrop(dir, "apps.json");
        CHECK(drop.size() == 1 && drop[0] == "apps.json.bad-100");                 // the 3 newest (400 300 200) stay
        CHECK(W::badToDrop(dir, "apps.json", 1).size() == 3);
        CHECK(W::badToDrop({ "apps.json.bad-1", "apps.json.bad-2", "apps.json.bad-3" }, "apps.json").empty());
        CHECK(W::badToDrop({}, "apps.json").empty());
    }

    if (argc > 1) { std::ofstream o(argv[1], std::ios::binary); o << W::pageScript(); }
    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
