// OMNI_DL_FOLDER_PLAY_V1 (D12): folder playback order.   node tests/test-folder-play.cjs
'use strict';
const a=require('node:assert/strict'),F=require('../worker/assets/folder-play.js');
let n=0;const t=(name,fn)=>{fn();n++;};
const id=k=>String(k).padStart(32,'0'),R=(k,name,extra={})=>({id:id(k),name,folder:'Show',place:'internal',kind:'video',...extra});
const rows=[R(1,'Episode 10.mp4'),R(2,'Episode 2.mp4'),R(3,'episode 1.mp4'),R(4,'Cover.jpg',{kind:'image'}),R(5,'Episode 3.mp4',{folder:'Other'}),
  R(6,'Episode 4.mp4',{place:'usb0'}),R(7,'Theme.m4a',{kind:'audio'}),{id:'bad',name:'x',folder:'Show',place:'internal',kind:'video'}];
const cur={place:'internal',folder:'Show'};
t('siblings: same place and folder, playable only, natural name order',()=>{
  a.deepEqual(F.siblings(rows,cur).map(r=>r.name),['episode 1.mp4','Episode 2.mp4','Episode 10.mp4','Theme.m4a']);
  a.deepEqual(F.siblings(null,cur),[]);a.deepEqual(F.siblings(rows,null),[]);});
t('next: in order stops at the end, repeat wraps, off stops',()=>{const L=F.siblings(rows,cur);
  a.equal(F.next(L,id(3),'order'),id(2));a.equal(F.next(L,id(2),'order'),id(1));a.equal(F.next(L,id(7),'order'),null);
  a.equal(F.next(L,id(7),'repeat'),id(3));a.equal(F.next(L,id(3),'off'),null);a.equal(F.next(L,'f'.repeat(32),'order'),id(3),'unknown current: from the top');
  a.equal(F.next([],id(1),'repeat'),null);});
t('shuffle never repeats the current file',()=>{const L=F.siblings(rows,cur);
  for(const r of[0,0.3,0.6,0.99])a.notEqual(F.next(L,id(2),'shuffle',()=>r),id(2));a.equal(F.next([L[0]],L[0].id,'shuffle',()=>0),null);});
t('modes cycle and persist; junk falls back to off',()=>{a.equal(F.cycle('off'),'order');a.equal(F.cycle('repeat'),'off');a.equal(F.cycle('x'),'order');
  const m=new Map(),s={getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v)};a.equal(F.load(s),'off');F.save(s,'shuffle');a.equal(F.load(s),'shuffle');
  m.set('omni-dl-folder-mode','evil');a.equal(F.load(s),'off');});
t('caption sidecars: same stem, .vtt only, bare first, languages checked, at most 4',()=>{
  const cur={place:'internal',folder:'Show',name:'My Film.mp4'};const S=(k,name,extra={})=>({id:id(k),name,folder:'Show',place:'internal',kind:'text',...extra});
  const got=F.sidecars([S(11,'My Film.fr.vtt'),S(12,'My Film.vtt'),S(13,'my film.EN.vtt'),S(14,'My Film.srt'),S(15,'Other.vtt'),S(16,'My Film.vtt',{folder:'Else'}),
    S(17,'My Film.not a lang.vtt'),S(18,'My Film.pt_BR.vtt'),S(19,'My Film.de.vtt'),S(20,'My Filmmaker.vtt')],cur);
  a.deepEqual(got.map(x=>x.label),['Captions','DE','EN','FR']);a.equal(got[0].id,id(12));a.equal(got[0].lang,'');
  a.deepEqual(F.sidecars(null,cur),[]);a.deepEqual(F.sidecars([S(1,'x.vtt')],{place:'internal',folder:'Show'}),[]);});
console.log('FOLDER PLAY PASS: '+n+' checks');
