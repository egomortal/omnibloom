// Omni add-on "Search blocklist": page glue. MIT, Omnibloom contributors.
// On Google / DuckDuckGo / Bing result pages, hides results whose real target (after the engine's redirect link) is a
// blocked domain or one of its subdomains, and says so in one line at the top ("N results hidden" + Show). Each result
// gets a "Block this site" button (a real <button>: D-pad and pointer reach it). The list lives in the add-on's own
// storage (at most 200 domains); private tabs cannot write there, so a block made in one lasts only for that page.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniSearchBlockCore;const eng=core.engine(location);if(!eng)return;
let enabled=false,shown=false,observer=null,timer=0,notice=null,status='';const marked=new Map();   // result block -> {host, button}
let local=null;   // private tab: list kept for this page only
const ATTR='data-omni-addon',THROTTLE_MS=300;
const node=(t,c,text)=>{const e=document.createElement(t);if(c)e.className=c;if(text!=null)e.textContent=text;e.setAttribute(ATTR,api.id);return e};
const list=()=>local||core.parseList(api.storage.get(core.STORAGE_KEY));
const mine=n=>{for(let e=n;e&&e.nodeType===1;e=e.parentNode)if(e.getAttribute&&e.getAttribute(ATTR)!=null)return true;return false};
function save(next){local=null;return Promise.resolve().then(()=>api.storage.set(core.STORAGE_KEY,next)).catch(()=>{local=next;status=' (this page only: private tab)'})}

// ---- Applying the list ----
function apply(){timer=0;if(!enabled)return;const set=new Set(list()),results=core.findResults(document,eng,location.href),seen=new Set(),buttons=api.settings.get('button')!==false;let hidden=0;
  for(const r of results){seen.add(r.node);let m=marked.get(r.node);if(!m){m={host:r.host,button:null};marked.set(r.node,m)}m.host=r.host;
    const by=core.matchOf(r.host,set);if(by)hidden++;
    r.node.classList.toggle('omni-sb-hidden',!!by&&!shown);r.node.classList.toggle('omni-sb-shown',!!by&&shown);
    if(buttons){if(!m.button||m.button.parentNode!==r.node){m.button=node('button','omni-sb-btn');m.button.type='button';m.button.onclick=()=>toggle(r.node);r.node.appendChild(m.button)}
      const site=by||core.siteOf(r.host)||r.host,label=by?'Unblock '+site:'Block this site';
      if(m.button.textContent!==label)m.button.textContent=label;m.button.setAttribute('aria-label',by?'Unblock '+site+' in search results':'Block '+site+' from search results')}
    else if(m.button){m.button.remove();m.button=null}}
  for(const[n,m]of marked)if(!seen.has(n)){n.classList.remove('omni-sb-hidden','omni-sb-shown');if(m.button)m.button.remove();marked.delete(n)}
  paintNotice(hidden,results[0]&&results[0].node)}
function paintNotice(hidden,firstResult){if(!hidden){if(notice){notice.remove();notice=null}shown=false;return}
  if(!notice){notice=node('div','omni-sb-notice');notice.setAttribute('role','status');const text=node('span','omni-sb-count'),b=node('button','omni-sb-btn omni-sb-show');
    b.type='button';b.onclick=()=>{shown=!shown;apply()};notice.append(text,b)}
  const where=firstResult&&firstResult.parentNode;if(where&&(notice.parentNode!==where||notice.nextSibling!==firstResult))where.insertBefore(notice,firstResult);
  const n=hidden===1?'1 result':hidden+' results',t=(shown?n+' from blocked sites shown':n+' hidden')+status;
  const[span,btn]=notice.childNodes;if(span.textContent!==t)span.textContent=t;const bt=shown?'Hide':'Show';if(btn.textContent!==bt)btn.textContent=bt;
  btn.setAttribute('aria-label',shown?'Hide results from blocked sites':'Show hidden results')}
// "Block this site" adds the result's host (without www.); "Unblock" removes the list entry that matched.
function toggle(block){const m=marked.get(block);if(!m)return;const cur=list(),by=core.matchOf(m.host,new Set(cur));let next;
  if(by)next=core.remove(cur,by);else{const r=core.add(cur,core.siteOf(m.host));if(r.full){status=' (list full: 200 sites)';apply();return}next=r.list}
  status='';return save(next).then(()=>{apply();// the blocked result is gone: keep D-pad focus on the line that can show it again
    if(!by&&!shown&&notice)try{notice.childNodes[1].focus({preventScroll:true})}catch(_){}})}

// ---- Results added later (infinite scroll, "more results"): look again, at most every 300 ms ----
function onMutate(records){if(!enabled||timer)return;
  if(records&&records.length&&records.every(r=>mine(r.target)||[...r.addedNodes,...r.removedNodes].every(n=>n.nodeType!==1||mine(n))))return;
  timer=setTimeout(apply,THROTTLE_MS)}
function start(){if(enabled)return;enabled=true;shown=false;apply();
  if(typeof MutationObserver==='function'){observer=new MutationObserver(onMutate);observer.observe(document.body||document.documentElement,{childList:true,subtree:true})}}
function stop(){if(!enabled)return;enabled=false;clearTimeout(timer);timer=0;if(observer){observer.disconnect();observer=null}
  for(const[n,m]of marked){n.classList.remove('omni-sb-hidden','omni-sb-shown');if(m.button)m.button.remove()}marked.clear();if(notice){notice.remove();notice=null}}
api.onEnable(start);api.onDisable(stop);if(api.onSettings)api.onSettings(()=>{if(enabled)apply()});
window.OmniSearchBlockDiagnostics=()=>({enabled,engine:eng,results:marked.size,hidden:[...marked.keys()].filter(n=>n.classList.contains('omni-sb-hidden')).length,shown,blocked:list().length});
if(api.active)start()})();
