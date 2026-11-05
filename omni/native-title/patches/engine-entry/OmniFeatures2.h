// OMNI_FEATURES_V2: saved logins + fill-on-demand, form autofill, file upload picker, site
// permissions. Included once from OmniBrowser.cpp just after OmniFeatures.h (inside its anonymous
// namespace, so every shell helper and the OmniFx panel are visible). Declarations used by the
// earlier hooks are in OmniFeatures2Decl.h. See outputs/changes/features-2/REPORT.md.
//
// Nothing here watches pages or reads what the user types into them: logins are added by hand and
// autofill/login values are written into a page only when the user chooses to, through a script that
// first checks the page's own origin. The only page->shell channels are the hit-test and keyboard
// probes that already existed.
#pragma once
#include "OmniF2Util.h"
#include "OmniPasswords.h"
#include "OmniAutofill.h"
#include "OmniPermissions.h"
#include "OmniFilePicker.h"

// --- keyboard fill strip: "Fill login" / "Fill form" above the keyboard for a page field ----------
// Shown while a webpage field is being edited and there is something to fill. Reached with Up from
// the top row of keys (like the address suggestions), or with the pointer. An overlay layer with
// blocksPage = false, so it never blocks the page; when nothing is focused it passes every button
// through to the keyboard (only Up at the top row enters it), exactly like omniSuggestButton.
static int omniF2FillSel = -1;
struct OmniF2FillItem { int id; std::string label; };
static std::vector<OmniF2FillItem> omniF2FillItems()
{
    std::vector<OmniF2FillItem> out;
    if (!editing || omniKb.kind != 1 || omniTestMode() || !active() || !omniFxStack.empty() || settingsOpen) return out;
    const std::string origin = omniF2OriginOf(active()->url);
    if (!omniPwFor(origin).empty()) out.push_back({ 1, "Fill login" });
    if (!omniAfEmpty()) { omniAfLoad(); if (omniAf.offer) out.push_back({ 2, "Fill form" }); }
    return out;
}
static bool omniF2FillOpen()
{
    const bool any = !omniF2FillItems().empty();
    if (!any) omniF2FillSel = -1;
    return any;
}
static void omniF2FillDo(int id)
{
    omniF2FillSel = -1;
    if (id == 1) omniPwFillCurrent();
    else if (id == 2) omniAfFill();
}
static bool omniF2FillButton(int b)
{
    const auto items = omniF2FillItems();
    const int n = int(items.size());
    if (n == 0) { omniF2FillSel = -1; return false; }
    if (omniF2FillSel < 0) {
        if (b == SDL_CONTROLLER_BUTTON_DPAD_UP && omniKbAtTopRow()) { omniF2FillSel = 0; omniShellDirty = true; return true; }
        return false;
    }
    omniF2FillSel = std::min(omniF2FillSel, n - 1);
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: if (omniF2FillSel > 0) --omniF2FillSel; omniShellDirty = true; return true;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: if (omniF2FillSel + 1 < n) ++omniF2FillSel; omniShellDirty = true; return true;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniF2FillSel = -1; omniShellDirty = true; return true;   // back to the keys
    case SDL_CONTROLLER_BUTTON_A: case SDL_CONTROLLER_BUTTON_Y: omniF2FillDo(items[omniF2FillSel].id); return true;
    case SDL_CONTROLLER_BUTTON_B: omniF2FillSel = -1; omniShellDirty = true; return true;
    default: return false;   // other buttons still reach the keyboard
    }
}
static void omniF2FillDraw()
{
    const auto items = omniF2FillItems();
    if (items.empty()) return;
    const OmniTheme& T = omniTheme();
    const int stripY = keyboardY - 58 - 48;
    int totalW = 20;
    std::vector<int> wds;
    for (auto& it : items) { const int w = int(omniTextWidthPx(omniSmall, it.label.c_str()) / displayScale + 0.5) + 44; wds.push_back(w); totalW += w + 8; }
    int x = (width - totalW) / 2;
    omniShadow(x, stripY, totalW, 40, omniRadius, 12, 120, 3);
    fillRounded(x, stripY, totalW, 40, omniRadius, T.raised);
    omniIcon(omniIconCheck, x + 18, stripY + 20, T.inkDim);
    int bx = x + 36;
    for (size_t i = 0; i < items.size(); ++i) {
        const bool sel = int(i) == omniF2FillSel;
        if (sel) fillRounded(bx, stripY + 5, wds[i], 30, omniRadius, T.accent);
        omniLabel(items[i].label, bx + wds[i] / 2, stripY + 20, omniSmall, sel ? T.accentInk : T.ink, 1);
        bx += wds[i] + 8;
    }
    if (omniF2FillSel < 0) {
        const char* tip = "\xe2\x96\xb2 Up from the keys to fill";
        omniLabel(tip, x + totalW - 12, stripY - 10, omniCaption, T.inkFaint, 2);
    }
}
static bool omniF2FillClick(int cx, int cy)
{
    const auto items = omniF2FillItems();
    if (items.empty()) return false;
    const int stripY = keyboardY - 58 - 48;
    if (cy < stripY || cy >= stripY + 40) return false;
    int totalW = 20; std::vector<int> wds;
    for (auto& it : items) { const int w = int(omniTextWidthPx(omniSmall, it.label.c_str()) / displayScale + 0.5) + 44; wds.push_back(w); totalW += w + 8; }
    int bx = (width - totalW) / 2 + 36;
    for (size_t i = 0; i < items.size(); ++i) { if (cx >= bx && cx < bx + wds[i]) { omniF2FillDo(items[i].id); return true; } bx += wds[i] + 8; }
    return false;
}

