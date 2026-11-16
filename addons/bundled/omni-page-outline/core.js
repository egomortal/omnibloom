// Omni add-on "Page outline": pure logic (walks any DOM-like tree; no layout, no globals). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniOutlineCore=value})(globalThis,()=>{'use strict';
const MAX_ENTRIES=300,MAX_TEXT=120,WALK_LIMIT=60000;
// Subtrees never listed: code, metadata, embedded graphics and form widgets (a <select>'s options are not headings).
const SKIP=new Set(['script','style','template','noscript','head','svg','math','iframe','object','canvas','select','textarea','button']);
const LANDMARK_TAGS={main:'main',nav:'nav',article:'article',section:'section'};
const LANDMARK_ROLES={main:'main',navigation:'nav',article:'article',region:'section'};
const DEFAULT_NAME={main:'Main content',nav:'Navigation',article:'Article',section:'Section'};
const attr=(el,k)=>{const v=el.getAttribute?el.getAttribute(k):null;return v==null?null:String(v)};
function clean(text,max=MAX_TEXT){const t=String(text==null?'':text).replace(/[\s ​]+/g,' ').trim();return t.length>max?t.slice(0,max-1).replace(/\s+\S*$/,'')+'…':t}
// Hidden by markup alone (the runtime adds a computed-style check through opts.isHidden).
function hiddenAttr(el){return el.hasAttribute&&(el.hasAttribute('hidden')||el.hasAttribute('inert')||attr(el,'aria-hidden')==='true')||!!(el.hasAttribute&&el.hasAttribute('data-omni-addon'))}
function headingLevel(el){const n=el.localName;if(/^h[1-4]$/.test(n))return +n[1];if(/^h[5-6]$/.test(n))return 0;
if(attr(el,'role')==='heading'){const l=parseInt(attr(el,'aria-level')||'2',10);return l>=1&&l<=4?l:0}return 0}
function landmarkKind(el){const role=attr(el,'role');if(role)return LANDMARK_ROLES[role.trim().toLowerCase()]||null;return LANDMARK_TAGS[el.localName]||null}
function firstHeading(el){const stack=[...el.childNodes].reverse();let n=0;while(stack.length&&n++<400){const c=stack.pop();if(c.nodeType!==1||hiddenAttr(c)||SKIP.has(c.localName))continue;
if(headingLevel(c)||/^h[5-6]$/.test(c.localName))return clean(c.textContent);for(let i=c.childNodes.length-1;i>=0;i--)stack.push(c.childNodes[i])}return ''}
function nameOf(el,byId){const label=clean(attr(el,'aria-label')||'');if(label)return label;const ids=attr(el,'aria-labelledby');
if(ids&&byId){const t=clean(ids.split(/\s+/).map(id=>{const r=byId(id);return r?r.textContent:''}).join(' '));if(t)return t}return clean(attr(el,'title')||'')}
// Document order walk: h1-h4 (and role=heading up to level 4) plus landmarks. Hidden, empty and our own UI are skipped.
// A <section> or role=region only counts when it has an accessible name, as in ARIA. Capped at MAX_ENTRIES.
function collect(root,opts={}){const isHidden=opts.isHidden||(()=>false),byId=opts.byId||null,landmarks=opts.landmarks!==false,max=opts.max||MAX_ENTRIES;
const items=[];let truncated=false,walked=0;if(!root||!root.childNodes)return{items,truncated};
const stack=[];for(let i=root.childNodes.length-1;i>=0;i--)stack.push(root.childNodes[i]);
while(stack.length){const el=stack.pop();if(el.nodeType!==1)continue;if(++walked>WALK_LIMIT){truncated=true;break}
if(SKIP.has(el.localName)||hiddenAttr(el))continue;
const level=headingLevel(el);
if(level){const text=clean(String(el.textContent||'').replace(/^[\s#¶§]+|[\s#¶§]+$/g,''))||nameOf(el,byId);if(text&&!isHidden(el)){if(items.length>=max){truncated=true;break}items.push({kind:'heading',level,depth:level-1,text,el})}continue}
const kind=landmarks?landmarkKind(el):null;
if(kind){const named=nameOf(el,byId);if((kind!=='section'||named)&&!isHidden(el)){if(items.length>=max){truncated=true;break}
items.push({kind:'landmark',landmark:kind,level:0,depth:0,text:named||firstHeading(el)||DEFAULT_NAME[kind],label:DEFAULT_NAME[kind],el})}}
for(let i=el.childNodes.length-1;i>=0;i--)stack.push(el.childNodes[i])}
return{items,truncated}}
// Current section from IntersectionObserver state: states[i] = {band, above}; band = inside the top reading band,
// above = scrolled past it. The current entry is the last one that has reached the band. -1 before the first.
function pickCurrent(states){for(let i=states.length-1;i>=0;i--){const s=states[i];if(s&&(s.band||s.above))return i}return -1}
function step(i,dir,n){if(n<=0)return -1;return Math.max(0,Math.min(n-1,(i<0?0:i)+dir))}
// D-pad up/down arrive as wheel events (Omni scrolls the page with them). One press is a single large delta; the right
// stick sends a stream of small ones, which are summed so it moves at a readable pace.
function wheelSteps(acc,dy){if(Math.abs(dy)>=40)return{steps:Math.sign(dy),acc:0};acc+=dy;if(Math.abs(acc)>=120)return{steps:Math.sign(acc),acc:0};return{steps:0,acc}}
return{MAX_ENTRIES,MAX_TEXT,clean,collect,headingLevel,landmarkKind,pickCurrent,step,wheelSteps}});
