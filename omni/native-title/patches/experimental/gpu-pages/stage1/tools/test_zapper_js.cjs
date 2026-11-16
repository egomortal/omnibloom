// OMNI_ZAPPER_V1: the page script (OmniZapper::kCore) on a fake DOM: picking, grow / shrink, the selector generator,
// page-only hide / unhide, the outline box. Run: ./t core.js && node test_zapper_js.cjs core.js
'use strict';
const fs = require('fs');
const vm = require('vm');
const core = fs.readFileSync(process.argv[2], 'utf8');
let fails = 0, checks = 0;
function check(c, what) { ++checks; if (!c) { ++fails; console.error('FAIL ' + what); } }

// --- a small DOM -----------------------------------------------------------------------------------------------------
class Style {
  constructor() { this.p = {}; }
  setProperty(k, v, pr) { this.p[k] = { v: String(v), pr: pr || '' }; }
  getPropertyValue(k) { return this.p[k] ? this.p[k].v : ''; }
  getPropertyPriority(k) { return this.p[k] ? this.p[k].pr : ''; }
  removeProperty(k) { delete this.p[k]; }
  set cssText(t) { this.p = {}; this.raw = t; }
}
class El {
  constructor(tag, attrs) {
    this.tagName = tag.toUpperCase(); this.nodeType = 1; this.children = []; this.parentElement = null; this.parentNode = null;
    this.id = (attrs && attrs.id) || ''; this.className = (attrs && attrs.cls) || ''; this.style = new Style(); this.attrs = {};
    this.rect = (attrs && attrs.rect) || { left: 0, top: 0, width: 100, height: 20 };
  }
  appendChild(c) { c.parentElement = this.nodeType === 1 && this.tagName !== '#DOC' ? this : null; c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentElement = null; c.parentNode = null; return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k === 'class' ? this.className : (this.attrs[k] === undefined ? null : this.attrs[k]); }
  getBoundingClientRect() { const r = this.rect; return { left: r.left, top: r.top, width: r.width, height: r.height }; }
  get isConnected() { let e = this; while (e.parentNode) e = e.parentNode; return e === doc; }
  matches(sel) { return matchSel(this, parseSel(sel)); }
}
function parseCompound(s) {
  const m = /^([a-z][a-z0-9-]*)?((?:[#.][A-Za-z_-][A-Za-z0-9_-]*)*)(?::nth-of-type\((\d+)\))?$/.exec(s);
  if (!m || s === '') throw new Error('SyntaxError: ' + s);
  const c = { tag: m[1] || null, id: null, cls: [], nth: m[3] ? +m[3] : 0 };
  (m[2].match(/[#.][^#.]+/g) || []).forEach(t => { if (t[0] === '#') c.id = t.slice(1); else c.cls.push(t.slice(1)); });
  return c;
}
function parseSel(sel) {
  if (typeof sel !== 'string' || !sel.trim()) throw new Error('SyntaxError');
  return sel.split(' > ').map(parseCompound);
}
function matchCompound(e, c) {
  if (!e || e.nodeType !== 1) return false;
  if (c.tag && e.tagName.toLowerCase() !== c.tag) return false;
  if (c.id && e.id !== c.id) return false;
  const cl = String(e.className).split(/\s+/);
  for (const x of c.cls) if (cl.indexOf(x) < 0) return false;
  if (c.nth) {
    const p = e.parentElement; if (!p) return false;
    const same = p.children.filter(x => x.tagName === e.tagName);
    if (same.indexOf(e) + 1 !== c.nth) return false;
  }
  return true;
}
function matchSel(e, parts) {
  if (!matchCompound(e, parts[parts.length - 1])) return false;
  let cur = e;
  for (let i = parts.length - 2; i >= 0; i--) { cur = cur.parentElement; if (!matchCompound(cur, parts[i])) return false; }
  return true;
}
function all(root) { const out = []; (function walk(e) { for (const c of e.children) { out.push(c); walk(c); } })(root); return out; }
let doc, html, body, hitList;
function newDoc() {
  doc = { tagName: '#DOC', nodeType: 9, children: [], appendChild: El.prototype.appendChild, removeChild: El.prototype.removeChild };
  html = new El('html'); doc.appendChild(html); html.parentElement = null;
  body = new El('body'); html.appendChild(body);
  doc.documentElement = html; doc.body = body;
  doc.createElement = t => new El(t);
  doc.querySelectorAll = sel => { const p = parseSel(sel); return all(html).filter(e => matchSel(e, p)); };
  doc.elementsFromPoint = () => hitList;
  return doc;
}
function el(parent, tag, attrs) { return parent.appendChild(new El(tag, attrs)); }
function chain(e) { const out = []; while (e && e.nodeType === 1) { out.push(e); e = e.parentElement; } return out; }   // innermost first

// --- running the script --------------------------------------------------------------------------------------------
let ctx;
function freshWindow() { ctx = { document: doc, JSON, Math, String, Object }; ctx.window = ctx; vm.createContext(ctx); }
function run(op, x, y, sel) { const f = vm.runInContext('(' + core + ')', ctx); return JSON.parse(f(op, x || 0, y || 0, sel || '')); }
function pick(target) { hitList = chain(target); return run('start', 5, 5); }
const generatedShape = s => /^[A-Za-z0-9_#.:()> -]+$/.test(s) && !/ {2}/.test(s) && !/[ >]$/.test(s) && s.length <= 280;
function shapeOk(r, what) { check(r.sel === '' || generatedShape(r.sel), what + ': shape ' + r.sel); }

// 1. stable unique id on the parent; grow / shrink; edges; the box
newDoc(); freshWindow();
const main = el(body, 'main');
for (let i = 0; i < 3; i++) el(main, 'span');
const banner = el(body, 'div', { id: 'cookie-banner', rect: { left: 0, top: 600, width: 1280, height: 120 } });
const bspan = el(banner, 'span');
let r = pick(bspan);
check(r.ok === 1 && r.sel === '#cookie-banner > span' && r.n === 1 && r.i === 0 && r.top === 1, '1 start ' + JSON.stringify(r));
shapeOk(r, '1');
const box = html.children.find(c => c.attrs && c.attrs['data-omni-zap'] === '1');
check(!!box && box.style.getPropertyValue('top') === '0px' && box.style.getPropertyValue('height') === '20px', '1 box placed');
r = run('up');
check(r.ok === 1 && r.sel === '#cookie-banner' && r.label === 'div#cookie-banner' && r.w === 1280 && r.h === 120 && r.i === 1 && !r.edge, '1 up ' + JSON.stringify(r));
check(box.style.getPropertyValue('height') === '120px', '1 box follows');
r = run('up');
check(r.ok === 1 && r.edge === 1 && r.i === 1, '1 up at the top (body is never picked) ' + JSON.stringify(r));
r = run('down'); r = run('down');
check(r.ok === 1 && r.edge === 1 && r.i === 0, '1 down at the bottom ' + JSON.stringify(r));
// the box itself is never picked (pointer-events none in a real page; first in the hit list here)
hitList = [box].concat(chain(bspan));
r = run('move', 5, 5);
check(r.ok === 1 && r.i === 0 && r.sel === '#cookie-banner > span', '1 box skipped ' + JSON.stringify(r));
// move over the same element keeps the depth; another element starts again at the innermost
run('up');
hitList = chain(bspan); r = run('move', 6, 6);
check(r.i === 1, '1 same element keeps depth');
hitList = chain(main.children[1]); r = run('move', 7, 7);
check(r.i === 0 && r.sel === 'span:nth-of-type(2)' && r.n === 1, '1 other element ' + JSON.stringify(r));   // the banner's span is the 1st of its type
hitList = chain(main.children[0]); r = run('move', 8, 8);
check(r.i === 0 && r.sel === 'main > span:nth-of-type(1)' && r.n === 1, '1 nth needs the parent ' + JSON.stringify(r));
r = run('sync');
check(r.ok === 1, '1 sync');
r = run('clear');
check(r.ok === 1 && !html.children.some(c => c.attrs && c.attrs['data-omni-zap']), '1 clear removes the box');

// 2. generated classes / ids are skipped; stable classes preferred
newDoc(); freshWindow();
const ad = el(body, 'div', { cls: 'css-1x2y3z sc-bdVaJa ad-slot', id: 'r12345' });
el(body, 'div', { cls: 'other' });
r = pick(ad);
check(r.sel === '.ad-slot' && r.n === 1 && r.label === 'div.ad-slot', '2 stable class ' + JSON.stringify(r));
const gen = el(body, 'section', { cls: 'x1n2onr6 xDqPmWbZ', id: ':r1:' });
el(body, 'section');
r = pick(gen);
check(r.sel === 'section:nth-of-type(1)' && r.n === 1, '2 generated skipped, nth used ' + JSON.stringify(r));
shapeOk(r, '2');
const twoCls = el(body, 'aside', { cls: 'sticky promo bottom' });
el(body, 'aside', { cls: 'sticky' });
r = pick(twoCls);
check(r.sel === '.sticky.promo', '2 at most two classes ' + JSON.stringify(r));

// 3. repeated structure: no unique selector within 4 levels -> n > 10 (the shell asks first)
newDoc(); freshWindow();
let deep = null;
for (let i = 0; i < 12; i++) {
  const s = el(body, 'section'), a = el(s, 'article'), d = el(a, 'div'), p = el(d, 'p'), sp = el(p, 'span');
  if (i === 4) deep = sp;
}
r = pick(deep);
check(r.ok === 1 && r.sel === 'article > div > p > span' && r.n === 12, '3 four levels at most ' + JSON.stringify(r));
check(r.sel.split(' > ').length <= 4, '3 depth cap');
r = run('up'); r = run('up'); r = run('up'); r = run('up');
check(r.sel === 'section:nth-of-type(5)' && r.n === 1, '3 grown to the section ' + JSON.stringify(r));

// 4. hide / unhide restore the element's own inline display
newDoc(); freshWindow();
const x1 = el(body, 'div', { cls: 'nag' }), x2 = el(body, 'div', { cls: 'nag' });
x1.style.setProperty('display', 'flex', '');
r = run('hide', 0, 0, '.nag');
check(r.ok === 1 && r.n === 2, '4 hide count');
check(x1.style.getPropertyValue('display') === 'none' && x1.style.getPropertyPriority('display') === 'important' && x2.style.getPropertyValue('display') === 'none', '4 hidden');
r = run('unhide', 0, 0, '.nag');
check(r.ok === 1 && r.n === 2 && x1.style.getPropertyValue('display') === 'flex' && x2.style.getPropertyValue('display') === '', '4 restored');
r = run('unhide', 0, 0, '.nag');
check(r.ok === 0, '4 nothing left to unhide');
r = run('hide', 0, 0, 'div{');
check(r.ok === 0, '4 a bad selector fails cleanly');

// 5. nothing usable under the pointer; a lost element; a new document drops the old state
newDoc(); freshWindow();
hitList = [body, html];
r = run('start', 1, 1);
check(r.ok === 0, '5 body only');
const gone = el(body, 'div', { id: 'gone' });
r = pick(gone);
check(r.ok === 1 && r.sel === '#gone', '5 picked');
body.removeChild(gone);
r = run('sync');
check(r.ok === 0, '5 sync after removal');
r = run('up');
check(r.ok === 0, '5 up after removal');
const old = ctx.__omniZapV1;
newDoc(); ctx.document = doc;
const fresh = el(body, 'p', { id: 'fresh' });
r = pick(fresh);
check(r.ok === 1 && ctx.__omniZapV1 !== old, '5 new document, new state');

// 6. the generated selector always matches the picked element; every answer has the shape the shell accepts
newDoc(); freshWindow();
const ul = el(body, 'ul', { cls: 'list' });
const items = [];
for (let i = 0; i < 5; i++) items.push(el(ul, 'li', { cls: 'item' }));
for (const it of items) {
  r = pick(it);
  shapeOk(r, '6');
  check(doc.querySelectorAll(r.sel).indexOf(it) >= 0 && r.n === 1, '6 matches its element ' + r.sel);
}

console.log(`${checks - fails}/${checks} checks passed`);
process.exit(fails ? 1 : 0);
