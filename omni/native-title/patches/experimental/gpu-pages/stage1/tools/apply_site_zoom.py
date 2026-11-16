#!/usr/bin/env python3
"""OMNI_SITE_ZOOM_V1 (2026-11-16): per-site zoom that Omni remembers, finished for the TV.

Omni already had a per-site zoom (OMNI_EVERYDAY_V1): WKPageSetPageZoomFactor(displayScale * omniPageScale * site zoom) on
every main-frame commit, /data/omni/site-zoom.txt, rows in Browser tools / Site settings / the Options menu. This unit
finishes it:
  - steps are 50 67 75 80 90 100 110 125 150 175 200 % (was up to 250); a step goes to the next step above / below the
    current zoom (also from a default-zoom setting between steps);
  - the file is host<TAB>percent, newest change last, at most 500 hosts (oldest dropped); old files (host<TAB>1.250)
    still load; written through omniIoQueue as before; hosts are registrable hosts without "www." (omniBlockerHostOf,
    and keys from old files are normalized the same way);
  - a short notice on every change ("Zoom 110% on example.com");
  - the zoom is (re)applied when a tab is shown (tab switch), besides each main-frame commit;
  - Options menu list (cols == 1, the OMNI_MQ_NATIVE_V1 submenus): one stepper row "Zoom (this site)  < 110% >",
    D-pad left/right change, Cross resets; it sits in Quick toggles when that group exists. The 3-column grid of the
    older quick menu keeps its Zoom out / Zoom in / Reset tiles (left/right move in a grid);
  - L2 + D-pad up / down: zoom this site in / out while browsing (only when OMNI_L2_CHORDS_V1 is in the tree: the L2
    chord handler swallows the press and release; L2 + Square/Triangle/Cross/Circle are unchanged), listed in Controls.
Pointer mapping: clicks / wheel go to WebKit in view pixels and WebKit applies the page zoom itself; the shell's
JavaScript hit tests (context menu, snap, L2 copy) already use omniFxCssPerLayout(), which divides by the page's live
WKPageGetPageZoomFactor, so they follow the site zoom without change.
The pure logic (steps, host keys, file parse/serialize, the 500 cap) is engine/entry/OmniSiteZoom.h (no WebKit types).

usage: apply_site_zoom.py <engine tree>   (writes engine/entry/OmniSiteZoom.h; edits engine/entry/OmniBrowser.cpp and
OmniQuickMenu.h; each anchor exactly once (the L2 / Controls / Quick-toggles ones only when present); idempotent;
keeps CRLF). Apply after apply_l2_chords.py (L2 chord) and after the OMNI_MQ_NATIVE_V1 sources (Quick toggles, Controls).
"""
import sys
from pathlib import Path

MARK = 'OMNI_SITE_ZOOM_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

