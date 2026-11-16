// node --test addons/tests   (Break reminder: pure counting rules)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),path=require('node:path');
const B=require(path.join(__dirname,'..','bundled','omni-break-reminder','core.js'));
const T0=new Date(2026,10,16,20,0,0).getTime();
test('active minutes: visible and (playing or recent input)',()=>{
  a.ok(B.active(true,true,0,T0));a.ok(B.active(true,false,T0-60e3,T0));a.ok(!B.active(true,false,T0-180e3,T0));a.ok(!B.active(false,true,T0,T0))});
test('counting, a reminder every N active minutes, snooze, new day',()=>{
  let s=null;for(let i=0;i<59;i++)s=B.tick(s,T0+i*60e3,true);a.ok(!B.due(s,'60',T0));
  s=B.tick(s,T0+59*60e3,true);a.equal(s.mins,60);a.ok(B.due(s,'60',T0+3600e3));a.ok(B.due(s,'30',T0));
  s=B.shown(s);a.ok(!B.due(s,'60',T0));s=B.tick(s,T0+3700e3,false);a.equal(s.mins,60,'inactive minute not counted');
  for(let i=0;i<60;i++)s=B.tick(s,T0+3800e3+i*60e3,true);a.ok(B.due(s,'60',T0+8000e3));
  s=B.snooze(s,T0+8000e3,15);for(let i=0;i<65;i++)s=B.tick(s,T0+8100e3+i*60e3,true);
  a.ok(!B.due(s,'60',T0+8000e3+10*60e3),'snoozed');a.ok(B.due(s,'60',T0+8000e3+16*60e3+3600e3));
  const next=B.tick(s,T0+86400e3,true);a.equal(next.mins,1);a.notEqual(next.day,s.day);a.equal(B.due({day:'x',mins:5,since:0},'bogus',0),false)});
test('friendly durations',()=>{a.equal(B.text(45),'45 minutes');a.equal(B.text(60),'1 hour');a.equal(B.text(90),'1 hour 30 min');a.equal(B.text(120),'2 hours')});
