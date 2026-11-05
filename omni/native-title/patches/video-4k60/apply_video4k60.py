#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""omni-video-4k60 patch set: apply (or check) the title-only marker patches.

  python3 apply_video4k60.py --folder <dir> --tree <dir> [--check] [--only 01,02,...]

--folder: a build folder laid out like omni-native-s3.3/ (engine/media/*.cpp|h, src-title/*.cpp|h): patches 00-03.
--tree:   the engine tree (e.g. /home/builder/s1 inside the build's private overlay) AFTER s3.1c's pointer-cross patch:
          patches 04-05 (engine/entry/OmniDarkPages.h, engine/entry/OmniBrowser.cpp). Both are title-only: compile them
          for the title link and never relink the child from that tree (the child stays 7b810ea5...).
A patch whose marker is already in every target file is skipped ("already"), so the set stacks on s3.1c (00 needed),
s3.3 (00 already there) or a later line that carries some of them. Each patch is applied with GNU patch --forward;
afterwards every marker must be present, else the run stops (exit 1). --check only reports.
"""
import argparse, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
PATCHES = [  # (id, file, root, {target: marker})
    ('00', '00-gpu-v2-base-s3.2.diff', 'folder', {'engine/media/OmniGpuVideo.cpp': 'OMNI_GPU_VIDEO_V2', 'engine/media/OmniHwService.cpp': 'omni_hw_video_counters',
                                                  'src-title/OmniGpuPresent.cpp': 'OMNI_GPU_PRESENT_V2', 'src-title/OmniPqOutShader.h': 'kOmniPqOutSpv'}),
    ('01', '01-gpu-video-v3.diff', 'folder', {'engine/media/OmniGpuVideo.cpp': 'OMNI_GPU_VIDEO_V3', 'engine/media/OmniGpuVideo.h': 'OMNI_GPU_VIDEO_V3'}),
    ('02', '02-hwservice-in-place.diff', 'folder', {'engine/media/OmniHwService.cpp': 'paceIsDirect'}),
    ('03', '03-gpu-present-v3.diff', 'folder', {'src-title/OmniGpuPresent.cpp': 'OMNI_GPU_PRESENT_V3'}),
    ('04', '04-dark-video.diff', 'tree', {'engine/entry/OmniDarkPages.h': 'OMNI_DARK_VIDEO_V1'}),
    ('05', '05-yt-probes.diff', 'tree', {'engine/entry/OmniBrowser.cpp': 'OMNI_HOLE_ELIGIBILITY_PROBE_V1'}),
]
def has(root, rel, marker):
    p = root / rel
    return p.exists() and marker.encode() in p.read_bytes()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder'); ap.add_argument('--tree'); ap.add_argument('--check', action='store_true'); ap.add_argument('--only')
    a = ap.parse_args()
    only = set(a.only.split(',')) if a.only else None
    roots = {'folder': Path(a.folder) if a.folder else None, 'tree': Path(a.tree) if a.tree else None}
    bad = 0
    for pid, fname, rootName, targets in PATCHES:
        if only and pid not in only: continue
        root = roots[rootName]
        if root is None: print(f'{pid} skipped: no --{rootName} given'); continue
        state = [has(root, t, m) for t, m in targets.items()]
        if all(state): print(f'{pid} already {fname}'); continue
        if any(state): print(f'{pid} PARTIAL {fname}: some targets carry the marker, some do not ({dict(zip(targets, state))})'); bad += 1; continue
        if a.check: print(f'{pid} would apply {fname}'); continue
        r = subprocess.run(['patch', '-p1', '--forward', '--batch', '--no-backup-if-mismatch', '-d', str(root), '-i', str(HERE / 'patches' / fname)], capture_output=True, text=True)
        ok = r.returncode == 0 and all(has(root, t, m) for t, m in targets.items())
        print(f'{pid} {"patched" if ok else "FAILED"} {fname}' + ('' if ok else ': ' + (r.stdout + r.stderr).strip().replace('\n', ' | ')[:600]))
        bad += not ok
    print('RESULT', 'FAIL' if bad else 'OK')
    return 1 if bad else 0
if __name__ == '__main__':
    sys.exit(main())
