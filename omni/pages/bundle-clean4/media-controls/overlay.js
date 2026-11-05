(()=>{'use strict';
const dialog=document.getElementById('media-overlay'),play=document.getElementById('session-play'),prev=document.getElementById('session-previous'),next=document.getElementById('session-next'),message=document.getElementById('session-status');
let adapter=null,unsubscribe=null,timer=0,opener=null,busy=false,epoch=0,attachment=0,read=0,activeReads=0,last=null;
function invalidate(){epoch++;read++;activeReads=0;clearInterval(timer);timer=0;busy=false;last=null;dialog.setAttribute('aria-busy','false');}
function current(token,owner){return token===epoch&&owner===adapter&&dialog.open;}
function startTimer(){clearInterval(timer);timer=0;if(adapter&&dialog.open)timer=setInterval(()=>{if(!activeReads)refresh()},500);}
async function refresh(){
 if(!adapter||!dialog.open)return;
 const token=epoch,request=++read,owner=adapter;let snapshot;activeReads++;
 try{snapshot=await owner.snapshot()}catch(e){snapshot={available:false,title:'Media controls unavailable',artist:'',actions:[]}}finally{if(token===epoch)activeReads--;}
 if(!current(token,owner)||request!==read)return;
 last=snapshot;
 document.getElementById('session-title').textContent=snapshot.title||'Current media';
 document.getElementById('session-artist').textContent=snapshot.artist||'';
 const actions=new Set(snapshot.actions||[]),action=snapshot.playbackState==='playing'?'pause':'play';
 play.textContent=action==='pause'?'Pause':'Play';play.dataset.action=action;
 play.disabled=!snapshot.available||!actions.has(action);prev.disabled=!actions.has('previoustrack');next.disabled=!actions.has('nexttrack');
 if(document.activeElement?.disabled)document.getElementById('session-close').focus();
}
function attach(value){
 invalidate();attachment++;unsubscribe?.();unsubscribe=null;adapter=value;
 const token=attachment,owner=adapter;
 unsubscribe=owner?.subscribe?.(()=>{if(token===attachment&&owner===adapter&&dialog.open)refresh()})||null;
 startTimer();refresh();
}
async function act(action){
 if(busy||!adapter||!last||!dialog.open)return;
 const token=epoch,owner=adapter,key=last.documentKey;
 busy=true;dialog.setAttribute('aria-busy','true');message.textContent='Applying your action…';
 try{
  await refresh();if(!current(token,owner))return;
  const snapshot=await owner.snapshot();if(!current(token,owner))return;
  if(snapshot.documentKey!==key){message.textContent='The active page changed. Open its controls again.';return;}
  const result=await owner.dispatch(action);if(!current(token,owner))return;
  message.textContent=result?.handled?'':'This control is unavailable on the current page.';
 }catch(e){if(current(token,owner))message.textContent='This action could not be completed.';}
 finally{if(current(token,owner)){busy=false;dialog.setAttribute('aria-busy','false');refresh();}}
}
async function open(){
 if(dialog.open)return;
 invalidate();const token=epoch,owner=adapter;
 opener=document.activeElement;message.textContent='';dialog.showModal();startTimer();
 await refresh();if(!current(token,owner))return;
 (play.disabled?document.getElementById('session-close'):play).focus();
}
function close(){const wasOpen=dialog.open;invalidate();if(wasOpen){dialog.close();opener?.focus();}}
document.getElementById('open-controls').onclick=open;document.getElementById('session-close').onclick=close;
play.onclick=()=>act(play.dataset.action);prev.onclick=()=>act('previoustrack');next.onclick=()=>act('nexttrack');
dialog.addEventListener('cancel',e=>{e.preventDefault();close()});
const previous=window.omniMediaController;
function controller(action){if(dialog.open&&(action==='circle'||action==='b'||action==='back')){close();return true}return previous(action)}
window.omniMediaController=window.omniPadController=controller;
dialog.addEventListener('focusin',()=>{document.querySelectorAll('.pad-focus').forEach(e=>{if(e!==document.activeElement)e.classList.remove('pad-focus')})});
dialog.addEventListener('close',()=>{if(!dialog.open)invalidate()});
window.obMediaOverlay={attach,open,close,refresh};
document.addEventListener('visibilitychange',()=>{if(document.hidden)close()});
window.addEventListener('pagehide',()=>{close();attach(null)});
async function native(method,params={}){if(typeof window.omnibloomHost?.request!=='function')throw Error('UNSUPPORTED');const r=await window.omnibloomHost.request({version:1,id:'media-'+Date.now(),method,params});if(r?.ok!==true)throw Error(r?.code||'UNSUPPORTED');return r.result;}
attach(window.omnibloomHost?{snapshot:()=>native('media.session.snapshot'),dispatch:action=>native('media.session.dispatch',{action})}:window.obFixtureBridge);
})();
