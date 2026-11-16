// OMNI_HELP_V1: node tests for the Help & troubleshooting page (omni/pages/bundle-clean4/help): topic search, "Open it"
// links against routes.json, docs anchors against the local Markdown, QR encoding checked by an independent reader,
// controller focus order, no network, registered and linked from the start page.
// node tools/test_help_page.cjs
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const repo = path.join(__dirname, '..');
const pages = path.join(repo, 'omni', 'pages', 'bundle-clean4');
const dir = path.join(pages, 'help');
const M = require(path.join(dir, 'model.js'));
const ids = M.TOPICS.map(t => t.id);
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { e.message = name + ': ' + e.message; throw e; } };

// The bundled encoder, loaded the way the page loads it (a plain script defining `qrcodegen`).
const ctx = {};
vm.runInNewContext(fs.readFileSync(path.join(pages, 'share', 'vendor', 'qrcodegen.js'), 'utf8') + '\nthis.qrcodegen = qrcodegen;', ctx);
const Q = ctx.qrcodegen;

// --- an independent QR reader for single-block symbols (versions 1-5, levels L / M), written from ISO/IEC 18004 ----
const EC = { 1: [7, 10], 2: [10, 16], 3: [15, 26], 4: [20, 18], 5: [26, 24] };     // ECC codewords per block [L, M]
const TOTAL = { 1: 26, 2: 44, 3: 70, 4: 100, 5: 134 };
const BLOCKS_M = { 4: 2, 5: 2 };                                                    // v4-M / v5-M have 2 blocks: not read here
const MASKS = [(x, y) => (x + y) % 2 === 0, (x, y) => y % 2 === 0, (x) => x % 3 === 0, (x, y) => (x + y) % 3 === 0,
  (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0, (x, y) => (x * y) % 2 + (x * y) % 3 === 0,
  (x, y) => ((x * y) % 2 + (x * y) % 3) % 2 === 0, (x, y) => ((x + y) % 2 + (x * y) % 3) % 2 === 0];
const EXP = [], LOG = [];
for (let i = 0, v = 1; i < 255; i++) { EXP[i] = v; LOG[v] = i; v <<= 1; if (v & 256) v ^= 0x11d; }
const mul = (a, b) => (a && b ? EXP[(LOG[a] + LOG[b]) % 255] : 0);
function rsRemainder(data, deg) {
  let g = [1];
  for (let i = 0; i < deg; i++) { const ng = new Array(g.length + 1).fill(0); g.forEach((c, j) => { ng[j] ^= c; ng[j + 1] ^= mul(c, EXP[i]); }); g = ng; }
  const r = data.concat(new Array(deg).fill(0));
  for (let i = 0; i < data.length; i++) { const f = r[i]; if (f) for (let j = 1; j < g.length; j++) r[i + j] ^= mul(g[j], f); }
  return r.slice(data.length);
}
function bch15(d) { let r = d << 10; for (let i = 14; i >= 10; i--) if ((r >> i) & 1) r ^= 0x537 << (i - 10); return (d << 10) | r; }
function readQr(rows) {
  const size = rows.length, version = (size - 17) / 4, at = (x, y) => rows[y][x];
  assert.ok(version >= 1 && version <= 5, 'reader handles versions 1-5');
  // finder patterns: 7x7 dark ring, light ring, 3x3 dark centre, at three corners
  for (const [ox, oy] of [[0, 0], [size - 7, 0], [0, size - 7]])
    for (let y = 0; y < 7; y++) for (let x = 0; x < 7; x++) {
      const d = Math.max(Math.abs(x - 3), Math.abs(y - 3));
      assert.strictEqual(at(ox + x, oy + y), d !== 2, 'finder at ' + ox + ',' + oy);
    }
  for (let i = 8; i < size - 8; i++) { assert.strictEqual(at(i, 6), i % 2 === 0, 'timing row'); assert.strictEqual(at(6, i), i % 2 === 0, 'timing column'); }
  // format: 15 bits around the top-left finder, a copy split between the other two
  let f1 = 0, f2 = 0;
  const a = [[8, 0], [8, 1], [8, 2], [8, 3], [8, 4], [8, 5], [8, 7], [8, 8], [7, 8], [5, 8], [4, 8], [3, 8], [2, 8], [1, 8], [0, 8]];
  a.forEach(([x, y], i) => { if (at(x, y)) f1 |= 1 << i; });
  for (let i = 0; i < 8; i++) if (at(size - 1 - i, 8)) f2 |= 1 << i;
  for (let i = 8; i < 15; i++) if (at(8, size - 15 + i)) f2 |= 1 << i;
  assert.strictEqual(f1, f2, 'both format copies agree');
  const fmt = (f1 ^ 0x5412) >> 10;
  assert.strictEqual(bch15(fmt), f1 ^ 0x5412, 'format BCH');
  const level = { 1: 'L', 0: 'M' }[fmt >> 3], mask = fmt & 7;
  assert.ok(level, 'single-block levels only');
  assert.ok(!(level === 'M' && BLOCKS_M[version]), 'single block');
  assert.strictEqual(at(8, size - 8), true, 'dark module');
  // function modules: finders + separators + format areas, timing, the one alignment pattern (v2+), dark module
  const fn = (x, y) => (x < 9 && y < 9) || (x >= size - 8 && y < 9) || (x < 9 && y >= size - 8) || x === 6 || y === 6
    || (version >= 2 && Math.abs(x - (size - 7)) <= 2 && Math.abs(y - (size - 7)) <= 2);
  const bits = [];
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let v = 0; v < size; v++) for (let j = 0; j < 2; j++) {
      const x = right - j, up = ((right + 1) & 2) === 0, y = up ? size - 1 - v : v;
      if (!fn(x, y)) bits.push(at(x, y) !== MASKS[mask](x, y) ? 1 : 0);
    }
  }
  const words = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) words.push(bits.slice(i, i + 8).reduce((s, b) => (s << 1) | b, 0));
  assert.strictEqual(words.length, TOTAL[version], 'codeword count');
  const ec = EC[version][level === 'L' ? 0 : 1], data = words.slice(0, TOTAL[version] - ec);
  assert.deepStrictEqual(rsRemainder(data, ec), words.slice(data.length), 'Reed-Solomon check');
  const stream = data.flatMap(w => [7, 6, 5, 4, 3, 2, 1, 0].map(i => (w >> i) & 1));
  const take = (k) => { let v = 0; for (let i = 0; i < k; i++) v = (v << 1) | stream.shift(); return v; };
  assert.strictEqual(take(4), 4, 'byte mode');
  const len = take(8), bytes = [];
  for (let i = 0; i < len; i++) bytes.push(take(8));
  return { version, level, mask, text: Buffer.from(bytes).toString('utf8') };
}

