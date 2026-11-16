// OMNI_AUTO_REFRESH_V1: hold Cross on a page > "Auto-refresh" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace) after OmniTabSleepShell.h, so after OmniTabMemory.h (omniTmIsUnloaded),
// OmniOfflineRetryShell.h (omniOrWatch, omniOrTabOffline), OmniDlProgressShell.h (omniDlpDrawn) and
// OmniSleepTimerShell.h (omniSt). The pure part is OmniAutoRefresh.h; the reasons are in tools/apply_auto_refresh.py.
// Main thread only. Cost: no tab with a timer: one branch per pass. Otherwise a look at the timers 4 times a second,
// one page script per due reload (the unsaved-input probe), and a top-bar redraw once a second while the shown tab's
// countdown is visible.
#pragma once

namespace OARF = OmniAutoRefresh;

struct OmniArfTab {
    OARF::Timer timer;
    std::string fromSite;             // the timer came from "Always for this site" for this site (leaving it: off)
    bool policyPost = false;          // the last main-frame navigation decided was a POST ...
    bool post = false;                // ... and the committed page came from it
    bool reader = false;              // Reader view committed (omniReader is cleared again when it finishes)
    bool probing = false, answered = false;
    uint32_t probeAt = 0, token = 0;
    OARF::Answer answer;
    OARF::Reason lastReason = OARF::kGo;   // skips are logged when the reason changes
    uint32_t reloads = 0;
    bool restorePending = false, reloadCommitted = false;   // the scroll fallback after our reload
    uint32_t reloadAt = 0;
    int savedX = 0, savedY = 0;
    std::string restoreURL;
};
static std::unordered_map<const void*, OmniArfTab> omniArfTabs;
static OARF::Sites omniArfSites;
static bool omniArfSitesLoaded = false, omniArfReady = false;
static int omniArfBusy = 0;                    // tabs with a timer or a pending scroll fallback (0: the tick returns)
static uint32_t omniArfLastTick = 0, omniArfToken = 0;
static std::string omniArfChipText;            // what the top bar shows now (a change redraws it)
static const void* omniArfMenuTab = nullptr;   // the tab the chooser was opened for

static void omniArfLoad()
{
    if (omniArfSitesLoaded) return;
    omniArfSitesLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData(OARF::kFileName).c_str(), "r")) {
        char b[512];
        size_t n = 0;
        while ((n = fread(b, 1, sizeof(b), f)) > 0 && text.size() < 65536) text.append(b, n);
        fclose(f);
    }
    omniArfSites = OARF::parseSites(text);
}
static void omniArfSave() { omniIoQueue(omniData(OARF::kFileName), OARF::serialize(omniArfSites), false); }
static void omniArfRecount()
{
    omniArfBusy = 0;
    for (auto& e : omniArfTabs) if (e.second.timer.on() || e.second.restorePending) ++omniArfBusy;
}
static void omniArfForget(const void* tab) { if (omniArfTabs.erase(tab)) omniArfRecount(); }

// --- what the rules look at ------------------------------------------------------------------------------------------
static OARF::Facts omniArfFacts(const Tab& t, const OmniArfTab& s, uint32_t now, bool cheap = false)
{
    OARF::Facts f;
    f.web = omniWebURL(t.url) && !t.omniPagesTab;
    f.reader = s.reader || t.omniReader;
    f.mediaApp = omniMediaOwns(t);
    if (cheap) return f;   // the chip: only "can this tab refresh at all"
    f.asleep = omniTmIsUnloaded(t);
    f.loading = t.loading;
    f.crashed = t.crashed;
    f.media = !f.asleep && t.page && !t.crashed && (WKPageGetMediaState(t.page) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo));
    f.shown = &t == active();
    f.typing = editing;
    f.sinceInputMs = uint32_t(now - omniLastInput);
    f.post = s.post;
    f.offline = omniOrWatch.indicator() || omniOrTabOffline(t);
    return f;
}

