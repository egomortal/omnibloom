// OMNI_COUCH_TIMER_V1: node tests for the Couch timer page (omni/pages/bundle-clean4/timer): time math, drift-free
// ticking, persistence across reloads, alarm next-day rollover, controller layout, the bundled WAV, no network.
// node tools/test_timer_page.cjs
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const pages = path.join(__dirname, '..', 'omni', 'pages', 'bundle-clean4');
const dir = path.join(pages, 'timer');
const M = require(path.join(dir, 'model.js'));
const MIN = 60000;
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { e.message = name + ': ' + e.message; throw e; } };
const local = (y, mo, d, h, mi, s) => new Date(y, mo - 1, d, h, mi, s || 0, 0).getTime();
function rng(seed) { return () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }; }

test('time math and formatting', () => {
  assert.strictEqual(M.hmsToMs(1, 2, 3), 3723000);
  assert.strictEqual(M.hmsToMs(99, 99, 99), M.hmsToMs(23, 59, 59));   // clamped
  assert.strictEqual(M.formatCountdown(5 * MIN), '5:00');
  assert.strictEqual(M.formatCountdown(5 * MIN - 1), '5:00');          // rounds up: 0:00 only at the very end
  assert.strictEqual(M.formatCountdown(4 * MIN + 59000), '4:59');
  assert.strictEqual(M.formatCountdown(1), '0:01');
  assert.strictEqual(M.formatCountdown(0), '0:00');
  assert.strictEqual(M.formatCountdown(-500), '0:00');
  assert.strictEqual(M.formatCountdown(M.hmsToMs(1, 5, 9)), '1:05:09');
  assert.deepStrictEqual(M.formatStopwatch(61234), { main: '1:01', frac: '.2' });
  assert.deepStrictEqual(M.formatStopwatch(3600000 + 999), { main: '1:00:00', frac: '.9' });
  assert.strictEqual(M.formatClock(local(2026, 11, 16, 7, 5)), '07:05');
  assert.strictEqual(M.formatIn(30000), 'under a minute');
  assert.strictEqual(M.formatIn(90 * MIN), '1 h 30 min');
  assert.strictEqual(M.formatIn(120 * MIN), '2 h');
  assert.strictEqual(M.formatIn(5 * MIN - 1), '5 min');
  assert.deepStrictEqual(M.PRESETS_MIN, [1, 3, 5, 10, 15, 30]);
});

test('countdown: start, pause, resume, reset, presets', () => {
  const t0 = 1_800_000_000_000, cd = M.newCountdown(3 * MIN);
  M.cdStart(cd, t0);
  assert.strictEqual(cd.end, t0 + 3 * MIN);
  assert.strictEqual(M.cdRemaining(cd, t0 + 61000), 119000);
  M.cdPause(cd, t0 + 61000);
  assert.strictEqual(cd.end, null);
  assert.strictEqual(M.cdRemaining(cd, t0 + 10 * MIN), 119000);       // paused: time does not move
  M.cdStart(cd, t0 + 10 * MIN);
  assert.strictEqual(cd.end, t0 + 10 * MIN + 119000);
  M.cdReset(cd);
  assert.deepStrictEqual(cd, { dur: 3 * MIN, end: null, left: 3 * MIN });
  M.cdSet(cd, 15 * MIN);
  assert.strictEqual(cd.left, 15 * MIN);
  cd.left = 0; M.cdStart(cd, t0);                                      // finished: Start runs the full time again
  assert.strictEqual(cd.end, t0 + 15 * MIN);
});

test('stopwatch: laps and splits', () => {
  const sw = M.newStopwatch();
  M.swToggle(sw, 1000);
  assert.ok(M.swLap(sw, 11000));
  assert.ok(M.swLap(sw, 26000));
  M.swToggle(sw, 30000);
  assert.strictEqual(M.swElapsed(sw, 99999), 29000);
  assert.strictEqual(M.swLap(sw, 40000), false);                        // no laps while stopped
  M.swToggle(sw, 50000);
  assert.strictEqual(M.swElapsed(sw, 51000), 30000);
  assert.deepStrictEqual(M.lapRows(sw.laps), [{ n: 2, split: 15000, total: 25000 }, { n: 1, split: 10000, total: 10000 }]);
  for (let i = 0; i < 200; i++) M.swLap(sw, 52000 + i);
  assert.strictEqual(sw.laps.length, M.MAX_LAPS);
  M.swReset(sw);
  assert.deepStrictEqual(sw, { start: null, acc: 0, laps: [] });
});

