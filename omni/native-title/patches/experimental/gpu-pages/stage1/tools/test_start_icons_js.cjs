// OMNI_START_ICONS_V1: node tests (no packages) for the start page's site icons.
//   1. start/start-icons.js, pure part through require(): hostKey + FNV-1a 64 against the C++ (OmniStartIcons::key)
//      vectors (built in below; test_start_icons.cpp writes a fresh set with an argument: pass it with --vectors);
//   2. its page part in a vm with a small fake DOM: attach() swaps a letter for the icon only after it loaded, never on
//      an error / bad key / outside omni://; Pinned / Recent buttons (data-osic-url) get an icon slot, redraws too;
//   3. start-custom.js / start-webapps.js: the "icon" key is checked and handed to attach() (letters stay without it);
//   4. Omni's Continue watching script (omniCwScript, cut from a patched tree's OmniContinueWatchingShell.h with --cw)
//      hands its letter disc to attach() with the item's key, and still draws without start-icons.js.
//   node test_start_icons_js.cjs [--bundle <start dir>] [--vectors <tsv>] [--cw <OmniContinueWatchingShell.h>]
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const arg = k => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : ''; };
const bundle = arg('--bundle') || (process.env.OMNI_PAGES_BUNDLE ? path.join(process.env.OMNI_PAGES_BUNDLE, 'start') : path.join(path.join(__dirname, '..', '..', '..', '..', '..', '..', 'pages', 'bundle-clean4'), 'start'));
let checks = 0, fails = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };

// --- 1. keys ---------------------------------------------------------------------------------------------------------
const SI = require(path.resolve(bundle, 'start-icons.js'));
// From test_start_icons.cpp (OmniStartIcons::key = OmniFavicons::fileName(hostKey(url)) without ".png").
let vectors = [
  ['https://www.youtube.com/tv', '062a93911cf634ad'], ['https://youtube.com/', '062a93911cf634ad'],
  ['HTTPS://WWW.Example.COM:8443/x?y#z', '576846634e2714c6'], ['http://user:pw@tv.example.org:8443/x#y', 'e436bd003f46451b'],
  ['https://www.com/', '4cdd11edef4d8a47'], ['https://www.', '5e63e419483e75ec'], ['https://www.a.b/', 'e61d99190466522c'],
  ['https://[::1]:8080/', 'd93d38d09d6ea210'], ['https://[2001:DB8::1]/x', 'c13b6f446092784d'], ['https://[::g]/', ''],
  ['https://example.com./', '576846634e2714c6'], ['https://example.com\\evil.com/', '576846634e2714c6'],
  ['https://a@b@c.example/', '93ab3ed62b6c574a'], ['https://exa mple.com/', ''], ['ftp://example.com/', ''], ['javascript:alert(1)', ''],
  ['https://', ''], ['https://xn--bcher-kva.example/', '7b26509724e3d0d4'], ['https://under_score.example/', '94f2fe9d9201cb00'],
  ['https://\u00e9t\u00e9.fr/', ''], ['https://example.com?q=@x.org', '576846634e2714c6'], ['http://localhost:3000/', 'db3f053403ad937a'],
  ['https://192.168.0.1/admin', '2e9082d8e3366183'], ['https://a.b.c.d.e.f.g.example.co.uk/p', '83bffd5439d7d349'],
];
if (arg('--vectors')) {
  vectors = fs.readFileSync(arg('--vectors'), 'utf8').split('\n').filter(Boolean).map(l => l.split('\t'));
  check(vectors.length >= 20, 'vectors file read');
}
for (const [u, k] of vectors) check(SI.key(u) === (k || ''), 'key(' + JSON.stringify(u) + ') = ' + JSON.stringify(SI.key(u)) + ', C++ ' + JSON.stringify(k));
check(SI.fnv1a64('') === 'cbf29ce484222325' && SI.fnv1a64('a') === 'af63dc4c8601ec8c' && SI.fnv1a64('foobar') === '85944171f73967e8', 'FNV-1a 64 reference values');
check(SI.hostKey('https://\u212Aelvin.example/') === '', 'non-ASCII letters never fold to ASCII (Kelvin sign)');
check(SI.siteKey('example.com') === SI.key('https://example.com/') && SI.siteKey('a/b') === '' && SI.siteKey('a@b') === '' && SI.siteKey('') === '', 'siteKey');
check(SI.valid('0123456789abcdef') && !SI.valid('0123456789ABCDEF') && !SI.valid('x') && !SI.valid(null), 'valid');
check(SI.pick('0123456789abcdef', 'https://a.com/') === '0123456789abcdef' && SI.pick('bad', 'https://youtube.com/') === '062a93911cf634ad'
  && SI.pick(undefined, 'about:blank') === '', 'pick: given key, else computed');
