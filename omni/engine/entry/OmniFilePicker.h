// OMNI_FEATURES_V2: file upload (<input type=file>). WebKit asks through the UI client's runOpenPanel;
// Omni shows a controller file picker over the console folders that make sense (Omni downloads and
// screenshots, USB drives under /mnt/usbN and /mnt/extN, Omni's data folder, /data), filtered by the
// input's accept attribute (Triangle shows every file), with multi-select when the input allows it.
// The chosen paths go back through WKOpenPanelResultListenerChooseFiles as file:// URLs; closing the
// picker (Circle, Options, another tab) always calls WKOpenPanelResultListenerCancel.
#pragma once

struct OmniPickEntry { std::string name; bool dir = false; long long size = 0, mtime = 0; };
struct OmniPickPlace { std::string label, path; };
struct OmniPick {
    WKTypeRef listener = nullptr;            // retained WKOpenPanelResultListenerRef while the picker is up
    const void* tab = nullptr;
    bool multi = false, dirs = false, showAll = false, shown = false;
    std::vector<std::string> exts;           // accepted extensions (lowercase, no dot); empty: any file
    std::string acceptText;                  // what the page asked for, shown in the subtitle
    std::string dir;                         // "" = the list of places
    std::string root;                        // the place `dir` is inside (Up stops there)
    std::vector<OmniPickEntry> entries;
    int hidden = 0;                          // files the filter hides in `dir`
    std::vector<std::string> chosen;         // full paths (multi-select)
    bool copying = false;                    // OMNI_FILES_BROKER_V1: USB files being copied in before the hand-off
    std::vector<OmniPickPlace> places;       // native title: places cached per picker (the broker call can take a moment)
    bool placesValid = false;
};
static OmniPick omniPick;
enum { omniPickKind = 7201 };

