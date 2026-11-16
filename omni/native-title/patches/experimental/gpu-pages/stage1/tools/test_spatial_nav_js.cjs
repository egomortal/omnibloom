// OMNI_SPATIAL_NAV_V1: runs the page script written by test_spatial_nav.cpp on fake DOM layouts.
//   node test_spatial_nav_js.cjs core.js samples.js
// core.js is the function expression (OmniSpatialNav::core()); samples.js holds one built call each, separated by "//@@" lines (move / act /
// hide). Checks: the W3C-style scoring (aligned beats near-diagonal, rows win left / right), skipping hidden / disabled /
// tiny / huge / covered / nested candidates, reach and scrolling into view, "none" at the end, the pointer start, the
// ring overlay (colour, place, follows scrolling, removed on hide), focus without scrolling (not for text boxes), and
// Cross: a hit-tested point, or the script's own click / focus when the element is covered.
'use strict';
const fs = require('fs');
const vm = require('vm');

const core = fs.readFileSync(process.argv[2], 'utf8');
const samples = fs.readFileSync(process.argv[3], 'utf8').split('\n//@@\n').filter((x) => x.trim());
let fails = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };

// --- a tiny selector matcher for the script's candidate list (tag, [a], [a=v], [a="v"], :not([...])) ---------------
function attrTest(src) {
  const m = /^\[([\w-]+)(?:=(?:"([^"]*)"|([^\]]*)))?\]$/.exec(src);
  if (!m) throw new Error('selector part not understood: ' + src);
  const name = m[1], value = m[2] !== undefined ? m[2] : m[3];
  return (e) => e.hasAttribute(name) && (value === undefined || e.getAttribute(name) === value);
}
function compile(selector) {
  return selector.split(',').map((part) => {
    const m = /^([a-z]+)?((?:\[[^\]]+\])*)((?::not\(\[[^\]]+\]\))*)$/.exec(part.trim());
    if (!m) throw new Error('selector not understood: ' + part);
    const tag = m[1], has = (m[2].match(/\[[^\]]+\]/g) || []).map(attrTest);
    const nots = (m[3].match(/\[[^\]]+\]/g) || []).map(attrTest);
    return (e) => (!tag || e.tagName.toLowerCase() === tag) && has.every((t) => t(e)) && !nots.some((t) => t(e));
  });
}
const compiled = new Map();
function matches(e, selector) {
  if (!compiled.has(selector)) compiled.set(selector, compile(selector));
  return compiled.get(selector).some((t) => t(e));
}

