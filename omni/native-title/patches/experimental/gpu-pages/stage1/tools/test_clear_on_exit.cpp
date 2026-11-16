// OMNI_CLEAR_ON_EXIT_V1: host tests of OmniClearOnExit.h (the pure part of "Clear on exit").
//   g++ -std=c++20 -Wall -Wextra -Werror -fsanitize=address,undefined -I. test_clear_on_exit.cpp -o t && ./t
// With arguments (tools/test_clear_on_exit_db.py passes them): <Cookies.db> <Cookies.db-wal or -> <expected domains file>
// reads real SQLite files written by Python's sqlite3 with WebKit's Curl cookie schema and checks the domains found.
#include "OmniClearOnExit.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace C = OmniClearOnExit;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)
#define EQ(a, b) do { ++checks; const auto va = (a); const auto vb = (b); if (!(va == vb)) { ++fails; std::ostringstream o; o << va << " != " << vb; std::fprintf(stderr, "FAIL %s:%d: %s == %s (%s)\n", __FILE__, __LINE__, #a, #b, o.str().c_str()); } } while (0)

static void testHostKey()
{
    EQ(C::hostKey("https://WWW.Example.com:8443/x?y#z"), std::string("example.com"));
    EQ(C::hostKey("http://user:pw@Mail.Example.com/"), std::string("mail.example.com"));
    EQ(C::hostKey(".example.com"), std::string("example.com"));
    EQ(C::hostKey("  example.com.  "), std::string("example.com"));
    EQ(C::hostKey("www.example.co.uk"), std::string("example.co.uk"));
    EQ(C::hostKey("www.com"), std::string("www.com"));          // "www." stays when no dot would remain after it
    EQ(C::hostKey("www"), std::string("www"));
    EQ(C::hostKey("localhost"), std::string("localhost"));
    EQ(C::hostKey("192.168.0.10:8080"), std::string("192.168.0.10"));
    EQ(C::hostKey("xn--bcher-kva.example"), std::string("xn--bcher-kva.example"));
    EQ(C::hostKey("_dmarc.example.com"), std::string("_dmarc.example.com"));
    EQ(C::hostKey("about:blank"), std::string());
    EQ(C::hostKey("omni://pages/start"), std::string());
    EQ(C::hostKey("file:///data/x"), std::string());
    EQ(C::hostKey("https://[::1]/"), std::string());
    EQ(C::hostKey("a..b"), std::string());
    EQ(C::hostKey("-a.com"), std::string());
    EQ(C::hostKey("a-.com"), std::string());
    EQ(C::hostKey("exa mple.com"), std::string());
    EQ(C::hostKey("example.com:abc"), std::string());
    EQ(C::hostKey("example.com:"), std::string());
    EQ(C::hostKey("/"), std::string());
    EQ(C::hostKey(""), std::string());
    EQ(C::hostKey(std::string(64, 'a') + ".com"), std::string());
    EQ(C::hostKey(std::string(63, 'a') + ".com"), std::string(63, 'a') + ".com");
    std::string longHost;
    while (longHost.size() < 260) longHost += "abcdefghi.";
    longHost += "com";
    EQ(C::hostKey(longHost), std::string());
}

static void testKeepMatching()
{
    const std::vector<std::string> keep = { "example.com" };
    CHECK(C::keptBy("example.com", keep) == 0);
    CHECK(C::keptBy("mail.example.com", keep) == 0);
    CHECK(C::keptBy("a.b.example.com", keep) == 0);
    CHECK(C::keptBy("notexample.com", keep) < 0);
    CHECK(C::keptBy("example.co", keep) < 0);
    CHECK(C::keptBy("example.com.evil.net", keep) < 0);
    CHECK(C::keptBy("com", keep) == 0);   // a parent of a kept site: deleting it could reach the kept one
    // a kept subdomain protects its whole site (WebKit deletes by registrable domain)
    const std::vector<std::string> sub = { "mail.example.com" };
    CHECK(C::keptBy("example.com", sub) == 0);
    CHECK(C::keptBy("other.example.com", sub) == 0);
    CHECK(C::keptBy("example.net", sub) < 0);
    // ccTLD second levels
    const std::vector<std::string> uk = { "bbc.co.uk" };
    CHECK(C::keptBy("news.bbc.co.uk", uk) == 0);
    CHECK(C::keptBy("itv.co.uk", uk) < 0);
    CHECK(C::keptBy("co.uk", uk) == 0);
    // private suffixes: wider than libpsl, so more is kept (never less)
    const std::vector<std::string> gh = { "alice.github.io" };
    CHECK(C::keptBy("bob.github.io", gh) == 0);
    CHECK(C::keptBy("alice.github.io", gh) == 0);
    CHECK(C::keptBy("github.com", gh) < 0);
    // IPs and one-label hosts only match themselves (and dotted children)
    const std::vector<std::string> ip = { "192.168.0.10", "nas" };
    CHECK(C::keptBy("192.168.0.10", ip) == 0);
    CHECK(C::keptBy("192.168.0.11", ip) < 0);
    CHECK(C::keptBy("nas", ip) == 1);
    CHECK(C::keptBy("printer", ip) < 0);
    CHECK(C::keptBy("", keep) < 0);
    CHECK(C::keptBy("example.com", {}) < 0);
    // related is symmetric
    CHECK(C::related("a.example.com", "example.com") && C::related("example.com", "a.example.com"));
    CHECK(!C::related("", "") && !C::related("a.com", ""));
}

