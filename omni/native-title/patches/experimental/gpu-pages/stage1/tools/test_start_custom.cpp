// OMNI_START_CUSTOM_V1: host tests for OmniStartCustom.h (the pure part of "Customise start page").
//   python3 apply_start_custom.py <tree>; g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_start_custom.cpp -o t && ./t
#include "OmniStartCustom.h"
#include <cstdint>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

namespace S = OmniStartCustom;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)
static bool has(const std::string& s, const std::string& sub) { return s.find(sub) != std::string::npos; }
static std::string orderText(const S::Config& c) { std::string o; for (int s : c.order) o += std::string(o.empty() ? "" : ",") + S::sectionKey(s); return o; }

int main()
{
    // defaults
    S::Config d = S::defaults();
    CHECK(orderText(d) == "search,apps,shortcuts,cw,reading,closed");
    CHECK(S::sameAsDefault(d) && S::defaultOrder(d) && d.bg == S::bgTheme && !d.clock);
    for (int s = 0; s < S::sCount; ++s) CHECK(S::sectionOf(S::sectionKey(s)) == s);
    CHECK(S::sectionOf("nope") == -1);

    // serialize -> parse round trip
    S::Config c = d;
    c.hidden[S::sClosed] = true; c.hidden[S::sApps] = true; c.bg = S::bgColour; c.colour = 3; c.clock = true;
    CHECK(S::move(c, S::sReading, -1));    // reading above cw
    const std::string j = S::serialize(c);
    CHECK(j == "{\"v\":1,\"order\":[\"search\",\"apps\",\"shortcuts\",\"reading\",\"cw\",\"closed\"],\"hidden\":[\"apps\",\"closed\"],"
               "\"bg\":\"colour\",\"colour\":3,\"picture\":\"\",\"clock\":true}\n");
    S::Config r;
    CHECK(S::parse(j, r));
    CHECK(orderText(r) == orderText(c) && r.hidden[S::sClosed] && r.hidden[S::sApps] && !r.hidden[S::sSearch]);
    CHECK(r.bg == S::bgColour && r.colour == 3 && r.clock && S::serialize(r) == j);
    CHECK(!S::sameAsDefault(r) && !S::defaultOrder(r));

    // tolerant parsing
    CHECK(!S::parse("", r) && S::sameAsDefault(r));
    CHECK(!S::parse("{\"order\":[", r) && S::sameAsDefault(r));
    CHECK(!S::parse("[1,2]", r) && S::sameAsDefault(r));
    CHECK(!S::parse("{\"a\":1} x", r));
    CHECK(S::parse("{}", r) && S::sameAsDefault(r));
    CHECK(S::parse("{\"order\":[\"closed\",\"closed\",\"bogus\",7,\"search\"]}", r));
    CHECK(orderText(r) == "closed,search,apps,shortcuts,cw,reading");    // duplicates / unknowns dropped, missing ones kept
    CHECK(S::parse("{\"order\":[\"cw\"],\"hidden\":[\"cw\",\"search\",\"x\"]}", r));
    CHECK(orderText(r) == "search,apps,shortcuts,cw,reading,closed");
    CHECK(!r.hidden[S::sCw] && r.hidden[S::sSearch]);                      // cw is its own flag, never stored here
    CHECK(S::parse("{\"bg\":\"colour\",\"colour\":99}", r) && r.bg == S::bgColour && r.colour == 0);
    CHECK(S::parse("{\"bg\":\"picture\",\"picture\":\"../../etc/x.png\"}", r) && r.bg == S::bgTheme);
    CHECK(S::parse("{\"bg\":\"picture\",\"picture\":\"a.b-20261116-101010.PNG\"}", r) && r.bg == S::bgPicture && r.picture == "a.b-20261116-101010.PNG");
    CHECK(S::parse("{\"bg\":\"picture\"}", r) && r.bg == S::bgPicture && r.picture.empty());
    CHECK(S::parse(" {\"clock\":true , \"x\":{\"y\":[1,\"\\u00e9\\ud83d\\ude00\",null,false]}}\n", r) && r.clock);
    CHECK(S::parse("{\"clock\":\"yes\"}", r) && !r.clock);
    std::string deep = "{\"a\":"; for (int i = 0; i < 20; ++i) deep += "["; deep += "1"; for (int i = 0; i < 20; ++i) deep += "]"; deep += "}";
    CHECK(!S::parse(deep, r));                                             // nesting limit
    CHECK(!S::parse("{\"a\":\"" + std::string(20000, 'x') + "\"}", r));   // size limit

    // JSON strings
    S::Json v;
    CHECK(S::parseJson("\"a\\\"b\\\\c\\n\\u00e9\\ud83d\\ude00\\ud800\"", v) && v.t == S::Json::tStr);
    CHECK(v.s == "a\"b\\c\n\xc3\xa9\xf0\x9f\x98\x80\xef\xbf\xbd");
    CHECK(!S::parseJson("\"a\nb\"", v));
    CHECK(S::quote("a\"\\<\n\xe2\x80\xa8x") == "\"a\\\"\\\\\\u003c\\u000a\\u2028x\"");

    // moving
    S::Config m = S::defaults();
    CHECK(!S::move(m, S::sSearch, -1) && orderText(m) == "search,apps,shortcuts,cw,reading,closed");
    CHECK(!S::move(m, S::sClosed, 1));
    CHECK(S::move(m, S::sSearch, 1) && orderText(m) == "apps,search,shortcuts,cw,reading,closed");
    CHECK(S::position(m, S::sSearch) == 1);
    CHECK(S::move(m, S::sClosed, -1) && S::move(m, S::sClosed, -1) && orderText(m) == "apps,search,shortcuts,closed,cw,reading");
    CHECK(!S::move(m, S::sApps, 2) && !S::move(m, 42, 1));
    for (int i = 0; i < 10; ++i) S::move(m, S::sReading, -1);
    CHECK(orderText(m) == "reading,apps,search,shortcuts,closed,cw");

    // background
    S::Config b = S::defaults();
    S::stepBackground(b, 1, false); CHECK(b.bg == S::bgColour && b.colour == 0 && S::backgroundText(b) == "Midnight");
    S::stepBackground(b, -1, false); CHECK(b.bg == S::bgTheme && S::backgroundText(b) == "Theme default");
    S::stepBackground(b, -1, false); CHECK(b.bg == S::bgColour && b.colour == 7);           // wraps past the picture
    S::stepBackground(b, 1, true); CHECK(b.bg == S::bgPicture && S::backgroundText(b) == "Your picture (start-bg.png)");
    S::stepBackground(b, 1, true); CHECK(b.bg == S::bgTheme);
    b.bg = S::bgPicture; S::stepBackground(b, 1, false); CHECK(b.bg == S::bgColour && b.colour == 0);   // picture gone
    CHECK(std::string(S::colour(-1).name) == "Snow" && std::string(S::colour(9).hex) == "#2a2e35");
    b.bg = S::bgPicture; b.picture.clear();
    CHECK(S::picturePath(b, "/shots") == "/data/omni/start-bg.png");
    b.picture = "x-20261116-101010.png"; CHECK(S::picturePath(b, "/shots") == "/shots/x-20261116-101010.png");
    b.picture = "../x.png"; CHECK(S::picturePath(b, "/shots").empty());
    b.bg = S::bgColour; CHECK(S::picturePath(b, "/shots").empty());
    CHECK(S::validPictureName("a.png") && !S::validPictureName(".a.png") && !S::validPictureName("a.txt") && !S::validPictureName("a/b.png")
          && !S::validPictureName("a\".png") && !S::validPictureName(".png"));

    // picture: names, magic bytes, 8 MB cap, cache key
    CHECK(S::validPictureName("a.JPG") && S::validPictureName("b.jpeg") && !S::validPictureName("c.gif") && !S::validPictureName("png"));
    const unsigned char pngMagic[] = { 0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a, 0 };
    const unsigned char jpgMagic[] = { 0xff, 0xd8, 0xff, 0xe0 };
    const unsigned char gifMagic[] = { 'G', 'I', 'F', '8', '9', 'a', 0, 0 };
    const unsigned char html[] = "<svg onload=x>";
    CHECK(std::string(S::pictureMime(pngMagic, sizeof pngMagic)) == "image/png");
    CHECK(std::string(S::pictureMime(jpgMagic, sizeof jpgMagic)) == "image/jpeg");
    CHECK(std::string(S::pictureMime(gifMagic, sizeof gifMagic)).empty() && std::string(S::pictureMime(html, sizeof html)).empty());
    CHECK(std::string(S::pictureMime(pngMagic, 7)).empty() && std::string(S::pictureMime(jpgMagic, 2)).empty() && std::string(S::pictureMime(nullptr, 0)).empty());
    CHECK(S::kMaxPicture == 8LL * 1024 * 1024);
    CHECK(S::pictureKey("/p.png", 10, 20) == "/p.png|10|20" && S::pictureKey("/p.png", 10, 20) != S::pictureKey("/p.png", 11, 20)
          && S::pictureKey("/p.png", 10, 20) != S::pictureKey("/p.png", 10, 21) && S::pictureKey("/a.png", 1, 1) != S::pictureKey("/b.png", 1, 1));

    // lists
    std::vector<std::pair<std::string, std::string>> closed = {
        { "https://a.com/1", "A1" }, { "https://www.B.com:8080/x", "" }, { "https://a.com/1", "A1 again" }, { "http://c.org", "C" } };
    auto nc = S::newestClosed(closed, 5);
    CHECK(nc.size() == 3 && nc[0].url == "http://c.org" && nc[1].url == "https://a.com/1" && nc[1].title == "A1 again" && nc[2].site == "b.com");
    CHECK(S::newestClosed(closed, 1).size() == 1);
    CHECK(S::site("https://u@www.Example.com:8443/x?y") == "example.com" && S::site("nope").empty());
    CHECK(S::validReadingId("a.com-20261116-101010.html") && !S::validReadingId("../x") && !S::validReadingId(".x") && !S::validReadingId("a b"));

    // the page's data
    std::vector<S::Reading> rl = { { "r1.html", "Title <1>", "a.com", "Today 10:00" }, { "r2.html", "", "b.com", "12 Nov" },
                                   { "r3.html", "T3", "c.com", "" }, { "r4.html", "T4", "d.com", "" } };
    const std::string pj = S::pageJson(c, false, true, rl, nc, "", "\xC3\x97 Open");
    CHECK(has(pj, "\"order\":[\"search\",\"apps\",\"shortcuts\",\"reading\",\"cw\",\"closed\"]"));
    CHECK(has(pj, "\"hidden\":[\"apps\",\"closed\"]") && has(pj, "\"bg\":{\"kind\":\"colour\",\"value\":\"#12355b\"}"));
    CHECK(has(pj, "\"clock\":true,\"private\":false,\"linear\":true"));
    CHECK(has(pj, "\"t\":\"Title \\u003c1>\"") && has(pj, "{\"id\":\"r2.html\",\"t\":\"b.com\"") && !has(pj, "r4.html"));
    CHECK(has(pj, "\"closed\":[{\"u\":\"http://c.org\""));
    S::Json pv;
    CHECK(S::parseJson(pj, pv) && pv.t == S::Json::tObj && pv.o["reading"].a.size() == 3 && pv.o["closed"].a.size() == 3);
    const std::string pp = S::pageJson(c, true, true, rl, nc, "", "");
    CHECK(has(pp, "\"hidden\":[\"apps\",\"cw\",\"closed\"]") && has(pp, "\"closed\":[]") && has(pp, "\"private\":true"));
    const std::string off = S::pageJson(S::defaults(), false, false, {}, {}, "", "");
    CHECK(has(off, "\"hidden\":[\"cw\"]") && has(off, "\"linear\":false") && has(off, "\"bg\":{\"kind\":\"theme\"}"));
    S::Config pic = S::defaults(); pic.bg = S::bgPicture;
    CHECK(has(S::pageJson(pic, false, true, {}, {}, "17-42-9", ""), "\"bg\":{\"kind\":\"picture\",\"url\":\"omni://pages/_user/start-bg.png?v=17-42-9\"}"));
    CHECK(has(S::pageJson(pic, false, true, {}, {}, "", ""), "\"bg\":{\"kind\":\"theme\"}"));   // picture missing: the theme

    // OMNI_START_CUSTOM_V1_R2: a file that does not parse is kept as <name>.bad-<unix time>, at most 3
    CHECK(S::badName("start-page.json", 1763300000) == "start-page.json.bad-1763300000" && S::badName("start-page.json", -5) == "start-page.json.bad-0");
    CHECK(S::badTime("start-page.json.bad-1763300000", "start-page.json") == 1763300000 && S::badTime("start-page.json.bad-0", "start-page.json") == 0);
    CHECK(S::badTime("start-page.json.bad-", "start-page.json") == -1 && S::badTime("start-page.json.bad-12x", "start-page.json") == -1 && S::badTime("start-page.json", "start-page.json") == -1);
    CHECK(S::badTime("apps.json.bad-12", "start-page.json") == -1 && S::badTime("start-page.json.bad-1234567890123456789", "start-page.json") == -1 && S::badTime("start-page.json.tmp", "start-page.json") == -1);
    {
        const std::vector<std::string> dir = { "start-page.json", "start-page.json.bad-100", "start-page.jsonx.bad-1", "start-page.json.bad-400", "start-page.json.bad-300", "start-page.json.bad-x", "start-page.json.bad-200", ".", ".." };
        const std::vector<std::string> drop = S::badToDrop(dir, "start-page.json");
        CHECK(drop.size() == 1 && drop[0] == "start-page.json.bad-100");                 // the 3 newest (400 300 200) stay
        CHECK(S::badToDrop(dir, "start-page.json", 1).size() == 3);
        CHECK(S::badToDrop({ "start-page.json.bad-1", "start-page.json.bad-2", "start-page.json.bad-3" }, "start-page.json").empty());
        CHECK(S::badToDrop({}, "start-page.json").empty());
    }
    // OMNI_START_CUSTOM_V1_R2: the closed-tab fingerprint changes on every push / pop / erase / clear / edit
    {
        std::vector<std::pair<std::string, std::string>> cl = { { "https://a.com/", "A" }, { "https://b.com/", "B" } };
        const uint64_t f0 = S::closedFingerprint(cl);
        CHECK(f0 == S::closedFingerprint(cl));                                  // stable
        auto c1 = cl; c1.emplace_back("https://c.com/", "C"); CHECK(S::closedFingerprint(c1) != f0);
        auto c2 = cl; c2.pop_back(); CHECK(S::closedFingerprint(c2) != f0);
        auto c3 = cl; c3.erase(c3.begin()); c3.emplace_back("https://b.com/", "B"); CHECK(S::closedFingerprint(c3) != f0);   // same size, same newest
        auto c4 = cl; c4[0].second = "A2"; CHECK(S::closedFingerprint(c4) != f0);
        CHECK(S::closedFingerprint({}) != f0 && S::closedFingerprint({ { "ab", "c" } }) != S::closedFingerprint({ { "a", "bc" } }));
    }

    printf("%s: %d/%d checks passed\n", fails ? "FAILED" : "OK", checks - fails, checks);
    return fails ? 1 : 0;
}
