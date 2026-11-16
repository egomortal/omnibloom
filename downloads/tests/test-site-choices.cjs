// OMNI_DL_SITE_CHOICES_V1 (D06): per-site form choices.   node tests/test-site-choices.cjs
'use strict';
const a=require('node:assert/strict'),S=require('../worker/assets/site-choices.js');
let n=0;const t=(name,fn)=>{fn();n++;};
function store(){const m=new Map();return{getItem:k=>m.has(k)?m.get(k):null,setItem:(k,v)=>m.set(k,String(v)),raw:m};}
t('site keys drop www/m/music, keep the rest, refuse non-http',()=>{
  a.equal(S.siteOf('https://www.youtube.com/watch?v=x'),'youtube.com');a.equal(S.siteOf('https://m.youtube.com/'),'youtube.com');
  a.equal(S.siteOf('https://music.youtube.com/'),'youtube.com');a.equal(S.siteOf('http://Example.org./a'),'example.org');
  a.equal(S.siteOf('https://media.example.org/x'),'media.example.org');
  for(const b of['ftp://x/y','javascript:alert(1)','not a url','',null])a.equal(S.siteOf(b),null,String(b));});
t('remember then lookup; only the host is stored',()=>{const s=store();
  a.ok(S.remember(s,'https://www.youtube.com/watch?v=secret123',{kind:'audio',engine:'ytdlp',type:'m4a',place:'usb1'},1000));
  a.deepEqual(S.lookup(s,'https://youtu.be.example/x'),null);
  const c=S.lookup(s,'https://m.youtube.com/watch?v=other');a.equal(c.site,'youtube.com');a.equal(c.kind,'audio');a.equal(c.type,'m4a');a.equal(c.place,'usb1');
  const raw=s.raw.get(S.STORE);a.ok(!/secret123|watch/.test(raw),raw);});
t('bad choices are refused or cleaned',()=>{const s=store();
  a.ok(!S.remember(s,'https://a.example/',{kind:'virus',engine:'ytdlp'}));a.ok(!S.remember(s,'https://a.example/',{kind:'video',engine:'curl'}));
  a.ok(S.remember(s,'https://a.example/',{kind:'video',engine:'ytdlp',type:'exe',place:'../etc'}));
  const c=S.lookup(s,'https://a.example/');a.equal(c.type,null);a.equal(c.place,null);});
t('tampered store falls back to nothing',()=>{const s=store();s.setItem(S.STORE,'{"bad host!":{"kind":"video","engine":"ytdlp"},"ok.example":{"kind":"x"}}');
  a.equal(S.lookup(s,'https://ok.example/'),null);s.setItem(S.STORE,'not json');a.equal(S.lookup(s,'https://ok.example/'),null);});
t('at most 200 sites, the oldest dropped; forget works',()=>{const s=store();
  for(let i=0;i<205;i++)S.remember(s,'https://site'+i+'.example/',{kind:'video',engine:'ytdlp'},i);
  a.equal(Object.keys(S.load(s)).length,200);a.equal(S.lookup(s,'https://site0.example/'),null);a.ok(S.lookup(s,'https://site204.example/'));
  a.ok(S.forget(s,'https://site204.example/a'));a.equal(S.lookup(s,'https://site204.example/'),null);a.ok(!S.forget(s,'https://nope.example/'));});
console.log('SITE CHOICES PASS: '+n+' checks');