HEADER = r'''// OMNI_SITE_ZOOM_V1: per-site zoom, the pure part (no WebKit, no SDL): zoom steps, host keys and the
// /data/omni/site-zoom.txt format: one "host<TAB>percent" line per site, newest change last, at most kMaxEntries.
// Lines from older builds ("host<TAB>1.250", a factor) still load. Tested on the host with g++ (test_site_zoom.cpp).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <string>
#include <utility>
#include <vector>

namespace OmniSiteZoom {

constexpr int kSteps[] = { 50, 67, 75, 80, 90, 100, 110, 125, 150, 175, 200 };
constexpr int kStepCount = int(sizeof(kSteps) / sizeof(kSteps[0]));
constexpr int kMin = 50, kMax = 200;
constexpr size_t kMaxEntries = 500;
constexpr size_t kMaxHost = 253;

inline int clampPercent(int percent) { return std::clamp(percent, kMin, kMax); }
inline int toPercent(double factor) { return factor > 0 && factor < 100 ? int(std::lround(factor * 100)) : 100; }

// The next step above (dir > 0) or below (dir < 0) `percent`; stays at the end steps. dir == 0: percent, clamped.
inline int step(int percent, int dir)
{
    if (dir > 0) { for (int s : kSteps) if (s > percent) return s; return kMax; }
    if (dir < 0) { for (int i = kStepCount - 1; i >= 0; --i) if (kSteps[i] < percent) return kSteps[i]; return kMin; }
    return clampPercent(percent);
}

// The key a site's zoom is stored under: lower case, no trailing dots, no leading "www." (when a dot remains after it).
// Empty when it cannot be a host name (empty, too long, or with characters a host never has).
inline std::string hostKey(std::string host)
{
    const size_t a = host.find_first_not_of(" \t\r\n"), b = host.find_last_not_of(" \t\r\n");
    host = a == std::string::npos ? std::string() : host.substr(a, b - a + 1);
    for (char& c : host) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.compare(0, 4, "www.") == 0 && host.find('.', 4) != std::string::npos) host.erase(0, 4);
    if (host.empty() || host.size() > kMaxHost || host.front() == '.') return {};
    for (unsigned char c : host)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_')) return {};
    return host;
}

// A stored value: a percent ("110") or an older build's factor ("1.100"). 0 when unusable; else clamped to 50-200.
inline int parseValue(const std::string& text)
{
    const char* s = text.c_str();
    char* end = nullptr;
    const double v = std::strtod(s, &end);
    if (end == s || !std::isfinite(v)) return 0;
    while (*end == ' ' || *end == '\r' || *end == '\n' || *end == '\t') ++end;
    if (*end == '%') ++end;
    while (*end == ' ' || *end == '\r' || *end == '\n' || *end == '\t') ++end;
    if (*end) return 0;
    const double percent = v < 10 ? v * 100 : v;   // older files: a factor 0.3 - 3.0
    if (percent < 30 || percent > 300) return 0;
    return clampPercent(int(std::lround(percent)));
}

// Hosts with their own zoom, oldest change first. At most kMaxEntries: a new one drops the oldest.
class Store {
public:
    int get(const std::string& host) const   // 0: no zoom of its own
    {
        const std::string key = hostKey(host);
        for (const auto& e : list_) if (e.first == key) return e.second;
        return 0;
    }
    bool set(const std::string& host, int percent)
    {
        std::string key = hostKey(host);
        if (key.empty()) return false;
        remove(key);
        list_.emplace_back(std::move(key), clampPercent(percent));
        if (list_.size() > kMaxEntries) list_.erase(list_.begin(), list_.begin() + (list_.size() - kMaxEntries));
        return true;
    }
    bool erase(const std::string& host) { return remove(hostKey(host)); }
    size_t size() const { return list_.size(); }
    void clear() { list_.clear(); }
    const std::vector<std::pair<std::string, int>>& entries() const { return list_; }

    // One file line ("host<TAB>value", any line ending). A later line for the same host wins.
    bool parseLine(const std::string& line)
    {
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) return false;
        const int percent = parseValue(line.substr(tab + 1));
        return percent && set(line.substr(0, tab), percent);
    }
    void parse(const std::string& text)
    {
        size_t at = 0;
        while (at < text.size()) {
            size_t nl = text.find('\n', at);
            if (nl == std::string::npos) nl = text.size();
            parseLine(text.substr(at, nl - at));
            at = nl + 1;
        }
    }
    std::string serialize() const
    {
        std::string out;
        out.reserve(list_.size() * 24);
        for (const auto& e : list_) { out += e.first; out += '\t'; out += std::to_string(e.second); out += '\n'; }
        return out;
    }

private:
    bool remove(const std::string& key)
    {
        if (key.empty()) return false;
        for (auto it = list_.begin(); it != list_.end(); ++it) if (it->first == key) { list_.erase(it); return true; }
        return false;
    }
    std::vector<std::pair<std::string, int>> list_;
};

} // namespace OmniSiteZoom
'''

