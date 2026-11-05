'use strict';const M=SessionRestoreModel,U=OmniUI,$=id=>document.getElementById(id);let snapshot=null,progress=null,selected=new Set(),busy=false,generation=0,loading=false,receiptKnown=false,snapshotKnown=false,active=true;window.OMNI_PREVIEW=!window.omnibloomHost;const fixture={version:1,id:'demo-session',revision:1,reason:'crash',endedAt:1793577600000,tabs:[{id:'guide',title:'A useful guide',url:'https://example.org/guide',private:false},{id:'studio',title:'Studio journal',url:'https://example.net/studio',private:false},{id:'learning',title:'Learning something new',url:'https://example.com/learn',private:false},{id:'private',title:'Private tab',url:'https://example.org/private',private:true}]};function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}function error(e){return({STORAGE_FULL:'Storage is unavailable. The last saved restore receipt is unchanged.',INVALID_PROGRESS:'The restore receipt could not be read. Check your open tabs.',INVALID_RESULT:'The restore result was incomplete. Check it before trying again.',PENDING_RESTORE:'A previous restore is still awaiting confirmation.'})[e.code||e.message]||'The restore could not be confirmed. Check the result before trying again.'}function draw(){const pending=!!progress?.request;$('pending').hidden=!pending;$('restore').disabled=!snapshot||!selected.size||pending||busy||loading||!receiptKnown;$('dismiss').disabled=pending||busy||loading||!receiptKnown;$('all').disabled=pending||busy||loading||!receiptKnown||!snapshot;$('none').disabled=pending||busy||loading||!receiptKnown||!snapshot;$('check').disabled=busy||!receiptKnown||!pending;$('retry-request').disabled=busy||!receiptKnown||!pending;$('tabs').replaceChildren();if(snapshot){$('heading').textContent=snapshot.reason==='crash'?'Your last session is ready':'Pick up where you left off';$('summary').textContent='Choose the tabs you want to bring back.';for(const tab of snapshot.tabs){const done=progress?.snapshotId===snapshot.id&&progress.completedIds.includes(tab.id),label=el('label','restore-row'+(done?' done':'')),check=el('input');check.type='checkbox';check.dataset.id=tab.id;check.checked=selected.has(tab.id)&&!done;check.disabled=pending||busy||loading||!receiptKnown||done;check.onchange=()=>{if(check.checked)selected.add(tab.id);else selected.delete(tab.id);updateCount()};const copy=el('span');copy.append(el('strong','',tab.title),el('small','',done?'Restored':tab.url==='about:newtab'?'New tab':new URL(tab.url).hostname));label.append(check,copy);$('tabs').append(label)}$('blocked').hidden=!snapshot.blocked;$('blocked').textContent=snapshot.blocked+' entries cannot be restored.';if(!snapshot.tabs.length)$('tabs').append(el('p','empty','No eligible tabs in this session.'))}else{$('heading').textContent=snapshotKnown?'A fresh start':'Pick up where you left off';$('summary').textContent=snapshotKnown?'There is no saved session to restore.':$('failure').hidden?'Choose the tabs you want to bring back.':'The saved session could not be read. It has not been replaced.'}updateCount()}
function updateCount(){$('selected-count').textContent=selected.size+' selected';$('restore').disabled=!snapshot||!selected.size||!!progress?.request||busy||loading||!receiptKnown}$('all').onclick=()=>{if(!active||busy||loading||!receiptKnown||!snapshot||progress?.request)return;selected=new Set(snapshot.tabs.filter(t=>!progress.completedIds.includes(t.id)).map(t=>t.id));draw();U.focus($('all'))};$('none').onclick=()=>{if(!active||busy||loading||!receiptKnown||progress?.request)return;selected.clear();draw();U.focus($('none'))};

