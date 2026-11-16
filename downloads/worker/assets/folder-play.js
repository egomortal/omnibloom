/* OMNI_DL_FOLDER_PLAY_V1 (D12): play a folder in order, shuffled or on repeat. Pure: the player passes the Library
   rows (id, name, folder, place, kind) and the current file; this picks what plays next. The mode is remembered in this
   origin's localStorage ('off' | 'order' | 'shuffle' | 'repeat'). */
(function(root,factory){'use strict';var api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.OmniFolderPlay=api;})(typeof globalThis!=='undefined'?globalThis:window,function(){
  'use strict';
  var MODES=['off','order','shuffle','repeat'],LABELS={off:'Folder: off',order:'Folder: in order',shuffle:'Folder: shuffle',repeat:'Folder: repeat'},STORE='omni-dl-folder-mode';
  var ID=/^[a-f0-9]{32}$/;
  // Playable files in the current file's folder (same place, same folder), in natural name order ("2" before "10").
  function siblings(rows,cur){if(!Array.isArray(rows)||!cur)return[];
    return rows.filter(function(r){return r&&ID.test(r.id||'')&&(r.kind==='video'||r.kind==='audio')&&r.place===cur.place&&(r.folder||'')===(cur.folder||'');})
      .sort(function(a,b){return String(a.name).localeCompare(String(b.name),undefined,{numeric:true,sensitivity:'base'})||(a.id<b.id?-1:1);});}
  // The next file id, or null to stop. rand() in [0,1) for shuffle (never the same file twice in a row when there are 2+).
  function next(list,curId,mode,rand){var n=list.length,i=-1;for(var k=0;k<n;k++)if(list[k].id===curId){i=k;break;}
    if(mode==='off'||!n)return null;
    if(mode==='shuffle'){if(n<2)return null;var others=list.filter(function(r){return r.id!==curId;});return others[Math.min(others.length-1,Math.floor((rand||Math.random)()*others.length))].id;}
    if(i<0)return list[0].id;
    if(i+1<n)return list[i+1].id;
    return mode==='repeat'?list[0].id:null;}
  // OMNI_DL_SIDECARS_V1 (D11): WebVTT captions beside a video: "Film.vtt" or "Film.<lang>.vtt" in the same folder.
  // -> [{id, lang, label}] (the bare one first, then by language), at most 4. SRT is not shown (the page cannot convert it).
  function sidecars(rows,cur){if(!Array.isArray(rows)||!cur||typeof cur.name!=='string')return[];var stem=cur.name.replace(/\.[^.]+$/,'').toLowerCase();
    var out=[];rows.forEach(function(r){if(!r||!ID.test(r.id||'')||r.place!==cur.place||(r.folder||'')!==(cur.folder||''))return;var n=String(r.name||'');
      if(!/\.vtt$/i.test(n))return;var base=n.slice(0,-4),low=base.toLowerCase(),lang='';
      if(low!==stem){if(low.indexOf(stem+'.')!==0)return;lang=base.slice(stem.length+1);if(!/^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?$/.test(lang))return;}
      out.push({id:r.id,lang:lang.replace('_','-'),label:lang?lang.replace('_','-').toUpperCase():'Captions'});});
    out.sort(function(a,b){return(a.lang?1:0)-(b.lang?1:0)||a.lang.localeCompare(b.lang);});return out.slice(0,4);}
  function cycle(mode){var i=MODES.indexOf(mode);return MODES[(i<0?1:i+1)%MODES.length];}   // unknown counts as 'off'
  function load(storage){try{var m=storage.getItem(STORE);return MODES.indexOf(m)>=0?m:'off';}catch(_){return'off';}}
  function save(storage,mode){try{storage.setItem(STORE,mode);}catch(_){}}
  return Object.freeze({MODES:MODES,LABELS:LABELS,sidecars:sidecars,siblings:siblings,next:next,cycle:cycle,load:load,save:save});
});
