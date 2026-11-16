// OMNI_TEXT_SELECT_V1: node tests for the page scripts.
//   node test_text_select_js.cjs <dir> <tree>/engine/entry/OmniContextMenu.h <tree>/engine/entry/OmniBrowser.cpp
// <dir>: the scripts written by `test_text_select --emit <dir>` (OmniTextSelect.h's script(op, x, y)), run on mock DOMs;
// then the patched hold-Cross hit test ("tx") and L2 + Square probe, assembled as the shell does it.
'use strict';
const fs = require('fs');
const path = require('path');
const [dir, ctxFile, browserFile] = process.argv.slice(2);
let fails = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };
const script = (n) => fs.readFileSync(path.join(dir, n), 'utf8');
for (const n of ['s.js', 'f.js', 'b.js', 'u.js', 'd.js', 'c.js', 'odd.js']) {
  try { new Function('return ' + script(n)); check(true, n); } catch (e) { check(false, n + ' syntax: ' + e.message); }
}

// --- a mock page: one text node in a <p>, a selection on it -------------------------------------------------------
function page(text, o = {}) {
  const node = { nodeType: 3, data: text };
  const sel = {
    node: null, a: 0, f: 0, calls: [],
    get rangeCount() { return this.node ? 1 : 0; },
    get isCollapsed() { return this.a === this.f; },
    get focusNode() { return this.node; }, get focusOffset() { return this.f; },
    setBaseAndExtent(n, a, n2, f) { this.node = n; this.a = a; this.f = f; },
    removeAllRanges() { this.node = null; this.a = this.f = 0; },
    modify(alter, dir, unit) {
      this.calls.push([alter, dir, unit].join(' '));
      const t = this.node.data;
      if (unit === 'line') { this.f = dir === 'forward' ? t.length : 0; return; }
      if (dir === 'forward') { let i = this.f; while (i < t.length && /\s/.test(t[i])) i++; while (i < t.length && !/\s/.test(t[i])) i++; this.f = i; }
      else { let i = this.f; while (i > 0 && /\s/.test(t[i - 1])) i--; while (i > 0 && !/\s/.test(t[i - 1])) i--; this.f = i; }
    },
    toString() { return this.node ? this.node.data.slice(Math.min(this.a, this.f), Math.max(this.a, this.f)) : ''; },
  };
  const rect0 = { left: 90, right: 140, top: 40, bottom: 60, width: 50, height: 20 };
  const doc = {
    elementFromPoint: () => { if (o.throws) throw new Error('boom'); return o.el || { tagName: 'P' }; },
    caretRangeFromPoint: () => (o.noCaret ? null : { startContainer: o.caretNode || node, startOffset: o.offset || 0 }),
    createRange: () => ({ setStart() {}, setEnd() {}, getBoundingClientRect: () => o.rect || rect0 }),
  };
  const frames = o.frames || [];
  const win = { document: doc, frames, innerHeight: 720, scrolled: 0, getSelection: () => sel, scrollBy(x, y) { this.scrolled += y; } };
  doc.defaultView = win;
  return { win, doc, sel, node, o };
}
function run(js, p, intl = Intl) {
  return JSON.parse(new Function('window', 'document', 'Intl', 'return ' + js)(p.win, p.doc, intl));
}

