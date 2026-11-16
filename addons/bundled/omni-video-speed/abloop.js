// A-B loop for the Video speed add-on: pure state, no DOM. Exported as OmniSpeedLoop (window) or module.exports (tests).
(function(root,factory){const value=factory();if(typeof module==='object')module.exports=value;else root.OmniSpeedLoop=value})(globalThis,()=>{'use strict';
const MIN_LEN=0.5;            // a loop shorter than half a second would only stutter
function time(t){if(typeof t!=='number'||!Number.isFinite(t)||t<0)throw Error('INVALID_TIME');return Math.round(t*100)/100}
function clock(t){t=Math.max(0,Math.floor(t));const h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;
  return (h?h+':'+String(m).padStart(2,'0'):String(m))+':'+String(s).padStart(2,'0')}
class Loop{
  constructor(){this.clear()}
  clear(){this.video=null;this.a=null;this.b=null}
  get active(){return this.video!==null&&this.a!==null&&this.b!==null}
  // Setting a point on another video starts a new loop for that video.
  own(video){if(this.video!==video){this.video=video;this.a=null;this.b=null}}
  setA(video,t,duration){this.own(video);this.a=time(t);if(this.b!==null)this.fix(duration);return this.a}
  setB(video,t,duration){this.own(video);this.b=time(t);if(this.a!==null)this.fix(duration);return this.b}
  fix(duration){
    if(this.b<this.a)[this.a,this.b]=[this.b,this.a];
    if(typeof duration==='number'&&Number.isFinite(duration)&&duration>0&&this.b>duration)this.b=time(duration);
    if(this.b-this.a<MIN_LEN){this.b=null;throw Error('LOOP_TOO_SHORT')}
  }
  // Where to seek for this playback position, or null. Seeking before A is allowed (the user may want to hear the lead-in).
  target(video,t){if(!this.active||video!==this.video||typeof t!=='number'||!Number.isFinite(t))return null;return t>=this.b?this.a:null}
  label(){if(this.a===null&&this.b===null)return 'No loop';
    return 'A '+(this.a===null?'—':clock(this.a))+' · B '+(this.b===null?'—':clock(this.b))}
}
return{MIN_LEN,time,clock,Loop}});