static void testSettingsEdit()
{
    C::Settings s;
    CHECK(!C::any(s));
    CHECK(C::addKeep(s, "https://www.Zeta.com/login"));
    CHECK(C::addKeep(s, "alpha.org"));
    CHECK(C::addKeep(s, "mail.alpha.org"));      // a separate entry (shown separately; both cover alpha.org)
    CHECK(!C::addKeep(s, "zeta.com"));          // exact duplicate
    CHECK(!C::addKeep(s, "about:blank"));
    EQ(s.keep.size(), size_t(3));
    EQ(s.keep[0], std::string("alpha.org"));
    EQ(s.keep[1], std::string("mail.alpha.org"));
    EQ(s.keep[2], std::string("zeta.com"));
    CHECK(C::removeExact(s, "mail.alpha.org"));
    CHECK(!C::removeExact(s, "mail.alpha.org"));
    CHECK(C::addKeep(s, "mail.alpha.org"));
    const auto gone = C::removeRelated(s, "https://docs.alpha.org/x");
    EQ(gone.size(), size_t(2));
    EQ(s.keep.size(), size_t(1));
    EQ(s.keep[0], std::string("zeta.com"));
    CHECK(C::removeRelated(s, "omni://pages").empty());
    C::Settings full;
    for (size_t i = 0; i < C::kMaxKeep; ++i) CHECK(C::addKeep(full, "s" + std::to_string(i) + ".example"));
    CHECK(!C::addKeep(full, "one-more.example"));
    EQ(full.keep.size(), C::kMaxKeep);
    CHECK(std::is_sorted(full.keep.begin(), full.keep.end()));
}

static void testFileFormat()
{
    // defaults: all off, nothing kept
    const C::Settings empty = C::parse("");
    CHECK(!empty.cookies && !empty.history && !empty.cache && empty.keep.empty());
    C::Settings s;
    s.cookies = true; s.cache = true;
    C::addKeep(s, "example.com");
    C::addKeep(s, "bbc.co.uk");
    const std::string text = C::serialize(s);
    EQ(text, std::string("# Omni clear on exit v1\ncookies=1\nhistory=0\ncache=1\nkeep=bbc.co.uk\nkeep=example.com\n"));
    const C::Settings back = C::parse(text);
    CHECK(back.cookies && !back.history && back.cache);
    CHECK(back.keep == s.keep);
    EQ(C::serialize(back), text);
    // CRLF, junk, unknown keys, bad and duplicate hosts, "true" is not "1", no final newline
    const C::Settings odd = C::parse("# x\r\ncookies=1\r\nhistory=true\r\nnonsense\r\nfuture=1\r\nkeep=https://www.Example.com/\r\n"
                                     "keep=example.com\r\nkeep=about:blank\r\nkeep=\r\nkeep=a..b\r\ncache=1");
    CHECK(odd.cookies && !odd.history && odd.cache);
    EQ(odd.keep.size(), size_t(1));
    EQ(odd.keep[0], std::string("example.com"));
    // later lines win; trailing spaces ignored
    const C::Settings twice = C::parse("cookies=1\ncookies=0  \nhistory=1\t\n");
    CHECK(!twice.cookies && twice.history);
    // at most kMaxKeep hosts read
    std::string many;
    for (size_t i = 0; i < C::kMaxKeep + 20; ++i) many += "keep=h" + std::to_string(i) + ".example\n";
    EQ(C::parse(many).keep.size(), C::kMaxKeep);
}

