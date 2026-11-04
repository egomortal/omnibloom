async function readApps(){
 if(window.omnibloomHost&&typeof window.omnibloomHost.getApps==='function')return await window.omnibloomHost.getApps();
 if(window.omnibloomHost||new URLSearchParams(location.search).get('preview')!=='1')throw Error('Apps unavailable');
 const r=await fetch('mock-apps.json');if(!r.ok)throw Error('Apps unavailable');return r.json();
}
function notify(message){obUI.toast(message)}
async function openApp(id){if(window.omnibloomHost&&typeof window.omnibloomHost.openApp==='function'){try{await window.omnibloomHost.openApp(id);notify('Open request sent.')}catch(e){notify('Could not open this app. Try again.')}}else notify('Preview only. App launch needs the Omni bridge.');}
function safeURL(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?u.href:null}catch(e){return null}}


let apps=[],pageIndex=0;
function focusedApp(){const box=document.getElementById('apps'),active=document.activeElement;return box.contains(active)&&active?.dataset.appId?active.dataset.appId:null}
function renderApps(focusHint=null){const box=document.getElementById('apps'),activeBefore=document.activeElement,focusedId=focusedApp()||(activeBefore===document.body?focusHint:null),wasPaging=['prev-apps','next-apps'].includes(activeBefore?.id);box.replaceChildren();const count=Math.max(1,Math.ceil(apps.length/4));pageIndex=Math.min(pageIndex,count-1);apps.slice(pageIndex*4,pageIndex*4+4).forEach(app=>{const tr=document.createElement('tr');[app.name,app.version||'Unknown',app.verified===false?'Unverified':app.up===true?'Running':app.up===false?'Stopped':'Unknown'].forEach((text,i)=>{const td=document.createElement('td');if(i===2){const badge=document.createElement('span');badge.className='badge '+(app.up?'':'neutral');badge.textContent=text;td.append(badge)}else if(i===0){const name=document.createElement('span');name.textContent=text;const row=document.createElement('span');row.className='app-name';row.append(obAppIcon(app.id),name);td.append(row)}else td.textContent=text;tr.append(td)});const td=document.createElement('td'),b=document.createElement('button');b.textContent='Open';b.dataset.appId=app.id;b.disabled=app.verified===false;b.setAttribute('aria-label',b.textContent+' '+app.name);b.onclick=()=>openApp(app.id);td.append(b);tr.append(td);box.append(tr)});document.getElementById('page-count').textContent=(pageIndex+1)+' of '+count;document.getElementById('prev-apps').disabled=pageIndex===0;document.getElementById('next-apps').disabled=pageIndex===count-1;
 if(focusedId){const target=[...box.querySelectorAll('button')].find(b=>b.dataset.appId===focusedId&&!b.disabled);obUI.focus(target&&target.getClientRects().length?target:document.getElementById('refresh'))}
 else if(wasPaging&&activeBefore.disabled)obUI.focus(document.getElementById('refresh'));
}
async function readStatus(){
 const run=async()=>{
  const data=await readApps(),rows=Array.isArray(data)?data:data&&data.apps;
  if(!Array.isArray(rows)||rows.some(app=>!app||typeof app.id!=='string'||!app.id||typeof app.name!=='string'||!app.name))throw Error('Invalid app response');
  return {apps:rows,focusHint:focusedApp()};
 };
 const states=window.BloomScreenStates,config=states?.config('status#root');
 if(config&&config.source===document.documentElement.dataset.bloomSource)
  return states.request('status#root',run,data=>data.apps.length?'full':'empty');
 return run();
}
let refreshGeneration=0;
async function refresh(){
 const generation=++refreshGeneration,summary=document.getElementById('summary');
 summary.textContent='Refreshing app status…';
 try{
  const data=await readStatus();if(generation!==refreshGeneration)return;
  const rows=Array.isArray(data)?data:data&&data.apps;
  if(!Array.isArray(rows)||rows.some(app=>!app||typeof app.id!=='string'||!app.id||typeof app.name!=='string'||!app.name))throw Error('Invalid app response');
  apps=rows;renderApps(data.focusHint);
  summary.textContent=!apps.length?'No installed apps reported.':window.omnibloomHost?'App status refreshed.':'Development fixture · '+apps.length+' installed apps';
 }catch(e){
  if(generation!==refreshGeneration)return;
  const code=e?.code||e?.message;
  const reason=code==='DENIED'?'App status access was denied.':code==='OFFLINE'?'App status is offline.':code==='Invalid app response'?'App status response was invalid.':code==='Apps unavailable'||code==='HOST_UNAVAILABLE'?'Bloom Core is unavailable.':'App status could not be refreshed.';
  summary.textContent=reason+(apps.length?' Showing previously loaded apps.':' Apps can still start independently.');
 }
}

document.getElementById('prev-apps').onclick=()=>{pageIndex--;renderApps();obUI.focus(document.querySelector('#apps button:not(:disabled)')||document.getElementById('refresh'))};document.getElementById('next-apps').onclick=()=>{pageIndex++;renderApps();obUI.focus(document.querySelector('#apps button:not(:disabled)')||document.getElementById('refresh'))};document.getElementById('refresh').onclick=refresh;refresh();
