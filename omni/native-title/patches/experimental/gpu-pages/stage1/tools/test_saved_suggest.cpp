// OMNI_SAVED_SUGGEST_V1: host tests for OmniSavedSuggest.h (bookmark / reading-list address suggestions).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<tools> test_saved_suggest.cpp -o t && ./t
#include "OmniSavedSuggest.h"
#include <cstdio>
#include <string>
#include <vector>

namespace S = OmniSavedSuggest;
static int fails = 0, checks = 0;
static void expect(bool ok, const char* what, const std::string& got = std::string())
{
    ++checks;
    if (!ok) { ++fails; std::printf("FAIL: %s  [%s]\n", what, got.c_str()); }
}
static std::string str(const std::vector<int>& v)
{
    std::string s;
    for (int x : v) s += (s.empty() ? "" : ",") + std::to_string(x);
    return s;
}
static std::string hits(const std::vector<S::Hit>& h)
{
    std::string s;
    for (auto& x : h) s += (s.empty() ? "" : ",") + std::string(x.kind == S::kBookmark ? "b" : "r") + std::to_string(x.index);
    return s;
}

int main()
{
    // the typed-text rule
    expect(S::query("a").empty(), "1 char: nothing");
    expect(S::query("  a  ").empty(), "1 char with spaces: nothing");
    expect(S::query("ab") == "ab", "2 chars");
    expect(S::query("https://").empty(), "scheme only: nothing");
    expect(S::query("HTTPS://WWW.GitHub.com") == "github.com", "scheme and www stripped, lowercase", S::query("HTTPS://WWW.GitHub.com"));
    expect(S::query("\xC3\xA9") .empty(), "one 2-byte character is 1 character");
    expect(S::query("\xC3\xA9t") == "\xC3\xA9t", "2 characters (UTF-8)");
    expect(S::bare("https://www.Example.com/a/") == "example.com/a", "bare", S::bare("https://www.Example.com/a/"));

    // word-prefix, case-insensitive matching
    const S::Entry gh = S::prepare(S::kBookmark, "https://github.com/omni/WebKit-port", "Omni WebKit port");
    expect(S::score(gh, S::words("git")) == 0, "address start");
    expect(S::score(gh, S::words("web")) == 0 || S::score(gh, S::words("web")) == 1, "word inside title");
    expect(S::score(gh, S::words("webk")) == 1, "word inside (not start)");
    expect(S::score(gh, S::words("omni")) == 0, "title start");
    expect(S::score(gh, S::words("port")) == 1, "word after a dash");
    expect(S::score(gh, S::words("ebkit")) == -1, "mid-word: no match");
    expect(S::score(gh, S::words("omni port")) == 0, "two words, both prefixes");
    expect(S::score(gh, S::words("omni zebra")) == -1, "two words, one missing");
    expect(S::score(gh, S::words("OMNI")) == -1, "words() takes the lowercased query (query() lowers)");
    expect(S::score(gh, S::words(S::query("OMNI"))) == 0, "case-insensitive through query()");
    expect(S::wordPrefixAt("abab ab", "ab") == 0, "first word start");
    expect(S::wordPrefixAt("xab ab", "ab") == 4, "skips mid-word hit", std::to_string(S::wordPrefixAt("xab ab", "ab")));
    const S::Entry js = S::prepare(S::kBookmark, "javascript:alert(1)", "Dark mode bookmarklet");
    expect(!S::offerable(js), "bookmarklets are never offered");

    // ranking: bookmark > reading list, at most 2, one per address, open tabs skipped
    std::vector<S::Entry> bm = {
        S::prepare(S::kBookmark, "https://news.example.com/", "Example News"),
        S::prepare(S::kBookmark, "https://recipes.org/pasta", "Pasta recipes"),
        S::prepare(S::kBookmark, "javascript:void(0)", "Pasta helper"),
        S::prepare(S::kBookmark, "https://shop.example.com/", "Pasta maker shop"),
    };
    std::vector<S::Entry> rl = {
        S::prepare(S::kReading, "https://blog.net/pasta-water", "Why salt pasta water", "r1.html"),
        S::prepare(S::kReading, "https://recipes.org/pasta/", "Pasta again (saved)", "r2.html"),
        S::prepare(S::kReading, "https://longread.com/x", "Exoplanets explained", "r3.html"),
    };
    expect(S::rank(bm, rl, "p", {}).empty(), "1 char: no rows");
    std::vector<S::Hit> h = S::rank(bm, rl, "pasta", {});
    expect(hits(h) == "b1,b3", "two bookmarks first (bookmarklet skipped)", hits(h));
    h = S::rank(bm, rl, "pasta", {}, 3);
    expect(hits(h) == "b1,b3,r0", "then the reading list; same address as a bookmark dropped", hits(h));
    h = S::rank(bm, rl, "exo", {});
    expect(hits(h) == "r2", "reading list alone", hits(h));
    h = S::rank(bm, {}, "exo", {});
    expect(h.empty(), "no reading list (private tab): nothing");
    h = S::rank(bm, rl, "pasta", { "recipes.org/pasta" });
    expect(hits(h) == "b3,r0", "an open tab's address is skipped", hits(h));
    h = S::rank(bm, rl, "shop pasta", {});
    expect(hits(h) == "b3", "multi-word", hits(h));
    h = S::rank(bm, rl, "EXAMPLE", {});
    expect(hits(h) == "b0,b3", "case-insensitive, title-start match first", hits(h));
    h = S::rank(bm, rl, "recipes", {});
    expect(hits(h) == "b1", "same page in both lists: one row", hits(h));

    // cache: rebuilt only when the key changes
    S::Cache c;
    int builds = 0;
    auto build = [&](std::vector<S::Entry>& out) { ++builds; out = bm; };
    const uint64_t k1 = S::Key().add(1000LL).add(4LL).h, k2 = S::Key().add(1001LL).add(4LL).h;
    expect(c.refresh(k1, build) && builds == 1, "first refresh builds");
    expect(!c.refresh(k1, build) && builds == 1, "same key: no rebuild");
    expect(!c.refresh(k1, build) && builds == 1, "still no rebuild");
    expect(c.refresh(k2, build) && builds == 2, "new file stamp: rebuild");
    expect(S::Key().add(std::string("ab")).add(std::string("c")).h != S::Key().add(std::string("a")).add(std::string("bc")).h,
           "key separates ids");
    expect(c.items.size() == 4, "items kept");

    // the row budget
    using R = S::Role;
    // tab row, URL row, 2 history, site row, 1 engine: 6 rows already clipped to 5 -> lead, url, local, site, engine
    std::vector<R> rows = { R::kLead, R::kUrl, R::kLocal, R::kSite, R::kEngine };
    std::vector<int> o = S::place(rows, 2);
    expect(str(o) == "0,-1,-2,1,3", "saved after the lead rows; engine then history dropped; site + URL stay", str(o));
    rows = { R::kUrl, R::kLocal, R::kLocal, R::kSite, R::kEngine };
    o = S::place(rows, 2);
    expect(str(o) == "-1,-2,0,1,3", "no lead rows: saved first", str(o));
    rows = { R::kLead, R::kLead, R::kLead, R::kUrl, R::kSite };
    o = S::place(rows, 2);
    expect(str(o) == "0,1,2,3,4", "only rows that stay: saved rows drop", str(o));
    rows = { R::kLead, R::kLead, R::kUrl, R::kSite };
    o = S::place(rows, 2);
    expect(str(o) == "0,1,-1,2,3", "one saved row fits", str(o));
    rows = { R::kEngine, R::kEngine };
    o = S::place(rows, 2);
    expect(str(o) == "-1,-2,0,1", "room for all", str(o));
    rows = {};
    o = S::place(rows, 1);
    expect(str(o) == "-1", "saved row alone", str(o));
    rows = { R::kSite, R::kEngine, R::kEngine, R::kEngine, R::kEngine };
    o = S::place(rows, 2);
    expect(str(o) == "-1,-2,0,1,2", "site row (first engine slot) stays; remote rows drop", str(o));
    rows = { R::kUrl, R::kLocal, R::kLocal, R::kLocal, R::kLocal };
    o = S::place(rows, 2);
    expect(str(o) == "-1,-2,0,1,2" && o.size() == 5, "history rows drop below saved; URL row stays", str(o));

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
