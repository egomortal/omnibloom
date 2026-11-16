#!/usr/bin/env python3
"""OMNI_QUICK_ACTIONS_V1 (2026-11-16): open a link in a background tab quickly, and a page-screenshot chord.

1. Background tab. Hold Cross (0.5 s) over a page already opens the context menu (OMNI_FEATURES_V1, OmniFeatures.h:
   omniFxButtonEvent / omniFxContextQuery), and its link rows already had "Open in background tab" (second row).
   It is now the FIRST row, so on a link: hold Cross, then Cross = background tab (the menu selects its first enabled
   row; the hold's own release is swallowed). It still goes through omniFxOpenInNewTab -> omniF3TabAllowed() (tab limit
   setting + memory guard, which says why), and the row is disabled when omniF3TabsFull(). No new gesture: hold Cross
   + Cross is already two presses and every free button is better kept for the screenshot chord.
2. Screenshot chord: L2 + R3 (Xbox: LT + RS) while browsing saves the visible page (page area, no bars) as
   /data/omni/downloads/media-worker/Saved/Screenshots/<host>-<yyyymmdd-hhmmss>.png (the Downloads app's "Saved"
   folder; folders created; "-2".."-99" on a name clash). Why it is free: L2 chords (OMNI_L2_CHORDS_V1) take only
   Square/Triangle/Cross/Circle and (OMNI_SITE_ZOOM_V1) D-pad up/down; R3 alone closes the tab and before this unit
   L2 + R3 simply closed the tab too (R3 is not an L2 chord button). R3 alone is unchanged. In trees WITHOUT
   OMNI_L2_CHORDS_V1, L2 itself opens Saved links on press, so there the chord only works while Media downloads is off.
   The release of L2 after the chord is not a saved-links tap (omniL2ChordUsed). Not in the keyboard, Settings, a
   panel, the find bar, fullscreen video, self-tests.
   The existing Screenshot rows (Options menu, context menu; OMNI_FEATURES_V3 omniPtScreenshot) use the same code, so
   they now save to the same folder too. Private tabs: never ("Screenshots are off in private tabs"), from every path.
   The page buffer is copied on the main thread (as before: one memcpy of the half-resolution page); mkdir, the
   name-clash check, the PNG encode (omniWritePng, libpng, already linked) and the write run on a detached thread;
   the tick shows "Screenshot saved (Downloads > Saved > Screenshots)". Video drawn by the hardware plane is not in
   the page buffer and comes out white (unchanged, documented in OmniPageTools.h).
Pure logic (host -> file name, timestamp, mkdir -p, unique path) is engine/entry/OmniQuickActions.h (no SDL/WebKit),
tested by test_quick_actions.cpp.

Anchors (none shared with apply_l2_chords / apply_site_zoom / apply_file_downloads / apply_grabber_suspects):
  OmniBrowser.cpp     the '#include "OmniNetGrabber.h" // OMNI_NET_GRABBER_V1' line (include the pure header)
  OmniContextMenu.h   the "Open link in new tab" / "Open in background tab" rows
  OmniFeatures.h      the start of omniFxButtonEvent (hold Cross); the chord runs first there, which is after
                      omniL2Chord in L2-chord trees (that dispatch line is apply_l2_chords' anchor and is not touched)
  OmniPageTools.h     omniPtShotState .. omniPtTick (the screenshot writer)
Apply AFTER apply_l2_chords.py when that is used (the chord marks omniL2ChordUsed only if the tree has it).
usage: apply_quick_actions.py <engine tree>   (anchored, exactly once each, idempotent, keeps CRLF)
"""
import sys
from pathlib import Path

MARK = 'OMNI_QUICK_ACTIONS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

