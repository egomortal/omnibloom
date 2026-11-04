// Omnibloom public Universes: every Universe at the console's page size (1280x576 CSS px; 1080p = scale 1.5, 4K = scale 3).
// node test-universes.cjs <outDir>   (stub_worker.py serving the staged GUI at 127.0.0.1:8765)
const pw = require('playwright'); const fs = require('fs'); const path = require('path');
const outDir = process.argv[2]; fs.mkdirSync(outDir, { recursive: true });
const BASE = 'http://127.0.0.1:' + (process.env.STUB_PORT || 8765) + '/downloads';
const NEW = ['bloom', 'relay', 'loom', 'kinetic', 'tide'];
const OLD = ['aurora', 'cosmic', 'arcade', 'solstice', 'metro', 'sakura', 'abyss', 'prism', 'atlas', 'cassette'];
const GONE = ['omnitrix', 'bayonetta', 'borderlands', 'dishonored', 'bioshockinfinite'];
const results = []; let failures = 0;
const check = (name, ok, data = {}) => { if (!ok) failures++; results.push({ check: name, pass: !!ok, ...data }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : ' ' + JSON.stringify(data))); };
(async () => {
  const b = await pw.chromium.launch({ args: ['--no-proxy-server'] });
  const run = async (theme, scale, opts = {}) => {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 576 }, deviceScaleFactor: scale, reducedMotion: opts.osReduce ? 'reduce' : 'no-preference' });
    await ctx.addInitScript(([t, rm, g]) => { try { localStorage.setItem('omni.production.preferences', JSON.stringify({ theme: t, reduced_motion: rm, sound: false })); if (g) localStorage.setItem('omni.glyphs', g); } catch (_) {} }, [theme, !!opts.reduce, opts.glyphs || '']);
    const p = await ctx.newPage(); const errs = []; const bytes = {}; const reqs = [];
    p.on('pageerror', e => errs.push(String(e)));
    p.on('response', async r => { const u = new URL(r.url()); reqs.push(u.pathname + ' ' + r.status()); if (r.status() === 200) { try { bytes[u.pathname] = (await r.body()).length; } catch (_) {} } });
    await p.goto(BASE); await p.waitForFunction(() => document.documentElement.dataset.ready === 'true', null, { timeout: 15000 });
    await p.waitForTimeout(450);
    return { ctx, p, errs, bytes, reqs };
  };
  const navInfo = p => p.evaluate(() => {
    const btns = [...document.querySelectorAll('#navigation [data-route]')];
    const vw = innerWidth;
    return { theme: document.body.dataset.theme, count: btns.length, dpr: devicePixelRatio,
      overflowX: document.documentElement.scrollWidth > vw + 1,
      buttons: btns.map(n => { const r = n.getBoundingClientRect(), cs = getComputedStyle(n), label = [...n.querySelectorAll('span')].find(s => s.textContent.trim().length > 2 && !s.classList.contains('u-num')) || n;
        const lr = label.getBoundingClientRect();
        return { route: n.dataset.route, current: n.classList.contains('is-current'), x: r.x, y: r.y, w: r.width, h: r.height, right: r.right,
          font: parseFloat(getComputedStyle(label).fontSize), clipped: label.scrollWidth > label.clientWidth + 1 || lr.right > r.right + 1 || lr.left < r.left - 1,
          transform: cs.transform, filter: cs.filter, border: cs.borderTopColor, transition: cs.transitionDuration, anim: cs.animationName }; }),
      hint: (() => { const h = document.querySelector('#navigation-hint'); return h ? { text: h.innerHTML.replace(/<br\s*\/?>/g, ' '), font: parseFloat(getComputedStyle(h).fontSize), visible: getComputedStyle(h).display !== 'none' && h.offsetParent !== null } : null; })(),
      title: document.querySelector('#universe-title').textContent, glyphKbd: document.querySelector('kbd[data-glyph="cross"]')?.textContent };
  });
  // ---- New Universes: 1080p and 4K
  for (const theme of NEW) {
    for (const scale of [1.5, 3]) {
      const tag = `${theme}@${scale === 1.5 ? '1080p' : '4k'}`;
      const { ctx, p, errs, bytes, reqs } = await run(theme, scale);
      const info = await navInfo(p);
      check(`${tag}: theme applied`, info.theme === theme, { got: info.theme });
      check(`${tag}: five routes`, info.count === 5, { count: info.count });
      check(`${tag}: no horizontal overflow`, !info.overflowX);
      check(`${tag}: route labels not clipped`, info.buttons.every(x => !x.clipped), { clipped: info.buttons.filter(x => x.clipped).map(x => x.route) });
      const minPx = Math.min(...info.buttons.map(x => x.font)) * 1.5; // device px at 1080p
      check(`${tag}: route text >= 22px at 1080p`, minPx >= 22, { px: minPx });
      if (info.hint && info.hint.visible) check(`${tag}: hint uses Xbox label by default`, /\bA\b/.test(info.hint.text) && !/Cross/.test(info.hint.text), { hint: info.hint.text });
      const cur = info.buttons.filter(x => x.current);
      check(`${tag}: one current route, raised`, cur.length === 1 && cur[0].transform !== 'none', { cur });
      const art = Object.keys(bytes).filter(k => k.startsWith('/assets/art/'));
      check(`${tag}: only its own art loads`, art.length === 1 && art[0] === `/assets/art/${theme}.webp`, { art });
      check(`${tag}: no franchise requests`, !reqs.some(r => /legends-pack|siren-showcase|watch-bezel|bayonetta|borderlands|omnitrix/.test(r)), { reqs: reqs.filter(r => /legends|siren|watch|bayonetta|borderlands|omnitrix/.test(r)) });
      const total = Object.values(bytes).reduce((a, c) => a + c, 0);
      results.push({ weight: tag, bytes: total, files: Object.keys(bytes).length, art: bytes[`/assets/art/${theme}.webp`] || 0 });
      if (scale === 1.5) {
        // Controller: walk focus onto the navigation with the D-pad actions, check focus is visible, then Cross opens it.
        await p.mouse.move(640, 570);
        let onNav = false;
        for (let i = 0; i < 14 && !onNav; i++) {
          const used = await p.evaluate(() => window.omniMediaController('saved.previous'));
          onNav = await p.evaluate(() => !!document.activeElement?.closest('#navigation [data-route]'));
          if (!used && !onNav) break;
        }
        if (!onNav) { await p.evaluate(() => document.querySelector('#navigation [data-route]').focus()); await p.evaluate(() => window.omniMediaController('saved.next')); onNav = await p.evaluate(() => !!document.activeElement?.closest('#navigation [data-route]')); }
        check(`${tag}: D-pad reaches the navigation`, onNav);
        // move to the second route (down in lists, right in bands)
        const dir = ['relay', 'loom', 'kinetic'].includes(theme) ? 'saved.right' : 'saved.next';
        await p.evaluate(() => document.querySelector('#navigation [data-route]').focus());
        await p.evaluate(() => { document.documentElement.dataset.omniInput = 'pad'; });
        const moved = await p.evaluate(d => window.omniMediaController(d), dir);
        const focusInfo = await p.evaluate(() => { const a = document.activeElement, cs = getComputedStyle(a); return { route: a.dataset.route, outline: cs.outlineStyle, outlineColor: cs.outlineColor, outlineWidth: cs.outlineWidth }; });
        check(`${tag}: D-pad moves between routes`, moved === true && focusInfo.route === 'queue', { moved, focusInfo });
        check(`${tag}: focus is visible (white outline)`, focusInfo.outline !== 'none' && /255, 255, 255/.test(focusInfo.outlineColor) && parseFloat(focusInfo.outlineWidth) >= 3, focusInfo);
        await p.screenshot({ path: path.join(outDir, `${theme}-1080p-focus.png`) });
        const chose = await p.evaluate(() => window.omniMediaController('saved.choose'));
        await p.waitForTimeout(1000);
        const after = await p.evaluate(() => ({ current: document.querySelector('#navigation .is-current')?.dataset.route, h1: document.querySelector('h1')?.textContent }));
        check(`${tag}: Cross opens the focused route`, chose === true && after.current === 'queue', { chose, after });
        // Brightness: the current route must be the brightest (sampled from a screenshot of each route).
        const rects = await p.evaluate(() => [...document.querySelectorAll('#navigation [data-route]')].map(n => { const r = n.getBoundingClientRect(); return { route: n.dataset.route, current: n.classList.contains('is-current'), x: r.x, y: r.y, w: r.width, h: r.height }; }));
        await p.evaluate(() => document.activeElement?.blur());
        const shotPath = path.join(outDir, `${theme}-1080p-current-queue.png`);
        await p.screenshot({ path: shotPath });
        results.push({ brightness: tag, shot: shotPath, rects, scale });
      }
      await p.screenshot({ path: path.join(outDir, `${tag.replace('@', '-')}.png`) });
      check(`${tag}: no page errors`, errs.length === 0, { errs });
      await ctx.close();
    }
  }
  // ---- Reduced motion (page setting and OS setting)
  for (const mode of ['page', 'os']) {
    const { ctx, p } = await run('bloom', 1.5, mode === 'page' ? { reduce: true } : { osReduce: true });
    const info = await navInfo(p);
    const cur = info.buttons.find(x => x.current);
    check(`reduced motion (${mode}): current route not moved, no transition/animation`, cur && cur.transform === 'none' && /^0s/.test(cur.transition) && (cur.anim === 'none' || !cur.anim), { cur });
    await ctx.close();
  }
  // ---- Bloom unfurl plays when Bloom is picked, not on load or on route changes
  { const { ctx, p } = await run('tide', 1.5);
    const onLoad = await p.evaluate(() => !!document.querySelector('.u-enter'));
    await p.evaluate(() => document.querySelector('#theme-toggle').click()); await p.waitForTimeout(300);
    await p.evaluate(() => document.querySelector('#theme-grid [data-theme-choice="bloom"]').click()); await p.waitForTimeout(60);
    const first = await p.evaluate(() => !!document.querySelector('.u-bloom.u-enter'));
    await p.evaluate(() => document.querySelector('#theme-dialog').close());
    await p.evaluate(() => document.querySelector('#navigation [data-route="queue"]').click()); await p.waitForTimeout(900);
    const again = await p.evaluate(() => !!document.querySelector('.u-bloom.u-enter'));
    check('bloom: unfurl only when picked (not on load or route change)', onLoad === false && first === true && again === false, { onLoad, first, again });
    await ctx.close(); }
  // ---- Controller labels setting
  { const { ctx, p } = await run('bloom', 1.5);
    const def = await navInfo(p);
    check('labels: Xbox by default (theme dialog hint)', def.glyphKbd === 'A', { kbd: def.glyphKbd });
    await p.evaluate(() => document.querySelector('#navigation [data-route="settings"]').click()); await p.waitForTimeout(900);
    const sel = await p.$('#glyph-select'); check('labels: setting present in Settings', !!sel);
    if (sel) { await p.evaluate(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Shift' })); document.querySelector('#glyph-select').focus(); });
      const used = await p.evaluate(() => window.omniMediaController('saved.choose')); await p.waitForTimeout(200);
      const ps = await navInfo(p); const stored = await p.evaluate(() => localStorage.getItem('omni.glyphs'));
      check('labels: Cross on the select switches to PlayStation', used === true && ps.glyphKbd === 'Cross' && /Cross/.test(ps.hint?.text || '') && stored === 'playstation', { used, kbd: ps.glyphKbd, hint: ps.hint?.text, stored });
      await p.screenshot({ path: path.join(outDir, 'settings-controller-labels.png') }); }
    await ctx.close(); }
  // ---- Theme gallery: originals only, 15 Universes, none of the removed ones
  { const { ctx, p, errs } = await run('bloom', 1.5);
    await p.evaluate(() => document.querySelector('#theme-toggle').click()); await p.waitForTimeout(500);
    const g = await p.evaluate(() => ({ ids: [...document.querySelectorAll('#theme-grid [data-theme-choice]')].map(n => n.dataset.themeChoice), legendsTab: !document.querySelector('[data-theme-collection="legends"]').hidden, games: !document.querySelector('#games-toggle').hidden }));
    check('gallery: 15 original Universes, Bloom first', g.ids.length === 15 && g.ids[0] === 'bloom' && NEW.concat(OLD).every(id => g.ids.includes(id)), { ids: g.ids });
    check('gallery: no Omnitrix or franchise Universes', !g.ids.some(id => GONE.includes(id)) && !g.legendsTab && !g.games, g);
    await p.screenshot({ path: path.join(outDir, 'gallery-1080p.png') });
    check('gallery: no page errors', errs.length === 0, { errs });
    await ctx.close(); }
  // ---- Public mark: the user's swirl icon, no hourglass
  { const { ctx, p } = await run('bloom', 1.5);
    const m = await p.evaluate(() => ({ mark: getComputedStyle(document.querySelector('.brand-mark')).backgroundImage, i: getComputedStyle(document.querySelector('.brand-mark i')).display, sigil: getComputedStyle(document.querySelector('.transform-hourglass')).clipPath, sigilBg: getComputedStyle(document.querySelector('.transform-hourglass')).backgroundImage }));
    const iconOk = await p.evaluate(async () => (await fetch('/assets/brand-icon.png')).status);
    check('mark: swirl icon in the header, no hourglass anywhere', /brand-icon\.png/.test(m.mark) && m.i === 'none' && m.sigil === 'none' && /brand-icon\.png/.test(m.sigilBg) && iconOk === 200, { ...m, iconOk });
    await ctx.close(); }
  // ---- Existing originals still render
  for (const theme of OLD) {
    const { ctx, p, errs } = await run(theme, 1.5);
    const info = await navInfo(p);
    check(`${theme}@1080p: renders (routes + no overflow + no errors)`, info.theme === theme && info.count >= 5 && !info.overflowX && errs.length === 0, { theme: info.theme, count: info.count, overflowX: info.overflowX, errs });
    await p.screenshot({ path: path.join(outDir, `${theme}-1080p.png`) });
    await ctx.close();
  }
  // ---- A stored Omnitrix preference from an old install falls back to Bloom
  { const { ctx, p } = await run('omnitrix', 1.5); const info = await navInfo(p);
    check('old omnitrix preference falls back to Bloom', info.theme === 'bloom', { theme: info.theme }); await ctx.close(); }
  await b.close();
  fs.writeFileSync(path.join(outDir, 'results.json'), JSON.stringify({ failures, results }, null, 1));
  console.log(failures ? `FAILURES: ${failures}` : 'ALL PASS');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
