// Omni add-on "Reader view": a compact article finder (original code, Readability-style scoring). MIT, Omnibloom contributors.
// Reads only nodeType, nodeValue, localName/tagName, childNodes, getAttribute (and currentSrc when present), so it
// runs on the live document and on the tests' small parsed trees. It never changes the page.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniReaderCore=value})(globalThis,()=>{'use strict';
const MAX_ELEMENTS=40000,MAX_OUT=6000;
const SKIP=new Set(['script','style','noscript','template','svg','math','canvas','iframe','frame','object','embed','form','button','input','select','textarea','nav','aside','footer','dialog','menu','audio','video','source','track','map','link','meta','head','title']);
const UNLIKELY=/comment|disqus|sidebar|side-bar|footer|masthead|breadcrumb|pagination|pager|social|share|sharing|newsletter|subscribe|signup|sign-up|promo|sponsor|advert|\bads?\b|ad-slot|adslot|banner|popup|modal|cookie|consent|gdpr|related|recommend|trending|most-read|outbrain|taboola|widget|toolbar|skip-link|navbar|menu|header-nav|site-header|login|paywall|tags?-list/i;
const MAYBE=/article|body|column|content|main|post|story|entry|text|prose/i;
const POSITIVE=/article|body|content|entry|main|post|story|text|prose|blog|hentry|h-entry|news-?text|e-content/i;
const NEGATIVE=/comment|sidebar|footer|foot|meta|related|share|social|promo|sponsor|widget|nav|menu|tool|tags?\b|byline-?share|caption-credit|hidden|shopping|subscribe|newsletter|\bads?\b|advert/i;
const BLOCK=new Set(['address','article','aside','blockquote','dd','div','dl','dt','fieldset','figure','footer','form','h1','h2','h3','h4','h5','h6','header','hr','li','main','nav','ol','p','pre','section','table','ul']);
const PARA=new Set(['p','pre','td','blockquote']);
const tag=n=>n&&n.nodeType===1?String(n.localName||n.tagName||'').toLowerCase():'';
const kids=n=>n.childNodes||[];
const attr=(n,k)=>{const v=n.getAttribute?n.getAttribute(k):null;return v==null?'':String(v)};
const squash=s=>String(s).replace(/\s+/g,' ');
function hidden(n){if(n.hasAttribute?n.hasAttribute('hidden'):attr(n,'hidden')!=='')return true;if(attr(n,'aria-hidden')==='true')return true;return/display\s*:\s*none|visibility\s*:\s*hidden/i.test(attr(n,'style'))}
function unlikely(n,t){if(t==='body'||t==='article'||t==='main'||t==='html')return false;const ci=attr(n,'class')+' '+attr(n,'id')+' '+attr(n,'role');if(/^(navigation|complementary|banner|contentinfo|dialog|menu|alert)$/i.test(attr(n,'role')))return true;return UNLIKELY.test(ci)&&!MAYBE.test(ci)}
function textOf(n){if(n.nodeType===3)return n.nodeValue||'';if(n.nodeType!==1||SKIP.has(tag(n)))return'';let s='';for(const c of kids(n))s+=textOf(c);return s}
function findAll(root,pred,limit=50){const out=[],stack=[root];let seen=0;while(stack.length&&out.length<limit&&seen++<MAX_ELEMENTS){const n=stack.pop();if(n.nodeType!==1&&n.nodeType!==9)continue;if(n.nodeType===1&&pred(n))out.push(n);const k=kids(n);for(let i=k.length-1;i>=0;i--)stack.push(k[i])}return out}
// One pass over the body: text length, link text length and commas per element (unlikely parts are left out).
function measure(body){const stats=new Map();let count=0;
function visit(n,inLink){const t=tag(n);if(++count>MAX_ELEMENTS||SKIP.has(t)||hidden(n)||unlikely(n,t))return{len:0,link:0,commas:0,own:0};
const link=inLink||t==='a';let len=0,linkLen=0,commas=0,own=0,blocks=0;
for(const c of kids(n)){if(c.nodeType===3){const s=squash(c.nodeValue||'').trim();if(s){len+=s.length+1;own+=s.length;commas+=(s.match(/[,،、，]/g)||[]).length;if(link)linkLen+=s.length+1}}
else if(c.nodeType===1){const r=visit(c,link);len+=r.len;linkLen+=r.link;commas+=r.commas;if(BLOCK.has(tag(c)))blocks++}}
const st={len,link:linkLen,commas,own,blocks,score:0,scored:false};stats.set(n,st);return st}
visit(body,false);return stats}
function initial(n,t){let s=0;if(t==='div')s=5;else if(t==='article')s=10;else if(t==='main'||t==='section')s=3;else if(t==='pre'||t==='td'||t==='blockquote')s=3;
else if(t==='address'||t==='ol'||t==='ul'||t==='dl'||t==='dd'||t==='dt'||t==='li'||t==='form')s=-3;else if(/^h[1-6]$|^th$/.test(t))s=-5;
const ci=attr(n,'class')+' '+attr(n,'id');if(ci.trim()){if(NEGATIVE.test(ci))s-=25;if(POSITIVE.test(ci))s+=25}if(attr(n,'itemprop')==='articleBody')s+=30;return s}
const density=st=>st&&st.len?st.link/st.len:0;
function isParagraph(n,t,st){return PARA.has(t)||((t==='div'||t==='section')&&st.blocks===0&&st.own>=25)}
// Scores every element; returns the best one with its stats map.
function score(doc){const body=doc.body||findAll(doc,n=>tag(n)==='body',1)[0];if(!body)return null;const stats=measure(body);
const parentOf=n=>{const p=n.parentNode;return p&&p.nodeType===1?p:null};
for(const[n,st]of stats){const t=tag(n);if(!isParagraph(n,t,st)||st.len<25)continue;const points=1+st.commas+Math.min(3,Math.floor(st.len/100));
let a=parentOf(n);for(let level=0;a&&level<3;level++,a=parentOf(a)){const s=stats.get(a);if(!s)break;if(!s.scored){s.scored=true;s.score=initial(a,tag(a))}s.score+=points/(level===0?1:level===1?2:level*3)}}
let best=null,bestScore=0;for(const[n,st]of stats)if(st.scored){st.final=st.score*(1-density(st));if(st.final>bestScore){bestScore=st.final;best=n}}
return best?{best,score:bestScore,stats,body}:null}
// The best element plus siblings that look like part of the same article.
function contentNodes(r){const{best,stats}=r;const parent=best.parentNode;if(!parent||tag(parent)==='html'||parent.nodeType!==1)return[best];
const limit=Math.max(10,r.score*.2),out=[];for(const s of kids(parent)){if(s===best){out.push(s);continue}if(s.nodeType!==1)continue;const st=stats.get(s);if(!st)continue;const t=tag(s);
if(st.scored&&st.final>=limit){out.push(s);continue}
if(t==='p'){const d=density(st);if((st.len>80&&d<.25)||(st.len>0&&st.len<=80&&d===0&&/\.( |$)/.test(squash(textOf(s)))))out.push(s)}}
return out}
function absolute(src,base){try{const u=new URL(src,base||undefined);return/^https?:$/.test(u.protocol)?u.href:''}catch(_){return''}}
function bestFromSrcset(set){let best='',w=-1;for(const part of String(set).split(/,\s+/)){const[url,size]=part.trim().split(/\s+/);const n=parseFloat(size)||1;if(url&&n>w){w=n;best=url}}return best}
function imageSource(n,base){const cur=n.currentSrc&&/^https?:/.test(n.currentSrc)?n.currentSrc:'';
for(const v of[attr(n,'data-src'),attr(n,'data-lazy-src'),attr(n,'data-original'),attr(n,'data-url'),cur,bestFromSrcset(attr(n,'data-srcset')),bestFromSrcset(attr(n,'srcset')),attr(n,'src')]){if(!v||/^data:/i.test(v))continue;const a=absolute(v,base);if(a)return a}return''}
// Clean output: a small tree of {tag, attrs, kids} and strings. Only these tags survive.
const KEEP=new Set(['p','h2','h3','h4','h5','h6','ul','ol','li','blockquote','pre','code','figure','figcaption','em','i','strong','b','sub','sup','br','hr','dl','dt','dd','table','thead','tbody','tr','th','td','caption','a','img']);
function clean(nodes,base,title,stats){let out=0,titleSeen=false;const want=squash(title).trim().toLowerCase();
function walk(n,pre){if(out>MAX_OUT)return[];if(n.nodeType===3){const s=pre?n.nodeValue||'':squash(n.nodeValue||'');return s?[s]:[]}if(n.nodeType!==1)return[];
let t=tag(n);if(SKIP.has(t)||hidden(n))return[];const st=stats.get(n);if(!st&&t!=='img'&&t!=='br'&&t!=='hr')return[];
if(st&&t!=='p'&&t!=='pre'&&t!=='table'&&density(st)>.5&&st.len<300&&/^(div|section|ul|ol|p|span|header)$/.test(t))return[];   // link lists, tag clouds
if(st&&(t==='div'||t==='section'||t==='ul'||t==='ol')){const ci=attr(n,'class')+' '+attr(n,'id');if(NEGATIVE.test(ci)&&!POSITIVE.test(ci)&&st.len<500)return[]}
if(st&&st.len<200&&/\b(byline|author|dateline)\b/i.test(attr(n,'class')+' '+attr(n,'id')+' '+attr(n,'rel')))return[];   // shown once, above the text
if(t==='h1')t='h2';
if(/^h[2-6]$/.test(t)&&!titleSeen&&want&&squash(textOf(n)).trim().toLowerCase()===want){titleSeen=true;return[]}
if(t==='img'){const src=imageSource(n,base);const w=parseInt(attr(n,'width'),10),h=parseInt(attr(n,'height'),10);if(!src||(w&&w<100)||(h&&h<100))return[];out++;return[{tag:'img',attrs:{src,alt:squash(attr(n,'alt')).trim().slice(0,300)},kids:[]}]}
const inner=[];for(const c of kids(n))inner.push(...walk(c,pre||t==='pre'));
if(!KEEP.has(t))return BLOCK.has(t)&&inner.length?[{tag:'div',attrs:{},kids:inner}]:inner;   // containers unwrap; blocks keep their line breaks
if(t==='a'){const href=absolute(attr(n,'href'),base);return href?[{tag:'a',attrs:{href},kids:inner}]:inner}
if(t!=='br'&&t!=='hr'&&!inner.length)return[];out++;return[{tag:t,attrs:{},kids:inner}]}
const result=[];for(const n of nodes)result.push(...walk(n,false));return result}
function meta(doc){const m={};for(const n of findAll(doc,n=>tag(n)==='meta',300)){const k=(attr(n,'property')||attr(n,'name')||attr(n,'itemprop')).toLowerCase(),v=squash(attr(n,'content')).trim();if(k&&v&&!(k in m))m[k]=v}return m}
function docTitle(doc){const t=findAll(doc,n=>tag(n)==='title',1)[0];return t?squash([...kids(t)].map(c=>c.nodeType===3?c.nodeValue||'':'').join('')).trim():''}
function pickTitle(doc,m){const h1s=findAll(doc.body||doc,n=>tag(n)==='h1',3).map(n=>squash(textOf(n)).trim()).filter(Boolean);const og=m['og:title']||m['twitter:title']||'';if(og)return og;if(h1s.length===1)return h1s[0];
const raw=docTitle(doc);const parts=raw.split(/\s+[|\-–—:»·]\s+/);if(parts.length>1){const longest=parts.reduce((a,b)=>b.split(' ').length>a.split(' ').length?b:a);if(longest.split(' ').length>=3)return longest}return raw||h1s[0]||''}
function pickByline(doc,m){const a=m.author||m['article:author']||m['parsely-author']||m['sailthru.author']||'';if(a&&!/^https?:/i.test(a))return a.slice(0,120);
const n=findAll(doc.body||doc,n=>attr(n,'rel')==='author'||attr(n,'itemprop')==='author'||/\b(byline|author)\b/i.test(attr(n,'class')+' '+attr(n,'id')),5).map(n=>squash(textOf(n)).trim()).find(s=>s&&s.length<=120);return n||''}
// Reading time from the clean tree: CJK (Han, kana, Hangul) counts per character at ~400 a minute, other text per word
// at ~230 a minute; code blocks (pre), captions (figcaption, table caption) and images are not read.
const CJK=/[ᄀ-ᇿ⺀-⿟぀-ヿ㄀-ㄯ㄰-㆏ㆠ-ㇿ㐀-䶿一-鿿가-힯豈-﫿ｦ-ﾟ]|[\ud840-\ud87f][\udc00-\udfff]/g;
const NOT_READ=new Set(['pre','figcaption','caption','img']);
const BREAKS=new Set(['p','h2','h3','h4','h5','h6','ul','ol','li','blockquote','div','figure','dl','dt','dd','table','thead','tbody','tr','th','td','br','hr']);
const CJK_PER_MIN=400,WORDS_PER_MIN=230;
function readingTime(input){let text='';
  const walk=items=>{for(const x of items||[]){if(typeof x==='string')text+=x;else if(x&&typeof x==='object'&&!NOT_READ.has(x.tag)){const b=BREAKS.has(x.tag);if(b)text+=' ';walk(x.kids);if(b)text+=' '}}};
  if(typeof input==='string')text=input;else walk(input);
  const chars=(text.match(CJK)||[]).length,words=(text.replace(CJK,' ').match(/\S+/g)||[]).filter(w=>/[\p{L}\p{N}]/u.test(w)).length;
  return{words,chars,minutes:Math.max(1,Math.round(chars/CJK_PER_MIN+words/WORDS_PER_MIN))}}
