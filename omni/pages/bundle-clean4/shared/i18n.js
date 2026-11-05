(function(){'use strict';
// Omnibloom page translator. The catalog is keyed by the exact English text, so pages keep their English source and
// this swaps visible text, placeholder, aria-label and title when another language is chosen. Dynamic text set
// later by the page is caught by a MutationObserver. Language: Omni's settings bridge, then ?lang=, then the saved
// preview choice, then English. Untranslated text stays English.
const pick=()=>{try{const h=window.omnibloomHost;if(h&&typeof h.getLanguage==='function'){const l=h.getLanguage();if(l)return l}}catch(e){}
 const q=new URLSearchParams(location.search).get('lang');if(q)return q;try{return localStorage.getItem('ob.lang')||'en'}catch(e){return 'en'}};
const lang=pick();document.documentElement.lang=lang;if(lang==='en')return;
let map=null;const ATTR=['placeholder','aria-label','title'];
function tr(s){if(!map||!s)return null;const k=s.trim();const t=map[k]&&map[k][lang];return t?s.replace(k,t):null}
function owned(node){const el=node.nodeType===1?node:node.parentElement;return !!el&&!!((window.BloomStateCopy&&el.closest('.bloom-screen-state[data-screen]'))||(window.BloomStatusCopy&&el.closest('#summary')))}
function walk(root){if(!map||owned(root))return;const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while((n=w.nextNode())){const p=n.parentElement;if(owned(n)||p&&/^(SCRIPT|STYLE)$/.test(p.tagName))continue;const t=tr(n.nodeValue);if(t!==null)n.nodeValue=t}
 (root.querySelectorAll?root:document).querySelectorAll('*').forEach(e=>ATTR.forEach(a=>{if(!owned(e)&&e.hasAttribute(a)){const t=tr(e.getAttribute(a));if(t!==null)e.setAttribute(a,t)}}))}
fetch('../shared/i18n-map.json').then(r=>r.ok?r.json():null).then(d=>{if(!d)return;map=d.strings;walk(document.body);
 new MutationObserver(ms=>ms.forEach(m=>{if(m.type==='characterData'){if(owned(m.target))return;const t=tr(m.target.nodeValue);if(t!==null&&t!==m.target.nodeValue)m.target.nodeValue=t}else m.addedNodes.forEach(x=>{if(x.nodeType===3){if(owned(x))return;const t=tr(x.nodeValue);if(t!==null)x.nodeValue=t}else if(x.nodeType===1)walk(x)})})).observe(document.body,{childList:true,subtree:true,characterData:true})}).catch(()=>{});
})();
