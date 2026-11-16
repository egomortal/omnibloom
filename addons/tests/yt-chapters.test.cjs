// node --test addons/tests   (YouTube chapters: pure parsing and navigation)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),path=require('node:path');
const C=require(path.join(__dirname,'..','bundled','omni-yt-chapters','core.js'));
test('timestamps parse and print',()=>{a.equal(C.seconds('0:00'),0);a.equal(C.seconds('12:34'),754);a.equal(C.seconds('1:02:03'),3723);
  for(const b of['','1:2','1:60','99','a:bc','1:60:00'])a.ok(Number.isNaN(C.seconds(b)),b);a.equal(C.clock(3723),'1:02:03');a.equal(C.clock(65),'1:05')});
test('description chapters follow YouTube rules',()=>{
  const d='Thanks for watching!\n0:00 Intro\n(1:30) - The setup\nPart three 3:00\n10:05 Outro\nlink: https://x.example/?t=1:23';
  a.deepEqual(C.fromDescription(d),[{t:0,title:'Intro'},{t:90,title:'The setup'},{t:180,title:'Part three'},{t:605,title:'Outro'}]);
  a.deepEqual(C.fromDescription('1:00 a\n2:00 b\n3:00 c'),[],'must start at 0:00');
  a.deepEqual(C.fromDescription('0:00 a\n1:00 b'),[],'at least three');
  a.deepEqual(C.fromDescription('0:00 a\n0:05 b\n1:00 c'),[],'each at least 10 s');
  a.deepEqual(C.fromDescription(''),[]);a.deepEqual(C.fromDescription(null),[])});
test('markers win, deduped and sorted; titles cleaned and capped',()=>{
  const m=C.fromMarkers([{title:' Two ',time:'2:00'},{title:'Start',time:'0:00'},{title:'dup',time:'2:00'},{title:'x'.repeat(300),time:'5:00'},{title:'bad',time:'zz'}]);
  a.deepEqual(m.map(x=>x.t),[0,120,300]);a.equal(m[1].title,'Two');a.equal(m[2].title.length,120);a.deepEqual(C.fromMarkers([{title:'a',time:'1:00'}]),[])});
test('next / previous chapter',()=>{const L=[{t:0},{t:60},{t:120}];
  a.equal(C.next(L,0),60);a.equal(C.next(L,59.5),60);a.equal(C.next(L,59.9),120,'0.25 s tolerance: just seeked to 60');a.equal(C.next(L,60),120);a.equal(C.next(L,130),null);
  a.equal(C.prev(L,70),60);a.equal(C.prev(L,61),0);a.equal(C.prev(L,1),0);a.equal(C.index(L,119.8),2)});
