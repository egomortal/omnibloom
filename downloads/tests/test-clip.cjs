// OMNI_DL_CLIP_V1 (D01): "Clip: start / end" on the new-download form. Shown for yt-dlp videos and audio only,
// checked in the page, sent as plain m:ss text, cleared after adding, and reachable with the D-pad.
// node test-clip.cjs <outDir>   (stub_worker.py serving the GUI at 127.0.0.1:8765)
const pw = require('playwright'); const fs = require('fs'); const path = require('path');
const ENGINE = process.env.PW_BROWSER || 'chromium';
const outDir = process.argv[2] || path.join(__dirname, '..', 'out-tools', 'clip'); fs.mkdirSync(outDir, { recursive: true });
const BASE = 'http://127.0.0.1:' + (process.env.STUB_PORT || 8765) + '/downloads';
const URL1 = 'https://example.com/talk.mp4';
const log = []; let failures = 0;
const check = (name, ok, data = {}) => { if (!ok) failures++; log.push({ check: name, pass: !!ok, ...data }); console.log((ok ? 'PASS ' : 'FAIL ') + name, ok ? '' : JSON.stringify(data)); };
(async () => {
  const b = await pw[ENGINE].launch(ENGINE === 'chromium' ? { args: ['--no-proxy-server'], ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}) } : {});
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  p.on('console', m => { if (m.type() === 'error' && !/404|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()); });
  const shot = name => p.screenshot({ path: path.join(outDir, name + '.png') });
  const lastJob = async () => p.evaluate(async () => {
    const t = document.querySelector('meta[name="omni-session-token"]')?.content;
    return (await fetch('/api/_last-job', { headers: { 'X-Omni-Token': t } })).json();
  });
  const open = async url => {
    await p.goto('about:blank'); await p.goto(BASE + '#url=' + encodeURIComponent(url));
    await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
  };
  const shown = () => p.evaluate(() => ({ box: !document.querySelector('#download-clip-box').hidden, help: !document.querySelector('#download-clip-help').hidden }));
  const submit = async () => { await p.click('#download-form button[type=submit]'); await p.waitForTimeout(500); };

  await open(URL1);
  let s = await shown();
  check('C1 clip start/end fields show for a yt-dlp video', s.box && s.help, s);
  const attrs = await p.evaluate(() => ['start', 'end'].map(k => { const n = document.querySelector('#download-clip-' + k); return [n.type, n.maxLength, n.autocomplete, n.spellcheck, document.querySelector('label[for="download-clip-' + k + '"]').textContent]; }));
  check('C2 plain text boxes (PS5 keyboard has : and .), labelled "Clip: start" / "Clip: end"', attrs.every(a => a[0] === 'text' && a[1] === 8 && a[2] === 'off' && a[3] === false) && /^Clip: start/.test(attrs[0][4]) && /^Clip: end/.test(attrs[1][4]), { attrs });
  await p.selectOption('#download-kind', 'audio'); s = await shown();
  check('C3 audio keeps the clip fields', s.box, s);
  // "Original file" can be greyed out for a checked media link; set it the way the page's own change event would.
  await p.evaluate(() => { const k = document.querySelector('#download-kind'); k.value = 'file'; k.dispatchEvent(new Event('change', { bubbles: true })); }); s = await shown();
  check('C4 original file hides them', !s.box && !s.help, s);
  await p.selectOption('#download-kind', 'video'); await p.selectOption('#download-engine', 'jdownloader'); s = await shown();
  check('C5 JDownloader hides them', !s.box, s);
  await p.selectOption('#download-engine', 'ytdlp');

  await p.fill('#download-clip-start', '1.20');
  await p.fill('#download-clip-end', '3:45');
  await shot('clip-01-form');
  await p.uncheck('#download-demo').catch(() => {});
  await submit();
  let last = await lastJob();
  check('C6 the job carries clip_start 1:20 (from "1.20") and clip_end 3:45', last.url === URL1 && last.clip_start === '1:20' && last.clip_end === '3:45', last);

  await open('https://example.com/second.mp4');
  const cleared = await p.evaluate(() => [document.querySelector('#download-clip-start').value, document.querySelector('#download-clip-end').value]);
  check('C7 the clip times are cleared for the next link', cleared.join('') === '', { cleared });

  await p.fill('#download-clip-end', '3:45');
  await submit();
  last = await lastJob();
  check('C8 only an end: clip from the start (no clip_start sent)', last.url === 'https://example.com/second.mp4' && last.clip_end === '3:45' && !('clip_start' in last), last);

  for (const [start, end, why, name] of [['3:45', '1:20', /start before it ends/, 'C9 start after end'],
    ['0:00', '7:00:00', /within the first 6 hours/, 'C10 longer than 6 hours'],
    ['1:20', '', /end time/, 'C11 a start without an end'],
    ['1:2', '3:45', /look like 1:20/, 'C12 a malformed time']]) {
    await open('https://example.com/bad.mp4');
    await p.fill('#download-clip-start', start); await p.fill('#download-clip-end', end);
    await submit();
    const error = await p.evaluate(() => document.querySelector('#download-error')?.textContent || '');
    last = await lastJob();
    check(name + ' is refused in the page and nothing is sent', why.test(error) && last.url !== 'https://example.com/bad.mp4', { error, sent: last.url });
  }
  await shot('clip-02-refused');

  // D-pad (the engine's own controller hook): the clip row sits under the folder / file name row.
  await p.goto('about:blank'); await p.goto(BASE);
  await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
  await p.click('#add-link');
  await p.waitForFunction(() => !!document.querySelector('#add-dialog[open]'));
  await p.focus('#download-folder');
  const pad = async action => { const used = await p.evaluate(a => window.omniMediaController?.(a) === true, action); await p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))); return used; };
  const focus = () => p.evaluate(() => document.activeElement?.id || document.activeElement?.className || document.activeElement?.tagName);
  await pad('saved.next');   // first press shows where focus is
  const path0 = [await focus()];
  await pad('saved.next'); path0.push(await focus());
  await pad('saved.right'); path0.push(await focus());
  await pad('saved.left'); path0.push(await focus());
  await pad('saved.previous'); path0.push(await focus());
  check('C13 D-pad: folder -> down clip start -> right clip end -> left clip start -> up folder', path0.join() === 'download-folder,download-clip-start,download-clip-end,download-clip-start,download-folder', { path0 });
  await p.focus('#download-name'); await pad('saved.next');
  check('C13b D-pad: file name -> down clip end (same column)', (await focus()) === 'download-clip-end', {});
  await shot('clip-03-dpad');

  check('C14 no page errors', errs.length === 0, { errs });
  fs.writeFileSync(path.join(outDir, 'clip-results.json'), JSON.stringify(log, null, 2));
  await b.close();
  console.log(failures ? 'CLIP FORM FAIL: ' + failures : 'CLIP FORM PASS: ' + log.length + ' checks');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
