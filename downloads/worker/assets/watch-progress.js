/* OMNI_DL_WATCH_V1: where each saved film was left, kept in this origin's localStorage only (nothing goes to the worker).
   The library's file id changes when the worker restarts (it is signed with the session token), so the store key is a
   short hash of place + file name + size. Only the hash is stored: no names, no paths.
   Used by player.js (save / resume prompt) and files-library.js (thin progress bar and "Watched" tick on tiles). */
(function(root,factory){'use strict';var api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.OmniWatch=api;})(typeof globalThis!=='undefined'?globalThis:window,function(){
  'use strict';
  var STORE='omni-dl-watch-v1',MAX=500,RESUME_MIN=30,RESUME_TAIL=30,WATCHED=0.9,KEY=/^w[a-f0-9]{16}$/;

  // Two FNV-1a 32-bit passes (different offsets) -> 16 hex digits. Stable across restarts, browsers and page loads.
  function fnv(text,seed){var h=seed>>>0;for(var i=0;i<text.length;i++){h^=text.charCodeAt(i);h=Math.imul(h,16777619)>>>0;}return ('0000000'+h.toString(16)).slice(-8);}
  function keyFor(file){
    if(!file||typeof file.name!=='string'||!file.name||typeof file.size!=='number'||!isFinite(file.size)||file.size<0)return null;
    var text=String(file.place||'')+'\0'+file.name+'\0'+Math.floor(file.size);
    return 'w'+fnv(text,2166136261)+fnv(text,0x811c9dc5^0x5bd1e995);
  }
  function valid(entry){return !!entry&&typeof entry==='object'&&typeof entry.p==='number'&&typeof entry.d==='number'&&typeof entry.t==='number'&&isFinite(entry.p)&&isFinite(entry.d)&&isFinite(entry.t)&&entry.p>=0&&entry.d>0&&entry.p<=entry.d+1;}

  // The store is per origin but still untrusted input: only well-formed entries survive a read.
  function load(storage){
    var out={};
    try{
      var raw=JSON.parse(storage.getItem(STORE)||'null');
      if(raw&&typeof raw==='object'&&!Array.isArray(raw))Object.keys(raw).forEach(function(k){if(KEY.test(k)&&valid(raw[k]))out[k]={p:raw[k].p,d:raw[k].d,w:raw[k].w?1:0,t:raw[k].t};});
    }catch(_){}
    return out;
  }
  function trim(all){
    var keys=Object.keys(all);if(keys.length<=MAX)return all;
    keys.sort(function(a,b){return all[a].t-all[b].t;});
    keys.slice(0,keys.length-MAX).forEach(function(k){delete all[k];});
    return all;
  }
  function get(storage,key){return key?load(storage)[key]||null:null;}
  // Save one position; past 90 % the file is marked watched (and stays watched). Oldest entries go past 500.
  function record(storage,key,position,duration,now){
    if(!key||!KEY.test(key)||typeof position!=='number'||typeof duration!=='number'||!isFinite(duration)||duration<=0||!isFinite(position))return null;
    var all=load(storage),p=Math.max(0,Math.min(duration,Math.round(position*10)/10)),before=all[key];
    var entry={p:p,d:Math.round(duration*10)/10,w:(before&&before.w)||p>=duration*WATCHED?1:0,t:typeof now==='number'?now:Date.now()};
    all[key]=entry;trim(all);
    try{storage.setItem(STORE,JSON.stringify(all));}catch(_){}
    return entry;
  }
  // Offer to resume only from the middle: not in the first 30 s, not in the last 30 s.
  function resumeAt(entry,duration){
    if(!valid(entry))return 0;
    var d=typeof duration==='number'&&isFinite(duration)&&duration>0?duration:entry.d;
    return entry.p>RESUME_MIN&&entry.p<d-RESUME_TAIL?entry.p:0;
  }
  function tileState(entry){
    if(!valid(entry))return {state:'none',fraction:0};
    if(entry.w)return {state:'watched',fraction:1};
    if(entry.p>RESUME_MIN)return {state:'partial',fraction:Math.max(0.01,Math.min(0.99,entry.p/entry.d))};
    return {state:'none',fraction:0};
  }
  function tileHtml(entry){
    var s=tileState(entry);
    if(s.state==='watched')return '<span class="lib-watched" data-watch="watched"><span aria-hidden="true">✓</span> Watched</span>';
    if(s.state==='partial'){var pct=Math.round(s.fraction*100);return '<span class="lib-progress" data-watch="partial" role="img" aria-label="'+pct+'% watched"><span style="width:'+pct+'%"></span></span>';}
    return '';
  }
  return Object.freeze({STORE:STORE,MAX:MAX,RESUME_MIN:RESUME_MIN,RESUME_TAIL:RESUME_TAIL,WATCHED:WATCHED,keyFor:keyFor,load:load,get:get,record:record,resumeAt:resumeAt,tileState:tileState,tileHtml:tileHtml});
});
