// Omni add-on "Unlock selection": pure logic (no page side effects). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniUnlockSelectCore=value})(globalThis,()=>{'use strict';
const ROOT_CLASS='omni-unlock-select';           // on <html> while unlocked; addon.css only acts under it
const TYPES=Object.freeze(['selectstart','copy','contextmenu','dragstart','mousedown']);
// Inline handler attributes that are removed when their code cancels the event (return false / preventDefault / returnValue=false).
const ATTRS=Object.freeze(['onselectstart','oncopy','oncut','oncontextmenu','ondragstart','onmousedown']);
const ATTR_SELECTOR=ATTRS.map(a=>'['+a+']').join(',');
const BLOCKER=/return\s*\(?\s*false\b|preventDefault\s*\(|returnValue\s*=\s*false\b/i;
const blockerCode=v=>typeof v==='string'&&BLOCKER.test(v);
// Times the page must be seen cancelling an event on plain text before Omni shields that event type.
// mousedown needs two: many apps cancel a single mousedown for their own reasons.
const THRESHOLD=Object.freeze({selectstart:1,copy:1,contextmenu:1,dragstart:1,mousedown:2});
const SCAN_MS=500;                               // mutation rescans are throttled to one per this
const BIG_CANVAS=0.5;                            // a canvas covering half the viewport = canvas app/game: hands off
const EDIT_TAGS=new Set(['input','textarea','select','option']);
const CONTROL_TAGS=new Set(['button','canvas','video','audio','svg','embed','object','iframe','img','map','area']);
const CONTROL_ROLES=/^(button|slider|tab|menuitem\w*|option|switch|checkbox|radio|scrollbar|spinbutton|combobox|textbox|searchbox|application|gridcell|treeitem)$/;
const isEl=n=>!!n&&n.nodeType===1;
const tagOf=el=>String(el&&(el.localName||el.tagName)||'').toLowerCase();
const attr=(el,k)=>el&&el.getAttribute?el.getAttribute(k):null;
// What the event landed on: 'edit' (text fields, editable regions), 'control' (buttons, canvas, media, Omni UI,
// draggable things), or 'text' (ordinary page content: the only place Omni ever interferes).
function kind(target){let el=isEl(target)?target:target&&target.nodeType===3?target.parentNode:null;if(!isEl(el))return'control';
  for(let e=el,first=true;isEl(e);e=e.parentNode,first=false){const t=tagOf(e);
    if(EDIT_TAGS.has(t))return'edit';const ce=attr(e,'contenteditable');if(ce!=null&&String(ce).toLowerCase()!=='false')return'edit';
    if(attr(e,'data-omni-addon')!=null)return'control';
    if(CONTROL_TAGS.has(t))return'control';const role=String(attr(e,'role')||'').toLowerCase();if(CONTROL_ROLES.test(role))return'control';
    if(first&&String(attr(e,'draggable')||'')==='true')return'control';
    if(t==='body'||t==='html')break}
  return'text'}
// Should this event be stopped before the page sees it?
// seen: {type: times the page cancelled it on text}; opts.mousedown: the mousedown unlock is on.
function shield(type,k,seen,opts={}){if(k!=='text'||!TYPES.includes(type))return false;if(type==='mousedown'&&opts.mousedown===false)return false;
  if(type==='mousedown'&&opts.button!=null&&opts.button!==0)return false;return(seen&&seen[type]||0)>=THRESHOLD[type]}
// After the page has handled an event: did it cancel something it should not have? (only text targets count)
const learn=(type,k,defaultPrevented)=>TYPES.includes(type)&&k==='text'&&!!defaultPrevented;
// Attributes to strip from one element: blocker code on the events above; onmousedown only off controls.
function stripList(el){const out=[];if(!isEl(el))return out;for(const a of ATTRS){const v=attr(el,a);if(!blockerCode(v))continue;
    if(a==='onmousedown'&&kind(el)!=='text')continue;out.push(a)}return out}
// rects: [{w,h}] of canvases; view: {w,h}. True when one canvas is the page's main content.
function bigCanvas(rects,view){const area=Math.max(1,(view&&view.w||0)*(view&&view.h||0));
  for(const r of rects||[])if(r&&r.w>0&&r.h>0&&Math.min(r.w,view.w||r.w)*Math.min(r.h,view.h||r.h)>=BIG_CANVAS*area)return true;return false}
return Object.freeze({ROOT_CLASS,TYPES,ATTRS,ATTR_SELECTOR,THRESHOLD,SCAN_MS,BIG_CANVAS,blockerCode,kind,shield,learn,stripList,bigCanvas})});
