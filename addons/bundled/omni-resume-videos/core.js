// Omni add-on "Resume videos": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniResumeCore=value})(globalThis,()=>{'use strict';
const MIN_DURATION=180,END_MARGIN=30,MIN_POSITION=30,NEAR_START=10,MAX_ENTRIES=200,SAVE_EVERY=60000,PREFIX='r:';
// Query parameters that only track the visitor; dropped so one video keeps one key.
const TRACKING=/^(utm_[a-z_]+|fbclid|gclid|dclid|gbraid|wbraid|gclsrc|msclkid|yclid|twclid|ttclid|li_fat_id|igshid|igsh|mc_cid|mc_eid|_ga|_gl|_hsenc|_hsmi|__hssc|__hstc|__hsfp|hsctatracking|mkt_tok|oly_anon_id|oly_enc_id|vero_id|vero_conv|s_cid|cmpid|ncid|sr_share|spm|scm|ref_src|ref_url|si|feature|share|trk|trkcampaign|campaign_id|ad_id|adset_id|wt_mc|wt\.mc_id|at_medium|at_campaign|rb_clickid|epik)$/i;
// A start time in the link (?t=90, ?start=1m30s) is not part of the video's identity.
const TIME_KEY=/^(t|start|time_continue)$/i,TIME_VALUE=/^(\d+(\.\d+)?s?|(\d+h)?(\d+m)?(\d+s)?)$/i;
function normalize(href){let u;try{u=new URL(String(href))}catch(_){return null}if(u.protocol!=='https:'&&u.protocol!=='http:')return null;
const host=u.hostname.toLowerCase().replace(/^www\./,'')+(u.port?':'+u.port:'');let path=u.pathname.replace(/\/{2,}/g,'/');if(path.length>1)path=path.replace(/\/+$/,'');
const params=[...u.searchParams].filter(([k,v])=>!TRACKING.test(k)&&!(TIME_KEY.test(k)&&TIME_VALUE.test(v))).sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:a[1]<b[1]?-1:a[1]>b[1]?1:0);
const query=params.length?'?'+params.map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&'):'';
const hash=/^#[!/]/.test(u.hash)?u.hash:'';   // hash routers (#/video/1, #!/v/1) name the page; other fragments do not
return host+path+query+hash}
// Two 32-bit FNV-1a style lanes: a short storage key that does not keep the address itself.
function hash(text){let a=0x811c9dc5,b=0x9e3779b1;for(let i=0;i<text.length;i++){const c=text.charCodeAt(i);a=Math.imul(a^c,16777619);b=Math.imul(b^c,2246822519)^(b>>>13)}return(a>>>0).toString(36)+(b>>>0).toString(36)}
function key(normalized,index){return PREFIX+hash(normalized+(index>0?'\n'+index:''))}
function longEnough(duration){return typeof duration==='number'&&Number.isFinite(duration)&&duration>MIN_DURATION}
function valid(e){return Array.isArray(e)&&e.length>=3&&e.every(x=>typeof x==='number'&&Number.isFinite(x)&&x>=0)}
// What to do with the current position: 'skip' (not stored), 'remove' (finished) or 'store'.
function saveAction(position,duration,ended){if(!longEnough(duration))return'skip';if(ended||position>=duration-END_MARGIN)return'remove';if(!(position>=MIN_POSITION))return'skip';return'store'}
function entry(position,duration,now){return[Math.floor(position),Math.round(duration),Math.floor(now/1000)]}
// The position to offer, or null. The video must start near 0 and still be the same length.
function decide(saved,duration,position){if(!valid(saved)||!longEnough(duration)||!(position<=NEAR_START))return null;const[t,d]=saved;
if(Math.abs(d-duration)>Math.max(5,duration*.02))return null;if(t<MIN_POSITION||t>=duration-END_MARGIN)return null;return t}
// Keys to drop so at most max entries remain: oldest first (invalid entries count as oldest).
function prune(entries,max=MAX_ENTRIES){const list=Object.keys(entries).filter(k=>k.startsWith(PREFIX)).map(k=>({k,at:valid(entries[k])?entries[k][2]:-1}));
if(list.length<=max)return[];list.sort((x,y)=>x.at-y.at||(x.k<y.k?-1:1));return list.slice(0,list.length-max).map(x=>x.k)}
// Continue watching (Omni's start page reads these): one 'w:' entry per video, same hash as its 'r:' key, holding the
// cleaned page address, title, og:image, position, duration and time. Unlike 'r:' it keeps the address (the start page
// must reopen it). At most 30; dropped when finished (over 95 %) and never added before 2 minutes were watched.
const WATCH_PREFIX='w:',WATCH_MAX=30,WATCH_MIN=120,WATCH_DONE=.95,URL_MAX=2048,TITLE_MAX=160;
function watchKey(normalized,index){return WATCH_PREFIX+hash(normalized+(index>0?'\n'+index:''))}
// The page address to reopen: tracking and start-time parameters dropped (as normalize()), no credentials, other fragments dropped.
function cleanHref(href){let u;try{u=new URL(String(href))}catch(_){return null}if(u.protocol!=='https:'&&u.protocol!=='http:')return null;
u.username='';u.password='';for(const k of[...new Set(u.searchParams.keys())]){const keep=u.searchParams.getAll(k).filter(v=>!TRACKING.test(k)&&!(TIME_KEY.test(k)&&TIME_VALUE.test(v)));
u.searchParams.delete(k);for(const v of keep)u.searchParams.append(k,v)}if(!/^#[!/]/.test(u.hash))u.hash='';const out=u.href.replace(/\?$/,'');return out.length<=URL_MAX?out:null}
function watchAction(position,duration,ended){if(!longEnough(duration))return'skip';if(ended||position>=duration*WATCH_DONE)return'remove';if(!(position>=WATCH_MIN))return'skip';return'store'}
function cut(text,max){const t=String(text==null?'':text).replace(/\s+/g,' ').trim();return t.length<=max?t:t.slice(0,max-1).trimEnd()+'…'}
function imageUrl(content,base){if(!content)return'';let u;try{u=new URL(String(content).trim(),base)}catch(_){return''}return(u.protocol==='https:'||u.protocol==='http:')&&!u.username&&!u.password&&u.href.length<=1024?u.href:''}
// The stored value: {u,t,i,p,d,a}; null when the page address can't be kept.
function watchEntry(o){const u=cleanHref(o.url);if(!u)return null;const e={u,t:cut(o.title,TITLE_MAX),p:Math.floor(o.position),d:Math.round(o.duration),a:Math.floor(o.now/1000)};
const i=imageUrl(o.image,u);if(i)e.i=i;return e}
function validWatch(e){return!!e&&typeof e==='object'&&!Array.isArray(e)&&typeof e.u==='string'&&cleanHref(e.u)!==null&&[e.p,e.d,e.a].every(x=>typeof x==='number'&&Number.isFinite(x)&&x>=0)}
// Keys to drop so at most max continue-watching entries remain: oldest first (invalid ones first of all).
function pruneWatch(entries,max=WATCH_MAX){const list=Object.keys(entries).filter(k=>k.startsWith(WATCH_PREFIX)).map(k=>({k,at:validWatch(entries[k])?entries[k].a:-1}));
if(list.length<=max)return[];list.sort((x,y)=>x.at-y.at||(x.k<y.k?-1:1));return list.slice(0,list.length-max).map(x=>x.k)}
function clock(seconds){const s=Math.max(0,Math.floor(seconds)),h=Math.floor(s/3600),m=Math.floor(s%3600/60),r=s%60,p=n=>String(n).padStart(2,'0');return h?h+':'+p(m)+':'+p(r):m+':'+p(r)}
return Object.freeze({MIN_DURATION,END_MARGIN,MIN_POSITION,NEAR_START,MAX_ENTRIES,SAVE_EVERY,PREFIX,WATCH_PREFIX,WATCH_MAX,WATCH_MIN,WATCH_DONE,normalize,hash,key,longEnough,saveAction,entry,decide,prune,clock,
  watchKey,cleanHref,watchAction,watchEntry,validWatch,pruneWatch})});
