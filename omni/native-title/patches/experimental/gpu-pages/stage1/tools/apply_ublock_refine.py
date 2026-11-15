#!/usr/bin/env python3
"""OMNI_UBLOCK_REFINE_V1 (2026-11-15, refinement review of omni/engine/entry). Applied after OMNI_UBLOCK_MISSING_V1.

OmniUBlock.cpp (network process in the engine child, popup check in the title):
  1. One request the uBlock matcher can't judge (a JavaScript exception, a non-number answer) blocked EVERY request
     for the rest of the session ("ublock-error"). Now that request alone is blocked; 8 failures in a row still mean
     the engine is broken and switch to block-everything, as before.
  2. The popup filter's wildcard matcher was recursive per '*' inside a scan over every URL position: a long crafted
     popup URL against rules with several '*' took ~n^3 steps on the UI thread (createNewPage). Now the standard
     iterative last-star backtracking match, O(url x pattern), with the unanchored scan folded in as a leading '*'.
  3. The private-network guard checked IPv6 by text: WebKit writes IPv4-mapped addresses in hex ("::ffff:7f00:1"),
     so a public page could reach 127.0.0.1 / the LAN through them, and "::" was not covered. Now by bytes
     (inet_pton): ::, ::1, IPv4-mapped/compatible (judged as IPv4), fc00::/7, fe80::/10, fec0::/10; 0.0.0.0/8.
  4. readAsset() returned "" for a missing file AND for a read error / a file over 8 MB, so a damaged rule file was
     treated like "not installed" (pages load with uBlock off). Now only a missing (ENOENT) or empty file is
     "missing"; an unreadable or oversized one is a filter failure (requests blocked, red shield), as before V1.
  6. OmniBrowser.cpp omniShortcutsSave(): a failed write (full disk) no longer replaces shortcuts.txt.
  5. The log line and the Omni notice said "pages load unfiltered" / "Ad block is off"; the basic host blocker can
     still be on. Now "most ads aren't blocked".
usage: apply_ublock_refine.py --ublock OmniUBlock.cpp [--browser OmniBrowser.cpp]
Idempotent (marker in each file); every anchor must be found exactly once; CRLF files stay CRLF."""
import argparse
import sys
from pathlib import Path

MARK = 'OMNI_UBLOCK_REFINE_V1'

GLOB_OLD = '''// Wildcard match of p[pi..] against s[si..]; `*` any run, `^` separator or end.
bool globAt(const std::string& p, size_t pi, const std::string& s, size_t si, bool endAnchor, bool matchCase, int depth) {
    if (depth > 64) return false;
    while (pi < p.size()) {
        char c = p[pi];
        if (c == '*') {
            while (pi < p.size() && p[pi] == '*') ++pi;
            if (pi == p.size()) return true;
            for (size_t k = si; k <= s.size(); ++k) if (globAt(p, pi, s, k, endAnchor, matchCase, depth + 1)) return true;
            return false;
        }
        if (c == '^') {
            if (si == s.size()) { ++pi; continue; }
            if (!isSeparator(s[si])) return false;
            ++si; ++pi; continue;
        }
        if (c == '|' && pi + 1 == p.size()) { endAnchor = true; ++pi; continue; }
        if (si >= s.size() || (matchCase ? s[si] : lower(s[si])) != c) return false;
        ++si; ++pi;
    }
    return !endAnchor || si == s.size();
}
'''
GLOB_NEW = '''// Wildcard match of p[pi..] against s[si..]; `*` any run, `^` separator or end, `|` at the end = end of s.
// OMNI_UBLOCK_REFINE_V1: iterative last-star backtracking, O(|s| x |p|). The recursive version (one recursion per
// '*', inside a scan over every start position) took ~n^3 steps on long crafted popup URLs, on the UI thread.
// `floating`: the match may start anywhere at or after si (an implicit leading '*'), which replaces that scan.
bool globAt(const std::string& p, size_t pi, const std::string& s, size_t si, bool matchCase, bool floating) {
    if (floating && si >= s.size()) return false;   // as the old scan: a start position inside the URL
    size_t starP = floating ? pi : std::string::npos, starS = si;
    bool realStar = !floating;
    for (;;) {
        if (pi < p.size() && p[pi] == '*') {
            while (pi < p.size() && p[pi] == '*') ++pi;
            if (pi == p.size()) return true;
            starP = pi; starS = si; realStar = true; continue;
        }
        if (pi == p.size()) return true;   // the rest of the URL is free (as before: no implicit end anchor)
        if (p[pi] == '|' && pi + 1 == p.size()) {
            if (si == s.size()) return true;
        } else if (p[pi] == '^') {
            if (si == s.size()) { ++pi; continue; }
            if (isSeparator(s[si])) { ++si; ++pi; continue; }
        } else if (si < s.size() && (matchCase ? s[si] : lower(s[si])) == p[pi]) {
            ++si; ++pi; continue;
        }
        // mismatch: let the last '*' take one more character, or fail
        if (starP == std::string::npos || starS >= s.size() || (!realStar && starS + 1 >= s.size())) return false;
        pi = starP; si = ++starS;
    }
}
'''

