// OMNI_PAUSE_INFO_V1: runs the pause info script (OmniPauseInfo::script, written by `./t --emit <dir>` of
// test_pause_info.cpp) against a small fake DOM and checks its answer.
//   node test_pause_info.cjs <dir>
// Not a browser: the video keys script's own cases are test_video_keys.cjs's; this checks the wrapper (title + answer).
'use strict';
const fs = require('fs');
const path = require('path');
const dir = process.argv[2];
if (!dir) { console.log('usage: node test_pause_info.cjs <dir>'); process.exit(2); }

let checks = 0, fails = 0;
function check(ok, what) { ++checks; if (!ok) { ++fails; console.log('FAIL ' + what); } }

function video(o) {
    const v = Object.assign({ tagName: 'VIDEO', paused: true, ended: false, readyState: 4, currentTime: 0, duration: 600,
        currentSrc: 'https://media.example/v.mp4', srcObject: null, playbackRate: 1, muted: false, seekable: null,
        textTracks: [], audioTracks: undefined, w: 1280, h: 720, plays: 0, pauses: 0 }, o);
    v.play = function () { this.paused = false; this.plays++; return Promise.resolve(); };
    v.pause = function () { this.paused = true; this.pauses++; };
    v.getBoundingClientRect = function () { return { width: this.w, height: this.h }; };
    return v;
}
function holder(videos = []) {
    return { tagName: 'DIV', querySelectorAll: (sel) => sel === 'video' ? videos : [] };
}
function doc(o = {}) {
    const d = holder(o.videos || []);
    d.fullscreenElement = o.fs || null;
    d.activeElement = null;
    d.getElementById = () => null;
    d.querySelector = () => null;
    return d;
}

const src = fs.readFileSync(path.join(dir, 'pzi.js'), 'utf8');
function run(document, mediaSession) {
    const f = new Function('document', 'location', 'navigator', 'return ' + src + ';');
    const out = String(f(document, { hostname: 'video.example' }, { language: 'en-US', mediaSession }));
    const p = out.split('\n');
    check(p.length === 14 && p[0] === 'omni-pzi1' && p[2] === 'omni-vk1', 'answer format (' + JSON.stringify(out).slice(0, 160) + ')');
    return { title: p[1], out: p[3], state: p[4], pos: p[5], dur: p[6], rate: p[7] };
}

{   // a paused full-screen video with a Media Session title: read only, nothing touched
    const v = video({ currentTime: 725, duration: 2710, playbackRate: 1.5 });
    const a = run(doc({ fs: v }), { metadata: { title: 'Big\nBuck\tBunny' } });
    check(a.title === 'Big Buck Bunny', 'title cleaned: ' + a.title);
    check(a.state === 'paused' && a.pos === '725.00' && a.dur === '2710.00' && a.rate === '1.50', 'state: ' + JSON.stringify(a));
    check(v.plays === 0 && v.pauses === 0 && v.currentTime === 725, 'the video is not touched');
}
{   // no Media Session: empty title; the video inside the full-screen element
    const v = video({ currentTime: 10 });
    const a = run(doc({ fs: holder([v]) }), undefined);
    check(a.title === '' && a.state === 'paused', 'no media session: ' + JSON.stringify(a));
}
{   // a Media Session whose metadata throws
    const ms = {}; Object.defineProperty(ms, 'metadata', { get() { throw new Error('nope'); } });
    const a = run(doc({ videos: [video({})] }), ms);
    check(a.title === '' && a.state === 'paused', 'throwing metadata');
}
{   // no video at all
    const a = run(doc({}), null);
    check(a.state === 'none' && a.out === 'none', 'no video: ' + JSON.stringify(a));
}
{   // a long title is cut to 300
    const a = run(doc({ videos: [video({})] }), { metadata: { title: 'x'.repeat(500) } });
    check(a.title.length === 300, 'title cut to 300');
}
console.log(checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
