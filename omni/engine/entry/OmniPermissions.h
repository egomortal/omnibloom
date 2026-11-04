// OMNI_FEATURES_V2: site permissions. What this WebKit build can actually ask for:
//  - Pop-ups: per site Default / Allow / Block, with "open the blocked pop-up" (popup() hook).
//  - Storage access (an embedded site asking for its cookies inside another site, WebKit's
//    requestStorageAccess): a prompt with Allow / Allow once / Block, remembered per site.
//  - Location, notifications, camera and microphone are compiled out of this WebKit build
//    (ENABLE_GEOLOCATION / ENABLE_NOTIFICATIONS / ENABLE_MEDIA_STREAM are OFF), so pages never get
//    those APIs. The callbacks are still answered "deny" (with one notice per site and session) in
//    case a later build turns them on; the Site permissions page lists them as "Not available on PS5".
// Stored in /data/omni/site-permissions.txt (host, permission, 1 allow / 2 block). Decisions made in
// a private tab last for this session only.
#pragma once

struct OmniPermStore { std::map<std::string, std::map<std::string, int>> saved, session; bool loaded = false; };
static OmniPermStore omniPerm;
static void omniPermLoad()
{
    if (omniPerm.loaded) return;
    omniPerm.loaded = true;
    if (FILE* f = fopen(omniData("site-permissions.txt").c_str(), "r")) {
        char line[1200];
        while (fgets(line, sizeof(line), f)) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            const size_t a = s.find('\t'), b = a == std::string::npos ? a : s.find('\t', a + 1);
            if (b == std::string::npos) continue;
            const int v = atoi(s.c_str() + b + 1);
            if (a && b > a + 1 && (v == 1 || v == 2)) omniPerm.saved[s.substr(0, a)][s.substr(a + 1, b - a - 1)] = v;
        }
        fclose(f);
    }
}
static void omniPermSave()
{
    std::string out;
    for (auto& [host, perms] : omniPerm.saved)
        for (auto& [perm, v] : perms) out += omniOneLine(host, 300) + "\t" + omniOneLine(perm, 600) + "\t" + std::to_string(v) + "\n";
    omniIoQueue(omniData("site-permissions.txt"), std::move(out), false);
}
static int omniPermGet(const std::string& host, const std::string& perm)
{
    omniPermLoad();
    for (auto* m : { &omniPerm.session, &omniPerm.saved }) {
        auto h = m->find(host);
        if (h == m->end()) continue;
        auto p = h->second.find(perm);
        if (p != h->second.end()) return p->second;
    }
    return 0;
}
static void omniPermSet(const std::string& host, const std::string& perm, int v, bool persist)
{
    omniPermLoad();
    if (host.empty()) return;
    auto& m = persist ? omniPerm.saved : omniPerm.session;
    (persist ? omniPerm.session : omniPerm.saved)[host].erase(perm);
    if (v) m[host][perm] = v; else m[host].erase(perm);
    for (auto* x : { &omniPerm.saved, &omniPerm.session }) if (x->count(host) && (*x)[host].empty()) x->erase(host);
    if (persist) omniPermSave();
}
static void omniPermClearHost(const std::string& host)
{
    omniPermLoad();
    omniPerm.session.erase(host);
    if (omniPerm.saved.erase(host)) omniPermSave();
}
static std::map<std::string, int> omniPermFor(const std::string& host)
{
    omniPermLoad();
    std::map<std::string, int> all;
    for (auto* m : { &omniPerm.saved, &omniPerm.session }) { auto h = m->find(host); if (h != m->end()) for (auto& [k, v] : h->second) all[k] = v; }
    return all;
}

