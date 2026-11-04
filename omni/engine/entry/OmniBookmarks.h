// OMNI_FEATURES_V1: bookmarks beyond the 19 shortcuts (/data/omni/bookmarks.txt, url TAB title per
// line, up to 500) and one manager for both lists: open, rename, delete, reorder.
#pragma once

constexpr size_t omniFxBookmarkMax = 500;
static std::vector<std::pair<std::string, std::string>> omniFxBookmarks;   // url, title
static bool omniFxBookmarksLoaded = false;
static void omniFxBookmarksLoad()
{
    if (omniFxBookmarksLoaded) return;
    omniFxBookmarksLoaded = true;
    if (FILE* f = fopen(omniData("bookmarks.txt").c_str(), "r")) {
        char line[2400];
        while (fgets(line, sizeof(line), f) && omniFxBookmarks.size() < omniFxBookmarkMax) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            const size_t t = s.find('\t');
            std::string url = t == std::string::npos ? s : s.substr(0, t), title = t == std::string::npos ? std::string() : s.substr(t + 1);
            if (!url.empty()) omniFxBookmarks.emplace_back(url, title.empty() ? url : title);
        }
        fclose(f);
    }
}
static void omniFxBookmarksSave()
{
    std::string s;
    for (auto& [url, title] : omniFxBookmarks) s += omniOneLine(url, 2048) + "\t" + omniOneLine(title, 300) + "\n";
    omniIoQueue(omniData("bookmarks.txt"), std::move(s), false);
}
static int omniFxBookmarkIndex(const std::string& url)
{
    omniFxBookmarksLoad();
    for (size_t i = 0; i < omniFxBookmarks.size(); ++i) if (omniFxBookmarks[i].first == url) return int(i);
    return -1;
}
static bool omniFxBookmarkAdd(const std::string& url, const std::string& title)
{
    if (!omniWebURL(url)) { notice("Only web pages can be bookmarked"); return false; }
    if (omniFxBookmarkIndex(url) >= 0) { notice("Already bookmarked"); return false; }
    if (omniFxBookmarks.size() >= omniFxBookmarkMax) { notice("Bookmarks are full (500): delete some first"); return false; }
    omniFxBookmarks.emplace_back(url, title.empty() ? omniShownURL(url) : title);
    omniFxBookmarksSave();
    notice("Bookmarked: " + omniFxBookmarks.back().second);
    return true;
}
static void omniFxBookmarkToggleCurrent()
{
    if (!active() || !omniWebURL(active()->url)) { notice("No page to bookmark"); return; }
    const int i = omniFxBookmarkIndex(active()->url);
    if (i >= 0) {
        notice("Bookmark removed: " + omniFxBookmarks[i].second);
        omniFxBookmarks.erase(omniFxBookmarks.begin() + i);
        omniFxBookmarksSave();
    } else omniFxBookmarkAdd(active()->url, active()->title);
}
static bool omniFxShortcutAdd(const std::string& url, const std::string& title)
{
    omniShortcutsLoad();
    if (!omniWebURL(url)) { notice("Only web pages can be shortcuts"); return false; }
    for (auto& s : omniShortcuts) if (s.first == url) { notice("Already in shortcuts"); return false; }
    if (omniShortcuts.size() >= size_t(omniShortcutMax)) { notice("Shortcuts are full (19): added to bookmarks instead"); return omniFxBookmarkAdd(url, title); }
    omniShortcuts.emplace_back(url, title.empty() ? omniShownURL(url) : title);
    omniShortcutsSave();
    notice("Saved to shortcuts: " + omniShortcuts.back().second);
    return true;
}

