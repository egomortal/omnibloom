// OMNI_READING_LIST_V1 host test: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_reading_list.cpp -o t && ./t <scratch dir>
// Checks the pure header: TSV escaping, index round trip and bad-line handling, the 500 MB / 200 page caps (oldest
// dropped), file names, size/date text, the saved-document wrapper (CSP first in <head>, banner first in <body>,
// escaping, missing head/body) and the capture script's result format. Writes one wrapped page into the scratch dir.
#include "OmniReadingList.h"
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>
#include <vector>

namespace RL = OmniReadingList;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static RL::Entry mk(const std::string& id, long long at, long long bytes)
{
    RL::Entry e; e.id = id; e.savedAt = at; e.bytes = bytes; e.url = "https://example.com/" + id; e.title = "T " + id;
    return e;
}

int main(int argc, char** argv)
{
    setenv("TZ", "UTC", 1);
    tzset();

    // escaping
    const std::string nasty = "a\tb\nc\\d\re";
    CHECK(RL::escapeField(nasty) == "a\\tb\\nc\\\\d\\re");
    CHECK(RL::unescapeField(RL::escapeField(nasty)) == nasty);
    CHECK(RL::escapeField(nasty).find('\t') == std::string::npos);

    // ids
    CHECK(RL::validId("example.com-20261116-140500.html"));
    CHECK(RL::validId("page-20261116-140500-2.html"));
    CHECK(!RL::validId("../etc/passwd.html"));
    CHECK(!RL::validId("a/b.html"));
    CHECK(!RL::validId("index.tsv"));
    CHECK(!RL::validId("Example.html"));
    CHECK(!RL::validId(".hidden.html"));
    CHECK(!RL::validId("x..y.html"));

    // index round trip
    std::vector<RL::Entry> list = { mk("a.com-20261101-000000.html", 100, 10), mk("b.com-20261102-000000.html", 200, 20) };
    list[1].title = "Tabs\tand\nnew lines \\ and \xe2\x9c\x93 unicode"; list[1].textOnly = true;
    list[0].url = "https://a.com/?q=x\ty";
    const std::string text = RL::serialize(list);
    CHECK(text.compare(0, 19, "omni-reading-list\t1") == 0);
    auto back = RL::parse(text);
    CHECK(back.size() == 2);
    if (back.size() == 2) {
        CHECK(back[0].id == list[0].id && back[0].savedAt == 100 && back[0].bytes == 10 && !back[0].textOnly && back[0].url == list[0].url);
        CHECK(back[1].title == list[1].title && back[1].textOnly);
    }
    // CRLF, bad lines, duplicates, unknown header
    std::string crlf;
    for (char c : text) { if (c == '\n') crlf += '\r'; crlf += c; }
    CHECK(RL::parse(crlf).size() == 2);
    std::string bad = text + "garbage line\n" + "../x.html\t1\t1\th\tu\tt\n" + "c.com-1.html\tabc\t1\th\tu\tt\n"
        + "c.com-2.html\t0\t1\th\tu\tt\n" + "c.com-3.html\t5\t1\tz\tu\tt\n" + list[0].id + "\t9\t9\th\tu\tdup\n" + "\n";
    CHECK(RL::parse(bad).size() == 2);
    CHECK(RL::parse("omni-reading-list\t2\n" + text.substr(text.find('\n') + 1)).empty());
    CHECK(RL::parse("").empty());
    CHECK(RL::parse(std::string(RL::kHeader) + "\n").empty());

    // caps: count
    {
        std::vector<RL::Entry> l;
        for (int i = 0; i < 200; ++i) l.push_back(mk("p" + std::to_string(i) + ".html", 1000 - i, 1));   // p199 is the oldest
        bool fits = false;
        auto dropped = RL::makeRoom(l, 1, fits);
        CHECK(fits && dropped.size() == 1 && dropped[0].id == "p199.html" && l.size() == 199);
        l.push_back(mk("new.html", 5000, 1));
        dropped = RL::makeRoom(l, 1, fits);
        CHECK(dropped.size() == 1 && dropped[0].id == "p198.html");
    }
    // caps: bytes (500 MB), oldest first, several at once
    {
        const long long MB = 1024 * 1024;
        std::vector<RL::Entry> l = { mk("c.html", 30, 200 * MB), mk("a.html", 10, 150 * MB), mk("b.html", 20, 100 * MB) };
        bool fits = false;
        auto dropped = RL::makeRoom(l, 40 * MB, fits);
        CHECK(fits && dropped.empty() && l.size() == 3);                           // 450 + 40 <= 500
        {
            auto copy = l;
            dropped = RL::makeRoom(copy, 200 * MB, fits);                          // 450 + 200: only a (150) goes, 500 fits
            CHECK(fits && dropped.size() == 1 && dropped[0].id == "a.html" && copy.size() == 2);
        }
        dropped = RL::makeRoom(l, 250 * MB, fits);                                 // 450 + 250: a (150) and b (100) go
        CHECK(fits && dropped.size() == 2 && dropped[0].id == "a.html" && dropped[1].id == "b.html");
        CHECK(l.size() == 1 && l[0].id == "c.html" && RL::totalBytes(l) == 200 * MB);
        dropped = RL::makeRoom(l, 501 * MB, fits);                                 // larger than the whole cap
        CHECK(!fits && dropped.empty() && l.size() == 1);
        dropped = RL::makeRoom(l, 500 * MB, fits);                                 // exactly the cap: everything else goes
        CHECK(fits && dropped.size() == 1 && l.empty());
    }
    {   // small custom caps
        std::vector<RL::Entry> l = { mk("x.html", 1, 5), mk("y.html", 2, 5) };
        bool fits = false;
        auto dropped = RL::makeRoom(l, 1, fits, 100, 2);
        CHECK(fits && dropped.size() == 1 && dropped[0].id == "x.html");
        dropped = RL::makeRoom(l, 1, fits, 100, 0);
        CHECK(!fits && dropped.empty());
    }
    {
        auto nf = RL::newestFirst({ mk("o.html", 1, 1), mk("n.html", 3, 1), mk("m.html", 2, 1) });
        CHECK(nf[0].id == "n.html" && nf[1].id == "m.html" && nf[2].id == "o.html");
    }

    // names
    struct tm when {};
    when.tm_year = 2026 - 1900; when.tm_mon = 10; when.tm_mday = 16; when.tm_hour = 14; when.tm_min = 5; when.tm_sec = 9;
    std::set<std::string> taken;
    auto exists = [&](const std::string& n) { return taken.count(n) > 0; };
    std::string id = RL::makeId("https://www.Example.COM:8443/a?b", when, exists);
    CHECK(id == "example.com-20261116-140509.html");
    taken.insert(id);
    CHECK(RL::makeId("https://example.com/other", when, exists) == "example.com-20261116-140509-2.html");
    CHECK(RL::makeId("about:blank", when, exists) == "page-20261116-140509.html");
    CHECK(RL::validId(RL::makeId("https://xn--bcher-kva.example/", when, exists)));
    CHECK(RL::makeId("https://a.com/", when, [](const std::string&) { return true; }).empty());
    CHECK(RL::site("https://www.news.example.org/x") == "news.example.org");
    CHECK(RL::site("about:blank").empty());

    // sizes / dates
    CHECK(RL::sizeText(0) == "0 KB");
    CHECK(RL::sizeText(1) == "1 KB");
    CHECK(RL::sizeText(1536 * 1024) == "1.5 MB");
    const time_t now = 1794837600;   // 2026-11-16 14:00 UTC (a Monday)
    CHECK(RL::dateText(now - 3600, now) == "Today 13:00");
    CHECK(RL::dateText(now - 86400, now) == "Yesterday 14:00");
    CHECK(RL::dateText(now - 10 * 86400, now) == "6 Nov");
    CHECK(RL::dateText(now - 400 * 86400, now) == "12 Oct 2025");
    CHECK(RL::longDate(when) == "16 Nov 2026, 14:05");

    // the saved document
    const std::string url = "https://example.com/a?x=1&y=\"2\"";
    std::string page = "<!doctype html><html lang=en><HEAD data-x=\"a>b\"><title>T</title></HEAD><body class=\"main\"><p>Hi</p></body></html>";
    std::string doc = RL::wrapSaved(page, url, "16 Nov 2026, 14:05", false);
    const size_t csp = doc.find("Content-Security-Policy"), head = doc.find("<HEAD"), title = doc.find("<title>");
    CHECK(csp != std::string::npos && head < csp && csp < title);                  // CSP before anything the page had
    CHECK(doc.find("script-src 'none'") != std::string::npos && doc.find("form-action 'none'") != std::string::npos);
    CHECK(doc.find("data-x=\"a>b\"><meta charset") != std::string::npos);           // quoted '>' skipped
    const size_t body = doc.find("<body class=\"main\">"), ban = doc.find("omni-saved-banner"), hi = doc.find("<p>Hi");
    CHECK(body < ban && ban < hi);
    CHECK(doc.find("href=\"https://example.com/a?x=1&amp;y=&quot;2&quot;\"") != std::string::npos);
    CHECK(doc.find("Saved copy") != std::string::npos);
    // <header> is not <head>, <bodyx> is not <body>
    doc = RL::wrapSaved("<html><header>h</header><bodyx></bodyx></html>", url, "w", false);
    CHECK(doc.find("<html><head><meta charset") == 0);
    CHECK(doc.find("</head><div id=\"omni-saved-banner\"") != std::string::npos);
    doc = RL::wrapSaved("<!DOCTYPE html><p>bare</p>", url, "w", true);
    CHECK(doc.find("<!DOCTYPE html><head><meta charset") == 0);
    CHECK(doc.find("Saved text") != std::string::npos);
    doc = RL::wrapSaved("", url, "w", false);
    CHECK(doc.find("<head>") == 0 && doc.find("omni-saved-banner") != std::string::npos);
    // text-only page
    const std::string td = RL::textDocument("Line <1>\r\n\n  \nLine & 2\n", "A <title>");
    CHECK(td.find("<p>Line &lt;1&gt;</p>") != std::string::npos && td.find("<p>Line &amp; 2</p>") != std::string::npos);
    CHECK(td.find("<title>A &lt;title&gt;</title>") != std::string::npos && td.find("<p></p>") == std::string::npos);
    CHECK(td.find("<script") == std::string::npos);

    // the script's answer
    std::string t, b;
    bool textOnly = true;
    CHECK(RL::parsePayload(std::string("OMNIRL1\x01") + "My page\x01h\x01<!doctype html><html></html>", t, textOnly, b));
    CHECK(t == "My page" && !textOnly && b == "<!doctype html><html></html>");
    CHECK(RL::parsePayload(std::string("OMNIRL1\x01\x01t\x01some text"), t, textOnly, b) && t.empty() && textOnly && b == "some text");
    CHECK(!RL::parsePayload(std::string("OMNIRL1\x01title\x01h\x01"), t, textOnly, b));   // empty body
    CHECK(!RL::parsePayload(std::string("OMNIRL1\x01title\x01x\x01body"), t, textOnly, b));
    CHECK(!RL::parsePayload(std::string("OMNIRL1\x01title\x01h"), t, textOnly, b));
    CHECK(!RL::parsePayload("", t, textOnly, b));
    CHECK(!RL::parsePayload("{\"html\":1}", t, textOnly, b));

    if (argc > 1) {
        const std::string dir = std::string(argv[1]) + "/reading-list";
        CHECK(OmniQuickActions::makeDirs(dir));
        const std::string path = dir + "/" + RL::makeId("https://example.com/", when, [&](const std::string& n) { return OmniQuickActions::fileExists(dir + "/" + n); });
        if (FILE* f = fopen(path.c_str(), "wb")) {
            const std::string out = RL::wrapSaved(page, url, RL::longDate(when), false);
            fwrite(out.data(), 1, out.size(), f);
            fclose(f);
            printf("wrote %s\n", path.c_str());
        }
    }
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
