// OMNI_TAB_SLEEP_V1: Browser settings > "Sleep idle tabs" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace) after the Background audio shell (OMNI_BG_AUDIO_V1), so after OmniTabMemory.h (omniTmUnloadOne,
// omniTmCanUnload), OmniTabMemoryViewShell.h (omniTmvForce, omniTmvKept), OmniPinnedTabsShell.h, OmniTabGroupsShell.h
// and OmniDlProgressShell.h (omniDlp). The pure part is OmniTabSleep.h; the reasons are in tools/apply_tab_sleep.py.
// Main thread only. Cost: while the setting is Off, one branch per pass. On: one check a minute (a loop over the tabs,
// at most 2 one-shot page scripts, at most 2 unloads); nothing else in between.
#pragma once

namespace OTSP = OmniTabSleep;

struct OmniTspTab {
    uint32_t seenAt = 0;              // first seen by a check (a tab opened in the background has no shownAt yet)
    uint32_t stint = 0;               // the shownAt the verdict belongs to (shown again: asked again)
    OTSP::Verdict verdict = OTSP::kUnknown;
    uint32_t probeAt = 0, token = 0;  // the page script in flight
    bool asleep = false;              // put to sleep by this feature ...
    uint32_t asleepShownAt = 0;       // ... while its shownAt still is this (shown again: no longer "Asleep")
};
static OTSP::Settings omniTspSet;
static bool omniTspLoaded = false, omniTspPrimed = false, omniTspReady = false;
static uint32_t omniTspCheckAt = 0, omniTspToken = 0;
static std::unordered_map<const void*, OmniTspTab> omniTspTabs;

static void omniTspLoad()
{
    if (omniTspLoaded) return;
    omniTspLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData(OTSP::kFileName).c_str(), "r")) {
        char b[256];
        size_t n = 0;
        while ((n = fread(b, 1, sizeof(b), f)) > 0 && text.size() < 4096) text.append(b, n);
        fclose(f);
    }
    omniTspSet = OTSP::parse(text);   // no file: Settings{} (30 min, pinned tabs excluded)
}
static void omniTspSave() { omniIoQueue(omniData(OTSP::kFileName), OTSP::serialize(omniTspSet), false); }

static uint32_t omniTspShownAt(const Tab& t)
{
    auto f = omniTmTabs.find(&t);
    return f != omniTmTabs.end() ? f->second.shownAt : 0;
}
// Declared in OmniFeatures3Decl.h: the Tabs panel (omniF3TabRowValue) and the Memory panel show "Asleep".
static bool omniTspAsleep(const Tab& t)
{
    if (!omniTmIsUnloaded(t)) return false;
    auto f = omniTspTabs.find(&t);
    return f != omniTspTabs.end() && f->second.asleep && f->second.asleepShownAt == omniTspShownAt(t);
}
static void omniTspForget(const void* tab) { omniTspTabs.erase(tab); }
// A WebKit download running, the Downloads app's progress showing, or a hand-over in its 10 s window: nothing sleeps.
static bool omniTspDownloadsBusy() { return !omniDownloads.empty() || omniDlp.visible() || omniDlp.handover(); }

