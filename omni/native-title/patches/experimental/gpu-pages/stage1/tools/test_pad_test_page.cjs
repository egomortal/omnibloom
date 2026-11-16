// OMNI_PAD_TEST_V1: node tests of the Controller test page (pages bundle controller/model.js + app.js) on fake input.
// usage: node test_pad_test_page.cjs [<pages bundle dir>]
'use strict';
const path = require('path');
const assert = require('assert');
const bundle = process.argv[2] || (process.env.OMNI_PAGES_BUNDLE || path.join(__dirname, '..', '..', '..', '..', '..', '..', 'pages', 'bundle-clean4'));
const M = require(path.join(bundle, 'controller', 'model.js'));
const { createApp } = require(path.join(bundle, 'controller', 'app.js'));

let n = 0;
function test(name, fn) { fn(); ++n; }

// --- fake input -------------------------------------------------------------------------------------------------
const bit = (...ids) => ids.reduce((b, i) => b | (1 << i), 0) >>> 0;
const push = (o = {}) => Object.assign({ v: 1, pad: 1, b: 0, ax: [0, 0, 0, 0, 0, 0], tp: [[0, 0, 0], [0, 0, 0]], bat: -1, dz: 1,
  dzl: [1400, 2000, 2800, 3800], dzr: [1500, 2136, 2800, 3800], hold: 0 }, o);
const gpButtons = (pressed = [], values = {}) => Array.from({ length: 17 }, (_, i) => ({ pressed: pressed.includes(i), value: values[i] ?? (pressed.includes(i) ? 1 : 0) }));
const gamepad = (o = {}) => Object.assign({ connected: true, id: 'Wireless Controller (STANDARD GAMEPAD)', axes: [0, 0, 0, 0], buttons: gpButtons() }, o);

