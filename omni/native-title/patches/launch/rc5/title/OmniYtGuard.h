// OMNI_YT_ATTEST_GUARD_V1 (2026-11-11): keep YouTube playing when its stream protection doesn't attest the session.
// YouTube's SABR answers carry STREAM_PROTECTION_STATUS (UMP part 58: 1 ok, 2 pending, 3 required). When the player's
// PO token isn't attested (never minted, or minted but not accepted) the status stays 2, YouTube serves about a minute
// and then withholds media (status 3): the "stops at 1:00" bug (outputs/omni-ytattest notes; gates y1..y6). A fresh
// page without Omni's HTTP cache always attested on the console (gate y5), so the guard's one recovery is: put the
// current position in the URL (t=), then reload the page bypassing the cache (WKPageReloadFromOrigin), at most once
// per video per tab (sessionStorage). It acts only on /watch pages, only after it has seen status 2 for 20 s after the
// first media response with no status 1, or status 3. It reads part types and the status number only.
// ON by default; kill switch /data/omni/ytguard-off.flag (checked when the shell starts).
// Reports through window.prompt('\x01OMNI_YTGUARD_V1', line): "reload ..." asks for the reload, anything else is logged.
#pragma once
#include <unistd.h>
#include <cerrno>
#include <cstdio>
#include <ctime>
#include <string>
static const char omniYtGuardSource[] = R"JS((function(){
if(window.__omniYtGuardV1)return;window.__omniYtGuardV1=1;
if(window.top!==window)return;
if(!/(^|\.)youtube\.com$/.test(location.hostname))return;
var P=window.prompt,N=0;
function say(m){if(N++>200)return;try{P.call(window,'\u0001OMNI_YTGUARD_V1',String(m).slice(0,300));}catch(e){}}
function T(){return (performance.now()/1000).toFixed(1);}
function vidNow(){if(location.pathname!=='/watch')return null;try{return new URLSearchParams(location.search).get('v');}catch(e){return null;}}
function isVp(u){return /googlevideo\.com\/videoplayback/.test(String(u));}
function isIt(u){return /\/api\/jnn\/v1\/GenerateIT/.test(String(u));}
var itAt=0;   // when the page's last GenerateIT answered (performance.now s): requests sent after it carry the minted token
function pbStatus(p){var i=0;while(i<p.length){var v=0,m=1,n=0;while(i+n<p.length){var c=p[i+n];v+=(c&127)*m;m*=128;n++;if(!(c&128))break;}i+=n;var f=Math.floor(v/8),w=v&7;
 if(w===0){var x=0,mm=1,k=0;while(i+k<p.length){var cc=p[i+k];x+=(cc&127)*mm;mm*=128;k++;if(!(cc&128))break;}i+=k;if(f===1)return x;}
 else if(w===2){var l=0,ml=1,kl=0;while(i+kl<p.length){var cl=p[i+kl];l+=(cl&127)*ml;ml*=128;kl++;if(!(cl&128))break;}i+=kl+l;}else if(w===5)i+=4;else if(w===1)i+=8;else return null;}return null;}
function vlen(f){return f<128?1:f<192?2:f<224?3:f<240?4:5;}
function vval(h,o){var f=h[o];if(f<128)return f;if(f<192)return (f&63)+64*h[o+1];if(f<224)return (f&31)+32*(h[o+1]+256*h[o+2]);if(f<240)return (f&15)+16*(h[o+1]+256*(h[o+2]+256*h[o+3]));return h[o+1]+256*(h[o+2]+256*(h[o+3]+256*h[o+4]));}
// Streaming UMP walk: headers are parsed, payloads skipped, only part 58 is collected. Resolves the first status or null.
function Ump(){this.h=[];this.skip=0;this.need=0;this.coll=null;this.done=false;this.st=null;}
Ump.prototype.feed=function(b){var i=0;while(i<b.length&&!this.done){
 if(this.skip>0){var s=Math.min(this.skip,b.length-i);i+=s;this.skip-=s;continue;}
 if(this.coll){var t=Math.min(this.need-this.coll.length,b.length-i);for(var j=0;j<t;j++)this.coll.push(b[i+j]);i+=t;
  if(this.coll.length>=this.need){this.st=pbStatus(this.coll);this.coll=null;if(this.st!=null){this.done=true;}}continue;}
 this.h.push(b[i++]);var h=this.h;if(h.length<1)continue;var l1=vlen(h[0]);if(h.length<l1+1)continue;var l2=vlen(h[l1]);if(h.length<l1+l2)continue;
 var type=vval(h,0),size=vval(h,l1);this.h=[];
 if(type===58&&size<4096){if(size===0)continue;this.coll=[];this.need=size;}else this.skip=size;}
 return this.done;};
