// Omni add-on "Same-tab links": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniSameTabCore=value})(globalThis,()=>{'use strict';
// A link to open in this tab instead of a new one: target _blank / _new (or a named target that is not a frame here),
// an http(s) address, not a download, no modifier keys (the user may want a new tab on purpose), and, in "other sites
// only" mode, only links that leave the current site.
function sameSite(a,b){const strip=h=>String(h||'').toLowerCase().replace(/^www\./,'');return strip(a)===strip(b)}
function retarget(link,page,mode,mods){
  if(!link||mods)return false;
  const t=String(link.target||'').toLowerCase();if(!t||t==='_self'||t==='_top'||t==='_parent')return false;
  if(t!=='_blank'&&t!=='_new'&&link.namedFrame)return false;
  if(link.download)return false;
  let u;try{u=new URL(link.href,page)}catch(_){return false}
  if(!/^https?:$/.test(u.protocol))return false;
  if(mode==='other'){let p;try{p=new URL(page)}catch(_){return false}if(sameSite(u.hostname,p.hostname))return false}
  return true}
return Object.freeze({retarget,sameSite})});
