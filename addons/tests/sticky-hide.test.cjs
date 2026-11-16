// node --test addons/tests   (Sticky bar hider: pure rules)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),path=require('node:path');
const S=require(path.join(__dirname,'..','bundled','omni-sticky-hide','core.js'));
const win={w:1920,h:1080},R=(top,h,w=1920)=>({top,bottom:top+h,width:w,height:h});
test('bars: wide, short, at an edge, fixed or sticky',()=>{
  a.equal(S.isBar(R(0,80),win,'fixed','HEADER',null),'top');a.equal(S.isBar(R(1000,80),win,'sticky','DIV',null),'bottom');
  a.equal(S.isBar(R(0,80),win,'static','DIV',null),false);a.equal(S.isBar(R(0,80,600),win,'fixed','DIV',null),false,'narrow');
  a.equal(S.isBar(R(0,600),win,'fixed','DIV',null),false,'tall overlay');a.equal(S.isBar(R(400,80),win,'fixed','DIV',null),false,'middle');
  a.equal(S.isBar(R(0,80),win,'fixed','DIALOG',null),false);a.equal(S.isBar(R(0,80),win,'fixed','DIV','alertdialog'),false);
  a.equal(S.isBar(R(0,80),win,'fixed','VIDEO',null),false);a.equal(S.isBar({top:0,bottom:0,width:0,height:0},win,'fixed','DIV',null),false)});
test('scroll direction with dead zones',()=>{let s={hidden:false,anchor:0};
  s=S.decide(s,50);a.equal(s.hidden,false,'near the top');s=S.decide(s,70);a.equal(s.hidden,false,'20 px: inside the dead zone');
  s=S.decide(s,130);a.equal(s.hidden,true,'30 px down past the anchor');s=S.decide(s,400);a.equal(s.hidden,true);
  s=S.decide(s,395);a.equal(s.hidden,true,'5 px up: still hidden');
  s=S.decide(s,380);a.equal(s.hidden,false,'15 px up from the turning point');s=S.decide(s,10);a.equal(s.hidden,false)});