check(SI.src('0123456789abcdef') === 'omni://pages/_user/icon/0123456789abcdef.png' && SI.src('../x') === '', 'src');

// --- fake DOM ----------------------------------------------------------------------------------------------------------
class ClassList {
  constructor(el) { this.el = el; }
  get set() { return new Set(this.el.className.split(/\s+/).filter(Boolean)); }
  write(s) { this.el.className = [...s].join(' '); }
  add(...c) { const s = this.set; c.forEach(x => s.add(x)); this.write(s); }
  remove(c) { const s = this.set; s.delete(c); this.write(s); }
  contains(c) { return this.set.has(c); }
  toggle(c, f) { const on = f === undefined ? !this.contains(c) : !!f; on ? this.add(c) : this.remove(c); return on; }
}
let doc, images;
class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.parentNode = null; this.className = ''; this.id = ''; this.attrs = {};
    this.style = { setProperty() {}, removeProperty() {} }; this.classList = new ClassList(this); this.listeners = {}; this.dataset = {}; this._text = '';
    if (this.tagName === 'IMG') { this.naturalWidth = 0; images.push(this); }
  }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get isConnected() { for (let e = this; e; e = e.parentNode) if (e === doc.body) return true; return false; }
  append(...ns) { for (const x of ns) { if (typeof x === 'string') { this._text += x; continue; } if (x.parentNode) x.remove(); x.parentNode = this; this.children.push(x); } doc._mut(this); }
  appendChild(x) { this.append(x); return x; }
  prepend(x) { if (x.parentNode) x.remove(); x.parentNode = this; this.children.unshift(x); doc._mut(this); }
  insertBefore(x, ref) { if (x.parentNode) x.remove(); x.parentNode = this; const i = this.children.indexOf(ref); this.children.splice(i < 0 ? this.children.length : i, 0, x); doc._mut(this); }
  replaceChildren(...ns) { this.children.forEach(c => c.parentNode = null); this.children = []; this._text = ''; this.append(...ns); }
  remove() { const p = this.parentNode; if (!p) return; p.children.splice(p.children.indexOf(this), 1); this.parentNode = null; doc._mut(p); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  fire(t) { (this.listeners[t] || []).forEach(f => f({ type: t, preventDefault() {} })); }
  click() { this.fire('click'); }
  focus() {}
  matches(sel) {
    if (sel === 'button[data-osic-url]') return this.tagName === 'BUTTON' && this.dataset.osicUrl !== undefined;
    return sel[0] === '.' ? this.classList.contains(sel.slice(1)) : sel[0] === '#' ? this.id === sel.slice(1) : this.tagName === sel.toUpperCase();
  }
  closest(sel) { for (let e = this; e; e = e.parentNode) if (e.matches && e.matches(sel)) return e; return null; }
  all() { return this.children.flatMap(c => [c, ...c.all()]); }
  querySelector(sel) {
    if (sel.startsWith(':scope > ')) return this.children.find(c => c.matches(sel.slice(9))) || null;
    if (sel === 'main section.hero') return this.all().find(e => e.tagName === 'SECTION' && e.classList.contains('hero')) || null;
    return this.all().find(e => e.matches(sel)) || null;
  }
  querySelectorAll(sel) { return this.all().filter(e => e.matches(sel)); }
}
function makeDoc() {
  images = [];
  doc = {
    _observers: [],
    _mut(target) { for (const o of this._observers) { for (let e = target; e; e = e.parentNode) if (e === o.target) { o.cb([]); break; } } },
    createElement: t => new El(t),
    getElementById(id) { return this.body.all().find(e => e.id === id) || null; },
    querySelector(sel) { return this.body.querySelector(sel); },
    querySelectorAll(sel) { return this.body.querySelectorAll(sel); },
  };
  doc.body = new El('body');
  return doc;
}
function makeWin(protocol, extra) {
  return Object.assign({
    document: doc, location: { protocol }, JSON, Math, String, Array, Set, Object, Error, Promise, console,
    MutationObserver: class { constructor(cb) { this.cb = cb; } observe(t) { doc._observers.push({ target: t, cb: this.cb }); } },
    setInterval() { return 1; }, clearInterval() {}, addEventListener() {},
  }, extra || {});
}
const load = (img, w = 32) => { img.naturalWidth = w; img.fire('load'); };

