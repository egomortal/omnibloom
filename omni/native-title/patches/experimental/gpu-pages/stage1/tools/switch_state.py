#!/usr/bin/env python3
"""Switch build tree A to the sources of a source-only overlay S (as build-omni-gpupages-launch-s1b-rc4.sh does).
Usage: switch_state.py UPPER_A UPPER_S MERGED_A MERGED_S LABEL. Every path changed in either upper (build/ excluded)
ends up byte-identical in A to S's merged view, or removed from A if S has no such file. Exit 1 if any differs."""
import os, shutil, sys
upa, ups, ta, ts, label = sys.argv[1:6]
def changed(up):
    s = set()
    for root, dirs, files in os.walk(up):
        rel = os.path.relpath(root, up)
        if rel == 'build' or rel.startswith('build/'): dirs[:] = []; continue
        for f in files:
            p = os.path.normpath(os.path.join(rel, f))
            if os.path.basename(p).startswith('.') or p.endswith('link-command.json'): continue
            s.add(p)
    return s
def same(a, b): return open(a, 'rb').read() == open(b, 'rb').read()
paths = sorted(changed(upa) | changed(ups)); n = {'copied': 0, 'removed': 0, 'same': 0}
for p in paths:
    a, b = os.path.join(ta, p), os.path.join(ts, p)
    if os.path.exists(b):
        if os.path.exists(a) and same(a, b): n['same'] += 1; continue
        os.makedirs(os.path.dirname(a), exist_ok=True); shutil.copyfile(b, a); n['copied'] += 1; print('copied', p)
    elif os.path.exists(a): os.remove(a); n['removed'] += 1; print('removed', p)
bad = [p for p in paths if os.path.exists(os.path.join(ts, p)) != os.path.exists(os.path.join(ta, p))
       or (os.path.exists(os.path.join(ts, p)) and not same(os.path.join(ta, p), os.path.join(ts, p)))]
print(f"RESULT {n['copied']} copied, {n['removed']} removed, {n['same']} already equal; after the switch "
      f"{len(paths) - len(bad)}/{len(paths)} changed paths equal {label}, {len(bad)} differ")
sys.exit(1 if bad else 0)
