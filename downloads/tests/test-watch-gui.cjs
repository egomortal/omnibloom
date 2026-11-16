// OMNI_DL_WATCH_V1: the player's resume prompt / position saving and the Library tile marks, in a real browser.
// Serves the real player.html + assets from a small in-process server with a fake /api/files/link and a 120 s tone.
// node tests/test-watch-gui.cjs [outDir]   env: PW_CHANNEL=msedge, WATCH_PORT=8793
'use strict';
const pw = require('playwright'); const fs = require('fs'); const path = require('path'); const http = require('http');
const W = require('../worker/assets/watch-progress.js');
const outDir = process.argv[2] || path.join(require('os').tmpdir(), 'omni-watch'); fs.mkdirSync(outDir, { recursive: true });
const WORKER = path.join(__dirname, '..', 'worker'), PORT = Number(process.env.WATCH_PORT || 8793), BASE = 'http://127.0.0.1:' + PORT;
const TOKEN = 'T'.repeat(43), FID = 'c'.repeat(32);
let failures = 0;
const check = (name, ok, data = {}) => { if (!ok) failures++; console.log((ok ? 'PASS ' : 'FAIL ') + name, ok ? '' : JSON.stringify(data)); };

// 120 s, 8 kHz, 8-bit mono WAV.
const SECONDS = 120, RATE = 8000, frames = RATE * SECONDS;
const wav = Buffer.alloc(44 + frames);
wav.write('RIFF', 0); wav.writeUInt32LE(36 + frames, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20);
wav.writeUInt16LE(1, 22); wav.writeUInt32LE(RATE, 24); wav.writeUInt32LE(RATE, 28); wav.writeUInt16LE(1, 32); wav.writeUInt16LE(8, 34);
wav.write('data', 36); wav.writeUInt32LE(frames, 40);
for (let i = 0; i < frames; i++) wav[44 + i] = 128 + Math.round(20 * Math.sin(i * 2 * Math.PI * 440 / RATE));
const FILE = { place: 'internal', name: 'Long Tone.wav', size: wav.length };
const KEY = W.keyFor(FILE);

const ASSETS = { 'player.js': 'text/javascript', 'player.css': 'text/css', 'watch-progress.js': 'text/javascript', 'files-library.js': 'text/javascript', 'files-library.css': 'text/css', 'icons.svg': 'image/svg+xml' };
const LIB_PAGE = `<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/assets/files-library.css"><section id="files-library"></section>
<script src="/assets/watch-progress.js"></script><script src="/assets/files-library.js"></script><script>
const files = [
  { id: '${'1'.repeat(32)}', name: 'Half.mp4', folder: '', place: 'internal', place_label: 'Console storage', size: 1000, mtime: 1700000000, kind: 'video', mime: 'video/mp4', job_title: '', category: 'video' },
  { id: '${'2'.repeat(32)}', name: 'Done.mkv', folder: 'Films', place: 'usb0', place_label: 'USB drive 1', size: 2000, mtime: 1700000000, kind: 'video', mime: 'video/x-matroska', job_title: '', category: 'video' },
  { id: '${'3'.repeat(32)}', name: 'Fresh.mp3', folder: '', place: 'internal', place_label: 'Console storage', size: 3000, mtime: 1700000000, kind: 'audio', mime: 'audio/mpeg', job_title: '', category: 'audio' },
  { id: '${'4'.repeat(32)}', name: 'Notes.pdf', folder: '', place: 'internal', place_label: 'Console storage', size: 4000, mtime: 1700000000, kind: 'pdf', mime: 'application/pdf', job_title: '', category: 'document' }];
OmniFilesLibrary.mount(document.getElementById('files-library'), { listFiles: async () => ({ files, total: files.length, truncated: false }), fileLink: async () => ({}), fileAction: async () => ({}) });
</script>`;

