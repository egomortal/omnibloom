// Omni add-on "Recipe mode": pure logic (no page changes). MIT, Omnibloom contributors.
// Finds a schema.org Recipe that the page itself declares (JSON-LD or microdata) and turns it into plain lists.
// No guessing: a page without that markup has no recipe. Reads only nodeType, nodeValue, localName/tagName,
// childNodes, getAttribute and textContent, so it runs on the live document and on the tests' small parsed trees.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniRecipeCore=value})(globalThis,()=>{'use strict';
const MAX_ELEMENTS=60000,MAX_JSON=1024*1024,MAX_DEPTH=12,MAX_ITEMS=200,MAX_TEXT=2000,MAX_PAGES=150,PREFIX='p:',SCALES=Object.freeze([.5,1,2]);
const tag=n=>n&&n.nodeType===1?String(n.localName||n.tagName||'').toLowerCase():'';
const attr=(n,k)=>{const v=n.getAttribute?n.getAttribute(k):null;return v==null?'':String(v)};
const has=(n,k)=>n.hasAttribute?n.hasAttribute(k):n.getAttribute&&n.getAttribute(k)!=null;
const squash=s=>String(s==null?'':s).replace(/\s+/g,' ').trim();
const cut=(s,max=MAX_TEXT)=>s.length<=max?s:s.slice(0,max-1).trimEnd()+'…';

// ---- Text from JSON-LD strings: sites often put HTML and entities in them ----
const ENT={amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' ',ndash:'–',mdash:'—',hellip:'…',rsquo:'’',lsquo:'‘',rdquo:'”',ldquo:'“',deg:'°',frac12:'½',frac14:'¼',frac34:'¾',frac13:'⅓',frac23:'⅔',times:'×',eacute:'é',egrave:'è',uuml:'ü',ouml:'ö',auml:'ä',ntilde:'ñ',ccedil:'ç'};
function decode(s){return s.replace(/&(#x[0-9a-f]{1,6}|#\d{1,7}|[a-z][a-z0-9]{1,8});/gi,(m,e)=>{if(e[0]==='#'){const c=e[1].toLowerCase()==='x'?parseInt(e.slice(2),16):parseInt(e.slice(1),10);
  return c>0&&c<0x110000&&!(c>=0xd800&&c<0xe000)?String.fromCodePoint(c):m}return ENT[e.toLowerCase()]??m})}
