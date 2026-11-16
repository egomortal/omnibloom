// Omni add-on "Form saver": pure logic (no page side effects). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniFormSaverCore=value})(globalThis,()=>{'use strict';
const PREFIX='omni-form-saver:';            // the page's own localStorage, one key per page (origin + path, hashed)
const MAX_AGE_MS=24*60*60*1000;            // older text is dropped, never offered
const MAX_BYTES=20*1024;                   // per field, UTF-8; longer text is not kept at all
const MAX_FIELDS=50;                       // per page; the oldest go first
const DEBOUNCE_MS=700;
const TEXT_TYPES=Object.freeze(['text','search','email','url']);
// autocomplete tokens that mark secrets (WHATWG HTML autofill): every cc-*, one-time-code and both password kinds.
function blockedAutocomplete(ac){return String(ac||'').toLowerCase().split(/\s+/).some(t=>/^cc-/.test(t)||t==='one-time-code'||t==='current-password'||t==='new-password')}
// Names and ids that say "secret" even without autocomplete.
const SENSITIVE=/(^|[^a-z])(pass(word|wd|code)?|pwd|cvv2?|cvc2?|csc|otp|totp|mfa|2fa|pin|ssn|iban)([^a-z]|$)|card.?(num|no|number)|cc.?(num|no|number)|credit.?card|one.?time|security.?code|verification.?code|auth.?code/i;
const sensitiveName=s=>!!s&&SENSITIVE.test(String(s).replace(/([a-z])([A-Z])/g,'$1_$2'));
// d: {tag, type, autocomplete, name, id, readOnly, disabled, passwordForm, ours}
function eligible(d){if(!d||d.disabled||d.readOnly||d.ours||d.passwordForm)return false;
  if(blockedAutocomplete(d.autocomplete)||sensitiveName(d.name)||sensitiveName(d.id))return false;
  const tag=String(d.tag||'').toLowerCase();if(tag==='textarea')return true;
  if(tag!=='input')return false;const type=String(d.type==null||d.type===''?'text':d.type).toLowerCase().trim();return TEXT_TYPES.includes(type)}
const isEl=n=>!!n&&n.nodeType===1;
const tagOf=el=>String(el&&(el.localName||el.tagName)||'').toLowerCase();
function closestForm(el){for(let e=el&&el.parentNode;isEl(e);e=e.parentNode)if(tagOf(e)==='form')return e;return null}
function hasPassword(form){if(!form)return false;try{if(form.querySelector('input[type=password]'))return true}catch(_){}
  const walk=e=>{for(const c of e.children||[]){if(tagOf(c)==='input'&&String(c.getAttribute('type')||'').toLowerCase()==='password')return true;if(walk(c))return true}return false};return walk(form)}
function describe(el){const g=k=>el.getAttribute?el.getAttribute(k):null;
  let ours=false;for(let e=el;isEl(e);e=e.parentNode)if(e.getAttribute&&e.getAttribute('data-omni-addon')!=null){ours=true;break}
  return{tag:tagOf(el),type:g('type'),autocomplete:g('autocomplete'),name:g('name'),id:g('id'),readOnly:!!el.readOnly||g('readonly')!=null,disabled:!!el.disabled||g('disabled')!=null,
    passwordForm:hasPassword(closestForm(el)),ours}}
// UTF-8 byte length without TextEncoder.
function byteLength(s){s=String(s);let n=0;for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);
  if(c<0x80)n+=1;else if(c<0x800)n+=2;else if(c>=0xd800&&c<0xdc00&&i+1<s.length&&(s.charCodeAt(i+1)&0xfc00)===0xdc00){n+=4;i++}else n+=3}return n}
