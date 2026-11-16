// OMNI_CONTINUE_WATCHING_V1: host tests for OmniContinueWatching.h (pure part of the start page's Continue watching row).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_continue_watching.cpp -o t && ./t
#include "OmniContinueWatching.h"
#include <cstdio>
#include <cstring>

namespace CW = OmniCw;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static std::string val(const char* u, const char* t, double p, double d, long long a, const char* extra = "")
{
    char b[4096];
    snprintf(b, sizeof b, "{\"u\":\"%s\",\"t\":\"%s\"%s,\"p\":%g,\"d\":%g,\"a\":%lld}", u, t, extra, p, d, a);
    return b;
}

int main()
{
    // flat JSON as the add-on's JSON.stringify writes it
    {
        std::map<std::string, std::string> s; std::map<std::string, double> n;
        CHECK(CW::parseFlat("{\"u\":\"https://e.com/a?b=1\",\"t\":\"Caf\\u00e9 \\\"x\\\" \\ud83c\\udfac\",\"p\":1421,\"d\":3600.5,\"a\":1700000000,\"z\":true,\"q\":null}", s, n));
        CHECK(s["u"] == "https://e.com/a?b=1");
        CHECK(s["t"] == "Caf\xC3\xA9 \"x\" \xF0\x9F\x8E\xAC");
        CHECK(n["p"] == 1421 && n["d"] == 3600.5 && n["a"] == 1700000000);
        CHECK(CW::parseFlat("{}", s, n));
        CHECK(!CW::parseFlat("[1421,3600,1]", s, n));                 // an 'r:' resume entry is an array
        CHECK(!CW::parseFlat("{\"u\":{\"x\":1}}", s, n));              // nested
        CHECK(!CW::parseFlat("{\"u\":\"open", s, n));                 // cut
        CHECK(!CW::parseFlat("{\"u\":\"a\"} junk", s, n));
        CHECK(!CW::parseFlat("{\"u\":\"a\nb\"}", s, n));               // raw control character
        s.clear(); n.clear();
        CHECK(CW::parseFlat("{\"t\":\"\\udc00 lone\"}", s, n) && s["t"] == "\xEF\xBF\xBD lone");
    }
    // entries: validity and the "worth a tile" rule
    {
        CW::Entry e;
        CHECK(CW::parseEntry("w:abc", val("https://e.com/v", "T", 1421, 3600, 5), e) && e.url == "https://e.com/v" && e.position == 1421 && e.at == 5);
        CHECK(CW::showable(e));
        CHECK(!CW::parseEntry("r:abc", val("https://e.com/v", "T", 1421, 3600, 5), e));      // not ours
        CHECK(!CW::parseEntry("w:abc", val("javascript:alert(1)", "T", 1421, 3600, 5), e));
        CHECK(!CW::parseEntry("w:abc", val("https://e.com/a b", "T", 1421, 3600, 5), e));
        CHECK(!CW::parseEntry("w:abc", "{\"u\":\"https://e.com/v\",\"p\":5}", e));             // no duration
        CHECK(!CW::parseEntry("w:a\tb", val("https://e.com/v", "T", 1421, 3600, 5), e));
        CHECK(!CW::parseEntry("w:" + std::string(200, 'k'), val("https://e.com/v", "T", 1421, 3600, 5), e));
        auto show = [](double p, double d) { CW::Entry x; x.url = "https://e.com/v"; x.position = p; x.duration = d; return CW::showable(x); };
        CHECK(!show(119, 3600));    // under 2 minutes watched
        CHECK(show(120, 3600));
        CHECK(show(3419, 3600));
        CHECK(!show(3420, 3600));   // 95 %: finished
        CHECK(!show(150, 170));     // short clip
    }
    // ranking: newest first, at most 6, one per address, junk and other keys ignored
    {
        std::map<std::string, std::string> kv;
        for (int i = 0; i < 9; ++i) kv["w:k" + std::to_string(i)] = val(("https://e.com/" + std::to_string(i)).c_str(), "T", 300, 1200, 100 + i);
        kv["w:dup"] = val("https://e.com/8", "Same page", 300, 1200, 50);
        kv["w:done"] = val("https://e.com/done", "Done", 1190, 1200, 999);
        kv["w:bad"] = "not json";
        kv["r:x"] = "[300,1200,999]";
        kv["settings"] = "1";
        kv["x:after"] = val("https://e.com/x", "T", 300, 1200, 9999);
        const auto list = CW::rank(kv);
        CHECK(list.size() == 6);
        CHECK(list[0].key == "w:k8" && list[5].key == "w:k3");
        for (auto& e : list) CHECK(e.key != "w:dup" && e.key != "w:done" && e.key != "x:after");
        CHECK(CW::rank(kv, 20).size() == 9);   // k0..k8; the older duplicate of /8 is dropped
        CHECK(CW::rank({}).empty());
    }
    // "12 min left"
    {
        CHECK(CW::leftText(2880, 3600) == "12 min left");
        CHECK(CW::leftText(2881, 3600) == "12 min left");     // 11:59 rounds up
        CHECK(CW::leftText(2879, 3600) == "13 min left");
        CHECK(CW::leftText(0, 3900) == "1 h 5 min left");
        CHECK(CW::leftText(0, 7200) == "2 h left");
        CHECK(CW::leftText(3570, 3600) == "Under 1 min left");
        CHECK(CW::leftText(3540, 3600) == "1 min left");
        CHECK(CW::percent(1800, 3600) == 50 && CW::percent(0, 3600) == 1 && CW::percent(3600, 3600) == 99 && CW::percent(5, 0) == 1);
    }
    // site and letter
    {
        CHECK(CW::site("https://www.Example.com/watch?v=1") == "example.com");
        CHECK(CW::site("http://user:pw@tv.example.org:8443/x#y") == "tv.example.org");
        CHECK(CW::site("https://[::1]:8080/") == "[::1]");
        CHECK(CW::site("nonsense") == "");
        CHECK(CW::letter("example.com") == "E" && CW::letter("9gag.com") == "9" && CW::letter("") == "?" && CW::letter("\xC3\xA9t\xC3\xA9.fr") == "?");
    }
    // the page JSON: escaped, safe as JavaScript source, empty title -> the site
    {
        CW::Entry a; a.key = "w:k1"; a.url = "https://www.example.com/v?a=1&b=\"2\""; a.title = "Ep </script> 1\xE2\x80\xA8x"; a.position = 1800; a.duration = 3600;
        CW::Entry b; b.key = "w:k2"; b.url = "https://other.net/v"; b.title = "   "; b.position = 600; b.duration = 1200;
        const std::string j = CW::pageJson({ a, b }, 1, "\xC3\x97 Resume");
        CHECK(j.find("\"k\":\"w:k1\"") != std::string::npos);
        CHECK(j.find("\"u\":\"https://www.example.com/v?a=1&b=\\\"2\\\"\"") != std::string::npos);
        CHECK(j.find("</script>") == std::string::npos && j.find("\\u003c/script>") != std::string::npos);
        CHECK(j.find("\xE2\x80\xA8") == std::string::npos && j.find("\\u2028") != std::string::npos);
        CHECK(j.find("\"t\":\"other.net\"") != std::string::npos);
        CHECK(j.find("\"s\":\"example.com\",\"l\":\"E\",\"p\":50,\"left\":\"30 min left\"") != std::string::npos);
        CHECK(j.find("\"focus\":1") != std::string::npos);
        CHECK(CW::pageJson({}, -1, "h").rfind("{\"items\":[]", 0) == 0);
        const std::string longTitle(500, 'x');
        CHECK(CW::cleanText(longTitle, CW::kTitleMax).size() == CW::kTitleMax + 3);
        std::string utf; for (int i = 0; i < 200; ++i) utf += "\xC3\xA9";   // 400 bytes of 2-byte characters
        const std::string cut = CW::cleanText(utf, 301);
        CHECK(cut.size() == 300 + 3 && cut.compare(0, 300, utf, 0, 300) == 0);
        CHECK(CW::cleanText("a\tb\nc", 10) == "a b c");
    }
    // the Square probe's answer
    {
        int i = -1; std::string k;
        CHECK(CW::parseProbe("2\tw:abc", i, k) && i == 2 && k == "w:abc");
        CHECK(!CW::parseProbe("", i, k));
        CHECK(!CW::parseProbe("-1\tw:abc", i, k));
        CHECK(!CW::parseProbe("1\tr:abc", i, k));       // only our own keys are ever removed
        CHECK(!CW::parseProbe("1\tw:a\"b", i, k));
    }
    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
