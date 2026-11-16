// Omni add-on "Auto-scroll": pure logic (no DOM). MIT, Omnibloom contributors.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniAutoScrollCore=value})(globalThis,()=>{'use strict';
const SPEEDS=Object.freeze([10,20,30,45,60,90,120,180]);   // CSS px per second
function speedIndex(v){const i=SPEEDS.indexOf(Number(v));return i<0?2:i}
function stepSpeed(i,dir){return Math.max(0,Math.min(SPEEDS.length-1,i+(dir<0?-1:1)))}
// Pixels for this frame: whole pixels only, carrying the fraction, and never past the bottom.
function advance(carry,speed,dtMs,y,maxY){const dt=Math.max(0,Math.min(250,dtMs));const want=carry+speed*dt/1000;const px=Math.floor(want);
  const room=Math.max(0,maxY-y);const move=Math.min(px,room);return{move,carry:want-px,done:room<=0}}
return Object.freeze({SPEEDS,speedIndex,stepSpeed,advance})});