test('drift: late timers never make the countdown slip', () => {
  const r = rng(7), t0 = 1_800_000_000_000, st = M.initial();
  M.cdSet(st.cd, 10 * MIN); M.cdStart(st.cd, t0);
  let t = t0, ticks = 0, naiveT = t0, last = null, ringAt = null, maxLate = 0;
  while (ringAt === null && ticks < 5000) {
    const late = r() < 0.05 ? 250 + Math.floor(r() * 600) : Math.floor(r() * 40);   // throttling and jitter
    t += M.nextDelay(st, t) + late;
    ticks++;
    naiveT += 1000 + late;                        // a naive "minus one second per setInterval" counter, same lateness
    if (M.check(st, t).length) ringAt = t;
    const shown = Math.ceil(M.cdRemaining(st.cd, t) / 1000);
    assert.strictEqual(shown, Math.max(0, Math.ceil((st.cd.end === null ? 0 : st.cd.end - t) / 1000)));
    if (last !== null) assert.ok(shown <= last, 'never goes backwards');
    last = shown;
    maxLate = Math.max(maxLate, late);
  }
  assert.ok(ringAt !== null, 'rang');
  assert.ok(ringAt - (t0 + 10 * MIN) >= 0 && ringAt - (t0 + 10 * MIN) <= maxLate + 2, 'rang on time, within one late tick');
  assert.strictEqual(st.ring.since, t0 + 10 * MIN, 'the ring is dated at the real end');
  const naiveZeroAt = t0 + (naiveT - t0) / ticks * 600;   // when that counter would finally show 0:00
  assert.ok(naiveZeroAt - (t0 + 10 * MIN) > 5000, 'a plain counter would ring ' + Math.round((naiveZeroAt - t0 - 10 * MIN) / 1000) + ' s late');
});

test('drift: each wait is measured to the next boundary', () => {
  const st = M.initial(), t0 = 1_800_000_000_000;     // t0 is a whole second
  M.cdStart(st.cd, t0 + 250);                          // ends at x.250
  assert.strictEqual(M.nextDelay(st, t0 + 250), 751);  // next whole second of wall clock comes first
  assert.strictEqual(M.nextDelay(st, t0 + 1100), 151); // countdown boundary at x.250
  assert.strictEqual(M.nextDelay(st, t0 + 1249), 2);
  assert.strictEqual(M.nextDelay(st, t0 + 1900), 101); // late tick: the next wait is short, not a full second
  const sw = M.initial(); sw.mode = 'stopwatch'; M.swToggle(sw.sw, t0 + 30);
  assert.strictEqual(M.nextDelay(sw, t0 + 95), 36);    // next tenth of the stopwatch
  sw.mode = 'countdown';
  assert.strictEqual(M.nextDelay(sw, t0 + 95), 906);   // not shown: no tenths ticking
  const al = M.initial(); al.al.at = t0 + 300;
  assert.strictEqual(M.nextDelay(al, t0 + 100), 201);
  const idle = M.initial();
  for (let i = 0; i < 3000; i += 137) { const d = M.nextDelay(idle, t0 + i); assert.ok(d >= 2 && d <= 1001); }
});

test('persistence: running, paused and finished timers survive a reload', () => {
  const t0 = 1_800_000_000_000, st = M.initial();
  st.mode = 'stopwatch';
  M.cdSet(st.cd, 5 * MIN); M.cdStart(st.cd, t0);
  M.swToggle(st.sw, t0); M.swLap(st.sw, t0 + 4000);
  st.al.h = 6; st.al.m = 30; M.alArm(st.al, t0);
  const saved = M.serialize(st);
  assert.ok(!/"left":\d+,"running"/.test(saved) && JSON.parse(saved).cd.end === t0 + 5 * MIN, 'a target time is stored, not a counter');

  const back = M.restore(saved, t0 + 2 * MIN);                       // reloaded two minutes later
  assert.strictEqual(back.mode, 'stopwatch');
  assert.strictEqual(M.cdRemaining(back.cd, t0 + 2 * MIN), 3 * MIN);
  assert.strictEqual(M.swElapsed(back.sw, t0 + 2 * MIN), 2 * MIN);
  assert.deepStrictEqual(back.sw.laps, [4000]);
  assert.strictEqual(back.al.at, st.al.at);
  assert.strictEqual(back.ring, null);

  M.cdPause(back.cd, t0 + 2 * MIN);
  const paused = M.restore(M.serialize(back), t0 + 60 * MIN);
  assert.strictEqual(M.cdRemaining(paused.cd, t0 + 60 * MIN), 3 * MIN);

  const ended = M.restore(saved, t0 + 7 * MIN);                      // ended 2 min ago while closed: rings
  assert.deepStrictEqual(ended.ring, { kind: 'countdown', since: t0 + 5 * MIN });
  assert.strictEqual(ended.cd.end, null);
  const stale = M.restore(saved, t0 + 30 * MIN);                     // ended 25 min ago: shown as missed
  assert.strictEqual(stale.ring, null);
  assert.deepStrictEqual(stale.missed, { kind: 'countdown', at: t0 + 5 * MIN });
  M.dismiss(ended);
  assert.strictEqual(ended.ring, null);
  assert.strictEqual(ended.cd.left, 5 * MIN);
});

