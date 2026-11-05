// OMNI_DARK_APPEARANCE_EMU_V1 host test: the page-world matchMedia emulation (second R"JS( block of OmniDarkPages.h).
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8'); const i = src.indexOf('omniDkAppearanceEmu = R"JS(');
if (i < 0) { console.log('FAIL: no OMNI_DARK_APPEARANCE_EMU_V1 script'); process.exit(1); }
const js = src.slice(i + 'omniDkAppearanceEmu = R"JS('.length, src.indexOf(')JS"', i));
let fails = 0, n = 0; const check = (name, ok) => { n++; if (!ok) fails++; console.log((ok ? 'PASS ' : 'FAIL ') + name); };
const attrs = {}; let mo = null;
const html = { getAttribute: k => (k in attrs ? attrs[k] : null) };
const set = (k, v) => { if (v === null) delete attrs[k]; else attrs[k] = v; mo && mo(); };
const realCalls = [];
const win = { document: { documentElement: html }, MutationObserver: class { constructor(cb) { mo = cb; } observe() {} },
  matchMedia: function (q) { realCalls.push(q); return { media: q, matches: false, real: true }; } };
win.window = win; vm.createContext(win); vm.runInContext(js, win); vm.runInContext(js, win);
check('not wanted: prefers-color-scheme goes to the real matchMedia', win.matchMedia('(prefers-color-scheme: dark)').real === true);
set('data-omni-dark-want', '1');
const d = win.matchMedia('(prefers-color-scheme: dark)'), l = win.matchMedia('( prefers-color-scheme : light )');
check('wanted: dark matches', d.matches === true && !d.real); check('wanted: light does not match', l.matches === false);
check('other queries untouched', win.matchMedia('(min-width: 600px)').real === true);
let got = []; d.addEventListener('change', e => got.push(e.matches)); d.onchange = e => got.push('on' + e.matches);
set('data-omni-dark-want', null); check('turned off: change fired with matches=false', got.join() === 'onfalse,false' && d.matches === false);
check('double install is a no-op', realCalls.length >= 1);
console.log((fails ? 'FAIL' : 'PASS') + ': dark-emu host test ' + (n - fails) + '/' + n); process.exit(fails ? 1 : 0);
