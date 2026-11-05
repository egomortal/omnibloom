#!/usr/bin/env python3
"""s3.4: put Astra's canonical CLEAN4 integration (integration.diff, 25 files; the engine/entry + engine/media part here)
into the s3.4 overlay tree, AFTER the child link and after OMNI_POINTER_CROSS_V1. Each tree file must first equal the
integration's pinned baseline (line endings normalised), so nothing is overwritten that the integration did not start
from. OmniBrowser.cpp is the 3-way merge (git merge-file, no conflicts) of the integration and Astra's fps diagnostics
(OMNI_YTTL_BOUNDED_LONG_V1 / OMNI_YTTL_FULLSCREEN_V1 / playback probe) over the same 594f4f85 baseline.
usage: apply_s34_entry.py <tree root>"""
import hashlib, json, sys
from pathlib import Path
N = Path(__file__).resolve().parent.parent; T = Path(sys.argv[1])
base = json.loads((N / 's34-entry-baseline.json').read_text())
lf = lambda b: hashlib.sha256(b.replace(b'\r\n', b'\n')).hexdigest()
src = {'engine/entry': N / 's34-entry', 'engine/media': N / 's34-media'}
done = []
for rel, v in sorted(base.items()):
    if rel == 'engine/media/OmniHwService.cpp': continue   # the title's copy is compiled by prep_s34.py from omni-native-s3.4/engine/media (as s3.3); the tree keeps s3's
    d, name = rel.rsplit('/', 1); new = (src[d] / name).read_bytes(); dst = T / rel
    if dst.exists():
        have = lf(dst.read_bytes())
        if have == lf(new): done.append('already ' + rel); continue
        if have != v['before_lf']: sys.exit('BLOCKED: %s is %s, not the integration baseline %s' % (rel, have[:12], (v['before_lf'] or 'absent')[:12]))
    elif v['before_lf'] is not None: sys.exit('BLOCKED: %s missing in the tree' % rel)
    if rel != 'engine/entry/OmniBrowser.cpp' and lf(new) != lf((N.parent / 'codex-ui/20261104-suite-clean4-integration/proposed' / rel).read_bytes()): sys.exit('BLOCKED: %s is not the integration proposal' % rel)
    dst.write_bytes(new); done.append('patched %s %s' % (rel, hashlib.sha256(new).hexdigest()[:12]))
for x in done: print(x)
print('s34 entry: %d files (%d patched)' % (len(done), sum(x.startswith('patched') for x in done)))
