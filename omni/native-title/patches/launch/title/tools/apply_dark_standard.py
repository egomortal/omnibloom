#!/usr/bin/env python3
"""OMNI_DARK_STANDARD_V1 (s3.4b, user-approved): Dark mode the standard way, title only.
(1) is already Omni's: while Dark mode is on for a page, the shell sets the page's real dark appearance
    (WKPageSetUseDarkAppearanceForTesting in omniDkTick), so CSS prefers-color-scheme and matchMedia report dark.
(2) The invert filter becomes the last resort. The page keeps its own dark theme when, measured again whenever it can
    change (html/body theme attributes, a prefers-color-scheme change, DOMContentLoaded, load +1.5/4/8 s): its own
    background is dark (as before), or its background is unset and it declares dark support (computed color-scheme
    with dark, <meta name=color-scheme> with dark, or @media (prefers-color-scheme: dark) rules in its readable style
    sheets) while the dark appearance is on.
(3) Hook for the Dark Reader add-on: <html data-omni-dark-addon="on"> (set by the add-on in the page) turns the filter
    off at once; removing it brings the filter rule back.
OMNI_DARK_VIDEO_PLANE_V1's rule (a playing video >= 20% of the viewport turns the filter off) is kept.
usage: apply_dark_standard.py <tree root>  (after apply_dark_video.py; idempotent)"""
import hashlib, sys
from pathlib import Path
V1_SHA = '545a253979e38e154cf1cf860a795b5aa39a66f9b76a581291c0b0bab56115ba'
EDITS = [
 ("var on=want()&&!fs&&!vp;", "var on=want()&&!fs&&!vp&&e.getAttribute('data-omni-dark-addon')!=='on';watchBody();"),
 ("else if(l<0&&/dark/.test(getComputedStyle(e).colorScheme||'')&&matchMedia('(prefers-color-scheme: dark)').matches)on=false;",
  "else if(l<0&&ownDark(e))on=false;"),
 ("function soon(){clearTimeout(timer);timer=setTimeout(update,30);}",
  "function soon(){clearTimeout(timer);timer=setTimeout(update,30);}\n"
  "function prefersDark(){try{return matchMedia('(prefers-color-scheme: dark)').matches;}catch(_){return false;}}\n"
  "var rulesN=-1,rulesHit=false;\n"
  "function darkRules(){var ss=D.styleSheets;if(!ss)return false;if(ss.length===rulesN)return rulesHit;rulesN=ss.length;rulesHit=false;var seen=0;\n"
  "for(var i=0;i<ss.length&&!rulesHit&&seen<4000;i++){var r=null;try{r=ss[i].cssRules;}catch(_){}if(!r)continue;\n"
  "for(var j=0;j<r.length&&seen<4000;j++,seen++){var m=r[j].media;if(m&&/prefers-color-scheme\\s*:\\s*dark/.test(m.mediaText||'')){rulesHit=true;break;}}}\n"
  "if(!rulesHit){var mt=D.querySelector&&D.querySelector('meta[name=\"color-scheme\"]');if(mt&&/dark/.test(mt.getAttribute('content')||''))rulesHit=true;}return rulesHit;}\n"
  "function ownDark(e){return prefersDark()&&(/dark/.test(getComputedStyle(e).colorScheme||'')||darkRules());}\n"
  "var bo=null;function watchBody(){if(bo||!D.body)return;bo=new MutationObserver(soon);bo.observe(D.body,{attributes:true,attributeFilter:['class','style','dark','theme','data-theme']});}"),
 ("new MutationObserver(soon).observe(e,{attributes:true,attributeFilter:['data-omni-dark']});}",
  "new MutationObserver(soon).observe(e,{attributes:true,attributeFilter:['data-omni-dark','data-omni-dark-addon','class','dark','theme','data-theme','data-color-mode']});}\n"
  "try{var mq=matchMedia('(prefers-color-scheme: dark)');if(mq.addEventListener)mq.addEventListener('change',soon);else if(mq.addListener)mq.addListener(soon);}catch(_){}"),
 ("addEventListener('load',function(){update();setTimeout(update,1500);});",
  "addEventListener('load',function(){update();setTimeout(update,1500);setTimeout(update,4000);setTimeout(update,8000);});"),
 ("//  2. A user script (document start, main frame, isolated world \"omni-dark\") that, once <body>",
  "//  OMNI_DARK_STANDARD_V1 (s3.4b): the filter is the last resort. A page that is dark by itself, or has no background\n"
  "//     of its own and declares dark support (color-scheme, <meta name=color-scheme>, prefers-color-scheme rules) while\n"
  "//     the dark appearance is on, keeps its own theme; it is measured again when its theme attributes or the\n"
  "//     appearance change. <html data-omni-dark-addon=\"on\"> (the Dark Reader add-on's hook) turns the filter off.\n"
  "//  2. A user script (document start, main frame, isolated world \"omni-dark\") that, once <body>"),
]
def main():
    p = Path(sys.argv[1]) / 'engine/entry/OmniDarkPages.h'; raw = p.read_bytes()
    crlf = b'\r\n' in raw; text = raw.decode('utf-8').replace('\r\n', '\n')
    if 'OMNI_DARK_STANDARD_V1' in text: print('already OMNI_DARK_STANDARD_V1'); return 0
    if hashlib.sha256(raw).hexdigest() != V1_SHA: sys.exit('BLOCKED: OmniDarkPages.h is not the OMNI_DARK_VIDEO_PLANE_V1 file %s' % V1_SHA[:12])
    for a, b in EDITS:
        if text.count(a) != 1: sys.exit('BLOCKED: anchor not found once: ' + a[:70])
        text = text.replace(a, b)
    out = (text.replace('\n', '\r\n') if crlf else text).encode('utf-8')
    p.write_bytes(out); print('patched OMNI_DARK_STANDARD_V1 (%d edits) sha %s' % (len(EDITS), hashlib.sha256(out).hexdigest()))
    return 0
sys.exit(main())