// --- model ------------------------------------------------------------------------------------------------------
test('push: every button bit lands on its own id', () => {
  for (const [id, sdl] of M.BUTTONS) {
    const s = M.fromPush(push({ b: bit(sdl) }));
    for (const [other] of M.BUTTONS) assert.strictEqual(s.buttons[other], other === id, id + ' / ' + other);
  }
  assert.strictEqual(M.fromPush(push({ b: bit(20) })).buttons.touchpad, true);
  assert.strictEqual(M.fromPush(push({ b: bit(31) })).buttons.cross, false);   // unknown bits ignored
});
test('push: raw axes normalise to -1..1, triggers to 0..1, raw kept', () => {
  const s = M.fromPush(push({ ax: [-32768, 32767, 16384, -16384, 32767, 0] }));
  assert.strictEqual(s.lx, -1); assert.strictEqual(s.ly, 1);
  assert.ok(Math.abs(s.rx - 0.5) < 0.001 && Math.abs(s.ry + 0.5) < 0.001);
  assert.strictEqual(s.l2, 1); assert.strictEqual(s.r2, 0);
  assert.deepStrictEqual(s.raw, { lx: -32768, ly: 32767, rx: 16384, ry: -16384, l2: 32767, r2: 0 });
});
test('push: touch points, battery, dead zone, hold', () => {
  const s = M.fromPush(push({ tp: [[1, 250, 500], [1, 1000, 0]], bat: 2, dz: 3, hold: 400 }));
  assert.deepStrictEqual(s.touch, [{ x: 0.25, y: 0.5 }, { x: 1, y: 0 }]);
  assert.strictEqual(s.battery, 'Medium');
  assert.strictEqual(s.dz.index, 3); assert.strictEqual(s.dz.left[3], 0.38);
  assert.strictEqual(s.holdMs, 400);
  assert.strictEqual(M.fromPush(push({ bat: -1 })).battery, null);
  assert.strictEqual(M.fromPush(push({ bat: 4 })).battery, 'Charging (wired)');
});
test('push: bad messages', () => {
  assert.strictEqual(M.fromPush(null), null);
  assert.strictEqual(M.fromPush({ v: 2 }), null);
  const s = M.fromPush(push({ dzl: [1, 2], ax: ['x', null], pad: 0 }));
  assert.strictEqual(s.pad, false); assert.strictEqual(s.dz, M.DZ_DEFAULT);
  const t = M.fromPush(push({ ax: ['x', null, 1e9, -1e9, -5, 1e9] }));
  assert.strictEqual(t.lx, 0); assert.strictEqual(t.rx, 1); assert.strictEqual(t.ry, -1); assert.strictEqual(t.l2, 0); assert.strictEqual(t.r2, 1);
});
test('gamepad API: standard mapping', () => {
  const s = M.fromGamepad(gamepad({ axes: [0.1, -0.2, 1, -1], buttons: gpButtons([0, 9, 12, 16], { 6: 0.3, 7: 1 }) }));
  assert.ok(s.buttons.cross && s.buttons.options && s.buttons.up && s.buttons.ps);
  assert.ok(!s.buttons.circle && !s.buttons.touchpad && !s.buttons.mute);
  assert.strictEqual(s.lx, 0.1); assert.strictEqual(s.ly, -0.2);
  assert.strictEqual(s.l2, 0.3); assert.strictEqual(s.r2, 1);
  assert.strictEqual(s.raw.rx, 32767); assert.strictEqual(s.raw.ry, -32768);
  assert.strictEqual(M.fromGamepad(null).pad, false);
  assert.strictEqual(M.fromGamepad(gamepad({ connected: false })).pad, false);
});
test('pick: fresh push > gamepad > last push > none', () => {
  const p = M.fromPush(push({ b: bit(0) }));
  assert.strictEqual(M.pick(1000, 0, p, [gamepad()]), p);
  assert.strictEqual(M.pick(M.PUSH_STALE_MS + 1, 0, p, [null, gamepad()]).source, 'gamepad');
  assert.strictEqual(M.pick(M.PUSH_STALE_MS + 1, 0, p, []), p);
  assert.strictEqual(M.pick(0, -1e9, null, null).source, 'none');
});
test('drift: 3 s at rest gives the max deviation; moving restarts', () => {
  const d = new M.DriftMeter();
  for (let t = 0; t <= 3040; t += 33) d.feed(t, t === 990 ? 0.05 : 0.02, t === 1980 ? -0.07 : 0.01);
  assert.ok(d.ready);
  assert.ok(Math.abs(d.max - Math.hypot(0.02, 0.07)) < 1e-9);
  assert.strictEqual(d.maxX, 0.05); assert.strictEqual(d.maxY, 0.07);
  d.feed(3100, 0.9, 0);                       // the user moves the stick
  assert.ok(!d.ready && d.since === null);
  d.feed(3200, 0.01, 0);
  assert.ok(!d.ready); assert.ok(d.progress(4700) > 0.49 && d.progress(4700) < 0.51);
  for (let t = 3200; t <= 6300; t += 50) d.feed(t, 0.01, 0);
  assert.ok(d.ready); assert.strictEqual(d.max, 0.01);
});
test('drift: old samples leave the 3 s window', () => {
  const d = new M.DriftMeter();
  d.feed(0, 0.3, 0);
  for (let t = 100; t <= 6000; t += 100) d.feed(t, 0.02, 0);
  assert.ok(d.ready); assert.strictEqual(d.max, 0.02);
});
test('suggest: smallest size that clears both sticks by the margin', () => {
  const dz = M.DZ_DEFAULT;
  assert.strictEqual(M.suggest(0.02, 0.02, dz).index, 0);              // Small covers it; Medium is set
  assert.strictEqual(M.suggest(0.02, 0.02, dz).level, 'ok');
  assert.ok(/Small would too/.test(M.suggest(0.02, 0.02, dz).text));
  assert.strictEqual(M.suggest(0.15, 0.05, dz).index, 1);
  assert.ok(/Your setting fits: Medium/.test(M.suggest(0.15, 0.05, dz).text));
  const big = M.suggest(0.30, 0.02, dz);
  assert.strictEqual(big.index, 3); assert.strictEqual(big.level, 'warn');
  assert.ok(/Suggested: Extra large \(now Medium\)/.test(big.text) && /Browser settings > Stick dead zone/.test(big.text));
  assert.strictEqual(M.suggest(0.36, 0, dz).level, 'bad');
  assert.strictEqual(M.suggest(0.12, 0.2, { index: 0, left: dz.left, right: dz.right }).index, 2);
});
test('trail: keeps the last 24 distinct points', () => {
  const tr = new M.Trail();
  assert.ok(tr.add(0, 0)); assert.ok(!tr.add(0.001, 0));
  for (let i = 1; i <= 40; ++i) tr.add(i / 100, 0);
  assert.strictEqual(tr.points.length, 24); assert.strictEqual(tr.points[23].x, 0.4);
});
test('labels follow the glyph setting', () => {
  assert.strictEqual(M.label('cross', 'playstation'), 'Cross'); assert.strictEqual(M.label('cross', 'xbox'), 'A');
  assert.ok(/Hold Circle/.test(M.leaveHint('playstation'))); assert.ok(/Hold B/.test(M.leaveHint('xbox')));
});

// --- app on a fake document ---------------------------------------------------------------------------------------
function fakeDoc() {
  const els = {};
  const ops = [];
  const mk = (tag) => ({ tag, textContent: '', className: '', style: {}, attrs: {}, children: [],
    width: 320, height: 320,
    setAttribute(k, v) { this.attrs[k] = v; },
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); },
    querySelectorAll(sel) { return this.children.filter((c) => sel === '.' + c.className); },
    getContext() { return this.tag === 'canvas' ? { ops, clearRect() {}, beginPath() {}, arc(x, y, r) { ops.push(['arc', x, y, r]); }, stroke() {}, fill() {}, moveTo() {}, lineTo() {} } : null; } });
  ['source', 'buttons', 'raw-l', 'raw-r', 'drift-l', 'drift-r', 'dz-name', 'name-l2', 'name-r2', 'bar-l2', 'bar-r2', 'val-l2', 'val-r2',
    'touchpad', 'tp-state', 'tp-note', 'suggest', 'dz-now', 'battery', 'leave-hint', 'leave-bar', 'leave-fill'].forEach((id) => { els[id] = mk('div'); });
  els['stick-l'] = mk('canvas'); els['stick-r'] = mk('canvas');
  return { els, ops, getElementById: (id) => els[id] || null, createElement: mk };
}
function app(opts = {}) {
  const doc = fakeDoc();
  const clock = { t: 0 };
  const pads = opts.pads || [];
  const a = createApp({ model: M, document: doc, glyphs: opts.glyphs, now: () => clock.t, getGamepads: () => pads });
  return { a, doc, clock, pads };
}

