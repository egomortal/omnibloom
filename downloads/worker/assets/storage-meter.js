/* OMNI_DL_STORAGE_METER_V1: the storage meter above the Library (console storage and each USB drive).
   Pure: it turns the worker's status.places ({id,label,free_bytes,total_bytes}) into rows the Library draws.
   "Largest files" in the Library is the existing size sort; this file only measures. */
(function(root,factory){'use strict';var api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.OmniStorageMeter=api;})(typeof globalThis!=='undefined'?globalThis:window,function(){
  'use strict';
  var LOW_SHARE=0.05,LOW_BYTES=2*1073741824,MAX_ROWS=9;
  function size(v){return v>=1099511627776?(v/1099511627776).toFixed(1)+' TB':v>=1073741824?(v/1073741824).toFixed(1)+' GB':v>=1048576?(v/1048576).toFixed(1)+' MB':v>=1024?Math.round(v/1024)+' KB':Math.max(0,Math.round(v))+' B';}
  function num(v){return typeof v==='number'&&isFinite(v)&&v>=0;}
  // One row per place with a usable size: used share (0..100, one decimal), the text, and whether space is low.
  function rows(places){
    if(!Array.isArray(places))return [];
    var out=[];
    for(var i=0;i<places.length&&out.length<MAX_ROWS;i++){
      var p=places[i];
      if(!p||typeof p.id!=='string'||!/^(internal|usb[0-7])$/.test(p.id)||typeof p.label!=='string')continue;
      if(!num(p.free_bytes)||!num(p.total_bytes)||p.total_bytes<=0)continue;
      var free=Math.min(p.free_bytes,p.total_bytes),used=p.total_bytes-free;
      var low=free<LOW_BYTES||free/p.total_bytes<LOW_SHARE;
      out.push({id:p.id,label:p.label.slice(0,40),used_pct:Math.round(used/p.total_bytes*1000)/10,
        text:size(free)+' free of '+size(p.total_bytes),low:low});
    }
    return out;
  }
  return Object.freeze({rows:rows,size:size,LOW_SHARE:LOW_SHARE,LOW_BYTES:LOW_BYTES});
});
