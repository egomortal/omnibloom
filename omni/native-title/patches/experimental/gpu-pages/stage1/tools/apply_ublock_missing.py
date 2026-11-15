#!/usr/bin/env python3
"""OMNI_UBLOCK_MISSING_V1 (2026-11-15): when uBlock's rule files are missing, pages load (unfiltered) and Omni says so,
instead of every request failing with "Filtering failed (error 1)" for the whole session.

Why: Omnibloom Setup turns the native blocker on (ublock-native.flag) but, up to v0.5.1, never installed its rule files
(/data/omni/ublock-engine.js, ublock-compiled.txt, public-suffix-list.dat). On a fresh install the network process found
no files, failed closed and blocked everything (seen on a user's console 2026-11-15). Setup now installs them; this makes
Omni recover if they are ever missing again. Any OTHER failure (a JS exception, a bad decision) still fails closed.

  - OmniUBlock.cpp: missing files -> /data/omni/ublock-missing.flag + one log line; requests are allowed this session.
  - OmniBlocker.cpp: the flag counts as a blocker error (red shield, "Error" in menus); cleared at start like the others.
  - OmniBrowser.cpp: one notice: "Ad block is off: its rule files are missing. Run Omnibloom Setup > Repair."
Idempotent; each anchor must be found exactly once; line endings are kept. A file not given is skipped.
usage: apply_ublock_missing.py [--ublock OmniUBlock.cpp] [--blocker OmniBlocker.cpp ...] [--browser OmniBrowser.cpp]"""
import argparse
import sys
from pathlib import Path

MARK = 'OMNI_UBLOCK_MISSING_V1'
NL = '\n'
CRLF = '\r\n'

UBLOCK = [
    ('    bool attempted = false;\n    bool failed = false;\n',
     '    bool attempted = false;\n    bool failed = false;\n    bool missing = false;   // ' + MARK + ': the rule files are not there\n'),
    ('bool filteringOff() {\n',
     '// ' + MARK + ': no rule files (an install without them) -> pages load unfiltered and Omni says so, once.\n'
     'bool filesMissing() {\n'
     '    static bool said = false;\n'
     '    if (!said) {\n'
     '        said = true;\n'
     '        unlink("/data/omni/ublock-ready.flag");\n'
     '        if (FILE* file = fopen("/data/omni/ublock-missing.flag", "w")) { fputs("1\\n", file); fclose(file); }\n'
     '        fprintf(stderr, "ublock engine: rule files missing; pages load unfiltered (Omnibloom Setup > Repair installs them)\\n");\n'
     '    }\n'
     '    return false;\n'
     '}\n'
     'bool filteringOff() {\n'),
    # Windows line endings (a rule file copied from a Windows checkout) made the engine load but match nothing.
    ('    fclose(file); return result;\n',
     '    fclose(file);\n'
     '    size_t kept = 0;   // ' + MARK + ': drop CR (a file with Windows line endings loaded but blocked nothing)\n'
     '    for (char c : result) if (c != \'\\r\') result[kept++] = c;\n'
     '    result.resize(kept);\n'
     '    return result;\n'),
    ('    if (bundle.empty() || compiled.empty() || suffixes.empty()) { fprintf(stderr,"ublock engine: missing assets (%s)\\n", engine.compiledName); return false; }\n',
     '    if (bundle.empty() || compiled.empty() || suffixes.empty()) { engine.missing = true; fprintf(stderr,"ublock engine: missing assets (%s)\\n", engine.compiledName); return false; }\n'),
    ('    if (!initialize(network)) return filterFailure();\n',
     '    if (!initialize(network)) return network.missing ? filesMissing() : filterFailure();   // ' + MARK + '\n'),
]
BLOCKER = [
    ('    nativeFailed = !access("/data/omni/ublock-error.flag", F_OK);\n',
     '    nativeFailed = !access("/data/omni/ublock-error.flag", F_OK) || !access("/data/omni/ublock-missing.flag", F_OK);   // ' + MARK + '\n'),
    ('    unlink("/data/omni/ublock-error.flag");\n',
     '    unlink("/data/omni/ublock-error.flag");\n    unlink("/data/omni/ublock-missing.flag");   // ' + MARK + '\n'),
]
BROWSER = [
    ('omniBlockerPoll();',
     'omniBlockerPoll(); { static bool omniUbMissingTold = false; if (!omniUbMissingTold && !access("/data/omni/ublock-missing.flag", F_OK)) { omniUbMissingTold = true; notice("Ad block is off: its rule files are missing. Run Omnibloom Setup > Repair."); } } /* ' + MARK + ' */'),
]


def apply(path, edits):
    p = Path(path)
    raw = p.read_bytes().decode('utf-8')
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    if MARK in t:
        print('already', p.name)
        return
    for old, new in edits:
        if t.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (p, t.count(old), old[:80]))
        t = t.replace(old, new, 1)
    if crlf:
        t = t.replace(NL, CRLF)   # keep the file's line endings
    p.write_bytes(t.encode('utf-8'))
    print('patched', p)


ap = argparse.ArgumentParser()
ap.add_argument('--ublock')
ap.add_argument('--blocker', action='append', default=[])
ap.add_argument('--browser')
a = ap.parse_args()
if a.ublock:
    apply(a.ublock, UBLOCK)
for b in a.blocker:
    apply(b, BLOCKER)
if a.browser:
    apply(a.browser, BROWSER)
