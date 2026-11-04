// dl6: unit test for the R3-043 preset fields ported onto the downloader-5 client (production-api.js).
'use strict';
const assert = require('assert');
const api = require('../worker/assets/production-api.js');
const sent = [];
const fetcher = async (path, init) => {
  sent.push({ path, body: init && init.body ? JSON.parse(init.body) : undefined });
  const body = path === '/api/jobs' ? { id: 'a'.repeat(16) } : {};
  return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(body) };
};
let n = 0;
const client = api.create({ fetch: fetcher, token: 'T'.repeat(24), randomBytes: () => new Uint8Array(16).fill(++n) });
const base = { url: 'https://example.org/v', engine: 'ytdlp', demo: false, audio: false };
(async () => {
  let r = await client.createJob(Object.assign({}, base, { preset: 'audio-opus' }));
  assert.strictEqual(r.id, 'a'.repeat(16));
  assert.strictEqual(sent.at(-1).body.preset, 'audio-opus');
  r = await client.createJob(Object.assign({}, base, { preset: 'subtitles', subtitle_lang: 'pt-BR' }));
  assert.strictEqual(sent.at(-1).body.subtitle_lang, 'pt-BR');
  await assert.rejects(client.createJob(Object.assign({}, base, { preset: 'everything' })), /valid preset/);
  await assert.rejects(client.createJob(Object.assign({}, base, { preset: 'best', quality: { height: 720 } })), /either a preset or a quality/);
  await assert.rejects(client.createJob(Object.assign({}, base, { engine: 'jdownloader', preset: 'best' })), /yt-dlp/);
  await assert.rejects(client.createJob(Object.assign({}, base, { preset: 'best', subtitle_lang: 'en' })), /subtitle language/);
  await assert.rejects(client.createJob(Object.assign({}, base, { preset: 'subtitles', subtitle_lang: '.*' })), /subtitle language/);
  // Old fields still pass through unchanged.
  await client.createJob(Object.assign({}, base, { quality: { height: 1080 } }));
  assert.deepStrictEqual(sent.at(-1).body.quality, { height: 1080 });
  assert.strictEqual(sent.at(-1).body.preset, undefined);
  console.log('CLIENT PRESETS PASS: 9 checks');
})().catch(e => { console.error('CLIENT PRESETS FAIL', e); process.exit(1); });
