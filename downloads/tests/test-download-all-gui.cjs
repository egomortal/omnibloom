// OMNI_DOWNLOAD_ALL_V1: the Downloads GUI side of "Download all..." against the REAL worker (queue held: nothing is
// fetched). #files= opens the confirm dialog (focus on "Download N files"), nothing is queued before the press, the
// press posts /api/jobs/batch with the token, the Queue view shows the waiting links and "Drop waiting links" clears them.
// node test-download-all-gui.cjs <outDir>   (serve_real_worker.py 8765 running; PW_CHANNEL=msedge optional)
const pw = require('playwright'); const fs = require('fs'); const path = require('path');
const outDir = process.argv[2] || path.join(require('os').tmpdir(), 'omni-download-all'); fs.mkdirSync(outDir, { recursive: true });
const BASE = 'http://127.0.0.1:' + (process.env.STUB_PORT || 8765) + '/downloads';
let failures = 0;
const check = (name, ok, data = {}) => { if (!ok) failures++; console.log((ok ? 'PASS ' : 'FAIL ') + name, ok ? '' : JSON.stringify(data)); };
const urls = Array.from({ length: 12 }, (_, i) => 'https://files.invalid/docs/report%20' + i + '.pdf');
const hash = '#files=' + encodeURIComponent(JSON.stringify({ v: 1, p: 'https://files.invalid/list', u: urls.concat(urls[0]) }));
(async () => {
  const b = await pw.chromium.launch({ args: ['--no-proxy-server'], ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}) });
  const p = await (await b.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  p.on('console', m => { if (m.type() === 'error' && !/404|400|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()); });
  await p.goto(BASE);
  await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
  const token = await p.evaluate(() => document.querySelector('meta[name="omni-session-token"]').content);
  const api = (url, body) => p.evaluate(async ([url, body, t]) => { const r = await fetch(url, { method: body ? 'POST' : 'GET', headers: { 'X-Omni-Token': t, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }); return { status: r.status, body: await r.json() }; }, [url, body, token]);
  check('G0 queue held', (await api('/api/queue', { paused: true })).status === 200);
  const before = (await api('/api/status')).body.jobs.length;

  await p.goto(BASE + hash);
  await p.waitForFunction(() => document.querySelector('#batch-dialog')?.open === true, null, { timeout: 5000 }).catch(() => {});
  check('G1 the list opens the confirm dialog', await p.evaluate(() => document.querySelector('#batch-dialog').open));
  check('G2 the fragment is removed at once', await p.evaluate(() => location.hash === ''));
  const texts = await p.evaluate(() => ({ h: document.querySelector('#batch-heading').textContent, b: document.querySelector('#batch-start').textContent, rows: [...document.querySelectorAll('#batch-list li')].map(n => n.textContent), focus: document.activeElement?.id, summary: document.querySelector('#batch-summary').textContent }));
  check('G3 heading and button count the unique links', texts.h === 'Download 12 files?' && texts.b === 'Download 12 files', texts);
  check('G4 rows show decoded names', texts.rows[0] === 'report 0.pdf' && texts.rows.length === 12, texts);
  check('G5 focus starts on the button', texts.focus === 'batch-start', texts);
  check('G6 summary names the page host', /files\.invalid/.test(texts.summary), texts);
  check('G7 nothing queued before the press', (await api('/api/status')).body.jobs.length === before);
  await p.screenshot({ path: path.join(outDir, 'download-all-01-dialog.png') });

  await p.keyboard.press('Shift');   // a controller press first puts the page in pad mode (as a D-pad press does)
  check('G8 Cross on the focused button (controller)', await p.evaluate(() => window.omniMediaController('saved.choose')) === true);
  await p.waitForFunction(() => !document.querySelector('#batch-dialog').open, null, { timeout: 5000 }).catch(() => {});
  const status = (await api('/api/status')).body;
  const queued = status.jobs.filter(j => j.state === 'queued' && urls.includes(j.url));
  check('G9 eight queued as original files, four held', queued.length === 8 && status.held === 4, { queued: queued.length, held: status.held });
  check('G10 toast reports it', /Added 12 files to Downloads · 4 wait/.test(await p.evaluate(() => document.querySelector('#toast').textContent)), { toast: await p.evaluate(() => document.querySelector('#toast').textContent) });
  await p.waitForFunction(() => document.querySelector('#held-note') && !document.querySelector('#held-note').hidden, null, { timeout: 5000 }).catch(() => {});
  check('G11 queue view shows the waiting links', await p.evaluate(() => document.querySelector('#held-text')?.textContent) === '4 more links wait for a free place in the queue.');
  await p.screenshot({ path: path.join(outDir, 'download-all-02-queue.png') });
  await p.click('#held-clear');
  await p.waitForFunction(() => document.querySelector('#held-note').hidden, null, { timeout: 5000 }).catch(() => {});
  check('G12 Drop waiting links empties the held list', (await api('/api/status')).body.held === 0 && await p.evaluate(() => document.querySelector('#held-note').hidden));

  await p.goto(BASE + '#files=' + encodeURIComponent(JSON.stringify({ v: 1, u: ['javascript:alert(1)'] })));
  await p.waitForTimeout(400);
  check('G13 a bad list opens nothing and says so', !(await p.evaluate(() => document.querySelector('#batch-dialog').open)) && /rejected/.test(await p.evaluate(() => document.querySelector('#toast').textContent)));
  for (const j of (await api('/api/status')).body.jobs) if (j.state === 'queued') await api('/api/cancel', { id: j.id });
  check('G14 no page errors', errs.length === 0, { errs });
  await b.close();
  console.log(failures ? 'DOWNLOAD ALL GUI FAIL: ' + failures : 'DOWNLOAD ALL GUI PASS');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error('DOWNLOAD ALL GUI FAIL', e); process.exit(1); });
