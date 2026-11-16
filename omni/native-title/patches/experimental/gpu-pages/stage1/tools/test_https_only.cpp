// OMNI_HTTPS_ONLY_V1: host tests for engine/entry/OmniHttpsOnly.h (written by apply_https_only.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_https_only.cpp -o t && ./t
#include "OmniHttpsOnly.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniHttpsOnly;

static bool v4(const char* s, uint32_t want) { uint32_t v = 0; return parseIPv4(s, v) && v == want; }
static bool v4bad(const char* s) { uint32_t v; return !parseIPv4(s, v); }
static bool v6(const char* s, std::initializer_list<int> want)
{
    uint8_t b[16];
    if (!parseIPv6(s, b)) return false;
    int i = 0;
    for (int w : want) if (b[i++] != uint8_t(w)) return false;
    return true;
}
static bool v6bad(const char* s) { uint8_t b[16]; return !parseIPv6(s, b); }
static Action act(const Store& s, const Session& sess, const char* url, bool get = true, bool hist = false, const char* inflight = "", std::string* out = nullptr)
{
    Nav n; n.url = url; n.get = get; n.historyOrReload = hist; n.inFlightHost = inflight;
    return decide(s, sess, n, out);
}

int main()
{
    // URL parsing
    Url u = parseUrl("http://User:pw@WWW.Example.COM:8080/a?b#c");
    CHECK(u.ok && u.http && u.host == "www.example.com" && u.port == 8080);
    u = parseUrl("https://example.com.");
    CHECK(u.ok && !u.http && u.host == "example.com" && u.port == -1);
    u = parseUrl("http://[2001:DB8::1]:81/x");
    CHECK(u.ok && u.host == "2001:db8::1" && u.port == 81);
    CHECK(parseUrl("HTTP://example.com/").http);
    CHECK(!parseUrl("omni://pages/start").ok);
    CHECK(!parseUrl("about:blank").ok);
    CHECK(!parseUrl("http:///nohost").ok);
    CHECK(!parseUrl("http://bad host/").ok);
    CHECK(!parseUrl("http://example.com:99999/").ok);
    CHECK(!parseUrl("http://example.com:8a/").ok);
    CHECK(!parseUrl("http://[::1/").ok);
    CHECK(!parseUrl("http://[foo.com]/").ok);
    CHECK(parseUrl("http://example.com:/").ok && parseUrl("http://example.com:/").port == -1);
    CHECK(parseUrl("http://a@b@example.com/").host == "example.com");
    CHECK(hostKey("WWW.Example.com.") == "example.com" && hostKey("[::1]") == "::1" && hostKey("www.") == "www");
    CHECK(urlHostKey("http://www.news.example.com/x") == "news.example.com");

    // IPv4 / IPv6
    CHECK(v4("10.0.0.1", 0x0a000001) && v4("255.255.255.255", 0xffffffff) && v4("0.0.0.0", 0));
    CHECK(v4bad("256.1.1.1") && v4bad("1.2.3") && v4bad("1.2.3.4.5") && v4bad("1..2.3") && v4bad("a.b.c.d") && v4bad("1.2.3.4 ") && v4bad("") && v4bad("1234.1.1.1"));
    CHECK(v6("::1", { 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1 }));
    CHECK(v6("::", { 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 }));
    CHECK(v6("fe80::1", { 0xfe,0x80,0,0,0,0,0,0,0,0,0,0,0,0,0,1 }));
    CHECK(v6("1::", { 0,1,0,0 }));
    CHECK(v6("1:2:3:4:5:6:7:8", { 0,1,0,2,0,3,0,4,0,5,0,6,0,7,0,8 }));
    CHECK(v6("::ffff:192.168.0.2", { 0,0,0,0,0,0,0,0,0,0,0xff,0xff,192,168,0,2 }));
    CHECK(v6bad("1:2:3:4:5:6:7:8:9") && v6bad("1::2::3") && v6bad(":1") && v6bad("1:") && v6bad("12345::") && v6bad("g::") && v6bad("") && v6bad("1:2:3:4:5:6:7"));

    // private / exempt hosts
    for (const char* h : { "localhost", "foo.localhost", "printer.local", "127.0.0.1", "127.5.5.5", "10.1.2.3", "172.16.0.1", "172.31.255.255",
                           "192.168.0.20", "169.254.1.1", "::1", "fd00::5", "fe80::1", "::ffff:10.0.0.1", "[::1]" })
        CHECK(privateHost(h));
    for (const char* h : { "example.com", "172.15.0.1", "172.32.0.1", "192.169.0.1", "11.0.0.1", "8.8.8.8", "2001:db8::1", "::ffff:8.8.8.8", "local", "localhost.com", "mylocal" })
        CHECK(!privateHost(h));
    CHECK(exempt(parseUrl("http://127.0.0.1:8080/fs/x")));
    CHECK(exempt(parseUrl("http://192.168.0.20:8095/")));
    CHECK(exempt(parseUrl("http://[::1]:8443/")));
    CHECK(exempt(parseUrl("http://console.example:8765/downloads")));   // the Downloads app port, any host
    CHECK(exempt(parseUrl("https://example.com/")));                     // already secure
    CHECK(exempt(parseUrl("omni://pages/start")));
    CHECK(!exempt(parseUrl("http://example.com/")));

    // upgrade URL
    CHECK(upgradeUrl("http://example.com/a?b#c") == "https://example.com/a?b#c");
    CHECK(upgradeUrl("http://example.com") == "https://example.com");
    CHECK(upgradeUrl("http://example.com:80/x") == "https://example.com/x");
    CHECK(upgradeUrl("http://example.com:8080/x") == "https://example.com:8080/x");
    CHECK(upgradeUrl("http://u:p@example.com:80/x") == "https://u:p@example.com/x");
    CHECK(upgradeUrl("http://[2001:db8::1]:80/") == "https://[2001:db8::1]/");
    CHECK(upgradeUrl("http://example.com?q=1") == "https://example.com?q=1");
    CHECK(upgradeUrl("https://example.com/").empty() && upgradeUrl("omni://x").empty());

    // decide: off by default
    Store s; Session sess;
    CHECK(act(s, sess, "http://example.com/") == kLoad);
    s.httpsOnly = true;
    std::string https;
    CHECK(act(s, sess, "http://example.com/a", true, false, "", &https) == kUpgrade && https == "https://example.com/a");
    CHECK(act(s, sess, "https://example.com/") == kLoad);
    CHECK(act(s, sess, "http://127.0.0.1:8080/") == kLoad);
    CHECK(act(s, sess, "http://10.0.0.2/") == kLoad);
    CHECK(act(s, sess, "omni://pages/start") == kLoad);
    CHECK(act(s, sess, "about:blank") == kLoad);
    CHECK(act(s, sess, "http://example.com/form", false) == kLoad);         // POST keeps its body
    CHECK(act(s, sess, "http://example.com/", true, true) == kLoad);        // Back / Forward / Reload
    // in flight: the site redirected https back to http -> panel (not a loop); another host still upgrades
    CHECK(act(s, sess, "http://www.example.com/", true, false, "example.com") == kInterstitial);
    CHECK(act(s, sess, "http://other.com/", true, false, "example.com") == kUpgrade);
    // allowed hosts
    allowForSession(sess, "www.example.com");
    CHECK(allowed(s, sess, "example.com") && act(s, sess, "http://example.com/") == kLoad);
    CHECK(act(s, sess, "http://www.example.com/", true, false, "example.com") == kLoad);
    CHECK(act(s, sess, "http://sub.example.com/") == kUpgrade);             // exact host, no subdomains
    sess.clear();
    CHECK(setSite(s, sess, "Example.com", true, false) && s.allow.count("example.com") && sess.empty());
    CHECK(act(s, sess, "http://example.com/") == kLoad);
    // private tab: only the session changes; a session row exists only while it differs from the saved choice
    CHECK(setSite(s, sess, "example.com", false, true) && sess.count("example.com") && !sess["example.com"] && s.allow.count("example.com"));
    CHECK(act(s, sess, "http://example.com/") == kUpgrade);
    CHECK(siteValue(s, sess, "example.com", true) == "Upgrade to https (this session)");
    CHECK(setSite(s, sess, "example.com", true, true) && sess.empty());
    CHECK(siteValue(s, sess, "example.com", false) == "Allow http");
    CHECK(setSite(s, sess, "news.org", true, true) && !s.allow.count("news.org") && siteValue(s, sess, "news.org", true) == "Allow http (this session)");
    CHECK(siteValue(s, sess, "other.org", false) == "Upgrade to https");
    CHECK(siteValue(s, sess, "192.168.0.5", false) == "Not needed (local)");
    CHECK(siteValue(s, sess, "::1", false) == "Not needed (local)");
    // a normal-tab choice clears the session row (e.g. "Continue")
    allowForSession(sess, "x.org");
    CHECK(setSite(s, sess, "x.org", false, false) && !sess.count("x.org") && !allowed(s, sess, "x.org"));
    CHECK(!setSite(s, sess, "", true, false));
    // 500 limit
    Store full; Session none;
    for (int i = 0; i < 500; ++i) full.allow.insert("h" + std::to_string(i) + ".com");
    CHECK(!setSite(full, none, "new.com", true, false) && setSite(full, none, "h1.com", false, false) && setSite(full, none, "new.com", true, false));
    CHECK(setSite(full, none, "another.com", true, true));   // a private choice is never refused

    // fallback errors
    CHECK(fallbackError("CurlErrorDomain", 60) && fallbackError("CurlErrorDomain", 35) && fallbackError("CurlErrorDomain", 7) && fallbackError("CurlErrorDomain", 28));
    CHECK(!fallbackError("CurlErrorDomain", 6));      // DNS: http would fail too
    CHECK(!fallbackError("WebKitErrorDomain", 102) && !fallbackError("OmniUBlock", 7) && !fallbackError("CurlErrorDomain", -999));

    // file
    Store w; w.httpsOnly = true; w.gpc = true; w.allow = { "example.com", "2001:db8::1" };
    const std::string text = serialize(w);
    CHECK(text == "omni-https-only\t1\nhttps_only\t1\ngpc\t1\nallow\t2001:db8::1\nallow\texample.com\n");
    Store r = parse(text);
    CHECK(r.httpsOnly && r.gpc && r.allow == w.allow);
    r = parse("omni-https-only\t1\r\nhttps_only\t0\r\ngpc\t1\r\nallow\tWWW.Foo.com\r\nallow\tbad host\r\nallow\tfoo.com:80\r\nallow\t\r\njunk\r\nallow\tbar.org");
    CHECK(!r.httpsOnly && r.gpc && r.allow.size() == 2 && r.allow.count("foo.com") && r.allow.count("bar.org"));
    CHECK(parse("").allow.empty() && !parse("").httpsOnly && !parse("").gpc);
    std::string many = kHeader; many += "\n";
    for (int i = 0; i < 600; ++i) many += "allow\th" + std::to_string(i) + ".com\n";
    CHECK(parse(many).allow.size() == kMaxAllow);

    // texts
    CHECK(std::string(interstitialTitle()) == "This site doesn't support a secure connection");
    CHECK(interstitialBody("example.com", 60).find("https://example.com but its security certificate isn't valid") != std::string::npos);
    CHECK(interstitialBody("example.com", kRedirectedBack).find("sent Omni back") != std::string::npos);
    CHECK(httpsOnlyNotice(true) == "HTTPS-only mode: On. Applies to pages you open from now on");
    CHECK(gpcNotice(false) == "Ask sites not to sell or share my data: Off. Applies to pages you open from now on");
    CHECK(siteNotice("foo.com", true, true, false, true) == "HTTPS-only on foo.com: Allow http (this session only)");
    CHECK(siteNotice("foo.com", false, false, false, false).find("off in Browser settings") != std::string::npos);
    CHECK(siteNotice("foo.com", true, false, true, true).find("500") != std::string::npos);
    CHECK(continueNotice("foo.com").find("until Omni closes") != std::string::npos);

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