// --- fake DOM ---------------------------------------------------------------------------------------------------------
class Rect {
  constructor(x, y, w, h) { this.left = x; this.top = y; this.width = w; this.height = h; this.right = x + w; this.bottom = y + h; this.x = x; this.y = y; }
}
class El {
  constructor(doc, tag, attrs, opts) {
    this.doc = doc; this.tagName = tag.toUpperCase(); this.attrs = Object.assign({}, attrs || {}); this.opts = opts || {};
    this.children = []; this.parentElement = null; this.parentNode = null; this.style = { cssText: '' };
    this.clicks = 0; this.focusCalls = [];
  }
  getAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n) ? String(this.attrs[n]) : null; }
  hasAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n); }
  setAttribute(n, v) { this.attrs[n] = String(v); }
  get disabled() { return !!this.opts.disabled; }
  get isContentEditable() { return this.attrs.contenteditable === '' || this.attrs.contenteditable === 'true'; }
  get isConnected() { let e = this; while (e.parentElement) e = e.parentElement; return e === this.doc.documentElement; }
  appendChild(c) { if (c.parentElement) c.parentElement.removeChild(c); c.parentElement = this; c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parentElement = null; c.parentNode = null; return c; }
  contains(o) { for (let e = o; e; e = e.parentElement) if (e === this) return true; return false; }
  matches(s) { return matches(this, s); }
  closest(s) { for (let e = this; e; e = e.parentElement) if (e.tagName !== 'HTML' && matches(e, s)) return e; return null; }
  rects() { return this.opts.rects || (this.opts.r ? [this.opts.r] : []); }
  view(r) { const sx = this.opts.fixed ? 0 : this.doc.scrollX, sy = this.opts.fixed ? 0 : this.doc.scrollY; return new Rect(r[0] - sx, r[1] - sy, r[2], r[3]); }
  getClientRects() { return this.rects().map((r) => this.view(r)); }
  getBoundingClientRect() {
    const rs = this.rects();
    if (!rs.length) return new Rect(0, 0, 0, 0);
    const x0 = Math.min(...rs.map((r) => r[0])), y0 = Math.min(...rs.map((r) => r[1]));
    const x1 = Math.max(...rs.map((r) => r[0] + r[2])), y1 = Math.max(...rs.map((r) => r[1] + r[3]));
    return this.view([x0, y0, x1 - x0, y1 - y0]);
  }
  focus(o) { this.focusCalls.push(o || null); if (this.opts.focusable !== false) this.doc.activeElement = this; }
  blur() { this.blurs = (this.blurs || 0) + 1; if (this.doc.activeElement === this) this.doc.activeElement = this.doc.body; }
  click() { this.clicks++; }
  scrollIntoView(o) {
    this.doc.intoView.push(o);
    const b = this.getBoundingClientRect(), w = this.doc.win;
    if (b.top < 0) this.doc.scrollY += b.top; else if (b.bottom > w.innerHeight) this.doc.scrollY += b.bottom - w.innerHeight;
    if (b.left < 0) this.doc.scrollX += b.left; else if (b.right > w.innerWidth) this.doc.scrollX += b.right - w.innerWidth;
  }
}
function makePage(VW, VH, items) {
  const doc = { scrollX: 0, scrollY: 0, intoView: [] };
  doc.documentElement = new El(doc, 'html');
  doc.body = doc.documentElement.appendChild(new El(doc, 'body'));
  doc.activeElement = doc.body;
  doc.createElement = (t) => new El(doc, t);
  const all = () => { const out = []; const walk = (e) => { for (const c of e.children) { out.push(c); walk(c); } }; walk(doc.documentElement); return out; };
  doc.querySelectorAll = (s) => all().filter((e) => matches(e, s));
  doc.elementFromPoint = (x, y) => {
    let best = null, bz = -Infinity;
    for (const e of all()) {
      if (e.opts.noHit || /pointer-events:none/.test(e.style.cssText || '')) continue;
      const hit = e.getClientRects().some((r) => x >= r.left && x < r.right && y >= r.top && y < r.bottom);
      const z = e.opts.z || 0;
      if (hit && z >= bz) { best = e; bz = z; }
    }
    return best || doc.body;
  };
  const listeners = [];
  const raf = [];
  const win = {
    document: doc, innerWidth: VW, innerHeight: VH,
    scrollBy(o) { doc.scrollY += o.top || 0; doc.scrollX += o.left || 0; doc.scrolledBy = (doc.scrolledBy || 0) + 1; },
    requestAnimationFrame(cb) { raf.push(cb); return raf.length; },
    cancelAnimationFrame() { raf.length = 0; },
    addEventListener(t, f, c) { listeners.push({ t, f, c }); },
    removeEventListener(t, f, c) { const i = listeners.findIndex((l) => l.t === t && l.f === f && l.c === c); if (i >= 0) listeners.splice(i, 1); },
    getComputedStyle(e) { return { visibility: e.opts.visibility || 'visible' }; },
  };
  win.window = win;
  doc.win = win;
  const ctx = vm.createContext(win);
  const byId = {};
  const add = (parent, it) => {
    const e = parent.appendChild(new El(doc, it.tag || 'a', it.attrs || (it.tag ? {} : { href: '#' }), it));
    if (it.id) byId[it.id] = e;
    for (const k of it.kids || []) add(e, k);
  };
  for (const it of items) add(doc.body, it);
  const run = (M, D, PX, PY, FP, C, H, W) => vm.runInContext(core + '(' + JSON.stringify(M) + ',' + D + ',' + PX + ',' + PY + ',' + FP + ',' +
    JSON.stringify(C || '#70e4d1') + ',' + JSON.stringify(H || '#000000') + ',' + (W || 4) + ')', ctx);
  const move = (D, fp, px, py) => run('m', D, px === undefined ? -1 : px, py === undefined ? -1 : py, fp ? 1 : 0);
  const ring = () => doc.documentElement.children.find((c) => c.tagName === 'DIV' && /z-index:2147483647/.test(c.style.cssText));
  const flush = () => { const q = raf.splice(0); for (const f of q) f(); };
  return { doc, win, ctx, byId, run, move, ring, listeners, flush, runRaw: (js) => vm.runInContext(js, ctx) };
}
const UP = 0, DOWN = 1, LEFT = 2, RIGHT = 3;
const centre = (ans) => { const p = ans.split(','); return [Number(p[1]), Number(p[2])]; };

