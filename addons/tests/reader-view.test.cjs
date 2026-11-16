// node --test addons/tests   (article finder of the Reader view add-on on small HTML fixtures; no jsdom)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const R=require('../bundled/omni-reader-view/core.js'),{parse}=require('./mini-dom.cjs');
const load=(name,base)=>parse(fs.readFileSync(path.join(__dirname,'fixtures',name),'utf8'),base);
const flat=items=>items.map(x=>typeof x==='string'?x:flat(x.kids)).join('');
const find=(items,tag,out=[])=>{for(const x of items)if(typeof x!=='string'){if(x.tag===tag)out.push(x);find(x.kids,tag,out)}return out};

test('news article: story body wins over comments, related links and navigation',()=>{
  const r=R.extract(load('reader-news.html','https://news.example.org/2026/11/bridge'));
  a.ok(r&&r.isArticle);a.equal(r.title,'Harbour bridge reopens after two years of repairs');a.equal(r.byline,'Mara Lindqvist');a.equal(r.site,'The Coastal Times');a.equal(r.lang,'en');
  a.equal(r.best.localName,'article');
  const text=flat(r.content);
  a.match(text,/reopened to traffic on Monday/);a.match(text,/temporary ferry/);a.match(text,/What changes for drivers/);
  for(const bad of[/Related stories/,/Finally, about time/,/All rights reserved/,/Weather/,/must, never, count/,/Share/,/By Mara/])a.doesNotMatch(text,bad);
  a.equal(find(r.content,'h2').filter(h=>/Harbour bridge reopens/.test(flat(h.kids))).length,0,'the title is not repeated');
  const imgs=find(r.content,'img');a.equal(imgs.length,1);a.equal(imgs[0].attrs.src,'https://news.example.org/img/bridge-1600.jpg','lazy data-src wins over the placeholder');a.equal(imgs[0].attrs.alt,'The bridge at dawn');
  a.ok(r.paragraphs>=5&&r.minutes>=1);
});
test('blog laid out with bare divs: text divs count as paragraphs, srcset gives the large image',()=>{
  const r=R.extract(load('reader-blog-divs.html','https://notes.example.net/2026/oslo'));
  a.ok(r&&r.isArticle,JSON.stringify(r&&{p:r.paragraphs,l:r.length}));
  a.equal(r.title,'A slow week in Oslo, by train and on foot');a.equal(r.byline,'Written by Teodor Berg');
  a.match(R.textOf(r.best),/night train north/);
  const text=flat(r.content);a.match(text,/cinnamon buns/);a.doesNotMatch(text,/Lisbon in three days/);a.doesNotMatch(text,/Archive/);a.doesNotMatch(text,/Written by/);
  a.equal(find(r.content,'img')[0].attrs.src,'https://notes.example.net/p/opera-1280.jpg');
});
test('front page of short linked teasers is not an article (no floating button)',()=>{
  const r=R.extract(load('reader-listing.html'));a.ok(!r||!r.isArticle,JSON.stringify(r&&{p:r.paragraphs,l:r.length}));
});
test('only http(s) links and images survive; scripts and handlers never reach the output',()=>{
  const doc=parse('<html><body><article><p>'+'Long enough sentence, with commas, to score as a paragraph. '.repeat(4)+'<a href="javascript:alert(1)">bad</a> <a href="/ok">good</a> <img src="javascript:x" onerror="alert(1)"><img src="/i.png" width="40"></p>'+('<p>'+'More plain text, more commas, more words to read. '.repeat(5)+'</p>').repeat(3)+'<script>alert(1)</script></article></body></html>','https://site.example/a/');
  const r=R.extract(doc),links=find(r.content,'a');
  a.deepEqual(links.map(l=>l.attrs.href),['https://site.example/ok']);a.equal(find(r.content,'img').length,0);
  a.doesNotMatch(JSON.stringify(r.content),/onerror|alert|javascript/);
});
test('hidden and aria-hidden parts are skipped; empty documents give null',()=>{
  const doc=parse('<body><div class="content">'+('<p>'+'Visible words, plenty of them, in a calm sentence. '.repeat(4)+'</p>').repeat(4)+'<p hidden>'+'Secret text, secret text. '.repeat(10)+'</p><div aria-hidden="true"><p>'+'Ghost words, ghost words. '.repeat(10)+'</p></div></div></body>');
  const text=flat(R.extract(doc).content);a.match(text,/Visible words/);a.doesNotMatch(text,/Secret|Ghost/);
  a.equal(R.extract(parse('<html><head></head><body></body></html>')),null);
});
