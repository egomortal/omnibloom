// OMNI_BOOKMARKS_MANAGER_V1: host tests for engine/entry/OmniBookmarksModel.h (written by apply_bookmarks_manager.py).
//   g++ -std=c++20 -Wall -Wextra -Wshadow -I<tree>/engine/entry test_bookmarks_manager.cpp -o t
//   ./t                                   unit tests
//   ./t setup <setup.txt> <omni.txt>      a file written by the Setup (test_bookmarks_manager_ref.py gen): read it,
//                                         check it, put bookmarks in folders, write what Omni would save
//   ./t reread <omni.txt> <merged.txt>    the Setup appended a PC import onto Omni's file: folders kept, new ones loose
#include "OmniBookmarksModel.h"
#include <cstdio>
#include <fstream>
#include <iterator>
#include <sstream>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniBookmarksModel;

static std::string readFile(const char* p)
{
    std::ifstream f(p, std::ios::binary);
    return std::string(std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>());
}
static void writeFile(const char* p, const std::string& s) { std::ofstream(p, std::ios::binary) << s; }

// The OMNI_FEATURES_V1 loader (before this change), on bytes: url = before the first tab, title = the rest.
static std::vector<std::pair<std::string, std::string>> oldOmniRead(const std::string& data)
{
    std::vector<std::pair<std::string, std::string>> out;
    size_t i = 0;
    while (i < data.size() && out.size() < 500) {
        const size_t nl = data.find('\n', i);
        const size_t stop = nl != std::string::npos && nl < i + 2399 ? nl + 1 : std::min(i + 2399, data.size());
        std::string s = data.substr(i, stop - i);
        i = stop;
        if (s.find('\0') != std::string::npos) s.resize(s.find('\0'));
        while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
        const size_t t = s.find('\t');
        std::string url = t == std::string::npos ? s : s.substr(0, t), title = t == std::string::npos ? std::string() : s.substr(t + 1);
        if (!url.empty()) out.emplace_back(url, title.empty() ? url : title);
    }
    return out;
}
static std::vector<std::string> urls(const std::vector<Entry>& l) { std::vector<std::string> u; for (auto& e : l) u.push_back(e.url); return u; }
static Entry E(const char* u, const char* t, const char* f = "") { return Entry { u, t, f }; }