static std::string omniPickExt(const std::string& name)
{
    const size_t dot = name.rfind('.');
    return dot == std::string::npos || dot == 0 ? std::string() : omniLower(name.substr(dot + 1));
}
static void omniPickAddMime(std::vector<std::string>& out, const std::string& mime)
{
    static const std::pair<const char*, const char*> table[] = {
        { "image/*", "jpg jpeg png gif webp bmp heic heif avif svg tif tiff ico" },
        { "video/*", "mp4 m4v webm mkv mov avi ts m2ts mpg mpeg 3gp" },
        { "audio/*", "mp3 m4a aac wav ogg oga opus flac weba" },
        { "text/*", "txt csv md html htm json xml log srt vtt" },
        { "image/jpeg", "jpg jpeg" }, { "image/png", "png" }, { "image/gif", "gif" }, { "image/webp", "webp" },
        { "image/svg+xml", "svg" }, { "image/heic", "heic" }, { "image/avif", "avif" }, { "image/bmp", "bmp" },
        { "video/mp4", "mp4 m4v" }, { "video/webm", "webm" }, { "video/quicktime", "mov" }, { "audio/mpeg", "mp3" },
        { "audio/mp4", "m4a" }, { "audio/wav", "wav" }, { "audio/ogg", "ogg oga opus" }, { "text/plain", "txt" },
        { "text/csv", "csv" }, { "application/pdf", "pdf" }, { "application/zip", "zip" }, { "application/json", "json" },
        { "application/x-zip-compressed", "zip" }, { "application/msword", "doc" },
        { "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx" },
        { "application/vnd.ms-excel", "xls" }, { "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx" },
    };
    const std::string m = omniLower(mime);
    for (auto& [k, v] : table) if (m == k) {
        std::string list = v;
        size_t at = 0;
        while (at < list.size()) { size_t sp = list.find(' ', at); if (sp == std::string::npos) sp = list.size(); out.push_back(list.substr(at, sp - at)); at = sp + 1; }
        return;
    }
    const size_t slash = m.find('/');   // unknown type: its subtype is the likeliest extension
    if (slash != std::string::npos && m.find('*') == std::string::npos && m.find('.') == std::string::npos && m.find('-') == std::string::npos) out.push_back(m.substr(slash + 1));
}
static bool omniPickAccepts(const OmniPickEntry& e)
{
    if (e.dir || omniPick.showAll || omniPick.exts.empty()) return true;
    const std::string x = omniPickExt(e.name);
    return std::find(omniPick.exts.begin(), omniPick.exts.end(), x) != omniPick.exts.end();
}
static bool omniPickIsDir(const std::string& path) { struct stat st {}; return !stat(path.c_str(), &st) && S_ISDIR(st.st_mode); }
static std::vector<OmniPickPlace> omniPickPlaces()
{
    if (omniNativeTitle() && omniPick.placesValid) return omniPick.places;   // OMNI_FILES_BROKER_V1
    std::vector<OmniPickPlace> out;
    auto add = [&](const std::string& label, const std::string& path) { if (omniPickIsDir(path)) out.push_back({ label, path }); };
    add("Omni downloads", omniData("downloads"));
    add("Screenshots", omniData("screenshots"));
    if (omniNativeTitle()) {   // OMNI_FILES_BROKER_V1: the title can't see /mnt/usb*, /mnt/ext*: ask the broker
        for (const auto& p : omniOfbPlaces()) {
            const bool usb = p.root.rfind("/mnt/usb", 0) == 0;
            const int n = atoi(p.root.c_str() + (usb ? 8 : 8)) + 1;
            out.push_back({ std::string(usb ? "USB drive " : "Extended storage ") + std::to_string(n), p.root });
        }
    } else {
    for (int i = 0; i < 8; ++i) add("USB drive " + std::to_string(i + 1), "/mnt/usb" + std::to_string(i));
    for (int i = 0; i < 2; ++i) add("Extended storage " + std::to_string(i + 1), "/mnt/ext" + std::to_string(i));
    }
    add("Omni data", omniData("").substr(0, omniData("").size() - 1));
    add("Console data", "/data");
    if (omniNativeTitle()) { omniPick.places = out; omniPick.placesValid = true; }
    return out;
}
static void omniPickScan()
{
    omniPick.entries.clear();
    omniPick.hidden = 0;
    if (omniPick.dir.empty()) return;
    if (omniOfbRemote(omniPick.dir)) {   // OMNI_FILES_BROKER_V1
        std::vector<OmniOfbEntry> rows;
        const int err = omniOfbList(omniPick.dir, rows);
        if (err) notice("Couldn't read " + omniPick.dir + ": " + omniOfbErr(err));
        for (auto& r : rows) {
            if (r.name.empty() || r.name[0] == '.') continue;
            OmniPickEntry e; e.name = r.name; e.dir = r.dir; e.size = r.size; e.mtime = r.mtime;
            omniPick.entries.push_back(std::move(e));
            if (omniPick.entries.size() >= 2000) break;
        }
    } else if (DIR* dp = opendir(omniPick.dir.c_str())) {
        while (dirent* de = readdir(dp)) {
            const std::string name = de->d_name;
            if (name.empty() || name[0] == '.') continue;
            struct stat st {};
            if (stat((omniPick.dir + "/" + name).c_str(), &st)) continue;
            OmniPickEntry e; e.name = name; e.dir = S_ISDIR(st.st_mode); e.size = st.st_size; e.mtime = st.st_mtime;
            if (!e.dir && !S_ISREG(st.st_mode)) continue;
            omniPick.entries.push_back(std::move(e));
            if (omniPick.entries.size() >= 2000) break;
        }
        closedir(dp);
    }
    std::sort(omniPick.entries.begin(), omniPick.entries.end(), [](const OmniPickEntry& a, const OmniPickEntry& b) {
        if (a.dir != b.dir) return a.dir;
        return omniLower(a.name) < omniLower(b.name);
    });
}
static void omniPickGo(const std::string& dir, const std::string& root)
{
    omniPick.dir = dir; omniPick.root = root;
    omniPickScan();
    if (!omniFxStack.empty() && omniFxStack.back().kind == omniPickKind) { omniFxStack.back().sel = 0; omniFxStack.back().scroll = 0; }
}
static std::string omniPickFileURL(const std::string& path)
{
    static const char* hex = "0123456789ABCDEF";
    std::string out = "file://";
    for (unsigned char c : path) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '/' || c == '-' || c == '_' || c == '.' || c == '~') out += char(c);
        else { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
    }
    return out;
}
static void omniPickFinish(const std::vector<std::string>& paths)
{
    if (!omniPick.listener) return;
    auto listener = static_cast<WKOpenPanelResultListenerRef>(omniPick.listener);
    omniPick.listener = nullptr;
    if (paths.empty()) WKOpenPanelResultListenerCancel(listener);
    else {
        auto urls = adoptWK(WKMutableArrayCreate());
        for (auto& p : paths) {
            auto u = adoptWK(WKURLCreateWithUTF8CString(omniPickFileURL(p).c_str()));
            WKArrayAppendItem(urls.get(), u.get());
        }
        auto types = adoptWK(WKMutableArrayCreate());   // must not be null (WebKit reads it unconditionally)
        WKOpenPanelResultListenerChooseFiles(listener, urls.get(), types.get());
        notice(paths.size() == 1 ? "Chose " + paths[0].substr(paths[0].rfind('/') + 1) : "Chose " + std::to_string(paths.size()) + " files");
    }
    WKRelease(listener);
    omniPick.tab = nullptr; omniPick.shown = false; omniPick.chosen.clear();
}
// OMNI_FILES_BROKER_V1: WebKit reads the chosen files itself, so USB files are copied to
// /data/omni/uploads/ first (on the broker job thread); omniPickTick hands the copies over.
static void omniPickChoose(const std::vector<std::string>& paths)
{
    bool remote = false;
    for (auto& p : paths) remote |= omniOfbRemote(p);
    if (!remote) { omniPickFinish(paths); return; }
    if (omniOfbBusy()) { notice("A USB copy is already running"); omniPickFinish({}); return; }
    omniPick.copying = true;
    mkdir(omniData("uploads").c_str(), 0777);
    notice("Copying from the USB drive...");
    omniOfbStart(1, [paths]() {
        static unsigned serial = 0;
        std::vector<std::string> local;
        for (auto& p : paths) {
            if (!omniOfbRemote(p)) { local.push_back(p); continue; }
            const std::string dest = omniData("uploads/") + std::to_string(time(nullptr)) + "-" + std::to_string(++serial) + "-" + omniSafeFileName(omniOfbBaseName(p));
            const int err = omniOfbCopyIn(p, dest);
            if (err) { omniOfbJob.error = "Couldn't copy " + omniOfbBaseName(p) + ": " + omniOfbErr(err); omniOfbJob.state = 3; return; }
            local.push_back(dest);
        }
        omniOfbJob.results = local;
        omniOfbJob.state = 2;
    });
}
static bool omniPickIsChosen(const std::string& path) { return std::find(omniPick.chosen.begin(), omniPick.chosen.end(), path) != omniPick.chosen.end(); }

