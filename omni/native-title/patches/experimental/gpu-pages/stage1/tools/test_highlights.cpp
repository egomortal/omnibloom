// OMNI_HIGHLIGHTS_V1: host test of the pure part (engine/entry/OmniHighlights.h).
//   g++ -std=c++20 -Wall -Wextra -Wshadow -I<tree>/engine/entry test_highlights.cpp -o t && ./t [--emit <dir>]
// --emit writes the page script and built calls for tools/test_highlights_js.cjs (and node --check).
#include "OmniHighlights.h"
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

namespace H = OmniHighlights;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define EQ(a, b) do { ++checks; const std::string x_ = (a), y_ = (b); if (x_ != y_) { ++fails; fprintf(stderr, "FAIL %s:%d: %s\n  got  [%s]\n  want [%s]\n", __FILE__, __LINE__, #a, x_.c_str(), y_.c_str()); } } while (0)

// Text that must survive every hop: quotes, backslashes, a script end tag, controls, U+2028, an emoji, CJK.
static const std::string kTricky = "He said \"hi\\there\" </script> 'x' \xe2\x80\xa8 line \xf0\x9f\x98\x80 \xe6\xbc\xa2\xe5\xad\x97 end";

static H::Item item(long long id, long long at, const std::string& url, const std::string& e, const std::string& title = "T")
{
    H::Item it; it.id = id; it.at = at; it.url = url; it.exact = e; it.title = title; it.prefix = "before "; it.suffix = " after";
    return it;
}

static void testUrl()
{
    EQ(H::normalizeUrl("https://Example.COM/a/b?x=1#frag"), "https://example.com/a/b?x=1");
    EQ(H::normalizeUrl("HTTP://www.example.com:80"), "http://www.example.com/");
    EQ(H::normalizeUrl("https://example.com:443/p"), "https://example.com/p");
    EQ(H::normalizeUrl("https://example.com:8443/p"), "https://example.com:8443/p");
    EQ(H::normalizeUrl("https://user:pw@example.com/p"), "https://example.com/p");
    EQ(H::normalizeUrl("https://example.com/p?utm_source=a&id=7&UTM_Medium=b&fbclid=z&gclid=1&si=2&x"), "https://example.com/p?id=7&x");
    EQ(H::normalizeUrl("https://example.com/p?utm_source=a"), "https://example.com/p");
    EQ(H::normalizeUrl("https://example.com/p?&&a=1&&"), "https://example.com/p?a=1");
    EQ(H::normalizeUrl("https://example.com/p?a=1#x?utm_source=b"), "https://example.com/p?a=1");
    EQ(H::normalizeUrl("  https://example.com/  "), "https://example.com/");
    EQ(H::normalizeUrl("https://[::1]:443/x"), "https://[::1]/x");
    EQ(H::normalizeUrl("about:blank"), "");
    EQ(H::normalizeUrl("omni://pages/new-tab"), "");
    EQ(H::normalizeUrl("file:///data/x.html"), "");
    EQ(H::normalizeUrl("javascript:alert(1)"), "");
    EQ(H::normalizeUrl("https://"), "");
    EQ(H::normalizeUrl("https://:80/"), "");
    EQ(H::normalizeUrl("https://exa mple.com/"), "");
    EQ(H::normalizeUrl("https://example.com/" + std::string(3000, 'a')), "");
    CHECK(!H::normalizeUrl("https://example.com/" + std::string(2000, 'a')).empty());
    EQ(H::site("https://www.example.com/a"), "example.com");
    EQ(H::site("https://news.example.com"), "news.example.com");
}

static void testJson()
{
    // escape -> parse round trip
    H::Json j;
    CHECK(H::parseJson(H::jsonEscape(kTricky), j));
    CHECK(j.kind == H::Json::Str);
    EQ(j.str, kTricky);
    const std::string esc = H::jsonEscape(kTricky);
    CHECK(esc.find("\xe2\x80\xa8") == std::string::npos);   // U+2028 escaped (a safe JS literal)
    CHECK(esc.find("\\u2028") != std::string::npos);
    EQ(H::jsonEscape(std::string("a\0b\x01\x7f", 5)), "\"a\\u0000b\\u0001\\u007f\"");
    EQ(H::jsonEscape("bad \xff\xc0\x80 x"), "\"bad \\ufffd\\ufffd\\ufffd x\"");
    EQ(H::jsonEscape("\xed\xa0\x80"), "\"\\ufffd\\ufffd\\ufffd\"");   // an encoded surrogate is invalid
    // \u escapes, pairs, lone surrogates
    CHECK(H::parseJson("\"\\ud83d\\ude00 \\u00e9 \\ud800x \\udc00\"", j));
    EQ(j.str, "\xf0\x9f\x98\x80 \xc3\xa9 \xef\xbf\xbdx \xef\xbf\xbd");
    CHECK(H::parseJson("\"\\ud800\\u0041\"", j));
    EQ(j.str, "\xef\xbf\xbd" "A");
    // structures
    CHECK(H::parseJson(" {\"a\":[1,2.5,-3e2,true,false,null,{\"b\":\"c\"}],\"d\":{}} ", j));
    CHECK(j.get("a") && j.get("a")->arr.size() == 7);
    CHECK(j.get("a")->arr[2].num == -300);
    EQ(j.get("a")->arr[6].s("b"), "c");
    CHECK(j.n("missing", 7) == 7);
    // garbage
    for (const char* bad : { "", "{", "[1,]", "{\"a\" 1}", "\"abc", "\"a\nb\"", "01x", "{\"a\":1} x", "nul", "\"\\x\"", "1e999" })
        CHECK(!H::parseJson(bad, j));
    std::string deep(40, '[');
    deep += std::string(40, ']');
    CHECK(!H::parseJson(deep, j));
}

static void testStore()
{
    std::vector<H::Item> v;
    CHECK(H::add(v, item(1, 100, "https://a.com/x", "first passage")));
    CHECK(H::add(v, item(2, 200, "https://a.com/x", kTricky, kTricky)));
    CHECK(H::add(v, item(3, 150, "https://b.com/", "  spaced \n\t text  ")));
    CHECK(!H::add(v, item(3, 1, "https://b.com/", "dup id")));
    CHECK(!H::add(v, item(4, 1, "https://b.com/", "  \n ")));        // no text
    CHECK(!H::add(v, item(5, 1, "", "no address")));
    EQ(v[2].exact, "spaced text");
    const std::string file = H::serialize(v);
    const std::vector<H::Item> back = H::parse(file);
    CHECK(back.size() == 3);
    if (back.size() == 3) {
        EQ(back[1].exact, v[1].exact);
        EQ(back[1].title, v[1].title);
        EQ(back[1].prefix, "before");
        EQ(back[1].suffix, "after");
        CHECK(back[1].at == 200 && back[1].id == 2);
        EQ(back[0].url, "https://a.com/x");
    }
    EQ(H::serialize(back), file);                                       // stable
    CHECK(H::nextId(back) == 4);
    // one item per line
    size_t lines = 0;
    for (char c : file) lines += c == '\n';
    CHECK(lines == 5);

    // caps of one item: the text is at most 2 KB
    H::Item big = item(9, 1, "https://c.com/", std::string(5000, 'x'), std::string(900, 't'));
    big.prefix = std::string(400, 'p'); big.suffix = std::string(400, 's');
    CHECK(H::clean(big));
    CHECK(big.exact.size() == H::kExactMaxBytes && big.prefix.size() == H::kContextMaxBytes && big.suffix.size() == H::kContextMaxBytes);
    CHECK(big.title.size() == H::kTitleMaxBytes);
    CHECK(H::itemBytes(big) <= H::kItemMaxBytes);
    H::Item cjk = item(10, 1, "https://c.com/", "", "");
    for (int i = 0; i < 1000; ++i) cjk.exact += "\xe6\xbc\xa2";
    cjk.prefix = "\xf0\x9f\x98\x80" + std::string(200, 'p');
    cjk.suffix = std::string(127, 's') + "\xe6\xbc\xa2";
    CHECK(H::clean(cjk));
    CHECK(cjk.exact.size() == 1599 && H::sanitize(cjk.exact) == cjk.exact);      // cut on a character
    EQ(cjk.prefix, std::string(128, 'p'));                                        // the tail, from a character
    EQ(cjk.suffix, std::string(127, 's'));

    // file-level: bad items skipped, duplicate ids, wrong types, unnormalised addresses normalised
    const std::string text = "{\"omni-highlights\":1,\"items\":["
        "{\"id\":1,\"at\":5,\"url\":\"https://X.com/p?utm_source=z#f\",\"e\":\"ok one\"},"
        "{\"id\":1,\"at\":6,\"url\":\"https://x.com/p\",\"e\":\"dup\"},"
        "{\"id\":2.5,\"url\":\"https://x.com/p\",\"e\":\"fraction id\"},"
        "{\"id\":-1,\"url\":\"https://x.com/p\",\"e\":\"negative\"},"
        "{\"id\":3,\"url\":\"about:blank\",\"e\":\"no web address\"},"
        "{\"id\":4,\"url\":\"https://x.com/p\",\"e\":\"\"},"
        "{\"id\":5,\"url\":\"https://x.com/p\",\"e\":7},"
        "[1,2], \"str\", null,"
        "{\"id\":6,\"at\":-9,\"url\":\"https://x.com/q\",\"e\":\"neg time\",\"title\":\"\\u2028t\"}"
        "]}";
    const std::vector<H::Item> p = H::parse(text);
    CHECK(p.size() == 2);
    if (p.size() == 2) {
        EQ(p[0].url, "https://x.com/p");
        EQ(p[0].exact, "ok one");
        CHECK(p[1].at == 0);
        EQ(p[1].title, "t");
    }
    CHECK(H::parse("not json").empty());
    CHECK(H::parse("{\"items\":{}}").empty());
    CHECK(H::parse(std::string(size_t(H::kMaxFileBytes) + 1, ' ')).empty());

    // 500 cap: add refuses, a larger file keeps the newest 500
    std::vector<H::Item> full;
    for (int i = 1; i <= 500; ++i) CHECK(H::add(full, item(i, i, "https://f.com/", "t" + std::to_string(i))));
    CHECK(!H::add(full, item(501, 501, "https://f.com/", "one more")));
    std::string f = "{\"items\":[";
    for (int i = 1; i <= 520; ++i) f += (i > 1 ? "," : "") + std::string("{\"id\":") + std::to_string(i) + ",\"at\":" + std::to_string(1000 - i) + ",\"url\":\"https://f.com/\",\"e\":\"x\"}";
    f += "]}";
    const std::vector<H::Item> capped = H::parse(f);
    CHECK(capped.size() == 500);
    bool newestKept = true;
    for (const H::Item& it : capped) if (it.id > 500) newestKept = false;   // ids 501..520 are the oldest
    CHECK(newestKept);

    // OMNI_HIGHLIGHTS_V1_R2: parseFile tells an unreadable file from an empty one (the shell then writes nothing)
    {
        std::vector<H::Item> pv { item(1, 1, "https://a.com/", "keep") };
        CHECK(H::parseFile("", pv) && pv.empty());
        CHECK(H::parseFile(" \r\n", pv) && pv.empty());
        CHECK(H::parseFile("{\"omni-highlights\":1,\"items\":[]}", pv) && pv.empty());
        CHECK(H::parseFile(H::serialize(full), pv) && pv.size() == 500);
        CHECK(!H::parseFile("not json", pv) && pv.empty());
        CHECK(!H::parseFile("{\"items\":{}}", pv));
        CHECK(!H::parseFile("{\"other\":1}", pv));
        CHECK(!H::parseFile("[1,2]", pv));
        CHECK(!H::parseFile(std::string(size_t(H::kMaxFileBytes) + 1, ' '), pv));
        CHECK(!H::parseFile(H::serialize(full).substr(0, 5000), pv) && pv.empty());   // a cut-off file
    }
    // OMNI_HIGHLIGHTS_V1_R2: the file never passes kMaxFileBytes. Worst-case items (long quoted text, long address)
    // fill it before 500; each serialized file still parses back whole.
    {
        CHECK(H::serializedBytes(full) == H::serialize(full).size());
        std::vector<H::Item> none;
        CHECK(H::serializedBytes(none) == H::serialize(none).size());
        std::vector<H::Item> huge;
        const std::string longPath = "https://big.example.com/" + std::string(1900, 'p');
        const std::string quotes(1600, '"');                                   // every byte escaped: 3200 bytes of JSON
        H::AddResult r = H::kAdded;
        long long id = 1;
        while ((r = H::addChecked(huge, item(id, id, longPath + std::to_string(id % 10), quotes, std::string(160, '\\')))) == H::kAdded) {
            ++id;
            CHECK(H::serializedBytes(huge) == H::serialize(huge).size());
            if (id > 600) break;
        }
        CHECK(r == H::kTooBig);
        CHECK(huge.size() < H::kMaxItems);
        const std::string hfile = H::serialize(huge);
        CHECK(hfile.size() <= size_t(H::kMaxFileBytes));
        std::vector<H::Item> hback;
        CHECK(H::parseFile(hfile, hback) && hback.size() == huge.size());
        CHECK(!H::add(huge, item(id + 1, 1, "https://s.com/", "tiny")) || H::serialize(huge).size() <= size_t(H::kMaxFileBytes));
        // the count cap still reports kFull, an unusable item kUnusable
        std::vector<H::Item> f2 = full;
        CHECK(H::addChecked(f2, item(900, 1, "https://f.com/", "x")) == H::kFull);
        std::vector<H::Item> e2;
        CHECK(H::addChecked(e2, item(1, 1, "", "no address")) == H::kUnusable);
        CHECK(H::addChecked(e2, item(1, 1, "https://a.com/", "fine")) == H::kAdded);
        CHECK(H::addChecked(e2, item(1, 1, "https://a.com/", "same id")) == H::kUnusable);
        EQ(H::bytesFullNotice(), "Highlights full: delete some in Options > Browse > Highlights");
    }

    // forUrl (oldest first), idsForUrl, removeIds, groups (pages newest first, items newest first)
    const std::vector<H::Item> fa = H::forUrl(v, "https://a.com/x");
    CHECK(fa.size() == 2 && fa[0].id == 1 && fa[1].id == 2);
    CHECK(H::forUrl(v, "").empty());
    const std::vector<H::Group> g = H::groups(v);
    CHECK(g.size() == 2);
    if (g.size() == 2) {
        EQ(g[0].url, "https://a.com/x");
        CHECK(g[0].newest == 200 && g[0].items.size() == 2 && g[0].items[0].id == 2);
        EQ(g[0].title, H::collapse(kTricky));   // the newest item's title
        EQ(g[1].url, "https://b.com/");
        EQ(H::pageDetail(g[0]), "a.com \xc2\xb7 2 highlights");
        EQ(H::pageDetail(g[1]), "b.com \xc2\xb7 1 highlight");
    }
    std::vector<H::Item> w = v;
    CHECK(H::removeIds(w, H::idsForUrl(w, "https://a.com/x")) == 2);
    CHECK(w.size() == 1 && w[0].id == 3);
    CHECK(H::removeIds(w, { 99 }) == 0);
}

static void testScriptAndAnswers()
{
    std::vector<H::Item> list = { item(7, 1, "https://a.com/", kTricky) };
    const std::string s = H::script('a', H::applyArg(list, 7));
    CHECK(s.rfind("(function(op,a){", 0) == 0);
    CHECK(s.find(")('a',{\"items\":[{\"i\":7,") != std::string::npos);
    CHECK(s.size() >= 3 && s.compare(s.size() - 3, 3, "7})") == 0);
    CHECK(s.find("\xe2\x80\xa8") == std::string::npos);
    EQ(H::script('x', ""), std::string("(") + H::kScript + ")('l',{})");
    EQ(H::createArg(12), "{\"i\":12}");
    EQ(H::removeArg({ 1, 22 }), "{\"ids\":[1,22]}");
    EQ(H::removeArg({}), "{\"ids\":[]}");
    EQ(H::applyArg({}, -4), "{\"items\":[],\"f\":0}");

    H::Created c = H::created("{\"ok\":1,\"e\":\"  some \\n text \",\"p\":\"pre \",\"s\":\" suf\",\"t\":\"Title\",\"u\":\"\",\"cut\":0}");
    CHECK(c.status == 0 && !c.cut);
    EQ(c.exact, "some text"); EQ(c.prefix, "pre"); EQ(c.suffix, "suf"); EQ(c.title, "Title");
    c = H::created("{\"ok\":1,\"e\":\"x\",\"cut\":1,\"u\":\"https://live.example/a\"}");
    CHECK(c.status == 0 && c.cut);
    EQ(c.live, "https://live.example/a");
    CHECK(H::created("{\"err\":\"none\"}").status == 1);
    CHECK(H::created("{\"err\":\"frame\"}").status == 2);
    CHECK(H::created("{\"ok\":1,\"e\":\" \"}").status == 1);
    CHECK(H::created("{}").status == 3);
    CHECK(H::created("").status == 3);
    CHECK(H::created("[1]").status == 3);
    c = H::created("{\"ok\":1,\"e\":\"" + std::string(3000, 'y') + "\"}");
    CHECK(c.status == 0 && c.cut && c.exact.size() == H::kExactMaxBytes);

    EQ(H::createErrorNotice(1), "Nothing selected to highlight");
    EQ(H::createErrorNotice(2), "Text inside a frame can't be highlighted");
    EQ(H::savedNotice(false), "Highlighted: Options > Browse > Highlights lists it");
    EQ(H::savedNotice(true), "Highlighted (the first 1,600 bytes): Options > Browse > Highlights lists it");
    EQ(H::deletePageTitle(1), "Delete the highlight on this page?");
    EQ(H::deletePageTitle(3), "Delete 3 highlights on this page?");
    EQ(H::panelSubtitle(1, 1), "1 highlight on 1 page \xc2\xb7 they come back when the page is opened");
    EQ(H::rowLabel(item(1, 1, "u", std::string(200, 'z'))), "\"" + std::string(107, 'z') + "...\"");
}

static void testDates()
{
    setenv("TZ", "UTC", 1);
    tzset();
    const long long now = 1794787200 + 12 * 3600;   // 2026-11-16 12:00 UTC
    EQ(H::dateText(now - 3600, now), "Today");
    EQ(H::dateText(now - 86400, now), "Yesterday");
    EQ(H::dateText(now - 3 * 86400, now), "13 Nov 2026");
    EQ(H::dateText(0, now), "1 Jan 1970");
}

static bool emit(const std::string& dir)
{
    auto put = [&](const std::string& name, const std::string& text) {
        std::ofstream f(dir + "/" + name, std::ios::binary);
        f << text;
        return bool(f);
    };
    std::vector<H::Item> tricky = { item(41, 1, "https://a.com/", kTricky) };
    tricky[0].prefix = "Intro: ";
    tricky[0].suffix = " The end.";
    return put("kscript.js", std::string("(") + H::kScript + ")\n")
        && put("call_apply.js", H::script('a', H::applyArg(tricky, 41)) + "\n")
        && put("call_create.js", H::script('c', H::createArg(42)) + "\n")
        && put("call_remove.js", H::script('r', H::removeArg({ 41, 42 })) + "\n")
        && put("call_live.js", H::script('l', "{}") + "\n")
        && put("tricky.txt", kTricky);
}

int main(int argc, char** argv)
{
    testUrl();
    testJson();
    testStore();
    testScriptAndAnswers();
    testDates();
    if (argc == 3 && std::string(argv[1]) == "--emit" && !emit(argv[2])) { fprintf(stderr, "emit failed\n"); return 2; }
    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
