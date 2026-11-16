#!/usr/bin/env python3
"""OMNI_DOWNLOAD_ALL_V1 (2026-11-16): the hold-Cross page menu's "Download all..." collects the file links of the page
and hands the chosen ones to the Downloads app in one go.

What the user sees
  - Page menu (hold Cross over the page, not over a link / image): "Download all..." after "Save page for later".
    Offered only where a single "Save link target" would go to Downloads (OMNI_SAVE_IMAGE_V1 / OMNI_FILE_DOWNLOADS_V1
    rules): never in private tabs, not with "Media downloads" off, not on the Downloads tab, not in self-tests, only on
    http(s) pages.
  - Cross: "Looking for files on this page..."; one read-only page script (main frame) lists candidates:
      <a href> with a known file extension, a download attribute, or a file MIME type attribute (type=);
      <img> whose natural (else rendered) longer side is >= 200 px; <video>/<audio>/<source> sources (not blob:).
    Absolute http(s) addresses only (no user@host, <= 2048 bytes), fragment dropped, deduplicated, at most 200 (page
    order; the subtitle says when there were more). Streams (.m3u8 / .mpd) and pages (.html, .php, ...) are left out.
  - The panel ("Download all", subtitle "<host>: N files found"):
        Download N files                  (first row; disabled until something is chosen)
        Select all files                  value: "All N" / "x of N" / "N found"
        Select all PDFs / Images / Audio / Video / Archives / Other files   (only groups that have files; same values)
          <file name>  <host>  [check]    one row per file, Cross toggles
    Type: the extension of the download attribute's name, else of the address's path, else the type= MIME, else the
    element (img / video / audio), else "Other files" when the link has a download attribute.
    Archives: zip 7z rar tar gz tgz bz2 xz. "Other files": a fixed extension list (documents, e-books, subtitles,
    disc images, installers, torrents; see kExt in OmniDownloadAll.h).
  - "Download N files": the Downloads tab opens / comes forward with #files=<{"v":1,"p":page,"u":[addresses]}>
    (omniMediaDownloadsRequest(false, false, false) + the tick's plan, like the media shortcut); notice
    "Sent N files to Downloads". The Downloads app shows the list and asks once ("Download N files"); its press posts
    the list to the worker's POST /api/jobs/batch (session token, localhost only; OMNI_DOWNLOAD_ALL_V1 in
    omnibloom/downloads/worker), which queues them as original files (8 at a time, the rest wait in the worker).
    The encoded list is capped at 240000 bytes: what does not fit is not sent ("Sent N of M files ...").
  - The same list again within 3 s is not sent twice (the notice repeats). A request that is not accepted ("Media
    downloads is opening", "Close a tab ...") keeps its own notice and the panel stays open for a retry.
  - The list is dropped if, when the worker answers, you are on another tab (the usual "press L1 + R1" notice shows).

Pure part: engine/entry/OmniDownloadAll.h (type classification, row parsing, dedupe, caps, selection, the #files=
field, texts, the page script). Tests: tools/test_download_all.cpp (g++; writes the page script to argv[1] when given),
tools/test_download_all_js.cjs <script file> (node: runs the script on mock DOMs).
Shell part: engine/entry/OmniDownloadAllShell.h (namespace alias ODAL; context row 995, panel kind 7540; both checked free
in the engine tree, comments stripped, before a first apply; names also against the sibling apply_*.py code), included from
OmniContextMenu.h before its menu section.
Anchors (each once; whole lines kept; inserted lines carry the MARK in /* */ comments):
  OmniBrowser.cpp                the OmniSaveImage.h include line (pure include after it)
  OmniMediaDownloadsHooks.inc    the omniMediaCandidatePage declaration (omniDalField after it); the tick's
                                 'omniMediaCandidatePage.clear();' line (the list is taken after it); the
                                 'omniDlpHandedOver();' line (the #files= plan before it)
  OmniContextMenu.h              the '// --- the menu ---' line (shell include before it); the omniRlContextRows line
                                 (row after it); the omniTslContextAction line (action after it)
  OmniControlsHelp.h             the "Save link target / Save image" row (new row after it)
Needs OMNI_SAVE_IMAGE_V1 (its pure header and include line). Apply at the end of the chain.
usage: apply_download_all.py <engine tree>   (anchored, idempotent, keeps CRLF)
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_DOWNLOAD_ALL_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).resolve().parent
IDS = ['995', '7540']                                   # page-menu row, panel kind
NAMES = [r'omniDal', r'ODAL', r'OmniDownloadAll']
MINE = {'OmniDownloadAll.h', 'OmniDownloadAllShell.h'}

PURE = r'''// OMNI_DOWNLOAD_ALL_V1: the pure part of the page menu's "Download all..." (no SDL, no WebKit): file type from
// extension / MIME / element, the page script's rows, dedupe, caps, the selection, the #files= field for the Downloads
// app, texts. Shell side: OmniDownloadAllShell.h; reasons in tools/apply_download_all.py. Tested on the host with g++
// (tools/test_download_all.cpp) and node (tools/test_download_all_js.cjs).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_set>
#include <vector>
#include "OmniMediaSection.h"
#include "OmniSaveImage.h"

namespace OmniDownloadAll {

constexpr size_t kMax = 200;          // candidates in the panel (page order)
constexpr size_t kUrlMax = 2048;      // longer addresses are left out (keeps the #files= list bounded)
constexpr size_t kFieldMax = 240000;  // the encoded #files= value; the Downloads app accepts up to 262144
constexpr size_t kRawMax = 600;       // rows the page script returns at most
constexpr int kMinImage = 200;        // <img>: the longer natural side, CSS px

enum Kind : int { Pdf = 0, Image, Audio, Video, Archive, Other, KindCount, None = -1 };

inline const char* groupName(int k)
{
    switch (k) {
    case Pdf: return "PDFs";
    case Image: return "Images";
    case Audio: return "Audio";
    case Video: return "Video";
    case Archive: return "Archives";
    case Other: return "Other files";
    }
    return "";
}

struct Ext { const char* ext; Kind kind; };
inline const std::vector<Ext>& kExt()
{
    static const std::vector<Ext> t = {
        { "pdf", Pdf },
        { "jpg", Image }, { "jpeg", Image }, { "png", Image }, { "gif", Image }, { "webp", Image }, { "bmp", Image },
        { "svg", Image }, { "avif", Image }, { "heic", Image }, { "tif", Image }, { "tiff", Image },
        { "mp3", Audio }, { "m4a", Audio }, { "aac", Audio }, { "flac", Audio }, { "wav", Audio }, { "ogg", Audio },
        { "oga", Audio }, { "opus", Audio }, { "wma", Audio },
        { "mp4", Video }, { "m4v", Video }, { "mkv", Video }, { "webm", Video }, { "mov", Video }, { "avi", Video },
        { "wmv", Video }, { "flv", Video }, { "mpg", Video }, { "mpeg", Video }, { "3gp", Video }, { "ts", Video },
        { "zip", Archive }, { "7z", Archive }, { "rar", Archive }, { "tar", Archive }, { "gz", Archive }, { "tgz", Archive },
        { "bz2", Archive }, { "xz", Archive },
        { "doc", Other }, { "docx", Other }, { "xls", Other }, { "xlsx", Other }, { "ppt", Other }, { "pptx", Other },
        { "odt", Other }, { "ods", Other }, { "odp", Other }, { "rtf", Other }, { "txt", Other }, { "csv", Other },
        { "epub", Other }, { "mobi", Other }, { "azw3", Other }, { "cbz", Other }, { "cbr", Other }, { "srt", Other },
        { "vtt", Other }, { "ass", Other }, { "iso", Other }, { "img", Other }, { "bin", Other }, { "apk", Other },
        { "exe", Other }, { "msi", Other }, { "dmg", Other }, { "deb", Other }, { "rpm", Other }, { "pkg", Other },
        { "torrent", Other },
    };
    return t;
}
// Extensions that mean "a page or a stream", never a file to save (unless the link has a download attribute).
inline bool pageExt(const std::string& e)
{
    static const char* const pages[] = { "html", "htm", "xhtml", "shtml", "php", "asp", "aspx", "jsp", "cgi", "m3u8", "mpd" };
    for (const char* p : pages) if (e == p) return true;
    return false;
}

inline char lowerChar(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }
inline std::string lower(std::string s) { for (auto& c : s) c = lowerChar(c); return s; }

// The extension of a name or path: after the last '.' of the last segment, 1..7 letters / digits, lower case.
inline std::string extOf(const std::string& name)
{
    const size_t slash = name.find_last_of("/\\"), start = slash == std::string::npos ? 0 : slash + 1;
    const size_t dot = name.rfind('.');
    if (dot == std::string::npos || dot < start || dot + 1 >= name.size() || name.size() - dot - 1 > 7) return "";
    std::string e = name.substr(dot + 1);
    for (char c : e) if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) return "";
    return lower(e);
}
inline Kind kindForExt(const std::string& e)
{
    if (e.empty()) return None;
    for (const auto& x : kExt()) if (e == x.ext) return x.kind;
    return None;
}
// "scheme://host/path?q#f" -> "/path" (percent-decoded); "" without a path.
inline std::string urlPath(const std::string& url)
{
    const size_t scheme = url.find("://"), start = scheme == std::string::npos ? 0 : scheme + 3;
    const size_t end = std::min(url.find_first_of("?#", start), url.size());
    const size_t path = url.find('/', start);
    if (path == std::string::npos || path >= end) return "";
    return OmniSaveImage::percentDecode(url.substr(path, end - path));
}
inline std::string hostOf(const std::string& url)
{
    const size_t scheme = url.find("://"), start = scheme == std::string::npos ? 0 : scheme + 3;
    const size_t end = std::min(url.find_first_of("/?#", start), url.size());
    return lower(url.substr(start, end - start));
}
inline std::string stripFragment(const std::string& url)
{
    const size_t hash = url.find('#');
    return hash == std::string::npos ? url : url.substr(0, hash);
}
inline Kind kindForMime(const std::string& mime0)
{
    std::string m = lower(mime0);
    const size_t semi = m.find(';');
    if (semi != std::string::npos) m.resize(semi);
    while (!m.empty() && m.back() == ' ') m.pop_back();
    while (!m.empty() && m[0] == ' ') m.erase(0, 1);
    if (m == "application/pdf") return Pdf;
    if (m == "application/vnd.apple.mpegurl" || m == "application/x-mpegurl" || m == "application/dash+xml"
        || m == "audio/mpegurl" || m == "audio/x-mpegurl") return None;   // streams
    if (m.compare(0, 6, "image/") == 0 && m.size() > 6) return Image;
    if (m.compare(0, 6, "audio/") == 0 && m.size() > 6) return Audio;
    if (m.compare(0, 6, "video/") == 0 && m.size() > 6) return Video;
    static const char* const archives[] = { "application/zip", "application/x-zip-compressed", "application/x-7z-compressed",
        "application/vnd.rar", "application/x-rar-compressed", "application/x-rar", "application/gzip", "application/x-gzip",
        "application/x-tar", "application/x-bzip2", "application/x-xz" };
    for (const char* a : archives) if (m == a) return Archive;
    return None;
}
inline bool bigEnough(int w, int h) { return std::max(w, h) >= kMinImage; }

// One row of the page script: tag (a / img / video / audio), natural size (img), download attribute (present + value),
// type= MIME, absolute address.
struct Raw {
    std::string tag, download, mime, url;
    int w = 0, h = 0;
    bool hasDownload = false;
};
inline Kind classify(const Raw& r)
{
    if (r.tag == "img" && !bigEnough(r.w, r.h)) return None;
    Kind k = kindForExt(extOf(r.download));
    if (k != None) return k;
    const std::string e = extOf(urlPath(r.url));
    k = kindForExt(e);
    if (k != None) return k;
    if (pageExt(e)) return r.hasDownload ? Other : None;
    k = kindForMime(r.mime);
    if (k != None) return k;
    if (r.tag == "img") return Image;
    if (r.tag == "video") return Video;
    if (r.tag == "audio") return Audio;
    return r.hasDownload ? Other : None;
}

struct Candidate { std::string url, name; Kind kind = None; };
struct List {
    std::vector<Candidate> items;
    std::vector<char> on;     // chosen, parallel to items
    size_t found = 0;         // files found (before the kMax cap)
    bool more = false;        // found > kMax
};

inline bool parseInt(const std::string& s, int& out)
{
    if (s.empty() || s.size() > 6) return false;
    int v = 0;
    for (char c : s) { if (c < '0' || c > '9') return false; v = v * 10 + (c - '0'); }
    out = v;
    return true;
}
inline std::vector<std::string> split(const std::string& s, char sep)
{
    std::vector<std::string> out;
    size_t from = 0;
    for (;;) {
        const size_t at = s.find(sep, from);
        out.push_back(s.substr(from, at == std::string::npos ? std::string::npos : at - from));
        if (at == std::string::npos) return out;
        from = at + 1;
    }
}
// A name with at least one letter or digit (any non-ASCII byte counts).
inline bool wordy(const std::string& s)
{
    for (unsigned char c : s) if ((c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c >= 0x80) return true;
    return false;
}
// The page script's answer: one row per line, "tag\tw\th\tdl\tdownload\tmime\turl". Bad rows are skipped.
inline List parseRows(const std::string& text)
{
    List list;
    std::unordered_set<std::string> seen;
    size_t rows = 0;
    for (const std::string& line0 : split(text, '\n')) {
        if (++rows > kRawMax) break;
        std::string line = line0;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const auto f = split(line, '\t');
        if (f.size() != 7) continue;
        Raw r;
        r.tag = f[0];
        if (!parseInt(f[1], r.w) || !parseInt(f[2], r.h) || (f[3] != "0" && f[3] != "1")) continue;
        r.hasDownload = f[3] == "1";
        r.download = f[4];
        r.mime = f[5];
        r.url = stripFragment(f[6]);
        if (r.url.size() > kUrlMax || !OmniMediaSection::validLink(r.url)) continue;
        const Kind k = classify(r);
        if (k == None || !seen.insert(r.url).second) continue;
        ++list.found;
        if (list.items.size() >= kMax) { list.more = true; continue; }
        Candidate c;
        c.url = r.url;
        c.kind = k;
        c.name = r.hasDownload ? OmniSaveImage::safeName(r.download) : std::string();
        if (!wordy(c.name)) c.name = OmniSaveImage::fileName(r.url, "file");   // download="" / "../": the address's name
        list.items.push_back(std::move(c));
    }
    list.on.assign(list.items.size(), 0);
    return list;
}

// --- the selection -----------------------------------------------------------------------------------------------
inline size_t count(const List& l, int k) { size_t n = 0; for (const auto& c : l.items) n += c.kind == k; return n; }
inline size_t chosen(const List& l, int k)
{
    size_t n = 0;
    for (size_t i = 0; i < l.items.size(); ++i) n += l.items[i].kind == k && l.on[i];
    return n;
}
inline size_t chosen(const List& l) { size_t n = 0; for (char c : l.on) n += c != 0; return n; }
inline void toggle(List& l, size_t i) { if (i < l.on.size()) l.on[i] = !l.on[i]; }
// "Select all ..." of a group: all chosen -> none, else all.
inline void toggleGroup(List& l, int k)
{
    const bool all = chosen(l, k) == count(l, k);
    for (size_t i = 0; i < l.items.size(); ++i) if (l.items[i].kind == k) l.on[i] = !all;
}
inline void toggleAll(List& l)
{
    const bool all = chosen(l) == l.items.size();
    for (auto& c : l.on) c = !all;
}
inline std::string countValue(size_t picked, size_t n)
{
    if (picked == n && n) return "All " + std::to_string(n);
    if (!picked) return std::to_string(n) + " found";
    return std::to_string(picked) + " of " + std::to_string(n);
}
inline std::string groupLabel(int k) { return std::string("Select all ") + (k == Pdf ? "PDFs" : k == Other ? "other files" : k == Audio ? "audio files" : k == Video ? "video files" : k == Image ? "images" : "archives"); }

// --- the hand-over -----------------------------------------------------------------------------------------------
inline std::string jsonString(const std::string& s)
{
    static const char hex[] = "0123456789abcdef";
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += char(c); }
        else if (c < 0x20 || c == 0x7f) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
        else out += char(c);
    }
    return out + "\"";
}
// The #files= value (percent-encoded JSON {"v":1,"p":page,"u":[...]}) of the chosen links, in page order, while it
// stays within maxBytes. sent: how many links it holds.
inline std::string field(const List& l, const std::string& page, size_t& sent, size_t maxBytes = kFieldMax)
{
    sent = 0;
    std::string head = "{\"v\":1";
    if (page.size() <= kUrlMax && OmniMediaSection::validLink(page)) head += ",\"p\":" + jsonString(page);
    head += ",\"u\":[";
    std::string out = OmniMediaSection::encode(head);
    const std::string tail = OmniMediaSection::encode("]}");
    for (size_t i = 0; i < l.items.size(); ++i) {
        if (!l.on[i]) continue;
        const std::string piece = OmniMediaSection::encode((sent ? "," : "") + jsonString(l.items[i].url));
        if (out.size() + piece.size() + tail.size() > maxBytes) break;
        out += piece;
        ++sent;
    }
    return sent ? out + tail : std::string();
}

// Offered where a single "Save link target" would go to the Downloads app (and only on http(s) pages).
inline bool offered(const OmniSaveImage::Where& w)
{
    return !w.testMode && !w.privateTab && !w.downloadsTab && w.downloadsOn && w.validLink;
}

inline std::string files(size_t n) { return std::to_string(n) + (n == 1 ? " file" : " files"); }
inline std::string buttonLabel(size_t n) { return n ? "Download " + files(n) : std::string("Download files (choose below)"); }
inline std::string sentNotice(size_t sent, size_t picked)
{
    if (sent >= picked) return "Sent " + files(sent) + " to Downloads";
    return "Sent " + std::to_string(sent) + " of " + files(picked) + " to Downloads (the list was too long)";
}
inline std::string subtitle(const std::string& host, const List& l)
{
    std::string s = (host.empty() ? std::string() : host + ": ") + files(l.found) + " found";
    if (l.more) s += " (the first " + std::to_string(kMax) + " are listed)";
    return s;
}
inline const char* noneNotice() { return "No files to download were found on this page"; }

// The page script (one expression; returns the rows as text, "" on any error). Read-only: it only reads the DOM.
inline std::string script()
{
    std::string exts;
    for (const auto& x : kExt()) { if (!exts.empty()) exts += '|'; exts += x.ext; }
    std::string js = R"JS((function(){try{var d=document,out=[],seen={},n=0,MAXR=@RAW@,MAXU=@URL@,MIN=@MIN@;
var re=/\.(@EXT@)$/i,mt=/^\s*((image|audio|video)\/[a-z0-9.+-]+|application\/(pdf|zip|x-zip-compressed|x-7z-compressed|vnd\.rar|x-rar-compressed|x-rar|gzip|x-gzip|x-tar|x-bzip2|x-xz))\s*(;|$)/i;
function cl(s,m){return String(s==null?'':s).replace(/[\t\r\n]+/g,' ').slice(0,m);}
function ok(u){return typeof u==='string'&&/^https?:\/\//i.test(u)&&u.length<=MAXU;}
function ext(u){try{return re.test(new URL(u).pathname);}catch(_){return false;}}
function add(t,w,h,dl,dn,ty,u){if(n>=MAXR||!ok(u))return;var k=u.split('#')[0];if(seen[k]===1)return;seen[k]=1;n++;out.push(t+'\t'+(Math.max(0,Math.min(999999,w|0)))+'\t'+(Math.max(0,Math.min(999999,h|0)))+'\t'+(dl?1:0)+'\t'+cl(dn,200)+'\t'+cl(ty,100)+'\t'+u);}
var as=d.links||[];for(var i=0;i<as.length&&i<4000;i++){var a=as[i],u=a.href;if(!ok(u))continue;var dl=!!(a.hasAttribute&&a.hasAttribute('download')),ty=(a.getAttribute&&a.getAttribute('type'))||'';if(dl||ext(u)||mt.test(ty))add('a',0,0,dl,dl?a.getAttribute('download'):'',ty,u);}
var im=d.images||[];for(var j=0;j<im.length&&j<2000;j++){var g=im[j],s=g.currentSrc||g.src,w=g.naturalWidth||g.width||0,h=g.naturalHeight||g.height||0;if(s&&Math.max(w,h)>=MIN)add('img',w,h,false,'','',s);}
var ms=d.querySelectorAll?d.querySelectorAll('video,audio,video source,audio source'):[];for(var m=0;m<ms.length&&m<300;m++){var e=ms[m],src=e.tagName==='SOURCE'?e.src:(e.currentSrc||e.src),p=e.tagName==='SOURCE'?e.parentNode:e,t=p&&p.tagName==='AUDIO'?'audio':'video';if(src&&!/^blob:/i.test(src))add(t,0,0,false,'',(e.getAttribute&&e.getAttribute('type'))||'',src);}
return out.join('\n');}catch(err){return '';}})())JS";
    auto put = [&](const char* key, const std::string& value) {
        const size_t at = js.find(key);
        if (at != std::string::npos) js.replace(at, std::char_traits<char>::length(key), value);
    };
    put("@EXT@", exts);
    put("@RAW@", std::to_string(kRawMax));
    put("@URL@", std::to_string(kUrlMax));
    put("@MIN@", std::to_string(kMinImage));
    return js;
}

} // namespace OmniDownloadAll
'''

SHELL = r'''// OMNI_DOWNLOAD_ALL_V1: the page menu's "Download all..." (shell side). Included from OmniContextMenu.h before its menu
// section (inside OmniBrowser.cpp's anonymous namespace, after OmniMediaDownloadsHooks.inc). The pure part is
// OmniDownloadAll.h; the reasons are in tools/apply_download_all.py. Main thread only.
#pragma once
namespace ODAL = OmniDownloadAll;
constexpr int omniDalContextId = 995;   // hold-Cross page menu row (checked free in the tree by apply_download_all.py)
constexpr int omniDalPanelKind = 7540;
enum { omniDalRowGo = 1, omniDalRowAll = 2, omniDalRowGroup = 100, omniDalRowItem = 1000 };
static ODAL::List omniDalList;            // the open panel's files
static std::string omniDalPage;           // the page they came from
static const void* omniDalTab = nullptr;  // its tab
static uint32_t omniDalGen = 0;           // the newest page query (older answers are dropped)
static OmniSaveImage::Recent omniDalRecent;
struct OmniDalQuery { const void* tab; uint32_t gen; std::string page; };

static bool omniDalOffered(Tab* t)
{
    if (!t) return false;
    OmniSaveImage::Where w;
    w.privateTab = t->omniPrivate;
    w.downloadsTab = t->omniMediaSection;
    w.testMode = omniTestMode();
    w.downloadsOn = omniMediaDownloadsEnabled;
    w.validLink = OmniMediaSection::validLink(t->url);
    return ODAL::offered(w);
}
static void omniDalContextRow(OmniFxPanel& p)
{
    if (!omniDalOffered(active())) return;   // private tabs, Media downloads off, the Downloads tab: not offered
    OmniFxRow r; r.id = omniDalContextId; r.label = "Download all..."; p.rows.push_back(r);
}

static void omniDalSend()
{
    Tab* t = active();
    if (!omniDalOffered(t) || t != omniDalTab || t->url != omniDalPage) {
        omniFxCloseAll();
        notice("The page changed: open Download all again");
        return;
    }
    const size_t picked = ODAL::chosen(omniDalList);
    size_t sent = 0;
    const std::string field = ODAL::field(omniDalList, omniDalPage, sent);
    if (!picked || field.empty()) { notice("Choose files first: Cross selects a file or a whole group"); return; }
    const uint32_t now = SDL_GetTicks();
    if (omniDalRecent.repeat(field, now)) { omniFxCloseAll(); notice(ODAL::sentNotice(sent, picked)); return; }   // already handed over
    omniDalField = field;   // taken by omniMediaDownloadsTick when the worker answers
    omniMediaDownloadsRequest(false, false, false);
    if (status != "Opening Media downloads...") { omniDalField.clear(); return; }   // not accepted: its notice stays, retry allowed
    omniDalRecent.note(field, now);
    omniFxCloseAll();
    notice(ODAL::sentNotice(sent, picked));
}

static void omniDalBuild(OmniFxPanel& p)
{
    const ODAL::List& l = omniDalList;
    const size_t picked = ODAL::chosen(l);
    p.subtitle = ODAL::subtitle(ODAL::hostOf(omniDalPage), l);
    OmniFxRow go; go.id = omniDalRowGo; go.label = ODAL::buttonLabel(picked); go.enabled = picked > 0; go.icon = omniIconPlus;
    p.rows.push_back(go);
    OmniFxRow all; all.id = omniDalRowAll; all.label = "Select all files"; all.value = ODAL::countValue(picked, l.items.size());
    p.rows.push_back(all);
    for (int k = 0; k < ODAL::KindCount; ++k) {
        const size_t n = ODAL::count(l, k);
        if (!n) continue;
        OmniFxRow g; g.id = omniDalRowGroup + k; g.label = ODAL::groupLabel(k); g.value = ODAL::countValue(ODAL::chosen(l, k), n);
        p.rows.push_back(g);
        for (size_t i = 0; i < l.items.size(); ++i) {
            if (l.items[i].kind != k) continue;
            OmniFxRow r;
            r.id = omniDalRowItem + int(i);
            r.prefix = "  ";
            r.label = OmniSaveImage::shown(l.items[i].name);
            r.detail = ODAL::hostOf(l.items[i].url);
            r.value = l.on[i] ? "\xe2\x9c\x93" : "";
            p.rows.push_back(r);
        }
    }
}
static bool omniDalInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (r.id == omniDalRowGo) {
        if (!r.enabled) notice("Choose files first: Cross selects a file or a whole group");
        else omniDalSend();
        return true;
    }
    if (r.id == omniDalRowAll) { ODAL::toggleAll(omniDalList); return true; }
    if (r.id >= omniDalRowItem) { ODAL::toggle(omniDalList, size_t(r.id - omniDalRowItem)); return true; }
    if (r.id >= omniDalRowGroup && r.id < omniDalRowGroup + int(ODAL::KindCount)) { ODAL::toggleGroup(omniDalList, r.id - omniDalRowGroup); return true; }
    return false;
}
static void omniDalShow(ODAL::List list, const void* tab, const std::string& page)
{
    if (list.items.empty()) { notice(ODAL::noneNotice()); return; }
    if (editing || settingsOpen || pageFullscreen || omniOverlayOpen() || !omniFxStack.empty()) return;   // something else opened meanwhile
    omniDalList = std::move(list);
    omniDalTab = tab;
    omniDalPage = page;
    OmniFxPanel p;
    p.kind = omniDalPanelKind;
    p.title = "Download all";
    p.w = 940; p.maxVisible = 9;
    p.build = omniDalBuild; p.input = omniDalInput;
    p.faces = { { 0, "Select" }, { 1, "Back" } };
    p.extra = "L1 / R1 page";
    omniFxPush(std::move(p));
}
// Cross on "Download all...": the read-only page script lists the page's files; the panel opens with its answer.
static void omniDalStart()
{
    Tab* t = active();
    omniFxCloseAll();
    if (!omniDalOffered(t) || t->crashed) return;
    static const std::string js = ODAL::script();
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    auto* q = new OmniDalQuery { t, ++omniDalGen, t->url };
    notice("Looking for files on this page...");
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), q, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniDalQuery> q(static_cast<OmniDalQuery*>(context));
        if (q->gen != omniDalGen || !omniTabAlive(q->tab) || active() != q->tab) return;
        Tab* now = active();
        if (!omniDalOffered(now) || now->url != q->page) return;   // went private / elsewhere meanwhile: nothing shown
        omniDalShow(ODAL::parseRows(omniFxResultString(result, error)), q->tab, q->page);
    });
}
static bool omniDalContextAction(int id)
{
    if (id != omniDalContextId) return false;
    omniDalStart();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSaveImage.h" // OMNI_SAVE_IMAGE_V1: page menu Save image / Save link target -> Downloads (pure)\n',
         '#include "OmniSaveImage.h" // OMNI_SAVE_IMAGE_V1: page menu Save image / Save link target -> Downloads (pure)\n'
         '#include "OmniDownloadAll.h" /* ' + MARK + ': page menu Download all... -> Downloads (pure) */\n'),
    ],
    'OmniMediaDownloadsHooks.inc': [
        ('static std::string omniMediaCandidatePage; // OMNI_NET_GRABBER_V1: source page of a wire sent to the form view\n',
         'static std::string omniMediaCandidatePage; // OMNI_NET_GRABBER_V1: source page of a wire sent to the form view\n'
         'static std::string omniDalField; /* ' + MARK + ': the encoded #files= list of an accepted "Download all..." */\n'),
        ('    omniMediaCandidatePage.clear();\n',
         '    omniMediaCandidatePage.clear();\n'
         '    const std::string dalField = std::move(omniDalField); /* ' + MARK + ': this answer\'s file list, if any */\n'
         '    omniDalField.clear();\n'),
        ('    omniDlpHandedOver(); // OMNI_DL_PROGRESS_V1: the Downloads tab opens: watch for jobs (top-bar progress)\n',
         '    if (!dalField.empty() && (plan.action == OmniMediaSection::Action::Create || plan.action == OmniMediaSection::Action::Activate))\n'
         '        plan.url = OmniMediaSection::base(completion.port) + "#files=" + dalField; /* ' + MARK + ': the list, no prefill */\n'
         '    omniDlpHandedOver(); // OMNI_DL_PROGRESS_V1: the Downloads tab opens: watch for jobs (top-bar progress)\n'),
    ],
    'OmniContextMenu.h': [
        ('// --- the menu --------------------------------------------------------------------------------------\n',
         '#include "OmniDownloadAllShell.h" /* ' + MARK + ': Download all... (row, panel, hand-over) */\n'
         '// --- the menu --------------------------------------------------------------------------------------\n'),
        ('        omniRlContextRows(p); // OMNI_READING_LIST_V1: Save page for later\n',
         '        omniRlContextRows(p); // OMNI_READING_LIST_V1: Save page for later\n'
         '        omniDalContextRow(p); /* ' + MARK + ': Download all... */\n'),
        ('    if (omniTslContextAction(p, r.id)) return true; // OMNI_TEXT_SELECT_V1\n',
         '    if (omniTslContextAction(p, r.id)) return true; // OMNI_TEXT_SELECT_V1\n'
         '    if (omniDalContextAction(r.id)) return true; /* ' + MARK + ' */\n'),
    ],
    'OmniControlsHelp.h': [
        ('    { kDownloads, { gCross }, 0, true, "Save link target / Save image", "Page menu; to Downloads when Media downloads is on", "omniFxContextInput omniCxSaveLink / omniCxSaveImage omniSviSave" }, /* OMNI_SAVE_IMAGE_V1 */\n',
         '    { kDownloads, { gCross }, 0, true, "Save link target / Save image", "Page menu; to Downloads when Media downloads is on", "omniFxContextInput omniCxSaveLink / omniCxSaveImage omniSviSave" }, /* OMNI_SAVE_IMAGE_V1 */\n'
         '    { kDownloads, { gCross }, 0, true, "Download all...", "Page menu: pick PDFs, images, audio, video, archives; to Downloads", "omniDalContextAction (' + MARK + ')" },\n'),
    ],
}


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


# Copied from apply_bf_list.py: comment-free code, so an id or name in another patch's notes is not a use.
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept)."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before a first apply: numeric ids against the engine tree's code only; names against tree and sibling code."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        m = name.search(code_only(f.read_text(encoding='utf-8', errors='replace')))
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in MINE or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        m = word.search(cpp_code(t)) or name.search(cpp_code(t))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    if 'OMNI_SAVE_IMAGE_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8') or not (root / 'OmniSaveImage.h').exists():
        sys.exit('OmniBrowser.cpp: OMNI_SAVE_IMAGE_V1 missing: apply_save_image.py first')
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniDownloadAll.h', PURE, 'OmniSaveImage.h'), write_new('OmniDownloadAllShell.h', SHELL, 'OmniSaveImage.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
