/* OMNI_WEB_APPS_V1: the "Web apps" tiles inside "Your apps" (sites saved with hold Cross > Add to Apps in Omni).
   Omni gives this page the list through one fixed script after it loads (window.omniWebAppsApply(data), or
   window.__omniWebApps when this file was not ready yet): {v:1, apps:[{id,n,h,c,k,l}], max:12, hint}.
   Nothing here reads files or storage, nothing is saved here. Cross on a tile asks Omni to open the app
   (request "webapps.open", params.url = the app id); "Manage" asks for the Apps panel ("webapps.manage").
   Tiles are coloured letters: this page's CSP allows only its own and data: images, so site icons are not drawn. */
(function (root) {
'use strict';
const MAX = 12;
const FALLBACK = '#3a3a3a';

function text(v, max) { return typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, max) : ''; }
function validId(id) { return typeof id === 'string' && /^a[0-9a-f]{12}$/.test(id); }
function colour(c, fallback) { return typeof c === 'string' && /^#[0-9a-fA-F]{6}$/.test(c) ? c.toLowerCase() : fallback; }
function letterOf(name) {
  const s = text(name, 200);
  if (!s) return '?';
  return String.fromCodePoint(s.codePointAt(0)).toUpperCase();
}
// The data from Omni -> checked tiles (at most 12, each id once).
function normalize(D) {
  const d = D && typeof D === 'object' ? D : {};
  const apps = [], seen = new Set();
  for (const a of Array.isArray(d.apps) ? d.apps : []) {
    if (apps.length >= MAX) break;
    if (!a || !validId(a.id) || seen.has(a.id)) continue;
    seen.add(a.id);
    const n = text(a.n, 40) || text(a.h, 80) || 'App';
    const l = text(a.l, 4);
    apps.push({ id: a.id, n, h: text(a.h, 80), c: colour(a.c, FALLBACK), k: colour(a.k, '#ffffff'), l: l && [...l].length === 1 ? l : letterOf(n) });
  }
  return { apps, hint: text(d.hint, 40) };
}
function countText(n) { return n + ' of ' + MAX; }

const api = { MAX, normalize, letterOf, validId, countText };
if (typeof module === 'object' && module.exports) { module.exports = api; return; }

// --- the page --------------------------------------------------------------------------------------------------------
const doc = root.document;
const $ = id => doc.getElementById(id);
let lastKey = '';
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
function box() {
  let b = $('omni-webapps');
  if (b) return b;
  const apps = $('apps');
  if (!apps || !apps.parentNode) return null;
  b = el('div', 'owap');
  b.id = 'omni-webapps';
  b.setAttribute('aria-label', 'Web apps');
  const head = el('div', 'row spread owap-head');
  const title = el('h3', 'owap-title', 'Web apps');
  const right = el('span', 'owap-right');
  const count = el('small', 'owap-count');
  const manage = el('button', 'owap-manage', 'Manage');
  manage.type = 'button';
  manage.addEventListener('click', () => ask('webapps.manage', '', 'Open Browser settings > Apps on start page.'));
  right.append(count, manage);
  head.append(title, right);
  b.append(head, el('div', 'owap-tiles'));
  apps.parentNode.insertBefore(b, apps.nextSibling);
  return b;
}
function tile(a) {
  const t = el('button', 'owap-tile');
  t.type = 'button';
  t.title = a.h ? a.n + ' (' + a.h + ')' : a.n;
  t.style.setProperty('--owap-bg', a.c);
  t.style.setProperty('--owap-ink', a.k);
  t.append(el('span', 'owap-letter', a.l), el('b', 'owap-name', a.n), el('small', 'owap-host', a.h));
  t.addEventListener('click', () => ask('webapps.open', a.id, 'This app could not open.'));
  return t;
}
function draw(n) {
  const key = JSON.stringify(n);
  const b = box();
  if (!b || (key === lastKey && b.querySelector('.owap-tiles'))) return;
  lastKey = key;
  b.querySelector('.owap-count').textContent = n.apps.length ? countText(n.apps.length) : '';
  const tiles = b.querySelector('.owap-tiles');
  if (n.apps.length) tiles.replaceChildren(...n.apps.map(tile));
  else tiles.replaceChildren(el('p', 'owap-empty', 'On a site: hold Cross, then "Add to Apps". It opens here without the address bar.'));
}
function apply(D) {
  const n = normalize(D);
  const a = doc.activeElement, had = a && a.classList && a.classList.contains('owap-tile') ? [...doc.querySelectorAll('.owap-tile')].indexOf(a) : -1;
  draw(n);
  if (had >= 0) {   // the focus stays on the same place when the list is redrawn
    const all = doc.querySelectorAll('.owap-tile');
    const next = all.length ? all[Math.min(had, all.length - 1)] : doc.querySelector('.owap-manage');
    try { if (next && root.obUI) root.obUI.focus(next); } catch (e) {}
  }
  return 'ok';
}
root.omniWebAppsApply = apply;
if (root.__omniWebApps) apply(root.__omniWebApps);   // Omni's data came before this file
})(typeof window !== 'undefined' ? window : globalThis);