const server = http.createServer((req, res) => {
  const url = new URL(req.url, BASE);
  if (url.pathname === '/player') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); return res.end(fs.readFileSync(path.join(WORKER, 'player.html'), 'utf8').replace('__TOKEN__', TOKEN)); }
  if (url.pathname === '/downloads') { res.writeHead(200, { 'Content-Type': 'text/html' }); return res.end('<!doctype html><title>downloads</title>'); }
  if (url.pathname === '/lib') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); return res.end(LIB_PAGE); }
  const asset = /^\/assets\/([a-z-]+\.(?:js|css|svg))$/.exec(url.pathname);
  if (asset && ASSETS[asset[1]]) { res.writeHead(200, { 'Content-Type': ASSETS[asset[1]] + '; charset=utf-8' }); return res.end(fs.readFileSync(path.join(WORKER, 'assets', asset[1]))); }
  if (url.pathname === '/api/files/link' && req.method === 'POST' && req.headers['x-omni-token'] === TOKEN) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ id: FID, ...FILE, kind: 'audio', mime: 'audio/x-wav', area: 'files', url: '/api/files/stream?id=' + FID + '&exp=9999999999&sig=' + 'd'.repeat(64), expires: 9999999999 }));
  }
  if (url.pathname === '/api/files/stream') {
    const range = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range || '');
    if (range) {
      const start = Number(range[1]), end = range[2] ? Math.min(Number(range[2]), wav.length - 1) : wav.length - 1;
      res.writeHead(206, { 'Content-Type': 'audio/x-wav', 'Accept-Ranges': 'bytes', 'Content-Range': `bytes ${start}-${end}/${wav.length}`, 'Content-Length': end - start + 1 });
      return res.end(wav.subarray(start, end + 1));
    }
    res.writeHead(200, { 'Content-Type': 'audio/x-wav', 'Accept-Ranges': 'bytes', 'Content-Length': wav.length }); return res.end(wav);
  }
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => server.listen(PORT, '127.0.0.1', r));
  let browser;
  try {
    browser = await pw.chromium.launch({ args: ['--no-proxy-server', '--autoplay-policy=no-user-gesture-required'], ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}) });
    const p = await (await browser.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
    const errs = []; p.on('pageerror', e => errs.push(String(e)));
    p.on('console', m => { if (m.type() === 'error' && !/404|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()); });
    const seed = async entries => { await p.goto(BASE + '/downloads'); await p.evaluate(([k, v]) => { localStorage.clear(); if (v) localStorage.setItem(k, JSON.stringify(v)); }, [W.STORE, entries]); };
    const open = async () => { await p.goto('about:blank'); await p.goto(BASE + '/player#id=' + FID); await p.waitForFunction(() => document.querySelector('audio')?.readyState >= 1, null, { timeout: 8000 }); };
    const entry = () => p.evaluate(([s, k]) => (JSON.parse(localStorage.getItem(s) || '{}'))[k] || null, [W.STORE, KEY]);
    const audio = () => p.$eval('audio', a => ({ t: a.currentTime, paused: a.paused }));
    const promptShown = () => p.evaluate(() => !!document.querySelector('.resume'));
    const focused = () => p.evaluate(() => document.activeElement?.dataset.resume || document.activeElement?.id || '');
    const saved = t => ({ [KEY]: { p: t, d: SECONDS, w: 0, t: Date.now() } });

    // Nothing saved: plays from the start, no prompt; pausing saves the position under the hash key.
    await seed(null); await open();
    check('W1 nothing saved: no prompt, playback starts', !(await promptShown()) && !(await audio()).paused, await audio());
    await p.evaluate(() => { const a = document.querySelector('audio'); a.currentTime = 75; a.pause(); });
    await p.waitForTimeout(200);
    const e1 = await entry();
    check('W2 pause saves the position (hash key, no file name stored)', e1 && Math.abs(e1.p - 75) < 1 && Math.abs(e1.d - SECONDS) < 1 && e1.w === 0 &&
      !(await p.evaluate(s => localStorage.getItem(s), W.STORE)).includes('Long'), { e1 });

    // Saved mid-film: prompt, D-pad between buttons, Cross resumes.
    await open();
    await p.waitForSelector('.resume', { timeout: 4000 });
    const text = await p.textContent('.resume');
    check('W3 prompt "Resume from 1:15?" with focus on Resume, playback held', /Resume from 1:15\?/.test(text) && await focused() === 'yes' && (await audio()).paused, { text, f: await focused() });
    await p.screenshot({ path: path.join(outDir, 'watch-01-prompt.png') });
    await p.keyboard.press('ArrowRight');
    const f1 = await focused();
    await p.keyboard.press('ArrowLeft');
    check('W4 Right/Left move between Resume and Start over', f1 === 'no' && await focused() === 'yes', { f1 });
    await p.keyboard.press('Enter');
    await p.waitForTimeout(400);
    const a1 = await audio();
    check('W5 Cross resumes at the saved spot and plays', !(await promptShown()) && a1.t >= 74.5 && a1.t < 78 && !a1.paused, a1);

    // Start over.
    await seed(saved(75)); await open(); await p.waitForSelector('.resume');
    await p.keyboard.press('ArrowRight'); await p.keyboard.press('Enter'); await p.waitForTimeout(300);
    const a2 = await audio();
    check('W6 Start over plays from 0', !(await promptShown()) && a2.t < 3 && !a2.paused, a2);
    await seed(saved(75)); await open(); await p.waitForSelector('.resume');
    await p.keyboard.press('Escape'); await p.waitForTimeout(300);
    check('W7 Circle in the prompt starts over (stays in the player)', !(await promptShown()) && (await audio()).t < 3 && new URL(p.url()).pathname === '/player', await audio());
    await seed(saved(75)); await open(); await p.waitForSelector('.resume');
    const hook = await p.evaluate(() => window.omniMediaController('saved.choose'));
    check('W8 the engine controller hook answers the prompt', hook === true && !(await promptShown()) && (await audio()).t >= 74.5, await audio());

    // No answer: resumes on its own after 5 s.
    await seed(saved(75)); await open(); await p.waitForSelector('.resume');
    const count = await p.textContent('.resume-count');
    await p.waitForFunction(() => !document.querySelector('.resume'), null, { timeout: 7000 }).catch(() => {});
    const a3 = await audio();
    check('W9 auto-resumes after 5 s', /Resuming in 5 s/.test(count) && !(await promptShown()) && a3.t >= 74.5 && !a3.paused, { count, a3 });

    // Thresholds: no prompt in the first 30 s or the last 30 s.
    await seed(saved(25)); await open(); await p.waitForTimeout(400);
    check('W10 saved at 0:25: no prompt, starts at 0', !(await promptShown()) && (await audio()).t < 3, await audio());
    await seed(saved(95)); await open(); await p.waitForTimeout(400);
    check('W11 saved in the last 30 s: no prompt, starts at 0', !(await promptShown()) && (await audio()).t < 3, await audio());

    // Saved every 5 s while playing, and watched past 90 %.
    await seed(null); await open();
    await p.evaluate(() => { document.querySelector('audio').currentTime = 50; });
    await p.waitForTimeout(5600);
    const e2 = await entry();
    check('W12 saved every 5 s while playing (no pause needed)', e2 && e2.p >= 50 && e2.p < 60 && e2.w === 0, { e2 });
    await p.evaluate(() => { const a = document.querySelector('audio'); a.currentTime = 110; a.pause(); });
    await p.waitForTimeout(200);
    check('W13 past 90 % the file is marked watched', (await entry())?.w === 1, { e: await entry() });
    await p.evaluate(() => { const a = document.querySelector('audio'); a.currentTime = 60; a.play().catch(() => {}); });
    await p.keyboard.press('Escape');
    await p.waitForURL(/\/downloads#view=files$/);
    const e3 = await entry();
    check('W14 Back saves on leaving and the watched mark stays', e3 && Math.abs(e3.p - 60) < 2 && e3.w === 1, { e3 });

    // Library tiles read the same store.
    const half = W.keyFor({ place: 'internal', name: 'Half.mp4', size: 1000 }), done = W.keyFor({ place: 'usb0', name: 'Done.mkv', size: 2000 }), pdf = W.keyFor({ place: 'internal', name: 'Notes.pdf', size: 4000 });
    await p.evaluate(([s, v]) => { localStorage.clear(); localStorage.setItem(s, JSON.stringify(v)); }, [W.STORE, { [half]: { p: 300, d: 600, w: 0, t: 1 }, [done]: { p: 10, d: 600, w: 1, t: 2 }, [pdf]: { p: 300, d: 600, w: 1, t: 3 } }]);
    await p.goto(BASE + '/lib');
    await p.waitForSelector('#files-library .lib-row');
    const tiles = await p.$$eval('#files-library .lib-row', rows => rows.map(r => ({ name: r.querySelector('strong').textContent, watch: r.querySelector('[data-watch]')?.dataset.watch || '', bar: r.querySelector('.lib-progress > span')?.style.width || '', label: r.querySelector('[data-watch]')?.getAttribute('aria-label') || r.querySelector('[data-watch]')?.textContent.trim() || '' })));
    check('W15 tiles: half-watched bar at 50 %, Watched tick, nothing on a fresh file or a PDF',
      JSON.stringify(tiles) === JSON.stringify([{ name: 'Half.mp4', watch: 'partial', bar: '50%', label: '50% watched' }, { name: 'Done.mkv', watch: 'watched', bar: '', label: '✓ Watched' }, { name: 'Fresh.mp3', watch: '', bar: '', label: '' }, { name: 'Notes.pdf', watch: '', bar: '', label: '' }]), { tiles });
    const barHeight = await p.$eval('#files-library .lib-progress', n => n.getBoundingClientRect().height);
    check('W16 the progress bar is thin', barHeight > 0 && barHeight <= 4, { barHeight });
    await p.screenshot({ path: path.join(outDir, 'watch-02-tiles.png') });
    check('W17 no page errors', errs.length === 0, { errs });
  } catch (error) {
    failures++; console.log('FAIL exception', error.stack);
  } finally {
    if (browser) await browser.close();
    server.close();
    console.log(failures ? failures + ' FAILED' : 'ALL PASS');
    process.exit(failures ? 1 : 0);
  }
})();
