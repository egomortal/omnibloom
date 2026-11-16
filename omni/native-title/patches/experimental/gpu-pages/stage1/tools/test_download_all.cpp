// OMNI_DOWNLOAD_ALL_V1: host tests for engine/entry/OmniDownloadAll.h (written by apply_download_all.py), with the real
// OmniMediaSection (validLink, encode) and OmniSaveImage (names) it uses.
//   g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry test_download_all.cpp -o t && ./t [script.js]
// With an argument the page script is written there (node test_download_all_js.cjs <script.js> runs it).
#include "OmniDownloadAll.h"
#include <cstdio>
#include <fstream>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

namespace ODAL = OmniDownloadAll;

static ODAL::Kind kindOf(const char* tag, const std::string& url, const std::string& mime = "", const char* dl = nullptr, int w = 0, int h = 0)
{
    ODAL::Raw r;
    r.tag = tag; r.url = url; r.mime = mime; r.w = w; r.h = h;
    r.hasDownload = dl != nullptr; r.download = dl ? dl : "";
    return ODAL::classify(r);
}
static std::string row(const char* tag, const std::string& url, int w = 0, int h = 0, const char* dl = nullptr, const char* mime = "")
{
    return std::string(tag) + "\t" + std::to_string(w) + "\t" + std::to_string(h) + "\t" + (dl ? "1" : "0") + "\t" + (dl ? dl : "") + "\t" + mime + "\t" + url;
}
static std::string decode(const std::string& s)
{
    std::string out;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '%' && i + 2 < s.size()) { out += char(std::stoi(s.substr(i + 1, 2), nullptr, 16)); i += 2; }
        else out += s[i];
    }
    return out;
}

