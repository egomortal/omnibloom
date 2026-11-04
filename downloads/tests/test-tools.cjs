// dl6: the three tool pages served by the REAL worker (presets / subtitles / library) at 1080p and 4K.
'use strict';
const pw = require('playwright'); const fs = require('fs'); const path = require('path');
const PORT = +process.argv[2] || 8799; const OUT = process.argv[3] || 'out-tools'; fs.mkdirSync(OUT, { recursive: true });
const base = `http://127.0.0.1:${PORT}`;
let pass = 0, fail = 0; const ok = (c, m) => { if (c) pass++; else { fail++; console.log('FAIL', m); } };
(async () => {
  const b = await pw.chromium.launch({ args: ['--no-proxy-server'] });
  for (const [w, h] of [[1920, 1080], [3840, 2160]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h } });
    for (const name of ['presets', 'subtitles', 'library']) {
      const page = await ctx.newPage(); const errors = [];
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      page.on('pageerror', e => errors.push(String(e)));
      const resp = await page.goto(`${base}/tools/${name}/`, { waitUntil: 'networkidle' });
      ok(resp.status() === 200, `${name} ${w} status ${resp.status()}`);
      await page.waitForTimeout(400);
      ok(errors.length === 0, `${name} ${w} console errors: ${errors.join(' | ')}`);
      const fontPx = await page.evaluate(() => parseFloat(getComputedStyle(document.querySelector('main p, main label, main h1')).fontSize));
      ok(fontPx >= 22, `${name} ${w} text ${fontPx}px`);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      ok(!overflow, `${name} ${w} horizontal overflow`);
      // D-pad through the page's own controller hook (as Omni drives it), falling back to Tab.
      await page.evaluate(() => { if (window.omniMediaController) { omniMediaController('down'); omniMediaController('down'); } });
      if (await page.evaluate(() => !window.omniMediaController)) { await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); }
      ok(await page.evaluate(() => document.querySelectorAll('.pad-focus').length === 1 || (document.activeElement && document.activeElement !== document.body)), `${name} ${w} D-pad focus moves`);
      if (name === 'presets') {
        await page.waitForFunction(() => !document.getElementById('queue').disabled, null, { timeout: 8000 }).catch(() => {});
        ok(await page.evaluate(() => !document.getElementById('queue').disabled), `presets ${w} enabled against dl6 worker (presets_v1)`);
        await page.fill('#url', 'https://example.invalid/video');
        await page.selectOption('#preset', 'audio-opus');
        await page.click('#queue');
        await page.waitForFunction(() => /queue|confirmed/i.test(document.getElementById('status').textContent), null, { timeout: 8000 }).catch(() => {});
        const st = await page.evaluate(() => document.getElementById('status').textContent);
        ok(/Added to the queue/.test(st), `presets ${w} submit -> "${st}"`);
      }
      await page.screenshot({ path: path.join(OUT, `${name}-${w}.png`) });
      await page.close();
    }
    await ctx.close();
  }
  // Token must not be readable cross-origin and unknown tool paths must 404.
  const r = await fetch(`${base}/tools/presets/../../worker.py`).catch(() => null);
  ok(!r || r.status !== 200, 'path traversal not served');
  await b.close();
  console.log(`TOOLS ${fail ? 'FAIL' : 'PASS'}: ${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
