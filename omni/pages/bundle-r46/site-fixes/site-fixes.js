(function(root){'use strict';
const entries=[
 {id:'youtube-focus',origin:'https://www.youtube.com',name:'Clear keyboard focus',selector:'ytd-app a:focus-visible,ytd-app button:focus-visible',css:'outline:3px solid #6ccbff!important;outline-offset:3px!important',fixture:'<ytd-app><button id="target">Open video</button></ytd-app>',focus:true,property:'outlineWidth',expected:'3px'},
 {id:'youtube-search-size',origin:'https://www.youtube.com',name:'Readable search field',selector:'ytd-searchbox input',css:'font-size:22px!important;min-height:44px!important',fixture:'<ytd-searchbox><input id="target" aria-label="Search"></ytd-searchbox>',property:'fontSize',expected:'22px'},
 {id:'wikipedia-table-scroll',origin:'https://en.wikipedia.org',name:'Reach wide article tables',selector:'.mw-parser-output .wikitable',css:'display:block;max-width:100%;overflow-x:auto',tabstop:true,fixture:'<div class="mw-parser-output"><table class="wikitable" id="target"><tbody><tr><td>Wide table</td></tr></tbody></table></div>',property:'overflowX',expected:'auto'},
 {id:'wikipedia-toc-height',origin:'https://en.wikipedia.org',name:'Keep contents within reach',selector:'.vector-toc',css:'max-height:70vh;overflow-y:auto;scroll-margin-top:24px',fixture:'<nav class="vector-toc" id="target">Contents</nav>',property:'overflowY',expected:'auto'},
 {id:'reddit-code-wrap',origin:'https://www.reddit.com',name:'Wrap long post code',selector:'shreddit-post pre',css:'white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%',fixture:'<shreddit-post><pre id="target">const example = "long content";</pre></shreddit-post>',property:'whiteSpace',expected:'pre-wrap'},
 {id:'reddit-focus',origin:'https://www.reddit.com',name:'Clear post-link focus',selector:'shreddit-post a:focus-visible',css:'outline:3px solid #6ccbff!important;outline-offset:3px!important',fixture:'<shreddit-post><a id="target" href="#post">Open post</a></shreddit-post>',focus:true,property:'outlineWidth',expected:'3px'},
 {id:'github-diff-scroll',origin:'https://github.com',name:'Reach wide code panels',selector:'.highlight,.js-diff-table',css:'max-width:100%;overflow-x:auto',tabstop:true,fixture:'<div class="highlight" id="target"><pre>Source code</pre></div>',property:'overflowX',expected:'auto'},
 {id:'github-focus',origin:'https://github.com',name:'Clear repository focus',selector:'main a:focus-visible,main button:focus-visible',css:'outline:3px solid #6ccbff!important;outline-offset:3px!important',fixture:'<main><button id="target">Read repository</button></main>',focus:true,property:'outlineWidth',expected:'3px'},
 {id:'bbc-article-images',origin:'https://www.bbc.com',name:'Fit article images',selector:'article img',css:'max-width:100%;height:auto',fixture:'<article><img id="target" width="2500" height="1200" alt="Example image"></article>',property:'maxWidth',expected:'100%'},
 {id:'bbc-focus',origin:'https://www.bbc.com',name:'Clear article-link focus',selector:'main a:focus-visible',css:'outline:3px solid #6ccbff!important;outline-offset:3px!important',fixture:'<main><a id="target" href="#story">Read story</a></main>',focus:true,property:'outlineWidth',expected:'3px'}
];

const registries=new WeakMap();
const limits=Object.freeze({visited:2000,selectorChecks:20000,matches:100,mutations:100,styles:10});
root.OmniSiteFixes={version:1,entries,limits,install(win,request){
 const reject=reason=>({applied:[],reason,dispose(){}});
 if(!request||request.version!==1||!Array.isArray(request.enabledIds)||request.enabledIds.length>10||typeof request.navigationId!=='string'||!request.navigationId.length||request.navigationId.length>128)return reject('INVALID_REQUEST');
 const doc=win.document;let url;try{url=new URL(win.location.href)}catch{return reject('INVALID_ORIGIN')}
 if(win.top!==win||url.protocol!=='https:'||url.origin!==request.origin)return reject('ORIGIN_OR_FRAME_DENIED');
 if(!doc.head||!doc.documentElement)return reject('DOCUMENT_UNAVAILABLE');
 let registry=registries.get(doc);if(!registry){registry=new Map();registries.set(doc,registry)}
 const owned=[],changes=[],applied=[],results=[],accepted=[];
 const counts={visited:0,selectorChecks:0,matches:0,mutations:0,styles:0};
 for(const id of new Set(request.enabledIds)){
  const entry=entries.find(e=>e.id===id&&e.origin===url.origin);if(!entry)continue;
  if(registry.get(id)?.isConnected){results.push({id,status:'ALREADY_INSTALLED'});continue}
  const style=doc.createElement('style');style.dataset.omniSiteFix=id;style.textContent=entry.selector+'{'+entry.css+'}';doc.head.append(style);owned.push({id,style});registry.set(id,style);counts.styles++;
  let stylesheetAccepted=false;
  try{stylesheetAccepted=!!style.sheet&&style.sheet.cssRules.length>0}catch{}
  const record={id,status:stylesheetAccepted?'STYLESHEET_ACCEPTED_UNVERIFIED':'BLOCKED_OR_UNVERIFIED',sampleMatches:0,verifiedSamples:0};results.push(record);
  if(stylesheetAccepted)accepted.push({entry,record});
 }
 let exhausted=false;
 if(accepted.length){
  const walker=doc.createTreeWalker(doc.documentElement,1);let node=walker.currentNode;
  while(node){
   if(counts.visited>=limits.visited||counts.matches>=limits.matches||counts.selectorChecks>=limits.selectorChecks){exhausted=true;break}
   counts.visited++;
   for(const {entry,record} of accepted){
    if(counts.matches>=limits.matches||counts.selectorChecks>=limits.selectorChecks){exhausted=true;break}
    counts.selectorChecks++;
    if(!node.matches(entry.selector))continue;
    counts.matches++;record.sampleMatches++;
    if(win.getComputedStyle(node)[entry.property]===entry.expected){record.verifiedSamples++;record.status='VERIFIED_SAMPLE';if(!applied.includes(entry.id))applied.push(entry.id)}
    if(entry.tabstop&&!node.hasAttribute('tabindex')&&counts.mutations<limits.mutations){changes.push(node);node.setAttribute('tabindex','0');counts.mutations++}
   }
   if(exhausted)break;
   node=walker.nextNode();
  }
 }
 let disposed=false;
 return{applied,reason:exhausted?'PARTIAL_COVERAGE':applied.length?'VERIFIED_SAMPLE':results.some(r=>r.status==='BLOCKED_OR_UNVERIFIED')?'BLOCKED_OR_UNVERIFIED':accepted.length?'STYLESHEET_ACCEPTED_UNVERIFIED':'NO_MATCH',navigationId:request.navigationId,partialCoverage:exhausted,counts,limits,results,dispose(){if(disposed)return;disposed=true;for(const {id,style} of owned){style.remove();if(registry.get(id)===style)registry.delete(id)}for(const node of changes)if(node.getAttribute('tabindex')==='0')node.removeAttribute('tabindex')}};
}};
})(window);