// --- navigation hooks (OmniBrowser.cpp omniEverydayNavigation) -------------------------------------------------------
// decidePolicyForNavigationAction, main frame: remember whether this navigation is a POST (a redirect's own decision,
// POST -> 303 -> GET, overwrites it).
static void omniArfPolicy(Tab& t, WKURLRequestRef request)
{
    std::string method;
    if (request) if (auto m = adoptWK(WKURLRequestCopyHTTPMethod(request))) method = OmniTest::toStd(m.get());
    for (char& c : method) if (c >= 'a' && c <= 'z') c = char(c - 'a' + 'A');
    const bool post = method == "POST";
    auto f = omniArfTabs.find(&t);
    if (f == omniArfTabs.end()) {
        if (!post) return;
        f = omniArfTabs.emplace(&t, OmniArfTab()).first;
    }
    f->second.policyPost = post;
}
// didCommitNavigation (tab.url is the new address): POST result, Reader view, a site's remembered interval, and the
// countdown starts again (our own reload included).
static void omniArfCommitted(Tab& t)
{
    const uint32_t now = SDL_GetTicks();
    std::string site;
    int rule = 0;
    if (!t.omniPrivate && omniWebURL(t.url)) {
        omniArfLoad();
        site = OARF::siteKey(t.url);
        rule = site.empty() ? 0 : omniArfSites.get(site);
    }
    auto f = omniArfTabs.find(&t);
    if (f == omniArfTabs.end()) {
        if (!rule) return;
        f = omniArfTabs.emplace(&t, OmniArfTab()).first;
    }
    OmniArfTab& s = f->second;
    s.post = s.policyPost;
    s.policyPost = false;
    s.reader = t.omniReader;
    s.probing = s.answered = false; s.token = 0;   // a question in flight belonged to the old page
    if (s.restorePending) s.reloadCommitted = true;
    if (rule && (!s.timer.on() || !s.fromSite.empty())) {
        if (s.timer.seconds != rule || s.fromSite != site) {
            fprintf(stderr, "OMNI AUTOREFRESH: every %d s (remembered for %s)\n", rule, site.c_str());
            fflush(stderr);
        }
        s.timer.seconds = rule;
        s.fromSite = site;
    } else if (!s.fromSite.empty() && s.fromSite != site) {   // left the remembered site (or private / not web)
        s.timer.set(0, now);
        s.fromSite.clear();
    }
    if (s.timer.on()) s.timer.restart(now);
    omniArfRecount();
}

// --- the round: probe, then reload or skip -------------------------------------------------------------------------
static void omniArfSkip(const Tab& t, OmniArfTab& s, OARF::Reason r, uint32_t now)
{
    s.timer.restart(now);   // tried again one interval later
    if (r == s.lastReason) return;
    s.lastReason = r;
    fprintf(stderr, "OMNI AUTOREFRESH: skipped (%s), next in %d s: %s\n", OARF::reasonText(r), s.timer.seconds, omniShownURL(t.url).substr(0, 80).c_str());
    fflush(stderr);
}
static void omniArfProbe(Tab& t, OmniArfTab& s, uint32_t now)
{
    if (!++omniArfToken) ++omniArfToken;
    s.probing = true; s.answered = false; s.probeAt = now; s.token = omniArfToken;
    const std::string js = OARF::probeScript(OmniTabSleep::kProbeScript);   // tab sleep's one-shot unsaved-input check
    auto script = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t.page, script.get(), reinterpret_cast<void*>(uintptr_t(s.token)), [](WKTypeRef result, WKErrorRef error, void* context) {
        const uint32_t token = uint32_t(reinterpret_cast<uintptr_t>(context));
        for (auto& e : omniArfTabs) {
            OmniArfTab& s = e.second;
            if (!token || s.token != token || !s.probing) continue;   // navigated / closed meanwhile: dropped
            s.token = 0;
            s.answered = true;
            s.answer = OARF::parseAnswer(omniFxResultString(result, error), error != nullptr);
            omniArfReady = true;   // acted on in the next pass (not inside WebKit's callback)
            return;
        }
    });
}
static void omniArfReload(Tab& t, OmniArfTab& s, uint32_t now)
{
    s.timer.restart(now);
    s.lastReason = OARF::kGo;
    if (OARF::wantsRestore(s.answer.y)) {
        s.restorePending = true; s.reloadCommitted = false; s.reloadAt = now;
        s.savedX = s.answer.x; s.savedY = s.answer.y; s.restoreURL = t.url;
    }
    if (++s.reloads == 1 || s.reloads % 20 == 0) {
        fprintf(stderr, "OMNI AUTOREFRESH: reload #%u (every %d s): %s\n", s.reloads, s.timer.seconds, omniShownURL(t.url).substr(0, 80).c_str());
        fflush(stderr);
    }
    WKPageReload(t.page);   // not ReloadFromOrigin: the HTTP cache revalidates as usual
}
// After our reload finished: WebKit has restored the scroll position from the history item; when the page still sits
// at the top (content built after the load event), one script scrolls back once.
static void omniArfRestoreStep(Tab& t, OmniArfTab& s, uint32_t now)
{
    if (t.url != s.restoreURL || OARF::reached(now, s.reloadAt + OARF::kRestoreWindowMs) || t.crashed) { s.restorePending = false; return; }
    if (!s.reloadCommitted || t.loading || int32_t(t.loadedAt - s.reloadAt) < 0 || !OARF::reached(now, t.loadedAt + OARF::kRestoreDelayMs)) return;
    s.restorePending = false;
    auto script = adoptWK(WKStringCreateWithUTF8CString(OARF::restoreScript(s.savedX, s.savedY).c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t.page, script.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) {});
}
// omniF3Tick, every pass.
static void omniArfTick(uint32_t now)
{
    if (!omniArfBusy || omniTestMode()) return;
    if (!omniArfReady && uint32_t(now - omniArfLastTick) < OARF::kTickMs) return;
    omniArfLastTick = now;
    omniArfReady = false;
    bool recount = false;
    for (auto& tp : tabs) {
        Tab& t = *tp;
        auto f = omniArfTabs.find(&t);
        if (f == omniArfTabs.end()) continue;
        OmniArfTab& s = f->second;
        if (s.restorePending) { omniArfRestoreStep(t, s, now); recount |= !s.restorePending; }
        if (!s.timer.on()) continue;
        if (s.probing) {
            if (s.answered) {
                s.probing = s.answered = false;
                const OARF::Reason r = !s.answer.clean ? OARF::kUnsaved : OARF::decide(omniArfFacts(t, s, now));   // re-checked now
                if (r == OARF::kGo) omniArfReload(t, s, now);
                else omniArfSkip(t, s, r, now);
            } else if (OARF::reached(now, s.probeAt + OARF::kProbeTimeoutMs)) {
                s.probing = false; s.token = 0;
                omniArfSkip(t, s, OARF::kNoAnswer, now);
            }
            continue;
        }
        if (!s.timer.isDue(now)) continue;
        const OARF::Reason r = OARF::decide(omniArfFacts(t, s, now));
        if (r == OARF::kNever) s.timer.restart(now);   // omni:// / Reader view / Downloads: silently waits
        else if (r != OARF::kGo) omniArfSkip(t, s, r, now);
        else omniArfProbe(t, s, now);
    }
    if (recount) omniArfRecount();
    // the shown tab's countdown: redraw the top bar when its text changes (once a second), only while the bars show
    std::string chip;
    if (Tab* a = active()) {
        auto f = omniArfTabs.find(a);
        if (f != omniArfTabs.end() && OARF::chipShown(f->second.timer, omniArfFacts(*a, f->second, now, true)))
            chip = OARF::countdown(f->second.probing ? 0u : f->second.timer.remainingMs(now));
    }
    if (chip != omniArfChipText && (omniChromeShown > 0 || chip.empty())) { omniArfChipText = chip; omniShellDirty = true; }
}

