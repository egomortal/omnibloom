const $=id=>document.getElementById(id);let flow=null,requestId=null,timer=null,unsubscribe=null;let host=window.omnibloomHost,session=null,disposed=false,subscription=0;
function render(){if(session&&!owns(session)){cancel();return}const focused=document.activeElement,s=flow?.tick();$('guide').textContent=OmniDeviceLogin.providers[$('provider').value].guide;const pending=s?.status==='pending';$('codePanel').hidden=!pending;$('code').textContent=pending?s.userCode:'';$('verification').textContent=pending?s.verificationUri:'';$('remaining').textContent=pending?'Expires in '+Math.ceil(s.remaining/60)+' min':'';$('cancel').disabled=!['requesting','pending'].includes(s?.status);$('start').disabled=['requesting','pending'].includes(s?.status);$('provider').disabled=['requesting','pending'].includes(s?.status);const messages={requesting:'Requesting a code from the provider…',pending:'Enter this code only on the provider address shown above.',approved:'The provider confirmed authorization.',denied:'Authorization was declined. You can request a new code.',expired:'This code expired. Request a new one.',canceled:'Sign-in canceled.',error:'The provider could not complete this request.'};if(s)$('status').textContent=messages[s.status]||'No sign-in code has been requested.';if(!pending&&s?.status!=='requesting'&&timer){clearInterval(timer);timer=null}if(!disposed&&focused?.disabled){($('cancel').disabled?$('start'):$('cancel')).focus()}}
function owns(context){return !disposed&&context===session&&!context.canceled&&context.owner===host&&context.owner.navigationId===context.navigationId}
function cleanup(context,id){
 if(typeof id!=='string'||!/^[-A-Za-z0-9_]{1,128}$/.test(id)||context.cleaned.has(id))return;
 context.cleaned.add(id);
 try{Promise.resolve(context.owner.request({version:1,method:'deviceLogin.cancel',params:{flowId:id,navigationId:context.navigationId}})).catch(()=>{})}catch{}
}
function responseFlowId(context,response){
 const packet=response?.display;
 if(response?.ok===true&&packet?.version===1&&packet.provider===context.provider&&packet.requestId===context.requestId&&packet.navigationId===context.navigationId&&typeof packet.flowId==='string'&&/^[-A-Za-z0-9_]{1,128}$/.test(packet.flowId))return packet.flowId;
}
function cleanupResponse(context,response){cleanup(context,responseFlowId(context,response))}
function receive(packet){if(session&&owns(session)&&flow?.accept(packet)){session.flowId=flow.state.flowId||session.flowId;render()}}
async function start(){
 if(disposed)return;
 cancel();flow?.dispose();
 const navigationId=host?.navigationId;
 if(!host?.request||typeof navigationId!=='string'){$('status').textContent='Open the provider’s sign-in screen to request a code.';return}
 requestId=crypto.randomUUID();
 const context={requestId,navigationId,owner:host,provider:$('provider').value,canceled:false,cleaned:new Set(),flowId:null,timeout:null};session=context;
 flow=OmniDeviceLogin.create(context);render();
 try{
  const begin=Promise.resolve(host.request({version:1,method:'deviceLogin.begin',params:{provider:context.provider,requestId:context.requestId,navigationId}})).then(response=>{
   context.returnedFlowId=responseFlowId(context,response);
   if(!owns(context)){cleanupResponse(context,response);if(session===context)cancel();return null}return response;
  });
  const response=await Promise.race([begin,new Promise((_,reject)=>{context.timeout=setTimeout(()=>reject(Error('timeout')),8000)})]);
  if(!owns(context))return;
  if(!response?.ok||!flow.accept(response.display)){cleanupResponse(context,response);throw Error('invalid response')}
  context.flowId=flow.state.flowId;
  if(timer)clearInterval(timer);timer=setInterval(render,1000);render();
 }catch{
  if(session!==context)return;
  cancel();$('status').textContent='A trusted provider code is unavailable. Try the provider’s sign-in screen.';
 }finally{clearTimeout(context.timeout);context.timeout=null}
}
function cancel(){
 const context=session;session=null;requestId=null;
 if(context){context.canceled=true;clearTimeout(context.timeout);context.timeout=null;cleanup(context,context.flowId||flow?.state.flowId);cleanup(context,context.returnedFlowId)}
 flow?.cancel();if(timer)clearInterval(timer);timer=null;render();
}
$('start').onclick=start;$('cancel').onclick=cancel;$('provider').onchange=()=>{cancel();flow?.dispose();flow=null;render();$('status').textContent='No sign-in code has been requested.'};const subscriptions=new WeakMap();let activeSubscription=null;function detach(){const record=activeSubscription;activeSubscription=null;if(!record)return;try{if(typeof record.cleanup==='function'){record.cleanup();record.registered=false}}catch{}}function subscribe(){detach();const owner=host;if(!owner||typeof owner!=='object'||typeof owner.subscribe!=='function')return;let record=subscriptions.get(owner);if(!record){record={registered:false,generation:0,cleanup:null};subscriptions.set(owner,record)}activeSubscription=record;if(record.registered)return;const generation=++record.generation;try{record.cleanup=owner.subscribe('deviceLogin.update',packet=>{if(activeSubscription===record&&record.generation===generation&&owner===host&&!disposed)receive(packet)});record.registered=true}catch{activeSubscription=null}}subscribe();document.addEventListener('visibilitychange',render);window.addEventListener('pagehide',()=>{disposed=true;cancel();detach();flow=null});window.addEventListener('pageshow',event=>{if(event.persisted&&disposed){host=window.omnibloomHost;disposed=false;subscribe();render();$('status').textContent='No sign-in code has been requested.'}});let ps=true;$('glyphs').onclick=()=>{ps=!ps;$('glyphs').textContent=ps?'PlayStation hints':'Xbox hints';$('hints').textContent=ps?'D-pad · Move / Cross · Select / Circle · Cancel':'D-pad · Move / A · Select / B · Cancel'};
window.omniPadController=window.omniMediaController=function(a){a=({cross:'confirm',a:'confirm',circle:'back',b:'back'})[a]||a;const nodes=[...document.querySelectorAll('button,select')].filter(e=>!e.disabled);const i=nodes.indexOf(document.activeElement),e=document.activeElement;if(['left','right'].includes(a)&&e?.tagName==='SELECT'){e.selectedIndex=Math.max(0,Math.min(e.options.length-1,e.selectedIndex+(a==='left'?-1:1)));e.dispatchEvent(new Event('change'));return true}if(['up','down','left','right'].includes(a)){nodes[(i+(a==='up'||a==='left'?-1:1)+nodes.length)%nodes.length]?.focus();return true}if(a==='confirm'){e?.click();return true}if(a==='back'&&flow){cancel();$('start').focus();return true}return false};document.addEventListener('keydown',e=>{const a={ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right',Escape:'back'}[e.key];if(a&&omniPadController(a))e.preventDefault()});render();
