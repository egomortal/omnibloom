/* SPDX-License-Identifier: GPL-3.0-or-later */
(function(r,f){if(typeof module==='object')module.exports=f();else r.Notices=f()})(this,function(){
 const MAX=50,TTL=7*86400000;
 function normalize(rows,now){if(!Array.isArray(rows))throw Error('Invalid notice list');const seen=new Set();return rows.filter(n=>n&&typeof n.id==='string'&&/^[a-z0-9-]{1,64}$/.test(n.id)&&typeof n.app==='string'&&/^[a-z0-9-]{1,40}$/.test(n.app)&&typeof n.title==='string'&&n.title.length<=100&&typeof n.body==='string'&&n.body.length<=300&&Number.isFinite(n.created)&&n.created<=now&&now-n.created<TTL).sort((a,b)=>b.created-a.created).filter(n=>{if(seen.has(n.id))return false;seen.add(n.id);return true}).slice(0,MAX).map(n=>({id:n.id,app:n.app,title:n.title,body:n.body,created:n.created,read:n.read===true}))}
 function dismiss(rows,id){return rows.filter(n=>n.id!==id)}
 return {normalize,dismiss,MAX,TTL};
});
