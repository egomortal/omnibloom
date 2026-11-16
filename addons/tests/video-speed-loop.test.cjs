// node --test addons/tests   (A-B loop state for omni-video-speed)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),path=require('node:path');
const L=require(path.join(__dirname,'..','bundled','omni-video-speed','abloop.js'));
const v1={id:1},v2={id:2};
test('loop jumps back to A at or after B, and only for its own video',()=>{
  const l=new L.Loop();l.setA(v1,80);l.setB(v1,225);a.ok(l.active);
  a.equal(l.target(v1,100),null);a.equal(l.target(v1,225),80);a.equal(l.target(v1,300),80);
  a.equal(l.target(v2,300),null);a.equal(l.target(v1,10),null);a.equal(l.target(v1,NaN),null);
});
test('B before A swaps, B past the end is clamped, too short is refused',()=>{
  const l=new L.Loop();l.setB(v1,50);l.setA(v1,90);a.equal(l.a,50);a.equal(l.b,90);
  const c=new L.Loop();c.setA(v1,10);c.setB(v1,999,120);a.equal(c.b,120);
  const s=new L.Loop();s.setA(v1,10);a.throws(()=>s.setB(v1,10.2),/LOOP_TOO_SHORT/);a.equal(s.b,null);a.equal(s.active,false);
});
test('a point on another video starts a new loop; clear resets',()=>{
  const l=new L.Loop();l.setA(v1,5);l.setB(v1,20);l.setA(v2,7);a.equal(l.video,v2);a.equal(l.b,null);a.equal(l.active,false);
  l.clear();a.equal(l.video,null);a.equal(l.label(),'No loop');
});
test('bad times are refused and labels read like a clock',()=>{
  const l=new L.Loop();for(const t of[-1,NaN,Infinity,'5',undefined])a.throws(()=>l.setA(v1,t),/INVALID_TIME/);
  a.equal(L.clock(65),'1:05');a.equal(L.clock(3725),'1:02:05');a.equal(L.clock(0),'0:00');
  l.setA(v1,80);a.equal(l.label(),'A 1:20 · B —');l.setB(v1,225);a.equal(l.label(),'A 1:20 · B 3:45');
});
