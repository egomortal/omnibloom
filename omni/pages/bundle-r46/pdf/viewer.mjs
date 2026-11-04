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
async function render(){
 if(!active||!documentPDF)return;
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
 canvas.setAttribute('aria-label','PDF page '+current+' of '+doc.numPages);viewport.scrollTop=viewport.scrollLeft=0;
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
async function page(delta){if(!active||!documentPDF)return false;const next=Math.max(1,Math.min(documentPDF.numPages,pageNumber+delta));if(next===pageNumber)return true;pageNumber=next;await render();return true;}
async function changeZoom(delta){if(!active||!documentPDF)return false;zoom=Math.max(.5,Math.min(3,zoom+delta));await render();return true;}
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
function controller(action){if(document.querySelector('dialog[open]'))return baseController(action);if((action==='left'||action==='right')&&document.activeElement===viewport){report(page(action==='left'?-1:1));return !!documentPDF;}if(action==='l1'||action==='r1'){report(changeZoom(action==='l1'?-.25:.25));return !!documentPDF;}return baseController(action);}
window.omniMediaController=window.omniPadController=controller;
document.addEventListener('keydown',e=>{if(document.activeElement===viewport&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){e.preventDefault();e.stopImmediatePropagation();controller(e.key==='ArrowLeft'?'left':'right');}},true);
window.obPDFViewer={openBytes,next:()=>page(1),previous:()=>page(-1),getState:()=>({version:pdfjs?.version||null,pageNumber,pages:documentPDF?.numPages||0,zoom,pixels:canvas.width*canvas.height,text:lastPageText,rendering:!!renderTask,active})};
addEventListener('pagehide',()=>{
 active=false;generation++;requested++;
 const task=loadingTask,doc=documentPDF;loadingTask=null;documentPDF=null;cancel(renderTask);renderTask=null;
 clearDocumentUI();document.getElementById('pdf-file').value='';notify('Open a PDF to begin. Documents stay on this device.');void queueDispose(task,doc);
});
addEventListener('pageshow',()=>{active=true;controls();if(!documentPDF)notify(window.omnibloomHost?'Open a PDF from Files.':'Open a PDF to begin. Documents stay on this device.');});
controls();
if(window.omnibloomHost)notify('Open a PDF from Files.');
else if(new URL(location.href).searchParams.get('sample')==='1'){
 const token=++generation;
 try{const response=await fetch('sample.pdf');if(!owns(token)){}else if(!response.ok)throw Error('Sample unavailable');else{const bytes=await response.arrayBuffer();if(owns(token))await openBytes(new Uint8Array(bytes));}}
 catch(e){if(owns(token))notify('Could not open the sample PDF. '+e.message);}
}else notify('Open a PDF to begin. Documents stay on this device.');
