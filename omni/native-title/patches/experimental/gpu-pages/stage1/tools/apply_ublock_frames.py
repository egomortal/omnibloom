#!/usr/bin/env python3
"""OMNI_UBLOCK_FRAMES_V1 (2026-11-16): uBlock site rules (site CSS, procedural filters, scriptlets) in subframes too,
matched by each frame's OWN host name as desktop uBO does, so ads drawn inside embedded (cross-origin) video players
and other iframes are hidden / defused. Network blocking already covered every frame; this is the in-page part.

Before: with /data/omni/ubo-content-mainframe-only.flag (the console's per-frame cost cut, OMNI_UBO_MAINFRAME_V1) every
uBlock script - including the small per-host site scripts of OMNI_UBO_SITE_V1 - was InjectInTopFrameOnly, so a
player iframe on player.example got nothing, although its host's rules were built and registered anyway.
Now (OmniBlocker.cpp, default on; /data/omni/ublock-frames-off.flag = exactly as before, read when the uBlock
scripts are installed, i.e. at start and when the trusted-site list changes):
  * per-host scripts are registered for all frames; WebKit's own allowlist (*://host/*) still picks, per frame, the
    scripts of that frame's host (document start, before page scripts; about:/blob:/data: frames take their parent's).
    Host keying is unchanged (OmniUBlockFrames::hostKey, the former siteHostOf). Ancestor ("host>>") rules keep
    using the page's top host, guarded at run time, and the trusted-site gate keeps using the top page's host.
  * the host cache is unchanged (built once per host, rebuilt only for a new top page with possibly new ancestor
    rules), and the cap of 48 registered hosts too; but hosts only ever seen inside frames have their own LRU pool of
    at most 16 of those 48, so ad/embed iframes cannot push the pages you visit out of the cache.
  * always-main.js (generic "*" scriptlets, 20 KB) runs in every frame, as in uBO.
  * generic cosmetic filtering stays cheap: always-generic.js (740-785 KB) keeps its top-frame-only setting; while
    it is top-frame only, subframes get just uBO's "highly generic" list from that file (~28 KB of CSS, one
    adoptedStyleSheet, no DOM survey), honouring the frame host's generichide and generic exceptions.
New file engine/entry/OmniUBlockFrames.h (pure C++, host-tested by tools/test_ublock_frames.cpp).
Does not touch the anchors of apply_ublock_missing.py / apply_ublock_refine.py.
usage: apply_ublock_frames.py <engine tree>      (the folder that holds engine/entry)
Idempotent (marker); every anchor must be found exactly once; CRLF files stay CRLF."""
import sys
from pathlib import Path

MARK = 'OMNI_UBLOCK_FRAMES_V1'

