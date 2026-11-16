/* OMNI_START_CUSTOM_V1: "Customise start page" (Browser settings > Customise start page..., or the gear here).
   Omni gives this page its settings through one fixed script after it loads (window.omniStartCustomApply(data), or
   window.__omniStartCustom when this file was not ready yet); nothing here reads files or storage, nothing is saved here.
   Sections: search (the hero's search box; the Universe picker stays), apps, shortcuts (Pinned + Recent sites),
   cw (Continue watching, drawn by Omni itself as #omni-cw), reading (latest 3 saved pages), closed (recently closed
   tabs). Default order: the Universe's own grid layout; any other order: one column in that order (CSS order). */
(function (root) {
'use strict';
const KEYS = ['search', 'apps', 'shortcuts', 'cw', 'reading', 'closed'];
const PICTURE = 'omni://pages/_user/start-bg.png?v=';
const MAX_READING = 3, MAX_CLOSED = 5;

function text(v, max) { return typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, max) : ''; }
function webURL(u) { return typeof u === 'string' && u.length <= 4096 && /^https?:\/\/[^\s"<>\\]+$/.test(u); }
function readingId(id) { return typeof id === 'string' && id.length > 0 && id.length <= 255 && id[0] !== '.' && !/[\s\/\\\u0000-\u001f\u007f]/.test(id); }

// The data from Omni -> a checked plan (anything unexpected falls back to the default look).
function normalize(D) {
  const d = D && typeof D === 'object' ? D : {};
  const order = [];
  for (const k of Array.isArray(d.order) ? d.order : []) if (KEYS.includes(k) && !order.includes(k)) order.push(k);
  KEYS.forEach((k, i) => {   // a section the data does not name: after its default predecessor
    if (order.includes(k)) return;
    let at = 0;
    for (let p = i - 1; p >= 0; p--) { const j = order.indexOf(KEYS[p]); if (j >= 0) { at = j + 1; break; } }
    order.splice(at, 0, k);
  });
  const hidden = new Set((Array.isArray(d.hidden) ? d.hidden : []).filter(k => KEYS.includes(k)));
  if (d.private === true) { hidden.add('cw'); hidden.add('closed'); }   // the existing private rules, again here
  let bg = { kind: 'theme' };
  const b = d.bg && typeof d.bg === 'object' ? d.bg : {};
  if (b.kind === 'colour' && /^#[0-9a-fA-F]{6}$/.test(b.value || '')) bg = { kind: 'colour', value: b.value };
  else if (b.kind === 'picture' && typeof b.url === 'string' && b.url.startsWith(PICTURE) && /^[\w\-]{1,64}$/.test(b.url.slice(PICTURE.length))) bg = { kind: 'picture', url: b.url };
  const reading = (Array.isArray(d.reading) ? d.reading : []).filter(r => r && readingId(r.id)).slice(0, MAX_READING)
    .map(r => ({ id: r.id, t: text(r.t, 200) || text(r.s, 200) || 'Saved page', s: text(r.s, 120), d: text(r.d, 40) }));
  const closed = d.private === true ? [] : (Array.isArray(d.closed) ? d.closed : []).filter(r => r && webURL(r.u)).slice(0, MAX_CLOSED)
    .map(r => ({ u: r.u, t: text(r.t, 200) || text(r.s, 200) || r.u, s: text(r.s, 120) }));
  const linear = order.join() !== KEYS.join();
  return { order, hidden, bg, clock: d.clock === true, private: d.private === true, linear, reading, closed, hint: text(d.hint, 80) };
}
// What each section gets: CSS order (one-column mode only) and whether it is shown.
function plan(n) {
  const out = {};
  n.order.forEach((k, i) => {
    const empty = (k === 'reading' && !n.reading.length) || (k === 'closed' && !n.closed.length);
    out[k] = { order: n.linear ? String(i + 1) : '', shown: !n.hidden.has(k) && !empty };
  });
  return out;
}
function clockText(date) {
  const h = date.getHours(), m = date.getMinutes();
  return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
}

const api = { KEYS, normalize, plan, clockText, webURL, readingId };
if (typeof module === 'object' && module.exports) { module.exports = api; return; }

// --- the page --------------------------------------------------------------------------------------------------------
const doc = root.document;
let current = null, lastLists = '', clockTimer = 0, observer = null;
const $ = id => doc.getElementById(id);
function host() { return root.omnibloomHost && typeof root.omnibloomHost.request === 'function' ? root.omnibloomHost : null; }
function toast(t) { try { root.obUI && root.obUI.toast(t); } catch (e) {} }
async function ask(method, url, failText) {
  const h = host();
  try {
    if (!h) throw Error('UNSUPPORTED');
    const r = await h.request({ method, params: url ? { url } : {} });
    if (!r || r.ok !== true) throw Error((r && r.code) || 'UNSUPPORTED');
  } catch (e) { toast(failText); }
}
function el(tag, cls, txt) { const e = doc.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
function sections() {
  const hero = doc.querySelector('.hero'), apps = $('apps'), pins = $('pins');
  return {
    search: hero, apps: apps && apps.closest('section'), shortcuts: pins && pins.closest('section'),
    cw: $('omni-cw'), reading: $('oscu-reading'), closed: $('oscu-closed'),
  };
}
function ensureSection(id, title) {
  let s = $(id);
  if (s) return s;
  s = el('section', 'section card oscu-extra');
  s.id = id;
  s.setAttribute('aria-label', title);
  const head = el('div', 'row spread');
  head.append(el('h2', null, title));
  s.append(head, el('div', 'oscu-tiles'));
  const main = $('main'), before = $('pin-dialog');
  if (before && before.parentNode === main) main.insertBefore(s, before); else main.append(s);
  return s;
}
function tile(title, sub, onclick) {
  const b = el('button', 'oscu-tile');
  b.type = 'button';
  b.title = title;
  b.append(el('b', null, title), el('small', null, sub));
  b.addEventListener('click', onclick);
  return b;
}
function drawLists(n) {
  const key = JSON.stringify([n.reading, n.closed, n.hint]);
  if (key === lastLists && $('oscu-reading') && $('oscu-closed')) return;
  lastLists = key;
  const r = ensureSection('oscu-reading', 'Reading list'), rt = r.querySelector('.oscu-tiles');
  rt.replaceChildren(...n.reading.map(x => tile(x.t, [x.s, x.d].filter(Boolean).join(' · '),
    () => ask('start.reading.open', x.id, 'This saved page could not open.'))));
  if (!r.querySelector('.oscu-all')) {
    const all = el('button', 'oscu-all', 'All saved pages');
    all.type = 'button';
    all.addEventListener('click', () => ask('start.reading.all', '', 'The reading list could not open.'));
    r.querySelector('.row').append(all);
  }
  const c = ensureSection('oscu-closed', 'Recently closed tabs'), ct = c.querySelector('.oscu-tiles');
  ct.replaceChildren(...n.closed.map(x => tile(x.t, x.s, () => ask('start.closed.open', x.u, 'This tab could not reopen.'))));
}
function place() {
  if (!current) return;
  const p = plan(current), s = sections();
  for (const k of KEYS) {
    const e = s[k];
    if (!e) continue;
    e.style.order = p[k].order;
    if (k !== 'search' && k !== 'apps' && k !== 'shortcuts') e.classList.add('oscu-extra');
    if (k === 'search') { const f = $('search'); if (f) f.classList.toggle('oscu-hidden', !p[k].shown); }
    else e.classList.toggle('oscu-hidden', !p[k].shown);
  }
  doc.body.classList.toggle('oscu-linear', current.linear);
}
function background(bg) {
  const st = doc.body.style;
  for (const name of ['background', 'background-image', 'background-color', 'background-size', 'background-position', 'background-attachment', 'background-repeat']) st.removeProperty(name);
  doc.body.classList.toggle('oscu-bg-picture', bg.kind === 'picture');
  doc.body.classList.toggle('oscu-bg-colour', bg.kind === 'colour');
  if (bg.kind === 'colour') st.setProperty('background', bg.value, 'important');
  else if (bg.kind === 'picture') {
    st.setProperty('background-color', '#000', 'important');
    st.setProperty('background-image', 'linear-gradient(rgba(0,0,0,.35),rgba(0,0,0,.35)),url("' + bg.url + '")', 'important');
    st.setProperty('background-size', 'cover', 'important');
    st.setProperty('background-position', 'center', 'important');
    st.setProperty('background-attachment', 'fixed', 'important');
    st.setProperty('background-repeat', 'no-repeat', 'important');
  }
}
function clock(on) {
  const top = doc.querySelector('.topline');
  let c = $('oscu-clock');
  if (!c && top) { c = el('time', 'oscu-clock'); c.id = 'oscu-clock'; c.setAttribute('aria-label', 'Time'); top.append(c); }
  if (!c) return;
  c.hidden = !on;
  root.clearInterval(clockTimer);
  clockTimer = 0;
  if (!on) return;
  const tick = () => { c.textContent = clockText(new Date()); };
  tick();
  clockTimer = root.setInterval(tick, 10000);
}
function gear() {
  const top = doc.querySelector('.topline');
  if (!top || $('oscu-gear')) return;
  const b = el('button', 'oscu-gear', '⚙ Customise');
  b.id = 'oscu-gear';
  b.type = 'button';
  b.setAttribute('aria-label', 'Customise start page');
  b.addEventListener('click', () => ask('start.customise', '', 'Open Browser settings > Customise start page.'));
  top.append(b);
}
// Focus that ended up inside something now hidden goes to the first visible control.
function keepFocus() {
  const a = doc.activeElement;
  if (a && a !== doc.body && !a.closest('.oscu-hidden')) return;
  try { const items = root.obUI && root.obUI.items(); if (items && items.length) root.obUI.focus(items[0]); } catch (e) {}
}
function apply(D) {
  current = normalize(D);
  gear();
  drawLists(current);
  place();
  background(current.bg);
  clock(current.clock);
  keepFocus();
  if (!observer && root.MutationObserver) {   // Continue watching (re)inserts its own section: place it again
    observer = new root.MutationObserver(place);
    observer.observe($('main'), { childList: true });
  }
  return 'ok';
}
root.omniStartCustomApply = apply;
root.addEventListener('pagehide', () => { root.clearInterval(clockTimer); clockTimer = 0; });
root.addEventListener('pageshow', e => { if (e.persisted && current) clock(current.clock); });
if (root.__omniStartCustom) apply(root.__omniStartCustom);   // Omni's data came before this file
})(typeof window !== 'undefined' ? window : globalThis);
