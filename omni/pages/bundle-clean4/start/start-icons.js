/* OMNI_START_ICONS_V1: real site icons on the start page's tiles (Pinned + Recent sites, Continue watching, Web apps,
   Reading list, Recently closed). Omni caches each site's icon (OMNI_FAVICONS_V1) and serves it to this page only as
   omni://pages/_user/icon/<key>.png (same origin: the page's CSP needs no change). The key is the icon's cache name:
   FNV-1a 64 of the site's host key, 16 hex digits. Omni hands it over as "icon" in its data (Continue watching, Web
   apps, Reading list, Recently closed); Pinned / Recent sites live in this page's own storage, so the key is computed
   here (key(), a byte-for-byte port of OmniFavicons::hostKey + fnv1a64). An icon replaces the letter only once it has
   loaded: no icon cached (a 404) = the letter / tile exactly as before. Nothing here is fetched from the web. */
(function (root) {
'use strict';
const ROUTE = 'omni://pages/_user/icon/';
const KEY = /^[0-9a-f]{16}$/;

const lowerAscii = s => s.replace(/[A-Z]/g, c => String.fromCharCode(c.charCodeAt(0) + 32));
// OmniFavicons::hostKey: lower case host of an http(s) address, no credentials / port / trailing dots, a leading
// "www." dropped (when more dots follow); "" for anything else. ASCII only, as the C++ (non-ASCII hosts: "").
function hostKey(url) {
  if (typeof url !== 'string' || url.length > 8192) return '';
  const head = lowerAscii(url.slice(0, 8));
  let p;
  if (head.startsWith('https://')) p = 8;
  else if (head.startsWith('http://')) p = 7;
  else return '';
  let end = url.length;
  for (let i = p; i < url.length; i++) { const c = url[i]; if (c === '/' || c === '?' || c === '#' || c === '\\') { end = i; break; } }
  const at = url.lastIndexOf('@', end ? end - 1 : 0);
  if (at >= p && at < end) p = at + 1;
  if (p < end && url[p] === '[') {
    const close = url.indexOf(']', p);
    if (close < 0 || close >= end) return '';
    const h = url.slice(p + 1, close);
    if (!h || !/^[0-9a-fA-F:.]+$/.test(h)) return '';
    return '[' + lowerAscii(h) + ']';
  }
  const colon = url.indexOf(':', p);
  let host = lowerAscii(url.slice(p, colon >= 0 && colon < end ? colon : end));
  host = host.replace(/\.+$/, '');
  if (!host || host.length > 253 || !/^[a-z0-9._-]+$/.test(host)) return '';
  if (host.startsWith('www.') && host.length > 4 && host.indexOf('.', 4) >= 0) host = host.slice(4);
  return host;
}
// FNV-1a, 64 bit, over the host key's bytes (ASCII: one byte per character), as 16 lowercase hex digits.
// Four 16-bit limbs (no BigInt needed): h = (h ^ byte) * 0x100000001b3 mod 2^64.
function fnv1a64(s) {
  let h = [0x2325, 0x8422, 0x9ce4, 0xcbf2];   // 0xcbf29ce484222325, least significant limb first
  for (let i = 0; i < s.length; i++) {
    h[0] ^= s.charCodeAt(i) & 0xff;
    // * 0x00000100000001b3 = h * 0x1b3 + (h << 40)
    const r = [0, 0, 0, 0];
    let carry = 0;
    for (let k = 0; k < 4; k++) { const v = h[k] * 0x1b3 + carry; r[k] = v & 0xffff; carry = Math.floor(v / 0x10000); }
    // h << 40: limb k moves to limb k + 2, shifted left by 8 bits
    let c2 = 0;
    for (let k = 2; k < 4; k++) {
      const sh = ((h[k - 2] << 8) & 0xffff) | (k - 3 >= 0 ? (h[k - 3] >>> 8) : 0);
      const v = r[k] + sh + c2;
      r[k] = v & 0xffff; c2 = v >>> 16;
    }
    h = r;
  }
  return h.slice().reverse().map(x => x.toString(16).padStart(4, '0')).join('');
}
function key(url) { const h = hostKey(url); return h ? fnv1a64(h) : ''; }
// A bare site ("example.com") as the reading list shows it.
function siteKey(site) { return typeof site === 'string' && site && site.length <= 253 && !/[\/?#@\\\s]/.test(site) ? key('https://' + site + '/') : ''; }
function valid(k) { return typeof k === 'string' && KEY.test(k); }
// Omni's key when it gave one, else the one computed from the address.
function pick(given, url) { return valid(given) ? given : key(url); }
function src(k) { return valid(k) ? ROUTE + k + '.png' : ''; }

const api = { ROUTE, hostKey, fnv1a64, key, siteKey, valid, pick, src };
if (typeof module === 'object' && module.exports) { module.exports = api; return; }

// --- the page --------------------------------------------------------------------------------------------------------
const doc = root.document;
const onPages = () => { try { return root.location.protocol === 'omni:'; } catch (e) { return false; } };
// slot: the element showing the letter (or an empty placeholder). Once the icon has loaded it replaces the slot's
// content and the slot gets .osic-on; until then (and on any error) nothing changes. false: no icon to try.
function attach(slot, k) {
  if (!slot || !valid(k) || !onPages()) return false;
  const img = doc.createElement('img');
  img.alt = '';
  img.className = 'osic-img';
  img.decoding = 'async';
  img.draggable = false;
  img.addEventListener('load', () => {
    if (!img.naturalWidth || !slot.isConnected) return;
    slot.replaceChildren(img);
    slot.classList.add('osic-on');
  });
  img.src = src(k);
  return true;
}
// Pinned / Recent sites: pins.js and app.js put the address on each button (data-osic-url); the icon goes in front of
// the name. Redrawn lists (replaceChildren) are decorated again.
function decorate(box) {
  if (!box) return;
  for (const b of box.querySelectorAll('button[data-osic-url]')) {
    const k = key(b.dataset.osicUrl);
    if (!valid(k) || b.dataset.osicKey === k) continue;
    b.dataset.osicKey = k;
    const old = b.querySelector(':scope > .osic-site');
    if (old) old.remove();
    const slot = doc.createElement('span');
    slot.className = 'osic-site';
    slot.setAttribute('aria-hidden', 'true');
    b.classList.add('osic-site-tile');
    b.prepend(slot);
    attach(slot, k);
  }
}
function watch(id) {
  const box = doc.getElementById(id);
  if (!box) return;
  decorate(box);
  if (root.MutationObserver) new root.MutationObserver(() => decorate(box)).observe(box, { childList: true, subtree: true });
}
root.omniStartIcons = Object.freeze({ ...api, attach, decorate });
if (onPages()) { watch('pins'); watch('recents'); }
})(typeof window !== 'undefined' ? window : globalThis);
