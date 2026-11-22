#!/usr/bin/env python3
"""OMNI_YT_POTOKEN_V1 (2026-11-21): long-term PO-token handling for the YouTube guard (design:
outputs/omni-ytattest/POTOKEN-DESIGN.md).

Why
  YouTube's web player mints a PO token from a BotGuard run. On Omni about 1 run in 2 to 1 in 3 is "not attested"
  (SABR stream protection status 2 -> 3, media stops at ~60 s). OMNI_YT_ATTEST_GUARD_V1 then reloads the page (a new
  BotGuard run), up to 5 times per video. Nothing remembered anything between launches, so every launch started blind,
  and nobody could say how often it happens per day.

What this adds (title side, all inside OmniYtGuard.h; needs the v3 guard + OMNI_YT_GUARD_RECOVER_V1 already applied)
  1. Outcome log in /data/omni/yt-attest-days.log ("<unix time> <event>", only [A-Za-z0-9=._ -], max 160 chars a line,
     max 40 lines a page, file rotated to .old at 32 KB). Events: att len=N how=first|rescue, rej len=N, early len=N,
     early-skip len=N, rescue r=ok|fail|skipped, reload why=rejected|status3|pending40s|stuck|cut try=N,
     id h=<FNV-1a hash of VISITOR_DATA, never the value> li=0|1 (signed in). The shell writes it ("potlog " prompt verb).
  2. The shell reads the last 16 KB of that log at start and hands it to the page (window.__omniPotCfg, youtube.com
     only). The guard then knows, per token length, how often YouTube accepted it in the last 14 days, and how the
     in-page re-mint (ytguard-extra.js rescue) did in the last 7.
  3. Token length sniff: the token the player puts in its SABR requests (VideoPlaybackAbrRequest f19 -> f2) is measured
     (length only, never stored) for requests sent after GenerateIT. Lengths are logged with the verdict.
  4. Early verdict ("pre-mint check"): a token whose length class was rejected >= 90% over >= 6 server verdicts in 14 days
     is treated as not attested at once (before YouTube's own status 2), so the re-mint / reload starts ~1-4 s earlier,
     before the video has visibly started. 1 in 4 such tokens are let through anyway ("early-skip") so the table keeps
     getting real verdicts; early verdicts are never counted as rejections. Off: /data/omni/yt-potoken-early-off.flag.
  5. Re-mint policy: the rescue (window.__omniYtRescue from /data/omni/ytguard-extra.js) gets max 3 runs
     (window.__omniYtRescueMax=3, read by extra v5) and the page's own Create request (window.__omniPotCreate, so v5
     can mirror the player's request key). If the rescue failed >= 6 times with 0 successes in 7 days it is skipped
     (straight to the reload, saving ~10-45 s) except for 1 video in 5, which still probes.
     /data/omni/yt-potoken-rescue.txt = on | off | auto (default auto).
  6. Daily summary: on each /watch page the guard logs "potoken today: att=.. rej=.. early=.. reloads=.. rescue=../..
     ids=.. signed-in=.." from the same log (history = earlier launches only; this launch's events count from the next start) (tally offline: outputs/omni-ytattest/potoken_tally.py).
  Master off switch: /data/omni/yt-potoken-off.flag (read at shell start): no log, no early verdict, no rescue policy;
  the guard behaves exactly as before.

Build safety: the C++ uses only names OmniYtGuard.h already uses (access, fopen, fread, fputs, fclose, rename, time,
fprintf, std::string, std::to_string, adoptWK, WKStringCreateWithUTF8CString, WKUserScriptCreateWithSource,
kWKInjectAtDocumentStart, omniBlockerAddShellScript): no new imports.

Usage
  apply_yt_potoken.py <title tree>             edits <tree>/engine/entry/OmniYtGuard.h (idempotent)
  apply_yt_potoken.py --dry-run <tree|header>  applies to a temp copy, checks it (anchors, raw-string delimiter, node
                                              --check of the page script when node exists), prints a summary; the
                                              original is never written
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MARK = 'OMNI_YT_POTOKEN_V1'

POT_JS = r"""// OMNI_YT_POTOKEN_V1 (2026-11-21; outputs/omni-ytattest/POTOKEN-DESIGN.md): remember PO-token outcomes across launches
// (/data/omni/yt-attest-days.log via the shell), judge a new token by its length class, decide whether the in-page
// re-mint is worth trying, and log a daily summary. window.__omniPotCfg comes from the shell (off: yt-potoken-off.flag).
var POT=window.__omniPotCfg||{},potN=0,potNow=Math.floor(Date.now()/1000),potLen={},potRes={ok:0,fail:0},potDay={},potIdSaid=false,potSumSaid=false;
function potLog(ev){if(POT.off||potN>=40)return;potN++;try{P.call(window,'\u0001OMNI_YTGUARD_V1','potlog '+String(ev).replace(/[^A-Za-z0-9=._ -]/g,'').slice(0,160));}catch(e){}}
(function(){if(POT.off)return;var L=String(POT.log||'').split('\n'),today=Math.floor(potNow/86400),ids={};
 for(var i=0;i<L.length;i++){var w=L[i].split(' '),t=+w[0];if(!t||potNow-t>14*86400||t>potNow+86400)continue;var kv={};
  for(var j=2;j<w.length;j++){var q=w[j].indexOf('=');if(q>0)kv[w[j].slice(0,q)]=w[j].slice(q+1);}
  if((w[1]==='att'||w[1]==='rej')&&kv.len){var o=potLen[kv.len]||(potLen[kv.len]={ok:0,rej:0});if(w[1]==='att')o.ok++;else o.rej++;}
  if(w[1]==='rescue'&&potNow-t<=7*86400){if(kv.r==='ok')potRes.ok++;else if(kv.r==='fail')potRes.fail++;}
  if(Math.floor(t/86400)===today){var k=w[1]==='reload'?'reload':w[1]==='rescue'?'rescue_'+(kv.r||''):w[1];potDay[k]=(potDay[k]||0)+1;
   if(w[1]==='id'){ids[kv.h]=1;if(kv.li==='1')potDay.li=(potDay.li||0)+1;}}}
 potDay.ids=Object.keys(ids).length;})();
