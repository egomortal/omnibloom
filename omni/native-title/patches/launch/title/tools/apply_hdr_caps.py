#!/usr/bin/env python3
"""OMNI_HDR_CAPS_V1 (s3.5-hdr), title only (the shell): tell sites the truth about HDR. A page script (document start,
all frames) answers matchMedia (dynamic-range / video-dynamic-range / color-gamut), screen.colorDepth / pixelDepth,
MediaSource.isTypeSupported, addSourceBuffer, SourceBuffer.changeType, canPlayType and mediaCapabilities.decodingInfo:
HDR (VP9.2 / AV1 with PQ or HLG transfer, eotf=, HDR fields) is reported only when the GPU present can show HDR10
(omni_gpu_present_hdr_state() >= 1: On with HDR10 output, or Auto on an HDR10 display), and then the engine (the frozen
child, which refuses transfer 16/18 because it had no HDR output path) is asked about the same stream with transfer 01.
YouTube's check (Mozilla bug 1751087): matchMedia('(dynamic-range: high)') || (screen.pixelDepth > 24 && color-gamut p3),
then isTypeSupported('video/webm; codecs="vp09.02.51.10.01.09.16.09.00"').
usage: apply_hdr_caps.py <tree root>  (after apply_s34_entry.py; idempotent)"""
import hashlib, sys
from pathlib import Path
JS = r"""(function(){if(window.__omniHdrCapsV1)return;window.__omniHdrCapsV1=1;var CAP=__CAP__;
var VP=/vp09\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)/gi,AV=/av01\.\d\.\d\d[MH]\.(10|12)\.\d\.\d{3}\.\d\d\.(16|18)\b/i;
function hdrType(t){t=String(t==null?'':t);if(/eotf\s*=\s*"?(smpte2084|arib-std-b67)/i.test(t)||AV.test(t))return true;var m,re=new RegExp(VP.source,'gi');while((m=re.exec(t)))if(m[6]==='16'||m[6]==='18')return true;return false;}
function sdrForm(t){return String(t).replace(new RegExp(VP.source,'gi'),function(s,p,l,d,c,cp,tc){return (tc==='16'||tc==='18')?'vp09.'+p+'.'+l+'.'+d+'.'+c+'.'+cp+'.01':s;}).replace(/;\s*eotf\s*=\s*"?[^;"]*"?/i,'');}
function wrap(o,k,f){try{var g=o&&o[k];if(typeof g==='function')o[k]=f(g);}catch(e){}}
try{if(window.MediaSource){wrap(MediaSource,'isTypeSupported',function(g){return function(t){if(hdrType(t))return CAP?g.call(this,sdrForm(t)):false;return g.call(this,t);};});
wrap(MediaSource.prototype,'addSourceBuffer',function(g){return function(t){return g.call(this,CAP&&hdrType(t)?sdrForm(t):t);};});}
if(window.SourceBuffer)wrap(SourceBuffer.prototype,'changeType',function(g){return function(t){return g.call(this,CAP&&hdrType(t)?sdrForm(t):t);};});
if(window.HTMLMediaElement)wrap(HTMLMediaElement.prototype,'canPlayType',function(g){return function(t){if(hdrType(t))return CAP?g.call(this,sdrForm(t)):'';return g.call(this,t);};});}catch(e){}
try{var mc=navigator.mediaCapabilities;if(mc&&mc.decodingInfo){var di=mc.decodingInfo;mc.decodingInfo=function(cfg){var v=cfg&&cfg.video;
if(v&&(v.hdrMetadataType||(v.colorGamut&&v.colorGamut!=='srgb')||(v.transferFunction&&v.transferFunction!=='srgb')||hdrType(v.contentType))){
if(!CAP)return Promise.resolve({supported:false,smooth:false,powerEfficient:false,configuration:cfg});
var c={};for(var k in cfg)c[k]=cfg[k];var w={};for(var j in v)if(j!=='hdrMetadataType'&&j!=='colorGamut'&&j!=='transferFunction')w[j]=v[j];w.contentType=sdrForm(v.contentType);c.video=w;
return di.call(mc,c).then(function(r){var o={supported:r.supported,smooth:r.smooth,powerEfficient:r.powerEfficient,configuration:cfg};return o;});}
return di.call(mc,cfg);};}}catch(e){}
try{var mm=window.matchMedia;if(mm){var T='(min-width:0px)',F='(max-width:0px) and (min-width:1px)';
window.matchMedia=function(q){var s=String(q).replace(/\(\s*(video-)?dynamic-range\s*:\s*(high|standard)\s*\)/gi,function(x,v,r){return r.toLowerCase()==='standard'||CAP?T:F;})
.replace(/\(\s*color-gamut\s*:\s*(srgb|p3|rec2020)\s*\)/gi,function(x,r){return r.toLowerCase()==='srgb'||CAP?T:F;});
var r=mm.call(window,s);if(s!==String(q)){try{Object.defineProperty(r,'media',{value:String(q)});}catch(e){}}return r;};}}catch(e){}
if(CAP)try{['colorDepth','pixelDepth'].forEach(function(k){Object.defineProperty(Screen.prototype,k,{configurable:true,get:function(){return 30;}});});}catch(e){}
})();"""
FUNC = ("// OMNI_HDR_CAPS_V1 (s3.5-hdr): what pages are told about HDR follows the GPU present's real output (see\n"
 "// tools/apply_hdr_caps.py). Decided once at start (the HDR setting applies at the next start).\n"
 "extern \"C\" int omni_gpu_present_hdr_state() __attribute__((weak));\n"
 "static void omniHdrCapsInstall()\n{\n"
 "    const int state = omni_gpu_present_hdr_state ? omni_gpu_present_hdr_state() : 0;\n"
 "    std::string js = R\"OMNIHDRJS(" + JS + ")OMNIHDRJS\";\n"
 "    const size_t at = js.find(\"__CAP__\"); if (at != std::string::npos) js.replace(at, 7, state >= 1 ? \"1\" : \"0\");\n"
 "    fprintf(stderr, \"OMNI_HDR_CAPS_V1: pages are told HDR %s (GPU present HDR state %d)\\n\", state >= 1 ? \"capable\" : \"not capable\", state); fflush(stderr);\n"
 "    auto text = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));\n"
 "    auto script = adoptWK(WKUserScriptCreateWithSource(text.get(), kWKInjectAtDocumentStart, false));   // all frames\n"
 "    omniBlockerAddShellScript(script.get());\n}\n\n")