static void unit()
{
    // old format, unchanged
    {
        const std::string old = "https://a.example/\tA\nhttps://b.example/\n\nhttps://c.example/\tC\r\n\thttps://no-url\n";
        const auto l = parse(old);
        CHECK(l.size() == 3);
        CHECK(l[0] == E("https://a.example/", "A"));
        CHECK(l[1] == E("https://b.example/", "https://b.example/"));
        CHECK(l[2] == E("https://c.example/", "C"));
        CHECK(serialize(l) == "https://a.example/\tA\nhttps://b.example/\thttps://b.example/\nhttps://c.example/\tC\n");
        // a file without folders written by the old code stays byte-identical
        const std::string saved = "https://a.example/\tA\nhttps://b.example/\tB\n";
        CHECK(serialize(parse(saved)) == saved);
    }
    // folder column, extra columns ignored, folder names cleaned
    {
        const auto l = parse("https://a.example/\tA\tWork\nhttps://b.example/\tB\t  Two   words \tfuture\tmore\nhttps://c.example/\tC\t\n");
        CHECK(l.size() == 3);
        CHECK(l[0].folder == "Work" && l[0].title == "A");
        CHECK(l[1].folder == "Two words" && l[1].title == "B");
        CHECK(l[2].folder.empty() && l[2].title == "C");
        CHECK(serializeLine(l[1]) == "https://b.example/\tB\tTwo words\n");
        CHECK(serializeLine(l[2]) == "https://c.example/\tC\n");
        CHECK(cleanFolder(std::string(60, 'f')).size() == kFolderMax);
        CHECK(cleanFolder("\t\r\n ") .empty());
        CHECK(cleanFolder(std::string(39, 'a') + "\xc3\xa9") == std::string(39, 'a'));   // cut on a character
    }
    // what older Omni sees in a new file: the same addresses, in the same order
    {
        std::vector<Entry> l = { E("https://a.example/", "A", "Work"), E("https://b.example/", "B"), E("https://c.example/", "C", "Fun") };
        const auto old = oldOmniRead(serialize(l));
        CHECK(old.size() == 3);
        for (size_t i = 0; i < old.size() && i < l.size(); ++i) CHECK(old[i].first == l[i].url);
        CHECK(old[0].second == "A\tWork");   // older Omni: the folder shows after the title
        CHECK(old[1].second == "B");
    }
    // fgets(2400) splitting, NUL, cap
    {
        const std::string longLine = "https://x.example/" + std::string(3000, 'x');
        const auto l = parse(longLine + "\nhttps://y.example/\tY\n");
        CHECK(l.size() == 3);
        CHECK(l[0].url.size() == 2399 && l[1].url.size() == longLine.size() - 2399 && l[2].url == "https://y.example/");
        CHECK(urls(l) == [&] { std::vector<std::string> u; for (auto& p : oldOmniRead(longLine + "\nhttps://y.example/\tY\n")) u.push_back(p.first); return u; }());
        const auto z = parse(std::string("https://z.example/\tZ\0junk\tF\n", 26));
        CHECK(z.size() == 1 && z[0].title == "Z" && z[0].folder.empty());
        std::string many;
        for (int i = 0; i < 600; ++i) many += "https://e" + std::to_string(i) + ".example/\tT\n";
        CHECK(parse(many).size() == 500);
        CHECK(parse(many, 10).size() == 10);
        // the longest line Omni writes still fits one fgets buffer
        const Entry big { "https://" + std::string(3000, 'u'), std::string(500, 't'), std::string(80, 'f') };
        const std::string line = serializeLine(big);
        CHECK(line.size() <= kLineBuffer - 1);
        const auto back = parse(line);
        CHECK(back.size() == 1 && back[0].url.size() == kUrlMax && back[0].title.size() == kTitleMax && back[0].folder.size() == kFolderMax);
    }
    // folders, normalize, reorder
    {
        std::vector<Entry> l = { E("u1", "1"), E("u2", "2", "B"), E("u3", "3", "A"), E("u4", "4"), E("u5", "5", "B") };
        CHECK((folders(l) == std::vector<std::string> { "B", "A" }));
        CHECK(folderCount(l, "B") == 2 && folderCount(l, "") == 2);
        normalize(l);
        CHECK((urls(l) == std::vector<std::string> { "u2", "u5", "u3", "u1", "u4" }));
        CHECK(moveEntry(l, 1, -1) == 0);
        CHECK((urls(l) == std::vector<std::string> { "u5", "u2", "u3", "u1", "u4" }));
        CHECK(moveEntry(l, 0, -1) == -1);          // first in its folder
        CHECK(moveEntry(l, 1, 1) == -1);           // last in B (u3 is in A)
        CHECK(moveEntry(l, 2, 1) == -1);           // only one in A
        CHECK(moveEntry(l, 3, 1) == 4);            // loose ones swap
        CHECK((urls(l) == std::vector<std::string> { "u5", "u2", "u3", "u4", "u1" }));
        CHECK(moveEntry(l, 9, 1) == -1 && moveEntry(l, -1, 1) == -1);
        CHECK(moveFolder(l, "A", -1));
        CHECK((urls(l) == std::vector<std::string> { "u3", "u5", "u2", "u4", "u1" }));
        CHECK(!moveFolder(l, "A", -1) && !moveFolder(l, "nope", 1));
        CHECK(moveFolder(l, "A", 1));
        CHECK((folders(l) == std::vector<std::string> { "B", "A" }));
        // setFolderAt: existing folder (last in it), new folder (after the others), none (last)
        CHECK(setFolderAt(l, "u1", "B") == 2);
        CHECK((urls(l) == std::vector<std::string> { "u5", "u2", "u1", "u3", "u4" }));
        CHECK(setFolderAt(l, "u4", " New\tone ") == 4);
        CHECK(l[4].folder == "New one");
        CHECK((folders(l) == std::vector<std::string> { "B", "A", "New one" }));
        CHECK(setFolderAt(l, "u5", "") == 4);
        CHECK((urls(l) == std::vector<std::string> { "u2", "u1", "u3", "u4", "u5" }));
        CHECK(setFolderAt(l, "missing", "B") == -1);
        // rename (merge into an existing folder), remove
        CHECK(renameFolder(l, "New one", "A"));
        CHECK((folders(l) == std::vector<std::string> { "B", "A" }) && folderCount(l, "A") == 2);
        CHECK(!renameFolder(l, "A", "  ") && !renameFolder(l, "nope", "X"));
        CHECK(removeFolder(l, "B") == 2);
        CHECK((urls(l) == std::vector<std::string> { "u3", "u4", "u5" }));
        CHECK(removeFolder(l, "") == 0);
        // a single loose bookmark into a folder when there are no folders yet
        std::vector<Entry> one = { E("x", "X"), E("y", "Y") };
        CHECK(setFolderAt(one, "y", "F") == 0 && one[0].url == "y");
    }
    // search
    {
        CHECK(hostOf("https://User:pw@WWW.Example.COM:8443/p?q#f") == "www.example.com");
        CHECK(hostOf("http://[2001:db8::1]:80/") == "[2001:db8::1]");
        CHECK(hostOf("https://example.org") == "example.org");
        const Entry e = E("https://news.example.com/today", "Morning Briefing", "Work");
        CHECK(matches(e, "") && matches(e, "  "));
        CHECK(matches(e, "brief") && matches(e, "NEWS.example") && matches(e, "morning news"));
        CHECK(!matches(e, "today"));               // the path is not searched, only title and host
        CHECK(!matches(e, "work"));                // nor the folder
        CHECK(!matches(e, "morning sport"));
    }
    // view rows
    {
        std::vector<Entry> l = { E("https://a.example/", "Alpha", "F1"), E("https://b.example/", "Beta", "F2"), E("https://c.example/", "Gamma"), E("https://d.example/", "Delta", "F1") };
        normalize(l);
        auto v = view(l, {}, "");
        CHECK(v.size() == 3);
        CHECK(v[0].kind == Row::Folder && v[0].folder == "F1" && v[0].count == 2 && !v[0].open && v[0].folderIndex == 0);
        CHECK(v[1].kind == Row::Folder && v[1].folder == "F2" && v[1].folderIndex == 1);
        CHECK(v[2].kind == Row::Bookmark && l[size_t(v[2].index)].title == "Gamma" && !v[2].nested);
        v = view(l, { "F1" }, "");
        CHECK(v.size() == 5);
        CHECK(v[0].open && v[1].nested && v[2].nested && l[size_t(v[1].index)].title == "Alpha" && l[size_t(v[2].index)].title == "Delta");
        v = view(l, { "F1" }, " ta ");             // flat: Beta, Delta (F1 before F2? display order: F1, F2, loose)
        CHECK(v.size() == 2);
        CHECK(l[size_t(v[0].index)].title == "Delta" && v[0].folder == "F1" && l[size_t(v[1].index)].title == "Beta");
        CHECK(view(l, {}, "zzz").empty());
        CHECK(view({}, {}, "").empty());
    }
}

