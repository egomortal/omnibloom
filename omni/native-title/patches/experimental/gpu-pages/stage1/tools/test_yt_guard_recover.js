// OMNI_YT_GUARD_RECOVER_V1 test: patches a copy of omni-ytattest/OmniYtGuard.h with apply_yt_guard_recover.py (twice:
// idempotent), node-checks the page script, drives it through the console's "status 3 after ok" pattern and the edge
// cases, then runs the guard's own guard_sim_test.js against the PATCHED header (the pre-ok rules must be unchanged).
// Usage: node test_yt_guard_recover.js   (PYTHON=python3 on Linux/WSL; default python on Windows)
const fs = require('fs'), os = require('os'), path = require('path'), cp = require('child_process');
const ATT = path.join(__dirname, '..', '..', '..', 'omni-ytattest');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ytgrec-')), entry = path.join(tmp, 'engine', 'entry');
fs.mkdirSync(entry, { recursive: true });
fs.copyFileSync(path.join(ATT, 'OmniYtGuard.h'), path.join(entry, 'OmniYtGuard.h'));
let all = true;
const okv = (c, m) => { console.log((c ? 'ok  ' : 'FAIL') + ' ' + m); if (!c) all = false; };
const ap = (n) => cp.execFileSync(PY, ['-I', path.join(__dirname, 'apply_yt_guard_recover.py'), tmp]).toString().trim();
okv(/applied OMNI_YT_GUARD_RECOVER_V1/.test(ap()), 'apply: applied');
okv(/already OMNI_YT_GUARD_RECOVER_V1/.test(ap()), 'apply again: already');
const src = fs.readFileSync(path.join(entry, 'OmniYtGuard.h'), 'utf8');
const js = src.slice(src.indexOf('R"JS(') + 5, src.indexOf(')JS"'));
fs.writeFileSync(path.join(tmp, 'guard.js'), js);
try { cp.execFileSync(process.execPath, ['--check', path.join(tmp, 'guard.js')]); okv(true, 'node --check guard page script'); }
catch (e) { okv(false, 'node --check: ' + e.stderr); }
okv(src.includes('/data/omni/ytguard-recover-off.flag') && src.split(')JS"').length === 2, 'kill switch present, one raw-string end');