// --- search ---------------------------------------------------------------------------------------------------------
test('topics: the asked-for set, each with short steps', () => {
  assert.deepStrictEqual(ids, ['youtube', 'shield', 'memory', 'slow', 'sound', 'keyboard', 'controller', 'downloads', 'translate', 'reset']);
  for (const t of M.TOPICS) {
    assert.ok(t.title && t.steps.length >= 3 && t.steps.length <= 6, t.id);
    for (const s of t.steps) assert.ok(s.length <= 200, t.id + ' step too long: ' + s);
  }
  assert.strictEqual(new Set(ids).size, ids.length);
});

test('search filters topics', () => {
  assert.deepStrictEqual(M.filter(M.TOPICS, ''), ids);
  assert.deepStrictEqual(M.filter(M.TOPICS, '   '), ids);
  assert.deepStrictEqual(M.filter(M.TOPICS, 'youtube'), ['youtube']);
  assert.deepStrictEqual(M.filter(M.TOPICS, 'YOUTUBE won\'t'), ['youtube']);
  assert.deepStrictEqual(M.filter(M.TOPICS, 'red shield'), ['shield']);
  assert.ok(M.filter(M.TOPICS, 'memory').includes('memory'));
  assert.ok(M.filter(M.TOPICS, 'mem').includes('memory'));                   // word prefixes
  assert.deepStrictEqual(M.filter(M.TOPICS, 'ory'), []);                      // not word middles
  assert.deepStrictEqual(M.filter(M.TOPICS, 'lite mode crash'), ['memory']);   // every word has to match
  assert.ok(M.filter(M.TOPICS, 'without cache').includes('slow'));
  assert.deepStrictEqual(M.filter(M.TOPICS, 'no sound'), ['sound']);
  assert.ok(M.filter(M.TOPICS, 'mute').includes('sound'));
  assert.ok(M.filter(M.TOPICS, 'keyboard').includes('keyboard'));
  assert.ok(M.filter(M.TOPICS, 'dualsense').includes('controller'));
  assert.ok(M.filter(M.TOPICS, 'download').includes('downloads'));
  assert.deepStrictEqual(M.filter(M.TOPICS, 'google privacy'), ['translate']);
  assert.ok(M.filter(M.TOPICS, 'reset').includes('reset'));
  assert.deepStrictEqual(M.filter(M.TOPICS, 'zzzz'), []);
  assert.deepStrictEqual(M.filter(M.TOPICS, '<script>'), []);
  assert.deepStrictEqual(M.filter(null, 'x'), []);
  assert.strictEqual(M.norm('  Won’t   PLAY!! '), 'wont play');
});

