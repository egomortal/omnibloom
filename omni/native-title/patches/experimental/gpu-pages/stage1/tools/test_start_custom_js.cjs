// OMNI_START_CUSTOM_V1: tests for the pages bundle's start/start-custom.js (node, no packages).
//   node test_start_custom_js.cjs [path/to/start-custom.js]
// Pure part through require(); the page part in a vm with a small fake DOM shaped like start/index.html.
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const file = process.argv[2] || process.env.OMNI_PAGES_BUNDLE ? path.join(process.env.OMNI_PAGES_BUNDLE, 'start', 'start-custom.js') : path.join(path.join(__dirname, '..', '..', '..', '..', '..', '..', 'pages', 'bundle-clean4'), 'start', 'start-custom.js');
let checks = 0, fails = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };

// --- pure ------------------------------------------------------------------------------------------------------------
const M = require(path.resolve(file));
let n = M.normalize(null);
check(n.order.join() === M.KEYS.join() && !n.linear && n.hidden.size === 0 && n.bg.kind === 'theme' && !n.clock, 'defaults');
n = M.normalize({ order: ['closed', 'closed', 'x', 'search'], hidden: ['apps', 'bogus'] });
check(n.order.join() === 'closed,search,apps,shortcuts,cw,reading' && n.linear, 'order repaired like the engine');
check(n.hidden.has('apps') && !n.hidden.has('bogus'), 'hidden filtered');
n = M.normalize({ private: true, closed: [{ u: 'https://a.com', t: 'A' }] });
check(n.hidden.has('cw') && n.hidden.has('closed') && n.closed.length === 0, 'private: no cw / closed');
check(M.normalize({ bg: { kind: 'colour', value: '#12355b' } }).bg.value === '#12355b', 'colour');
check(M.normalize({ bg: { kind: 'colour', value: 'red;x' } }).bg.kind === 'theme', 'bad colour -> theme');
check(M.normalize({ bg: { kind: 'picture', url: 'omni://pages/_user/start-bg.png?v=1-2-3' } }).bg.kind === 'picture', 'picture');
check(M.normalize({ bg: { kind: 'picture', url: 'https://evil/x.png' } }).bg.kind === 'theme', 'foreign picture refused');
check(M.normalize({ bg: { kind: 'picture', url: 'omni://pages/_user/start-bg.png?v=1")x' } }).bg.kind === 'theme', 'picture version charset');
n = M.normalize({ reading: [{ id: 'a.html', t: 'A' }, { id: '../x', t: 'bad' }, { id: 'b.html', s: 'b.com' }, { id: 'c.html' }, { id: 'd.html' }],
  closed: [{ u: 'javascript:alert(1)' }, { u: 'https://x.org/p', t: 'X\u0000' }] });
check(n.reading.length === 3 && n.reading[1].t === 'b.com' && n.reading[2].t === 'Saved page', 'reading: checked, 3 at most');
check(n.closed.length === 1 && n.closed[0].t === 'X ', 'closed: web addresses only, control characters removed');
let p = M.plan(M.normalize({ order: M.KEYS }));
check(p.search.order === '' && p.reading.shown === false && p.closed.shown === false && p.apps.shown, 'default plan: grid, empty lists hidden');
p = M.plan(M.normalize({ order: ['apps', 'search'], reading: [{ id: 'a.html' }] }));
check(p.apps.order === '1' && p.shortcuts.order === '2' && p.search.order === '6' && p.reading.shown, 'linear plan (missing ones follow their default predecessor)');
check(M.clockText(new Date(2026, 10, 16, 7, 5)) === '07:05', 'clock text');

