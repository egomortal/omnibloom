// OMNI_DL_QUEUE_ORDER_V1 (D04): unit test for queue reorder on the downloads client (production-api.js)
// and the queued-row buttons in app.js.   node tests/test-client-queue.cjs
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const api = require('../worker/assets/production-api.js');
const A = 'a'.repeat(16), B = 'b'.repeat(16), C = 'c'.repeat(16), D = 'd'.repeat(16);
const sent = [];
let reply = () => ({});
const fetcher = async (url, init) => {
  sent.push({ url, body: init && init.body ? JSON.parse(init.body) : undefined });
  const { status = 200, body } = reply(url, init);
  return { ok: status < 400, status, headers: { get: () => null }, text: async () => JSON.stringify(body) };
};
const client = api.create({ fetch: fetcher, token: 'T'.repeat(24), randomBytes: () => new Uint8Array(16).fill(1) });
let checks = 0;
const ok = () => { checks++; };
const job = (id, state, extra) => Object.assign({ id, state, engine: 'ytdlp', demo: true, audio: false, url: '', title: id, error: '', progress: 0 }, extra);
(async () => {
  // normalizeJob: a place only for waiting jobs with a sane number.
  assert.strictEqual(api.normalizeJob(job(A, 'queued', { queue_position: 2 })).queue_position, 2); ok();
  for (const bad of [0, -1, 1.5, '2', null, undefined, 101, true])
    { assert.strictEqual(api.normalizeJob(job(A, 'queued', { queue_position: bad })).queue_position, null, String(bad)); ok(); }
  assert.strictEqual(api.normalizeJob(job(A, 'downloading', { queue_position: 1 })).queue_position, null); ok();

  // queueOrder: waiting rows keep their slots but follow the run order (next on top); others stay put.
  const rows = [{ id: 'x' }, { id: C, queue_position: 3 }, { id: 'y' }, { id: A, queue_position: 1 }, { id: B, queue_position: 2 }];
  assert.deepStrictEqual(api.queueOrder(rows).map(r => r.id), ['x', A, 'y', B, C]); ok();
  assert.deepStrictEqual(rows.map(r => r.id), ['x', C, 'y', A, B]); ok();          // input untouched

  // state(): the list from /api/status comes back in run order.
  reply = url => url === '/api/status'
    ? { body: { api_version: 1, service: 'omni-media-worker', max_pending: 8, queue_paused: true, ytdlp: true, jdownloader: false, folder: '', history_error: '',
        jobs: [job(A, 'queued', { queue_position: 3 }), job(B, 'queued', { queue_position: 1 }), job(C, 'completed'), job(D, 'queued', { queue_position: 2 })] } }
    : url === '/api/saved-links' ? { body: { links: [], max_links: 64, writable: true, persistent: true, error: '' } } : { body: {} };
  const state = await client.state();
  assert.deepStrictEqual(state.jobs.map(j => j.id), [B, C, D, A]); ok();

  // move(): sends {id, to}, checks the receipt.
  reply = (url, init) => ({ body: { ok: true, id: JSON.parse(init.body).id, queue: [JSON.parse(init.body).id, A] } });
  for (const to of ['front', 'end', 'up', 'down', 0, 7]) {
    await client.move(B, to);
    assert.deepStrictEqual(sent.at(-1), { url: '/api/queue/move', body: { id: B, to } }); ok();
  }
  const before = sent.length;
  for (const to of ['top', '', null, -1, 1.5, '1', true, 100]) { await assert.rejects(client.move(B, to), /front, end/, String(to)); ok(); }
  await assert.rejects(client.move('nothex', 'front'), /Invalid job identity/); ok();
  assert.strictEqual(sent.length, before); ok();                                   // nothing sent for bad input
  reply = () => ({ body: { ok: true, id: B, queue: [A] } });
  await assert.rejects(client.move(B, 'front'), /did not confirm/); ok();
  reply = () => ({ status: 409, body: { error: 'Only a waiting download can be moved; this one is not in the queue.' } });
  await assert.rejects(client.move(B, 'front'), e => e.status === 409 && /waiting download/.test(e.message)); ok();

  // app.js: queued rows get the four move buttons (same icon-button pattern), wired through the client.
  const app = fs.readFileSync(path.join(__dirname, '../worker/app.js'), 'utf8');
  for (const [action, label] of [['move-front', 'Start next'], ['move-up', 'Move up'], ['move-down', 'Move down'], ['move-end', 'Move to end']]) {
    assert.ok(app.includes(`jobButton('${action}','${action}','${label}',job)`), action); ok();
  }
  assert.ok(/move-\(front\|end\|up\|down\)\$\/\.exec\(path\);[^\n]*\n\s*if\(move&&method==='POST'\)return client\.move\(move\[1\],move\[2\]\);/.test(app)); ok();
  assert.ok(app.includes("'+q'+job.queue_position+'/'+queueLength"), 'buttons re-render when the place changes'); ok();
  const icons = fs.readFileSync(path.join(__dirname, '../worker/assets/icons.svg'), 'utf8');
  for (const name of ['move-front', 'move-up', 'move-down', 'move-end']) { assert.ok(icons.includes(`<symbol id="${name}"`), name); ok(); }

  // moveButtons(): run the real function from app.js on a few rows.
  const source = app.slice(app.indexOf('  let queueLength=0;'), app.indexOf('  function jobButtons(job){'));
  const make = new Function('jobButton', source + '\nreturn {set:n=>{queueLength=n;},moveButtons};');
  const kit = make((action) => action + ' ');
  const at = (n, len) => { kit.set(len); return kit.moveButtons({ queue_position: n }).trim(); };
  assert.strictEqual(at(1, 3), 'move-down move-end'); ok();
  assert.strictEqual(at(2, 3), 'move-front move-up move-down move-end'); ok();
  assert.strictEqual(at(3, 3), 'move-front move-up'); ok();
  assert.strictEqual(at(1, 1), ''); ok();                                            // alone: nothing to reorder
  assert.strictEqual(at(null, 3), ''); ok();
  console.log('CLIENT QUEUE PASS: ' + checks + ' checks');
})().catch(e => { console.error('CLIENT QUEUE FAIL', e); process.exit(1); });