// --- 1. a 3 x 3 grid of links -----------------------------------------------------------------------------------------
function grid(extra) {
  const items = [];
  for (let j = 0; j < 3; ++j) for (let i = 0; i < 3; ++i) items.push({ id: 'g' + j + i, r: [100 + i * 300, 100 + j * 200, 200, 40] });
  return makePage(1000, 800, items.concat(extra || []));
}
{
  const P = grid();
  let a = P.move(DOWN);
  check(a === 'moved,200.0,120.0', 'grid: first down from the top edge -> top-left (' + a + ')');
  check(P.doc.activeElement === P.byId.g00, 'grid: the link has the focus');
  check(P.byId.g00.focusCalls.length === 1 && P.byId.g00.focusCalls[0] && P.byId.g00.focusCalls[0].preventScroll === true, 'grid: focus without scrolling');
  const g = P.ring();
  check(!!g, 'grid: ring added');
  check(g && g.style.left === '94px' && g.style.top === '94px' && g.style.width === '212px' && g.style.height === '52px', 'grid: ring around the link with 2 px gap');
  check(g && /border:4px solid #70e4d1/.test(g.style.cssText) && /box-shadow:0 0 0 2px #000000,inset 0 0 0 2px #000000/.test(g.style.cssText), 'grid: ring colours');
  check(g && /position:fixed/.test(g.style.cssText) && /pointer-events:none/.test(g.style.cssText), 'grid: fixed overlay, no hits');
  check(g && g.getAttribute('aria-hidden') === 'true', 'grid: ring hidden from accessibility');
  a = P.move(RIGHT); check(a === 'moved,500.0,120.0', 'grid: right -> (0,1) ' + a);
  a = P.move(DOWN); check(a === 'moved,500.0,320.0', 'grid: down -> (1,1) ' + a);
  a = P.move(LEFT); check(a === 'moved,200.0,320.0', 'grid: left -> (1,0) ' + a);
  check(P.byId.g01.blurs >= 1 || P.doc.activeElement === P.byId.g10, 'grid: focus follows');
  a = P.move(UP); check(a === 'moved,200.0,120.0', 'grid: up -> (0,0) ' + a);
  a = P.move(UP); check(a === 'none', 'grid: nothing above -> none');
  a = P.move(LEFT); check(a === 'none', 'grid: nothing left -> none');
  check(P.doc.activeElement === P.byId.g00 && !!P.ring(), 'grid: none keeps the ring');
  // the ring follows scrolling (one frame per burst)
  const scrollL = P.listeners.find((l) => l.t === 'scroll');
  check(!!scrollL && scrollL.c === true, 'grid: capture scroll listener while shown');
  P.doc.scrollY = 30; scrollL.f(); scrollL.f(); P.flush();
  check(P.ring().style.top === '64px', 'grid: ring follows a scroll (' + P.ring().style.top + ')');
  // hide
  a = P.run('h', 0, -1, -1, 0);
  check(a === 'hidden' && !P.ring() && P.listeners.length === 0, 'grid: hide removes the ring and listeners');
  a = P.run('a', 0, -1, -1, 0);
  check(a === 'none', 'grid: Cross with no ring -> none');
}

// --- 2. aligned beats near-diagonal; rows win left / right ------------------------------------------------------------
{
  const P = makePage(1000, 800, [
    { id: 'A', r: [100, 100, 100, 40] },
    { id: 'C', r: [400, 200, 100, 40] },   // nearer, but far off to the side
    { id: 'B', r: [100, 400, 100, 40] },   // straight below
  ]);
  P.move(DOWN);
  const a = P.move(DOWN);
  check(a === 'moved,150.0,420.0', 'scoring: straight below wins over the near diagonal (' + a + ')');
  const Q = makePage(1000, 800, [
    { id: 'A', r: [100, 100, 100, 40] },
    { id: 'R', r: [700, 110, 100, 40] },   // same row, far
    { id: 'D', r: [260, 180, 100, 40] },   // near, a bit lower
  ]);
  Q.move(DOWN);
  const b = Q.move(RIGHT);
  check(b === 'moved,750.0,130.0', 'scoring: right keeps the row (orthogonal weight 30) (' + b + ')');
}

// --- 3. skipped candidates ----------------------------------------------------------------------------------------------
{
  const P = makePage(1000, 800, [
    { id: 'first', r: [100, 50, 200, 40] },
    { id: 'hidden', r: [100, 120, 200, 40], visibility: 'hidden' },
    { id: 'dis', tag: 'button', r: [100, 190, 200, 40], disabled: true },
    { id: 'tiny', r: [100, 260, 1, 1] },
    { id: 'big', tag: 'div', attrs: { onclick: 'x()' }, r: [0, 300, 1000, 500], kids: [
      { id: 'inBig', r: [100, 330, 200, 40] },                     // a link inside a huge clickable box: reachable
    ] },
    { id: 'covered', r: [100, 400, 200, 40] },
    { id: 'cover', tag: 'div', r: [0, 390, 1000, 60], z: 5 },      // e.g. a cookie bar over it
    { id: 'outer', r: [100, 470, 200, 40], kids: [{ id: 'innerBtn', tag: 'button', r: [110, 475, 50, 30] }] },
    { id: 'cb', tag: 'input', attrs: { type: 'checkbox' }, r: [100, 540, 20, 20] },
    { id: 'hid', tag: 'input', attrs: { type: 'hidden' }, r: [100, 580, 200, 20] },
    { id: 'neg', tag: 'div', attrs: { tabindex: '-1' }, r: [100, 610, 200, 20] },
    { id: 'role', tag: 'div', attrs: { role: 'button' }, r: [100, 650, 200, 40] },
  ]);
  const seq = [];
  for (let k = 0; k < 8; ++k) { const a = P.move(DOWN); if (a === 'none') break; const c = centre(a); seq.push(Math.round(c[1])); }
  // first (70), inBig (350), outer (490; its inner button skipped), checkbox (550), role=button (670)
  check(JSON.stringify(seq) === JSON.stringify([70, 350, 490, 550, 670]), 'skips hidden / disabled / tiny / huge / covered / nested / hidden input / tabindex -1: ' + JSON.stringify(seq));
}

// --- 4. reach, scrolling into view, margin -----------------------------------------------------------------------------
{
  const P = makePage(1000, 800, [
    { id: 'top', r: [100, 100, 200, 40] },
    { id: 'below', r: [100, 1300, 200, 40] },   // 500 px below the screen: within 3/4 of a screen
    { id: 'far', r: [100, 3000, 200, 40] },     // more than 3/4 of a screen below 'below'
  ]);
  P.move(DOWN);
  const a = P.move(DOWN);
  const c = centre(a);
  check(a.startsWith('moved,') && P.doc.scrollY > 0, 'reach: moves to an element below the screen and scrolls (' + a + ', scrollY ' + P.doc.scrollY + ')');
  check(c[1] >= 48 && c[1] <= 800 - 48, 'reach: kept a margin from the edge (' + c[1] + ')');
  check(P.doc.intoView.length === 1 && P.doc.intoView[0].block === 'nearest' && P.doc.intoView[0].behavior === 'instant', 'reach: scrollIntoView nearest, instant');
  const b = P.move(DOWN);
  check(b === 'none', 'reach: too far -> none (the shell scrolls the page)');
}

// --- 5. Cross ------------------------------------------------------------------------------------------------------------
{
  const P = makePage(1000, 800, [
    { id: 'link', r: [100, 100, 200, 40] },
    { id: 'field', tag: 'input', attrs: { type: 'text' }, r: [100, 200, 300, 40] },
    { id: 'btn', tag: 'button', r: [100, 300, 200, 40] },
    { id: 'multi', rects: [[600, 100, 300, 20], [0, 120, 100, 20]] },   // a link over two lines
  ]);
  P.move(DOWN);
  let a = P.run('a', 0, -1, -1, 0);
  check(a === 'pt,200.0,120.0', 'Cross: the centre to click (' + a + ')');
  a = P.move(DOWN);
  check(a === 'moved,250.0,220.0' && P.doc.activeElement !== P.byId.field && P.byId.field.focusCalls.length === 0, 'move: a text box is not focused before Cross');
  check(P.byId.link.blurs === 1, 'move: the link focused before loses the focus');
  a = P.run('a', 0, -1, -1, 0);
  check(a === 'pt,250.0,220.0', 'Cross on a text box: a real click (the keyboard opens) (' + a + ')');
  // covered after the ring moved: the script acts itself
  const cover = new El(P.doc, 'div', {}, { r: [0, 190, 1000, 160], z: 9 });
  P.doc.body.appendChild(cover);
  a = P.run('a', 0, -1, -1, 0);
  check(a === 'field' && P.doc.activeElement === P.byId.field, 'Cross on a covered text box: focused, "field"');
  P.doc.body.removeChild(cover);
  P.move(DOWN);
  P.doc.body.appendChild(cover);
  a = P.run('a', 0, -1, -1, 0);
  check(a === 'clicked' && P.byId.btn.clicks === 1, 'Cross on a covered button: clicked by the script');
  P.doc.body.removeChild(cover);
  const M2 = makePage(1000, 800, [{ id: 'multi', rects: [[600, 100, 300, 20], [0, 120, 100, 20]] }]);
  a = M2.move(DOWN);
  check(a === 'moved,750.0,110.0', 'two-line link: the first line\'s centre (' + a + ')');
  // removed element: none
  M2.doc.body.removeChild(M2.byId.multi);
  a = M2.run('a', 0, -1, -1, 0);
  check(a === 'none' && !M2.ring(), 'Cross after the element went: none, ring gone');
}

// --- 6. starting from the pointer ----------------------------------------------------------------------------------------
{
  const P = grid();
  let a = P.move(DOWN, true, 650, 330);   // between columns 1 and 2 on row 1: the first of row 2 at equal distance
  check(a === 'moved,500.0,520.0', 'pointer start: from the point (' + a + ')');
  const Q = grid();
  a = Q.move(DOWN, true, 150, 120);       // over (0,0): from that link
  check(a === 'moved,200.0,320.0', 'pointer start: from the link under the pointer (' + a + ')');
  a = Q.move(RIGHT, false);
  check(a === 'moved,500.0,320.0', 'then from the ring (' + a + ')');
  // offscreen ring: start from the viewport edge again
  Q.doc.scrollY = 1000;
  const R = makePage(1000, 800, [{ id: 'a', r: [100, 100, 200, 40] }, { id: 'b', r: [100, 1500, 200, 40] }]);
  R.move(DOWN);
  R.doc.scrollY = 1200;   // the user scrolled away with the right stick
  a = R.move(DOWN);
  check(a === 'moved,200.0,320.0', 'ring scrolled away: from the top edge (' + a + ')');
}

// --- 7. pages without a document element, odd input -----------------------------------------------------------------
{
  const ctx = vm.createContext({ document: {}, innerWidth: 1, innerHeight: 1 });
  ctx.window = ctx;
  check(vm.runInContext(core + "('m',1,-1,-1,0,'#000000','#ffffff',4)", ctx) === 'none', 'no documentElement: none');
  const bad = vm.createContext({ document: { documentElement: {} }, innerWidth: 10, innerHeight: 10 });
  bad.window = bad;
  check(vm.runInContext(core + "('m',1,-1,-1,0,'#000000','#ffffff',4)", bad) === 'err', 'a broken DOM: err, no throw');
}

// --- 8. the built samples (from the C++ builder) -----------------------------------------------------------------------
{
  check(samples.length === 3, 'three samples');
  const P = grid();
  const r0 = P.runRaw(samples[0]);   // move down from the pointer at 123.5,67
  check(r0 === 'moved,200.0,120.0', 'sample move (' + r0 + ')');
  const ringEl = P.ring();
  check(ringEl && /#70e4d1/.test(ringEl.style.cssText), 'sample move: accent ring');
  const Q = grid();
  check(Q.runRaw(samples[1]) === 'none', 'sample act with no ring: none');
  check(P.runRaw(samples[2]) === 'hidden' && !P.ring(), 'sample hide');
}

console.log((fails ? 'FAIL' : 'OK') + ': ' + checks + ' checks, ' + fails + ' failures');
process.exit(fails ? 1 : 0);
