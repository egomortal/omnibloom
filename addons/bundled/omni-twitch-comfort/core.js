// Omni add-on "Twitch comfort": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniTwitchCore=value})(globalThis,()=>{'use strict';
// Twitch's own test ids / labels (stable data-a-target attributes). Checked 2026-11-16.
const SEL=Object.freeze({theatre:'button[data-a-target="player-theatre-mode-button"]',
  chatToggle:'button[data-a-target="right-column__toggle-collapse-btn"]',
  claimArea:'.community-points-summary, [data-test-selector="community-points-summary"]'});
const RESERVED=new Set(['directory','settings','subscriptions','inventory','wallet','drops','videos','search','downloads','jobs','p','turbo','prime','friends','messages','payments']);
// A live channel page: /<login> (and /<login>/ only); not /videos, /directory, /settings, clips, VODs.
function isChannel(path){const m=/^\/([A-Za-z0-9_]{3,25})\/?$/.exec(String(path||''));return !!m&&!RESERVED.has(m[1].toLowerCase())}
// Theatre once per channel visit, only when the player is not already in theatre mode (Twitch's label says what a press does).
function wantTheatre(label,already){const l=String(label||'');return !already&&/theat(re|er) mode/i.test(l)&&!/exit/i.test(l)}
// A bonus claim button: its accessible name is exactly "Claim Bonus" (any case).
function isClaim(label){return /^\s*claim bonus\s*$/i.test(String(label||''))}
// At most one claim per 10 s and 60 per hour (a broken page must never turn into a click loop).
function limiter(now,log){const recent=log.filter(t=>now-t<3600e3);
  if(recent.length&&now-recent[recent.length-1]<10e3)return{ok:false,log:recent};
  if(recent.length>=60)return{ok:false,log:recent};recent.push(now);return{ok:true,log:recent}}
return Object.freeze({SEL,isChannel,wantTheatre,isClaim,limiter})});
