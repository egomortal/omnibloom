// Included in Browser's existing anonymous namespace after saved-link helpers.
static OmniLinkReview::Gate omniLinkGate;
static OmniLinkReview::Context omniLinkPending, omniLinkLastHandoff;
static OmniLinkReview::ClearLatch omniLinkClearPending;
static uint32_t omniLinkStartedAt = 0, omniLinkHandoffAt = 0;
// OMNI_C52_FIX1 (review L1): destination of an R2 / Send current link / L1+R1 / menu press whose snapshot
// has not answered it yet (-1 = none). If the press is cancelled (navigation, dialog, tab switch, timeout,
// shutdown) instead of read, the next tick runs that button's old immediate path, so no press is dropped.
// L2 (destination 0) keeps its "dropped" semantics and is never owed.
static int omniLinkOwed = -1;

static OmniLinkReview::Context omniLinkContext()
{
    OmniLinkReview::Context result;
    auto* tab = active();
    // Native privacy/ownership checks precede ANY source URL getter or copy.
    if (!tab || tab->omniPrivate || tab->omniMediaSection || !omniMediaDownloadsEnabled
        || !running || omniTestMode() || tab->loading || tab->crashed || !tab->message.empty()
        || pageFullscreen || !omniSavedContext().enabled) return result;
    const auto url = omniSavedCurrentURL();
    if (!OmniLinkReview::validHttp(url) || OmniMediaSection::belongs(url, OmniMediaSection::base())) return result;
    result = { tab->omniMediaIdentity, tab->omniSavedDocument, reinterpret_cast<uintptr_t>(tab->page),
        omniSavedContext().pad, true, url };
    return result;
}
static bool omniLinkClearGui()
{
    if (!running) return false;
    bool deferred = false;
    for (const auto& tab : tabs) {
        if (!tab->omniMediaSection || tab->omniPrivate || tab->crashed) continue;
        if (tab->loading) { deferred = true; continue; }
        const auto url = adoptWK(WKPageCopyActiveURL(tab->page));
        if (!url) continue;
        const auto current = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
        if (current != OmniMediaSection::base() && current != OmniMediaSection::base() + "#view=saved") {
            if (OmniMediaSection::belongs(current, OmniMediaSection::base())) deferred = true;
            continue;
        }
        // Recheck the fixed trusted URI at execution too: an asynchronous clear
        // must not invoke a function supplied by a newly navigated remote page.
        auto script = adoptWK(WKStringCreateWithUTF8CString("if(location.href==='http://127.0.0.1:8765/downloads'||location.href==='http://127.0.0.1:8765/downloads#view=saved'){window.omniMediaController?.('candidates.clear')}"));
        WKPageCallAsyncJavaScriptWithoutUserGesture(tab->page, script.get(), nullptr, nullptr, nullptr, nullptr);
    }
    return !deferred;
}
static void omniLinkReviewCancel()
{
    omniLinkGate.cancel();
    omniLinkPending.url.clear();
    omniMediaCandidateWire.clear();
}
static void omniLinkClearHandoff()
{
    if (!omniLinkLastHandoff.tab) return;
    omniLinkLastHandoff = {};
    omniMediaCandidateWire.clear();
    omniLinkClearPending.request();
    omniLinkClearPending.acknowledge(omniLinkClearGui());
}
static bool omniLinkHandoffAlive()
{
    if (!omniLinkLastHandoff.tab) return true;
    for (const auto& tab : tabs) {
        if (tab->omniMediaIdentity != omniLinkLastHandoff.tab) continue;
        if (tab->omniPrivate || tab->omniMediaSection || tab->loading || tab->crashed
            || tab->omniSavedDocument != omniLinkLastHandoff.document
            || reinterpret_cast<uintptr_t>(tab->page) != omniLinkLastHandoff.page) return false;
        // A surviving source identity may remain in the background while its
        // manual review GUI is active. Never authorize from GUI-supplied g.
        return tab->url == omniLinkLastHandoff.url;
    }
    return false;
}
// OMNI_NET_GRABBER_V1: fold the active tab's network-observed manifests/media files into a snapshot
// wire that validateWire already accepted. The result is validated again with the same source and
// document; on any failure the original wire is kept unchanged. Protected (EME) snapshots are left
// alone, and an empty/failed snapshot keeps the existing source-page fallback.
// OMNI_NET_GRABBER_V1: URL to prefill from a validated wire: its first row when that row is a manifest
// or media file on an unprotected page, otherwise the page URL (empty = use the page URL).
static std::string omniNetTopCandidate(const std::string& wire, const std::string& page)
{
    auto value = JSON::Value::parseJSON(WTF::String::fromUTF8(wire));
    auto object = value ? value->asObject() : nullptr;
    auto rows = object ? object->getArray("rows"_s) : nullptr;
    if (!rows) return page;
    std::vector<OmniNetGrabber::Row> list;
    for (size_t i = 0; i < rows->length(); ++i) {
        auto row = rows->get(i)->asObject();
        auto evidence = row ? row->getArray("e"_s) : nullptr;
        if (!row || !evidence) return page;
        OmniNetGrabber::Row item;
        item.u = OmniLinkReview::utf8(row->getString("u"_s));
        item.k = OmniLinkReview::utf8(row->getString("k"_s));
        for (size_t j = 0; j < evidence->length(); ++j) item.e.push_back(OmniLinkReview::utf8(evidence->get(j)->asString()));
        list.push_back(std::move(item));
    }
    return OmniNetGrabber::topCandidate(list, page);
}
static void omniNetMergeWire(const OmniLinkReview::Context& source, std::string& wire)
{
    auto* tab = active();
    if (wire.empty() || !tab || tab->omniPrivate || tab->omniMediaSection
        || reinterpret_cast<uintptr_t>(tab->page) != source.page) return;
    if (tab->omniNetRing.manifests.empty() && tab->omniNetRing.media.empty()) return;
    auto value = JSON::Value::parseJSON(WTF::String::fromUTF8(wire));
    auto object = value ? value->asObject() : nullptr;
    auto rows = object ? object->getArray("rows"_s) : nullptr;
    if (!rows) return;
    std::vector<OmniNetGrabber::Row> snapshot;
    for (size_t i = 0; i < rows->length(); ++i) {
        auto row = rows->get(i)->asObject();
        auto score = row ? row->getInteger("s"_s) : std::nullopt;
        auto evidence = row ? row->getArray("e"_s) : nullptr;
        if (!row || !score || !evidence) return;
        OmniNetGrabber::Row item;
        item.u = OmniLinkReview::utf8(row->getString("u"_s));
        item.k = OmniLinkReview::utf8(row->getString("k"_s));
        item.s = *score;
        for (size_t j = 0; j < evidence->length(); ++j) item.e.push_back(OmniLinkReview::utf8(evidence->get(j)->asString()));
        snapshot.push_back(std::move(item));
    }
    bool truncated = object->getBoolean("t"_s).value_or(false);
    auto merged = OmniNetGrabber::merge(snapshot, tab->omniNetRing, [](const std::string& url) { return OmniLinkReview::validHttp(url); }, truncated);
    if (merged.empty()) return;
    // Drop the lowest-ranked rows until the 16 KiB encoded wire limit is met.
    for (size_t count = merged.size(); count >= 1; --count) {
        auto out = JSON::Object::create();
        out->setInteger("v"_s, 1);
        out->setString("g"_s, object->getString("g"_s));
        out->setString("p"_s, object->getString("p"_s));
        auto list = JSON::Array::create();
        for (size_t i = 0; i < count; ++i) {
            auto row = JSON::Object::create();
            row->setString("u"_s, WTF::String::fromUTF8(merged[i].u));
            row->setString("k"_s, WTF::String::fromUTF8(merged[i].k));
            row->setInteger("s"_s, merged[i].s);
            auto evidence = JSON::Array::create();
            for (const auto& code : merged[i].e) evidence->pushString(WTF::String::fromUTF8(code));
            row->setArray("e"_s, std::move(evidence));
            list->pushObject(std::move(row));
        }
        out->setArray("rows"_s, std::move(list));
        out->setBoolean("t"_s, truncated || count < merged.size());
        std::string candidate;
        if (OmniLinkReview::validateWire(out->toJSONString(), source.url, source.document, candidate)) { wire = std::move(candidate); return; }
    }
}
// OMNI_NET_GRABBER_V1: one snapshot + validate + network-merge path shared by every grab button and
// the grabber self-test. The destination only decides which existing downloads view receives the rows.
enum : int { omniLinkToSaved = 0, omniLinkToShare = 1, omniLinkToSection = 2 };
static int omniLinkDestination = omniLinkToSaved;
template<typename Result>
static std::string omniLinkWireFromResult(Result& result, const OmniLinkReview::Context& current)
{
    std::string wire;
    if (result) {
        auto api = result->toAPI();
        auto type = WebKit::toAPI(api.get());
        if (type && WKGetTypeID(type) == WKStringGetTypeID()) {
            auto string = static_cast<WKStringRef>(type);
            if (WKStringGetLength(string) <= 65536)
                OmniLinkReview::validateWire(WebKit::toImpl(string)->string(), current.url, current.document, wire);
        }
    }
    omniNetMergeWire(current, wire); // OMNI_NET_GRABBER_V1
    return wire;
}
template<typename Completion>
static bool omniLinkDispatchSnapshot(WKPageRef page, uint64_t document, Completion&& completion)
{
    std::string code = omniLinkSnapshotSource;
    const auto marker = code.find("__OMNI_DOCUMENT_GENERATION__");
    if (marker == std::string::npos) return false;
    code.replace(marker, sizeof("__OMNI_DOCUMENT_GENERATION__") - 1, std::to_string(document));
    auto script = adoptWK(WKStringCreateWithUTF8CString(code.c_str()));
    return OmniLinkReview::evaluateInNamedWorld(page, script.get(), std::forward<Completion>(completion));
}
// Rows (or none) go to the view the pressed button always opened. An empty wire is the old behaviour.
static void omniLinkDeliver(int destination, const OmniLinkReview::Context& current, const std::string& wire)
{
    if (destination == omniLinkToSaved) { omniMediaDownloadsOpenSaved(current.url, active()->omniSavedVideo.seen, wire); return; }
    if (wire.empty()) { omniMediaDownloadsOpen(destination == omniLinkToShare); return; }
    if (destination == omniLinkToShare) {
        // Prefill the top candidate (manifest first); the page URL stays available as the shared-page row.
        const auto top = omniNetTopCandidate(wire, current.url);
        omniMediaDownloadsRequest(false, false, true, top.empty() ? current.url : top, false, wire, current.url);
    } else omniMediaDownloadsRequest(false, false, false, "", false, wire, current.url); // section: no prefill, rows only
}
static void omniLinkSupersedeOwed() { if (omniLinkPending.url.empty()) omniLinkOwed = -1; } // OMNI_C52_FIX1: a newer press wins
static bool omniLinkReviewBegin(int destination)
{
    omniLinkSupersedeOwed();
    const auto source = omniLinkContext();
    const auto now = SDL_GetTicks();
    const auto serial = omniLinkGate.begin(source, now);
    if (!serial) return false; // Busy/blocked still permits existing source-page review.
    omniLinkPending = source; omniLinkStartedAt = now; omniLinkDestination = destination;
    omniLinkOwed = destination != omniLinkToSaved ? destination : -1; // OMNI_C52_FIX1: set before dispatch (a reply may come at once)
    const bool dispatched = omniLinkDispatchSnapshot(active()->page, source.document, [serial, destination](auto&& result) {
        const auto current = omniLinkContext();
        const bool allowed = omniLinkGate.mayRead(serial, current, SDL_GetTicks());
        // No result inspection, API conversion, source copy or GUI activation
        // occurs before this native public/tab/document/URL/controller check.
        omniLinkGate.finish(serial); omniLinkPending = {};
        if (!allowed) return; // OMNI_C52_FIX1: an owed press is answered by omniLinkReviewTick
        omniLinkOwed = -1;
        const std::string wire = omniLinkWireFromResult(result, current);
        if (!wire.empty()) { omniLinkClearPending.freshHandoff(); omniLinkLastHandoff = current; omniLinkHandoffAt = SDL_GetTicks(); }
        else omniLinkClearHandoff();
        omniLinkDeliver(destination, current, wire);
    });
    if (!dispatched) { omniLinkGate.finish(serial); omniLinkPending = {}; omniLinkOwed = -1; } // OMNI_C52_FIX1: the caller runs the old path
    return dispatched;
}
static void omniLinkReviewTick()
{
    const auto now = SDL_GetTicks();
    if (omniLinkClearPending.pending()) omniLinkClearPending.acknowledge(omniLinkClearGui());
    if (omniLinkOwed >= 0 && omniLinkPending.url.empty()) {
        // OMNI_C52_FIX1: the press was cancelled or invalidated (or its reply was refused) without delivery.
        // The old path re-reads the then-current tab and applies its own private/disabled/capacity checks.
        const int destination = omniLinkOwed;
        omniLinkOwed = -1;
        if (running) omniMediaDownloadsOpen(destination == omniLinkToShare);
    }
    if (!omniLinkGate.outstanding() && !omniLinkLastHandoff.tab) return;
    const auto current = omniLinkPending.url.empty() ? OmniLinkReview::Context {} : omniLinkContext();
    const bool fallback = omniLinkGate.outstanding() && OmniLinkReview::sameSource(omniLinkPending, current)
        && now - omniLinkStartedAt >= OmniLinkReview::Gate::timeoutMs;
    const bool invalidated = omniLinkGate.poll(current, now);
    if (invalidated) omniLinkPending = {};
    if (fallback && invalidated) { omniLinkOwed = -1; omniLinkDeliver(omniLinkDestination, current, ""); } // OMNI_NET_GRABBER_V1: each button's old fallback
    if (omniLinkLastHandoff.tab && (!omniMediaDownloadsEnabled || !omniLinkHandoffAlive()
            || now - omniLinkHandoffAt >= 600000)) omniLinkClearHandoff();
}

