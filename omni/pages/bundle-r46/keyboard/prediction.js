/* SPDX-License-Identifier: GPL-3.0-or-later */
(function(root){
 'use strict';
 const fold=(v,locale)=>v.normalize('NFC').toLocaleLowerCase(locale);
 function safeURL(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
 function candidates({value='',cursor=value.length,locale='en',mode='text',privateField=false,history=[],recentURLs=[]},dictionary){
  if(privateField||mode==='password')return [];
  const left=value.slice(0,cursor),prefix=left.split(/\s/u).pop(),key=fold(prefix,locale),seen=new Set(),rows=[];
  const add=(text,kind,start,end)=>{const id=fold(text,locale);if(!seen.has(id)&&text.length<=4096){seen.add(id);rows.push({text,kind,start,end});}};
  if(mode==='url'&&left.trim())for(const raw of recentURLs.slice(0,100)){if(typeof raw!=='string')continue;const url=safeURL(raw);if(url&&fold(url.replace(/^https?:\/\//,''),locale).startsWith(fold(left.replace(/^https?:\/\//,''),locale)))add(url,'url',0,value.length);}
  if(left.trim())for(const text of history.slice(0,100))if(typeof text==='string'&&fold(text,locale).startsWith(fold(left,locale)))add(text,'history',0,value.length);
  if(key)for(const text of dictionary[locale]||dictionary.en||[])if(fold(text,locale).startsWith(key)&&fold(text,locale)!==key)add(text,'word',left.length-prefix.length,cursor);
  return rows.slice(0,3);
 }
 function apply(value,candidate,maxLength=2048){const next=value.slice(0,candidate.start)+candidate.text+value.slice(candidate.end);if(next.length>maxLength)return null;return{value:next,cursor:candidate.start+candidate.text.length};}
 function queue(entries,now=Date.now()){
  if(!Array.isArray(entries))return [];
  const seen=new Set();return entries.slice(0,20).filter(x=>x&&typeof x.id==='string'&&/^[\w-]{1,80}$/.test(x.id)&&typeof x.text==='string'&&x.text.length>0&&x.text.length<=4096&&Number.isFinite(x.expiresAt)&&x.expiresAt>now&&x.expiresAt<=now+86400000&&!seen.has(x.id)&&seen.add(x.id)).map(x=>({id:x.id,text:x.text,label:typeof x.label==='string'?x.label.slice(0,100):'Received text',expiresAt:x.expiresAt}));
 }
 const api={safeURL,candidates,apply,queue};if(typeof module!=='undefined')module.exports=api;else root.OmniPrediction=api;
})(globalThis);
