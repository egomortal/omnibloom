// OMNI_DL_SAVE_V1 (Downloads 0.5.4): "Save to", file type, folder/file name, live byte counts, friendly quality names.
// node test-save.cjs <outDir>   (STUB_PROBE=1 stub_worker.py serving the GUI at 127.0.0.1:8765)
const pw = require('playwright'); const fs = require('fs'); const path = require('path');
const ENGINE = process.env.PW_BROWSER || 'chromium';
const outDir = process.argv[2]; fs.mkdirSync(outDir, { recursive: true });
const BASE = 'http://127.0.0.1:' + (process.env.STUB_PORT || 8765) + '/downloads';
const URL1 = 'https://example.com/clip.mp4';
const log = []; let failures = 0;
const check = (name, ok, data = {}) => { if (!ok) failures++; log.push({ check: name, pass: !!ok, ...data }); console.log((ok ? 'PASS ' : 'FAIL ') + name, ok ? '' : JSON.stringify(data)); };
(async () => {
  const b = await pw[ENGINE].launch(ENGINE === 'chromium' ? { args: ['--no-proxy-server'], ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}) } : {});
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  p.on('console', m => { if (m.type() === 'error' && !/404|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()); });
  const shot = name => p.screenshot({ path: path.join(outDir, name + '.png') });
  const token = async () => p.evaluate(() => document.querySelector('meta[name="omni-session-token"]')?.content);

  await p.goto(BASE + '#url=' + encodeURIComponent(URL1));
  await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
  await p.waitForFunction(() => document.querySelectorAll('#download-place option').length === 2, null, { timeout: 5000 }).catch(() => {});
  const form = () => p.evaluate(() => ({
    open: !!document.querySelector('#add-dialog[open]'),
    places: [...document.querySelectorAll('#download-place option')].map(o => o.value + '=' + o.textContent),
    types: [...document.querySelectorAll('#download-type option')].map(o => o.value),
    typeHidden: document.querySelector('#download-type-box').hidden,
  }));
  let f = await form();
  check('S1 add dialog open with the link', f.open, f);
  check('S2 "Save to" lists console storage and the USB drive with free space',
    f.places.length === 2 && /^internal=Console storage · 312(\.\d)? GB free$/.test(f.places[0]) && /^usb0=USB drive 1 · 900 MB free$/.test(f.places[1]), f);
  check('S3 video file types: MP4 first, MKV', f.types.join() === 'mp4,mkv' && !f.typeHidden, f);
  await shot('save-01-form-video');

  await p.selectOption('#download-kind', 'audio');
  f = await form();
  check('S4 audio file types: M4A first, WebM', f.types.join() === 'm4a,webm', f);
  await p.selectOption('#download-engine', 'jdownloader');
  f = await form();
  check('S5 JDownloader (original file): no file-type choice', f.typeHidden, f);
  await p.selectOption('#download-engine', 'ytdlp');
  await p.selectOption('#download-kind', 'video');
  f = await form();
  check('S5b back to yt-dlp video: MP4/MKV again', f.types.join() === 'mp4,mkv' && !f.typeHidden, f);

  await p.selectOption('#download-place', 'usb0');
  await p.selectOption('#download-type', 'mkv');
  await p.fill('#download-folder', 'Music videos');
  await p.fill('#download-name', 'My clip');
  await shot('save-02-form-filled');
  await p.uncheck('#download-demo').catch(() => {});
  await p.click('#download-form button[type=submit]');
  await p.waitForTimeout(600);
  const t = await token();
  const last = await p.evaluate(async t => (await fetch('/api/_last-job', { headers: { 'X-Omni-Token': t } })).json(), t);
  check('S6 the job carries place, type, folder and name (no paths)',
    last.save_place === 'usb0' && last.container === 'mkv' && last.save_folder === 'Music videos' && last.save_name === 'My clip', last);

  // Live byte line on the queue page while it downloads, then "Saved to" when done.
  await p.waitForFunction(() => /of 1\.4 GB · 4\.2 MB\/s · /.test(document.querySelector('.job .job-byte-label')?.textContent || ''), null, { timeout: 6000 }).catch(() => {});
  const line = await p.evaluate(() => [...document.querySelectorAll('.job .job-byte-label')].map(n => n.textContent));
  check('S7 queue shows "X of 1.4 GB · 4.2 MB/s · time left"', line.some(l => /^\d[\d.]* (MB|GB) of 1\.4 GB · 4\.2 MB\/s · (\d+ min left|under a minute left)$/.test(l)), { line });
  await shot('save-03-queue-progress');
  await p.waitForFunction(() => [...document.querySelectorAll('.job .job-byte-label')].some(n => /^Saved to .*clip\.mp4$/.test(n.textContent)), null, { timeout: 8000 }).catch(() => {});
  const done = await p.evaluate(() => [...document.querySelectorAll('.job .job-byte-label')].map(n => n.textContent));
  check('S8 a finished job says where it was saved', done.some(l => /^Saved to /.test(l)), { done });

  // A bad name is refused before anything is sent.
  await p.goto(BASE + '#url=' + encodeURIComponent('https://example.com/other.mp4'));
  await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
  await p.fill('#download-folder', '../system');
  await p.click('#download-form button[type=submit]');
  await p.waitForTimeout(400);
  const error = await p.evaluate(() => document.querySelector('#download-error')?.textContent || '');
  const after = await p.evaluate(async t => (await fetch('/api/_last-job', { headers: { 'X-Omni-Token': t } })).json(), await token());
  check('S9 a folder name with ".." is refused in the page', /Folder names may use/.test(error) && after.url === URL1, { error, after: after.url });

  check('S10 no page errors', errs.length === 0, { errs });
  fs.writeFileSync(path.join(outDir, 'save-results.json'), JSON.stringify(log, null, 2));
  await b.close();
  console.log(failures ? 'SAVE FORM FAIL: ' + failures : 'SAVE FORM PASS: ' + log.length + ' checks');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
