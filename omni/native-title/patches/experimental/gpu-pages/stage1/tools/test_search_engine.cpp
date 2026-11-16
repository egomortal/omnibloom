// OMNI_SEARCH_ENGINE_V1: host tests for engine/entry/OmniSearchEngine.h (written by apply_search_engine.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_search_engine.cpp -o t && ./t
#include "OmniSearchEngine.h"
#include <cstdio>
#include <cstring>
#include <set>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniSearchEngine;

static bool has(const std::string& s, const char* part) { return s.find(part) != std::string::npos; }

int main()
{
    // table: saved indexes 0..3 keep their old meaning (omniFxEngines order before OMNI_SEARCH_ENGINE_V1)
    CHECK(!strcmp(kEngines[0].name, "Google") && !strcmp(kEngines[1].name, "DuckDuckGo") && !strcmp(kEngines[2].name, "Bing")
          && !strcmp(kEngines[3].name, "Startpage"));
    CHECK(!strcmp(kEngines[kBrave].name, "Brave") && !strcmp(kEngines[kEcosia].name, "Ecosia") && !strcmp(kEngines[kQwant].name, "Qwant"));
    CHECK(kCount == 8 && kDefault == kGoogle);
    for (int i = 0; i < kCount; ++i) {
        if (i == kCustom) { CHECK(!*kEngines[i].tmpl && !*kEngines[i].suggest); continue; }
        CHECK(validTemplate(kEngines[i].tmpl));                               // built-ins pass the custom rules too
        CHECK(validTemplate(kEngines[i].suggest));
        CHECK(std::string(kEngines[i].action).rfind("https://", 0) == 0);
    }
    { std::set<int> seen(kOrder, kOrder + kCount); CHECK(seen.size() == size_t(kCount)); CHECK(*seen.begin() == 0 && *seen.rbegin() == kCount - 1); }
    { std::set<std::string> keys; for (const auto& e : kEngines) keys.insert(e.key); CHECK(keys.size() == size_t(kCount)); }

    // settings order: DuckDuckGo / Google / Bing / Brave / Startpage / Ecosia / Qwant / Custom, wrapping both ways
    CHECK(step(kDuckDuckGo, 1) == kGoogle && step(kGoogle, 1) == kBing && step(kBing, 1) == kBrave && step(kBrave, 1) == kStartpage);
    CHECK(step(kStartpage, 1) == kEcosia && step(kEcosia, 1) == kQwant && step(kQwant, 1) == kCustom && step(kCustom, 1) == kDuckDuckGo);
    CHECK(step(kDuckDuckGo, -1) == kCustom && step(kGoogle, -1) == kDuckDuckGo && step(kStartpage, -1) == kBrave);
    { int e = kGoogle; for (int i = 0; i < kCount; ++i) e = step(e, 1); CHECK(e == kGoogle); }
    CHECK(clampIndex(-1) == kDefault && clampIndex(99) == kDefault && clampIndex(kQwant) == kQwant);
    CHECK(step(42, 1) == kBing);   // a bad saved value counts as the default

    // encoding: RFC 3986 unreserved kept, UTF-8 bytes, space %20, reserved characters encoded
    CHECK(encode("cats") == "cats");
    CHECK(encode("lofi beats") == "lofi%20beats");
    CHECK(encode("a+b=c&d") == "a%2Bb%3Dc%26d");
    CHECK(encode("100% #1 ?/") == "100%25%20%231%20%3F%2F");
    CHECK(encode("v1.2_x-y~z") == "v1.2_x-y~z");
    CHECK(encode("caf\xC3\xA9") == "caf%C3%A9");                                     // café
    CHECK(encode("\xE6\x97\xA5\xE6\x9C\xAC") == "%E6%97%A5%E6%9C%AC");                // 日本
    CHECK(encode("\xF0\x9F\x90\xB1") == "%F0%9F%90%B1");                              // cat emoji (4 bytes)
    CHECK(encode("\"<'>`") == "%22%3C%27%3E%60");

    // cleaning: trimmed, control characters -> space, capped on a UTF-8 boundary
    CHECK(cleanQuery("  cats \n") == "cats");
    CHECK(cleanQuery("a\tb\x01" "c") == "a b c");
    CHECK(cleanQuery("a  b") == "a  b");
    CHECK(cleanQuery(" \t\r\n").empty());
    { std::string q(kMaxQuery - 1, 'a'); q += "\xC3\xA9"; q += "zz"; const std::string c = cleanQuery(q);
      CHECK(c.size() == kMaxQuery - 1 && c.back() == 'a'); }                          // the 2-byte é would straddle the cap: dropped
    { std::string q(kMaxQuery - 2, 'a'); q += "\xC3\xA9"; q += "zz"; CHECK(cleanQuery(q).size() == kMaxQuery); }   // é fits exactly
    { std::string q(kMaxQuery + 50, 'b'); CHECK(cleanQuery(q).size() == kMaxQuery); }

    // search URLs
    CHECK(urlFor(kGoogle, "", "lofi beats") == "https://www.google.com/search?q=lofi%20beats");
    CHECK(urlFor(kDuckDuckGo, "", "caf\xC3\xA9") == "https://duckduckgo.com/?q=caf%C3%A9");
    CHECK(urlFor(kBing, "", " x ") == "https://www.bing.com/search?q=x");
    CHECK(urlFor(kBrave, "", "a&b") == "https://search.brave.com/search?q=a%26b");
    CHECK(urlFor(kStartpage, "", "q") == "https://www.startpage.com/do/search?q=q");
    CHECK(urlFor(kEcosia, "", "trees") == "https://www.ecosia.org/search?q=trees");
    CHECK(urlFor(kQwant, "", "x y") == "https://www.qwant.com/?q=x%20y");
    CHECK(urlFor(kCustom, "https://search.example.org/find?lang=en&q=%s&safe=1", "a b") == "https://search.example.org/find?lang=en&q=a%20b&safe=1");
    CHECK(urlFor(kCustom, "https://example.com/search/%s/page", "x/y") == "https://example.com/search/x%2Fy/page");   // %s in the path
    CHECK(urlFor(kCustom, "http://bad.example/?q=%s", "x") == "https://www.google.com/search?q=x");               // invalid: default
    CHECK(urlFor(99, "", "x") == "https://www.google.com/search?q=x");
    CHECK(urlFor(kGoogle, "", kSentinel) == std::string("https://www.google.com/search?q=") + kSentinel);       // sentinel survives

    // effective engine
    CHECK(effective(kBing, false, false) == kBing);
    CHECK(effective(kBing, false, true) == kGoogle);                                  // self-test modes: Google, as before
    CHECK(effective(kCustom, false, false) == kGoogle && effective(kCustom, true, false) == kCustom);
    CHECK(effective(-5, true, false) == kGoogle);

    // suggestions: per stored engine; Custom never (not even to the fallback); query encoded
    CHECK(suggestUrlFor(kGoogle, "lofi beats") == "https://suggestqueries.google.com/complete/search?client=firefox&ie=utf-8&oe=utf-8&q=lofi%20beats");
    CHECK(suggestUrlFor(kDuckDuckGo, "a") == "https://duckduckgo.com/ac/?type=list&q=a");
    CHECK(suggestUrlFor(kEcosia, "\xC3\xA9") == "https://ac.ecosia.org/autocomplete?q=%C3%A9&type=list");
    CHECK(suggestUrlFor(kQwant, "x") == "https://api.qwant.com/v3/suggest?q=x&client=opensearch");
    CHECK(suggestUrlFor(kCustom, "x").empty() && suggestTemplate(kCustom).empty());
    CHECK(suggestNote(kCustom, true) == "none for a custom engine");
    CHECK(suggestNote(kGoogle, false).empty());
    CHECK(has(suggestNote(kBrave, true), "Brave") && has(suggestNote(kBrave, true), "private"));

    // custom template validation: https only, exactly one %s, no spaces (+ host / percent / character rules)
    CHECK(check("https://search.example.org/?q=%s") == Bad::None);
    CHECK(check("HTTPS://Search.Example.org:8443/s?q=%s&x=%2F") == Bad::None);
    CHECK(check("https://example.com/search/%s") == Bad::None);
    CHECK(check("") == Bad::Empty);
    CHECK(check(std::string("https://example.com/?q=%s&p=") + std::string(kMaxTemplate, 'a')) == Bad::TooLong);
    CHECK(check("https://example.com/?q=%s and") == Bad::Space);
    CHECK(check("https://example.com/?q=%s\t") == Bad::Space);
    CHECK(check("http://example.com/?q=%s") == Bad::NotHttps);
    CHECK(check("ftp://example.com/?q=%s") == Bad::NotHttps);
    CHECK(check("javascript:alert(1)//%s") == Bad::NotHttps);
    CHECK(check("example.com/?q=%s") == Bad::NotHttps);
    CHECK(check("https://example.com/?q=%s\"") == Bad::BadChar);
    CHECK(check("https://example.com/?q='%s'") == Bad::BadChar);
    CHECK(check("https://example.com/?q=%s<x>") == Bad::BadChar);
    CHECK(check("https://example.com/?q=\xC3\xA9%s") == Bad::BadChar);
    CHECK(check("https://user:pw@example.com/?q=%s") == Bad::Credentials);
    CHECK(check("https://localhost/?q=%s") == Bad::BadHost);
    CHECK(check("https://.example.com/?q=%s") == Bad::BadHost);
    CHECK(check("https://a..b/?q=%s") == Bad::BadHost);
    CHECK(check("https://exa_mple.com/?q=%s") == Bad::BadHost);
    CHECK(check("https://example.com:/?q=%s") == Bad::BadHost);
    CHECK(check("https://example.com:80a/?q=%s") == Bad::BadHost);
    CHECK(check("https://example.com%s/") == Bad::BadHost);                          // %s in the host
    CHECK(check("https://example.com?q=%s") == Bad::None);                            // query straight after the host
    CHECK(check("https://example.com") == Bad::BadHost || check("https://example.com") == Bad::NoPlaceholder);
    CHECK(check("https://example.com/?q=") == Bad::NoPlaceholder);
    CHECK(check("https://example.com/?q=%S") == Bad::BadPercent);                     // %S is not the placeholder
    CHECK(check("https://example.com/?q=%s&r=%s") == Bad::ManyPlaceholders);
    CHECK(check("https://example.com/?q=%s&r=%zz") == Bad::BadPercent);
    CHECK(check("https://example.com/?q=%s&r=%") == Bad::BadPercent);
    CHECK(check("https://example.com/?q=%%s") == Bad::BadPercent);
    for (Bad b : { Bad::Empty, Bad::TooLong, Bad::Space, Bad::NotHttps, Bad::BadChar, Bad::Credentials, Bad::BadHost, Bad::NoPlaceholder,
                   Bad::ManyPlaceholders, Bad::BadPercent })
        CHECK(std::strlen(why(b)) > 5);
    CHECK(has(why(Bad::NotHttps), "https://") && has(why(Bad::NoPlaceholder), "%s"));

    // helpers and names
    CHECK(fill("https://a.b/?q=%s&x=1", "Z") == "https://a.b/?q=Z&x=1");
    CHECK(prefixOf("https://a.b/?q=%s") == "https://a.b/?q=");
    CHECK(hostOf("https://www.Search.Example.org:8443/x?q=%s") == "search.example.org");
    CHECK(hostOf("https://www.com/?q=%s") == "www.com");
    CHECK(shortName(kBing, "") == "Bing");
    CHECK(shortName(kCustom, "https://www.search.example.org/?q=%s") == "search.example.org");
    CHECK(shortName(kCustom, "nope") == "Google");
    CHECK(displayName(kCustom, "https://search.example.org/?q=%s") == "Custom: search.example.org");
    CHECK(displayName(kCustom, "") == "Custom\xE2\x80\xA6 (not set)");
    CHECK(displayName(kEcosia, "") == "Ecosia" && displayName(77, "") == "Google");
    CHECK(actionFor(kGoogle, "") == "https://www.google.com/search");
    CHECK(actionFor(kCustom, "https://search.example.org/find?q=%s") == "https://search.example.org/find");
    CHECK(actionFor(kCustom, "") == "https://www.google.com/search");

    // new-tab script: & as &amp; inside the attribute, nothing that ends the JS string or the attribute
    {
        const std::string s = formScript(urlFor(kGoogle, "", kSentinel) + "&safe=active");
        CHECK(s == std::string("if(v){location.href='https://www.google.com/search?q=") + kSentinel
                   + "&amp;safe=active'.split('" + kSentinel + "').join(encodeURIComponent(v));return false}");
        const std::string evil = formScript("https://x.y/?q='+alert(1)+'\"><script>\\");
        size_t quotes = 0; for (char c : evil) quotes += c == '\'';
        CHECK(quotes == 4 && !has(evil, "\"") && !has(evil, "<") && !has(evil, ">") && !has(evil, "\\"));
    }

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "PASS", checks, fails);
    return fails ? 1 : 0;
}
