/* OMNI_SOLITAIRE_V1: Klondike solitaire rules (draw one, unlimited passes). Pure: no DOM (tools/test_solitaire_page.cjs).
   State: { stock:[card], waste:[card], found:[[card]x4], tab:[[card]x7], moves, seed }; card = { s:0..3, r:1..13, up:bool }.
   Suits 0 spades, 1 hearts, 2 diamonds, 3 clubs (hearts and diamonds are red). */
(function (root, factory) { 'use strict'; var api = factory(); if (typeof module === 'object' && module.exports) module.exports = api; else root.OmniSolitaire = api; })(typeof globalThis !== 'undefined' ? globalThis : window, function () {
  'use strict';
  var KEY = 'omni-solitaire-v1', SUITS = ['♠', '♥', '♦', '♣'], RANKS = ['', 'A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'];
  var UNDO = 50;
  function red(c) { return c.s === 1 || c.s === 2; }
  function label(c) { return RANKS[c.r] + SUITS[c.s]; }
  function rng(seed) { var a = seed >>> 0; return function () { a = (a + 0x6D2B79F5) >>> 0; var t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function deal(seed) {
    var deck = [], s, r, i, rand = rng(seed);
    for (s = 0; s < 4; ++s) for (r = 1; r <= 13; ++r) deck.push({ s: s, r: r, up: false });
    for (i = deck.length - 1; i > 0; --i) { var j = Math.floor(rand() * (i + 1)), t = deck[i]; deck[i] = deck[j]; deck[j] = t; }
    var tab = [];
    for (i = 0; i < 7; ++i) { var col = deck.splice(0, i + 1); col[col.length - 1].up = true; tab.push(col); }
    return { stock: deck, waste: [], found: [[], [], [], []], tab: tab, moves: 0, seed: seed >>> 0 };
  }
  function top(p) { return p.length ? p[p.length - 1] : null; }
  function canFound(c, pile) { var t = top(pile); return t ? (t.s === c.s && c.r === t.r + 1) : c.r === 1; }
  function canStack(c, pile) { var t = top(pile); return t ? (t.up && red(t) !== red(c) && c.r === t.r - 1) : c.r === 13; }
  function flip(col) { var t = top(col); if (t && !t.up) t.up = true; }
  function won(st) { return st.found.every(function (f) { return f.length === 13; }); }
  // The stock: one card to the waste; an empty stock takes the waste back (face down, same order as dealt).
  function draw(st) {
    if (st.stock.length) { var c = st.stock.pop(); c.up = true; st.waste.push(c); }
    else if (st.waste.length) { st.stock = st.waste.reverse().map(function (c) { c.up = false; return c; }); st.waste = []; }
    else return false;
    st.moves++; return true;
  }
  // Sources: {kind:'waste'} | {kind:'found', i} | {kind:'tab', i, k} (k = first card of the moved run, face up).
  function cardsAt(st, src) {
    if (src.kind === 'waste') return st.waste.length ? [top(st.waste)] : [];
    if (src.kind === 'found') return st.found[src.i].length ? [top(st.found[src.i])] : [];
    if (src.kind === 'tab') { var col = st.tab[src.i]; if (src.k < 0 || src.k >= col.length || !col[src.k].up) return []; return col.slice(src.k); }
    return [];
  }
  function take(st, src, n) {
    if (src.kind === 'waste') st.waste.pop();
    else if (src.kind === 'found') st.found[src.i].pop();
    else { st.tab[src.i].splice(st.tab[src.i].length - n, n); flip(st.tab[src.i]); }
  }
  // Destinations: {kind:'found', i} | {kind:'tab', i}. Returns true when it moved.
  function move(st, src, dst) {
    var cards = cardsAt(st, src); if (!cards.length) return false;
    if (dst.kind === 'found') { if (cards.length !== 1 || src.kind === 'found' || !canFound(cards[0], st.found[dst.i])) return false; take(st, src, 1); st.found[dst.i].push(cards[0]); }
    else if (dst.kind === 'tab') { if ((src.kind === 'tab' && src.i === dst.i) || !canStack(cards[0], st.tab[dst.i])) return false; take(st, src, cards.length); Array.prototype.push.apply(st.tab[dst.i], cards); }
    else return false;
    st.moves++; return true;
  }
  // Square: the obvious move for a source: a foundation first (single card), else the first tableau column that takes it.
  function auto(st, src) {
    var cards = cardsAt(st, src), i; if (!cards.length) return false;
    if (cards.length === 1 && src.kind !== 'found') for (i = 0; i < 4; ++i) if (move(st, src, { kind: 'found', i: i })) return true;
    for (i = 0; i < 7; ++i) if (!(src.kind === 'tab' && src.i === i) && move(st, src, { kind: 'tab', i: i })) return true;
    return false;
  }
  // The first face-up card of a column (where a "whole run" pick starts); -1 for an empty column.
  function runStart(col) { for (var k = 0; k < col.length; ++k) if (col[k].up) return k; return -1; }
  function snapshot(st) { return JSON.stringify(st); }
  function valid(st) {
    if (!st || !Array.isArray(st.stock) || !Array.isArray(st.waste) || !Array.isArray(st.found) || st.found.length !== 4 || !Array.isArray(st.tab) || st.tab.length !== 7) return false;
    var seen = {}, n = 0, ok = true;
    function each(c) { if (!c || typeof c.s !== 'number' || typeof c.r !== 'number' || c.s < 0 || c.s > 3 || c.r < 1 || c.r > 13 || seen[c.s * 20 + c.r]) ok = false; else seen[c.s * 20 + c.r] = 1; n++; }
    st.stock.forEach(each); st.waste.forEach(each); st.found.forEach(function (f) { f.forEach(each); }); st.tab.forEach(function (t) { t.forEach(each); });
    return ok && n === 52;
  }
  function restore(text, seed) { try { var st = JSON.parse(text); if (valid(st)) return st; } catch (e) { /* new game */ } return deal(seed); }
  return Object.freeze({ KEY: KEY, UNDO: UNDO, label: label, red: red, deal: deal, draw: draw, move: move, auto: auto, cardsAt: cardsAt,
    canFound: canFound, canStack: canStack, won: won, runStart: runStart, snapshot: snapshot, restore: restore, valid: valid });
});