function potBad(n){var o=potLen[String(n)];return !POT.off&&POT.early!=='off'&&!!o&&o.rej>=6&&o.rej>=9*o.ok?o:null;}
function potRescueSkip(s){if(POT.off||POT.rescue==='on')return false;var skip=POT.rescue==='off';
 if(!skip&&potRes.fail>=6&&potRes.ok===0){var h=0;for(var i=0;i<s.vid.length;i++)h=(h*31+s.vid.charCodeAt(i))>>>0;skip=(h%5)!==0;}
 if(skip&&!s.potSkipSaid){s.potSkipSaid=true;say('re-mint skipped t='+T()+' vid='+s.vid+' (mode '+(POT.rescue||'auto')+', last 7 days '+potRes.ok+' ok / '+potRes.fail+' failed)');potLog('rescue r=skipped');}
 return skip;}
function potFields(u,s,e){var out=[],i=s,n=0;while(i<e&&n++<64){var t=0,m=1,k=0;while(i+k<e){var c=u[i+k];t+=(c&127)*m;m*=128;k++;if(!(c&128))break;}i+=k;var w=t&7,f=Math.floor(t/8),ps=i;
 if(w===0){while(i<e&&(u[i]&128))i++;i++;}else if(w===2){var l=0,ml=1;while(i<e){var cl=u[i++];l+=(cl&127)*ml;ml*=128;if(!(cl&128))break;}ps=i;i+=l;}else if(w===5)i+=4;else if(w===1)i+=8;else return null;
 if(i>e)return null;out.push({f:f,w:w,ps:ps,pe:i});}return out;}
