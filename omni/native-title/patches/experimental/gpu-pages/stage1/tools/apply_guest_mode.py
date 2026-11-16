#!/usr/bin/env python3
"""OMNI_GUEST_MODE_V1 (2026-11-16): Guest mode for a visitor on a shared console.

What the user sees
  - Options (top level) has a row "Guest mode" (value "For visitors"). Cross asks (the shell's own modal, Cancel focused):
        "Start guest mode?"
        "All tabs close. Your tabs will be restored when you leave guest mode. A guest can't see your bookmarks, history,
         reading list, saved sessions, apps or passwords, and nothing the guest does is saved. Downloads are off for guests."
    "Start": every tab closes, one guest tab opens on a plain start page (search only, the private look), the top bar
    shows a purple "GUEST" pill where the Omni identity is, and the notice says how to leave.
  - The same row then reads "Leave guest mode" ("Guest session"). "Leave": the guest tabs close, everything from the
    guest session is deleted (cookies, site data, history, site-setting changes) and the owner's tabs come back exactly
    as at startup (session.txt, pinned tabs and tab groups included).
  - In guest mode: every tab is a private tab on a fresh non-persistent data store (as "New private tab" makes), so the
    private-tab rules apply everywhere (no history, no reading-list saves, no pinning / groups, no media hand-off, no
    screenshots, no learned words). Bookmarks / History / Reopen closed tab / Apps show the guest's own (empty) lists.
    Passwords, autofill, saved tab sessions, reading list, Downloads, Screenshots, Clear browsing data, Browser settings
    and the shell's Settings say "<X> isn't available in guest mode". A download is cancelled ("Downloads are off in
    guest mode"): the safer of the two choices (the Downloads folder is shared with the owner).
  - Parental controls (r2, OMNI_PARENTAL_V1 when in the tree): still enforced in guest tabs (omniParPolicy is the
    navigation client's first line for every tab, private / guest ones included; safe search too). A guest can't change
    them: Parental controls lives in Browser settings, which is blocked; Site settings keeps its own PIN gate
    (Lock settings). parental.txt is on the write allowlist, so the wrong-PIN count / 5-minute lockout and any PIN-gated
    "Always allow" are saved as usual (a guest can't reset the lockout by restarting). Entering / leaving guest mode asks
    for no PIN. "Lock private tabs" on: guest mode is refused ("Guest mode is off: parental controls lock private
    tabs"; row value "Locked"), since guest tabs are private tabs and would otherwise bypass that lock.

r2 (OMNI_GUEST_MODE_V1_R2, the full chain: chain_final.txt + apply_guest_mode.py last)
  - Clipboard history (OMNI_CLIP_HISTORY_V1): omniClh taken on entering (with omniKbClipboard): the guest's copies are
    memory only and dropped on leaving; the owner's are not listed to the guest.
  - Highlights (OMNI_HIGHLIGHTS_V1): omniHltItems taken and omniHltLoad returns before reading in guest mode: the
    owner's highlights are neither listed nor re-applied in guest tabs; a guest's highlights are private-tab marks
    (visit only, never stored: that patch's own rule).
  - Notice history (OMNI_NOTICE_HISTORY_V1): omniNhRecord returns in guest mode (also during the transitions, when no
    private tab exists); omniNhList taken (the guest sees no owner notices).
  - uBlock (OmniBlocker.cpp includes OmniGuestMode.h): saveTrustedSites and the ublock-disabled.flag write do nothing in
    guest mode (memory only); on leaving the shell puts the owner's switch and trusted sites back through the setters.
  - ui-bars.txt: omniBarsSave returns in guest mode; omniQaHidden / omniHintsHidden kept (put back on leaving).
  - Shortcuts (shortcuts.txt): MEMORY ONLY: omniShortcuts taken (the guest starts with none), the loader doesn't read the
    file, omniShortcutsSave returns; the guest's edits are dropped on leaving.
  - Add-ons: BLOCKED (the list panel and the quick switch: "Add-ons isn't available in guest mode"); omniAdState kept;
    add-on storage was already never written from private tabs (guest tabs are private).
  - The Downloads app tab: BLOCKED (omniMediaDownloadsRequest: the top-bar indicator, Quick access "Downloads", the
    media hand-off).
  - Reader-auto (OMNI_READER_AUTO_V1): omniRauStore kept, omniRauSession taken.
  - The owner's tabs come back from omniSessionText() captured on entering (OGST::parseSession + the pinned / group
    restore lines), not through omniEverydayStart: OMNI_STARTUP_CHOICE_V1's start choice and crash marker there belong
    to a real start. running.txt (that crash marker) is on the write allowlist.
  - The private context is made by the shell's omniGstPrivateEnsure (a copy of omniNewPrivateTab's creation, which
    OMNI_PARENTAL_V1 now gates); r1's split of omniNewPrivateTab is gone (a tree patched by r1 keeps it, harmless).
  - The generated OmniGuestModeShell.h starts with OMNI_GST_HAS_{CLIP,HIGHLIGHTS,NOTICES,PARENTAL,READER_AUTO} 0 / 1
    (which optional patches the tree has); apply this script after them.

Design: one flag, omniGuest() (OmniGuestMode.h: an atomic phase Owner -> Entering -> Guest -> Leaving -> Owner; the rules
hold in every non-Owner phase), checked at a few chokepoints. Pure header (state machine, write allowlist, Stash, texts):
engine/entry/OmniGuestMode.h, tested by tools/test_guest_mode.cpp:
    g++ -std=c++20 -Wall -Wextra -I<dir with OmniGuestMode.h> test_guest_mode.cpp -o t && ./t
Shell side: engine/entry/OmniGuestModeShell.h (included after OmniHistoryKeepShell.h, after every store it stashes).

Chokepoints patched (file: what)
  OmniBrowser.cpp     omniIoQueue: in guest mode a write under OMNI_DATA_DIR is refused (logged once per file) unless
                      OmniGuestMode::writeAllowed (crash / startup markers only). Every queued store write goes here
                      (bookmarks, history, session.txt, sessions.txt, kb-words, apps.json, start-page.json, browser
                      settings, site-zoom / site-ua / site-dark / dark-style / site-permissions / autoplay / https-only /
                      popup-allow / site-tweaks / site-volume, quick-access, autofill, add-on state + storage, captions,
                      night light, history keep, kb-layout, theme-prev, pointer-large).
                      newTab: with no supplied configuration in guest mode the page gets the private context + store
                      (omniGstConfig) and the tab is marked omniPrivate. Popups inherit their opener's configuration.
                      omniHistoryLoad, omniKwLoadLearned: loaders return before reading (and before marking loaded).
                      omniDownloadInstall: the download is cancelled (no destination), notice.
                      omniDrawTopBar: the "GUEST" pill over the identity.
  OmniBookmarks.h     omniFxBookmarksLoad: returns empty (not marked loaded).
  OmniTabSessionsShell.h  omniTsLoad: returns empty; omniTsListShow: blocked.
  OmniWebAppsShell.h  omniWapApps: the (stashed, empty) list without reading apps.json.
  OmniReadingListShell.h  omniRlShow: blocked (saving was already refused in private tabs).
  OmniPasswords.h     omniPwFor: no logins; omniPwSave (the vault writes its own files): refused; omniPwFillCurrent and
                      omniPwListShow: blocked.
  OmniAutofill.h      omniAfFill, omniAfPanelShow: blocked.
  OmniDownloadsPage.h omniFxDownloadsShow: blocked (it lists and deletes files of the shared folder).
  OmniShotGalleryShell.h  omniSsOpen: blocked (the owner's screenshots).
  OmniClearRangeShell.h   omniClrShow: blocked (it clears the owner's persistent store and unlinks owner files).
  OmniHistoryKeepShell.h  omniHkTick: no prune of the owner's history file during a guest session.
  OmniBrowserSettings.h   omniFxSettingsShow: blocked.
  OmniStartCustomShell.h  omniScuRender: the guest start page JSON (search only, private, no reading list / closed tabs).
  OmniFeatures3.h     omniF3Tick: omniGstTick (does the asked enter / leave on the next pass; closes the shell's Settings
                      if a guest opens them by any of their five entry points).
  OmniQuickMenu.h     Options (top level): the row and its input.
In memory (OmniGuestModeShell.h, on entering; put back on leaving):
  taken (guest sees none): omniHistory, omniFxBookmarks + omniBmFolderOf, omniTsList, omniWapList, omniKw.learned,
    omniKbClipboard (the keyboard's clipboard), omniFxClosed (reopen closed tab), the private-tab "this run" choices
    (omniApSession, omniHoSession, omniPnSession, omniStSession, omniTvPrivate).
  kept (guest works on a copy, dropped on leaving): omniSiteZoom, omniMobileHosts, omniDkSites, omniPerm (its private
    session part cleared for the guest), omniApStore, omniHoStore, omniPnSaved, omniStStore, omniTvSaved. Their loaders
    run before the copy (a copy of an unloaded store would come back "loaded" and empty).
  The private store is cleared and released on entering (the owner's own private tabs' cookies are not the guest's) and
  on leaving (the guest's); a fresh one is made for the next private tab.

Not covered (a guest can still reach these)
  - Search shortcuts (search-shortcuts.txt keywords): read-only, the owner's custom keywords work for the guest.
  - Settings stores a guest can't open (Browser settings / Settings are blocked) but that change in memory through
    other paths would keep that change until the next start (writes refused): e.g. tips seen, the Send link flag.
  - Playback-speed memory for private tabs and the permission prompts' per-session notices: shared in memory.

Anchors (exactly once each; MARK / REV make each file idempotent):
  r2 (REV): OmniBrowser.cpp omniShortcutsLoad's loaded check, omniShortcutsSave's and omniBarsSave's heads;
  OmniBlocker.cpp the OmniBlocker.h include, saveTrustedSites' head, omniBlockerSetEnabled's ublock-native.flag check;
  OmniAddons.h omniAdListShow's and omniAdQuickAction's heads; OmniMediaDownloadsHooks.inc omniMediaDownloadsRequest's
  head; optional: OmniHighlightsShell.h omniHltLoad's loaded check, OmniNoticeHistoryShell.h omniNhRecord's first line.
  r1 (MARK):
  OmniBrowser.cpp     the OmniSiteClear.h include (pure include); the OmniFeatures3Decl.h include (declarations);
                      newTab's `if (!supplied) {...}` block and its `auto tab = std::make_unique<Tab>();` +
                      omniPagesCapable lines; omniIoQueue's first lines; omniHistoryLoad's and omniKwLoadLearned's
                      loaded checks; omniDownloadInstall's head;
                      the omniHudIdentity() line of omniDrawTopBar; the OmniHistoryKeepShell.h include (shell include).
  OmniFeatures3.h     the omniScTick line (apply_site_clear.py r2).
  OmniQuickMenu.h     the omniDlpQuickInput declaration, the omniDlpQuickRow call, the omniDlpQuickInput call
                      (apply_dl_progress.py's).
  OmniBookmarks.h, OmniTabSessionsShell.h, OmniWebAppsShell.h, OmniReadingListShell.h, OmniPasswords.h, OmniAutofill.h,
  OmniDownloadsPage.h, OmniShotGalleryShell.h, OmniClearRangeShell.h, OmniHistoryKeepShell.h, OmniBrowserSettings.h,
  OmniStartCustomShell.h: a function head (`static ... name(...)\\n{\\n`) or loaded check each, listed in EDITS.
Ids: Options top-level row 8510 (grep of every apply_*.py and the tree: unused; 8000-8005 Options groups, 8100 now
playing, 8200 controls, 8470 pop-ups, 8480 downloads, 8490 reader auto). Alias OGST (unused). Checked before a first
apply with apply_bf_list.py's cpp_code() / code_only() (comments and notes are not uses; OmniGuestMode.h, omniGuest()
and OMNI_GUEST_MODE_V1 are public: apply_notes.py uses them).
Apply LAST (after apply_site_clear.py r2, apply_dl_progress.py, apply_start_custom.py, apply_web_apps.py,
apply_history_keep.py, apply_clear_range.py, apply_reading_list.py, apply_tab_sessions.py, apply_screenshot_gallery.py).
usage: apply_guest_mode.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_GUEST_MODE_V1'
ROW_ID = 8510
ALIAS = 'OGST'
TOOLS = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

G = ' // ' + MARK


def head(sig, guard):
    """A function head `sig\\n{\\n` and a first body line."""
    return (sig + '\n{\n', sig + '\n{\n    ' + guard + G + '\n')


EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n',
         '#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n'
         '#include "OmniGuestMode.h" // OMNI_GUEST_MODE_V1: guest mode: state machine, write allowlist, stash (pure)\n'),
        ('#include "OmniFeatures3Decl.h" // OMNI_FEATURES_V3: star, suggestions, page tools, dark pages, tab memory\n',
         '#include "OmniFeatures3Decl.h" // OMNI_FEATURES_V3: star, suggestions, page tools, dark pages, tab memory\n'
         '// OMNI_GUEST_MODE_V1 (OmniGuestModeShell.h): the chokepoints call these\n'
         'static void omniGstRefused(const std::string& path);\n'
         'static bool omniGstBlocked(const char* what);\n'
         'static bool omniGstConfig(WKPageConfigurationRef config);\n'
         'static void omniGstDownloadRefused(WKDownloadRef download);\n'
         'static std::string omniGstStartJson(const std::string& hint);\n'
         'static void omniGstDrawBadge();\n'
         'static void omniGstTick(uint32_t now);\n'),
        ('    if (!supplied) {\n'
         '        WKPageConfigurationSetContext(config.get(), context.get());\n'
         '        WKPageConfigurationSetPreferences(config.get(), preferences.get());\n'
         '        WKPageConfigurationSetWebsiteDataStore(config.get(), websiteDataStore.get());\n'
         '    }\n',
         '    if (!supplied) {\n'
         '        WKPageConfigurationSetContext(config.get(), context.get());\n'
         '        WKPageConfigurationSetPreferences(config.get(), preferences.get());\n'
         '        WKPageConfigurationSetWebsiteDataStore(config.get(), websiteDataStore.get());\n'
         '    }\n'
         '    const bool omniGstTab = !supplied && omniGstConfig(config.get());' + G + ': guest tabs use the guest (private, non-persistent) store\n'),
        ('    auto tab = std::make_unique<Tab>();\n'
         '    tab->omniPagesCapable = omniPagesOnConfig; // s3 OMNI_PAGES_V1\n',
         '    auto tab = std::make_unique<Tab>();\n'
         '    tab->omniPagesCapable = omniPagesOnConfig; // s3 OMNI_PAGES_V1\n'
         '    if (omniGstTab) tab->omniPrivate = true;' + G + ': every guest tab is a private tab (no history, nothing saved)\n'),
        ('static void omniIoQueue(const std::string& path, std::string data, bool append)\n{\n',
         'static void omniIoQueue(const std::string& path, std::string data, bool append)\n{\n'
         '    if (omniGuest() && !OmniGuestMode::writeAllowed(path, OMNI_DATA_DIR)) { omniGstRefused(path); return; }' + G + ': nothing under the data folder is written\n'),
        ('    if (omniHistoryLoaded) return;\n    omniHistoryLoaded = true;\n',
         '    if (omniHistoryLoaded) return;\n'
         '    if (omniGuest()) return;' + G + ': the owner\'s history is not read (not marked loaded either)\n'
         '    omniHistoryLoaded = true;\n'),
        ('    if (omniKw.learnedLoaded) return;\n    omniKw.learnedLoaded = true;\n',
         '    if (omniKw.learnedLoaded) return;\n'
         '    if (omniGuest()) return;' + G + ': the owner\'s learned words are not read\n'
         '    omniKw.learnedLoaded = true;\n'),
        ('static void omniDownloadInstall(WKDownloadRef download)\n{\n',
         'static void omniDownloadInstall(WKDownloadRef download)\n{\n'
         '    if (omniGuest()) { omniGstDownloadRefused(download); return; }' + G + ': the download folder is shared with the owner\n'),
        ('    omniHudIdentity(); // OMNI_HUD_ASTRA_V1: the user\'s icon + "OMNI" (was "O" in the accent colour + "MNI")\n',
         '    omniHudIdentity(); // OMNI_HUD_ASTRA_V1: the user\'s icon + "OMNI" (was "O" in the accent colour + "MNI")\n'
         '    omniGstDrawBadge();' + G + ': "GUEST" over the identity while in guest mode\n'),
        ('#include "OmniHistoryKeepShell.h" /* OMNI_HISTORY_KEEP_V1 */\n',
         '#include "OmniHistoryKeepShell.h" /* OMNI_HISTORY_KEEP_V1 */\n'
         '#include "OmniGuestModeShell.h"' + G + ': guest mode (after every store it stashes)\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n',
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'
         '    omniGstTick(now);' + G + ': enter / leave on the next pass; Settings stay closed to a guest\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniDlpQuickInput(const OmniFxRow& r, int b);\n',
         'static bool omniDlpQuickInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniGstQuickRowId = %d;' % ROW_ID + G + ': Options (top level) "Guest mode" (OmniGuestModeShell.h)\n'
         'static void omniGstQuickRow(OmniFxPanel& p);\n'
         'static bool omniGstQuickInput(const OmniFxRow& r, int b);\n'),
        ('        omniDlpQuickRow(p); // OMNI_DL_PROGRESS_V1: Downloads (n active), while the Downloads app has jobs\n',
         '        omniDlpQuickRow(p); // OMNI_DL_PROGRESS_V1: Downloads (n active), while the Downloads app has jobs\n'
         '        omniGstQuickRow(p);' + G + ': Guest mode / Leave guest mode\n'),
        ('    if (omniDlpQuickInput(r, b)) return true; // OMNI_DL_PROGRESS_V1 (before the >= 900 rows)\n',
         '    if (omniGstQuickInput(r, b)) return true;' + G + ' (before the >= 900 rows)\n'
         '    if (omniDlpQuickInput(r, b)) return true; // OMNI_DL_PROGRESS_V1 (before the >= 900 rows)\n'),
    ],
    'OmniBookmarks.h': [
        ('    if (omniFxBookmarksLoaded) return;\n    omniFxBookmarksLoaded = true;\n',
         '    if (omniFxBookmarksLoaded) return;\n'
         '    if (omniGuest()) return;' + G + ': the owner\'s bookmarks are not read\n'
         '    omniFxBookmarksLoaded = true;\n'),
    ],
    'OmniTabSessionsShell.h': [
        ('    if (omniTsLoaded) return;\n    omniTsLoaded = true;\n',
         '    if (omniTsLoaded) return;\n'
         '    if (omniGuest()) return;' + G + ': the owner\'s sessions are not read\n'
         '    omniTsLoaded = true;\n'),
        head('static void omniTsListShow()', 'if (omniGstBlocked("Saved tab sessions")) return;'),
    ],
    'OmniWebAppsShell.h': [
        ('    if (omniWapLoaded) return omniWapList;\n    omniWapLoaded = true;\n',
         '    if (omniWapLoaded) return omniWapList;\n'
         '    if (omniGuest()) return omniWapList;' + G + ': apps.json is not read (the guest\'s list)\n'
         '    omniWapLoaded = true;\n'),
    ],
    'OmniReadingListShell.h': [
        head('static void omniRlShow()', 'if (omniGstBlocked("The reading list")) return;'),
    ],
    'OmniPasswords.h': [
        head('static bool omniPwSave()', 'if (omniGstBlocked("Saving passwords")) return false;'),
        head('static std::vector<int> omniPwFor(const std::string& origin)', 'if (omniGuest()) return {};'),
        head('static void omniPwFillCurrent()', 'if (omniGstBlocked("Passwords")) return;'),
        head('static void omniPwListShow()', 'if (omniGstBlocked("Passwords")) return;'),
    ],
    'OmniAutofill.h': [
        head('static void omniAfFill()', 'if (omniGstBlocked("Autofill")) return;'),
        head('static void omniAfPanelShow()', 'if (omniGstBlocked("Autofill")) return;'),
    ],
    'OmniDownloadsPage.h': [
        head('static void omniFxDownloadsShow()', 'if (omniGstBlocked("Downloads")) return;'),
    ],
    'OmniShotGalleryShell.h': [
        head('static void omniSsOpen()', 'if (omniGstBlocked("Screenshots")) return;'),
    ],
    'OmniClearRangeShell.h': [
        head('static void omniClrShow()', 'if (omniGstBlocked("Clear browsing data")) return;'),
    ],
    'OmniHistoryKeepShell.h': [
        ('static void omniHkTick(uint32_t now)   // from omniF3Tick\n{\n    if (omniTestMode()) return;\n',
         'static void omniHkTick(uint32_t now)   // from omniF3Tick\n{\n    if (omniTestMode()) return;\n'
         '    if (omniGuest()) return;' + G + ': the owner\'s history file is not pruned during a guest session\n'),
    ],
    'OmniBrowserSettings.h': [
        head('static void omniFxSettingsShow()', 'if (omniGstBlocked("Browser settings")) return;'),
    ],
    'OmniStartCustomShell.h': [
        ('    const std::string data = OSCU::pageJson(c, tab->omniPrivate, omniCwOn(), omniScuReading(), OSCU::newestClosed(omniFxClosed),\n'
         '        omniScuPictureVersion(c), hint);\n',
         '    const std::string data = omniGuest() ? omniGstStartJson(hint)' + G.replace(' // ', ' /* ') + ': the plain guest start page */\n'
         '        : OSCU::pageJson(c, tab->omniPrivate, omniCwOn(), omniScuReading(), OSCU::newestClosed(omniFxClosed),\n'
         '        omniScuPictureVersion(c), hint);\n'),
    ],
}

NEEDS = {   # marker that must be present (the anchors are these patches' lines)
    'OmniFeatures3.h': 'OMNI_SITE_CLEAR_V1_R2',
    'OmniQuickMenu.h': 'OMNI_DL_PROGRESS_V1',
    'OmniStartCustomShell.h': 'OMNI_START_CUSTOM_V1',
    'OmniWebAppsShell.h': 'OMNI_WEB_APPS_V1',
    'OmniHistoryKeepShell.h': 'OMNI_HISTORY_KEEP_V1',
    'OmniClearRangeShell.h': 'OMNI_CLEAR_RANGE_V1',
}
NEW = ['OmniGuestMode.h', 'OmniGuestModeShell.h']

# --- r2 (OMNI_GUEST_MODE_V1_R2): REV makes these idempotent; a tree patched by r1 gets only these ----------------------
REV = 'OMNI_GUEST_MODE_V1_R2'
GR = ' // ' + REV
EDITS_R2 = {
    'OmniBrowser.cpp': [
        ('    if (omniShortcutsLoaded) return;\n    omniShortcutsLoaded = true;\n',
         '    if (omniShortcutsLoaded) return;\n'
         '    if (omniGuest()) return;' + GR + ': the owner\'s shortcuts are not read\n'
         '    omniShortcutsLoaded = true;\n'),
        ('static void omniShortcutsSave()\n{\n',
         'static void omniShortcutsSave()\n{\n'
         '    if (omniGuest()) return;' + GR + ': a guest\'s shortcut edits stay in memory (dropped on leaving)\n'),
        ('static void omniBarsSave()\n{\n',
         'static void omniBarsSave()\n{\n'
         '    if (omniGuest()) return;' + GR + ': quick bar / hints: memory only in guest mode (put back on leaving)\n'),
    ],
    'OmniBlocker.cpp': [
        ('#include "OmniBlocker.h"\n',
         '#include "OmniBlocker.h"\n'
         '#include "OmniGuestMode.h"' + GR + ': uBlock changes stay in memory in guest mode\n'),
        ('bool saveTrustedSites()\n{\n',
         'bool saveTrustedSites()\n{\n'
         '    if (omniGuest()) return true;' + GR + ': trusted sites: memory only (the shell puts the owner\'s back)\n'),
        ('    if (!access("/data/omni/ublock-native.flag", F_OK)) {\n        if (value) {\n',
         '    if (!omniGuest() && !access("/data/omni/ublock-native.flag", F_OK)) {' + GR + ': no flag file in guest mode\n'
         '        if (value) {\n'),
    ],
    'OmniAddons.h': [
        ('static void omniAdListShow()\n{\n',
         'static void omniAdListShow()\n{\n'
         '    if (omniGstBlocked("Add-ons")) return;' + GR + '\n'),
        ('static bool omniAdQuickAction(int id)\n{\n',
         'static bool omniAdQuickAction(int id)\n{\n'
         '    if ((id == omniAdQuickTile || id == omniAdListTile) && omniGstBlocked("Add-ons")) return true;' + GR + '\n'),
    ],
    'OmniMediaDownloadsHooks.inc': [
        ('    const std::string& candidate = "", bool detected = false, const std::string& wire = "", const std::string& wirePage = "")\n{\n',
         '    const std::string& candidate = "", bool detected = false, const std::string& wire = "", const std::string& wirePage = "")\n{\n'
         '    if (omniGstBlocked("The Downloads app")) return;' + GR + ': the shared Downloads app (the owner\'s jobs)\n'),
    ],
}
# Optional patches (in the full chain, not in the rc6 recipe): edited only when the file has the marker; the shell's
# OMNI_GST_HAS_* lines say which are present (the stores it stashes). Apply this script after them.
OPTIONAL = {
    'OmniHighlightsShell.h': ('OMNI_HIGHLIGHTS_V1', 'HIGHLIGHTS', [
        ('    if (omniHltLoaded) return;\n    omniHltLoaded = true;\n',
         '    if (omniHltLoaded) return;\n'
         '    if (omniGuest()) return;' + GR + ': the owner\'s highlights are not read (nor re-applied in guest tabs)\n'
         '    omniHltLoaded = true;\n'),
    ]),
    'OmniNoticeHistoryShell.h': ('OMNI_NOTICE_HISTORY_V1', 'NOTICES', [
        ('    if (omniTestMode() || omniNhPrivateOpen()) return;   // never recorded while any private tab exists\n',
         '    if (omniTestMode() || omniNhPrivateOpen()) return;   // never recorded while any private tab exists\n'
         '    if (omniGuest()) return;' + GR + ': nothing is recorded in guest mode (transitions included)\n'),
    ]),
    'OmniClipHistoryShell.h': ('OMNI_CLIP_HISTORY_V1', 'CLIP', []),
    'OmniParentalShell.h': ('OMNI_PARENTAL_V1', 'PARENTAL', []),
    'OmniReaderAutoShell.h': ('OMNI_READER_AUTO_V1', 'READER_AUTO', []),
}

# Build-safe id / name checks (cpp_code / code_only from apply_bf_list.py): comments and notes are not uses.
IDS = (str(ROW_ID),)
# OmniGuestMode.h / omniGuest() / OMNI_GUEST_MODE_V1 are this patch's public names: other patches may use them
# (apply_notes.py includes the header with __has_include and calls omniGuest()); only the shell's own names are checked.
NAMES = (r'\bOGST\b', r'\bomniGst', 'OmniGuestModeShell', r'\bOMNI_GST_HAS')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    for f in sorted(TOOLS.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        m = name.search(code_only(f.read_text(encoding='utf-8', errors='replace')))
        if m:   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in NEW or not f.is_file() or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or name.search(c)
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def read(name):
    return (root / name).read_bytes().decode('utf-8')


def check(name, edits, mark=MARK):
    s = read(name)
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if mark in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, like, prefix=''):
    text = prefix + (TOOLS / name).read_bytes().decode('utf-8').replace('\r\n', '\n')
    if REV not in text:
        sys.exit('%s: %s missing (tools copy out of date)' % (name, REV))
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def present():
    """Optional patches in this tree: {file: (feature, edits)} for those whose file has the marker."""
    out = {}
    for name, (mark, feature, edits) in OPTIONAL.items():
        p = root / name
        if p.exists() and mark in p.read_bytes().decode('utf-8', errors='replace'):
            out[name] = (feature, edits)
    return out


def main():
    for name, mark in NEEDS.items():
        if mark not in read(name):
            sys.exit('%s: %s missing: apply its patch first' % (name, mark))
    if MARK not in read('OmniBrowser.cpp'):
        ids_free()
    have = present()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    for name, edits in EDITS_R2.items():
        check(name, edits, REV)
    for name, (_f, edits) in have.items():
        check(name, edits, REV)
    feats = sorted(f for f, _e in have.values())
    prefix = '// OMNI_GUEST_MODE_V1_R2: optional patches in this tree (written by apply_guest_mode.py, applied after them)\n'
    prefix += ''.join('#define OMNI_GST_HAS_%s %d\n' % (f, 1 if f in feats else 0)
                      for f in sorted(x[1] for x in OPTIONAL.values()))
    msgs = [write_new('OmniGuestMode.h', 'OmniSiteClear.h'),
            write_new('OmniGuestModeShell.h', 'OmniSiteClearShell.h', prefix)]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    msgs += [patch(name, edits, REV).replace(': ', ' (r2): ', 1) for name, edits in EDITS_R2.items()]
    msgs += [patch(name, edits, REV).replace(': ', ' (r2): ', 1) for name, (_f, edits) in have.items() if edits]
    for m in msgs:
        print(m)
    print('optional patches: %s' % (', '.join(feats) or 'none'))
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