// --- page (fake DOM) ---------------------------------------------------------------------------------------------------
class ClassList {
  constructor(el) { this.el = el; }
  get set() { return new Set(this.el.className.split(/\s+/).filter(Boolean)); }
  write(s) { this.el.className = [...s].join(' '); }
  add(c) { const s = this.set; s.add(c); this.write(s); }
  remove(c) { const s = this.set; s.delete(c); this.write(s); }
  contains(c) { return this.set.has(c); }
  toggle(c, f) { const on = f === undefined ? !this.contains(c) : !!f; on ? this.add(c) : this.remove(c); return on; }
}
class Style {
  constructor() { this.props = {}; this.order = ''; }
  setProperty(k, v, pr) { this.props[k] = v + (pr ? ' !' + pr : ''); }
  removeProperty(k) { delete this.props[k]; }
}
let doc;
class El {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.parentNode = null; this.className = ''; this.id = ''; this.attrs = {};
    this.style = new Style(); this.classList = new ClassList(this); this.listeners = {}; this.hidden = false; this._text = ''; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  set textContent(v) { this.children = []; this._text = String(v); }
  append(...ns) { for (const x of ns) { if (x.parentNode) x.remove(); x.parentNode = this; this.children.push(x); } doc._mut(this); }
  insertBefore(x, ref) { if (x.parentNode) x.remove(); x.parentNode = this; const i = this.children.indexOf(ref); this.children.splice(i < 0 ? this.children.length : i, 0, x); doc._mut(this); }
  replaceChildren(...ns) { this.children.forEach(c => c.parentNode = null); this.children = []; this.append(...ns); }
  remove() { const p = this.parentNode; if (!p) return; p.children.splice(p.children.indexOf(this), 1); this.parentNode = null; doc._mut(p); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  click() { (this.listeners.click || []).forEach(f => f({ type: 'click' })); }
  matches(sel) { return sel[0] === '.' ? this.classList.contains(sel.slice(1)) : sel[0] === '#' ? this.id === sel.slice(1) : this.tagName === sel.toUpperCase(); }
  closest(sel) { for (let e = this; e; e = e.parentNode) if (e.matches && e.matches(sel)) return e; return null; }
  all() { return this.children.flatMap(c => [c, ...c.all()]); }
  querySelector(sel) { return this.all().find(e => e.matches(sel)) || null; }
}
function makePage(data, opts = {}) {
  const requests = [], toasts = [], focused = [];
  doc = {
    _observers: [],
    _mut(target) { for (const o of this._observers) if (o.target === target || o.target === null) o.cb([]); },
    createElement: t => new El(t),
    body: new El('body'),
    getElementById(id) { return this.body.all().find(e => e.id === id) || null; },
    querySelector(sel) { return this.body.querySelector(sel); },
  };
  const b = doc.body, main = new El('main'); main.id = 'main';
  const top = new El('header'); top.className = 'topline';
  const hero = new El('section'); hero.className = 'hero universe-hero';
  const form = new El('form'); form.id = 'search'; const q = new El('input'); q.id = 'query'; form.append(q); hero.append(form);
  const appsS = new El('section'); appsS.className = 'section'; const apps = new El('div'); apps.id = 'apps'; appsS.append(apps);
  const lib = new El('section'); lib.className = 'section grid two';
  const c1 = new El('div'); c1.className = 'card'; const pins = new El('div'); pins.id = 'pins'; c1.append(pins);
  const c2 = new El('div'); c2.className = 'card'; const rec = new El('div'); rec.id = 'recents'; c2.append(rec); lib.append(c1, c2);
  const dlg = new El('dialog'); dlg.id = 'pin-dialog';
  main.append(top, hero, appsS, lib, dlg); b.append(main);
  doc.activeElement = opts.focus === 'query' ? q : b;
  const timers = [];
  const win = {
    document: doc, Date, JSON, Math, String, Array, Set, Object, Error, Promise, console,
    MutationObserver: class { constructor(cb) { this.cb = cb; } observe(t) { doc._observers.push({ target: t, cb: this.cb }); } },
    setInterval(f, ms) { timers.push({ f, ms }); return timers.length; }, clearInterval() {},
    addEventListener() {},
    omnibloomHost: opts.noHost ? undefined : { request: async r => { requests.push(r); return opts.fail ? { ok: false, code: 'UNSUPPORTED' } : { ok: true, result: null }; } },
    obUI: { toast: t => toasts.push(t), items: () => [appsS], focus: e => focused.push(e) },
  };
  if (data) win.__omniStartCustom = data;
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), win, { filename: 'start-custom.js' });
  return { win, doc, main, top, hero, form, appsS, lib, requests, toasts, focused, timers, q };
}
const tick = () => new Promise(r => setImmediate(r));

