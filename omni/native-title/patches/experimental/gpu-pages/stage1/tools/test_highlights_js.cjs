// OMNI_HIGHLIGHTS_V1: node test of the page script (OmniHighlights::kScript) on a small fake DOM.
//   ./t --emit <dir>   (tools/test_highlights.cpp) then   node test_highlights_js.cjs <dir>
// <dir>/kscript.js is "(" + kScript + ")"; call_*.js are whole calls built by the C++ side (JSON arguments).
'use strict';
const fs = require('fs');
const path = require('path');
const dir = process.argv[2];
if (!dir) { console.error('usage: node test_highlights_js.cjs <emit dir>'); process.exit(2); }
const KS = fs.readFileSync(path.join(dir, 'kscript.js'), 'utf8');
const TRICKY = fs.readFileSync(path.join(dir, 'tricky.txt'), 'utf8');
let fails = 0, checks = 0;
function ok(c, what) { ++checks; if (!c) { ++fails; console.error('FAIL ' + what); } }
function eq(a, b, what) { ++checks; if (JSON.stringify(a) !== JSON.stringify(b)) { ++fails; console.error('FAIL ' + what + '\n  got  ' + JSON.stringify(a) + '\n  want ' + JSON.stringify(b)); } }

// --- the fake DOM -------------------------------------------------------------------------------------------------
const XH = 'http://www.w3.org/1999/xhtml', SVG = 'http://www.w3.org/2000/svg';
class N0 {
    constructor(t) { this.nodeType = t; this.parentNode = null; this.childNodes = []; }
    get firstChild() { return this.childNodes[0] || null; }
    get nextSibling() { const p = this.parentNode; if (!p) return null; return p.childNodes[p.childNodes.indexOf(this) + 1] || null; }
    appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.childNodes.push(c); return c; }
    insertBefore(c, ref) {
        if (!ref) return this.appendChild(c);
        if (c.parentNode) c.parentNode.removeChild(c);
        const i = this.childNodes.indexOf(ref); if (i < 0) throw new Error('insertBefore: not a child');
        c.parentNode = this; this.childNodes.splice(i, 0, c); return c;
    }
    removeChild(c) { const i = this.childNodes.indexOf(c); if (i < 0) throw new Error('removeChild: not a child'); this.childNodes.splice(i, 1); c.parentNode = null; return c; }
    normalize() {
        for (let i = 0; i < this.childNodes.length;) {
            const c = this.childNodes[i];
            if (c.nodeType === 3) {
                if (c.data === '') { this.removeChild(c); continue; }
                const n = this.childNodes[i + 1];
                if (n && n.nodeType === 3) { c.data += n.data; this.removeChild(n); continue; }
            } else c.normalize();
            ++i;
        }
    }
    get textContent() { return this.nodeType === 3 ? this.data : this.childNodes.map(c => c.textContent).join(''); }
}
class Text extends N0 {
    constructor(d) { super(3); this.data = d; }
    get length() { return this.data.length; }
    splitText(o) {
        if (o < 0 || o > this.data.length) throw new Error('splitText: offset');
        const n = new Text(this.data.slice(o)); this.data = this.data.slice(0, o);
        if (this.parentNode) this.parentNode.insertBefore(n, this.nextSibling);
        return n;
    }
}
class El extends N0 {
    constructor(tag, ns) {
        super(1); this.tagName = ns === SVG ? tag : tag.toUpperCase(); this.namespaceURI = ns || XH; this.attrs = {}; this.scrolled = 0;
        const props = {}; this.style = { props, setProperty(k, v, p) { props[k] = [v, p]; } };
    }
    get id() { return this.attrs.id || ''; }
    get className() { return this.attrs.class || ''; }
    set className(v) { this.attrs.class = String(v); }
    get href() { return this.attrs.href; }
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
    setAttribute(k, v) { this.attrs[k] = String(v); }
    all() { const o = []; const walk = n => { for (const c of n.childNodes) if (c.nodeType === 1) { o.push(c); walk(c); } }; walk(this); return o; }
    querySelectorAll(sel) {
        if (sel === 'mark.omni-hl') return this.all().filter(e => e.tagName === 'MARK' && e.className.split(' ').includes('omni-hl'));
        if (sel === 'a[href]') return this.all().filter(e => e.tagName === 'A' && 'href' in e.attrs);
        throw new Error('selector not supported: ' + sel);
    }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
    scrollIntoView() { this.scrolled++; }
}
function order(root) { const o = []; const walk = n => { o.push(n); for (const c of n.childNodes) walk(c); }; walk(root); return o; }
function lastDesc(n) { while (n.childNodes.length) n = n.childNodes[n.childNodes.length - 1]; return n; }
class Doc {
    constructor() { this.documentElement = new El('html'); this.body = this.documentElement.appendChild(new El('body')); this.title = ''; }
    createElement(t) { return new El(t); }
    getElementById(id) { return this.documentElement.all().find(e => e.id === id) || null; }
    querySelectorAll(sel) { return this.documentElement.querySelectorAll(sel); }
    createTreeWalker(root, what, filter) {
        const f = typeof filter === 'function' ? filter : filter && filter.acceptNode.bind(filter);
        const verdict = n => { const shown = (n.nodeType === 1 && (what & 1)) || (n.nodeType === 3 && (what & 4)); return shown ? (f ? f(n) : 1) : 3; };
        let cur = root;
        return {
            nextNode() {
                let n = cur, skipKids = false;
                for (;;) {
                    let next = null;
                    if (!skipKids && n.childNodes.length) next = n.childNodes[0];
                    else for (let m = n; m && m !== root; m = m.parentNode) { const s = m.nextSibling; if (s) { next = s; break; } }
                    if (!next) return null;
                    n = next;
                    const v = verdict(n);
                    if (v === 1) { cur = n; return n; }
                    skipKids = v === 2;
                }
            },
        };
    }
    key(c, o) {
        const ord = order(this.documentElement);
        if (c.nodeType === 3) return [ord.indexOf(c), o];
        if (o < c.childNodes.length) return [ord.indexOf(c.childNodes[o]), -1];
        return [ord.indexOf(lastDesc(c)), Infinity];
    }
}
const cmp = (a, b) => a[0] - b[0] || (a[1] === b[1] ? 0 : a[1] < b[1] ? -1 : 1);
class Range0 {
    constructor(doc, sc, so, ec, eo) { Object.assign(this, { doc, startContainer: sc, startOffset: so, endContainer: ec, endOffset: eo }); }
    intersectsNode(n) {
        const ord = order(this.doc.documentElement), i = ord.indexOf(n);
        return cmp([i, -1], this.doc.key(this.endContainer, this.endOffset)) < 0 && cmp([ord.indexOf(lastDesc(n)), Infinity], this.doc.key(this.startContainer, this.startOffset)) > 0;
    }
}
function env(href) {
    const doc = new Doc();
    const timers = [];
    const sel = { range: null, get rangeCount() { return this.range ? 1 : 0; },
        get isCollapsed() { const r = this.range; return !r || (r.startContainer === r.endContainer && r.startOffset === r.endOffset); },
        getRangeAt() { return this.range; }, removeAllRanges() { this.range = null; } };
    const win = { frames: [], getSelection: () => sel, setTimeout(fn) { timers.push(fn); return timers.length; } };
    const loc = { href: href || 'https://example.com/page' };
    const fn = new Function('document', 'window', 'location', 'return ' + KS)(doc, win, loc);
    const run = (op, a) => JSON.parse(fn(op, a));
    const runCall = file => JSON.parse(new Function('document', 'window', 'location', 'return ' + fs.readFileSync(path.join(dir, file), 'utf8'))(doc, win, loc));
    const select = (sc, so, ec, eo) => { sel.range = new Range0(doc, sc, so, ec, eo); };
    return { doc, win, sel, timers, loc, run, runCall, select };
}
// Builds children from a tiny spec: strings are text, [tag, attrs, ...children] elements.
function build(parent, ...kids) {
    for (const k of kids) {
        if (typeof k === 'string') parent.appendChild(new Text(k));
        else { const [tag, attrs, ...rest] = k; const e = new El(tag, attrs && attrs.ns); for (const a in attrs || {}) if (a !== 'ns') e.setAttribute(a, attrs[a]); parent.appendChild(e); build(e, ...rest); }
    }
    return parent;
}
const marks = (doc, id) => doc.querySelectorAll('mark.omni-hl').filter(m => id === undefined || m.getAttribute('data-omni-hl') === String(id));
const markText = (doc, id) => marks(doc, id).map(m => m.textContent).join('|');

