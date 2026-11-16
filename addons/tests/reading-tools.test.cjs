// node --test addons/tests   (Auto-scroll, Reading ruler, Same-tab links: pure rules)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),path=require('node:path');
const B=path.join(__dirname,'..','bundled');
const AS=require(path.join(B,'omni-auto-scroll','core.js')),RR=require(path.join(B,'omni-reading-ruler','core.js')),ST=require(path.join(B,'omni-same-tab','core.js'));
test('auto-scroll: speeds, whole pixels with carry, capped frames, stops at the end',()=>{
  a.equal(AS.speedIndex(30),2);a.equal(AS.speedIndex('nonsense'),2);a.equal(AS.stepSpeed(0,-1),0);a.equal(AS.stepSpeed(7,1),7);a.equal(AS.stepSpeed(2,1),3);
  let r=AS.advance(0,30,16,0,1000);a.equal(r.move,0);a.ok(Math.abs(r.carry-0.48)<1e-9);
  r=AS.advance(r.carry,30,40,0,1000);a.equal(r.move,1);
  a.equal(AS.advance(0,60,5000,0,1000).move,15,'a 5 s stall moves at most 250 ms worth');
  r=AS.advance(0,180,250,995,1000);a.equal(r.move,5);a.equal(r.done,false);a.equal(AS.advance(0,180,16,1000,1000).done,true)});
test('ruler: band from the text line height, clamped and centred',()=>{
  a.equal(RR.bandPx(16,24,'medium'),58);a.equal(RR.bandPx(16,NaN,'small'),32);a.equal(RR.bandPx(0,0,'large'),72);
  a.equal(RR.bandPx(200,300,'large'),400);a.equal(RR.bandPx(8,8,'small'),24);a.equal(RR.bandPx(16,24,'nope'),58);
  a.equal(RR.bandTop(1080,58),511);a.equal(RR.bandTop(40,100),0)});
test('same-tab: which links are kept in this tab',()=>{const P='https://www.example.com/page';
  const L=(target,href,extra={})=>({target,href,download:false,namedFrame:false,...extra});
  a.ok(ST.retarget(L('_blank','https://other.example/x'),P,'all',false));a.ok(ST.retarget(L('_new','/local'),P,'all',false));
  a.ok(!ST.retarget(L('','https://other.example/'),P,'all',false));a.ok(!ST.retarget(L('_self','/x'),P,'all',false));
  a.ok(!ST.retarget(L('_blank','https://other.example/'),P,'all',true),'modifier keeps a new tab');
  a.ok(!ST.retarget(L('_blank','/file.zip',{download:true}),P,'all',false));
  a.ok(!ST.retarget(L('frame1','/x',{namedFrame:true}),P,'all',false));a.ok(ST.retarget(L('somewin','/x'),P,'all',false));
  a.ok(!ST.retarget(L('_blank','mailto:a@b.example'),P,'all',false));a.ok(!ST.retarget(L('_blank','javascript:void(0)'),P,'all',false));
  a.ok(!ST.retarget(L('_blank','https://example.com/other'),P,'other',false),'same site in other-only mode');
  a.ok(ST.retarget(L('_blank','https://news.example.org/'),P,'other',false));a.ok(!ST.retarget(null,P,'all',false))});