HEADER = r'''// OMNI_QUICK_ACTIONS_V1: the pure part of the page-screenshot chord (no SDL, no WebKit): the folder, the
// "<host>-<yyyymmdd-hhmmss>.png" name, mkdir -p and a free file name. Tested on the host with g++ (test_quick_actions.cpp).
#pragma once
#include <cerrno>
#include <cstdio>
#include <ctime>
#include <string>
#include <sys/stat.h>
#include <sys/types.h>

namespace OmniQuickActions {

// The Downloads app's "Saved" folder (media worker), so screenshots are listed with downloads.
static const char* const kShotDir = "/data/omni/downloads/media-worker/Saved/Screenshots";

// The page's host as a file-name part: lower case, no "www.", no user info / port, only [a-z0-9.-] (others -> '-'),
// at most 64 characters, no leading/trailing '.' or '-'. "page" when there is none (about:, data:, file:).
inline std::string hostForFile(const std::string& url)
{
    std::string host;
    const size_t scheme = url.find("://");
    if (scheme != std::string::npos) {
        size_t start = scheme + 3, end = url.find_first_of("/?#", start);
        if (end == std::string::npos) end = url.size();
        std::string auth = url.substr(start, end - start);
        const size_t at = auth.rfind('@');
        if (at != std::string::npos) auth = auth.substr(at + 1);
        if (!auth.empty() && auth[0] == '[') {                 // [v6]:port
            const size_t close = auth.find(']');
            auth = auth.substr(1, close == std::string::npos ? std::string::npos : close - 1);
        } else {
            const size_t colon = auth.find(':');
            if (colon != std::string::npos) auth = auth.substr(0, colon);
        }
        host = auth;
    }
    std::string out;
    for (char c : host) {
        if (c >= 'A' && c <= 'Z') c = char(c + 32);
        const bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-';
        out += ok ? c : '-';
    }
    if (out.compare(0, 4, "www.") == 0) out.erase(0, 4);
    if (out.size() > 64) out.resize(64);
    while (!out.empty() && (out.back() == '.' || out.back() == '-')) out.pop_back();
    while (!out.empty() && (out[0] == '.' || out[0] == '-')) out.erase(0, 1);
    return out.empty() ? std::string("page") : out;
}

// yyyymmdd-hhmmss from a broken-down local time.
inline std::string stamp(const struct tm& t)
{
    char b[32];
    snprintf(b, sizeof(b), "%04d%02d%02d-%02d%02d%02d", (t.tm_year + 1900) % 10000, (t.tm_mon + 1) % 100, t.tm_mday % 100,
        t.tm_hour % 100, t.tm_min % 100, t.tm_sec % 100);
    return b;
}

// "<host>-<stamp>.png", or "<host>-<stamp>-<n>.png" for n >= 2.
inline std::string fileName(const std::string& host, const std::string& when, int n = 1)
{
    return host + "-" + when + (n >= 2 ? "-" + std::to_string(n) : std::string()) + ".png";
}

inline bool isDir(const std::string& path)
{
    struct stat st {};
    return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

// mkdir -p (absolute or relative). True when the folder exists at the end.
inline bool makeDirs(const std::string& path, mode_t mode = 0777)
{
    if (path.empty()) return false;
    for (size_t at = 1; at <= path.size(); ++at) {
        if (at != path.size() && path[at] != '/') continue;
        const std::string part = path.substr(0, at);
        if (part.empty() || part.back() == '/') continue;
        if (mkdir(part.c_str(), mode) != 0 && errno != EEXIST) return false;
    }
    return isDir(path);
}

inline bool fileExists(const std::string& path)
{
    struct stat st {};
    return stat(path.c_str(), &st) == 0;
}

// dir/<host>-<stamp>.png, then -2 .. -99; empty when all are taken.
template <class Exists>
inline std::string uniquePath(const std::string& dir, const std::string& host, const std::string& when, Exists exists)
{
    for (int n = 1; n < 100; ++n) {
        const std::string p = dir + "/" + fileName(host, when, n);
        if (!exists(p)) return p;
    }
    return std::string();
}
inline std::string uniquePath(const std::string& dir, const std::string& host, const std::string& when)
{
    return uniquePath(dir, host, when, fileExists);
}

} // namespace OmniQuickActions
'''

INCLUDE = ('''#include "OmniNetGrabber.h" // OMNI_NET_GRABBER_V1
''', '''#include "OmniNetGrabber.h" // OMNI_NET_GRABBER_V1
#include "OmniQuickActions.h" // OMNI_QUICK_ACTIONS_V1: screenshot folder / file name (pure)
''')

CONTEXT = ('''        add(omniCxNewTab, "Open link in new tab", !four, omniIconPlus);
        add(omniCxBackground, "Open in background tab", !four);
''', '''        add(omniCxBackground, "Open in background tab", !four, omniIconPlus); // OMNI_QUICK_ACTIONS_V1: first: hold Cross, then Cross
        add(omniCxNewTab, "Open link in new tab", !four);
''')

