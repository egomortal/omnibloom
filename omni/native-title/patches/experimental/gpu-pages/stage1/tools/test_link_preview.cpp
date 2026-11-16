// OMNI_LINK_PREVIEW_V1: host tests of OmniLinkPreview.h (pure part of "Show link address on hover").
// g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_link_preview.cpp -o t && ./t
#include "OmniLinkPreview.h"
#include <cstdio>
#include <string>

namespace L = OmniLinkPreview;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)
#define CHECK_EQ(a, b) do { ++checks; const std::string x_ = (a), y_ = (b); if (x_ != y_) { ++fails; std::printf("FAIL %s:%d %s\n  got  [%s]\n  want [%s]\n", __FILE__, __LINE__, #a, x_.c_str(), y_.c_str()); } } while (0)

static std::string puny(const char* s)
{
    std::vector<uint32_t> v;
    return L::punycodeDecode(s, v) ? L::encodeUtf8(v) : std::string("<bad>");
}

int main()
{
    // --- UTF-8 helpers
    CHECK_EQ(L::encodeUtf8(L::decodeUtf8("a\xc3\xbc\xe2\x80\xa6\xf0\x9f\x98\x80")), "a\xc3\xbc\xe2\x80\xa6\xf0\x9f\x98\x80");
    CHECK(L::decodeUtf8("\xff").size() == 1 && L::decodeUtf8("\xff")[0] == 0xFFFD);
    CHECK(L::decodeUtf8("\xc0\xaf").size() == 2);   // overlong
    CHECK(L::decodeUtf8("\xe2\x80").size() == 2);   // truncated
    CHECK(L::utf8Length("m\xc3\xbcnchen") == 7);
    CHECK_EQ(L::utf8Cut("ab\xc3\xbc", 3), "ab");
    CHECK_EQ(L::utf8Cut("ab\xc3\xbc", 4), "ab\xc3\xbc");
    CHECK_EQ(L::tailChars("abcdef", 3), "def");
    CHECK_EQ(L::headChars("abcdef", 2), "ab");

    // --- punycode (vectors from Python's punycode codec)
    CHECK_EQ(puny("mnchen-3ya"), "m\xc3\xbcnchen");
    CHECK_EQ(puny("bcher-kva"), "b\xc3\xbc" "cher");
    CHECK_EQ(puny("80ak6aa92e"), "\xd0\xb0\xd1\x80\xd1\x80\xd3\x8f\xd0\xb5");   // аррӏе
    CHECK_EQ(puny("wgv71a119e"), "\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e");       // 日本語
    CHECK_EQ(puny("fsqu00a"), "\xe4\xbe\x8b\xe5\xad\x90");                      // 例子
    CHECK_EQ(puny("pypal-4ve"), "p\xd0\xb0ypal");                              // pаypal (Cyrillic а)
    CHECK_EQ(puny("h1alffa9f"), "\xd1\x80\xd0\xbe\xd1\x81\xd1\x81\xd0\xb8\xd1\x8f");   // россия
    CHECK_EQ(puny("3e0b707e"), "\xed\x95\x9c\xea\xb5\xad");                     // 한국
    CHECK_EQ(puny("abc-"), "<bad>");          // nothing encoded
    CHECK_EQ(puny("a!b"), "<bad>");
    CHECK_EQ(puny("zzzzzzzzzzzzzzzzzzzz"), "<bad>");   // overflow / out of range
    CHECK_EQ(puny(""), "<bad>");

    // --- host display: IDN shown when safe, punycode + warning when not
    {
        L::HostView h = L::viewHost("xn--mnchen-3ya.de");
        CHECK(h.idn && !h.deceptive); CHECK_EQ(h.shown, "m\xc3\xbcnchen.de");
        h = L::viewHost("xn--80ak6aa92e.com");   // аррӏе.com: whole-script Cyrillic look-alike of apple.com
        CHECK(h.deceptive); CHECK_EQ(h.shown, "xn--80ak6aa92e.com"); CHECK_EQ(h.unicode, "\xd0\xb0\xd1\x80\xd1\x80\xd3\x8f\xd0\xb5.com");
        h = L::viewHost("xn--pypal-4ve.com");    // Latin + Cyrillic mixed
        CHECK(h.deceptive); CHECK_EQ(h.shown, "xn--pypal-4ve.com");
        h = L::viewHost("xn--h1alffa9f.xn--p1ai");   // россия.рф: Cyrillic under a Cyrillic TLD, fine
        CHECK(!h.deceptive); CHECK_EQ(h.shown, "\xd1\x80\xd0\xbe\xd1\x81\xd1\x81\xd0\xb8\xd1\x8f.\xd1\x80\xd1\x84");
        h = L::viewHost("xn--h1alffa9f.com");    // россия.com: Cyrillic, but not made only of Latin look-alikes
        CHECK(!h.deceptive);
        h = L::viewHost("xn--wgv71a119e.jp");
        CHECK(!h.deceptive); CHECK_EQ(h.shown, "\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e.jp");
        h = L::viewHost("xn--zz-nnn.com");       // undecodable xn-- label
        CHECK(h.deceptive && h.shown == "xn--zz-nnn.com");
        h = L::viewHost("www.example.com");
        CHECK(!h.idn && !h.deceptive && h.shown == "www.example.com");
    }
    // scripts
    CHECK(L::scriptOf(0x430) == L::Script::Cyrillic);
    CHECK(L::scriptOf(0x217C) == L::Script::Bad);   // small roman numeral fifty (ⅼ)
    CHECK(L::scriptOf(0x200B) == L::Script::Bad);   // zero width space
    CHECK(L::scriptOf(0x131) == L::Script::Bad);    // dotless i
    CHECK(L::scriptOf(0xE9) == L::Script::Latin);
    // Japanese / Korean mixes with Latin allowed, Latin + Greek not; a Greek word with non-look-alike letters is fine
    CHECK(!L::viewHost("xn--abc-v08fl0d.jp").deceptive);        // abc日本
    CHECK(!L::viewHost("xn--eckwd4c7cu47r2wf.jp").deceptive);   // ドメイン名例
    CHECK(!L::viewHost("xn--abc-lt8lk11n.kr").deceptive);       // 한국abc
    CHECK(L::viewHost("xn--ac-f9b.com").deceptive);             // aβc
    CHECK(!L::viewHost("xn--hxargifdar.com").deceptive);        // ελληνικά
    CHECK(L::viewHost("xn--0xad.com").deceptive);               // ρο: only Latin look-alikes ("po")

    // --- skeleton
    CHECK_EQ(L::skeleton("paypa1"), "paypal");
    CHECK_EQ(L::skeleton("g00gle"), "google");
    CHECK_EQ(L::skeleton("rnicrosoft"), "microsoft");
    CHECK_EQ(L::skeleton("\xd0\xb0\xd1\x80\xd1\x80\xd3\x8f\xd0\xb5"), "apple");
    CHECK_EQ(L::skeleton("PayPal"), "paypal");

    // --- registrable domain
    CHECK_EQ(L::registrableDomain("www.example.com"), "example.com");
    CHECK_EQ(L::registrableDomain("a.b.example.co.uk"), "example.co.uk");
    CHECK_EQ(L::registrableDomain("news.bbc.co.uk"), "bbc.co.uk");
    CHECK_EQ(L::registrableDomain("alice.github.io"), "alice.github.io");
    CHECK_EQ(L::registrableDomain("x.alice.github.io"), "alice.github.io");
    CHECK_EQ(L::registrableDomain("bucket.s3.amazonaws.com"), "bucket.s3.amazonaws.com");
    CHECK_EQ(L::registrableDomain("paypal.com.evil.xyz"), "evil.xyz");
    CHECK_EQ(L::registrableDomain("192.168.0.10"), "192.168.0.10");
    CHECK_EQ(L::registrableDomain("[::1]"), "[::1]");
    CHECK_EQ(L::registrableDomain("Example.COM."), "example.com");
    CHECK_EQ(L::registrableDomain("localhost"), "localhost");
    CHECK_EQ(L::registrableDomain("shop.example.com.au"), "example.com.au");

    // --- what the text claims
    CHECK_EQ(L::domainInText("paypal.com"), "paypal.com");
    CHECK_EQ(L::domainInText("  PayPal.com  "), "paypal.com");
    CHECK_EQ(L::domainInText("https://www.paypal.com/signin?x=1"), "www.paypal.com");
    CHECK_EQ(L::domainInText("example.com:8080/a"), "example.com");
    CHECK_EQ(L::domainInText("\xc2\xa0" "bbc.co.uk\xc2\xa0"), "bbc.co.uk");
    CHECK_EQ(L::domainInText("Read more"), "");
    CHECK_EQ(L::domainInText("Visit paypal.com"), "");
    CHECK_EQ(L::domainInText("me@paypal.com"), "");
    CHECK_EQ(L::domainInText("readme.md"), "");          // a file name
    CHECK_EQ(L::domainInText("setup.py"), "");
    CHECK_EQ(L::domainInText("https://setup.py/x"), "setup.py");   // explicit: counts
    CHECK_EQ(L::domainInText("www.example.md"), "www.example.md");
    CHECK_EQ(L::domainInText("version 1.2"), "");
    CHECK_EQ(L::domainInText("1.2.3"), "");
    CHECK_EQ(L::domainInText("Node.js"), "");
    CHECK_EQ(L::domainInText("example.com/very/long/path\xe2\x80\xa6"), "example.com");
    CHECK_EQ(L::domainInText("examp\xe2\x80\xa6"), "");
    CHECK_EQ(L::domainInText("exam\xe2\x80\xa6.com"), "");   // an ellipsis inside the host: truncated, not trusted
    CHECK_EQ(L::domainInText(""), "");
    CHECK_EQ(L::domainInText("-bad.com"), "");

    // --- URL parsing
    {
        L::Url u = L::parseUrl("https://user:pw@Example.com:8443/a/b?q=1#frag");
        CHECK(u.ok && u.hierarchical); CHECK_EQ(u.scheme, "https"); CHECK_EQ(u.user, "user:pw"); CHECK_EQ(u.host, "example.com");
        CHECK_EQ(u.port, "8443"); CHECK_EQ(u.path, "/a/b"); CHECK_EQ(u.query, "q=1"); CHECK_EQ(u.fragment, "frag");
        u = L::parseUrl("http://[::1]:8080/x");
        CHECK_EQ(u.host, "[::1]"); CHECK_EQ(u.port, "8080");
        u = L::parseUrl("mailto:a@b.com");
        CHECK(u.ok && !u.hierarchical && u.scheme == "mailto" && u.path == "a@b.com");
        CHECK(!L::parseUrl("no scheme here").ok);
        CHECK(!L::parseUrl(":x").ok);
    }

    // --- shortening
    CHECK_EQ(L::shorten("example.com", "/news"), "example.com/news");
    CHECK_EQ(L::shorten("example.com", "/news/article-about-something", 25), "example.com/news/article\xe2\x80\xa6");
    CHECK(L::utf8Length(L::shorten("example.com", "/news/article-about-something", 25)) == 25);
    CHECK_EQ(L::shorten("very-long-subdomain.example.com", "/x", 12), "\xe2\x80\xa6" "example.com");
    CHECK(L::utf8Length(L::shorten(std::string(200, 'a') + ".com", "/" + std::string(300, 'b'))) == L::kMaxChars);

    // --- the preview
    {
        L::Preview p = L::make("https://example.com/news/article-about-the-thing-that-happened-yesterday-in-town?id=5", "Read more");
        CHECK(p.kind == L::Kind::Web && p.secure && !p.warn);
        CHECK(L::utf8Length(p.text) == L::kMaxChars);
        CHECK_EQ(L::headChars(p.text, 25), "example.com/news/article-");
        CHECK_EQ(L::tailChars(p.text, 1), "\xe2\x80\xa6");
        p = L::make("https://www.example.com/", "");
        CHECK_EQ(p.text, "example.com"); CHECK(p.shown() == "example.com");
        p = L::make("http://example.com/a?b=1", "x");
        CHECK(!p.secure); CHECK_EQ(p.text, "example.com/a?\xe2\x80\xa6");
        p = L::make("http://example.com:8080/a", "");
        CHECK_EQ(p.text, "example.com:8080/a");
        p = L::make("https://example.com:443/", "");
        CHECK_EQ(p.text, "example.com");
        p = L::make("javascript:void(0)", "Menu");
        CHECK(p.kind == L::Kind::Script && p.text == "Script link" && !p.warn && !p.secure);
        p = L::make("JavaScript:alert(1)", "paypal.com");
        CHECK(p.kind == L::Kind::Script);
        p = L::make("data:text/html;base64,PGgxPg==", "");
        CHECK(p.kind == L::Kind::Data && p.text == "Data link");
        p = L::make("mailto:someone@example.com", "Mail us");
        CHECK(p.kind == L::Kind::Other && p.text == "mailto:someone@example.com");
        p = L::make("   ", "x");
        CHECK(p.kind == L::Kind::None);
        p = L::make("", "x");
        CHECK(p.kind == L::Kind::None);
    }
    // phishing hints
    {
        L::Preview p = L::make("https://paypa1-login.xyz/verify", "paypal.com");
        CHECK(p.warn && p.reason == L::Reason::TextMismatch);
        CHECK_EQ(p.shown(), "paypa1-login.xyz/verify \xc2\xb7 not paypal.com");
        p = L::make("https://paypa1.com/", "paypal.com");   // same skeleton: a look-alike name
        CHECK(p.warn && p.reason == L::Reason::LookAlike);
        CHECK_EQ(p.note, "not paypal.com");
        p = L::make("https://paypal.com.evil.xyz/login", "https://www.paypal.com/login");
        CHECK(p.warn && p.reason == L::Reason::TextMismatch); CHECK_EQ(p.note, "not paypal.com");
        p = L::make("https://www.paypal.com/signin", "paypal.com");   // same site: fine
        CHECK(!p.warn);
        p = L::make("https://accounts.google.com/x", "mail.google.com");
        CHECK(!p.warn);
        p = L::make("https://t.co/abc123", "example.com/article\xe2\x80\xa6");   // X/Twitter shows the destination: fine
        CHECK(!p.warn);
        p = L::make("https://bob.github.io/", "alice.github.io");
        CHECK(p.warn);
        p = L::make("https://xn--80ak6aa92e.com/", "Apple");   // аррӏе.com
        CHECK(p.warn && p.reason == L::Reason::DeceptiveIdn);
        CHECK_EQ(p.shown(), "xn--80ak6aa92e.com \xc2\xb7 look-alike letters");
        p = L::make("https://xn--80ak6aa92e.com/", "apple.com");   // the text claim wins (more telling)
        CHECK(p.reason == L::Reason::LookAlike || p.reason == L::Reason::TextMismatch);
        p = L::make("https://xn--mnchen-3ya.de/", "m\xc3\xbcnchen.de");   // IDN text = IDN target
        CHECK(!p.warn); CHECK_EQ(p.text, "m\xc3\xbcnchen.de");
        p = L::make("https://xn--mnchen-3ya.de/", "xn--mnchen-3ya.de");
        CHECK(!p.warn);
        p = L::make("https://paypal.com@evil.example/", "Sign in");
        CHECK(p.warn && p.reason == L::Reason::UserInfo); CHECK_EQ(p.note, "not paypal.com");
        CHECK_EQ(p.text, "evil.example");
        p = L::make("https://bob:secret@example.com/", "Sign in");
        CHECK(p.warn && p.note == "hidden user name");
        p = L::make("https://example.com/readme.md", "readme.md");   // a file name, not a claim
        CHECK(!p.warn);
        p = L::make("http://192.168.0.1/", "router.example.com");
        CHECK(p.warn);
        p = L::make("https://example.com/", std::string(300, 'a') + ".com");   // text too long to be an address: ignored
        CHECK(!p.warn);
        p = L::make("https://evil.xyz/", "a-very-long-subdomain-name-for-testing.paypal.com");
        CHECK(p.warn && L::utf8Length(p.note) <= 4 + L::kNoteChars);
    }

    // --- dwell
    {
        L::Dwell d;
        CHECK(!d.update("https://a/", true, 1000));
        CHECK(!d.update("https://a/", true, 1100));      // still moving
        CHECK(!d.update("https://a/", false, 1200));     // resting 100 ms
        CHECK(!d.update("https://a/", false, 1349));
        CHECK(d.update("https://a/", false, 1350));      // 250 ms at rest
        CHECK(d.update("https://a/", true, 1400));       // moving within the same link: stays
        CHECK(!d.update("https://b/", false, 1410));     // another link: hidden at once
        CHECK(!d.update("https://b/", false, 1600));
        CHECK(d.update("https://b/", false, 1660));
        CHECK(!d.update("", false, 1700));               // off the link
        CHECK(d.url.empty() && !d.shown);
        CHECK(!d.update("https://b/", false, 0xFFFFFFF0u));   // tick wrap
        CHECK(d.update("https://b/", false, 0xFFFFFFF0u + 300));
    }

    // --- placement
    {
        L::Rect r = L::place(300, 32, 1280, 688, 640, 300, 0, 0, 0);
        CHECK(r.x == 12 && r.y == 688 - 10 - 32 && r.w == 300 && r.h == 32);
        CHECK(r.y + r.h <= 688);   // never into the bottom button bar
        r = L::place(300, 32, 1280, 688, 100, 660, 0, 0, 0);   // pointer on it: other corner
        CHECK(r.x == 1280 - 12 - 300);
        r = L::place(300, 32, 1280, 688, 640, 300, 200, 1080, 688 - 18 - 44);   // a wide toast: lifted above it
        CHECK(r.y + r.h <= 688 - 18 - 44 - 8);
        r = L::place(100, 32, 1280, 688, 640, 300, 500, 780, 688 - 18 - 44);    // a narrow toast: no overlap, stays
        CHECK(r.y == 688 - 10 - 32);
        r = L::place(300, 32, 1280, 720, 640, 300, 0, 0, 0);    // bars hidden: page reaches the screen bottom
        CHECK(r.y + r.h == 710);
    }

    // --- texts
    CHECK_EQ(L::settingLabel(), "Show link address on hover");
    CHECK_EQ(L::settingValue(true), "On");
    CHECK_EQ(L::toggledNotice(false), "Link address on hover: Off");

    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
