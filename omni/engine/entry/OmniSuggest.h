// OMNI_FEATURES_V3: live search suggestions in the address bar, merged with the history and
// shortcut suggestions. The request goes through WebKit's own networking: a hidden page (a WKView
// that is never shown or painted, same context and data store as normal tabs) loads the chosen
// engine's OpenSearch suggest URL; its JSON arrives as a text document and is read back with
// WKPageGetContentsAsString. Everything is asynchronous IPC: nothing waits on the main thread.
// Typing is debounced (220 ms after the last change); one request at a time (a newer query
// replaces the queued one); a request older than 4 s is abandoned. Never for private tabs, URLs,
// self-test modes, or when switched off in Browser settings. After 3 failures in a row the
// remote part stays off until Omni restarts (logged); the hidden page closes after 60 s idle.
#pragma once

// OpenSearch suggest endpoints (same order as omniFxEngines; all answer ["query",["s1","s2",...]]).
static const char* const omniSgEndpoints[] = {
    "https://suggestqueries.google.com/complete/search?client=firefox&ie=utf-8&oe=utf-8&q=",
    "https://duckduckgo.com/ac/?type=list&q=",
    "https://api.bing.com/osjson.aspx?query=",
    "https://www.startpage.com/osuggestions?q=",
};
static WKRetainPtr<WKViewRef> omniSgView;
static std::string omniSgWant, omniSgInFlight, omniSgFor;   // query wanted / being fetched / that the results are for
static std::vector<std::string> omniSgResults;
static uint32_t omniSgWantAt = 0, omniSgStartedAt = 0, omniSgUsedAt = 0;
static int omniSgFailures = 0;
static uint64_t omniSgSerial = 0;