function potTokLen(b){try{var u=null;if(b instanceof Uint8Array)u=b;else if(b instanceof ArrayBuffer)u=new Uint8Array(b);else if(b&&ArrayBuffer.isView&&ArrayBuffer.isView(b))u=new Uint8Array(b.buffer,b.byteOffset,b.byteLength);
 if(!u)return -1;var top=potFields(u,0,u.length);if(!top)return -1;for(var k=0;k<top.length;k++)if(top[k].f===19&&top[k].w===2){var fs=potFields(u,top[k].ps,top[k].pe);if(!fs)return -1;
  for(var j=0;j<fs.length;j++)if(fs[j].f===2&&fs[j].w===2)return fs[j].pe-fs[j].ps;return 0;}}catch(e){}return -1;}
// R2 (2026-11-21, console g9q: 7 ids in 7 pages): VISITOR_DATA also carries a timestamp, so it changes every page. Hash only
// the visitor ID inside it (protobuf field 1); "k=raw" marks a page where that couldn't be read.
function potVisitorId(v){try{var s=decodeURIComponent(v).replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';var b=atob(s);
 if(b.charCodeAt(0)!==10)return '';var l=b.charCodeAt(1);if(l<1||l>64||b.length<2+l)return '';var id=b.slice(2,2+l);return /^[A-Za-z0-9_-]+$/.test(id)?id:'';}catch(e){return '';}}
function potId(){if(potIdSaid||POT.off)return;potIdSaid=true;var vd='',li=0;try{var c=window.ytcfg;if(c&&c.get){vd=c.get('VISITOR_DATA')||'';li=c.get('LOGGED_IN')?1:0;}}catch(e){}
 var vi=potVisitorId(vd),src=vi||vd,h=2166136261;for(var i=0;i<src.length;i++){h^=src.charCodeAt(i);h=Math.imul(h,16777619)>>>0;}potLog('id h='+(src?('00000000'+h.toString(16)).slice(-8):'none')+' li='+li+' k='+(vi?'id':'raw'));}   // OMNI_YT_POTOKEN_V1_R2
function potGotLen(vid,n,sentAt){if(!vid||n<=0||!itAt||sentAt<=itAt+0.2||POT.off)return;var s=state(vid);if(s.tokLen===n)return;s.tokLen=n;s.tokHow=s.rescuing?'rescue':'first';potId();
 if(s.ok||s.rejected)return;var o=potBad(n);if(!o)return;
 if(Math.random()<0.25){potLog('early-skip len='+n);return;}
 s.rejected=true;s.early=true;say('token not attested (early: length '+n+' rejected '+o.rej+'/'+(o.rej+o.ok)+' in 14 days) t='+T()+' vid='+vid);potLog('early len='+n);check();}
function potSniff(u,input,init){if(POT.off)return;try{
 if(/\/api\/jnn\/v1\/Create/.test(u)&&!window.__omniPotCreate)window.__omniPotCreate={url:u,body:(init&&typeof init.body==='string')?init.body:null};
 if(!isVp(u))return;var vid=vidNow(),at=performance.now()/1000;if(!vid||!itAt||at<=itAt+0.2)return;
 if(init&&init.body!=null){potGotLen(vid,potTokLen(init.body),at);return;}
 if(input&&typeof input==='object'&&input.clone&&input.method==='POST')input.clone().arrayBuffer().then(function(b){potGotLen(vid,potTokLen(b),at);},function(){});}catch(e){}}
function potSniffX(u,b){if(POT.off)return;try{if(/\/api\/jnn\/v1\/Create/.test(u)&&!window.__omniPotCreate)window.__omniPotCreate={url:u,body:typeof b==='string'?b:null};
 if(isVp(u)&&b!=null){var at=performance.now()/1000;potGotLen(vidNow(),potTokLen(b),at);}}catch(e){}}
