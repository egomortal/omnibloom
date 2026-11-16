import {parseParams,docFetchPath,docAddress,decide} from './viewer-nav.mjs'; // OMNI_PDF_VIEWER_V1
const openParams=parseParams(location.search); // OMNI_PDF_VIEWER_V1: ?doc=<token>&name=..&src=.. (a PDF Omni opened here)
let pdfjs=null,pdfLibraryPromise=null;
async function ensurePDFJS(){
 if(!pdfLibraryPromise)pdfLibraryPromise=import('./vendor/pdfjs/pdf.mjs').then(module=>{module.GlobalWorkerOptions.workerSrc=new URL('./vendor/pdfjs/pdf.worker.mjs',import.meta.url).href;pdfjs=module;return module}).catch(error=>{pdfLibraryPromise=null;throw error});
 return pdfLibraryPromise;
}
const canvas=document.getElementById('pdf-canvas'),viewport=document.getElementById('viewport'),status=document.getElementById('pdf-status');
const MAX_FILE=50*1024*1024,MAX_PIXELS=4000000;
let documentPDF=null,pageNumber=1,zoom=1,renderTask=null,loadingTask=null,generation=0,requested=0,lastPageText='',active=true,disposalTail=Promise.resolve(),disposalFailure=false;
const disposedOwners=new WeakSet();
const notify=t=>status.textContent=t;
const owns=token=>active&&token===generation;
function cancel(task){try{task?.cancel()}catch(_){}}
function queueDispose(task,doc){
 const owner=task||doc;
 if(owner&&!disposedOwners.has(owner)){
  disposedOwners.add(owner);
  disposalTail=disposalTail.then(()=>owner.destroy()).catch(()=>{disposalFailure=true;});
 }
 return disposalTail;
}
function controls(){
 document.getElementById('previous').disabled=!documentPDF||pageNumber<=1;
 document.getElementById('next').disabled=!documentPDF||pageNumber>=documentPDF.numPages;
 document.getElementById('text-open').disabled=!documentPDF;
 document.getElementById('page-label').textContent=documentPDF?'Page '+pageNumber+' of '+documentPDF.numPages:'No document';
 document.getElementById('zoom-label').textContent=Math.round(zoom*100)+'%';
}
function clearDocumentUI(){
 pageNumber=1;zoom=1;lastPageText='';canvas.width=canvas.height=1;
 canvas.removeAttribute('aria-label');document.getElementById('page-text').textContent='';controls();
}
async function render(edge){
 if(!active||!documentPDF)return;
 const keepX=viewport.scrollWidth>viewport.clientWidth?(viewport.scrollLeft+viewport.clientWidth/2)/viewport.scrollWidth:.5,keepY=viewport.scrollHeight>viewport.clientHeight?(viewport.scrollTop+viewport.clientHeight/2)/viewport.scrollHeight:0;
 const token=++requested,epoch=generation,doc=documentPDF,current=pageNumber;
 const currentRender=()=>owns(epoch)&&token===requested&&doc===documentPDF;
 const previous=renderTask;renderTask=null;cancel(previous);
 if(previous){try{await previous.promise}catch(_){}if(!currentRender())return;}
 const page=await doc.getPage(current);if(!currentRender())return;
 const natural=page.getViewport({scale:1}),padding=innerWidth>=3000?64:32;
 const fit=Math.min((viewport.clientWidth-padding)/natural.width,(viewport.clientHeight-padding)/natural.height);
 const scale=Math.min(fit*zoom,Math.sqrt(MAX_PIXELS/(natural.width*natural.height)));zoom=scale/fit;
 const box=page.getViewport({scale});canvas.width=Math.max(1,Math.floor(box.width));canvas.height=Math.max(1,Math.floor(box.height));
 notify('Rendering page '+current+'…');
 const task=page.render({canvasContext:canvas.getContext('2d',{alpha:false}),viewport:box,background:'rgb(255,255,255)'});renderTask=task;
 try{await task.promise}catch(e){if(e.name==='RenderingCancelledException'||!currentRender())return;throw e}finally{if(renderTask===task)renderTask=null;}
 if(!currentRender())return;
 const text=await page.getTextContent();if(!currentRender())return;
 lastPageText=text.items.map(i=>i.str+(i.hasEOL?'\n':' ')).join('');
 document.getElementById('page-text').textContent=lastPageText||'This page has no extractable text.';
 canvas.setAttribute('aria-label','PDF page '+current+' of '+doc.numPages);
 if(edge==='keep'){viewport.scrollLeft=Math.max(0,keepX*viewport.scrollWidth-viewport.clientWidth/2);viewport.scrollTop=Math.max(0,keepY*viewport.scrollHeight-viewport.clientHeight/2);} // OMNI_PDF_VIEWER_V1: zoom keeps the view centre
 else{viewport.scrollLeft=0;viewport.scrollTop=edge==='bottom'?viewport.scrollHeight:0;} // OMNI_PDF_VIEWER_V1: up at the top shows the previous page's end
 controls();notify('Page '+current+' ready.');
 if(document.activeElement===document.body||document.activeElement?.disabled)obUI.focus(viewport);
 page.cleanup();
}
async function openBytes(bytes){
 if(!active)return;
 if(!(bytes instanceof Uint8Array))bytes=new Uint8Array(bytes);
 if(bytes.byteLength>MAX_FILE)throw Error('PDF exceeds the 50 MiB viewer limit.');
 const token=++generation;requested++;
 const previousRender=renderTask,previousLoad=loadingTask,previousDoc=documentPDF;
 renderTask=null;loadingTask=null;documentPDF=null;cancel(previousRender);clearDocumentUI();notify('Opening PDF…');
 const previousDisposal=queueDispose(previousLoad,previousDoc);
 try{
  if(previousRender){try{await previousRender.promise}catch(_){}}
  await previousDisposal;if(!owns(token))return;
  if(disposalFailure)throw Error('The previous PDF could not be closed. Reload the viewer before opening another document.');
  await ensurePDFJS();if(!owns(token))return;
  const task=pdfjs.getDocument({data:bytes,maxImageSize:8000000,canvasMaxAreaInBytes:16000000,isEvalSupported:false,useWasm:false,disableFontFace:true,useSystemFonts:true,isOffscreenCanvasSupported:false,isImageDecoderSupported:false,cMapUrl:new URL('./vendor/pdfjs/cmaps/',import.meta.url).href,cMapPacked:true,stopAtErrors:true,disableAutoFetch:true});
  loadingTask=task;let passwordBlocked=false;
  task.onPassword=()=>{if(!owns(token)||loadingTask!==task)return;passwordBlocked=true;notify('Password-protected PDF: unlock a copy in a trusted PDF tool first.');void queueDispose(task,null);};
  try{
   const doc=await task.promise;
   if(!owns(token)){await queueDispose(task,doc);return;}
   documentPDF=doc;await render();if(!owns(token))return;
  }catch(e){
   if(owns(token)){documentPDF=null;if(loadingTask===task)loadingTask=null;controls();notify(passwordBlocked?'Password-protected PDF: unlock a copy in a trusted PDF tool first.':'Could not open this PDF. '+String(e.message||e).slice(0,160));void queueDispose(task,null);}
  }
 }catch(e){if(owns(token)){documentPDF=null;controls();notify('Could not open this PDF. '+String(e.message||e).slice(0,160));}}
}
async function page(delta,edge){if(!active||!documentPDF)return false;const next=Math.max(1,Math.min(documentPDF.numPages,pageNumber+delta));if(next===pageNumber)return true;pageNumber=next;await render(edge);return true;}
async function changeZoom(delta){if(!active||!documentPDF)return false;zoom=Math.max(.5,Math.min(3,zoom+delta));await render('keep');return true;}
function report(promise){const epoch=generation;Promise.resolve(promise).catch(e=>{if(owns(epoch))notify('PDF rendering failed. '+String(e.message||e).slice(0,160));});}
document.getElementById('previous').onclick=()=>report(page(-1));document.getElementById('next').onclick=()=>report(page(1));
document.getElementById('zoom-out').onclick=()=>report(changeZoom(-.25));document.getElementById('zoom-in').onclick=()=>report(changeZoom(.25));
document.getElementById('fit').onclick=()=>{zoom=1;report(render());};document.getElementById('text-open').onclick=()=>obUI.openDialog('text-dialog');
document.getElementById('pdf-file').onchange=async e=>{
 const file=e.target.files[0];if(!file||!active)return;
 if(file.size>MAX_FILE){notify('PDF exceeds the 50 MiB viewer limit.');return;}
 const selection=++generation;requested++;
 try{const bytes=await file.arrayBuffer();if(!owns(selection))return;await openBytes(new Uint8Array(bytes));}catch(error){if(owns(selection))notify(error.message);}
};
const baseController=window.omniMediaController;
// OMNI_PDF_VIEWER_V1: D-pad scrolls (turns the page at the ends), L1 / R1 page, R2 / L2 zoom (sent by the shell),
// Square saves to Downloads, Circle goes back (the shared controller: dialogs first). Decisions: viewer-nav.mjs.
async function saveToDownloads(){
 const host=window.omnibloomHost,address=docAddress(openParams.doc);
 if(!host||!address||!documentPDF){notify('Save works for PDFs Omni opened from a link.');return;}
 notify('Saving to Downloads…');
 const r=await host.request({method:'pdf.save',params:{url:address}});
 notify(r&&r.ok?'Saved '+((r.result&&r.result.name)||'the PDF')+' to Downloads.':r&&r.code==='NOT_FOUND'?'This PDF is no longer open: open its link again to save it.':'Could not save this PDF.');
}
function navState(){
 const e=document.activeElement;
 return {hasDoc:!!documentPDF,dialogOpen:!!document.querySelector('dialog[open]'),inViewport:!e||e===document.body||e===viewport||viewport.contains(e),
  page:pageNumber,pages:documentPDF?documentPDF.numPages:0,top:viewport.scrollTop,maxTop:viewport.scrollHeight-viewport.clientHeight,
  left:viewport.scrollLeft,maxLeft:viewport.scrollWidth-viewport.clientWidth,viewH:viewport.clientHeight,viewW:viewport.clientWidth};
}
function controller(action){
 const d=decide(action,navState());
 switch(d.kind){
 case 'scroll':viewport.scrollBy({left:d.dx,top:d.dy,behavior:'smooth'});return true;
 case 'page':report(page(d.delta,d.edge));return true;
 case 'zoom':report(changeZoom(d.delta));return true;
 case 'save':report(saveToDownloads());return true;
 case 'none':return true;
 case 'ignore':return false;
 default:return baseController(action);
 }
}
window.omniMediaController=window.omniPadController=controller;
document.addEventListener('keydown',e=>{const k={ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down',PageUp:'l1',PageDown:'r1'}[e.key];if(k&&documentPDF&&(document.activeElement===viewport||document.activeElement===document.body)){e.preventDefault();e.stopImmediatePropagation();controller(k);}},true);
// The right stick scrolls with wheel events at the pointer: outside the document area they move the document too.
document.addEventListener('wheel',e=>{if(!documentPDF||viewport.contains(e.target)||e.target.closest?.('dialog'))return;e.preventDefault();viewport.scrollBy(e.deltaX,e.deltaY);},{passive:false});
const original=document.getElementById('open-original');
if(original){original.hidden=!openParams.src;original.onclick=()=>{if(openParams.src&&window.omnibloomHost)window.omnibloomHost.request({method:'navigation.open',params:{url:openParams.src}});};}
async function openFromOmni(){
 // A PDF Omni downloaded for this tab: same-origin bytes from omni://pages/_user/pdf/<token>.pdf (held in memory by Omni).
 const token=++generation;
 if(openParams.name){document.title=openParams.name+' · PDF reader';}
 notify('Opening '+(openParams.name||'PDF')+'…');
 try{
  const response=await fetch(docFetchPath(openParams.doc),{cache:'no-store'});
  if(!owns(token))return;
  if(!response.ok){notify('This PDF is no longer open.'+(openParams.src?' Use Open original to load it again.':''));if(original&&openParams.src)original.hidden=false;return;}
  const bytes=await response.arrayBuffer();
  if(owns(token))await openBytes(new Uint8Array(bytes));
 }catch(e){if(owns(token))notify('Could not open this PDF. '+String(e.message||e).slice(0,160));}
}
window.obPDFViewer={openBytes,next:()=>page(1),previous:()=>page(-1),getState:()=>({version:pdfjs?.version||null,pageNumber,pages:documentPDF?.numPages||0,zoom,pixels:canvas.width*canvas.height,text:lastPageText,rendering:!!renderTask,active})};
addEventListener('pagehide',()=>{
 active=false;generation++;requested++;
 const task=loadingTask,doc=documentPDF;loadingTask=null;documentPDF=null;cancel(renderTask);renderTask=null;
 clearDocumentUI();document.getElementById('pdf-file').value='';notify('Open a PDF to begin. Documents stay on this device.');void queueDispose(task,doc);
});
addEventListener('pageshow',e=>{active=true;controls();if(documentPDF)return;if(e.persisted&&openParams.doc&&window.omnibloomHost){void openFromOmni();return;}if(!openParams.doc)notify(window.omnibloomHost?'Open a PDF from Files.':'Open a PDF to begin. Documents stay on this device.');}); // OMNI_PDF_VIEWER_V1: Back / Forward to the reader opens it again
controls();
if(openParams.doc&&window.omnibloomHost)await openFromOmni(); // OMNI_PDF_VIEWER_V1
else if(window.omnibloomHost)notify('Open a PDF from Files.');
else if(new URL(location.href).searchParams.get('sample')==='1'){
 const token=++generation;
 try{const response=await fetch('sample.pdf');if(!owns(token)){}else if(!response.ok)throw Error('Sample unavailable');else{const bytes=await response.arrayBuffer();if(owns(token))await openBytes(new Uint8Array(bytes));}}
 catch(e){if(owns(token))notify('Could not open the sample PDF. '+e.message);}
}else notify('Open a PDF to begin. Documents stay on this device.');
