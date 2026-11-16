// OMNI_DOWNLOAD_ALL_V1: the "#files=" wire (batch-wire.js) and the client's addBatch / clearHeld (production-api.js).
// Run: node tests/test-download-all.cjs   (from the downloads folder)
'use strict';
const assert = require('assert');
const wire = require('../worker/assets/batch-wire.js');
const api = require('../worker/assets/production-api.js');
const valid = api.validUrl;
let checks = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); checks++; };
const eq = (a, b, msg) => { assert.deepStrictEqual(a, b, msg); checks++; };
const hash = value => '#files=' + encodeURIComponent(typeof value === 'string' ? value : JSON.stringify(value));

// --- wire ---
const urls = ['https://example.com/a.pdf', 'https://cdn.example.com/b%20c.zip?x=1', 'http://example.org/pic.jpg'];
let r = wire.parse(hash({ v: 1, p: 'https://example.com/page', u: urls }), valid);
eq(r, { ok: true, urls, page: 'https://example.com/page', message: '' }, 'plain list');
r = wire.parse(hash({ v: 1, u: urls.concat(urls[0]) }), valid);
eq([r.ok, r.urls.length, r.page], [true, 3, ''], 'duplicates dropped, page optional');
for (const bad of [
  { v: 2, u: urls }, { v: 1, u: [] }, { v: 1, u: 'https://example.com/a' }, { v: 1, u: urls, x: 1 },
  { v: 1, u: ['javascript:alert(1)'] }, { v: 1, u: ['https://u:p@example.com/a'] }, { v: 1, u: ['https://example.com/a b'] },
  { v: 1, u: urls, p: 'ftp://example.com/' }, { v: 1, u: Array.from({ length: 201 }, (_, i) => 'https://e.com/' + i) }, [urls],
]) ok(!wire.parse(hash(bad), valid).ok, 'rejects ' + JSON.stringify(bad).slice(0, 60));
ok(!wire.parse('#files=%7Bnot json', valid).ok, 'bad JSON');
ok(!wire.parse(hash({ v: 1, u: urls }) + '&files=x', valid).ok, 'two files fields');
ok(!wire.parse(hash({ v: 1, u: urls }), null).ok, 'no validator');
ok(/safety limit/.test(wire.parse('#files=' + 'x'.repeat(wire.hashMax), valid).message), 'size bound');
ok(wire.parse(hash({ v: 1, u: Array.from({ length: 200 }, (_, i) => 'https://e.com/' + 'p'.repeat(900) + i) }), valid).ok, '200 long links fit the bound');
eq(wire.nameOf('https://cdn.example.com/b%20c.zip?x=1'), 'b c.zip', 'name decoded');
eq(wire.nameOf('https://example.com/'), 'example.com', 'host when no name');
eq(wire.nameOf('https://example.com/%E0%A4%A.pdf'), '%E0%A4%A.pdf', 'bad escape kept');

// --- client ---
const sent = [];
let reply = () => ({ accepted: 3, skipped: 0, held: 0, replayed: false });
const fetcher = async (path, init) => {
  sent.push({ path, headers: init.headers, body: init.body ? JSON.parse(init.body) : undefined });
  const body = path === '/api/jobs/held/clear' ? { cleared: 5 } : reply();
  return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(body) };
};
let n = 0;
const client = api.create({ fetch: fetcher, token: 'T'.repeat(24), randomBytes: () => new Uint8Array(16).fill(++n) });
(async () => {
  let v = await client.addBatch(urls, 'https://example.com/page');
  eq(v, { accepted: 3, skipped: 0, held: 0, replayed: false }, 'receipt');
  const first = sent.at(-1);
  eq(first.path, '/api/jobs/batch', 'route');
  eq(first.headers['X-Omni-Token'], 'T'.repeat(24), 'token sent');
  eq(Object.keys(first.body).sort(), ['referer', 'request_id', 'urls'], 'body fields');
  ok(/^[a-f0-9]{32}$/.test(first.body.request_id), 'request id');
  await client.addBatch(urls, 'https://example.com/page');
  ok(sent.at(-1).body.request_id !== first.body.request_id, 'a confirmed batch gets a fresh id next time');
  reply = () => ({ accepted: 'x' });
  await assert.rejects(client.addBatch(urls.slice(0, 1)), e => e.code === 'INVALID_RESPONSE' && e.ambiguous === true); checks++;
  const retryId = sent.at(-1).body.request_id;
  reply = () => ({ accepted: 1, skipped: 0, held: 0, replayed: true });
  await client.addBatch(urls.slice(0, 1));
  eq(sent.at(-1).body.request_id, retryId, 'an unconfirmed batch is retried with the same id');
  ok(!('referer' in sent.at(-1).body), 'no referer when none');
  const before = sent.length;
  await assert.rejects(client.addBatch([]), /1 to 200/); checks++;
  await assert.rejects(client.addBatch(['javascript:1']), /1 to 200/); checks++;
  await assert.rejects(client.addBatch(urls, 'nope'), /page address/); checks++;
  await assert.rejects(client.addBatch(Array(201).fill(urls[0])), /1 to 200/); checks++;
  eq(sent.length, before, 'nothing sent for a bad list');
  eq(await client.clearHeld(), { cleared: 5 }, 'clear');
  eq(sent.at(-1).body, { clear: true }, 'clear body');
  console.log('DOWNLOAD ALL CLIENT PASS: ' + checks + ' checks');
})().catch(e => { console.error('DOWNLOAD ALL CLIENT FAIL', e); process.exit(1); });
