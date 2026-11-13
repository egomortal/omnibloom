/* Native isolated-world candidate wire. All detections are hints, never verified files. */
(function(root,factory){'use strict';var api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.OmniCandidateWire=api;})(typeof globalThis!=='undefined'?globalThis:window,function(){
 'use strict';
 var KINDS=new Set(['media-url','manifest','metadata-url','source-page']);
 var SCORES=new Set([25,35,45,55,60,75,90,95]);
 var EVIDENCE=new Set(['media-current','media-source','og-video','anchor-media','page-video','media-blob','iframe','encrypted-media-page-fallback','blob-is-not-a-network-file','resource-timing','iframe-media']);
 function keys(value,allowed){return !!value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).every(function(key){return allowed.includes(key);});}
  function utf8Length(value){
    var bytes=0;
    for(var index=0;index<value.length;index++){
      var point=value.charCodeAt(index);
      if(point>=0xD800&&point<=0xDBFF){var next=value.charCodeAt(index+1);if(!(next>=0xDC00&&next<=0xDFFF))return -1;index++;bytes+=4;}
      else if(point>=0xDC00&&point<=0xDFFF)return -1;
      else bytes+=point<=0x7F?1:point<=0x7FF?2:3;
    }
    return bytes;
  }
  function url(value){
    if(typeof value!=='string'||!value||value.length>4096||!/^https?:\/\//i.test(value)||/[\s\\\u0000-\u001f\u007f]/.test(value))return false;
    var bytes=utf8Length(value);if(bytes<0||bytes>8192)return false;
    try{var authority=value.match(/^https?:\/\/([^/?#]*)/i);if(!authority||authority[1].includes('@'))return false;var parsed=new URL(value);return /^(https?:)$/.test(parsed.protocol)&&!!parsed.hostname&&!parsed.username&&!parsed.password&&parsed.port!=='0';}catch(_){return false;}
  }
 function parse(hash){
   var invalid={ok:false,rows:[],source:'',generation:'',truncated:false,message:'Media suggestions were rejected as invalid. No links were saved or downloaded.'};
   if(typeof hash!=='string'||hash.length>32768)return invalid;
   var raw=hash.replace(/^#/,'').split('&').filter(function(pair){return pair.split('=')[0]==='candidates';});
   if(raw.length!==1||raw[0].slice('candidates='.length).length>16384)return invalid;
   try{
     var params=new URLSearchParams(hash.replace(/^#/,'')),value=JSON.parse(params.get('candidates'));
     if(!keys(value,['v','g','p','rows','t'])||value.v!==1||typeof value.g!=='string'||!/^[0-9]{1,20}$/.test(value.g)||!url(value.p)||typeof value.t!=='boolean'||!Array.isArray(value.rows)||value.rows.length>8)return invalid;
     var seen=new Set(),rows=[];
     for(var row of value.rows){
       if(!keys(row,['u','k','s','e'])||!url(row.u)||!KINDS.has(row.k)||!SCORES.has(row.s)||!Array.isArray(row.e)||!row.e.length||row.e.length>4||new Set(row.e).size!==row.e.length||row.e.some(function(code){return !EVIDENCE.has(code);})||row.k==='source-page'&&row.u!==value.p||seen.has(row.u))return invalid;
       seen.add(row.u);rows.push({url:row.u,kind:row.k,score:row.s,evidence:row.e.slice(),confidence:row.s>=85?'High':row.s>=50?'Medium':'Low'});
     }
     return {ok:true,rows:rows,source:value.p,generation:value.g,truncated:value.t,message:'Browser suggestions only. Format and downloadability are unverified.'};
   }catch(_){return invalid;}
 }
 return Object.freeze({parse:parse,validUrl:url});
});
