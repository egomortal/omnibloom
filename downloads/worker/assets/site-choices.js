/* OMNI_DL_SITE_CHOICES_V1 (D06): the new-download form remembers what you chose per site (what to save, file type,
   engine, save place) and fills it in the next time a link from that site is pasted. Kept in this origin's
   localStorage only, keyed by the site's host (no full addresses), at most 200 sites, oldest dropped.
   Pure functions + a small store wrapper; app.js does the form glue. */
(function(root,factory){'use strict';var api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.OmniSiteChoices=api;})(typeof globalThis!=='undefined'?globalThis:window,function(){
  'use strict';
  var STORE='omni-dl-site-choices-v1',MAX=200;
  var KINDS=['video','audio','file'],ENGINES=['ytdlp','jdownloader'],TYPES=['','mp4','mkv','m4a','webm'],PLACE=/^(internal|usb[0-7])$/;
  // The site a link belongs to: its host without "www." / "m." / "music."; null for anything not http(s).
  function siteOf(url){try{var u=new URL(String(url||'').trim());if(!/^https?:$/.test(u.protocol)||!u.hostname)return null;
    return u.hostname.toLowerCase().replace(/^(www|m|music|mobile)\./,'').replace(/\.$/,'').slice(0,253);}catch(_){return null;}}
  function clean(c){if(!c||typeof c!=='object')return null;
    var out={kind:KINDS.indexOf(c.kind)>=0?c.kind:null,engine:ENGINES.indexOf(c.engine)>=0?c.engine:null,
      type:TYPES.indexOf(c.type)>=0?c.type:null,place:typeof c.place==='string'&&PLACE.test(c.place)?c.place:null,t:typeof c.t==='number'&&isFinite(c.t)?c.t:0};
    return out.kind&&out.engine?out:null;}
  function load(storage){var out={};try{var raw=JSON.parse(storage.getItem(STORE)||'{}');
    if(raw&&typeof raw==='object')Object.keys(raw).slice(0,MAX*2).forEach(function(k){var c=clean(raw[k]);if(c&&/^[a-z0-9.-]{1,253}$/.test(k))out[k]=c;});}catch(_){}return out;}
  function save(storage,map){var keys=Object.keys(map).sort(function(a,b){return map[b].t-map[a].t;}).slice(0,MAX),out={};
    keys.forEach(function(k){out[k]=map[k];});try{storage.setItem(STORE,JSON.stringify(out));}catch(_){}return out;}
  function remember(storage,url,choice,now){var site=siteOf(url),c=clean(Object.assign({},choice,{t:typeof now==='number'&&isFinite(now)?now:Date.now()}));if(!site||!c)return false;
    var map=load(storage);map[site]=c;save(storage,map);return true;}
  function lookup(storage,url){var site=siteOf(url);if(!site)return null;var c=load(storage)[site];return c?Object.assign({site:site},c):null;}
  function forget(storage,url){var site=siteOf(url);if(!site)return false;var map=load(storage);if(!map[site])return false;delete map[site];save(storage,map);return true;}
  return Object.freeze({STORE:STORE,MAX:MAX,siteOf:siteOf,remember:remember,lookup:lookup,forget:forget,load:load});
});