function potOk(s){if(POT.off)return;if(s.tokLen)potLog('att len='+s.tokLen+' how='+(s.rescuing?'rescue':(s.tokHow||'first')));if(s.rescuing)potLog('rescue r=ok');}
function potSummary(){if(potSumSaid||POT.off||!vidNow())return;potSumSaid=true;var d=potDay,bad=[];for(var k in potLen){if(potBad(k))bad.push(k);}
 say('potoken today: att='+(d.att||0)+' rej='+(d.rej||0)+' early='+(d.early||0)+' reloads='+(d.reload||0)+' rescue='+(d.rescue_ok||0)+'/'+((d.rescue_ok||0)+(d.rescue_fail||0))+' ids='+(d.ids||0)+' signed-in='+(d.li||0)+' bad-lengths='+(bad.join(',')||'-')+' rescue-7d='+potRes.ok+'/'+(potRes.ok+potRes.fail));}
"""

CPP_FUNCS = r"""// OMNI_YT_POTOKEN_V1 (2026-11-21): the page's "potlog <event>" lines go to /data/omni/yt-attest-days.log, one line
// "<unix time> <event>" each (only A-Z a-z 0-9 = . _ - and space, max 160 chars); rotated to .old past 32 KB. The shell
// hands the last 16 KB back to the page at start (window.__omniPotCfg). Off with /data/omni/yt-potoken-off.flag.
static const char* const kOmniPotLog = "/data/omni/yt-attest-days.log";
static long omniPotBytes = -1;   // current log size, set when the shell reads it at start (-1: never read = don't rotate)
static bool omniPotOff = false;
static std::string omniPotClean(const std::string& in, size_t max, bool keepNl)
{
    std::string o;
    for (char c : in) {
        if (o.size() >= max) break;
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '=' || c == '.' || c == '_' || c == '-' || c == ' ' || (keepNl && c == '\n')) o += c;
    }
    return o;
}
static void omniPotAppend(const std::string& ev)
{
    if (omniPotOff) return;
    const std::string line = std::to_string((long long)time(nullptr)) + " " + omniPotClean(ev, 160, false) + "\n";
    if (omniPotBytes > 32768) {
        const std::string old = std::string(kOmniPotLog) + ".old";
        if (!rename(kOmniPotLog, old.c_str())) omniPotBytes = 0;
    }
    FILE* f = fopen(kOmniPotLog, "ab");
    if (!f) return;
    fputs(line.c_str(), f);
    fclose(f);
    if (omniPotBytes >= 0) omniPotBytes += (long)line.size();
}
"""

CPP_INSTALL = r"""    {   // OMNI_YT_POTOKEN_V1: hand the outcome history to YouTube pages (window.__omniPotCfg), before the guard script
        std::string cfg;
        if (!access("/data/omni/yt-potoken-off.flag", F_OK)) {
            omniPotOff = true;
            cfg = "window.__omniPotCfg={off:1};";
            fprintf(stderr, "OMNI YTPOT: off (/data/omni/yt-potoken-off.flag)\n");
        } else {
            std::string hist;
            omniPotBytes = 0;
            if (FILE* f = fopen(kOmniPotLog, "rb")) {
                char buf[8192]; size_t n;
                while ((n = fread(buf, 1, sizeof buf, f)) > 0) {
                    omniPotBytes += (long)n;
                    hist.append(buf, n);
                    if (hist.size() > 65536) hist.erase(0, hist.size() - 16384);
                }
                fclose(f);
            }
            if (hist.size() > 16384) {
                hist.erase(0, hist.size() - 16384);
                const size_t nl = hist.find('\n');
                hist.erase(0, nl == std::string::npos ? hist.size() : nl + 1);
            }
            std::string mode = "auto";
            if (FILE* f = fopen("/data/omni/yt-potoken-rescue.txt", "rb")) {
                char b[16]; const size_t n = fread(b, 1, sizeof b - 1, f);
                fclose(f);
                std::string m = omniPotClean(std::string(b, n), 8, false);
                while (!m.empty() && m[m.size() - 1] == ' ') m.erase(m.size() - 1);
                if (m == "on" || m == "off") mode = m;
            }
            std::string esc;
            for (char c : omniPotClean(hist, 16384, true)) { if (c == '\n') esc += "\\n"; else esc += c; }
            const bool early = access("/data/omni/yt-potoken-early-off.flag", F_OK) != 0;
            cfg = "if(/(^|\\.)youtube\\.com$/.test(location.hostname)){window.__omniPotCfg={log:\"" + esc + "\",rescue:\"" + mode
                + "\",early:\"" + (early ? "on" : "off") + "\"};window.__omniYtRescueMax=3;}";
            fprintf(stderr, "OMNI YTPOT: on (OMNI_YT_POTOKEN_V1; history %ld bytes, re-mint %s, early verdict %s; off with /data/omni/yt-potoken-off.flag)\n",
                omniPotBytes, mode.c_str(), early ? "on" : "off");
        }
        auto ptext = adoptWK(WKStringCreateWithUTF8CString(cfg.c_str()));
        auto pscript = adoptWK(WKUserScriptCreateWithSource(ptext.get(), kWKInjectAtDocumentStart, true));
        omniBlockerAddShellScript(pscript.get());
    }