(async () => {
  // data arrives before the script: picked up from window.__omniStartCustom
  const D = { v: 1, order: ['apps', 'search', 'shortcuts', 'reading', 'cw', 'closed'], hidden: ['apps'], bg: { kind: 'colour', value: '#12355b' },
    clock: true, private: false, linear: true, reading: [{ id: 'r1.html', t: 'Saved one', s: 'a.com', d: 'Today 10:00' }],
    closed: [{ u: 'https://x.org/p', t: 'X page', s: 'x.org' }], hint: 'x Open' };
  let P = makePage(D, { focus: 'query' });
  check(typeof P.win.omniStartCustomApply === 'function', 'apply exported');
  check(P.doc.getElementById('oscu-gear') && P.doc.getElementById('oscu-gear').parentNode === P.top, 'gear in the header');
  check(P.doc.body.classList.contains('oscu-linear'), 'linear mode for a custom order');
  check(P.hero.style.order === '2' && P.appsS.style.order === '1' && P.lib.style.order === '3', 'CSS order follows the data');
  check(P.appsS.classList.contains('oscu-hidden') && !P.hero.classList.contains('oscu-hidden'), 'apps hidden, hero kept');
  const R = P.doc.getElementById('oscu-reading'), C = P.doc.getElementById('oscu-closed');
  check(R && C && R.style.order === '4' && C.style.order === '6' && R.classList.contains('oscu-extra'), 'reading / closed sections placed');
  check(P.main.children.indexOf(R) < P.main.children.indexOf(P.doc.getElementById('pin-dialog')), 'new sections before the dialogs');
  check(R.querySelector('.oscu-tiles').children.length === 1 && R.querySelector('.oscu-all'), 'reading tiles + All saved pages');
  check(P.doc.body.style.props.background === '#12355b !important', 'colour background');
  const clock = P.doc.getElementById('oscu-clock');
  check(clock && !clock.hidden && /^\d\d:\d\d$/.test(clock.textContent) && P.timers.length === 1, 'clock shown and ticking');
  // tiles ask Omni
  R.querySelector('.oscu-tiles').children[0].click();
  C.querySelector('.oscu-tiles').children[0].click();
  P.doc.getElementById('oscu-gear').click();
  R.querySelector('.oscu-all').click();
  await tick();
  check(JSON.stringify(P.requests.map(r => [r.method, r.params.url || ''])) ===
    JSON.stringify([['start.reading.open', 'r1.html'], ['start.closed.open', 'https://x.org/p'], ['start.customise', ''], ['start.reading.all', '']]), 'bridge requests');
  // Continue watching inserts its row later: it is placed too
  const cw = new El('section'); cw.id = 'omni-cw'; P.main.insertBefore(cw, P.appsS);
  check(cw.style.order === '5' && cw.classList.contains('oscu-extra'), 'Continue watching row placed after it appears');
  // new data: default order, search hidden, picture, clock off, empty lists, private
  P.win.omniStartCustomApply({ order: M.KEYS, hidden: ['search'], bg: { kind: 'picture', url: 'omni://pages/_user/start-bg.png?v=1-2-3' }, clock: false,
    private: true, reading: [], closed: [{ u: 'https://y.org', t: 'Y' }] });
  check(!P.doc.body.classList.contains('oscu-linear') && P.hero.style.order === '' && cw.style.order === '', 'default order: grid again');
  check(P.form.classList.contains('oscu-hidden') && !P.hero.classList.contains('oscu-hidden'), 'search hidden: the form only');
  check(cw.classList.contains('oscu-hidden') && C.classList.contains('oscu-hidden') && R.classList.contains('oscu-hidden'), 'private: cw / closed hidden; empty reading hidden');
  check(C.querySelector('.oscu-tiles').children.length === 0, 'private: no closed tiles drawn');
  check(/url\("omni:\/\/pages\/_user\/start-bg.png\?v=1-2-3"\)/.test(P.doc.body.style.props['background-image'] || '') && !P.doc.body.style.props.background, 'picture background, colour removed');
  check(clock.hidden, 'clock hidden');
  check(P.focused.length === 1, 'focus moved off the hidden search box');
  check(P.doc.body.all().filter(e => e.id === 'oscu-gear').length === 1 && P.doc.body.all().filter(e => e.id === 'oscu-reading').length === 1, 'apply is idempotent');
  P.win.omniStartCustomApply({});
  check(!P.doc.body.style.props['background-image'] && !P.form.classList.contains('oscu-hidden'), 'theme default restores');
  // an engine without the feature: the request fails -> a toast that says where the setting is
  P = makePage(null, { fail: true });
  check(!P.doc.getElementById('oscu-gear'), 'no data from Omni: no gear');
  P.win.omniStartCustomApply({});
  P.doc.getElementById('oscu-gear').click();
  await tick(); await tick();
  check(P.toasts.length === 1 && /Browser settings/.test(P.toasts[0]), 'failed request -> toast');

  console.log((fails ? 'FAILED' : 'OK') + ': ' + (checks - fails) + '/' + checks + ' checks passed');
  process.exit(fails ? 1 : 0);
})();
