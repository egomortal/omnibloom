// OMNI_FIND_PLUS_V1: the shell side of Find on page (included by OmniBrowser.cpp where OMNI_EVERYDAY_V1's find block
// was; keeps its entry points omniFindStart / omniFindBarOpen / omniFindButton / omniFindClick / omniFindDraw /
// omniEverydayTabCreated). Pure part: OmniFindPlus.h. Reasons: tools/apply_find_plus.py.
#pragma once

namespace OFND = OmniFindPlus;
static_assert(OFND::kCaseInsensitive == uint32_t(kWKFindOptionsCaseInsensitive) && OFND::kBackwards == uint32_t(kWKFindOptionsBackwards)
    && OFND::kWrapAround == uint32_t(kWKFindOptionsWrapAround) && OFND::kShowOverlay == uint32_t(kWKFindOptionsShowOverlay)
    && OFND::kShowFindIndicator == uint32_t(kWKFindOptionsShowFindIndicator) && OFND::kShowHighlight == uint32_t(kWKFindOptionsShowHighlight),
    "OMNI_FIND_PLUS_V1: WKFindOptions bits moved");

static OFND::Store omniFndStore;      // per tab, memory only (session); private tabs' states die with the tab
static std::string omniFindQuery;     // the keyboard's buffer while "Find on page" is typed