static void testPlan()
{
    const std::vector<std::string> keep = { "example.com", "bbc.co.uk" };
    const std::vector<std::string> cand = { ".example.com", "accounts.example.com", ".doubleclick.net", "doubleclick.net",
        "www.doubleclick.net", "news.bbc.co.uk", "itv.co.uk", "junk..name", "/", "", "https://www.shop.test/cart",
        "http://shop.test/", "about:blank", "Tracker.IO" };
    const C::Plan p = C::plan(cand, keep);
    const std::vector<std::string> want = { "doubleclick.net", "itv.co.uk", "shop.test", "tracker.io" };
    CHECK(p.hosts == want);
    EQ(p.keptSkipped, size_t(3));   // example.com, accounts.example.com, news.bbc.co.uk
    EQ(p.more, size_t(0));
    const C::Plan capped = C::plan(cand, keep, 2);
    EQ(capped.hosts.size(), size_t(2));
    EQ(capped.more, size_t(2));
    const C::Plan none = C::plan(cand, {});
    EQ(none.hosts.size(), size_t(7));
    EQ(none.keptSkipped, size_t(0));
    CHECK(C::removeCacheOrigin("www.itv.co.uk", keep));
    CHECK(!C::removeCacheOrigin("static.example.com", keep));
    CHECK(!C::removeCacheOrigin("[2001:db8::1]", keep));   // unreadable host with sites kept: left alone
}

// --- a hand-built SQLite page (the format as documented; the real files are checked by test_clear_on_exit_db.py) ----
static std::string varintBytes(uint64_t v)
{
    if (v < 0x80) return std::string(1, char(v));
    std::string rev;
    rev += char(v & 0x7f);
    v >>= 7;
    while (v) { rev += char(0x80 | (v & 0x7f)); v >>= 7; }
    return std::string(rev.rbegin(), rev.rend());
}
struct V { bool text; std::string s; long long n; };
static std::string recordBytes(const std::vector<V>& vals)
{
    std::string types, body;
    for (const auto& v : vals) {
        if (v.text) { types += varintBytes(13 + 2 * v.s.size()); body += v.s; }
        else { types += varintBytes(1); body += char(v.n & 0xff); }
    }
    std::string hdr = varintBytes(types.size() + 1) + types;   // header size < 128 here
    return hdr + body;
}
static void put16(std::string& p, size_t at, uint32_t v) { p[at] = char(v >> 8); p[at + 1] = char(v & 0xff); }
static void put32(std::string& p, size_t at, uint32_t v) { for (int i = 0; i < 4; ++i) p[at + i] = char((v >> (24 - 8 * i)) & 0xff); }
// cells: the full cell bytes; placed from the end of the page.
static std::string pageBytes(size_t ps, size_t hdrOff, unsigned char type, const std::vector<std::string>& cells)
{
    std::string p(ps, '\0');
    p[hdrOff] = char(type);
    put16(p, hdrOff + 3, uint32_t(cells.size()));
    const size_t ptrs = hdrOff + (type == 0x02 || type == 0x05 ? 12 : 8);
    size_t end = ps;
    for (size_t i = 0; i < cells.size(); ++i) {
        end -= cells[i].size();
        p.replace(end, cells[i].size(), cells[i]);
        put16(p, ptrs + 2 * i, uint32_t(end));
    }
    put16(p, hdrOff + 5, uint32_t(end));
    return p;
}
static std::string tableCell(long long rowid, const std::string& rec) { return varintBytes(rec.size()) + varintBytes(rowid) + rec; }
static std::string indexCell(const std::string& rec) { return varintBytes(rec.size()) + rec; }
static std::set<std::string> keys(const std::vector<std::string>& v)
{
    std::set<std::string> out;
    for (const auto& s : v) if (!C::hostKey(s).empty()) out.insert(C::hostKey(s));
    return out;
}

