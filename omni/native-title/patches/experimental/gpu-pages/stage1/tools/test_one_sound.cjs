// OMNI_ONE_SOUND_V1: runs the pause script (written by ./t --emit <file>, test_one_sound.cpp) against a small fake DOM.
// node test_one_sound.cjs <file>
'use strict';
const fs = require('fs');
const vm = require('vm');
const file = process.argv[2];
if (!file) { console.log('usage: node test_one_sound.cjs <emitted script>'); process.exit(2); }
const src = fs.readFileSync(file, 'utf8');
let fails = 0, checks = 0;
function check(c, what) { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } }

function media(o) {
  const e = Object.assign({ paused: false, ended: false, muted: false, volume: 1, pausedCalls: 0, played: 0 }, o);
  e.pause = function () { this.pausedCalls++; this.paused = true; };
  e.play = function () { this.played++; this.paused = false; };
  return e;
}
function doc(elements, frames) {
  return {
    querySelectorAll(sel) { return sel === 'video,audio' ? elements : sel === 'iframe,frame' ? frames : []; },
  };
}
function run(document) {
  const ctx = { document };
  return vm.runInNewContext(src + '\nomniOsnResult;', ctx);
}

// a playing video, a paused audio, a muted preview, a volume-0 element, an ended one
{
  const v = media({}), a = media({ paused: true }), m = media({ muted: true }), z = media({ volume: 0 }), d = media({ ended: true });
  const r = run(doc([v, a, m, z, d], []));
  check(r === 'omni-os1\n1', 'one audible element paused: ' + JSON.stringify(r));
  check(v.paused && v.pausedCalls === 1, 'the playing video is paused');
  check(a.pausedCalls === 0 && m.pausedCalls === 0 && z.pausedCalls === 0 && d.pausedCalls === 0, 'silent / paused ones untouched');
  check(!m.paused && !z.paused, 'muted / 0 volume keep playing (silent)');
  check(v.played + a.played + m.played + z.played === 0, 'never plays');
}
// same-origin frames (depth up to 3), a cross-origin frame (contentDocument throws), depth 5 not reached
{
  const inner = media({}), deep = media({});
  const xo = { get contentDocument() { throw new Error('cross-origin'); } };
  let d5 = doc([deep], []);
  for (let i = 0; i < 4; ++i) d5 = doc([], [{ contentDocument: d5 }]);   // deep sits at depth 5
  const top = doc([], [{ contentDocument: doc([inner], []) }, xo, { contentDocument: d5 }]);
  const r = run(top);
  check(r === 'omni-os1\n1', 'frame element paused, cross-origin skipped: ' + JSON.stringify(r));
  check(inner.paused && !deep.paused, 'depth cap');
}
// nothing on the page; a throwing pause() still counts nothing and answers
{
  check(run(doc([], [])) === 'omni-os1\n0', 'empty page');
  const bad = media({});
  bad.pause = function () { throw new Error('nope'); };
  check(run(doc([bad], [])) === 'omni-os1\n0', 'pause() throwing');
}
// querySelectorAll throwing (odd document)
{
  check(run({ querySelectorAll() { throw new Error('x'); } }) === 'omni-os1\n0', 'broken document');
}
console.log((fails ? 'FAIL' : 'ok') + ': ' + checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
