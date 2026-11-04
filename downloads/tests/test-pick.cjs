// downloader-3 (OMNI_DOWNLOADS_PICK_V3) + downloader-4 (OMNI_DOWNLOADS_NAV_V4): grabbed candidate rows on the form view.
// Drives the page like the engine (omniMediaController actions; not-true = engine fallback).
// node test-pick.cjs <outDir>   (stub_worker.py serving the GUI at 127.0.0.1:8765)
const pw = require('playwright'); const fs = require('fs'); const path = require('path');
const ENGINE = process.env.PW_BROWSER || 'chromium';
const outDir = process.argv[2]; fs.mkdirSync(outDir, { recursive: true });
const BASE = 'http://127.0.0.1:' + (process.env.STUB_PORT || 8765) + '/downloads';
const PAGE = 'https://site.example/watch/1';
const TOP = 'https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8';
const VAR = 'https://test-streams.mux.dev/x36xhzz/url_0/193039199_mp4_h264_aac_hd_7.m3u8';
const wire = JSON.stringify({ v: 1, g: '7', p: PAGE, t: false, rows: [
  { u: TOP, k: 'manifest', s: 95, e: ['resource-timing'] },
  { u: VAR, k: 'manifest', s: 90, e: ['resource-timing'] },
  { u: PAGE, k: 'source-page', s: 25, e: ['iframe'] }] });