static OFND::State* omniFndActive()
{
    Tab* t = active();
    return t ? omniFndStore.find(OFND::key(t)) : nullptr;
}
static std::string omniFndString(WKStringRef s)
{
    if (!s) return std::string();
    std::string out(WKStringGetMaximumUTF8CStringSize(s), '\0');
    const size_t n = WKStringGetUTF8CString(s, out.data(), out.size());
    out.resize(n ? n - 1 : 0);   // n counts the terminating NUL
    return out;
}
static void omniFindRun(int step)
{
    Tab* t = active();
    OFND::State* s = omniFndActive();
    if (!t || !s || !s->open || s->query.empty()) return;
    s->begin(step);
    auto q = adoptWK(WKStringCreateWithUTF8CString(s->query.c_str()));
    WKPageFindString(t->page, q.get(), OFND::options(s->caseSensitive, step), OFND::kMaxMatches);
    omniShellDirty = true;
}
// Circle / Escape: the bar closes and WebKit drops every highlight and the indicator (FindController::hideFindUI).
static void omniFindClose()
{
    Tab* t = active();
    OFND::State* s = omniFndActive();
    if (!t || !s || !s->open) return;
    WKPageHideFindUI(t->page);
    s->close();
    omniShellDirty = omniPageDirty = true;
}
static void omniFndRetainAlive()
{
    std::vector<uintptr_t> alive;
    alive.reserve(tabs.size());
    for (auto& t : tabs) alive.push_back(OFND::key(t.get()));
    omniFndStore.retain(alive);
}
static void omniFindStart()
{
    Tab* t = active();
    if (!t) return;
    omniFndRetainAlive();
    const OFND::State* s = omniFndStore.find(OFND::key(t));
    omniFindQuery = s ? s->query : std::string();   // this tab's last search (never another tab's: private stays private)
    const void* tab = t;
    omniKbEdit(&omniFindQuery, "Find on page", [tab](bool submitted) {
        if (!submitted || omniFindQuery.empty() || !omniTabAlive(tab) || active() != tab) return;
        OFND::State& st = omniFndStore.at(OFND::key(tab));
        st.setQuery(omniFindQuery);
        st.open = true;
        omniFindRun(0);
    });
}
static bool omniFindBarOpen()
{
    if (pageFullscreen || editing) return false;
    const OFND::State* s = omniFndActive();
    return s && s->open;
}
static void omniFndToggleCase()
{
    OFND::State* s = omniFndActive();
    if (!s) return;
    s->caseSensitive = !s->caseSensitive;
    notice(OFND::caseNotice(s->caseSensitive));
    omniFindRun(0);   // search again with the new setting (the count changes)
}
static bool omniFindButton(int b)
{
    const OFND::Button pb = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? OFND::bDpadLeft : b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? OFND::bDpadRight
        : b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER ? OFND::bL1 : b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER ? OFND::bR1
        : b == SDL_CONTROLLER_BUTTON_Y ? OFND::bTriangle : b == SDL_CONTROLLER_BUTTON_X ? OFND::bSquare
        : b == SDL_CONTROLLER_BUTTON_B ? OFND::bCircle : OFND::bOther;
    switch (OFND::actionFor(pb)) {
    case OFND::Action::Next: omniFindRun(1); return true;
    case OFND::Action::Previous: omniFindRun(-1); return true;
    case OFND::Action::Edit: omniFindStart(); return true;
    case OFND::Action::ToggleCase: omniFndToggleCase(); return true;
    case OFND::Action::Close: omniFindClose(); return true;
    case OFND::Action::None: break;
    }
    return false;
}
static int omniFindY() { return std::max(8, omniPageTop() + 10); }
static bool omniFindClick(int x, int y)
{
    switch (OFND::hit(x - OFND::kBarX, y - omniFindY())) {
    case OFND::Hit::None: return false;
    case OFND::Hit::Close: omniFindClose(); break;
    case OFND::Hit::Next: omniFindRun(1); break;
    case OFND::Hit::Previous: omniFindRun(-1); break;
    case OFND::Hit::ToggleCase: omniFndToggleCase(); break;
    case OFND::Hit::Edit: omniFindStart(); break;
    }
    return true;
}
static void omniFindDraw()
{
    const OFND::State* s = omniFndActive();
    if (!s) return;
    const OmniTheme& T = omniTheme();
    const int x = OFND::kBarX, y = omniFindY(), w = OFND::kBarW, h = OFND::kBarH;
    const bool none = s->noMatches();
    omniShadow(x, y, w, h, omniRadius, 14, 140, 4);
    fillRounded(x, y, w, h, omniRadius, T.raised);
    if (none) fillRounded(x, y + h - 4, w, 4, 2, omniBad);   // a red underline: "no matches" seen from the sofa
    const float cy = y + h / 2.f;
    const int lw = omniLabel("Find", x + 16, cy, omniSmallBold, T.accent);
    omniLabel(s->query, x + 28 + lw, cy, omniBody, none ? omniBad : T.ink, 0, OFND::kQueryMaxW);
    // match case chip: filled when on
    const int cx = x + OFND::kChipX;
    if (s->caseSensitive) fillRounded(cx, y + 11, OFND::kChipW, 28, 8, T.accent);
    else fillRounded(cx, y + 11, OFND::kChipW, 28, 8, T.inkDim, 60);
    omniLabel(OFND::caseChip(), cx + OFND::kChipW / 2.f, cy, omniSmallBold, s->caseSensitive ? T.accentInk : T.inkDim, 1);
    const std::string count = OFND::countLabel(*s);
    if (none) {   // white on red, the same pill shape as the tips
        const int tw = int(omniTextWidthPx(omniSmallBold, count) / displayScale + 0.5);
        fillRounded(x + OFND::kCountRight - tw - 20, y + 11, tw + 20, 28, 14, omniBad);
        omniLabel(count, x + OFND::kCountRight - 10, cy, omniSmallBold, SDL_Color { 255, 255, 255, 255 }, 2);
    } else omniLabel(count, x + OFND::kCountRight, cy, omniSmall, T.inkDim, 2);
    omniIcon(omniIconBack, x + w - 125, cy, none ? T.inkDim : T.ink);
    omniIcon(omniIconForward, x + w - 75, cy, none ? T.inkDim : T.ink);
    omniIcon(omniIconClose, x + w - 25, cy, T.inkDim);
    {
        const std::string tip = OmniControlsHelp::expand(OFND::tipText(), playStationIcons);
        const int tw = int(omniTextWidthPx(omniCaption, tip) / displayScale + 0.5);
        fillRounded(x + w - tw - 24, y + h + 6, tw + 24, 24, 12, T.raised, 235);
        omniLabel(tip, x + w - 12, y + h + 18, omniCaption, T.inkDim, 2);
    }
}
// A navigation in the tab ends its find: the new page has no highlights. The query and case setting are kept.
static void omniFndFinished(Tab& tab)
{
    if (OFND::State* s = omniFndStore.find(OFND::key(&tab))) s->close();
}
static void omniEverydayTabCreated(Tab* tab)
{
    omniFndStore.erase(OFND::key(tab));   // the address may be a closed tab's: start clean
    omniFndRetainAlive();
    static WKPageFindClientV0 find {};
    find.base.version = 0;
    find.didFindString = [](WKPageRef page, WKStringRef string, unsigned matchCount, const void*) {
        Tab* t = omniTabForPage(page);
        OFND::State* s = t ? omniFndStore.find(OFND::key(t)) : nullptr;
        if (!s || !s->open) return;
        const OFND::Wrap w = s->found(omniFndString(string), matchCount);
        if (w != OFND::Wrap::None && t == active()) notice(OFND::wrapNotice(w));
        omniShellDirty = omniPageDirty = true;
    };
    find.didFailToFindString = [](WKPageRef page, WKStringRef string, const void*) {
        Tab* t = omniTabForPage(page);
        OFND::State* s = t ? omniFndStore.find(OFND::key(t)) : nullptr;
        if (!s || !s->open) return;
        s->failed(omniFndString(string));
        omniShellDirty = true;
    };
    find.didCountStringMatches = nullptr;   // the count comes with didFindString (marking counts); no second DOM walk
    WKPageSetPageFindClient(tab->page, &find.base);
}