static std::string omniSgTrim(const std::string& v)
{
    const size_t a = v.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return std::string();
    return v.substr(a, v.find_last_not_of(" \t\r\n") - a + 1);
}
static std::string omniSgEncode(const std::string& v)
{
    std::string out;
    for (unsigned char c : v) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_') out += char(c);
        else { char hex[4]; snprintf(hex, sizeof(hex), "%%%02X", c); out += hex; }
    }
    return out;
}
static bool omniSgEligible(const std::string& q)
{
    if (q.empty() || q.size() > 120 || omniTestMode() || !omniF3Set.suggest || omniSgFailures >= 3) return false;
    if (!active() || active()->omniPrivate) return false;
    const std::string l = omniLower(q);
    if (l.find("://") != std::string::npos || l.rfind("www.", 0) == 0 || l.rfind("about:", 0) == 0) return false;
    if (l.find(' ') == std::string::npos && l.find('.') != std::string::npos && l.find('.') + 1 < l.size()) return false;   // looks like an address
    return true;
}
// Reads ["q",["a","b",...], ...]: the strings of the second element.
static std::vector<std::string> omniSgParse(const std::string& j)
{
    std::vector<std::string> out;
    size_t i = j.find('[');
    if (i == std::string::npos) return out;
    i = j.find('[', i + 1);
    if (i == std::string::npos) return out;
    for (++i; i < j.size() && out.size() < 10;) {
        while (i < j.size() && (j[i] == ' ' || j[i] == ',' || j[i] == '\n' || j[i] == '\r' || j[i] == '\t')) ++i;
        if (i >= j.size() || j[i] != '"') break;
        size_t e = i + 1;
        while (e < j.size() && j[e] != '"') e += j[e] == '\\' ? 2 : 1;
        if (e >= j.size()) break;
        std::string v;
        const std::string wrapped = "{\"s\":" + j.substr(i, e - i + 1) + "}";
        if (omniFxJsonString(wrapped, "s", v)) { v = omniSgTrim(v); if (!v.empty()) out.push_back(v); }
        i = e + 1;
    }
    return out;
}
static void omniSgClose()
{
    if (!omniSgView) return;
    WKPageClose(WKViewGetPage(omniSgView.get()));
    omniSgView = WKRetainPtr<WKViewRef>();
    omniSgInFlight.clear();
}
static void omniSgDone(bool ok, const std::string& text, uint64_t serial)
{
    if (serial != omniSgSerial || omniSgInFlight.empty()) return;   // a newer request replaced it, or it was abandoned (already counted) OMNI_FEATURES_V3_FIX1
    const std::string q = omniSgInFlight;
    omniSgInFlight.clear();
    std::vector<std::string> found = ok ? omniSgParse(text) : std::vector<std::string>();
    if (!ok || (found.empty() && text.find('[') == std::string::npos)) {
        if (++omniSgFailures >= 3) fprintf(stderr, "OMNI SUGGEST: 3 failures in a row; search suggestions off until restart\n");
        return;
    }
    omniSgFailures = 0;
    omniSgFor = q; omniSgResults = std::move(found);
    if (omniSuggestSelected() < 0 && omniSgTrim(address) == q) { omniSuggestFor = "\x01"; omniShellDirty = true; }   // re-merge on the next draw
}
static void omniSgStart(const std::string& q)
{
    if (!omniSgView) {
        auto config = adoptWK(WKPageConfigurationCreate());
        WKPageConfigurationSetContext(config.get(), context.get());
        WKPageConfigurationSetPreferences(config.get(), preferences.get());
        WKPageConfigurationSetWebsiteDataStore(config.get(), websiteDataStore.get());
        omniSgView = adoptWK(WKViewCreate(config.get()));
        WKViewSetSize(omniSgView.get(), WKSizeMake(320, 240));
        WKViewSetVisible(omniSgView.get(), false);
        WKViewSetActive(omniSgView.get(), false);
        WKPageNavigationClientV0 nav {};
        nav.base.version = 0; nav.base.clientInfo = nullptr;
        nav.didFinishNavigation = [](WKPageRef page, WKNavigationRef, WKTypeRef, const void*) {
            WKPageGetContentsAsString(page, reinterpret_cast<void*>(uintptr_t(omniSgSerial)), [](WKStringRef s, WKErrorRef error, void* ctx) {
                omniSgDone(!error && s, s ? OmniTest::toStd(s) : std::string(), uint64_t(uintptr_t(ctx)));
            });
        };
        nav.didFailProvisionalNavigation = [](WKPageRef, WKNavigationRef, WKErrorRef, WKTypeRef, const void*) { omniSgDone(false, std::string(), omniSgSerial); };
        nav.didFailNavigation = nav.didFailProvisionalNavigation;
        WKPageSetPageNavigationClient(WKViewGetPage(omniSgView.get()), &nav.base);
    }
    omniFxLoad();
    const int engine = std::clamp(omniFxSet.search, 0, int(sizeof(omniSgEndpoints) / sizeof(omniSgEndpoints[0])) - 1);
    const std::string url = std::string(omniSgEndpoints[engine]) + omniSgEncode(q);
    ++omniSgSerial;
    omniSgInFlight = q;
    omniSgStartedAt = omniSgUsedAt = SDL_GetTicks();
    auto u = adoptWK(WKURLCreateWithUTF8CString(url.c_str()));
    WKPageLoadURL(WKViewGetPage(omniSgView.get()), u.get());
}
static void omniSgTick(uint32_t now)
{
    if (!omniSgInFlight.empty() && now - omniSgStartedAt > 4000) {   // too slow: abandon it
        if (omniSgView) WKPageStopLoading(WKViewGetPage(omniSgView.get()));
        ++omniSgSerial; omniSgInFlight.clear();
        if (++omniSgFailures >= 3) fprintf(stderr, "OMNI SUGGEST: 3 failures in a row; search suggestions off until restart\n");
    }
    if (!omniSgWant.empty() && omniSgInFlight.empty() && omniSgWant != omniSgFor && now - omniSgWantAt >= 220) {
        if (editing && omniSgTrim(address) == omniSgWant && omniSgEligible(omniSgWant)) omniSgStart(omniSgWant);
        else omniSgWant.clear();
    }
    if (omniSgView && omniSgInFlight.empty() && now - omniSgUsedAt > 60000) omniSgClose();
}

// --- hooks ------------------------------------------------------------------------------------------
static std::string omniF3SuggestDetail() { return "Search " + omniFxSearchName(); }
static void omniF3SuggestMerge(std::vector<OmniSuggestion>& local)
{
    const std::string q = omniSgTrim(address);
    if (omniSgEligible(q)) {
        if (q != omniSgWant) { omniSgWant = q; omniSgWantAt = SDL_GetTicks(); }
    } else omniSgWant.clear();
    std::vector<OmniSuggestion> remote;
    if (omniSgEligible(q) && q == omniSgFor) {
        const std::string lq = omniLower(q);
        for (const auto& r : omniSgResults) {
            if (omniLower(r) == lq) continue;
            OmniSuggestion s; s.url = omniFxSearchPrefix() + omniSgEncode(r); s.title = r; s.search = true;
            remote.push_back(std::move(s));
        }
    }
    const size_t keepLocal = remote.empty() ? 5 : std::min<size_t>(local.size(), 3);
    for (size_t i = 0; i < local.size() && i < keepLocal; ++i) omniSuggestions.push_back(local[i]);
    for (size_t i = 0; i < remote.size() && omniSuggestions.size() < 5; ++i) omniSuggestions.push_back(remote[i]);
}
