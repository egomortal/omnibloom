// OMNI_DL_PANEL_V1: host tests of the pure "Downloaded files" model (OmniDlPanel.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_dl_panel.cpp -o t && ./t [--emit DIR]   (run in tools/, or -I<tree>/engine/entry)
// --emit DIR writes the player-page scripts (play / image) for tools/test_dl_panel_js.cjs (node).
#include "OmniDlPanel.h"
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>

namespace D = OmniDlPanel;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

// A fake folder tree: "dir" -> entries.
struct FakeFs {
    std::map<std::string, std::vector<D::DirEnt>> dirs;
    std::vector<std::string> reads;
    bool operator()(const std::string& rel, std::vector<D::DirEnt>& out, size_t budget)
    {
        reads.push_back(rel);
        auto it = dirs.find(rel);
        if (it == dirs.end()) return false;
        for (const auto& e : it->second) { if (out.size() >= budget) break; out.push_back(e); }
        return true;
    }
};
static D::DirEnt file(const char* n, uint64_t size, int64_t mtime) { D::DirEnt e; e.name = n; e.type = D::Type::File; e.size = size; e.mtime = mtime; return e; }
static D::DirEnt dir(const char* n) { D::DirEnt e; e.name = n; e.type = D::Type::Dir; return e; }
static D::DirEnt link(const char* n) { D::DirEnt e; e.name = n; e.type = D::Type::Link; return e; }

