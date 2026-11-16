/* OMNI_DOWNLOAD_ALL_V1: the "#files=" hand-over from Omni's page menu "Download all...".
   {"v":1,"p":"<page address>","u":["<file address>",...]} (1..200 links). Links only: nothing is downloaded until the
   user presses "Download N files" in the Downloads app. Every link must pass the same check as a single shared link. */
(function(root,factory){'use strict';var api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.OmniBatchWire=api;})(typeof globalThis!=='undefined'?globalThis:window,function(){
  'use strict';
  var MAX=200,HASH_MAX=262144;
  var INVALID='The file list from the browser was rejected. Nothing was downloaded.';
  function invalid(message){return {ok:false,urls:[],page:'',message:message||INVALID};}
  function parse(hash,validUrl){
    if(typeof validUrl!=='function')return invalid();
    if(typeof hash!=='string'||hash.length>HASH_MAX)return invalid('The file list exceeded its safety limit. Nothing was downloaded.');
    var body=hash.replace(/^#/,'');
    var fields=body.split('&').filter(function(pair){return pair.split('=')[0]==='files';});
    if(fields.length!==1)return invalid();
    try{
      var value=JSON.parse(new URLSearchParams(body).get('files'));
      if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(function(key){return ['v','p','u'].indexOf(key)<0;}))return invalid();
      if(value.v!==1||!Array.isArray(value.u)||!value.u.length||value.u.length>MAX)return invalid();
      if(value.p!==undefined&&value.p!==''&&!validUrl(value.p))return invalid();
      var seen=new Set(),urls=[];
      for(var i=0;i<value.u.length;i++){
        var url=value.u[i];
        if(!validUrl(url))return invalid();
        if(!seen.has(url)){seen.add(url);urls.push(url);}
      }
      return {ok:true,urls:urls,page:typeof value.p==='string'?value.p:'',message:''};
    }catch(_){return invalid();}
  }
  // The name a row shows: the address's last path part (decoded), else its host.
  function nameOf(url){
    try{
      var parsed=new URL(url),parts=parsed.pathname.split('/'),last=parts[parts.length-1]||'';
      try{last=decodeURIComponent(last);}catch(_){}
      last=last.replace(/[\u0000-\u001f\u007f]/g,'').trim();
      return last||parsed.hostname;
    }catch(_){return String(url);}
  }
  return Object.freeze({parse:parse,nameOf:nameOf,max:MAX,hashMax:HASH_MAX});
});