var cur=null;
function state(vid){if(!cur||cur.vid!==vid)cur={vid:vid,first:0,last:null,ok:false,acted:false,seen2:false,rejected:false};return cur;}
function onStatus(vid,st,sentAt){if(!vid)return;var s=state(vid);var now=performance.now()/1000;if(!s.first)s.first=now;
 if(st==null)return;if(st===1&&!s.ok){s.ok=true;try{sessionStorage.removeItem('omniYtGuardV1:'+vid);}catch(e){}if(s.seen2)say('attested t='+T()+' vid='+vid);}
 if(st===2&&!s.ok&&itAt&&sentAt>itAt+0.2&&!s.rejected){s.rejected=true;say('token not attested t='+T()+' vid='+vid);}
 if(st!==1&&s.last!==st)say('status '+st+' t='+T()+' vid='+vid+(s.ok?' (after ok)':''));
 if(st===2)s.seen2=true;s.last=st;check();}
var MAXR=5;
function recover(s,why){s.acted=true;var key='omniYtGuardV1:'+s.vid,n=0;try{n=+(sessionStorage.getItem(key)||0);}catch(e){}
 if(n>=MAXR){say('gave up t='+T()+' vid='+s.vid+' '+why+' (already reloaded '+n+' times for this video in this tab)');return;}
 try{sessionStorage.setItem(key,String(n+1));}catch(e){say('no sessionStorage: not reloading');return;}
 var v=document.querySelector('video'),pos=v?Math.max(0,Math.floor(v.currentTime)-2):0;
 try{var u=new URL(location.href);u.searchParams.set('t',pos+'s');history.replaceState(history.state,'',u.toString());}catch(e){}
 say((why==='rejected'?'reloadn ':'reload ')+why+' t='+T()+' vid='+s.vid+' pos='+pos+' try='+(n+1));
 setTimeout(function(){location.reload();},8000);}   // only if the shell didn't reload (guard header missing)
function check(){var s=cur;if(!s||s.ok||s.acted||!s.first)return;if(vidNow()!==s.vid)return;var now=performance.now()/1000;
 if(s.rejected)recover(s,'rejected');else if(s.last===3)recover(s,'status3');else if(s.last===2&&now-s.first>20)recover(s,'pending20s');}
setInterval(check,2000);
var F=window.fetch;
if(F){window.fetch=function(input,init){var u=(typeof input==='string')?input:(input&&input.url)||String(input);var p=F.apply(this,arguments);
 if(isIt(u))p.then(function(r){if(r&&r.ok)itAt=performance.now()/1000;},function(){});
 if(isVp(u)){var vid=vidNow(),sentAt=performance.now()/1000;p.then(function(r){try{if(!r.body||!r.clone)return;var rd=r.clone().body.getReader(),um=new Ump();
  var pump=function(){return rd.read().then(function(x){if(x.done){onStatus(vid,um.st,sentAt);return;}if(um.feed(x.value)){onStatus(vid,um.st,sentAt);try{rd.cancel();}catch(e){}return;}return pump();});};
  pump().catch(function(){});}catch(e){}},function(){});}
 return p;};}
