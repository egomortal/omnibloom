// OMNI_DARK_VIDEO_PLANE_V1 host test: runs the dark-page user script from OmniDarkPages.h in a minimal fake DOM.
// usage: node dark_video_test.js <OmniDarkPages.h> [expect-old]   (expect-old: the unpatched script, a negative control)
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8'); const old = process.argv[3] === 'expect-old';
const js = src.slice(src.indexOf('R"JS(') + 5, src.indexOf(')JS"'));
let timers = [], fails = 0, n = 0;
function check(name, ok) { n++; if (!ok) fails++; console.log((ok ? 'PASS ' : 'FAIL ') + name); }
function el(tag) { const a = {}; return { tagName: tag, attrs: a, style: { setProperty() {} }, children: [],
  hasAttribute: k => k in a, getAttribute: k => (k in a ? a[k] : null), setAttribute: (k, v) => { a[k] = String(v); }, removeAttribute: k => { delete a[k]; },
  appendChild(c) { this.children.push(c); return c; } }; }
const listeners = {}, wl = {};
const html = el('html'), body = el('body'), head = el('head'); let videos = [];
const doc = { documentElement: html, body, head, fullscreenElement: null, webkitFullscreenElement: null,
  getElementById: id => head.children.find(c => c.id === id) || null, createElement: t => el(t),
  getElementsByTagName: t => (t === 'video' ? videos : []),
  addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); } };
const win = { document: doc, location: { protocol: 'https:', hostname: 'www.youtube.com' }, innerWidth: 1280, innerHeight: 720,
  getComputedStyle: () => ({ backgroundColor: 'rgb(255, 255, 255)', colorScheme: 'normal' }), matchMedia: () => ({ matches: false }),
  MutationObserver: class { observe() {} disconnect() {} }, setTimeout: (f) => { timers.push(f); return timers.length; }, clearTimeout: () => {},
  addEventListener: (t, f) => { (wl[t] = wl[t] || []).push(f); }, __omniDarkCfg: { v: 1, g: 0, on: ['youtube.com'], off: [] } };
win.window = win;
const flush = () => { for (let i = 0; i < 20 && timers.length; i++) { const t = timers; timers = []; t.forEach(f => f()); } };
const fire = t => { (listeners[t] || []).forEach(f => f({ type: t })); flush(); };
const dark = () => 'data-omnidark' in html.attrs;
vm.createContext(win); vm.runInContext(js, win); flush();
check('light page, no video: dark filter on', dark());
const big = { paused: true, ended: false, getBoundingClientRect: () => ({ left: 24, top: 102, right: 874, bottom: 580 }) };
videos = [big]; fire('loadeddata');
check('paused large video: dark stays on', dark());
big.paused = false; fire('play');
check('large video plays: filter off (plane eligible)', old ? dark() : !dark());
fire('playing'); check('still playing: filter stays off', old ? dark() : !dark());
big.paused = true; fire('pause'); check('pause: dark back on', dark());
big.paused = false; fire('play'); big.ended = true; big.paused = true; fire('ended'); check('ended: dark back on', dark());
const small = { paused: false, ended: false, getBoundingClientRect: () => ({ left: 100, top: 100, right: 400, bottom: 270 }) };
videos = [small]; fire('play'); check('small hover preview playing: dark stays on', dark());
const off = { paused: false, ended: false, getBoundingClientRect: () => ({ left: 0, top: 2000, right: 1280, bottom: 2720 }) };
videos = [off]; fire('play'); check('large video off screen: dark stays on', dark());
const shorts = { paused: false, ended: false, getBoundingClientRect: () => ({ left: 437, top: 0, right: 843, bottom: 720 }) };
videos = [small, shorts]; fire('playing'); check('Shorts-size video playing: filter off', old ? dark() : !dark());
shorts.paused = true; fire('pause'); doc.fullscreenElement = {}; (listeners['fullscreenchange'] || []).forEach(f => f()); flush();
check('fullscreen: filter off (unchanged rule)', !dark());
doc.fullscreenElement = null; (listeners['fullscreenchange'] || []).forEach(f => f()); flush(); check('leave fullscreen, paused: dark on', dark());
html.attrs['data-omni-dark'] = 'off'; videos = []; fire('emptied'); win.__omniDarkApply(); check('site switched off: no filter', !dark());
console.log((fails ? 'FAIL' : 'PASS') + ': dark-video host test ' + (n - fails) + '/' + n + (old ? ' (unpatched script, negative control)' : ''));
process.exit(fails ? 1 : 0);
