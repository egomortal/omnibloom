/* OMNI_SOLITAIRE_V1: Solitaire page (DOM side). Rules: model.js.
   Controller: D-pad moves the cursor (up / down inside a column picks how many cards), Cross picks up / puts down,
   Square sends the card under the cursor where it obviously goes, Triangle undoes, L1 / R1 deal a new game,
   Circle drops what is held (else Omni's own Back). The game is kept in localStorage; nothing is sent anywhere. */
(function (root) {
  'use strict';
  if (typeof module === 'object' && module.exports) return;
  var M = root.OmniSolitaire, doc = root.document, $ = function (id) { return doc.getElementById(id); };
  var store = null; try { store = root.localStorage; } catch (e) { store = null; }
  function read() { try { return store ? store.getItem(M.KEY) : null; } catch (e) { return null; } }
  function save() { try { if (store) store.setItem(M.KEY, M.snapshot(st)); } catch (e) { /* storage off: in memory only */ } }
  var st = M.restore(read(), Date.now()), undo = [], held = null;
  // Cursor: row 0 = stock (0), waste (1), foundations (3..6); row 1 = tableau column c, depth k (card index).
  var cur = { row: 1, c: 0, k: -1 };
  function topRow() { return [0, 1, 3, 4, 5, 6]; }
  function depthFor(c) { var col = st.tab[c]; return col.length ? col.length - 1 : -1; }
  function srcAtCursor() {
    if (cur.row === 0) { if (cur.c === 1) return { kind: 'waste' }; if (cur.c >= 3) return { kind: 'found', i: cur.c - 3 }; return null; }
    var col = st.tab[cur.c]; if (!col.length) return null; return { kind: 'tab', i: cur.c, k: Math.max(cur.k, M.runStart(col)) };
  }
  function dstAtCursor() { if (cur.row === 0 && cur.c >= 3) return { kind: 'found', i: cur.c - 3 }; if (cur.row === 1) return { kind: 'tab', i: cur.c }; return null; }
  function remember() { undo.push(M.snapshot(st)); if (undo.length > M.UNDO) undo.shift(); }
  function note(text) { $('note').textContent = text; }
  function act(a) {
    if (a === 'left' || a === 'right') {
      var d = a === 'left' ? -1 : 1;
      if (cur.row === 0) { var tr = topRow(), i = tr.indexOf(cur.c); cur.c = tr[Math.max(0, Math.min(tr.length - 1, i + d))]; }
      else { cur.c = Math.max(0, Math.min(6, cur.c + d)); cur.k = depthFor(cur.c); }
      return true;
    }
    if (a === 'up') {
      if (cur.row === 1) { var col = st.tab[cur.c], s0 = M.runStart(col); if (col.length && cur.k > s0) { cur.k--; return true; } cur.row = 0; cur.c = cur.c <= 1 ? cur.c : Math.min(6, Math.max(3, cur.c)); return true; }
      return false;
    }
    if (a === 'down') {
      if (cur.row === 0) { cur.row = 1; cur.c = cur.c === 1 ? 1 : cur.c; cur.k = depthFor(cur.c); return true; }
      if (cur.k < depthFor(cur.c)) { cur.k++; return true; }
      return false;
    }
    if (a === 'cross') {
      if (cur.row === 0 && cur.c === 0) { remember(); if (!M.draw(st)) undo.pop(); held = null; return true; }
      if (held) {
        var dst = dstAtCursor(); remember();
        if (dst && M.move(st, held, dst)) { held = null; cur.k = depthFor(cur.c); return true; }
        undo.pop(); note('That card does not go there.'); return true;
      }
      var src = srcAtCursor(); if (src && M.cardsAt(st, src).length) { held = src; note(''); return true; }
      return false;
    }
    if (a === 'square') { var s = held || srcAtCursor(); if (!s) return false; remember(); if (M.auto(st, s)) { held = null; cur.k = depthFor(cur.c); return true; } undo.pop(); note('No move for that card.'); return true; }
    if (a === 'triangle') { if (!undo.length) { note('Nothing to undo.'); return true; } st = JSON.parse(undo.pop()); held = null; cur.k = Math.min(cur.k, depthFor(cur.c)); return true; }
    if (a === 'l1' || a === 'r1') { st = M.deal(Date.now()); undo = []; held = null; cur = { row: 1, c: 0, k: depthFor(0) }; note('New game.'); return true; }
    if (a === 'circle') { if (held) { held = null; note(''); return true; } return false; }
    return false;
  }
  function cardEl(c, here, chosen) {
    var e = doc.createElement('div'); e.className = 'card' + (c.up ? (M.red(c) ? ' red' : ' black') : ' back') + (here ? ' here' : '') + (chosen ? ' held' : '');
    e.textContent = c.up ? M.label(c) : ''; e.setAttribute('aria-label', c.up ? M.label(c) : 'face-down card'); return e;
  }
  function slot(here, text) { var e = doc.createElement('div'); e.className = 'card slot' + (here ? ' here' : ''); e.textContent = text || ''; return e; }
  function render() {
    var heldCards = held ? M.cardsAt(st, held) : [];
    var top = $('top'); top.replaceChildren();
    var stockHere = cur.row === 0 && cur.c === 0, wasteHere = cur.row === 0 && cur.c === 1;
    top.append(st.stock.length ? cardEl({ up: false }, stockHere, false) : slot(stockHere, '↻'));
    var w = st.waste[st.waste.length - 1]; top.append(w ? cardEl(w, wasteHere, held && held.kind === 'waste') : slot(wasteHere));
    var gap = doc.createElement('div'); gap.className = 'gap'; top.append(gap);
    st.found.forEach(function (f, i) { var here = cur.row === 0 && cur.c === 3 + i, t = f[f.length - 1]; top.append(t ? cardEl(t, here, held && held.kind === 'found' && held.i === i) : slot(here, 'A')); });
    var tab = $('tab'); tab.replaceChildren();
    st.tab.forEach(function (col, i) {
      var c = doc.createElement('div'); c.className = 'col';
      if (!col.length) c.append(slot(cur.row === 1 && cur.c === i, 'K'));
      col.forEach(function (card, k) { var here = cur.row === 1 && cur.c === i && (k === cur.k || (cur.k < 0 && k === col.length - 1));
        var chosen = held && held.kind === 'tab' && held.i === i && k >= held.k; c.append(cardEl(card, here, chosen)); });
      tab.append(c);
    });
    $('moves').textContent = st.moves + ' moves';
    $('holding').textContent = heldCards.length ? 'Holding ' + heldCards.map(M.label).join(' ') : '';
    if (M.won(st)) note('You won in ' + st.moves + ' moves! L1 / R1 deals a new game.');
    save();
  }
  function controller(a) { var used = act(a); if (used) render(); return used; }
  root.omniPadController = controller;
  doc.addEventListener('keydown', function (e) {
    var a = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Enter: 'cross', Escape: 'circle', PageUp: 'l1', PageDown: 'r1',
      ' ': 'square', Backspace: 'triangle', u: 'triangle', n: 'r1' }[e.key];
    if (a && controller(a)) e.preventDefault();
  });
  cur.k = depthFor(0); render();
})(typeof window !== 'undefined' ? window : globalThis);
