'use strict';
const M=ContextMenuModel,U=OmniUI,$=id=>document.getElementById(id);
let context=null,busy=false,generation=0,active=true,origin=null;
window.OMNI_PREVIEW=!window.omnibloomHost;
const usable=e=>e?.tagName!=='BODY'&&e?.tagName!=='HTML'&&e?.isConnected&&!e.disabled&&!e.closest('[hidden],[inert]')&&e.getClientRects().length;
function foreignModal(){return [...document.querySelectorAll('dialog[open],[role=dialog][aria-modal=true]')].some(e=>e!==$('menu')&&e!==$('qr-dialog')&&!e.hidden&&e.getClientRects().length)}
function restoreOrigin(){
 if(usable(origin)){origin.focus();return;}
 const fallback=document.querySelector('#content a[href],#content button:not([hidden])');
 if(usable(fallback))fallback.focus();
 else{const heading=document.querySelector('#content h1');heading.tabIndex=-1;heading.focus();}
}
function hideOwned(restore=true){
 const ownedFocus=$('menu').contains(document.activeElement)||$('qr-dialog').contains(document.activeElement);
 const wasOpen=!$('menu').hidden||!$('qr-dialog').hidden;
 $('menu').hidden=true;$('qr-dialog').hidden=true;if(wasOpen&&!foreignModal())$('content').removeAttribute('inert');
 $('qr-code').replaceChildren();$('qr-url').textContent='';
 if(restore&&wasOpen&&ownedFocus&&!foreignModal())restoreOrigin();
}
function state(value){window.BloomScreenStates?.show('context-menu#root',value,{retain:true,focus:false})}
function invalidate(restore=true){state('full');generation++;context=null;busy=false;hideOwned(restore);$('target').textContent='';$('menu-title').textContent='';$('actions').replaceChildren();}
function show(value){
 if(!active||foreignModal())return false;
 state('full');
 const wasOpen=!$('menu').hidden||!$('qr-dialog').hidden;
 const focusedAction=document.activeElement?.dataset.action;
 const old=context;generation++;const token=generation;context=null;busy=false;
 if(!wasOpen)origin=document.activeElement;
 hideOwned(false);
 try{
  context=M.validate(value);
  $('kind').textContent=context.kind.toUpperCase();$('menu-title').textContent=context.title||'More options';$('target').textContent=context.url;
  $('restriction').textContent=context.protected?'Downloads and saving are unavailable for protected media.':context.url.length>1024?'This address is too long to show as a readable QR code.':'';
  $('status').textContent='';$('actions').replaceChildren();
  for(const a of M.actions(context)){const b=document.createElement('button');b.textContent=a.label;b.dataset.action=a.id;b.disabled=!a.enabled;b.onclick=()=>act(a.id,token);$('actions').append(b)}
  U.modal('menu');
  if(old?.contextId===context.contextId&&old?.navigationEpoch===context.navigationEpoch&&focusedAction){const b=$('actions').querySelector('[data-action="'+focusedAction+'"]');if(usable(b))b.focus();}
  return true;
 }catch(_){$('status').textContent='This target is not available.';restoreOrigin();return false}
}
async function act(action,owner=generation){
 if(!active||owner!==generation||busy||!context)return;
 const current=context,token=generation;
 if(!M.actions(current).some(a=>a.id===action&&a.enabled))return;
 if(action==='qr'){try{OmniQR.render($('qr-code'),current.url);$('qr-url').textContent=current.url;U.close();U.modal('qr-dialog')}catch(_){U.notify('This address cannot be shown as a QR code.')}return;}
 const invoking=document.activeElement,restore=invoking?.dataset.action===action;
 busy=true;for(const b of $('actions').querySelectorAll('button'))b.disabled=true;if(restore)$('close-menu').focus();
 try{
  const call=M.request(current,action),result=await U.request(call.method,call.params,()=>action==='copy'?{copied:true}:action==='save-image'?{status:'saved',fileName:'original-image.png'}:{accepted:true});
  if(!active||token!==generation)return;
  let message;
  if(action==='copy'){if(result?.copied!==true)throw Error('NOT_COPIED');message='Link copied.'}
  else if(action==='save-image'){if(!['saved','cancelled','pending'].includes(result?.status))throw Error('INVALID_RESULT');message={saved:'Image saved to USB.',cancelled:'Save cancelled.',pending:'Choose a destination on USB.'}[result.status]}
  else{if(result?.accepted!==true)throw Error('NOT_ACCEPTED');message=action==='open'?'Opened in a new tab.':'Sent to Downloads.'}
  U.notify(window.OMNI_PREVIEW?'Preview: '+message.toLowerCase():message);
 }catch(_){if(active&&token===generation)U.notify('That action could not be completed. The page may have changed.')}
 finally{
  if(active&&token===generation){busy=false;for(const a of M.actions(current)){const b=$('actions').querySelector('[data-action="'+a.id+'"]');if(b)b.disabled=!a.enabled;}if(restore&&document.activeElement===$('close-menu')&&usable(invoking))invoking.focus();}
 }
}
function close(){
 const last=context;invalidate(true);
 if(last&&window.omnibloomHost)U.request('context.dismiss',{contextId:last.contextId,navigationEpoch:last.navigationEpoch}).catch(()=>{});
}
function back(){if(!active||!context)return;U.close();U.modal('menu');const b=$('actions').querySelector('[data-action="qr"]');if(usable(b))b.focus();}
$('close-menu').onclick=close;$('qr-back').onclick=back;
window.handlePageController=a=>{if(a!=='circle')return false;if(!$('qr-dialog').hidden){back();return true}if(!$('menu').hidden){close();return true}return false};
const demo=(kind,protectedMedia=false)=>({version:1,contextId:'demo-'+kind,navigationEpoch:'demo-page',kind,title:{link:'Original studio journal',image:'Original illustration',video:'Original sample film'}[kind],url:'https://example.org/'+{link:'journal',image:'original-image.png',video:'original-film.mp4'}[kind],protected:protectedMedia,canDownload:true,canSaveImage:kind==='image'});
document.querySelectorAll('[data-kind]').forEach(b=>b.onclick=()=>show(demo(b.dataset.kind)));$('protected-demo').onclick=()=>show(demo('video',true));
async function refresh(){
 if(!active)return;
 const token=++generation;state('loading');
 try{const value=await U.request('context.current',{});if(active&&token===generation){state('full');show(value)}}
 catch(_){if(active&&token===generation){state(foreignModal()?'full':'error');if(foreignModal())return;U.notify('No page target is available.');restoreOrigin();}}
}
window.OmniContextMenu=Object.freeze({show,close});
window.addEventListener('omnibloom-event',e=>{if(e.detail?.event==='navigation.changed')invalidate(true)});
window.addEventListener('pagehide',()=>{active=false;invalidate(false)});
window.addEventListener('pageshow',()=>{if(active)return;active=true;if(!window.OMNI_PREVIEW)refresh()});
if(window.OMNI_PREVIEW)show(demo('link'));else{document.querySelectorAll('[data-kind],#protected-demo').forEach(e=>e.hidden=true);refresh();}