static void testSqlitePages()
{
    const size_t ps = 1024;
    std::string file(ps * 4, '\0');
    // page 1: file header + a table leaf like sqlite_master (5 columns, column 3 an integer: not a cookie row)
    std::string page1 = pageBytes(ps, 100, 0x0d, { tableCell(1, recordBytes({ { true, "table", 0 }, { true, "Cookie", 0 }, { true, "Cookie", 0 },
                                                                                { false, "", 2 }, { true, "CREATE TABLE Cookie(...)", 0 } })) });
    std::memcpy(page1.data(), "SQLite format 3\0", 16);
    put16(page1, 16, uint32_t(ps));
    page1[20] = 0;
    file.replace(0, ps, page1);
    // page 2: Cookie rows (name, value, domain, path, expires, size, session, httponly, secure, lastupdated)
    auto row = [](const std::string& name, const std::string& value, const std::string& domain) {
        return recordBytes({ { true, name, 0 }, { true, value, 0 }, { true, domain, 0 }, { true, "/", 0 }, { false, "", 1 },
                             { false, "", 9 }, { false, "", 0 }, { false, "", 1 }, { false, "", 1 }, { false, "", 5 } });
    };
    file.replace(ps, ps, pageBytes(ps, 0, 0x0d, { tableCell(1, row("SID", "abc123", ".google.com")),
                                                  tableCell(2, row("id", "x.y.z", "ads.tracker.example")) }));
    // page 3: domain_index leaf (domain, rowid) + a path_index entry, which is skipped
    file.replace(2 * ps, ps, pageBytes(ps, 0, 0x0a, { indexCell(recordBytes({ { true, "only-in-index.test", 0 }, { false, "", 7 } })),
                                                      indexCell(recordBytes({ { true, "/account", 0 }, { false, "", 8 } })) }));
    // page 4: autoindex interior page (name, domain, path, rowid) with a 4-byte child pointer per cell
    {
        std::string cell = std::string(4, '\0') + indexCell(recordBytes({ { true, "pref", 0 }, { true, ".interior.example", 0 },
                                                                           { true, "/", 0 }, { false, "", 3 } }));
        put32(cell, 0, 2);
        std::string pg = pageBytes(ps, 0, 0x02, { cell });
        put32(pg, 8, 3);   // right-most child
        file.replace(3 * ps, ps, pg);
    }
    std::vector<std::string> found;
    size_t reserved = 99;
    CHECK(C::dbDomains(file, found, &reserved));
    EQ(reserved, size_t(0));
    const std::set<std::string> want = { "google.com", "ads.tracker.example", "only-in-index.test", "interior.example" };
    CHECK(keys(found) == want);
    CHECK(std::find(found.begin(), found.end(), std::string("Cookie")) == found.end());

    // the index page as a WAL frame (page number 3)
    std::string wal(32, '\0');
    put32(wal, 0, 0x377f0682u);
    put32(wal, 8, uint32_t(ps));
    std::string frame(24, '\0');
    put32(frame, 0, 3);
    wal += frame + file.substr(2 * ps, ps);
    std::vector<std::string> walFound;
    CHECK(C::walDomains(wal, 0, walFound));
    CHECK(keys(walFound) == std::set<std::string>({ "only-in-index.test" }));

    // not SQLite / damaged: nothing, no crash
    std::vector<std::string> none;
    CHECK(!C::dbDomains("", none));
    CHECK(!C::dbDomains(std::string(200, 'x'), none));
    std::string badSize = file;
    put16(badSize, 16, 1000);
    CHECK(!C::dbDomains(badSize, none));
    CHECK(!C::walDomains(std::string(10, '\0'), 0, none));
    CHECK(!C::walDomains(file, 0, none));
    CHECK(none.empty());
    std::vector<std::string> cut;
    CHECK(C::dbDomains(file.substr(0, ps + 700), cut));   // a partial last page is not read
    CHECK(cut.empty());
    // a cell pointer past the page, a huge payload size, a header size past the record: skipped
    std::string broken = file;
    put16(broken, ps + 8, 0xfff0);
    broken[2 * ps + ps - 30] = char(0xff);
    std::vector<std::string> some;
    CHECK(C::dbDomains(broken, some));

    // random bytes in every page type: must not crash (sanitizers watch)
    uint32_t seed = 12345;
    auto rnd = [&] { seed = seed * 1103515245u + 12345u; return (seed >> 16) & 0xff; };
    for (int round = 0; round < 3000; ++round) {
        std::string f = file;
        const size_t page = 1 + rnd() % 3;
        for (int k = 0; k < 40; ++k) f[page * ps + (rnd() * 256 + rnd()) % ps] = char(rnd());
        if (round % 3 == 0) f[page * ps] = char(round % 2 ? 0x0a : 0x0d);
        std::vector<std::string> junk;
        C::dbDomains(f, junk);
        const C::Plan p = C::plan(junk, { "google.com" });
        for (const auto& h : p.hosts) CHECK(C::keptBy(h, { "google.com" }) < 0);
    }
}