test('app: buttons light from the shell push; triggers, raw values, battery', () => {
  const { a, doc, clock } = app();
  assert.strictEqual(doc.els.buttons.children.length, M.BUTTONS.length);
  clock.t = 10;
  assert.strictEqual(a.push(push({ b: bit(0, 20), ax: [1000, -2000, 0, 0, 16384, 32767], bat: 3 })), true);
  a.frame(16);
  const chip = (id) => doc.els.buttons.children.find((c) => c.attrs['data-id'] === id);
  assert.strictEqual(chip('cross').className, 'btn on'); assert.strictEqual(chip('circle').className, 'btn');
  assert.strictEqual(doc.els.touchpad.className, 'touchpad on'); assert.strictEqual(doc.els['tp-state'].textContent, 'Pressed');
  assert.strictEqual(doc.els['raw-l'].textContent, 'x 1000 · y -2000');
  assert.strictEqual(doc.els['bar-r2'].style.width, '100.0%'); assert.strictEqual(doc.els['val-l2'].textContent, '50% · 16384');
  assert.strictEqual(doc.els.battery.textContent, 'Full');
  assert.strictEqual(doc.els.source.textContent, 'Live from Omni');
  assert.strictEqual(a.push({ v: 9 }), false);
});
test('app: dead-zone circle drawn at Omni\'s radius; fingers drawn', () => {
  const { a, doc, clock } = app();
  clock.t = 1; a.push(push({ dz: 2, tp: [[1, 500, 500], [0, 0, 0]] })); a.frame(2);
  const R = 160 - 14;
  assert.ok(doc.ops.some((o) => o[0] === 'arc' && Math.abs(o[3] - R * 0.28) < 1e-9), 'Large dead zone circle');
  assert.strictEqual(doc.els.touchpad.children.length, 1);   // one finger (tp-state is its own element here)
});
test('app: drift readout after 3 s idle and a suggestion (text only)', () => {
  const { a, doc, clock } = app();
  for (let t = 0; t <= 3100; t += 33) { clock.t = t; a.push(push({ ax: [Math.round(0.3 * 32767), 0, 600, -600, 0, 0] })); a.frame(t); }
  assert.ok(/^Drift at rest: 30\.0%/.test(doc.els['drift-l'].textContent), doc.els['drift-l'].textContent);
  assert.strictEqual(doc.els['drift-l'].className, 'drift warn');
  assert.strictEqual(doc.els['drift-r'].className, 'drift ok');
  assert.ok(/Suggested: Extra large \(now Medium\)/.test(doc.els.suggest.textContent), doc.els.suggest.textContent);
  assert.strictEqual(doc.els.suggest.className, 'suggest warn');
});
test('app: falls back to the Gamepad API when the shell is silent', () => {
  const { a, doc, pads } = app({ glyphs: 'xbox' });
  pads.push(gamepad({ buttons: gpButtons([1]) }));
  a.frame(100);
  assert.strictEqual(a.state().source, 'gamepad');
  assert.strictEqual(doc.els.buttons.children.find((c) => c.attrs['data-id'] === 'circle').textContent, 'B');
  assert.strictEqual(doc.els.buttons.children.find((c) => c.attrs['data-id'] === 'circle').className, 'btn on');
  assert.strictEqual(doc.els['name-l2'].textContent, 'LT');
  assert.ok(/touchpad/.test(doc.els['tp-note'].textContent));
});
test('app: leave progress bar follows the shell\'s Circle hold', () => {
  const { a, doc, clock } = app();
  clock.t = 5; a.push(push({ hold: 500 })); a.frame(6);
  assert.strictEqual(doc.els['leave-bar'].className, 'leave on'); assert.strictEqual(doc.els['leave-fill'].style.width, '50%');
  clock.t = 7; a.push(push({ hold: 0 })); a.frame(8);
  assert.strictEqual(doc.els['leave-bar'].className, 'leave');
});
test('app: no controller', () => {
  const { a, doc } = app();
  a.frame(1);
  assert.ok(/Waiting for a controller/.test(doc.els.source.textContent));
  assert.strictEqual(doc.els.suggest.textContent, 'Connect a controller to measure drift.');
});

console.log('test_pad_test_page: ' + n + ' tests passed');
