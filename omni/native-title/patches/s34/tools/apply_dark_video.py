#!/usr/bin/env python3
"""OMNI_DARK_VIDEO_PLANE_V1 (s3.4): the dark-page filter steps aside while a large video plays.
Cause of the YouTube stall at currentTime 0.0145 s: with Dark pages on for a light site (site-dark.txt has
youtube.com 1), the user script puts filter:invert() on <html>. The child's hole-punch geometry check
(OmniMSEPlayer::holeGeometry: "opacity, filter, mask, clip-path, blend or reflection on the way up") then refuses
the video plane, and the frozen child's startup gate ("no timeout may silently bypass the startup gate") waits for a
plane that is never claimed, so the clock never leaves the start. Fullscreen already turned the filter off for this
reason; this extends the same rule to a playing video that covers >= 20% of the viewport. Title-only: the script is
registered by the shell (UI process); the child is linked before this patch and stays byte-identical.
usage: apply_dark_video.py <tree root>   (edits <root>/engine/entry/OmniDarkPages.h in place; idempotent)"""
import hashlib, sys
from pathlib import Path
BASE_SHA = '22663be5cbdef4f2a7f0459e5d982433e0db1029ef903026cc321e8773a539c9'
EDITS = [
 ("var D=document,fs=false,timer=0;", "var D=document,fs=false,vp=false,timer=0,mt=0;"),
 ("var on=want()&&!fs;", "var on=want()&&!fs&&!vp;"),
 ("D.addEventListener('webkitfullscreenchange',full);D.addEventListener('fullscreenchange',full);",
  "D.addEventListener('webkitfullscreenchange',full);D.addEventListener('fullscreenchange',full);\n"
  "function plane(){try{var vs=D.getElementsByTagName('video'),W=innerWidth||0,H=innerHeight||0,A=W*H;if(!(A>0))return false;\n"
  "for(var i=0;i<vs.length;i++){var v=vs[i];if(v.paused||v.ended)continue;var b=v.getBoundingClientRect();\n"
  "var w=Math.min(b.right,W)-Math.max(b.left,0),h=Math.min(b.bottom,H)-Math.max(b.top,0);if(w>0&&h>0&&w*h>=0.2*A)return true;}}catch(_){}return false;}\n"
  "function media(){mt=0;var n=plane();if(n!==vp){vp=n;update();}}\n"
  "function mediaSoon(){if(!mt)mt=setTimeout(media,0);}\n"
  "['play','playing','pause','ended','emptied','loadeddata','resize'].forEach(function(t){D.addEventListener(t,mediaSoon,true);});\n"
  "addEventListener('resize',mediaSoon);"),
 ("//     filter again, so they keep their real colours. Fullscreen turns the filter off.",
  "//     filter again, so they keep their real colours. Fullscreen turns the filter off, and so does a playing\n"
  "//     video covering >= 20% of the viewport (OMNI_DARK_VIDEO_PLANE_V1, s3.4): a filtered ancestor keeps the video\n"
  "//     off the hole-punch plane, and the child's startup gate then never starts the clock (YouTube stuck at 0.0145 s)."),
]
def main():
    p = Path(sys.argv[1]) / 'engine/entry/OmniDarkPages.h'; raw = p.read_bytes()
    crlf = b'\r\n' in raw; text = raw.decode('utf-8').replace('\r\n', '\n')
    if 'OMNI_DARK_VIDEO_PLANE_V1' in text: print('already OMNI_DARK_VIDEO_PLANE_V1'); return 0
    if hashlib.sha256(raw).hexdigest() != BASE_SHA: sys.exit('BLOCKED: OmniDarkPages.h is not the s3 file %s' % BASE_SHA[:12])
    for a, b in EDITS:
        if text.count(a) != 1: sys.exit('BLOCKED: anchor not found once: ' + a[:60])
        text = text.replace(a, b)
    out = text.replace('\n', '\r\n') if crlf else text
    p.write_bytes(out.encode('utf-8')); print('patched OMNI_DARK_VIDEO_PLANE_V1 (%d edits) sha %s' % (len(EDITS), hashlib.sha256(out.encode()).hexdigest()))
    return 0
sys.exit(main())
