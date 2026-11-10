#!/usr/bin/env python3
"""omni-jit2 OMNI_SOAK_READ_V1: the staged-media self-test read the page's results 30 s after the staged start
(55 s with long-media-selftest) EVEN WITH the endurance flags, so every "20-minute" soak ended after ~40-56 s with
empty results and the shell shut down. With media-endurance-selftest the read now waits for the soak: 1230 s with
media-thirty-minute-selftest (the 20-minute yt-soak page), 630 s without. The overall timeouts (1890 s / 650 s) are
unchanged and still above these. Idempotent; the anchor must match exactly once."""
import sys
from pathlib import Path
p = Path(sys.argv[1]) / 'engine/entry/OmniBrowser.cpp'
s = p.read_text()
if 'OMNI_SOAK_READ_V1' in s: print('already applied'); sys.exit(0)
old = '> (stagedMediaTest ? (longMediaTest ? (pipelineTraceTest ? 2000u : 55000u) : 30000u) : 12000u)'
new = '> (stagedMediaTest ? (mediaEnduranceTest ? (mediaThirtyMinuteTest ? 1230000u : 630000u) : longMediaTest ? (pipelineTraceTest ? 2000u : 55000u) : 30000u) : 12000u) /* OMNI_SOAK_READ_V1 */'
n = s.count(old)
if n != 1: sys.exit(f'anchor matched {n} times')
p.write_text(s.replace(old, new)); print('patched', p)