// --- 2. start-icons.js page part ------------------------------------------------------------------------------------------
{
  makeDoc();
  const main = new El('main'); main.id = 'main';
  const pins = new El('div'); pins.id = 'pins'; const rec = new El('div'); rec.id = 'recents';
  const p1 = new El('button'); p1.className = 'pinned-open'; p1.textContent = 'YouTube'; p1.dataset.osicUrl = 'https://www.youtube.com/tv';
  const p2 = new El('button'); p2.textContent = 'Edit';   // no address: never decorated
  pins.append(p1, p2); main.append(pins, rec); doc.body.append(main);
  const win = makeWin('omni:');
  vm.runInNewContext(fs.readFileSync(path.join(bundle, 'start-icons.js'), 'utf8'), win, { filename: 'start-icons.js' });
  const A = win.omniStartIcons;
  check(A && typeof A.attach === 'function' && Object.isFrozen(A), 'window.omniStartIcons exported (frozen)');
  const slot1 = p1.children[0];
  check(slot1 && slot1.className === 'osic-site' && slot1.attrs['aria-hidden'] === 'true' && p1.textContent === 'YouTube', 'pinned button: an empty slot first, title kept');
  check(p2.children.length === 0, 'buttons without an address untouched');
  check(images.length === 1 && images[0].src === 'omni://pages/_user/icon/062a93911cf634ad.png', 'pinned icon requested from the route');
  check(!slot1.classList.contains('osic-on'), 'slot hidden until the icon loads');
  load(images[0]);
  check(slot1.classList.contains('osic-on') && slot1.children[0] === images[0] && images[0].alt === '', 'loaded: the icon shows');
  // recents: a redraw (replaceChildren) is decorated again, a failing icon leaves the plain button
  const r1 = new El('button'); r1.textContent = 'twitch.tv'; r1.dataset.osicUrl = 'https://twitch.tv/';
  rec.replaceChildren(r1);
  check(r1.children.length === 1 && images.length === 2, 'recent button decorated after a redraw');
  images[1].fire('error');
  check(!r1.children[0].classList.contains('osic-on') && r1.children[0].children.length === 0, 'error: nothing shown (no broken image)');
  const r2 = new El('button'); r2.textContent = 'x'; r2.dataset.osicUrl = 'javascript:alert(1)';
  rec.replaceChildren(r2);
  check(r2.children.length === 0 && images.length === 2, 'no key for a non-web address: nothing requested');
  // re-decoration does not duplicate
  A.decorate(pins); A.decorate(pins);
  check(p1.children.filter(c => c.className.includes('osic-site')).length === 1 && images.length === 2, 'decorate is idempotent');
  // attach rules
  const letter = new El('span'); letter.textContent = 'Y'; main.append(letter);
  check(A.attach(letter, 'nothex!') === false && A.attach(null, '0123456789abcdef') === false, 'bad key / no slot refused');
  check(A.attach(letter, '0123456789abcdef') === true && letter.textContent === 'Y', 'letter stays while loading');
  load(images[images.length - 1], 0);
  check(letter.textContent === 'Y' && !letter.classList.contains('osic-on'), 'a 0-width image is not an icon');
  A.attach(letter, '0123456789abcdef'); letter.remove(); load(images[images.length - 1]);
  check(!letter.classList.contains('osic-on'), 'a slot no longer in the page is left alone');
  // outside omni:// (the old new-tab page, a copy opened from disk): never
  makeDoc();
  const w2 = makeWin('https:');
  vm.runInNewContext(fs.readFileSync(path.join(bundle, 'start-icons.js'), 'utf8'), w2, { filename: 'start-icons.js' });
  check(w2.omniStartIcons.attach(new El('i'), '0123456789abcdef') === false && images.length === 0, 'not on omni://pages: no icons');
}

