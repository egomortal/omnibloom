// OMNI_DL_PANEL_V1: the pure part of Options > More > "Downloaded files" (no SDL, no WebKit): the Downloads app's
// Library read straight from its console save root (<downloads folder>/Saved, files_library.py roots()), newest first,
// at most kMaxList files: the folder walk (files_library.py _scan's rules: no hidden names, no links, depth, entry
// budget), file kinds (files_library.py KINDS), what Cross opens, the Library trash path, the list selection, the
// script the Downloads app's player page runs to find the file's Library id, and the texts.
// Shell side: OmniDlPanelShell.h; reasons in tools/apply_dl_panel.py. Tests: tools/test_dl_panel.cpp (g++).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace OmniDlPanel {

constexpr int kTile = 468;                 // Options tile id (More; Screenshots 467)
constexpr size_t kMaxList = 500;           // newest files shown
constexpr int kMaxScan = 20000;            // directory entries looked at per listing (files_library.py MAX_SCAN)
constexpr int kMaxDepth = 8;               // folders below the root (files_library.py MAX_DEPTH)
constexpr int kTrashMax = 999;             // "name (999).ext" (files_library.py _free)
constexpr int kMaxLibraryOffset = 5000;    // the player page looks at most this far into the Library listing
static const char* const kTrash = ".trash";
static const char* const kShotFolder = "Screenshots";   // OmniQuickActions::kShotDir's last part

// --- names ---------------------------------------------------------------------------------------------------------
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline std::string lowerStr(std::string s) { for (char& c : s) c = lower(c); return s; }
inline bool endsNoCase(const std::string& s, const char* e)
{
    const std::string x = e;
    return s.size() >= x.size() && lowerStr(s.substr(s.size() - x.size())) == lowerStr(x);
}
// os.path.splitext's extension, lower case: from the last '.', leading dots of the name don't count ("" when none).
inline std::string extOf(const std::string& name)
{
    const size_t dot = name.rfind('.');
    if (dot == std::string::npos) return std::string();
    const size_t first = name.find_first_not_of('.');
    if (first == std::string::npos || dot < first) return std::string();
    return lowerStr(name.substr(dot));
}
inline bool validUtf8(const std::string& s)
{
    for (size_t i = 0; i < s.size();) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        size_t n = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : (c >> 3) == 30 ? 4 : 0;
        if (!n || i + n > s.size()) return false;
        uint32_t cp = n == 1 ? c : n == 2 ? (c & 0x1f) : n == 3 ? (c & 0x0f) : (c & 0x07);
        for (size_t k = 1; k < n; ++k) {
            const unsigned char d = static_cast<unsigned char>(s[i + k]);
            if ((d >> 6) != 2) return false;
            cp = (cp << 6) | (d & 0x3f);
        }
        if ((n == 2 && cp < 0x80) || (n == 3 && cp < 0x800) || (n == 4 && (cp < 0x10000 || cp > 0x10ffff)) || (cp >= 0xd800 && cp <= 0xdfff))
            return false;
        i += n;
    }
    return true;
}
// A name the walk looks at: not hidden (files_library.py: names starting with '.' are skipped), no separator.
inline bool plainName(const std::string& n)
{
    return !n.empty() && n[0] != '.' && n.find('/') == std::string::npos && n.find('\\') == std::string::npos && n.find('\0') == std::string::npos;
}
// A relative path the Library would serve (files_library.py _plain_parts): plain parts only.
inline bool plainRel(const std::string& rel)
{
    if (rel.empty()) return false;
    size_t at = 0;
    for (;;) {
        const size_t slash = rel.find('/', at);
        if (!plainName(rel.substr(at, slash == std::string::npos ? std::string::npos : slash - at))) return false;
        if (slash == std::string::npos) return true;
        at = slash + 1;
    }
}
// A download that is not finished yet (yt-dlp / aria2 / browser part files): left out of the list.
inline bool partial(const std::string& name)
{
    static const char* const parts[] = { ".part", ".ytdl", ".tmp", ".temp", ".crdownload", ".download", ".aria2", ".partial" };
    for (const char* p : parts) if (endsNoCase(name, p)) return true;
    return lowerStr(name).find(".part-frag") != std::string::npos;
}
inline std::string folderOf(const std::string& rel) { const size_t s = rel.rfind('/'); return s == std::string::npos ? std::string() : rel.substr(0, s); }
inline std::string nameOf(const std::string& rel) { const size_t s = rel.rfind('/'); return s == std::string::npos ? rel : rel.substr(s + 1); }

