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
// ---- Continue watching (1.1.0): 'w:' entries Omni's start page lists ----
test('continue-watching entries: cleaned address, capped title, absolute og:image, same hash as the resume key',()=>{
  const n=C.normalize('https://www.example.com/watch/ep-4?id=9&utm_source=x');
  a.equal(C.watchKey(n,0),C.WATCH_PREFIX+C.key(n,0).slice(C.PREFIX.length));a.notEqual(C.watchKey(n,0),C.watchKey(n,1));
  a.equal(C.cleanHref('https://user:pw@www.example.com/watch/ep-4?id=9&utm_source=x&t=95&fbclid=1#comments'),'https://www.example.com/watch/ep-4?id=9');
  a.equal(C.cleanHref('https://tv.example.com/#/show/12'),'https://tv.example.com/#/show/12');
  a.equal(C.cleanHref('https://example.com/v?utm_medium=a'),'https://example.com/v');
  a.equal(C.cleanHref('javascript:alert(1)'),null);a.equal(C.cleanHref('https://example.com/'+'x'.repeat(3000)),null);
  const e=C.watchEntry({url:'https://example.com/film?id=1&gclid=z',title:'  A   long\nfilm  '+'y'.repeat(300),image:'/img/poster.jpg',position:1421.7,duration:3600.4,now:1700000000999});
  a.equal(e.u,'https://example.com/film?id=1');a.equal(e.t.length,160);a.ok(e.t.startsWith('A long film y')&&e.t.endsWith('…'));
  a.equal(e.i,'https://example.com/img/poster.jpg');a.equal(e.p,1421);a.equal(e.d,3600);a.equal(e.a,1700000000);
  a.equal(C.watchEntry({url:'https://e.com/v',title:'',image:'data:image/png;base64,AA',position:200,duration:600,now:0}).i,undefined,'only http(s) images');
  a.equal(C.watchEntry({url:'ftp://e.com/v',title:'x',position:200,duration:600,now:0}),null);
  a.ok(JSON.stringify(e).indexOf('\n')<0);
});
test('continue watching: not before 2 minutes, removed past 95 % or at the end, only long videos',()=>{
  a.equal(C.watchAction(119,3600,false),'skip');a.equal(C.watchAction(120,3600,false),'store');
  a.equal(C.watchAction(3420,3600,false),'remove');a.equal(C.watchAction(3419,3600,false),'store');a.equal(C.watchAction(500,3600,true),'remove');
  a.equal(C.watchAction(150,170,false),'skip','short clips never');a.equal(C.watchAction(300,Infinity,false),'skip','live streams never');
});
test('continue watching keeps the newest 30 and leaves resume entries alone',()=>{
  const all={};for(let i=0;i<40;i++)all[C.WATCH_PREFIX+'k'+i]={u:'https://e.com/'+i,t:'',p:200,d:600,a:1000+i};
  all[C.WATCH_PREFIX+'bad']={u:'javascript:x',p:1,d:2,a:9e9};all[C.PREFIX+'r']=[60,600,1];
  const drop=C.pruneWatch(all);a.equal(drop.length,11);a.ok(drop.includes(C.WATCH_PREFIX+'bad'));
  for(let i=0;i<10;i++)a.ok(drop.includes(C.WATCH_PREFIX+'k'+i));a.ok(!drop.includes(C.WATCH_PREFIX+'k10'));a.ok(!drop.includes(C.PREFIX+'r'));
});
test('200 resume + 30 continue-watching entries stay inside add-on storage (256 KB, 512 keys)',()=>{
  let bytes=0;for(let i=0;i<200;i++)bytes+=C.key('e/'+i,0).length+JSON.stringify(C.entry(86399,86400,Date.now())).length;
  for(let i=0;i<30;i++){const e=C.watchEntry({url:'https://example.com/'+'p'.repeat(2000)+i,title:'t'.repeat(400),image:'https://img.example.com/'+'i'.repeat(990),position:200,duration:600,now:Date.now()});
    a.ok(e&&e.i);bytes+=C.watchKey('e/'+i,0).length+JSON.stringify(e).length}
  a.ok(bytes<128*1024,String(bytes));a.ok(200+30<512);
});
// The page glue against a fake page: timeupdate/pause write both entries; private tabs (storage refused) write nothing more.
function runtimeHarness(opts){
  const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
  const store=new Map(),writes=[],handlers={};
  const api={id:'omni-resume-videos',active:true,onEnable(){},onDisable(){},storage:{get:k=>store.has(k)?JSON.parse(store.get(k)):undefined,keys:()=>[...store.keys()],
    set(k,v){writes.push(k);if(opts.private)return Promise.reject(new Error('error: private tab'));store.set(k,JSON.stringify(v));return Promise.resolve(true)},
    remove(k){if(opts.private)return Promise.reject(new Error('error: private tab'));store.delete(k);return Promise.resolve(true)}}};
  class HTMLVideoElement{constructor(){this.currentTime=0;this.duration=3600;this.paused=false;this.ended=false;this.readyState=0;this.currentSrc='https://cdn.example.com/v.mp4'}closest(){return null}}
  const video=new HTMLVideoElement();
  const document={title:'Episode 4 - Example TV',getElementsByTagName:()=>[video],addEventListener(t,f){handlers[t]=f},removeEventListener(){},
    querySelector:sel=>sel.includes('og:image')?{getAttribute:()=>'https://img.example.com/ep4.jpg'}:null,visibilityState:'visible'};
  const ctx={window:null,document,location:{href:opts.href||'https://www.example.com/watch/ep-4?utm_source=x'},HTMLVideoElement,addEventListener(){},removeEventListener(){},
    setInterval,clearInterval,URL,Promise,Date,Math,Object,JSON,String,Number,Array,Set,WeakMap,RegExp,Error};
  ctx.window=ctx;ctx.globalThis=ctx;ctx.omniAddon=api;vm.createContext(ctx);
  const dir=path.join(__dirname,'..','bundled','omni-resume-videos');
  vm.runInContext(fs.readFileSync(path.join(dir,'core.js'),'utf8'),ctx);vm.runInContext(fs.readFileSync(path.join(dir,'runtime.js'),'utf8'),ctx);
  return{store,writes,video,fire:t=>handlers[t]({type:t,target:video})};
}
test('page glue: pause after 2 minutes stores both entries; past 95 % / the end removes them',async()=>{
  const h=runtimeHarness({});h.video.currentTime=60;h.video.paused=true;h.fire('pause');await new Promise(r=>setImmediate(r));
  a.deepEqual([...h.store.keys()].map(k=>k.slice(0,2)),['r:'],'under 2 minutes: resume only');
  h.video.currentTime=1500;h.fire('pause');await new Promise(r=>setImmediate(r));
  const w=[...h.store.keys()].find(k=>k.startsWith('w:')),e=JSON.parse(h.store.get(w));
  a.equal(e.u,'https://www.example.com/watch/ep-4');a.equal(e.t,'Episode 4 - Example TV');a.equal(e.i,'https://img.example.com/ep4.jpg');a.equal(e.p,1500);a.equal(e.d,3600);
  h.video.currentTime=3500;h.fire('pause');await new Promise(r=>setImmediate(r));
  a.deepEqual([...h.store.keys()].map(k=>k.slice(0,2)),['r:'],'past 95 %: off the start page, the resume offer stays');
  h.video.currentTime=3590;h.fire('pause');await new Promise(r=>setImmediate(r));
  a.equal(h.store.size,0,'last 30 s: both entries gone');
});
test('page glue: a private tab (storage refused) stops writing after the first refusal',async()=>{
  const h=runtimeHarness({private:true});h.video.currentTime=1500;h.video.paused=true;h.fire('pause');await new Promise(r=>setImmediate(r));
  const n=h.writes.length;a.ok(n>=1&&n<=2);a.equal(h.store.size,0);
  h.video.currentTime=1700;h.fire('pause');await new Promise(r=>setImmediate(r));a.equal(h.writes.length,n,'no further writes');
});