// Row ids: 1 Up, 2 Upload selected, 3 Upload this folder, 4 Show all, 1000+ places, 10000+ entries.
static void omniPickBuild(OmniFxPanel& p)
{
    std::string sub;
    if (omniPick.dir.empty()) sub = "Choose a place";
    else sub = omniPick.dir;
    if (!omniPick.acceptText.empty()) sub += omniPick.showAll ? "   \xc2\xb7 showing all files" : "   \xc2\xb7 " + omniPick.acceptText;
    p.subtitle = sub;
    p.corner = omniPick.multi ? std::to_string(omniPick.chosen.size()) + " selected" : std::string();
    auto add = [&](int id, const std::string& label, std::string value = {}, int icon = -1) { OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.icon = icon; p.rows.push_back(r); return &p.rows.back(); };
    if (omniPick.multi && !omniPick.chosen.empty()) add(2, "Upload " + std::to_string(omniPick.chosen.size()) + (omniPick.chosen.size() == 1 ? " file" : " files"), "", omniIconCheck);
    if (omniPick.dir.empty()) {
        const auto places = omniPickPlaces();
        for (size_t i = 0; i < places.size(); ++i) add(1000 + int(i), places[i].label, places[i].path);
        if (places.empty()) add(0, "No folders found")->enabled = false;
        return;
    }
    add(1, "Up one folder", omniPick.dir == omniPick.root ? std::string("Places") : omniPick.dir.substr(0, omniPick.dir.rfind('/')), omniIconBack);
    if (omniPick.dirs && !omniOfbRemote(omniPick.dir)) add(3, "Upload this whole folder");   // OMNI_FILES_BROKER_V1: files only from USB
    int shown = 0, hidden = 0;
    for (size_t i = 0; i < omniPick.entries.size(); ++i) {
        const OmniPickEntry& e = omniPick.entries[i];
        if (!omniPickAccepts(e)) { ++hidden; continue; }
        if (e.dir) add(10000 + int(i), e.name + "/", "folder", omniIconForward);
        else {
            const bool on = omniPickIsChosen(omniPick.dir + "/" + e.name);
            add(10000 + int(i), e.name, omniFxSize(e.size) + " \xc2\xb7 " + omniAgo(e.mtime), on ? omniIconCheck : -1);
        }
        ++shown;
    }
    omniPick.hidden = hidden;
    if (hidden) add(4, std::to_string(hidden) + (hidden == 1 ? " file doesn't" : " files don't") + " match what the page accepts", "Show all");
    else if (omniPick.showAll && !omniPick.exts.empty()) add(4, "Showing every file", "Filter");
    if (!shown && !hidden) add(0, "This folder is empty")->enabled = false;
}
static bool omniPickInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    const bool a = b == SDL_CONTROLLER_BUTTON_A;
    if (b == SDL_CONTROLLER_BUTTON_Y || (r.id == 4 && a)) { if (!omniPick.exts.empty()) { omniPick.showAll = !omniPick.showAll; } return true; }
    if (b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || (r.id == 1 && a)) {
        if (omniPick.dir.empty()) return true;
        if (omniPick.dir == omniPick.root) omniPickGo("", "");
        else omniPickGo(omniPick.dir.substr(0, omniPick.dir.rfind('/')), omniPick.root);
        return true;
    }
    if (r.id == 2 && a) { const auto paths = omniPick.chosen; omniFxPop(); omniPickChoose(paths); return true; }
    if (r.id == 3 && a) { const std::vector<std::string> paths { omniPick.dir }; omniPickFinish(paths); omniFxPop(); return true; }
    if (r.id >= 1000 && r.id < 10000 && (a || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT)) {
        const auto places = omniPickPlaces();
        const size_t i = size_t(r.id - 1000);
        if (i < places.size()) omniPickGo(places[i].path, places[i].path);
        return true;
    }
    if (r.id >= 10000) {
        const size_t i = size_t(r.id - 10000);
        if (i >= omniPick.entries.size()) return true;
        const OmniPickEntry e = omniPick.entries[i];
        const std::string path = omniPick.dir + "/" + e.name;
        if (e.dir) { if (a || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) omniPickGo(path, omniPick.root); return true; }
        if (omniPick.multi && (a || b == SDL_CONTROLLER_BUTTON_X)) {
            auto it = std::find(omniPick.chosen.begin(), omniPick.chosen.end(), path);
            if (it != omniPick.chosen.end()) omniPick.chosen.erase(it); else omniPick.chosen.push_back(path);
            return true;
        }
        if (a) { omniFxPop(); omniPickChoose({ path }); return true; }
    }
    return false;
}
static void omniPickShow()
{
    omniPick.shown = true;
    OmniFxPanel p;
    p.kind = omniPickKind; p.w = 900; p.maxVisible = 10; p.rowH = 46;
    p.title = omniPick.multi ? "Choose files to upload" : "Choose a file to upload";
    p.build = omniPickBuild; p.input = omniPickInput;
    if (omniPick.multi) p.faces = { { 0, "Select / open" }, { 3, "All files" }, { 1, "Cancel" } };
    else p.faces = { { 0, "Choose / open" }, { 3, "All files" }, { 1, "Cancel" } };
    p.extra = "D-pad \xe2\x97\x80 up a folder";
    omniFxPush(std::move(p));
}
static void omniPickOpen(WKPageRef page, WKFrameRef, WKOpenPanelParametersRef params, WKOpenPanelResultListenerRef listener, const void*)
{
    Tab* t = omniTabForPage(page);
    if (!t || t != active() || omniPick.listener || pageFullscreen) {
        WKOpenPanelResultListenerCancel(listener);
        if (omniPick.listener) notice("A file picker is already open");
        return;
    }
    omniPick = OmniPick();
    omniPick.listener = WKRetain(listener);
    omniPick.tab = t;
    omniPick.multi = WKOpenPanelParametersGetAllowsMultipleFiles(params);
    omniPick.dirs = WKOpenPanelParametersGetAllowsDirectories(params);
    std::vector<std::string> accept;
    for (auto copy : { WKOpenPanelParametersCopyAcceptedMIMETypes, WKOpenPanelParametersCopyAcceptedFileExtensions }) {
        auto list = adoptWK(copy(params));
        const size_t n = list ? WKArrayGetSize(list.get()) : 0;
        for (size_t i = 0; i < n && i < 64; ++i) {
            WKTypeRef item = WKArrayGetItemAtIndex(list.get(), i);
            if (item && WKGetTypeID(item) == WKStringGetTypeID()) accept.push_back(OmniTest::toStd(static_cast<WKStringRef>(item)));
        }
    }
    for (auto& a : accept) {
        if (a.empty()) continue;
        if (!omniPick.acceptText.empty()) omniPick.acceptText += ", ";
        omniPick.acceptText += a;
        if (a.find('/') != std::string::npos) omniPickAddMime(omniPick.exts, a);
        else omniPick.exts.push_back(omniLower(a[0] == '.' ? a.substr(1) : a));
    }
    if (omniPick.acceptText.size() > 60) omniPick.acceptText = omniPick.acceptText.substr(0, 57) + "...";
    if (!omniPick.acceptText.empty()) omniPick.acceptText = "accepts " + omniPick.acceptText;
    if (omniPick.exts.empty()) omniPick.acceptText.clear();   // nothing we can filter by: show every file
    if (omniNativeTitle()) omniOfbCleanUploads(3600);   // OMNI_FILES_BROKER_V1: copies from earlier pickers
    if (editing) dismissKeyboard();
    omniFxCloseAll();
    // Start in the downloads folder when it has something, else in the list of places.
    const std::string dl = omniData("downloads");
    if (omniPickIsDir(dl)) omniPickGo(dl, dl); else omniPickGo("", "");
    omniPickShow();
}
// OMNI_FILES_BROKER_V1: finishes broker copy jobs on the main thread, and the files self-test
// (native title only, /data/omni/native/files-selftest.flag): starts the broker, lists its places
// through the picker, copies one USB file in and compares it; with no drive it checks that the broker
// refuses everything outside /mnt/usb*, /mnt/ext*. Then Omni exits normally (never killed).
static bool omniOfbSelfTestDone = false;
static void omniOfbSelfTestFinish(bool pass, const std::string& what)
{
    log(("FILES SELFTEST " + std::string(pass ? "PASS" : "FAIL") + ": " + what).c_str());
    omniOfbCleanUploads(0);
    omniPick = OmniPick();
    running = false;
}
static bool omniOfbRefusalsOk(std::string& detail)
{
    std::string sink;
    const int hello = omniOfbCall("hello", "", "", nullptr, 0, &sink);
    const int user = omniOfbCall("list", "/user/home", "", nullptr, 0, &sink);
    const int dots = omniOfbCall("list", "/mnt/usb0/../../user", "", nullptr, 0, &sink);
    const int data = omniOfbCall("read", "/data/omni/native/broker.token", "0\t32", nullptr, 0, &sink);
    const int sysd = omniOfbCall("list", "/system_data/priv", "", nullptr, 0, &sink);
    detail = "hello=" + std::to_string(hello) + " /user=" + std::to_string(user) + " dotdot=" + std::to_string(dots)
        + " /data=" + std::to_string(data) + " /system_data=" + std::to_string(sysd);
    return hello == 0 && user == EACCES && dots == EACCES && data == EACCES && sysd == EACCES;
}
static void omniOfbSelfTestTick()
{
    static const uint32_t start = SDL_GetTicks();
    if (omniOfbSelfTestDone || !omniNativeTitle() || SDL_GetTicks() - start < 8000) return;
    omniOfbSelfTestDone = true;
    if (access("/data/omni/native/files-selftest.flag", F_OK)) return;
    if (omniPick.listener) { log("FILES SELFTEST: a picker is open, skipped"); return; }
    log("FILES SELFTEST: start (OMNI_FILES_BROKER_V1)");
    omniPick = OmniPick();
    const auto places = omniPickPlaces();   // the picker's own path: starts the broker on first use
    std::vector<OmniPickPlace> usb;
    for (auto& p : places) {
        log(("FILES SELFTEST: place " + p.label + " = " + p.path).c_str());
        if (omniOfbRemote(p.path)) usb.push_back(p);
    }
    std::string refusals;
    const bool refuse = omniOfbRefusalsOk(refusals);
    log(("FILES SELFTEST: refusals " + refusals + (refuse ? " (ok)" : " (WRONG)")).c_str());
    if (usb.empty()) { omniOfbSelfTestFinish(refuse, "no USB drive; broker up and refusing everything outside the USB roots: " + refusals); return; }
    omniPickGo(usb[0].path, usb[0].path);   // the picker's directory scan through the broker
    std::string pick;
    long long size = 0;
    for (auto& e : omniPick.entries)
        if (!e.dir && e.size > 0 && e.size <= (64LL << 20)) { pick = usb[0].path + "/" + e.name; size = e.size; break; }
    log(("FILES SELFTEST: " + usb[0].path + " lists " + std::to_string(omniPick.entries.size()) + " entries").c_str());
    if (pick.empty()) { omniOfbSelfTestFinish(refuse, "listed " + usb[0].path + " (" + std::to_string(omniPick.entries.size()) + " entries) but found no file up to 64 MB to copy; " + refusals); return; }
    log(("FILES SELFTEST: copying " + pick + " (" + std::to_string(size) + " bytes)").c_str());
    mkdir(omniData("uploads").c_str(), 0777);
    omniOfbStart(3, [pick, size, refuse]() {
        const std::string dest = omniData("uploads/") + "selftest-" + omniSafeFileName(omniOfbBaseName(pick));
        const int err = omniOfbCopyIn(pick, dest);
        if (err) { omniOfbJob.error = "copy failed: " + omniOfbErr(err); omniOfbJob.state = 3; return; }
        struct stat st {};
        stat(dest.c_str(), &st);
        std::string head;
        const long long n = std::min<long long>(4096, size);
        const int rerr = omniOfbCall("read", pick, "0\t" + std::to_string(n), nullptr, 0, &head);
        std::string local(size_t(n), '\0');
        if (FILE* f = fopen(dest.c_str(), "rb")) { local.resize(fread(&local[0], 1, size_t(n), f)); fclose(f); }
        const bool same = !rerr && head == local && (long long)st.st_size == size;
        omniOfbJob.results = { dest, std::to_string(st.st_size), same ? "match" : "MISMATCH", refuse ? "refusals ok" : "refusals WRONG" };
        omniOfbJob.state = (same && refuse) ? 2 : 3;
        if (!same) omniOfbJob.error = "copied file differs (size " + std::to_string(st.st_size) + " of " + std::to_string(size) + ")";
        else if (!refuse) omniOfbJob.error = "refusals wrong";
    });
}
static void omniOfbTick()
{
    omniOfbSelfTestTick();
    const int st = omniOfbJob.state.load();
    if (st == 1) {
        const long long total = omniOfbJob.total.load(), done = omniOfbJob.done.load();
        if (omniOfbJob.kind != 3 && total > (8LL << 20) && SDL_GetTicks() - omniOfbJob.lastNotice > 1000) {
            omniOfbJob.lastNotice = SDL_GetTicks();
            notice(std::string(omniOfbJob.kind == 1 ? "Copying from the USB drive: " : "Copying to the USB drive: ") + std::to_string(int(100.0 * done / total)) + "%");
        }
        return;
    }
    if (st != 2 && st != 3) return;
    if (omniOfbThread.joinable()) omniOfbThread.join();
    const int kind = omniOfbJob.kind;
    const auto results = omniOfbJob.results;
    const std::string error = omniOfbJob.error;
    omniOfbJob.state = 0;
    if (kind == 1) {
        omniPick.copying = false;
        const bool tabGone = !omniTabAlive(omniPick.tab) || omniPick.tab != active();
        if (st == 3) { notice(error); omniPickFinish({}); }
        else if (tabGone) { notice("Upload cancelled: the tab changed"); omniPickFinish({}); }
        else omniPickFinish(results);
    } else if (kind == 2) {
        notice(st == 2 ? "Copied to " + results[0] : error);
    } else if (kind == 3) {
        std::string what = st == 2 ? "copied " + results[0] + " (" + results[1] + " bytes, " + results[2] + ", " + results[3] + ")" : error;
        omniOfbSelfTestFinish(st == 2, what);
    }
}
// Per pass: a picker that was closed without a choice (Circle, Options, a tab switch) cancels.
static void omniPickTick()
{
    omniOfbTick();   // OMNI_FILES_BROKER_V1: copy jobs, the files self-test
    if (!omniPick.listener) return;
    if (omniPick.copying) return;   // the copy job finishes (or cancels) the hand-off
    bool open = false;
    for (auto& p : omniFxStack) open |= p.kind == omniPickKind;
    const bool tabGone = !omniTabAlive(omniPick.tab) || omniPick.tab != active();
    if (open && !tabGone) return;
    if (open) for (auto it = omniFxStack.begin(); it != omniFxStack.end(); ++it) if (it->kind == omniPickKind) { omniFxStack.erase(it, omniFxStack.end()); omniShellDirty = true; break; }
    omniPickFinish({});
}
