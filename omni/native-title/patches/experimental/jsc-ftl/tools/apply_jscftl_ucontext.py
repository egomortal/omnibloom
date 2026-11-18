#!/usr/bin/env python3
"""OMNI_JSC_UCONTEXT_V1 (P2): WTF's registersFromUContext() uses this firmware's ucontext layout.

On the PS5 the saved machine context sits 48 bytes later than in the SDK's FreeBSD ucontext_t (uc_mcontext at +64,
not +16). Omni already fixed the thread-suspend handler (WTF/wtf/posix/ThreadingPOSIX.cpp, "PS5 inserts 48 bytes
before uc_mcontext"), but registersFromUContext() in WTF/wtf/PlatformRegisters.h still returns &ucontext->uc_mcontext.
It is what JavaScriptCore's fault handler (WTF/wtf/threads/Signals.cpp jscSignalHandler) hands to every
SIGSEGV/SIGBUS handler: the DFG/FTL signal-based VM traps (hlt in optimized code) and any Wasm fault handling.
With the header offset a handler would read a garbage PC, decline the fault, and the child would die silently.
OMNI_JSC_DFGFTL_V1 keeps polling traps on regardless; this makes the signal path correct anyway.

usage: apply_jscftl_ucontext.py <tree root containing webkit/>   anchored, every anchor checked before writing, idempotent.
Backups: $OMNI_PATCH_BACKUP_DIR/<relpath>.before-<MARK> if set, else <file>.before-<MARK>.
"""
import os, sys
from pathlib import Path

MARK = 'OMNI_JSC_UCONTEXT_V1'

def patch_files(root, plan):
    todo, results = [], []
    for rel, edits in plan:
        p = root / rel
        if not p.is_file():
            sys.exit('%s: file missing' % p)
        s = p.read_text(encoding='utf-8')
        if MARK in s:
            results.append(('already', rel)); continue
        t = s
        for old, new in edits:
            n = t.count(old)
            if n != 1:
                sys.exit('%s: anchor found %d times: %r' % (rel, n, old[:100]))
            t = t.replace(old, new, 1)
        if MARK not in t:
            sys.exit('%s: patched text lacks the marker %s' % (rel, MARK))
        todo.append((rel, p, s, t))
    for rel, p, s, t in todo:
        bdir = os.environ.get('OMNI_PATCH_BACKUP_DIR')
        b = (Path(bdir) / (rel + '.before-' + MARK)) if bdir else p.with_name(p.name + '.before-' + MARK)
        b.parent.mkdir(parents=True, exist_ok=True)
        if not b.exists():
            b.write_text(s, encoding='utf-8')
        p.write_text(t, encoding='utf-8')
        results.append(('applied', rel))
    for state, rel in results:
        print('%s %s %s' % (state, MARK, rel))
    print('applied' if any(r[0] == 'applied' for r in results) else 'already')

if len(sys.argv) != 2:
    sys.exit(__doc__)
root = Path(sys.argv[1])

patch_files(root, [('webkit/Source/WTF/wtf/PlatformRegisters.h', [
    ('inline PlatformRegisters& registersFromUContext(ucontext_t* ucontext)\n'
     '{\n'
     '#if OS(OPENBSD)\n',
     'inline PlatformRegisters& registersFromUContext(ucontext_t* ucontext)\n'
     '{\n'
     '#if PLATFORM(PLAYSTATION)\n'
     '    // OMNI_JSC_UCONTEXT_V1: this firmware saves the machine context 48 bytes later than the SDK\'s FreeBSD\n'
     '    // ucontext_t says (+64, not +16): the same fix as the suspend handler in posix/ThreadingPOSIX.cpp.\n'
     '    static_assert(offsetof(ucontext_t, uc_mcontext) == 16 || offsetof(ucontext_t, uc_mcontext) == 64);\n'
     '    return *std::bit_cast<PlatformRegisters*>(reinterpret_cast<char*>(ucontext) + 64);\n'
     '#elif OS(OPENBSD)\n'),
])])
