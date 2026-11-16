// OMNI_DOWNLOAD_ALL_V1: the "Download all..." page script (OmniDownloadAll::script(), written by test_download_all.cpp
// when given a path), run on mock DOMs.
//   node test_download_all_js.cjs <script.js>
'use strict';
const fs = require('fs');
const js = fs.readFileSync(process.argv[2], 'utf8');
new Function('return ' + js);   // syntax: one expression

let fails = 0, checks = 0;
const check = (c, what, got) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what + (got === undefined ? '' : ' :: ' + JSON.stringify(got))); } };

function a(href, attrs = {}) {
  return { tagName: 'A', href, hasAttribute: k => k in attrs, getAttribute: k => (k in attrs ? attrs[k] : null) };
}
function img(src, w, h, o = {}) { return Object.assign({ tagName: 'IMG', src, currentSrc: '', naturalWidth: w, naturalHeight: h, width: 0, height: 0 }, o); }
function media(tag, src, parentTag, type) {
  return { tagName: tag, src, currentSrc: '', parentNode: parentTag ? { tagName: parentTag } : null, getAttribute: k => (k === 'type' ? type || null : null) };
}
function run(dom) {
  const document = { links: dom.links || [], images: dom.images || [], querySelectorAll: () => dom.media || [] };
  return new Function('document', 'URL', 'return ' + js)(document, URL);
}
const rows = text => (text ? text.split('\n').map(l => l.split('\t')) : []);

// links: file extensions, download attribute, type=, pages and non-http left out
let r = rows(run({ links: [
  a('https://e.com/doc.pdf'), a('https://e.com/page.html'), a('https://e.com/get?id=1', { download: 'Report\t2026.xlsx' }),
  a('https://e.com/blob', { type: 'application/zip' }), a('https://e.com/x', { type: 'text/html' }), a('javascript:void(0)'),
  a('mailto:x@e.com'), a('https://e.com/doc.pdf#p2'), a('https://e.com/pack.7Z?x=1'), a('https://e.com/' + 'x'.repeat(2100) + '.zip'),
  a('https://e.com/v.mkv'), a('https://e.com/dir.v2/'),
] }));
check(r.length === 5, 'five links kept', r.map(x => x[6]));
check(r.every(x => x.length === 7), 'seven fields per row');
check(r[0][0] === 'a' && r[0][6] === 'https://e.com/doc.pdf' && r[0][3] === '0', 'pdf row', r[0]);
check(r[1][3] === '1' && r[1][4] === 'Report 2026.xlsx', 'download attribute, tab cleaned', r[1]);
check(r[2][5] === 'application/zip', 'type attribute kept', r[2]);
check(r[3][6] === 'https://e.com/pack.7Z?x=1', 'extension ignores case and query', r[3]);
check(!r.some(x => /#p2/.test(x[6])), 'same file with a fragment not repeated');

// images: the longer side >= 200 (natural, else rendered)
r = rows(run({ images: [img('https://e.com/a.png', 640, 480), img('https://e.com/icon.png', 32, 32), img('https://e.com/wide.png', 300, 20),
  img('https://e.com/lazy.png', 0, 0, { width: 250, height: 100 }), img('data:image/png;base64,AAAA', 999, 999),
  img('https://e.com/b.png', 400, 400, { currentSrc: 'https://e.com/b@2x.png' })] }));
check(r.map(x => x[6]).join() === 'https://e.com/a.png,https://e.com/wide.png,https://e.com/lazy.png,https://e.com/b@2x.png', 'image rows', r.map(x => x[6]));
check(r[0][0] === 'img' && r[0][1] === '640' && r[0][2] === '480', 'image size', r[0]);

// media: video / audio / source, blob: left out
r = rows(run({ media: [media('VIDEO', 'https://e.com/v.mp4'), media('VIDEO', 'blob:https://e.com/1'), media('AUDIO', 'https://e.com/s.mp3'),
  media('SOURCE', 'https://e.com/s.ogg', 'AUDIO', 'audio/ogg'), media('SOURCE', 'https://e.com/v.webm', 'VIDEO')] }));
check(r.map(x => x[0] + ' ' + x[6]).join() === 'video https://e.com/v.mp4,audio https://e.com/s.mp3,audio https://e.com/s.ogg,video https://e.com/v.webm', 'media rows', r.map(x => x[0] + ' ' + x[6]));
check(r[2][5] === 'audio/ogg', 'source type', r[2]);

// caps and robustness
const many = Array.from({ length: 900 }, (_, i) => a('https://e.com/f' + i + '.pdf'));
check(rows(run({ links: many })).length === 600, 'at most 600 rows');
check(run({ links: [{ tagName: 'A', get href() { throw new Error('x'); } }] }) === '', 'an error answers ""');
check(run({}) === '', 'empty page');

console.log((fails ? 'FAILED' : 'ok') + ': ' + checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
