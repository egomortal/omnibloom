// OMNI_TAB_SEARCH_V1: host tests for engine/entry/OmniTabSearch.h (the pure part of "Switch to tab" suggestions).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_search.cpp -o t && ./t
#include "OmniTabSearch.h"
#include <cstdio>
#include <string>
#include <vector>

namespace Q = OmniTabSearch;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static Q::Item item(int id, const char* url, const char* title, uint64_t rec, bool priv = false, bool current = false)
{
    Q::Item it; it.id = id; it.url = url; it.title = title; it.recency = rec; it.priv = priv; it.current = current;
    it.web = it.url.rfind("http", 0) == 0;
    return it;
}
static std::vector<int> ids(const std::vector<Q::Hit>& h) { std::vector<int> v; for (auto& x : h) v.push_back(x.id); return v; }

int main()
{
    // --- normalizing
    CHECK(Q::normalizeQuery("  HTTPS://www.GitHub.com ") == "github.com");
    CHECK(Q::normalizeQuery("http://") == "");
    CHECK(Q::normalizeQuery("   ") == "");
    CHECK(Q::bareURL("https://www.Example.com/a/b//") == "example.com/a/b");
    CHECK(Q::hostOf("https://www.example.com:8080/x?y") == "example.com");
    CHECK(Q::hostOf("https://user@mail.google.com/") == "mail.google.com");
    CHECK(Q::hostOf("http://[::1]:80/") == "[::1]");
    CHECK(Q::hostOf("") == "");
    CHECK((Q::words("  a  bb c ") == std::vector<std::string>{ "a", "bb", "c" }));

    // --- quality: word-prefix (0), substring (1), none (-1)
    CHECK(Q::quality("GitHub - Issues", "https://github.com/omni/issues", "git") == 0);       // bare address starts
    CHECK(Q::quality("Lo-fi Radio", "https://www.youtube.com/watch?v=1", "radio") == 0);     // title word
    CHECK(Q::quality("Lo-fi Radio", "https://www.youtube.com/watch?v=1", "fi") == 0);        // after '-'
    CHECK(Q::quality("Inbox", "https://mail.google.com/", "google") == 0);                  // host label
    CHECK(Q::quality("Inbox", "https://my-site.example.org/", "site") == 0);                // host label after '-'
    CHECK(Q::quality("Hacker News", "https://news.ycombinator.com/", "comb") == 1);          // substring of the address
    CHECK(Q::quality("Hacker News", "https://news.ycombinator.com/", "acker") == 1);         // substring of the title
    CHECK(Q::quality("Hacker News", "https://news.ycombinator.com/", "k") == -1);            // 1 letter: word-prefix only
    CHECK(Q::quality("Hacker News", "https://news.ycombinator.com/", "c") == 0);             // the host label "com"
    CHECK(Q::quality("Hacker News", "https://news.ycombinator.com/", "h") == 0);
    CHECK(Q::quality("Hacker News", "https://news.ycombinator.com/", "zzz") == -1);
    CHECK(Q::quality("Hacker News", "https://news.ycombinator.com/", "") == -1);
    CHECK(Q::quality("HACKER News", "https://x.com/", "hacker") == 0);                        // case-insensitive
    // every word must match; the worst word counts
    CHECK(Q::quality("Rust Book - Ownership", "https://doc.rust-lang.org/book/", "rust own") == 0);
    CHECK(Q::quality("Rust Book - Ownership", "https://doc.rust-lang.org/book/", "rust ner") == 1);
    CHECK(Q::quality("Rust Book - Ownership", "https://doc.rust-lang.org/book/", "rust python") == -1);
    CHECK(Q::quality("Rust Book", "https://doc.rust-lang.org/book/", "doc.rust-lang.org/bo") == 0);  // address prefix with path
    CHECK(Q::quality("Café menu", "https://cafe.example/", "menu") == 0);                    // UTF-8 title ok

    // --- visibility of private tabs
    CHECK(Q::visible(false, false));
    CHECK(Q::visible(false, true));
    CHECK(!Q::visible(true, false));
    CHECK(Q::visible(true, true));

    // --- ranking
    {
        std::vector<Q::Item> t = {
            item(0, "https://news.ycombinator.com/", "Hacker News", 10),
            item(1, "https://github.com/omni", "omni on GitHub", 50),
            item(2, "https://www.youtube.com/watch?v=lofi", "lofi hip hop radio", 30),
            item(3, "https://github.com/omni/issues", "Issues", 40),
            item(4, "https://secret.example/", "Hidden github notes", 99, true),   // private
            item(5, "https://github.com/me", "Me", 999, false, true),            // the current tab
        };
        // word-prefix hits by recency (1:50, 3:40, then 4 hidden, 5 current); substring later
        CHECK((ids(Q::rank(t, "github", false, 3)) == std::vector<int>{ 1, 3 }));
        CHECK((ids(Q::rank(t, "github", true, 3)) == std::vector<int>{ 4, 1, 3 }));   // private shows in private
        CHECK((ids(Q::rank(t, "github", true, 2)) == std::vector<int>{ 4, 1 }));      // max
        CHECK((ids(Q::rank(t, "GITHUB.com", false, 3)) == std::vector<int>{ 1, 3 }));
        CHECK(Q::rank(t, "", false, 3).empty());
        CHECK(Q::rank(t, "github", false, 0).empty());
        // quality before recency: "hub" is a substring of github (1) but a word prefix nowhere -> both 1, recency
        CHECK((ids(Q::rank(t, "hub", false, 3)) == std::vector<int>{ 1, 3 }));
        // "radio": title word of 2 (quality 0) beats ... only one hit
        CHECK((ids(Q::rank(t, "radio", false, 3)) == std::vector<int>{ 2 }));
        // "o": one letter -> only word-prefix: "omni on GitHub" (title words) and nothing else
        CHECK((ids(Q::rank(t, "o", false, 3)) == std::vector<int>{ 1 }));
        // mixed quality: "ne" -> 0 "news" word prefix (Hacker News), others no
        std::vector<Q::Item> m = {
            item(0, "https://a.example/", "Planet earth", 100),   // "ne" substring of "planet" -> 1
            item(1, "https://b.example/", "New things", 1),       // word prefix -> 0
        };
        CHECK((ids(Q::rank(m, "ne", false, 3)) == std::vector<int>{ 1, 0 }));
        // never-shown tabs (recency 0) after shown ones; equal recency keeps tab order
        std::vector<Q::Item> r = { item(0, "https://x.example/1", "doc one", 0), item(1, "https://x.example/2", "doc two", 0),
                                   item(2, "https://x.example/3", "doc three", 5) };
        CHECK((ids(Q::rank(r, "doc", false, 3)) == std::vector<int>{ 2, 0, 1 }));
        // duplicates by bare address: the better-ranked one only
        std::vector<Q::Item> d = { item(0, "https://www.example.com/", "Example", 1), item(1, "http://example.com", "Example", 9) };
        CHECK((ids(Q::rank(d, "exam", false, 3)) == std::vector<int>{ 1 }));
        // non-web pages never match
        std::vector<Q::Item> nw = { item(0, "omni://pages/newtab", "New tab", 9), item(1, "about:blank", "about", 9) };
        CHECK(Q::rank(nw, "new", false, 3).empty());
        CHECK(Q::rank(nw, "about", false, 3).empty());
        // skipBare: closed tabs whose address is open are skipped
        std::vector<Q::Item> c = { item(0, "https://github.com/omni", "omni", 1), item(1, "https://gitlab.com/x", "x", 2) };
        CHECK((ids(Q::rank(c, "git", false, 2, { "github.com/omni" })) == std::vector<int>{ 1 }));
    }

    // --- texts
    CHECK(Q::detail(Q::kSwitch, "https://www.github.com/omni", false, false) == "Switch to tab \xC2\xB7 github.com");
    CHECK(Q::detail(Q::kSwitch, "https://github.com/", true, false) == "Switch to tab \xC2\xB7 Pinned \xC2\xB7 github.com");
    CHECK(Q::detail(Q::kSwitch, "https://github.com/", false, true) == "Switch to private tab \xC2\xB7 github.com");
    CHECK(Q::detail(Q::kReopen, "https://example.com/a", true, false) == "Reopen \xC2\xB7 example.com");

    // --- row budget: the list stays at 5
    CHECK(Q::keepAfter(0, 5) == 5);
    CHECK(Q::keepAfter(2, 5) == 3);
    CHECK(Q::keepAfter(3, 1) == 1);
    CHECK(Q::keepAfter(5, 4) == 0);
    CHECK(Q::keepAfter(6, 4) == 0);
    CHECK(Q::kMaxTabs == 3 && Q::kMaxReopen == 2 && Q::kMaxTabs + Q::kMaxReopen == Q::kMaxRows);

    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
