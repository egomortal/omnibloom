// OMNI_PARENTAL_V1: host tests for engine/entry/OmniParental.h (pure part of Parental controls).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_parental.cpp -o t && ./t
//   with the real KDF too:  g++ -std=c++20 -Wall -Wextra -DOPAR_TEST_OPENSSL -I<tree>/engine/entry test_parental.cpp -lcrypto -o t && ./t
#include "OmniParental.h"
#include <cstdio>
#include <cstring>
#ifdef OPAR_TEST_OPENSSL
#include "OmniVault.h"
#endif

namespace P = OmniParental;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define EQ(a, b) do { ++checks; const std::string x_ = (a), y_ = (b); if (x_ != y_) { ++fails; fprintf(stderr, "FAIL %s:%d: %s\n   got  [%s]\n   want [%s]\n", __FILE__, __LINE__, #a, x_.c_str(), y_.c_str()); } } while (0)

static P::Store blockStore(std::initializer_list<const char*> block, std::initializer_list<const char*> allow = {})
{
    P::Store s;
    s.enabled = true;
    s.pin.iterations = P::kDefaultIterations; s.pin.saltHex = std::string(32, 'a'); s.pin.hashHex = std::string(64, 'b');
    for (auto b : block) P::addSite(s.block, b);
    for (auto a : allow) P::addSite(s.allow, a);
    return s;
}
static bool blocked(const P::Store& s, const std::string& url, uint32_t now = 1000, const P::Session& ses = P::Session())
{
    return P::decide(s, ses, url, now).verdict == P::kBlock;
}
// a fake KDF: deterministic, depends on pin, salt and rounds
static bool fakeKdf(const std::string& pin, const std::string& salt, int it, uint8_t out[32])
{
    for (int i = 0; i < 32; ++i) out[i] = uint8_t(i * 7 + it);
    for (size_t i = 0; i < pin.size(); ++i) out[i % 32] ^= uint8_t(pin[i] * 31 + i);
    for (size_t i = 0; i < salt.size(); ++i) out[(i + 5) % 32] ^= uint8_t(salt[i]);
    return true;
}

int main()
{
    // --- host normalisation ------------------------------------------------------------------------------------------
    EQ(P::normHost("WWW.Example.COM"), "www.example.com");
    EQ(P::normHost("example.com."), "example.com");
    EQ(P::normHost("example.com..."), "example.com");
    EQ(P::normHost("exa%6Dple.com"), "example.com");
    EQ(P::normHost("a..b"), "");
    EQ(P::normHost("ex ample.com"), "");
    EQ(P::normHost("2130706433"), "127.0.0.1");
    EQ(P::normHost("0x7f.1"), "127.0.0.1");
    EQ(P::normHost("0177.0.0.1"), "127.0.0.1");
    EQ(P::normHost("93.184.216.34"), "93.184.216.34");
    EQ(P::normHost("1.2.3.256"), "");                 // numeric, invalid: unreadable (fail closed)
    EQ(P::normHost("1.2.3.4.5"), "");
    EQ(P::normHost("[2001:DB8:0:0:0:0:0:1]"), "2001:db8::1");
    EQ(P::normHost("[::FFFF:127.0.0.1]"), "::ffff:7f00:1");
    EQ(P::normHost("[::1]"), "::1");
    EQ(P::normHost("[1::2::3]"), "");
    EQ(P::normHost("b\xc3\xbc" "cher.de"), "xn--bcher-kva.de");          // IDN -> punycode
    EQ(P::normHost("B\xc3\xbc" "cher.DE"), "xn--bcher-kva.de");
    EQ(P::normHost("\xe4\xbe\x8b\xe3\x81\x88.jp"), "xn--r8jz45g.jp");      // 例え.jp
    EQ(P::normHost("example\xe3\x80\x82" "com"), "example.com");         // ideographic full stop
    EQ(P::normHost("\xff.com"), "");                                      // broken UTF-8

    // --- list entries ------------------------------------------------------------------------------------------------
    EQ(P::entryKey("https://www.YouTube.com/watch?v=1"), "youtube.com");
    EQ(P::entryKey("  *.Example.org  "), "example.org");
    EQ(P::entryKey(".example.org"), "example.org");
    EQ(P::entryKey("user:pw@evil.com:8080/x"), "evil.com");
    EQ(P::entryKey("[2001:db8::1]:443"), "2001:db8::1");
    EQ(P::entryKey("www.com"), "www.com");     // "www." only dropped when something is left
    EQ(P::entryKey(""), "");
    EQ(P::entryKey("b\xc3\xbc" "cher.de"), "xn--bcher-kva.de");

    // --- matching with subdomains ------------------------------------------------------------------------------------
    CHECK(P::hostMatches("example.com", "example.com"));
    CHECK(P::hostMatches("a.b.example.com", "example.com"));
    CHECK(!P::hostMatches("evilexample.com", "example.com"));
    CHECK(!P::hostMatches("example.com.evil.net", "example.com"));
    CHECK(!P::hostMatches("example.com", "a.example.com"));
    CHECK(!P::hostMatches("10.0.0.1", "0.0.1"));

    // --- URL classification and bypass attempts ------------------------------------------------------------------------
    {
        const P::Store s = blockStore({ "youtube.com", "93.184.216.34", "xn--bcher-kva.de" });
        CHECK(blocked(s, "https://www.youtube.com/watch?v=x"));
        CHECK(blocked(s, "https://m.youtube.com/"));
        CHECK(blocked(s, "https://YOUTUBE.COM/"));                       // upper case
        CHECK(blocked(s, "HTTPS://WWW.YouTube.Com./"));                  // scheme case + trailing dot
        CHECK(blocked(s, "https://youtube.com../"));
        CHECK(blocked(s, "https://kids.example@youtube.com/"));          // userinfo is not the host
        CHECK(blocked(s, "https://user:pass@www.youtube.com:443/x"));
        CHECK(!blocked(s, "https://youtube.com@kids.example.org/"));     // ... and the real host is checked
        CHECK(blocked(s, "https://kids.example.org\\@youtube.com/") == false); // backslash ends the host (special scheme)
        CHECK(blocked(s, "http:youtube.com/"));                          // no slashes
        CHECK(blocked(s, "http:\\\\youtube.com\\"));                     // backslashes
        CHECK(blocked(s, "https://you\ttube.com/"));                     // tab stripped like WHATWG
        CHECK(blocked(s, "https://you%74ube.com/"));                     // percent-encoded host
        CHECK(blocked(s, "https://93.184.216.34/"));                     // IP literal on the list
        CHECK(blocked(s, "https://1572395042/"));                        // same IP, decimal form
        CHECK(blocked(s, "https://0x5d.0xb8.0xd8.0x22/"));               // same IP, hex form
        CHECK(blocked(s, "https://b\xc3\xbc" "cher.de/"));               // IDN typed raw
        CHECK(blocked(s, "https://xn--bcher-kva.de/"));                  // IDN as WebKit hands it
        CHECK(blocked(s, "https://shop.xn--bcher-kva.de/"));
        CHECK(blocked(s, "blob:https://www.youtube.com/1234-5678"));     // blob: of a blocked origin
        CHECK(blocked(s, "wss://www.youtube.com/socket"));
        CHECK(blocked(s, "ftp://youtube.com/"));
        CHECK(blocked(s, "https://1.2.3.999/"));                         // unreadable numeric host: fail closed
        CHECK(blocked(s, "https://[::1/"));                              // broken IPv6
        CHECK(blocked(s, "https:///"));                                  // no host at all
        CHECK(!blocked(s, "https://kids.example.org/"));
        CHECK(!blocked(s, "https://notyoutube.com/"));
        CHECK(!blocked(s, "data:text/html,<iframe src=https://youtube.com>"));   // the iframe navigates separately
        CHECK(!blocked(s, "javascript:location='https://youtube.com'"));         // runs in the (allowed) page
        CHECK(!blocked(s, "about:blank"));
        CHECK(!blocked(s, "about:srcdoc"));
        CHECK(!blocked(s, "omni://pages/start/"));
        CHECK(!blocked(s, "blob:null/1234"));
        CHECK(!blocked(s, "mailto:a@youtube.com"));
        CHECK(!blocked(s, "http://127.0.0.1:8765/downloads"));           // Omni's own apps
        CHECK(!blocked(s, "http://localhost/"));
        CHECK(!blocked(s, "http://[::1]:80/"));
    }
    {   // allow-list mode
        P::Store s = blockStore({}, { "kids.example.org", "www.pbskids.org" });
        s.mode = P::kAllowList;
        CHECK(!blocked(s, "https://kids.example.org/"));
        CHECK(!blocked(s, "https://games.kids.example.org/"));
        CHECK(!blocked(s, "https://pbskids.org/"));                      // "www." entry covers the bare domain
        CHECK(blocked(s, "https://example.org/"));                       // the parent is not allowed
        CHECK(blocked(s, "https://kids.example.org.evil.com/"));
        CHECK(blocked(s, "https://evil.com/?kids.example.org"));
        CHECK(blocked(s, "https://evil.com/#@kids.example.org"));
        CHECK(blocked(s, "https://kids.example.org@evil.com/"));
        CHECK(blocked(s, "https://kids.example.org%2eevil.com/") == true);   // %2e decodes to a dot: kids.example.org.evil.com
        CHECK(blocked(s, "https://93.184.216.34/"));                     // unlisted IP
        CHECK(blocked(s, "http://192.168.0.10/"));                       // LAN proxy: not exempt
        CHECK(blocked(s, "blob:https://evil.com/x"));
        CHECK(!blocked(s, "data:text/html,hi"));
        CHECK(!blocked(s, "http://127.0.0.1/"));
        CHECK(!blocked(s, "http://[::ffff:127.0.0.1]/"));
        CHECK(blocked(s, "http://[::ffff:7f:1]/"));                      // 0.127.0.1, not loopback
        // allow once
        P::Session ses;
        ses.allow("evil.com", 5000);
        CHECK(!blocked(s, "https://evil.com/", 6000, ses));
        CHECK(!blocked(s, "https://a.evil.com/", 6000, ses));
        CHECK(blocked(s, "https://evil.com/", 5000 + P::kOnceMs, ses));  // an hour later
        CHECK(blocked(s, "https://evil.com/", 4000, ses));          // wrap-safe: "before" counts as long ago
    }
    {   // inactive: nothing blocked
        P::Store s = blockStore({ "youtube.com" });
        s.enabled = false;
        CHECK(!blocked(s, "https://youtube.com/"));
        s.enabled = true; s.pin = P::Pin();
        CHECK(!blocked(s, "https://youtube.com/"));                      // no PIN: never active
        CHECK(!s.active());
    }
    {   // block mode: allow entries are exceptions
        const P::Store s = blockStore({ "google.com" }, { "classroom.google.com" });
        CHECK(blocked(s, "https://www.google.com/"));
        CHECK(!blocked(s, "https://classroom.google.com/c/1"));
        CHECK(P::decide(s, P::Session(), "https://www.google.com/", 0).host == "www.google.com");
    }

    // --- safe search -------------------------------------------------------------------------------------------------
    EQ(P::safeSearchUrl("https://www.google.com/search?q=cats"), "https://www.google.com/search?q=cats&safe=active");
    EQ(P::safeSearchUrl("https://www.google.com/search?q=cats&safe=off"), "https://www.google.com/search?q=cats&safe=active");
    EQ(P::safeSearchUrl("https://www.google.com/search?SAFE=off&q=cats&safe=off#top"), "https://www.google.com/search?safe=active&q=cats#top");
    EQ(P::safeSearchUrl("https://www.google.com/search?q=cats&safe=active"), "");
    EQ(P::safeSearchUrl("https://www.google.co.uk/search?q=cats"), "https://www.google.co.uk/search?q=cats&safe=active");
    EQ(P::safeSearchUrl("https://google.de/search?tbm=isch&q=x"), "https://google.de/search?tbm=isch&q=x&safe=active");
    EQ(P::safeSearchUrl("https://www.google.com/webhp?q=x"), "https://www.google.com/webhp?q=x&safe=active");
    EQ(P::safeSearchUrl("https://www.google.com/search"), "https://www.google.com/search?safe=active");
    EQ(P::safeSearchUrl("https://www.google.com/"), "");
    EQ(P::safeSearchUrl("https://www.google.com/maps?q=x"), "");
    EQ(P::safeSearchUrl("https://mail.google.com/search?q=x"), "");
    EQ(P::safeSearchUrl("https://google.evil.com/search?q=x"), "");
    EQ(P::safeSearchUrl("https://www.bing.com/search?q=cats"), "https://www.bing.com/search?q=cats&adlt=strict");
    EQ(P::safeSearchUrl("https://www.bing.com/images/search?q=cats&adlt=off"), "https://www.bing.com/images/search?q=cats&adlt=strict");
    EQ(P::safeSearchUrl("https://www.bing.com/search?q=cats&adlt=strict"), "");
    EQ(P::safeSearchUrl("https://duckduckgo.com/?q=cats"), "https://duckduckgo.com/?q=cats&kp=1");
    EQ(P::safeSearchUrl("https://duckduckgo.com/?q=cats&kp=-2"), "https://duckduckgo.com/?q=cats&kp=1");
    EQ(P::safeSearchUrl("https://html.duckduckgo.com/html/?q=cats"), "https://html.duckduckgo.com/html/?q=cats&kp=1");
    EQ(P::safeSearchUrl("https://duckduckgo.com/about"), "");
    EQ(P::safeSearchUrl("https://www.youtube.com/results?search_query=x"), "");   // not enforceable (documented)
    EQ(P::safeSearchUrl("https://WWW.GOOGLE.COM/search?q=a"), "https://WWW.GOOGLE.COM/search?q=a&safe=active");
    EQ(P::safeSearchUrl("data:text/html,x"), "");
    // idempotent: the rewritten URL needs no further rewrite (no reload loop)
    for (const char* u : { "https://www.google.com/search?q=a&safe=off&safe=images", "https://www.bing.com/search?q=a", "https://duckduckgo.com/?q=a&kp=-1" }) {
        const std::string r = P::safeSearchUrl(u);
        CHECK(!r.empty());
        EQ(P::safeSearchUrl(r), "");
    }

    // --- PIN -----------------------------------------------------------------------------------------------------------
    CHECK(P::validPin("1234"));
    CHECK(P::validPin("123456"));
    CHECK(!P::validPin("123"));
    CHECK(!P::validPin("1234567"));
    CHECK(!P::validPin("12a4"));
    CHECK(!P::validPin(""));
    {
        P::Pin p;
        const std::string salt(16, '\x5a');
        CHECK(P::makePin("4711", salt, P::kDefaultIterations, fakeKdf, &p));
        CHECK(p.ok());
        CHECK(p.hashHex.find("4711") == std::string::npos);
        CHECK(P::verifyPin(p, "4711", fakeKdf));
        CHECK(!P::verifyPin(p, "4712", fakeKdf));
        CHECK(!P::verifyPin(p, "47110", fakeKdf));
        CHECK(!P::makePin("12", salt, P::kDefaultIterations, fakeKdf, &p));
        CHECK(!P::makePin("1234", "short", P::kDefaultIterations, fakeKdf, &p));
        P::Pin bad = p; bad.hashHex[0] = bad.hashHex[0] == 'a' ? 'b' : 'a';
        CHECK(!P::verifyPin(bad, "4711", fakeKdf));
    }
#ifdef OPAR_TEST_OPENSSL
    {   // the real KDF the shell uses (OmniVault::deriveKey = PKCS5_PBKDF2_HMAC SHA-256), RFC 7914 / known vector
        uint8_t k[32];
        CHECK(OmniVault::deriveKey("password", "salt", 1, k));
        EQ(P::toHex(k, 32), "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b");
        std::string salt(16, '\0');
        CHECK(OmniVault::randomBytes(&salt[0], 16));
        P::Pin p;
        CHECK(P::makePin("2468", salt, P::kMinIterations, OmniVault::deriveKey, &p));
        CHECK(P::verifyPin(p, "2468", OmniVault::deriveKey));
        CHECK(!P::verifyPin(p, "2469", OmniVault::deriveKey));
        P::Store s; s.pin = p; s.enabled = true;
        const P::Store back = P::parse(P::serialize(s));
        CHECK(P::verifyPin(back.pin, "2468", OmniVault::deriveKey));
        CHECK(P::serialize(s).find("2468") == std::string::npos);
        fprintf(stderr, "real KDF: ok\n");
    }
#endif

    // --- limiter ------------------------------------------------------------------------------------------------------
    {
        P::Limiter l;
        for (int i = 0; i < P::kMaxFails - 1; ++i) CHECK(!l.failed(100));
        CHECK(l.triesLeft() == 1);
        CHECK(l.failed(100));                       // 5th wrong PIN: cooldown
        CHECK(l.locked(100));
        CHECK(l.remaining(100) == P::kCooldownSec);
        CHECK(l.failed(150));                       // while locked: still locked, nothing extended
        CHECK(l.remaining(150) == P::kCooldownSec - 50);
        CHECK(!l.locked(100 + P::kCooldownSec));
        CHECK(!l.failed(100 + P::kCooldownSec));    // a fresh round of 5
        CHECK(l.triesLeft() == P::kMaxFails - 1);
        l.succeeded();
        CHECK(l.triesLeft() == P::kMaxFails);
        P::Limiter far; far.lockUntil = 1000000;    // clock set back / file edited: at most the cooldown
        CHECK(far.remaining(10) == P::kCooldownSec);
        EQ(P::cooldownText(299), "Too many wrong PINs. Try again in 4:59");
    }

    // --- file --------------------------------------------------------------------------------------------------------
    {
        P::Store s = blockStore({ "youtube.com", "Example.ORG" }, { "kids.example.org" });
        s.mode = P::kAllowList; s.safeSearch = true; s.lockPrivate = true; s.lockSettings = true;
        s.limiter.fails = 2; s.limiter.lockUntil = 12345;
        const std::string text = P::serialize(s);
        bool ok = false;
        const P::Store b = P::parse(text, &ok);
        CHECK(ok);
        EQ(P::serialize(b), text);
        CHECK(b.active() && b.mode == P::kAllowList && b.safeSearch && b.lockPrivate && b.lockSettings);
        CHECK(b.block.count("example.org") && b.allow.count("kids.example.org"));
        CHECK(b.limiter.fails == 2 && b.limiter.lockUntil == 12345);
        // CRLF, junk lines, bad entries, an edited PIN record
        std::string crlf;
        for (char c : text) { if (c == '\n') crlf += '\r'; crlf += c; }
        EQ(P::serialize(P::parse(crlf)), text);
        const P::Store j = P::parse(std::string(P::kHeader) + "\nenabled\t1\njunk\nblock\t\nblock\t1.2.3.999\nblock\twww.Foo.com\npin\tpbkdf2-sha256\t100000\tzz\t00\n");
        CHECK(j.block.size() == 1 && j.block.count("foo.com"));
        CHECK(!j.pin.ok() && !j.active());           // no usable PIN: not active (the panel offers to set one)
        bool ok2 = true;
        CHECK(!P::parse("something else\nenabled\t1\n", &ok2).enabled);
        CHECK(!ok2);
        CHECK(!P::parse("").enabled);
        // list cap
        P::Store big;
        for (size_t i = 0; i < P::kMaxSites + 5; ++i) P::addSite(big.block, "s" + std::to_string(i) + ".com");
        CHECK(big.block.size() == P::kMaxSites);
        CHECK(P::addSite(big.block, "s1.com") == P::kAlready);
        CHECK(P::addSite(big.block, "new.com") == P::kFull);
        CHECK(P::addSite(big.block, "bad host") == P::kBad);
    }
    // --- texts ---------------------------------------------------------------------------------------------------------
    EQ(P::dots(2), "\xe2\x97\x8f \xe2\x97\x8f \xe2\x97\x8b \xe2\x97\x8b \xe2\x97\x8b \xe2\x97\x8b");
    CHECK(P::forgotBody().find("/data/omni/parental.txt") != std::string::npos);
    CHECK(P::blockedBody("youtube.com", P::kBlockList).find("youtube.com") == 0);
    EQ(P::summary(P::Store()), "Off");

    printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
