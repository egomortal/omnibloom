"""OMNI_FIRST_RUN_V1 (2026-11-13, public report): Omni didn't start after a fresh install.

The title's main() (engine/entry/OmniMain.cpp, shared with the old test engine) needed two files that only consoles with
an older Omni setup have, and that Setup never creates:
  /data/omni/omni-engine.elf     "upload omni-engine.elf to /data/omni first" and exit. The title never runs this file:
                                 its children are started from /data/omni/native/omni-engine-child.elf
                                 (NativeLauncherState.cpp maps the name), and its resources are built in.
  /data/omni/browser-mode.flag   without it main() ran the engine self-test, not the browser.

Now: the self path falls back to the installed native child, and the browser is the default; the old self-test runs
only with /data/omni/engine-selftest.flag. Consoles that have the old files behave exactly as before.

usage: apply_first_run.py <engine tree>   (edits engine/entry/OmniMain.cpp; anchored, idempotent)
"""
import sys
from pathlib import Path

MARK = 'OMNI_FIRST_RUN_V1'
p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniMain.cpp'
raw = p.read_bytes()
nl = '\r\n' if b'\r\n' in raw else '\n'
s = raw.decode('utf-8')
if MARK in s:
    print('already'); sys.exit(0)


def rep(old, new, count=1):
    global s
    old, new = old.replace('\n', nl), new.replace('\n', nl)
    if s.count(old) != count:
        sys.exit('anchor found %d times (want %d): %r' % (s.count(old), count, old[:80]))
    s = s.replace(old, new)


rep('static const char* const kSelf[] = { "/data/omni/omni-engine.elf", nullptr };',
    '// OMNI_FIRST_RUN_V1: a fresh install has only the native child engine (the title maps the first name to it anyway).\n'
    'static const char* const kSelf[] = { "/data/omni/omni-engine.elf", "/data/omni/native/omni-engine-child.elf", nullptr };')
rep('static void setResourceEnv()\n{',
    '// OMNI_FIRST_RUN_V1: the browser is the default; the old engine self-test only with /data/omni/engine-selftest.flag\n'
    '// (it used to need /data/omni/browser-mode.flag, which a fresh install never has).\n'
    'static bool omniBrowserModeWanted() { return access("/data/omni/engine-selftest.flag", F_OK) != 0; }\n'
    'static void setResourceEnv()\n{')
rep('!access("/data/omni/browser-mode.flag", F_OK)', 'omniBrowserModeWanted()', count=2)
p.write_bytes(s.encode('utf-8'))
print('applied OMNI_FIRST_RUN_V1')
