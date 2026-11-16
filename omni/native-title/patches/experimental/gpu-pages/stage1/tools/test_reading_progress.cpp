// OMNI_READING_PROGRESS_V1 host test: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_reading_progress.cpp -o t && ./t <scratch dir>
// Checks the pure header: progress lines inside index.tsv (old 6-field parser still reads every page and skips them;
// round trip; bad lines; later line wins; only listed pages written), the finished rule (>= 95 %, sticky), the 1 % step,
// labels / row value, the restore target, the 7-day prune plan, the script result format. Writes the two page scripts
// (restore at 0, 400, 1000 permille) into the scratch dir for `node --check`.
#include "OmniReadingProgress.h"
#include <cstdio>
#include <string>
#include <vector>

namespace RL = OmniReadingList;
namespace ORPG = OmniReadingProgress;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static RL::Entry mk(const std::string& id, long long at)
{
    RL::Entry e; e.id = id; e.savedAt = at; e.bytes = 1000; e.url = "https://example.com/" + id; e.title = "T\t" + id;
    return e;
}
static bool writeFile(const std::string& path, const std::string& s)
{
    FILE* f = fopen(path.c_str(), "wb");
    if (!f) return false;
    const bool ok = fwrite(s.data(), 1, s.size(), f) == s.size();
    return fclose(f) == 0 && ok;
}