HEADER = r'''// OMNI_UBLOCK_FRAMES_V1: uBlock site rules for subframes (embedded players, cross-origin iframes), matched by each
// frame's OWN host name, as desktop uBO does. The pure parts (no WebKit types): host keying, the registration cap with
// a separate least-recently-used pool for hosts only ever seen inside frames, and the small "highly generic" CSS
// script that stands in for the 740 KB generic cosmetic script in subframes. Used by OmniBlocker.cpp; also built by
// tools/test_ublock_frames.cpp (g++, host side).
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <cstddef>
#include <string>
#include <vector>

namespace OmniUBlockFrames {

constexpr const char* killSwitchPath = "/data/omni/ublock-frames-off.flag";
constexpr size_t maxFrameOnlyRegistered = 16;   // of the 48 registered hosts at most 16 may be frame-only (ad/embed hosts)

inline bool validHost(const std::string& host)
{
    if (host.empty() || host.size() > 253) return false;
    return std::all_of(host.begin(), host.end(), [](char c) { return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-'; });
}

// The key a frame's rules are built and registered under: the frame URL's own host, lower case, without user info,
// port or trailing dots. http(s) only (about:/blob:/data: frames match their parent document in WebKit itself;
// IPv6 literals and anything else get no site rules). Same result as the former siteHostOf() in OmniBlocker.cpp.
inline std::string hostKey(const std::string& url)
{
    size_t begin;
    if (url.rfind("https://", 0) == 0) begin = 8;
    else if (url.rfind("http://", 0) == 0) begin = 7;
    else return { };
    auto end = url.find_first_of("/?#", begin);
    std::string authority = url.substr(begin, end == std::string::npos ? std::string::npos : end - begin);
    if (auto at = authority.rfind('@'); at != std::string::npos) authority = authority.substr(at + 1);
    if (authority.empty() || authority[0] == '[') return { };
    if (auto colon = authority.find(':'); colon != std::string::npos) authority.resize(colon);
    std::transform(authority.begin(), authority.end(), authority.begin(), [](unsigned char c) { return static_cast<char>(c >= 'A' && c <= 'Z' ? c + 32 : c); });
    while (!authority.empty() && authority.back() == '.') authority.pop_back();
    return validHost(authority) ? authority : std::string { };
}

// One host whose scripts are on the content controller right now.
struct Registered {
    std::string host;
    unsigned long long used = 0;   // larger = more recently used
    bool frameOnly = false;        // never seen as a page's top document
};

// Which hosts to unregister after `keep` was (re)registered, so that at most maxTotal hosts are registered and at
// most maxFrameOnly of them are frame-only. Least recently used first; `keep` is never chosen. Frame-only hosts
// over their own cap go first, so ad and embed iframes can't push the pages you visit out of the cache.
inline std::vector<std::string> evictions(std::vector<Registered> live, const std::string& keep, size_t maxTotal, size_t maxFrameOnly)
{
    std::sort(live.begin(), live.end(), [](const Registered& a, const Registered& b) { return a.used != b.used ? a.used < b.used : a.host < b.host; });
    size_t total = live.size(), frameOnly = 0;
    for (auto& r : live) if (r.frameOnly) ++frameOnly;
    std::vector<std::string> out;
    std::vector<bool> gone(live.size(), false);
    for (size_t i = 0; i < live.size() && frameOnly > maxFrameOnly; ++i) {
        if (!live[i].frameOnly || live[i].host == keep) continue;
        gone[i] = true; out.push_back(live[i].host); --frameOnly; --total;
    }
    for (size_t i = 0; i < live.size() && total > maxTotal; ++i) {
        if (gone[i] || live[i].host == keep) continue;
        gone[i] = true; out.push_back(live[i].host); --total;
    }
    return out;
}

// Copies a JavaScript string literal, writing non-ASCII UTF-8 as \uXXXX so the script stays an 8-bit (Latin-1)
// string in JavaScriptCore (half the memory of a 16-bit one, in the UI process, the IPC and every web process).
inline bool asciiLiteral(const std::string& in, std::string& out)
{
    out.clear();
    out.reserve(in.size());
    for (size_t i = 0; i < in.size();) {
        unsigned char c = static_cast<unsigned char>(in[i]);
        if (c < 0x80) { out += static_cast<char>(c); ++i; continue; }
        unsigned cp; size_t n;
        if ((c & 0xE0) == 0xC0) { cp = c & 0x1F; n = 2; }
        else if ((c & 0xF0) == 0xE0) { cp = c & 0x0F; n = 3; }
        else if ((c & 0xF8) == 0xF0) { cp = c & 0x07; n = 4; }
        else return false;
        if (i + n > in.size()) return false;
        for (size_t k = 1; k < n; ++k) {
            unsigned char d = static_cast<unsigned char>(in[i + k]);
            if ((d & 0xC0) != 0x80) return false;
            cp = cp << 6 | (d & 0x3F);
        }
        auto hex = [&out](unsigned u) { static const char* x = "0123456789abcdef"; out += "\\u"; for (int s = 12; s >= 0; s -= 4) out += x[(u >> s) & 15]; };
        if (cp >= 0x10000) { cp -= 0x10000; hex(0xD800 | (cp >> 10)); hex(0xDC00 | (cp & 0x3FF)); }
        else hex(cp);
        i += n;
    }
    return true;
}

// Subframes don't get always-generic.js (740-785 KB: a hashed selector table surveyed against every id/class) while
// it is top-frame only (ubo-content-mainframe-only.flag or ubo-site-generic-top-only.flag). Instead they get uBO's
// "highly generic" list (~27 KB of plain CSS: fixed ad sizes and the like) from that same file, inserted once at
// document end. It honours the frame host's generic exceptions and generichide (set by the frame host's own
// site script, document start, same world) and the trusted-site list (the top page's host, as every Omni script).
// The top frame is skipped (it has the full generic script). Returns "" if the generic script has no such list.
inline std::string highlyGenericScript(const std::string& genericSource, const std::string& allowJSON)
{
    static const std::string head = "const omniHighly = \"";
    const size_t start = genericSource.find(head);
    if (start == std::string::npos) return { };
    const size_t open = start + head.size() - 1;   // the opening quote
    size_t close = std::string::npos;
    for (size_t i = open + 1; i < genericSource.size(); ++i) {
        if (genericSource[i] == '\\') { ++i; continue; }
        if (genericSource[i] == '\n') return { };
        if (genericSource[i] == '"') { close = i; break; }
    }
    if (close == std::string::npos || close == open + 1) return { };
    std::string literal;
    if (!asciiLiteral(genericSource.substr(open, close + 1 - open), literal)) return { };
    std::string s =
        "(function omniUBlockFrameGeneric() {\n"
        "if (window.top === window) return;\n"
        "const ALLOW = ";
    s += allowJSON.empty() ? std::string("[]") : allowJSON;
    s += ";\n"
        "const hostsOf = hn => { const a = [hn]; for (let p = 0; ; ) { p = hn.indexOf('.', p) + 1; if (p === 0) break; a.push(hn.slice(p)); } return a; };\n"
        "const entsOf = hns => { const e = []; for (let hn of hns) { for (;;) { const p = hn.lastIndexOf('.'); if (p === -1) break; hn = hn.slice(0, p); e.push(hn + '.*'); } } return e; };\n"
        "const hostMatches = (hn, list) => { if (!hn || list.length === 0) return false; const hns = hostsOf(hn), ens = entsOf(hns); return list.some(p => p.endsWith('.*') ? ens.includes(p) : hns.includes(p)); };\n"
        "const topHost = (() => { try { const a = document.location.ancestorOrigins; const o = a && a.length ? a[a.length - 1] : document.location.origin; const h = new URL(o).hostname; return h || document.location.hostname; } catch { return document.location.hostname; } })();\n"
        "if (hostMatches(topHost, ALLOW)) return;\n"
        "if (self.omniGenericOff === true) return;\n"
        "const exc = new Set(self.omniGenericExc || []);\n"
        "const H = ";
    s += literal;
    s += ";\n"
        "const sel = exc.size === 0 ? H : H.split(',\\n').filter(x => !exc.has(x)).join(',\\n');\n"
        "if (sel === '') return;\n"
        "try { const sheet = new CSSStyleSheet(); sheet.replaceSync(sel + '\\n{display:none!important;}'); document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet]; } catch { }\n"
        "})();\n"
        "void 0;\n";
    return s;
}

} // namespace OmniUBlockFrames
'''

