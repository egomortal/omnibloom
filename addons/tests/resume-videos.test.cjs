// node --test addons/tests   (logic of the Resume videos add-on; no browser needed)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),C=require('../bundled/omni-resume-videos/core.js');

test('normalizer drops tracking and start-time parameters, keeps the page identity',()=>{
  a.equal(C.normalize('https://www.Example.com/watch/ep-4/?utm_source=x&b=2&fbclid=abc&a=1#comments'),'example.com/watch/ep-4?a=1&b=2');
  a.equal(C.normalize('http://example.com/watch/ep-4?a=1&b=2&gclid=z&t=95'),'example.com/watch/ep-4?a=1&b=2');
  a.equal(C.normalize('https://example.com/v?id=7&start=1m30s&si=xyz'),'example.com/v?id=7');
  a.equal(C.normalize('https://example.com/v?t=intro'),'example.com/v?t=intro','a non-time t= is kept');
  a.equal(C.normalize('https://tv.example.com/#/show/12/ep/3'),'tv.example.com/#/show/12/ep/3','hash routes are kept');
  a.equal(C.normalize('https://example.com:8443//a//b/'),'example.com:8443/a/b');
  a.equal(C.normalize('https://example.com/'),'example.com/');
  a.equal(C.normalize('ftp://example.com/x'),null);a.equal(C.normalize('not a url'),null);a.equal(C.normalize('blob:https://example.com/1'),null);
});
test('keys are stable, short, address-free and differ per video index',()=>{
  const u=C.normalize('https://example.com/movie?id=1'),k=C.key(u,0);
  a.equal(k,C.key(u,0));a.notEqual(k,C.key(u,1));a.notEqual(k,C.key(C.normalize('https://example.com/movie?id=2'),0));
  a.ok(k.startsWith(C.PREFIX)&&k.length<=128);a.ok(!k.includes('example'));
  a.equal(C.key(C.normalize('https://example.com/movie?id=1&utm_medium=mail'),0),k);
});
test('only videos over 3 minutes are kept; the last 30 s forget the entry',()=>{
  a.equal(C.saveAction(100,180,false),'skip');a.equal(C.saveAction(100,Infinity,false),'skip');a.equal(C.saveAction(100,NaN,false),'skip');
  a.equal(C.saveAction(10,600,false),'skip','barely started');a.equal(C.saveAction(300,600,false),'store');
  a.equal(C.saveAction(571,600,false),'remove');a.equal(C.saveAction(200,600,true),'remove');
  a.deepEqual(C.entry(1421.7,3600.4,1700000000999),[1421,3600,1700000000]);
});
test('offer only near the start of the same video, never past the end margin',()=>{
  const e=[1421,3600,1];
  a.equal(C.decide(e,3600,0),1421);a.equal(C.decide(e,3640,4),1421,'2% length drift allowed');
  a.equal(C.decide(e,3600,45),null,'site already resumed or user seeked');a.equal(C.decide(e,1800,0),null,'different video');
  a.equal(C.decide([3580,3600,1],3600,0),null);a.equal(C.decide([20,3600,1],3600,0),null);
  a.equal(C.decide(undefined,3600,0),null);a.equal(C.decide(['x',3600,1],3600,0),null);a.equal(C.decide(e,120,0),null);
});
test('pruning keeps the newest 200 entries and ignores other keys',()=>{
  const all={'settings-note':1};for(let i=0;i<230;i++)all[C.PREFIX+'k'+i]=[60,600,1000+i];all[C.PREFIX+'broken']='junk';
  const drop=C.prune(all);a.equal(drop.length,31);a.ok(drop.includes(C.PREFIX+'broken'));
  for(let i=0;i<30;i++)a.ok(drop.includes(C.PREFIX+'k'+i));a.ok(!drop.includes(C.PREFIX+'k30'));a.ok(!drop.includes('settings-note'));
  a.deepEqual(C.prune({[C.PREFIX+'a']:[1,2,3]}),[]);
});
test('clock text for the prompt',()=>{a.equal(C.clock(1421),'23:41');a.equal(C.clock(59.9),'0:59');a.equal(C.clock(3723),'1:02:03')});
test('200 entries fit easily in Omni add-on storage (256 KB, 512 keys)',()=>{
  let bytes=0;for(let i=0;i<200;i++){const k=C.key('example.com/very/long/path/'+i+'?id='+'x'.repeat(200),0);bytes+=k.length+JSON.stringify(C.entry(86399,86400,Date.now())).length}
  a.ok(bytes<16*1024,String(bytes));
});