function hash(text){let a=0x811c9dc5,b=0x9e3779b1;for(let i=0;i<text.length;i++){const c=text.charCodeAt(i);a=Math.imul(a^c,16777619);b=Math.imul(b^c,2246822519)^(b>>>13)}return(a>>>0).toString(36)+(b>>>0).toString(36)}
// Query and hash are left out: the same form after a reload or Back, whatever tracking parameters came along.
function pageKey(loc){return String(loc&&loc.origin||'')+String(loc&&loc.pathname||'/')}
function storageKey(loc){return PREFIX+hash(pageKey(loc))}
// Field key: id, else name (+ its place among same-name fields of that tag), else an XPath-like path from <body>.
const elementChildren=e=>[...(e&&e.children||[])].filter(isEl);
function pathOf(el){const steps=[];for(let e=el;isEl(e)&&e.parentNode&&isEl(e.parentNode)&&tagOf(e)!=='body';e=e.parentNode){
  const t=tagOf(e),same=elementChildren(e.parentNode).filter(c=>tagOf(c)===t);steps.unshift(t+'['+(same.indexOf(e)+1)+']')}return'/'+steps.join('/')}
function allOf(root,pred,out=[]){for(const c of elementChildren(root)){if(pred(c))out.push(c);allOf(c,pred,out)}return out}
function fieldKey(el,body){const id=el.getAttribute('id');if(id)return'i:'+id;const name=el.getAttribute('name'),t=tagOf(el);
  if(name){const same=body?allOf(body,c=>tagOf(c)===t&&c.getAttribute('name')===name):[el];return'n:'+t+':'+name+'#'+Math.max(0,same.indexOf(el))}
  return'x:'+pathOf(el)}
function findField(body,key){if(!body||typeof key!=='string')return null;
  if(key.startsWith('i:')){const id=key.slice(2);return allOf(body,c=>c.getAttribute('id')===id)[0]||null}
  if(key.startsWith('n:')){const m=/^n:([a-z]+):(.*)#(\d+)$/.exec(key);if(!m)return null;return allOf(body,c=>tagOf(c)===m[1]&&c.getAttribute('name')===m[2])[+m[3]]||null}
  if(key.startsWith('x:/')){let e=body;for(const s of key.slice(3).split('/').filter(Boolean)){const m=/^([a-z0-9-]+)\[(\d+)\]$/.exec(s);if(!m)return null;
    e=elementChildren(e).filter(c=>tagOf(c)===m[1])[+m[2]-1];if(!e)return null}return e===body?null:e}
  return null}
const fresh=(at,now)=>typeof at==='number'&&Number.isFinite(at)&&at<=now+60000&&now-at<=MAX_AGE_MS;
const fits=t=>typeof t==='string'&&t.length>0&&byteLength(t)<=MAX_BYTES;
// Stored value: {"f":{fieldKey:[text, savedAtMs]}}. Anything stale, too big or malformed is dropped on read.
function parse(raw,now){let o=null;try{o=JSON.parse(raw)}catch(_){}const f={};
  if(o&&typeof o==='object'&&o.f&&typeof o.f==='object')for(const k of Object.keys(o.f)){const e=o.f[k];if(Array.isArray(e)&&fits(e[0])&&fresh(e[1],now))f[k]=[e[0],e[1]]}
  return{f}}
// Record one field's text; empty or oversize text removes the field. Returns whether the text is kept.
function put(page,key,text,now){if(!fits(text)){delete page.f[key];return false}page.f[key]=[text,now];
  const ks=Object.keys(page.f);if(ks.length>MAX_FIELDS){ks.sort((x,y)=>page.f[x][1]-page.f[y][1]);for(const k of ks.slice(0,ks.length-MAX_FIELDS))delete page.f[k]}
  return key in page.f}
const serialize=page=>Object.keys(page.f).length?JSON.stringify({f:page.f}):null;
// A whole stored page is gone when nothing in it is still fresh (for the sweep of other pages' keys).
const stale=(raw,now)=>serialize(parse(raw,now))===null;
// Fields worth offering: saved text and the field on this page still empty.
function restorable(page,body){const out=[];for(const k of Object.keys(page.f)){const el=findField(body,k);
  if(el&&eligible(describe(el))&&String(el.value||'')==='')out.push({key:k,el,text:page.f[k][0]})}return out}
return Object.freeze({PREFIX,MAX_AGE_MS,MAX_BYTES,MAX_FIELDS,DEBOUNCE_MS,TEXT_TYPES,blockedAutocomplete,sensitiveName,eligible,describe,byteLength,hash,pageKey,storageKey,pathOf,fieldKey,findField,fresh,parse,put,serialize,stale,restorable})});
