// OMNI_PLAYBACK_SPEED_V1: runs the scripts written by test_playback_speed.cpp (./t <dir>) against a small fake DOM.
//   node test_playback_speed.cjs <dir>
'use strict';
const fs = require('fs');
const path = require('path');
const dir = process.argv[2];
let failures = 0, checks = 0;
function check(c, what) { ++checks; if (!c) { ++failures; console.log('FAIL: ' + what); } }

function media(src, opts = {}) {
    return Object.assign({ currentSrc: src, srcObject: null, playbackRate: 1, defaultPlaybackRate: 1, preservesPitch: false, paused: false }, opts);
}
function doc(list, frames = [], player = null) {
    return {
        querySelectorAll(sel) { return sel === 'video,audio' ? list : frames; },
        getElementById(id) { return id === 'movie_player' ? player : null; },
    };
}
function run(file, document) {
    const src = fs.readFileSync(path.join(dir, file), 'utf8');
    return new Function('document', 'return ' + src.trim())(document);
}

{   // plain page + a same-origin frame + a cross-origin frame
    const a = media('https://x/a.mp4'), b = media('blob:https://x/1'), none = media('');
    const inner = media('https://x/b.mp3');
    const frames = [{ contentDocument: doc([inner]) }, { get contentDocument() { throw new Error('cross-origin'); } }];
    const out = run('speed-150.js', doc([a, b, none], frames)).split('\n');
    check(out[0] === 'omni-sp1' && out[1] === '3' && out[2] === '0' && out[3] === '0' && out[4] === '4', 'answer ' + out.join('|'));
    check(a.playbackRate === 1.5 && b.playbackRate === 1.5 && inner.playbackRate === 1.5 && none.playbackRate === 1, 'rates');
    check(a.preservesPitch === true && a.webkitPreservesPitch === true && a.defaultPlaybackRate === 1.5, 'pitch / default');
}
{   // YouTube player API
    let asked = null;
    const v = media('blob:https://www.youtube.com/9');
    const out = run('speed-150.js', doc([v], [], { setPlaybackRate(r) { asked = r; } })).split('\n');
    check(asked === 1.5 && out[3] === '1' && v.playbackRate === 1.5, 'youtube ' + out.join('|'));
}
{   // MSE not available (holepunch-v5-disabled.flag): MSE left alone, YouTube API not called, files still set
    let asked = null;
    const m = media('blob:https://x/1'), f = media('https://x/a.mp4'), so = media('', { srcObject: {} });
    const out = run('speed-200-nomse.js', doc([m, f, so], [], { setPlaybackRate(r) { asked = r; } })).split('\n');
    check(out[1] === '1' && out[2] === '2' && out[3] === '0', 'nomse ' + out.join('|'));
    check(m.playbackRate === 1 && so.playbackRate === 1 && f.playbackRate === 2 && asked === null, 'nomse rates');
    const back = run('speed-100-nomse.js', doc([m], [], { setPlaybackRate(r) { asked = r; } })).split('\n');
    check(back[1] === '1' && back[2] === '0' && asked === 1, 'back to 1x always applies ' + back.join('|'));
}
{   // a throwing element does not stop the others
    const bad = media('https://x/a.mp4'); Object.defineProperty(bad, 'playbackRate', { set() { throw new Error('no'); }, get() { return 1; } });
    const good = media('https://x/b.mp4');
    const out = run('speed-150.js', doc([bad, good])).split('\n');
    check(out[1] === '1' && good.playbackRate === 1.5, 'throwing element ' + out.join('|'));
}
{   // nothing on the page
    const out = run('speed-150.js', doc([])).split('\n');
    check(out.join('|') === 'omni-sp1|0|0|0|0', 'empty ' + out.join('|'));
}
console.log(checks + ' checks, ' + failures + ' failures');
process.exit(failures ? 1 : 0);
