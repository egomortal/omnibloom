/* SPDX-License-Identifier: GPL-3.0-or-later */
(function(root){'use strict';
function url(value){try{const u=new URL(value);if(!['http:','https:'].includes(u.protocol)||u.username||u.password)return null;return u.href;}catch{return null;}}
function rank(query,{tabs=[],tabsRevision=null,bookmarks=[],history=[],remote=[],privateMode=false}={}){
 const needle=String(query).trim().toLocaleLowerCase().slice(0,512),rows=[],seen=new Set();
 for(const [kind,list]of [['tab',tabs],['bookmark',bookmarks],['history',privateMode?[]:history]])for(const item of list.slice(0,2000)){
  if(!item||typeof item.title!=='string'||typeof item.url!=='string')continue;const value=url(item.url);if(!value||seen.has(value))continue;
  const title=item.title.slice(0,120),hay=(title+' '+value).toLocaleLowerCase();if(needle&&!hay.includes(needle))continue;
  if(kind==='tab'&&(!Number.isSafeInteger(tabsRevision)||tabsRevision<0))continue;
  if(kind==='tab'&&(typeof item.id!=='string'||!item.id||item.id.length>128))continue;
  seen.add(value);rows.push({kind,title,url:value,id:kind==='tab'?item.id:undefined,revision:kind==='tab'?tabsRevision:undefined,score:(kind==='tab'?300:kind==='bookmark'?200:100)+(title.toLocaleLowerCase().startsWith(needle)?20:0)});
 }
 rows.sort((a,b)=>b.score-a.score||a.title.localeCompare(b.title));
 if(!privateMode&&needle)for(const text of remote.slice(0,5))if(typeof text==='string'&&text.trim()&&text.length<=200&&!rows.some(r=>r.kind==='search'&&r.query===text))rows.push({kind:'search',title:text,query:text});
 return rows.slice(0,6);
}
function intent(row){if(row.kind==='tab'){if(!Number.isSafeInteger(row.revision)||row.revision<0)throw Error('INVALID_STATE');return{method:'tabs.activate',params:{id:row.id,revision:row.revision}};}if(row.kind==='search')return{method:'search.submit',params:{query:row.query}};const value=url(row.url);if(!value)throw Error('Invalid navigation URL');return{method:'navigation.open',params:{url:value}};}
const api={url,rank,intent};if(typeof module!=='undefined')module.exports=api;else root.OmniAddress=api;
})(globalThis);
