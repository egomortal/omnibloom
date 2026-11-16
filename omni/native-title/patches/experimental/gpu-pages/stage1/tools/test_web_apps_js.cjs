// OMNI_WEB_APPS_V1: node tests (no packages) for
//   1. the pages bundle's start/start-webapps.js (pure part through require(); the page part in a vm with a small
//      fake DOM shaped like start/index.html's "Your apps" section);
//   2. the engine's page query (OmniWebApps::pageScript, written by test_web_apps.cpp to argv[3]) run as an async
//      function body against fake documents: manifest, no manifest, hostile manifest, hung fetch.
//   node test_web_apps_js.cjs [start-webapps.js] [-] [page-script.js]
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const file = process.argv[2] && process.argv[2] !== '-' ? process.argv[2]
  : (process.env.OMNI_PAGES_BUNDLE ? require('path').join(process.env.OMNI_PAGES_BUNDLE, 'start', 'start-webapps.js') : require('path').join(__dirname, '..', '..', '..', '..', '..', '..', 'pages', 'bundle-clean4', 'start', 'start-webapps.js'));
const scriptFile = process.argv[4] || process.argv[3];
let checks = 0, fails = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };

// --- 1a. pure ----------------------------------------------------------------------------------------------------------
const M = require(path.resolve(file));
check(M.normalize(null).apps.length === 0, 'no data');
let n = M.normalize({ apps: [
  { id: 'a0123456789ab', n: 'YouTube', h: 'youtube.com', c: '#FF0000', k: '#ffffff', l: 'Y' },
  { id: 'a0123456789ab', n: 'dup' },
  { id: 'bad', n: 'x' },
  { id: 'a00000000000f', n: '', h: 'twitch.tv', c: 'red;background:url(x)', k: 'x', l: 'TOO' },
  { id: 'a00000000000e', n: '<img src=x onerror=1>\u0000', h: 'x' } ] });
check(n.apps.length === 3, 'ids checked, duplicates dropped');
check(n.apps[0].c === '#ff0000' && n.apps[0].l === 'Y', 'colour lower case');
check(n.apps[1].n === 'twitch.tv' && n.apps[1].c === '#3a3a3a' && n.apps[1].k === '#ffffff' && n.apps[1].l === 'T', 'fallbacks');
check(n.apps[2].n === '<img src=x onerror=1>', 'names are text (drawn with textContent), control characters removed');
const many = [];
for (let i = 0; i < 30; i++) many.push({ id: 'a' + i.toString(16).padStart(12, '0'), n: 'S' + i });
check(M.normalize({ apps: many }).apps.length === 12, 'at most 12');
check(M.letterOf('\u00e9t\u00e9') === '\u00c9' && M.letterOf('') === '?' && M.letterOf('\ud83d\ude00x') === '\ud83d\ude00', 'letters');
check(M.countText(3) === '3 of 12', 'count');

// --- 1b. the page in a fake DOM ------------------------------------------------------------------------------------------
function fakeDom() {
  const byId = new Map();
  class El {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.parentNode = null; this.className = ''; this._text = '';
      this.attrs = {}; this.listeners = {}; this.styleProps = {}; const self = this;
      this.style = { setProperty(k, v) { self.styleProps[k] = v; } };
      this.classList = { contains: c => self.className.split(/\s+/).includes(c) }; }
    set id(v) { this._id = v; byId.set(v, this); } get id() { return this._id; }
    set textContent(v) { this._text = String(v); this.children = []; } get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
    setAttribute(k, v) { this.attrs[k] = String(v); }
    append(...cs) { for (const c of cs) { c.parentNode = this; this.children.push(c); } }
    replaceChildren(...cs) { this.children = []; this._text = ''; this.append(...cs); }
    insertBefore(c, ref) { c.parentNode = this; const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); }
    get nextSibling() { const p = this.parentNode; if (!p) return null; const i = p.children.indexOf(this); return p.children[i + 1] || null; }
    addEventListener(t, f) { this.listeners[t] = f; }
    click() { this.listeners.click && this.listeners.click(); }
    all() { return this.children.flatMap(c => [c, ...c.all()]); }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
    querySelectorAll(sel) { const cls = sel.split(',').map(s => s.trim().replace(/^\./, '')); return this.all().filter(e => cls.some(c => e.classList.contains(c))); }
  }
  const body = new El('body');
  const section = new El('section'); body.append(section);
  const head = new El('div'); section.append(head);
  const apps = new El('div'); apps.id = 'apps'; apps.className = 'grid section'; section.append(apps);
  const document = { createElement: t => new El(t), getElementById: id => byId.get(id) || null, activeElement: body,
    querySelector: s => body.querySelector(s), querySelectorAll: s => body.querySelectorAll(s) };
  return { document, body, section, apps };
}
{
  const dom = fakeDom(), asked = [], toasts = [];
  const win = { document: dom.document, obUI: { toast: t => toasts.push(t), focus() {} },
    omnibloomHost: { request: async r => { asked.push(r); return r.method === 'webapps.open' && r.params.url === 'a0123456789ab' ? { ok: true } : { ok: false, code: 'NOT_FOUND' }; } } };
  win.__omniWebApps = { apps: [{ id: 'a0123456789ab', n: 'YouTube', h: 'youtube.com', c: '#ff0000', k: '#ffffff', l: 'Y' }], hint: 'x' };
  win.window = win;
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), { window: win, globalThis: win, Set, JSON, String, Math, Error });
  const box = dom.document.getElementById('omni-webapps');
  check(box && box.parentNode === dom.section && dom.section.children.indexOf(box) === dom.section.children.indexOf(dom.apps) + 1, 'box right after #apps inside Your apps');
  const tiles = dom.body.querySelectorAll('.owap-tile');
  check(tiles.length === 1 && tiles[0].styleProps['--owap-bg'] === '#ff0000', 'one tile, colour through CSSOM (CSP-safe)');
  check(dom.body.querySelector('.owap-count').textContent === '1 of 12', 'count shown');
  tiles[0].click();
  dom.body.querySelector('.owap-manage').click();
  setTimeout(() => {
    check(asked.length === 2 && asked[0].method === 'webapps.open' && asked[0].params.url === 'a0123456789ab', 'tile asks webapps.open with the id');
    check(asked[1].method === 'webapps.manage' && toasts.length === 1, 'manage asked; its failure toasts');
    check(win.omniWebAppsApply({ apps: [] }) === 'ok' && dom.body.querySelectorAll('.owap-tile').length === 0
      && dom.body.querySelector('.owap-empty'), 'empty list: the hint');
    check(dom.document.getElementById('omni-webapps') === box, 'redraw reuses the box');
    part2();
  }, 10);
}