// start: the word under the pointer
let p = page('Hello brave new world', { offset: 8 });
let r = run(script('s.js'), p);
check(r.ok === 1 && r.t === 'brave' && r.n === 5, 'start word: ' + JSON.stringify(r));
check(p.sel.a === 6 && p.sel.f === 11, 'anchor at the word start, focus at its end');
p = page('Hello brave new world', { offset: 11 });                    // just after the word
check(run(script('s.js'), p).t === 'brave', 'end of word');
p = page('Hello brave new world', { offset: 0 });
check(run(script('s.js'), p).t === 'Hello', 'first word');
p = page('Hello   world', { offset: 7 });                             // inside a run of spaces
check(JSON.stringify(run(script('s.js'), p)) === '{}', 'spaces: nothing');
p = page('see --> there', { offset: 5 });
check(run(script('s.js'), p).t === '-->', 'punctuation run');
p = page('日本語のテキストです', { offset: 1 });
r = run(script('s.js'), p);
check(r.ok === 1 && r.t.length >= 1 && r.t.length < 10 && '日本語のテキストです'.includes(r.t), 'CJK word (segmenter): ' + JSON.stringify(r));
// without Intl.Segmenter (the regex fallback)
p = page('naïve café crème', { offset: 7 });
check(run(script('s.js'), p, {}).t === 'café', 'fallback: accented word');
p = page('Hello brave new world', { offset: 8 });
check(run(script('s.js'), p, undefined).t === 'brave', 'fallback: no Intl at all');
// not offered: form fields, no caret, far from the text, an element node, a throwing page
check(JSON.stringify(run(script('s.js'), page('abc', { el: { tagName: 'INPUT' } }))) === '{}', 'input');
check(JSON.stringify(run(script('s.js'), page('abc', { noCaret: true }))) === '{}', 'no caret');
check(JSON.stringify(run(script('s.js'), page('abc', { caretNode: { nodeType: 1 } }))) === '{}', 'element caret');
check(JSON.stringify(run(script('s.js'), page('abc def', { offset: 1, rect: { left: 600, right: 640, top: 400, bottom: 420, width: 40, height: 20 } }))) === '{}', 'far away');
check(JSON.stringify(run(script('s.js'), page('abc', { throws: true }))) === '{}', 'page throws');
check(JSON.stringify(run(script('odd.js'), page('abc'))) === '{}', 'NaN / huge coordinates (0, 1e6): far from the text');
// a cross-origin frame (its document throws) is skipped, the selection still found
const xo = {}; Object.defineProperty(xo, 'document', { get() { throw new Error('SecurityError'); } });
p = page('Hello brave new world', { offset: 8, frames: [xo] });
check(run(script('s.js'), p).t === 'brave', 'cross-origin frame');

// extend: word / line, both directions; the moving end kept in view
p = page('Hello brave new world', { offset: 8 });
run(script('s.js'), p);
r = run(script('f.js'), p);
check(r.t === 'brave new' && p.sel.calls[0] === 'extend forward word', 'extend right: ' + JSON.stringify(r) + ' ' + p.sel.calls);
r = run(script('b.js'), p);
check(r.t === 'brave ' && p.sel.calls[1] === 'extend backward word', 'extend left: ' + JSON.stringify(r));
r = run(script('b.js'), p);
check(r.ok === 1 && r.t === '', 'collapsed: still answered');
r = run(script('b.js'), p);
check(r.t === 'Hello ', 'past the anchor: extends the other way: ' + JSON.stringify(r));
r = run(script('d.js'), p);
check(p.sel.calls[4] === 'extend forward line' && r.t === 'brave new world', 'down: line forward: ' + JSON.stringify(r));
run(script('u.js'), p);
check(p.sel.calls[5] === 'extend backward line', 'up: line backward');
p = page('Hello brave new world', { offset: 8 });
run(script('s.js'), p);
p.o.rect = { left: 90, right: 140, top: 700, bottom: 718, width: 50, height: 18 };   // the focus near the bottom
run(script('f.js'), p);
check(p.win.scrolled > 0, 'focus below the view: scrolled down');
// no selection any more: {}
p = page('abc');
check(JSON.stringify(run(script('f.js'), p)) === '{}', 'extend without selection');
// clear
p = page('Hello brave', { offset: 1 });
run(script('s.js'), p);
check(JSON.stringify(run(script('c.js'), p)) === '{"ok":1}' && p.sel.rangeCount === 0, 'clear');
// long selections: 4096 units, a surrogate pair never split, n is the full length
p = page('a'.repeat(4095) + '\u{1F600}' + 'b'.repeat(100), { offset: 0 });
p.sel.setBaseAndExtent(p.node, 0, p.node, p.node.data.length);
r = run(script('f.js'), p);
check(r.t.length === 4095 && r.n === 4095 + 2 + 100, 'cap at 4096 without a split pair: ' + r.t.length + ' ' + r.n);

