#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lay out this folder's sources the way recipe/replay.py reads them (stage sources under packages/<stage>/source/).

    python3 recipe/make_layout.py <jdownloader folder> <new layout folder> <folder with the 5 pinned downloads>
"""
import shutil, sys
from pathlib import Path

SRC, OUT, DL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
if OUT.exists():
    sys.exit('%s exists; pick a new folder' % OUT)
scripts = SRC / 'recipe' / 'scripts'
eng = SRC / 'engine'
OUT.mkdir(parents=True)
for p in scripts.iterdir():                      # every build script at the top, like the original workspace
    if p.is_file():
        shutil.copyfile(p, OUT / p.name)
for p in eng.iterdir():
    if p.is_file():
        shutil.copyfile(p, OUT / p.name)
STAGES = {
    'jd-002': {'java_worker.cpp': eng / 'stages/java_worker.jd-002.cpp', 'package_payload.py': scripts / 'package_payload.py',
               'build_step.py': scripts / 'build_step.py', 'resident_spec.py': scripts / 'resident_spec.py',
               'NativeProviderProbe.java': SRC / 'java/NativeProviderProbe.java'},
    'jd-003': {'java_worker.cpp': eng / 'stages/java_worker.jd-003.cpp', 'relink_telemetry.py': scripts / 'relink_telemetry.py'},
    'jd-004': {'java_worker.cpp': eng / 'stages/java_worker.jd-004.cpp', 'relink_deadlines.py': scripts / 'relink_deadlines.py'},
    'jd-005': {n: (scripts if n.endswith('.py') else eng) / n for n in ('relink_filesystem.py', 'filesystem_compat.cpp', 'test_filesystem_compat.cpp')},
    'jd-006': {'java_worker.cpp': eng / 'stages/java_worker.jd-006.cpp', 'relink_sampling.py': scripts / 'relink_sampling.py',
               'test_metadata_sampler.cpp': eng / 'test_metadata_sampler.cpp'},
    'jd-007': {'java_worker.cpp': eng / 'stages/java_worker.jd-007.cpp', 'relink_own_uid.py': scripts / 'relink_own_uid.py',
               'own_uid.hpp': eng / 'own_uid.hpp', 'test_own_uid.cpp': eng / 'test_own_uid.cpp'},
    'jd-008': {n: (scripts if n.endswith('.py') else eng) / n for n in ('build_space_runtime.py', 'space_compat.cpp', 'test_space_compat.cpp',
                                                                       'ps5MountSnapshot.h', 'test_mount_snapshot.cpp')},
}
for stage, files in STAGES.items():
    d = OUT / 'packages' / stage / 'source'
    d.mkdir(parents=True)
    for name, src in files.items():
        shutil.copyfile(src, d / name)
(OUT / 'downloads').symlink_to(DL.resolve(), target_is_directory=True)
print('layout ready:', OUT)
