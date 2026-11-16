// OMNI_SITE_CLEAR_V1: runs the page script written by test_site_clear.cpp (argv[1]) against stub storage APIs.
//   node test_site_clear_js.mjs script.js
// Checks: it parses as an async function body, clears every store, sets the expected cookie deletions,
// survives missing APIs, a blocked database and a hanging API (step timeout), and answers in the tagged format.
// r2: it keeps answering when the page replaces setTimeout / Promise.race / Promise.all while it runs (a page that
// replaced them before it starts is the shell's native timeout's job: OmniSiteClear::kNativeMs).
import fs from 'node:fs';
import vm from 'node:vm';

const body = fs.readFileSync(process.argv[2], 'utf8');
let fails = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };

function makeEnv(opts) {
  const writes = [];
  const store = (n) => ({ length: n, cleared: false, clear() { this.cleared = true; this.length = 0; } });
  const env = {
    setTimeout, Promise, Object, Array, console,
    localStorage: store(3), sessionStorage: store(1),
    location: { hostname: opts.host, pathname: opts.path },
    document: {},
    navigator: {},
  };
  let jar = opts.cookies;
  Object.defineProperty(env.document, 'cookie', { get: () => jar, set: (v) => { writes.push(v); } });
  if (opts.idb) env.indexedDB = {
    databases: () => Promise.resolve(opts.idb.map((name) => ({ name, version: 1 }))),
    deleteDatabase(name) {
      const rq = {};
      setTimeout(() => {
        if (name === 'blocked') { rq.onblocked && rq.onblocked(); return; }   // never succeeds
        if (name === 'bad') { rq.onerror && rq.onerror(); return; }
        rq.onsuccess && rq.onsuccess();
      }, 5);
      return rq;
    },
  };
  if (opts.caches) env.caches = { keys: () => Promise.resolve(opts.caches), delete: (k) => Promise.resolve(k !== 'stuck') };
  if (opts.sw) env.navigator.serviceWorker = { getRegistrations: () => opts.hangSw ? new Promise(() => {}) : Promise.resolve(opts.sw.map(() => ({ unregister: () => Promise.resolve(true) }))) };
  env.window = env;
  return { env, writes };
}
async function run(opts) {
  const { env, writes } = makeEnv(opts);
  const ctx = vm.createContext(env);
  const fn = vm.runInContext('(async function () {\n' + body + '\n})', ctx);
  const t0 = Date.now();
  const answer = await fn();
  return { answer, env, writes, ms: Date.now() - t0 };
}
const field = (a, k) => Number((a.split(';').find((x) => x.startsWith(k + '=')) || '').split('=')[1]);

// 1. everything present, www. host under the site
let r = await run({ host: 'www.example.com', path: '/a/b', cookies: 'sid=1; theme=dark', idb: ['one', 'two'], caches: ['v1'], sw: [1] });
check(r.answer.startsWith('omni-site-clear;'), 'tag: ' + r.answer);
check(field(r.answer, 'ls') === 3 && field(r.answer, 'ss') === 1 && r.env.localStorage.cleared && r.env.sessionStorage.cleared, 'storage');
check(field(r.answer, 'ck') === 2, 'cookies counted');
check(field(r.answer, 'idb') === 2 && field(r.answer, 'idbb') === 0, 'idb');
check(field(r.answer, 'cs') === 1 && field(r.answer, 'sw') === 1 && field(r.answer, 'to') === 0, 'caches / sw');
// 2 names x 3 domains ("", www.example.com, example.com) x 3 paths (/, /a/b, /a)
check(r.writes.length === 18, 'cookie writes ' + r.writes.length);
check(r.writes.some((w) => w === 'sid=; expires=Thu, 01 Jan 1970 00:00:00 GMT; max-age=0; path=/; domain=example.com'), 'parent domain write');
check(!r.writes.some((w) => w.includes('domain=com')), 'never the public suffix');

// 2. no APIs at all (http page: no caches, no IndexedDB.databases, no service workers), no cookies
r = await run({ host: 'example.org', path: '/', cookies: '' });
check(field(r.answer, 'idb') === -1 && field(r.answer, 'cs') === -1 && field(r.answer, 'sw') === -1 && field(r.answer, 'ck') === 0, 'missing APIs: ' + r.answer);
check(r.writes.length === 0, 'no cookie writes');

// 3. blocked + failing database, a cache that doesn't delete, a hanging service worker API
r = await run({ host: 'example.com', path: '/', cookies: 'a=1', idb: ['ok', 'blocked', 'bad'], caches: ['v1', 'stuck'], sw: [1], hangSw: true });
check(field(r.answer, 'idb') === 1 && field(r.answer, 'idbb') === 1 && field(r.answer, 'idbf') === 1, 'idb mix: ' + r.answer);
check(field(r.answer, 'cs') === 1, 'one cache deleted');
check(field(r.answer, 'sw') === -1, 'hanging sw: not reached');
check(r.ms < 7000, 'within the overall limit (' + r.ms + ' ms)');

// 4. the page replaces setTimeout / Promise.race while the script runs: its own copies still end the hanging step
{
  const { env } = makeEnv({ host: 'example.com', path: '/', cookies: '', idb: ['x'], sw: [1], hangSw: true });
  class PagePromise extends Promise {}
  env.Promise = PagePromise;
  const realDelete = env.indexedDB.deleteDatabase;
  env.indexedDB.deleteDatabase = (name) => {
    env.setTimeout = () => 0;                                  // timers the page breaks after the script started
    PagePromise.race = () => new Promise(() => {});
    PagePromise.all = () => new Promise(() => {});
    return realDelete(name);
  };
  const ctx = vm.createContext(env);
  const fn = vm.runInContext('(async function () {\n' + body + '\n})', ctx);
  const t0 = Date.now();
  const answer = await Promise.race([fn(), new Promise((r) => setTimeout(() => r('HUNG'), 9000))]);
  check(answer !== 'HUNG' && answer.startsWith('omni-site-clear;'), 'replaced globals mid-run: ' + answer);
  check(field(answer, 'idb') === 1 && field(answer, 'sw') === -1, 'replaced globals: steps ' + answer);
  // the hanging step ended on its own 2.5 s timer (not the 6 s overall one): the replaced globals were not used
  check(field(answer, 'to') === 0 && Date.now() - t0 < 5000, 'replaced globals: step timer still works (' + (Date.now() - t0) + ' ms)');
}

console.log(checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
