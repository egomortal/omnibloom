// OMNI_SAVE_IMAGE_V1: the hold-Cross hit-test script of a patched OmniContextMenu.h, assembled the way
// omniFxContextQuery does it (head + template minus its trailing "(" / "()" + "(X,Y);})()"), run on mock DOMs.
//   node test_save_image_js.cjs <tree>/engine/entry/OmniContextMenu.h
'use strict';
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').replace(/\r\n/g, '\n');
let js = /R"JS\(([\s\S]*?)\)JS"/.exec(src)[1];
if (js.endsWith('()')) js = js.slice(0, -2); else if (js.endsWith('(')) js = js.slice(0, -1);
js = '(function(){var X=100.0,Y=50.0;return ' + js + '(X,Y);})()';
new Function(js);   // syntax

let fails = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };

const win = { innerWidth: 1280, innerHeight: 720, getComputedStyle: (e) => ({ backgroundImage: e.bg || 'none' }) };
const doc = { defaultView: win };
function el(tag, o = {}) {
  const e = Object.assign({ tagName: tag, ownerDocument: doc, title: '', parent: null, attrs: {},
    getAttribute(k) { return this.attrs[k] || null; },
    getBoundingClientRect() { return this.rect || { left: 0, top: 0, width: 200, height: 100 }; },
    closest(sel) { for (let n = this; n; n = n.parent) if (sel === 'a[href]' && n.tagName === 'A' && n.href) return n; return null; },
    querySelector() { return this.child || null; } }, o);
  return e;
}
function run(stack) {
  const document = { elementsFromPoint: () => stack, elementFromPoint: () => stack[0] };
  const window = win;
  return JSON.parse(new Function('document', 'window', 'getComputedStyle', 'return ' + js)(document, window, win.getComputedStyle));
}

const body = el('BODY', { bg: 'url("https://example.com/page-bg.jpg")' });
const html = el('HTML');
// <img>
let r = run([el('IMG', { currentSrc: 'https://example.com/cat.jpg', alt: ' A  cat ' }), body, html]);
check(r.img === 'https://example.com/cat.jpg' && r.alt === 'A cat', 'img: ' + JSON.stringify(r));
// link around an image
const a = el('A', { href: 'https://example.com/page', innerText: 'Cat page' });
const img = el('IMG', { src: 'https://example.com/c.png', alt: '', parent: a });
r = run([img, a, body, html]);
check(r.link === 'https://example.com/page' && r.text === 'Cat page' && r.img === 'https://example.com/c.png', 'link+img: ' + JSON.stringify(r));
// background image on a card
r = run([el('DIV', { bg: 'linear-gradient(red, blue), url("https://cdn.example.com/hero.webp")', attrs: { 'aria-label': 'Hero' } }), body, html]);
check(r.img === 'https://cdn.example.com/hero.webp' && r.alt === 'Hero', 'background: ' + JSON.stringify(r));
// page-wide backdrop and body background are not images
r = run([el('DIV', { bg: 'url("https://example.com/wall.jpg")', rect: { left: 0, top: 0, width: 1280, height: 700 } }), body, html]);
check(!r.img, 'backdrop: ' + JSON.stringify(r));
r = run([el('P'), body, html]);
check(!r.img && !r.link, 'body bg: ' + JSON.stringify(r));
// data: background is not offered
r = run([el('SPAN', { bg: 'url("data:image/png;base64,AAAA")' }), body, html]);
check(!r.img, 'data bg: ' + JSON.stringify(r));
// a video stops the search (no background taken)
r = run([el('VIDEO', { currentSrc: 'https://example.com/v.mp4' }), el('DIV', { bg: 'url("https://example.com/poster.jpg")' }), body]);
check(r.video === 'https://example.com/v.mp4' && !r.img, 'video: ' + JSON.stringify(r));
// javascript: links are not links
r = run([el('A', { href: 'javascript:void(0)' }), body]);
check(!r.link, 'javascript: ' + JSON.stringify(r));
// empty point
r = run([]);
check(Object.keys(r).length === 0, 'empty: ' + JSON.stringify(r));

console.log((fails ? 'FAILED' : 'ok') + ': ' + checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
