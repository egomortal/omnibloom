// node --test addons/tests   (Image gallery: pure picking rules)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),path=require('node:path');
const G=require(path.join(__dirname,'..','bundled','omni-image-gallery','core.js'));
const B='https://example.com/gallery/page.html';
test('largest srcset candidate',()=>{
  a.equal(G.bestFromSrcset('a.jpg 480w, b.jpg 1080w, c.jpg 720w'),'b.jpg');a.equal(G.bestFromSrcset('a.jpg 1x, b.jpg 2x'),'b.jpg');
  a.equal(G.bestFromSrcset('only.jpg'),'only.jpg');a.equal(G.bestFromSrcset(''),null);a.equal(G.bestFromSrcset(null),null)});
test('picks large images, lazy ones too, deduped, absolute, no svg or data:',()=>{
  const out=G.pick([{src:'big.jpg',w:800,h:600},{src:'icon.png',w:32,h:32,nw:32,nh:32},{src:'big.jpg#x',w:800,h:600},
    {src:'blank.gif',dataSrc:'lazy.jpg',w:0,h:0},{src:'p.jpg',srcset:'p-s.jpg 400w, p-l.jpg 1600w',nw:400,nh:300},
    {src:'logo.svg',w:900,h:300},{src:'data:image/png;base64,AAAA',w:900,h:900},{src:'javascript:x',w:900,h:900},null],B);
  a.deepEqual(out,['https://example.com/gallery/big.jpg','https://example.com/gallery/lazy.jpg','https://example.com/gallery/p-l.jpg'])});
test('capped at 300',()=>{const many=Array.from({length:400},(_,k)=>({src:'i'+k+'.jpg',w:300,h:300}));a.equal(G.pick(many,B).length,300)});
test('wrap and the decode window',()=>{a.equal(G.wrap(-1,5),4);a.equal(G.wrap(5,5),0);a.equal(G.wrap(3,0),0);
  a.deepEqual(G.keep(0,5),[0,1]);a.deepEqual(G.keep(4,5),[4,0]);a.deepEqual(G.keep(0,1),[0]);a.deepEqual(G.keep(0,0),[])});