var XO=XMLHttpRequest.prototype.open,XS=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open=function(m,u){this.__omniYgU=String(u);return XO.apply(this,arguments);};
XMLHttpRequest.prototype.send=function(){var x=this;if(isIt(x.__omniYgU||''))x.addEventListener('loadend',function(){if(x.status===200)itAt=performance.now()/1000;});
 if(isVp(x.__omniYgU||'')){var vid=vidNow(),sentAt=performance.now()/1000;x.addEventListener('loadend',function(){try{if(x.responseType==='arraybuffer'&&x.response){var um=new Ump();um.feed(new Uint8Array(x.response));onStatus(vid,um.st,sentAt);}}catch(e){}});}
 return XS.apply(this,arguments);};
var t0=null;try{t0=new URLSearchParams(location.search).get('t');}catch(e){}
say('on '+location.pathname+' t='+T()+(vidNow()?' vid='+vidNow():'')+(t0?' start='+t0:''));
})();)JS";
// The shell's runJavaScriptPrompt calls this first; true when the prompt was the guard's (answered at once).
static bool omniYtGuardPrompt(WKPageRef page, WKStringRef text, WKStringRef value, WKPageRunJavaScriptPromptResultListenerRef listener)
{
    if (OmniTest::toStd(text) != "\x01OMNI_YTGUARD_V1") return false;
    const std::string v = OmniTest::toStd(value);
    log(("page: OMNI_YTGUARD " + v).c_str());
    WKPageRunJavaScriptPromptResultListenerCall(listener, nullptr);
    if (v.rfind("reload ", 0) == 0 && page) {
        log("OMNI YTGUARD: reloading the page from the network (cache bypassed) at the position in its URL");
        WKPageReloadFromOrigin(page);
    } else if (v.rfind("reloadn ", 0) == 0 && page) {
        log("OMNI YTGUARD: reloading the page (new BotGuard run) at the position in its URL");
        WKPageReload(page);
    }
    return true;
}
// OMNI_NC_RESET_V1: once per profile, before the data store is configured, the HTTP cache built by the builds without
// OMNI_NC_BLOB_COPY_V1 (every large body lost, records left bodiless) is set aside, so the new child starts from an
// empty cache. Renamed, never deleted (NetworkCache.before-rc5-<unix time>). Marker <profile>/.omni-nc-reset-v1;
// kill switch /data/omni/nc-reset-off.flag (then nothing happens and no marker is written).
static void omniNcResetOnce(const std::string& profile)
{
    if (!access("/data/omni/nc-reset-off.flag", F_OK)) { fprintf(stderr, "OMNI NCRESET: off (/data/omni/nc-reset-off.flag)\n"); return; }
    const std::string marker = profile + "/.omni-nc-reset-v1", nc = profile + "/NetworkCache";
    if (!access(marker.c_str(), F_OK)) return;
    if (!access(nc.c_str(), F_OK)) {
        const std::string aside = nc + ".before-rc5-" + std::to_string((long long)time(nullptr));
        if (rename(nc.c_str(), aside.c_str())) { fprintf(stderr, "OMNI NCRESET: rename failed (errno %d); cache left in place, will retry next start\n", errno); return; }
        fprintf(stderr, "OMNI NCRESET: old HTTP cache set aside as %s (OMNI_NC_RESET_V1, once)\n", aside.c_str());
    } else fprintf(stderr, "OMNI NCRESET: no HTTP cache to set aside\n");
    if (FILE* m = fopen(marker.c_str(), "w")) { fputs("OMNI_NC_RESET_V1\n", m); fclose(m); }
}
// Install once at shell start. On unless /data/omni/ytguard-off.flag.
static void omniYtGuardInstall()
{
    if (!access("/data/omni/ytguard-off.flag", F_OK)) { fprintf(stderr, "OMNI YTGUARD: off (/data/omni/ytguard-off.flag)\n"); return; }
    auto text = adoptWK(WKStringCreateWithUTF8CString(omniYtGuardSource));
    auto script = adoptWK(WKUserScriptCreateWithSource(text.get(), kWKInjectAtDocumentStart, true));   // main frame only
    omniBlockerAddShellScript(script.get());
    fprintf(stderr, "OMNI YTGUARD: installed (OMNI_YT_ATTEST_GUARD_V1; off with /data/omni/ytguard-off.flag)\n");
}