// OMNI_NET_GRABBER_TEST_V1: /data/omni/grabber-selftest.flag. About 15 s after the test page loads, run the
// snapshot + validateWire + network merge the grab buttons use, log the rows (one line each, at most 8),
// then "GRABBER TEST DONE" and exit. It never opens Media downloads and never contacts the worker.
static bool omniGrabberTestPending = false;
static void omniGrabberTestFinish(const char* line)
{
    if (line) log(line);
    log("GRABBER TEST DONE");
    running = false;
}
static void omniGrabberTestLogWire(const std::string& wire)
{
    auto value = wire.empty() ? nullptr : JSON::Value::parseJSON(WTF::String::fromUTF8(wire));
    auto object = value ? value->asObject() : nullptr;
    auto rows = object ? object->getArray("rows"_s) : nullptr;
    if (!rows || !rows->length()) {
        log(wire.empty() ? "GRABBER TEST: rows=0 (snapshot wire empty, invalid or protected)" : "GRABBER TEST: rows=0");
        return;
    }
    const size_t count = std::min<size_t>(rows->length(), 8);
    for (size_t i = 0; i < count; ++i) {
        auto row = rows->get(i)->asObject();
        if (!row) continue;
        std::string evidence;
        if (auto list = row->getArray("e"_s))
            for (size_t j = 0; j < list->length(); ++j) evidence += (j ? "+" : "") + OmniLinkReview::utf8(list->get(j)->asString());
        const auto kind = OmniLinkReview::utf8(row->getString("k"_s));
        const auto host = OmniNetGrabber::logHostPath(OmniLinkReview::utf8(row->getString("u"_s)));
        const int score = row->getInteger("s"_s).value_or(0);
        char line[512];
        if (!i) snprintf(line, sizeof line, "GRABBER TEST: rows=%zu first=%s,%d,%s url=%s", static_cast<size_t>(rows->length()), kind.c_str(), score, evidence.c_str(), host.c_str());
        else snprintf(line, sizeof line, "GRABBER TEST: row%zu=%s,%d,%s url=%s", i + 1, kind.c_str(), score, evidence.c_str(), host.c_str());
        log(line);
    }
}
static void omniGrabberTestRun()
{
    auto* tab = active();
    if (!tab || omniGrabberTestPending) return;
    omniGrabberTestPending = true;
    char line[160];
    snprintf(line, sizeof line, "GRABBER TEST: ring manifests=%zu media=%zu", tab->omniNetRing.manifests.size(), tab->omniNetRing.media.size());
    log(line);
    // The test page's own state (what the cross-origin player reported via postMessage), for diagnosis only.
    auto probe = adoptWK(WKStringCreateWithUTF8CString("JSON.stringify(window.grabberTestState||null).slice(0,300)"));
    WKPageEvaluateJavaScriptInMainFrame(tab->page, probe.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
        const auto state = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : std::string("unavailable");
        log(("GRABBER TEST: page=" + state).c_str());
        auto* tab = active();
        if (!running || !tab) return;
        OmniLinkReview::Context source;
        source.tab = tab->omniMediaIdentity; source.document = tab->omniSavedDocument;
        source.page = reinterpret_cast<uintptr_t>(tab->page); source.eligible = true;
        if (auto url = adoptWK(WKPageCopyActiveURL(tab->page))) source.url = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
        const bool dispatched = omniLinkDispatchSnapshot(tab->page, source.document, [source](auto&& result) {
            auto* now = active();
            if (!running) return;
            if (!now || reinterpret_cast<uintptr_t>(now->page) != source.page || now->omniSavedDocument != source.document) {
                omniGrabberTestFinish("GRABBER TEST FAIL: page changed during the snapshot"); return;
            }
            omniGrabberTestLogWire(omniLinkWireFromResult(result, source));
            omniGrabberTestFinish(nullptr);
        });
        if (!dispatched) omniGrabberTestFinish("GRABBER TEST FAIL: snapshot not dispatched");
    });
}
