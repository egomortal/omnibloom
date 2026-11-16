/* OMNI_WHATSNEW_V1: the "What's new" page. Data: whatsnew.json in this folder (generated from CHANGELOG.md by the
   repo's tools/gen_whatsnew.py). Native side: apply_whatsnew.py (whatsnew.info, whatsnew.try). Never fetches anything
   but its own bundled file. Controller: D-pad moves between cards, Cross runs the card's "Try it", L1 / R1 jump between
   groups, Circle is Omni's own Back. Pure helpers are exported for node tests (tools/test_whatsnew_page.cjs). */
(function (root) {
  'use strict';

  var STR = {
    en: { title: "What's new in Omni", updated: 'Omni was updated to {v}', version: 'Omni {v}', tryIt: 'Try it',
      where: 'Where:', hint: 'D-pad: move   {cross}: try it   {l1} / {r1}: next group   {circle}: back',
      notInOmni: 'Open this page in Omni to try it', failed: "That couldn't be opened", empty: 'Nothing to show.',
      tabs: 'Tabs', video: 'Video', reading: 'Reading', privacy: 'Privacy', accessibility: 'Accessibility',
      controller: 'Controller', keyboard: 'Keyboard', browsing: 'Browsing' },
    es: { title: 'Novedades de Omni', updated: 'Omni se actualizó a {v}', version: 'Omni {v}', tryIt: 'Probar',
      where: 'Dónde:', hint: 'Cruceta: mover   {cross}: probar   {l1} / {r1}: siguiente grupo   {circle}: atrás',
      notInOmni: 'Abre esta página en Omni para probarlo', failed: 'No se pudo abrir', empty: 'Nada que mostrar.',
      tabs: 'Pestañas', video: 'Vídeo', reading: 'Lectura', privacy: 'Privacidad', accessibility: 'Accesibilidad',
      controller: 'Mando', keyboard: 'Teclado', browsing: 'Navegación' },
    fr: { title: 'Nouveautés d’Omni', updated: 'Omni a été mis à jour en {v}', version: 'Omni {v}', tryIt: 'Essayer',
      where: 'Où :', hint: 'Croix directionnelle : déplacer   {cross} : essayer   {l1} / {r1} : groupe suivant   {circle} : retour',
      notInOmni: 'Ouvrez cette page dans Omni pour essayer', failed: 'Impossible de l’ouvrir', empty: 'Rien à afficher.',
      tabs: 'Onglets', video: 'Vidéo', reading: 'Lecture', privacy: 'Confidentialité', accessibility: 'Accessibilité',
      controller: 'Manette', keyboard: 'Clavier', browsing: 'Navigation' },
    de: { title: 'Neu in Omni', updated: 'Omni wurde auf {v} aktualisiert', version: 'Omni {v}', tryIt: 'Ausprobieren',
      where: 'Wo:', hint: 'Steuerkreuz: bewegen   {cross}: ausprobieren   {l1} / {r1}: nächste Gruppe   {circle}: zurück',
      notInOmni: 'Diese Seite in Omni öffnen, um es auszuprobieren', failed: 'Konnte nicht geöffnet werden', empty: 'Nichts anzuzeigen.',
      tabs: 'Tabs', video: 'Video', reading: 'Lesen', privacy: 'Datenschutz', accessibility: 'Bedienungshilfen',
      controller: 'Controller', keyboard: 'Tastatur', browsing: 'Surfen' },
    pt: { title: 'Novidades do Omni', updated: 'O Omni foi atualizado para {v}', version: 'Omni {v}', tryIt: 'Experimentar',
      where: 'Onde:', hint: 'Direcional: mover   {cross}: experimentar   {l1} / {r1}: próximo grupo   {circle}: voltar',
      notInOmni: 'Abra esta página no Omni para experimentar', failed: 'Não foi possível abrir', empty: 'Nada para mostrar.',
      tabs: 'Abas', video: 'Vídeo', reading: 'Leitura', privacy: 'Privacidade', accessibility: 'Acessibilidade',
      controller: 'Controle', keyboard: 'Teclado', browsing: 'Navegação' }
  };
  var GLYPHS = { playstation: { cross: 'Cross', circle: 'Circle', l1: 'L1', r1: 'R1' },
    xbox: { cross: 'A', circle: 'B', l1: 'LB', r1: 'RB' } };

  function langOf(code) {
    var c = String(code || '').toLowerCase().slice(0, 2);
    return Object.prototype.hasOwnProperty.call(STR, c) ? c : 'en';
  }
  function t(lang, key, vars) {
    var s = (STR[langOf(lang)] || STR.en)[key];
    if (s === undefined) s = STR.en[key] === undefined ? key : STR.en[key];
    return String(s).replace(/\{(\w+)\}/g, function (m, k) { return vars && vars[k] !== undefined ? String(vars[k]) : m; });
  }
  function glyphKind(v) { return v === 'xbox' ? 'xbox' : 'playstation'; }

  // Cards in reading order: {g: group index, i: item index, row: global row, col}; `cols` cards per row in a group.
  function layout(groups, cols) {
    var cells = [], row = 0, n = Math.max(1, cols | 0);
    (groups || []).forEach(function (grp, g) {
      var items = grp && grp.items || [];
      items.forEach(function (_, i) { cells.push({ g: g, i: i, row: row + Math.floor(i / n), col: i % n }); });
      if (items.length) row += Math.ceil(items.length / n);
    });
    return cells;
  }
  // The card D-pad `dir` (up down left right) moves to from cells[idx]; idx itself when nothing is that way.
  function move(cells, idx, dir) {
    var c = cells[idx];
    if (!c) return cells.length ? 0 : -1;
    if (dir === 'left' || dir === 'right') {
      var j = idx + (dir === 'right' ? 1 : -1);
      return cells[j] && cells[j].row === c.row ? j : idx;
    }
    if (dir !== 'up' && dir !== 'down') return idx;
    var target = c.row + (dir === 'down' ? 1 : -1), best = -1;
    for (var k = 0; k < cells.length; k++) {
      if (cells[k].row !== target) continue;
      if (best < 0 || cells[k].col <= c.col) best = k;   // same column, else the row's last card
    }
    return best < 0 ? idx : best;
  }
  // First card of the previous / next group (dir -1 / +1); previous from inside a group: its own first card first.
  function groupJump(cells, idx, dir) {
    var c = cells[idx];
    if (!c) return cells.length ? 0 : -1;
    var first = function (g) { for (var k = 0; k < cells.length; k++) if (cells[k].g === g) return k; return -1; };
    if (dir < 0 && first(c.g) !== idx) return first(c.g);
    for (var g = c.g + (dir < 0 ? -1 : 1); g >= 0 && g <= cells[cells.length - 1].g; g += dir < 0 ? -1 : 1) {
      var f = first(g);
      if (f >= 0) return f;
    }
    return idx;
  }
  function buttonText(btn, kind) {
    if (!btn) return '';
    return glyphKind(kind) === 'xbox' ? String(btn.xbox || btn.ps || '') : String(btn.ps || btn.xbox || '');
  }
  function noteText(btn, kind) {
    if (!btn) return '';
    return glyphKind(kind) === 'xbox' ? String(btn.noteXbox || btn.note || '') : String(btn.note || '');
  }
  // A "Try it" only for the actions the native side lists (whatsnew.info), or the known list when not in Omni.
  function canTry(item, actions) {
    return !!(item && typeof item.try === 'string' && item.try && (!actions || actions.indexOf(item.try) >= 0));
  }
  // The data file, checked: groups with a key, a title and items with a title.
  function validData(d) {
    return !!(d && d.schema === 1 && Array.isArray(d.groups) && d.groups.every(function (g) {
      return g && typeof g.key === 'string' && typeof g.title === 'string' && Array.isArray(g.items)
        && g.items.every(function (i) { return i && typeof i.title === 'string' && typeof i.text === 'string'; });
    }));
  }
  function hintText(lang, kind) { return t(lang, 'hint', GLYPHS[glyphKind(kind)]); }

  var api = { STR: STR, langOf: langOf, t: t, layout: layout, move: move, groupJump: groupJump, buttonText: buttonText,
    noteText: noteText, canTry: canTry, validData: validData, hintText: hintText };
  if (typeof module === 'object' && module.exports) { module.exports = api; return; }
  root.OmniWhatsNewPage = api;

  // --- the page ------------------------------------------------------------------------------------------------------
  var doc = root.document, host = root.omnibloomHost;
  var state = { lang: 'en', kind: 'playstation', info: null, data: null, cells: [], cards: [], idx: -1 };
  var $ = function (id) { return doc.getElementById(id); };
  var toastTimer = 0;

  function toast(msg) {
    var el = $('wn-toast');
    el.textContent = msg; el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 3000);
  }
  function el(tag, cls, text) {
    var e = doc.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function cols() { return root.innerWidth <= 900 ? 1 : 2; }
  function focusAt(i) {
    if (i < 0 || !state.cards[i]) return;
    if (state.cards[state.idx]) state.cards[state.idx].classList.remove('focus');
    state.idx = i;
    var c = state.cards[i];
    c.classList.add('focus');
    c.focus({ preventScroll: true });
    c.scrollIntoView({ block: 'nearest' });
    if (i === 0) root.scrollTo(0, 0);
  }
  function tryItem(item) {
    if (!canTry(item, state.info && state.info.actions)) return;
    if (!host || typeof host.request !== 'function') { toast(t(state.lang, 'notInOmni')); return; }
    host.request({ method: 'whatsnew.try', params: { url: item.try } }).then(function (r) {
      if (!r || !r.ok) toast(t(state.lang, 'failed'));
    });
  }
  function render() {
    var d = state.data, L = state.lang, box = $('wn-groups');
    doc.documentElement.lang = L;
    $('wn-title').textContent = t(L, 'title');
    doc.title = t(L, 'title');
    var v = state.info && state.info.version;
    $('wn-sub').textContent = v ? t(L, state.info.afterUpdate ? 'updated' : 'version', { v: v }) : '';
    $('wn-intro').textContent = d && d.intro || '';
    $('wn-hint').textContent = hintText(L, state.kind);
    box.textContent = '';
    state.cards = [];
    if (!d || !d.groups.length) { $('wn-empty').textContent = t(L, 'empty'); $('wn-empty').hidden = false; return; }
    d.groups.forEach(function (g) {
      var sec = el('section', 'wn-group');
      sec.appendChild(el('h2', '', STR[L][g.key] || g.title));
      var grid = el('div', 'wn-grid');
      g.items.forEach(function (item) {
        var card = el('article', 'wn-card');
        card.tabIndex = 0;
        card.appendChild(el('h3', '', item.title));
        card.appendChild(el('p', 'wn-text', item.text));
        var meta = el('div', 'wn-meta');
        var b = buttonText(item.button, state.kind), n = noteText(item.button, state.kind);
        if (b) meta.appendChild(el('span', 'wn-btn', b));
        if (n) meta.appendChild(el('span', 'wn-where', n));
        if (item.where) meta.appendChild(el('span', 'wn-where', t(L, 'where') + ' ' + item.where));
        if (canTry(item, state.info && state.info.actions)) meta.appendChild(el('span', 'wn-try', t(L, 'tryIt')));
        if (meta.childNodes.length) card.appendChild(meta);
        var at = state.cards.length;
        card.addEventListener('click', function () { focusAt(at); tryItem(item); });
        grid.appendChild(card);
        state.cards.push(card);
      });
      sec.appendChild(grid);
      box.appendChild(sec);
    });
    state.cells = layout(d.groups, cols());
    focusAt(Math.max(0, Math.min(state.idx, state.cards.length - 1)));
  }
  function itemAt(i) { var c = state.cells[i]; return c && state.data.groups[c.g].items[c.i]; }
  function controller(a) {
    if (!state.cards.length) return false;
    if (a === 'up' || a === 'down' || a === 'left' || a === 'right') { focusAt(move(state.cells, state.idx, a)); return true; }
    if (a === 'l1' || a === 'r1') { focusAt(groupJump(state.cells, state.idx, a === 'l1' ? -1 : 1)); return true; }
    if (a === 'cross') { tryItem(itemAt(state.idx)); return true; }
    return false;   // circle: Omni's own Back
  }
  root.omniMediaController = controller;
  root.omniPadController = controller;
  doc.addEventListener('keydown', function (e) {
    var a = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Enter: 'cross', PageUp: 'l1', PageDown: 'r1' }[e.key];
    if (a && controller(a)) e.preventDefault();
  });
  root.addEventListener('resize', function () { if (state.data) state.cells = layout(state.data.groups, cols()); });

  function start() {
    try { state.kind = glyphKind(host && typeof host.getGlyphs === 'function' ? host.getGlyphs() : root.localStorage.getItem('ob.glyphs')); } catch (_) {}
    var info = host && typeof host.request === 'function'
      ? host.request({ method: 'whatsnew.info' }).then(function (r) { return r && r.ok ? r.result : null; }, function () { return null; })
      : Promise.resolve(null);
    var data = fetch('whatsnew.json').then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    Promise.all([info, data]).then(function (res) {
      state.info = res[0];
      state.lang = langOf(state.info && state.info.lang || (root.navigator && root.navigator.language));
      state.data = validData(res[1]) ? res[1] : null;
      render();
    });
  }
  start();
})(typeof window !== 'undefined' ? window : this);