int main(int argc, char** argv)
{
    using K = ODAL::Kind;
    // extensions
    CHECK(ODAL::extOf("a/b/report.PDF") == "pdf");
    CHECK(ODAL::extOf("archive.tar.gz") == "gz");
    CHECK(ODAL::extOf("/dir.v2/file") == "");
    CHECK(ODAL::extOf("noext") == "");
    CHECK(ODAL::extOf("x.") == "");
    CHECK(ODAL::extOf("x.toolongext") == "");
    CHECK(ODAL::extOf("x.p-f") == "");
    CHECK(ODAL::urlPath("https://e.com/a%20b/c.zip?x=1#y") == "/a b/c.zip");
    CHECK(ODAL::urlPath("https://e.com?x=/a.pdf") == "");
    CHECK(ODAL::hostOf("https://WWW.E.com:8080/a") == "www.e.com:8080");

    // classification: the order download name > path > MIME > element
    CHECK(kindOf("a", "https://e.com/doc.pdf") == K::Pdf);
    CHECK(kindOf("a", "https://e.com/get?id=7") == K::None);                          // a plain link
    CHECK(kindOf("a", "https://e.com/get?id=7", "", "manual.pdf") == K::Pdf);         // download="manual.pdf"
    CHECK(kindOf("a", "https://e.com/get?id=7", "", "") == K::Other);                 // bare download attribute
    CHECK(kindOf("a", "https://e.com/pack.7z") == K::Archive);
    CHECK(kindOf("a", "https://e.com/pack.RAR") == K::Archive);
    CHECK(kindOf("a", "https://e.com/pack.zip?token=1") == K::Archive);
    CHECK(kindOf("a", "https://e.com/song.flac") == K::Audio);
    CHECK(kindOf("a", "https://e.com/movie.mkv") == K::Video);
    CHECK(kindOf("a", "https://e.com/photo.JPEG") == K::Image);
    CHECK(kindOf("a", "https://e.com/book.epub") == K::Other);
    CHECK(kindOf("a", "https://e.com/x", "application/pdf") == K::Pdf);
    CHECK(kindOf("a", "https://e.com/x", " Application/ZIP ; q=1") == K::Archive);
    CHECK(kindOf("a", "https://e.com/x", "application/x-7z-compressed") == K::Archive);
    CHECK(kindOf("a", "https://e.com/x", "application/vnd.rar") == K::Archive);
    CHECK(kindOf("a", "https://e.com/x", "video/mp4") == K::Video);
    CHECK(kindOf("a", "https://e.com/x", "text/html") == K::None);
    CHECK(kindOf("a", "https://e.com/x", "application/x-mpegURL") == K::None);       // stream
    CHECK(kindOf("a", "https://e.com/page.html") == K::None);
    CHECK(kindOf("a", "https://e.com/page.php", "application/pdf") == K::None);      // a page, whatever type= says
    CHECK(kindOf("a", "https://e.com/page.php", "", "") == K::Other);                // ... unless it is a download
    CHECK(kindOf("video", "https://e.com/live.m3u8") == K::None);
    CHECK(kindOf("video", "https://e.com/manifest.mpd") == K::None);
    CHECK(kindOf("video", "https://e.com/stream?id=1") == K::Video);
    CHECK(kindOf("audio", "https://e.com/stream?id=1") == K::Audio);
    CHECK(kindOf("video", "https://e.com/a.mp3") == K::Audio);                        // the extension wins
    CHECK(kindOf("img", "https://e.com/i?id=1", "", nullptr, 640, 480) == K::Image);
    CHECK(kindOf("img", "https://e.com/big.png", "", nullptr, 200, 10) == K::Image);  // the longer side counts
    CHECK(kindOf("img", "https://e.com/icon.png", "", nullptr, 199, 199) == K::None); // small
    CHECK(kindOf("img", "https://e.com/i.png", "", nullptr, 0, 0) == K::None);        // not loaded, no size
    CHECK(ODAL::bigEnough(200, 0) && !ODAL::bigEnough(199, 150));

    // rows: absolute http(s) only, dedupe (fragment dropped), names
    {
        std::string text = row("a", "https://e.com/a.pdf") + "\n"
            + row("a", "https://e.com/a.pdf#page=2") + "\n"                        // same file
            + row("a", "https://e.com/p.html") + "\n"                              // a page: skipped
            + row("a", "https://e.com/p.html", 0, 0, "Notes 1.txt") + "\n"         // download name
            + row("img", "https://e.com/thumb.png", 64, 64) + "\n"                 // small
            + row("img", "https://e.com/photo.png", 1024, 768) + "\n"
            + row("a", "ftp://e.com/x.zip") + "\n"
            + row("a", "https://u:p@e.com/x.zip") + "\n"
            + row("a", "https://e.com/" + std::string(2100, 'x') + ".zip") + "\n"  // too long
            + row("a", "https://e.com/%E2%9C%93%20ok.zip") + "\r\n"
            + "garbage line\n"
            + "a\tx\t0\t0\t\t\thttps://e.com/bad-size.zip\n"
            + "a\t0\t0\t2\t\t\thttps://e.com/bad-flag.zip\n"
            + row("video", "https://e.com/v.mp4") + "\n"
            + row("audio", "https://e.com/s.mp3");
        const ODAL::List l = ODAL::parseRows(text);
        CHECK(l.items.size() == 6);
        CHECK(l.found == 6 && !l.more);
        CHECK(l.on.size() == 6 && ODAL::chosen(l) == 0);
        CHECK(l.items[0].url == "https://e.com/a.pdf" && l.items[0].kind == K::Pdf && l.items[0].name == "a.pdf");
        CHECK(l.items[1].name == "Notes 1.txt" && l.items[1].kind == K::Other);
        CHECK(l.items[2].kind == K::Image && l.items[2].name == "photo.png");
        CHECK(l.items[3].name == "\xe2\x9c\x93 ok.zip" && l.items[3].kind == K::Archive);
        CHECK(l.items[4].kind == K::Video && l.items[5].kind == K::Audio);
        CHECK(ODAL::count(l, K::Pdf) == 1 && ODAL::count(l, K::Image) == 1 && ODAL::count(l, K::Archive) == 1);
    }
    {   // a download name that is only path characters falls back to the address
        const ODAL::List l = ODAL::parseRows(row("a", "https://e.com/x/report.pdf", 0, 0, "../"));
        CHECK(l.items.size() == 1 && l.items[0].name == "report.pdf");
    }
    {   // a small <img> first, then a link to the same file: the link counts
        const ODAL::List l = ODAL::parseRows(row("img", "https://e.com/a.png", 10, 10) + "\n" + row("a", "https://e.com/a.png"));
        CHECK(l.items.size() == 1 && l.items[0].kind == K::Image);
    }
    {   // caps: 200 listed, the rest counted; raw rows beyond kRawMax ignored
        std::string text;
        for (int i = 0; i < 250; ++i) text += row("a", "https://e.com/f" + std::to_string(i) + ".pdf") + "\n";
        ODAL::List l = ODAL::parseRows(text);
        CHECK(l.items.size() == ODAL::kMax && l.found == 250 && l.more);
        CHECK(l.items[199].url == "https://e.com/f199.pdf");
        CHECK(ODAL::subtitle("e.com", l) == "e.com: 250 files found (the first 200 are listed)");
        std::string many;
        for (int i = 0; i < 700; ++i) many += row("a", "https://e.com/g" + std::to_string(i) + ".pdf") + "\n";
        CHECK(ODAL::parseRows(many).found == ODAL::kRawMax);
        CHECK(ODAL::parseRows("").items.empty());
    }

    // selection
    {
        ODAL::List l = ODAL::parseRows(row("a", "https://e.com/1.pdf") + "\n" + row("a", "https://e.com/2.pdf") + "\n" + row("a", "https://e.com/3.zip"));
        CHECK(ODAL::countValue(ODAL::chosen(l, K::Pdf), ODAL::count(l, K::Pdf)) == "2 found");
        ODAL::toggle(l, 0);
        CHECK(ODAL::countValue(ODAL::chosen(l, K::Pdf), 2) == "1 of 2");
        ODAL::toggleGroup(l, K::Pdf);   // some -> all
        CHECK(ODAL::chosen(l, K::Pdf) == 2 && ODAL::chosen(l) == 2);
        CHECK(ODAL::countValue(2, 2) == "All 2");
        ODAL::toggleGroup(l, K::Pdf);   // all -> none
        CHECK(ODAL::chosen(l) == 0);
        ODAL::toggleAll(l);
        CHECK(ODAL::chosen(l) == 3);
        ODAL::toggleAll(l);
        CHECK(ODAL::chosen(l) == 0);
        ODAL::toggle(l, 99);            // out of range: nothing
        CHECK(ODAL::chosen(l) == 0);
        CHECK(ODAL::buttonLabel(0) == "Download files (choose below)");
        CHECK(ODAL::buttonLabel(1) == "Download 1 file" && ODAL::buttonLabel(12) == "Download 12 files");
        CHECK(ODAL::groupLabel(K::Pdf) == "Select all PDFs" && ODAL::groupLabel(K::Archive) == "Select all archives");
        CHECK(std::string(ODAL::groupName(K::Other)) == "Other files");

        // the #files= field
        size_t sent = 9;
        CHECK(ODAL::field(l, "https://e.com/list", sent).empty() && sent == 0);   // nothing chosen
        ODAL::toggle(l, 0); ODAL::toggle(l, 2);
        const std::string f = ODAL::field(l, "https://e.com/list?q=\"x\"", sent);
        CHECK(sent == 2);
        CHECK(f.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~%") == std::string::npos);
        CHECK(decode(f) == "{\"v\":1,\"p\":\"https://e.com/list?q=\\\"x\\\"\",\"u\":[\"https://e.com/1.pdf\",\"https://e.com/3.zip\"]}");
        CHECK(decode(ODAL::field(l, "omni://start", sent)) == "{\"v\":1,\"u\":[\"https://e.com/1.pdf\",\"https://e.com/3.zip\"]}");
        CHECK(ODAL::sentNotice(2, 2) == "Sent 2 files to Downloads" && ODAL::sentNotice(1, 1) == "Sent 1 file to Downloads");
    }
    {   // the byte cap: what does not fit is not sent
        std::string text;
        for (int i = 0; i < 200; ++i) text += row("a", "https://e.com/" + std::string(1900, 'p') + std::to_string(i) + ".pdf") + "\n";
        ODAL::List l = ODAL::parseRows(text);
        ODAL::toggleAll(l);
        size_t sent = 0;
        const std::string f = ODAL::field(l, "https://e.com/", sent);
        CHECK(sent > 100 && sent < 200 && f.size() <= ODAL::kFieldMax);
        CHECK(decode(f).back() == '}');
        CHECK(ODAL::sentNotice(sent, 200) == "Sent " + std::to_string(sent) + " of 200 files to Downloads (the list was too long)");
        size_t small = 0;
        CHECK(ODAL::field(l, "", small, 50).empty() && small == 0);   // not even one fits
    }
    CHECK(ODAL::jsonString(std::string("a\x01\\b\x7f")) == "\"a\\u0001\\\\b\\u007f\"");

    // offered: the single-download rules
    {
        OmniSaveImage::Where w; w.downloadsOn = true; w.validLink = true;
        CHECK(ODAL::offered(w));
        OmniSaveImage::Where p = w; p.privateTab = true; CHECK(!ODAL::offered(p));
        OmniSaveImage::Where o = w; o.downloadsOn = false; CHECK(!ODAL::offered(o));
        OmniSaveImage::Where t = w; t.downloadsTab = true; CHECK(!ODAL::offered(t));
        OmniSaveImage::Where s = w; s.testMode = true; CHECK(!ODAL::offered(s));
        OmniSaveImage::Where v = w; v.validLink = false; CHECK(!ODAL::offered(v));
    }

    // the page script: one complete expression, every placeholder filled
    const std::string js = ODAL::script();
    CHECK(js.find('@') == std::string::npos);
    CHECK(js.compare(0, 12, "(function(){") == 0 && js.compare(js.size() - 4, 4, "})()") == 0);
    CHECK(js.find("|7z|rar|") != std::string::npos && js.find("MAXR=600") != std::string::npos && js.find("MIN=200") != std::string::npos);
    if (argc > 1) { std::ofstream(argv[1], std::ios::binary) << js; }

    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