SITE_HOST_OLD = '''std::string siteHostOf(const std::string& url)
{
    size_t begin;
    if (url.rfind("https://", 0) == 0) begin = 8;
    else if (url.rfind("http://", 0) == 0) begin = 7;
    else return { };
    auto end = url.find_first_of("/?#", begin);
    std::string authority = url.substr(begin, end == std::string::npos ? std::string::npos : end - begin);
    if (auto at = authority.rfind('@'); at != std::string::npos) authority = authority.substr(at + 1);
    if (authority.empty() || authority[0] == '[') return { };
    if (auto colon = authority.find(':'); colon != std::string::npos) authority.resize(colon);
    std::transform(authority.begin(), authority.end(), authority.begin(), [](unsigned char c) { return std::tolower(c); });
    while (!authority.empty() && authority.back() == '.') authority.pop_back();
    return validHost(authority) ? authority : std::string { };
}
'''
SITE_HOST_NEW = '''// OMNI_UBLOCK_FRAMES_V1: the same keying, now in OmniUBlockFrames.h (host-tested).
std::string siteHostOf(const std::string& url) { return OmniUBlockFrames::hostKey(url); }
'''

INSTALL_OLD = '''    const bool genericTopOnly = topOnly || !access("/data/omni/ubo-site-generic-top-only.flag", F_OK);
    auto first = siteScript(always, true, false, topOnly, { });
    auto second = siteScript(generic, false, true, genericTopOnly, { });
    ucAddScript(first.get());
    ucAddScript(second.get());
'''
INSTALL_NEW = '''    const bool genericTopOnly = topOnly || !access("/data/omni/ubo-site-generic-top-only.flag", F_OK);
    // OMNI_UBLOCK_FRAMES_V1: site rules reach subframes (the per-host scripts below and in omniBlockerPrepareSite),
    // the generic scriptlets (always-main.js, 20 KB) run in every frame as in uBO, and the generic cosmetic script
    // keeps its setting; while it is top-frame only, subframes get the highly generic CSS (~28 KB) instead.
    siteFrames = access(OmniUBlockFrames::killSwitchPath, F_OK) != 0;
    auto first = siteScript(always, true, false, topOnly && !siteFrames, { });
    auto second = siteScript(generic, false, true, genericTopOnly, { });
    ucAddScript(first.get());
    ucAddScript(second.get());
    size_t frameGenericBytes = 0;
    if (siteFrames && genericTopOnly) {
        const std::string lite = OmniUBlockFrames::highlyGenericScript(generic, allow);
        if (!lite.empty()) {
            auto third = siteScript(lite, false, true, false, { });
            ucAddScript(third.get());
            frameGenericBytes = lite.size();
        }
    }
'''
LOG_OLD = '''    siteAllow = allow;
    siteActive = true;
'''
LOG_NEW = '''    siteAllow = allow;
    siteActive = true;
    if (siteFrames) // OMNI_UBLOCK_FRAMES_V1
        fprintf(stderr, "browser: uBlock site rules in subframes too (OMNI_UBLOCK_FRAMES_V1; each frame's own host; subframe generic: %s %zu B; frame-only hosts <= %zu of %zu)\\n",
            !genericTopOnly ? "full" : frameGenericBytes ? "highly generic CSS" : "none", !genericTopOnly ? generic.size() : frameGenericBytes,
            OmniUBlockFrames::maxFrameOnlyRegistered, siteMaxRegistered);
'''