BROWSER = [
    # the pure header
    ('#include <dirent.h> // OMNI_FEATURES_V1: downloads page\n',
     '#include <dirent.h> // OMNI_FEATURES_V1: downloads page\n'
     '#include "OmniSiteZoom.h" // OMNI_SITE_ZOOM_V1: zoom steps, host keys, site-zoom.txt (pure)\n', False),
    ('static std::unordered_map<std::string, double> omniSiteZoom;\n',
     'static OmniSiteZoom::Store omniSiteZoom; // OMNI_SITE_ZOOM_V1: host -> percent, newest last, at most 500\n', False),
    # load: percent or an older build's factor; keys normalized; newest 500 kept
    ('''            const size_t t = s.find('\\t');
            const double z = t == std::string::npos ? 0 : atof(s.c_str() + t + 1);
            if (z >= 0.3 && z <= 3.0) omniSiteZoom[s.substr(0, t)] = z;
''', '''            omniSiteZoom.parseLine(s); // OMNI_SITE_ZOOM_V1: "host<TAB>percent" (or an older "host<TAB>factor")
''', False),
    # save
    ('''    char z[32];
    for (auto& [host, factor] : omniSiteZoom) { snprintf(z, sizeof(z), "%.3f", factor); zoom += host + "\\t" + z + "\\n"; }
''', '''    zoom = omniSiteZoom.serialize(); // OMNI_SITE_ZOOM_V1: host<TAB>percent lines, newest change last
''', False),
    # lookup
    ('''    auto found = omniSiteZoom.find(host);
    return found == omniSiteZoom.end() ? omniFxDefaultZoom() : found->second; // OMNI_FEATURES_V1: default zoom setting
''', '''    const int percent = omniSiteZoom.get(host); // OMNI_SITE_ZOOM_V1
    return percent ? percent / 100.0 : omniFxDefaultZoom(); // OMNI_FEATURES_V1: default zoom setting
''', False),
    # a step, with a notice
    ('''    const double now = omniZoomFor(host);
    const int last = int(sizeof(omniZoomSteps) / sizeof(omniZoomSteps[0])) - 1;
    int i = 0;   // nearest step
    for (int k = 1; k <= last; ++k) if (std::fabs(omniZoomSteps[k] - now) < std::fabs(omniZoomSteps[i] - now)) i = k;
    const double z = dir == 0 ? omniFxDefaultZoom() : omniZoomSteps[std::clamp(i + dir, 0, last)]; // OMNI_FEATURES_V1: reset = default zoom
    if (std::fabs(z - omniFxDefaultZoom()) < 1e-3) omniSiteZoom.erase(host); else omniSiteZoom[host] = z;
    omniPrefsSave();
    for (auto& t : tabs) if (omniBlockerHostOf(t->url) == host) omniApplySiteZoom(t.get());
    omniPageDirty = true;
''', '''    // OMNI_SITE_ZOOM_V1: 50-200 % steps from the current zoom; reset = the default zoom setting (OMNI_FEATURES_V1)
    const int def = OmniSiteZoom::toPercent(omniFxDefaultZoom()), before = OmniSiteZoom::toPercent(omniZoomFor(host));
    const int z = dir == 0 ? def : OmniSiteZoom::step(before, dir);
    if (z == def) omniSiteZoom.erase(host); else omniSiteZoom.set(host, z);
    omniPrefsSave();
    for (auto& t : tabs) if (omniBlockerHostOf(t->url) == host) omniApplySiteZoom(t.get());
    omniPageDirty = true;
    if (dir != 0 && z == before) notice(std::string("Zoom is at its ") + (dir > 0 ? "largest" : "smallest") + " (" + std::to_string(z) + "%)");
    else notice((dir == 0 ? "Zoom reset to " : "Zoom ") + std::to_string(z) + "% on " + host);
''', False),
    # the Browser tools hint
    ('"D-pad up/down: move   left/right: zoom, mobile site"',
     '"D-pad up/down: move   left/right: zoom this site (remembered), mobile site" /* OMNI_SITE_ZOOM_V1 */', False),
    # tab switch: the shown tab gets its site's zoom (a no-op when it already has it)
    ('''static void omniEverydayActivated()
{
    Tab* tab = active();
    if (!tab || tab->omniLazyURL.empty()) return;
''', '''static void omniEverydayActivated()
{
    Tab* tab = active();
    omniApplySiteZoom(tab); // OMNI_SITE_ZOOM_V1: on tab switch too (compares first; null-safe)
    if (!tab || tab->omniLazyURL.empty()) return;
''', False),
    # L2 + D-pad up / down (OMNI_L2_CHORDS_V1 trees only)
    ('''    if (event.button != SDL_CONTROLLER_BUTTON_X && event.button != SDL_CONTROLLER_BUTTON_Y && event.button != SDL_CONTROLLER_BUTTON_A
        && event.button != SDL_CONTROLLER_BUTTON_B) return false;
    if (!active() || editing || settingsOpen || pageFullscreen || omniOverlayOpen()) return false;
    omniL2ChordUsed = true;
    omniL2Swallow |= bit;
''', '''    const bool omniZoomChord = event.button == SDL_CONTROLLER_BUTTON_DPAD_UP || event.button == SDL_CONTROLLER_BUTTON_DPAD_DOWN; // OMNI_SITE_ZOOM_V1
    if (!omniZoomChord && event.button != SDL_CONTROLLER_BUTTON_X && event.button != SDL_CONTROLLER_BUTTON_Y && event.button != SDL_CONTROLLER_BUTTON_A
        && event.button != SDL_CONTROLLER_BUTTON_B) return false;
    if (!active() || editing || settingsOpen || pageFullscreen || omniOverlayOpen()) return false;
    omniL2ChordUsed = true;
    omniL2Swallow |= bit;
    if (omniZoomChord) {   // OMNI_SITE_ZOOM_V1: L2 + D-pad up / down: zoom this site in / out
        if (omniMenuHost().empty()) notice("Zoom works on web pages");
        else omniZoomStep(event.button == SDL_CONTROLLER_BUTTON_DPAD_UP ? 1 : -1);
        return true;
    }
''', True),
]

