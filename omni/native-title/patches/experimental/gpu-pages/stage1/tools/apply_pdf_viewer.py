#!/usr/bin/env python3
"""OMNI_PDF_VIEWER_V1 (2026-11-16): PDFs open inside Omni, in the built-in PDF reader page (omni://pages/pdf/,
Mozilla pdf.js 6.5.438 legacy build, Apache-2.0, already shipped in the pages bundle with its notices).

What the user sees
  - A link / address that answers with a PDF (Content-Type application/pdf or application/x-pdf, or a generic
    octet-stream / download type whose address or file name ends in .pdf) in the main frame: the notice
    "Opening <name>..." (with a percentage every second for big files), then the same tab shows the PDF reader
    with that document. Back (Circle) returns to the page the link was on.
  - Kept as before (Downloads app / WebKit's own download): Content-Disposition: attachment (the site asked for a
    download, as Chrome does), PDFs in frames, non-HTTP(S) addresses, the Downloads tab, self-test modes, files
    over 32 MB (Content-Length known up front: straight to Downloads; found while loading: cancelled, then sent
    to Downloads with "PDF too large for the reader (over 32 MB): sent to Downloads"), Browser settings
    "Open PDFs in Omni" Off, or the reader missing from the pages bundle (row shows "Not installed").
  - Browser settings: "Open PDFs in Omni"  On / Off (default On when omni://pages/pdf/ with pdf.js is present;
    checked once at runtime: pdf/index.html, viewer.mjs, viewer-nav.mjs, vendor/pdfjs/pdf.mjs, pdf.worker.mjs).
    Off = /data/omni/pdf-viewer-off.flag.
  - Reader controls (the page's own controller, plus two shell routes): D-pad up / down scroll (at the bottom /
    top they turn the page), D-pad left / right scroll sideways when zoomed, else turn the page; right stick
    scrolls (wheel events, forwarded to the document area); L1 / R1 previous / next page; R2 / L2 zoom in / out
    (held: repeats); Square "Save to Downloads"; Circle back. The left stick stays the pointer (toolbar buttons).
  - Private tabs: the reader opens in the same private tab (a private viewer tab); the document is held in memory
    only; the temporary download file is deleted the moment it is read (and the temp folder is emptied on first
    use, after a crash). Nothing about it is written to history / sessions by this feature. Square in a private tab
    saves only because the user asked.

Byte path (why this one)
  The reader page is omni://pages (CSP connect-src 'self'); pdf.js can't fetch https://site/x.pdf from there (CSP,
  and CORS for a non-http origin). Rejected: (a) a "pdf.fetch" bridge = Omni's own networking (cookies, referrer,
  POST, private sessions) - not wanted; (b) the Downloads worker fetching to a file and serving it on 127.0.0.1 -
  a second request without the page's cookies (signed-in PDFs fail), private links must never reach Downloads,
  and the page would need CSP / CORS changes; (c) a hidden WKPage - it ends in the same download decision.
  Chosen: the navigation response that is ALREADY in flight becomes a WebKit download (WKFramePolicyListenerDownload,
  the network process of the tab's own session: same cookies, POST body, redirects, private store) into
  /data/omni/pdf-temp/<token>.pdf with a download client of our own (not the Downloads list). When it finishes the
  shell reads the file into memory (<= 32 MB), deletes it, and keeps the bytes under a random 128-bit token (at most
  2 documents, newest kept). The reader loads omni://pages/pdf/index.html?doc=<token>&name=..&src=.. and fetches
  ../_user/pdf/<token>.pdf - same origin, served by the omni://pages scheme handler (new hook beside START_CUSTOM's
  _user/ file hook; web content can't reach omni://pages at all: omniPagesAllow). No second request, no new
  networking, no CSP change. A document no longer in memory (restart, evicted) shows "This PDF is no longer open"
  with "Open original" (navigation.open of the src address).
  Save (Square): bridge request "pdf.save" (url = the document address) writes the bytes Omni already holds to
  /data/omni/downloads/<name> (unique name) - the Omni Downloads list; nothing is fetched again.

Pure part: engine/entry/OmniPdfViewer.h (namespace OmniPdfViewer, alias OPDF): response test, decision, token,
viewer address, file name, document store, trigger repeat, setting texts. Tests: tools/test_pdf_viewer.cpp
(g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry). Page logic: pages bundle pdf/viewer-nav.mjs, tested by
tools/test_pdf_viewer_js.mjs <bundle>/pdf/viewer-nav.mjs (node).
Shell part: engine/entry/OmniPdfViewerShell.h, included from OmniBrowser.cpp right after OmniPages.h. Names omniPdfv*;
settings row id 896 (OmniPdfViewer::kRowId; offline retry 895, history keep 897). Refused when the tree already uses
896 / omniPdfv / OPDF / omniPagesSetPdfFile.
Anchors (each exactly once; whole lines kept, new lines before / after them, /* */ comments only):
  OmniBrowser.cpp   the OmniHttpsOnly.h include (pure include before);
                    the omniFileDownloadsTake declaration (OMNI_FILE_DOWNLOADS_V1; our declarations after);
                    the omniFileDownloadsTake call in the response policy (the PDF test before it);
                    the navigationResponseDidBecomeDownload line (replaced: our download client first);
                    omniSavedContext's last two lines (replaced: R2 / L2 stand down on the reader);
                    the OmniPages.h include (shell include after)
  OmniPages.h       the R1 case of omniPagesButton (Square case after: the reader only);
                    the webapps. bridge line (pdf. methods before)
  OmniBlocker.cpp   pagesUserFile's variable and setter (ours after); the _user/ branch (the _user/pdf/ branch before)
  OmniBlocker.h     the omniPagesSetUserFile declaration (ours after)
  OmniBrowserSettings.h  omniOrRowId (declarations after), its add() row (our row after), its input line (ours before)
  OmniFeatures3.h   the omniDlpTick line of omniF3Tick (omniPdfvTick after)
Needs OMNI_FILE_DOWNLOADS_V1, OMNI_OFFLINE_RETRY_V1, OMNI_DL_PROGRESS_V1, OMNI_START_CUSTOM_V1, OMNI_WEB_APPS_V1 first.
r2 (OMNI_PDF_VIEWER_V1_R2, REV): a private tab's PDF download that finishes, fails or reports progress after the last
private tab closed went into "Recent notices" (OMNI_NOTICE_HISTORY_V1 records once no private tab is left) with its
file name. Those notices now say "the PDF" for job.privateTab (omniPdfvJobName); nothing else changes. Only
OmniPdfViewerShell.h changes (rewritten whole: an r1 tree upgrades).
usage: apply_pdf_viewer.py <engine tree>   (anchored, idempotent, keeps CRLF; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_PDF_VIEWER_V1'
REV = 'OMNI_PDF_VIEWER_V1_R2'   # r2: no file name in notices of a private tab's PDF (shell only)
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_PDF_VIEWER_V1: the pure part of "PDFs open in Omni" (no SDL, no WebKit). A main-frame PDF response becomes a
// WebKit download into a temporary file; the bytes are kept in memory under a random token and the built-in reader
// (omni://pages/pdf/, pdf.js) fetches them same-origin from omni://pages/_user/pdf/<token>.pdf.
// Shell side: OmniPdfViewerShell.h; reasons in tools/apply_pdf_viewer.py. Tests: tools/test_pdf_viewer.cpp.
#pragma once
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace OmniPdfViewer {

constexpr int kRowId = 896;                       // Browser settings "Open PDFs in Omni" (offline retry 895)
constexpr size_t kMaxBytes = 32u << 20;           // larger PDFs go to Downloads (memory: shell + page + pdf.js copies)
constexpr size_t kKeepDocs = 2;                   // documents held in memory (newest kept)
constexpr uint32_t kPendingMs = 10000;            // policy decision -> "became a download" must match within this
constexpr size_t kMaxUrl = 4096;
constexpr int kTriggerOn = 16000, kTriggerOff = 9000;   // R2 / L2 press / release (of 32767)
constexpr uint32_t kRepeatFirstMs = 450, kRepeatMs = 300;
static const char* const kTempDir = "pdf-temp";
static const char* const kOffFlag = "pdf-viewer-off.flag";
static const char* const kViewerPrefix = "omni://pages/pdf/";
static const char* const kDocBase = "omni://pages/_user/pdf/";
static const char* const kViewerFiles[] = { "pdf/index.html", "pdf/viewer.mjs", "pdf/viewer-nav.mjs",
    "pdf/vendor/pdfjs/pdf.mjs", "pdf/vendor/pdfjs/pdf.worker.mjs" };

inline std::string lower(std::string s) { for (auto& c : s) c = char(std::tolower(static_cast<unsigned char>(c))); return s; }
inline bool startsNoCase(const std::string& s, const char* p)
{
    size_t i = 0;
    for (; p[i]; ++i) if (i >= s.size() || std::tolower(static_cast<unsigned char>(s[i])) != std::tolower(static_cast<unsigned char>(p[i]))) return false;
    return true;
}
inline bool endsNoCase(const std::string& s, const char* e)
{
    const std::string x = e;
    return s.size() >= x.size() && lower(s.substr(s.size() - x.size())) == lower(x);
}
// "Application/PDF; charset=x" -> "application/pdf"
inline std::string bareMime(const std::string& mime)
{
    std::string m = lower(mime.substr(0, mime.find(';')));
    while (!m.empty() && (m.back() == ' ' || m.back() == '\t')) m.pop_back();
    while (!m.empty() && (m.front() == ' ' || m.front() == '\t')) m.erase(0, 1);
    return m;
}
// The address's path (no query / fragment).
inline std::string urlPath(const std::string& url)
{
    const size_t scheme = url.find("://");
    const size_t start = scheme == std::string::npos ? 0 : url.find('/', scheme + 3);
    if (start == std::string::npos) return std::string();
    return url.substr(start, url.find_first_of("?#", start) - start);
}
inline bool httpURL(const std::string& url)
{
    if (url.empty() || url.size() > kMaxUrl) return false;
    if (!startsNoCase(url, "http://") && !startsNoCase(url, "https://")) return false;
    const size_t hostStart = url.find("://") + 3, hostEnd = url.find_first_of("/?#", hostStart);
    const std::string authority = url.substr(hostStart, hostEnd == std::string::npos ? std::string::npos : hostEnd - hostStart);
    if (authority.empty() || authority.find('@') != std::string::npos) return false;   // no user@host
    for (unsigned char c : url) if (c <= 0x20 || c == 0x7f) return false;
    return true;
}
// Is this response a PDF? application/pdf (x-pdf); or a generic binary type with a .pdf address / file name.
inline bool isPdfResponse(const std::string& mime, const std::string& url, const std::string& suggested)
{
    const std::string m = bareMime(mime);
    if (m == "application/pdf" || m == "application/x-pdf" || m == "application/acrobat") return true;
    const bool generic = m.empty() || m == "application/octet-stream" || m == "binary/octet-stream" || m == "application/download"
        || m == "application/x-download" || m == "application/force-download" || m == "application/unknown";
    return generic && (endsNoCase(urlPath(url), ".pdf") || endsNoCase(suggested, ".pdf"));
}

struct Decision {
    bool testMode = false, settingOn = true, viewerPresent = false, pagesCapable = false;
    bool mainFrame = true, attachment = false, downloadsTab = false;
    int status = 200;
    uint64_t expectedLength = 0;   // 0 / ~0: unknown
    std::string url, mime, suggested;
};
enum class Route { Normal, Reader };
inline bool lengthTooBig(uint64_t n) { return n != 0 && n != 0xFFFFFFFFull && n != ~0ull && n > kMaxBytes; }
inline Route decide(const Decision& d)
{
    if (d.testMode || !d.settingOn || !d.viewerPresent || !d.pagesCapable || d.downloadsTab) return Route::Normal;
    if (!d.mainFrame || d.attachment || d.status >= 400 || !httpURL(d.url)) return Route::Normal;
    if (!isPdfResponse(d.mime, d.url, d.suggested) || lengthTooBig(d.expectedLength)) return Route::Normal;
    return Route::Reader;
}

// 16 random bytes -> 32 lower-case hex digits.
inline std::string token(const uint8_t (&b)[16])
{
    static const char* hex = "0123456789abcdef";
    std::string t;
    for (uint8_t x : b) { t += hex[x >> 4]; t += hex[x & 15]; }
    return t;
}
inline bool validToken(const std::string& t)
{
    if (t.size() != 32) return false;
    for (char c : t) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    return true;
}
// The scheme handler's name for a document file: "<token>.pdf" -> token ("" when not one of ours).
inline std::string tokenFromFile(const std::string& name)
{
    if (name.size() != 36 || name.compare(32, 4, ".pdf")) return std::string();
    const std::string t = name.substr(0, 32);
    return validToken(t) ? t : std::string();
}
// "omni://pages/_user/pdf/<token>.pdf" (the page's save request) -> token.
inline std::string tokenFromDocURL(const std::string& url)
{
    const std::string base = kDocBase;
    if (url.compare(0, base.size(), base)) return std::string();
    return tokenFromFile(url.substr(base.size()));
}
inline std::string docURL(const std::string& tok) { return std::string(kDocBase) + tok + ".pdf"; }

inline std::string percentEncode(const std::string& s)
{
    static const char* hex = "0123456789ABCDEF";
    std::string o;
    for (unsigned char c : s) {
        if (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') o += char(c);
        else { o += '%'; o += hex[c >> 4]; o += hex[c & 15]; }
    }
    return o;
}
inline std::string percentDecode(const std::string& s)
{
    std::string o;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '%' && i + 2 < s.size() && std::isxdigit(static_cast<unsigned char>(s[i + 1])) && std::isxdigit(static_cast<unsigned char>(s[i + 2]))) {
            o += char(std::stoi(s.substr(i + 1, 2), nullptr, 16)); i += 2;
        } else o += s[i];
    }
    return o;
}
// A shown / saved file name: the suggested one, else the address's last path segment; safe characters; ends ".pdf".
inline std::string fileName(const std::string& suggested, const std::string& url)
{
    std::string n = suggested;
    if (n.empty()) {
        const std::string p = urlPath(url);
        n = percentDecode(p.substr(p.rfind('/') + 1));
    }
    std::string o;
    for (unsigned char c : n) {
        if (c < 0x20 || c == 0x7f || c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|') o += '_';
        else o += char(c);
    }
    while (!o.empty() && (o[0] == '.' || o[0] == ' ')) o.erase(0, 1);
    while (!o.empty() && (o.back() == ' ' || o.back() == '.')) o.pop_back();
    if (o.empty()) o = "document";
    if (o.size() > 120) o = o.substr(0, 116);
    if (!endsNoCase(o, ".pdf")) o += ".pdf";
    return o;
}
// Shown in notices: at most 60 characters ("first...last").
inline std::string shortName(const std::string& n) { return n.size() > 60 ? n.substr(0, 28) + "..." + n.substr(n.size() - 28) : n; }
// The reader's address (relative to omni://pages/, as omniPagesOpen takes it).
inline std::string viewerPath(const std::string& tok, const std::string& name, const std::string& src)
{
    std::string p = "pdf/index.html?doc=" + tok + "&name=" + percentEncode(name);
    if (httpURL(src)) p += "&src=" + percentEncode(src);
    return p;
}
inline bool isViewerURL(const std::string& url) { return url.compare(0, std::string(kViewerPrefix).size(), kViewerPrefix) == 0; }

// "name (2).pdf" ... when "name.pdf" is taken (exists() asks the file system); "" after 999 tries.
inline std::string uniqueName(const std::string& name, const std::function<bool(const std::string&)>& exists)
{
    if (!exists(name)) return name;
    const size_t dot = name.rfind('.');
    const std::string stem = dot == std::string::npos || dot == 0 ? name : name.substr(0, dot), ext = dot == std::string::npos || dot == 0 ? "" : name.substr(dot);
    for (int i = 2; i < 1000; ++i) {
        const std::string n = stem + " (" + std::to_string(i) + ")" + ext;
        if (!exists(n)) return n;
    }
    return std::string();
}

// Documents in memory: newest last; the oldest goes beyond kKeepDocs.
struct Doc {
    std::string token, name, src;
    std::vector<uint8_t> bytes;
    bool privateTab = false;
};
struct Store {
    std::vector<Doc> docs;
    void add(Doc d)
    {
        for (size_t i = 0; i < docs.size(); ++i) if (docs[i].token == d.token) { docs.erase(docs.begin() + long(i)); break; }
        docs.push_back(std::move(d));
        while (docs.size() > kKeepDocs) docs.erase(docs.begin());
    }
    const Doc* find(const std::string& tok) const
    {
        if (!validToken(tok)) return nullptr;
        for (const auto& d : docs) if (d.token == tok) return &d;
        return nullptr;
    }
    size_t bytes() const { size_t n = 0; for (const auto& d : docs) n += d.bytes.size(); return n; }
};

// R2 / L2 held: fire on press, again after kRepeatFirstMs, then every kRepeatMs; hysteresis on / off.
struct Trigger {
    bool held = false;
    uint32_t next = 0;
    bool step(int value, uint32_t now)
    {
        if (!held) {
            if (value < kTriggerOn) return false;
            held = true; next = now + kRepeatFirstMs;
            return true;
        }
        if (value <= kTriggerOff) { held = false; return false; }
        if (int32_t(now - next) < 0) return false;
        next = now + kRepeatMs;
        return true;
    }
    void reset() { held = false; next = 0; }
};

inline const char* settingValue(bool on, bool present) { return !present ? "Not installed" : on ? "On" : "Off"; }
inline const char* settingNotice(bool on) { return on ? "PDFs open in Omni's reader" : "PDFs go to Downloads"; }
inline std::string openingNotice(const std::string& name, long long total, long long expected)
{
    if (expected > 0 && total >= 0) {
        long long pct = total * 100 / expected;
        if (pct > 99) pct = 99;
        return "Opening " + shortName(name) + ": " + std::to_string(pct) + "%";
    }
    return "Opening " + shortName(name) + "...";
}
inline const char* tooBigNotice(bool sent) { return sent ? "PDF too large for the reader (over 32 MB): sent to Downloads" : "PDF too large for the reader (over 32 MB)"; }

} // namespace OmniPdfViewer
'''

SHELL = r'''// OMNI_PDF_VIEWER_V1: the shell side of "PDFs open in Omni" (pure part: OmniPdfViewer.h; reasons in
// tools/apply_pdf_viewer.py). Included from OmniBrowser.cpp right after OmniPages.h (omniPagesOpen / omniPagesRoot,
// omniMediaDownloadsRequest, omniSafeFileName and the download types are above).
#pragma once
namespace OPDF = OmniPdfViewer;

static OPDF::Store omniPdfvDocs;
static int omniPdfvSetting = -1, omniPdfvPresent = -1;
static bool omniPdfvTempClean = false;
struct OmniPdfvPending { WKPageRef page = nullptr; std::string url, name; bool privateTab = false; uint32_t at = 0; };
static OmniPdfvPending omniPdfvPending;
struct OmniPdfvJob { WKPageRef page = nullptr; std::string url, name, token, path; bool privateTab = false, tooBig = false; uint32_t noticeAt = 0; };
static std::unordered_map<const void*, OmniPdfvJob> omniPdfvJobs;   // by WKDownloadRef
static OPDF::Trigger omniPdfvTrig[2];

static bool omniPdfvOn()
{
    if (omniPdfvSetting < 0) omniPdfvSetting = access(omniData(OPDF::kOffFlag).c_str(), F_OK) != 0 ? 1 : 0;
    return omniPdfvSetting == 1;
}
static bool omniPdfvFile(const std::string& name, std::vector<uint8_t>& data, std::string& mime)
{
    const OPDF::Doc* d = omniPdfvDocs.find(OPDF::tokenFromFile(name));
    if (!d) return false;
    data = d->bytes;
    mime = "application/pdf";
    return true;
}
// The reader and pdf.js in the pages bundle (checked once; the scheme hook is registered with it).
static bool omniPdfvViewerPresent()
{
    if (omniPdfvPresent < 0) {
        bool ok = omniPagesEnabled() && !omniPagesRoot.empty();
        for (const char* f : OPDF::kViewerFiles) if (ok && access((omniPagesRoot + "/" + f).c_str(), R_OK)) ok = false;
        omniPdfvPresent = ok ? 1 : 0;
        if (ok) omniPagesSetPdfFile(omniPdfvFile);
        fprintf(stderr, "pdf: OMNI_PDF_VIEWER_V1 reader %s\n", ok ? "present" : "missing");
    }
    return omniPdfvPresent == 1;
}
static bool omniPdfvIsViewer(const Tab* tab) { return tab && tab->omniPagesTab && OPDF::isViewerURL(tab->url); }
static bool omniPdfvOwnsTriggers()
{
    const Tab* t = active();
    return omniPdfvIsViewer(t) && !t->crashed && !editing && !settingsOpen && !pageFullscreen && !omniOverlayOpen();
}

// --- the response policy -----------------------------------------------------------------------------------------------
static bool omniPdfvTake(WKPageRef page, WKURLResponseRef response, bool mainFrame, bool attachment)
{
    Tab* tab = omniTabForPage(page);
    if (!tab || !response) return false;
    OPDF::Decision d;
    d.testMode = omniTestMode();
    if (d.testMode) return false;
    d.settingOn = omniPdfvOn();
    d.viewerPresent = d.settingOn && omniPdfvViewerPresent();
    d.pagesCapable = tab->omniPagesCapable;
    d.downloadsTab = tab->omniMediaSection;
    d.mainFrame = mainFrame;
    d.attachment = attachment;
    d.status = WKURLResponseHTTPStatusCode(response);
    d.expectedLength = WKURLResponseGetExpectedContentLength(response);
    if (auto url = adoptWK(WKURLResponseCopyURL(response))) d.url = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
    if (auto mime = adoptWK(WKURLResponseCopyMIMEType(response))) d.mime = OmniTest::toStd(mime.get());
    if (auto s = adoptWK(WKURLResponseCopySuggestedFilename(response))) d.suggested = OmniTest::toStd(s.get());
    if (OPDF::decide(d) != OPDF::Route::Reader) return false;
    omniPdfvPending = { page, d.url, OPDF::fileName(d.suggested, d.url), tab->omniPrivate, SDL_GetTicks() };
    notice(OPDF::openingNotice(omniPdfvPending.name, 0, 0));
    return true;   // the caller turns the response into a WebKit download (same request, same session)
}

// --- the download: a temporary file of our own, read into memory and deleted ------------------------------------------
static void omniPdfvCleanTemp()
{
    const std::string dir = omniData(OPDF::kTempDir);
    mkdir(dir.c_str(), 0700);
    if (omniPdfvTempClean) return;
    omniPdfvTempClean = true;   // first use this run: leftovers of a crash go
    if (DIR* dp = opendir(dir.c_str())) {
        while (dirent* e = readdir(dp)) if (e->d_name[0] != '.') unlink((dir + "/" + e->d_name).c_str());
        closedir(dp);
    }
}
static std::string omniPdfvNewToken()
{
    uint8_t b[16] = {};
    bool ok = false;
    if (FILE* f = fopen("/dev/urandom", "rb")) { ok = fread(b, 1, sizeof b, f) == sizeof b; fclose(f); }
    if (!ok) {   // no /dev/urandom: splitmix64 over clock, ticks, a counter and an address (web content can't reach these
                 // documents anyway: omniPagesAllow keeps omni://pages to Omni's own pages)
        static uint64_t state = uint64_t(time(nullptr)) ^ (uint64_t(reinterpret_cast<uintptr_t>(&state)) << 16);
        for (auto& x : b) {
            state += 0x9E3779B97F4A7C15ull ^ uint64_t(SDL_GetTicks());
            uint64_t z = state;
            z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
            z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
            x = uint8_t(z ^ (z >> 31));
        }
    }
    return OPDF::token(b);
}
static WKStringRef omniPdfvDestination(WKDownloadRef download, WKURLResponseRef, WKStringRef, const void*)
{
    auto it = omniPdfvJobs.find(download);
    if (it == omniPdfvJobs.end()) return WKStringCreateWithUTF8CString((omniData(OPDF::kTempDir) + "/orphan.pdf").c_str());
    omniPdfvCleanTemp();
    it->second.path = omniData(OPDF::kTempDir) + "/" + it->second.token + ".pdf";
    return WKStringCreateWithUTF8CString(it->second.path.c_str());   // +1: WebKit adopts it
}
// OMNI_PDF_VIEWER_V1_R2: the name a notice may show: none for a private tab's PDF (the notice can outlive the last
// private tab and land in Recent notices).
static std::string omniPdfvJobName(const OmniPdfvJob& job) { return job.privateTab ? std::string("the PDF") : OPDF::shortName(job.name); }
static void omniPdfvFailed(WKDownloadRef download)
{
    auto it = omniPdfvJobs.find(download);
    if (it == omniPdfvJobs.end()) return;
    const OmniPdfvJob job = it->second;
    omniPdfvJobs.erase(it);
    if (!job.path.empty()) unlink(job.path.c_str());
    if (!job.tooBig) { notice("Couldn't open " + omniPdfvJobName(job)); return; }
    const bool send = !job.privateTab && omniMediaDownloadsEnabled && OmniMediaSection::validLink(job.url);
    if (send) omniMediaDownloadsRequest(false, false, true, job.url);   // as OMNI_FILE_DOWNLOADS_V1 hands files over
    notice(OPDF::tooBigNotice(send));
}
static void omniPdfvFinished(WKDownloadRef download)
{
    auto it = omniPdfvJobs.find(download);
    if (it == omniPdfvJobs.end()) return;
    const OmniPdfvJob job = it->second;
    omniPdfvJobs.erase(it);
    OPDF::Doc doc;
    doc.token = job.token; doc.name = job.name; doc.src = job.url; doc.privateTab = job.privateTab;
    bool ok = false;
    if (FILE* f = job.path.empty() ? nullptr : fopen(job.path.c_str(), "rb")) {
        uint8_t buf[65536];
        size_t n;
        ok = true;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0) {
            if (doc.bytes.size() + n > OPDF::kMaxBytes) { ok = false; break; }
            doc.bytes.insert(doc.bytes.end(), buf, buf + n);
        }
        fclose(f);
    }
    if (!job.path.empty()) unlink(job.path.c_str());   // never kept on disk (private tabs included)
    Tab* tab = omniTabForPage(job.page);
    if (!ok || doc.bytes.empty()) { notice("Couldn't open " + omniPdfvJobName(job)); return; }
    if (!tab || !tab->omniPagesCapable) return;   // the tab closed meanwhile: nothing kept
    const std::string path = OPDF::viewerPath(doc.token, doc.name, doc.src);
    omniPdfvDocs.add(std::move(doc));
    if (!omniPagesOpen(tab, path)) notice("Couldn't open the PDF reader");
}
static bool omniPdfvBecameDownload(WKPageRef page, WKNavigationResponseRef navigationResponse, WKDownloadRef download)
{
    if (!omniPdfvPending.page || omniPdfvPending.page != page || SDL_GetTicks() - omniPdfvPending.at > OPDF::kPendingMs) return false;
    std::string url;
    if (auto response = adoptWK(WKNavigationResponseCopyResponse(navigationResponse)))
        if (auto u = adoptWK(WKURLResponseCopyURL(response.get()))) url = OmniTest::toStd(adoptWK(WKURLCopyString(u.get())).get());
    if (url != omniPdfvPending.url) return false;
    OmniPdfvJob job;
    job.page = page; job.url = url; job.name = omniPdfvPending.name; job.privateTab = omniPdfvPending.privateTab;
    job.token = omniPdfvNewToken();
    omniPdfvPending = OmniPdfvPending();
    omniPdfvJobs[download] = job;
    static WKDownloadClientV0 client {};
    client.base.version = 0;
    client.decideDestinationWithResponse = omniPdfvDestination;
    client.didWriteData = [](WKDownloadRef download, long long, long long total, long long expected, const void*) {
        auto it = omniPdfvJobs.find(download);
        if (it == omniPdfvJobs.end() || it->second.tooBig) return;
        if (total > (long long)OPDF::kMaxBytes) {
            it->second.tooBig = true;
            WKDownloadCancel(download, nullptr, [](WKDataRef, const void*) {});   // didFailWithError follows
            return;
        }
        if (SDL_GetTicks() - it->second.noticeAt < 1000) return;
        it->second.noticeAt = SDL_GetTicks();
        notice(OPDF::openingNotice(it->second.privateTab ? std::string("the PDF") : it->second.name, total, expected)); // R2: no name for private
    };
    client.didFinish = [](WKDownloadRef download, const void*) { omniPdfvFinished(download); };
    client.didFailWithError = [](WKDownloadRef download, WKErrorRef, WKDataRef, const void*) { omniPdfvFailed(download); };
    WKDownloadSetClient(download, &client.base);
    return true;
}

// --- the reader page's requests (omnibloomHost.request) -----------------------------------------------------------------
static std::string omniPdfvBridge(WKPageRef, Tab& tab, const std::string& method, const std::string& url)
{
    if (!omniPdfvIsViewer(&tab)) return omniPagesErr("DENIED");
    if (method != "pdf.save") return omniPagesErr("UNSUPPORTED");
    const OPDF::Doc* d = omniPdfvDocs.find(OPDF::tokenFromDocURL(url));
    if (!d) return omniPagesErr("NOT_FOUND");
    const std::string dir = omniData("downloads");
    mkdir(dir.c_str(), 0777);
    const std::string name = OPDF::uniqueName(omniSafeFileName(d->name), [&](const std::string& n) { return access((dir + "/" + n).c_str(), F_OK) == 0; });
    if (name.empty()) return omniPagesErr("UNAVAILABLE");
    const std::string path = dir + "/" + name;
    FILE* f = fopen(path.c_str(), "wb");
    if (!f) return omniPagesErr("UNAVAILABLE");
    const bool ok = fwrite(d->bytes.data(), 1, d->bytes.size(), f) == d->bytes.size();
    if (fclose(f) != 0 || !ok) { unlink(path.c_str()); return omniPagesErr("UNAVAILABLE"); }
    notice("Saved " + OPDF::shortName(name) + " to Downloads");
    return omniPagesOk("{\"name\":" + omniPagesJsonQuote(name) + "}");
}

// --- R2 / L2 on the reader: zoom (the saved-links trigger shortcuts stand down there: omniSavedContext) -----------------
static void omniPdfvTick(uint32_t now)
{
    if (!omniPdfvOwnsTriggers() || active()->loading || !controller || !SDL_GameControllerGetAttached(controller)) {
        omniPdfvTrig[0].reset(); omniPdfvTrig[1].reset();
        return;
    }
    for (int i = 0; i < 2; ++i) {
        const int v = SDL_GameControllerGetAxis(controller, i ? SDL_CONTROLLER_AXIS_TRIGGERRIGHT : SDL_CONTROLLER_AXIS_TRIGGERLEFT);
        if (!omniPdfvTrig[i].step(v, now)) continue;
        auto js = adoptWK(WKStringCreateWithUTF8CString(i ? "window.omniMediaController?.('r2')" : "window.omniMediaController?.('l2')"));   // fixed scripts
        WKPageEvaluateJavaScriptInMainFrame(active()->page, js.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
    }
}

// --- Browser settings: "Open PDFs in Omni" On / Off ----------------------------------------------------------------------
static void omniPdfvSettingsRow(OmniFxPanel& p)
{
    const bool present = omniPdfvViewerPresent();
    OmniFxRow r; r.id = OPDF::kRowId; r.label = "Open PDFs in Omni"; r.value = OPDF::settingValue(omniPdfvOn(), present); r.stepper = present;
    r.enabled = present;
    p.rows.push_back(r);
}
static bool omniPdfvSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    if (!omniPdfvViewerPresent()) return true;
    const std::string flag = omniData(OPDF::kOffFlag);
    if (omniPdfvOn()) { if (FILE* f = fopen(flag.c_str(), "w")) { fputs("1\n", f); fclose(f); } }
    else unlink(flag.c_str());
    omniPdfvSetting = -1;
    notice(OPDF::settingNotice(omniPdfvOn()));
    return true;
}
'''

C = '/* ' + MARK + ' */'
EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n',
         '#include "OmniPdfViewer.h" /* ' + MARK + ': PDFs open in the built-in reader (pure) */\n'
         '#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n'),
        ('static bool omniFileDownloadsTake(WKPageRef page, WKURLResponseRef response); // OMNI_FILE_DOWNLOADS_V1\n',
         'static bool omniFileDownloadsTake(WKPageRef page, WKURLResponseRef response); // OMNI_FILE_DOWNLOADS_V1\n'
         'static bool omniPdfvTake(WKPageRef page, WKURLResponseRef response, bool mainFrame, bool attachment); /* ' + MARK + ' (OmniPdfViewerShell.h) */\n'
         'static bool omniPdfvBecameDownload(WKPageRef page, WKNavigationResponseRef navigationResponse, WKDownloadRef download); ' + C + '\n'
         'static bool omniPdfvIsViewer(const Tab* tab); ' + C + '\n'
         'static bool omniPdfvOwnsTriggers(); ' + C + '\n'
         'static void omniPdfvTick(uint32_t now); ' + C + '\n'
         'static std::string omniPdfvBridge(WKPageRef page, Tab& tab, const std::string& method, const std::string& url); ' + C + '\n'),
        ('            if (omniFileDownloadsTake(page, response.get())) WKFramePolicyListenerIgnore(listener);\n',
         '            if (omniPdfvTake(page, response.get(), mainFrame, attachment)) { WKFramePolicyListenerDownload(listener); return; } /* ' + MARK + ': a PDF opens in the reader (this response, downloaded by WebKit) */\n'
         '            if (omniFileDownloadsTake(page, response.get())) WKFramePolicyListenerIgnore(listener);\n'),
        ('    nav.navigationResponseDidBecomeDownload = [](WKPageRef, WKNavigationResponseRef, WKDownloadRef download, const void*) { omniDownloadInstall(download); };\n',
         '    nav.navigationResponseDidBecomeDownload = [](WKPageRef page, WKNavigationResponseRef navigationResponse, WKDownloadRef download, const void*) {\n'
         '        if (omniPdfvBecameDownload(page, navigationResponse, download)) return; /* ' + MARK + ': the reader\'s own download client */\n'
         '        omniDownloadInstall(download);\n'
         '    };\n'),
        ('        && !omniOverlayOpen() && !omniFindBarOpen() && !active()->crashed;\n'
         '    return { pad, active() ? active()->omniMediaIdentity : 0, active() ? active()->omniSavedDocument : 0, allowed, pageFullscreen };\n',
         '        && !omniOverlayOpen() && !omniFindBarOpen() && !active()->crashed\n'
         '        && !omniPdfvOwnsTriggers(); /* ' + MARK + ': R2 / L2 zoom the PDF reader */\n'
         '    return { pad, active() ? active()->omniMediaIdentity : 0, active() ? active()->omniSavedDocument : 0, allowed, pageFullscreen };\n'),
        ('#include "OmniPages.h" // s3 OMNI_PAGES_V1: omni://pages built-in pages\n',
         '#include "OmniPages.h" // s3 OMNI_PAGES_V1: omni://pages built-in pages\n'
         '#include "OmniPdfViewerShell.h" /* ' + MARK + ': PDFs open in the reader (after OmniPages.h) */\n'),
    ],
    'OmniPages.h': [
        ("    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: script = \"window.omniMediaController?.('r1')===true?'1':'0'\"; break;\n",
         "    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: script = \"window.omniMediaController?.('r1')===true?'1':'0'\"; break;\n"
         "    case SDL_CONTROLLER_BUTTON_X: if (!omniPdfvIsViewer(active())) return false; script = \"window.omniMediaController?.('square')===true?'1':'0'\"; break; /* " + MARK + ": Square saves (the reader only) */\n"),
        ('        if (method.rfind("webapps.", 0) == 0) return omniWapBridge(page, *tab, method, omniPagesField(a, "url")); // OMNI_WEB_APPS_V1 (OmniWebAppsShell.h)\n',
         '        if (method.rfind("pdf.", 0) == 0) return omniPdfvBridge(page, *tab, method, omniPagesField(a, "url")); /* ' + MARK + ': pdf.save */\n'
         '        if (method.rfind("webapps.", 0) == 0) return omniWapBridge(page, *tab, method, omniPagesField(a, "url")); // OMNI_WEB_APPS_V1 (OmniWebAppsShell.h)\n'),
    ],
    'OmniBlocker.cpp': [
        ('OmniPagesUserFileFn pagesUserFile = nullptr;   // OMNI_START_CUSTOM_V1\n',
         'OmniPagesUserFileFn pagesUserFile = nullptr;   // OMNI_START_CUSTOM_V1\n'
         'OmniPagesUserFileFn pagesPdfFile = nullptr; /* ' + MARK + ': _user/pdf/<token>.pdf from the shell\'s memory */\n'),
        ('        if (rel.rfind("_user/", 0) == 0) { // OMNI_START_CUSTOM_V1: only the start page\'s picture, from the shell\'s cached copy\n',
         '        if (rel.rfind("_user/pdf/", 0) == 0) { /* ' + MARK + ': a PDF the shell holds (the reader fetches it same-origin) */\n'
         '            std::vector<uint8_t> bytes;\n'
         '            std::string mime;\n'
         '            if (!pagesPdfFile || !pagesPdfFile(rel.substr(10), bytes, mime) || bytes.empty() || mime != "application/pdf") { fail(404, "not found"); return; }\n'
         '            WebCore::ResourceResponse response { WTF::URL { wurl }, WTF::String::fromLatin1("application/pdf"), static_cast<long long>(bytes.size()), WTF::String() };\n'
         '            response.setHTTPStatusCode(200);\n'
         '            response.setHTTPHeaderField(WebCore::HTTPHeaderName::ContentSecurityPolicy, WTF::String::fromLatin1(pagesCSP));\n'
         '            response.setHTTPHeaderField(WTF::String::fromLatin1("X-Content-Type-Options"), WTF::String::fromLatin1("nosniff"));\n'
         '            response.setHTTPHeaderField(WTF::String::fromLatin1("Cache-Control"), WTF::String::fromLatin1("no-store"));\n'
         '            task.didReceiveResponse(WTF::move(response));\n'
         '            task.didReceiveData(WebCore::SharedBuffer::create(std::span<const uint8_t>(bytes.data(), bytes.size())));\n'
         '            task.didComplete(WebCore::ResourceError());\n'
         '            return;\n'
         '        }\n'
         '        if (rel.rfind("_user/", 0) == 0) { // OMNI_START_CUSTOM_V1: only the start page\'s picture, from the shell\'s cached copy\n'),
        ('void omniPagesSetUserFile(OmniPagesUserFileFn fn) { pagesUserFile = fn; } // OMNI_START_CUSTOM_V1\n',
         'void omniPagesSetUserFile(OmniPagesUserFileFn fn) { pagesUserFile = fn; } // OMNI_START_CUSTOM_V1\n'
         'void omniPagesSetPdfFile(OmniPagesUserFileFn fn) { pagesPdfFile = fn; } ' + C + '\n'),
    ],
    'OmniBlocker.h': [
        ('void omniPagesSetUserFile(OmniPagesUserFileFn fn);\n',
         'void omniPagesSetUserFile(OmniPagesUserFileFn fn);\n'
         'void omniPagesSetPdfFile(OmniPagesUserFileFn fn); /* ' + MARK + ': omni://pages/_user/pdf/<token>.pdf */\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniOrRowId = 895; // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h)\n',
         'constexpr int omniOrRowId = 895; // OMNI_OFFLINE_RETRY_V1 (OmniOfflineRetryShell.h)\n'
         'static void omniPdfvSettingsRow(OmniFxPanel& p); /* ' + MARK + ': "Open PDFs in Omni" (OmniPdfViewerShell.h; row id OmniPdfViewer::kRowId) */\n'
         'static bool omniPdfvSettingsInput(int b); ' + C + '\n'),
        ('    add(omniOrRowId, "Reload pages when back online", omniOrOn() ? "On" : "Off", true); // OMNI_OFFLINE_RETRY_V1\n',
         '    add(omniOrRowId, "Reload pages when back online", omniOrOn() ? "On" : "Off", true); // OMNI_OFFLINE_RETRY_V1\n'
         '    omniPdfvSettingsRow(p); /* ' + MARK + ': Open PDFs in Omni */\n'),
        ('    if (r.id == omniOrRowId) return omniOrSettingsInput(b); // OMNI_OFFLINE_RETRY_V1 (before the >= 300 rows)\n',
         '    if (r.id == OmniPdfViewer::kRowId) return omniPdfvSettingsInput(b); /* ' + MARK + ' (before the >= 300 rows) */\n'
         '    if (r.id == omniOrRowId) return omniOrSettingsInput(b); // OMNI_OFFLINE_RETRY_V1 (before the >= 300 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n',
         '    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n'
         '    omniPdfvTick(now);  /* ' + MARK + ': R2 / L2 zoom on the PDF reader */\n'),
    ],
}
NEEDS = [('OmniBrowser.cpp', 'OMNI_FILE_DOWNLOADS_V1', 'apply_file_downloads.py'),
         ('OmniBrowserSettings.h', 'OMNI_OFFLINE_RETRY_V1', 'apply_offline_retry.py'),
         ('OmniFeatures3.h', 'OMNI_DL_PROGRESS_V1', 'apply_dl_progress.py'),
         ('OmniBlocker.cpp', 'OMNI_START_CUSTOM_V1', 'apply_start_custom.py'),
         ('OmniPages.h', 'OMNI_WEB_APPS_V1', 'apply_web_apps.py')]
TAKEN = [re.compile(r'\b896\b'), re.compile(r'\bomniPdfv\w*'), re.compile(r'\bOPDF\b'), re.compile(r'\bomniPagesSetPdfFile\b'),
         re.compile(r'\bpagesPdfFile\b'), re.compile(r'\bOmniPdfViewer\b')]


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


# OMNI_PDF_VIEWER_V1_R2: a block compiled only when this patch is there (#if __has_include("OmniPdfViewer.h") ...
# #endif, e.g. OmniScrollPlusShell.h's omniPdfvOwnsTriggers() check) uses our names on purpose.
HAS_PDFV = re.compile(r'#if __has_include\("OmniPdfViewer(?:Shell)?\.h"\).*?#endif', re.S)


def ids_free():
    """Before the first apply: the row id and our names must not be used anywhere in the tree yet."""
    for f in sorted(root.iterdir()):
        if f.suffix not in ('.h', '.cpp', '.inc') or f.name in ('OmniPdfViewer.h', 'OmniPdfViewerShell.h'):
            continue
        s = cpp_code(f.read_bytes().decode('utf-8', 'replace'))
        s = HAS_PDFV.sub('', s)   # R2: other patches' guarded calls into this one (OMNI_SCROLL_PLUS_V1_R2) are not clashes
        for rx in (TAKEN[:1] if f.name in GUIDE else TAKEN):
            m = rx.search(s)
            if m:
                sys.exit('%s: %r already used (%s): choose another id / alias' % (f.name, m.group(0), MARK))


def main():
    for name, mark, tool in NEEDS:
        if mark not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (name, mark, tool))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniPdfViewer.h', PURE, 'OmniHttpsOnly.h'),
            write_new('OmniPdfViewerShell.h', SHELL, 'OmniHttpsOnlyShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