static void testLocalBytes()
{
    // U = 4096: table leaf X = 4061; index X = ((4084 * 64) / 255) - 23 = 1002, M = ((4084 * 32) / 255) - 23 = 489
    EQ(C::localBytes(100, 4096, true), size_t(100));
    EQ(C::localBytes(4061, 4096, true), size_t(4061));
    EQ(C::localBytes(1002, 4096, false), size_t(1002));
    const size_t M = 489, K = M + (5000 - M) % (4096 - 4);
    EQ(C::localBytes(5000, 4096, false), K <= 1002 ? K : M);
}

static void testTexts()
{
    C::Settings s;
    EQ(C::settingsValue(s), std::string("Off"));
    EQ(C::settingsDetail(s), std::string("Nothing is cleared when Omni closes"));
    s.history = true;
    EQ(C::settingsValue(s), std::string("History"));
    s.cookies = true; s.cache = true;
    EQ(C::settingsValue(s), std::string("Cookies, history, cache"));
    C::addKeep(s, "example.com");
    EQ(C::settingsDetail(s), std::string("Cleared when Omni next starts; 1 kept site"));
    EQ(C::cookiesDetail(s), std::string("Every site except 1 kept site; site storage stays while sites are kept"));
    CHECK(C::askCookiesBody(0).find("signed out everywhere") != std::string::npos);
    CHECK(C::askCookiesBody(2).find("2 kept sites") != std::string::npos);
    EQ(C::siteValue("example.com", false, s.keep), std::string("On"));
    EQ(C::siteValue("mail.example.com", false, s.keep), std::string("On (example.com)"));
    EQ(C::siteValue("other.net", false, s.keep), std::string("Off"));
    EQ(C::siteValue("example.com", true, s.keep), std::string("Private tab"));
    EQ(C::siteValue("", false, s.keep), std::string("-"));
    EQ(C::keptNotice("a.com", true, false), std::string("a.com: cookies kept when Omni clears on exit (Clear on exit is off for cookies)"));
    EQ(C::keptNotice("a.com", false, true), std::string("a.com: no longer kept"));
    C::Result r;
    r.cookies = true; r.cookiesAll = true; r.history = true; r.visits = 12; r.cache = true;
    EQ(C::summary(r), std::string("Clear on exit: cleared cookies and site data, history (12 visits), cached files."));
    C::Result k;
    k.cookies = true; k.sites = 41; k.keepCount = 3; k.more = 2;
    EQ(C::summary(k), std::string("Clear on exit: cleared cookies of 41 sites (3 kept sites left alone). Not cleared: cookies of 2 more sites (limit 1500)."));
    C::Result t;
    t.cookies = true; t.cookiesOk = false; t.cache = true; t.cacheOk = false;
    EQ(C::summary(t), std::string("Clear on exit: nothing cleared. Not cleared: some cookies (no answer in time), cached files (no answer in time)."));
    CHECK(C::expired(0, C::kNativeMs) && !C::expired(0, C::kNativeMs - 1));
    CHECK(C::expired(0xffffff00u, C::kNativeMs - 0x100u) && !C::expired(0xffffff00u, 0x10u));
}

static std::string readAll(const char* path)
{
    std::ifstream f(path, std::ios::binary);
    return std::string(std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>());
}

int main(int argc, char** argv)
{
    testHostKey();
    testKeepMatching();
    testSettingsEdit();
    testFileFormat();
    testPlan();
    testLocalBytes();
    testSqlitePages();
    testTexts();
    if (argc == 4) {   // real SQLite files
        std::vector<std::string> found;
        size_t reserved = 0;
        const std::string db = readAll(argv[1]);
        CHECK(C::dbDomains(db, found, &reserved));
        size_t fromDb = keys(found).size();
        if (std::string(argv[2]) != "-") CHECK(C::walDomains(readAll(argv[2]), reserved, found));
        std::set<std::string> want;
        std::istringstream in(readAll(argv[3]));
        for (std::string line; std::getline(in, line);) if (!line.empty()) want.insert(C::hostKey(line));
        const std::set<std::string> got = keys(found);
        for (const auto& w : want) if (!got.count(w)) { ++fails; std::fprintf(stderr, "FAIL real db: %s not found\n", w.c_str()); }
        for (const auto& g : got) if (!want.count(g)) { ++fails; std::fprintf(stderr, "FAIL real db: unexpected %s\n", g.c_str()); }
        ++checks;
        std::printf("real db: %zu domains (%zu from the main file, %zu values read)\n", got.size(), fromDb, found.size());
    }
    std::printf("%d checks, %d failures\n", checks, fails);
    return fails ? 1 : 0;
}
