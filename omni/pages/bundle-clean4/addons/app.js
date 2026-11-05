// OMNI_ADDONS_V1: the add-ons page. Talks only to window.omnibloomHost.addons (ENGINE-CONTRACT §7);
// without it (opened outside Omni) it shows a safe "unavailable" state.
(function(){'use strict';
const host=window.omnibloomHost&&window.omnibloomHost.addons;
let data=null;
const SITE={'-2':'Not used on this site','-1':'Default','1':'Always on','0':'Always off'};
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function toast(t){if(window.obUI)obUI.toast(t)}
async function call(op,id,a,b){try{const r=await host.call(op,id,a==null?'':String(a),b==null?'':String(b));if(r!=='ok')throw Error(r);await load(true)}catch(e){toast('Could not change that: '+String(e.message||e).replace(/^error: /,''))}}
function settingField(item,s){
  const wrap=el('div','addon-field');wrap.append(el('span',null,s.label));
  if(s.type==='bool'){const b=el('button',null,s.value?'On':'Off');b.setAttribute('aria-pressed',String(!!s.value));b.setAttribute('aria-label',s.label);b.onclick=()=>call('setSetting',item.id,s.key,JSON.stringify(!s.value));wrap.append(b)}
  else if(s.type==='choice'){const sel=el('select');sel.setAttribute('aria-label',s.label);s.choices.forEach((c,i)=>{const o=el('option',null,s.labels[i]||c);o.value=c;if(c===s.value)o.selected=true;sel.append(o)});sel.onchange=()=>call('setSetting',item.id,s.key,JSON.stringify(sel.value));wrap.append(sel)}
  else if(s.type==='range'){const r=el('input');r.type='range';r.min=s.min;r.max=s.max;r.step=s.step;r.value=s.value;r.setAttribute('aria-label',s.label);const v=el('span','addon-value',String(s.value));r.oninput=()=>{v.textContent=r.value};r.onchange=()=>call('setSetting',item.id,s.key,r.value);wrap.append(r,v)}
  else{const t=el('input');t.type='text';t.value=s.value;t.maxLength=1024;t.setAttribute('aria-label',s.label);const b=el('button',null,'Save');b.onclick=()=>call('setSetting',item.id,s.key,JSON.stringify(t.value));wrap.append(t,b)}
  return wrap}
function card(item){
  const c=el('article','card addon');c.dataset.id=item.id;
  const head=el('div','addon-head');head.append(el('h2',null,item.name+(item.dev?' (developer)':'')));if(item.version||item.licence)head.append(el('span','addon-meta',[item.version,item.licence].filter(Boolean).join(' · ')));c.append(head);
  if(item.description)c.append(el('p',null,item.description));
  if(item.error){c.append(el('p','addon-error','Not loaded: '+item.error));return c}
  const row=el('div','addon-row');
  const g=el('button',null,item.on?'On for all sites':'Off for all sites');g.setAttribute('aria-pressed',String(item.on));g.onclick=()=>call('setGlobal',item.id,!item.on);row.append(g);
  const site=el('button',null,data.host?(data.host+': '+SITE[item.site]):'No site open');site.disabled=!data.host||item.site===-2;
  site.onclick=()=>call('setSite',item.id,data.host,{'-1':'on','1':'off','0':'default'}[item.site]);row.append(site);
  const q=el('button',null,data.quick===item.id?'Quick switch':'Use as quick switch');q.setAttribute('aria-pressed',String(data.quick===item.id));q.onclick=()=>call('setQuick',item.id);row.append(q);
  if(item.source){const a=el('a','button','Source');a.href=item.source;row.append(a)}
  c.append(row);
  c.append(el('p','muted',item.privateSafe?'Also runs in private tabs.':'Never runs in private tabs.'));
  if(item.settings.length){const s=el('div','addon-settings');s.append(el('h3',null,'Settings'));item.settings.forEach(x=>s.append(settingField(item,x)));const r=el('button',null,'Reset settings');r.onclick=()=>call('resetSettings',item.id);s.append(r);c.append(s)}
  return c}
async function load(keepFocus){
  const list=document.getElementById('list'),summary=document.getElementById('summary');
  if(!host){summary.textContent='Add-ons are managed by Omni. Open this page from Omni’s Options menu.';document.getElementById('shortcut').disabled=true;return}
  const focusedId=keepFocus&&document.activeElement&&document.activeElement.closest('[data-id]')?document.activeElement.closest('[data-id]').dataset.id:null;
  const focusedText=keepFocus&&document.activeElement?document.activeElement.getAttribute('aria-label')||document.activeElement.textContent:null;
  try{data=await host.list()}catch(e){summary.textContent='Add-ons are unavailable right now.';return}
  list.replaceChildren(...data.items.map(card));
  const on=data.items.filter(i=>!i.error&&(i.on||i.site===1)).length;
  summary.textContent=data.items.length?(data.items.length+' add-ons · '+on+' on'+(data.host?' · this site: '+data.host:'')):'No add-ons installed.';
  const sc=document.getElementById('shortcut');sc.value=data.shortcut||'off';
  if(focusedId&&window.obUI){const box=list.querySelector('[data-id="'+CSS.escape(focusedId)+'"]');const all=box?[...box.querySelectorAll('button,select,input,a')]:[];obUI.focus(all.find(e=>(e.getAttribute('aria-label')||e.textContent)===focusedText)||all[0])}
}
document.getElementById('shortcut').onchange=e=>call('setShortcut','',e.target.value);
load(false);
})();
