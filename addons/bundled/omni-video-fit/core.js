// Omni add-on "Video fit": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniVideoFitCore=value})(globalThis,()=>{'use strict';
// Order is the order on the panel and of Alt+Shift+F. 'fit' is the page's own look (nothing applied).
const MODES=Object.freeze(['fit','fill','stretch','zoom110','zoom120','zoom133']);
const LABELS=Object.freeze({fit:'Fit',fill:'Fill (crop)',stretch:'Stretch',zoom110:'Zoom 1.1×',zoom120:'Zoom 1.2×',zoom133:'Zoom 1.33×'});
const ZOOM=Object.freeze({zoom110:1.1,zoom120:1.2,zoom133:4/3});
// Omni's hardware video plane (engine/media/OmniHwProtocol.h): a present rect over 4096 on a side or over
// 3840x2160 pixels is refused and the video falls back to the software paint path.
const HOLE_MAX_SIDE=4096,HOLE_MAX_PIXELS=3840*2160;
// Videos smaller than this (CSS px) are previews, ads or avatars: left alone.
const MIN_W=200,MIN_H=112;
const SITE_PREFIX='h:',MAX_SITES=300;
const valid=m=>typeof m==='string'&&MODES.includes(m);
function next(mode,dir){const i=MODES.indexOf(mode);if(i<0)return MODES[0];return MODES[(i+(dir<0?MODES.length-1:1))%MODES.length]}
const num=x=>typeof x==='number'&&Number.isFinite(x)&&x>0;
// The rect object-fit: contain paints the picture in (centred), in the box's units.
function containSize(bw,bh,vw,vh){if(!num(bw)||!num(bh))return{w:0,h:0};if(!num(vw)||!num(vh))return{w:bw,h:bh};const s=Math.min(bw/vw,bh/vh);return{w:vw*s,h:vh*s}}
// How much larger object-fit: cover paints than contain (1 when the shapes match).
function coverFactor(bw,bh,vw,vh){if(!num(bw)||!num(bh)||!num(vw)||!num(vh))return 1;const a=bw/bh,b=vw/vh;return a>b?a/b:b/a}
function fits(w,h){return w<=HOLE_MAX_SIDE&&h<=HOLE_MAX_SIDE&&w*h<=HOLE_MAX_PIXELS}
// The largest scale of a w x h rect the plane still takes.
function maxZoom(w,h){if(!num(w)||!num(h))return Infinity;return Math.min(HOLE_MAX_SIDE/w,HOLE_MAX_SIDE/h,Math.sqrt(HOLE_MAX_PIXELS/(w*h)))}
// What to put on one video. box: layout size in CSS px (no transforms), video: intrinsic size (0 = unknown yet),
// scale: device pixels per CSS px, keepHw: keep the picture's rect within the plane's limits.
// Returns {fit:null|'contain'|'cover'|'fill', zoom, limited, rect:{w,h} (device px, the rect the player reports)}.
function plan(mode,box,video,o){o=o||{};const scale=num(o.scale)?o.scale:1,keepHw=o.keepHw!==false;
  const bw=box&&box.w,bh=box&&box.h,vw=video&&video.w,vh=video&&video.h,c=containSize(bw,bh,vw,vh),cw=c.w*scale,ch=c.h*scale;
  const out=(fit,zoom,limited,w,h)=>({fit,zoom,limited,rect:{w:Math.round(w),h:Math.round(h)}});
  if(!valid(mode)||mode==='fit')return out(null,1,false,cw,ch);
  if(mode==='stretch')return out('fill',1,false,(bw||0)*scale,(bh||0)*scale);
  const want=mode==='fill'?coverFactor(bw,bh,vw,vh):ZOOM[mode];
  if(!keepHw||fits(cw*want,ch*want))return mode==='fill'?out('cover',1,false,cw*want,ch*want):out('contain',want,false,cw*want,ch*want);
  // Over the plane's limits: the most zoom it still takes (contain + scale gives the same centred crop as cover).
  const z=Math.max(1,Math.floor(maxZoom(cw,ch)*1000)/1000);return out('contain',z,true,cw*z,ch*z)}
// A model of the WebProcess players' holeGeometry() (engine/entry/OmniMSEPlayer.cpp): the paint rect RenderVideo uses
// (object-fit applied to the content box), mapped through the element's transforms, bounding box in root-view pixels.
// el: {x,y,w,h} layout box (CSS px), fit: object-fit, zoom: scale() about the centre, scale: device px per CSS px.
function holeRect(el,video,fit,zoom,scale){const s=num(scale)?scale:1,z=num(zoom)?zoom:1;let w=el.w,h=el.h;
  if(fit==='contain'||fit==='cover'){const c=containSize(el.w,el.h,video.w,video.h),k=fit==='cover'?coverFactor(el.w,el.h,video.w,video.h):1;w=c.w*k;h=c.h*k}
  const cx=el.x+el.w/2,cy=el.y+el.h/2,W=w*z,H=h*z;
  const r={x:Math.round((cx-W/2)*s),y:Math.round((cy-H/2)*s),w:Math.round(W*s),h:Math.round(H*s)};
  r.accepted=r.w>=2&&r.h>=2&&fits(r.w,r.h);return r}
// Big enough to be the thing being watched (fullscreen always is).
function worthIt(w,h,fullscreen){return!!fullscreen||num(w)&&num(h)&&w>=MIN_W&&h>=MIN_H}
// Per-site memory: one key per site, a hash of the host (the host itself is not stored), value [mode, seconds].
function host(h){return String(h||'').toLowerCase().replace(/^www\./,'').replace(/\.$/,'')}
function hash(text){let a=0x811c9dc5,b=0x9e3779b1;for(let i=0;i<text.length;i++){const c=text.charCodeAt(i);a=Math.imul(a^c,16777619);b=Math.imul(b^c,2246822519)^(b>>>13)}return(a>>>0).toString(36)+(b>>>0).toString(36)}
function siteKey(hostname){const h=host(hostname);return h?SITE_PREFIX+hash(h):null}
function entry(mode,now){return[mode,Math.floor(now/1000)]}
function saved(e){return Array.isArray(e)&&valid(e[0])?e[0]:null}
// Keys to drop so at most max sites remain: oldest first, broken entries first of all.
function prune(entries,max=MAX_SITES){const list=Object.keys(entries).filter(k=>k.startsWith(SITE_PREFIX)).map(k=>{const e=entries[k];return{k,at:saved(e)&&typeof e[1]==='number'?e[1]:-1}});
  if(list.length<=max)return[];list.sort((x,y)=>x.at-y.at||(x.k<y.k?-1:1));return list.slice(0,list.length-max).map(x=>x.k)}
// The mode for this page: this page's choice, else the site's saved one, else the settings page default.
function resolve(session,stored,fallback){return valid(session)?session:valid(stored)?stored:valid(fallback)?fallback:'fit'}
return Object.freeze({MODES,LABELS,ZOOM,HOLE_MAX_SIDE,HOLE_MAX_PIXELS,MIN_W,MIN_H,SITE_PREFIX,MAX_SITES,valid,next,containSize,coverFactor,fits,maxZoom,plan,holeRect,worthIt,host,hash,siteKey,entry,saved,prune,resolve})});
