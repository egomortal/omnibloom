/* Trusted host invokes createOmniDarkReader; no page-owned preferences or bridge. */
(function(root){
'use strict';
root.createOmniDarkReader=function(win,options={}){
 const dr=win.DarkReader,doc=win.document; let applied='off',cachedNode=null,paused=false,last=null,rootFilter=null;
 if(!dr)throw Error('DARK_ENGINE_MISSING');
 dr.setFetchMethod((url)=>win.fetch(url,{mode:'cors',credentials:'same-origin',redirect:'follow'}));
 const own=options.ownPage===true;
 function clear(){dr.disable();cachedNode?.remove();cachedNode=null;if(rootFilter!==null){doc.documentElement.style.filter=rootFilter;rootFilter=null}doc.querySelectorAll('[data-omni-filter-media]').forEach(e=>{e.style.filter=e.dataset.omniFilterMedia;e.removeAttribute('data-omni-filter-media')});applied='off'}
 function apply(state,css){last={state,css};clear();if(own||paused||doc.fullscreenElement||state.enabled!==true)return applied;
 const theme={brightness:Math.max(50,Math.min(150,Number(state.brightness)||100)),contrast:Math.max(50,Math.min(150,Number(state.contrast)||100)),sepia:Math.max(0,Math.min(100,Number(state.sepia)||0))};
 if(state.mode==='cache'&&typeof css==='string'&&css.length<1048576){cachedNode=doc.createElement('style');cachedNode.dataset.omniDarkCache='';cachedNode.textContent=css;doc.documentElement.append(cachedNode);applied='cache'}
 else if(state.mode==='filter'){rootFilter=doc.documentElement.style.filter;doc.documentElement.style.filter=`invert(1) hue-rotate(180deg) brightness(${theme.brightness}%) contrast(${theme.contrast}%) sepia(${theme.sepia}%)`;doc.querySelectorAll('img,video,canvas,svg image').forEach(e=>{e.dataset.omniFilterMedia=e.style.filter;e.style.filter='invert(1) hue-rotate(180deg)'});applied='filter'}
 else {dr.enable(theme);applied='dynamic'}return applied;
 }
 function fullscreen(){if(doc.fullscreenElement)clear();else if(last)apply(last.state,last.css)}
 doc.addEventListener('fullscreenchange',fullscreen);
 return {apply,disable:clear,get mode(){return applied},isEnabled:()=>applied!=='off',exportCSS:()=>dr.exportGeneratedCSS(),mediaActive(value){paused=!!value;if(paused)clear();else if(last)apply(last.state,last.css)},dispose(){clear();doc.removeEventListener('fullscreenchange',fullscreen)}};
};
})(window);