// --- the patched hit test (omniFxContextScript + the tx line), assembled as omniFxContextQuery does --------------
const ctx = fs.readFileSync(ctxFile, 'utf8').replace(/\r\n/g, '\n');
let hit = /R"JS\(([\s\S]*?)\)JS"/.exec(ctx)[1];
if (hit.endsWith('()')) hit = hit.slice(0, -2); else if (hit.endsWith('(')) hit = hit.slice(0, -1);
hit = '(function(){var X=100.0,Y=50.0;return ' + hit + '(X,Y);})()';
new Function(hit);
check(hit.includes('r.tx=1'), 'hit test has the text probe');
function probe(stack, caret, rect) {
  const win = { innerWidth: 1280, innerHeight: 720, getComputedStyle: () => ({ backgroundImage: 'none' }) };
  const doc = { defaultView: win, caretRangeFromPoint: () => caret,
    createRange: () => ({ setStart() {}, setEnd() {}, getBoundingClientRect: () => rect || { left: 95, right: 105, top: 40, bottom: 60, width: 10, height: 20 } }) };
  for (const e of stack) { e.ownerDocument = doc; e.getAttribute = e.getAttribute || (() => null); e.closest = e.closest || (() => null);
    e.getBoundingClientRect = e.getBoundingClientRect || (() => ({ left: 0, top: 0, width: 100, height: 20 })); }
  const document = { elementsFromPoint: () => stack, elementFromPoint: () => stack[0] };
  return JSON.parse(new Function('document', 'window', 'return ' + hit)(Object.assign(document, { defaultView: win }), win));
}
const tn = { nodeType: 3, data: 'Some words here', length: 15 };
r = probe([{ tagName: 'P' }, { tagName: 'BODY' }], { startContainer: tn, startOffset: 3 });
check(r.tx === 1 && !r.link, 'text: tx ' + JSON.stringify(r));
r = probe([{ tagName: 'P' }], { startContainer: { nodeType: 3, data: '   \n ' }, startOffset: 1 });
check(!r.tx, 'blank text: no tx');
r = probe([{ tagName: 'P' }], { startContainer: tn, startOffset: 3 }, { left: 700, right: 710, top: 300, bottom: 320, width: 10, height: 20 });
check(!r.tx, 'far text: no tx');
r = probe([{ tagName: 'TEXTAREA' }], { startContainer: tn, startOffset: 3 });
check(!r.tx, 'form field: no tx');
r = probe([{ tagName: 'DIV', isContentEditable: true }], { startContainer: tn, startOffset: 3 });
check(!r.tx, 'editable: no tx');
const link = { tagName: 'A', href: 'https://example.com/', innerText: 'Example' };
r = probe([Object.assign({ tagName: 'SPAN' }, { closest: () => link })], { startContainer: tn, startOffset: 3 });
check(r.link === 'https://example.com/' && !r.tx, 'link: no tx ' + JSON.stringify(r));
r = probe([{ tagName: 'P' }], null);
check(!r.tx, 'no caret: no tx');

// --- L2 + Square's probe (omniL2CopyScript): the old cut was a SyntaxError; the patched assembly runs ------------
const ob = fs.readFileSync(browserFile, 'utf8').replace(/\r\n/g, '\n');
const l2src = /omniL2CopyScript = R"JS\(([\s\S]*?)\)JS"/.exec(ob)[1];
let old = l2src.slice(0, -2) + '(X,Y);})()';
let oldBroken = false;
try { new Function('return (function(){var X=1,Y=2;return ' + old); } catch (e) { oldBroken = true; }
check(oldBroken, 'the old L2 assembly was a SyntaxError');
check(ob.includes('js += "(X,Y);})()";') && !ob.includes('js.replace(js.size() - 2, 2, "(X,Y);})()");'), 'omniL2Copy patched');
let l2 = l2src.endsWith('()') ? l2src.slice(0, -2) : l2src.endsWith('(') ? l2src.slice(0, -1) : l2src;
l2 = '(function(){var X=10.0,Y=20.0;return ' + l2 + '(X,Y);})()';
const l2doc = { activeElement: { tagName: 'BODY' }, elementsFromPoint: () => [{ tagName: 'P', closest: () => null }] };
const l2win = { getSelection: () => 'picked words' };
r = JSON.parse(new Function('document', 'window', 'return ' + l2)(l2doc, l2win));
check(r.sel === 'picked words', 'L2 copy reads the selection: ' + JSON.stringify(r));

console.log(checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
