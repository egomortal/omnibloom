(()=>{'use strict';
const base=window.BloomLayoutSkeleton,profiles=window.BloomLoadingProfiles;if(!base||!profiles)return;
const pending=new Set();
function hiddenAncestor(e){for(let p=e.parentElement;p;p=p.parentElement){if(p.hidden||getComputedStyle(p).display==='none'||getComputedStyle(p).visibility==='hidden')return true}return false}
function clean(r){const x=r.loadingProfile;if(!x)return;for(const n of x.nodes)n.remove();r.region.style.cssText=x.style;if(x.marker?.isConnected)x.marker.replaceWith(r.panel);delete r.loadingProfile;pending.delete(r)}
function before(r){base.before(r);clean(r)}
function after(r,state,retain){
 const p=profiles[r.c.id];if(!p||state!=='loading'||retain||!r.region){base.after(r,state,retain);return}
 if(r.originalHidden||hiddenAncestor(r.region)){r.region.hidden=r.originalHidden;r.skeleton.hidden=true;r.panel.dataset.skeletonGeometry='hidden-preserved';return}
 const real=[...r.region.children].filter(n=>n!==r.panel);
 if(real.length||r.region.textContent.trim()&&r.region!==r.root){base.after(r,state,retain);return}
 const nodes=[];for(const html of p.html.slice(0,5)){const t=document.createElement('template');t.innerHTML=html;for(const n of t.content.children){n.dataset.loadingReservation='true';n.inert=true;n.setAttribute('aria-hidden','true');nodes.push(n)}}
 let marker=null;if(r.region.contains(r.panel)){marker=document.createComment('loading-panel-anchor');r.panel.before(marker);r.region.before(r.panel)}
 r.loadingProfile={nodes,marker,style:r.region.style.cssText};pending.add(r);r.region.append(...nodes);if(p.reserveExtraRem){r.region.hidden=false;const panelHidden=r.panel.hidden;r.panel.hidden=true;const height=r.region.getBoundingClientRect().height;r.panel.hidden=panelHidden;r.region.style.minHeight=(height+p.reserveExtraRem*parseFloat(getComputedStyle(document.documentElement).fontSize))+'px'}base.after(r,state,retain);
 if(r.layoutSkeleton)r.panel.dataset.skeletonGeometry='source-profile';
 else clean(r);
}
window.BloomLayoutSkeleton=Object.freeze({before,after});
window.addEventListener('pagehide',()=>{for(const r of [...pending])before(r)});
window.BloomLoadingProfileDiagnostics=()=>({active:pending.size});
})();

