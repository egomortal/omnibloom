(()=>{'use strict';
let current=null,pending=null,lifecycle=0,pageActive=true;
const $=x=>document.getElementById(x),active=()=>pageActive&&!document.hidden;
const owns=request=>active()&&pending===request&&request.lifecycle===lifecycle;
function render(){const busy=!!pending,ok=HDR.eligible(current);$('badge').textContent=current?HDR.badge(current):'Output unknown';$('availability').textContent=ok?'HDR can be requested in this fullscreen session.':'HDR is unavailable for this playback session.';$('source').textContent=current?.source==='pq-bt2020'?'PQ / BT.2020':'Not confirmed';$('display').textContent=current?.display?'Available':'Not confirmed';$('mode').disabled=!active()||!current||busy;$('mode').options[1].disabled=!ok;if(!ok)$('mode').value='sdr';for(const o of $('tone').options)o.disabled=!current?.toneModes.includes(o.value);const first=[...$('tone').options].find(o=>!o.disabled);if(first&&!current?.toneModes.includes($('tone').value))$('tone').value=first.value;$('tone').disabled=!active()||!first||busy;$('apply').disabled=!active()||!current||!first||busy;$('refresh').disabled=!active();$('refresh').setAttribute('aria-busy',String(busy));$('toneInfo').textContent=first?'Choose how supported SDR conversion treats bright areas.':'Tone controls need support from the video engine.'}
function begin(){const request={lifecycle};pending=request;return request}
function finish(request){if(owns(request)){pending=null;render()}}
function invalidate(){lifecycle++;pending=null;current=null;$('result').textContent='';OmniUI.notify('Refresh playback to check this session.');render()}
$('refresh').onclick=async()=>{if(pending||!active())return;const request=begin();current=null;$('result').textContent='';render();try{const value=HDR.state(await OmniUI.request('video.hdr.state',{}));if(!owns(request))return;if(!value)throw Error('INVALID');current=value;OmniUI.notify('Playback state updated.')}catch(_){if(owns(request))OmniUI.notify('Playback state unavailable.')}finally{finish(request)}};
$('apply').onclick=async()=>{if(pending||!current||!active())return;const request=begin();render();try{const requested=HDR.request(current,$('mode').value,$('tone').value),reply=await OmniUI.request('video.hdr.preference',requested);if(!owns(request))return;if(reply?.session!==requested.session||reply?.accepted!==true)throw Error('STALE');$('result').textContent='Preference accepted. Refresh to confirm actual output.'}catch(_){if(owns(request)){current=null;$('result').textContent='Preference not confirmed. Refresh before trying again.'}}finally{finish(request)}};
for(const id of ['mode','tone'])$(id).onchange=()=>{$('result').textContent=''};
document.addEventListener('visibilitychange',()=>{if(document.hidden)invalidate();else render()});
addEventListener('pagehide',()=>{pageActive=false;invalidate()});
addEventListener('pageshow',()=>{pageActive=true;render()});
render();
})();