static OTSP::Cand omniTspCand(const Tab& t, uint32_t now)
{
    OmniTspTab& s = omniTspTabs[&t];
    if (!s.seenAt) s.seenAt = now ? now : 1;
    const uint32_t shown = omniTspShownAt(t);
    if (s.stint != shown) { s.stint = shown; s.verdict = OTSP::kUnknown; s.probeAt = 0; s.token = 0; }
    if (s.verdict == OTSP::kProbing && OTSP::probeTimedOut(now, s.probeAt)) { s.verdict = OTSP::kUnknown; s.token = 0; }
    OTSP::Cand c;
    c.free = omniTmCanUnload(t);   // shown, unloaded, loading, crashed, media section, not a web page, playing
    c.sound = t.omniTaBadge != 0;
    c.priv = t.omniPrivate;
    c.pinned = omniPtPinned(t);
    c.kept = omniTmvKept(t);
    c.collapsed = omniTgCollapsedTab(t);
    c.idleSince = shown ? shown : s.seenAt;
    c.verdict = s.verdict;
    return c;
}
static Tab* omniTspTabOf(const void* p)
{
    for (auto& t : tabs) if (t.get() == p) return t.get();
    return nullptr;
}
// One-shot page script: does this page hold unsaved input? The answer holds until the tab is shown again.
static void omniTspProbe(Tab& t, OmniTspTab& s, uint32_t now)
{
    if (!++omniTspToken) ++omniTspToken;
    s.verdict = OTSP::kProbing; s.probeAt = now; s.token = omniTspToken;
    auto script = adoptWK(WKStringCreateWithUTF8CString(OTSP::kProbeScript));
    WKPageEvaluateJavaScriptInMainFrame(t.page, script.get(), reinterpret_cast<void*>(uintptr_t(s.token)), [](WKTypeRef result, WKErrorRef error, void* context) {
        const uint32_t token = uint32_t(reinterpret_cast<uintptr_t>(context));
        std::string answer;
        if (!error && result && WKGetTypeID(result) == WKStringGetTypeID()) answer = OmniTest::toStd(static_cast<WKStringRef>(result));
        for (auto& e : omniTspTabs) {
            OmniTspTab& s = e.second;
            if (!token || s.token != token || s.verdict != OTSP::kProbing) continue;   // shown / closed meanwhile: dropped
            s.token = 0;
            s.verdict = OTSP::verdictOf(answer, error != nullptr);
            if (s.verdict == OTSP::kClean) { omniTspReady = true; return; }   // slept on the next pass (not inside WebKit's callback)
            const Tab* t = omniTspTabOf(e.first);
            fprintf(stderr, "OMNI TABSLEEP: stays awake (%s): %s\n", error ? "page script failed" : "unsaved input",
                t ? omniShownURL(t->url).substr(0, 80).c_str() : "?");
            fflush(stderr);
            return;
        }
    });
}
static bool omniTspSleep(Tab& t, OmniTspTab& s)
{
    omniTmvForce = &t;   // omniTmvPick: exactly this tab, if omniTmCanUnload still allows it
    const bool done = omniTmUnloadOne(OTSP::kUnloadWhy);
    omniTmvForce = nullptr;
    if (done) { s.asleep = true; s.asleepShownAt = omniTspShownAt(t); s.verdict = OTSP::kUnknown; }
    return done;
}
// omniF3Tick, every pass: returns at once unless a check is due (once a minute) or a page script answered "clean".
static void omniTspTick(uint32_t now)
{
    omniTspLoad();
    if (omniTspSet.minutes <= 0 || omniTestMode()) return;
    const bool due = OTSP::checkDue(now, omniTspCheckAt, omniTspPrimed);
    if (!due && !omniTspReady) return;
    const bool busy = omniTspDownloadsBusy();
    std::vector<OTSP::Cand> cs;
    cs.reserve(tabs.size());
    for (auto& t : tabs) cs.push_back(omniTspCand(*t, now));
    if (omniTspReady) {   // answers to this check's scripts (at most kMaxPerCheck): sleep the clean ones still eligible
        omniTspReady = false;
        for (size_t i = 0; i < tabs.size(); ++i) {
            OmniTspTab& s = omniTspTabs[tabs[i].get()];
            if (s.verdict == OTSP::kClean && s.probeAt == omniTspCheckAt && OTSP::decide(cs[i], now, omniTspSet, busy) == OTSP::kSleep)
                omniTspSleep(*tabs[i], s);
        }
    }
    if (!due) return;
    omniTspCheckAt = now;
    for (auto it = omniTspTabs.begin(); it != omniTspTabs.end();) it = omniTabAlive(it->first) ? std::next(it) : omniTspTabs.erase(it);
    for (int i : OTSP::pick(cs, now, omniTspSet, busy)) {
        Tab& t = *tabs[size_t(i)];
        OmniTspTab& s = omniTspTabs[&t];
        if (cs[size_t(i)].verdict == OTSP::kClean) omniTspSleep(t, s);   // answered "clean" earlier this stint
        else omniTspProbe(t, s, now);
    }
}

// --- Browser settings rows (omniF3SettingsRows, after "Tabs kept loaded"; input from omniF3SettingsInput) ----------
static void omniTspSettingsRows(OmniFxPanel& p)
{
    omniTspLoad();
    OmniFxRow r; r.id = OTSP::kRowMinutes; r.label = OTSP::label(); r.value = OTSP::minutesValue(omniTspSet.minutes);
    r.stepper = true; r.detail = OTSP::minutesDetail(omniTspSet.minutes);
    p.rows.push_back(r);
    OmniFxRow q; q.id = OTSP::kRowPinned; q.label = OTSP::pinnedLabel(); q.value = omniTspSet.pinned ? "On" : "Off";
    q.stepper = true; q.detail = OTSP::pinnedDetail(omniTspSet.pinned, omniTspSet.minutes);
    p.rows.push_back(q);
}
static bool omniTspSettingsInput(int id, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    const int dir = left ? -1 : (right || a) ? 1 : 0;
    if (!dir) return false;
    omniTspLoad();
    if (id == OTSP::kRowMinutes) {
        omniTspSet.minutes = OTSP::stepMinutes(omniTspSet.minutes, dir, a);
        notice(OTSP::minutesNotice(omniTspSet.minutes));
        omniTspCheckAt = SDL_GetTicks();   // the next check a minute from now
    } else {
        omniTspSet.pinned = !omniTspSet.pinned;
        notice(OTSP::pinnedNotice(omniTspSet.pinned));
    }
    omniTspSave();
    fprintf(stderr, "OMNI TABSLEEP: setting %d min, pinned %s\n", omniTspSet.minutes, omniTspSet.pinned ? "included" : "excluded");
    fflush(stderr);
    return true;
}