// --- pop-ups ---------------------------------------------------------------------------------------
struct OmniPermPopup { std::string host, target; };
static std::vector<OmniPermPopup> omniPermPopups;   // the last blocked pop-up of each site (this session)
static int omniF2PopupPolicy(WKPageRef, const std::string& opener, const std::string&, bool gesture)
{
    if (omniTestMode()) return 0;
    const std::string host = omniBlockerHostOf(opener);
    if (host.empty()) return 0;
    const int v = omniPermGet(host, "popups");
    if (v == 1) return 1;
    if (v == 2 && !gesture) return -1;
    return 0;
}
static void omniF2PopupBlocked(WKPageRef, const std::string& opener, const std::string& target)
{
    if (omniTestMode()) return;
    const std::string host = omniBlockerHostOf(opener);
    if (host.empty() || !omniWebURL(target)) return;
    omniPermPopups.erase(std::remove_if(omniPermPopups.begin(), omniPermPopups.end(), [&](const OmniPermPopup& p) { return p.host == host; }), omniPermPopups.end());
    omniPermPopups.push_back({ host, target });
    if (omniPermPopups.size() > 20) omniPermPopups.erase(omniPermPopups.begin());
    notice("Pop-up blocked. To open it: Options > Site settings > Site permissions");
}

// --- device permissions this build doesn't have ------------------------------------------------------
static std::vector<std::string> omniPermToldUnavailable;
static void omniPermUnavailable(WKSecurityOriginRef origin, const char* what)
{
    const std::string host = origin ? OmniTest::toStd(adoptWK(WKSecurityOriginCopyHost(origin)).get()) : std::string();
    const std::string key = host + "\t" + what;
    if (std::find(omniPermToldUnavailable.begin(), omniPermToldUnavailable.end(), key) != omniPermToldUnavailable.end()) return;
    omniPermToldUnavailable.push_back(key);
    notice(std::string(what) + " isn't available on PS5" + (host.empty() ? std::string() : ": " + host + " was told no"));
}

// --- storage access prompt -------------------------------------------------------------------------
struct OmniPermAsk { WKTypeRef listener = nullptr; const void* tab = nullptr; std::string host, other; bool priv = false, shown = false; };
static std::deque<OmniPermAsk> omniPermAsks;
enum { omniPermKindAsk = 7303, omniPermKindSite = 7301, omniPermKindAll = 7302 };
static void omniPermAnswer(OmniPermAsk& a, bool allow)
{
    if (!a.listener) return;
    WKPageRequestStorageAccessConfirmResultListenerCall(static_cast<WKPageRequestStorageAccessConfirmResultListenerRef>(a.listener), allow);
    WKRelease(a.listener);
    a.listener = nullptr;
}
static void omniPermStorageAccess(WKPageRef page, WKFrameRef, WKStringRef requesting, WKStringRef current, WKPageRequestStorageAccessConfirmResultListenerRef listener, const void*)
{
    Tab* t = omniTabForPage(page);
    if (!t || omniTestMode()) { WKPageRequestStorageAccessConfirmResultListenerCall(listener, true); return; }   // what WebKit did without a callback
    OmniPermAsk a;
    a.other = requesting ? OmniTest::toStd(requesting) : std::string();
    a.host = current ? OmniTest::toStd(current) : std::string();
    const int v = omniPermGet(a.host, "storage:" + a.other);
    if (v) { WKPageRequestStorageAccessConfirmResultListenerCall(listener, v == 1); return; }
    a.listener = WKRetain(listener); a.tab = t; a.priv = t->omniPrivate;
    omniPermAsks.push_back(std::move(a));
    omniShellDirty = true;
}
static bool omniPermAskInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A || omniPermAsks.empty()) return b == SDL_CONTROLLER_BUTTON_A;
    OmniPermAsk a = omniPermAsks.front();
    omniPermAsks.pop_front();
    if (r.id == 1 || r.id == 3) omniPermSet(a.host, "storage:" + a.other, r.id == 1 ? 1 : 2, !a.priv);
    omniPermAnswer(a, r.id != 3);
    omniFxPop();
    return true;
}
static void omniPermAskShow(OmniPermAsk& a)
{
    a.shown = true;
    OmniFxPanel p;
    p.kind = omniPermKindAsk; p.w = 820;
    p.title = a.other + " wants to use its cookies here";
    p.subtitle = "Inside " + a.host + ". This can keep you signed in to " + a.other + " in this page.";
    auto add = [&](int id, const char* label, const char* detail) { OmniFxRow r; r.id = id; r.label = label; r.detail = detail; p.rows.push_back(r); };
    add(1, "Allow", "remembered for this site");
    add(2, "Allow once", "this time only");
    add(3, "Block", "remembered for this site");
    p.input = omniPermAskInput;
    p.faces = { { 0, "Choose" }, { 1, "Not now" } };
    omniFxPush(std::move(p));
}
static void omniPermTick(bool canPrompt)
{
    if (omniPermAsks.empty()) return;
    OmniPermAsk& a = omniPermAsks.front();
    if (!omniTabAlive(a.tab)) { omniPermAnswer(a, false); omniPermAsks.pop_front(); return; }
    if (a.shown) {
        bool open = false;
        for (auto& p : omniFxStack) open |= p.kind == omniPermKindAsk;
        if (!open) { omniPermAnswer(a, false); omniPermAsks.pop_front(); }   // closed with Circle / Options: not now
        return;
    }
    if (canPrompt && a.tab == active()) omniPermAskShow(a);
}