function venc(n) { if (n < 128) return [n]; if (n < 16384) return [128 | (n & 63), n >> 6]; return [192 | (n & 31), (n >> 5) & 255, n >> 13]; }
function part(t, p) { return [...venc(t), ...venc(p.length), ...p]; }
function ump(st) { return Uint8Array.from([...part(21, new Array(300).fill(7)), ...part(58, [0x08, st])]); }
const rng = (a) => ({ length: a.length, start: i => a[i][0], end: i => a[i][1] });
// The console pattern (Lyt0-104557): attested early, status 3 ~12 s before the media stops at 60.0 (buffer drained),
// player torn down ~10 s after that (currentTime 0, paused, readyState 0).
function consoleVideo() {
  return (now) => {
    if (now >= 85) return { currentTime: 0, paused: true, seeking: false, ended: false, readyState: 0, buffered: rng([]) };
    const ct = Math.min(60, now * 0.8);
    return { currentTime: ct, paused: false, seeking: false, ended: false, readyState: ct < 57 ? 4 : ct < 60 ? 3 : 2, buffered: rng([[0, 60]]) };
  };
}
async function scenario(name, o) {
  let now = 0; const timers = [], said = [], store = Object.assign({}, o.store || {});
  const steps = o.plan.filter(e => e.st).map(e => e.st);
  const win = { prompt: (m, v) => { said.push(v); return null; }, addEventListener() {},
    fetch: async () => new Response(ump(steps.shift()), { status: 200 }) };
  win.top = win; if (o.off) win.__omniYtNoCutRecover = 1;
  const doc = { hidden: false, querySelector: () => o.video(now), getElementById: () => null,
    createElement: () => ({ setAttribute() {}, style: {} }), documentElement: { appendChild() {} } };
  const ctx = { window: win, location: { hostname: 'www.youtube.com', pathname: '/watch', search: '?v=abc', href: 'https://www.youtube.com/watch?v=abc', reload() {} },
    history: { state: null, replaceState() {} }, sessionStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => store[k] = v, removeItem: k => delete store[k] },
    performance: { now: () => now * 1000 }, setInterval: (f) => timers.push(f), setTimeout: () => {}, document: doc,
    XMLHttpRequest: function () {}, URL, URLSearchParams, Uint8Array, Promise };
  ctx.XMLHttpRequest.prototype = { open() {}, send() {} };
  new Function(...Object.keys(ctx), js)(...Object.values(ctx));
  const f = win.fetch;
  for (const ev of o.plan) {
    while (now + 2 < ev.t) { now += 2; timers.forEach(t => t()); }
    now = ev.t;
    if (ev.st) await f('https://rr1---x.googlevideo.com/videoplayback?x');
    await new Promise(r => setTimeout(r, 5)); timers.forEach(t => t());
  }
  const rl = said.filter(x => /^reload/.test(x));
  const ok = rl.length === o.reloads && (!o.kind || rl.every(x => x.startsWith(o.kind))) && (!o.saw || said.some(x => o.saw.test(x)))
    && (!o.pos || rl.every(x => o.pos.test(x)));
  okv(ok, name + ': ' + (rl.join(' / ') || '(no reload)') + (o.saw ? ' | ' + (said.find(x => o.saw.test(x)) || '(missing ' + o.saw + ')') : ''));
}
(async () => {
  const cut = [{ t: 4, st: 2 }, { t: 7, st: 1 }, { t: 16, st: 2 }, { t: 66, st: 3 }, { t: 120 }];
  // console pattern -> exactly one cache-bypass reload, at the last real position (57-59 s, not 0)
  await scenario('cut after ok (console pattern)', { plan: cut, video: consoleVideo(), reloads: 1, kind: 'reload cut-after-ok', pos: / pos=5[789] / });
  // the player is already torn down when status 3 arrives -> still reloads at the remembered position
  await scenario('torn down before the status', { plan: [{ t: 4, st: 2 }, { t: 7, st: 1 }, { t: 90, st: 3 }, { t: 100 }], video: consoleVideo(), reloads: 1, kind: 'reload cut-after-ok', pos: / pos=5[789] / });
  // kill switch -> old behaviour (no reload)
  await scenario('kill switch', { plan: cut, video: consoleVideo(), off: 1, reloads: 0 });
  // status 1 again before the buffer drains -> cleared, no reload
  await scenario('status 1 cancels', { plan: [{ t: 4, st: 2 }, { t: 7, st: 1 }, { t: 74, st: 3 }, { t: 76, st: 1 }, { t: 82 }], video: (now) => ({ currentTime: now - 25, paused: false, seeking: false, readyState: 4, buffered: rng([[0, now - 10]]) }), reloads: 0, saw: /^cut cleared/ });
  // paused by the user with a full buffer -> waits, no reload
  await scenario('paused waits', { plan: [{ t: 4, st: 2 }, { t: 7, st: 1 }, { t: 74, st: 3 }, { t: 95 }], video: () => ({ currentTime: 49, paused: true, seeking: false, readyState: 4, buffered: rng([[0, 60]]) }), reloads: 0 });
  // cap: already 3 reloads for this video in the last 10 min -> gave up once, no reload
  await scenario('cap reached', { plan: cut, video: consoleVideo(), store: { 'omniYtGuardRc:abc': '3|' + Date.now() }, reloads: 0, saw: /^cut after ok, gave up/ });
  // cap expired (last reload 11 min ago) -> reload allowed again, try=1
  await scenario('cap expired', { plan: cut, video: consoleVideo(), store: { 'omniYtGuardRc:abc': '3|' + (Date.now() - 660000) }, reloads: 1, kind: 'reload cut-after-ok', pos: / try=1 / });
  // healthy playback with status 2 after ok (seen in the good v052ae runs) -> no reload
  await scenario('status 2 after ok only', { plan: [{ t: 4, st: 2 }, { t: 7, st: 1 }, { t: 16, st: 2 }, { t: 120 }], video: (now) => ({ currentTime: now - 3, paused: false, seeking: false, readyState: 4, buffered: rng([[0, now + 10]]) }), reloads: 0 });
  // the guard's own simulator against the patched header (pre-ok rules unchanged)
  fs.copyFileSync(path.join(ATT, 'guard_sim_test.js'), path.join(entry, 'guard_sim_test.js'));
  const r = cp.spawnSync(process.execPath, [path.join(entry, 'guard_sim_test.js')]);
  const out = r.stdout.toString();
  okv(r.status === 0 && !/FAIL/.test(out), 'guard_sim_test.js on the patched header (' + (out.match(/^ok /gm) || []).length + ' ok)');
  if (r.status !== 0) console.log(out + r.stderr);
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(all ? 'ALL OK' : 'FAILURES'); process.exit(all ? 0 : 1);
})();
