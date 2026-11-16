#!/usr/bin/env python3
"""OMNI_DL_PANEL_V1 (2026-11-16): Options > More > "Downloaded files": the Downloads app's finished files, opened from Omni.

What the user sees
  - Options > More has a "Downloaded files" row (tile id OmniDlPanel::kTile = 468, More by omniMqGroup's default; not
    there in guest mode). Cross closes the menu and opens the panel:
        "Downloaded files"                                            "37 files"  (or "Newest 500 of 812")
        "The Downloads app's Library, newest first"
        a list, 8 rows a page: a type icon (film frame + play, note, picture, page + "PDF", page with lines, page),
        the file name, and "Video · 1.4 GB · 16 Nov 2026, 14:03 · in Music/Live".
    D-pad up / down one row, L1 / R1 a page, right stick scrolls, the pointer selects then opens a row.
    Cross opens the file:
      video / audio  -> the Downloads app's player page (/player) in a new tab: the page looks the file up in the
                        Library listing with its own token and starts it (/player#id=<Library id>, as the Library does).
      PDF            -> Omni's PDF reader (OMNI_PDF_VIEWER_V1) in a new tab: the file is read (worker thread, at most
                        OmniPdfViewer::kMaxBytes = 32 MB) into the reader's own document store under a new random token
                        (omniPdfvDocs.add, exactly as a downloaded PDF), then omni://pages/pdf/index.html?doc=<token>
                        &name=<name> (no "src": nothing to reload from). "PDF too large for the reader (over 32 MB)" /
                        a memory notice (omniTmQueryMiB() < 64 + 3 x size) instead; reader missing -> Downloads app.
      picture        -> a PNG in Saved/Screenshots: the screenshot gallery's full-screen view of it (OMNI_SCREENSHOT_
                        GALLERY_V1: omniSsOpen + omniSsShow). Any other picture: the player page in a new tab asks
                        the Library for the file's signed stream link and Omni's image viewer (OMNI_IMAGE_VIEWER_V1,
                        omniImvStart) shows it over that page (fit / zoom / Circle closes; the tab stays on the player
                        page, titled with the file name).
      anything else  -> "Open in Downloads": the Downloads tab on its Library (/downloads#view=files).
    Triangle: "Open in Downloads" for any file. Square asks once (the shell's modal, Cancel focused):
        "Move this file to the trash?" / "<name> (<size>). It moves to the Downloads trash, where the Downloads app can
        restore it or delete it for good."  -> <Saved>/.trash/<same folders>/<name> ("name (2).ext" .. "(999)" as
        files_library.py _free; OmniShotGallery::trashPath), "Moved to the Downloads trash".
    Circle / Options close it. Empty: "Nothing downloaded yet" / "Files the Downloads app saves to the console show up
    here."
  - Private tabs: works (the files are the shared Library's anyway) and says so in the subtitle: "Private tab: these
    are the Downloads app's shared files (not private). They open in a normal tab." Files open in normal tabs.
  - Guest mode (OMNI_GUEST_MODE_V1): the row is not shown, and opening it is refused with guest mode's own notice
    (guest mode's own "Downloads isn't available in guest mode"); an open panel closes when guest mode begins.

Listing: read straight from the folder (no worker route): <downloads folder>/Saved = the parent of
OmniQuickActions::kShotDir (/data/omni/downloads/media-worker/Saved), files_library.py's console save root, with its
_scan rules (no names starting with '.', so .trash is never listed; no symbolic links; 8 folders deep; 20000 entries
looked at), unfinished downloads (.part, .ytdl, .part-FragN, .crdownload, ...) left out, newest first (mtime, then
name), 500 at most. On a worker thread (started on first use, then idle on a condition variable; never destroyed:
heap mutex / cv / queues, as the screenshot gallery's r2). Refreshed when the panel opens and when
/data/omni/downloads-done.txt changes (omniDownloadsDoneTick: the Downloads worker writes a line per finished job, the
source of the "Downloaded: ..." notice). USB save roots are not listed (console storage only).

Why the player page finds the id itself: the Library names files by HMAC ids keyed by the worker's session token, which
the shell does not have (OMNI_DL_PROGRESS_V1: /api/active is the only token-free route). /player already carries the
token in its meta tag, so after it loads (the tab polled in omniDlpnTick, no new load hook) one fixed script runs there
(OmniDlPanel::resolveScript: same-origin GET /api/files?kind=all&area=files&offset=N&limit=100 with X-Omni-Token, the
row with place "internal", the same folder and name; at most 5000 rows looked at), then sets #id= and reloads (video /
audio) or POSTs /api/files/link and leaves the signed link in window.__omniDlpn (pictures; checked by
OmniDlPanel::streamLinkOk before the image viewer gets it). No new worker routes, nothing tokenless that writes.
Before a player / Library opening, one GET /api/active (OmniDlProgressShell.h's omniDlpRun, its own thread, blocking
socket with timeouts) says whether the Downloads app runs; when it doesn't, it is started as L1 + R1 does
(omniMediaDownloadsOpen) with "Starting the Downloads app: choose the file again when it's open".
Player tabs (video / audio) are Downloads-section tabs (omniMediaSection, as omniMediaApplyPlan makes them): no link
grabber on them, and its Back goes to the Library. Picture tabs are not (the image viewer stands down on the Downloads
tab).

Pure part: OmniDlPanel.h (kept in tools/, written into the tree; namespace OmniDlPanel, alias ODLN): kinds, routes,
the walk, the list, selection, trash folders, the player-page script, texts. Tests:
    g++ -std=c++20 -Wall -Wextra -Werror -I. test_dl_panel.cpp -o t && ./t && ./t --emit DIR && node test_dl_panel_js.cjs DIR
Shell part: engine/entry/OmniDlPanelShell.h, included from OmniBrowser.cpp right after OmniHistoryKeepShell.h (after
OmniPdfViewerShell.h and OmniFeatures3.h's gallery / image viewer / Downloads progress). Guest mode's names are not
used in this file's code (apply_guest_mode.py refuses sibling scripts that use them): omniGuest() and
OmniGuestMode::blockedNotice (its pure header) only.
Names omniDlpn*; tile id 468. Refused when the tree or another apply_*.py already uses them.
Anchors (each exactly once; whole lines kept, new lines before / after them, /* */ comments only):
  OmniBrowser.cpp   the OmniShotGallery.h include (pure include after); the omniPdfvTick declaration (ours after);
                    "    if (!tracker.restamp(stamp)) return;" in omniDownloadsDoneTick (omniDlpnDoneChanged() after);
                    the OmniHistoryKeepShell.h include (shell include after)
  OmniQuickMenu.h   the omniSsQuickAction declaration (ours after); the Screenshots add() row (our row after);
                    the omniSsQuickAction call (ours before)
  OmniFeatures3.h   the omniPdfvTick(now) line of omniF3Tick (omniDlpnTick(now) after)
Needs OMNI_PDF_VIEWER_V1, OMNI_IMAGE_VIEWER_V1, OMNI_SCREENSHOT_GALLERY_V1, OMNI_GUEST_MODE_V1, OMNI_DL_PROGRESS_V1,
OMNI_SMALL_COMFORTS_V1 first.
usage: apply_dl_panel.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_DL_PANEL_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_dl_panel.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('468',)
NAMES = ('ODLN', 'omniDlpn', 'OmniDlPanel', 'OMNI_DL_PANEL')

SHELL = r'''// OMNI_DL_PANEL_V1: Options > More > "Downloaded files" (shell side): the Downloads app's finished files (its Library's
// console save root, read straight from the folder on a worker thread), newest first, opened from Omni: video / audio in
// the Downloads app's player, PDFs in Omni's reader, pictures in the screenshot gallery / image viewer, the rest in the
// Downloads app. Square moves a file to the Library's trash. Included from OmniBrowser.cpp after OmniHistoryKeepShell.h.
// The pure part is OmniDlPanel.h; the reasons are in tools/apply_dl_panel.py. Main thread except omniDlpnWorker.
#pragma once

namespace ODLN = OmniDlPanel;

// --- the worker: listings and PDF reads ---------------------------------------------------------------------------------
struct OmniDlpnJob { int kind = 0; uint32_t gen = 0; std::string rel; };   // kind 0: list the folder, 1: read a PDF
struct OmniDlpnResult {
    int kind = 0;
    uint32_t gen = 0;
    std::string rel;
    ODLN::Listing listing;
    std::vector<uint8_t> bytes;
    int status = 0;            // PDF: 0 read, 1 couldn't, 2 too large
};
// Never destroyed (heap, as OMNI_SCREENSHOT_GALLERY_V1_R2): the detached worker waits on them for the life of the process.
static std::mutex& omniDlpnMu = *new std::mutex;
static std::condition_variable& omniDlpnCv = *new std::condition_variable;
static std::deque<OmniDlpnJob>& omniDlpnJobs = *new std::deque<OmniDlpnJob>;          // guarded by omniDlpnMu
static std::deque<OmniDlpnResult>& omniDlpnResults = *new std::deque<OmniDlpnResult>; // guarded by omniDlpnMu
static bool omniDlpnWorkerUp = false;

// <downloads folder>/Saved: the Library's console save root, the screenshot folder's parent.
static std::string omniDlpnRoot()
{
    const std::string d = OmniQuickActions::kShotDir;
    const size_t s = d.rfind('/');
    return s == std::string::npos ? d : d.substr(0, s);
}
static std::string omniDlpnPath(const std::string& rel) { return omniDlpnRoot() + "/" + rel; }
static bool omniDlpnReadDir(const std::string& rel, std::vector<ODLN::DirEnt>& out, size_t budget)
{
    const std::string dir = rel.empty() ? omniDlpnRoot() : omniDlpnPath(rel);
    DIR* d = opendir(dir.c_str());
    if (!d) return false;
    while (dirent* e = readdir(d)) {
        if (out.size() >= budget) break;
        ODLN::DirEnt x;
        x.name = e->d_name;
        if (x.name == "." || x.name == "..") continue;
        if (x.name[0] != '.') {   // hidden names are skipped by the walk: no lstat for them
            struct stat st {};
            if (lstat((dir + "/" + x.name).c_str(), &st) == 0) {
                x.type = S_ISLNK(st.st_mode) ? ODLN::Type::Link : S_ISDIR(st.st_mode) ? ODLN::Type::Dir
                    : S_ISREG(st.st_mode) ? ODLN::Type::File : ODLN::Type::Other;
                x.size = uint64_t(st.st_size);
                x.mtime = int64_t(st.st_mtime);
            }
        }
        out.push_back(std::move(x));
    }
    closedir(d);
    return true;
}
// No symbolic link from the root down to the file, and the file a regular one (files_library.py _checked).
static bool omniDlpnPlainFile(const std::string& rel, uint64_t* size = nullptr)
{
    if (!ODLN::plainRel(rel)) return false;
    struct stat st {};
    if (lstat(omniDlpnRoot().c_str(), &st) != 0 || !S_ISDIR(st.st_mode)) return false;
    for (const std::string& c : ODLN::chain(rel))
        if (lstat(omniDlpnPath(c).c_str(), &st) != 0 || S_ISLNK(st.st_mode)) return false;
    if (!S_ISREG(st.st_mode)) return false;
    if (size) *size = uint64_t(st.st_size);
    return true;
}
static int omniDlpnReadPdf(const std::string& rel, std::vector<uint8_t>& bytes)
{
    uint64_t size = 0;
    if (!omniDlpnPlainFile(rel, &size)) return 1;
    if (size > OPDF::kMaxBytes) return 2;
    FILE* f = fopen(omniDlpnPath(rel).c_str(), "rb");
    if (!f) return 1;
    int status = 0;
    uint8_t buf[65536];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) {
        if (bytes.size() + n > OPDF::kMaxBytes) { status = 2; break; }   // grew while reading
        bytes.insert(bytes.end(), buf, buf + n);
    }
    if (ferror(f)) status = 1;
    fclose(f);
    if (status) std::vector<uint8_t>().swap(bytes);
    return status;
}
static void omniDlpnWorker()
{
    for (;;) {
        OmniDlpnJob j;
        {
            std::unique_lock<std::mutex> lock(omniDlpnMu);
            omniDlpnCv.wait(lock, [] { return !omniDlpnJobs.empty(); });
            j = std::move(omniDlpnJobs.front());
            omniDlpnJobs.pop_front();
        }
        OmniDlpnResult r;
        r.kind = j.kind; r.gen = j.gen; r.rel = j.rel;
        if (j.kind == 0) {
            struct stat st {};   // the root itself must be a plain folder (files_library.py roots())
            if (lstat(omniDlpnRoot().c_str(), &st) == 0 && S_ISDIR(st.st_mode)) r.listing = ODLN::list(ODLN::scan(omniDlpnReadDir));
        } else {
            r.status = omniDlpnReadPdf(j.rel, r.bytes);
        }
        std::lock_guard<std::mutex> lock(omniDlpnMu);
        omniDlpnResults.push_back(std::move(r));
    }
}
static void omniDlpnPost(OmniDlpnJob j)
{
    if (!omniDlpnWorkerUp) { omniDlpnWorkerUp = true; std::thread(omniDlpnWorker).detach(); }
    {
        std::lock_guard<std::mutex> lock(omniDlpnMu);
        omniDlpnJobs.push_back(std::move(j));
    }
    omniDlpnCv.notify_one();
}

// --- state ----------------------------------------------------------------------------------------------------------------
constexpr int omniDlpnVis = 8, omniDlpnRowH = 66;
static bool omniDlpnOpenFlag = false;
static uint32_t omniDlpnGen = 0;                   // bumped on open / close: listings for an earlier opening are dropped
static bool omniDlpnLoading = false, omniDlpnRescan = false;
static ODLN::Listing omniDlpnList;
static std::vector<std::string> omniDlpnWhen;      // "16 Nov 2026, 14:03" per row
static ODLN::Sel omniDlpnSel;
static bool omniDlpnPrivate = false;
static float omniDlpnScrollAcc = 0;
static uint32_t omniDlpnPdfSeq = 0;                // the PDF read asked for last (an older one coming back is dropped)

static void omniDlpnScan()
{
    if (omniDlpnLoading) { omniDlpnRescan = true; return; }   // one listing at a time; the newest request runs after it
    omniDlpnLoading = true;
    omniDlpnPost({ 0, omniDlpnGen, std::string() });
}
static void omniDlpnTake(ODLN::Listing&& l)
{
    const std::string keep = omniDlpnSel.sel < int(omniDlpnList.items.size()) ? omniDlpnList.items[size_t(omniDlpnSel.sel)].rel : std::string();
    omniDlpnList = std::move(l);
    omniDlpnWhen.clear();
    omniDlpnWhen.reserve(omniDlpnList.items.size());
    for (const ODLN::Item& it : omniDlpnList.items) {
        const time_t mt = time_t(it.mtime);
        struct tm tmv {};
        localtime_r(&mt, &tmv);
        omniDlpnWhen.push_back(OSG::formatWhen(OSG::stampOf(tmv.tm_year + 1900, tmv.tm_mon + 1, tmv.tm_mday, tmv.tm_hour, tmv.tm_min, tmv.tm_sec)));
    }
    omniDlpnSel.count = int(omniDlpnList.items.size());
    const int at = keep.empty() ? -1 : ODLN::indexOf(omniDlpnList.items, keep);
    if (at >= 0) omniDlpnSel.sel = at;
    omniDlpnSel.clamp(omniDlpnVis);
}
static void omniDlpnClose()
{
    if (!omniDlpnOpenFlag) return;
    omniDlpnOpenFlag = false;
    ++omniDlpnGen;
    omniDlpnLoading = omniDlpnRescan = false;   // a listing in flight comes back with the old generation and is dropped
    omniDlpnList = ODLN::Listing();
    std::vector<std::string>().swap(omniDlpnWhen);
    omniDlpnSel = ODLN::Sel();
    omniShellDirty = true;
}
static void omniDlpnOpen()
{
    if (omniGuest()) { notice(OmniGuestMode::blockedNotice("Downloads")); return; }   // OMNI_GUEST_MODE_V1: the owner's downloads
    omniFxCloseAll();
    ++omniDlpnGen;
    omniDlpnOpenFlag = true;
    omniDlpnLoading = omniDlpnRescan = false;
    omniDlpnList = ODLN::Listing();
    omniDlpnWhen.clear();
    omniDlpnSel = ODLN::Sel();
    omniDlpnScrollAcc = 0;
    omniDlpnPrivate = active() && active()->omniPrivate;
    omniDlpnScan();
    fprintf(stderr, "OMNI DL PANEL: opened (%s)\n", omniDlpnRoot().c_str()); fflush(stderr);
    omniShellDirty = true;
}
// omniDownloadsDoneTick: /data/omni/downloads-done.txt changed (a Downloads job finished).
static void omniDlpnDoneChanged()
{
    if (omniDlpnOpenFlag) omniDlpnScan();
}

// --- opening through the Downloads app (player page, picture link, Library) -------------------------------------------------
struct OmniDlpnOpener {
    int stage = 0;                 // 0 idle, 1 is the Downloads app running?, 2 the player page loading, 3 the picture link
    ODLN::Route route = ODLN::Route::Library;
    std::string name, folder;
    unsigned port = 0;
    std::shared_ptr<OmniDlpPoll> poll;
    uintptr_t tab = 0;             // the player tab (omniMediaIdentity)
    uint32_t at = 0, askedAt = 0;
    bool asking = false;
};
static OmniDlpnOpener omniDlpnOp;
static uint32_t omniDlpnOpSeq = 0;                 // answers from an opening that was replaced are dropped
constexpr uint32_t omniDlpnLoadMs = 20000, omniDlpnLinkMs = 20000, omniDlpnAskMs = 300;

static Tab* omniDlpnTabById(uintptr_t id)
{
    if (!id) return nullptr;
    for (auto& t : tabs) if (t->omniMediaIdentity == id) return &*t;
    return nullptr;
}
static void omniDlpnNoTab()
{
    const std::string why = omniF3TabRefusal();
    notice(why.empty() ? std::string("Close a tab to open this file") : why);
}
static void omniDlpnStartOpen(const ODLN::Item& it, ODLN::Route route)
{
    const unsigned port = OmniMediaSection::assignedPort();
    if (!omniMediaDownloadsEnabled || !port) { omniMediaDownloadsOpen(false); return; }   // its own notice (disabled / unavailable)
    ++omniDlpnOpSeq;
    omniDlpnOp = OmniDlpnOpener();
    omniDlpnOp.stage = 1;
    omniDlpnOp.route = route;
    omniDlpnOp.name = it.name;
    omniDlpnOp.folder = it.folder;
    omniDlpnOp.port = port;
    omniDlpnOp.at = SDL_GetTicks();
    auto p = std::make_shared<OmniDlpPoll>();
    p->port = uint16_t(port);
    omniDlpnOp.poll = p;
    std::thread(omniDlpRun, p).detach();   // GET /api/active: blocking socket with timeouts, its own struct
    notice(route == ODLN::Route::Library ? std::string("Opening the Downloads app...") : "Opening " + OPDF::shortName(it.name) + "...");
}
static void omniDlpnLaunch(uint32_t now)
{
    OmniDlpnOpener& o = omniDlpnOp;
    if (o.route == ODLN::Route::Library) {
        o.stage = 0;
        auto plan = OmniMediaSection::plan(omniMediaDownloadsEnabled, true, omniMediaTabSnapshot(), "", false, o.port);
        if (plan.action == OmniMediaSection::Action::Create || plan.action == OmniMediaSection::Action::Activate) plan.url = ODLN::libraryURL(o.port);
        omniDlpHandedOver();
        omniMediaApplyPlan(plan);
        return;
    }
    Tab* t = newTab();
    if (!t) { o.stage = 0; omniDlpnNoTab(); return; }
    if (o.route == ODLN::Route::Player) { t->omniMediaSection = true; omniNetGrabberApply(*t); }   // a Downloads-app tab
    navigate(ODLN::playerURL(o.port));
    o.tab = t->omniMediaIdentity;
    o.stage = 2;
    o.at = now;
}
struct OmniDlpnCall { uint32_t seq; };
static void omniDlpnEval(Tab* t, const std::string& js, bool poll)
{
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    if (!poll) {
        WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
        return;
    }
    omniDlpnOp.asking = true;
    omniDlpnOp.askedAt = SDL_GetTicks();
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), new OmniDlpnCall { omniDlpnOpSeq }, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniDlpnCall> c(static_cast<OmniDlpnCall*>(context));
        if (c->seq != omniDlpnOpSeq || omniDlpnOp.stage != 3) return;
        omniDlpnOp.asking = false;
        const std::string r = omniFxResultString(result, error);
        std::string state, src;
        omniFxJsonString(r, "state", state);
        omniFxJsonString(r, "src", src);
        if (state == "busy" || state.empty()) return;   // asked again on a later tick
        omniDlpnOp.stage = 0;
        Tab* t = omniDlpnTabById(omniDlpnOp.tab);
        if (state != "ok" || !ODLN::streamLinkOk(src, omniDlpnOp.port)) {
            notice(state == "gone" ? "This file is no longer in the Downloads library" : "The Downloads app couldn't open this file");
            return;
        }
        if (!t || t != active()) return;   // the user moved on: the page shows the file's name, nothing pops up elsewhere
        omniImvStart(t, src, false, false);   // OMNI_IMAGE_VIEWER_V1 over the player page
    });
}
static void omniDlpnOpenTick(uint32_t now)
{
    OmniDlpnOpener& o = omniDlpnOp;
    if (o.stage == 1) {
        if (o.poll && o.poll->done.load(std::memory_order_acquire)) {
            const ODLP::Reply reply = ODLP::Reply(o.poll->reply);
            o.poll.reset();
            if (reply == ODLP::Reply::Ok || reply == ODLP::Reply::Missing) omniDlpnLaunch(now);   // Missing: an older worker, running
            else {
                o.stage = 0;
                if (o.route != ODLN::Route::Library) notice("Starting the Downloads app: choose the file again when it's open");
                omniMediaDownloadsOpen(false);
            }
        } else if (ODLP::after(now, o.at + ODLP::kAbandonMs)) {
            o.stage = 0;
            o.poll.reset();   // its thread ends on its own timeouts and writes only into its own struct
            notice("The Downloads app didn't answer");
        }
        return;
    }
    if (o.stage != 2 && o.stage != 3) return;
    Tab* t = omniDlpnTabById(o.tab);
    if (!t || t->crashed) { o.stage = 0; return; }
    if (o.stage == 2) {
        if (t->loading) {
            if (ODLP::after(now, o.at + omniDlpnLoadMs)) { o.stage = 0; notice("The Downloads app's player didn't open"); }
            return;
        }
        if (!ODLN::isPlayerURL(t->url, o.port)) { o.stage = 0; notice("The Downloads app's player didn't open"); return; }
        const bool play = o.route == ODLN::Route::Player;
        omniDlpnEval(t, ODLN::resolveScript(o.name, o.folder, play), false);
        if (play) { o.stage = 0; return; }   // the page sets #id= and reloads into the file
        o.stage = 3;
        o.at = now;
        o.asking = false;
        o.askedAt = now;
        return;
    }
    if (ODLP::after(now, o.at + omniDlpnLinkMs)) { o.stage = 0; notice("The Downloads app couldn't open this file"); return; }
    if (t->loading || !ODLN::isPlayerURL(t->url, o.port)) { o.stage = 0; return; }   // the user went elsewhere
    if (o.asking && !ODLP::after(now, o.askedAt + 3000)) return;   // an answer that never comes no longer holds the next ask
    if (!ODLP::after(now, o.askedAt + omniDlpnAskMs)) return;
    omniDlpnEval(t, ODLN::pollScript(), true);
}

// --- PDFs: Omni's reader, from the file -------------------------------------------------------------------------------------
static void omniDlpnOpenPdf(const ODLN::Item& it)
{
    if (!omniPdfvViewerPresent()) {
        notice("Omni's PDF reader isn't installed: opening the Downloads app");
        omniDlpnClose();
        omniDlpnStartOpen(it, ODLN::Route::Library);
        return;
    }
    if (it.size > OPDF::kMaxBytes) { notice(OPDF::tooBigNotice(false)); return; }
    const long long freeMiB = omniTmQueryMiB();
    if (freeMiB >= 0 && freeMiB < 64 + (long long)((it.size * 3) >> 20)) { notice("Not enough memory to open this PDF right now"); return; }
    omniDlpnClose();
    omniDlpnPost({ 1, ++omniDlpnPdfSeq, it.rel });
    notice(OPDF::openingNotice(it.name, 0, 0));
}
static void omniDlpnPdfReady(OmniDlpnResult& r)
{
    const std::string name = OPDF::fileName(ODLN::nameOf(r.rel), std::string());
    if (r.status == 2) { notice(OPDF::tooBigNotice(false)); return; }
    if (r.status != 0 || r.bytes.empty()) { notice("Couldn't open " + OPDF::shortName(name)); return; }
    Tab* t = newTab();
    if (!t) { omniDlpnNoTab(); return; }
    OPDF::Doc doc;
    doc.token = omniPdfvNewToken();
    doc.name = name;
    doc.bytes = std::move(r.bytes);
    const std::string path = OPDF::viewerPath(doc.token, doc.name, std::string());   // no src: nothing to reload from
    omniPdfvDocs.add(std::move(doc));
    if (!omniPagesOpen(t, path)) notice("Couldn't open the PDF reader");
    fprintf(stderr, "OMNI DL PANEL: %s in the PDF reader\n", r.rel.c_str()); fflush(stderr);
}

// --- per pass (from omniF3Tick) -------------------------------------------------------------------------------------------------
static void omniDlpnTick(uint32_t now)
{
    if (omniDlpnOpenFlag && omniGuest()) omniDlpnClose();   // guest mode began
    std::deque<OmniDlpnResult> done;
    {
        std::lock_guard<std::mutex> lock(omniDlpnMu);
        done.swap(omniDlpnResults);
    }
    for (OmniDlpnResult& r : done) {
        if (r.kind == 1) { if (r.gen == omniDlpnPdfSeq) omniDlpnPdfReady(r); continue; }
        if (!omniDlpnOpenFlag || r.gen != omniDlpnGen) continue;
        omniDlpnLoading = false;
        omniDlpnTake(std::move(r.listing));
        omniShellDirty = true;
        if (omniDlpnRescan) { omniDlpnRescan = false; omniDlpnScan(); }
    }
    omniDlpnOpenTick(now);
}

// --- actions -------------------------------------------------------------------------------------------------------------------
static void omniDlpnActivate(int i, bool library)
{
    if (i < 0 || i >= int(omniDlpnList.items.size())) return;
    const ODLN::Item it = omniDlpnList.items[size_t(i)];
    const ODLN::Route route = library ? ODLN::Route::Library : ODLN::routeFor(it.kind, it.rel);
    fprintf(stderr, "OMNI DL PANEL: open %s (route %d)\n", it.rel.c_str(), int(route)); fflush(stderr);
    switch (route) {
    case ODLN::Route::PdfReader: omniDlpnOpenPdf(it); break;
    case ODLN::Route::Gallery: {
        omniDlpnClose();
        omniSsOpen();   // OMNI_SCREENSHOT_GALLERY_V1
        const int at = omniSsOpenFlag ? OSG::indexOf(omniSsShots, it.name) : -1;
        if (at >= 0) omniSsShow(at);
        break;
    }
    default:
        omniDlpnClose();
        omniDlpnStartOpen(it, route);
        break;
    }
}
// Into the Library's trash (<Saved>/.trash/<folders>/<name>), where Downloads > Library > Trash restores or deletes it.
static void omniDlpnDelete(const std::string& rel)
{
    const std::string root = omniDlpnRoot();
    bool ok = omniDlpnPlainFile(rel);
    const std::vector<std::string> dirs = ODLN::trashDirs(rel);
    for (const std::string& d : dirs) {   // one level at a time, no link on the way (files_library.py _make_dirs)
        if (!ok) break;
        const std::string p = root + "/" + d;
        struct stat st {};
        if (mkdir(p.c_str(), 0777) != 0 && errno != EEXIST) ok = false;
        else if (lstat(p.c_str(), &st) != 0 || !S_ISDIR(st.st_mode)) ok = false;
    }
    const std::string tdir = root + "/" + dirs.back();
    const std::string to = ok ? OSG::trashPath(tdir, ODLN::nameOf(rel), [](const std::string& p) { struct stat st {}; return lstat(p.c_str(), &st) == 0; })
                              : std::string();
    if (to.empty() || rename(omniDlpnPath(rel).c_str(), to.c_str()) != 0) {
        fprintf(stderr, "OMNI DL PANEL: couldn't move %s to the trash (errno %d)\n", rel.c_str(), errno); fflush(stderr);
        notice("Couldn't move the file to the trash");
        return;
    }
    fprintf(stderr, "OMNI DL PANEL: %s -> %s\n", rel.c_str(), to.c_str()); fflush(stderr);
    const int i = ODLN::indexOf(omniDlpnList.items, rel);
    if (i >= 0) {
        omniDlpnList.items.erase(omniDlpnList.items.begin() + i);
        omniDlpnWhen.erase(omniDlpnWhen.begin() + i);
        if (omniDlpnList.total) --omniDlpnList.total;
    }
    omniDlpnSel.count = int(omniDlpnList.items.size());
    omniDlpnSel.clamp(omniDlpnVis);
    notice("Moved to the Downloads trash");
    omniShellDirty = true;
}
static void omniDlpnAskDelete(int i)
{
    if (i < 0 || i >= int(omniDlpnList.items.size())) return;
    const ODLN::Item it = omniDlpnList.items[size_t(i)];
    const uint32_t gen = omniDlpnGen;
    omniAsk(ODLN::askTitle(), ODLN::askBody(it), "Move to trash", [rel = it.rel, gen](bool ok) {
        if (ok && omniDlpnOpenFlag && gen == omniDlpnGen) omniDlpnDelete(rel);
    });
}

// --- input ------------------------------------------------------------------------------------------------------------------------
static bool omniDlpnButton(int b)
{
    omniShellDirty = true;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_START: case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: omniDlpnClose(); break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniDlpnSel.move(-1, omniDlpnVis); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniDlpnSel.move(1, omniDlpnVis); break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: omniDlpnSel.page(-1, omniDlpnVis); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: omniDlpnSel.page(1, omniDlpnVis); break;
    case SDL_CONTROLLER_BUTTON_A: omniDlpnActivate(omniDlpnSel.sel, false); break;   // Cross
    case SDL_CONTROLLER_BUTTON_Y: omniDlpnActivate(omniDlpnSel.sel, true); break;    // Triangle: Open in Downloads
    case SDL_CONTROLLER_BUTTON_X: omniDlpnAskDelete(omniDlpnSel.sel); break;         // Square
    default: break;
    }
    return true;
}

// --- drawing ----------------------------------------------------------------------------------------------------------------------
struct OmniDlpnGeom { int x, y, w, h, listY; };
static OmniDlpnGeom omniDlpnGeometry()
{
    OmniDlpnGeom g {};
    g.w = std::min(1000, width - 40);
    g.h = 92 + omniDlpnVis * omniDlpnRowH + 16;
    g.x = (width - g.w) / 2;
    g.y = std::max(6, (height - bottom - g.h) / 2);
    g.listY = g.y + 92;
    return g;
}
// The type icons, in a 24 x 24 box: signed distance (< 0 inside).
static float omniDlpnGlyphSd(ODLN::Kind k, float x, float y)
{
    switch (k) {
    case ODLN::Kind::Video: {   // a screen with a play triangle
        const SDL_FPoint tri[3] = { { 10, 8.5f }, { 10, 15.5f }, { 15.8f, 12 } };
        return std::min(std::fabs(omniSdBox(x, y, 12, 12, 9.5f, 7.5f, 2)) - 1.f, omniSdPoly(tri, 3, x, y));
    }
    case ODLN::Kind::Audio:     // a note
        return std::min({ std::hypot(x - 8.6f, y - 17.f) - 2.9f, omniSdSeg(x, y, 11.2f, 17, 11.2f, 4.5f, 1.f), omniSdSeg(x, y, 11.2f, 4.5f, 17.5f, 7.5f, 1.f) });
    case ODLN::Kind::Image: {   // a frame, hills and a sun
        const SDL_FPoint hills[5] = { { 5, 17.5f }, { 9.5f, 11 }, { 13, 15 }, { 15.5f, 12.5f }, { 19, 17.5f } };
        return std::min({ std::fabs(omniSdBox(x, y, 12, 12, 9.5f, 8, 2)) - 1.f, omniSdPoly(hills, 5, x, y), std::hypot(x - 15.5f, y - 7.8f) - 1.7f });
    }
    default: {                  // a page with a folded corner (Text: lines on it)
        const SDL_FPoint page[5] = { { 6, 3 }, { 14.5f, 3 }, { 18, 6.5f }, { 18, 21 }, { 6, 21 } };
        float d = std::min({ std::fabs(omniSdPoly(page, 5, x, y)) - 0.9f, omniSdSeg(x, y, 14.5f, 3, 14.5f, 6.5f, 0.8f), omniSdSeg(x, y, 14.5f, 6.5f, 18, 6.5f, 0.8f) });
        if (k == ODLN::Kind::Text)
            for (float ly : { 10.f, 13.5f, 17.f }) d = std::min(d, omniSdSeg(x, y, 9, ly, 15, ly, 0.8f));
        return d;
    }
    }
}
static void omniDlpnGlyph(ODLN::Kind k, float cx, float cy, SDL_Color c)
{
    const OmniPix f = omniPix();
    if (!f.ok) return;
    const float s = float(displayScale), size = 30.f, unit = size / 24.f;
    const float X0 = (cx - size / 2) * s, Y0 = (cy - size / 2) * s;
    const int x0 = std::max(0, int(X0)), x1 = std::min(canvas->w, int(X0 + size * s) + 1);
    const int y0 = std::max(0, int(Y0)), y1 = std::min(canvas->h, int(Y0 + size * s) + 1);
    for (int y = y0; y < y1; ++y) {
        uint32_t* row = omniRow(y);
        for (int x = x0; x < x1; ++x) {
            const float d = omniDlpnGlyphSd(k, (x + 0.5f - X0) / (s * unit), (y + 0.5f - Y0) / (s * unit)) * unit * s;
            const float cov = std::clamp(0.5f - d, 0.f, 1.f);
            if (cov > 0) omniBlendPx(row[x], f, c, uint32_t(cov * 255));
        }
    }
    if (k == ODLN::Kind::Pdf) omniLabel("PDF", cx, cy + 3, omniCaptionBold, c, 1);
}
static void omniDlpnDraw()
{
    const OmniTheme& T = omniTheme();
    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, 110);
    const OmniDlpnGeom g = omniDlpnGeometry();
    omniShadow(g.x, g.y, g.w, g.h, omniRadius + 2, 22, 160, 6);
    fillRounded(g.x, g.y, g.w, g.h, omniRadius + 2, T.panel);
    const int cornerW = omniLabel(ODLN::corner(omniDlpnList, omniDlpnLoading), g.x + g.w - 28, g.y + 34, omniSmall, T.inkFaint, 2);
    omniLabel(ODLN::title(), g.x + 28, g.y + 34, omniBodyBold, T.ink, 0, g.w - 70 - cornerW);
    omniLabel(ODLN::subtitle(omniDlpnPrivate), g.x + 28, g.y + 64, omniSmall, T.inkDim, 0, g.w - 56);
    const int n = int(omniDlpnList.items.size());
    if (!n) {
        const float cy = g.listY + omniDlpnVis * omniDlpnRowH / 2.f;
        if (omniDlpnLoading) omniLabel("Loading\xe2\x80\xa6", g.x + g.w / 2.f, cy, omniBody, T.inkDim, 1);
        else {
            omniLabel(ODLN::emptyTitle(), g.x + g.w / 2.f, cy - 18, omniBodyBold, T.ink, 1);
            omniLabel(ODLN::emptyBody(), g.x + g.w / 2.f, cy + 18, omniSmall, T.inkDim, 1, g.w - 80);
        }
        omniPanelHints({ { 1, "Back" } }, nullptr);
        return;
    }
    for (int k = 0; k < omniDlpnVis && omniDlpnSel.scroll + k < n; ++k) {
        const int i = omniDlpnSel.scroll + k;
        const ODLN::Item& it = omniDlpnList.items[size_t(i)];
        const int ry = g.listY + k * omniDlpnRowH;
        const bool sel = i == omniDlpnSel.sel;
        if (sel) fillRounded(g.x + 12, ry + 2, g.w - 24, omniDlpnRowH - 4, omniRadius, T.accent);
        const SDL_Color ink = sel ? T.accentInk : T.ink, dim = sel ? T.accentInk : T.inkDim;
        fillRounded(g.x + 24, ry + 9, 48, 48, omniRadius, sel ? T.panel : T.tab);
        omniDlpnGlyph(it.kind, g.x + 48.f, ry + omniDlpnRowH / 2.f, sel ? T.accent : T.ink);
        omniLabel(it.name, g.x + 88, ry + 23.f, omniBody, ink, 0, g.w - 88 - 40);
        omniLabel(ODLN::detail(it, size_t(i) < omniDlpnWhen.size() ? omniDlpnWhen[size_t(i)] : std::string()), g.x + 88, ry + 47.f, omniSmall, dim, 0, g.w - 128);
    }
    if (n > omniDlpnVis) {   // scroll position
        const int trackY = g.listY + 4, trackH = omniDlpnVis * omniDlpnRowH - 8;
        const int thumbH = std::max(24, trackH * omniDlpnVis / n), thumbY = trackY + (trackH - thumbH) * omniDlpnSel.scroll / std::max(1, n - omniDlpnVis);
        fillRounded(g.x + g.w - 8, trackY, 3, trackH, 1, T.line);
        fillRounded(g.x + g.w - 8, thumbY, 3, thumbH, 1, T.inkDim);
    }
    const ODLN::Item& cur = omniDlpnList.items[size_t(std::clamp(omniDlpnSel.sel, 0, n - 1))];
    const char* act = ODLN::actionHint(ODLN::routeFor(cur.kind, cur.rel));
    if (n > omniDlpnVis) omniPanelHints({ { 0, act }, { 2, "Delete" }, { 3, "Open in Downloads" }, { omniHintShoulders, "Page" }, { 1, "Back" } }, nullptr);
    else omniPanelHints({ { 0, act }, { 2, "Delete" }, { 3, "Open in Downloads" }, { 1, "Back" } }, nullptr);
}

// --- pointer (Cross at the pointer, mouse) and right stick ---------------------------------------------------------------------------
static bool omniDlpnClick(int x, int y)
{
    const OmniDlpnGeom g = omniDlpnGeometry();
    if (x >= g.x + 12 && x < g.x + g.w - 12 && y >= g.listY && y < g.listY + omniDlpnVis * omniDlpnRowH) {
        const int i = omniDlpnSel.scroll + (y - g.listY) / omniDlpnRowH;
        if (i < int(omniDlpnList.items.size())) {
            if (i == omniDlpnSel.sel) omniDlpnActivate(i, false); else omniDlpnSel.sel = i;
        }
    }
    omniShellDirty = true;
    return true;
}
static bool omniDlpnScroll(double amount)
{
    omniDlpnScrollAcc -= float(amount);
    while (omniDlpnScrollAcc >= 50) { omniDlpnScrollAcc -= 50; omniDlpnSel.move(1, omniDlpnVis); }
    while (omniDlpnScrollAcc <= -50) { omniDlpnScrollAcc += 50; omniDlpnSel.move(-1, omniDlpnVis); }
    omniShellDirty = true;
    return true;
}

// Shown while no features panel is on top (as the screenshot gallery).
static bool omniDlpnShown() { return omniDlpnOpenFlag && omniFxStack.empty(); }
[[maybe_unused]] static const bool omniDlpnLayer = [] {
    omniOverlayLayers().push_back({ omniDlpnShown, omniDlpnButton, omniDlpnClick, omniDlpnScroll, omniDlpnDraw, true });
    return true;
}();

// --- Options > More > Downloaded files ---------------------------------------------------------------------------------------------
static bool omniDlpnQuickAction(int id)
{
    if (id != ODLN::kTile) return false;
    omniDlpnOpen();
    return true;
}
'''

C = '/* ' + MARK + ' */'
EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniShotGallery.h" // OMNI_SCREENSHOT_GALLERY_V1: Options > Screenshots listing / paging / cache (pure)\n',
         '#include "OmniShotGallery.h" // OMNI_SCREENSHOT_GALLERY_V1: Options > Screenshots listing / paging / cache (pure)\n'
         '#include "OmniDlPanel.h" /* ' + MARK + ': Options > Downloaded files: walk / kinds / routes / player script (pure) */\n'),
        ('static void omniPdfvTick(uint32_t now); /* OMNI_PDF_VIEWER_V1 */\n',
         'static void omniPdfvTick(uint32_t now); /* OMNI_PDF_VIEWER_V1 */\n'
         'static void omniDlpnTick(uint32_t now); /* ' + MARK + ' (OmniDlPanelShell.h) */\n'
         'static void omniDlpnDoneChanged(); ' + C + '\n'),
        ('    if (!tracker.restamp(stamp)) return;\n',
         '    if (!tracker.restamp(stamp)) return;\n'
         '    omniDlpnDoneChanged(); /* ' + MARK + ': a Downloads job finished: Downloaded files lists again */\n'),
        ('#include "OmniHistoryKeepShell.h" /* OMNI_HISTORY_KEEP_V1 */\n',
         '#include "OmniHistoryKeepShell.h" /* OMNI_HISTORY_KEEP_V1 */\n'
         '#include "OmniDlPanelShell.h" /* ' + MARK + ': Downloaded files (after the PDF reader and OmniFeatures3.h) */\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniSsQuickAction(int id); // OMNI_SCREENSHOT_GALLERY_V1 (OmniShotGalleryShell.h)\n',
         'static bool omniSsQuickAction(int id); // OMNI_SCREENSHOT_GALLERY_V1 (OmniShotGalleryShell.h)\n'
         'static bool omniDlpnQuickAction(int id); /* ' + MARK + ' (OmniDlPanelShell.h) */\n'),
        ('    add(OmniShotGallery::kTile, "Screenshots", true); // OMNI_SCREENSHOT_GALLERY_V1: the screenshot gallery (More)\n',
         '    add(OmniShotGallery::kTile, "Screenshots", true); // OMNI_SCREENSHOT_GALLERY_V1: the screenshot gallery (More)\n'
         '    if (!omniGuest()) add(OmniDlPanel::kTile, "Downloaded files", true); /* ' + MARK + ': the Downloads app\'s files (More; not in guest mode) */\n'),
        ('    if (omniSsQuickAction(r.id)) return true; // OMNI_SCREENSHOT_GALLERY_V1: opens the gallery (closes the menu)\n',
         '    if (omniDlpnQuickAction(r.id)) return true; /* ' + MARK + ': opens Downloaded files (closes the menu) */\n'
         '    if (omniSsQuickAction(r.id)) return true; // OMNI_SCREENSHOT_GALLERY_V1: opens the gallery (closes the menu)\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniPdfvTick(now);  /* OMNI_PDF_VIEWER_V1: R2 / L2 zoom on the PDF reader */\n',
         '    omniPdfvTick(now);  /* OMNI_PDF_VIEWER_V1: R2 / L2 zoom on the PDF reader */\n'
         '    omniDlpnTick(now);  /* ' + MARK + ': listings / PDF reads from its worker, the player-page opening */\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_SCREENSHOT_GALLERY_V1', 'OMNI_PDF_VIEWER_V1', 'OMNI_GUEST_MODE_V1', 'OMNI_SMALL_COMFORTS_V1'),
         'OmniFeatures3.h': ('OMNI_PDF_VIEWER_V1', 'OMNI_IMAGE_VIEWER_V1', 'OMNI_DL_PROGRESS_V1', 'OMNI_SCREENSHOT_GALLERY_V1'),
         'OmniQuickMenu.h': ('OMNI_SCREENSHOT_GALLERY_V1',)}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
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
    mine = {'OmniDlPanel.h', 'OmniDlPanelShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniDlPanel.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniDlPanel.h: %s missing' % MARK)
    msgs = [write_new('OmniDlPanel.h', pure, 'OmniShotGallery.h'),
            write_new('OmniDlPanelShell.h', SHELL, 'OmniShotGalleryShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