// --- 2. the engine's page query ------------------------------------------------------------------------------------------
async function runQuery(body, docSpec, fetchImpl) {
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const links = (docSpec.links || []).map(l => ({ href: l.href, crossOrigin: l.crossOrigin || null, getAttribute: k => l[k] === undefined ? null : l[k] }));
  const document = {
    title: docSpec.title || '',
    querySelectorAll: sel => sel === 'link[rel][href]' ? links : [],
    querySelector: sel => {
      if (sel.startsWith('meta[name="theme-color"]')) return docSpec.theme ? { getAttribute: () => docSpec.theme } : null;
      if (sel.startsWith('link[rel~="manifest"]')) return links.find(l => /\bmanifest\b/.test(l.getAttribute('rel'))) || null;
      return null;
    } };
  const fn = new AsyncFunction('document', 'location', 'fetch', 'setTimeout', body);
  return fn(document, { href: docSpec.url }, fetchImpl, setTimeout);
}
async function part2() {
  if (!scriptFile || !fs.existsSync(scriptFile)) { console.log('(page query: no script file given; run test_web_apps.cpp with a path first)'); return done(); }
  const body = fs.readFileSync(scriptFile, 'utf8');
  try { new (Object.getPrototypeOf(async function () {}).constructor)(body); check(true, 'parses'); } catch (e) { check(false, 'page script parses: ' + e.message); }
  const manifest = { name: 'YouTube', short_name: 'YouTube', start_url: '/?feature=ytca', theme_color: '#FF0000',
    icons: [{ src: '/i/48.png', sizes: '48x48' }, { src: '/i/192.png', sizes: '192x192', purpose: 'any maskable' }, { src: '/i/mono.png', sizes: '512x512', purpose: 'monochrome' }] };
  let r = JSON.parse(await runQuery(body, { url: 'https://www.youtube.com/watch?v=1', title: 'Video - YouTube', theme: '#000',
    links: [{ rel: 'icon', href: 'https://www.youtube.com/favicon.ico' }, { rel: 'manifest', href: 'https://www.youtube.com/manifest.webmanifest' }] },
    async (u, o) => { check(o.credentials === 'same-origin', 'manifest fetched without cross-site cookies'); return { ok: true, text: async () => JSON.stringify(manifest) }; }));
  check(r.m === 1 && r.name === 'YouTube' && r.start === 'https://www.youtube.com/?feature=ytca', 'manifest read, start_url resolved');
  check(r.icon === 'https://www.youtube.com/i/192.png' && r.theme === '#FF0000' && r.tc === '#000', 'largest usable icon, colours');
  r = JSON.parse(await runQuery(body, { url: 'https://music.example/', title: 'Music',
    links: [{ rel: 'icon', href: 'https://music.example/16.png', sizes: '16x16' }, { rel: 'apple-touch-icon', href: 'https://music.example/t.png' }, { rel: 'icon', href: 'data:image/png;base64,AA' }] }, undefined));
  check(r.m === 0 && r.title === 'Music' && r.fav === 'https://music.example/t.png', 'no manifest: title + touch icon');
  r = JSON.parse(await runQuery(body, { url: 'https://p.example/', links: [] }, undefined));
  check(r.fav === 'https://p.example/favicon.ico', 'no icon links: /favicon.ico');
  r = JSON.parse(await runQuery(body, { url: 'https://h.example/', links: [{ rel: 'manifest', href: 'https://h.example/m.json' }] },
    async () => ({ ok: true, text: async () => '{"name":' + JSON.stringify('x'.repeat(5000)) + ',"icons":"nope","start_url":{"a":1}}' })));
  check(r.m === 1 && r.name.length === 200 && r.icon === '' && r.start === '', 'hostile manifest: capped / ignored');
  r = JSON.parse(await runQuery(body, { url: 'https://h.example/', links: [{ rel: 'manifest', href: 'https://h.example/m.json' }] },
    async () => ({ ok: true, text: async () => 'not json' })));
  check(r.m === 0, 'broken manifest: no manifest');
  const t0 = Date.now();
  r = JSON.parse(await runQuery(body, { url: 'https://slow.example/', title: 'Slow', links: [{ rel: 'manifest', href: 'https://slow.example/m.json' }] },
    () => new Promise(() => {})));
  const ms = Date.now() - t0;
  check(r.title === 'Slow' && r.m === 0 && ms >= 2400 && ms < 3300, 'hung fetch: answers after ~2.5 s (' + ms + ' ms)');
  done();
}
function done() { console.log(checks + ' checks, ' + fails + ' failed'); process.exitCode = fails ? 1 : 0; }
