// OMNI_SITE_SEARCH_V1: host tests for tools/OmniSiteSearch.h (copied into the tree by apply_site_search.py).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<tools> -I<tree>/engine/entry test_site_search.cpp -o t && ./t [script.js]
// (OmniSearchEngine.h / OmniSearchTiles.h come from a tree patched by apply_search_engine.py / apply_search_tiles.py.)
// With an argument the page script is written there, for test_site_search_js.mjs.
#include "OmniSiteSearch.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniSiteSearch;
namespace OST = OmniSearchTiles;

static std::string osd(const std::string& inner, const std::string& head = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
{
    return head + "<OpenSearchDescription xmlns=\"http://a9.com/-/spec/opensearch/1.1/\">\n" + inner + "\n</OpenSearchDescription>\n";
}
static bool has(const std::string& s, const char* part) { return s.find(part) != std::string::npos; }

int main(int argc, char** argv)
{
    // --- a normal description -----------------------------------------------------------------------------------
    {
        const std::string x = osd("  <ShortName>Example Wiki</ShortName>\n  <Description>Search it</Description>\n"
                                  "  <Image height=\"16\" width=\"16\">https://wiki.example.org/favicon.ico</Image>\n"
                                  "  <Url type=\"application/x-suggestions+json\" template=\"https://wiki.example.org/s?q={searchTerms}\"/>\n"
                                  "  <Url type=\"text/html\" method=\"get\" template=\"https://wiki.example.org/w/index.php?title=Special:Search&amp;search={searchTerms}\"/>\n");
        const Offer o = offerFrom(x);
        CHECK(o.ok);
        CHECK(o.name == "Example Wiki");
        CHECK(o.tmpl == "https://wiki.example.org/w/index.php?title=Special:Search&search=%s");
        CHECK(o.host == "wiki.example.org");
        CHECK(OmniSearchEngine::validTemplate(o.tmpl) && OST::validTemplate(o.tmpl));
    }
    // prefixed namespace, single quotes, CDATA name, comments, PI, rel=results, optional params, required defaults
    {
        const std::string x = "\xEF\xBB\xBF<?xml version='1.0'?><!-- hi --><os:OpenSearchDescription xmlns:os='http://a9.com/-/spec/opensearch/1.1/'>"
                              "<os:ShortName><![CDATA[Caf\xC3\xA9 & Co]]></os:ShortName>"
                              "<os:Url type='text/html; charset=UTF-8' rel='results' template='https://www.cafe.example/find?q={searchTerms}&amp;p={startPage?}&amp;n={count}&amp;i={startIndex}&amp;l={language}&amp;e={inputEncoding}&amp;g={geo:box?}'/>"
                              "</os:OpenSearchDescription><!-- bye -->";
        const Offer o = offerFrom(x);
        CHECK(o.ok);
        CHECK(o.name == "Caf\xC3\xA9 & Co");
        CHECK(o.tmpl == "https://www.cafe.example/find?q=%s&p=&n=20&i=1&l=*&e=UTF-8&g=");
        CHECK(o.host == "cafe.example");
    }
    // entities and numeric references in the name; whitespace collapsed
    {
        const Offer o = offerFrom(osd("<ShortName>\n  A &amp; B &#x263A;\t&#65;  </ShortName><Url type=\"text/html\" template=\"https://ab.example/?q={searchTerms}\"/>"));
        CHECK(o.ok && o.name == "A & B \xE2\x98\xBA A");
    }
    // no ShortName: the template's host is the name
    {
        const Offer o = offerFrom(osd("<Url type=\"text/html\" template=\"https://www.find.example/?q={searchTerms}\"/>"));
        CHECK(o.ok && o.name == "find.example");
    }
    // the first usable text/html Url wins; POST and rel=suggestions skipped
    {
        const Offer o = offerFrom(osd("<ShortName>X</ShortName>"
                                      "<Url type=\"text/html\" method=\"post\" template=\"https://x.example/post?q={searchTerms}\"/>"
                                      "<Url type=\"text/html\" rel=\"suggestions\" template=\"https://x.example/sug?q={searchTerms}\"/>"
                                      "<Url type=\"text/html\" template=\"https://x.example/get?q={searchTerms}\"><Param name=\"a\" value=\"b\"/></Url>"));
        CHECK(o.ok && o.tmpl == "https://x.example/get?q=%s");
    }
    {
        const Offer o = offerFrom(osd("<ShortName>X</ShortName><Url type=\"text/html\" method=\"POST\" template=\"https://x.example/post?q={searchTerms}\"/>"));
        CHECK(!o.ok && has(o.why, "POST"));
    }

    // --- templates refused ----------------------------------------------------------------------------------------
    std::string why;
    CHECK(convertTemplate("http://x.example/?q={searchTerms}", &why).empty() && has(why, "https"));
    CHECK(convertTemplate("javascript:alert(1)//{searchTerms}").empty());
    CHECK(convertTemplate("data:text/html,{searchTerms}").empty());
    CHECK(convertTemplate("https://x.example/?q=cats", &why).empty() && has(why, "searchTerms"));
    CHECK(convertTemplate("https://x.example/?q={searchTerms}&r={searchTerms}", &why).empty() && has(why, "more than once"));
    CHECK(convertTemplate("https://x.example/?q={searchTerms?}") == "https://x.example/?q=%s");   // optional searchTerms still counts
    CHECK(convertTemplate("https://x.example/?q=%s").empty());
    CHECK(convertTemplate("https://x.example/?f=%s&q={searchTerms}").empty());
    CHECK(convertTemplate("https://x.example/?q={searchTerms}&x={unknown}", &why).empty() && has(why, "unknown"));
    CHECK(convertTemplate("https://x.example/?q={searchTerms}&x={a:b}").empty());
    CHECK(convertTemplate("https://x.example/?q={searchTerms}&x={unknown?}") == "https://x.example/?q=%s&x=");
    CHECK(convertTemplate("https://x.example/?q={searchTerms").empty());
    CHECK(convertTemplate("https://x.example/?q=}{searchTerms}").empty());
    CHECK(convertTemplate("https://x.example/?q={{searchTerms}}").empty());
    CHECK(convertTemplate("https://user:pw@x.example/?q={searchTerms}").empty());
    CHECK(convertTemplate("https://x.example/a b?q={searchTerms}").empty());
    CHECK(convertTemplate("https://x.example/?q={searchTerms}\"onload=\"x").empty());
    CHECK(convertTemplate("https://x.example/?q={searchTerms}<script>").empty());
    CHECK(convertTemplate("https://x.example/?q={searchTerms}&z=%zz").empty());
    CHECK(convertTemplate("https://x.example/?q={searchTerms}&z=%41") == "https://x.example/?q=%s&z=%41");
    CHECK(convertTemplate("https://x..example/?q={searchTerms}").empty());
    CHECK(convertTemplate("https://localhost/?q={searchTerms}").empty());         // no dot: not a plain public host
    CHECK(convertTemplate("https://x.example/\xC3\xA9?q={searchTerms}").empty());  // non-ASCII
    CHECK(convertTemplate("https://x.example?q={searchTerms}") == "https://x.example?q=%s");   // '?' right after the host is fine
    CHECK(convertTemplate("https://x.example{searchTerms}").empty());              // the words in the host
    CHECK(convertTemplate("  https://x.example/?q={searchTerms}  ") == "https://x.example/?q=%s");
    CHECK(convertTemplate("HTTPS://X.example/?q={searchTerms}") == "HTTPS://X.example/?q=%s");
    CHECK(convertTemplate(std::string("https://x.example/?q={searchTerms}&") + std::string(600, 'a')).empty());   // too long
    {   // an attribute with a newline / tab entity never makes it into a template
        const Offer o = offerFrom(osd("<Url type=\"text/html\" template=\"https://x.example/?q={searchTerms}&#10;evil\"/>"));
        CHECK(!o.ok);
        const Offer o2 = offerFrom(osd("<Url type=\"text/html\" template=\"https://x.example/?q={searchTerms}&#9;evil\"/>"));
        CHECK(!o2.ok);
    }

    // --- malicious / broken XML -----------------------------------------------------------------------------------
    const std::string good = osd("<ShortName>G</ShortName><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"/>");
    CHECK(offerFrom(good).ok);
    CHECK(!parseDocument("").ok);
    CHECK(!offerFrom("not xml at all").ok);
    CHECK(!offerFrom("<html><body>hi</body></html>").ok && has(offerFrom("<html></html>").why, "OpenSearch"));
    // billion laughs / external entities: any DOCTYPE fails
    CHECK(!offerFrom("<?xml version=\"1.0\"?><!DOCTYPE lolz [<!ENTITY lol \"lol\"><!ENTITY lol2 \"&lol;&lol;&lol;\">]>"
                     "<OpenSearchDescription><ShortName>&lol2;</ShortName><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"/></OpenSearchDescription>").ok);
    CHECK(!offerFrom("<!DOCTYPE x SYSTEM \"file:///etc/passwd\"><OpenSearchDescription><ShortName>&xxe;</ShortName></OpenSearchDescription>").ok);
    CHECK(!offerFrom(osd("<ShortName>&lol;</ShortName><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"/>")).ok);   // unknown entity
    CHECK(!offerFrom(osd("<ShortName>a & b</ShortName><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"/>")).ok);   // bare &
    CHECK(!offerFrom(osd("<ShortName>&#0;</ShortName><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"/>")).ok);
    CHECK(!offerFrom(osd("<ShortName>&#xD800;</ShortName><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"/>")).ok);
    CHECK(!offerFrom(osd("<ShortName>&#x110000;</ShortName><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"/>")).ok);
    CHECK(!offerFrom(osd("<ShortName>&#99999999999999999999;</ShortName>")).ok);
    CHECK(!offerFrom(osd("<ShortName>&#x;</ShortName>")).ok);
    // truncated / mismatched / unquoted / duplicate roots / trailing content
    CHECK(!offerFrom(good.substr(0, good.size() / 2)).ok);
    CHECK(!offerFrom("<OpenSearchDescription><ShortName>x</Shortname></OpenSearchDescription>").ok);
    CHECK(!offerFrom("<OpenSearchDescription><Url type=text/html template=\"https://g.example/?q={searchTerms}\"/></OpenSearchDescription>").ok);
    CHECK(!offerFrom("<OpenSearchDescription><Url type=\"text/html\" template/></OpenSearchDescription>").ok);
    CHECK(!offerFrom("<OpenSearchDescription><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}/></OpenSearchDescription>").ok);
    CHECK(!offerFrom("<OpenSearchDescription><Url type=\"a<b\" template=\"https://g.example/?q={searchTerms}\"/></OpenSearchDescription>").ok);
    CHECK(!offerFrom(good + "<OpenSearchDescription/>").ok);
    CHECK(!offerFrom(good + "junk").ok);
    CHECK(!offerFrom("junk" + good).ok);
    CHECK(!offerFrom("<OpenSearchDescription><!-- never closed </OpenSearchDescription>").ok);
    CHECK(!offerFrom("<OpenSearchDescription><![CDATA[ never closed </OpenSearchDescription>").ok);
    CHECK(!offerFrom("<?xml never closed <OpenSearchDescription/>").ok);
    CHECK(!offerFrom("<OpenSearchDescription><a><b></a></b></OpenSearchDescription>").ok);
    CHECK(!offerFrom("<OpenSearchDescription></OpenSearchDescription></OpenSearchDescription>").ok);
    CHECK(!offerFrom("<OpenSearchDescription><1bad/></OpenSearchDescription>").ok);
    CHECK(!offerFrom("<OpenSearchDescription><Url / ></OpenSearchDescription>").ok);
    CHECK(!offerFrom("<OpenSearchDescription><Url type=\"text/html\"template=\"x\"/></OpenSearchDescription>").ok);   // no space between attributes
    // the only usable Url nested too deep is not a direct child: not used
    CHECK(!offerFrom(osd("<x><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"/></x>")).ok);
    // depth / element / attribute / size limits
    {
        std::string deep;
        for (int k = 0; k < 40; ++k) deep += "<a>";
        for (int k = 0; k < 40; ++k) deep += "</a>";
        CHECK(!offerFrom(osd(deep)).ok && has(offerFrom(osd(deep)).why, "deep"));
        std::string many;
        for (int k = 0; k < 600; ++k) many += "<b/>";
        CHECK(!offerFrom(osd(many)).ok);
        std::string attrs = "<Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"";
        for (int k = 0; k < 40; ++k) attrs += " a" + std::to_string(k) + "=\"1\"";
        CHECK(!offerFrom(osd(attrs + "/>")).ok);
        const std::string big = osd("<ShortName>" + std::string(kMaxXml, 'a') + "</ShortName>");
        CHECK(!offerFrom(big).ok && has(offerFrom(big).why, "big"));
        std::string justUnder = osd("<ShortName>G</ShortName><Url type=\"text/html\" template=\"https://g.example/?q={searchTerms}\"/><!--");
        justUnder += std::string(kMaxXml - justUnder.size() - 30, 'c') + "-->";
        justUnder += "</OpenSearchDescription>";
        CHECK(justUnder.size() <= kMaxXml && offerFrom(justUnder).ok);
    }
    // a hostile name: tabs / newlines / control characters / bad UTF-8 can't reach the file; length capped on a boundary
    {
        const Offer o = offerFrom(osd("<ShortName>Evil&#10;yt\thttps://evil.example/?q=%s&#13;\x01\xFF\xC0\xAF</ShortName>"
                                      "<Url type=\"text/html\" template=\"https://evil.example/?q={searchTerms}\"/>"));
        CHECK(o.ok);
        CHECK(o.name.find('\n') == std::string::npos && o.name.find('\t') == std::string::npos && o.name.find('\r') == std::string::npos);
        CHECK(o.name.size() <= kMaxName);
        CHECK(o.name.find('\x01') == std::string::npos && o.name.find('\xFF') == std::string::npos && o.name.find('\xC0') == std::string::npos);
        std::string longName;
        for (int k = 0; k < 30; ++k) longName += "\xE2\x82\xAC";   // 3-byte euro signs
        const std::string c = cleanName(longName);
        CHECK(c.size() == 39 && c.size() <= kMaxName);
        CHECK(cleanName("\xED\xA0\x80x") == "x");          // UTF-16 surrogate encoded: dropped
        CHECK(cleanName("\xE0\x80\xAFx") == "x");          // overlong '/'
        CHECK(cleanName("a\xE2\x80\xA8" "b") == "ab");     // line separator
        CHECK(cleanName("  \t a \n\n b  ") == "a b");
        CHECK(cleanName("").empty());
    }

    // --- answers from the page script --------------------------------------------------------------------------------
    {
        std::string xml;
        CHECK(parseAnswer("", &xml) == Answer::Nothing);
        CHECK(parseAnswer("whatever", &xml) == Answer::Nothing);
        CHECK(parseAnswer(kTagNone, &xml) == Answer::NoLink);
        CHECK(parseAnswer(kTagFail, &xml) == Answer::Failed);
        CHECK(parseAnswer(std::string(kTag) + good, &xml) == Answer::Xml && xml == good);
        CHECK(parseAnswer(std::string(kTag) + std::string(kMaxXml + 1, 'x'), &xml) == Answer::Failed);
    }

    // --- sites ----------------------------------------------------------------------------------------------------------
    CHECK(pageSite("https://www.example.com/a?b") == "example.com");
    CHECK(pageSite("http://www.example.com/").empty());
    CHECK(pageSite("omni://pages").empty() && pageSite("about:blank").empty());
    CHECK(sameSite("search.example.com", "example.com") && sameSite("example.com", "search.example.com") && sameSite("a.b", "a.b"));
    CHECK(!sameSite("evilexample.com", "example.com") && !sameSite("example.com.evil.net", "example.com") && !sameSite("", "x.y"));
    CHECK(sameSearch("https://www.youtube.com/results?search_query=%s", "https://youtube.com/results/?search_query=%s&page=&utm_source=opensearch"));
    CHECK(!sameSearch("https://www.youtube.com/results?search_query=%s", "https://www.youtube.com/feed?q=%s"));
    CHECK(!sameSearch("x", "y"));

    // --- keywords -----------------------------------------------------------------------------------------------------
    {
        const auto& b = OST::builtins();
        CHECK(defaultKeyword("Example Wiki", "wiki.example.org", b) == "example");
        CHECK(defaultKeyword("YouTube", "youtube.com", b) == "youtube");
        CHECK(defaultKeyword("\xE6\x97\xA5\xE6\x9C\xAC", "nihon.example", b) == "nihon");
        CHECK(defaultKeyword("!!!", "", b) == "site");
        CHECK(defaultKeyword("W", "w.example", b) == "w2");                 // "w" is Wikipedia's
        CHECK(defaultKeyword("Supercalifragilisticexpialidocious", "x.y", b).size() <= 16);
        std::vector<OST::Engine> l = b;
        l.push_back({ "x", "X", "https://x.example/?q=%s" });
        l.push_back({ "x2", "X2", "https://x2.example/?q=%s" });
        CHECK(defaultKeyword("X", "x.example", l) == "x3");
        std::string kw;
        CHECK(checkKeyword("  E x ", b, kw) == KwBad::Invalid);             // inner space
        CHECK(checkKeyword("  Ex-1 ", b, kw) == KwBad::None && kw == "ex-1");
        CHECK(checkKeyword("yt", b, kw) == KwBad::Taken);
        CHECK(checkKeyword("YT", b, kw, "yt") == KwBad::None);              // renaming to itself
        CHECK(checkKeyword("", b, kw) == KwBad::Invalid);
        CHECK(checkKeyword("a.b", b, kw) == KwBad::Invalid);
        CHECK(checkKeyword("abcdefghijklmnopq", b, kw) == KwBad::Invalid);  // 17
        CHECK(checkKeyword("a\tb", b, kw) == KwBad::Invalid);
        CHECK(std::string(keywordWhy(KwBad::Taken)).size() > 3);
    }

    // --- the file: add / remove / rename keep the format and other lines -----------------------------------------------
    {
        // a missing file: the built-ins are written first, then the new entry; parseFile reads all of them
        const std::string t = addEntry("", false, "ex", "https://wiki.example.org/?q=%s", "Example\tWiki\n");
        int rejected = -1;
        const auto list = OST::parseFile(t, &rejected);
        CHECK(rejected == 0);
        CHECK(list.size() == OST::builtins().size() + 1);
        CHECK(list.back().prefix == "ex" && list.back().name == "Example Wiki" && list.back().tmpl == "https://wiki.example.org/?q=%s");
        CHECK(list[0].prefix == "yt" && list[0].name == "YouTube");
        // matching through the existing resolver
        OST::Match m;
        CHECK(OST::match("ex caf\xC3\xA9 au lait", list, m) && m.url == "https://wiki.example.org/?q=caf%C3%A9%20au%20lait");
    }
    {
        // an existing CRLF file with a comment, an invalid line, a space-form line and no final newline
        const std::string f = "# mine\r\nzz\thttp://bad.example/?q=%s\r\nk https://k.example/?q=%s\r\ngh\thttps://github.com/search?q=%s\tGitHub";
        const std::string a = addEntry(f, true, "ex", "https://e.example/?q=%s", "E");
        CHECK(a == f + "\r\nex\thttps://e.example/?q=%s\tE\r\n");
        int rejected = 0;
        const auto l = OST::parseFile(a, &rejected);
        CHECK(l.size() == 3 && rejected == 1 && l[2].prefix == "ex");
        // rename keeps the template and the line's own name; others untouched
        bool found = false;
        const std::string r = renameEntry(a, true, "gh", "git", &found);
        CHECK(found);
        CHECK(r == "# mine\r\nzz\thttp://bad.example/?q=%s\r\nk https://k.example/?q=%s\r\ngit\thttps://github.com/search?q=%s\tGitHub\r\nex\thttps://e.example/?q=%s\tE\r\n");
        const std::string r2 = renameEntry(a, true, "k", "kk", &found);   // space form, no name: written in TAB form without one
        CHECK(found && has(r2, "\r\nkk\thttps://k.example/?q=%s\r\n") && !has(r2, "\nk https"));
        CHECK(OST::parseFile(r2)[0].prefix == "kk" && OST::parseFile(r2)[0].name == "k.example");
        // rename of something that isn't there: unchanged
        CHECK(renameEntry(a, true, "nope", "x", &found) == a && !found);
        CHECK(renameEntry(a, true, "zz", "x", &found) == a && !found);      // an invalid line is not an entry
        // remove keeps the comment and the invalid line
        const std::string d = removeEntry(a, true, "gh", &found);
        CHECK(found && d == "# mine\r\nzz\thttp://bad.example/?q=%s\r\nk https://k.example/?q=%s\r\nex\thttps://e.example/?q=%s\tE\r\n");
        CHECK(removeEntry(a, true, "nope", &found) == a && !found);
    }
    {
        // dead duplicates go with the entry (they would otherwise come alive)
        const std::string f = "d\thttps://one.example/?q=%s\nd\thttps://two.example/?q=%s\nx\thttps://x.example/?q=%s\n";
        bool found = false;
        const std::string d = removeEntry(f, true, "d", &found);
        CHECK(found && d == "x\thttps://x.example/?q=%s\n");
        const std::string r = renameEntry(f, true, "d", "e", &found);
        CHECK(found && r == "e\thttps://one.example/?q=%s\nx\thttps://x.example/?q=%s\n");
        // an invalid first line of a prefix: the valid later one is the entry
        const std::string g = "d\thttp://bad.example/?q=%s\nd\thttps://good.example/?q=%s\n";
        CHECK(renameEntry(g, true, "d", "e", &found) == "e\thttps://good.example/?q=%s\n" && found);
    }
    {
        // a missing file: deleting / renaming a built-in writes the others
        bool found = false;
        const std::string d = removeEntry("", false, "yt", &found);
        CHECK(found);
        const auto l = OST::parseFile(d);
        CHECK(l.size() == OST::builtins().size() - 1);
        for (const auto& e : l) CHECK(e.prefix != "yt");
        const std::string r = renameEntry("", false, "w", "wiki", &found);
        const auto l2 = OST::parseFile(r);
        CHECK(found && l2.size() == OST::builtins().size() && l2[1].prefix == "wiki" && l2[1].name == "Wikipedia");
        CHECK(OST::parseFile(builtinsText()).size() == OST::builtins().size());
    }
    // already saved: the built-in YouTube shortcut covers YouTube's own description
    {
        const Offer o = offerFrom(osd("<ShortName>YouTube</ShortName><Url type=\"text/html\" template=\"https://www.youtube.com/results?search_query={searchTerms}&amp;page={startPage?}&amp;utm_source=opensearch\"/>"));
        CHECK(o.ok && alreadySaved(o, OST::builtins()));
        const Offer o2 = offerFrom(good);
        CHECK(o2.ok && !alreadySaved(o2, OST::builtins()));
    }

    // --- settings file ------------------------------------------------------------------------------------------------
    CHECK(parseOffer(""));
    CHECK(!parseOffer("offer\t0\n"));
    CHECK(parseOffer("offer\t1\r\n"));
    CHECK(parseOffer("offer\tbanana\n"));
    CHECK(!parseOffer(offerText(false)) && parseOffer(offerText(true)));

    // --- texts ----------------------------------------------------------------------------------------------------------
    {
        Offer o; o.name = "Example"; o.host = "search.other.example";
        CHECK(quickLabel(o) == "Add Example search");
        CHECK(has(hintText(o), "Options > Add Example search"));
        CHECK(whereValue(o, "example.com") == "search.other.example (not this site)");
        o.host = "search.example.com";
        CHECK(whereValue(o, "example.com") == "search.example.com");
        CHECK(usage("ex", "Example") == "Type \"ex words\" in the address bar to search Example");
    }

    // --- the script -----------------------------------------------------------------------------------------------------
    {
        const std::string js = pageScript();
        CHECK(has(js, "const MAX = 16384") && has(js, "opensearchdescription+xml") && has(js, "credentials: \"omit\""));
        CHECK(has(js, "\"omni-sse\\n\"") && has(js, "omni-sse-none") && has(js, "omni-sse-fail"));
        if (argc > 1) {
            if (FILE* f = std::fopen(argv[1], "wb")) { std::fputs(js.c_str(), f); std::fclose(f); }
        }
    }

    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "OK", checks, fails);
    return fails ? 1 : 0;
}
