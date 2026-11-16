// Omni add-on "YouTube chapters": pure logic (no DOM). MIT, Omnibloom contributors.
// Chapters come from YouTube's own chapter markers when the page has them, else from the description's timestamp list,
// under YouTube's own rules for description chapters: the first is 0:00, at least 3, ascending, each at least 10 s long.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniYtChaptersCore=value})(globalThis,()=>{'use strict';
const MAX=200,TITLE=120;
// "1:02:03" / "12:34" / "0:05" -> seconds; anything else -> NaN
function seconds(text){const m=/^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})$/.exec(String(text||'').trim());if(!m)return NaN;
  const h=m[1]?Number(m[1]):0,mi=Number(m[2]),s=Number(m[3]);if(s>59||(m[1]&&mi>59))return NaN;return h*3600+mi*60+s}
function clock(t){t=Math.max(0,Math.floor(t));const h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;
  return(h?h+':'+String(m).padStart(2,'0'):String(m))+':'+String(s).padStart(2,'0')}
function cleanTitle(s){return String(s||'').replace(/[\u0000-\u001f\u007f]/g,' ').replace(/^[\s\-–—:|•·.)\]]+/,'').replace(/\s+/g,' ').trim().slice(0,TITLE)}
// One timestamp per line, at the start ("0:00 Intro", "(0:00) Intro", "0:00 - Intro") or at the end ("Intro 0:00").
const START=/^\s*[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*(.*)$/,END=/^(.*?)(?:^|[\s\-–—|]+)[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*$/;   // a space, dash or bracket before it: never ?t=1:23 in a link
function fromDescription(text){
  const out=[];for(const raw of String(text||'').split(/\r?\n/).slice(0,2000)){
    let m=START.exec(raw),t,title;
    if(m){t=seconds(m[1]);title=cleanTitle(m[2])}else if((m=END.exec(raw))){t=seconds(m[2]);title=cleanTitle(m[1])}else continue;
    if(!Number.isFinite(t))continue;out.push({t,title:title||clock(t)});if(out.length>=MAX)break}
  return valid(out)?out:[]}
function valid(list){if(list.length<3||list[0].t!==0)return false;
  for(let i=1;i<list.length;i++)if(list[i].t-list[i-1].t<10)return false;return true}
// From YouTube's own markers: [{title, time:"1:23"}] in page order -> sorted, deduped, valid start.
function fromMarkers(items){const out=[];const seen=new Set();
  for(const it of(Array.isArray(items)?items:[]).slice(0,MAX)){const t=seconds(it&&it.time);if(!Number.isFinite(t)||seen.has(t))continue;
    seen.add(t);out.push({t,title:cleanTitle(it.title)||clock(t)})}
  out.sort((a,b)=>a.t-b.t);return out.length>=2&&out[0].t===0?out:[]}
function index(list,t){let k=-1;for(let i=0;i<list.length;i++){if(list[i].t<=t+0.25)k=i;else break}return k}
// Next chapter start after t (null at the last); previous: the current chapter's start unless within 3 s of it.
function next(list,t){const i=index(list,t);return i+1<list.length?list[i+1].t:null}
function prev(list,t){const i=index(list,t);if(i<0)return 0;if(t-list[i].t>3)return list[i].t;return i>0?list[i-1].t:0}
return Object.freeze({seconds,clock,fromDescription,fromMarkers,valid,index,next,prev})});