// --- top bar (omniDrawTopBar, right of the downloads indicator) ------------------------------------------------------
static void omniArfDrawTopBar(float base)
{
    Tab* t = active();
    if (!t || !omniArfBusy) return;
    auto f = omniArfTabs.find(t);
    if (f == omniArfTabs.end()) return;
    const uint32_t now = SDL_GetTicks();
    const OmniArfTab& s = f->second;
    if (!OARF::chipShown(s.timer, omniArfFacts(*t, s, now, true))) return;
    float x = 0;
    if (omniDlpDrawn.mode) x = omniDlpDrawn.x + omniDlpDrawn.w + OARF::kBadgeGap;   // drawn just before us this frame
    else {   // where the downloads indicator would start: after the sleep timer and the offline badge (as it computes)
        const float sleepW = omniSt.on() ? float(omniTextWidthPx(omniCaption, omniSt.badge(now)) / displayScale) : 0.f;
        int offMode = 0, offTextMax = 0;
        float offX = 0, offTextW = 0;
        if (omniOrWatch.indicator()) {
            offTextW = float(omniTextWidthPx(omniCaptionBold, OOR::kBadge) / displayScale);
            const OOR::BadgeLayout o = OOR::badgeLayout(base, sleepW, offTextW);
            offMode = o.mode; offX = o.x; offTextMax = o.textMax;
        }
        x = ODLP::startX(base, sleepW, offMode, offX, offTextW, offTextMax);
    }
    const std::string text = OARF::countdown(s.probing ? 0u : s.timer.remainingMs(now));
    const OARF::Chip c = OARF::chipLayout(x, float(omniTextWidthPx(omniCaption, text) / displayScale));
    if (!c.mode) return;
    const OmniTheme& T = omniTheme();
    omniIcon(omniIconReload, c.x + OARF::kIconW / 2, 30, T.inkDim);
    if (c.mode == 2) omniLabel(text, c.x + OARF::kIconW + OARF::kTextGap, 30, omniCaption, T.inkDim, 0, c.textMax);
    omniArfChipText = text;
}

