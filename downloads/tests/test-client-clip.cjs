// OMNI_DL_CLIP_V1 (D01): unit test for the clip fields on the downloads client (production-api.js).
'use strict';
const assert = require('assert');
const api = require('../worker/assets/production-api.js');
const sent = [];
const fetcher = async (path, init) => {
  sent.push({ path, body: init && init.body ? JSON.parse(init.body) : undefined });
  const body = path === '/api/jobs' ? { id: 'b'.repeat(16) } : {};
  return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(body) };
};
let n = 0;
const client = api.create({ fetch: fetcher, token: 'T'.repeat(24), randomBytes: () => new Uint8Array(16).fill(++n) });
const base = { url: 'https://example.org/v', engine: 'ytdlp', demo: false, audio: false };
let checks = 0;
const ok = () => { checks++; };
(async () => {
  await client.createJob(Object.assign({}, base, { clip_start: '1:20', clip_end: '3:45' }));
  assert.strictEqual(sent.at(-1).body.clip_start, '1:20'); assert.strictEqual(sent.at(-1).body.clip_end, '3:45'); ok();
  const first = sent.at(-1).body.request_id;
  await client.createJob(Object.assign({}, base, { clip_end: '1:02:03' }));
  assert.strictEqual(sent.at(-1).body.clip_start, undefined); assert.strictEqual(sent.at(-1).body.clip_end, '1:02:03'); ok();
  assert.notStrictEqual(sent.at(-1).body.request_id, first); ok();   // another clip is another request
  for (const bad of ['80', '1:2', '1:60', '1.20', '12:00:00', '1:20 ', 'x', 5]) {
    await assert.rejects(client.createJob(Object.assign({}, base, { clip_end: bad })), /Clip times look like/, String(bad)); ok();
  }
  await assert.rejects(client.createJob(Object.assign({}, base, { clip_start: '1:20' })), /end time/); ok();
  await assert.rejects(client.createJob(Object.assign({}, base, { engine: 'jdownloader', clip_end: '3:45' })), /yt-dlp/); ok();
  await assert.rejects(client.createJob(Object.assign({}, base, { direct: true, clip_end: '3:45' })), /yt-dlp/); ok();
  // A whole download sends no clip fields.
  await client.createJob(Object.assign({}, base, { clip_start: '', clip_end: '' }));
  assert.ok(!('clip_start' in sent.at(-1).body) && !('clip_end' in sent.at(-1).body)); ok();
  console.log('CLIENT CLIP PASS: ' + checks + ' checks');
})().catch(e => { console.error('CLIENT CLIP FAIL', e); process.exit(1); });
