// OMNI_WHATSNEW_V1: node tests for the What's new page's pure helpers and its generated data.
// node tools/test_whatsnew_page.cjs
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '..', 'omni', 'pages', 'bundle-clean4', 'whatsnew');
const P = require(path.join(dir, 'whatsnew.js'));
let n = 0;
const test = (name, fn) => { fn(); n++; };

const groups = [{ key: 'tabs', title: 'Tabs', items: [{}, {}, {}] }, { key: 'video', title: 'Video', items: [{}] },
  { key: 'empty', title: 'E', items: [] }, { key: 'privacy', title: 'Privacy', items: [{}, {}] }];

test('layout: rows per group, two columns', () => {
  const c = P.layout(groups, 2);
  assert.deepStrictEqual(c.map(x => [x.g, x.i, x.row, x.col]),
    [[0, 0, 0, 0], [0, 1, 0, 1], [0, 2, 1, 0], [1, 0, 2, 0], [3, 0, 3, 0], [3, 1, 3, 1]]);
  assert.strictEqual(P.layout(groups, 1).length, 6);
  assert.strictEqual(P.layout(groups, 1)[5].row, 5);
  assert.deepStrictEqual(P.layout([], 2), []);
  assert.deepStrictEqual(P.layout(null, 2), []);
});

test('move: D-pad between cards', () => {
  const c = P.layout(groups, 2);
  assert.strictEqual(P.move(c, 0, 'right'), 1);
  assert.strictEqual(P.move(c, 1, 'right'), 1);      // row end
  assert.strictEqual(P.move(c, 1, 'left'), 0);
  assert.strictEqual(P.move(c, 0, 'left'), 0);
  assert.strictEqual(P.move(c, 2, 'right'), 2);      // a lone card: the next group's card is not "right"
  assert.strictEqual(P.move(c, 1, 'down'), 2);       // column 1 -> the shorter row's last card
  assert.strictEqual(P.move(c, 2, 'down'), 3);       // into the next group
  assert.strictEqual(P.move(c, 3, 'down'), 4);       // the empty group is skipped
  assert.strictEqual(P.move(c, 5, 'up'), 3);
  assert.strictEqual(P.move(c, 3, 'up'), 2);
  assert.strictEqual(P.move(c, 0, 'up'), 0);
  assert.strictEqual(P.move(c, 5, 'down'), 5);
  assert.strictEqual(P.move(c, 0, 'cross'), 0);
  assert.strictEqual(P.move(c, 99, 'down'), 0);
  assert.strictEqual(P.move([], 0, 'down'), -1);
});

test('groupJump: L1 / R1', () => {
  const c = P.layout(groups, 2);
  assert.strictEqual(P.groupJump(c, 0, 1), 3);
  assert.strictEqual(P.groupJump(c, 3, 1), 4);       // empty group skipped
  assert.strictEqual(P.groupJump(c, 4, 1), 4);       // last group
  assert.strictEqual(P.groupJump(c, 5, -1), 4);      // own group's first card first
  assert.strictEqual(P.groupJump(c, 4, -1), 3);
  assert.strictEqual(P.groupJump(c, 2, -1), 0);
  assert.strictEqual(P.groupJump(c, 0, -1), 0);
});

test('buttons, notes, Try it, language', () => {
  const b = { ps: 'Hold Cross', xbox: 'Hold A', note: '{x} Cross', noteXbox: 'A' };
  assert.strictEqual(P.buttonText(b, 'playstation'), 'Hold Cross');
  assert.strictEqual(P.buttonText(b, 'xbox'), 'Hold A');
  assert.strictEqual(P.buttonText(b, 'weird'), 'Hold Cross');
  assert.strictEqual(P.buttonText(null, 'xbox'), '');
  assert.strictEqual(P.noteText(b, 'xbox'), 'A');
  assert.strictEqual(P.canTry({ try: 'tabs' }, ['tabs']), true);
  assert.strictEqual(P.canTry({ try: 'tabs' }, ['history']), false);
  assert.strictEqual(P.canTry({ try: 'tabs' }, null), true);
  assert.strictEqual(P.canTry({ try: null }, null), false);
  assert.strictEqual(P.langOf('fr-CA'), 'fr');
  assert.strictEqual(P.langOf('ja'), 'en');
  assert.strictEqual(P.langOf(undefined), 'en');
  assert.strictEqual(P.t('es', 'tryIt'), 'Probar');
  assert.strictEqual(P.t('xx', 'tryIt'), 'Try it');
  assert.strictEqual(P.t('de', 'updated', { v: '0.5.4' }), 'Omni wurde auf 0.5.4 aktualisiert');
  assert.ok(P.hintText('en', 'xbox').includes('A: try it') && P.hintText('en', 'xbox').includes('LB / RB'));
  assert.ok(P.hintText('en', 'playstation').includes('Circle: back'));
  for (const lang of Object.keys(P.STR))
    assert.deepStrictEqual(Object.keys(P.STR[lang]).sort(), Object.keys(P.STR.en).sort(), lang + ' keys');
});

test('the generated data file', () => {
  const d = JSON.parse(fs.readFileSync(path.join(dir, 'whatsnew.json'), 'utf8'));
  assert.ok(P.validData(d));
  assert.match(d.id, /^[0-9a-f]{16}$/);
  const raw = fs.readFileSync(path.join(dir, 'whatsnew.json'), 'utf8');
  assert.ok(raw.indexOf('"id"') < raw.indexOf('"groups"'));   // the engine reads the first "id"
  const actions = ['controls', 'options', 'settings', 'site-settings', 'tabs', 'history', 'downloads', 'reading-list', 'bookmarks', 'screenshots'];
  for (const g of d.groups) {
    assert.ok(P.STR.en[g.key], 'group ' + g.key + ' has a heading');
    for (const i of g.items) {
      if (i.try !== null) assert.ok(actions.includes(i.try), i.try);
      if (i.button) assert.ok(i.button.ps && i.button.xbox);
    }
  }
  assert.strictEqual(P.validData({ schema: 2, groups: [] }), false);
  assert.strictEqual(P.validData({ schema: 1, groups: [{ key: 'a', title: 'A', items: [{ title: 1 }] }] }), false);
});

test('the page never reaches the network', () => {
  const js = fs.readFileSync(path.join(dir, 'whatsnew.js'), 'utf8');
  const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
  assert.ok(!/https?:\/\//.test(js) && !/https?:\/\//.test(html));
  assert.deepStrictEqual(js.match(/fetch\(([^)]*)\)/g), ["fetch('whatsnew.json')"]);
  assert.ok(!/innerHTML|eval\(|new Function/.test(js));
  assert.ok(html.includes("script-src 'self'") && !/<script>/.test(html));
});

console.log('all ' + n + ' whatsnew page tests passed');