// --- 3. start-custom.js / start-webapps.js ---------------------------------------------------------------------------------
{
  const C = require(path.resolve(bundle, 'start-custom.js'));
  const n = C.normalize({ reading: [{ id: 'r1.html', t: 'T', s: 'a.com', icon: '0123456789abcdef' }, { id: 'r2.html', icon: '"><img>' }],
    closed: [{ u: 'https://x.org/', t: 'X', icon: 'ABCDEF0123456789' }, { u: 'https://y.org/', icon: 'fedcba9876543210' }] });
  check(n.reading[0].icon === '0123456789abcdef' && n.reading[1].icon === '' && n.closed[0].icon === '' && n.closed[1].icon === 'fedcba9876543210', 'start-custom: icon keys checked');
  const W = require(path.resolve(bundle, 'start-webapps.js'));
  const w = W.normalize({ apps: [{ id: 'a0123456789ab', n: 'YouTube', icon: '062a93911cf634ad' }, { id: 'a0123456789ac', n: 'B', icon: 'x' }] });
  check(w.apps[0].icon === '062a93911cf634ad' && w.apps[1].icon === '', 'start-webapps: icon keys checked');

  // pages: tiles hand their slot / letter to attach()
  makeDoc();
  const main = new El('main'); main.id = 'main';
  const top = new El('header'); top.className = 'topline';
  const hero = new El('section'); hero.className = 'hero';
  const appsS = new El('section'); const apps = new El('div'); apps.id = 'apps'; appsS.append(apps);
  const lib = new El('section'); const pins = new El('div'); pins.id = 'pins'; lib.append(pins);
  main.append(top, hero, appsS, lib); doc.body.append(main);
  const calls = [];
  const fakeSI = { attach: (slot, k) => { calls.push([slot.className, slot.textContent, k]); return true; } };
  const win = makeWin('omni:', { omniStartIcons: fakeSI, obUI: { toast() {}, items: () => [], focus() {} }, omnibloomHost: { request: async () => ({ ok: true }) } });
  win.__omniStartCustom = { reading: [{ id: 'r1.html', t: 'Saved', s: 'a.com', icon: '0123456789abcdef' }, { id: 'r2.html', t: 'No icon', s: 'b.com' }],
    closed: [{ u: 'https://x.org/p', t: 'X', s: 'x.org', icon: 'fedcba9876543210' }] };
  win.__omniWebApps = { apps: [{ id: 'a0123456789ab', n: 'YouTube', h: 'youtube.com', c: '#ff0000', k: '#ffffff', l: 'Y', icon: '062a93911cf634ad' },
    { id: 'a0123456789ac', n: 'Bare', h: 'bare.org', l: 'B' }] };
  vm.runInNewContext(fs.readFileSync(path.join(bundle, 'start-custom.js'), 'utf8'), win, { filename: 'start-custom.js' });
  vm.runInNewContext(fs.readFileSync(path.join(bundle, 'start-webapps.js'), 'utf8'), win, { filename: 'start-webapps.js' });
  check(JSON.stringify(calls) === JSON.stringify([['oscu-ico', '', '0123456789abcdef'], ['oscu-ico', '', 'fedcba9876543210'], ['owap-letter', 'Y', '062a93911cf634ad']]),
    'reading / closed slots and the web-app letter go to attach() with their keys (none without a key): ' + JSON.stringify(calls));
  const rt = doc.getElementById('oscu-reading').querySelector('.oscu-tiles').children[0];
  check(rt.querySelector('.oscu-head') && rt.querySelector('.oscu-ico') && rt.querySelector('b').textContent === 'Saved', 'reading tile: icon slot before the title');
  const tiles = doc.getElementById('omni-webapps').querySelectorAll('.owap-tile');
  check(tiles.length === 2 && tiles[1].querySelector('.owap-letter').textContent === 'B', 'web app without a key keeps its letter');
  // and without start-icons.js (an older bundle): everything still draws
  makeDoc();
  const m2 = new El('main'); m2.id = 'main'; const ap2 = new El('div'); ap2.id = 'apps'; const s2 = new El('section'); s2.append(ap2); m2.append(s2); doc.body.append(m2);
  const w3 = makeWin('omni:', { obUI: { toast() {}, items: () => [], focus() {} } });
  w3.__omniWebApps = win.__omniWebApps;
  vm.runInNewContext(fs.readFileSync(path.join(bundle, 'start-webapps.js'), 'utf8'), w3, { filename: 'start-webapps.js' });
  check(doc.getElementById('omni-webapps').querySelectorAll('.owap-tile').length === 2, 'no start-icons.js: tiles drawn as before');
}