// --- kinds (files_library.py KINDS) ----------------------------------------------------------------------------------
enum class Kind { Video, Audio, Image, Pdf, Text, Other };
inline Kind kindOf(const std::string& name)
{
    const std::string e = extOf(name);
    static const char* const video[] = { ".mp4", ".m4v", ".webm", ".mkv", ".mov", ".ts", ".ogv" };
    static const char* const audio[] = { ".m4a", ".mp3", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wav", ".weba" };
    static const char* const image[] = { ".png", ".jpg", ".jpeg", ".gif", ".webp" };
    static const char* const text[] = { ".txt", ".vtt", ".srt" };
    for (const char* x : video) if (e == x) return Kind::Video;
    for (const char* x : audio) if (e == x) return Kind::Audio;
    for (const char* x : image) if (e == x) return Kind::Image;
    if (e == ".pdf") return Kind::Pdf;
    for (const char* x : text) if (e == x) return Kind::Text;
    return Kind::Other;
}
inline const char* kindLabel(Kind k)
{
    switch (k) {
    case Kind::Video: return "Video";
    case Kind::Audio: return "Audio";
    case Kind::Image: return "Picture";
    case Kind::Pdf: return "PDF";
    case Kind::Text: return "Text";
    default: return "File";
    }
}

// --- what Cross opens ------------------------------------------------------------------------------------------------
enum class Route {
    Player,        // video / audio: the Downloads app's player page (/player#id=<Library id>) in a new tab
    PdfReader,     // Omni's PDF reader (omni://pages/pdf/), the file read into memory under a token
    Gallery,       // a PNG in Saved/Screenshots: the screenshot gallery's full-screen view
    ImageViewer,   // other pictures: Omni's image viewer over the player page, on the Library's signed stream link
    Library        // anything else: the Downloads app's Library
};
inline Route routeFor(Kind k, const std::string& rel)
{
    const std::string name = nameOf(rel), folder = folderOf(rel);
    // the player page finds the file by name in the Library's JSON listing: names that aren't UTF-8 can't be matched
    const bool findable = validUtf8(rel);
    switch (k) {
    case Kind::Video: case Kind::Audio: return findable ? Route::Player : Route::Library;
    case Kind::Pdf: return Route::PdfReader;
    case Kind::Image:
        if (folder == kShotFolder && extOf(name) == ".png") return Route::Gallery;
        return findable ? Route::ImageViewer : Route::Library;
    default: return Route::Library;
    }
}
inline bool needsWorker(Route r) { return r == Route::Player || r == Route::ImageViewer || r == Route::Library; }

// --- the folder walk (files_library.py Library._scan) ------------------------------------------------------------------
enum class Type { Other, File, Dir, Link };
struct DirEnt { std::string name; Type type = Type::Other; uint64_t size = 0; int64_t mtime = 0; };
struct Entry { std::string rel; uint64_t size = 0; int64_t mtime = 0; };
struct Scan { std::vector<Entry> files; bool truncated = false; };
// readDir(relDir, out, budget): the entries of <root>/<relDir> ("" = the root), at most `budget`; false when it can't
// be opened (skipped, as an OSError there). Depth-first like _scan (a stack: the last folder found is read next).
template <class ReadDir>
inline Scan scan(ReadDir readDir)
{
    Scan r;
    int budget = kMaxScan;
    struct Todo { std::string prefix; int depth; };
    std::vector<Todo> stack { { std::string(), 0 } };
    std::vector<DirEnt> ents;
    while (!stack.empty() && budget > 0) {
        const Todo t = stack.back();
        stack.pop_back();
        ents.clear();
        if (!readDir(t.prefix.empty() ? std::string() : t.prefix.substr(0, t.prefix.size() - 1), ents, size_t(budget))) continue;
        for (const DirEnt& e : ents) {
            if (--budget <= 0) break;
            if (!plainName(e.name) || e.type == Type::Link) continue;
            const std::string rel = t.prefix + e.name;
            if (e.type == Type::Dir) { if (t.depth + 1 < kMaxDepth) stack.push_back({ rel + "/", t.depth + 1 }); }
            else if (e.type == Type::File) r.files.push_back({ rel, e.size, e.mtime });
        }
    }
    r.truncated = budget <= 0;
    return r;
}

// --- the list ----------------------------------------------------------------------------------------------------------
struct Item {
    std::string rel, name, folder;
    Kind kind = Kind::Other;
    uint64_t size = 0;
    int64_t mtime = 0;
};
struct Listing { std::vector<Item> items; size_t total = 0; bool truncated = false; };
// Newest first (then by name, as the Library), unfinished downloads left out, at most kMaxList.
inline Listing list(const Scan& s)
{
    Listing out;
    out.truncated = s.truncated;
    for (const Entry& e : s.files) {
        if (!plainRel(e.rel)) continue;
        Item it;
        it.rel = e.rel; it.name = nameOf(e.rel); it.folder = folderOf(e.rel);
        if (partial(it.name)) continue;
        it.kind = kindOf(it.name); it.size = e.size; it.mtime = e.mtime;
        out.items.push_back(std::move(it));
    }
    std::sort(out.items.begin(), out.items.end(), [](const Item& a, const Item& b) {
        if (a.mtime != b.mtime) return a.mtime > b.mtime;
        if (a.name != b.name) return a.name < b.name;
        return a.rel < b.rel;
    });
    out.total = out.items.size();
    if (out.items.size() > kMaxList) out.items.resize(kMaxList);
    return out;
}
inline int indexOf(const std::vector<Item>& items, const std::string& rel)
{
    for (size_t i = 0; i < items.size(); ++i) if (items[i].rel == rel) return int(i);
    return -1;
}

// --- selection (D-pad one row, L1 / R1 one page, kept on screen) ----------------------------------------------------------
struct Sel {
    int count = 0, sel = 0, scroll = 0;
    void clamp(int vis)
    {
        sel = count > 0 ? std::clamp(sel, 0, count - 1) : 0;
        if (vis < 1) vis = 1;
        if (sel < scroll) scroll = sel;
        if (sel >= scroll + vis) scroll = sel - vis + 1;
        scroll = std::clamp(scroll, 0, std::max(0, count - vis));
    }
    bool move(int d, int vis) { const int was = sel; sel += d; clamp(vis); return sel != was; }
    bool page(int d, int vis) { return move(d * std::max(1, vis), vis); }
};

// --- Square: into the Library's trash (files_library.py trash(): <root>/.trash mirrors the root) ---------------------------
// The folders to make, root-relative, outermost first: ".trash", ".trash/a", ".trash/a/b" for "a/b/x.mp4".
inline std::vector<std::string> trashDirs(const std::string& rel)
{
    std::vector<std::string> out { kTrash };
    const std::string folder = folderOf(rel);
    size_t at = 0;
    while (!folder.empty()) {
        const size_t slash = folder.find('/', at);
        out.push_back(std::string(kTrash) + "/" + folder.substr(0, slash));
        if (slash == std::string::npos) break;
        at = slash + 1;
    }
    return out;
}
// The path prefixes from the root down to the file ("a", "a/b", "a/b/x.mp4"): none may be a link when it moves.
inline std::vector<std::string> chain(const std::string& rel)
{
    std::vector<std::string> out;
    for (size_t at = 0;;) {
        const size_t slash = rel.find('/', at);
        out.push_back(rel.substr(0, slash));
        if (slash == std::string::npos) return out;
        at = slash + 1;
    }
}

// --- the player page (the Downloads app's /player, which holds its session token in a meta tag) -------------------------
inline std::string origin(unsigned port) { return port >= 8761 && port <= 8899 ? "http://127.0.0.1:" + std::to_string(port) : std::string(); }
inline std::string playerURL(unsigned port) { const std::string o = origin(port); return o.empty() ? o : o + "/player"; }
inline std::string libraryURL(unsigned port) { const std::string o = origin(port); return o.empty() ? o : o + "/downloads#view=files"; }
inline bool isPlayerURL(const std::string& url, unsigned port)
{
    const std::string p = playerURL(port);
    return !p.empty() && url.compare(0, p.size(), p) == 0 && (url.size() == p.size() || url[p.size()] == '#' || url[p.size()] == '?');
}
// A JavaScript / JSON string literal that is safe inside a script: quotes, backslashes, control characters, <, >, &,
// U+2028 / U+2029 escaped. UTF-8 is kept as it is (the caller checks validUtf8).
inline std::string jsQuote(const std::string& s)
{
    static const char* hex = "0123456789abcdef";
    std::string o = "\"";
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c == '"') o += "\\\"";
        else if (c == '\\') o += "\\\\";
        else if (c == '\n') o += "\\n";
        else if (c == '\r') o += "\\r";
        else if (c == '\t') o += "\\t";
        else if (c < 0x20 || c == 0x7f || c == '<' || c == '>' || c == '&') { o += "\\u00"; o += hex[c >> 4]; o += hex[c & 15]; }
        else if (c == 0xe2 && i + 2 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0x80
                 && (static_cast<unsigned char>(s[i + 2]) == 0xa8 || static_cast<unsigned char>(s[i + 2]) == 0xa9)) {
            o += static_cast<unsigned char>(s[i + 2]) == 0xa8 ? "\\u2028" : "\\u2029";
            i += 2;
        } else o += char(c);
    }
    return o + "\"";
}
// Runs on the player page: finds the file in the Library listing (console storage, same folder and name; newest first,
// 100 a page, at most kMaxLibraryOffset) with the page's own token, then
//   play:  /player#id=<id> and a reload (the player starts that file);
//   image: asks /api/files/link for a signed stream link and leaves {state:"ok", src} in window.__omniDlpn.
// State "gone" / "error" otherwise. Nothing is sent anywhere but the page's own origin.
inline std::string resolveScript(const std::string& name, const std::string& folder, bool play)
{
    return "(function(){var N=" + jsQuote(name) + ",F=" + jsQuote(folder) + ",P=" + (play ? "true" : "false") + ",W=window;"
        "if(W.__omniDlpn&&W.__omniDlpn.state==='busy')return 'busy';W.__omniDlpn={state:'busy',src:''};"
        "var m=document.querySelector('meta[name=\"omni-session-token\"]'),T=m?m.content:'';"
        "function done(s,u){W.__omniDlpn={state:s,src:u||''};}"
        "function say(x){var e=document.getElementById('message');if(e)e.textContent=x;var h=document.getElementById('title');if(h)h.textContent=N;document.title=N;}"
        "function list(o){return fetch('/api/files?kind=all&area=files&offset='+o+'&limit=100',{headers:{'X-Omni-Token':T},cache:'no-store',credentials:'same-origin',redirect:'error'})"
        ".then(function(r){if(!r.ok)throw new Error('list');return r.json();});}"
        "function find(o){return list(o).then(function(v){var f=v&&Array.isArray(v.files)?v.files:[];"
        "for(var i=0;i<f.length;i++){var x=f[i];if(x&&x.place==='internal'&&x.name===N&&x.folder===F&&/^[0-9a-f]{32}$/.test(x.id))return x.id;}"
        "o+=f.length;if(f.length&&o<(+v.total||0)&&o<" + std::to_string(kMaxLibraryOffset) + ")return find(o);return '';});}"
        "say('Opening\\u2026');"
        "find(0).then(function(id){if(!id){say('This file is no longer in the Downloads library.');done('gone');return;}"
        "if(P){done('ok');location.hash='#id='+id;location.reload();return;}"
        "return fetch('/api/files/link',{method:'POST',headers:{'X-Omni-Token':T,'Content-Type':'application/json'},body:JSON.stringify({id:id}),cache:'no-store',credentials:'same-origin',redirect:'error'})"
        ".then(function(r){return r.json().then(function(v){"
        "if(!r.ok||!v||typeof v.url!=='string'||!/^\\/api\\/files\\/stream\\?id=[a-f0-9]{32}&exp=\\d+&sig=[a-f0-9]{64}$/.test(v.url))throw new Error('link');"
        "say('');done('ok',location.origin+v.url);});});"
        "}).catch(function(){say('The Downloads app could not open this file.');done('error');});return 'started';})()";
}
inline std::string pollScript() { return "JSON.stringify(window.__omniDlpn||{state:'none',src:''})"; }
// The image link the page handed back must be this worker's own stream route.
inline bool streamLinkOk(const std::string& src, unsigned port)
{
    const std::string o = origin(port) + "/api/files/stream?id=";
    if (o.size() < 30 || src.compare(0, o.size(), o) != 0 || src.size() > 300) return false;
    for (unsigned char c : src) if (c <= 0x20 || c >= 0x7f || c == '"' || c == '\'' || c == '\\' || c == '<' || c == '>') return false;
    return true;
}