// --- manager ---------------------------------------------------------------------------------------
enum { omniFxBmSwitch = -1, omniFxBmEmpty = -2 };
static std::vector<std::pair<std::string, std::string>>& omniFxBmList(int mode) { omniShortcutsLoad(); omniFxBookmarksLoad(); return mode ? omniShortcuts : omniFxBookmarks; }
static void omniFxBmSaveList(int mode) { if (mode) omniShortcutsSave(); else omniFxBookmarksSave(); }
static void omniFxBookmarksBuild(OmniFxPanel& p)
{
    auto& list = omniFxBmList(p.mode);
    OmniFxRow sw; sw.id = omniFxBmSwitch; sw.stepper = true; sw.label = "Showing";
    sw.value = p.mode ? "Shortcuts" : "Bookmarks";
    p.rows.push_back(sw);
    for (size_t i = 0; i < list.size(); ++i) {
        OmniFxRow r; r.id = int(i); r.label = list[i].second; r.detail = omniShownURL(list[i].first);
        p.rows.push_back(r);
    }
    if (list.empty()) {
        OmniFxRow r; r.id = omniFxBmEmpty; r.enabled = false;
        r.label = p.mode ? "No shortcuts: press L3 on a page to add one" : "No bookmarks: Options \xe2\x86\x92 Bookmark page";
        p.rows.push_back(r);
    }
    p.corner = p.mode ? std::to_string(list.size()) + " of " + std::to_string(omniShortcutMax) : std::to_string(list.size());
}
static std::string omniFxRenameBuf, omniFxRenameURL;
static int omniFxRenameMode = 0;
static bool omniFxBookmarksInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (r.id == omniFxBmSwitch) {
        if (b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT || b == SDL_CONTROLLER_BUTTON_A) { p.mode = !p.mode; p.sel = 0; p.scroll = 0; return true; }
        return false;
    }
    auto& list = omniFxBmList(p.mode);
    if (r.id < 0 || r.id >= int(list.size())) return false;
    const int i = r.id;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: { const std::string url = list[i].first; omniFxCloseAll(); navigate(url); return true; }
    case SDL_CONTROLLER_BUTTON_X:
        notice("Removed: " + list[i].second);
        list.erase(list.begin() + i); omniFxBmSaveList(p.mode);
        return true;
    case SDL_CONTROLLER_BUTTON_Y:
        omniFxRenameBuf = list[i].second; omniFxRenameURL = list[i].first; omniFxRenameMode = p.mode;
        omniKbEdit(&omniFxRenameBuf, "Rename", [](bool ok) {
            if (!ok) return;
            auto& l = omniFxBmList(omniFxRenameMode);
            for (auto& e : l) if (e.first == omniFxRenameURL) { e.second = omniFxRenameBuf.empty() ? omniShownURL(e.first) : omniFxRenameBuf; break; }
            omniFxBmSaveList(omniFxRenameMode);
            omniFxRefresh();
        });
        return true;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: {
        const int j = i + (b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER ? -1 : 1);
        if (j < 0 || j >= int(list.size())) return true;
        std::swap(list[i], list[j]); omniFxBmSaveList(p.mode);
        p.sel = j + 1;   // row 0 is the switch
        return true;
    }
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: {   // open in a new tab
        const std::string url = list[i].first;
        omniFxCloseAll();
        if (newTab()) navigate(url); // OMNI_FEATURES_V3: newTab() says why
        return true;
    }
    default: return false;
    }
}
static void omniFxBookmarksShow(int mode)
{
    OmniFxPanel p;
    p.title = "Bookmarks"; p.subtitle = "Bookmarks and the shortcuts on the new-tab page"; p.mode = mode;
    p.w = 980; p.maxVisible = 9;
    p.build = omniFxBookmarksBuild; p.input = omniFxBookmarksInput;
    p.faces = { { 0, "Open" }, { 3, "Rename" }, { 2, "Delete" }, { 1, "Back" } };
    p.extra = "L1/R1 move up/down   \xe2\x96\xb6 new tab";
    omniFxPush(std::move(p));
    if (!omniFxStack.empty() && omniFxStack.back().rows.size() > 1) omniFxStack.back().sel = 1;
}
