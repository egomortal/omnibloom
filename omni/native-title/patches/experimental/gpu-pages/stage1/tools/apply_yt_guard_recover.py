#!/usr/bin/env python3
"""OMNI_YT_GUARD_RECOVER_V1 (2026-11-16): the YouTube guard recovers from "status 3 AFTER ok".

Why
  OMNI_YT_ATTEST_GUARD_V1 (OmniYtGuard.h, copied into the title tree by the rc6 recipe before the chain) reloads the
  page when YouTube's SABR stream-protection status says the session isn't attested (2 for 40 s, rejected, or 3) -
  but only until it has seen status 1 ("ok"). Once ok, check() only runs the v3 "stuck 15 s" rule. Console gates
  Lyt0-013923 (v052aa), Lyt0-104557 and Lyt0-105939 (v052ag) all logged
      page: OMNI_YTGUARD status 2 t=15.7 ... (after ok)
      page: OMNI_YTGUARD status 3 t=74.4 ... (after ok)
  then the media position stopped at exactly 60.0 s (readyState 4 -> 3 -> 2, buffer drained), and ~10 s later the
  player tore the element down (currentTime 0, paused, readyState 0). The stuck rule never fires: 10 s < 15 s, and
  after the teardown the element is paused. The video simply ends at 1:00.

What this adds (page script only, plus one kill switch in omniYtGuardInstall)
  - onStatus: after ok, a status 3 arms s.cut (the time); a later status 1 disarms it ("cut cleared").
  - check(): while ok, the last real position is remembered (s.pos; teardown resets currentTime to 0), and cutCheck()
    runs before the stuck rule. It waits while the video still has >= 2 s buffered ahead and plays (max 25 s from
    the status 3), while it is paused by the user, or while seeking; then it reloads the page from the network at the
    last position - the same "reload " prompt (WKPageReloadFromOrigin, fresh BotGuard run, empty cache for the page)
    and "Reconnecting to YouTube..." overlay the pre-ok status-3 rule already uses. The page log line is
        page: OMNI_YTGUARD reload cut-after-ok t=.. vid=.. pos=.. try=N rs=.. ahead=..
  - Cap: 3 such reloads per video per tab (sessionStorage omniYtGuardRc:<vid> = "n|ms"); the count restarts when the
    last one is older than 10 minutes, so a long video that is cut every so often keeps going, a loop does not.
    Past the cap: "cut after ok, gave up ..." once, and the video stops as before.
  - Kill switch /data/omni/ytguard-recover-off.flag (read at shell start): a one-line page script sets
    window.__omniYtNoCutRecover=1 and the guard behaves exactly as before (A/B on the console without a rebuild).

Build safety: only names OmniYtGuard.h already uses (access, adoptWK, WKStringCreateWithUTF8CString,
WKUserScriptCreateWithSource, kWKInjectAtDocumentStart, omniBlockerAddShellScript, fprintf). No new prompt verbs: the
shell's omniYtGuardPrompt already routes "reload " to WKPageReloadFromOrigin.

Usage: apply_yt_guard_recover.py <title tree>   (edits <tree>/engine/entry/OmniYtGuard.h; idempotent)
"""
import sys
from pathlib import Path

MARK = 'OMNI_YT_GUARD_RECOVER_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

CUT_FUNCS = r"""// OMNI_YT_GUARD_RECOVER_V1 (2026-11-16): status 3 AFTER the session attested (gates Lyt0 v052aa/v052ag: "status 3
// ... (after ok)", media stops at 60.0 s, ~10 s later the player tears down). Reload from the network at the last
// position once the buffer is nearly drained (or the player stalled / tore down, or 25 s passed), at most 3 times per
// video per tab within 10 min. A later status 1 cancels it. Off with /data/omni/ytguard-recover-off.flag.
var MAXC=3;
function cutPos(s){var v=document.querySelector('video');if(v&&!v.seeking&&v.currentTime>0&&v.readyState>=2)s.pos=v.currentTime;}
function cutCheck(s,now){if(!s.cut||window.__omniYtNoCutRecover)return false;
 var v=document.querySelector('video'),ct=v?(v.currentTime||0):0,ahead=0;
 try{var b=v?v.buffered:null;for(var i=0;b&&i<b.length;i++){if(b.start(i)<=ct+0.05&&ct<b.end(i))ahead=b.end(i)-ct;}}catch(e){}
 var gone=!v||v.readyState<2||(ct===0&&(s.pos||0)>5);
 if(!gone&&(v.paused||v.seeking))return true;
 if(!gone&&v.readyState>=3&&ahead>=2&&now-s.cut<25)return true;
 var key='omniYtGuardRc:'+s.vid,n=0,at=0;try{var r=(sessionStorage.getItem(key)||'').split('|');n=+(r[0]||0);at=+(r[1]||0);}catch(e){}
 if(at&&Date.now()-at>600000)n=0;
 if(n>=MAXC){if(!s.cutSaid){s.cutSaid=true;say('cut after ok, gave up t='+T()+' vid='+s.vid+' (reloaded '+n+' times in 10 min)');}s.cut=0;return false;}
 try{sessionStorage.setItem(key,(n+1)+'|'+Date.now());}catch(e){say('no sessionStorage: not reloading');s.cut=0;return false;}
 s.acted=true;var pos=Math.max(0,Math.floor(Math.max(ct,s.pos||0))-1);
 try{var u=new URL(location.href);u.searchParams.set('t',pos+'s');history.replaceState(history.state,'',u.toString());}catch(e){}
 say('reloadn cut-after-ok t='+T()+' vid='+s.vid+' pos='+pos+' try='+(n+1)+' rs='+(v?v.readyState:-1)+' ahead='+ahead.toFixed(1));
 overlayOn(true);setTimeout(function(){location.reload();},8000);return true;}
"""

