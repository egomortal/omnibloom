// Included inside OmniBrowser.cpp's anonymous namespace after shell helpers.
// WebKit/SDL calls stay on the main loop. Worker startup only returns data.
static bool omniMediaDownloadsEnabled = false;
static uintptr_t omniMediaOriginIdentity = 0;
static uint64_t omniMediaOriginDocument = 0;
static std::string omniMediaOriginURL;
static std::string omniMediaCandidateWire;
static std::string omniMediaCandidatePage; // OMNI_NET_GRABBER_V1: source page of a wire sent to the form view
static bool omniMediaOriginFullscreen = false, omniMediaOriginPrivate = false;
static bool omniMediaSavedDestination = false, omniMediaCandidateProvided = false, omniMediaDetectedCandidate = false;
static void omniMediaDownloadsLoadPreference()
{
    omniMediaDownloadsEnabled = !omniTestMode() && !access(OmniMediaDownloads::preferencePath, F_OK);
    omniNetGrabberSyncAll(); // OMNI_C52_FIX1: add/remove the grabber's resource-load client on open tabs
}
static bool omniMediaOwns(const Tab& tab)
{
    return tab.omniMediaSection && OmniMediaSection::belongs(tab.url, OmniMediaSection::base());
}
static std::vector<OmniMediaSection::Tab> omniMediaTabSnapshot()
{
    std::vector<OmniMediaSection::Tab> snapshot;
    snapshot.reserve(tabs.size());
    for (auto& tab : tabs)
        snapshot.push_back({ tab->omniMediaIdentity, tab->omniMediaSection, tab->url });
    return snapshot;
}
static void omniMediaApplyPlan(const OmniMediaSection::Plan& result)
{
    using OmniMediaSection::Action;
    switch (result.action) {
    case Action::Create:
        if (auto* tab = newTab()) { tab->omniMediaSection = true; omniNetGrabberApply(*tab); /* OMNI_C52_FIX1 */ navigate(result.url); }
        break;
    case Action::Activate:
        for (size_t i = 0; i < tabs.size(); ++i)
            if (tabs[i]->omniMediaIdentity == result.key) {
                activate(i);
                if (!result.url.empty()) navigate(result.url);
                break;
            }
        break;
    case Action::Disabled: notice("Media downloads is disabled"); break;
    case Action::Unavailable: notice("Media downloads unavailable; browsing can continue"); break;
    case Action::Full: notice("Close a tab to open Media downloads"); break;
    case Action::PrivateLink: notice("Private links are not shared with Media downloads"); break;
    case Action::InvalidLink: notice("This page cannot be shared as a media link"); break;
    }
}
static void omniMediaDownloadsRequest(bool shareCurrentLink, bool saved, bool supplied,
    const std::string& candidate = "", bool detected = false, const std::string& wire = "", const std::string& wirePage = "")
{
    using OmniMediaSection::Action;
    const bool privateSource = shareCurrentLink && active() && active()->omniPrivate;
    // Never copy a private source URL, including into a transient startup request.
    if (privateSource) { omniMediaApplyPlan({ Action::PrivateLink, 0, "" }); return; }
    const std::string link = shareCurrentLink && active() ? active()->url : supplied ? candidate : "";
    const auto plan = OmniMediaSection::plan(omniMediaDownloadsEnabled, true, omniMediaTabSnapshot(), link, false);
    if (plan.action != Action::Create && plan.action != Action::Activate) { omniMediaApplyPlan(plan); return; }
    using OmniMediaDownloads::RequestResult;
    switch (OmniMediaDownloads::starter().request(omniMediaDownloadsEnabled, link, false)) {
    case RequestResult::Started:
        omniMediaOriginIdentity = active() ? active()->omniMediaIdentity : 0;
        omniMediaOriginDocument = active() ? active()->omniSavedDocument : 0;
        omniMediaOriginPrivate = active() && active()->omniPrivate;
        omniMediaOriginURL = active() && !omniMediaOriginPrivate ? active()->url : "";
        omniMediaOriginFullscreen = pageFullscreen;
        // Busy cannot replace the view/candidate of an already accepted request.
        omniMediaSavedDestination = saved;
        omniMediaCandidateProvided = supplied;
        omniMediaDetectedCandidate = detected && !link.empty();
        omniMediaCandidateWire = wire;
        omniMediaCandidatePage = wire.empty() ? "" : wirePage; // OMNI_NET_GRABBER_V1
        notice(saved ? "Opening saved links..." : "Opening Media downloads...");
        break;
    case RequestResult::Busy: notice("Media downloads is opening; browsing can continue"); break;
    case RequestResult::Disabled: notice("Media downloads is disabled"); break;
    case RequestResult::PrivateLink: notice("Private links are not shared with Media downloads"); break;
    case RequestResult::InvalidLink: notice("This page cannot be shared as a media link"); break;
    case RequestResult::ThreadError: notice("Media downloads could not start; browsing can continue"); break;
    }
}
static void omniMediaDownloadsOpen(bool shareCurrentLink)
{
    omniMediaDownloadsRequest(shareCurrentLink, false, false);
}
static void omniMediaDownloadsOpenSaved(const std::string& candidate, bool detected, const std::string& wire = "")
{
    omniMediaDownloadsRequest(false, true, true, candidate, detected, wire);
}
static void omniMediaDownloadsTick()
{
    if (!omniMediaDownloadsEnabled) return;
    OmniMediaDownloads::Completion completion;
    if (!OmniMediaDownloads::starter().take(completion)) return;
    const auto candidateWire = std::move(omniMediaCandidateWire);
    omniMediaCandidateWire.clear();
    const auto candidatePage = std::move(omniMediaCandidatePage); // OMNI_NET_GRABBER_V1
    omniMediaCandidatePage.clear();
    if (completion.outcome != OmniMediaDownloads::Outcome::Ready) {
        notice(OmniMediaDownloads::message(completion.outcome));
        return;
    }
    if (!active() || active()->omniMediaIdentity != omniMediaOriginIdentity
        || active()->omniSavedDocument != omniMediaOriginDocument || active()->omniPrivate != omniMediaOriginPrivate
        || (!omniMediaOriginPrivate && active()->url != omniMediaOriginURL)
        || (pageFullscreen && !omniMediaOriginFullscreen)) {
        notice("Media downloads is ready. Open it again when you want it.");
        return;
    }
    auto plan = OmniMediaSection::plan(omniMediaDownloadsEnabled, true, omniMediaTabSnapshot(), completion.link);
    if (omniMediaSavedDestination && (plan.action == OmniMediaSection::Action::Create || plan.action == OmniMediaSection::Action::Activate)) {
        plan.url = OmniMediaSection::base() + "#view=saved";
        if (omniMediaCandidateProvided)
            plan.url += "&candidate=" + OmniMediaSection::encode(completion.link)
                + "&detected=" + (omniMediaDetectedCandidate ? "1" : "0");
        if (!candidateWire.empty()) {
            const auto field = "&candidates=" + OmniMediaSection::encode(candidateWire);
            if (plan.url.size() + field.size() <= 32768) plan.url += field;
        }
    } else if (!candidateWire.empty() && !candidatePage.empty() && !plan.url.empty()
        && (plan.action == OmniMediaSection::Action::Create || plan.action == OmniMediaSection::Action::Activate)) {
        // OMNI_NET_GRABBER_V1: the form view keeps opening as before (with its #url= prefill, if any); the
        // grabbed rows ride along, and the page URL stays available as the shared-page candidate. An already
        // open section that would not navigate (no link) is only activated, as before.
        const auto field = std::string(plan.url.find('#') == std::string::npos ? "#" : "&")
            + "candidate=" + OmniMediaSection::encode(candidatePage) + "&detected=0&candidates=" + OmniMediaSection::encode(candidateWire);
        if (plan.url.size() + field.size() <= 32768) plan.url += field;
    }
    omniMediaApplyPlan(plan);
}