// --- 1. simple apply across elements, styling, idempotent ---------------------------------------------------------
{
    const E = env();
    build(E.doc.body, ['p', null, 'Hello ', ['b', null, 'brave'], ' new world.']);
    const r = E.run('a', { items: [{ i: 1, p: 'Hello', e: 'brave new', s: 'world.' }], f: 0 });
    eq(r, { ok: 1, f: [1], m: [], fx: 0 }, 'apply: answer');
    eq(markText(E.doc, 1), 'brave| new', 'apply: wrapped across <b> and the text after');
    eq(E.doc.body.textContent, 'Hello brave new world.', 'apply: text unchanged');
    const m0 = marks(E.doc, 1)[0];
    eq(m0.style.props['background-color'], ['#ffe45c', 'important'], 'apply: yellow, important');
    eq(m0.style.props.color, ['#16181d', 'important'], 'apply: dark text');
    E.run('a', { items: [{ i: 1, p: 'Hello', e: 'brave new', s: 'world.' }], f: 0 });
    eq(marks(E.doc, 1).length, 2, 'apply twice: no second wrap');
    eq(E.timers.length, 0, 'apply: no retry when everything was found');
}
// --- 2. duplicates: context decides ------------------------------------------------------------------------------
{
    const E = env();
    build(E.doc.body, ['p', null, 'the cat sat. '], ['p', null, 'the cat ran. the dog sat.']);
    E.run('a', { items: [{ i: 2, p: 'sat. ', e: 'the cat', s: ' ran.' }, { i: 3, p: 'cat ran. ', e: 'the', s: ' dog' }] });
    const m2 = marks(E.doc, 2), m3 = marks(E.doc, 3);
    ok(m2.length === 1 && m2[0].parentNode === E.doc.body.childNodes[1], 'duplicates: the second "the cat" (suffix " ran.")');
    ok(m3.length === 1 && m3[0].nextSibling && m3[0].nextSibling.data.startsWith(' dog'), 'duplicates: "the" before "dog"');
    eq(E.doc.body.textContent, 'the cat sat. the cat ran. the dog sat.', 'duplicates: text unchanged');
}
// --- 3. whitespace / block boundaries / zero-width differences are ignored ----------------------------------------
{
    const E = env();
    build(E.doc.body, ['div', null, ['p', null, 'Line one\n     ends'], ['p', null, 'here and​ there']]);
    const r = E.run('a', { items: [{ i: 4, p: '', e: 'one ends here and there', s: '' }] });
    eq(r.f, [4], 'whitespace: found');
    eq(markText(E.doc, 4), 'one\n     ends|here and​ there', 'whitespace: wrapped per text node');
}
// --- 4. excluded containers, the saved-copy banner, SVG parents -----------------------------------------------------
{
    const E = env();
    build(E.doc.body, ['script', null, 'secret words'], ['style', null, '.secret{}'], ['div', { id: 'omni-saved-banner' }, 'Saved copy ', ['a', { href: 'https://x/' }, 'Open live page']],
        ['svg', { ns: SVG }, ['text', { ns: SVG }, 'vector words']], ['p', null, 'plain words']);
    let r = E.run('a', { items: [{ i: 5, e: 'secret words' }, { i: 6, e: 'Open live page' }] });
    eq(r.m, [5, 6], 'excluded: script text and banner not matched');
    r = E.run('a', { items: [{ i: 7, e: 'vector words' }, { i: 8, e: 'plain words' }] });
    eq(marks(E.doc).length, 1, 'svg: matched but not wrapped (non-HTML parent)');
    eq(markText(E.doc, 8), 'plain words', 'svg: the HTML one wrapped');
}
// --- 5. missing -> one retry 2 s later; focus scroll -----------------------------------------------------------------
{
    const E = env();
    build(E.doc.body, ['p', null, 'early text']);
    const r = E.run('a', { items: [{ i: 9, e: 'late text' }, { i: 10, e: 'early text' }], f: 9 });
    eq(r, { ok: 1, f: [10], m: [9], fx: 0 }, 'retry: first answer');
    eq(E.timers.length, 1, 'retry: one timer');
    build(E.doc.body, ['p', null, 'late text']);
    E.timers.shift()();
    eq(markText(E.doc, 9), 'late text', 'retry: found later');
    eq(marks(E.doc, 9)[0].scrolled, 1, 'retry: scrolled to the focus');
    eq(E.timers.length, 0, 'retry: only once');
    const r2 = E.run('a', { items: [{ i: 10, e: 'early text' }], f: 10 });
    eq(r2.fx, 1, 'focus: present mark scrolled');
    eq(marks(E.doc, 10)[0].scrolled, 1, 'focus: scrollIntoView called');
}
// --- 6. create from a selection, then remove -------------------------------------------------------------------------
{
    const E = env();
    E.doc.title = 'A "page"';
    build(E.doc.body, ['h1', null, 'Title words'], ['p', null, 'Intro sentence. The quick ', ['i', null, 'brown'], ' fox jumps over the lazy dog. Outro.']);
    const p = E.doc.body.childNodes[1], t0 = p.childNodes[0], t2 = p.childNodes[2];
    E.select(t0, 16, t2, 4);                         // "The quick brown fox"
    const c = E.run('c', { i: 42 });
    eq(c.e, 'The quick brown fox', 'create: exact');
    ok(/sentence\. $/.test(c.p) && c.p.length <= 64, 'create: prefix context ' + JSON.stringify(c.p));
    ok(/^ jumps over/.test(c.s), 'create: suffix context ' + JSON.stringify(c.s));
    eq([c.t, c.u, c.cut], ['A "page"', '', 0], 'create: title, no live address, not cut');
    eq(markText(E.doc, 42), 'The quick |brown| fox', 'create: wrapped');
    ok(E.sel.range === null, 'create: selection cleared');
    eq(E.doc.body.textContent, 'Title wordsIntro sentence. The quick brown fox jumps over the lazy dog. Outro.', 'create: text unchanged');
    // the stored quote finds the same place on a fresh copy of the page that has the phrase twice
    const F = env();
    build(F.doc.body, ['p', null, 'The quick brown fox is here too. '], ['p', null, 'Intro sentence. The quick brown fox jumps over the lazy dog.']);
    F.run('a', { items: [{ i: 42, p: c.p, e: c.e, s: c.s }] });
    ok(marks(F.doc, 42).length === 1 && marks(F.doc, 42)[0].parentNode === F.doc.body.childNodes[1], 'create -> apply: the right occurrence');
    // remove
    const rm = E.run('r', { ids: [42, 99] });
    eq(rm, { ok: 1, n: 3 }, 'remove: three marks');
    eq(marks(E.doc).length, 0, 'remove: none left');
    eq(p.childNodes.length, 3, 'remove: text nodes merged back');
    eq(E.doc.body.textContent, 'Title wordsIntro sentence. The quick brown fox jumps over the lazy dog. Outro.', 'remove: text unchanged');
}
// --- 7. create: element boundaries, nothing selected, frames, long selections, saved copy --------------------------------
{
    const E = env();
    build(E.doc.body, ['p', null, 'alpha'], ['p', null, 'beta gamma']);
    E.select(E.doc.body, 0, E.doc.body.childNodes[1].childNodes[0], 4);   // element start .. "beta"
    const c = E.run('c', { i: 5 });
    eq(c.e, 'alphabeta', 'create: element boundary start (block boundaries have no space in the text model)');
    eq(markText(E.doc, 5), 'alpha|beta', 'create: wrapped');
    eq(E.run('c', { i: 6 }), { err: 'none' }, 'create: nothing selected');
    E.win.frames = [{ getSelection: () => ({ rangeCount: 1, isCollapsed: false }) }];
    eq(E.run('c', { i: 6 }), { err: 'frame' }, 'create: selection in a frame');
    E.win.frames = [];
    const t = E.doc.body.childNodes[1].lastChild;
    E.select(t, 1, t, 1);
    eq(E.run('c', { i: 6 }), { err: 'none' }, 'create: collapsed');

    const L = env('about:blank');
    build(L.doc.body, ['div', { id: 'omni-saved-banner' }, 'Saved copy · ', ['a', { href: 'https://live.example/a?b=1' }, 'Open live page']]);
    const big = '漢'.repeat(700) + ' tail';                 // 700 x 3 bytes > 1600
    build(L.doc.body, ['p', null, big]);
    eq(L.run('l', {}), { ok: 1, u: 'https://live.example/a?b=1' }, 'live: the banner link');
    const bt = L.doc.body.childNodes[1].childNodes[0];
    L.select(bt, 0, bt, bt.data.length);
    const lc = L.run('c', { i: 7 });
    eq([lc.cut, lc.u], [1, 'https://live.example/a?b=1'], 'create: cut and live address');
    eq(lc.e, '漢'.repeat(533), 'create: cut at 1,600 bytes (533 x 3)');
    eq(markText(L.doc, 7), '漢'.repeat(533), 'create: only the kept part highlighted');
    eq(env('https://example.com/').run('l', {}), { ok: 1, u: '' }, 'live: not a saved copy');
    // surrogate pairs at the context edges
    const S = env();
    build(S.doc.body, ['p', null, '😀'.repeat(40) + 'MID' + '😀'.repeat(40)]);
    const st = S.doc.body.childNodes[0].childNodes[0];
    S.select(st, 80, st, 83);
    const sc = S.run('c', { i: 8 });
    ok(sc.e === 'MID' && !/^[\udc00-\udfff]/.test(sc.p) && !/[\ud800-\udbff]$/.test(sc.s), 'create: no split pair in the context');
}
// --- 8. overlapping highlights in one node; broken input -----------------------------------------------------------
{
    const E = env();
    build(E.doc.body, ['p', null, 'one two three four']);
    E.run('a', { items: [{ i: 1, e: 'two three' }, { i: 2, e: 'three four' }, { i: 3, e: 'one' }] });
    eq([markText(E.doc, 1), markText(E.doc, 2), markText(E.doc, 3)], ['', 'three four', 'one'], 'overlap in one node: the piece starting later wins, the other is skipped');
    eq(E.run('a', { items: [null, { i: 4 }, { i: 5, e: '   ' }] }).m, [5], 'apply: bad items ignored, blank one missing');
    eq(E.run('zz', {}), {}, 'unknown op');
    eq(E.run('a', null), { ok: 1, f: [], m: [], fx: 0 }, 'no argument');
}
// --- 9. the C++-built calls: tricky text (quotes, backslashes, </script>, U+2028, emoji) through JSON ----------------
{
    const E = env();
    build(E.doc.body, ['p', null, 'Intro: ' + TRICKY + ' The end.']);
    const r = E.runCall('call_apply.js');
    eq(r, { ok: 1, f: [41], m: [], fx: 1 }, 'C++ apply call: found and focused');
    eq(markText(E.doc, 41), TRICKY, 'C++ apply call: exact tricky text wrapped');
    const t = E.doc.body.childNodes[0].childNodes[0];
    E.select(t, 0, t, 6);
    const c = E.runCall('call_create.js');
    eq(c.e, 'Intro:', 'C++ create call');
    eq(E.runCall('call_remove.js'), { ok: 1, n: 2 }, 'C++ remove call');
    eq(E.runCall('call_live.js'), { ok: 1, u: '' }, 'C++ live call');
    eq(E.doc.body.textContent, 'Intro: ' + TRICKY + ' The end.', 'C++ calls: text unchanged');
}
// --- 10. a page that throws: answers "{}" --------------------------------------------------------------------------
{
    const E = env();
    E.doc.querySelectorAll = () => { throw new Error('hostile'); };
    eq(E.run('a', { items: [{ i: 1, e: 'x' }] }), {}, 'hostile page: "{}"');
}
console.log(checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