// --- texts -------------------------------------------------------------------------------------------------------------
inline std::string sizeText(uint64_t b)
{
    char s[32];
    if (b >= 1073741824ull) snprintf(s, sizeof s, "%.2f GB", double(b) / 1073741824.0);
    else if (b >= 1048576ull) snprintf(s, sizeof s, "%.1f MB", double(b) / 1048576.0);
    else snprintf(s, sizeof s, "%llu KB", (unsigned long long)((b + 1023) / 1024));
    return s;
}
// "Video · 1.4 GB · 16 Nov 2026, 14:03 · in Music/Live"
inline std::string detail(const Item& it, const std::string& when)
{
    std::string d = std::string(kindLabel(it.kind)) + " \xc2\xb7 " + sizeText(it.size);
    if (!when.empty()) d += " \xc2\xb7 " + when;
    if (!it.folder.empty()) d += " \xc2\xb7 in " + it.folder;
    return d;
}
inline std::string corner(const Listing& l, bool loading)
{
    if (loading && l.items.empty()) return "Loading\xe2\x80\xa6";
    std::string s = l.total == 1 ? std::string("1 file") : std::to_string(l.total) + " files";
    if (l.total > l.items.size()) s = "Newest " + std::to_string(l.items.size()) + " of " + std::to_string(l.total);
    if (l.truncated) s += "+";
    return s;
}
inline const char* title() { return "Downloaded files"; }
inline const char* subtitle(bool privateTab)
{
    return privateTab ? "Private tab: these are the Downloads app's shared files (not private). They open in a normal tab."
                      : "The Downloads app's Library, newest first";
}
inline const char* emptyTitle() { return "Nothing downloaded yet"; }
inline const char* emptyBody() { return "Files the Downloads app saves to the console show up here."; }
inline const char* actionHint(Route r)
{
    switch (r) {
    case Route::Player: return "Play";
    case Route::PdfReader: case Route::Gallery: case Route::ImageViewer: return "View";
    default: return "Open in Downloads";
    }
}
inline const char* askTitle() { return "Move this file to the trash?"; }
inline std::string askBody(const Item& it)
{
    return it.name + " (" + sizeText(it.size) + "). It moves to the Downloads trash, where the Downloads app can restore it or delete it for good.";
}

} // namespace OmniDlPanel
