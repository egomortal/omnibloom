/* SPDX-License-Identifier: GPL-3.0-or-later */
(function(r,f){if(typeof module==='object')module.exports=f();else r.Themes=f()})(this,function(){
 const themes={'silver-blue':{ground:'#070C12',panel:'#0E1821',accent:'#6CCBFF'},'aurora':{ground:'#071410',panel:'#10251C',accent:'#8EE3B1'},'ember':{ground:'#190E0B',panel:'#2B1B15',accent:'#FFC28A'}};
 function normalize(s){s=s&&typeof s==='object'?s:{};return {theme:Object.prototype.hasOwnProperty.call(themes,s.theme)?s.theme:'silver-blue',accent:/^#[0-9a-fA-F]{6}$/.test(s.accent||'')?s.accent:null,motion:s.motion==='reduced'?'reduced':'full'}}
 function apply(doc,s){const v=normalize(s),p=themes[v.theme],root=doc.documentElement;root.style.setProperty('--ob-ground',p.ground);root.style.setProperty('--ob-panel',p.panel);root.style.setProperty('--ob-accent',v.accent||p.accent);root.style.setProperty('--ob-accent-ink',ink(v.accent||p.accent));root.dataset.motion=v.motion;return v}
 function ink(hex){const c=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:Math.pow((x+.055)/1.055,2.4));const l=.2126*c[0]+.7152*c[1]+.0722*c[2];return l>.179?'#000000':'#FFFFFF'}
 function attach(sdk,doc,onError){let alive=true,generation=0;async function refresh(){const n=++generation;try{const s=await sdk.readSettings();if(alive&&n===generation)apply(doc,s)}catch(e){if(alive&&onError)onError(e)}}const stop=sdk.listen(e=>{if(['theme.changed','settings.changed','resync'].includes(e.type))refresh()},onError);refresh();return ()=>{alive=false;stop()}}
 return {themes,normalize,apply,attach,ink};
});
