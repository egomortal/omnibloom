#!/usr/bin/env python3
"""Generate B-frame video in a caller-owned temporary directory, retain AAC fixture."""
from pathlib import Path
import shutil
import subprocess
import sys
here = Path(__file__).resolve().parent
out = Path(sys.argv[1])
out.mkdir()
for path in (here / 'generated').glob('*-1*'):
    if path.suffix in ('.mp4', '.m4s'):
        shutil.copyfile(path, out / path.name)
subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
    'testsrc2=size=320x180:rate=30', '-t', '4', '-an', '-c:v', 'libx264',
    '-profile:v', 'main', '-bf', '2', '-g', '30', '-keyint_min', '30',
    '-sc_threshold', '0', '-pix_fmt', 'yuv420p', '-f', 'dash', '-seg_duration', '1',
    '-init_seg_name', 'init-$RepresentationID$.mp4',
    '-media_seg_name', 'segment-$RepresentationID$-$Number%05d$.m4s',
    str(out / 'stream.mpd')], check=True, timeout=60)