EDITS_UBLOCK = [
    ('#include <cstdio>\n', '#include <cerrno>   // OMNI_UBLOCK_REFINE_V1\n#include <cstdio>\n'),
    ('// OMNI_UBLOCK_MISSING_V1: no rule files (an install without them) -> pages load unfiltered and Omni says so, once.\n',
     '// OMNI_UBLOCK_REFINE_V1: a request the matcher can\'t judge is blocked on its own; only 8 in a row mean the engine is\n'
     '// broken (then every request is blocked for the session, as before). One odd URL used to switch filtering to\n'
     '// "block everything" until Omni restarted.\n'
     'int failedInARow = 0;\n'
     'bool matchFailure() {\n'
     '    if (++failedInARow >= 8) return filterFailure();\n'
     '    fprintf(stderr, "ublock engine: a request could not be judged; blocked it (%d in a row)\\n", failedInARow);\n'
     '    return true;\n'
     '}\n'
     '// OMNI_UBLOCK_MISSING_V1: no rule files (an install without them) -> pages load unfiltered and Omni says so, once.\n'),
    ('rule files missing; pages load unfiltered (Omnibloom Setup > Repair installs them)',
     'rule files missing; uBlock filtering off, basic host blocking only (Omnibloom Setup > Repair installs them)'),
    ('std::string readAsset(const char* name) {\n',
     '// OMNI_UBLOCK_REFINE_V1: set when a rule file is there but can\'t be read (or is over 8 MB). That is a failure,\n'
     '// not "missing": only a missing or empty file loads pages without uBlock.\n'
     'bool assetBroken = false;\n'
     'std::string readAsset(const char* name) {\n'),
    ('    if (!file) return result;\n',
     '    if (!file) { if (errno != ENOENT) assetBroken = true; return result; }   // OMNI_UBLOCK_REFINE_V1\n'),
    ('    if (ferror(file) || result.size() > 8 * 1024 * 1024) result.clear();\n',
     '    if (ferror(file) || result.size() > 8 * 1024 * 1024) { result.clear(); assetBroken = true; }   // OMNI_UBLOCK_REFINE_V1\n'),
    ('    auto bundle = readAsset("ublock-engine.js");\n',
     '    assetBroken = false;   // OMNI_UBLOCK_REFINE_V1\n    auto bundle = readAsset("ublock-engine.js");\n'),
    ('{ engine.missing = true; fprintf(stderr,"ublock engine: missing assets (%s)\\n", engine.compiledName); return false; }',
     '{ engine.missing = !assetBroken; fprintf(stderr,"ublock engine: %s assets (%s)\\n", assetBroken ? "unreadable" : "missing", engine.compiledName); return false; }'),
    ('    if (exception) { report(ctx, exception); return filterFailure(); }\n'
     '    if (!result || !JSValueIsNumber(ctx, result)) return filterFailure();\n'
     '    double decision = JSValueToNumber(ctx, result, nullptr);\n'
     '    if (decision != 0 && decision != 1 && decision != 2) return filterFailure();\n'
     '    return decision == 1;\n',
     '    if (exception) { report(ctx, exception); return matchFailure(); }   // OMNI_UBLOCK_REFINE_V1\n'
     '    if (!result || !JSValueIsNumber(ctx, result)) return matchFailure();\n'
     '    double decision = JSValueToNumber(ctx, result, nullptr);\n'
     '    if (decision != 0 && decision != 1 && decision != 2) return matchFailure();\n'
     '    failedInARow = 0;\n'
     '    return decision == 1;\n'),
    (GLOB_OLD, GLOB_NEW),
    ('            if ((i == hostStart || url[i - 1] == \'.\') && globAt(pattern, 2, url, i, false, matchCase, 0)) return true;\n',
     '            if ((i == hostStart || url[i - 1] == \'.\') && globAt(pattern, 2, url, i, matchCase, false)) return true;\n'),
    ('    if (pattern[0] == \'|\') return globAt(pattern, 1, url, 0, false, matchCase, 0);\n'
     '    for (size_t i = 0; i < url.size(); ++i) if (globAt(pattern, 0, url, i, false, matchCase, 0)) return true;\n'
     '    return false;\n',
     '    if (pattern[0] == \'|\') return globAt(pattern, 1, url, 0, matchCase, false);\n'
     '    return globAt(pattern, 0, url, 0, matchCase, true);   // OMNI_UBLOCK_REFINE_V1: anywhere in the URL\n'),
    ('        return (x >> 24) == 10 || (x >> 24) == 127 || (x >> 20) == 0xAC1 || (x >> 16) == 0xC0A8 || (x >> 16) == 0xA9FE || x == 0 || (x >> 22) == (100u << 2 | 1);\n',
     '        return (x >> 24) == 10 || (x >> 24) == 127 || (x >> 20) == 0xAC1 || (x >> 16) == 0xC0A8 || (x >> 16) == 0xA9FE || (x >> 24) == 0 || (x >> 22) == (100u << 2 | 1);\n'),
    ('    // IPv6 by text (no in6_addr needed): loopback, unique-local fc00::/7, link-local fe80::/10, IPv4-mapped ::ffff:a.b.c.d\n'
     '    if (h.find(\':\') != std::string::npos) {\n'
     '        if (h == "::1" || h == "0:0:0:0:0:0:0:1") return true;\n'
     '        if (h.rfind("::ffff:", 0) == 0 && h.find(\'.\') != std::string::npos) return pnaPrivate(h.substr(7));\n',
     '    // OMNI_UBLOCK_REFINE_V1: IPv6 by its bytes. WebKit writes IPv4-mapped addresses in hex ("::ffff:7f00:1"), which\n'
     '    // the text check below missed, and "::" was not covered. Text check only for what inet_pton refuses (zone ids).\n'
     '    if (h.find(\':\') != std::string::npos) {\n'
     '        unsigned char b[16];\n'
     '        if (inet_pton(AF_INET6, h.c_str(), b) == 1) {\n'
     '            static const unsigned char zero[10] = {};\n'
     '            if (!memcmp(b, zero, 10) && ((b[10] == 0xff && b[11] == 0xff) || (!b[10] && !b[11]))) {   // ::ffff:a.b.c.d, ::a.b.c.d\n'
     '                if (!b[10] && !b[12] && !b[13] && !b[14] && b[15] <= 1) return true;                    // ::, ::1\n'
     '                char v4[16]; snprintf(v4, sizeof v4, "%u.%u.%u.%u", b[12], b[13], b[14], b[15]);\n'
     '                return pnaPrivate(v4);\n'
     '            }\n'
     '            return (b[0] & 0xfe) == 0xfc || (b[0] == 0xfe && (b[1] & 0x80) == 0x80);   // fc00::/7; fe80::/10 + fec0::/10\n'
     '        }\n'
     '        if (h == "::1" || h == "0:0:0:0:0:0:0:1") return true;\n'
     '        if (h.rfind("::ffff:", 0) == 0 && h.find(\'.\') != std::string::npos) return pnaPrivate(h.substr(7));\n'),
]

