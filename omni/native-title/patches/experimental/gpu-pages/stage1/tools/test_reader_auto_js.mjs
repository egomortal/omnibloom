// OMNI_READER_AUTO_V1: runs the readability page script written by test_reader_auto.cpp (argv[2]) on fake DOMs.
//   node test_reader_auto_js.mjs script.js
// Checks the answer format and the counts on: a news article, a short <article>, a listing of teasers, a search-ish
// page with nav links only, a page with a playing video, an editor, no body, a throwing DOM, nav / aside paragraphs,
// more than 600 paragraphs, and whitespace-only padding. The C++ test decides on such answers (isArticle / decide).
import fs from 'node:fs';

const script = fs.readFileSync(process.argv[2], 'utf8');
let fails = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };

const SKIP = ['nav', 'aside', 'footer', 'form'];
const ROLE_SKIP = ['navigation', 'complementary'];
function el(tag, opts = {}) {
  const n = { tagName: tag.toUpperCase(), children: [], parent: null, text: opts.text || '', role: opts.role || '',
    paused: opts.paused !== undefined ? opts.paused : true, ended: false, readyState: opts.readyState || 0,
    isContentEditable: !!opts.editable };
  Object.defineProperty(n, 'textContent', { get() { return n.text + n.children.map((c) => c.textContent).join(''); } });
  n.closest = (sel) => {
    for (let a = n; a; a = a.parent) {
      const t = a.tagName.toLowerCase();
      if (SKIP.includes(t) || ROLE_SKIP.includes(a.role)) { check(sel.includes(t) || sel.includes(a.role), 'selector covers ' + t); return a; }
    }
    return null;
  };
  return n;
}
function add(parent, child) { child.parent = parent; parent.children.push(child); return child; }
function all(n, tag, out = []) { for (const c of n.children) { if (c.tagName === tag.toUpperCase()) out.push(c); all(c, tag, out); } return out; }
function doc(body, extra = {}) {
  return { body, designMode: extra.designMode || 'off', getElementsByTagName: (t) => (body ? all(body, t) : []) };
}
function run(d) { return new Function('document', 'return ' + script)(d); }
function parse(a) {
  const m = /^omni-rauto 1 p(\d+) c(\d+) a(\d+) t(\d+) v(\d) e(\d)$/.exec(a);
  return m ? { p: +m[1], c: +m[2], a: +m[3], t: +m[4], v: +m[5], e: +m[6] } : null;
}
const para = (n) => 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore. '.repeat(n);

// 1. a news article: 8 long paragraphs in <article>, a nav with long link text, an aside, a footer paragraph
{
  const body = el('body');
  const nav = add(body, el('nav')); add(nav, el('p', { text: para(2) }));
  const art = add(body, el('article'));
  add(art, el('h1', { text: 'Title' }));
  for (let i = 0; i < 8; i++) add(art, el('p', { text: para(3) }));
  add(art, el('p', { text: 'Short caption.' }));
  const aside = add(body, el('aside')); add(aside, el('p', { text: para(2) }));
  const div = add(body, el('div', { role: 'complementary' })); add(div, el('p', { text: para(2) }));
  const foot = add(body, el('footer')); add(foot, el('p', { text: para(2) }));
  const r = parse(run(doc(body)));
  check(r && r.p === 8, 'article: 8 counted paragraphs (nav/aside/footer/role skipped, short one skipped) ' + JSON.stringify(r));
  check(r && r.c === 8 * para(3).trim().length, 'article: characters of the counted paragraphs');
  check(r && r.a === 1 && r.t > 8 * 300 && r.v === 0 && r.e === 0, 'article: one article, its text, no video, not editable');
}
// 2. listing: 12 <article> teasers with one long paragraph each
{
  const body = el('body');
  for (let i = 0; i < 12; i++) { const a = add(body, el('article')); add(a, el('p', { text: para(1) })); }
  const r = parse(run(doc(body)));
  check(r && r.a === 12 && r.p === 12, 'listing: 12 articles counted ' + JSON.stringify(r));
}
// 3. a page of links / short texts only
{
  const body = el('body');
  for (let i = 0; i < 50; i++) add(body, el('p', { text: 'Result ' + i + ' - a short line' }));
  const r = parse(run(doc(body)));
  check(r && r.p === 0 && r.c === 0 && r.a === 0, 'short lines: nothing counted');
}
// 4. a playing video (paused=false, readyState 4) next to long text; a paused one alone does not count
{
  const body = el('body');
  add(body, el('video', { paused: false, readyState: 4 }));
  for (let i = 0; i < 6; i++) add(body, el('p', { text: para(3) }));
  check(parse(run(doc(body))).v === 1, 'video playing: v1');
  const body2 = el('body'); add(body2, el('video', { paused: true, readyState: 4 })); add(body2, el('video', { paused: false, readyState: 1 }));
  check(parse(run(doc(body2))).v === 0, 'paused / not ready video: v0');
}
// 5. editors
{
  const body = el('body', { editable: true });
  check(parse(run(doc(body))).e === 1, 'contentEditable body: e1');
  check(parse(run(doc(el('body'), { designMode: 'on' }))).e === 1, 'designMode on: e1');
}
// 6. no body, a throwing DOM
check(run(doc(null)) === 'omni-rauto 0', 'no body: omni-rauto 0');
check(run({ body: el('body'), getElementsByTagName() { throw new Error('x'); } }) === 'omni-rauto 0', 'throwing DOM: omni-rauto 0');
// 7. whitespace padding: a paragraph of 200 spaces + 20 letters does not count; caps (600 paragraphs, 4000 chars each)
{
  const body = el('body');
  add(body, el('p', { text: ' '.repeat(200) + 'twenty letters here.' }));
  check(parse(run(doc(body))).p === 0, 'whitespace-padded short paragraph: not counted');
  const big = el('body');
  for (let i = 0; i < 700; i++) add(big, el('p', { text: para(60) }));
  const r = parse(run(doc(big)));
  check(r && r.p === 600 && r.c === 600 * 4000, 'caps: 600 paragraphs, 4000 characters each ' + JSON.stringify(r));
}
// 8. no Element.closest (old engines): still counts
{
  const body = el('body');
  for (let i = 0; i < 5; i++) { const p = add(body, el('p', { text: para(5) })); p.closest = undefined; }
  check(parse(run(doc(body))).p === 5, 'without closest: counted');
}
// 9. one evaluation: the script returns a string right away (no Promise, no timers)
check(typeof run(doc(el('body'))) === 'string', 'synchronous string answer');

console.log((fails ? 'FAILED' : 'OK') + ': ' + checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
