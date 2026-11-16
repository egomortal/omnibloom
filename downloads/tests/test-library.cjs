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
    // OMNI_DL_LIBRARY_SEARCH_V1: type chips (several at once), search, sort, remembered choices, Show trash toggle.
    const waitRows = (want, extra) => p.waitForFunction(([w, x]) => {
      const names = [...document.querySelectorAll('#files-library .lib-row strong')].map(n => n.textContent).join('|');
      const st = document.querySelector('#files-library .lib-status')?.textContent || '';
      return names === w && (!x || new RegExp(x).test(st));
    }, [want, extra ? extra.source : ''], { timeout: 8000 }).then(() => true, () => false);
    const chip = c => p.click(`#files-library [data-lib-cat="${c}"]`);
    const pressed = () => p.$$eval('#files-library [data-lib-cat][aria-pressed="true"]', n => n.map(x => x.dataset.libCat).join());
    await chip('audio');
    check('L6 Audio chip (back to page 1)', await waitRows('Tone.wav', /^1 file, newest first/) && await pressed() === 'audio', { rows: await rows(), pressed: await pressed() });
    await chip('video');
    check('L7 Video chip adds to Audio', await waitRows('Clip.mp4|Tone.wav', /^2 files/) && await pressed() === 'video,audio', { rows: await rows() });
    await chip('audio');
    check('L7b pressing Audio again removes it', await waitRows('Clip.mp4'), { rows: await rows() });
    await chip('all');
    await waitStatus(/^56 files/);
    await chip('image');
    check('L8 Images chip', await waitRows('Picture.png'), { rows: await rows() });
    await chip('image'); await chip('archive');
    check('L8b Archives chip', await waitRows('Archive.zip'), { rows: await rows() });
    await chip('archive'); await chip('other');
    await waitStatus(/^52 files/);
    check('L8c Other chip: only the .bin parts', (await rows()).every(n => /^Part \d\d\.bin$/.test(n)), {});
    await chip('other'); await chip('document');
    check('L8d Documents chip with nothing to show says so', await waitRows('', /^No files match in the chosen types/), { status: await status() });
    await chip('all');
    await waitStatus(/^56 files/);
    check('L8e All clears the chips', await pressed() === 'all', { pressed: await pressed() });

    await p.click('#lib-search');
    await p.keyboard.type('part 5');
    check('L8f search filters by name as you type (case-insensitive)', await waitRows('Part 50.bin|Part 51.bin', /^2 files match “part 5”, newest first/), { rows: await rows(), status: await status() });
    check('L8g focus stays in the search box while the list updates', await p.evaluate(() => document.activeElement?.id === 'lib-search'), {});
    await p.fill('#lib-search', 'finished tone');
    await p.keyboard.press('Enter');
    check('L8h search also matches the download title (Enter searches at once)', await waitRows('Tone.wav', /^1 file matches “finished tone”/), { rows: await rows() });
    await chip('video');
    check('L8i search and chips combine', await waitRows('', /^No files match “finished tone” in the chosen types/), { status: await status() });
    await chip('all');
    await p.fill('#lib-search', '');
    await waitStatus(/^56 files, newest first/);

    const sortTo = async (value, first, note) => { await p.selectOption('#lib-sort', value); return p.waitForFunction(([f, n]) => document.querySelector('#files-library .lib-row strong')?.textContent === f && (document.querySelector('#files-library .lib-status')?.textContent || '').includes(n), [first, note], { timeout: 8000 }).then(() => true, () => false); };
    check('L8j sort Name', await sortTo('name', 'Archive.zip', 'by name'), { rows: (await rows()).slice(0, 3) });
    check('L8k sort Size (largest first)', await sortTo('size', 'Tone.wav', 'largest first'), { rows: (await rows()).slice(0, 3) });
    check('L8l sort Oldest', await sortTo('oldest', 'Part 51.bin', 'oldest first'), { rows: (await rows()).slice(0, 3) });
    check('L8m sort Type (video first)', await sortTo('type', 'Clip.mp4', 'by type'), { rows: (await rows()).slice(0, 3) });

    await sortTo('size', 'Tone.wav', 'largest first');
    await chip('other');
    await waitStatus(/^52 files, largest first/);
    const stored = await p.evaluate(() => localStorage.getItem('omni-dl-library-view-v1'));
    await p.goto('about:blank'); await p.goto(BASE + '/downloads#view=files');
    await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
    await waitStatus(/^52 files, largest first/);
    check('L8n sort and chips are remembered across a reload (localStorage)', stored === '{"sort":"size","cats":["other"]}' && await p.$eval('#lib-sort', s => s.value) === 'size' && await pressed() === 'other' && (await rows())[0] === 'Part 51.bin', { stored, first: (await rows())[0] });
    await p.evaluate(() => localStorage.setItem('omni-dl-library-view-v1', '{"sort":"evil<script>","cats":["exe","video","video"]}'));
    await p.goto('about:blank'); await p.goto(BASE + '/downloads#view=files');
    await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
    check('L8o a tampered store falls back to known values', await waitRows('Clip.mp4', /newest first/) && await p.$eval('#lib-sort', s => s.value) === 'newest', { rows: await rows() });
    await chip('all');
    await waitStatus(/^56 files, newest first/);

    // Controller: every new control is a plain focusable (button / text field / select) in reading order, so the
    // D-pad moves over them and Cross steps the select or opens the on-screen keyboard on the field.
    const order = await p.$$eval('#files-library button, #files-library input, #files-library select', n => n.filter(x => x.getClientRects().length && !x.disabled && x.tabIndex >= 0).slice(0, 12).map(x => x.id || x.dataset.libCat || (x.dataset.libArea ? 'trash-toggle' : x.dataset.libLargest !== undefined ? 'largest' : 'refresh')));
    check('L8p controls are focusable in order: trash toggle, largest files, refresh, search, sort, chips',
      order.join() === 'trash-toggle,largest,refresh,lib-search,lib-sort,all,video,audio,image,document,archive,other', { order });
    check('L8q the search field is a plain text field (on-screen keyboard), 100 chars max',
      await p.$eval('#lib-search', i => i.type === 'search' && i.maxLength === 100 && i.autocomplete === 'off'), {});
    check('L8r Show trash is a toggle', await p.$eval('#files-library [data-lib-area]', b => b.getAttribute('aria-pressed') === 'false' && /Show trash/.test(b.textContent)), {});
    await shot('library-01b-tools');
    // OMNI_DL_STORAGE_METER_V1: the meter shows the worker's free space; Largest files switches to the size sort.
    await p.waitForFunction(() => !document.querySelector('#files-library .lib-storage')?.hidden, null, { timeout: 8000 }).catch(() => {});
    const meter = await p.$$eval('#files-library .lib-meter', n => n.map(m => ({ label: m.querySelector('.lib-meter-label').textContent, text: m.querySelector('.lib-meter-text').textContent, now: Number(m.querySelector('[role=meter]').getAttribute('aria-valuenow')) })));
    check('L8s storage meter shows console storage with free space and a used share', meter.length >= 1 && meter[0].label === 'Console storage' && /free of/.test(meter[0].text) && meter[0].now >= 0 && meter[0].now <= 100, { meter });
    await p.click('#files-library [data-lib-largest]');
    await waitStatus(/largest first/);
    check('L8t Largest files switches to the size sort', await p.$eval('#lib-sort', s => s.value) === 'size', {});
    await p.selectOption('#lib-sort', 'newest'); await waitStatus(/newest first/);

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
    check('L21b Show trash toggle reads pressed in the trash', await p.$eval('#files-library [data-lib-area]', b => b.getAttribute('aria-pressed') === 'true'), {});
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
