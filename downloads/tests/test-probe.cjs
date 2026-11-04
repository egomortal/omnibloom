// downloader-5 (OMNI_DOWNLOADS_PROBE_V5): checked-link badges, best-first order and the quality picker.
// node test-probe.cjs <outDir>   (STUB_PROBE=1 stub_worker.py serving the GUI at 127.0.0.1:8765)
const pw = require('playwright'); const fs = require('fs'); const path = require('path');
const ENGINE = process.env.PW_BROWSER || 'chromium';
const outDir = process.argv[2]; fs.mkdirSync(outDir, { recursive: true });
const BASE = 'http://127.0.0.1:' + (process.env.STUB_PORT || 8765) + '/downloads';
const PAGE = 'https://site.example/watch/1';
const TOP = 'https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8';
const VAR = 'https://test-streams.mux.dev/x36xhzz/url_0/193039199_mp4_h264_aac_hd_7.m3u8';
const DRM = 'https://cdn.example/drm/master.m3u8';
const GONE = 'https://cdn.example/gone/clip.mp4';
const wire = JSON.stringify({ v: 1, g: '7', p: PAGE, t: false, rows: [
  { u: VAR, k: 'manifest', s: 95, e: ['resource-timing'] },
  { u: DRM, k: 'manifest', s: 90, e: ['resource-timing'] },
  { u: TOP, k: 'manifest', s: 90, e: ['resource-timing'] },
  { u: GONE, k: 'media-url', s: 75, e: ['media-current'] },
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
    await p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    return used;
  };
  const rows = sel => p.evaluate(s => [...document.querySelectorAll(s + ' .candidate-pick')].map(r => ({ url: r.dataset.pickUrl, probe: r.dataset.probe, head: r.querySelector('strong').textContent, small: r.querySelector('small').textContent, pressed: r.getAttribute('aria-pressed') })), sel);
  const snap = () => p.evaluate(() => {
    const a = document.activeElement;
    return { open: [...document.querySelectorAll('dialog[open]')].map(d => d.id),
      focus: a ? (a.dataset.pickUrl ? 'pick:' + a.dataset.pickUrl : a.dataset.qualityKey ? 'q:' + a.dataset.qualityGroup + ':' + a.dataset.qualityKey : a.id ? '#' + a.id : a.tagName) : null,
      title: document.querySelector('#form-candidates .form-candidates-title span')?.textContent,
      note: document.querySelector('#form-candidates .quality-note:not([hidden]) span')?.textContent || '',
      options: [...document.querySelectorAll('#quality-options .quality-option')].map(o => o.dataset.qualityKey),
      langs: [...document.querySelectorAll('#quality-langs .quality-option')].map(o => o.dataset.qualityKey),
      summary: document.querySelector('#quality-summary')?.textContent || '',
      downloadUrl: document.querySelector('#download-url').value, toast: document.querySelector('#toast')?.textContent || '',
      formText: document.querySelector('#form-candidates')?.textContent || '' };
  });
  const open = async (hash) => {
    await p.goto('about:blank'); await p.goto(BASE + hash);
    await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
    await p.waitForTimeout(150); await p.mouse.move(960, 1060);
  };
  const shot = async name => p.screenshot({ path: path.join(outDir, name + '.png') });
  const settled = sel => p.waitForFunction(s => { const t = document.querySelector(s + ' .form-candidates-title span'); return t && t.textContent === 'checked'; }, sel, { timeout: 20000 });

  // A. R2 share: every row checked, best first, failures last, no "unverified" wording.
  await open('#url=' + enc(TOP) + '&candidate=' + enc(PAGE) + '&detected=0&candidates=' + enc(wire));
  let r = await rows('#form-candidates');
  check('A1 rows start as Checking…', r.some(x => /Checking/.test(x.head)), r);
  await settled('#form-candidates');
  await p.waitForTimeout(300);
  r = await rows('#form-candidates'); let s = await snap();
  check('A2 every row checked (title says checked)', s.title === 'checked' && r.every(x => x.probe && x.probe !== 'checking'), { s, r });
  check('A3 best first: 1080p60 HLS, then the page (1080p via site check)', r[0].url === TOP && r[1].url === PAGE, r.map(x => x.url));
  check('A4 failures sorted last', ['protected', 'dead'].includes(r[3].probe) && ['protected', 'dead'].includes(r[4].probe), r.map(x => x.probe));
  check('A5 HLS badge shows type, quality, codecs, duration and size', /^HLS · 1080p60 · H\.264\/AAC · 10:35 · ~\d/.test(r[0].head), r[0]);
  check('A6 HLS detail lists qualities, audio and subtitles', /3 qualities/.test(r[0].small) && /English, Español/.test(r[0].small) && /subtitles: en/.test(r[0].small), r[0]);
  check('A7 page row verified by the site check after a slow first answer', /^Page link · Generic · 1080p · H\.264\/AAC/.test(r[1].head) && /Big Buck Bunny/.test(r[1].small), r[1]);
  check('A8 DRM row says protected, dead row says dead', r.some(x => x.probe === 'protected' && /DRM/.test(x.head)) && r.some(x => x.probe === 'dead' && /Dead link/.test(x.head)), r);
  check('A9 no unverified / evidence-hint wording left', !/unverified|evidence hint/i.test(s.formText), s.formText.slice(0, 300));
  check('A10 field still holds the shared link and its row is marked', s.downloadUrl === TOP && r[0].pressed === 'true', { s, r });
  await shot('d5-01-checked-rows');

  // B. Quality picker by controller: Cross on the HLS row opens it; pick 720p + Spanish; Done.
  await p.evaluate(u => document.querySelector(`#form-candidates .candidate-pick[data-pick-url="${u}"]`).focus(), TOP);
  await p.keyboard.press('Shift');
  await pad('cross'); s = await snap();
  check('B1 Cross on a multi-quality row opens the quality picker', s.open.includes('quality-dialog') && s.open.includes('add-dialog'), s);
  check('B2 options: Best, 1080p60, 720p, 480p, Audio only', s.options.join() === 'best,h1080f60,h720f30,h480f0,audio', s.options);
  check('B3 audio languages offered', s.langs.join() === 'en,es', s.langs);
  check('B4 focus starts on the chosen option (Best)', s.focus === 'q:video:best', s);
  check('B5 summary repeats the checked badge', /^HLS · 1080p60/.test(s.summary), s.summary);
  await shot('d5-02-quality-picker');
  await pad('down'); s = await snap();
  if (s.focus === 'q:video:best') { await pad('down'); s = await snap(); }
  await pad('down'); s = await snap();
  check('B6 D-pad walks the qualities', s.focus === 'q:video:h720f30', s);
  await pad('cross'); s = await snap();
  check('B7 Cross marks 720p; dialog stays for the language', s.open.includes('quality-dialog'), s);
  for (let i = 0; i < 6 && s.focus !== 'q:lang:es'; i++) { await pad('down'); s = await snap(); }
  check('B8 D-pad reaches the Spanish audio', s.focus === 'q:lang:es', s);
  await pad('cross');
  for (let i = 0; i < 3 && s.focus !== '#quality-done'; i++) { await pad('down'); s = await snap(); }
  check('B9 D-pad reaches Use this quality', s.focus === '#quality-done', s);
  await pad('cross'); s = await snap();
  check('B10 Done closes the picker, add dialog stays', !s.open.includes('quality-dialog') && s.open.includes('add-dialog'), s);
  check('B11 focus returns to the row', s.focus === 'pick:' + TOP, s);
  check('B12 quality note shows the choice', /^Quality: 720p .*audio es/.test(s.note), s.note);
  await shot('d5-03-quality-chosen');

  // C. Circle in the picker keeps the earlier choice.
  await p.click('#form-candidates .quality-change'); await p.waitForTimeout(120); s = await snap();
  check('C1 Change quality reopens the picker on 720p', s.open.includes('quality-dialog') && s.focus === 'q:video:h720f30', s);
  await pad('circle'); s = await snap();
  check('C2 Circle closes the picker only', !s.open.includes('quality-dialog') && s.open.includes('add-dialog') && /^Quality: 720p/.test(s.note), s);

  // D. Submit sends the checked choice and the page origin (never a raw format string).
  await p.check('#download-demo');
  await p.click('#download-form button[type=submit]');
  await p.waitForFunction(() => !document.querySelector('#add-dialog').open, null, { timeout: 5000 });
  const job = await p.evaluate(async () => { const t = document.querySelector('meta[name="omni-session-token"]').content; return (await fetch('/api/_last-job', { headers: { 'X-Omni-Token': t } })).json(); });
  check('D1 job carries quality {height:720,fps:30,audio_lang:es}', JSON.stringify(job.quality) === JSON.stringify({ height: 720, fps: 30, audio_lang: 'es' }), job);
  check('D2 job carries the page origin as referer', job.referer === 'https://site.example/', job);
  check('D3 no raw format text sent', !('format' in job), job);

  // E. A single-quality pick does not open the picker; a protected pick warns.
  await open('#url=' + enc(VAR) + '&candidate=' + enc(PAGE) + '&detected=0&candidates=' + enc(wire));
  await settled('#form-candidates');
  await p.click(`#form-candidates .candidate-pick[data-pick-url="${GONE}"]`); s = await snap();
  check('E1 dead pick: no picker, warning toast', !s.open.includes('quality-dialog') && /Dead link/.test(s.toast), s);
  await p.click(`#form-candidates .candidate-pick[data-pick-url="${VAR}"]`); s = await snap();
  check('E2 single-quality pick: no picker, badge toast', !s.open.includes('quality-dialog') && /Link chosen: HLS/.test(s.toast), s);

  // F. Launch page (L1+R1) and Saved view show the same checked rows.
  await open('#candidate=' + enc(PAGE) + '&detected=0&candidates=' + enc(wire));
  await settled('#launch-candidates');
  r = await rows('#launch-candidates');
  check('F1 Launch rows checked and sorted', r[0].url === TOP && /^HLS · 1080p60/.test(r[0].head), r.map(x => x.head));
  await shot('d5-04-launch');
  await open('#view=saved&candidate=' + enc(PAGE) + '&detected=0&candidates=' + enc(wire));
  await p.waitForFunction(() => [...document.querySelectorAll('#candidate-rows .candidate-row strong')].some(n => /^HLS · 1080p60/.test(n.textContent)), null, { timeout: 15000 });
  const saved = await p.evaluate(() => [...document.querySelectorAll('#candidate-rows .candidate-row')].map(c => c.textContent));
  check('F2 Saved view shows checked badges, no Unverified wording', saved.some(t => /HLS · 1080p60/.test(t)) && !saved.some(t => /Unverified|evidence hint/.test(t)), saved);
  await shot('d5-05-saved');

  check('no page errors', errs.length === 0, { errs });
  fs.writeFileSync(path.join(outDir, 'test-probe-' + ENGINE + '.json'), JSON.stringify({ browser: ENGINE + ' ' + b.version(), log }, null, 1));
  console.log(`${log.length - failures}/${log.length} checks pass (${ENGINE} ${b.version()})`);
  await b.close(); process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