function usable(e){return e&&e!==document.body&&e.isConnected&&!e.disabled&&!e.closest('[hidden],[inert]')&&e.getClientRects().length}
function holdFocus(){const e=document.activeElement;if(e&&(e===document.body||$('content').contains(e))&&!e.closest('[role=dialog],dialog')){ $('heading').tabIndex=-1;$('heading').focus();return true}return false}
function recover(held,preferred){if(!active||!held||document.activeElement!==$('heading'))return;const e=preferred|| (progress?.request?$('check'):$('restore').disabled?$('dismiss'):$('restore'));if(usable(e))U.focus(e);}
function accept(result){const done=M.finish(progress,result);progress=M.save(localStorage,done);for(const id of done.completedIds)selected.delete(id);if(snapshot&&done.snapshotId!==snapshot.id){progress=M.fresh(snapshot.id);M.save(localStorage,progress);selected=new Set(snapshot.tabs.map(t=>t.id))}U.notify(result.failed.length?'Some tabs could not be restored. You can select them and try again.':'Selected tabs restored.');}
async function operate(method){
 if(!active||busy||!receiptKnown||!progress?.request)return;
 const request={...progress.request},snapshotId=progress.snapshotId,token=++generation;
 loading=false;busy=true;const held=holdFocus();draw();
 try{
  const result=await U.request(method,method==='sessions.restore'?{snapshotId,revision:request.revision,tabIds:request.tabIds,requestId:request.id}:{requestId:request.id},()=>method==='sessions.restore'?{restoredIds:request.tabIds,failed:[]}:{state:'complete',result:{restoredIds:request.tabIds,failed:[]}});
  if(!active||token!==generation)return;
  if(method==='sessions.restore')accept(result);
  else if(result?.state==='complete')accept(result.result);
  else U.notify(result?.state==='pending'?'Restore is still in progress.':'No receipt was found. Retry uses the same request ID.');
 }catch(e){if(active&&token===generation)U.notify(error(e))}
 finally{busy=false;if(active&&token===generation){draw();recover(held,progress?.request?$('check'):$('dismiss'));}else if(active)load();}
}
$('restore').onclick=async()=>{if(!active||busy||loading||!receiptKnown||!snapshot||progress?.request)return;try{const next=M.begin(snapshot,progress,[...selected],'restore-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10));progress=M.save(localStorage,next);await operate('sessions.restore')}catch(e){U.notify(error(e));draw()}};
$('retry-request').onclick=()=>operate('sessions.restore');$('check').onclick=()=>operate('sessions.restoreStatus');
$('dismiss').onclick=async()=>{if(!active||busy||loading||!receiptKnown||progress?.request)return;busy=true;const token=++generation,held=holdFocus();draw();try{await U.request('sessions.dismiss',{snapshotId:snapshot?.id||null},()=>({accepted:true}));if(active&&token===generation)U.notify(window.OMNI_PREVIEW?'Preview: session kept for later.':'Session kept for later.')}catch(e){if(active&&token===generation)U.notify(error(e))}finally{busy=false;if(active&&token===generation){draw();recover(held,$('dismiss'));}else if(active)load();}};
async function load(){
 if(!active||busy)return;
 const token=++generation,held=holdFocus();loading=true;receiptKnown=false;
 try{progress=M.load(localStorage);receiptKnown=true;}catch(e){progress=null;loading=false;snapshot=null;selected.clear();draw();$('failure').hidden=false;U.notify(error(e));recover(held,$('reload'));return}
 draw();
 try{
  const next=M.prepare(await U.request('sessions.last',{},()=>fixture));
  if(!active||token!==generation)return;
  snapshot=next;snapshotKnown=true;
  if(!progress?.request)progress=snapshot&&progress?.snapshotId===snapshot.id?progress:snapshot?M.fresh(snapshot.id):null;
  selected=new Set(snapshot?snapshot.tabs.filter(t=>!progress?.completedIds.includes(t.id)).map(t=>t.id):[]);
  $('failure').hidden=true;
 }catch(e){if(active&&token===generation){$('failure').hidden=false;U.notify(error(e));}}
 finally{if(active&&token===generation){loading=false;draw();recover(held,progress?.request?$('check'):$('failure').hidden?null:$('reload'));}}
}
$('reload').onclick=load;
window.addEventListener('pagehide',()=>{active=false;generation++;loading=false;});
window.addEventListener('pageshow',()=>{if(active)return;active=true;if(!busy)load();});
load();
