#!/usr/bin/env python3
"""OMNI_LAYERS_DEFAULT_ON_V1 (2026-11-18, owner: "Turn layers on" + "Yes, next preview"): GPU page layers (stage 1),
async scrolling and the async readback ON BY DEFAULT; each keeps its existing kill switch.

Evidence: with OMNI_GPU_ONE_SUBMITTER_V1, 20/20 layers-on console runs clean (12 x 4K YouTube 200 s, 8 x movy.sx scroll
with async + asyncread), 0 hangs (old rate ~2 in 10); movy.sx ~2.6x more screen updates.
Before: each part was opt-in (gpu-pages-stage1.flag, gpu-pages-async.flag, gpu-pages-asyncread.flag). Now:
  stage 1    on unless /data/omni/gpu-pages-stage1-off.flag       (title service + engine child)
  async      on unless /data/omni/gpu-pages-async-off.flag         (needs stage 1, as before)
  asyncread  on unless /data/omni/gpu-pages-asyncread-off.flag
The old on-flags are simply ignored. Only builds that also carry the one-submitter lock may use this (Bloom Preview
line); the stable build is not rebuilt.

Modes (idempotent per file, "applied|already <file>"; every anchor must be found exactly once; CRLF kept):
  title <OmniGpuPagesService.cpp>          the title's layers service
  child <dir holding ogp-s1-child.c>       the engine child's constructor (a COPY the child recipe compiles)
  inc   <dir holding ogp-s1b-async.inc and ogp-s1-surface.inc>   the engine child's tree copies (NOT the title tree: the
                                           title compiles those .inc only for its in-process engine, which never runs
                                           them, and its recipe gates them equal to the rc4 pair's)
usage: apply_layers_default_on.py MODE PATH"""
import shutil
import sys
from pathlib import Path

MARK = 'OMNI_LAYERS_DEFAULT_ON_V1'

EDITS = {
    'title': {'OmniGpuPagesService.cpp': [
        ('    if (access(kFlag, F_OK) || !access(kOff, F_OK)) return;   // the default: nothing starts\n',
         '    if (!access(kOff, F_OK)) return;   // ' + MARK + ': on unless the kill switch (was: only with kFlag)\n')]},
    'child': {'ogp-s1-child.c': [
        ('    if (access(OGP_S1_FLAG, F_OK) || !access(OGP_S1_OFF, F_OK)) return;\n',
         '    if (!access(OGP_S1_OFF, F_OK)) return;   /* ' + MARK + ': on unless the kill switch (was: only with OGP_S1_FLAG) */\n')]},
    'inc': {
        'ogp-s1b-async.inc': [
            ('        allowed = s1 && !access("/data/omni/gpu-pages-async.flag", F_OK) && access("/data/omni/gpu-pages-async-off.flag", F_OK);\n',
             '        allowed = s1 && access("/data/omni/gpu-pages-async-off.flag", F_OK) != 0;   // ' + MARK + ': on unless the off flag\n')],
        'ogp-s1-surface.inc': [
            ('    static const bool wanted = !access("/data/omni/gpu-pages-asyncread.flag", F_OK) && access("/data/omni/gpu-pages-asyncread-off.flag", F_OK);\n',
             '    static const bool wanted = access("/data/omni/gpu-pages-asyncread-off.flag", F_OK) != 0;   // ' + MARK + ': on unless the off flag\n')],
    },
}


def patch(p, edits, backup=True):
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    s = raw.replace('\r\n', '\n')
    if MARK in s:
        print('already', p.name)
        return
    for old, _ in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old.strip()[:90]))
    for old, new in edits:
        s = s.replace(old, new, 1)
    bak = p.with_name(p.name + '.before-layers-default-on')
    if backup and not bak.exists():   # never in the child modes: they patch COPIES, and a stray file trips the child recipe's changed-file gate
        shutil.copy2(p, bak)
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    print('applied', p.name)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in EDITS:
        sys.exit(__doc__)
    mode, path = sys.argv[1], Path(sys.argv[2])
    files = EDITS[mode]
    if mode == 'title':
        if path.name != 'OmniGpuPagesService.cpp':
            sys.exit('title mode wants the OmniGpuPagesService.cpp path')
        patch(path, files['OmniGpuPagesService.cpp'])
        return
    for name, edits in files.items():
        patch(path / name, edits, backup=False)


if __name__ == '__main__':
    main()
