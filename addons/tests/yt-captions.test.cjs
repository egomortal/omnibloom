// node --test addons/tests   (YouTube captions on: pure rules)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),path=require('node:path');
const C=require(path.join(__dirname,'..','bundled','omni-yt-captions','core.js'));
const ID='dQw4w9WgXcQ';
test('video ids from watch, live and shorts pages only',()=>{
  a.equal(C.videoId('https://www.youtube.com/watch?v='+ID+'&t=5'),ID);a.equal(C.videoId('https://m.youtube.com/watch?v='+ID),ID);
  a.equal(C.videoId('https://www.youtube.com/shorts/'+ID),ID);a.equal(C.videoId('https://www.youtube.com/live/'+ID+'?si=x'),ID);
  for(const u of['https://www.youtube.com/','https://www.youtube.com/watch?v=short','https://youtube.com.evil.example/watch?v='+ID,'https://example.com/watch?v='+ID,'nope'])a.equal(C.videoId(u),null,u)});
test('press once, only an off and visible button',()=>{const h=new Set();
  a.ok(C.shouldPress({pressed:'false',display:'block'},h,ID));a.ok(!C.shouldPress({pressed:'true',display:'block'},h,ID));
  a.ok(!C.shouldPress({pressed:'false',display:'none'},h,ID),'no captions for this video');a.ok(!C.shouldPress({pressed:'false',hidden:true},h,ID));
  a.ok(!C.shouldPress(null,h,ID));a.ok(!C.shouldPress({pressed:'false'},h,null));h.add(ID);a.ok(!C.shouldPress({pressed:'false',display:'block'},h,ID),'user turned it off')});
