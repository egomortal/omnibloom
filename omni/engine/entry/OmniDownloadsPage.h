// OMNI_FEATURES_V1: Downloads page for ordinary file downloads (not the media-downloads worker).
// Running downloads come from the WKDownload client in OmniBrowser.cpp (three hooks); finished ones
// are the files in /data/omni/downloads/. Open plays/shows a file through the console's local file
// server (http://127.0.0.1:8080/fs/...), the same server the self-tests load pages from.
#pragma once
// <dirent.h> is included at the top of OmniBrowser.cpp (outside the anonymous namespace).

struct OmniFxDl { WKDownloadRef ref = nullptr; std::string path, name; long long bytes = 0, expected = 0; int state = 0; uint32_t lastDraw = 0; };   // state: 0 running, 1 done, 2 failed, 3 cancelled
static std::deque<OmniFxDl> omniFxDls;   // this session
struct OmniFxFile { std::string name; long long size; long long mtime; };
static std::vector<OmniFxFile> omniFxFiles;
static bool omniFxDownloadsShown();

static OmniFxDl* omniFxDlFind(WKDownloadRef d) { for (auto& x : omniFxDls) if (x.ref == d) return &x; return nullptr; }
static void omniFxDownloadStarted(WKDownloadRef download, const std::string& path)
{
    OmniFxDl d;
    d.ref = download; WKRetain(download);
    d.path = path;
    const size_t slash = path.rfind('/');
    d.name = slash == std::string::npos ? path : path.substr(slash + 1);
    omniFxDls.push_back(d);
    while (omniFxDls.size() > 40 && omniFxDls.front().state != 0) omniFxDls.pop_front();
    if (omniFxDownloadsShown()) omniFxRefresh();
}
static void omniFxDownloadProgress(WKDownloadRef download, long long total, long long expected)
{
    OmniFxDl* d = omniFxDlFind(download);
    if (!d) return;
    d->bytes = total; d->expected = expected;
    if (omniFxDownloadsShown() && SDL_GetTicks() - d->lastDraw > 250) { d->lastDraw = SDL_GetTicks(); omniShellDirty = true; }
}
static void omniFxScanFiles();
static void omniFxDownloadEnded(WKDownloadRef download, bool ok)
{
    OmniFxDl* d = omniFxDlFind(download);
    if (!d) return;
    if (d->state == 3) unlink(d->path.c_str());   // cancelled: no half file left behind
    else d->state = ok ? 1 : 2;
    WKRelease(d->ref); d->ref = nullptr;
    if (omniFxDownloadsShown()) { omniFxScanFiles(); omniFxRefresh(); }
}
static void omniFxScanFiles()
{
    omniFxFiles.clear();
    const std::string dir = omniData("downloads");
    if (DIR* dp = opendir(dir.c_str())) {
        while (dirent* e = readdir(dp)) {
            if (e->d_name[0] == '.') continue;
            struct stat st {};
            const std::string path = dir + "/" + e->d_name;
            if (stat(path.c_str(), &st) || !S_ISREG(st.st_mode)) continue;
            bool running = false;
            for (auto& x : omniFxDls) if (x.state == 0 && x.path == path) running = true;
            if (!running) omniFxFiles.push_back({ e->d_name, (long long)st.st_size, (long long)st.st_mtime });
            if (omniFxFiles.size() >= 400) break;
        }
        closedir(dp);
    }
    std::sort(omniFxFiles.begin(), omniFxFiles.end(), [](const OmniFxFile& a, const OmniFxFile& b) { return a.mtime > b.mtime; });
}
static std::string omniFxSize(long long b)
{
    char s[32];
    if (b >= 1073741824LL) snprintf(s, sizeof(s), "%.2f GB", b / 1073741824.0);
    else if (b >= 1048576) snprintf(s, sizeof(s), "%.1f MB", b / 1048576.0);
    else snprintf(s, sizeof(s), "%lld KB", (b + 1023) / 1024);
    return s;
}
static int omniFxDownloadsRunning() { int n = 0; for (auto& x : omniFxDls) n += x.state == 0; return n; }
// Row ids: 0..99 session downloads (index), 1000+ files.
static void omniFxDownloadsBuild(OmniFxPanel& p)
{
    for (int i = int(omniFxDls.size()) - 1; i >= 0; --i) {
        const OmniFxDl& d = omniFxDls[i];
        if (d.state == 1) continue;   // finished: listed with the files
        OmniFxRow r; r.id = i; r.label = d.name;
        if (d.state == 0) {
            char b[96];
            if (d.expected > 0) snprintf(b, sizeof(b), "%d%% of %s", int(100.0 * d.bytes / d.expected), omniFxSize(d.expected).c_str());
            else snprintf(b, sizeof(b), "%s so far", omniFxSize(d.bytes).c_str());
            r.value = b; r.detail = "Downloading";
        } else { r.value = d.state == 2 ? "Failed" : "Cancelled"; r.danger = d.state == 2; }
        p.rows.push_back(r);
    }
    for (size_t i = 0; i < omniFxFiles.size(); ++i) {
        OmniFxRow r; r.id = 1000 + int(i); r.label = omniFxFiles[i].name;
        r.value = omniFxSize(omniFxFiles[i].size) + " \xc2\xb7 " + omniAgo(omniFxFiles[i].mtime);
        p.rows.push_back(r);
    }
    if (p.rows.empty()) { OmniFxRow r; r.id = -1; r.enabled = false; r.label = "No downloads yet. Files you download are saved in /data/omni/downloads/"; p.rows.push_back(r); }
    const int running = omniFxDownloadsRunning();
    p.corner = running ? std::to_string(running) + " running" : std::to_string(omniFxFiles.size()) + " files";
}
static std::string omniFxFileURL(const std::string& name) { return "http://127.0.0.1:8080/fs" + omniData("downloads/") + omniPercentEncode(name); }
static std::string omniFxDeleteName;
static bool omniFxDownloadsInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id >= 1000) {
        const int i = r.id - 1000;
        if (i >= int(omniFxFiles.size())) return false;
        const std::string name = omniFxFiles[i].name;
        if (b == SDL_CONTROLLER_BUTTON_A) {
            omniFxCloseAll();
            if (newTab()) navigate(omniFxFileURL(name)); else { notice("No new tab possible: opening here"); /* OMNI_FEATURES_V3 */ navigate(omniFxFileURL(name)); }
            return true;
        }
        if (b == SDL_CONTROLLER_BUTTON_Y && omniNativeTitle()) {   // OMNI_FILES_BROKER_V1: copy to a USB drive
            omniOfbCopyToUsb(omniData("downloads/") + name);
            return true;
        }
        if (b == SDL_CONTROLLER_BUTTON_X) {
            omniFxDeleteName = name;
            omniAsk("Delete this file?", name + " (" + omniFxSize(omniFxFiles[i].size) + ") will be deleted from the console.", "Delete", [](bool ok) {
                if (!ok) return;
                const std::string path = omniData("downloads/") + omniFxDeleteName;
                if (unlink(path.c_str())) notice("Couldn't delete " + omniFxDeleteName); else notice("Deleted " + omniFxDeleteName);
                omniFxScanFiles(); omniFxRefresh();
            });
            return true;
        }
        return false;
    }
    if (r.id < 0 || r.id >= int(omniFxDls.size())) return false;
    OmniFxDl& d = omniFxDls[r.id];
    if (b == SDL_CONTROLLER_BUTTON_X || (b == SDL_CONTROLLER_BUTTON_A && d.state == 0)) {
        if (d.state == 0 && d.ref) {
            d.state = 3;
            WKDownloadCancel(d.ref, nullptr, [](WKDataRef, const void*) {});
            notice("Cancelled " + d.name);
        } else if (d.state != 0) omniFxDls.erase(omniFxDls.begin() + r.id);   // clear a failed / cancelled entry
        return true;
    }
    return false;
}
static bool omniFxDownloadsShown() { for (auto& p : omniFxStack) if (p.build == omniFxDownloadsBuild) return true; return false; }
static void omniFxDownloadsShow()
{
    omniFxScanFiles();
    OmniFxPanel p;
    p.title = "Downloads"; p.subtitle = omniData("downloads/"); p.w = 980; p.maxVisible = 9;
    p.build = omniFxDownloadsBuild; p.input = omniFxDownloadsInput;
    p.faces = { { 0, "Open" }, { 2, "Delete / cancel" }, { 1, "Back" } };
    if (omniNativeTitle()) p.faces = { { 0, "Open" }, { 2, "Delete / cancel" }, { 3, "Copy to USB" }, { 1, "Back" } };   // OMNI_FILES_BROKER_V1
    omniFxPush(std::move(p));
}