"""

# (anchor, replacement, required). Every required anchor must occur exactly once; optional ones 0 or 1 times.
EDITS = [
    # page script: the PO-token block after the guard's state holder
    ("var cur=null;\n",
     "var cur=null;\n" + POT_JS, True),
    # first ok: log the attested token (and a rescue success) before the guard's own handling
    (" if(st==null)return;if(st===1&&!s.ok){s.ok=true;",
     " if(st==null)return;if(st===1&&!s.ok){potOk(s);s.ok=true;", True),
    # server says rejected: log it with the token's length
    ("if(st===2&&!s.ok&&itAt&&sentAt>itAt+0.2&&!s.rejected){s.rejected=true;",
     "if(st===2&&!s.ok&&itAt&&sentAt>itAt+0.2&&!s.rejected){s.rejected=true;potLog('rej len='+(s.tokLen||0));", True),
    # rescue failed -> log
    ("me.rescuing=false;me.acted=false;say('rescue failed t='",
     "me.rescuing=false;me.acted=false;potLog('rescue r=fail');say('rescue failed t='", True),
    # rescue policy: skip the re-mint when the recent record says it doesn't work
    ("if(s.rejected&&!s.rescueTried&&typeof window.__omniYtRescue==='function'){",
     "if(s.rejected&&!s.rescueTried&&typeof window.__omniYtRescue==='function'&&!potRescueSkip(s)){", True),
    # every reload is counted
    (" say((why==='rejected'?'reloadn ':'reload ')+why+",
     " potLog('reload why='+why+' try='+(n+1));say((why==='rejected'?'reloadn ':'reload ')+why+", True),
    (" say('reloadn stuck t='",
     " potLog('reload why=stuck try='+(n+1));say('reloadn stuck t='", True),
    (" say('reloadn cut-after-ok t='",
     " potLog('reload why=cut try='+(n+1));say('reloadn cut-after-ok t='", False),
    # token length sniff + the player's Create request (fetch, before the request is sent / its body used)
    ("window.fetch=function(input,init){var u=(typeof input==='string')?input:(input&&input.url)||String(input);var p=F.apply(this,arguments);",
     "window.fetch=function(input,init){var u=(typeof input==='string')?input:(input&&input.url)||String(input);potSniff(u,input,init);var p=F.apply(this,arguments);", True),
    # ... and XHR
    ("XMLHttpRequest.prototype.send=function(){var x=this;",
     "XMLHttpRequest.prototype.send=function(b){var x=this;potSniffX(x.__omniYgU||'',b);", True),
    # daily summary, once per watch page
    ("say('on '+location.pathname+",
     "potSummary();say('on '+location.pathname+", True),
    # shell: the potlog writer, before the prompt handler
    ("// The shell's runJavaScriptPrompt calls this first;",
     CPP_FUNCS + "// The shell's runJavaScriptPrompt calls this first;", True),
    # shell: route "potlog " lines to the file (the line is already logged above it)
    ('    if (v.rfind("reload ", 0) == 0 && page) {',
     '    if (v.rfind("potlog ", 0) == 0) { omniPotAppend(v.substr(7)); return true; }   // ' + MARK + '\n'
     '    if (v.rfind("reload ", 0) == 0 && page) {', True),
    # shell: the history/config script, injected before the guard
    ("    auto text = adoptWK(WKStringCreateWithUTF8CString(omniYtGuardSource));\n",
     CPP_INSTALL + "    auto text = adoptWK(WKStringCreateWithUTF8CString(omniYtGuardSource));\n", True),
]

OLD_ID = r"""function potId(){if(potIdSaid||POT.off)return;potIdSaid=true;var vd='',li=0;try{var c=window.ytcfg;if(c&&c.get){vd=c.get('VISITOR_DATA')||'';li=c.get('LOGGED_IN')?1:0;}}catch(e){}
 var h=2166136261;for(var i=0;i<vd.length;i++){h^=vd.charCodeAt(i);h=Math.imul(h,16777619)>>>0;}potLog('id h='+(vd?('00000000'+h.toString(16)).slice(-8):'none')+' li='+li);}
