// OMNI_DL_PANEL_V1: the player-page script (OmniDlPanel::resolveScript) on a mock page (node).
//   ./t --emit DIR   (test_dl_panel.cpp), then: node test_dl_panel_js.cjs DIR
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const dir = process.argv[2];
if (!dir) { console.log('usage: node test_dl_panel_js.cjs <dir with dl_play.js, dl_image.js, dl_poll.js>'); process.exit(2); }
const src = (n) => fs.readFileSync(path.join(dir, n), 'utf8');
let fails = 0, checks = 0;
const check = (ok, what) => { ++checks; if (!ok) { ++fails; console.log('FAIL ' + what); } };
const ID = '0123456789abcdef0123456789abcdef', SIG = 'a'.repeat(64);

function page(files, opts = {}) {
  const calls = [];
  const els = { message: { textContent: 'No file was chosen.' }, title: { textContent: 'Nothing to play' } };
  const ctx = {
    calls, els, reloaded: 0,
    window: null,
    document: {
      title: '',
      querySelector: (q) => q === 'meta[name="omni-session-token"]' ? { content: 'TOKEN' } : null,
      getElementById: (id) => els[id] || null,
    },
    location: { hash: '', origin: 'http://127.0.0.1:8765', reload() { ctx.reloaded++; } },
    fetch: async (url, init) => {
      calls.push({ url, init });
      if (opts.fail) return { ok: false, status: 500, json: async () => ({}) };
      if (url.startsWith('/api/files?')) {
        const q = new URLSearchParams(url.split('?')[1]);
        const o = +q.get('offset'), l = +q.get('limit');
        return { ok: true, status: 200, json: async () => ({ files: files.slice(o, o + l), total: files.length }) };
      }
      if (url === '/api/files/link') {
        const id = JSON.parse(init.body).id;
        return { ok: true, status: 200, json: async () => ({ url: opts.badLink ? 'http://evil/' : '/api/files/stream?id=' + id + '&exp=1800000000&sig=' + SIG }) };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    },
    JSON, Array, Error, URLSearchParams,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  return ctx;
}
const run = (ctx, file) => vm.runInContext(src(file), ctx);
const settle = () => new Promise((r) => setTimeout(r, 20));

(async () => {
  const name = 'Live "set" </script>   é.mp4';
  // play: found on the second page (newest first; another root and another folder with the same name are skipped)
  {
    const files = [];
    for (let i = 0; i < 120; i++) files.push({ id: String(i).padStart(32, '0').replace(/[^0-9a-f]/g, '0'), name: 'f' + i + '.mp4', folder: '', place: 'internal' });
    files.push({ id: 'f'.repeat(32), name, folder: 'Music/Live', place: 'usb0' });
    files.push({ id: 'e'.repeat(32), name, folder: 'Music', place: 'internal' });
    files.push({ id: ID, name, folder: 'Music/Live', place: 'internal' });
    const p = page(files);
    check(run(p, 'dl_play.js') === 'started', 'play: returns started');
    check(run(p, 'dl_play.js') === 'busy', 'play: a second run while busy');
    await settle();
    check(p.location.hash === '#id=' + ID, 'play: hash set to the right id, got ' + p.location.hash);
    check(p.reloaded === 1, 'play: reloaded once');
    check(p.calls.length === 2 && p.calls[1].url.includes('offset=100'), 'play: two listing pages');
    check(p.calls.every((c) => c.init.headers['X-Omni-Token'] === 'TOKEN' && c.init.credentials === 'same-origin'), 'play: token header, same origin');
    check(JSON.parse(run(p, 'dl_poll.js')).state === 'ok', 'play: state ok');
    check(p.document.title === name, 'play: title is the file name');
  }
  // play: not in the library
  {
    const p = page([{ id: ID, name: 'other.mp4', folder: '', place: 'internal' }]);
    run(p, 'dl_play.js');
    await settle();
    check(p.reloaded === 0 && p.location.hash === '', 'gone: no reload');
    check(JSON.parse(run(p, 'dl_poll.js')).state === 'gone', 'gone: state');
    check(/no longer in the Downloads library/.test(p.els.message.textContent), 'gone: message');
  }
  // the worker refuses
  {
    const p = page([], { fail: true });
    run(p, 'dl_play.js');
    await settle();
    check(JSON.parse(run(p, 'dl_poll.js')).state === 'error', 'error: state');
  }
  // image: a signed link comes back, no reload
  {
    const p = page([{ id: ID, name: 'cat.jpg', folder: '', place: 'internal' }]);
    check(JSON.parse(run(p, 'dl_poll.js')).state === 'none', 'image: none before');
    run(p, 'dl_image.js');
    await settle();
    const st = JSON.parse(run(p, 'dl_poll.js'));
    check(st.state === 'ok' && st.src === 'http://127.0.0.1:8765/api/files/stream?id=' + ID + '&exp=1800000000&sig=' + SIG, 'image: link ' + st.src);
    check(p.reloaded === 0, 'image: no reload');
    const post = p.calls.find((c) => c.url === '/api/files/link');
    check(post && post.init.method === 'POST' && JSON.parse(post.init.body).id === ID, 'image: link asked for the id');
    check(p.els.message.textContent === '', 'image: message cleared');
  }
  // image: a link that isn't the stream route is refused
  {
    const p = page([{ id: ID, name: 'cat.jpg', folder: '', place: 'internal' }], { badLink: true });
    run(p, 'dl_image.js');
    await settle();
    check(JSON.parse(run(p, 'dl_poll.js')).state === 'error', 'bad link: error');
  }
  console.log((fails ? 'FAIL' : 'ok') + ': ' + checks + ' checks, ' + fails + ' failed');
  process.exit(fails ? 1 : 0);
})();
