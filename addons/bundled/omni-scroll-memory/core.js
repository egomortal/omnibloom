// Omni add-on "Remember reading position": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniScrollMemCore=value})(globalThis,()=>{'use strict';
const MAX=300,DAYS=30;
// The key for a page: origin + path (no query except a few that name an article, no fragment), hashed so no address
// is stored. Two FNV-1a passes -> 16 hex digits.
const KEEP=/^(id|p|page_id|article|story|post|v|t)$/i;
function fnv(text,seed){let h=seed>>>0;for(let i=0;i<text.length;i++){h^=text.charCodeAt(i);h=Math.imul(h,16777619)>>>0}return('0000000'+h.toString(16)).slice(-8)}
function keyFor(href){let u;try{u=new URL(href)}catch(_){return null}if(!/^https?:$/.test(u.protocol))return null;
  const q=[...u.searchParams].filter(([k])=>KEEP.test(k)).sort().map(([k,v])=>k+'='+v).join('&');
  const text=u.origin.toLowerCase()+u.pathname+(q?'?'+q:'');return 'p'+fnv(text,2166136261)+fnv(text,0x811c9dc5^0x5bd1e995)}
// Worth remembering: a long page (at least 3 screens) scrolled past the first screen and not at the very end.
function worth(y,maxY,winH){return maxY>=winH*2&&y>winH*0.8&&y<maxY-winH*0.3}
// Saved positions are fractions of the page height (layouts reflow); restore to the same fraction.
function fraction(y,maxY){return maxY>0?Math.max(0,Math.min(1,y/maxY)):0}
function restoreY(frac,maxY){return Math.round(Math.max(0,Math.min(1,Number(frac)||0))*Math.max(0,maxY))}
function fresh(entry,now){return!!entry&&typeof entry.f==='number'&&typeof entry.t==='number'&&now-entry.t<DAYS*864e5&&entry.f>0&&entry.f<1}
// Trim a map {key:{f,t}} to the newest MAX.
function trim(map){const keys=Object.keys(map).filter(k=>/^p[0-9a-f]{16}$/.test(k)&&map[k]&&typeof map[k].t==='number');keys.sort((a,b)=>map[b].t-map[a].t);
  const out={};for(const k of keys.slice(0,MAX))out[k]={f:map[k].f,t:map[k].t};return out}
return Object.freeze({MAX,DAYS,keyFor,worth,fraction,restoreY,fresh,trim})});