CHORD_L2 = '''    omniL2ChordUsed = true;   // the L2 release is not a saved-links tap (OMNI_L2_CHORDS_V1)
'''
CHORD_NO_L2 = '''    if (omniMediaDownloadsEnabled) return false;   // no OMNI_L2_CHORDS_V1 here: L2 itself opens Saved links on press
'''
BUTTON = ('''// SDL button events, before omniShoulderButton(): Cross over the page is held back until release
// (a press shorter than 0.5 s clicks as before, on release); a longer hold opens the context menu.
static bool omniFxButtonEvent(const SDL_ControllerButtonEvent& event)
{
    if (event.button != SDL_CONTROLLER_BUTTON_A) return false;
''', '''// OMNI_QUICK_ACTIONS_V1: L2 + R3 (LT + RS) while browsing: save the visible page as a PNG (omniPtScreenshot:
// Downloads > Saved > Screenshots, never in private tabs). Free: L2 chords use the face buttons and D-pad up/down only;
// R3 alone still closes the tab. Runs before hold Cross (and after omniL2Chord where that exists); R3's release does
// nothing anywhere (omniShoulderButton acts on presses only).
static void omniPtScreenshot();
static bool omniQaShotChord(const SDL_ControllerButtonEvent& event)
{
    if (event.type != SDL_CONTROLLERBUTTONDOWN || event.button != SDL_CONTROLLER_BUTTON_RIGHTSTICK) return false;
    SDL_GameController* pad = SDL_GameControllerFromInstanceID(event.which);
    if (!pad || SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT) < 20000) return false;
    if (!active() || editing || pageEditing || settingsOpen || pageFullscreen || omniOverlayOpen() || omniFindBarOpen() || omniTestMode()) return false;
    if (omniMediaDownloadsEnabled && omniSavedOwnedView() != OmniSavedView::None) return false;
@@L2@@    omniPtScreenshot();
    omniShellDirty = true;
    return true;
}
// SDL button events, before omniShoulderButton(): Cross over the page is held back until release
// (a press shorter than 0.5 s clicks as before, on release); a longer hold opens the context menu.
static bool omniFxButtonEvent(const SDL_ControllerButtonEvent& event)
{
    if (omniQaShotChord(event)) return true; // OMNI_QUICK_ACTIONS_V1
    if (event.button != SDL_CONTROLLER_BUTTON_A) return false;
''')

SHOT = ('''static std::atomic<int> omniPtShotState { 0 };   // 0 idle, 1 writing, 2 written, 3 failed
static std::string omniPtShotPath;
static void omniPtScreenshot()
{
    Tab* t = active();
    if (!t) return;
    if (omniPtShotState.load() == 1) { notice("Still saving the last screenshot..."); return; }
''', '''static std::atomic<int> omniPtShotState { 0 };   // 0 idle, 1 writing, 2 written, 3 failed
static std::string omniPtShotPath;   // OMNI_QUICK_ACTIONS_V1: set by the writer thread before it stores 2 / 3
static void omniPtScreenshot()
{
    Tab* t = active();
    if (!t) return;
    if (t->omniPrivate) { notice("Screenshots are off in private tabs"); return; } // OMNI_QUICK_ACTIONS_V1
    if (omniPtShotState.load() == 1) { notice("Still saving the last screenshot..."); return; }
''')