// --- the chooser (page menu > Auto-refresh) ---------------------------------------------------------------------------
static Tab* omniArfMenuTarget()
{
    Tab* t = active();
    return t && t == omniArfMenuTab && omniTabAlive(t) ? t : nullptr;
}
static void omniArfSet(Tab& t, int seconds)
{
    OmniArfTab& s = omniArfTabs[&t];
    s.timer.set(seconds, SDL_GetTicks());
    s.probing = s.answered = false; s.token = 0; s.lastReason = OARF::kGo;
    s.fromSite.clear();
    if (!t.omniPrivate) {   // a remembered site follows the new choice (Off forgets it)
        omniArfLoad();
        const std::string site = OARF::siteKey(t.url);
        if (!site.empty() && omniArfSites.get(site)) {
            if (omniArfSites.set(site, seconds)) omniArfSave();
            if (seconds) s.fromSite = site;
        }
    }
    omniArfRecount();
    fprintf(stderr, "OMNI AUTOREFRESH: tab set to %d s%s\n", seconds, s.fromSite.empty() ? "" : " (and its site)");
    fflush(stderr);
}
static void omniArfBuild(OmniFxPanel& p)
{
    Tab* t = omniArfMenuTarget();
    if (!t) return;
    omniArfLoad();
    const auto f = omniArfTabs.find(t);
    const int cur = f != omniArfTabs.end() ? f->second.timer.seconds : 0;
    for (int i = 0; i < OARF::kStepCount; ++i) {
        const int sec = OARF::steps()[i];
        OmniFxRow r; r.id = sec; r.label = OARF::choiceLabel(sec);
        if (sec == cur) { r.icon = omniIconCheck; r.value = "Current"; }
        p.rows.push_back(r);
    }
    const std::string site = t->omniPrivate ? std::string() : OARF::siteKey(t->url);
    const int rule = site.empty() ? 0 : omniArfSites.get(site);
    OmniFxRow r; r.id = OARF::kRowSite; r.label = "Always for this site"; r.value = rule ? "On" : "Off";
    r.enabled = !site.empty() && (rule || cur > 0);
    r.detail = t->omniPrivate ? std::string(OARF::privateDetail())
        : site.empty() ? std::string("Web pages only")
        : rule ? site + ": every " + OARF::choiceLabel(rule) + " in every tab"
        : cur > 0 ? "Remember every " + OARF::choiceLabel(cur) + " for " + site
        : std::string("Pick an interval first");
    p.rows.push_back(r);
}
static bool omniArfInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    Tab* t = omniArfMenuTarget();
    if (!t) { omniFxCloseAll(); return true; }
    if (r.id == OARF::kRowSite) {
        const std::string site = OARF::siteKey(t->url);
        if (t->omniPrivate || site.empty()) return true;
        omniArfLoad();
        OmniArfTab& s = omniArfTabs[t];
        const int sec = omniArfSites.get(site) ? 0 : s.timer.seconds;   // On -> Off forgets; Off -> On remembers the tab's
        if (omniArfSites.set(site, sec)) omniArfSave();
        s.fromSite = sec ? site : std::string();
        notice(OARF::siteNotice(site, sec));
        fprintf(stderr, "OMNI AUTOREFRESH: site %s %s\n", site.c_str(), sec ? "remembered" : "forgotten");
        fflush(stderr);
        omniFxRefresh();
        return true;
    }
    if (!OARF::validSeconds(r.id)) return true;
    omniArfSet(*t, r.id);
    notice(OARF::setNotice(r.id));
    omniFxCloseAll();
    omniShellDirty = true;
    return true;
}
static void omniArfOpen()
{
    Tab* t = active();
    if (!t) return;
    omniArfMenuTab = t;
    OmniFxPanel p;
    p.kind = OARF::kPanelKind; p.title = "Auto-refresh";
    p.subtitle = omniShownURL(t->url);
    p.w = 600;
    p.build = omniArfBuild; p.input = omniArfInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    p.extra = "Waits while you type, play media or have unsaved input";
    omniFxPush(std::move(p));
}

// --- hold-Cross page menu (declared in OmniFeatures3Decl.h) ----------------------------------------------------------
static void omniArfContextRow(OmniFxPanel& p)
{
    Tab* t = active();
    if (!t) return;
    const auto f = omniArfTabs.find(t);
    const int cur = f != omniArfTabs.end() ? f->second.timer.seconds : 0;
    OmniArfTab none;
    const OARF::Facts facts = omniArfFacts(*t, f != omniArfTabs.end() ? f->second : none, SDL_GetTicks(), true);
    OmniFxRow r; r.id = OARF::kContextId; r.label = "Auto-refresh"; r.value = OARF::rowValue(cur); r.icon = omniIconReload;
    r.enabled = cur > 0 || OARF::decide(facts) != OARF::kNever;   // a running timer can always be turned off
    p.rows.push_back(r);
}
static bool omniArfContextAction(int id)
{
    if (id != OARF::kContextId) return false;
    omniArfOpen();
    return true;
}
