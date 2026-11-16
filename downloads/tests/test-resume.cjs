// OMNI_DL_RESUME_V1: pause / resume / retry buttons on the queue rows, by pointer and by controller.
// node test-resume.cjs <outDir>   (STUB_PROBE=1 stub_worker.py serving the GUI at 127.0.0.1:8765; PW_CHANNEL=msedge)
const pw = require('playwright'); const fs = require('fs'); const path = require('path');
const outDir = process.argv[2] || path.join(require('os').tmpdir(), 'omni-resume'); fs.mkdirSync(outDir, { recursive: true });
const BASE = 'http://127.0.0.1:' + (process.env.STUB_PORT || 8765) + '/downloads';
const log = []; let failures = 0;
const check = (name, ok, data = {}) => { if (!ok) failures++; log.push({ check: name, pass: !!ok, ...data }); console.log((ok ? 'PASS ' : 'FAIL ') + name, ok ? '' : JSON.stringify(data)); };
(async () => {
  const b = await pw.chromium.launch({ args: ['--no-proxy-server'], ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}) });
  const p = await (await b.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  p.on('console', m => { if (m.type() === 'error' && !/404|400|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()); });
  const shot = name => p.screenshot({ path: path.join(outDir, name + '.png') });
  await p.goto(BASE);
  await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
  const token = await p.evaluate(() => document.querySelector('meta[name="omni-session-token"]').content);
  const post = (url, body) => p.evaluate(async ([url, body, t]) => { const r = await fetch(url, { method: 'POST', headers: { 'X-Omni-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); return { status: r.status, body: await r.json() }; }, [url, body, token]);
  const ids = (await post('/api/_seed-resume', {})).body.ids;
  await p.evaluate(() => document.querySelector('#navigation [data-route="queue"]').click());
  await p.waitForFunction(n => document.querySelectorAll('#job-list .job').length >= n, 4, { timeout: 8000 }).catch(() => {});
  const row = id => `#job-list [data-job-id="${id}"]`;
  const buttons = id => p.evaluate(sel => [...document.querySelectorAll(sel + ' .job-controls button')].map(n => n.dataset.action), row(id));
  const status = id => p.evaluate(sel => document.querySelector(sel)?.dataset.status, row(id));

  check('R1 running row: pause next to cancel', (await buttons(ids['running.mp4'])).join() === 'pause,cancel', { got: await buttons(ids['running.mp4']) });
  check('R2 failed row with its link kept: retry', (await buttons(ids['broken.mp4'])).join() === 'retry', { got: await buttons(ids['broken.mp4']) });
  check('R3 interrupted row with its link kept: resume and cancel', (await buttons(ids['stopped.mp4'])).join() === 'resume,cancel', { got: await buttons(ids['stopped.mp4']) });
  check('R4 old interrupted record without a link: no resume', (await buttons(ids['old.mp4'])).length === 0, { got: await buttons(ids['old.mp4']) });
  await shot('resume-01-rows');

  // Pointer: pause the running job, then resume it.
  await p.click(row(ids['running.mp4']) + ' [data-action="pause"]');
  await p.waitForFunction(sel => document.querySelector(sel)?.dataset.status === 'paused', row(ids['running.mp4']), { timeout: 5000 }).catch(() => {});
  check('R5 pause -> row shows Paused with resume + cancel', await status(ids['running.mp4']) === 'paused' && (await buttons(ids['running.mp4'])).join() === 'resume,cancel', { status: await status(ids['running.mp4']), got: await buttons(ids['running.mp4']) });
  const label = await p.evaluate(sel => document.querySelector(sel + ' .status-label').textContent, row(ids['running.mp4']));
  check('R6 status label says Paused', label === 'Paused', { label });
  await shot('resume-02-paused');
  await p.click(row(ids['running.mp4']) + ' [data-action="resume"]');
  await p.waitForFunction(sel => ['queued', 'downloading'].includes(document.querySelector(sel)?.dataset.status), row(ids['running.mp4']), { timeout: 5000 }).catch(() => {});
  check('R7 resume -> running again with pause button', (await buttons(ids['running.mp4'])).join() === 'pause,cancel', { status: await status(ids['running.mp4']) });

  // Controller: D-pad up (newest rows are on top, so the failed row is above) to the retry button, then Cross.
  await p.evaluate(sel => document.querySelector(sel + ' [data-action="pause"]').focus(), row(ids['running.mp4']));
  const reach = await p.evaluate(async target => {
    const seen = [];
    for (let i = 0; i < 12; i++) {
      const el = document.activeElement;
      seen.push(el?.dataset?.action || el?.id || el?.tagName);
      if (el?.dataset?.action === 'retry' && el.closest('[data-job-id]')?.dataset.jobId === target) return { ok: true, seen };
      if (window.omniMediaController('saved.previous') !== true) break;
    }
    return { ok: false, seen };
  }, ids['broken.mp4']);
  check('R8 D-pad reaches the retry button', reach.ok, reach);
  const pressed = await p.evaluate(() => window.omniMediaController('saved.choose'));
  await p.waitForFunction(sel => ['queued', 'downloading', 'completed'].includes(document.querySelector(sel)?.dataset.status), row(ids['broken.mp4']), { timeout: 5000 }).catch(() => {});
  check('R9 Cross on retry queues the failed job again', pressed === true && ['queued', 'downloading', 'completed'].includes(await status(ids['broken.mp4'])), { pressed, status: await status(ids['broken.mp4']) });
  const focusAfter = await p.evaluate(() => ({ action: document.activeElement?.dataset?.action || null, row: document.activeElement?.closest('[data-job-id]')?.dataset.jobId || null }));
  check('R10 focus stays on the row after its buttons change', focusAfter.row === ids['broken.mp4'], focusAfter);

  const actions = (await post('/api/_actions', {})).body.actions.map(a => a[0]).join();
  check('R11 worker got pause, resume, retry', actions === 'pause,resume,retry', { actions });
  const bad = await post('/api/jobs/pause', { id: ids['old.mp4'], extra: true });
  check('R12 extra fields are refused', bad.status === 400, bad);
  await shot('resume-03-after');
  check('R13 no page errors', errs.length === 0, { errs });
  fs.writeFileSync(path.join(outDir, 'resume-results.json'), JSON.stringify(log, null, 2));
  await b.close();
  console.log(failures ? 'RESUME FAIL: ' + failures : 'RESUME PASS: ' + log.length + ' checks');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
