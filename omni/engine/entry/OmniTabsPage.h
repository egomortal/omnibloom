// OMNI_FEATURES_V1: tab overview (switch, close, new, private) and reopen-closed-tab.
// The four-tab limit stays: every tab shares one web process (WKContextSetUsesSingleWebProcess) and
// memory on the console has not been measured with more; the overview makes four easier to manage.
#pragma once

static std::vector<std::pair<std::string, std::string>> omniFxClosed;   // url, title (newest last)
static void omniFxTabClosing(Tab& tab)
{
    if (!omniTestMode() && !tab.omniPrivate && omniWebURL(tab.url)) {
        omniFxClosed.emplace_back(tab.url, tab.title);
        if (omniFxClosed.size() > 10) omniFxClosed.erase(omniFxClosed.begin());
    }
    omniFxForgetTab(&tab);
}
static void omniFxReopenClosed()
{
    if (omniFxClosed.empty()) { notice("No closed tabs to reopen"); return; }
    const auto last = omniFxClosed.back();
    if (!newTab()) return; // OMNI_FEATURES_V3: newTab() says why (limit or memory)
    omniFxClosed.pop_back();
    navigate(last.first);
    notice("Reopened " + (last.second.empty() ? omniShownURL(last.first) : last.second));
}
// Opens `url` in a new tab; background: stay on the current tab. Private tabs open private tabs.
static bool omniFxOpenInNewTab(const std::string& url, bool background, bool forcePrivate)
{
    Tab* from = active();
    const size_t back = selected;
    const bool priv = forcePrivate || (from && from->omniPrivate);
    if (!omniF3TabAllowed()) return false; // OMNI_FEATURES_V3: limit setting + memory guard (it says why)
    if (priv) omniNewPrivateTab(); else if (!newTab()) return false;
    if (!active() || active() == from) return false;
    navigate(url);
    if (background && back < tabs.size()) { activate(back); notice("Opened in a background tab (R1 to view)"); }
    return true;
}

enum { omniFxTabNew = 100, omniFxTabPrivate, omniFxTabReopen };
static void omniFxTabsBuild(OmniFxPanel& p)
{
    for (size_t i = 0; i < tabs.size(); ++i) {
        const Tab& t = *tabs[i];
        OmniFxRow r; r.id = int(i);
        r.label = !t.title.empty() ? t.title : !t.url.empty() ? omniShownURL(t.url) : std::string("New tab");
        r.detail = t.url.empty() ? std::string() : omniShownURL(t.url);
        r.value = i == selected ? "Current" : t.crashed ? "Stopped" : t.loading ? "Loading" : t.omniPrivate ? "Private" : "";
        if (t.omniPrivate && i == selected) r.value = "Current, private";
        omniF3TabRowValue(t, i == selected, r.value); // OMNI_FEATURES_V3: "Unloaded"
        r.danger = t.crashed;
        p.rows.push_back(r);
    }
    OmniFxRow n; n.id = omniFxTabNew; n.label = "New tab"; n.icon = omniIconPlus; n.enabled = !omniF3TabsFull(); if (!n.enabled) n.value = "Tab limit reached"; // OMNI_FEATURES_V3
    p.rows.push_back(n);
    OmniFxRow v; v.id = omniFxTabPrivate; v.label = "New private tab"; v.icon = omniIconPlus; v.enabled = !omniF3TabsFull(); // OMNI_FEATURES_V3
    p.rows.push_back(v);
    OmniFxRow c; c.id = omniFxTabReopen; c.label = "Reopen closed tab"; c.icon = omniIconReload; c.enabled = !omniFxClosed.empty() && !omniF3TabsFull(); // OMNI_FEATURES_V3
    if (!omniFxClosed.empty()) c.value = omniFxClosed.back().second.empty() ? omniShownURL(omniFxClosed.back().first) : omniFxClosed.back().second;
    p.rows.push_back(c);
    p.corner = std::to_string(tabs.size()) + " of " + std::to_string(omniF3TabLimit()); // OMNI_FEATURES_V3
}
static bool omniFxTabsInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (r.id < int(tabs.size())) {
        if (b == SDL_CONTROLLER_BUTTON_A) { omniFxCloseAll(); activate(size_t(r.id)); return true; }
        if (b == SDL_CONTROLLER_BUTTON_X) {
            const Tab* keep = active() == tabs[r.id].get() ? nullptr : active();
            omniTmSkipRestore = true; activate(size_t(r.id)); omniTmSkipRestore = false; closeTab(); // OMNI_FEATURES_V3_FIX1
            if (keep) for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == keep) { activate(i); break; }
            p.sel = std::min(r.id, int(tabs.size()) - 1);
            return true;
        }
        return false;
    }
    if (b != SDL_CONTROLLER_BUTTON_A || !r.enabled) return r.id >= omniFxTabNew;
    omniFxCloseAll();
    if (r.id == omniFxTabNew) { if (newTab()) { omniOpenNewTabPage(active()); address.clear(); editing = true; omniKbPageReset(); } }
    else if (r.id == omniFxTabPrivate) omniNewPrivateTab();
    else if (r.id == omniFxTabReopen) omniFxReopenClosed();
    return true;
}
static void omniFxTabsShow()
{
    OmniFxPanel p;
    p.title = "Tabs"; p.w = 900; p.maxVisible = 8;
    p.build = omniFxTabsBuild; p.input = omniFxTabsInput;
    p.faces = { { 0, "Switch" }, { 2, "Close tab" }, { 1, "Back" } };
    omniFxPush(std::move(p));
    if (!omniFxStack.empty()) omniFxStack.back().sel = int(selected);
}