// --- links ----------------------------------------------------------------------------------------------------------
test('every "Open it" link resolves in routes.json', () => {
  const routes = JSON.parse(fs.readFileSync(path.join(pages, 'routes.json'), 'utf8')).routes.map(r => r.path);
  let links = 0;
  for (const t of M.TOPICS) {
    if (!t.open) { assert.strictEqual(M.href(t), null); continue; }
    links++;
    assert.ok(routes.includes(t.open.path), t.id + ': ' + t.open.path + ' is not in routes.json');
    assert.ok(fs.existsSync(path.join(pages, t.open.path)), t.id + ': ' + t.open.path + ' missing');
    assert.strictEqual(M.href(t), '../' + t.open.path);
    assert.strictEqual(M.omniUrl(t), 'omni://pages/' + t.open.path);
    assert.ok(t.open.label);
  }
  assert.ok(links >= 8);
  assert.ok(routes.includes('help/index.html'));
});

test('every docs address is the project repo and its anchor exists in the local docs', () => {
  const readme = fs.readFileSync(path.join(repo, 'README.md'), 'utf8');
  assert.ok(readme.includes('Repository: <' + M.REPO + '>'), 'REPO matches README');
  const slug = (h) => h.trim().toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, '').replace(/\s/g, '-');   // GitHub's anchors
  for (const t of M.TOPICS) {
    const url = M.docUrl(t);
    assert.ok(url.startsWith(M.REPO + '/blob/main/'), url);
    const [file, anchor] = t.doc.split('#');
    const md = fs.readFileSync(path.join(repo, file), 'utf8');
    const anchors = md.split(/\r?\n/).filter(l => /^#{1,6} /.test(l)).map(l => slug(l.replace(/^#+ /, '')));
    assert.ok(anchors.includes(anchor), t.id + ': #' + anchor + ' not a heading in ' + file);
  }
  assert.strictEqual(slug('"Media downloads unavailable" (LT / double bumper)'), 'media-downloads-unavailable-lt--double-bumper');
});

// --- QR -------------------------------------------------------------------------------------------------------------
test('QR: a known string decodes back with an independent reader', () => {
  const m = M.qr(Q, M.REPO);                      // 38 bytes: version 3, boosted from L to M (still fits)
  assert.strictEqual(m.size, 29);
  assert.strictEqual(m.version, 3);
  const r = readQr(m.rows);
  assert.strictEqual(r.text, 'https://github.com/egomortal/omnibloom');
  assert.strictEqual(r.level, 'M');
  const v1 = Q.QrCode.encodeSegments([Q.QrSegment.makeBytes([...Buffer.from('help')])], Q.QrCode.Ecc.MEDIUM, 1, 1, 3, false);
  const grid = (c) => Array.from({ length: c.size }, (_, y) => Array.from({ length: c.size }, (_, x) => c.getModule(x, y)));
  assert.deepStrictEqual(Object.values(readQr(grid(v1))), [1, 'M', 3, 'help']);
  const v2 = Q.QrCode.encodeSegments([Q.QrSegment.makeBytes([...Buffer.from('Omni help: café ☕')])], Q.QrCode.Ecc.LOW, 2, 2, -1, false);
  const back = readQr(grid(v2));
  assert.deepStrictEqual([back.version, back.level, back.text], [2, 'L', 'Omni help: café ☕']);
  assert.strictEqual(M.qr(null, 'x'), null);      // no encoder: the page says "QR code unavailable"
});