test('persistence: bad or tampered data falls back safely', () => {
  const d = M.initial();
  for (const bad of [null, '', 'nope', '{"v":2}', '[]', '{"v":1,"mode":"x","cd":5}']) {
    const s = M.restore(bad, 1e12);
    assert.strictEqual(s.mode, 'countdown');
    assert.deepStrictEqual(s.cd, d.cd);
  }
  const s = M.restore(JSON.stringify({ v: 1, mode: 'alarm', cd: { dur: 1e15, end: 'x', left: -5 }, sw: { start: 5e12, acc: -1, laps: [1, 'a', -2, 3] },
    al: { h: 40, m: -3, at: 0 }, ring: { kind: 'boom', since: 1 } }), 1e12);
  assert.strictEqual(s.mode, 'alarm');
  assert.strictEqual(s.cd.dur, M.hmsToMs(23, 59, 59));
  assert.strictEqual(s.cd.left, 0);
  assert.strictEqual(s.sw.start, 1e12);                               // a start in the future is pulled back to now
  assert.strictEqual(s.sw.acc, 0);
  assert.deepStrictEqual(s.sw.laps, [1, 3]);
  assert.deepStrictEqual(s.al, { h: 23, m: 0, at: null });
  assert.strictEqual(s.ring, null);
});

test('alarm: next-day rollover', () => {
  const night = local(2026, 11, 16, 23, 30);
  assert.strictEqual(M.nextAlarmAt(7, 0, night), local(2026, 11, 17, 7, 0));
  assert.strictEqual(M.nextAlarmAt(23, 45, night), local(2026, 11, 16, 23, 45));
  assert.strictEqual(M.nextAlarmAt(23, 30, night), local(2026, 11, 17, 23, 30));        // exactly now: tomorrow
  assert.strictEqual(M.nextAlarmAt(23, 30, night - 1), night);
  assert.strictEqual(M.nextAlarmAt(0, 0, local(2026, 11, 30, 23, 59)), local(2026, 12, 1, 0, 0));
  assert.strictEqual(M.nextAlarmAt(6, 0, local(2026, 12, 31, 22, 0)), local(2027, 1, 1, 6, 0));
  assert.strictEqual(M.nextAlarmAt(9, 0, local(2028, 2, 28, 10, 0)), local(2028, 2, 29, 9, 0)); // leap day
  // the alarm lands on the wall-clock time on the next calendar day even across a DST change (where there is one)
  for (const [y, mo, d] of [[2026, 3, 7], [2026, 3, 28], [2026, 10, 24], [2026, 10, 31]]) {
    const at = new Date(M.nextAlarmAt(7, 0, local(y, mo, d, 8, 0)));
    assert.deepStrictEqual([at.getDate(), at.getHours(), at.getMinutes()], [new Date(y, mo - 1, d + 1).getDate(), 7, 0]);
  }
  const st = M.initial(); st.al.h = 7; st.al.m = 0; M.alArm(st.al, night);
  assert.deepStrictEqual(M.check(st, local(2026, 11, 17, 6, 59, 59)), []);
  assert.deepStrictEqual(M.check(st, local(2026, 11, 17, 7, 0, 0)), ['alarm']);
  assert.deepStrictEqual(st.ring, { kind: 'alarm', since: local(2026, 11, 17, 7, 0) });
  assert.strictEqual(st.al.at, null);
  assert.deepStrictEqual(M.check(st, local(2026, 11, 17, 7, 11)), []);    // rings 10 min at most, then "missed"
  assert.strictEqual(st.ring, null);
  assert.strictEqual(st.missed.kind, 'alarm');
});

