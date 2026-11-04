'use strict';
const U=OmniUI,M=ShareQRModel,$=id=>document.getElementById(id);
let current=null,hidden=false,generation=0,active=true,mustReveal=document.hidden,dismissing=null;
window.OMNI_PREVIEW=!window.omnibloomHost;
function clear(){const lost=$('address-controls').contains(document.activeElement);$('code').replaceChildren();$('page-title').textContent='';$('page-url').textContent='';$('page-url').scrollTop=0;$('address-controls').hidden=true;$('private-note').hidden=true;$('toggle').disabled=true;if(lost&&active&&!document.hidden)U.focus($('done'));}
function paint(){const concealed=hidden||mustReveal||document.hidden||!active;$('code').replaceChildren();$('toggle').textContent=concealed?'Show code':'Hide code';$('code-hidden').hidden=!concealed;$('code-hidden').textContent='Code hidden';if(current&&!concealed)OmniQR.render($('code'),current.url);}
function show(value){generation++;dismissing=null;clear();current=null;if(!active)return false;try{current=M.validate(value);$('page-title').textContent=current.title||new URL(current.url).hostname;$('page-url').textContent=current.url;$('address-controls').hidden=false;$('private-note').hidden=!current.private;hidden=mustReveal||document.hidden;$('toggle').disabled=false;paint();U.notify('');if(!document.hidden)U.focus($('toggle'));return true;}catch(e){$('code-hidden').hidden=false;$('code-hidden').textContent='Code unavailable';U.notify(e.message==='URL_TOO_LONG'?'This address is too long for a readable QR code.':'This page does not have a shareable HTTP or HTTPS address.');if(!document.hidden)U.focus($('done'));return false;}}
function toggle(){if(!current||!active||document.hidden)return;hidden=!hidden;mustReveal=hidden;paint();}
$('toggle').onclick=toggle;
function scrollAddress(direction){if(!current||!active)return;const region=$('page-url');region.scrollTop+=direction*Math.max(1,Math.floor(region.clientHeight*.75));U.notify(region.scrollTop<=0?'Start of address.':region.scrollTop+region.clientHeight>=region.scrollHeight-1?'End of address.':'More of the address.');}
$('address-earlier').onclick=()=>scrollAddress(-1);$('address-later').onclick=()=>scrollAddress(1);
async function dismiss(){if(!active||dismissing===generation)return;const token=generation,epoch=current?.navigationEpoch||null;dismissing=token;const owns=()=>active&&token===generation&&epoch===(current?.navigationEpoch||null);try{const result=await U.request('share.dismiss',{navigationEpoch:epoch},()=>({accepted:true}));if(!owns())return;if(result?.accepted!==true)throw Error('NOT_ACCEPTED');generation++;clear();current=null;$('code-hidden').hidden=false;$('code-hidden').textContent='Sharing closed';U.notify('Sharing closed.');U.focus($('done'));}catch(_){if(owns())U.notify('Could not close sharing. Try again.');}finally{if(dismissing===token)dismissing=null;}}
$('done').onclick=dismiss;
window.handlePageController=a=>{if(a==='circle'||a==='b'){dismiss();return true;}if(a==='a')return window.omniPadController('cross');return false;};
async function refresh(){const token=++generation;dismissing=null;clear();current=null;if(!active)return;U.notify('Preparing the current page.');try{const value=await U.request('navigation.current',{},()=>({version:1,navigationEpoch:'demo-page',title:'Original studio journal',url:'https://example.org/journal',private:false}));if(active&&token===generation)show(value);}catch(_){if(active&&token===generation){$('code-hidden').hidden=false;$('code-hidden').textContent='Code unavailable';U.notify('The current page is not available to share.');}}}
window.OmniShareQR=Object.freeze({show,refresh});
window.addEventListener('omnibloom-event',e=>{if(e.detail?.event==='navigation.changed')refresh();});
document.addEventListener('visibilitychange',()=>{if(document.hidden){mustReveal=true;hidden=true;if(current)paint();}});
window.addEventListener('pagehide',()=>{active=false;mustReveal=true;hidden=true;generation++;dismissing=null;clear();current=null;});
window.addEventListener('pageshow',e=>{if(e.persisted){active=true;refresh();}});
if(window.OMNI_PREVIEW){$('preview').hidden=false;$('demo-show').onclick=()=>show({version:1,navigationEpoch:'demo-page',title:'Address preview',url:$('demo-url').value,private:false});}
refresh();
