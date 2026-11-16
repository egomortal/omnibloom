// Omni add-on "Reading ruler": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniRulerCore=value})(globalThis,()=>{'use strict';
const HEIGHTS=Object.freeze({small:1.6,medium:2.4,large:3.6});   // band height in lines of the page's text
// Band height in px from the line height of the text at the band (computed "normal" ~ 1.25 x font size), clamped.
function bandPx(size,lineHeight,setting){const fs=Number(size)>0?Number(size):16;let lh=Number(lineHeight);if(!(lh>0))lh=fs*1.25;
  const k=HEIGHTS[setting]||HEIGHTS.medium;return Math.round(Math.max(24,Math.min(400,lh*k)))}
// Band top: centred on the window's middle (the place D-pad scrolling keeps the reading line).
function bandTop(winH,band){return Math.round(Math.max(0,(winH-band)/2))}
return Object.freeze({HEIGHTS,bandPx,bandTop})});
