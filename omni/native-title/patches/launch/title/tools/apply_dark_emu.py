#!/usr/bin/env python3
"""OMNI_DARK_APPEARANCE_EMU_V1 (s3.4d). Console finding on s3.4c: with youtube.com "always dark", the page's
matchMedia('(prefers-color-scheme: dark)') was FALSE although the shell calls WKPageSetUseDarkAppearanceForTesting:
the dark appearance does not reach the page in this engine (the place that would honour it is the child engine, which
stays unchanged). So the title emulates it for script, the documented fallback: a main-world document-start user script
answers matchMedia('(prefers-color-scheme: dark|light)') from <html data-omni-dark-want="1">, which the dark-page
script (isolated world) sets whenever Dark mode is wanted for the page; change listeners fire when it flips. Sites that
pick their theme in script (YouTube's "device theme") then go dark by themselves, the page measures dark and the
invert filter is not used. CSS @media (prefers-color-scheme) cannot be emulated by script; those sites still get the
filter (last resort). color-scheme on :root is NOT forced (it would repaint unstyled light pages and fool the measure).
usage: apply_dark_emu.py <tree root>   (after apply_dark_standard.py; idempotent)"""
import hashlib, sys
from pathlib import Path
STD_SHA = '852ec3a16171d9703ca1141ee8ad66879fea05c68c173eae38094cb2928dc5ee'
EMU = r'''
// OMNI_DARK_APPEARANCE_EMU_V1 (s3.4d): page world, document start, main frame. matchMedia for prefers-color-scheme
// follows <html data-omni-dark-want> (set by the dark-page script); other queries go to the real matchMedia.
static const char* const omniDkAppearanceEmu = R"JS((function(){
if(window.__omniDarkMQ)return;window.__omniDarkMQ=1;var real=window.matchMedia;if(typeof real!=='function')return;
var D=document,lists=[];
function want(){var e=D.documentElement;return !!e&&e.getAttribute('data-omni-dark-want')==='1';}
function mk(q,dark){var l={media:q,onchange:null,_h:[],_last:null};
Object.defineProperty(l,'matches',{get:function(){return dark?want():!want();}});
l.addListener=function(f){if(typeof f==='function')l._h.push(f);};l.removeListener=function(f){l._h=l._h.filter(function(x){return x!==f;});};
l.addEventListener=function(t,f){if(t==='change')l.addListener(f);};l.removeEventListener=function(t,f){if(t==='change')l.removeListener(f);};
l.dispatchEvent=function(){return true;};l._last=l.matches;lists.push(l);return l;}
window.matchMedia=function(q){var s=String(q).toLowerCase().replace(/\s+/g,'');
var m=/^\(prefers-color-scheme:(dark|light)\)$/.exec(s);if(m&&want())return mk(String(q),m[1]==='dark');return real.apply(window,arguments);};
function fire(){for(var i=0;i<lists.length;i++){var l=lists[i],now=l.matches;if(now===l._last)continue;l._last=now;var ev={matches:now,media:l.media,type:'change'};
try{if(typeof l.onchange==='function')l.onchange(ev);}catch(_){}for(var j=0;j<l._h.length;j++){try{l._h[j].call(l,ev);}catch(_){}}}}
try{new MutationObserver(fire).observe(D.documentElement,{attributes:true,attributeFilter:['data-omni-dark-want']});}catch(_){}
})();)JS";
static void omniDkAddMainScript(const char* source)
{
    auto text = adoptWK(WKStringCreateWithUTF8CString(source));
    auto script = adoptWK(WKUserScriptCreateWithSource(text.get(), kWKInjectAtDocumentStart, true));   // page world, main frame
    if (script) omniBlockerAddShellScript(script.get());
}
'''
EDITS = [
 ("function update(){try{var e=D.documentElement;if(!e)return;var on=want()&&",
  "function update(){try{var e=D.documentElement;if(!e)return;var w0=want();if(w0){if(e.getAttribute('data-omni-dark-want')!=='1')e.setAttribute('data-omni-dark-want','1');}else if(e.hasAttribute('data-omni-dark-want'))e.removeAttribute('data-omni-dark-want');var on=w0&&"),
 ("static std::string omniDkJsonList(int value)", EMU.lstrip('\n') + "static std::string omniDkJsonList(int value)"),
 ("if (!omniDkInstalled) { omniDkInstalled = true; omniDkAddScript(omniDkLogic); }",
  "if (!omniDkInstalled) { omniDkInstalled = true; omniDkAddMainScript(omniDkAppearanceEmu); omniDkAddScript(omniDkLogic); }   // OMNI_DARK_APPEARANCE_EMU_V1"),
]
def main():
    p = Path(sys.argv[1]) / 'engine/entry/OmniDarkPages.h'; raw = p.read_bytes()
    crlf = b'\r\n' in raw; text = raw.decode('utf-8').replace('\r\n', '\n')
    if 'OMNI_DARK_APPEARANCE_EMU_V1' in text: print('already OMNI_DARK_APPEARANCE_EMU_V1'); return 0
    if hashlib.sha256(raw).hexdigest() != STD_SHA: sys.exit('BLOCKED: OmniDarkPages.h is not the OMNI_DARK_STANDARD_V1 file %s' % STD_SHA[:12])
    for a, b in EDITS:
        if text.count(a) != 1: sys.exit('BLOCKED: anchor not found once: ' + a[:70])
        text = text.replace(a, b)
    out = (text.replace('\n', '\r\n') if crlf else text).encode('utf-8')
    p.write_bytes(out); print('patched OMNI_DARK_APPEARANCE_EMU_V1 (%d edits) sha %s' % (len(EDITS), hashlib.sha256(out).hexdigest()))
    return 0
sys.exit(main())