LRU_OLD = '''    // Keep the number of patterns every frame checks small: drop the least recently used hosts' scripts.
    size_t registered = 0;
    for (auto& item : siteHosts) if (item.second.main || item.second.isolated) ++registered;
    while (registered > siteMaxRegistered) {
        auto oldest = siteHosts.end();
        for (auto it = siteHosts.begin(); it != siteHosts.end(); ++it)
            if ((it->second.main || it->second.isolated) && it->first != host && (oldest == siteHosts.end() || it->second.used < oldest->second.used)) oldest = it;
        if (oldest == siteHosts.end()) break;
        siteUnregister(oldest->second);
        siteHosts.erase(oldest); // rebuilt on its next navigation
        --registered;
    }
'''
LRU_NEW = '''    // Keep the number of patterns every frame checks small: drop the least recently used hosts' scripts.
    // OMNI_UBLOCK_FRAMES_V1: hosts only seen inside frames (ads, players) have their own LRU cap within the 48.
    std::vector<OmniUBlockFrames::Registered> live;
    for (auto& item : siteHosts) if (item.second.main || item.second.isolated) live.push_back({ item.first, item.second.used, !item.second.topSeen });
    for (auto& victim : OmniUBlockFrames::evictions(std::move(live), host, siteMaxRegistered, siteFrames ? OmniUBlockFrames::maxFrameOnlyRegistered : siteMaxRegistered)) {
        auto it = siteHosts.find(victim);
        if (it == siteHosts.end()) continue;
        siteUnregister(it->second);
        siteHosts.erase(it); // rebuilt on its next navigation
    }
'''

