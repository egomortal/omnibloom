// Omni add-on "Image gallery": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniGalleryCore=value})(globalThis,()=>{'use strict';
const MAX=300,MIN_W=200,MIN_H=150;
// The largest candidate of a srcset ("a.jpg 480w, b.jpg 1080w" or "a.jpg 1x, b.jpg 2x"); null when it has none.
function bestFromSrcset(srcset){let best=null,score=-1;
  for(const part of String(srcset||'').split(/,\s+(?=\S)/)){const m=/^\s*(\S+)(?:\s+(\d+(?:\.\d+)?)([wx]))?\s*$/.exec(part);if(!m)continue;
    const s=m[2]?Number(m[2])*(m[3]==='x'?1000:1):1;if(s>score){score=s;best=m[1]}}
  return best}
function usable(url,base){if(!url)return null;let u;try{u=new URL(url,base)}catch(_){return null}
  if(!/^https?:$/.test(u.protocol))return null;if(/\.svg(\?|#|$)/i.test(u.pathname))return null;u.hash='';return u.href}
// Candidates: {src, srcset, dataSrc, dataSrcset, w, h, nw, nh} (displayed and natural sizes; lazy images may have 0 natural).
function pick(cands,base){const out=[],seen=new Set();
  for(const c of Array.isArray(cands)?cands:[]){if(!c)continue;
    const big=(c.nw>=MIN_W&&c.nh>=MIN_H)||(c.w>=MIN_W&&c.h>=MIN_H)||(!c.nw&&!c.w&&(c.dataSrc||c.dataSrcset));
    if(!big)continue;
    const url=usable(bestFromSrcset(c.dataSrcset)||bestFromSrcset(c.srcset)||c.dataSrc||c.src,base);
    if(!url||seen.has(url))continue;seen.add(url);out.push(url);if(out.length>=MAX)break}
  return out}
function wrap(i,n){return n?((i%n)+n)%n:0}
// Which images to keep decoded: the current one and the next (one neighbour; memory stays bounded on the console).
function keep(i,n){return n?[...new Set([wrap(i,n),wrap(i+1,n)])]:[]}
return Object.freeze({MAX,bestFromSrcset,usable,pick,wrap,keep})});
