// OMNI_DARK_STANDARD_V1 host test: the dark-page user script from OmniDarkPages.h in a minimal fake DOM, per scenario.
// usage: node dark_standard_test.js <OmniDarkPages.h> [expect-old]
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8'); const old = process.argv[3] === 'expect-old';
const js = src.slice(src.indexOf('R"JS(') + 5, src.indexOf(')JS"'));
let fails = 0, n = 0;
function check(name, ok) { n++; if (!ok) fails++; console.log((ok ? 'PASS ' : 'FAIL ') + name); }
function page(o) {
  let timers = [], mos = [];
  const el = tag => { const a = {}; return { tagName: tag, attrs: a, style: { setProperty() {} }, children: [],
    hasAttribute: k => k in a, getAttribute: k => (k in a ? a[k] : null),
    setAttribute: (k, v) => { a[k] = String(v); mos.forEach(m => m.t === html_ && m.f.includes(k) && m.cb()); }, removeAttribute: k => { delete a[k]; mos.forEach(m => m.t === html_ && m.f.includes(k) && m.cb()); },
    appendChild(c) { this.children.push(c); return c; } }; };
  const html_ = el('html'), body = el('body'), head = el('head'); const listeners = {}, wl = {}, mql = [];
  const doc = { documentElement: html_, body, head, styleSheets: o.sheets || [], getElementsByTagName: () => [],
    getElementById: id => head.children.find(c => c.id === id) || null, createElement: t => el(t),
    querySelector: s => (s.startsWith('meta') && o.meta ? { getAttribute: () => o.meta } : null),
    addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); } };
  const win = { document: doc, location: { protocol: 'https:', hostname: o.host || 'example.com' }, innerWidth: 1280, innerHeight: 720,
    getComputedStyle: e => ({ backgroundColor: e === html_ ? o.htmlBg : o.bodyBg, colorScheme: e === html_ ? (o.scheme || 'normal') : 'normal' }),
    matchMedia: () => { const m = { matches: !!o.prefersDark, addEventListener: (t, f) => mql.push(f) }; return m; },
    MutationObserver: class { constructor(cb) { this.cb = cb; } observe(t, opt) { mos.push({ t, f: opt.attributeFilter || [], cb: this.cb }); } disconnect() {} },
    setTimeout: f => { timers.push(f); return timers.length; }, clearTimeout: () => {},
    addEventListener: (t, f) => { (wl[t] = wl[t] || []).push(f); }, __omniDarkCfg: { v: 1, g: 0, on: [o.host || 'example.com'], off: [] } };
  win.window = win;
  const flush = () => { for (let i = 0; i < 30 && timers.length; i++) { const t = timers; timers = []; t.forEach(f => f()); } };
  vm.createContext(win); vm.runInContext(js, win); flush();
  return { dark: () => 'data-omnidark' in html_.attrs, html: html_, o, flush, fireWin: t => { (wl[t] || []).forEach(f => f()); flush(); },
           mq: () => { mql.forEach(f => f()); flush(); } };
}
const W = 'rgb(255, 255, 255)', K = 'rgb(15, 15, 15)', T = 'rgba(0, 0, 0, 0)';
let p = page({ htmlBg: W, bodyBg: W }); check('light site with no dark theme: filter (fallback)', p.dark());
p = page({ htmlBg: K, bodyBg: K, prefersDark: true }); check('site dark by itself: no filter', !p.dark());
p = page({ htmlBg: T, bodyBg: T, prefersDark: true, sheets: [{ cssRules: [{ media: { mediaText: '(prefers-color-scheme: dark)' } }] }] });
check('no own background + prefers-color-scheme: dark rules: no filter', old ? p.dark() : !p.dark());
p = page({ htmlBg: T, bodyBg: T, prefersDark: true, meta: 'light dark' }); check('<meta name=color-scheme content="light dark">: no filter', old ? p.dark() : !p.dark());
p = page({ htmlBg: T, bodyBg: T, prefersDark: false, sheets: [{ cssRules: [{ media: { mediaText: '(prefers-color-scheme: dark)' } }] }] });
check('dark rules but no dark appearance: filter', p.dark());
p = page({ htmlBg: T, bodyBg: T, prefersDark: true, sheets: [{ get cssRules() { throw new Error('cross-origin'); } }] }); check('unreadable cross-origin sheet only: filter (no crash)', p.dark());
p = page({ htmlBg: W, bodyBg: W, prefersDark: true, host: 'youtube.com' }); check('YouTube still light at first: filter', p.dark());
p.o.htmlBg = K; p.html.setAttribute('dark', ''); p.flush(); check('YouTube turns dark later (html[dark]): filter removed', old ? p.dark() : !p.dark());
p = page({ htmlBg: W, bodyBg: W, prefersDark: true }); p.o.htmlBg = K; p.fireWin('load'); check('dark by load +1.5/4/8 s re-check: filter removed', !p.dark());
p = page({ htmlBg: W, bodyBg: W }); p.html.setAttribute('data-omni-dark-addon', 'on'); p.flush(); check('Dark Reader add-on hook on: no invert filter', old ? p.dark() : !p.dark());
p.html.removeAttribute('data-omni-dark-addon'); p.flush(); check('add-on hook removed: filter back', p.dark());
console.log((fails ? 'FAIL' : 'PASS') + ': dark-standard host test ' + (n - fails) + '/' + n + (old ? ' (expectations of the unpatched script, negative control)' : ''));
process.exit(fails ? 1 : 0);