test('controller: rows, D-pad moves, digit editing', () => {
  const cd = M.rows('countdown');
  assert.deepStrictEqual(cd[0], ['tab-countdown', 'tab-stopwatch', 'tab-alarm']);
  assert.deepStrictEqual(cd[2], ['preset-1', 'preset-3', 'preset-5', 'preset-10', 'preset-15', 'preset-30']);
  assert.deepStrictEqual(M.navigate(cd, { r: 2, c: 5 }, 'down'), { r: 3, c: 1 });
  assert.deepStrictEqual(M.navigate(cd, { r: 3, c: 0 }, 'up'), { r: 2, c: 0 });
  assert.deepStrictEqual(M.navigate(cd, { r: 1, c: 0 }, 'down'), { r: 2, c: 2 });
  assert.deepStrictEqual(M.navigate(cd, { r: 3, c: 1 }, 'right'), { r: 3, c: 1 });
  assert.deepStrictEqual(M.navigate(cd, { r: 3, c: 1 }, 'down'), { r: 3, c: 1 });
  assert.deepStrictEqual(M.navigate(cd, { r: 9, c: 9 }, ''), { r: 3, c: 1 });
  assert.deepStrictEqual(M.rows('stopwatch')[1], ['sw-go', 'sw-lap', 'sw-reset']);
  assert.deepStrictEqual(M.rows('alarm').slice(1), [['al-display'], ['al-go']]);
  assert.deepStrictEqual(M.editStep([0, 5, 0], 1, 'up', M.CD_LIMITS), [0, 6, 0]);
  assert.deepStrictEqual(M.editStep([0, 0, 0], 2, 'down', M.CD_LIMITS), [0, 0, 59]);    // wraps
  assert.deepStrictEqual(M.editStep([23, 59], 0, 'up', M.AL_LIMITS), [0, 59]);
  assert.deepStrictEqual(M.editStep([1, 2], 0, 'left', M.AL_LIMITS), [1, 2]);
  assert.strictEqual(M.editField(0, 'left', 3), 0);
  assert.strictEqual(M.editField(1, 'right', 3), 2);
  assert.strictEqual(M.editField(2, 'right', 3), 2);
  assert.ok(M.hint('xbox', 'normal').includes('LB / RB: mode') && M.hint('xbox', 'normal').includes('B: back'));
  assert.ok(M.hint('playstation', 'edit').includes('Circle: cancel'));
  assert.strictEqual(M.hint('playstation', 'ring'), 'Cross or Circle: stop');
});

test('sound: feature detection and the bundled WAV', () => {
  const fake = (r) => ({ play() {}, canPlayType() { if (r instanceof Error) throw r; return r; } });
  assert.strictEqual(M.canPlayWav(fake('maybe')), true);
  assert.strictEqual(M.canPlayWav(fake('probably')), true);
  assert.strictEqual(M.canPlayWav(fake('')), false);
  assert.strictEqual(M.canPlayWav(fake('no')), false);
  assert.strictEqual(M.canPlayWav(fake(new Error('x'))), false);
  assert.strictEqual(M.canPlayWav({ canPlayType: () => 'maybe' }), false);   // no play(): not a media element
  assert.strictEqual(M.canPlayWav(null), false);
  const gen = require(path.join(__dirname, 'gen_timer_beep.cjs'));
  const wav = fs.readFileSync(path.join(dir, 'beep.wav'));
  assert.ok(wav.equals(gen.makeWav()), 'beep.wav matches tools/gen_timer_beep.cjs (re-run it)');
  assert.strictEqual(wav.toString('ascii', 0, 4), 'RIFF');
  assert.strictEqual(wav.toString('ascii', 8, 12), 'WAVE');
  assert.strictEqual(wav.readUInt16LE(20), 1);          // PCM
  assert.strictEqual(wav.readUInt32LE(24), 16000);
  assert.strictEqual(wav.readUInt32LE(40), wav.length - 44);
  assert.ok(wav.length < 64 * 1024);
});

test('page: no network, CSP, registered and linked', () => {
  const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
  const js = ['model.js', 'app.js'].map(f => fs.readFileSync(path.join(dir, f), 'utf8')).join('\n');
  const css = fs.readFileSync(path.join(dir, 'timer.css'), 'utf8');
  assert.ok(!/https?:\/\//.test(js + html + css));
  assert.ok(!/fetch\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|AudioContext|innerHTML|eval\(|new Function/.test(js));
  assert.ok(html.includes("connect-src 'none'") && html.includes("media-src 'self'") && html.includes("script-src 'self'"));
  assert.ok(!/<script>/.test(html) && html.includes('src="beep.wav"'));
  for (const id of M.MODES.map(m => M.rows(m)).flat(2).concat(['ring', 'hint', 'sound', 'missed', 'beep']))
    assert.ok(html.includes('id="' + id + '"'), 'element #' + id);
  const routes = JSON.parse(fs.readFileSync(path.join(pages, 'routes.json'), 'utf8')).routes;
  assert.ok(routes.some(r => r.path === 'timer/index.html'));
  assert.ok(fs.readFileSync(path.join(pages, 'start', 'index.html'), 'utf8').includes('href="../timer/index.html"'));
});

console.log('all ' + n + ' timer page tests passed');
