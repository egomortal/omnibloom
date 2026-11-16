// OMNI_SITE_SEARCH_V1: runs the page script written by test_site_search.cpp (argv[2]) against stub page APIs.
//   node test_site_search_js.mjs script.js
// Checks: it parses as an async function body; no link -> none; the description is fetched from the page (https only,
// no cookies) and answered with the tag; http links / http pages / redirects to http / non-ok / thrown fetches /
// oversized bodies (by content-length and by streamed size) / a missing ReadableStream all answer "fail".
import fs from 'node:fs';

const body = fs.readFileSync(process.argv[2], 'utf8');
let fails = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };

const AsyncFunction = (async () => {}).constructor;
const names = ['document', 'location', 'fetch', 'URL', 'AbortController', 'TextDecoder', 'setTimeout', 'clearTimeout'];
let make;
try { make = new AsyncFunction(...names, body); check(true, 'parses'); } catch (e) { check(false, 'parses: ' + e.message); process.exit(1); }

const enc = new TextEncoder();
function response({ ok = true, url = 'https://ex.example/osd.xml', text = '<x/>', length = null, stream = true, chunks = null }) {
  const parts = chunks || [enc.encode(text)];
  let i = 0;
  return {
    ok, url,
    headers: { get: (h) => (h.toLowerCase() === 'content-length' && length !== null ? String(length) : null) },
    body: stream ? { getReader: () => ({ read: async () => (i < parts.length ? { done: false, value: parts[i++] } : { done: true }), cancel() { this.cancelled = true; } }) } : null,
    text: async () => text,
  };
}
async function run({ link = { href: '/osd.xml' }, page = 'https://ex.example/a/b', resp = {}, fetchThrows = false }) {
  const calls = [];
  const document = {
    baseURI: page,
    querySelector: (sel) => {
      calls.push(['qs', sel]);
      return link ? { getAttribute: (n) => (n === 'href' ? link.href : null) } : null;
    },
  };
  const location = { protocol: new URL(page).protocol, href: page };
  const fetch = async (u, opts) => { calls.push(['fetch', u, opts]); if (fetchThrows) throw new TypeError('cors'); return response(resp); };
  const out = await make(document, location, fetch, URL, AbortController, TextDecoder, setTimeout, clearTimeout);
  return { out, calls };
}

{
  const { out, calls } = await run({});
  check(out === 'omni-sse\n<x/>', 'answers the XML with the tag: ' + JSON.stringify(out));
  const f = calls.find((c) => c[0] === 'fetch');
  check(f && f[1] === 'https://ex.example/osd.xml', 'resolves the href against the page');
  check(f && f[2].credentials === 'omit', 'no cookies');
  check(calls[0][1].includes('opensearchdescription+xml') && calls[0][1].includes('rel~="search"'), 'selector');
}
check((await run({ link: null })).out === 'omni-sse-none', 'no link: none');
check((await run({ link: { href: 'http://ex.example/osd.xml' } })).out === 'omni-sse-fail', 'http link refused');
check((await run({ link: { href: 'javascript:alert(1)' } })).out === 'omni-sse-fail', 'javascript: link refused');
check((await run({ link: { href: 'https://[bad' } })).out === 'omni-sse-fail', 'bad URL');
check((await run({ page: 'http://ex.example/' })).out === 'omni-sse-fail', 'http page refused');
check((await run({ resp: { url: 'http://ex.example/osd.xml' } })).out === 'omni-sse-fail', 'redirect to http refused');
check((await run({ resp: { ok: false } })).out === 'omni-sse-fail', 'non-ok');
check((await run({ fetchThrows: true })).out === 'omni-sse-fail', 'fetch throws (CORS)');
check((await run({ resp: { length: 20000 } })).out === 'omni-sse-fail', 'content-length too big');
check((await run({ resp: { chunks: [new Uint8Array(10000), new Uint8Array(10000)] } })).out === 'omni-sse-fail', 'streamed too big');
check((await run({ resp: { stream: false, text: 'y'.repeat(20000) } })).out === 'omni-sse-fail', 'text too big');
check((await run({ resp: { stream: false, text: '<ok/>' } })).out === 'omni-sse\n<ok/>', 'text fallback');
{
  const multi = [enc.encode('<a>caf'), new Uint8Array([0xc3]), new Uint8Array([0xa9]), enc.encode('</a>')];
  check((await run({ resp: { chunks: multi } })).out === 'omni-sse\n<a>café</a>', 'UTF-8 split across chunks');
}
{
  const exact = 'z'.repeat(16384);
  check((await run({ resp: { text: exact } })).out === 'omni-sse\n' + exact, 'exactly 16 KB accepted');
}

console.log((fails ? 'FAILED' : 'OK') + ': ' + checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
