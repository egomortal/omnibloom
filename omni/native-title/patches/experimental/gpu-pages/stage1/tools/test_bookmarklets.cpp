// OMNI_BOOKMARKLETS_V1: host tests of the pure bookmarklet part (OmniBookmarklets.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_bookmarklets.cpp -o t && ./t      (run in tools/)
// With -DOBKL_MODEL -I<tree>/engine/entry (a tree with OMNI_BOOKMARKS_MANAGER_V1's OmniBookmarksModel.h) it also checks
// OmniBookmarkletsFile.h: long javascript: lines kept whole, every other line read / written as the model does.
#include "OmniBookmarklets.h"
#ifdef OBKL_MODEL
#include "OmniBookmarkletsFile.h"
#endif
#include <cstdio>
#include <string>

namespace K = OmniBookmarklets;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

int main()
{
    using std::string;
    // --- what counts as a bookmarklet ---
    CHECK(K::isBookmarklet("javascript:alert(1)"));
    CHECK(K::isBookmarklet("JavaScript:void(0)"));
    CHECK(K::isBookmarklet("  \x01javascript:x"));             // leading C0 / spaces trimmed
    CHECK(K::isBookmarklet("java\nscr\tipt:x"));               // tab / LF / CR removed anywhere (URL Standard)
    CHECK(K::isBookmarklet("javascript:"));
    CHECK(!K::isBookmarklet("javascript :x"));
    CHECK(!K::isBookmarklet("https://javascript.info/"));
    CHECK(!K::isBookmarklet("javascrip"));
    CHECK(!K::isBookmarklet(""));
    CHECK(!K::isBookmarklet("xjavascript:1"));
    CHECK(!K::isBookmarklet("vbscript:1"));

    // --- decoding as browsers do ---
    CHECK(K::sourceOf("javascript:alert(1)") == "alert(1)");
    CHECK(K::sourceOf("javascript:alert(%22hi%20there%22)") == "alert(\"hi there\")");
    CHECK(K::sourceOf("javascript:a%3Db") == "a=b");                 // upper-case hex
    CHECK(K::sourceOf("javascript:a%3db") == "a=b");                 // lower-case hex
    CHECK(K::sourceOf("javascript:1+1") == "1+1");                   // '+' is not a space
    CHECK(K::sourceOf("javascript:x%2") == "x%2");                   // short escape kept
    CHECK(K::sourceOf("javascript:x%zz%") == "x%zz%");               // bad escapes kept
    CHECK(K::sourceOf("javascript:%2541") == "%41");                 // decoded once only
    CHECK(K::sourceOf("javascript:a%0Ab") == "a\nb");                // encoded line breaks survive
    CHECK(K::sourceOf("javascript:a\nb") == "ab");                   // raw ones don't (URL clean-up)
    CHECK(K::sourceOf("javascript://x%0Aalert(1)") == "//x\nalert(1)");
    CHECK(K::sourceOf("  javascript:go()  ") == "go()");
    CHECK(K::sourceOf("JAVASCRIPT:q?a=1#frag") == "q?a=1#frag");     // query and fragment are part of the code
    CHECK(K::sourceOf("javascript:%E2%82%AC") == "\xe2\x82\xac");    // UTF-8 bytes -> the euro sign
    CHECK(K::sourceOf("javascript:\xe2\x82\xac") == "\xe2\x82\xac"); // raw non-ASCII kept
    CHECK(K::sourceOf("javascript:%FF") == "\xef\xbf\xbd");           // invalid byte -> U+FFFD
    CHECK(K::sourceOf("javascript:%C3") == "\xef\xbf\xbd");           // truncated sequence -> one U+FFFD
    CHECK(K::sourceOf("javascript:%C3x") == "\xef\xbf\xbdx");         // the breaking byte is read again
    CHECK(K::sourceOf("javascript:%E2%82") == "\xef\xbf\xbd");        // maximal subpart -> one U+FFFD
    CHECK(K::sourceOf("javascript:%ED%A0%80") == "\xef\xbf\xbd\xef\xbf\xbd\xef\xbf\xbd");   // surrogate: 3 x U+FFFD
    CHECK(K::sourceOf("javascript:%C0%AF") == "\xef\xbf\xbd\xef\xbf\xbd");                 // overlong
    CHECK(K::sourceOf("javascript:%F0%9F%98%80") == "\xf0\x9f\x98\x80");                   // 4-byte emoji
    CHECK(K::sourceOf("javascript:%F4%90%80%80") == "\xef\xbf\xbd\xef\xbf\xbd\xef\xbf\xbd\xef\xbf\xbd");   // > U+10FFFF
    CHECK(K::sourceOf("javascript:%EF%BB%BFx") == "x");              // UTF-8 decode drops a leading BOM
    CHECK(K::sourceOf("javascript:x%EF%BB%BF") == "x\xef\xbb\xbf");  // ... only a leading one
    CHECK(K::sourceOf("javascript:a%00b") == string("a\0b", 3));      // NUL kept (the shell passes the length)
    CHECK(K::sourceOf("https://x/") == "");
    // a typical real one (Kill Sticky, as browsers store it)
    {
        const string u = "javascript:(function()%7Bdocument.querySelectorAll('body%20*').forEach(function(n)%7Bvar%20p%3DgetComputedStyle(n).position%3Bif(p%3D%3D%3D'fixed'%7C%7Cp%3D%3D%3D'sticky')n.remove()%7D)%7D)()";
        CHECK(K::sourceOf(u) == "(function(){document.querySelectorAll('body *').forEach(function(n){var p=getComputedStyle(n).position;if(p==='fixed'||p==='sticky')n.remove()})})()");
    }

    // --- typed / pasted in "Add bookmarklet" ---
    {
        const string code = "// show passwords\nfor (const i of document.querySelectorAll('input[type=password]')) i.type = 'text';\t100%  ";
        const string u = K::fromTyped(code);
        CHECK(u.rfind("javascript:", 0) == 0);
        CHECK(u.find('\n') == string::npos && u.find('\t') == string::npos && u.find(' ') == string::npos);
        CHECK(K::sourceOf(u) == code);                                  // byte for byte, trailing spaces too
        CHECK(K::fromTyped("  JavaScript:alert(1)\n") == "javascript:alert(1)");
        CHECK(K::fromTyped("javascript:a\nb") == "javascript:ab");     // an address is cleaned as browsers clean it
        CHECK(K::fromTyped("javascript:a%0Ab") == "javascript:a%0Ab"); // already encoded: kept
        CHECK(K::fromTyped("javascript:a\x01" "b") == "javascript:a%01b");
        CHECK(K::fromTyped("") == "");
        CHECK(K::fromTyped("  \n ") == "");
        CHECK(K::fromTyped("javascript:") == "");
        CHECK(K::fromTyped("javascript:%20") == "");
        CHECK(K::fromTyped("%41") == "javascript:%2541");
        CHECK(K::sourceOf(K::fromTyped("%41")) == "%41");
        CHECK(K::encodeCode("a b") == "javascript:a%20b");
        const string bin = string("x\0y\x7f", 4);
        CHECK(K::sourceOf(K::encodeCode(bin)) == bin);
    }

    // --- SHA-256 (FIPS 180-4 / NIST vectors) ---
    CHECK(K::sha256Hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    CHECK(K::sha256Hex("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    CHECK(K::sha256Hex("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq") == "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
    CHECK(K::sha256Hex(string(1000000, 'a')) == "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
    CHECK(K::sha256Hex(string(55, 'a')).size() == 64);   // padding edges: 55, 56, 64 bytes
    CHECK(K::sha256Hex(string(56, 'a')) != K::sha256Hex(string(55, 'a')));
    CHECK(K::sha256Hex(string(64, 'a')) == "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb");
    // same code, different spelling: same key
    CHECK(K::keyOf(K::sourceOf("javascript:alert(%22x%22)")) == K::keyOf(K::sourceOf("JavaScript:alert(\"x\")")));
    CHECK(K::keyOf("a") != K::keyOf("b"));

    // --- consent store ---
    {
        const string k1 = K::keyOf("one"), k2 = K::keyOf("two"), k3 = K::keyOf("three");
        K::Consent c;
        CHECK(!c.has(k1));
        c.allow(k1); c.allow(k2); c.allow(k1);
        CHECK(c.keys.size() == 2 && c.keys.back() == k1);
        c.allow("not-a-key");
        CHECK(c.keys.size() == 2);
        const string text = K::serializeConsent(c);
        CHECK(text == k2 + "\n" + k1 + "\n");
        string messy = "junk\r\n" + k3 + "\r\n\n";
        for (char& ch : messy) if (ch >= 'a' && ch <= 'f') ch = char(ch - 32);   // upper-case hex is accepted
        messy += k2 + "  \n" + k3;
        const K::Consent p = K::parseConsent(messy);
        CHECK(p.keys.size() == 2 && p.keys[0] == k2 && p.keys[1] == k3 && p.has(k3) && !p.has(k1));
        CHECK(K::parseConsent(K::serializeConsent(p)).keys == p.keys);
        c.forget(k2);
        CHECK(!c.has(k2) && c.has(k1));
        K::Consent big;
        for (int i = 0; i < 1005; ++i) big.allow(K::keyOf(std::to_string(i)));
        CHECK(big.keys.size() == K::kConsentMax && !big.has(K::keyOf("4")) && big.has(K::keyOf("5")) && big.has(K::keyOf("1004")));
    }

    // --- decide ---
    {
        const string url = "javascript:document.body.style.filter%3D'invert(1)'";
        const string src = "document.body.style.filter='invert(1)'";
        K::Context c;
        c.hasTab = true; c.pageUrl = "https://Example.com:8443/a?b#c";
        K::Consent none, yes;
        yes.allow(K::keyOf(src));
        string s, k;
        CHECK(K::decide(c, url, none, &s, &k) == K::Verdict::Ask && s == src && k == K::keyOf(src));
        CHECK(K::decide(c, url, yes) == K::Verdict::Run);
        K::Context p = c; p.privateTab = true;
        CHECK(K::decide(p, url, yes) == K::Verdict::AskPrivate);    // private: asked every time, even after Always
        K::Context x = c; x.parental = true;
        CHECK(K::decide(x, url, yes) == K::Verdict::Parental);      // parental wins over everything
        x = c; x.omniPage = true;
        CHECK(K::decide(x, url, yes) == K::Verdict::OmniPage);
        x = c; x.pageUrl = "omni://pages/start";
        CHECK(K::decide(x, url, yes) == K::Verdict::OmniPage);
        x = c; x.reader = true;
        CHECK(K::decide(x, url, yes) == K::Verdict::Reader);
        x = c; x.savedCopy = true; x.pageUrl = "about:blank";
        CHECK(K::decide(x, url, yes) == K::Verdict::SavedCopy);
        x = c; x.pageUrl = "about:blank";
        CHECK(K::decide(x, url, yes) == K::Verdict::NotWeb);
        x = c; x.pageUrl = "file:///data/x.html";
        CHECK(K::decide(x, url, yes) == K::Verdict::NotWeb);
        x = c; x.hasTab = false;
        CHECK(K::decide(x, url, yes) == K::Verdict::NoPage);
        x = c; x.crashed = true;
        CHECK(K::decide(x, url, yes) == K::Verdict::NoPage);
        x = c; x.unloaded = true;
        CHECK(K::decide(x, url, yes) == K::Verdict::NoPage);
        CHECK(K::pageVerdict(c) == K::Verdict::Run);
        x = c; x.reader = true;
        CHECK(K::pageVerdict(x) == K::Verdict::Reader);
        x = c; x.parental = true;
        CHECK(K::pageVerdict(x) == K::Verdict::Parental);
        CHECK(K::decide(c, "javascript:%20%0A", yes) == K::Verdict::Empty);
        x = c; x.parental = true;
        CHECK(K::decide(x, "javascript:", yes) == K::Verdict::Parental);   // parental before the empty check too
        CHECK(K::decide(c, "javascript:" + string(K::kMaxBytes, 'x'), yes) == K::Verdict::TooBig);
        CHECK(K::decide(c, "javascript:" + string(K::kMaxBytes - 11, 'x'), none) == K::Verdict::Ask);   // exactly 64 KB
        // a short address cannot decode to more than it holds, so the source cap is the same cap
        CHECK(string(K::refusal(K::Verdict::Parental)).find("parental") != string::npos);
        CHECK(string(K::refusal(K::Verdict::Run)).empty());
        CHECK(K::askTitle(c.pageUrl) == "Run this bookmarklet on example.com?");
        CHECK(K::askTitle("https://user:pw@[::1]:80/") == "Run this bookmarklet on [::1]?");
        CHECK(K::askTitle("about:blank") == "Run this bookmarklet on this page?");
        CHECK(K::askSubtitle(false) == "It can read and change this page.");
        CHECK(K::askSubtitle(true).find("asked every time") != string::npos);
    }

    // --- texts ---
    CHECK(K::sizeText(1) == "1 byte" && K::sizeText(312) == "312 bytes" && K::sizeText(1024) == "1 KB");
    CHECK(K::sizeText(1229) == "1.2 KB" && K::sizeText(65536) == "64 KB");
    CHECK(K::rowDetail("javascript:abc") == "Bookmarklet \xc2\xb7 3 bytes");
    CHECK(K::shown("javascript:%41%42") == "bookmarklet, 2 bytes");
    CHECK(K::runScript("a()//c") == "a()//c\n;\"omni-bookmarklet-ran\"");

#ifdef OBKL_MODEL
    // --- bookmarks.txt with bookmarklets (OmniBookmarkletsFile.h over the tree's OmniBookmarksModel.h) ---
    {
        namespace M = OmniBookmarksModel;
        namespace F = OmniBookmarkletsFile;
        const string js = "javascript:" + string(20000, 'a');
        const string web = "https://example.com/" + string(3000, 'b');
        const string file = "https://a.com/\tA\n" + js + "\tBig one\tTools\n" + web + "\tLong web\n" + "https://z.com/\tZ\n";
        const auto list = F::parse(file);
        CHECK(list.size() == 5);                                  // the web line still splits at 2399 (as fgets did)
        CHECK(list[1].url == js && list[1].title == "Big one" && list[1].folder == "Tools");
        CHECK(list[2].url.size() == 2399 && list[4].url == "https://z.com/");
        CHECK(M::parse(file).size() == 13);                       // what the model alone made of it (cut in pieces)
        CHECK(F::serializeLine(list[1]) == js + "\tBig one\tTools\n");   // kept whole up to 64 KB
        const std::vector<M::Entry> kept { list[0], list[1], list[4] };   // (the cut web pieces don't round-trip, as before)
        CHECK(F::parse(F::serialize(kept)) == kept);
        const M::Entry w { web, "W", "" };
        CHECK(F::serializeLine(w) == M::serializeLine(w) && F::serializeLine(w).size() == 2048 + 3);   // web: as before
        const M::Entry huge { "javascript:" + string(70000, 'c'), "H", "" };
        CHECK(F::serializeLine(huge).size() == K::kMaxBytes + 3);
        const string over = "javascript:" + string(70000, 'd') + "\tX\n";
        CHECK(F::parse(over).size() == 3);                        // past its buffer the line splits again
        CHECK(F::parse(" JavaScript:x\tT\n")[0].url == " JavaScript:x");
        CHECK(F::parse("JavaScript:x\r\n")[0].title == "JavaScript:x");
        const M::Entry tabby { "javascript:a\tb\nc", "T\tt", "F\tf" };
        CHECK(F::serializeLine(tabby) == "javascript:a b c\tT t\tF f\n");   // one line whatever comes in
        CHECK(F::parse(string("javascript:a\0b\tT\n", 18))[0].url == "javascript:a");
        // a file without bookmarklets: same entries, same bytes as the model alone
        string plain;
        for (int i = 0; i < 520; ++i) plain += "https://s" + std::to_string(i) + ".com/\tS" + std::to_string(i) + (i % 3 ? "\tF" + std::to_string(i % 4) : string()) + "\r\n";
        plain += string(5000, 'x') + "\n\n\tno url\n";
        CHECK(F::parse(plain) == M::parse(plain) && F::parse(plain).size() == 500);
        CHECK(F::parse(plain, 600) == M::parse(plain, 600));
        CHECK(F::serialize(M::parse(plain, 600)) == M::serialize(M::parse(plain, 600)));
    }
#endif
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