"""
NEW_ID = r"""// R2 (2026-11-21, console g9q: 7 ids in 7 pages): VISITOR_DATA also carries a timestamp, so it changes every page. Hash only
// the visitor ID inside it (protobuf field 1); "k=raw" marks a page where that couldn't be read.
function potVisitorId(v){try{var s=decodeURIComponent(v).replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';var b=atob(s);
 if(b.charCodeAt(0)!==10)return '';var l=b.charCodeAt(1);if(l<1||l>64||b.length<2+l)return '';var id=b.slice(2,2+l);return /^[A-Za-z0-9_-]+$/.test(id)?id:'';}catch(e){return '';}}
function potId(){if(potIdSaid||POT.off)return;potIdSaid=true;var vd='',li=0;try{var c=window.ytcfg;if(c&&c.get){vd=c.get('VISITOR_DATA')||'';li=c.get('LOGGED_IN')?1:0;}}catch(e){}
 var vi=potVisitorId(vd),src=vi||vd,h=2166136261;for(var i=0;i<src.length;i++){h^=src.charCodeAt(i);h=Math.imul(h,16777619)>>>0;}potLog('id h='+(src?('00000000'+h.toString(16)).slice(-8):'none')+' li='+li+' k='+(vi?'id':'raw'));}   // OMNI_YT_POTOKEN_V1_R2
"""

NEW_NAMES = ('POT', 'potLog', 'potBad', 'potRescueSkip', 'potFields', 'potTokLen', 'potId', 'potGotLen', 'potSniff',
             'potSniffX', 'potOk', 'potSummary', 'potVisitorId', 'omniPotAppend', 'omniPotClean', 'kOmniPotLog', '__omniPotCfg')


def variants(old0, s):
    """The anchor with the file's own line endings."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def patch(s):
    """Returns (new text, notes). Raises SystemExit with a reason when the file is not the expected guard."""
    if MARK in s:
        old, e = variants(OLD_ID, s)
        if s.count(old) == 1:   # R2 upgrade of an already patched guard
            s = s.replace(old, NEW_ID.replace('\n', e), 1)
            if s.count(')JS"') != 1:
                sys.exit('OmniYtGuard.h: raw string delimiter count changed; not writing')
            return s, ['upgraded to ' + MARK + ' R2 (visitor ID hash)']
        return None, ['already ' + MARK + (' R2' if 'OMNI_YT_POTOKEN_V1_R2' in s else '')]
    for need in ('OMNI_YT_ATTEST_GUARD_V1', 'function stuckCheck(', 'function overlayOn(', 'OMNI_YTGUARD_EXTRA_V1'):
        if need not in s:
            sys.exit('OmniYtGuard.h: %s missing (needs the v3 guard with overlay + extra script)' % need)
    for name in NEW_NAMES:
        if name + '(' in s or 'var ' + name + '=' in s or name + ' =' in s or ('window.' + name) in s:
            sys.exit('OmniYtGuard.h: name %s already used; refusing to add a clash' % name)
    notes = []
    for old0, _new, req in EDITS:   # every anchor is checked before anything is changed
        old, _e = variants(old0, s)
        c = s.count(old)
        if (req and c != 1) or (not req and c > 1):
            sys.exit('OmniYtGuard.h: anchor found %d times: %r' % (c, old0[:90]))
        if not req and c == 0:
            notes.append('optional anchor absent (skipped): %r' % old0[:60])
    for old0, new0, req in EDITS:
        old, e = variants(old0, s)
        if s.count(old) == 1:
            s = s.replace(old, new0.replace('\n', e), 1)
    if ')JS"' in POT_JS or s.count(')JS"') != 1 or s.count('R"JS(') != 1:
        sys.exit('OmniYtGuard.h: raw string delimiter count changed; not writing')
    return s, notes


