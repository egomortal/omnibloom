#!/usr/bin/env python3
"""OMNI_BOOKMARKS_MANAGER_V1 (2026-11-16): a controller-first bookmarks manager with folders.

What existed (OMNI_FEATURES_V1, OmniBookmarks.h): /data/omni/bookmarks.txt ("url TAB title" per line, at most 500),
the address-bar star (OmniAddressStar.h), Options > Bookmark page / Bookmarks, the context menu's Bookmark link, and
one manager panel for bookmarks + the 19 new-tab shortcuts (Cross open, Square delete at once, Triangle rename,
L1/R1 reorder, D-pad right new tab). The Setup's PC import (setup/omnibloom_setup/bookmarks.py) flattens the PC's
folders (it keeps no folder field) and appends "url TAB title" lines after the existing bytes.

What this adds (bookmarks list only; the Shortcuts view keeps its old rows):
  Rows: Showing (Bookmarks / Shortcuts), "Add current page", "Search" (title or site; Square clears it), then
  folders ("> Name", count; Cross / D-pad right opens, Cross / D-pad left closes) with their bookmarks indented
  below when open, then bookmarks without a folder. While a search is set the list is flat: matching bookmarks,
  each with its folder named.
  Bookmark: Cross opens, D-pad right opens in a new tab, Square deletes (asks once), Triangle edits (Name via the
  on-screen keyboard; Folder: No folder / a folder / New folder...), L1/R1 move it up / down inside its folder.
  Folder: Square deletes it with its bookmarks (asks once, counts them), Triangle renames it (same name as another
  folder: they merge), L1/R1 move the folder up / down. Shortcuts: Square now asks once too.
  Private tabs: unchanged rule ("Add current page" goes through omniFxBookmarkAdd like the star and Options).

File format (backward compatible): a bookmark in a folder gets an optional third tab-separated column:
      url TAB title TAB folder
  Bookmarks without a folder are written exactly as before (so a file without folders stays byte-identical). The
  reader still mirrors fgets(2400) line splitting and the 500 cap; columns past the third are ignored. Older Omni
  reads such a line with "title TAB folder" as the title (it shows the folder after the title and drops the folder
  when it next saves); the Setup importer only reads the address (before the first tab), so its de-duplication and
  append are unaffected. Folder names: one line, at most 40 bytes, so a line stays <= 2048+1+300+1+40+1 < 2399.

Files: OmniBookmarksModel.h (new, pure: parse/serialize, folders, reorder, filter, view rows),
       OmniBookmarksShell.h (new, shell: panel rows + input), included from OmniBookmarks.h just before
       omniFxBookmarksShow (so it needs nothing from OmniFeatures3.h and stays clear of other helpers' anchors).
Edits: OmniBrowser.cpp (pure include after OmniTabSessions.h), OmniBookmarks.h (load/save; Show).
Panel kinds 7460-7462 (unused). Writes go through omniIoQueue as before.

usage: apply_bookmarks_manager.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_BOOKMARKS_MANAGER_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_BOOKMARKS_MANAGER_V1: the pure part of the bookmarks manager (no SDL, no WebKit, no I/O).
// bookmarks.txt: one bookmark per line, "url TAB title" (OMNI_FEATURES_V1, also written by the Setup's PC import),
// plus an optional third column "TAB folder" for a bookmark in a folder (one level). Columns past the third are
// ignored. Lines are read the way the first loader read them (fgets with a 2400-byte buffer: a longer line counts as
// several; the first 500 entries), which is also how the Setup counts them.
#pragma once
#include <algorithm>
#include <cstddef>
#include <string>
#include <vector>

namespace OmniBookmarksModel {

constexpr std::size_t kMax = 500, kLineBuffer = 2400, kUrlMax = 2048, kTitleMax = 300, kFolderMax = 40;

struct Entry {
    std::string url, title, folder;   // folder "": not in a folder
    bool operator==(const Entry& o) const { return url == o.url && title == o.title && folder == o.folder; }
};

// omniOneLine: tabs and line breaks become spaces, cut at `max` bytes on a UTF-8 character boundary.
inline std::string oneLine(std::string s, std::size_t max)
{
    for (auto& c : s) if (c == '\t' || c == '\n' || c == '\r') c = ' ';
    if (s.size() > max) {
        std::size_t cut = max;
        while (cut && (static_cast<unsigned char>(s[cut]) & 0xc0) == 0x80) --cut;
        s.resize(cut);
    }
    return s;
}
inline std::string trim(const std::string& s)
{
    std::size_t a = 0, b = s.size();
    while (a < b && static_cast<unsigned char>(s[a]) <= ' ') ++a;
    while (b > a && static_cast<unsigned char>(s[b - 1]) <= ' ') --b;
    return s.substr(a, b - a);
}
// A folder name as stored: one line, control characters out, runs of spaces folded, trimmed, <= kFolderMax bytes.
inline std::string cleanFolder(const std::string& name)
{
    std::string s;
    bool space = false;
    for (char c : name) {
        if (static_cast<unsigned char>(c) <= ' ' || c == 0x7f) { space = true; continue; }
        if (space && !s.empty()) s += ' ';
        space = false;
        s += c;
    }
    return trim(oneLine(s, kFolderMax));
}

inline std::vector<Entry> parse(const std::string& data, std::size_t max = kMax)
{
    std::vector<Entry> out;
    const std::size_t n = data.size(), chunk = kLineBuffer - 1;
    std::size_t i = 0;
    while (i < n && out.size() < max) {
        const std::size_t nl = data.find('\n', i);
        const std::size_t stop = nl != std::string::npos && nl < i + chunk ? nl + 1 : std::min(i + chunk, n);
        std::string line = data.substr(i, stop - i);
        i = stop;
        const std::size_t nul = line.find('\0');
        if (nul != std::string::npos) line.resize(nul);
        while (!line.empty() && (line.back() == '\n' || line.back() == '\r')) line.pop_back();
        const std::size_t t1 = line.find('\t');
        Entry e;
        e.url = line.substr(0, t1);
        if (e.url.empty()) continue;
        if (t1 != std::string::npos) {
            const std::size_t t2 = line.find('\t', t1 + 1);
            e.title = line.substr(t1 + 1, t2 == std::string::npos ? std::string::npos : t2 - t1 - 1);
            if (t2 != std::string::npos) {
                const std::size_t t3 = line.find('\t', t2 + 1);
                e.folder = cleanFolder(line.substr(t2 + 1, t3 == std::string::npos ? std::string::npos : t3 - t2 - 1));
            }
        }
        if (e.title.empty()) e.title = e.url;
        out.push_back(std::move(e));
    }
    return out;
}
inline std::string serializeLine(const Entry& e)
{
    std::string s = oneLine(e.url, kUrlMax) + "\t" + oneLine(e.title, kTitleMax);
    const std::string f = cleanFolder(e.folder);
    if (!f.empty()) s += "\t" + f;
    return s + "\n";
}
inline std::string serialize(const std::vector<Entry>& list)
{
    std::string s;
    for (const auto& e : list) s += serializeLine(e);
    return s;
}

// --- folders (one level) ------------------------------------------------------------------------------------------
inline std::vector<std::string> folders(const std::vector<Entry>& list)   // in order of first appearance
{
    std::vector<std::string> out;
    for (const auto& e : list)
        if (!e.folder.empty() && std::find(out.begin(), out.end(), e.folder) == out.end()) out.push_back(e.folder);
    return out;
}
inline int folderCount(const std::vector<Entry>& list, const std::string& folder)
{
    int n = 0;
    for (const auto& e : list) n += e.folder == folder;
    return n;
}
// Stable: each folder's bookmarks together, folders in order of first appearance, then the bookmarks in no folder.
// Bookmarks grouped by `order` (folders not in it, and no folder, go last), stable inside each group.
inline void groupBy(std::vector<Entry>& list, const std::vector<std::string>& order)
{
    auto rank = [&](const Entry& e) {
        const auto it = std::find(order.begin(), order.end(), e.folder);
        return e.folder.empty() || it == order.end() ? order.size() : std::size_t(it - order.begin());
    };
    std::stable_sort(list.begin(), list.end(), [&](const Entry& a, const Entry& b) { return rank(a) < rank(b); });
}
inline void normalize(std::vector<Entry>& list) { groupBy(list, folders(list)); }
// Swap bookmark `index` with the previous / next bookmark of the same folder. Returns its new index, -1: no move.
inline int moveEntry(std::vector<Entry>& list, int index, int delta)
{
    if (index < 0 || index >= int(list.size()) || !delta) return -1;
    const std::string& f = list[size_t(index)].folder;
    for (int j = index + (delta < 0 ? -1 : 1); j >= 0 && j < int(list.size()); j += delta < 0 ? -1 : 1) {
        if (list[size_t(j)].folder != f) continue;
        std::swap(list[size_t(index)], list[size_t(j)]);
        return j;
    }
    return -1;
}
inline bool moveFolder(std::vector<Entry>& list, const std::string& folder, int delta)
{
    auto order = folders(list);
    const auto it = std::find(order.begin(), order.end(), folder);
    if (it == order.end() || !delta) return false;
    const int i = int(it - order.begin()), j = i + (delta < 0 ? -1 : 1);
    if (j < 0 || j >= int(order.size())) return false;
    std::swap(order[size_t(i)], order[size_t(j)]);
    groupBy(list, order);
    return true;
}
// Put the bookmark with this address in `folder` ("" none), last in it; a new folder comes after the others.
// The list is normalized first. Returns the bookmark's new index, -1 when the address is not in the list.
inline int setFolderAt(std::vector<Entry>& list, const std::string& url, const std::string& folder)
{
    normalize(list);
    int index = -1;
    for (int i = 0; i < int(list.size()); ++i) if (list[size_t(i)].url == url) { index = i; break; }
    if (index < 0) return -1;
    Entry e = std::move(list[size_t(index)]);
    list.erase(list.begin() + index);
    e.folder = cleanFolder(folder);
    std::size_t at = list.size();
    if (!e.folder.empty()) {
        int last = -1, firstRoot = -1;
        for (int i = 0; i < int(list.size()); ++i) {
            if (list[size_t(i)].folder == e.folder) last = i;
            if (firstRoot < 0 && list[size_t(i)].folder.empty()) firstRoot = i;
        }
        at = last >= 0 ? size_t(last + 1) : firstRoot >= 0 ? size_t(firstRoot) : list.size();
    }
    list.insert(list.begin() + std::ptrdiff_t(at), std::move(e));
    return int(at);
}
inline bool renameFolder(std::vector<Entry>& list, const std::string& from, const std::string& to)
{
    const std::string name = cleanFolder(to);
    if (from.empty() || name.empty()) return false;
    bool any = false;
    for (auto& e : list) if (e.folder == from) { e.folder = name; any = true; }
    if (any) normalize(list);
    return any;
}
inline int removeFolder(std::vector<Entry>& list, const std::string& folder)
{
    if (folder.empty()) return 0;
    const std::size_t before = list.size();
    list.erase(std::remove_if(list.begin(), list.end(), [&](const Entry& e) { return e.folder == folder; }), list.end());
    return int(before - list.size());
}

// --- search -------------------------------------------------------------------------------------------------------
inline std::string lower(std::string s)
{
    for (auto& c : s) if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    return s;
}
// The host of an address: no scheme, user info, port, path; lower case; "www." kept (the search is a substring).
inline std::string hostOf(const std::string& url)
{
    std::size_t a = url.find("://");
    a = a == std::string::npos ? 0 : a + 3;
    std::size_t b = url.find_first_of("/?#", a);
    std::string h = url.substr(a, b == std::string::npos ? std::string::npos : b - a);
    const std::size_t at = h.rfind('@');
    if (at != std::string::npos) h = h.substr(at + 1);
    if (!h.empty() && h[0] == '[') { const std::size_t e = h.find(']'); if (e != std::string::npos) h = h.substr(0, e + 1); }
    else { const std::size_t c = h.find(':'); if (c != std::string::npos) h.resize(c); }
    return lower(h);
}
// Every word of the query is in the title or the host (ASCII case-insensitive). An empty query matches everything.
inline bool matches(const Entry& e, const std::string& query)
{
    const std::string title = lower(e.title), host = hostOf(e.url), q = lower(query);
    std::size_t i = 0;
    while (i < q.size()) {
        while (i < q.size() && q[i] == ' ') ++i;
        std::size_t j = i;
        while (j < q.size() && q[j] != ' ') ++j;
        if (j > i) {
            const std::string w = q.substr(i, j - i);
            if (title.find(w) == std::string::npos && host.find(w) == std::string::npos) return false;
        }
        i = j;
    }
    return true;
}

// --- what the panel lists ------------------------------------------------------------------------------------------
struct Row {
    enum Kind { Folder, Bookmark } kind = Bookmark;
    int index = -1;            // Bookmark: index into the list
    int folderIndex = -1;      // Folder: index into folders(list)
    std::string folder;        // Folder: its name; Bookmark: the folder it is in
    int count = 0;             // Folder: bookmarks in it
    bool open = false;         // Folder: expanded
    bool nested = false;       // Bookmark: shown under an open folder
};
inline std::vector<Row> view(const std::vector<Entry>& list, const std::vector<std::string>& open, const std::string& query)
{
    std::vector<Row> rows;
    const auto order = folders(list);
    const std::string q = trim(query);
    auto bookmark = [&](int i, bool nested) {
        Row r; r.kind = Row::Bookmark; r.index = i; r.folder = list[size_t(i)].folder; r.nested = nested;
        rows.push_back(std::move(r));
    };
    if (!q.empty()) {   // flat: matching bookmarks, folders first (the list's display order)
        for (const auto& f : order)
            for (int i = 0; i < int(list.size()); ++i) if (list[size_t(i)].folder == f && matches(list[size_t(i)], q)) bookmark(i, false);
        for (int i = 0; i < int(list.size()); ++i) if (list[size_t(i)].folder.empty() && matches(list[size_t(i)], q)) bookmark(i, false);
        return rows;
    }
    for (int k = 0; k < int(order.size()); ++k) {
        Row r; r.kind = Row::Folder; r.folderIndex = k; r.folder = order[size_t(k)];
        r.count = folderCount(list, r.folder);
        r.open = std::find(open.begin(), open.end(), r.folder) != open.end();
        rows.push_back(r);
        if (r.open) for (int i = 0; i < int(list.size()); ++i) if (list[size_t(i)].folder == r.folder) bookmark(i, true);
    }
    for (int i = 0; i < int(list.size()); ++i) if (list[size_t(i)].folder.empty()) bookmark(i, false);
    return rows;
}

} // namespace OmniBookmarksModel
'''

SHELL = r'''// OMNI_BOOKMARKS_MANAGER_V1: the bookmarks manager panel (shell side). Included from OmniBookmarks.h (inside
// OmniBrowser.cpp's anonymous namespace) just before omniFxBookmarksShow. The pure part is OmniBookmarksModel.h; the
// file format and the controls are described in tools/apply_bookmarks_manager.py. Main thread only.
// Row ids (bookmarks list): >= 0 a bookmark (index into omniFxBookmarks), omniFxBmSwitch / omniFxBmEmpty as before,
// omniBmRowAdd / omniBmRowSearch, and omniBmRowFolder0 - k for the k-th folder.
#pragma once

namespace OBMK = OmniBookmarksModel;

enum { omniBmRowSearch = -3, omniBmRowAdd = -4, omniBmRowNoMatch = -5, omniBmRowFolder0 = -100 };
enum { omniBmKindList = 7460, omniBmKindEdit = 7461, omniBmKindPick = 7462 };
static std::vector<std::string> omniBmOpen;                      // expanded folders
static std::string omniBmQuery, omniBmQueryEdit;                 // the search (empty: the tree)
static std::string omniBmFocusURL, omniBmFocusFolder;            // the row to focus on the next rebuild
static std::string omniBmEditURL, omniBmEditBuf, omniBmFolderFrom;

static std::vector<OBMK::Entry> omniBmEntries()
{
    omniFxBookmarksLoad();
    std::vector<OBMK::Entry> out;
    out.reserve(omniFxBookmarks.size());
    for (auto& [url, title] : omniFxBookmarks) {
        const auto it = omniBmFolderOf.find(url);
        out.push_back({ url, title, it == omniBmFolderOf.end() ? std::string() : it->second });
    }
    return out;
}
static void omniBmStore(const std::vector<OBMK::Entry>& list)   // replace the list and save it
{
    omniFxBookmarks.clear();
    omniBmFolderOf.clear();
    for (auto& e : list) {
        omniFxBookmarks.emplace_back(e.url, e.title);
        if (!e.folder.empty()) omniBmFolderOf[e.url] = e.folder;
    }
    omniFxBookmarksSave();
}
static void omniBmSetOpen(const std::string& folder, bool open)
{
    const auto it = std::find(omniBmOpen.begin(), omniBmOpen.end(), folder);
    if (open && it == omniBmOpen.end()) omniBmOpen.push_back(folder);
    if (!open && it != omniBmOpen.end()) omniBmOpen.erase(it);
}
static bool omniBmIsOpen(const std::string& folder) { return std::find(omniBmOpen.begin(), omniBmOpen.end(), folder) != omniBmOpen.end(); }
static void omniBmPopTo(int kind)
{
    while (!omniFxStack.empty() && omniFxStack.back().kind != kind) omniFxStack.pop_back();
    if (!omniFxStack.empty()) omniFxRebuild(omniFxStack.back());
    omniShellDirty = true;
}

static void omniBmBuild(OmniFxPanel& p)
{
    if (p.mode) { omniFxBookmarksBuild(p); return; }   // Shortcuts: the old rows
    const auto list = omniBmEntries();
    OmniFxRow sw; sw.id = omniFxBmSwitch; sw.stepper = true; sw.label = "Showing"; sw.value = "Bookmarks";
    p.rows.push_back(sw);
    const Tab* t = active();
    const bool web = t && omniWebURL(t->url);
    OmniFxRow add; add.id = omniBmRowAdd; add.label = "Add current page";
    add.enabled = web && omniFxBookmarkIndex(t->url) < 0;
    add.detail = !web ? "No web page in this tab" : add.enabled ? omniShownURL(t->url) : "Already bookmarked";
    p.rows.push_back(add);
    const auto rows = OBMK::view(list, omniBmOpen, omniBmQuery);
    OmniFxRow s; s.id = omniBmRowSearch; s.label = "Search";
    s.value = omniBmQuery.empty() ? "Title or site" : omniBmQuery;
    if (!omniBmQuery.empty()) s.detail = std::to_string(rows.size()) + (rows.size() == 1 ? " match" : " matches") + ". Square clears";
    p.rows.push_back(s);
    const size_t head = p.rows.size();
    for (const auto& v : rows) {
        OmniFxRow r;
        if (v.kind == OBMK::Row::Folder) {
            r.id = omniBmRowFolder0 - v.folderIndex;
            r.label = (v.open ? "\xe2\x96\xbc " : "\xe2\x96\xb6 ") + v.folder;   // down / right triangle
            r.value = std::to_string(v.count);
        } else {
            const auto& e = list[size_t(v.index)];
            r.id = v.index;
            r.label = (v.nested ? "      " : "") + e.title;
            r.detail = (omniBmQuery.empty() || e.folder.empty() ? std::string() : e.folder + " \xc2\xb7 ") + omniShownURL(e.url);
        }
        p.rows.push_back(r);
    }
    if (list.empty()) {
        OmniFxRow r; r.id = omniFxBmEmpty; r.enabled = false;
        r.label = "No bookmarks: Add current page, or the star in the address bar";
        p.rows.push_back(r);
    } else if (rows.empty()) {
        OmniFxRow r; r.id = omniBmRowNoMatch; r.enabled = false; r.label = "No bookmark matches \"" + omniBmQuery + "\"";
        p.rows.push_back(r);
    }
    p.corner = std::to_string(list.size()) + " of " + std::to_string(omniFxBookmarkMax);
    if (!omniBmFocusURL.empty() || !omniBmFocusFolder.empty()) {
        const auto order = OBMK::folders(list);
        for (size_t i = head; i < p.rows.size(); ++i) {
            const int id = p.rows[i].id;
            const bool hit = id >= 0 ? !omniBmFocusURL.empty() && id < int(list.size()) && list[size_t(id)].url == omniBmFocusURL
                : id <= omniBmRowFolder0 && !omniBmFocusFolder.empty() && size_t(omniBmRowFolder0 - id) < order.size() && order[size_t(omniBmRowFolder0 - id)] == omniBmFocusFolder;
            if (hit) { p.sel = int(i); break; }
        }
        omniBmFocusURL.clear(); omniBmFocusFolder.clear();
    }
}

static void omniBmAskDelete(const std::string& url, const std::string& title, int mode)
{
    omniAsk(mode ? "Remove this shortcut?" : "Delete this bookmark?", title + " (" + omniShownURL(url) + ") will be removed from this console.", mode ? "Remove" : "Delete", [url, mode](bool ok) {
        if (!ok) return;
        auto& list = omniFxBmList(mode);
        for (size_t i = 0; i < list.size(); ++i) if (list[i].first == url) {
            notice("Removed: " + list[i].second);
            list.erase(list.begin() + std::ptrdiff_t(i));
            omniFxBmSaveList(mode);
            break;
        }
        omniFxRefresh();
    });
}

// "Edit bookmark": Name, Folder. "Move to folder": No folder, the folders, New folder...
enum { omniBmEditName = 1, omniBmEditFolder = 2, omniBmPickNone = -1, omniBmPickNew = -2 };
static void omniBmMoveTo(const std::string& folder)
{
    auto list = omniBmEntries();
    if (OBMK::setFolderAt(list, omniBmEditURL, folder) < 0) return;
    omniBmStore(list);
    const std::string f = OBMK::cleanFolder(folder);
    if (!f.empty()) omniBmSetOpen(f, true);
    notice(f.empty() ? std::string("Moved out of its folder") : "Moved to " + f);
    omniBmFocusURL = omniBmEditURL;
    omniBmPopTo(omniBmKindList);
}
static void omniBmPickBuild(OmniFxPanel& p)
{
    const auto list = omniBmEntries();
    std::string cur;
    for (auto& e : list) if (e.url == omniBmEditURL) { cur = e.folder; break; }
    OmniFxRow none; none.id = omniBmPickNone; none.label = "No folder"; none.value = cur.empty() ? "\xe2\x9c\x93" : "";
    p.rows.push_back(none);
    const auto order = OBMK::folders(list);
    for (int k = 0; k < int(order.size()); ++k) {
        OmniFxRow r; r.id = k; r.label = order[size_t(k)]; r.value = order[size_t(k)] == cur ? "\xe2\x9c\x93" : "";
        p.rows.push_back(r);
    }
    OmniFxRow nw; nw.id = omniBmPickNew; nw.label = "New folder\xe2\x80\xa6";
    p.rows.push_back(nw);
}
static bool omniBmPickInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (r.id == omniBmPickNone) { omniBmMoveTo(""); return true; }
    if (r.id == omniBmPickNew) {
        omniBmEditBuf.clear();
        omniKbEdit(&omniBmEditBuf, "New folder name", [](bool ok) {
            if (!ok) return;
            if (OBMK::cleanFolder(omniBmEditBuf).empty()) { notice("A folder needs a name"); return; }
            omniBmMoveTo(omniBmEditBuf);
        });
        return true;
    }
    const auto order = OBMK::folders(omniBmEntries());
    if (r.id >= 0 && r.id < int(order.size())) omniBmMoveTo(order[size_t(r.id)]);
    return true;
}
static void omniBmEditBuild(OmniFxPanel& p)
{
    const auto list = omniBmEntries();
    const OBMK::Entry* e = nullptr;
    for (auto& x : list) if (x.url == omniBmEditURL) { e = &x; break; }
    if (!e) { OmniFxRow r; r.enabled = false; r.label = "This bookmark was removed"; p.rows.push_back(r); return; }
    p.subtitle = omniShownURL(e->url);
    OmniFxRow n; n.id = omniBmEditName; n.label = "Name"; n.value = e->title; p.rows.push_back(n);
    OmniFxRow f; f.id = omniBmEditFolder; f.label = "Folder"; f.value = e->folder.empty() ? "None" : e->folder; p.rows.push_back(f);
}
static bool omniBmEditInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (r.id == omniBmEditName) {
        const int i = omniFxBookmarkIndex(omniBmEditURL);
        if (i < 0) return true;
        omniBmEditBuf = omniFxBookmarks[size_t(i)].second;
        omniKbEdit(&omniBmEditBuf, "Bookmark name", [](bool ok) {
            if (!ok) return;
            const int j = omniFxBookmarkIndex(omniBmEditURL);
            if (j < 0) return;
            const std::string name = OBMK::trim(OBMK::oneLine(omniBmEditBuf, OBMK::kTitleMax));
            omniFxBookmarks[size_t(j)].second = name.empty() ? omniShownURL(omniBmEditURL) : name;
            omniFxBookmarksSave();
            omniBmFocusURL = omniBmEditURL;
            omniFxRefresh();
        });
        return true;
    }
    if (r.id == omniBmEditFolder) {
        OmniFxPanel q;
        q.kind = omniBmKindPick; q.title = "Move to folder"; q.w = 760; q.maxVisible = 9;
        q.build = omniBmPickBuild; q.input = omniBmPickInput;
        q.faces = { { 0, "Move here" }, { 1, "Back" } };
        omniFxPush(std::move(q));
        return true;
    }
    return false;
}

static bool omniBmInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (r.id == omniFxBmSwitch) return omniFxBookmarksInput(p, r, b);
    if (p.mode) {   // Shortcuts: the old controls, but Square asks first
        if (b == SDL_CONTROLLER_BUTTON_X && r.id >= 0) {
            auto& list = omniFxBmList(1);
            if (r.id < int(list.size())) omniBmAskDelete(list[size_t(r.id)].first, list[size_t(r.id)].second, 1);
            return true;
        }
        return omniFxBookmarksInput(p, r, b);
    }
    const bool lr = b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER || b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER;
    const int delta = b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER ? -1 : 1;
    if (r.id == omniBmRowAdd) {
        if (b != SDL_CONTROLLER_BUTTON_A) return false;
        Tab* t = active();
        if (r.enabled && t && omniFxBookmarkAdd(t->url, t->title)) omniBmFocusURL = t->url;   // the old rule, private tabs included
        return true;
    }
    if (r.id == omniBmRowSearch) {
        if (b == SDL_CONTROLLER_BUTTON_X) { omniBmQuery.clear(); return true; }
        if (b != SDL_CONTROLLER_BUTTON_A) return false;
        omniBmQueryEdit = omniBmQuery;
        omniKbEdit(&omniBmQueryEdit, "Search bookmarks: title or site", [](bool ok) {
            if (ok) omniBmQuery = OBMK::trim(OBMK::oneLine(omniBmQueryEdit, 120));
            omniFxRefresh();
        });
        return true;
    }
    auto list = omniBmEntries();
    if (r.id <= omniBmRowFolder0) {
        const auto order = OBMK::folders(list);
        const size_t k = size_t(omniBmRowFolder0 - r.id);
        if (k >= order.size()) return false;
        const std::string name = order[k];
        switch (b) {
        case SDL_CONTROLLER_BUTTON_A: omniBmSetOpen(name, !omniBmIsOpen(name)); return true;
        case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniBmSetOpen(name, true); return true;
        case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniBmSetOpen(name, false); return true;
        case SDL_CONTROLLER_BUTTON_X: {
            const int n = OBMK::folderCount(list, name);
            omniAsk("Delete the folder " + name + "?", n == 1 ? "Its bookmark will be removed from this console." : "Its " + std::to_string(n) + " bookmarks will be removed from this console.", "Delete", [name](bool ok) {
                if (!ok) return;
                auto l = omniBmEntries();
                const int gone = OBMK::removeFolder(l, name);
                omniBmStore(l);
                omniBmSetOpen(name, false);
                notice("Deleted " + name + " (" + std::to_string(gone) + (gone == 1 ? " bookmark)" : " bookmarks)"));
                omniFxRefresh();
            });
            return true;
        }
        case SDL_CONTROLLER_BUTTON_Y:
            omniBmFolderFrom = name; omniBmEditBuf = name;
            omniKbEdit(&omniBmEditBuf, "Folder name", [](bool ok) {
                if (!ok) return;
                const std::string to = OBMK::cleanFolder(omniBmEditBuf);
                if (to.empty()) { notice("A folder needs a name"); return; }
                auto l = omniBmEntries();
                const bool wasOpen = omniBmIsOpen(omniBmFolderFrom);
                if (to == omniBmFolderFrom || !OBMK::renameFolder(l, omniBmFolderFrom, to)) return;
                omniBmStore(l);
                omniBmSetOpen(omniBmFolderFrom, false);
                if (wasOpen) omniBmSetOpen(to, true);
                omniBmFocusFolder = to;
                omniFxRefresh();
            });
            return true;
        default:
            if (!lr) return false;
            if (OBMK::moveFolder(list, name, delta)) { omniBmStore(list); omniBmFocusFolder = name; }
            return true;
        }
    }
    if (r.id < 0 || r.id >= int(list.size())) return false;
    const OBMK::Entry e = list[size_t(r.id)];
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: omniFxCloseAll(); navigate(e.url); return true;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniFxCloseAll(); if (newTab()) navigate(e.url); return true;
    case SDL_CONTROLLER_BUTTON_X: omniBmAskDelete(e.url, e.title, 0); return true;
    case SDL_CONTROLLER_BUTTON_Y: {
        omniBmEditURL = e.url;
        OmniFxPanel q;
        q.kind = omniBmKindEdit; q.title = "Edit bookmark"; q.w = 860; q.maxVisible = 4;
        q.build = omniBmEditBuild; q.input = omniBmEditInput;
        q.faces = { { 0, "Change" }, { 1, "Back" } };
        omniFxPush(std::move(q));
        return true;
    }
    default:
        if (!lr) return false;
        if (!omniBmQuery.empty()) { notice("Clear the search to reorder"); return true; }
        if (OBMK::moveEntry(list, r.id, delta) >= 0) { omniBmStore(list); omniBmFocusURL = e.url; }
        return true;
    }
}
static void omniBmFocusFirst(OmniFxPanel& p)   // "Add current page" when it can add, else the first folder / bookmark
{
    if (p.mode) { if (p.rows.size() > 1) p.sel = 1; return; }
    for (size_t i = 0; i < p.rows.size(); ++i) if (p.rows[i].id == omniBmRowAdd && p.rows[i].enabled) { p.sel = int(i); return; }
    for (size_t i = 0; i < p.rows.size(); ++i) if (p.rows[i].enabled && (p.rows[i].id >= 0 || p.rows[i].id <= omniBmRowFolder0)) { p.sel = int(i); return; }
    for (size_t i = 0; i < p.rows.size(); ++i) if (p.rows[i].id == omniBmRowSearch) { p.sel = int(i); return; }
}
'''

LOAD_OLD = '''    if (FILE* f = fopen(omniData("bookmarks.txt").c_str(), "r")) {
        char line[2400];
        while (fgets(line, sizeof(line), f) && omniFxBookmarks.size() < omniFxBookmarkMax) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\\n' || s.back() == '\\r')) s.pop_back();
            const size_t t = s.find('\\t');
            std::string url = t == std::string::npos ? s : s.substr(0, t), title = t == std::string::npos ? std::string() : s.substr(t + 1);
            if (!url.empty()) omniFxBookmarks.emplace_back(url, title.empty() ? url : title);
        }
        fclose(f);
    }
}
static void omniFxBookmarksSave()
{
    std::string s;
    for (auto& [url, title] : omniFxBookmarks) s += omniOneLine(url, 2048) + "\\t" + omniOneLine(title, 300) + "\\n";
    omniIoQueue(omniData("bookmarks.txt"), std::move(s), false);
}
'''
LOAD_NEW = '''    // OMNI_BOOKMARKS_MANAGER_V1: OmniBookmarksModel reads the same lines (fgets(2400) splitting, 500 cap) plus the
    // optional third column (folder); folders come first, each one's bookmarks together.
    std::string data;
    if (FILE* f = fopen(omniData("bookmarks.txt").c_str(), "rb")) {
        char buf[16384];
        size_t n;
        while ((n = fread(buf, 1, sizeof(buf), f)) > 0 && data.size() < (size_t(8) << 20)) data.append(buf, n);
        fclose(f);
    }
    auto list = OmniBookmarksModel::parse(data, omniFxBookmarkMax);
    OmniBookmarksModel::normalize(list);
    for (auto& e : list) {
        omniFxBookmarks.emplace_back(e.url, e.title);
        if (!e.folder.empty()) omniBmFolderOf[e.url] = e.folder;
    }
}
static void omniFxBookmarksSave()
{
    // OMNI_BOOKMARKS_MANAGER_V1: "url TAB title" as before; a bookmark in a folder adds "TAB folder".
    std::unordered_map<std::string, std::string> keep;   // folders of bookmarks that still exist
    std::vector<OmniBookmarksModel::Entry> list;
    list.reserve(omniFxBookmarks.size());
    for (auto& [url, title] : omniFxBookmarks) {
        const auto it = omniBmFolderOf.find(url);
        list.push_back({ url, title, it == omniBmFolderOf.end() ? std::string() : it->second });
        if (it != omniBmFolderOf.end()) keep.insert(*it);
    }
    omniBmFolderOf.swap(keep);
    omniIoQueue(omniData("bookmarks.txt"), OmniBookmarksModel::serialize(list), false);
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTabSessions.h" // OMNI_TAB_SESSIONS_V1: named tab sessions, sessions.txt (pure)\n',
         '#include "OmniTabSessions.h" // OMNI_TAB_SESSIONS_V1: named tab sessions, sessions.txt (pure)\n'
         '#include "OmniBookmarksModel.h" // OMNI_BOOKMARKS_MANAGER_V1: bookmarks.txt with folders, reorder, search (pure)\n'),
    ],
    'OmniBookmarks.h': [
        ('static bool omniFxBookmarksLoaded = false;\n',
         'static bool omniFxBookmarksLoaded = false;\n'
         'static std::unordered_map<std::string, std::string> omniBmFolderOf;   // OMNI_BOOKMARKS_MANAGER_V1: url -> folder\n'),
        (LOAD_OLD, LOAD_NEW),
        ('static void omniFxBookmarksShow(int mode)\n{\n    OmniFxPanel p;\n',
         '#include "OmniBookmarksShell.h" // OMNI_BOOKMARKS_MANAGER_V1: folders, search, Add current page, Edit\n'
         'static void omniFxBookmarksShow(int mode)\n{\n    OmniFxPanel p;\n    p.kind = omniBmKindList; // OMNI_BOOKMARKS_MANAGER_V1\n'),
        ('    p.build = omniFxBookmarksBuild; p.input = omniFxBookmarksInput;\n'
         '    p.faces = { { 0, "Open" }, { 3, "Rename" }, { 2, "Delete" }, { 1, "Back" } };\n'
         '    p.extra = "L1/R1 move up/down   \\xe2\\x96\\xb6 new tab";\n'
         '    omniFxPush(std::move(p));\n'
         '    if (!omniFxStack.empty() && omniFxStack.back().rows.size() > 1) omniFxStack.back().sel = 1;\n',
         '    p.build = omniBmBuild; p.input = omniBmInput; // OMNI_BOOKMARKS_MANAGER_V1\n'
         '    p.faces = { { 0, "Open" }, { 3, "Edit" }, { 2, "Delete" }, { 1, "Back" } };\n'
         '    p.extra = "L1/R1 move up/down   \\xe2\\x96\\xb6 new tab / open folder";\n'
         '    omniFxPush(std::move(p));\n'
         '    if (!omniFxStack.empty()) omniBmFocusFirst(omniFxStack.back()); // OMNI_BOOKMARKS_MANAGER_V1\n'),
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


def main():
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniBookmarksModel.h', PURE, 'OmniTabSessions.h'),
            write_new('OmniBookmarksShell.h', SHELL, 'OmniBookmarks.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