int main(int argc, char** argv)
{
    if (argc == 3 && !std::strcmp(argv[1], "--emit")) {
        const std::string dirp = argv[2];
        const struct { const char* file; std::string text; } outs[] = {
            { "/dl_play.js", D::resolveScript("Live \"set\" </script> \xe2\x80\xa8 \xc3\xa9.mp4", "Music/Live", true) },
            { "/dl_image.js", D::resolveScript("cat.jpg", "", false) },
            { "/dl_poll.js", D::pollScript() },
        };
        for (const auto& o : outs) {
            FILE* f = std::fopen((dirp + o.file).c_str(), "wb");
            if (!f) { std::printf("can't write %s\n", o.file); return 1; }
            std::fwrite(o.text.data(), 1, o.text.size(), f);
            std::fclose(f);
        }
        std::printf("emitted 3 scripts to %s\n", dirp.c_str());
        return 0;
    }

    // --- names and kinds ---
    CHECK(D::extOf("a.MP4") == ".mp4");
    CHECK(D::extOf("archive.tar.gz") == ".gz");
    CHECK(D::extOf("noext") == "");
    CHECK(D::extOf(".bashrc") == "");
    CHECK(D::extOf("..a") == "");
    CHECK(D::extOf("a.") == ".");
    CHECK(D::kindOf("film.MKV") == D::Kind::Video);
    CHECK(D::kindOf("clip.ts") == D::Kind::Video);
    CHECK(D::kindOf("song.opus") == D::Kind::Audio);
    CHECK(D::kindOf("song.weba") == D::Kind::Audio);
    CHECK(D::kindOf("p.JPEG") == D::Kind::Image);
    CHECK(D::kindOf("p.webp") == D::Kind::Image);
    CHECK(D::kindOf("doc.Pdf") == D::Kind::Pdf);
    CHECK(D::kindOf("subs.srt") == D::Kind::Text);
    CHECK(D::kindOf("x.zip") == D::Kind::Other);
    CHECK(D::kindOf("README") == D::Kind::Other);
    CHECK(std::string(D::kindLabel(D::Kind::Image)) == "Picture");
    CHECK(D::partial("film.mp4.part"));
    CHECK(D::partial("film.mp4.PART"));
    CHECK(D::partial("film.f137.mp4.part-Frag12"));
    CHECK(D::partial("x.ytdl"));
    CHECK(D::partial("x.crdownload"));
    CHECK(!D::partial("party.mp4"));
    CHECK(!D::partial("partial results.pdf"));
    CHECK(D::plainRel("a/b/c.mp4"));
    CHECK(D::plainRel("c.mp4"));
    CHECK(!D::plainRel(""));
    CHECK(!D::plainRel("a//c"));
    CHECK(!D::plainRel("a/.hidden/c"));
    CHECK(!D::plainRel("../c"));
    CHECK(!D::plainRel("a/"));
    CHECK(!D::plainRel("a\\b"));
    CHECK(D::folderOf("a/b/c.mp4") == "a/b" && D::nameOf("a/b/c.mp4") == "c.mp4");
    CHECK(D::folderOf("c.mp4") == "" && D::nameOf("c.mp4") == "c.mp4");
    CHECK(D::validUtf8("caf\xc3\xa9 \xe2\x80\xa8 \xf0\x9f\x8e\xb5"));
    CHECK(!D::validUtf8("bad \xff"));
    CHECK(!D::validUtf8("over \xc0\xaf"));
    CHECK(!D::validUtf8("surrogate \xed\xa0\x80"));
    CHECK(!D::validUtf8("cut \xe2\x80"));

    // --- routes ---
    CHECK(D::routeFor(D::Kind::Video, "Videos/a.mp4") == D::Route::Player);
    CHECK(D::routeFor(D::Kind::Audio, "a.mp3") == D::Route::Player);
    CHECK(D::routeFor(D::Kind::Audio, "bad\xff.mp3") == D::Route::Library);
    CHECK(D::routeFor(D::Kind::Pdf, "bad\xff.pdf") == D::Route::PdfReader);
    CHECK(D::routeFor(D::Kind::Image, "Screenshots/news.org-20261116-140300.png") == D::Route::Gallery);
    CHECK(D::routeFor(D::Kind::Image, "Screenshots/photo.jpg") == D::Route::ImageViewer);
    CHECK(D::routeFor(D::Kind::Image, "Screenshots/sub/x.png") == D::Route::ImageViewer);
    CHECK(D::routeFor(D::Kind::Image, "x.png") == D::Route::ImageViewer);
    CHECK(D::routeFor(D::Kind::Text, "subs.srt") == D::Route::Library);
    CHECK(D::routeFor(D::Kind::Other, "x.zip") == D::Route::Library);
    CHECK(D::needsWorker(D::Route::Player) && D::needsWorker(D::Route::ImageViewer) && D::needsWorker(D::Route::Library));
    CHECK(!D::needsWorker(D::Route::PdfReader) && !D::needsWorker(D::Route::Gallery));
    CHECK(std::string(D::actionHint(D::Route::Player)) == "Play");
    CHECK(std::string(D::actionHint(D::Route::Library)) == "Open in Downloads");

    // --- the walk: hidden names, links, unreadable folders, depth ---
    {
        FakeFs fs;
        fs.dirs[""] = { file("a.mp4", 10, 100), dir("Screenshots"), dir(".trash"), file(".hidden.mp4", 1, 999), link("evil"), dir("locked"), dir("d1") };
        fs.dirs["Screenshots"] = { file("s.png", 5, 300) };
        fs.dirs[".trash"] = { file("gone.mp4", 1, 1000) };
        std::string p = "d1";
        for (int i = 1; i <= 9; ++i) {   // d1/d2/.../d9, a file fN.txt in each dN
            fs.dirs[p].push_back(file(("f" + std::to_string(i) + ".txt").c_str(), 1, 50 + i));
            if (i == 9) break;
            fs.dirs[p].push_back(dir(("d" + std::to_string(i + 1)).c_str()));
            p += "/d" + std::to_string(i + 1);
        }
        const D::Scan s = D::scan(fs);
        CHECK(!s.truncated);
        std::vector<std::string> rels;
        for (const auto& e : s.files) rels.push_back(e.rel);
        auto has = [&](const std::string& r) { return std::find(rels.begin(), rels.end(), r) != rels.end(); };
        CHECK(has("a.mp4"));
        CHECK(has("Screenshots/s.png"));
        CHECK(!has(".hidden.mp4"));
        CHECK(!has(".trash/gone.mp4"));
        CHECK(std::find(fs.reads.begin(), fs.reads.end(), ".trash") == fs.reads.end());
        CHECK(std::find(fs.reads.begin(), fs.reads.end(), "evil") == fs.reads.end());
        CHECK(has("d1/f1.txt"));
        // depth: the root is 0; folders are read while depth + 1 < 8, so d1 .. d7 (depth 1 .. 7) are read, d8 isn't
        CHECK(has("d1/d2/d3/d4/d5/d6/d7/f7.txt"));
        CHECK(!has("d1/d2/d3/d4/d5/d6/d7/d8/f8.txt"));
        CHECK(std::find(fs.reads.begin(), fs.reads.end(), "d1/d2/d3/d4/d5/d6/d7/d8") == fs.reads.end());
    }
    // --- the walk: the entry budget ---
    {
        FakeFs fs;
        for (int i = 0; i < D::kMaxScan + 50; ++i) fs.dirs[""].push_back(file(("f" + std::to_string(i) + ".mp4").c_str(), 1, i));
        const D::Scan s = D::scan(fs);
        CHECK(s.truncated);
        CHECK(s.files.size() == size_t(D::kMaxScan - 1));
    }
    {
        FakeFs fs;   // the root itself can't be read: nothing, not truncated
        const D::Scan s = D::scan(fs);
        CHECK(s.files.empty() && !s.truncated);
    }

    // --- the list: newest first, partial files out, cap ---
    {
        D::Scan s;
        s.files = { { "old.mp4", 1, 100 }, { "new.pdf", 2, 300 }, { "b.mp3", 3, 200 }, { "a.mp3", 4, 200 }, { "x.mp4.part", 5, 999 },
                    { "bad//rel", 1, 1 }, { "Music/a.mp3", 6, 200 } };
        const D::Listing l = D::list(s);
        CHECK(l.items.size() == 5 && l.total == 5);
        CHECK(l.items[0].rel == "new.pdf" && l.items[0].kind == D::Kind::Pdf);
        CHECK(l.items[1].rel == "Music/a.mp3" || l.items[1].rel == "a.mp3");
        CHECK(l.items[1].name == "a.mp3" && l.items[2].name == "a.mp3");
        CHECK(l.items[1].rel == "Music/a.mp3" && l.items[1].folder == "Music");   // same time and name: by path
        CHECK(l.items[3].rel == "b.mp3");
        CHECK(l.items[4].rel == "old.mp4");
        CHECK(D::indexOf(l.items, "b.mp3") == 3 && D::indexOf(l.items, "nope") == -1);
        CHECK(D::corner(l, false) == "5 files");
        CHECK(D::corner(l, true) == "5 files");
    }
    {
        D::Scan s;
        for (int i = 0; i < 700; ++i) s.files.push_back({ "f" + std::to_string(i) + ".mp4", 1, i });
        s.truncated = true;
        const D::Listing l = D::list(s);
        CHECK(l.items.size() == D::kMaxList && l.total == 700);
        CHECK(l.items.front().rel == "f699.mp4" && l.items.back().rel == "f200.mp4");
        CHECK(D::corner(l, false) == "Newest 500 of 700+");
        D::Listing empty;
        CHECK(D::corner(empty, true) == "Loading\xe2\x80\xa6");
        empty.total = 1; empty.items.resize(1);
        CHECK(D::corner(empty, false) == "1 file");
    }

    // --- selection ---
    {
        D::Sel s;
        s.count = 20;
        s.clamp(8);
        CHECK(s.sel == 0 && s.scroll == 0);
        CHECK(!s.move(-1, 8));
        CHECK(s.move(1, 8) && s.sel == 1);
        for (int i = 0; i < 7; ++i) s.move(1, 8);
        CHECK(s.sel == 8 && s.scroll == 1);
        CHECK(s.page(1, 8) && s.sel == 16 && s.scroll == 9);
        CHECK(s.page(1, 8) && s.sel == 19 && s.scroll == 12);
        CHECK(!s.page(1, 8));
        CHECK(s.page(-1, 8) && s.sel == 11 && s.scroll == 11);
        s.count = 3; s.clamp(8);
        CHECK(s.sel == 2 && s.scroll == 0);
        s.count = 0; s.clamp(8);
        CHECK(s.sel == 0 && s.scroll == 0 && !s.move(1, 8));
    }

    // --- trash paths ---
    CHECK((D::trashDirs("x.mp4") == std::vector<std::string> { ".trash" }));
    CHECK((D::trashDirs("a/b/x.mp4") == std::vector<std::string> { ".trash", ".trash/a", ".trash/a/b" }));
    CHECK((D::chain("a/b/x.mp4") == std::vector<std::string> { "a", "a/b", "a/b/x.mp4" }));
    CHECK((D::chain("x.mp4") == std::vector<std::string> { "x.mp4" }));

    // --- the player page ---
    CHECK(D::origin(8765) == "http://127.0.0.1:8765");
    CHECK(D::origin(0).empty() && D::origin(8080).empty() && D::playerURL(9000).empty());
    CHECK(D::playerURL(8765) == "http://127.0.0.1:8765/player");
    CHECK(D::libraryURL(8765) == "http://127.0.0.1:8765/downloads#view=files");
    CHECK(D::isPlayerURL("http://127.0.0.1:8765/player", 8765));
    CHECK(D::isPlayerURL("http://127.0.0.1:8765/player#id=0123", 8765));
    CHECK(!D::isPlayerURL("http://127.0.0.1:8765/playerx", 8765));
    CHECK(!D::isPlayerURL("http://127.0.0.1:8766/player", 8765));
    CHECK(!D::isPlayerURL("http://127.0.0.1:8765/player", 0));
    CHECK(D::jsQuote("a\"b\\c") == "\"a\\\"b\\\\c\"");
    CHECK(D::jsQuote("</script>") == "\"\\u003c/script\\u003e\"");
    CHECK(D::jsQuote("x\ny\x01z") == "\"x\\ny\\u0001z\"");
    CHECK(D::jsQuote("a\xe2\x80\xa8" "b\xe2\x80\xa9") == "\"a\\u2028b\\u2029\"");
    CHECK(D::jsQuote("caf\xc3\xa9") == "\"caf\xc3\xa9\"");
    {
        const std::string js = D::resolveScript("a'b\".mp4", "x</script>", true);
        CHECK(js.find("</script>") == std::string::npos);
        CHECK(js.find("N=\"a'b\\\".mp4\"") != std::string::npos);
        CHECK(js.find("P=true") != std::string::npos);
        CHECK(js.find("x.place==='internal'") != std::string::npos);
        CHECK(D::resolveScript("a", "", false).find("P=false") != std::string::npos);
    }
    const std::string link = "http://127.0.0.1:8765/api/files/stream?id=0123456789abcdef0123456789abcdef&exp=1800000000&sig="
        + std::string(64, 'a');
    CHECK(D::streamLinkOk(link, 8765));
    CHECK(!D::streamLinkOk(link, 8766));
    CHECK(!D::streamLinkOk("http://127.0.0.1:8765/api/files/streamx", 8765));
    CHECK(!D::streamLinkOk("javascript:alert(1)", 8765));
    CHECK(!D::streamLinkOk(link + "\"onerror", 8765));
    CHECK(!D::streamLinkOk(link, 0));

    // --- texts ---
    CHECK(D::sizeText(0) == "0 KB");
    CHECK(D::sizeText(1) == "1 KB");
    CHECK(D::sizeText(1536 * 1024) == "1.5 MB");
    CHECK(D::sizeText(3ull << 30) == "3.00 GB");
    {
        D::Item it; it.name = "a.mp4"; it.kind = D::Kind::Video; it.size = 1536 * 1024; it.folder = "Music/Live";
        CHECK(D::detail(it, "16 Nov 2026, 14:03") == "Video \xc2\xb7 1.5 MB \xc2\xb7 16 Nov 2026, 14:03 \xc2\xb7 in Music/Live");
        it.folder.clear();
        CHECK(D::detail(it, "") == "Video \xc2\xb7 1.5 MB");
        CHECK(D::askBody(it).rfind("a.mp4 (1.5 MB). It moves to the Downloads trash", 0) == 0);
    }
    CHECK(std::string(D::subtitle(true)).find("not private") != std::string::npos);
    CHECK(std::string(D::subtitle(false)).find("newest first") != std::string::npos);

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