QUICK = [
    # one stepper row in lists; the grid keeps its three tiles
    ('''    add(omniQmZoomOut, "Zoom out", page, -1, "\\xe2\\x88\\x92");
    add(omniQmZoomIn, "Zoom in", page, -1, "+");
    add(omniQmZoomReset, "Reset zoom", page, -1, omniFxPercent(omniZoomFor(host)));
''', '''    if (p.cols == 1) {   // OMNI_SITE_ZOOM_V1: a list: one row, D-pad left/right change the zoom, Cross resets it
        OmniFxRow z; z.id = omniQmZoomReset; z.label = "Zoom (this site)"; z.value = omniFxPercent(omniZoomFor(host));
        z.enabled = page; z.stepper = true; z.detail = page ? "Remembered. Cross resets" : "";
        p.rows.push_back(z);
    } else {
    add(omniQmZoomOut, "Zoom out", page, -1, "\\xe2\\x88\\x92");
    add(omniQmZoomIn, "Zoom in", page, -1, "+");
    add(omniQmZoomReset, "Reset zoom", page, -1, omniFxPercent(omniZoomFor(host)));
    }
''', False),
    ('''static bool omniFxQuickInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
''', '''static bool omniFxQuickInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id == omniQmZoomReset && r.stepper && (b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT)) { // OMNI_SITE_ZOOM_V1
        if (r.enabled) omniZoomStep(b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : -1);
        return true;
    }
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
''', False),
    # OMNI_MQ_NATIVE_V1 trees: the zoom row sits in Quick toggles
    ('    case omniMqBlock: case 303: return 2; // existing omniF3Dark\n',
     '    case omniMqBlock: case 303: case omniQmZoomReset: return 2; // existing omniF3Dark; OMNI_SITE_ZOOM_V1: zoom row\n', True),
]
CONTROLS = ('    row("Saved links", ps ? "L2" : "LT");\n',
            '    row("Saved links", ps ? "L2" : "LT");\n'
            '    row("Zoom this site in / out", ps ? "L2 + D-pad up / down" : "LT + D-pad up / down"); // OMNI_SITE_ZOOM_V1\n', True)


def patch(name, edits):
    p = root / name
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s:
        return name + ': already', nl
    done = []
    for old0, new0, optional in edits:
        # files with mixed endings (lines added by earlier patches): the anchor's own line ending decides
        for e in (nl, '\n' if nl == '\r\n' else '\r\n'):
            old, new = old0.replace('\n', e), new0.replace('\n', e)
            if s.count(old):
                break
        else:
            old, new = old0.replace('\n', nl), new0.replace('\n', nl)
        n = s.count(old)
        if n == 0 and optional:
            done.append('skipped optional anchor %r' % old.strip()[:50])
            continue
        if n != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, n, old[:90]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied' + ''.join('; ' + d for d in done), nl


def main():
    browser = (root / 'OmniBrowser.cpp').read_text(encoding='utf-8', errors='replace')
    chord = 'OMNI_L2_CHORDS_V1' in browser
    msg, nl = patch('OmniBrowser.cpp', BROWSER)
    print(msg + ('' if chord or 'already' in msg else ' (no OMNI_L2_CHORDS_V1: no L2 + D-pad zoom)'))
    print(patch('OmniQuickMenu.h', QUICK + ([CONTROLS] if chord else []))[0])
    h = root / 'OmniSiteZoom.h'
    data = HEADER.replace('\n', nl).encode('utf-8')
    if not h.exists() or h.read_bytes() != data:
        h.write_bytes(data)
        print('OmniSiteZoom.h: written')
    else:
        print('OmniSiteZoom.h: already')
    print('applied ' + MARK)


main()