KILL = r"""    if (!access("/data/omni/ytguard-recover-off.flag", F_OK)) {   // OMNI_YT_GUARD_RECOVER_V1 kill switch
        auto off = adoptWK(WKStringCreateWithUTF8CString("window.__omniYtNoCutRecover=1;"));
        auto offScript = adoptWK(WKUserScriptCreateWithSource(off.get(), kWKInjectAtDocumentStart, true));
        omniBlockerAddShellScript(offScript.get());
        fprintf(stderr, "OMNI YTGUARD: cut-after-ok recovery off (/data/omni/ytguard-recover-off.flag)\n");
    }
"""

EDITS = [
    # 1. onStatus: arm on status 3 after ok, disarm on a later status 1
    (" if(st===2)s.seen2=true;s.last=st;check();}\n",
     " if(s.ok){if(st===3&&!s.cut){s.cut=now;}else if(st===1&&s.cut){s.cut=0;say('cut cleared t='+T()+' vid='+vid);}}   // " + MARK + "\n"
     " if(st===2)s.seen2=true;s.last=st;check();}\n"),
    # 2. the recovery functions, before check()
    ("function check(){var s=cur;if(!s||s.acted||!s.first)return;",
     CUT_FUNCS + "function check(){var s=cur;if(!s||s.acted||!s.first)return;"),
    # 3. check(): after ok, remember the position and run the cut rule before the stuck rule
    (" if(s.ok){stuckCheck(s,now);return;}\n",
     " if(s.ok){cutPos(s);if(cutCheck(s,now))return;stuckCheck(s,now);return;}   // " + MARK + "\n"),
    # 4. kill switch, before the guard script is installed
    ("    auto text = adoptWK(WKStringCreateWithUTF8CString(omniYtGuardSource));\n",
     KILL + "    auto text = adoptWK(WKStringCreateWithUTF8CString(omniYtGuardSource));\n"),
]


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def main():
    p = root / 'OmniYtGuard.h'
    if not p.exists():
        sys.exit('OmniYtGuard.h missing in %s (the recipe copies it from omni-ytattest first)' % root)
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        # OMNI_YT_GUARD_RECOVER_V1_R2: the cut reload is a normal reload ("reloadn " -> WKPageReload). On the console the
        # cache-bypassed reload ("reload " -> WKPageReloadFromOrigin) came back 'token not attested' and needed a 2nd reload.
        old = " say('reload cut-after-ok t='"
        if old in s:
            p.write_bytes(s.replace(old, " say('reloadn cut-after-ok t='", 1).encode('utf-8'))
            print('OmniYtGuard.h: upgraded to R2 (normal reload after a cut)')
            print('applied ' + MARK + ' R2')
            return
        print('OmniYtGuard.h: already')
        print('already ' + MARK)
        return
    if 'OMNI_YT_ATTEST_GUARD_V1' not in s or 'function stuckCheck(' not in s or 'function overlayOn(' not in s:
        sys.exit('OmniYtGuard.h: not the v3 guard with the overlay (OMNI_YT_ATTEST_GUARD_V1 / stuckCheck / overlayOn missing)')
    for name in ('MAXC', 'cutPos', 'cutCheck', '__omniYtNoCutRecover', 'omniYtGuardRc:'):
        if name in s:
            sys.exit('OmniYtGuard.h: name %s already used; refusing to add a clash' % name)
    for old0, _ in EDITS:   # every anchor is checked before anything is written
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('OmniYtGuard.h: anchor found %d times: %r' % (s.count(old), old0[:90]))
    for old0, new0 in EDITS:
        old, e = variants(old0, s)
        s = s.replace(old, new0.replace('\n', e), 1)
    if ')JS"' in CUT_FUNCS or s.count(')JS"') != 1:
        sys.exit('OmniYtGuard.h: raw string delimiter count changed; not writing')
    p.write_bytes(s.encode('utf-8'))
    print('OmniYtGuard.h: applied')
    print('applied ' + MARK)


main()