EDITS = [
    ('#include "OmniUBlockSite.h"\n',
     '#include "OmniUBlockSite.h"\n#include "OmniUBlockFrames.h" // ' + MARK + '\n'),
    ('constexpr size_t siteMaxTops = 8;\n',
     'constexpr size_t siteMaxTops = 8;\n'
     '// ' + MARK + ': per-host scripts in all frames (each frame matches its own host); /data/omni/ublock-frames-off.flag\n'
     '// = top frame only with ubo-content-mainframe-only.flag, as before. Set by installSiteScripts().\n'
     'bool siteFrames = false;\n'),
    ('    unsigned long long used = 0;\n};\nstd::unordered_map<std::string, SiteEntry> siteHosts;\n',
     '    unsigned long long used = 0;\n'
     '    bool topSeen = false; // ' + MARK + ': seen as a page\'s top document (otherwise a frame-only host)\n'
     '};\nstd::unordered_map<std::string, SiteEntry> siteHosts;\n'),
    (SITE_HOST_OLD, SITE_HOST_NEW),
    (INSTALL_OLD, INSTALL_NEW),
    (LOG_OLD, LOG_NEW),
    ('    entry.used = ++siteClock;\n',
     '    entry.used = ++siteClock;\n    if (!subframe) entry.topSeen = true; // ' + MARK + '\n'),
    ('entry.main = siteScript(built.main, true, false, siteTopOnly, host);',
     'entry.main = siteScript(built.main, true, false, siteTopOnly && !siteFrames, host);'),
    ('entry.isolated = siteScript(built.isolated, true, true, siteTopOnly, host);',
     'entry.isolated = siteScript(built.isolated, true, true, siteTopOnly && !siteFrames, host);'),
    (LRU_OLD, LRU_NEW),
]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    entry = Path(sys.argv[1]) / 'engine' / 'entry'
    p = entry / 'OmniBlocker.cpp'
    raw = p.read_bytes().decode('utf-8')
    crlf = '\r\n' in raw
    nl = '\r\n' if crlf else '\n'
    t = raw.replace('\r\n', '\n')
    if MARK in t:
        print('OmniBlocker.cpp: already ' + MARK)
    else:
        if 'OMNI_UBO_SITE_V1' not in t:
            sys.exit('OmniBlocker.cpp: no OMNI_UBO_SITE_V1 (per-site rules): wrong tree')
        for old, new in EDITS:
            if t.count(old) != 1:
                sys.exit('OmniBlocker.cpp: anchor found %d times: %r' % (t.count(old), old[:80]))
            t = t.replace(old, new, 1)
        p.write_bytes((t.replace('\n', nl) if crlf else t).encode('utf-8'))
        print('OmniBlocker.cpp: applied %s (%d edits)' % (MARK, len(EDITS)))
    h = entry / 'OmniUBlockFrames.h'
    data = HEADER.replace('\n', nl).encode('utf-8')
    if h.exists() and h.read_bytes() == data:
        print('OmniUBlockFrames.h: already ' + MARK)
    else:
        h.write_bytes(data)
        print('OmniUBlockFrames.h: written')


main()