ANCHOR_DEF = "// --- layout and drawing ---"
ANCHOR_CALL = "        omniSelectInstall(); // OMNI_DIALOGS_V1: <select> menus (not in self-test modes)\n"
def main():
    p = Path(sys.argv[1]) / 'engine/entry/OmniBrowser.cpp'; raw = p.read_bytes()
    crlf = b'\r\n' in raw; text = raw.decode('utf-8').replace('\r\n', '\n')
    if 'OMNI_HDR_CAPS_V1' in text: print('already OMNI_HDR_CAPS_V1'); return 0
    if text.count(ANCHOR_DEF) != 1 or text.count(ANCHOR_CALL) != 1: sys.exit('BLOCKED: anchors not found once in OmniBrowser.cpp')
    text = text.replace(ANCHOR_DEF, FUNC + ANCHOR_DEF)
    text = text.replace(ANCHOR_CALL, ANCHOR_CALL + "        omniHdrCapsInstall(); // OMNI_HDR_CAPS_V1: what pages are told about HDR (test modes too: the fps runs measure real pages)\n")
    out = (text.replace('\n', '\r\n') if crlf else text).encode('utf-8')
    p.write_bytes(out); print('patched OMNI_HDR_CAPS_V1 sha %s' % hashlib.sha256(out).hexdigest())
    return 0
sys.exit(main())