// --- panel integration (rows added into the existing OmniFx panels) --------------------------------
static void omniF2SiteExtra(OmniFxPanel& p)
{
    const std::string host = omniMenuHost();
    OmniFxRow perms; perms.id = 900; perms.label = "Site permissions"; perms.enabled = !host.empty(); perms.icon = omniIconShield; p.rows.push_back(perms);
    const auto logins = omniPwFor(omniF2OriginOf(active() ? active()->url : std::string()));
    OmniFxRow fill; fill.id = 901; fill.label = "Fill saved login"; fill.enabled = !logins.empty() || omniPwLocked();
    fill.value = omniPwLocked() ? std::string("Locked") : logins.empty() ? std::string("None saved") : std::to_string(logins.size()) + " saved";
    p.rows.push_back(fill);
}
static bool omniF2SiteInput(const OmniFxRow& r, int b)
{
    if (r.id == 900) { if (b != SDL_CONTROLLER_BUTTON_A) return r.enabled ? false : true; if (r.enabled) omniPermSiteShow(omniMenuHost()); return true; }
    if (r.id == 901) { if (b != SDL_CONTROLLER_BUTTON_A) return r.enabled ? false : true; if (r.enabled) omniPwFillCurrent(); return true; }
    return false;
}
static void omniF2SettingsExtra(OmniFxPanel& p)
{
    OmniFxRow pw; pw.id = 900; pw.label = "Passwords"; omniPwLoad(); pw.value = omniPwLocked() ? std::string("Locked") : omniPw.list.empty() ? std::string("None") : std::to_string(omniPw.list.size()); p.rows.push_back(pw);
    OmniFxRow af; af.id = 901; af.label = "Autofill"; af.value = omniAfEmpty() ? std::string("Off") : "On"; p.rows.push_back(af);
    OmniFxRow sp; sp.id = 902; sp.label = "Site permissions"; p.rows.push_back(sp);
}
static bool omniF2SettingsInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (r.id == 900) { omniPwListShow(); return true; }
    if (r.id == 901) { omniAfPanelShow(); return true; }
    if (r.id == 902) { omniPermAllShow(); return true; }
    return false;
}
static bool omniF2QuickExtra(OmniFxPanel& p)
{
    const std::string origin = omniF2OriginOf(active() ? active()->url : std::string());
    const bool login = !omniPwFor(origin).empty();
    if (login) { OmniFxRow r; r.id = 902; r.label = "Fill saved login"; p.rows.push_back(r); return true; }
    return false;
}
static bool omniF2QuickInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (r.id == 902) { omniFxCloseAll(); omniPwFillCurrent(); return true; }
    return false;
}

// --- per pass --------------------------------------------------------------------------------------
static void omniF2Tick()
{
    omniPickTick();
    const bool canPrompt = !omniModalVisible() && !pageFullscreen && !settingsOpen && omniFxStack.empty() && !editing;
    omniPermTick(canPrompt);
    if (omniPwRevealRow >= 0) {   // stop revealing a password once the Passwords list is gone
        bool open = false;
        for (auto& q : omniFxStack) open |= q.kind == omniPwKindList;
        if (!open) omniPwRevealRow = -1;
    }
}

// --- WebKit UI client ------------------------------------------------------------------------------
static void omniF2InstallUI(WKPageUIClientV19& ui)
{
    ui.runOpenPanel = omniPickOpen;   // OmniFilePicker.h
    omniPermInstallUI(ui);            // OmniPermissions.h: storage access + deny location/notif/camera/mic
}

// --- overlay layer registration --------------------------------------------------------------------
[[maybe_unused]] static const bool omniF2Layers = [] {
    auto& layers = omniOverlayLayers();
    layers.push_back({ omniF2FillOpen, omniF2FillButton, omniF2FillClick, nullptr, omniF2FillDraw, false });
    return true;
}();
