// OMNI_PAGE_INFO_V1: host tests of the pure part of Page info (OmniPageInfo.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_page_info.cpp -o t && ./t [script.js]   (run in tools/, or -I<tree>/engine/entry)
// With an argument the page script is written there too: node --check it, then node test_page_info_js.cjs script.js.
#include "OmniPageInfo.h"
#include <cstdio>
#include <string>

namespace P = OmniPageInfo;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

static bool ascii(const std::string& s)
{
    for (unsigned char c : s) if (c >= 0x80) return false;
    return true;
}

int main(int argc, char** argv)
{
    // --- hosts ---
    CHECK(P::hostOf("https://WWW.Example.COM./path?q#f") == "www.example.com");
    CHECK(P::hostOf("http://user:pw@host.test:8080/x") == "host.test");
    CHECK(P::hostOf("http://[::1]:8080/") == "::1");
    CHECK(P::hostOf("https://[2001:db8::1]/") == "2001:db8::1");
    CHECK(P::hostOf("http://[::1/") == "");
    CHECK(P::hostOf("about:blank") == "");
    CHECK(P::hostOf("https://a.b/c@d") == "a.b");   // '@' in the path is not user info

    // --- local hosts ---
    for (const char* h : { "localhost", "app.localhost", "127.0.0.1", "127.8.9.1", "10.0.0.5", "192.168.0.20", "172.16.0.1", "172.31.255.255",
                           "169.254.1.1", "0.0.0.0", "::1", "fd12:3456::1", "fc00::1", "fe80::1", "febf::1", "::ffff:192.168.0.1", "nas.local",
                           "printer.home.arpa", "router" })
        CHECK(P::localHost(h));
    for (const char* h : { "", "example.com", "8.8.8.8", "172.15.0.1", "172.32.0.1", "192.169.0.1", "2001:db8::1", "fec0::1", "::ffff:8.8.8.8",
                           "localhost.example.com", "256.1.1.1", "1.2.3", "100.64.0.1" })
        CHECK(!P::localHost(h));

    // --- classification + padlock ---
    {
        const auto s = P::classify("https://www.example.com/a");
        CHECK(s.kind == P::kSecure && P::padlock(s) && s.host == "www.example.com" && s.scheme == "https");
        CHECK(P::connectionValue(s) == "Secure (https)");
        CHECK(P::connectionDetail(s) == "Encrypted to www.example.com. Certificate details aren't available in this build");
        const auto h = P::classify("HTTP://Example.com/");
        CHECK(h.kind == P::kNotSecure && !P::padlock(h) && P::connectionValue(h) == "Not secure (http)");
        CHECK(P::connectionDetail(h).find("example.com") != std::string::npos);
        const auto l = P::classify("http://127.0.0.1:8080/app");
        CHECK(l.kind == P::kLocal && !P::padlock(l) && P::connectionValue(l) == "Local network (http)");
        CHECK(P::classify("http://192.168.0.10/").kind == P::kLocal);
        CHECK(P::classify("https://192.168.0.10/").kind == P::kSecure);   // encrypted wins, even at home
        CHECK(P::classify("omni://pages/start").kind == P::kInternal);
        CHECK(P::classify("about:blank").kind == P::kInternal);
        CHECK(P::classify("file:///data/x.html").kind == P::kFile);
        const auto d = P::classify("data:text/html,hi");
        CHECK(d.kind == P::kOther && P::connectionValue(d) == "No connection (data:)");
        CHECK(P::classify("blob:https://x.com/uuid").kind == P::kOther);
        CHECK(P::classify("").kind == P::kNone && P::connectionValue(P::classify("")) == "No page");
        CHECK(P::classify("no colon here").kind == P::kNone);
        CHECK(P::classify("https:///nohost").kind == P::kOther);
        CHECK(P::classify("http://").kind == P::kOther);
        CHECK(P::classify("ht tp://x").kind == P::kNone);
        CHECK(P::subtitle(P::classify("https://a.com/"), "Title") == "a.com");
        CHECK(P::subtitle(P::classify("about:blank"), "New tab") == "New tab");
        CHECK(P::subtitle(P::classify("about:blank"), "") == "Omni page");
        CHECK(P::subtitle(P::classify(""), "") == "No page");
    }

    // --- the answer ---
    {
        const auto r = P::parse("omni-page-info;lang=en-GB;w=1234;c=0;ck=3;ls=10;ss=2;ld=2430;dcl=1100;fb=120;nt=1;tb=49152");
        CHECK(r.ok && r.lang == "en-GB" && r.words == 1234 && r.cjk == 0 && r.cookies == 3 && r.local == 10 && r.session == 2);
        CHECK(r.loadMs == 2430 && r.readyMs == 1100 && r.firstByteMs == 120 && r.navType == 1 && r.bytes == 49152);
        CHECK(!P::parse("").ok && !P::parse("omni-site-clear;ls=1").ok && !P::parse("omni-page-info").ok);
        const auto e = P::parse("omni-page-info;");
        CHECK(e.ok && e.lang.empty() && e.cookies == -1 && e.loadMs == -1 && e.navType == -1);
        const auto bad = P::parse("omni-page-info;lang=e<n>;x;w=abc;ck=-1;ld=-5;nt=7;tb=9999999999999;w2=5;c=-3");
        CHECK(bad.ok && bad.lang == "en" && bad.words == 0 && bad.cookies == -1 && bad.loadMs == -1 && bad.navType == -1 && bad.bytes == -1 && bad.cjk == 0);
        const auto longLang = P::parse("omni-page-info;lang=abcdefghijklmnopqrstuvwxyz0123");
        CHECK(longLang.lang.size() == 24);
    }

    // --- formatting ---
    CHECK(P::grouped(0) == "0" && P::grouped(999) == "999" && P::grouped(1000) == "1,000" && P::grouped(1234567) == "1,234,567" && P::grouped(-4500) == "-4,500");
    CHECK(P::plural(1, "word", "words") == "1 word" && P::plural(2, "word", "words") == "2 words" && P::plural(0, "word", "words") == "0 words");
    CHECK(P::msText(-1) == "-" && P::msText(0) == "0 ms" && P::msText(850) == "850 ms" && P::msText(999) == "999 ms");
    CHECK(P::msText(1000) == "1 s" && P::msText(2430) == "2.4 s" && P::msText(2460) == "2.5 s" && P::msText(9960) == "10 s");
    CHECK(P::msText(12000) == "12 s" && P::msText(59400) == "59 s" && P::msText(60000) == "1 min" && P::msText(65000) == "1 min 5 s");
    CHECK(P::bytesText(-1) == "-" && P::bytesText(0) == "0 bytes" && P::bytesText(1) == "1 byte" && P::bytesText(900) == "900 bytes");
    CHECK(P::bytesText(1024) == "1 KB" && P::bytesText(1536) == "1.5 KB" && P::bytesText(49152) == "48 KB" && P::bytesText(2500000) == "2.4 MB");
    CHECK(P::bytesText(5LL * 1024 * 1024 * 1024) == "5 GB" && P::bytesText(1048064) == "1 MB");

    // --- reading time ---
    CHECK(P::readingMinutes(0, 0) == 0 && P::readingMinutes(1, 0) == 1 && P::readingMinutes(230, 0) == 1 && P::readingMinutes(231, 0) == 2);
    CHECK(P::readingMinutes(0, 500) == 1 && P::readingMinutes(0, 501) == 2 && P::readingMinutes(230, 500) == 2 && P::readingMinutes(-5, -5) == 0);
    CHECK(P::readingMinutes(2300, 0) == 10);
    {
        P::Report r; r.ok = true; r.words = 1234;
        CHECK(P::readingValue(r) == "About 6 min");
        CHECK(P::wordsText(r) == "1,234 words. An estimate: menus and footers may count");
        r.words = 40; CHECK(P::readingValue(r) == "Under a minute");
        r.words = 0; CHECK(P::readingValue(r) == "No text to read" && P::wordsText(r) == "No readable text on this page");
        r.cjk = 1200; CHECK(P::readingValue(r) == "About 3 min");
        CHECK(P::wordsText(r) == "1,200 characters (Chinese / Japanese / Korean). An estimate: menus and footers may count");
        r.words = 1; CHECK(P::wordsText(r).rfind("1 word and 1,200 characters", 0) == 0);
        P::Report none; CHECK(P::readingValue(none) == "-" && P::wordsText(none).empty());
    }

    // --- language ---
    {
        P::Report r; r.ok = true;
        CHECK(P::languageValue(r) == "Not stated by the page" && !P::translatable(r));
        r.lang = "en-GB"; CHECK(P::languageValue(r) == "English (en-GB)" && !P::translatable(r));
        r.lang = "EN"; CHECK(P::languageValue(r) == "English (EN)" && !P::translatable(r));
        r.lang = "ja"; CHECK(P::languageValue(r) == "Japanese (ja)" && P::translatable(r));
        r.lang = "pt_BR"; CHECK(P::languageValue(r) == "Portuguese (pt_BR)" && P::translatable(r));
        r.lang = "xx"; CHECK(P::languageValue(r) == "xx" && P::translatable(r));
        r.lang = "-x"; CHECK(!P::translatable(r));
        P::Report none; CHECK(P::languageValue(none) == "-");
        for (const char* c : { "ja", "zh", "ko", "es", "fr", "de", "pt", "it", "ru", "ar", "hi", "th", "vi", "id", "tr", "pl", "nl", "uk" })
            CHECK(P::languageName(c) != nullptr);   // every language the translate offer names
    }

    // --- load time ---
    {
        P::Report r = P::parse("omni-page-info;ld=2430;dcl=1100;fb=120;nt=1;tb=49152");
        CHECK(P::loadValue(r, false) == "2.4 s");
        CHECK(P::loadDetail(r) == "First byte 120 ms \xc2\xb7 Content ready 1.1 s \xc2\xb7 48 KB \xc2\xb7 Reloaded");
        r = P::parse("omni-page-info;ld=-1;dcl=900;fb=80;nt=0;tb=0");
        CHECK(P::loadValue(r, false) == "Still loading" && P::loadDetail(r) == "First byte 80 ms \xc2\xb7 Content ready 900 ms \xc2\xb7 From the cache \xc2\xb7 Opened");
        r = P::parse("omni-page-info;");
        CHECK(P::loadValue(r, true) == "Still loading" && P::loadValue(r, false) == "Not available");
        CHECK(P::loadDetail(r) == "This page's own load, not later in-page changes");
        r = P::parse("omni-page-info;nt=2;tb=-1");
        CHECK(P::loadDetail(r) == "Back / forward");
        P::Report none; CHECK(P::loadValue(none, true) == "-" && P::loadDetail(none).empty());
    }

    // --- cookies and site data ---
    {
        P::Report r = P::parse("omni-page-info;ck=3;ls=10;ss=2");
        CHECK(P::storageValue(r) == "3 cookies \xc2\xb7 12 stored items");
        r = P::parse("omni-page-info;ck=1;ls=0;ss=-1");
        CHECK(P::storageValue(r) == "1 cookie \xc2\xb7 0 stored items");
        r = P::parse("omni-page-info;ck=-1;ls=-1;ss=-1");
        CHECK(P::storageValue(r) == "Not readable on this page");
        r = P::parse("omni-page-info;ck=0;ls=-1;ss=-1");
        CHECK(P::storageValue(r) == "0 cookies");
        r = P::parse("omni-page-info;ck=-1;ls=1;ss=0");
        CHECK(P::storageValue(r) == "1 stored item");
        P::Report none; CHECK(P::storageValue(none) == "-");
        CHECK(std::string(P::kStorageDetail).find("HttpOnly") != std::string::npos);
    }

    // --- permissions ---
    CHECK(P::permissionsValue({}) == "None granted");
    CHECK(P::permissionsValue({ { "popups", 1 } }) == "Pop-ups allowed");
    CHECK(P::permissionsValue({ { "popups", 2 }, { "storage:a.com", 1 }, { "storage:b.com", 1 }, { "storage:c.com", 2 } })
          == "Pop-ups blocked \xc2\xb7 Cookie access for 2 sites \xc2\xb7 Cookie access blocked for 1 site");
    CHECK(P::permissionsValue({ { "storage:a.com", 0 }, { "other", 1 } }) == "None granted");

    // --- uBlock ---
    CHECK(P::ublockValue(true, true, false, true) == "Error");
    CHECK(P::ublockValue(false, false, true, true) == "Off everywhere");
    CHECK(P::ublockValue(true, false, true, true) == "Off for this site");
    CHECK(P::ublockValue(true, false, false, true) == "On" && P::ublockValue(true, false, true, false) == "On");
    CHECK(std::string(P::kUblockDetail).find("isn't available in this build") != std::string::npos);

    // --- panel texts ---
    CHECK(P::savedValue(0) == "None (defaults)" && P::savedValue(1) == "1 setting" && P::savedValue(4) == "4 settings");
    CHECK(std::string(P::kCertificateText) == "Certificate details aren't available in this build");
    CHECK(std::string(P::kReading) == "Reading\xe2\x80\xa6");

    // --- the script ---
    {
        const std::string s = P::script();
        CHECK(s.rfind("(function(){", 0) == 0);
        CHECK(s.size() > 40 && s.compare(s.size() - 5, 5, "})()\n") == 0);   // a whole expression, nothing to trim
        CHECK(s.find("3000000") != std::string::npos && s.find("getEntriesByType('navigation')") != std::string::npos);
        CHECK(s.find("'omni-page-info;'") != std::string::npos);
        CHECK(ascii(s));                                         // \u escapes only: no raw UTF-8 in the script
        CHECK(s.find("</script") == std::string::npos);
        CHECK(s.find("\\u3040") != std::string::npos);           // the escape reached the script as text
        if (argc > 1) {
            FILE* f = std::fopen(argv[1], "wb");
            CHECK(f != nullptr);
            if (f) { std::fwrite(s.data(), 1, s.size(), f); std::fclose(f); }
        }
    }

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
