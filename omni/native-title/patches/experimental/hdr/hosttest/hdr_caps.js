(function(){if(window.__omniHdrCapsV1)return;window.__omniHdrCapsV1=1;var CAP=__CAP__;
var VP=/vp09\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)/gi,AV=/av01\.\d\.\d\d[MH]\.(10|12)\.\d\.\d{3}\.\d\d\.(16|18)\b/i;
function hdrType(t){t=String(t==null?'':t);if(/eotf\s*=\s*"?(smpte2084|arib-std-b67)/i.test(t)||AV.test(t))return true;var m,re=new RegExp(VP.source,'gi');while((m=re.exec(t)))if(m[6]==='16'||m[6]==='18')return true;return false;}
function sdrForm(t){return String(t).replace(new RegExp(VP.source,'gi'),function(s,p,l,d,c,cp,tc){return (tc==='16'||tc==='18')?'vp09.'+p+'.'+l+'.'+d+'.'+c+'.'+cp+'.01':s;}).replace(/;\s*eotf\s*=\s*"?[^;"]*"?/i,'');}
function wrap(o,k,f){try{var g=o&&o[k];if(typeof g==='function')o[k]=f(g);}catch(e){}}
try{if(window.MediaSource){wrap(MediaSource,'isTypeSupported',function(g){return function(t){if(hdrType(t))return CAP?g.call(this,sdrForm(t)):false;return g.call(this,t);};});
wrap(MediaSource.prototype,'addSourceBuffer',function(g){return function(t){return g.call(this,CAP&&hdrType(t)?sdrForm(t):t);};});}
if(window.SourceBuffer)wrap(SourceBuffer.prototype,'changeType',function(g){return function(t){return g.call(this,CAP&&hdrType(t)?sdrForm(t):t);};});
if(window.HTMLMediaElement)wrap(HTMLMediaElement.prototype,'canPlayType',function(g){return function(t){if(hdrType(t))return CAP?g.call(this,sdrForm(t)):'';return g.call(this,t);};});}catch(e){}
try{var mc=navigator.mediaCapabilities;if(mc&&mc.decodingInfo){var di=mc.decodingInfo;mc.decodingInfo=function(cfg){var v=cfg&&cfg.video;
if(v&&(v.hdrMetadataType||(v.colorGamut&&v.colorGamut!=='srgb')||(v.transferFunction&&v.transferFunction!=='srgb')||hdrType(v.contentType))){
if(!CAP)return Promise.resolve({supported:false,smooth:false,powerEfficient:false,configuration:cfg});
var c={};for(var k in cfg)c[k]=cfg[k];var w={};for(var j in v)if(j!=='hdrMetadataType'&&j!=='colorGamut'&&j!=='transferFunction')w[j]=v[j];w.contentType=sdrForm(v.contentType);c.video=w;
return di.call(mc,c).then(function(r){var o={supported:r.supported,smooth:r.smooth,powerEfficient:r.powerEfficient,configuration:cfg};return o;});}
return di.call(mc,cfg);};}}catch(e){}
try{var mm=window.matchMedia;if(mm){var T='(min-width:0px)',F='(max-width:0px) and (min-width:1px)';
window.matchMedia=function(q){var s=String(q).replace(/\(\s*(video-)?dynamic-range\s*:\s*(high|standard)\s*\)/gi,function(x,v,r){return r.toLowerCase()==='standard'||CAP?T:F;})
.replace(/\(\s*color-gamut\s*:\s*(srgb|p3|rec2020)\s*\)/gi,function(x,r){return r.toLowerCase()==='srgb'||CAP?T:F;});
var r=mm.call(window,s);if(s!==String(q)){try{Object.defineProperty(r,'media',{value:String(q)});}catch(e){}}return r;};}}catch(e){}
if(CAP)try{['colorDepth','pixelDepth'].forEach(function(k){Object.defineProperty(Screen.prototype,k,{configurable:true,get:function(){return 30;}});});}catch(e){}
})();
