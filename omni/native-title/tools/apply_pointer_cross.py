#!/usr/bin/env python3
"""OMNI_POINTER_CROSS_V1: applies patches/pointer-cross.diff (OmniBrowser.cpp, OmniFeaturesPanel.h, new OmniPointerCross.h)
to <tree>/engine/entry with GNU patch. Run after the s3.1b engine changes (apply_yt.py / apply_soak_read.py also edit
OmniBrowser.cpp; the diff's context is the file after them). Idempotent: a tree that already has the marker in all three
files is left alone; anything else must apply cleanly (dry run first) or nothing is written."""
import subprocess, sys
from pathlib import Path
tree = Path(sys.argv[1]); diff = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / 'patches/pointer-cross.diff'
E = tree / 'engine/entry'; M = 'OMNI_POINTER_CROSS_V1'
files = [E / 'OmniBrowser.cpp', E / 'OmniFeaturesPanel.h', E / 'OmniPointerCross.h']
def marked(): return [f.exists() and M in f.read_text(errors='replace') for f in files]
m = marked()
if all(m): print('already', ' '.join(f.name for f in files)); sys.exit(0)
if any(m): sys.exit(f'BLOCKED: {M} only partly present: {dict(zip([f.name for f in files], m))}')
base = ['patch', '-p1', '--forward', '--batch', '-d', str(tree), '-i', str(diff)]
r = subprocess.run(base + ['--dry-run'], capture_output=True, text=True)
if r.returncode: sys.exit('BLOCKED: dry run failed:\n' + r.stdout + r.stderr)
r = subprocess.run(base + ['--no-backup-if-mismatch'], capture_output=True, text=True)
print(r.stdout.strip())
if r.returncode or not all(marked()): sys.exit('FAILED: patch did not apply: ' + r.stderr)
counts = {f.name: f.read_text(errors='replace').count(M) for f in files}
print('patched', M, counts)
