// Omni add-on "YouTube captions on": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniYtCaptionsCore=value})(globalThis,()=>{'use strict';
// The video id of a watch / live / shorts page, or null.
function videoId(href){let u;try{u=new URL(href)}catch(_){return null}if(!/(^|\.)youtube\.com$/.test(u.hostname))return null;
  if(u.pathname==='/watch'){const v=u.searchParams.get('v');return v&&/^[A-Za-z0-9_-]{11}$/.test(v)?v:null}
  const m=/^\/(?:live|shorts)\/([A-Za-z0-9_-]{11})/.exec(u.pathname);return m?m[1]:null}
// Press the CC button? Only when it exists, is visible (YouTube hides it for videos without captions), is off, and this
// video was not handled yet (so a user who turns captions off keeps them off for that video).
function shouldPress(btn,handled,vid){if(!btn||!vid||handled.has(vid))return false;if(btn.hidden||btn.display==='none')return false;
  return String(btn.pressed)==='false'}
return Object.freeze({videoId,shouldPress})});
