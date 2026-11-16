// OMNI_GRABBER_SUSPECTS_V1: "maybe a playlist" rows from Omni (kind manifest, score 45) appear only once the link
// check confirms them. node test-suspects.cjs <outDir>   (STUB_PROBE=1 stub_worker.py serving the GUI at 127.0.0.1:8765)
const pw = require('playwright'); const fs = require('fs'); const path = require('path');
const outDir = process.argv[2]; fs.mkdirSync(outDir, { recursive: true });
const BASE = 'http://127.0.0.1:' + (process.env.STUB_PORT || 8765) + '/downloads';
const PAGE = 'https://site.example/watch/2';
const GOOD = 'https://cdn.example/hls/list.m3u8.png'; // the stub's check answers "ok" (any other address)
const BAD = 'https://cdn.example/gone/list.txt';        // the stub's check answers "dead"
const wire = JSON.stringify({ v: 1, g: '9', p: PAGE, t: false, rows: [
  { u: GOOD, k: 'manifest', s: 45, e: ['resource-timing'] },
  { u: BAD, k: 'manifest', s: 45, e: ['resource-timing'] },
  { u: PAGE, k: 'source-page', s: 25, e: ['iframe'] }] });
let failures = 0;
const check = (name, ok, data) => { if (!ok) failures++; console.log((ok ? 'PASS ' : 'FAIL ') + name, ok ? '' : JSON.stringify(data)); };
(async () => {
  const b = await pw.chromium.launch({ args: ['--no-proxy-server'], ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}) });
  const p = await (await b.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.goto(BASE + '#url=' + encodeURIComponent(PAGE) + '&candidate=' + encodeURIComponent(PAGE) + '&detected=0&candidates=' + encodeURIComponent(wire));
  await p.waitForFunction(() => document.documentElement.dataset.ready === 'true');
  await p.waitForTimeout(2500); // the checks answer after ~0.25 s each
  const rows = await p.evaluate(() => [...document.querySelectorAll('#form-candidates .candidate-pick')].map(n => n.dataset.pickUrl));
  check('U1 a confirmed suspect is shown', rows.includes(GOOD), rows);
  check('U2 a suspect the check rejects stays hidden', !rows.includes(BAD), rows);
  check('U3 the page row is still there', rows.includes(PAGE), rows);
  check('U4 no page errors', !errs.length, errs);
  await p.screenshot({ path: path.join(outDir, 'suspects.png') });
  await b.close();
  console.log(failures ? 'SUSPECTS FAIL: ' + failures : 'SUSPECTS PASS');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
