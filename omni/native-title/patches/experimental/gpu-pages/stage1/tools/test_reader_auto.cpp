// OMNI_READER_AUTO_V1: host tests of OmniReaderAuto.h (written into the tree by apply_reader_auto.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_reader_auto.cpp -o t && ./t [script.js]
// With an argument it also writes the page script there (node --check it; test_reader_auto_js.mjs runs it).
#include "OmniReaderAuto.h"
#include <cstdio>
#include <string>

namespace R = OmniReaderAuto;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

int main(int argc, char** argv)
{
    // --- site keys
    CHECK(R::siteKey("https://User@WWW.Example.COM:8443/a?b") == "example.com");
    CHECK(R::siteKey("http://news.example.com./x") == "news.example.com");
    CHECK(R::siteKey("https://[::1]:8080/") == "[::1]");
    CHECK(R::siteKey("omni://pages/start").empty());
    CHECK(R::siteKey("about:blank").empty());
    CHECK(R::siteKey("file:///data/x.html").empty());
    CHECK(R::siteKey("https://www./").empty() == false);   // "www." alone stays (not stripped to nothing)
    CHECK(R::siteKey("https://bad host/").empty());

    // --- search results heuristic
    CHECK(R::searchResultsUrl("https://www.google.com/search?q=omni+browser"));
    CHECK(R::searchResultsUrl("https://www.google.co.uk/search?q=x&hl=en"));
    CHECK(R::searchResultsUrl("https://www.bing.com/search?q=x"));
    CHECK(R::searchResultsUrl("https://duckduckgo.com/?q=x"));
    CHECK(R::searchResultsUrl("https://html.duckduckgo.com/html/?q=x"));
    CHECK(R::searchResultsUrl("https://search.yahoo.com/search?p=x"));
    CHECK(R::searchResultsUrl("https://search.brave.com/search?q=x"));
    CHECK(R::searchResultsUrl("https://yandex.ru/search/?text=x"));
    CHECK(R::searchResultsUrl("https://www.baidu.com/s?wd=x"));
    CHECK(R::searchResultsUrl("https://www.youtube.com/results?search_query=cats"));
    CHECK(R::searchResultsUrl("https://en.wikipedia.org/w/index.php?search=cats&title=Special:Search") == false);   // no search segment: a page
    CHECK(R::searchResultsUrl("https://www.bbc.co.uk/search?q=weather"));
    CHECK(R::searchResultsUrl("https://blog.example.com/?s=recipes"));
    CHECK(R::searchResultsUrl("https://shop.example.com/en/search/?query=shoes"));
    CHECK(R::searchResultsUrl("https://www.google.com/") == false);             // the engine's home page: checked, not an article
    CHECK(R::searchResultsUrl("https://example.com/search") == false);          // no terms: e.g. an article about search
    CHECK(R::searchResultsUrl("https://example.com/2024/research/cells?q=") == false);
    CHECK(R::searchResultsUrl("https://example.com/news/story?id=4#q=x") == false);
    CHECK(R::searchResultsUrl("https://www.theguardian.com/world/2024/jan/01/story") == false);
    CHECK(R::searchResultsUrl("https://googleblog.example.com/post?q=1") == false);   // "google" only as a full label
    CHECK(R::eligible("https://www.theguardian.com/world/2024/jan/01/story"));
    CHECK(!R::eligible("https://www.google.com/search?q=x"));
    CHECK(!R::eligible("omni://pages/start"));
    CHECK(!R::eligible("about:blank"));

    // --- answers and thresholds
    R::Measure m = R::parseAnswer("omni-rauto 1 p12 c5400 a1 t6000 v0 e0");
    CHECK(m.ok && m.paragraphs == 12 && m.chars == 5400 && m.articles == 1 && m.articleChars == 6000 && !m.video && !m.editable);
    CHECK(R::isArticle(m));
    CHECK(!R::parseAnswer("omni-rauto 0").ok);
    CHECK(!R::parseAnswer("").ok);
    CHECK(!R::parseAnswer("omni-rauto 1").ok);
    CHECK(!R::parseAnswer("omni-rauto 1 px").ok);
    CHECK(!R::parseAnswer("omni-rauto 10 p5").ok);
    CHECK(R::parseAnswer("omni-rauto 1 p5 c2000 z9 a0 t0 v0 e0").ok);           // unknown fields ignored
    CHECK(R::isArticle(R::parseAnswer("omni-rauto 1 p5 c2000 a0 t0 v0 e0")));    // exactly the thresholds
    CHECK(!R::isArticle(R::parseAnswer("omni-rauto 1 p4 c9000 a0 t0 v0 e0")));   // too few paragraphs, no article
    CHECK(!R::isArticle(R::parseAnswer("omni-rauto 1 p9 c1999 a0 t0 v0 e0")));   // too little text
    CHECK(R::isArticle(R::parseAnswer("omni-rauto 1 p3 c900 a1 t1500 v0 e0")));  // a short <article>
    CHECK(!R::isArticle(R::parseAnswer("omni-rauto 1 p2 c900 a1 t5000 v0 e0")));
    CHECK(!R::isArticle(R::parseAnswer("omni-rauto 1 p40 c30000 a12 t3000 v0 e0")));   // a listing of 12 teasers
    CHECK(!R::isArticle(R::parseAnswer("omni-rauto 1 p40 c30000 a1 t30000 v0 e1")));   // an editor
    CHECK(R::parseAnswer("omni-rauto 1 p40 c99999999999 a0 t0 v1 e0").chars > 0);       // huge numbers saturate

    // --- decision
    const R::Measure art = R::parseAnswer("omni-rauto 1 p12 c5400 a1 t6000 v0 e0");
    const R::Measure vid = R::parseAnswer("omni-rauto 1 p12 c5400 a1 t6000 v1 e0");
    const R::Measure none = R::parseAnswer("omni-rauto 1 p1 c100 a0 t0 v0 e0");
    CHECK(R::decide(art, false, false, false) == R::kHint);
    CHECK(R::decide(art, true, false, false) == R::kOpen);
    CHECK(R::decide(art, true, true, false) == R::kHint);    // blocked by the guard: hint only
    CHECK(R::decide(art, true, false, true) == R::kHint);    // media playing in the tab
    CHECK(R::decide(vid, true, false, false) == R::kHint);   // a <video> playing in the page
    CHECK(R::decide(none, true, false, false) == R::kNone);
    CHECK(R::decide(R::Measure(), true, false, false) == R::kNone);

    // --- r2: the automatic open's guard, simulated like the shell drives it ---------------------------------------
    // policy(type) -> finished(reader?) -> autoAllowed(..., current item == converted item) -> (open: remember item)
    {
        struct Sim {
            R::Guard g;
            int converted = 0;         // Tab::omniRauItem (0: none)
            int opens = 0;
            // One main-frame load landing on history item `item`; returns whether Reader view opened by itself.
            bool load(R::Nav nav, int item, bool readerPage, uint32_t now, bool policySeen = true)
            {
                if (policySeen) g.navigation(nav);
                const R::Nav n = g.finished(readerPage, now);
                if (readerPage) return false;
                const bool allowed = R::autoAllowed(g, n, item == converted, now);
                const R::Action a = R::decide(R::parseAnswer("omni-rauto 1 p12 c5400 a1 t6000 v0 e0"), true, !allowed, false);
                if (a != R::kOpen) return false;
                converted = item; ++opens;
                return true;
            }
        };
        // open -> auto reader -> Back stays on the original
        Sim s1;
        CHECK(s1.load(R::kNavNormal, 1, false, 1000));                  // the article (item 1): opens by itself
        CHECK(!s1.load(R::kNavNormal, 2, true, 1400));                  // the Reader view page (item 2)
        CHECK(!s1.load(R::kNavBackForward, 1, false, 9000));            // Back: stays on the article
        CHECK(!s1.load(R::kNavUnknown, 1, false, 20000, false));        // a page-cache Back with no policy call: same item
        CHECK(s1.opens == 1);
        // ... a Reload of the original after 3 s opens again; within 3 s of leaving it does not
        Sim s2;
        CHECK(s2.load(R::kNavNormal, 1, false, 1000));
        CHECK(!s2.load(R::kNavNormal, 2, true, 1500));
        CHECK(!s2.load(R::kNavBackForward, 1, false, 5000));            // left Reader view at 5000
        CHECK(!s2.load(R::kNavReload, 1, false, 7999));                 // reload 2.999 s later: no
        CHECK(s2.load(R::kNavReload, 1, false, 8000 + 3000));           // reload >= 3 s after leaving: opens again
        // forward into the reader page works (no automatic open, no reopen on the way back)
        Sim s3;
        CHECK(s3.load(R::kNavNormal, 1, false, 1000));
        CHECK(!s3.load(R::kNavNormal, 2, true, 1200));
        CHECK(!s3.load(R::kNavBackForward, 1, false, 4000));            // Back to the article
        CHECK(!s3.load(R::kNavBackForward, 2, true, 6000));             // Forward: the reader page, nothing extra
        CHECK(!s3.load(R::kNavBackForward, 2, false, 6000));            // (restored as a plain page: still nothing)
        CHECK(!s3.load(R::kNavBackForward, 1, false, 12000));           // Back again: stays
        CHECK(s3.opens == 1);
        // a new article (new item) via a link opens, even right after another one
        Sim s4;
        CHECK(s4.load(R::kNavNormal, 1, false, 1000));
        CHECK(!s4.load(R::kNavNormal, 2, true, 1100));
        CHECK(!s4.load(R::kNavNormal, 3, false, 2000));                 // a link out of Reader view within 3 s: no
        CHECK(s4.load(R::kNavNormal, 4, false, 6000));                  // the next article later: yes
        CHECK(R::autoAllowed(R::Guard(), R::kNavUnknown, false, 0));    // first load ever, no policy seen: allowed
        R::Guard wrap; wrap.left = true; wrap.leftAt = 0xFFFFFC00u;     // SDL_GetTicks wrap
        CHECK(!R::autoAllowed(wrap, R::kNavNormal, false, 0x00000100u));
        CHECK(R::autoAllowed(wrap, R::kNavNormal, false, 0x00001000u));
    }

    // --- store, private split
    R::Store s;
    std::map<std::string, bool> session;
    bool now = false;
    CHECK(!R::always(s, session, "example.com", false));
    CHECK(R::toggle(s, session, "example.com", false, now) && now && R::saved(s, "example.com"));
    CHECK(R::always(s, session, "example.com", false) && R::always(s, session, "example.com", true));
    CHECK(!R::always(s, session, "news.example.com", false));   // exact host only
    CHECK(R::toggle(s, session, "example.com", true, now) && !now);   // private: Ask for this session
    CHECK(!R::always(s, session, "example.com", true));
    CHECK(R::always(s, session, "example.com", false));          // a normal tab never sees the private choice
    CHECK(R::saved(s, "example.com"));                            // and the saved store is unchanged
    CHECK(R::toggle(s, session, "example.com", true, now) && now && session.empty());   // back to the saved choice: no row
    CHECK(R::toggle(s, session, "private.example", true, now) && now && session.count("private.example"));
    CHECK(!R::always(s, session, "private.example", false));
    CHECK(R::serialize(s).find("private.example") == std::string::npos);
    CHECK(R::toggle(s, session, "example.com", false, now) && !now && !R::saved(s, "example.com"));
    CHECK(!R::always(s, session, "", true));

    // --- file
    R::Store f;
    R::setSite(f, "b.example", true);
    R::setSite(f, "a.example", true);
    const std::string text = R::serialize(f);
    CHECK(text == "omni-reader-sites\t1\nalways\ta.example\nalways\tb.example\n");
    const R::Store back = R::parse(text);
    CHECK(back.always == f.always);
    const R::Store messy = R::parse("omni-reader-sites\t1\r\nalways\tWWW.Mixed.Example\r\nalways\t\r\nnever\tx.example\nalways\ta/b\njunk\n"
                                    "always\tbad host\nalways\tok.example \n");
    CHECK(messy.always.size() == 2 && messy.always.count("mixed.example") && messy.always.count("ok.example"));
    R::Store full;
    for (size_t i = 0; i < R::kMaxSites; ++i) CHECK(R::setSite(full, "h" + std::to_string(i) + ".example", true));
    CHECK(!R::setSite(full, "one-more.example", true));
    CHECK(R::setSite(full, "h1.example", true));                 // already there
    CHECK(R::setSite(full, "h1.example", false));                // removing always works
    std::map<std::string, bool> ses;
    R::Store full2 = full;
    R::setSite(full2, "h1.example", true);
    CHECK(!R::toggle(full2, ses, "new.example", false, now));    // full: nothing changed
    CHECK(R::siteNotice("new.example", true, false, true).find("500") != std::string::npos);
    std::string big = "omni-reader-sites\t1\n";
    for (int i = 0; i < 700; ++i) big += "always\tx" + std::to_string(i) + ".example\n";
    CHECK(R::parse(big).always.size() == R::kMaxSites);

    // --- hints once per site
    std::set<std::string> seen;
    CHECK(R::firstHint(seen, "example.com"));
    CHECK(!R::firstHint(seen, "example.com"));
    CHECK(!R::firstHint(seen, ""));
    for (size_t i = 0; i < R::kHintedMax + 10; ++i) R::firstHint(seen, "s" + std::to_string(i));
    CHECK(seen.size() == R::kHintedMax);

    // --- texts
    CHECK(R::rowValue(true) == "Always for this site" && R::rowValue(false) == "Ask");
    CHECK(R::siteNotice("example.com", true, true, false) == "Reader view on example.com: always. Articles there open in Reader view (this session only)");
    CHECK(R::siteNotice("example.com", false, false, false) == "Reader view on example.com: ask. Articles there show a hint");

    // --- the script's numbers are the header's
    const std::string js = R::kCheckScript;
    CHECK(js.find("t.length<" + std::to_string(R::kMinParagraphChars) + ")") != std::string::npos);
    CHECK(js.find("Math.min(ps.length," + std::to_string(R::kScanParagraphs) + ")") != std::string::npos);
    CHECK(js.find("Math.min(t.length," + std::to_string(R::kParagraphCap) + ")") != std::string::npos);
    CHECK(js.find(std::string("'") + R::kAnswerTag + " 1 p'") != std::string::npos);
    CHECK(js.find("setTimeout") == std::string::npos && js.find("setInterval") == std::string::npos
          && js.find("Observer") == std::string::npos);   // one measurement, no polling
    CHECK(R::kSiteRowId == 760 && R::kQuickRowId == 8490);

    if (argc > 1) {
        if (FILE* out = std::fopen(argv[1], "wb")) { std::fputs(R::kCheckScript, out); std::fclose(out); }
        else { std::printf("FAIL cannot write %s\n", argv[1]); ++fails; }
    }
    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "OK", checks, fails);
    return fails ? 1 : 0;
}