EDITS_BROWSER = [
    ('    fclose(f);\n    rename("/data/omni/shortcuts.tmp", "/data/omni/shortcuts.txt");\n',
     '    // OMNI_UBLOCK_REFINE_V1 (refinement): replace the list only when the new file was written in full. A full disk\n'
     '    // used to leave a cut-off file that then replaced the saved shortcuts.\n'
     '    bool written = !ferror(f);\n'
     '    if (fclose(f) || !written) { unlink("/data/omni/shortcuts.tmp"); notice("Couldn\'t save shortcuts"); return; }\n'
     '    rename("/data/omni/shortcuts.tmp", "/data/omni/shortcuts.txt");\n'),
    ('notice("Ad block is off: its rule files are missing. Run Omnibloom Setup > Repair.");',
     'notice("Ad block rules are missing, so most ads aren\'t blocked. Run Omnibloom Setup > Repair."); /* OMNI_UBLOCK_REFINE_V1 */'),
]


def patch(path, edits):
    p = Path(path)
    raw = p.read_bytes().decode('utf-8')
    crlf = '\r\n' in raw
    t = raw.replace('\r\n', '\n')
    if MARK in t:
        print('%s: already %s' % (p.name, MARK))
        return
    for old, new in edits:
        if t.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (p.name, t.count(old), old[:80]))
        t = t.replace(old, new, 1)
    if crlf:
        t = t.replace('\n', '\r\n')
    p.write_bytes(t.encode('utf-8'))
    print('%s: applied %s (%d edits)' % (p.name, MARK, len(edits)))


ap = argparse.ArgumentParser()
ap.add_argument('--ublock', required=True)
ap.add_argument('--browser')
a = ap.parse_args()
patch(a.ublock, EDITS_UBLOCK)
if a.browser:
    patch(a.browser, EDITS_BROWSER)