static const char* const kSetupUrls[] = {   // what test_bookmarks_manager_ref.py gen imports, in the Setup's order
    "https://news.example.com/", "https://docs.example.com/a?b=1#c", "https://example.org/caf%C3%A9",
    "http://untitled.example.net", "https://other.example.com:8443/path", "https://long.example.com/" };

static void setupRoundTrip(const char* in, const char* out)
{
    const std::string data = readFile(in);
    CHECK(!data.empty());
    auto l = parse(data);
    CHECK(l.size() == 6);
    for (size_t i = 0; i < l.size() && i < 6; ++i) CHECK(l[i].url == kSetupUrls[i]);
    if (l.size() == 6) {
        CHECK(l[1].title == "Docs Tabbed title");                         // the Setup folds tabs and spaces
        CHECK(l[2].title == "Caf\xc3\xa9 \xe2\x80\x93 r\xc3\xa9sum\xc3\xa9");
        CHECK(l[3].title == l[3].url);                                    // empty title: the address
        CHECK(l[5].title.size() <= kTitleMax);
        for (auto& e : l) CHECK(e.folder.empty());                        // the Setup carries no folders
    }
    // Omni reads it the same way the old loader did
    const auto old = oldOmniRead(data);
    CHECK(old.size() == l.size());
    for (size_t i = 0; i < old.size() && i < l.size(); ++i) CHECK(old[i].first == l[i].url && old[i].second == l[i].title);
    // saving without folders changes only the empty title (as the old code did)
    std::string expect = data;
    const std::string untitled = "http://untitled.example.net\t\n";
    CHECK(expect.find(untitled) != std::string::npos);
    expect.replace(expect.find(untitled), untitled.size(), "http://untitled.example.net\thttp://untitled.example.net\n");
    CHECK(serialize(l) == expect);
    // the user files some of them, reorders, and Omni saves
    CHECK(setFolderAt(l, "https://docs.example.com/a?b=1#c", "Work") == 0);
    CHECK(setFolderAt(l, "https://example.org/caf%C3%A9", "Caf\xc3\xa9s") == 1);
    CHECK(setFolderAt(l, "https://long.example.com/", "Work") == 1);
    CHECK(moveEntry(l, 1, -1) == 0);
    const std::string saved = serialize(l);
    writeFile(out, saved);
    const auto again = parse(saved);
    CHECK(again == l);
    CHECK(serialize(again) == saved);
    CHECK((folders(again) == std::vector<std::string> { "Work", "Caf\xc3\xa9s" }));
}

static void reread(const char* omniFile, const char* merged)
{
    const std::string before = readFile(omniFile), after = readFile(merged);
    CHECK(after.compare(0, before.size(), before) == 0);
    const auto a = parse(before), l = parse(after);
    CHECK(l.size() == a.size() + 2);
    for (size_t i = 0; i < a.size() && i < l.size(); ++i) CHECK(l[i] == a[i]);   // folders survive the Setup's append
    if (l.size() == a.size() + 2) {
        CHECK(l[a.size()] == E("https://new-a.example.com/", "New A"));
        CHECK(l[a.size() + 1] == E("https://new-b.example.com/", "New B"));          // PC folders arrive loose
    }
    auto n = l;
    normalize(n);
    const auto v = view(n, {}, "");
    int folderRows = 0;
    for (auto& r : v) folderRows += r.kind == Row::Folder;
    CHECK(folderRows == 2);
}

int main(int argc, char** argv)
{
    if (argc == 4 && std::string(argv[1]) == "setup") setupRoundTrip(argv[2], argv[3]);
    else if (argc == 4 && std::string(argv[1]) == "reread") reread(argv[2], argv[3]);
    else unit();
    std::printf("%s: %d checks, %d failed\n", argc > 1 ? argv[1] : "unit", checks, fails);
    return fails ? 1 : 0;
}
