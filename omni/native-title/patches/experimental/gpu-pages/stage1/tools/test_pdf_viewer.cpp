// OMNI_PDF_VIEWER_V1: tests of the pure part (engine/entry/OmniPdfViewer.h, written by apply_pdf_viewer.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_pdf_viewer.cpp -o t && ./t
#include "OmniPdfViewer.h"
#include <cstdio>
#include <set>

namespace P = OmniPdfViewer;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

static P::Decision base()
{
    P::Decision d;
    d.viewerPresent = true; d.pagesCapable = true; d.settingOn = true;
    d.url = "https://example.com/files/report.pdf"; d.mime = "application/pdf"; d.status = 200;
    return d;
}

int main()
{
    // MIME / address recognition
    CHECK(P::isPdfResponse("application/pdf", "https://a.b/x", ""));
    CHECK(P::isPdfResponse("Application/PDF; charset=binary", "https://a.b/x", ""));
    CHECK(P::isPdfResponse("application/x-pdf", "https://a.b/x", ""));
    CHECK(P::isPdfResponse("application/octet-stream", "https://a.b/doc.PDF?x=1#p", ""));
    CHECK(P::isPdfResponse("", "https://a.b/download", "manual.pdf"));
    CHECK(P::isPdfResponse("binary/octet-stream", "https://a.b/get?id=3", "Report 2026.pdf"));
    CHECK(!P::isPdfResponse("application/octet-stream", "https://a.b/x.zip", "x.zip"));
    CHECK(!P::isPdfResponse("application/zip", "https://a.b/x.pdf", "x.pdf"));   // a specific other type wins
    CHECK(!P::isPdfResponse("text/html", "https://a.b/x.pdf", ""));
    CHECK(!P::isPdfResponse("application/octet-stream", "https://a.b/x?f=a.pdf", ""));   // the query is not the path

    // decision
    CHECK(P::decide(base()) == P::Route::Reader);
    { auto d = base(); d.testMode = true; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.settingOn = false; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.viewerPresent = false; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.pagesCapable = false; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.downloadsTab = true; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.mainFrame = false; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.attachment = true; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.status = 404; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.url = "ftp://a.b/x.pdf"; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.url = "blob:https://a.b/123"; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.url = "https://user:pw@a.b/x.pdf"; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.url = "https://a.b/x y.pdf"; CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.url = "https://a.b/" + std::string(5000, 'a'); CHECK(P::decide(d) == P::Route::Normal); }
    { auto d = base(); d.url = "http://a.b/@x.pdf"; CHECK(P::decide(d) == P::Route::Reader); }   // '@' in the path is fine
    { auto d = base(); d.expectedLength = 0xFFFFFFFFull; CHECK(P::decide(d) == P::Route::Reader); }   // unknown length
    { auto d = base(); d.expectedLength = P::kMaxBytes; CHECK(P::decide(d) == P::Route::Reader); }
    { auto d = base(); d.expectedLength = P::kMaxBytes + 1; CHECK(P::decide(d) == P::Route::Normal); }

    // tokens
    uint8_t b[16];
    for (int i = 0; i < 16; ++i) b[i] = uint8_t(i * 17 + 3);
    const std::string t = P::token(b);
    CHECK(t.size() == 32 && P::validToken(t));
    CHECK(t == "03142536475869" "7a8b9cadbecfe0f102");
    CHECK(!P::validToken("03142536475869")); CHECK(!P::validToken(std::string(32, 'G'))); CHECK(!P::validToken(std::string(32, 'A')));
    CHECK(P::tokenFromFile(t + ".pdf") == t);
    CHECK(P::tokenFromFile(t + ".png").empty()); CHECK(P::tokenFromFile("../" + t.substr(3) + ".pdf").empty()); CHECK(P::tokenFromFile("start-bg.png").empty());
    CHECK(P::tokenFromDocURL(P::docURL(t)) == t);
    CHECK(P::tokenFromDocURL("https://evil/_user/pdf/" + t + ".pdf").empty());
    CHECK(P::tokenFromDocURL("omni://pages/_user/pdf/" + t + ".pdf?x").empty());

    // names and the reader's address
    CHECK(P::fileName("Manual.pdf", "") == "Manual.pdf");
    CHECK(P::fileName("", "https://a.b/dir/My%20Report.pdf?x=1") == "My Report.pdf");
    CHECK(P::fileName("", "https://a.b/download") == "download.pdf");
    CHECK(P::fileName("", "https://a.b/") == "document.pdf");
    CHECK(P::fileName("../../etc/passwd", "") == "_.._etc_passwd.pdf");
    CHECK(P::fileName("a\nb:c.PDF", "") == "a_b_c.PDF");
    CHECK(P::fileName(std::string(300, 'x'), "").size() == 120);
    CHECK(P::shortName(std::string(100, 'n')).size() == 59);
    const std::string vp = P::viewerPath(t, "My Report.pdf", "https://a.b/x.pdf?q=1&r=2");
    CHECK(vp == "pdf/index.html?doc=" + t + "&name=My%20Report.pdf&src=https%3A%2F%2Fa.b%2Fx.pdf%3Fq%3D1%26r%3D2");
    CHECK(P::viewerPath(t, "a.pdf", "javascript:alert(1)").find("src=") == std::string::npos);
    CHECK(P::isViewerURL("omni://pages/pdf/index.html?doc=" + t));
    CHECK(!P::isViewerURL("omni://pages/pdfx/index.html") && !P::isViewerURL("https://pages/pdf/"));
    CHECK(P::percentDecode(P::percentEncode("a b/ü?&")) == "a b/ü?&");

    // unique names
    std::set<std::string> taken = { "r.pdf", "r (2).pdf" };
    auto exists = [&](const std::string& n) { return taken.count(n) > 0; };
    CHECK(P::uniqueName("new.pdf", exists) == "new.pdf");
    CHECK(P::uniqueName("r.pdf", exists) == "r (3).pdf");
    CHECK(P::uniqueName("x", [](const std::string&) { return true; }).empty());

    // store: newest kept, at most kKeepDocs, replacing the same token
    P::Store s;
    auto doc = [](char c, size_t n) { P::Doc d; d.token = std::string(32, c); d.bytes.assign(n, 1); return d; };
    s.add(doc('a', 10)); s.add(doc('b', 20));
    CHECK(s.find(std::string(32, 'a')) && s.find(std::string(32, 'b')) && s.bytes() == 30);
    s.add(doc('c', 5));
    CHECK(!s.find(std::string(32, 'a')) && s.find(std::string(32, 'c')) && s.docs.size() == 2 && s.bytes() == 25);
    s.add(doc('b', 7));
    CHECK(s.docs.size() == 2 && s.docs.back().token == std::string(32, 'b') && s.bytes() == 12);
    CHECK(!s.find("zz") && !s.find(""));

    // trigger repeat
    P::Trigger tr;
    CHECK(!tr.step(10000, 0));
    CHECK(tr.step(20000, 100));
    CHECK(!tr.step(20000, 300));
    CHECK(tr.step(20000, 550));
    CHECK(!tr.step(20000, 700));
    CHECK(tr.step(12000, 850));     // still held above the release level
    CHECK(!tr.step(8000, 900));     // released
    CHECK(!tr.step(12000, 950));    // below the press level again
    CHECK(tr.step(30000, 1000));

    // texts
    CHECK(std::string(P::settingValue(true, true)) == "On" && std::string(P::settingValue(false, true)) == "Off");
    CHECK(std::string(P::settingValue(true, false)) == "Not installed");
    CHECK(P::openingNotice("a.pdf", 50, 200) == "Opening a.pdf: 25%");
    CHECK(P::openingNotice("a.pdf", 200, 200) == "Opening a.pdf: 99%");
    CHECK(P::openingNotice("a.pdf", 0, 0) == "Opening a.pdf...");

    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
