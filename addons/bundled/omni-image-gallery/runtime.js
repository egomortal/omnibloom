// Omni add-on "Image gallery": page glue. MIT, Omnibloom contributors.
// Alt+Shift+G shows the page's large images (lazy ones too) full screen; Left / Right step, Escape closes.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniGalleryCore;
let enabled=false,root=null,imgs=[],urls=[],i=0,prior=null,label=null;
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e};
function collect(){return core.pick([...document.images].filter(im=>!im.closest('[data-omni-addon]')).map(im=>({src:im.currentSrc||im.src,srcset:im.getAttribute('srcset'),
  dataSrc:im.getAttribute('data-src')||im.getAttribute('data-lazy-src')||im.getAttribute('data-original'),dataSrcset:im.getAttribute('data-srcset'),
  w:im.clientWidth,h:im.clientHeight,nw:im.naturalWidth,nh:im.naturalHeight})),location.href)}
function show(){const n=urls.length;i=core.wrap(i,n);const keep=new Set(core.keep(i,n));
  imgs.forEach((im,k)=>{const want=keep.has(k);if(want&&!im.src)im.src=urls[k];if(!want&&im.src){im.removeAttribute('src')}im.hidden=k!==i});
  label.textContent=(i+1)+' / '+n}
function open(){if(root)return close();urls=collect();if(!urls.length){if(api.toast)api.toast('No large images on this page');return}
  prior=document.activeElement;i=0;root=node('div','omni-gal');root.dataset.omniAddon=api.id;root.tabIndex=-1;root.setAttribute('role','dialog');root.setAttribute('aria-label','Image gallery');
  imgs=urls.map(()=>{const im=node('img','omni-gal-img');im.alt='';im.decoding='async';im.referrerPolicy='no-referrer-when-downgrade';im.hidden=true;return im});
  label=node('div','omni-gal-count');const hint=node('div','omni-gal-hint','Left / Right: previous / next · Escape: close');
  root.append(...imgs,label,hint);document.body.append(root);root.addEventListener('keydown',key,true);
  root.addEventListener('click',e=>{const x=e.clientX/window.innerWidth;i+=x<0.5?-1:1;show()});root.focus();show()}
function close(){if(!root)return;imgs.forEach(im=>im.removeAttribute('src'));root.remove();root=null;imgs=[];urls=[];
  try{prior&&prior.isConnected&&prior.focus({preventScroll:true})}catch(_){}prior=null}
function key(e){if(!root)return;const k=e.key;
  if(k==='ArrowRight'||k==='ArrowDown'||k===' '){i++;show()}else if(k==='ArrowLeft'||k==='ArrowUp'){i--;show()}
  else if(k==='Home'){i=0;show()}else if(k==='End'){i=urls.length-1;show()}else if(k==='Escape'||k==='Backspace'){close()}else return;
  e.preventDefault();e.stopPropagation()}
function global(e){if(enabled&&e.altKey&&e.shiftKey&&!e.ctrlKey&&!e.metaKey&&e.code==='KeyG'){e.preventDefault();e.stopPropagation();open()}}
function start(){if(enabled)return;enabled=true;document.addEventListener('keydown',global,true)}
function stop(){enabled=false;document.removeEventListener('keydown',global,true);close()}
api.onEnable(start);api.onDisable(stop);if(api.active)start()})();