// --- Site permissions page -------------------------------------------------------------------------
static std::string omniPermValueName(int v) { return v == 1 ? "Allowed" : v == 2 ? "Blocked" : "Default"; }
static void omniPermSiteBuild(OmniFxPanel& p)
{
    const std::string& host = p.page;
    const auto perms = omniPermFor(host);
    auto add = [&](int id, const std::string& label, std::string value, bool on, bool stepper = false) { OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.enabled = on; r.stepper = stepper; p.rows.push_back(r); return &p.rows.back(); };
    const int pop = perms.count("popups") ? perms.at("popups") : 0;
    add(1, "Pop-ups and redirects", pop ? omniPermValueName(pop) : std::string("Default"), true, true);
    for (auto& b : omniPermPopups) if (b.host == host) { add(2, "Open the blocked pop-up", "", true)->detail = omniShownURL(b.target); break; }
    int i = 0;
    for (auto& [k, v] : perms) {
        ++i;
        if (k.rfind("storage:", 0) != 0) continue;
        add(100 + i, "Cookies for " + k.substr(8), omniPermValueName(v), true);
    }
    add(10, "Location", "Not available on PS5", false);
    add(11, "Camera", "Not available on PS5", false);
    add(12, "Microphone", "Not available on PS5", false);
    add(13, "Notifications", "Not available on PS5", false);
    add(14, "Fullscreen", "Allowed (WebKit doesn't ask)", false);
    add(21, "Reset permissions for this site", "", !perms.empty())->danger = true;
}
static bool omniPermSiteInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (!r.enabled) return b == SDL_CONTROLLER_BUTTON_A;
    const std::string host = p.page;
    const bool a = b == SDL_CONTROLLER_BUTTON_A, left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    const bool persist = !(active() && active()->omniPrivate);
    if (r.id == 1) {
        if (!a && !left && !right) return false;
        const int v = omniPermGet(host, "popups");
        omniPermSet(host, "popups", (v + (left ? 2 : 1)) % 3, persist);
        return true;
    }
    if (r.id == 2) {
        if (!a) return false;
        for (auto it = omniPermPopups.begin(); it != omniPermPopups.end(); ++it) if (it->host == host) {
            const std::string url = it->target;
            omniPermPopups.erase(it);
            omniFxCloseAll();
            omniFxOpenInNewTab(url, false, false);
            break;
        }
        return true;
    }
    if (r.id > 100) {
        const auto perms = omniPermFor(host);
        int i = 0;
        for (auto& [k, v] : perms) if (++i == r.id - 100) {
            if (b == SDL_CONTROLLER_BUTTON_X) { omniPermSet(host, k, 0, true); omniPermSet(host, k, 0, false); return true; }
            if (a || left || right) { omniPermSet(host, k, v == 1 ? 2 : 1, persist); return true; }
        }
        return false;
    }
    if (r.id == 21 && a) { omniPermClearHost(host); notice("Permissions reset for " + host); return true; }
    return false;
}
static void omniPermSiteShow(const std::string& host)
{
    if (host.empty()) { notice("Open a website first"); return; }
    OmniFxPanel p;
    p.kind = omniPermKindSite; p.w = 820; p.page = host;
    p.title = "Site permissions"; p.subtitle = host;
    p.build = omniPermSiteBuild; p.input = omniPermSiteInput;
    p.faces = { { 0, "Change" }, { 2, "Forget" }, { 1, "Back" } };
    p.extra = "Pop-ups: Default blocks those a site opens without a press (when uBlock is on)";
    omniFxPush(std::move(p));
}
static void omniPermAllBuild(OmniFxPanel& p)
{
    omniPermLoad();
    std::map<std::string, int> hosts;
    for (auto* m : { &omniPerm.saved, &omniPerm.session }) for (auto& [h, perms] : *m) hosts[h] += int(perms.size());
    int i = 0;
    for (auto& [h, n] : hosts) {
        OmniFxRow r; r.id = 1000 + i++; r.label = h;
        const int pop = omniPermGet(h, "popups");
        r.value = pop ? "Pop-ups " + omniOneLine(omniLower(omniPermValueName(pop)), 20) : std::to_string(n) + (n == 1 ? " choice" : " choices");
        p.rows.push_back(r);
    }
    if (p.rows.empty()) { OmniFxRow r; r.id = 1; r.label = "No site has saved permissions yet"; r.enabled = false; p.rows.push_back(r); }
}
static bool omniPermAllInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (r.id < 1000) return b == SDL_CONTROLLER_BUTTON_A;
    if (b == SDL_CONTROLLER_BUTTON_A) { omniPermSiteShow(r.label); return true; }
    if (b == SDL_CONTROLLER_BUTTON_X) { omniPermClearHost(r.label); notice("Permissions reset for " + r.label); (void)p; return true; }
    return false;
}
static void omniPermAllShow()
{
    OmniFxPanel p;
    p.kind = omniPermKindAll; p.w = 820;
    p.title = "Site permissions"; p.subtitle = "Sites with a saved choice";
    p.build = omniPermAllBuild; p.input = omniPermAllInput;
    p.faces = { { 0, "Open" }, { 2, "Reset" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}

// --- WebKit callbacks ------------------------------------------------------------------------------
static void omniPermInstallUI(WKPageUIClientV19& ui)
{
    ui.requestStorageAccessConfirm = omniPermStorageAccess;
    ui.decidePolicyForGeolocationPermissionRequest = [](WKPageRef, WKFrameRef, WKSecurityOriginRef origin, WKGeolocationPermissionRequestRef r, const void*) {
        WKGeolocationPermissionRequestDeny(r); omniPermUnavailable(origin, "Location");
    };
    ui.decidePolicyForNotificationPermissionRequest = [](WKPageRef, WKSecurityOriginRef origin, WKNotificationPermissionRequestRef r, const void*) {
        WKNotificationPermissionRequestDeny(r); omniPermUnavailable(origin, "Notifications");
    };
    ui.decidePolicyForUserMediaPermissionRequest = [](WKPageRef, WKFrameRef, WKSecurityOriginRef origin, WKSecurityOriginRef, WKUserMediaPermissionRequestRef r, const void*) {
        const bool camera = WKUserMediaPermissionRequestRequiresCameraCapture(r);
        WKUserMediaPermissionRequestDeny(r, kWKPermissionDenied);
        omniPermUnavailable(origin, camera ? "Camera" : "Microphone");
    };
}
