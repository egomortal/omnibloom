// Omni add-on "Break reminder": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniBreakCore=value})(globalThis,()=>{'use strict';
const EVERY=Object.freeze({'30':30,'60':60,'90':90,'120':120});
function day(ms){const d=new Date(ms);return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}
// One minute of activity: the page is visible and either a video plays or there was input in the last 2 minutes.
function active(visible,playing,lastInputMs,now){return !!visible&&(!!playing||now-lastInputMs<120e3)}
// The stored counter {day, mins, since} (since = minutes at the last reminder or snooze end). A new day starts at 0.
function tick(st,now,isActive){const d=day(now);let s=st&&st.day===d?{day:d,mins:st.mins|0,since:st.since|0,snooze:Number(st.snooze)||0}:{day:d,mins:0,since:0,snooze:0};
  if(isActive)s.mins++;return s}
// Remind when `every` active minutes passed since the last reminder and no snooze is running.
function due(s,every,now){const e=EVERY[String(every)]||60;return s.mins-s.since>=e&&now>=(s.snooze||0)}
function shown(s){return Object.assign({},s,{since:s.mins})}
function snooze(s,now,mins){return Object.assign({},s,{since:s.mins,snooze:now+mins*60e3})}
function text(mins){const h=Math.floor(mins/60),m=mins%60;return h?(h+(h===1?' hour':' hours')+(m?' '+m+' min':'')):(m+' minutes')}
return Object.freeze({EVERY,day,active,tick,due,shown,snooze,text})});