int main(int argc, char** argv)
{
    const long long day = 86400, t0 = 1763300000;
    std::vector<RL::Entry> list = { mk("a.com-20261116-140500.html", t0), mk("b.org-20261116-140600.html", t0 + 1), mk("c.net-20261116-140700.html", t0 + 2) };

    // update: first value, 1 % step, finished sticky
    ORPG::Progress p;
    CHECK(!ORPG::update(p, -1, t0) && !ORPG::update(p, 1001, t0) && p.permille == -1);
    CHECK(ORPG::update(p, 400, t0) && p.permille == 400 && p.at == t0 && !ORPG::finished(p));
    CHECK(!ORPG::update(p, 405, t0 + 5) && p.permille == 400 && p.at == t0);
    CHECK(ORPG::update(p, 390, t0 + 6) && p.permille == 390);
    CHECK(ORPG::update(p, 945, t0 + 7) && p.permille == 945 && !ORPG::finished(p));
    CHECK(!ORPG::update(p, 949, t0 + 8) && !ORPG::finished(p));             // 94.9 %: under the step, not finished
    p = ORPG::Progress();
    CHECK(ORPG::update(p, 949, t0) && !ORPG::finished(p) && ORPG::label(&p) == "94% read");
    CHECK(ORPG::update(p, 950, t0 + 10) && ORPG::finished(p) && p.finishedAt == t0 + 10);   // >= 95 %
    CHECK(ORPG::label(&p) == "Finished");
    CHECK(ORPG::update(p, 100, t0 + 20) && ORPG::finished(p) && p.finishedAt == t0 + 10);  // sticky, first time kept
    CHECK(ORPG::label(&p) == "Finished" && ORPG::restoreTo(&p) == 0);
    ORPG::Progress q;
    CHECK(ORPG::update(q, 955, t0) && ORPG::finished(q));                     // first reading already finished
    ORPG::Progress q2;
    CHECK(ORPG::update(q2, 1000, t0) && ORPG::finished(q2));

    // labels, row value, restore target
    CHECK(ORPG::label(nullptr).empty());
    ORPG::Progress z; z.permille = 5; z.at = t0;
    CHECK(ORPG::label(&z).empty() && ORPG::restoreTo(&z) == 0);
    z.permille = 10;
    CHECK(ORPG::label(&z) == "1% read" && ORPG::restoreTo(&z) == 10);
    z.permille = 400;
    CHECK(ORPG::label(&z) == "40% read" && ORPG::restoreTo(&z) == 400);
    CHECK(ORPG::rowValue(&z, "312 KB") == "40% read \xc2\xb7 312 KB");
    CHECK(ORPG::rowValue(nullptr, "312 KB") == "312 KB");
    CHECK(ORPG::rowValue(&p, "1.2 MB") == "Finished \xc2\xb7 1.2 MB");
    CHECK(ORPG::restoreTo(nullptr) == 0);

    // index round trip: page lines + progress lines in one file
    ORPG::Map m;
    m[list[0].id] = z;                                     // 40 %
    m[list[2].id] = p;                                     // finished
    m["gone.com-20261116-000000.html"] = z;                // not in the list: not written
    const std::string text = RL::serialize(list) + ORPG::lines(list, m);
    CHECK(text.find("gone.com") == std::string::npos);
    CHECK(text.find("p\ta.com-20261116-140500.html\t400\t") != std::string::npos);
    // the OLD reader (OMNI_READING_LIST_V1 parse) still gets every page, ignores the progress lines
    const auto pages = RL::parse(text);
    CHECK(pages.size() == 3 && pages[0].id == list[0].id && pages[2].id == list[2].id && pages[1].title == list[1].title);
    // every progress line has 5 fields (the old parser needs exactly 6 for a page) and "p" is no valid id
    {
        size_t at = 0; int pl = 0;
        while (at < text.size()) {
            size_t nl = text.find('\n', at); if (nl == std::string::npos) nl = text.size();
            const std::string line = text.substr(at, nl - at); at = nl + 1;
            if (line.rfind("p\t", 0) == 0) { ++pl; CHECK(RL::splitTabs(line).size() == 5); }
        }
        CHECK(pl == 2 && !RL::validId("p"));
    }
    const auto back = ORPG::parseLines(text);
    CHECK(back.size() == 2);
    CHECK(back.count(list[0].id) && back.at(list[0].id).permille == 400 && back.at(list[0].id).at == t0 && !ORPG::finished(back.at(list[0].id)));
    CHECK(back.count(list[2].id) && back.at(list[2].id).finishedAt == t0 + 10 && back.at(list[2].id).permille == 100);
    // CRLF file, a file written by an older Omni (no progress lines), wrong header, bad lines, later line wins
    std::string crlf;
    for (char c : text) { if (c == '\n') crlf += "\r\n"; else crlf += c; }
    CHECK(ORPG::parseLines(crlf).size() == 2 && RL::parse(crlf).size() == 3);
    CHECK(ORPG::parseLines(RL::serialize(list)).empty());
    CHECK(ORPG::parseLines("omni-reading-list\t2\np\ta.com-20261116-140500.html\t400\t1\t0\n").empty());
    CHECK(ORPG::parseLines("").empty());
    const std::string bad = std::string(RL::kHeader) + "\n"
        "p\ta.com-20261116-140500.html\t1001\t5\t0\n"          // permille out of range
        "p\t../x.html\t100\t5\t0\n"                            // bad id
        "p\tb.org-20261116-140600.html\t100\t0\t0\n"           // no time
        "p\tb.org-20261116-140600.html\t-5\t5\t0\n"            // negative
        "p\tb.org-20261116-140600.html\t100\t5\n"              // 4 fields
        "p\tb.org-20261116-140600.html\t100\t5\t0\textra\n"    // 6 fields (would look like a page line)
        "q\tc.net-20261116-140700.html\t100\t5\t0\n"           // other tag
        "p\tc.net-20261116-140700.html\t100\t5\t0\n"
        "p\tc.net-20261116-140700.html\t300\t6\t0\n"           // later wins
        "p\ta.com-20261116-140500.html\t960\t9\t0\n";          // >= 95 % without a finished time: finished at its time
    const auto bm = ORPG::parseLines(bad);
    CHECK(bm.size() == 2);
    CHECK(bm.count("c.net-20261116-140700.html") && bm.at("c.net-20261116-140700.html").permille == 300);
    CHECK(bm.count("a.com-20261116-140500.html") && bm.at("a.com-20261116-140500.html").finishedAt == 9);
    CHECK(RL::parse(bad).empty());   // no page lines at all: nothing for the old parser either
    // unknown permille not written
    ORPG::Map u; u[list[1].id] = ORPG::Progress();
    CHECK(ORPG::lines(list, u).empty());

    // prune plan: finished >= 7 days ago, only when enabled, list order
    ORPG::Map pm;
    ORPG::Progress f1; f1.permille = 980; f1.at = t0; f1.finishedAt = t0;
    ORPG::Progress f2; f2.permille = 990; f2.at = t0; f2.finishedAt = t0 + 3 * day;
    ORPG::Progress f3; f3.permille = 500; f3.at = t0;
    pm[list[0].id] = f2; pm[list[1].id] = f1; pm[list[2].id] = f3;
    CHECK(ORPG::prunePlan(list, pm, t0 + 30 * day, false).empty());
    CHECK(ORPG::prunePlan(list, pm, t0 + 7 * day - 1, true).empty());
    {
        const auto ids = ORPG::prunePlan(list, pm, t0 + 7 * day, true);
        CHECK(ids.size() == 1 && ids[0] == list[1].id);
        const auto ids2 = ORPG::prunePlan(list, pm, t0 + 10 * day, true);
        CHECK(ids2.size() == 2 && ids2[0] == list[0].id && ids2[1] == list[1].id);
        CHECK(ORPG::prunePlan({}, pm, t0 + 30 * day, true).empty());
    }

    // script results
    CHECK(ORPG::parseResult("ORP1:0") == 0 && ORPG::parseResult("ORP1:400") == 400 && ORPG::parseResult("ORP1:1000") == 1000);
    CHECK(ORPG::parseResult("ORP1:-1") == -1 && ORPG::parseResult("ORP1:1001") == -1 && ORPG::parseResult("ORP1:") == -1);
    CHECK(ORPG::parseResult("ORP1:ok") == -1 && ORPG::parseResult("") == -1 && ORPG::parseResult("400") == -1 && ORPG::parseResult("ORP1:4x") == -1);

    // scripts: whole, the permille in place, clamped
    const std::string rs = ORPG::restoreScript(400), r0 = ORPG::restoreScript(-5), r1 = ORPG::restoreScript(5000);
    CHECK(rs.rfind("(function(){var P=400/1000;", 0) == 0 && rs.size() > 60 && rs.substr(rs.size() - 4) == "})()");
    CHECK(r0.find("P=0/1000;") != std::string::npos && r1.find("P=1000/1000;") != std::string::npos);
    const std::string rd = ORPG::readScript();
    CHECK(rd.rfind("(function(){", 0) == 0 && rd.substr(rd.size() - 4) == "})()" && rd.find("omni-saved-banner") != std::string::npos);
    CHECK(rs.find("omni-saved-banner") != std::string::npos);

    if (argc > 1) {
        const std::string dir = argv[1];
        CHECK(writeFile(dir + "/rprog_read.js", rd));
        CHECK(writeFile(dir + "/rprog_restore.js", rs));
        CHECK(writeFile(dir + "/rprog_restore0.js", r0));
        CHECK(writeFile(dir + "/rprog_restore1000.js", r1));
        CHECK(writeFile(dir + "/rprog_index.tsv", text));
    }
    printf("%s: %d checks, %d failures\n", failures ? "FAIL" : "PASS", checks, failures);
    return failures ? 1 : 0;
}