// Lines of plain text: <br>, </p>, </li>, </div> and newlines end a line; other tags vanish.
function lines(value){if(value==null||typeof value==='object')return[];let s=String(value);if(s.length>MAX_JSON)s=s.slice(0,MAX_JSON);
  s=s.replace(/<\s*(script|style)[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi,' ').replace(/<\s*br\s*\/?>|<\s*\/\s*(p|li|div|h[1-6])\s*>/gi,'\n').replace(/<\s*\/?\s*(td|th|tr|ul|ol|table|section|article|blockquote)\b[^>]{0,2000}>/gi,'\n').replace(/<[^>]{0,2000}>/g,'');
  return decode(decode(s)).split(/\r?\n/).map(squash).filter(Boolean)}
const text1=v=>lines(v).join(' ');

// ---- Finding Recipe objects in JSON-LD (@graph, arrays, nesting) ----
const typesOf=o=>{const t=o&&o['@type'];return(Array.isArray(t)?t:[t]).filter(x=>typeof x==='string').map(x=>x.replace(/^(https?:\/\/schema\.org\/|schema:)/i,''))};
const isRecipe=o=>!!o&&typeof o==='object'&&!Array.isArray(o)&&typesOf(o).includes('Recipe');
// Control characters are never valid inside JSON strings, and outside strings they are only whitespace; some sites
// leave raw newlines inside their strings, so they become spaces before a second try. Nothing else is repaired.
function parseJson(src){const s=String(src||'').trim().replace(/^<!--|-->$/g,'').replace(/^\s*\/\*\s*<!\[CDATA\[\s*\*\/|\/\*\s*\]\]>\s*\*\/\s*$/g,'').trim();
  if(!s||s.length>MAX_JSON)return undefined;try{return JSON.parse(s)}catch(_){}try{return JSON.parse(s.replace(/[\u0000-\u001f]+/g,' '))}catch(_){return undefined}}
function collectRecipes(value,out=[],depth=0){if(!value||typeof value!=='object'||depth>MAX_DEPTH||out.length>=8)return out;
  if(Array.isArray(value)){for(const v of value)collectRecipes(v,out,depth+1);return out}
  if(isRecipe(value)){out.push(value);return out}
  for(const k of Object.keys(value))if(k!=='recipeInstructions'&&k!=='recipeIngredient')collectRecipes(value[k],out,depth+1);return out}

// ---- Microdata (itemscope itemtype=".../Recipe") ----
const isRecipeType=t=>/(^|\s)(https?:\/\/)?schema\.org\/Recipe(\s|$)/i.test(t);
function walk(rootNode,visit){const stack=[rootNode];let seen=0;while(stack.length&&seen++<MAX_ELEMENTS){const n=stack.pop();if(visit(n)===false)continue;const k=n.childNodes||[];for(let i=k.length-1;i>=0;i--)if(k[i].nodeType===1||k[i].nodeType===9)stack.push(k[i])}}
function propValue(n){const t=tag(n);if(t==='meta')return attr(n,'content');if(t==='a'||t==='link'||t==='area')return attr(n,'href');
  if(t==='img'||t==='source'||t==='video'||t==='audio'||t==='embed'||t==='iframe')return attr(n,'src');if(t==='time'&&has(n,'datetime'))return attr(n,'datetime');
  if((t==='data'||t==='meter')&&has(n,'value'))return attr(n,'value');if(has(n,'content'))return attr(n,'content');return textOf(n)}
function textOf(n){if(n.nodeType===3)return n.nodeValue||'';if(n.nodeType!==1&&n.nodeType!==9)return'';const t=tag(n);if(t==='script'||t==='style'||t==='template'||t==='noscript')return'';
  if(t==='br')return'\n';let s='';for(const c of n.childNodes||[])s+=textOf(c);return/^(p|li|div|h[1-6]|tr|ol|ul|section)$/.test(t)?'\n'+s+'\n':s}
// An item: {type:[...], props:{name:[values]}}; a value is a string or a nested item.
function item(scope,depth=0){const out={type:attr(scope,'itemtype').split(/\s+/).filter(Boolean).map(x=>x.replace(/^https?:\/\/schema\.org\//i,'')),props:{}};
  walk(scope,n=>{if(n===scope)return true;if(n.nodeType!==1)return false;const p=attr(n,'itemprop').split(/\s+/).filter(Boolean),nested=has(n,'itemscope');
    if(p.length){const v=nested?(depth<6?item(n,depth+1):null):propValue(n);if(v!=null)for(const k of p)(out.props[k]||(out.props[k]=[])).push(nested?v:{el:n,text:v})}
    return!nested});return out}
// Microdata items are reshaped like JSON-LD so one normaliser serves both.
function asJson(it){const o={'@type':it.type};for(const[k,vs]of Object.entries(it.props)){const list=vs.map(v=>v&&v.props?asJson(v):k==='recipeInstructions'?listOrText(v.el,v.text):v.text);o[k]=list.length===1?list[0]:list}return o}
// recipeInstructions on an <ol>/<ul> marks the whole list: each <li> is one step (the markup says so; no guessing).
function listOrText(el,text){const t=tag(el);if(t==='ol'||t==='ul'){const li=(el.childNodes||[]).filter(c=>tag(c)==='li').map(c=>squash(textOf(c))).filter(Boolean);if(li.length)return li}return textOf(el)}

function find(doc){const found=[];if(!doc)return null;const root=doc.documentElement||doc;
  walk(root,n=>{if(n.nodeType!==1)return true;const t=tag(n);
    if(t==='script'){if(/^\s*application\/ld\+json\s*$/i.test(attr(n,'type')))collectRecipes(parseJson((n.childNodes||[]).map(c=>c.nodeValue||'').join('')),found);return false}
    if(has(n,'itemscope')&&isRecipeType(attr(n,'itemtype'))){found.push(asJson(item(n)));return false}
    return true});
  let best=null,score=-1;for(const raw of found){const r=normalize(raw);if(!r)continue;const s=r.ingredients.length+r.steps.length;if(s>score){best=r;score=s}}return best}

// ---- Normalising one Recipe object ----
const first=v=>Array.isArray(v)?v.find(x=>x!=null&&x!==''):v;
function ingredientsOf(raw){let v=raw.recipeIngredient!=null?raw.recipeIngredient:raw.ingredients;if(v==null)return[];if(!Array.isArray(v))v=[v];const out=[];
  for(const x of v){if(out.length>=MAX_ITEMS)break;if(x&&typeof x==='object'){const t=text1(x.name||x.text);if(t)out.push(cut(t))}else for(const l of lines(x))if(out.length<MAX_ITEMS)out.push(cut(l))}return out}
function stepsOf(value,section,out,depth=0){if(value==null||out.length>=MAX_ITEMS||depth>MAX_DEPTH)return out;
  if(Array.isArray(value)){for(const v of value)stepsOf(v,section,out,depth+1);return out}
  if(typeof value!=='object'){for(const l of lines(value))if(out.length<MAX_ITEMS)out.push({text:cut(l),section,tip:false,time:0});return out}
  const types=typesOf(value),list=value.itemListElement!=null?value.itemListElement:value.steps;
  if(types.includes('HowToSection')||(types.includes('ItemList')&&list!=null)||(!types.length&&list!=null&&value.text==null)){
    return stepsOf(list,text1(value.name)||section,out,depth+1)}
  if(types.includes('ListItem')&&value.item!=null&&value.text==null)return stepsOf(value.item,section,out,depth+1);
  let t=text1(value.text);if(!t&&list!=null){const sub=stepsOf(list,section,[],depth+1);t=sub.map(s=>s.text).join(' ')}
  if(!t)t=text1(value.description)||text1(value.name);if(!t)return out;
  out.push({text:cut(t),section,tip:types.includes('HowToTip'),time:duration(first(value.performTime))||duration(first(value.totalTime))||duration(first(value.timeRequired))||0});return out}
function yieldOf(raw){const v=raw.recipeYield!=null?raw.recipeYield:raw.yield;const list=(Array.isArray(v)?v:[v]).filter(x=>x!=null&&typeof x!=='object').map(x=>text1(x)).filter(Boolean);
  if(!list.length)return null;const withWords=list.find(x=>/[a-z]/i.test(x))||list[0],n=list.map(x=>parseNumber(x)).find(x=>x&&x.value>0);
  return{text:cut(withWords,80),count:n?n.value:0}}
function normalize(raw){if(!raw||typeof raw!=='object')return null;const ingredients=ingredientsOf(raw),steps=stepsOf(raw.recipeInstructions,'',[]);
  if(!ingredients.length&&!steps.length)return null;
  for(const s of steps){s.timers=timers(s.text);if(!s.timers.length&&s.time>0)s.timers=[{seconds:s.time,max:s.time,label:clock(s.time),start:-1,end:-1}];delete s.time}
  return{name:cut(text1(first(raw.name)),200),yield:yieldOf(raw),prep:duration(first(raw.prepTime)),cook:duration(first(raw.cookTime)),total:duration(first(raw.totalTime)),ingredients,steps}}

// ---- ISO 8601 durations (PT1H30M, P0DT0H20M, PT0.5H, P1DT2H) ----
function duration(v){if(typeof v!=='string')return 0;const m=/^\s*P(?:(\d+(?:[.,]\d+)?)W)?(?:(\d+(?:[.,]\d+)?)D)?(?:T(?:(\d+(?:[.,]\d+)?)H)?(?:(\d+(?:[.,]\d+)?)M)?(?:(\d+(?:[.,]\d+)?)S)?)?\s*$/i.exec(v);
  if(!m||!/\d/.test(v))return 0;const f=x=>x?parseFloat(x.replace(',','.')):0;const s=Math.round(f(m[1])*604800+f(m[2])*86400+f(m[3])*3600+f(m[4])*60+f(m[5]));return s>0&&s<=7*86400?s:0}
// "1 h 30 min", "45 min", "30 s"
function human(seconds){const s=Math.max(0,Math.round(seconds));if(!s)return'';const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60),r=s%60;
  return[d&&d+' d',h&&h+' h',m&&m+' min',!d&&!h&&r&&r+' s'].filter(Boolean).join(' ')}
// Countdown text: 9:05, 1:02:03
function clock(seconds){const s=Math.max(0,Math.ceil(seconds)),h=Math.floor(s/3600),m=Math.floor(s%3600/60),r=s%60,p=n=>String(n).padStart(2,'0');return h?h+':'+p(m)+':'+p(r):m+':'+p(r)}

// ---- Numbers: 2, 1.5, 1,5, 1/2, ½, 1½, 1 ½, 1 1/2, 1⁄2 ----
const VULGAR={'½':1/2,'⅓':1/3,'⅔':2/3,'¼':1/4,'¾':3/4,'⅕':1/5,'⅖':2/5,'⅗':3/5,'⅘':4/5,'⅙':1/6,'⅚':5/6,'⅛':1/8,'⅜':3/8,'⅝':5/8,'⅞':7/8};
const VG='[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]';
const NUM='(?:\\d+\\s+\\d+\\s*[/⁄]\\s*\\d+|\\d+\\s*'+VG+'|'+VG+'|\\d+\\s*[/⁄]\\s*\\d+|\\d{1,3}(?:,\\d{3})+(?![\\d.])|\\d+(?:\\.\\d+|,\\d{1,2}(?!\\d))?|\\.\\d+)';
function numberValue(s){s=s.trim();let m;
  if((m=/^(\d+)\s+(\d+)\s*[/⁄]\s*(\d+)$/.exec(s)))return+m[3]?+m[1]+m[2]/m[3]:NaN;
  if((m=new RegExp('^(\\d*)\\s*('+VG+')$').exec(s)))return(m[1]?+m[1]:0)+VULGAR[m[2]];
  if((m=/^(\d+)\s*[/⁄]\s*(\d+)$/.exec(s)))return+m[2]?m[1]/m[2]:NaN;
  if(/^\d{1,3}(,\d{3})+$/.test(s))return parseFloat(s.replace(/,/g,''));   // 1,000 is a thousand; 1,5 is one and a half
  return parseFloat(s.replace(',','.'))}
// The first number in a string: {value, start, end}
function parseNumber(s){const m=new RegExp(NUM).exec(String(s));if(!m)return null;const value=numberValue(m[0]);return Number.isFinite(value)?{value,start:m.index,end:m.index+m[0].length}:null}
const GLYPH=[[1/8,'⅛'],[1/4,'¼'],[1/3,'⅓'],[3/8,'⅜'],[1/2,'½'],[5/8,'⅝'],[2/3,'⅔'],[3/4,'¾'],[7/8,'⅞']];
// Kitchen-friendly: whole numbers plain, common fractions as ½ ¼ ⅓ ¾ ⅔ ⅛, anything else to two decimals.
function formatNumber(v){if(!(v>0))return String(v===0?0:v);let whole=Math.floor(v+1e-9),frac=v-whole;if(frac<.02)return String(whole);if(frac>.98)return String(whole+1);
  if(whole<100){for(const[f,g]of GLYPH)if(Math.abs(frac-f)<.02)return(whole?whole:'')+g}return String(Math.round(v*100)/100)}
// Scales the quantity (or range) at the start of an ingredient line; the rest of the line is left alone, so
// "1 (400 g) tin" becomes "2 (400 g) tin". Lines without a leading number are returned as they are.
const LEAD=new RegExp('^(\\s*(?:[-•*·]\\s*)?)('+NUM+')(?:(\\s*(?:-|–|—|to|or)\\s*)('+NUM+'))?');
function scaleIngredient(line,factor){const s=String(line);if(factor===1||!(factor>0))return s;const m=LEAD.exec(s);if(!m)return s;
  const a=numberValue(m[2]);if(!Number.isFinite(a))return s;let out=m[1]+formatNumber(a*factor);
  if(m[4]!==undefined){const b=numberValue(m[4]);if(!Number.isFinite(b))return s;out+=m[3]+formatNumber(b*factor)}
  let rest=s.slice(m[0].length);if(/^\d/.test(rest))rest=' '+rest;return out+rest}

// ---- Step timers: "10 minutes", "10-12 mins", "1 1/2 hours", "1 hour 15 minutes", "30 seconds", "an hour" ----
const WORDS={a:1,an:1,one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,eleven:11,twelve:12,fifteen:15,twenty:20,thirty:30,forty:40,'forty-five':45,sixty:60,ninety:90};
const TNUM='(?:'+NUM+'|forty-five|'+Object.keys(WORDS).filter(w=>w!=='forty-five').join('|')+')';
const UNIT='(hours?|hrs?|minutes?|mins?|seconds?|secs?)';
const TIMER=new RegExp('(^|[^\\w.,/⁄])('+TNUM+')(?:\\s*(?:-|–|—|to|or)\\s*('+TNUM+'))?[\\s-]*'+UNIT+'(?![a-z])','gi');
const unitSeconds=u=>/^h/i.test(u)?3600:/^m/i.test(u)?60:1;
const tval=s=>{const w=WORDS[s.toLowerCase()];return w!==undefined?w:numberValue(s)};
function timers(textValue){const s=String(textValue||''),found=[];TIMER.lastIndex=0;let m;
  while((m=TIMER.exec(s))&&found.length<8){const per=unitSeconds(m[4]),lo=tval(m[2]),hi=m[3]?tval(m[3]):lo;if(!(lo>0)||!Number.isFinite(hi))continue;
    const start=m.index+m[1].length,t={seconds:Math.round(lo*per),max:Math.round(Math.max(lo,hi)*per),label:squash(m[0].slice(m[1].length)),start,end:m.index+m[0].length,per};
    // "1 hour 15 minutes", "1 hour and 15 minutes": one timer
    const prev=found[found.length-1];if(prev&&prev.per>per&&prev.seconds===prev.max&&t.seconds===t.max&&/^\s*(,|and|,\s*and)?\s*$/i.test(s.slice(prev.end,t.start))){
      prev.seconds+=t.seconds;prev.max+=t.max;prev.label=squash(s.slice(prev.start,t.end));prev.end=t.end;prev.per=per;continue}
    found.push(t)}
  return found.filter(t=>t.seconds>=1&&t.seconds<=86400).map(({seconds,max,label,start,end})=>({seconds,max,label,start,end}))}

// ---- Per-page state in the add-on's storage ----
// Query parameters that only track the visitor; dropped so one recipe keeps one key.
const TRACKING=/^(utm_[a-z_]+|fbclid|gclid|dclid|gbraid|wbraid|msclkid|yclid|igshid|mc_cid|mc_eid|_ga|_gl|_hsenc|_hsmi|mkt_tok|ref|ref_src|si|share|spm|cmpid|ncid)$/i;
function pageId(href){let u;try{u=new URL(String(href))}catch(_){return null}if(u.protocol!=='https:'&&u.protocol!=='http:')return null;
  let path=u.pathname.replace(/\/{2,}/g,'/');if(path.length>1)path=path.replace(/\/+$/,'');
  const q=[...u.searchParams].filter(([k])=>!TRACKING.test(k)).sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:a[1]<b[1]?-1:a[1]>b[1]?1:0);
  return u.hostname.toLowerCase().replace(/^www\./,'')+(u.port?':'+u.port:'')+path+(q.length?'?'+q.map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&'):'')}
// Two 32-bit lanes: a short key that does not keep the address itself.
function hash(t){let a=0x811c9dc5,b=0x9e3779b1;for(let i=0;i<t.length;i++){const c=t.charCodeAt(i);a=Math.imul(a^c,16777619);b=Math.imul(b^c,2246822519)^(b>>>13)}return(a>>>0).toString(36)+(b>>>0).toString(36)}
function key(href){const id=pageId(href);return id?PREFIX+hash(id):null}
// Stored: {c:[checked ingredient indexes], n:ingredient count, s:scale, i:step, a:seconds since 1970}
function entry(state,now){const n=state.n|0;return{c:[...state.checked].filter(i=>Number.isInteger(i)&&i>=0&&i<n).sort((x,y)=>x-y),n,s:SCALES.includes(state.scale)?state.scale:1,i:Math.max(0,state.step|0),a:Math.floor(now/1000)}}
// What a stored entry gives back for a recipe with n ingredients and m steps; a changed recipe (other count) drops the ticks.
function restore(saved,n,m){const out={checked:new Set(),scale:1,step:0};if(!saved||typeof saved!=='object'||Array.isArray(saved))return out;
  if(saved.n===n&&Array.isArray(saved.c))for(const i of saved.c)if(Number.isInteger(i)&&i>=0&&i<n)out.checked.add(i);
  if(SCALES.includes(saved.s))out.scale=saved.s;if(Number.isInteger(saved.i)&&saved.i>=0&&saved.i<m)out.step=saved.i;return out}
const validEntry=e=>!!e&&typeof e==='object'&&!Array.isArray(e)&&Array.isArray(e.c)&&typeof e.a==='number'&&Number.isFinite(e.a);
// Keys to drop so at most max pages remain: oldest first (broken entries first of all).
function prune(entries,max=MAX_PAGES){const list=Object.keys(entries).filter(k=>k.startsWith(PREFIX)).map(k=>({k,at:validEntry(entries[k])?entries[k].a:-1}));
  if(list.length<=max)return[];list.sort((x,y)=>x.at-y.at||(x.k<y.k?-1:1));return list.slice(0,list.length-max).map(x=>x.k)}
const nextScale=s=>SCALES[(SCALES.indexOf(s)+1)%SCALES.length];
const scaleLabel=s=>s===.5?'×½':'×'+s;
return Object.freeze({MAX_ITEMS,MAX_PAGES,PREFIX,SCALES,find,normalize,collectRecipes,parseJson,lines,duration,human,clock,parseNumber,formatNumber,scaleIngredient,timers,
  pageId,hash,key,entry,restore,prune,nextScale,scaleLabel})});
