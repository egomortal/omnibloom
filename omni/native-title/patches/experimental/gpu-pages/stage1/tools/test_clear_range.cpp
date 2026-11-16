// OMNI_CLEAR_RANGE_V1: host tests for engine/entry/OmniClearRange.h (written by apply_clear_range.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_clear_range.cpp -o t && ./t
#include "OmniClearRange.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniClearRange;

struct Visit { long long time; std::string url, title; };
static bool has(const std::string& s, const char* part) { return s.find(part) != std::string::npos; }

int main()
{
    const long long now = 1763300000;
    // ranges
    CHECK(rangeStart(LastHour, now) == now - 3600);
    CHECK(rangeStart(Last24Hours, now) == now - 86400);
    CHECK(rangeStart(Last7Days, now) == now - 604800);
    CHECK(rangeStart(AllTime, now) == LLONG_MIN);
    CHECK(stepRange(LastHour, -1) == AllTime && stepRange(AllTime, 1) == LastHour && stepRange(Last24Hours, 1) == Last7Days);
    CHECK(std::string(rangeName(Last7Days)) == "Last 7 days");
    CHECK(expired(100, 100 + kNativeMs) && !expired(100, 100 + kNativeMs - 1));
    CHECK(expired(0xFFFFFF00u, 0xFFFFFF00u + kNativeMs));   // wraps

    // how each category applies
    CHECK(how(History, LastHour) == ByTime && how(ContinueWatching, Last7Days) == ByTime);
    CHECK(how(Cookies, Last24Hours) == SitesInRange && how(Cookies, AllTime) == Everything);
    CHECK(how(Cache, LastHour) == WholeAnyRange && how(Cache, AllTime) == Everything);
    CHECK(how(KbWords, Last7Days) == AllTimeOnly && how(ClosedTabs, LastHour) == AllTimeOnly);
    CHECK(how(KbWords, AllTime) == Everything && how(ClosedTabs, AllTime) == Everything);
    Choice ch;
    CHECK(ch.range == LastHour && ch.on[History] && ch.on[Cookies] && ch.on[Cache] && !ch.on[KbWords] && !ch.on[ContinueWatching] && !ch.on[ClosedTabs]);
    CHECK(anything(ch));
    ch = Choice();
    for (bool& b : ch.on) b = false;
    ch.on[KbWords] = ch.on[ClosedTabs] = true;
    CHECK(!anything(ch) && !applies(ch, KbWords));   // words / closed tabs only with All time
    ch.range = AllTime;
    CHECK(anything(ch) && applies(ch, KbWords) && applies(ch, ClosedTabs) && !applies(ch, History));
    CHECK(!applies(ch, -1) && !applies(ch, CatCount));

    // history by time
    std::vector<Visit> h = {
        { now - 8 * 86400, "https://old.example/a", "old" },
        { now - 3 * 86400, "https://www.News.example.com:8443/x?y#z", "news" },
        { now - 7200, "http://user:pw@shop.example.org/cart", "shop" },
        { now - 1800, "https://news.example.com/b", "news again" },
        { now - 60, "https://[2001:DB8::1]:8080/", "v6" },
        { now - 30, "https://WWW.shop.example.org./", "shop www" },
        { now + 100, "https://future.example/", "clock moved" },
    };
    CHECK(countSince(h, rangeStart(LastHour, now)) == 4);
    CHECK(countSince(h, rangeStart(Last24Hours, now)) == 5);
    CHECK(countSince(h, rangeStart(Last7Days, now)) == 6);
    CHECK(countSince(h, rangeStart(AllTime, now)) == 7);
    {
        auto copy = h;
        CHECK(eraseSince(copy, rangeStart(LastHour, now)) == 4);
        CHECK(copy.size() == 3 && copy[0].title == "old" && copy[2].title == "shop");   // order kept
        CHECK(eraseSince(copy, rangeStart(AllTime, now)) == 3 && copy.empty());
    }

    // hosts
    CHECK(hostOf("https://www.News.example.com:8443/x") == "www.news.example.com");
    CHECK(hostOf("http://user:pw@shop.example.org/cart") == "shop.example.org");
    CHECK(hostOf("HTTPS://Example.COM.") == "example.com");
    CHECK(hostOf("https://[2001:DB8::1]:8080/") == "[2001:db8::1]");
    CHECK(hostOf("https://a.example/p@q") == "a.example");   // '@' in the path is not userinfo
    CHECK(hostOf("ftp://example.com/") == "" && hostOf("omni://pages/start/") == "" && hostOf("https://") == "");
    CHECK(hostOf("https://exa mple.com/") == "" && hostOf("https://[::1/") == "");
    CHECK(siteKey("www.example.com") == "example.com" && siteKey("example.com") == "example.com" && siteKey("www.") == "www.");
    {
        size_t more = 99;
        auto hosts = hostsSince(h, rangeStart(LastHour, now), kMaxSites, &more);
        // newest first; shop.example.org and its www. twin are one site (the newest spelling kept)
        CHECK(hosts.size() == 4 && more == 0);
        CHECK(hosts.size() == 4 && hosts[0] == "future.example" && hosts[1] == "www.shop.example.org" && hosts[2] == "[2001:db8::1]" && hosts[3] == "news.example.com");
        auto week = hostsSince(h, rangeStart(Last7Days, now), kMaxSites, &more);
        CHECK(week.size() == 4);   // www.news.example.com merges with news.example.com, shop with www.shop
        auto capped = hostsSince(h, rangeStart(AllTime, now), 2, &more);
        CHECK(capped.size() == 2 && more == 3);
        CHECK(hostsSince(h, now + 1000, kMaxSites, &more).empty() && more == 0);
    }

    // Continue watching entries
    CHECK(cwKey("w:abc") && !cwKey("w:") && !cwKey("x:abc") && !cwKey("resume:abc"));
    double a = 0;
    CHECK(jsonNumber("{\"u\":\"https://v.example/\",\"t\":\"t\",\"p\":1421,\"d\":3600,\"a\":1700000000}", "a", a) && a == 1700000000);
    CHECK(jsonNumber("{ \"a\" : 12.5 }", "a", a) && a == 12.5);
    CHECK(!jsonNumber("{\"t\":\"say \\\"a\\\":5 here\",\"p\":1}", "a", a));        // "a": inside a string is not the field
    CHECK(jsonNumber("{\"t\":\"x\\\\\",\"a\":7}", "a", a) && a == 7);                 // an escaped backslash ends the string right
    CHECK(jsonNumber("{\"n\":{\"a\":1},\"a\":8}", "a", a) && a == 8);                // nested objects are skipped
    CHECK(!jsonNumber("{\"a\":\"5\"}", "a", a) && !jsonNumber("{\"a\":5x}", "a", a) && !jsonNumber("[1]", "a", a) && !jsonNumber("", "a", a));
    CHECK(!jsonNumber("{\"u\":\"unterminated", "a", a));
    std::map<std::string, std::string> kv = {
        { "w:new", "{\"u\":\"https://v/1\",\"p\":200,\"d\":900,\"a\":" + std::to_string(now - 600) + "}" },
        { "w:day", "{\"u\":\"https://v/2\",\"p\":200,\"d\":900,\"a\":" + std::to_string(now - 20000) + "}" },
        { "w:old", "{\"u\":\"https://v/3\",\"p\":200,\"d\":900,\"a\":" + std::to_string(now - 30 * 86400) + "}" },
        { "w:notime", "{\"u\":\"https://v/4\",\"p\":200,\"d\":900}" },
        { "w:junk", "not json" },
        { "resume:https://v/1", "{\"p\":200,\"a\":" + std::to_string(now) + "}" },
        { "x", "1" },
    };
    CHECK(cwKeysSince(kv, rangeStart(LastHour, now)) == std::vector<std::string>({ "w:new" }));
    CHECK(cwKeysSince(kv, rangeStart(Last24Hours, now)).size() == 2);
    CHECK(cwKeysSince(kv, rangeStart(Last7Days, now)).size() == 2);
    CHECK(cwKeysSince(kv, rangeStart(AllTime, now)).size() == 5);   // every "w:" key, junk and timeless included, never others

    // texts
    Counts c;
    c.visits = 4; c.sites = 3; c.words = 37; c.cw = 1; c.closed = 2;
    CHECK(rowDetail(History, LastHour, c) == "4 visits");
    CHECK(rowDetail(Cookies, LastHour, c) == "Cookies of 3 sites visited; their storage stays");
    CHECK(rowDetail(Cookies, AllTime, c) == "Every site: you will be signed out");
    CHECK(has(rowDetail(Cache, Last7Days, c), "can't be cleared by time") && rowDetail(Cache, AllTime, c) == "Whole cache");
    CHECK(has(rowDetail(KbWords, LastHour, c), "All time only") && rowDetail(KbWords, AllTime, c) == "37 words");
    CHECK(rowDetail(ClosedTabs, AllTime, c) == "2 tabs" && rowDetail(ContinueWatching, LastHour, c) == "1 entry");
    { Counts none; none.cwAvailable = false; CHECK(rowDetail(Cookies, LastHour, none) == "No sites visited in this time" && rowDetail(ContinueWatching, LastHour, none) == "Add-on not installed"); }
    CHECK(askTitle(LastHour) == "Clear browsing data from the last hour?");
    CHECK(askTitle(Last24Hours) == "Clear browsing data from the last 24 hours?");
    CHECK(askTitle(AllTime) == "Clear all browsing data?");
    {
        Choice q;   // defaults: history, cookies, cache; last hour
        const std::string body = askBody(q, c);
        CHECK(has(body, "History: 4 visits.") && has(body, "3 sites you visited") && has(body, "local storage and databases stay"));
        CHECK(has(body, "whole cache") && has(body, "Private tabs are not affected.") && !has(body, "keyboard"));
        Counts many = c; many.sitesMore = 7;
        CHECK(has(askBody(q, many), "the newest 3 of 10"));
        q.range = AllTime; q.on[KbWords] = q.on[ClosedTabs] = q.on[ContinueWatching] = true;
        const std::string all = askBody(q, c);
        CHECK(has(all, "every site (you will be signed out)") && has(all, "37 learned keyboard words") && has(all, "2 closed tabs") && has(all, "Continue watching: 1 entry"));
        Counts zero;
        q = Choice();
        CHECK(has(askBody(q, zero), "Cookies: no sites visited in that time"));
    }
    {
        Result r;
        r.history = r.cookies = r.cache = true; r.visits = 12; r.sites = 4;
        CHECK(summary(r) == "Cleared 12 visits, cookies of 4 sites, cached files.");
        r.cacheOk = false;
        CHECK(summary(r) == "Cleared 12 visits, cookies of 4 sites. Not cleared: cached files (no answer in time).");
        r = Result(); r.range = AllTime; r.cookies = r.words = r.closed = r.cw = true; r.wordCount = 1; r.closedCount = 3; r.cwCount = 2;
        CHECK(summary(r) == "Cleared cookies and site data, 1 learned word, 2 Continue watching entries, 3 closed tabs.");
        r.cookiesOk = false;
        CHECK(has(summary(r), "Not cleared: cookies and site data (no answer in time)."));
        r = Result(); r.range = Last24Hours; r.history = true;
        CHECK(summary(r) == "Nothing to clear from the last 24 hours.");
        r.range = AllTime;
        CHECK(summary(r) == "Nothing to clear.");
        r = Result(); r.cookies = true; r.sites = 400; r.sitesMore = 5;
        CHECK(summary(r) == "Cleared cookies of 400 sites. Not cleared: cookies of 5 older sites (limit 400).");
        r = Result(); r.cookies = true; r.cookiesOk = false; r.sites = 2;
        CHECK(summary(r) == "Nothing to clear from the last hour. Not cleared: some cookies (no answer in time).");
    }
    // ids: row ids inside 7421..7428, no overlap
    CHECK(kRowCat + CatCount - 1 < kRowClear && kRowRange < kRowCat && kPanelKind < kRowRange);

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