const enc = encodeURIComponent;
const log = []; let failures = 0;
const check = (name, ok, data = {}) => { if (!ok) failures++; log.push({ check: name, pass: !!ok, ...data }); console.log((ok ? 'PASS ' : 'FAIL ') + name, ok ? '' : JSON.stringify(data)); };
(async () => {
  const b = await pw[ENGINE].launch(ENGINE === 'chromium' ? { args: ['--no-proxy-server'] } : {});
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e))); p.on('console', m => { if (m.type() === 'error' && !/404|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()); });
  const pad = async (button) => {
    const action = { up: 'saved.previous', down: 'saved.next', left: 'saved.left', right: 'saved.right', cross: 'saved.choose', circle: 'saved.dismiss' }[button];
    const used = await p.evaluate(a => window.omniMediaController?.(a) === true, action);
    if (!used && button === 'cross') { await p.mouse.down(); await p.mouse.up(); }
    if (!used && button === 'circle') await p.evaluate(() => { const d = [...document.querySelectorAll('dialog[open]')].pop(); if (d) d.close(); });
    if (!used && (button === 'up' || button === 'down')) await p.mouse.wheel(0, button === 'down' ? 140 : -140);
    await p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    return used;
  };
  const snap = () => p.evaluate(() => {
    const a = document.activeElement, rows = sel => [...document.querySelectorAll(sel + ' .candidate-pick')];
    return { open: [...document.querySelectorAll('dialog[open]')].map(d => d.id),
      focus: a ? (a.dataset.pickIndex !== undefined ? 'pick:' + a.closest('.form-candidates').id + ':' + a.dataset.pickIndex : a.id ? '#' + a.id : a.tagName) : null,
      formVisible: !document.querySelector('#form-candidates').hidden, formRows: rows('#form-candidates').length,
      formPressed: rows('#form-candidates').map(r => r.getAttribute('aria-pressed')),
      launchVisible: !!document.querySelector('#launch-candidates') && !document.querySelector('#launch-candidates').hidden,
      launchRows: rows('#launch-candidates').length, launchPressed: rows('#launch-candidates').map(r => r.getAttribute('aria-pressed')),
      downloadUrl: document.querySelector('#download-url').value, quickUrl: document.querySelector('#quick-url')?.value ?? null,
      hash: location.hash, toast: document.querySelector('#toast')?.textContent || '' };
  });
  const open = async (hash) => {
    await p.goto('about:blank'); await p.goto(BASE + hash);
    await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
    await p.waitForTimeout(150); await p.mouse.move(960, 1060);
  };
  const shot = async name => p.screenshot({ path: path.join(outDir, name + '.png') });

  // A. R2 / Send current link (engine grabber-net-1b): top candidate prefilled, rows + page candidate attached.
  await open('#url=' + enc(TOP) + '&candidate=' + enc(PAGE) + '&detected=0&candidates=' + enc(wire));
  let s = await snap();
  check('A1 share: add dialog opens (unchanged)', s.open.includes('add-dialog'), s);
  check('A2 share: hash cleared before anything else', s.hash === '', s);
  check('A3 share: URL field holds the top candidate', s.downloadUrl === TOP, s);
  check('A4 share: pick list shown in the dialog with 3 rows', s.formVisible && s.formRows === 3, s);
  check('A5 share: top row preselected', s.formPressed.join() === 'true,false,false', s);
  check('A6 share: focus starts on the preselected row', s.focus === 'pick:form-candidates:0', s);
  check('A7 share: Launch page shows the same rows behind', s.launchVisible && s.launchRows === 3, s);
  await shot('d3-01-share-dialog-top-preselected');
  await pad('down'); s = await snap();
  check('A8 D-pad down moves to row 2 (first press in pad mode)', s.focus === 'pick:form-candidates:1' || s.focus === 'pick:form-candidates:0', s);
  if (s.focus === 'pick:form-candidates:0') { await pad('down'); s = await snap(); }
  check('A9 D-pad down reaches row 2', s.focus === 'pick:form-candidates:1', s);
  await pad('cross'); s = await snap();
  check('A10 Cross picks row 2 into the URL field', s.downloadUrl === VAR && s.formPressed.join() === 'false,true,false', s);
  check('A11 dialog stays open after a pick', s.open.includes('add-dialog'), s);
  await shot('d3-02-share-row2-picked');
  await pad('down'); await pad('cross'); s = await snap();
  check('A12 page row picks the page URL', s.downloadUrl === PAGE && s.formPressed.join() === 'false,false,true', s);
  for (let i = 0; i < 5 && s.focus !== '#download-url'; i++) { await pad('up'); s = await snap(); }
  check('A13 up from the rows reaches the URL field (via the existing duplicate-check button)', s.focus === '#download-url', s);
  // draft protection: a typed draft is never overwritten by a pick
  await p.fill('#download-url', 'https://my.own/draft'); await p.evaluate(() => document.querySelector('#form-candidates .candidate-pick').focus());
  await p.keyboard.press('Shift'); await pad('cross'); s = await snap();
  check('A14 typed draft is kept (toast)', s.downloadUrl === 'https://my.own/draft' && /draft is kept/i.test(s.toast), s);
  // submit path still works with a picked row
  await p.fill('#download-url', ''); await p.click('#form-candidates .candidate-pick >> nth=0'); s = await snap();
  check('A15 pointer click on a row picks it', s.downloadUrl === TOP && s.formPressed[0] === 'true', s);
  await pad('circle'); s = await snap();
  check('A16 Circle closes the dialog', !s.open.includes('add-dialog'), s);

  // B. L1+R1 / menu Media downloads: rows + page candidate, no url -> Launch page, no dialog.
  await open('#candidate=' + enc(PAGE) + '&detected=0&candidates=' + enc(wire));
  s = await snap();
  check('B1 section: no dialog opens (unchanged)', s.open.length === 0, s);
  check('B2 section: Launch pick list shown with 3 rows', s.launchVisible && s.launchRows === 3, s);
  check('B3 section: top row preselected into the quick link', s.quickUrl === TOP && s.launchPressed.join() === 'true,false,false', s);
  await p.keyboard.press('Shift'); // pad mode, nothing focused (the engine's pointer may sit anywhere)
  await pad('down'); s = await snap();
  check('B4 first D-pad press lands on the preselected row', s.focus === 'pick:launch-candidates:0', s);
  await shot('d3-03-section-launch-rows');
  await pad('down'); await pad('cross'); s = await snap();
  check('B5 Cross picks row 2 into the quick link', s.quickUrl === VAR && s.launchPressed.join() === 'false,true,false', s);
  await p.click('#add-link'); await p.waitForTimeout(60); s = await snap();
  check('B6 Add a link dialog shows the rows too, focus on the marked row', s.open.includes('add-dialog') && s.formVisible && s.focus === 'pick:form-candidates:0', s);
  await pad('circle');

  // C. No candidates: everything as before.
  await open('#url=' + enc('https://example.com/a.mp4'));
  s = await snap();
  check('C1 plain share: dialog opens, list hidden, focus on URL field', s.open.includes('add-dialog') && !s.formVisible && s.focus === '#download-url' && s.downloadUrl === 'https://example.com/a.mp4', s);
  check('C2 plain share: Launch list hidden', !s.launchVisible, s);
  await pad('circle'); await open(''); s = await snap();
  check('C3 plain open: no lists', !s.formVisible && !s.launchVisible && s.open.length === 0, s);

  // D. Saved view (L2) unchanged: panel rows still rendered there.
  await open('#view=saved&candidate=' + enc(PAGE) + '&detected=1&candidates=' + enc(wire));
  const saved = await p.evaluate(() => ({ panel: !document.querySelector('#native-candidate').hidden, rows: document.querySelectorAll('#candidate-rows .candidate-row').length, hash: location.hash }));
  check('D1 saved view: native candidate panel with 3 rows (unchanged)', saved.panel && saved.rows === 3 && saved.hash === '#view=saved', saved);
  await shot('d3-04-saved-view-unchanged');

  // E. Invalid wire: rejected as before, no lists.
  await open('#url=' + enc(TOP) + '&candidate=' + enc(PAGE) + '&candidates=' + enc('{"v":2}'));
  s = await snap();
  check('E1 invalid wire: no pick rows, dialog still opens with the url', s.open.includes('add-dialog') && !s.formVisible && s.downloadUrl === TOP, s);

  // F. downloader-4 (OMNI_DOWNLOADS_NAV_V4): many long grabbed links, a pointer that drifts between presses.
  const LONG = Array.from({ length: 6 }, (_, i) => `https://cdn${i}.very-long-streaming-host.example.net/hls/variant_${i}/index-${'x'.repeat(60)}.m3u8?token=${'t'.repeat(80)}`);
  const wire6 = JSON.stringify({ v: 1, g: '8', p: PAGE, t: false, rows: LONG.map((u, i) => ({ u, k: 'manifest', s: [95, 90, 75, 60, 55, 45][i], e: ['resource-timing'] })) });
  const STICK = `(()=>{const d=[...document.querySelectorAll('dialog[open]')].pop();if(!d)return false;const s=[d,...d.querySelectorAll('*')].find(e=>e.scrollHeight>e.clientHeight+1&&/(auto|scroll)/.test(getComputedStyle(e).overflowY));if(s)s.scrollBy(0,120);return true})()`; // the shell's right-stick script, stick down
  const addVisible = () => p.evaluate(() => { const d = document.querySelector('#add-dialog'), b = [...d.querySelectorAll('button')].find(x => /Add to queue/.test(x.textContent)); const r = b.getBoundingClientRect(), q = d.getBoundingClientRect();
    return { focused: document.activeElement === b, visible: r.top >= Math.max(0, q.top) - 1 && r.bottom <= Math.min(innerHeight, q.bottom) + 1 }; });
  const walk = async (drift, until, max = 14) => { const seen = []; let px = 300, stuck = 0;
    for (let i = 0; i < max; i++) {
      if (drift) { px += 7; await p.mouse.move(px, 560); await p.mouse.move(px + 4, 563); } // a drifting stick: a few px per step, never a real move
      const before = (await snap()).focus; await pad('down'); const after = await snap(); seen.push(after.focus);
      if (after.focus === before && i > 0) stuck++; // the first press after pointer use only shows focus (by design)
      if (await until(after)) return { reached: true, steps: i + 1, stuck, seen };
    } return { reached: false, stuck, seen }; };
  for (const [vw, vh] of [[1920, 1000], [1920, 720]]) {
    await p.setViewportSize({ width: vw, height: vh });
    for (const drift of [false, true]) {
      await open('#url=' + enc(LONG[0]) + '&candidate=' + enc(PAGE) + '&detected=0&candidates=' + enc(wire6));
      await p.keyboard.press('Shift');
      const r = await walk(drift, async () => (await addVisible()).focused);
      const v = await addVisible();
      check(`F1 ${vw}x${vh}${drift ? ' drift' : ''}: D-pad down reaches Add to queue, visible, every press after the first moves`, r.reached && v.visible && r.stuck === 0, { ...r, ...v });
      await pad('circle');
    }
    await open('#url=' + enc(LONG[0]) + '&candidate=' + enc(PAGE) + '&detected=0&candidates=' + enc(wire6));
    for (let i = 0; i < 20; i++) await p.evaluate(STICK);
    check(`F2 ${vw}x${vh}: right stick scrolls the dialog to Add to queue`, (await addVisible()).visible, await addVisible());
    await pad('circle');
    for (const drift of [false, true]) {
      await open('#candidate=' + enc(PAGE) + '&detected=0&candidates=' + enc(wire6));
      await p.keyboard.press('Shift');
      const r = await walk(drift, async s => s.focus === '#engine-jdownloader' || s.focus === '#engine-ytdlp');
      check(`F3 ${vw}x${vh}${drift ? ' drift' : ''}: Launch rows -> engine choice, every press after the first moves`, r.reached && r.stuck === 0, r);
    }
  }
  await p.setViewportSize({ width: 1920, height: 1080 });

  check('no page errors', errs.length === 0, { errs });
  fs.writeFileSync(path.join(outDir, 'pick-log.json'), JSON.stringify({ engine: ENGINE, version: b.version(), failures, log }, null, 1));
  console.log(`${log.length - failures}/${log.length} checks pass (${ENGINE} ${b.version()})`);
  await b.close(); process.exit(failures ? 1 : 0);
})();
