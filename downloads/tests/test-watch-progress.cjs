// OMNI_DL_WATCH_V1: player resume + watched marks store (watch-progress.js): key stability, thresholds, cap/eviction,
// tile state. Run: node tests/test-watch-progress.cjs   (from the downloads folder)
'use strict';
const assert = require('assert');
const W = require('../worker/assets/watch-progress.js');
let checks = 0;
const ok = (value, message) => { assert.ok(value, message); checks++; };
const eq = (a, b, message) => { assert.deepStrictEqual(a, b, message); checks++; };
const memory = () => { const m = new Map(); return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), raw: m }; };
const film = { place: 'internal', name: 'Example Film (2024).mkv', size: 4294967296 };

// Key stability: same file -> same key, no matter the session-signed id or extra row fields; different file -> different key.
const key = W.keyFor(film);
ok(/^w[a-f0-9]{16}$/.test(key), 'key shape');
eq(W.keyFor({ ...film, id: 'a'.repeat(32), place_label: 'Console storage', folder: 'Films', mtime: 1 }), key, 'library row and player info agree');
eq(W.keyFor({ ...film, id: 'b'.repeat(32) }), key, 'worker restart (new id) keeps the key');
ok(W.keyFor({ ...film, size: film.size + 1 }) !== key, 'size changes the key');
ok(W.keyFor({ ...film, place: 'usb0' }) !== key, 'place changes the key');
ok(W.keyFor({ ...film, name: 'Other.mkv' }) !== key, 'name changes the key');
eq(W.keyFor({ name: '', size: 1 }), null, 'no name -> no key');
eq(W.keyFor({ name: 'x.mp4', size: NaN }), null, 'bad size -> no key');
eq(W.keyFor(null), null, 'nothing -> no key');
ok(!key.includes('Example') && !key.includes('internal'), 'the key carries no name');

// Saving stores only the hash key and numbers.
const s = memory();
W.record(s, key, 754.2, 6000, 1000);
const stored = s.raw.get(W.STORE);
ok(!stored.includes('Example') && !stored.includes('mkv'), 'store has no file names');
eq(W.get(s, key), { p: 754.2, d: 6000, w: 0, t: 1000 }, 'position saved');
eq(W.record(s, 'not-a-key', 1, 2), null, 'bad key refused');
eq(W.record(s, key, 10, Infinity), null, 'unknown duration not saved');

// Resume thresholds: > 30 s and < duration - 30 s.
eq(W.resumeAt(W.get(s, key), 6000), 754.2, 'mid-film resumes');
eq(W.resumeAt({ p: 30, d: 6000, w: 0, t: 1 }, 6000), 0, 'exactly 30 s: start over');
eq(W.resumeAt({ p: 30.5, d: 6000, w: 0, t: 1 }, 6000), 30.5, 'just past 30 s: resume');
eq(W.resumeAt({ p: 5970, d: 6000, w: 0, t: 1 }, 6000), 0, 'last 30 s: start over');
eq(W.resumeAt({ p: 5969, d: 6000, w: 0, t: 1 }, 6000), 5969, 'just before the last 30 s: resume');
eq(W.resumeAt({ p: 100, d: 6000, w: 0, t: 1 }, 110), 0, 'the real duration wins over the saved one');
eq(W.resumeAt({ p: 100, d: 6000, w: 0, t: 1 }, Infinity), 100, 'unknown real duration uses the saved one');
eq(W.resumeAt(null, 6000), 0, 'nothing saved');

// Watched past 90 %, and it stays watched.
eq(W.record(s, key, 5399, 6000, 2000).w, 0, 'just under 90 %: not watched');
eq(W.record(s, key, 5400, 6000, 3000).w, 1, '90 %: watched');
eq(W.record(s, key, 12, 6000, 4000).w, 1, 'watching again from the start keeps the mark');

// Tile state.
eq(W.tileState({ p: 3000, d: 6000, w: 0, t: 1 }), { state: 'partial', fraction: 0.5 }, 'half way: progress bar');
eq(W.tileState({ p: 20, d: 6000, w: 0, t: 1 }), { state: 'none', fraction: 0 }, 'first 30 s: no mark');
eq(W.tileState({ p: 12, d: 6000, w: 1, t: 1 }).state, 'watched', 'watched tick');
eq(W.tileState(undefined).state, 'none', 'never played');
ok(/data-watch="partial"[^>]*aria-label="50% watched".*width:50%/.test(W.tileHtml({ p: 3000, d: 6000, w: 0, t: 1 })), 'partial html');
ok(/data-watch="watched".*Watched/.test(W.tileHtml({ p: 1, d: 6000, w: 1, t: 1 })), 'watched html');
eq(W.tileHtml(undefined), '', 'no mark html');

// Untrusted store contents are dropped on read.
const bad = memory();
bad.setItem(W.STORE, JSON.stringify({ [key]: { p: -1, d: 10, t: 1 }, wzz: { p: 1, d: 10, t: 1 }, ['w' + '1'.repeat(16)]: { p: 5, d: 10, w: 'yes', t: 2 }, ['w' + '2'.repeat(16)]: { p: 50, d: 10, t: 3 } }));
eq(Object.keys(W.load(bad)), ['w' + '1'.repeat(16)], 'only well-formed entries survive');
eq(W.load(bad)['w' + '1'.repeat(16)].w, 1, 'watched flag normalised');
const junk = memory(); junk.setItem(W.STORE, '{not json'); eq(W.load(junk), {}, 'broken JSON reads as empty');
eq(W.load({ getItem() { throw new Error('blocked'); } }), {}, 'blocked storage reads as empty');
ok(W.record({ getItem: () => null, setItem() { throw new Error('full'); } }, key, 100, 6000), 'a full store does not throw');

// Cap: at most 500 entries; the oldest go first.
const cap = memory();
const keys = [];
for (let i = 0; i < W.MAX + 25; i++) { const k = W.keyFor({ place: 'internal', name: 'clip' + i + '.mp4', size: i }); keys.push(k); W.record(cap, k, 100, 600, 10000 + i); }
eq(new Set(keys).size, keys.length, 'no key collisions across 525 files');
const all = W.load(cap);
eq(Object.keys(all).length, W.MAX, 'capped at 500');
ok(keys.slice(0, 25).every(k => !(k in all)), 'oldest 25 dropped');
ok(keys.slice(25).every(k => k in all), 'newest 500 kept');
W.record(cap, keys[25], 200, 600, 99999); // touch the oldest survivor, then add one more
const extra = W.keyFor({ place: 'usb0', name: 'new.mp4', size: 7 }); W.record(cap, extra, 100, 600, 100000);
const after = W.load(cap);
ok(keys[25] in after && extra in after && !(keys[26] in after), 'a recently played file survives eviction');

console.log('WATCH PROGRESS PASS: ' + checks + ' checks');
