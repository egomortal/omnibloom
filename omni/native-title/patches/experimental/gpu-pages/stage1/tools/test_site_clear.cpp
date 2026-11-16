// OMNI_SITE_CLEAR_V1 (r2): host tests for engine/entry/OmniSiteClear.h (written by apply_site_clear.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_site_clear.cpp -o t && ./t [script.js]
// With an argument the page script (for example.com) is written there, for test_site_clear_js.mjs.
#include "OmniSiteClear.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniSiteClear;

static bool has(const std::string& s, const char* part) { return s.find(part) != std::string::npos; }

int main(int argc, char** argv)
{
    // sites
    CHECK(siteOf("www.example.com") == "example.com");
    CHECK(siteOf("example.com") == "example.com");
    CHECK(siteOf("WWW.Example.COM.") == "example.com");
    CHECK(siteOf("a.b.c.example.org") == "example.org");
    CHECK(siteOf("www.example.co.uk") == "example.co.uk");
    CHECK(siteOf("example.co.uk") == "example.co.uk");
    CHECK(siteOf("shop.example.com.au") == "example.com.au");
    CHECK(siteOf("www.example.de") == "example.de");
    CHECK(siteOf("www.example.io") == "example.io");     // "io" is not in the second-level list as a TLD case
    CHECK(siteOf("localhost") == "localhost");
    CHECK(siteOf("192.0.2.7") == "192.0.2.7");           // documentation range, IP literals stay whole
    CHECK(siteOf("2001:db8::1") == "2001:db8::1");
    CHECK(siteOf("a..example.com") == "a..example.com");
    CHECK(isIPv4("192.0.2.7") && !isIPv4("192.0.2") && !isIPv4("192.0.2.256") && !isIPv4("1.2.3.4.5") && !isIPv4("example.com"));

    CHECK(sameSite("example.com", "example.com"));
    CHECK(sameSite("www.example.com", "example.com"));
    CHECK(sameSite("a.b.example.com", "example.com"));
    CHECK(!sameSite("badexample.com", "example.com"));
    CHECK(!sameSite("example.com.evil.example.org", "example.com"));
    CHECK(!sameSite("example.org", "example.com"));
    CHECK(!sameSite("", "example.com") && !sameSite("example.com", ""));

    // targets
    Target t = target("https://www.example.com/path?q=1#x");
    CHECK(t.ok && t.https && t.host == "www.example.com" && t.site == "example.com" && t.origin == "https://www.example.com");
    t = target("HTTP://User:pw@Example.ORG:8080/a");
    CHECK(t.ok && !t.https && t.host == "example.org" && t.site == "example.org" && t.origin == "http://example.org:8080");
    t = target("https://example.com:443");
    CHECK(t.ok && t.origin == "https://example.com");
    t = target("http://example.com:80/");
    CHECK(t.ok && t.origin == "http://example.com");
    t = target("https://[2001:DB8::1]:8443/");
    CHECK(t.ok && t.host == "2001:db8::1" && t.site == "2001:db8::1" && t.origin == "https://[2001:db8::1]:8443");
    CHECK(!target("omni://newtab").ok);
    CHECK(!target("about:blank").ok);
    CHECK(!target("").ok);
    CHECK(!target("https://").ok);
    CHECK(!target("https://exa mple.com/").ok);
    CHECK(!target("https://example.com:99999/").ok);
    CHECK(!target("https://example.com:12a/").ok);
    CHECK(!target("https://[2001:db8::1/").ok);
    CHECK(!target("https://exa\"mple.com/").ok);
    CHECK(!target("https://example.com<script>/").ok);
    t = target("https://example.com./");
    CHECK(t.ok && t.host == "example.com");

    // cookie URLs: a URL (not a bare host), only the page's own host (WebKit widens it by libpsl itself)
    auto cu = cookieUrls(target("https://www.example.com/x"));
    CHECK(cu.size() == 1 && cu[0] == "https://www.example.com/");
    cu = cookieUrls(target("https://alice.github.io/"));
    CHECK(cu.size() == 1 && cu[0] == "https://alice.github.io/");   // never https://github.io/
    cu = cookieUrls(target("http://example.org/"));
    CHECK(cu.size() == 1 && cu[0] == "https://example.org/");
    cu = cookieUrls(target("https://[2001:db8::1]/"));
    CHECK(cu.size() == 1 && cu[0] == "https://[2001:db8::1]/");
    CHECK(cookieUrls(target("about:blank")).empty());

    // www. twins
    CHECK(wwwTwin("www.example.com") == "example.com" && wwwTwin("example.com") == "www.example.com");
    CHECK(wwwTwin("alice.github.io") == "www.alice.github.io" && wwwTwin("www.com") == "" && wwwTwin("localhost") == "");
    CHECK(wwwTwin("192.0.2.7") == "" && wwwTwin("2001:db8::1") == "" && wwwTwin("") == "");

    // CacheStorage origins: exact host + its www. / bare twin only, never by the heuristic site
    t = target("https://alice.github.io/repo/");
    CHECK(t.ok && t.site == "github.io");                 // the heuristic is wrong here, which is why it isn't used
    CHECK(cacheOriginMatches("alice.github.io", t) && cacheOriginMatches("ALICE.github.io.", t) && cacheOriginMatches("www.alice.github.io", t));
    CHECK(!cacheOriginMatches("bob.github.io", t) && !cacheOriginMatches("github.io", t) && !cacheOriginMatches("x.alice.github.io", t));
    t = target("https://myapp.netlify.app/");
    CHECK(cacheOriginMatches("myapp.netlify.app", t) && !cacheOriginMatches("other.netlify.app", t) && !cacheOriginMatches("netlify.app", t));
    t = target("https://someblog.blogspot.com/2026/");
    CHECK(cacheOriginMatches("someblog.blogspot.com", t) && !cacheOriginMatches("otherblog.blogspot.com", t) && !cacheOriginMatches("www.blogspot.com", t));
    t = target("https://my-app.herokuapp.com/");
    CHECK(cacheOriginMatches("my-app.herokuapp.com", t) && !cacheOriginMatches("other-app.herokuapp.com", t));
    t = target("http://www.school.k12.ca.us/");
    CHECK(t.site == "ca.us");
    CHECK(cacheOriginMatches("www.school.k12.ca.us", t) && cacheOriginMatches("school.k12.ca.us", t));
    CHECK(!cacheOriginMatches("other.k12.ca.us", t) && !cacheOriginMatches("city.ca.us", t) && !cacheOriginMatches("ca.us", t));
    t = target("https://www.example.com/");
    CHECK(cacheOriginMatches("example.com", t) && cacheOriginMatches("www.example.com", t));
    CHECK(!cacheOriginMatches("shop.example.com", t) && !cacheOriginMatches("example.org", t) && !cacheOriginMatches("", t));
    t = target("https://[2001:db8::1]/");
    CHECK(cacheOriginMatches("2001:db8::1", t) && cacheOriginMatches("[2001:db8::1]", t) && !cacheOriginMatches("2001:db8::2", t));
    CHECK(!cacheOriginMatches("example.com", target("about:blank")));

    // native timeout (SDL_GetTicks wraps after ~49 days)
    CHECK(!expired(1000, 1000) && !expired(1000, 1000 + kNativeMs - 1) && expired(1000, 1000 + kNativeMs));
    CHECK(expired(0xfffffff0u, 0xfffffff0u + kNativeMs) && !expired(0xfffffff0u, 5));
    CHECK(kNativeMs > uint32_t(kScriptMs));

    // JS strings
    CHECK(jsString("example.com") == "\"example.com\"");
    CHECK(jsString("a\"b\\c") == "\"a\\\"b\\\\c\"");
    CHECK(jsString("</script>") == "\"\\u003c/script\\u003e\"");
    CHECK(jsString("a\nb\r\t") == "\"a\\nb\\r\\t\"");
    CHECK(jsString(std::string("x\x01y", 3)) == "\"x\\u0001y\"");
    CHECK(jsString("a\xe2\x80\xa8" "b\xe2\x80\xa9") == "\"a\\u2028b\\u2029\"");
    CHECK(jsString("caf\xc3\xa9") == "\"caf\xc3\xa9\"");   // other UTF-8 passes through
    CHECK(jsString("&") == "\"\\u0026\"");

    // the script
    const std::string js = clearScript("example.com");
    CHECK(js.rfind("const site = \"example.com\";\n", 0) == 0);
    CHECK(has(js, "localStorage.clear()") && has(js, "sessionStorage.clear()") && has(js, "indexedDB.deleteDatabase")
          && has(js, "caches.delete") && has(js, "unregister()") && has(js, "document.cookie ="));
    CHECK(has(js, "\"omni-site-clear;\""));
    CHECK(has(js, "stepMs = 2500") && has(js, "allMs = 6000"));
    CHECK(has(js, "race = Promise.race.bind(Promise)") && has(js, "later = setTimeout;"));   // own copies first
    {   // after the copies, the script never calls the page's (possibly replaced) globals
        const std::string rest = js.substr(js.find("const out ="));
        CHECK(!has(rest, "setTimeout") && !has(rest, "Promise."));
    }
    CHECK(clearScript("a\"b").rfind("const site = \"a\\\"b\";", 0) == 0);

    // answers
    Report r = parseReport("omni-site-clear;ls=3;ss=1;ck=2;idb=1;idbb=0;idbf=0;cs=2;sw=1;to=0");
    CHECK(r.ok && r.ls == 3 && r.ss == 1 && r.ck == 2 && r.idb == 1 && r.idbBlocked == 0 && r.cs == 2 && r.sw == 1 && !r.timedOut);
    r = parseReport("omni-site-clear;ls=-1;ss=0;ck=0;idb=-1;idbb=2;idbf=1;cs=-1;sw=-1;to=1");
    CHECK(r.ok && r.ls == -1 && r.idb == -1 && r.idbBlocked == 2 && r.idbFailed == 1 && r.cs == -1 && r.timedOut);
    CHECK(!parseReport("").ok && !parseReport("other;ls=1").ok && !parseReport("omni-site-clear").ok);
    r = parseReport("omni-site-clear;ls=abc;zz=4;ss=;=3;cs=99999999;sw=2");
    CHECK(r.ok && r.ls == -1 && r.ss == -1 && r.cs == -1 && r.sw == 2);
    r = parseReport("omni-site-clear;idbb=-5");
    CHECK(r.ok && r.idbBlocked == 0);

    // texts
    t = target("https://www.example.com/");
    CHECK(askTitle(t) == "Clear cookies and site data for www.example.com?");
    const std::string body = askBody(t, false);
    CHECK(body.rfind("You may be signed out.", 0) == 0 && has(body, "Cookies for www.example.com (and its parent site) are deleted")
          && has(body, "(https://www.example.com)") && has(body, "other addresses keep their storage"));
    CHECK(!has(body, "subdomains") && !has(body, "Private"));
    CHECK(has(askBody(t, true), "Private tab: only this private session"));
    CHECK(rowValue(t, false) == "www.example.com" && rowValue(t, true) == "Clearing..." && rowValue(target("about:blank"), false) == "-");
    {   // hosting domains: the texts never name the public suffix
        const Target gh = target("https://alice.github.io/");
        CHECK(askTitle(gh) == "Clear cookies and site data for alice.github.io?" && !has(askBody(gh, false), " github.io"));
        CHECK(rowValue(gh, false) == "alice.github.io");
        CHECK(summary(gh, Report(), false, 0, false).rfind("Cleared alice.github.io: cookies.", 0) == 0);
    }

    std::string s = summary(t, parseReport("omni-site-clear;ls=3;ss=0;ck=2;idb=1;idbb=0;idbf=0;cs=0;sw=0;to=0"), true, 0, false);
    CHECK(s == "Cleared www.example.com: cookies, 3 stored items, 1 database. Reloading");
    s = summary(t, parseReport("omni-site-clear;ls=1;ss=0;ck=0;idb=0;idbb=1;idbf=0;cs=2;sw=1;to=0"), true, 1, false);
    CHECK(s == "Cleared www.example.com: cookies, 1 stored item, 2 caches, 1 service worker. Not cleared: 1 database in use. Reloading");
    s = summary(t, parseReport("omni-site-clear;ls=0;ss=0;ck=0;idb=0;idbb=0;idbf=0;cs=-1;sw=-1;to=0"), true, 2, true);
    CHECK(s == "Private tab: cleared www.example.com: cookies, caches. Reloading");
    s = summary(t, Report(), true, 0, false);
    CHECK(s == "Cleared www.example.com: cookies. Not cleared: page storage (the page didn't answer). Reloading");
    s = summary(t, Report(), false, 0, false);
    CHECK(s == "Cleared www.example.com: cookies. Not cleared: page storage (the tab shows another site). Reloading");
    s = summary(t, parseReport("omni-site-clear;ls=0;idb=2;idbb=0;idbf=2;to=1"), true, 0, false);
    CHECK(s == "Cleared www.example.com: cookies, 2 databases. Not cleared: 2 databases, some storage (timed out). Reloading");
    // native timeout: what had come back is reported, the rest is named
    Native n; n.timedOut = true;
    s = summary(t, Report(), true, 0, false, n);
    CHECK(s == "Cleared www.example.com: cookies. Not cleared: page storage (the page didn't answer in time). Reloading");
    n.cookies = false; n.caches = false;
    s = summary(t, Report(), true, 0, false, n);
    CHECK(s == "Nothing confirmed cleared for www.example.com. Not cleared: cookies (no answer in time), caches (no answer in time), page storage (the page didn't answer in time). Reloading");
    s = summary(t, Report(), true, 0, true, n);
    CHECK(s.rfind("Private tab: nothing confirmed cleared for www.example.com.", 0) == 0);
    n.cookies = true;
    s = summary(t, parseReport("omni-site-clear;ls=2;ss=0;ck=1;idb=0;cs=0;sw=0;to=0"), true, 1, false, n);
    CHECK(s == "Cleared www.example.com: cookies, 2 stored items. Not cleared: caches (no answer in time). Reloading");

    if (argc > 1) {
        if (FILE* f = std::fopen(argv[1], "wb")) { std::fputs(js.c_str(), f); std::fclose(f); }
    }
    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