def page_script(s):
    return s[s.index('R"JS(') + 5:s.index(')JS"')]


def node_check(js, tmp):
    node = shutil.which('node')
    if not node:
        return 'node not found: page-script syntax not checked'
    p = Path(tmp) / 'guard_page.js'
    p.write_text(js, encoding='utf-8')
    r = subprocess.run([node, '--check', str(p)], capture_output=True, text=True)
    if r.returncode:
        sys.exit('page script syntax error:\n' + (r.stderr or r.stdout)[-1500:])
    return 'node --check: page script OK'


def header_of(arg):
    p = Path(arg)
    return p if p.is_file() else p / 'engine' / 'entry' / 'OmniYtGuard.h'


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    args = [a for a in args if a != '--dry-run']
    if len(args) != 1:
        sys.exit(__doc__)
    src = header_of(args[0])
    if not src.exists():
        sys.exit('OmniYtGuard.h missing: %s (the recipe copies it from omni-ytattest first)' % src)
    if not dry:
        s = src.read_bytes().decode('utf-8')
        new, notes = patch(s)
        for n in notes:
            print('OmniYtGuard.h: ' + n)
        if new is None:
            return
        src.write_bytes(new.encode('utf-8'))
        print('OmniYtGuard.h: applied (+%d bytes)' % (len(new) - len(s)))
        print('applied ' + MARK)
        return
    tmp = tempfile.mkdtemp(prefix='omni-potoken-dry-')
    try:
        entry = Path(tmp) / 'engine' / 'entry'
        entry.mkdir(parents=True)
        copy = entry / 'OmniYtGuard.h'
        shutil.copyfile(src, copy)
        before = src.read_bytes()
        s = copy.read_bytes().decode('utf-8')
        new, notes = patch(s)
        for n in notes:
            print('dry-run: ' + n)
        if new is None:
            print('dry-run: nothing to do (already applied)')
            return
        copy.write_bytes(new.encode('utf-8'))
        again, _ = patch(new)
        if again is not None:
            sys.exit('dry-run: not idempotent')
        print('dry-run: ' + node_check(page_script(new), tmp))
        print('dry-run: %d edits, +%d bytes, page script %d -> %d bytes, %s occurs %d times' % (
            len([e for e in EDITS if variants(e[0], s)[0] in s]), len(new) - len(s), len(page_script(s)),
            len(page_script(new)), MARK, new.count(MARK)))
        if os.environ.get('POTOKEN_KEEP'):
            out = Path(os.environ['POTOKEN_KEEP'])
            out.write_bytes(new.encode('utf-8'))
            print('dry-run: patched copy kept at %s' % out)
        if src.read_bytes() != before:
            sys.exit('dry-run: the original changed!')
        print('dry-run: original untouched; ' + MARK + ' would apply')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


main()
