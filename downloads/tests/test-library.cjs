// OMNI_DL_LIBRARY_V1: Library panel, player page, open, two-step delete via trash. Runs the REAL worker
// (serve_library_worker.py, temp folder) and stops it afterwards.
// node test-library.cjs <outDir>   env: PW_CHANNEL=msedge, PYTHON=python, LIB_PORT=8791
const pw = require('playwright'); const fs = require('fs'); const path = require('path'); const { spawn } = require('child_process');
const outDir = process.argv[2] || path.join(__dirname, '..', 'out-tools', 'library'); fs.mkdirSync(outDir, { recursive: true });
const PORT = Number(process.env.LIB_PORT || 8791), BASE = 'http://127.0.0.1:' + PORT;
const log = []; let failures = 0;
const check = (name, ok, data = {}) => { if (!ok) failures++; log.push({ check: name, pass: !!ok, ...data }); console.log((ok ? 'PASS ' : 'FAIL ') + name, ok ? '' : JSON.stringify(data)); };

function startWorker() {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON || 'python', [path.join(__dirname, 'serve_library_worker.py'), String(PORT)], { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    const timer = setTimeout(() => reject(new Error('worker did not start: ' + err)), 20000);
    child.stdout.on('data', d => { out += d; const m = /ready (\d+) (.+)\r?\n/.exec(out); if (m) { clearTimeout(timer); resolve({ child, tmp: m[2].trim() }); } });
    child.stderr.on('data', d => { err += d; });
    child.on('exit', code => { clearTimeout(timer); reject(new Error('worker exited ' + code + ': ' + err)); });
  });
}