// --- 4. Continue watching (Omni's own script) --------------------------------------------------------------------------------
const cwFile = arg('--cw');
if (cwFile) {
  const h = fs.readFileSync(cwFile, 'utf8');
  const m = /omniCwScript = R"JS\(([\s\S]*?)\)JS";/.exec(h);
  check(!!m, 'omniCwScript found');
  if (m) {
    const run = (withSI, protocol) => {
      makeDoc();
      const main = new El('main'); const hero = new El('section'); hero.className = 'hero'; main.append(hero); doc.body.append(main);
      const calls = [];
      const SIw = withSI ? { attach: (slot, k) => { calls.push([slot.textContent, k]); return true; }, pick: SI.pick } : undefined;
      const D = { items: [
        { k: 'w:1', u: 'https://www.youtube.com/watch?v=1', t: 'A', s: 'youtube.com', l: 'Y', p: 50, left: '1 min left', icon: '062a93911cf634ad' },
        { k: 'w:2', u: 'https://vimeo.com/2', t: 'B', s: 'vimeo.com', l: 'V', p: 10, left: '9 min left' } ], focus: -1, hint: 'h' };
      const win = makeWin(protocol, { omniStartIcons: SIw });
      win.window = win;
      const out = vm.runInNewContext(m[1].replace('%DATA%', JSON.stringify(D)), win, { filename: 'omniCwScript.js' });
      return { out, calls, sec: doc.getElementById('omni-cw') };
    };
    const a = run(true, 'omni:');
    check(a.out === '2' && a.sec, 'Continue watching row drawn');
    check(JSON.stringify(a.calls) === JSON.stringify([['Y', '062a93911cf634ad'], ['V', SI.key('https://vimeo.com/2')]]),
      'each letter disc goes to attach(): Omni\'s key, else the one from the address: ' + JSON.stringify(a.calls));
    const b = run(false, 'omni:');
    check(b.out === '2' && b.sec && b.calls.length === 0, 'without start-icons.js: letters as before');
    const c = run(true, 'data:');
    check(c.out === '2' && c.calls.length === 0, 'old data: new-tab page: no icons');
  }
} else console.log('(Continue watching script: pass --cw <patched tree>/engine/entry/OmniContinueWatchingShell.h)');

console.log((fails ? 'FAILED: ' : 'OK: ') + (checks - fails) + '/' + checks + ' checks passed');
process.exit(fails ? 1 : 0);
