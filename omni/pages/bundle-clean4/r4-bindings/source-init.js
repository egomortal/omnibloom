(()=>{'use strict';
const script=document.currentScript,source=script.dataset.source;
document.documentElement.dataset.bloomSource=source;
const configs=BloomScreenConfig.filter(x=>x.source===source&&!x.native),root=configs.find(x=>x.id.endsWith('#root'));
let helpReady=false,legacyInstalled=false;
function classify(value){
 const rows=Array.isArray(value)?value:['items','apps','entries','tabs','notes','jobs','processes','records'].map(k=>value?.[k]).find(Array.isArray);
 return rows&&!rows.length&&root.states.empty.applicable?'empty':'full';
}
function installNativeReadStates(){
 if(legacyInstalled)return false;
 const host=window.omnibloomHost,original=host?.request;
 if(typeof original!=='function')return false;
 if(original.bloomStateOwner===root.id)return true;
 function request(...args){
  const method=args[0]?.method;
  if(!root.readMethods.includes(method)||!document.querySelector(root.selector)||document.documentElement.dataset.bloomSource!==source)return original.apply(this,args);
  const receiver=this;let resolved=false,reply;
  const run=()=>Promise.resolve().then(()=>original.apply(receiver,args)).then(value=>{
   resolved=true;reply=value;
   const code=value?.error?.code||value?.code||'REQUEST_FAILED';
   if(value?.ok!==true)throw Object.assign(Error(code),{code});
   return Object.prototype.hasOwnProperty.call(value,'result')?value.result:value.data;
  });
  return BloomScreenStates.request(root.id,run,classify).then(()=>reply,error=>{
   // UI classification must not rewrite the native envelope contract.
   if(resolved)return reply;
   throw error;
  });
 }
 request.bloomStateOwner=root.id;
 try{host.request=request;return host.request===request}catch(_){return false}
}
function init(installHelp=false){
 if(installHelp&&!helpReady&&!document.querySelector('[data-bloom-help]'))BloomUI.addHelp({title:root?.title||'This screen',container:document.createElement('div')});
 if(installHelp)helpReady=true;
 if(!root||!root.readMethods?.length)return;
 if(installNativeReadStates())return;
 for(const host of[window.OmniUI,window.r2,window]){
  if(!host||typeof host.request!=='function'||host.request.bloomWrapped)continue;
  const original=host.request;
  function request(method,...args){
   if(!root.readMethods.includes(method))return original.call(this,method,...args);
   return BloomScreenStates.request(root.id,()=>original.call(this,method,...args),value=>{
    const rows=Array.isArray(value)?value:['items','apps','entries','tabs','notes','jobs','processes','records'].map(k=>value?.[k]).find(Array.isArray);
    if(rows&&rows.length>500)throw Error('INVALID_ITEMS');
    return classify(value);
   });
  }
  request.bloomWrapped=true;
  try{host.request=request;if(host.request===request)legacyInstalled=true}catch(_){/* Immutable helpers keep their existing request behavior. */}
 }
}
// Native host methods exist before deferred application scripts start their reads.
// Installing here does not create UI until a request has a mounted root.
init();
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>queueMicrotask(()=>init(true)),{once:true});else init(true);
})();