// extract(document, {base}) -> {title, byline, site, lang, dir, content, length, paragraphs, words, chars, minutes, isArticle} or null.
function extract(doc,opts={}){const r=score(doc);if(!r)return null;const m=meta(doc),title=pickTitle(doc,m),nodes=contentNodes(r);
let length=0,paragraphs=0;for(const n of nodes){const st=r.stats.get(n);if(st)length+=st.len}
for(const n of nodes)for(const p of findAll(n,x=>{const st=r.stats.get(x);return!!st&&tag(x)!=='td'&&isParagraph(x,tag(x),st)&&st.len>=80&&density(st)<.3},2000))paragraphs++;
const content=clean(nodes,opts.base||doc.baseURI||'',title,r.stats);const html=doc.documentElement||findAll(doc,n=>tag(n)==='html',1)[0];
const typed=/article|blog|news/i.test(m['og:type']||'');const isArticle=paragraphs>=3&&length>=(typed?600:900);
const rt=readingTime(content);
return{title,byline:pickByline(doc,m),site:m['og:site_name']||'',lang:html?attr(html,'lang'):'',dir:html?attr(html,'dir'):'',content,length,paragraphs,words:rt.words,chars:rt.chars,minutes:rt.minutes,isArticle,best:r.best,score:r.score}}
return Object.freeze({extract,readingTime,CJK_PER_MIN,WORDS_PER_MIN,score,contentNodes,meta,pickTitle,imageSource,textOf,MAX_ELEMENTS})});