SHOT_WRITE = ('''    const std::string dir = omniData("downloads");
    mkdir(dir.c_str(), 0777);
    char stamp[32];
    const time_t now = time(nullptr);
    struct tm tmv {};
    localtime_r(&now, &tmv);
    strftime(stamp, sizeof(stamp), "%Y%m%d-%H%M%S", &tmv);
    std::string path = dir + "/screenshot-" + stamp + ".png";
    for (int n = 2; !access(path.c_str(), F_OK) && n < 100; ++n) path = dir + "/screenshot-" + stamp + "-" + std::to_string(n) + ".png";
    std::vector<uint8_t> copy(src, src + size_t(w) * h * 4);
    omniPtShotPath = path;
    omniPtShotState = 1;
    std::thread([copy = std::move(copy), w, h, path]() {
        const bool ok = omniWritePng(path.c_str(), copy.data(), w, h, w * 4);
        omniPtShotState = ok ? 2 : 3;
    }).detach();
    fprintf(stderr, "OMNI SCREENSHOT: %dx%d -> %s\\n", w, h, path.c_str());
    notice("Saving screenshot...");
}
static void omniPtTick()
{
    const int s = omniPtShotState.load();
    if (s == 2) { omniPtShotState = 0; notice("Screenshot saved: " + omniPtShotPath); omniShellDirty = true; }
''', '''    // OMNI_QUICK_ACTIONS_V1: Downloads > Saved > Screenshots/<host>-<yyyymmdd-hhmmss>.png. Only the pixel copy stays
    // on the main thread: mkdir -p, the name-clash check, the PNG encode and the write run on the writer thread.
    const time_t now = time(nullptr);
    struct tm tmv {};
    localtime_r(&now, &tmv);
    const std::string host = OmniQuickActions::hostForFile(t->url), when = OmniQuickActions::stamp(tmv);
    std::vector<uint8_t> copy(src, src + size_t(w) * h * 4);
    omniPtShotState = 1;
    std::thread([copy = std::move(copy), w, h, host, when]() {
        const std::string dir = OmniQuickActions::kShotDir;
        std::string path = OmniQuickActions::makeDirs(dir) ? OmniQuickActions::uniquePath(dir, host, when) : std::string();
        const bool ok = !path.empty() && omniWritePng(path.c_str(), copy.data(), w, h, w * 4);
        if (!ok && !path.empty()) unlink(path.c_str());   // no half-written PNG in the Saved list
        fprintf(stderr, "OMNI SCREENSHOT: %dx%d -> %s (%s)\\n", w, h, path.empty() ? dir.c_str() : path.c_str(), ok ? "ok" : "failed");
        omniPtShotPath = path.empty() ? dir : path;
        omniPtShotState = ok ? 2 : 3;
    }).detach();
    notice("Saving screenshot...");
}
static void omniPtTick()
{
    const int s = omniPtShotState.load();
    if (s == 2) { omniPtShotState = 0; notice("Screenshot saved (Downloads > Saved > Screenshots)"); omniShellDirty = true; } // OMNI_QUICK_ACTIONS_V1
''')


def patch(name, edits):
    p = root / name
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s:
        return name + ': already', nl
    for old0, new0 in edits:
        for e in (nl, '\n' if nl == '\r\n' else '\r\n'):   # mixed endings: the anchor's own endings decide
            old, new = old0.replace('\n', e), new0.replace('\n', e)
            if s.count(old):
                break
        n = s.count(old)
        if n != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, n, old0[:90]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied', nl


def main():
    browser = (root / 'OmniBrowser.cpp').read_text(encoding='utf-8', errors='replace')
    chord = 'static bool omniL2Held = false, omniL2Pending = false, omniL2ChordUsed = false;' in browser
    button = (BUTTON[0], BUTTON[1].replace('@@L2@@', CHORD_L2 if chord else CHORD_NO_L2))
    # check every anchor before writing anything
    for name, edits in (('OmniBrowser.cpp', [INCLUDE]), ('OmniContextMenu.h', [CONTEXT]), ('OmniFeatures.h', [button]),
                        ('OmniPageTools.h', [SHOT, SHOT_WRITE])):
        s = (root / name).read_bytes().decode('utf-8')
        if MARK in s:
            continue
        for old0, _ in edits:
            if s.count(old0.replace('\n', '\r\n')) + s.count(old0) != 1:
                sys.exit('%s: anchor not found exactly once: %r' % (name, old0[:90]))
    print(patch('OmniBrowser.cpp', [INCLUDE])[0] + ('' if chord else ' (no OMNI_L2_CHORDS_V1: L2 + R3 only while Media downloads is off)'))
    print(patch('OmniContextMenu.h', [CONTEXT])[0])
    print(patch('OmniFeatures.h', [button])[0])
    msg, nl = patch('OmniPageTools.h', [SHOT, SHOT_WRITE])
    print(msg)
    h = root / 'OmniQuickActions.h'
    data = HEADER.replace('\n', nl).encode('utf-8')
    if not h.exists() or h.read_bytes() != data:
        h.write_bytes(data)
        print('OmniQuickActions.h: written')
    else:
        print('OmniQuickActions.h: already')
    print('applied ' + MARK)


main()
