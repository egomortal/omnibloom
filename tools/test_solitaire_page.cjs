// OMNI_SOLITAIRE_V1: Klondike rules.   node tools/test_solitaire_page.cjs
'use strict';
const a = require('node:assert/strict'), path = require('node:path');
const M = require(path.join(__dirname, '..', 'omni', 'pages', 'bundle-clean4', 'solitaire', 'model.js'));
let n = 0; const t = (name, fn) => { fn(); n++; };
const C = (s, r, up = true) => ({ s, r, up });
t('a deal has 52 distinct cards, 7 columns 1..7 with only the last face up, and is seeded', () => {
  const st = M.deal(42); a.ok(M.valid(st));
  st.tab.forEach((col, i) => { a.equal(col.length, i + 1); col.forEach((c, k) => a.equal(c.up, k === i)); });
  a.equal(st.stock.length, 24); a.deepEqual(M.deal(42), M.deal(42)); a.notDeepEqual(M.deal(42).tab, M.deal(43).tab);
});
t('foundation and tableau rules', () => {
  a.ok(M.canFound(C(0, 1), [])); a.ok(!M.canFound(C(0, 2), [])); a.ok(M.canFound(C(0, 2), [C(0, 1)])); a.ok(!M.canFound(C(1, 2), [C(0, 1)]));
  a.ok(M.canStack(C(0, 13), [])); a.ok(!M.canStack(C(0, 12), [])); a.ok(M.canStack(C(1, 6), [C(0, 7)])); a.ok(!M.canStack(C(3, 6), [C(0, 7)]));
  a.ok(!M.canStack(C(1, 6), [C(0, 7, false)]), 'never onto a face-down card');
});
t('draw and recycle', () => {
  const st = M.deal(1); const first = st.stock[st.stock.length - 1];
  a.ok(M.draw(st)); a.deepEqual(st.waste[0], { ...first, up: true });
  while (st.stock.length) M.draw(st); a.equal(st.waste.length, 24);
  a.ok(M.draw(st)); a.equal(st.stock.length, 24); a.equal(st.waste.length, 0); a.ok(st.stock.every(c => !c.up));
  a.equal(st.stock[st.stock.length - 1].r, first.r, 'same order as dealt');
});
t('moves: a run between columns flips the card left behind; illegal moves change nothing', () => {
  const st = { stock: [], waste: [], found: [[], [], [], []], moves: 0, seed: 0,
    tab: [[C(2, 5, false), C(0, 9), C(1, 8)], [C(1, 10)], [], [], [], [], []] };
  const before = JSON.stringify(st);
  a.ok(!M.move(st, { kind: 'tab', i: 0, k: 0 }, { kind: 'tab', i: 1 }), 'face-down start'); a.equal(JSON.stringify(st), before);
  a.ok(M.move(st, { kind: 'tab', i: 0, k: 1 }, { kind: 'tab', i: 1 }));
  a.deepEqual(st.tab[1].map(c => c.r), [10, 9, 8]); a.equal(st.tab[0].length, 1); a.ok(st.tab[0][0].up, 'flipped');
  a.ok(!M.move(st, { kind: 'tab', i: 1, k: 1 }, { kind: 'found', i: 0 }), 'only one card to a foundation');
  a.ok(!M.move(st, { kind: 'tab', i: 1, k: 2 }, { kind: 'tab', i: 1 }), 'not onto itself');
});
t('auto prefers a foundation, then a column; win detection', () => {
  const st = { stock: [], waste: [C(0, 1)], found: [[], [], [], []], moves: 0, seed: 0, tab: [[C(1, 2)], [], [], [], [], [], []] };
  a.ok(M.auto(st, { kind: 'waste' })); a.equal(st.found[0].length, 1);
  const w = { stock: [], waste: [], tab: [[], [], [], [], [], [], []], moves: 0, seed: 0, found: [0, 1, 2, 3].map(s => Array.from({ length: 13 }, (_, r) => C(s, r + 1))) };
  a.ok(M.won(w)); a.ok(!M.won(M.deal(5)));
});
t('restore: a saved game comes back; junk or a broken deck starts a new one', () => {
  const st = M.deal(9); M.draw(st); const back = M.restore(M.snapshot(st), 1); a.deepEqual(back, st);
  a.ok(M.valid(M.restore('not json', 7))); const broken = JSON.parse(M.snapshot(st)); broken.tab[0].push(broken.tab[1][0]);
  a.deepEqual(M.restore(JSON.stringify(broken), 7), M.deal(7));
});
console.log('SOLITAIRE PASS: ' + n + ' checks');
