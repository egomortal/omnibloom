// A tiny, tolerant HTML parser for add-on logic tests (no jsdom). It builds just what the add-on cores read:
// nodeType, nodeValue, localName/tagName, childNodes, parentNode, getAttribute/hasAttribute, textContent.
'use strict';
const VOID=new Set(['area','base','br','col','embed','hr','img','input','link','meta','source','track','wbr']);
const RAW=new Set(['script','style','textarea','title']);
const CLOSES_P=new Set(['address','article','aside','blockquote','div','dl','fieldset','figure','footer','form','h1','h2','h3','h4','h5','h6','header','hr','main','nav','ol','p','pre','section','table','ul']);
const ENT={amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' ',mdash:'—',ndash:'–',hellip:'…',rsquo:'’',lsquo:'‘',rdquo:'”',ldquo:'“'};
const decode=s=>s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi,(m,e)=>e[0]==='#'?String.fromCodePoint(e[1].toLowerCase()==='x'?parseInt(e.slice(2),16):parseInt(e.slice(1),10)):ENT[e.toLowerCase()]??m);
class Node{constructor(type){this.nodeType=type;this.childNodes=[];this.parentNode=null}append(c){c.parentNode=this;this.childNodes.push(c);return c}
get textContent(){if(this.nodeType===3)return this.nodeValue;return this.childNodes.map(c=>c.nodeType===8?'':c.textContent).join('')}}
class Text extends Node{constructor(v){super(3);this.nodeValue=v}}
class Element extends Node{constructor(name,attrs){super(1);this.localName=name;this.tagName=name.toUpperCase();this.attrs=attrs}
getAttribute(k){return this.attrs.has(k)?this.attrs.get(k):null}hasAttribute(k){return this.attrs.has(k)}}
class Document extends Node{constructor(base){super(9);this.baseURI=base}
get documentElement(){return this.childNodes.find(n=>n.localName==='html')||null}
get body(){const h=this.documentElement;return h?h.childNodes.find(n=>n.localName==='body')||null:null}}
function attrs(src){const m=new Map(),re=/([^\s=\/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;let a;while((a=re.exec(src)))m.set(a[1].toLowerCase(),decode(a[2]??a[3]??a[4]??''));return m}
function parse(html,base='https://example.com/'){const doc=new Document(base),root=new Element('html',new Map());doc.append(root);let head=null,body=null;const stack=[root];
const top=()=>stack[stack.length-1];const re=/<!--[\s\S]*?-->|<!doctype[^>]*>|<\/?([a-zA-Z][a-zA-Z0-9-]*)([^>]*)>|[^<]+|</gi;let m;
while((m=re.exec(html))){const tok=m[0];if(tok.startsWith('<!'))continue;
if(!m[1]){top().append(new Text(decode(tok)));continue}const name=m[1].toLowerCase();
if(tok[1]==='/'){const i=stack.map(n=>n.localName).lastIndexOf(name);if(i>0)stack.length=i;continue}
if(name==='html'){for(const[k,v]of attrs(m[2]))root.attrs.set(k,v);continue}
if(name==='head'){head=root.append(new Element('head',attrs(m[2])));stack.length=1;stack.push(head);continue}
if(name==='body'){body=root.append(new Element('body',attrs(m[2])));stack.length=1;stack.push(body);continue}
if(CLOSES_P.has(name)){const i=stack.map(n=>n.localName).lastIndexOf('p');if(i>0)stack.length=i}
if(name==='li'){const i=stack.map(n=>n.localName).lastIndexOf('li');if(i>0&&!stack.slice(i).some(n=>n.localName==='ul'||n.localName==='ol'))stack.length=i}
const el=top().append(new Element(name,attrs(m[2])));
if(RAW.has(name)){const end=html.toLowerCase().indexOf('</'+name,re.lastIndex);const stop=end<0?html.length:end;el.append(new Text(html.slice(re.lastIndex,stop)));re.lastIndex=stop;const gt=html.indexOf('>',stop);re.lastIndex=gt<0?html.length:gt+1;continue}
if(!VOID.has(name)&&!/\/\s*$/.test(m[2]))stack.push(el)}
if(!body){body=new Element('body',new Map());for(const c of root.childNodes.filter(c=>c!==head))body.append(c);root.childNodes=head?[head,body]:[body];body.parentNode=root}
return doc}
module.exports={parse};
