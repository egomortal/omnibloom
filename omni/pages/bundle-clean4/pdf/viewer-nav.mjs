// OMNI_PDF_VIEWER_V1: pure page logic of the PDF reader (no DOM): the address the shell opens, the document address,
// and what each controller action does. Tested by stage1/tools/test_pdf_viewer_js.mjs (node).
export const DOC_BASE='omni://pages/_user/pdf/';
const TOKEN=/^[0-9a-f]{32}$/;
function cleanName(n){n=String(n||'').replace(/[\u0000-\u001f\u007f]/g,'').trim();if(n.length>200)n=n.slice(0,200);return n;}
function httpURL(u){if(typeof u!=='string'||!u||u.length>4096)return '';try{const x=new URL(u);if((x.protocol!=='http:'&&x.protocol!=='https:')||x.username||x.password)return '';return x.href;}catch(_){return '';}}
// "?doc=<token>&name=<name>&src=<address>" (the shell's viewer address). Anything invalid is dropped.
export function parseParams(search){
 let p;try{p=new URLSearchParams(String(search||''));}catch(_){p=new URLSearchParams();}
 const doc=p.get('doc')||'';
 return {doc:TOKEN.test(doc)?doc:'',name:cleanName(p.get('name')),src:httpURL(p.get('src')||'')};
}
// Same-origin address the page fetches (relative to omni://pages/pdf/index.html) and the absolute one for pdf.save.
export function docFetchPath(doc){return TOKEN.test(doc)?'../_user/pdf/'+doc+'.pdf':'';}
export function docAddress(doc){return TOKEN.test(doc)?DOC_BASE+doc+'.pdf':'';}
// One controller action -> what to do. s: {hasDoc, dialogOpen, inViewport, page, pages, top, maxTop, left, maxLeft, viewH, viewW}
// Results: {kind:'base'} (the shared controller: focus moves, dialogs, Circle = back), {kind:'none'} (used, nothing to do),
// {kind:'scroll',dx,dy}, {kind:'page',delta,edge:'top'|'bottom'}, {kind:'zoom',delta}, {kind:'save'}, {kind:'ignore'} (false: Omni's own).
export const ZOOM_STEP=.25;
export function decide(action,s){
 const a=String(action||'').toLowerCase();
 if(s.dialogOpen)return {kind:'base'};
 if(a==='square')return s.hasDoc?{kind:'save'}:{kind:'ignore'};
 if(a==='r2'||a==='l2')return s.hasDoc?{kind:'zoom',delta:a==='r2'?ZOOM_STEP:-ZOOM_STEP}:{kind:'ignore'};
 if(a==='l1'||a==='r1'){
  if(!s.hasDoc)return {kind:'base'};
  const d=a==='l1'?-1:1,n=s.page+d;
  return n>=1&&n<=s.pages?{kind:'page',delta:d,edge:'top'}:{kind:'none'};
 }
 if(!s.hasDoc||!s.inViewport)return {kind:'base'};
 const stepY=Math.max(40,Math.round((s.viewH||0)*.25)),stepX=Math.max(40,Math.round((s.viewW||0)*.25));
 if(a==='down'){if(s.top<s.maxTop-1)return {kind:'scroll',dx:0,dy:stepY};return s.page<s.pages?{kind:'page',delta:1,edge:'top'}:{kind:'none'};}
 if(a==='up'){if(s.top>0)return {kind:'scroll',dx:0,dy:-stepY};return s.page>1?{kind:'page',delta:-1,edge:'bottom'}:{kind:'base'};}
 if(a==='left'||a==='right'){
  const d=a==='left'?-1:1;
  if(s.maxLeft>0&&(d<0?s.left>0:s.left<s.maxLeft-1))return {kind:'scroll',dx:d*stepX,dy:0};
  const n=s.page+d;return n>=1&&n<=s.pages?{kind:'page',delta:d,edge:'top'}:{kind:'none'};
 }
 return {kind:'base'};
}