test('QR: every topic\'s code is a sensible size; the SVG path covers exactly the dark modules', () => {
  for (const t of M.TOPICS) {
    const m = M.qr(Q, M.docUrl(t));
    assert.ok(m.version <= 10, t.id + ' version ' + m.version);
    const p = M.qrPath(m), dark = m.rows.flat().filter(Boolean).length;
    assert.strictEqual((p.match(/M/g) || []).length, dark);
    assert.ok(p.startsWith('M4,4h1v1h-1z'));       // top-left finder corner, after the quiet zone
  }
});

// --- controller -----------------------------------------------------------------------------------------------------
test('controller: focus order', () => {
  assert.deepStrictEqual(M.rows(M.TOPICS, ids, null), ['search'].concat(ids.map(i => 'topic-' + i)));
  const open = M.rows(M.TOPICS, ids, 'memory');
  assert.deepStrictEqual(open.slice(2, 6), ['topic-shield', 'topic-memory', 'open-memory', 'topic-slow']);
  assert.deepStrictEqual(M.rows(M.TOPICS, ids, 'youtube').slice(0, 3), ['search', 'topic-youtube', 'topic-shield']);   // no link: no extra row
  assert.deepStrictEqual(M.rows(M.TOPICS, ['sound'], 'sound'), ['search', 'topic-sound', 'open-sound']);
  assert.deepStrictEqual(M.rows(M.TOPICS, ['nope'], null), ['search']);
});

test('controller: D-pad, Cross, Circle, Triangle, Square, L1 / R1', () => {
  const T = M.TOPICS, st = M.initial();
  const go = (a) => M.step(st, a, T);
  assert.strictEqual(go('up').handled, true);
  assert.strictEqual(st.focus, 'search');                                     // top: stays
  assert.deepStrictEqual(go('cross'), { handled: true, go: null, edit: true }); // Cross on search: type
  go('down'); go('down'); go('down');
  assert.strictEqual(st.focus, 'topic-memory');
  go('cross');
  assert.strictEqual(st.open, 'memory');
  go('down');
  assert.strictEqual(st.focus, 'open-memory');
  assert.deepStrictEqual(go('cross'), { handled: true, go: '../tabs/index.html', edit: false });
  go('down');
  assert.strictEqual(st.focus, 'topic-slow');
  go('up'); go('left');                                                       // left on the link closes, focus to header
  assert.deepStrictEqual([st.open, st.focus], [null, 'topic-memory']);
  go('right');
  assert.strictEqual(st.open, 'memory');
  go('down'); go('circle');                                                   // Circle closes the open topic first
  assert.deepStrictEqual([st.open, st.focus], [null, 'topic-memory']);
  assert.strictEqual(go('circle').handled, false);                            // then it is Omni's Back
  go('up'); go('cross');
  assert.strictEqual(st.open, 'shield');
  go('down'); assert.strictEqual(st.focus, 'open-shield');
  go('down'); go('cross');                                                    // opening another closes the first
  assert.deepStrictEqual([st.open, st.focus], ['memory', 'topic-memory']);
  go('cross'); assert.strictEqual(st.open, null);
  go('r1'); assert.strictEqual(st.focus, 'topic-slow');
  go('l1'); go('l1'); assert.strictEqual(st.focus, 'topic-shield');
  for (let i = 0; i < 20; i++) go('r1');
  assert.strictEqual(st.focus, 'topic-reset');
  for (let i = 0; i < 20; i++) go('down');
  assert.strictEqual(st.focus, 'topic-reset');                                // bottom: stays (no link while closed)
  go('triangle'); assert.strictEqual(st.focus, 'search');
  go('r1'); assert.strictEqual(st.focus, 'topic-youtube');
  assert.strictEqual(go('square').handled, false);                            // nothing to clear
  assert.strictEqual(go('options').handled, false);
});

