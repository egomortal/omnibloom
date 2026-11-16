/* OMNI_HELP_V1: Help & troubleshooting page (DOM side). Pure logic and texts: model.js (tools/test_help_page.cjs).
   Controller: D-pad up / down moves, Cross opens or closes a topic (on the search box: type), D-pad right / left open
   and close, Triangle jumps to search, Square clears it, L1 / R1 jump between topics; Circle closes the open topic,
   otherwise it is Omni's own Back. QR codes are drawn here from bundled text by ../share/vendor/qrcodegen.js (MIT).
   No network, nothing stored (the glyph choice is only read); every node is built with createElement and textContent. */
(function (root) {
  'use strict';
  if (typeof module === 'object' && module.exports) return;
  var M = root.OmniHelpModel, doc = root.document, host = root.omnibloomHost, Q = root.qrcodegen;
  var $ = function (id) { return doc.getElementById(id); };
  var NS = 'http://www.w3.org/2000/svg';

  var kind = 'playstation';
  try { kind = (host && typeof host.getGlyphs === 'function' && host.getGlyphs()) || root.localStorage.getItem('ob.glyphs') || 'playstation'; } catch (e) { /* storage off */ }
  kind = kind === 'xbox' ? 'xbox' : 'playstation';

  var st = M.initial(), drawn = {}, focusedId = null;
  var input = $('search'), list = $('topics'), count = $('count');

  function el(tag, cls, text) { var e = doc.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  // --- build once ---------------------------------------------------------------------------------------------------
  M.TOPICS.forEach(function (t, n) {
    var sec = el('section', 'topic'); sec.id = 't-' + t.id;
    var head = el('button', 'head'); head.id = 'topic-' + t.id; head.type = 'button';
    head.setAttribute('aria-expanded', 'false'); head.setAttribute('aria-controls', 'body-' + t.id);
    head.appendChild(el('span', 'num', String(n + 1)));
    head.appendChild(el('span', 'title', t.title));
    head.appendChild(el('span', 'chev', ''));
    var body = el('div', 'body'); body.id = 'body-' + t.id; body.hidden = true;
    var text = el('div', 'text'), ol = el('ol', 'steps');
    t.steps.forEach(function (s) { ol.appendChild(el('li', null, s)); });
    text.appendChild(ol);
    if (t.open) {
      var a = el('a', 'open'); a.id = 'open-' + t.id; a.href = M.href(t);
      a.appendChild(el('span', 'open-label', 'Open it: ' + t.open.label));
      a.appendChild(el('span', 'open-url', M.omniUrl(t)));
      text.appendChild(a);
    }
    var fig = el('figure', 'qr'); fig.id = 'qr-' + t.id;
    var cap = el('figcaption', null, 'Scan for the online guide'); cap.appendChild(el('span', 'qr-file', 'GitHub · ' + M.docLabel(t)));
    fig.appendChild(cap);
    body.appendChild(text); body.appendChild(fig);
    sec.appendChild(head); sec.appendChild(body);
    list.appendChild(sec);
  });

  function drawQr(t) {
    if (drawn[t.id]) return;
    drawn[t.id] = true;
    var fig = $('qr-' + t.id), m = null;
    try { m = M.qr(Q, M.docUrl(t)); } catch (e) { m = null; }
    if (!m) { fig.insertBefore(el('p', 'qr-none', 'QR code unavailable'), fig.firstChild); return; }
    var side = m.size + 8, svg = doc.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + side + ' ' + side);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'QR code for the online guide: ' + M.docLabel(t));
    svg.setAttribute('shape-rendering', 'crispEdges');
    var bg = doc.createElementNS(NS, 'rect'); bg.setAttribute('width', side); bg.setAttribute('height', side); bg.setAttribute('fill', '#ffffff');
    var dark = doc.createElementNS(NS, 'path'); dark.setAttribute('d', M.qrPath(m)); dark.setAttribute('fill', '#000000');
    svg.appendChild(bg); svg.appendChild(dark);
    fig.insertBefore(svg, fig.firstChild);
  }

  // --- draw -----------------------------------------------------------------------------------------------------------
  function render() {
    var v = M.refresh(st, M.TOPICS);
    M.TOPICS.forEach(function (t) {
      var shown = v.shown.indexOf(t.id) >= 0, open = st.open === t.id;
      $('t-' + t.id).hidden = !shown;
      $('topic-' + t.id).setAttribute('aria-expanded', String(open));
      $('t-' + t.id).className = 'topic' + (open ? ' is-open' : '');
      $('body-' + t.id).hidden = !open;
      if (open) drawQr(t);
    });
    if (input.value !== st.query) input.value = st.query;
    count.textContent = st.query ? v.shown.length + ' of ' + M.TOPICS.length + ' topics' : '';
    $('none').hidden = v.shown.length > 0;
    if (focusedId !== st.focus) {
      if (focusedId && $(focusedId)) $(focusedId).classList.remove('focus');
      focusedId = st.focus;
    }
    var fe = $(st.focus);
    if (fe) {
      fe.classList.add('focus');
      if (fe !== input && doc.activeElement !== fe) { try { fe.focus({ preventScroll: true }); } catch (e) { fe.focus(); } }
      if (fe === input && doc.activeElement !== input && doc.activeElement && doc.activeElement !== doc.body) doc.activeElement.blur();
      var r = fe.getBoundingClientRect(), vh = root.innerHeight || 720;
      if (r.top < vh * 0.15 || r.bottom > vh * 0.85) fe.scrollIntoView({ block: 'center' });
    }
    $('hint').textContent = M.hint(kind);
  }

  function controller(a) {
    var res = M.step(st, a, M.TOPICS);
    if (!res.handled) return false;
    if (res.go) { root.location.href = res.go; return true; }
    render();
    if (res.edit) { try { input.focus(); input.select(); } catch (e) { /* no keyboard */ } }
    else if (st.focus !== 'search' && doc.activeElement === input) input.blur();
    return true;
  }
  root.omniMediaController = controller;
  root.omniPadController = controller;

  input.addEventListener('input', function () { st.query = input.value.slice(0, 80); render(); });
  doc.addEventListener('keydown', function (e) {
    var typing = doc.activeElement === input;
    if (typing && (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'Backspace' || e.key.length === 1)) return;
    if (typing && (e.key === 'Enter' || e.key === 'Escape')) { input.blur(); if (e.key === 'Enter') controller('down'); e.preventDefault(); return; }
    var a = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Enter: 'cross', Escape: 'circle',
      PageUp: 'l1', PageDown: 'r1' }[e.key];
    if (a && controller(a)) e.preventDefault();
  });
  // Pointer / touch: the clicked control takes focus, then does what Cross would.
  doc.addEventListener('click', function (e) {
    var b = e.target && e.target.closest ? e.target.closest('button.head, a.open, #search') : null;
    if (!b) return;
    st.focus = b.id;
    if (b.id === 'search') { render(); return; }
    if (b.tagName === 'A') return;               // the link navigates by itself
    controller('cross');
  });

  render();
})(typeof window !== 'undefined' ? window : this);
