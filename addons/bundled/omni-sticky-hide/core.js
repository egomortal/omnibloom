// Omni add-on "Sticky bar hider": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniStickyCore=value})(globalThis,()=>{'use strict';
// A bar worth hiding: fixed or sticky, wide (at least 60% of the window), short (at most 30% of its height), stuck to the
// top or the bottom edge, not a dialog / full-screen overlay / the page's own video, and not ours.
function isBar(r,win,pos,tag,role){
  if(pos!=='fixed'&&pos!=='sticky')return false;
  if(!r||!(r.width>0&&r.height>0))return false;
  if(/^(video|dialog)$/i.test(tag||'')||/^(dialog|alertdialog)$/i.test(role||''))return false;
  if(r.width<win.w*0.6||r.height>win.h*0.3)return false;
  const top=r.top<=8,bottom=win.h-r.bottom<=8;return top?'top':bottom?'bottom':false}
// Scroll direction with a dead zone: hide after 24 px down, show after 12 px up or near the top of the page.
function decide(state,y){const d=y-state.anchor;
  if(y<64)return{hidden:false,anchor:y};
  if(!state.hidden&&d>24)return{hidden:true,anchor:y};
  if(state.hidden&&d<-12)return{hidden:false,anchor:y};
  if(state.hidden?d>0:d<0)return{hidden:state.hidden,anchor:y};   // keep the anchor at the turning point
  return state}
return Object.freeze({isBar,decide})});