test('controller: search narrows the list and moves focus and the open topic out of hidden topics', () => {
  const T = M.TOPICS, st = M.initial();
  st.focus = 'topic-downloads'; st.open = 'downloads';
  st.query = 'sound'; M.refresh(st, T);
  assert.deepStrictEqual([st.open, st.focus], [null, 'search']);
  M.step(st, 'down', T);
  assert.strictEqual(st.focus, 'topic-sound');
  M.step(st, 'cross', T); M.step(st, 'down', T);
  assert.strictEqual(st.focus, 'open-sound');
  st.query = 'mute'; M.refresh(st, T);                                         // still shown: everything stays
  assert.deepStrictEqual([st.open, st.focus], ['sound', 'open-sound']);
  assert.strictEqual(M.step(st, 'square', T).handled, true);                  // Square clears the search
  assert.strictEqual(st.query, '');
  assert.deepStrictEqual([st.open, st.focus], ['sound', 'open-sound']);
  st.query = 'zzzz'; M.refresh(st, T);
  assert.deepStrictEqual([st.open, st.focus], [null, 'search']);
  M.step(st, 'down', T); M.step(st, 'r1', T);
  assert.strictEqual(st.focus, 'search');                                     // nothing to move to
});

test('hints name the right buttons', () => {
  assert.ok(M.hint('playstation').includes('Cross: open / close') && M.hint('playstation').includes('Circle: back'));
  assert.ok(M.hint('xbox').includes('A: open / close') && M.hint('xbox').includes('LB / RB: topic') && M.hint('xbox').includes('Y: search'));
  assert.strictEqual(M.hint('weird'), M.hint('playstation'));
});

// --- page -----------------------------------------------------------------------------------------------------------
test('page: no network, CSP, no personal data, registered and linked', () => {
  const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
  const model = fs.readFileSync(path.join(dir, 'model.js'), 'utf8'), app = fs.readFileSync(path.join(dir, 'app.js'), 'utf8');
  const css = fs.readFileSync(path.join(dir, 'help.css'), 'utf8');
  // the only web address is the public repo, used as QR text (never loaded); the SVG namespace is not a request
  assert.deepStrictEqual([...new Set(model.match(/https?:\/\/[^'"\s)]+/g))], [M.REPO]);
  assert.deepStrictEqual(app.match(/https?:\/\/[^'"\s)]+/g), ['http://www.w3.org/2000/svg']);
  assert.ok(!/https?:\/\//.test(html + css));
  assert.ok(!/fetch\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function/.test(model + app));
  assert.ok(html.includes("connect-src 'none'") && html.includes("script-src 'self'") && html.includes("default-src 'none'"));
  assert.ok(!/<script>/.test(html));
  assert.deepStrictEqual(html.match(/<script src="[^"]+"/g), ['<script src="../share/vendor/qrcodegen.js"', '<script src="model.js"', '<script src="app.js"']);
  assert.ok(fs.existsSync(path.join(pages, 'share', 'vendor', 'qrcodegen.js')));
  for (const id of ['search', 'topics', 'count', 'none', 'hint']) assert.ok(html.includes('id="' + id + '"'), '#' + id);
  const all = html + model + app + css + fs.readFileSync(path.join(dir, 'SOURCES.md'), 'utf8');
  assert.ok(!/[A-Za-z]:\\|\/home\/|\/Users\/|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|@[a-z0-9-]+\.[a-z]/i.test(all), 'no local paths, IPs or e-mail');
  const notice = fs.readFileSync(path.join(dir, 'SOURCES.md'), 'utf8');
  assert.ok(notice.includes('MIT') && notice.includes('Project Nayuki') && notice.includes('v1.8.0'));
  const start = fs.readFileSync(path.join(pages, 'start', 'index.html'), 'utf8');
  assert.ok(start.includes('<a href="../timer/index.html">Couch timer</a><a href="../help/index.html">Help</a>'));
});

console.log('all ' + n + ' help page tests passed');
