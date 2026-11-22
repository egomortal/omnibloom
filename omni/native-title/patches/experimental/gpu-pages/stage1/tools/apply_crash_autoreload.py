#!/usr/bin/env python3
"""OMNI_CRASH_AUTORELOAD_V1 (2026-11-19, owner: "heavy memory pages and reloading", "fix it ... and improve on it").

On top of OMNI_CRASH_CHOICES_V1 (apply_crash_choices.py, run it first). Two changes:
  1. The SHOWN tab also gets the one automatic reload (before: background tabs only; a shown tab always got the panel).
     The first crash on a site reloads at once with a notice; the loop guard is unchanged (the 2nd crash on the same host
     within 5 min shows the panel with its choices), so a page that keeps crashing cannot loop. Never in self-tests.
  2. Honest texts: the panel no longer says "often memory on a heavy page" (the 2026-11-19 crashes were a compositor
     thread assertion, a video-size bug and allocator traps, not memory); the notice covers shown and background tabs.
Patches engine/entry/OmniCrashChoices.h and engine/entry/OmniCrashChoicesShell.h under the given tree.
usage: apply_crash_autoreload.py <tree root holding engine/entry>"""
import sys
from pathlib import Path

MARK = 'OMNI_CRASH_AUTORELOAD_V1'
root = Path(sys.argv[1]) / 'engine/entry'
EDITS = {
    'OmniCrashChoices.h': [
        ('constexpr const char* kBody = "The page\'s process ended (often memory on a heavy page). Your other tabs are fine.";\n',
         'constexpr const char* kBody = "This page stopped unexpectedly and could not be restarted. Your other tabs are fine.";   // ' + MARK + '\n'),
        ('constexpr const char* kAutoNotice = "This tab stopped in the background. Reloading...";\n',
         'constexpr const char* kAutoNotice = "This page stopped unexpectedly. Reloading...";   // ' + MARK + ': shown or background tab\n'),
    ],
    'OmniCrashChoicesShell.h': [
        ('    s.autoPending = &tab != active() && ledger.autoReloadOk(s.host);\n',
         '    s.autoPending = ledger.autoReloadOk(s.host);   // ' + MARK + ': the shown tab too (loop guard unchanged)\n'),
        ('        fprintf(stderr, "OMNI CRASH: background crash, reloading on show\\n"); fflush(stderr);\n',
         '        fprintf(stderr, "OMNI CRASH: automatic reload (first crash on this site in 5 min)\\n"); fflush(stderr);   /* ' + MARK + ' */\n'),
    ],
}
done = 0
for name, edits in EDITS.items():
    p = root / name
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    s = raw.replace('\r\n', '\n')
    if MARK in s:
        continue
    for old, _ in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old.strip()[:80]))
    for old, new in edits:
        s = s.replace(old, new, 1)
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    done += 1
print('applied' if done else 'already', '%d files' % done)