(async () => {
  const { child, tmp } = await startWorker();
  let browser;
  try {
    browser = await pw.chromium.launch({ args: ['--no-proxy-server', '--autoplay-policy=no-user-gesture-required'], ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}) });
    const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
    const p = await ctx.newPage();
    const errs = []; p.on('pageerror', e => errs.push(String(e)));
    p.on('console', m => { if (m.type() === 'error' && !/404|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()); });
    const shot = name => p.screenshot({ path: path.join(outDir, name + '.png') });
    const rows = () => p.$$eval('#files-library .lib-row strong', n => n.map(x => x.textContent));
    const status = () => p.$eval('#files-library .lib-status', n => n.textContent);
    const waitStatus = re => p.waitForFunction(r => new RegExp(r).test(document.querySelector('#files-library .lib-status')?.textContent || ''), re.source, { timeout: 8000 });

    await p.goto(BASE + '/downloads#view=files');
    await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
    await waitStatus(/files, newest first/);
    let names = await rows();
    check('L1 #view=files opens the Queue page with the Library listing, newest first',
      names.slice(0, 4).join('|') === 'Clip.mp4|Tone.wav|Picture.png|Archive.zip' && /^56 files/.test(await status()), { names: names.slice(0, 5), status: await status() });
    check('L2 hidden work files are not listed and the hash was cleared', !names.includes('Hidden.mp4') && !(await p.evaluate(() => location.hash)), {});
    check('L3 a page lists 50, pager shows the range', names.length === 50 && (await p.$eval('#files-library .lib-range', n => n.textContent)) === '1–50 of 56', { n: names.length });
    const toneRow = await p.$eval('#files-library .lib-row:nth-child(2) small', n => n.textContent);
    check('L4 row shows type, size, date and place/folder', /^Audio · 234 KB · .+ · Console storage \/ Music$/.test(toneRow), { toneRow });
    await shot('library-01-list');

    await p.click('#files-library [data-lib-page="1"]');
    await p.waitForFunction(() => document.querySelector('#files-library .lib-range')?.textContent === '51–56 of 56');
    names = await rows();
    check('L5 Next shows the last 6 (oldest last)', names.length === 6 && names[5] === 'Part 51.bin', { names });
    await p.click('#files-library [data-lib-kind="audio"]');
    await waitStatus(/^1 file/);
    check('L6 Audio filter', (await rows()).join() === 'Tone.wav', { rows: await rows() });
    await p.click('#files-library [data-lib-kind="video"]');
    await waitStatus(/^1 file/);
    check('L7 Video filter', (await rows()).join() === 'Clip.mp4', { rows: await rows() });
    await p.click('#files-library [data-lib-kind="other"]');
    await waitStatus(/^54 files/);
    check('L8 Other filter (no audio/video)', !(await rows()).some(n => /\.(wav|mp4)$/.test(n)), {});
    await p.click('#files-library [data-lib-kind="all"]');
    await waitStatus(/^56 files/);

    // Job row: a finished download has a Play button.
    check('L9 the finished job row has a Play button', !!(await p.$('[data-job-id="abababababababab"] [data-file-job]')), {});

    // Play the tone in the player page.
    await p.click('#files-library .lib-row:nth-child(2) [data-lib-play]');
    await p.waitForURL(/\/player#id=[0-9a-f]{32}$/);
    await p.waitForFunction(() => document.querySelector('audio')?.readyState >= 1, null, { timeout: 8000 });
    const title = await p.textContent('#title');
    const src = await p.$eval('audio', a => a.getAttribute('src'));
    check('L10 player loads the file over a signed link', title === 'Tone.wav' && /^\/api\/files\/stream\?id=[0-9a-f]{32}&exp=\d+&sig=[0-9a-f]{64}$/.test(src), { title, src });
    await p.evaluate(() => { const a = document.querySelector('audio'); a.pause(); a.currentTime = 0; });
    await p.keyboard.press('Enter');
    await p.waitForTimeout(700);
    const afterPlay = await p.$eval('audio', a => ({ paused: a.paused, t: a.currentTime }));
    check('L11 Cross (Enter) plays', !afterPlay.paused && afterPlay.t > 0, afterPlay);
    await p.keyboard.press('ArrowRight');
    await p.waitForTimeout(300);
    const afterSeek = await p.$eval('audio', a => a.currentTime);
    check('L12 Right seeks forward 10 s (Range requests)', afterSeek >= 10, { afterSeek });
    await p.keyboard.press('ArrowLeft');
    await p.waitForTimeout(200);
    const afterBack = await p.$eval('audio', a => a.currentTime);
    check('L13 Left seeks back 10 s', afterBack < afterSeek - 8, { afterSeek, afterBack });
    await p.keyboard.press('Enter');
    check('L14 Cross again pauses', await p.$eval('audio', a => a.paused), {});
    check('L15 the Omni controller hook works (saved.dismiss = Circle is handled)', await p.evaluate(() => typeof window.omniMediaController === 'function' && window.omniMediaController('saved.left') === true && window.omniMediaController('saved.up') === false), {});
    await shot('library-02-player');
    await p.keyboard.press('Escape');
    await p.waitForFunction(() => location.pathname === '/downloads' && !location.hash && document.documentElement.dataset.ready === 'true', null, { timeout: 8000 });
    await waitStatus(/files, newest first/);
    check('L16 Circle (Escape) returns to the Library', (await rows()).length === 50, {});

    // Open a picture: the browser shows the signed stream URL.
    await p.click('#files-library .lib-row:nth-child(3) [data-lib-open]');
    await p.waitForURL(/\/api\/files\/stream\?id=/);
    const img = await p.evaluate(() => ({ type: document.contentType, w: document.images[0]?.naturalWidth }));
    check('L17 Open shows the picture inline (image/png)', img.type === 'image/png' && img.w === 1, img);
    await p.goBack();
    await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');

    // Two-step delete -> trash -> delete for good.
    await p.goto(BASE + '/downloads#view=files');
    await waitStatus(/^56 files/);
    const zip = '#files-library .lib-row:nth-child(4)';
    check('L18 Archive.zip has no Play/Open (only Delete)', !(await p.$(zip + ' [data-lib-play]')) && !(await p.$(zip + ' [data-lib-open]')), {});
    await p.click(zip + ' [data-lib-trash]');
    const armed = await p.$eval(zip + ' [data-lib-trash]', b => b.textContent.trim());
    check('L19 first press only arms Delete', armed === 'Delete?' && (await rows()).includes('Archive.zip'), { armed });
    await shot('library-03-confirm');
    await p.click(zip + ' [data-lib-trash]');
    await waitStatus(/^55 files/);
    check('L20 second press moves it to the trash', !(await rows()).includes('Archive.zip'), {});
    await p.click('#files-library [data-lib-area="trash"]');
    await waitStatus(/in the trash/);
    check('L21 Trash view lists it', (await rows()).join() === 'Archive.zip', { rows: await rows() });
    await p.click('#files-library [data-lib-delete]');
    await p.click('#files-library [data-lib-delete]');
    await waitStatus(/trash is empty/);
    check('L22 Delete for good empties the trash', (await rows()).length === 0 && !fs.existsSync(path.join(tmp, 'Saved', '.trash', 'Archive.zip')) && !fs.existsSync(path.join(tmp, 'Saved', 'Archive.zip')), {});
    await shot('library-04-trash');

    // The API refuses a raw path and an unsigned stream.
    const t = await p.evaluate(() => document.querySelector('meta[name="omni-session-token"]').content);
    const api = await p.evaluate(async t => {
      const link = await fetch('/api/files/link', { method: 'POST', headers: { 'X-Omni-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify({ path: 'C:/Windows/win.ini' }) });
      const bare = await fetch('/api/files/stream?id=' + 'a'.repeat(32));
      return { link: link.status, bare: bare.status };
    }, t);
    check('L23 raw paths and unsigned streams are refused', api.link === 400 && api.bare === 403, api);
    check('L24 no page errors', errs.length === 0, { errs });
  } catch (error) {
    failures++; console.log('FAIL exception', error.stack);
  } finally {
    if (browser) await browser.close();
    child.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
    fs.writeFileSync(path.join(outDir, 'library-results.json'), JSON.stringify(log, null, 2));
    console.log(failures ? failures + ' FAILED' : 'ALL PASS');
    process.exit(failures ? 1 : 0);
  }
})().catch(e => { console.error(e); process.exit(1); });
