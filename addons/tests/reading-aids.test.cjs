// node --test addons/tests   (Remember reading position: pure rules; Readable font / Clear links: CSS sanity)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const B=path.join(__dirname,'..','bundled'),M=require(path.join(B,'omni-scroll-memory','core.js'));
test('page keys: hashed, same article same key, junk refused',()=>{
  const k=M.keyFor('https://news.example.com/2026/story?utm_source=x&id=42#c3');a.match(k,/^p[0-9a-f]{16}$/);
  a.equal(k,M.keyFor('https://news.example.com/2026/story?id=42&ref=abc'),'tracking / fragment ignored');
  a.notEqual(k,M.keyFor('https://news.example.com/2026/story?id=43'));a.notEqual(k,M.keyFor('https://news.example.com/2026/other?id=42'));
  for(const b of['ftp://x/y','about:blank','not a url'])a.equal(M.keyFor(b),null,b);a.ok(!/news|story/.test(k))});
test('worth remembering, fractions, freshness, trim',()=>{
  a.ok(M.worth(3000,10000,1000));a.ok(!M.worth(500,10000,1000),'still on the first screen');a.ok(!M.worth(9900,10000,1000),'finished');
  a.ok(!M.worth(1500,1500,1000),'short page');a.equal(M.fraction(2500,10000),0.25);a.equal(M.fraction(5,0),0);
  a.equal(M.restoreY(0.25,8000),2000);a.equal(M.restoreY(7,8000),8000);a.equal(M.restoreY('x',8000),0);
  const now=1e12;a.ok(M.fresh({f:0.4,t:now-864e5},now));a.ok(!M.fresh({f:0.4,t:now-31*864e5},now));a.ok(!M.fresh({f:1,t:now},now));a.ok(!M.fresh(null,now));
  const map={};for(let i=0;i<320;i++)map['p'+String(i).padStart(16,'0')]={f:0.5,t:i};map.bad={f:1,t:1e15};
  const out=M.trim(map);a.equal(Object.keys(out).length,300);a.ok(!('bad' in out));a.ok(!('p0000000000000000' in out))});
test('CSS add-ons never touch icons, code or form text with the face rule',()=>{
  const css=fs.readFileSync(path.join(B,'omni-readable-font','addon.css'),'utf8');
  for(const x of[':not(i)',':not(code)',':not(pre)','[class*="icon"]'])a.ok(css.includes(x),x);a.ok(!/input|textarea|select/.test(css.split('font-family')[0]));
  const links=fs.readFileSync(path.join(B,'omni-clear-links','addon.css'),'utf8');a.ok(/:focus\{/.test(links));a.ok(/outline:4px/.test(links))});
