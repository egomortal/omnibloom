// node --test addons/tests   (Twitch comfort: pure rules)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),path=require('node:path');
const C=require(path.join(__dirname,'..','bundled','omni-twitch-comfort','core.js'));
test('channel pages only',()=>{
  for(const p of['/somechannel','/some_channel/','/abc'])a.ok(C.isChannel(p),p);
  for(const p of['/','/directory','/settings','/somechannel/videos','/videos/123','/ab','/'+'x'.repeat(30),'/some-channel','/Directory'])a.ok(!C.isChannel(p),p)});
test('theatre only when the button would enter it',()=>{
  a.ok(C.wantTheatre('Theatre Mode (alt+t)',false));a.ok(!C.wantTheatre('Exit Theatre Mode (alt+t)',false));
  a.ok(!C.wantTheatre('Theatre Mode (alt+t)',true));a.ok(!C.wantTheatre('Fullscreen',false));a.ok(!C.wantTheatre(null,false))});
test('claim button by its exact name',()=>{
  a.ok(C.isClaim('Claim Bonus'));a.ok(C.isClaim(' claim bonus '));
  for(const b of['Claim','Claim Bonus now','Bonus','',null])a.ok(!C.isClaim(b),String(b))});
test('claims are rate limited',()=>{
  let r=C.limiter(0,[]);a.ok(r.ok);r=C.limiter(5e3,r.log);a.ok(!r.ok);r=C.limiter(11e3,r.log);a.ok(r.ok);
  const log=Array.from({length:60},(_,i)=>i*20e3);a.ok(!C.limiter(60*20e3,log).ok,'60 per hour');
  a.ok(C.limiter(3600e3+20e3*2,log).ok,'old ones age out')});
