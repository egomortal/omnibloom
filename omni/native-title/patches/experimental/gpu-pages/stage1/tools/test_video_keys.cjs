// OMNI_VIDEO_KEYS_V1: runs the full-screen video key scripts (OmniVideoKeys::script, written by
// `./t --emit <dir>` of test_video_keys.cpp) against a small fake DOM and checks what they do and answer.
//   node test_video_keys.cjs <dir>
// Not a browser: WebKit specifics (play() promise, seekable ranges, TextTrack modes, YouTube's player API) are modelled,
// not exercised.
'use strict';
const fs = require('fs');
const path = require('path');
const dir = process.argv[2];
if (!dir) { console.log('usage: node test_video_keys.cjs <dir>'); process.exit(2); }

let checks = 0, fails = 0;
function check(ok, what) { ++checks; if (!ok) { ++fails; console.log('FAIL ' + what); } }

function video(o) {
    const v = Object.assign({ tagName: 'VIDEO', paused: true, ended: false, readyState: 4, currentTime: 0, duration: 600,
        currentSrc: 'https://media.example/v.mp4', srcObject: null, playbackRate: 1, muted: false, seekable: null,
        textTracks: [], audioTracks: undefined, w: 1280, h: 720, plays: 0 }, o);
    v.play = function () { this.paused = false; this.plays++; return Promise.resolve(); };
    v.pause = function () { this.paused = true; };
    v.getBoundingClientRect = function () { return { width: this.w, height: this.h }; };
    return v;
}
function track(kind, label, language, mode = 'disabled') { return { kind, label, language, mode }; }
function classes(...names) { return { contains: (n) => names.includes(n) }; }
function button(cls) { return { tagName: 'BUTTON', classList: classes(cls), clicks: 0, click() { this.clicks++; } }; }
function resumeBox(time) {
    const yes = button('omni-resume-yes'), no = button('omni-resume-no');
    const q = { textContent: 'Resume from ' + time + '?' };
    const box = { yes, no, removed: false,
        contains(x) { return x === yes || x === no || x === box; },
        querySelector(sel) { return sel === '.omni-resume-yes' ? yes : sel === '.omni-resume-no' ? no : sel === '.omni-resume-q' ? q : null; } };
    return box;
}
// el: an element that holds videos / frames (a fullscreen <div>), or the document itself.
function holder(videos = [], frames = []) {
    return { tagName: 'DIV', querySelectorAll: (sel) => sel === 'video' ? videos : sel === 'iframe,frame' ? frames : [] };
}
function doc(o = {}) {
    const d = holder(o.videos || [], o.frames || []);
    d.fullscreenElement = o.fs || null;
    d.activeElement = o.active || null;
    d.box = o.box || null;
    d.ids = o.ids || {};
    d.sel = o.sel || {};
    d.getElementById = (id) => d.ids[id] || null;
    d.querySelector = (sel) => sel === '.omni-resume[data-omni-addon]' ? d.box : (d.sel[sel] || null);
    return d;
}
function crossOriginFrame() {
    return { tagName: 'IFRAME', get contentDocument() { throw new Error('SecurityError'); } };
}

function run(name, document, host = 'video.example', language = 'en-US') {
    const src = fs.readFileSync(path.join(dir, 'vk-' + name + '.js'), 'utf8');
    const f = new Function('document', 'location', 'navigator', 'return ' + src + ';');
    const out = f(document, { hostname: host }, { language });
    const p = String(out).split('\n');
    check(p.length === 12 && p[0] === 'omni-vk1', name + ': answer format (' + JSON.stringify(out).slice(0, 160) + ')');
    return { out: p[1], state: p[2], pos: p[3], dur: p[4], rate: p[5], muted: p[6], cap: p[7], aud: p[8], resume: p[9], note: p[10], yt: p[11] };
}

// --- no video ---
let d = doc();
let r = run('info', d);
check(r.out === 'none' && r.state === 'none' && r.pos === '' && r.yt === '0', 'info without video');
r = run('fwd10', d);
check(r.out === 'key', 'seek without video: the old key');
r = run('fwd60', d);
check(r.out === 'key' && r.state === 'none', 'R2 seek without video: nothing (the shell has no key for it)');
r = run('audio', d);
check(r.out === 'none' && r.note === '', 'audio without video');

// --- a plain page: play / pause, seek with clamps, mute ---
let v = video({ paused: false, currentTime: 100, playbackRate: 1.25 });
d = doc({ videos: [v] });
r = run('toggle', d);
check(v.paused && r.out === 'acted' && r.state === 'paused' && r.rate === '1.25', 'toggle pauses');
r = run('toggle', d);
check(!v.paused && v.plays === 1 && r.state === 'playing', 'toggle plays');
r = run('fwd10', d);
check(v.currentTime === 110 && r.out === 'acted' && r.pos === '110.00' && r.dur === '600.00', 'L1/R1: 10 s');
r = run('left', d);
check(v.currentTime === 105, 'D-pad: 5 s');
v.currentTime = 590; run('fwd60', d);
check(v.currentTime === 599.5, 'seek stops half a second before the end');
v.currentTime = 30; run('back60', d);
check(v.currentTime === 0, 'seek stops at 0');
r = run('mute', d);
check(v.muted && r.muted === '1' && r.out === 'acted', 'mute');
run('mute', d);
check(!v.muted, 'unmute');

// --- live stream: the seekable range ---
v = video({ paused: false, duration: Infinity, currentTime: 500, seekable: { length: 1, start: () => 100, end: () => 520 } });
d = doc({ videos: [v] });
r = run('fwd60', d);
check(v.currentTime === 520 && r.dur === 'live', 'live: clamped to the seekable end');
run('back60', d); run('back60', d); run('back60', d); run('back60', d); run('back60', d); run('back60', d); run('back60', d);
check(v.currentTime === 100, 'live: clamped to the seekable start');

// --- which video ---
const fsVideo = video({ paused: true, currentTime: 10, w: 1920, h: 1080 });
const adPlaying = video({ paused: false, currentTime: 3, w: 300, h: 170, currentSrc: 'https://ads.example/a.mp4' });
d = doc({ videos: [adPlaying, fsVideo], fs: fsVideo });
run('fwd10', d);
check(fsVideo.currentTime === 20 && adPlaying.currentTime === 3, 'the full-screen <video> itself');
const inA = video({ paused: true, currentTime: 50, w: 1920, h: 1080 }), inB = video({ paused: false, currentTime: 7, w: 200, h: 100 });
const outside = video({ paused: false, currentTime: 1 });
const fsDiv = holder([inA, inB]);
d = doc({ videos: [outside, inA, inB], fs: fsDiv });
run('fwd10', d);
check(inB.currentTime === 17 && inA.currentTime === 50 && outside.currentTime === 1, 'inside the full-screen element: the playing one');
inB.paused = true; run('fwd10', d);
check(inA.currentTime === 60, 'nothing playing: the largest');
const noSrc = video({ currentSrc: '', paused: false, w: 5000, h: 5000 });
d = doc({ videos: [noSrc, inA] });
run('fwd10', d);
check(inA.currentTime === 70 && noSrc.currentTime === 0, 'a video without a source is skipped');
// same-origin frame inside the full-screen element
const framed = video({ currentTime: 5 });
const frameDoc = holder([framed]);
const sameFrame = { tagName: 'IFRAME', contentDocument: frameDoc };
d = doc({ fs: sameFrame, frames: [sameFrame] });
run('fwd10', d);
check(framed.currentTime === 15, 'a same-origin frame in full screen');
// another site's frame in full screen: no video in reach, the key goes to the page
d = doc({ fs: crossOriginFrame(), videos: [video({ paused: false, currentTime: 9 })] });
r = run('toggle', d);
check(r.out === 'key' && r.state === 'none', 'a cross-origin frame: the old key');
r = run('info', d);
check(r.out === 'none', 'a cross-origin frame: info finds nothing');

// --- frame step ---
v = video({ paused: false, currentTime: 30 });
d = doc({ videos: [v] });
r = run('framefwd', d);
check(v.paused && Math.abs(v.currentTime - (30 + 1 / 30)) < 1e-9 && r.out === 'acted' && r.state === 'paused', 'frame +1 pauses');
run('frameback', d); run('frameback', d);
check(Math.abs(v.currentTime - (30 - 1 / 30)) < 1e-9, 'frame -1');

// --- captions (WebKit-rendered <track>) ---
const en = track('subtitles', 'English', 'en'), de = track('captions', 'Deutsch', 'de'), chap = track('chapters', 'Chapters', 'en');
v = video({ textTracks: [de, chap, en] });
d = doc({ videos: [v] });
r = run('captions', d);
check(en.mode === 'showing' && de.mode === 'disabled' && chap.mode === 'disabled' && r.cap === 'English' && r.out === 'acted', 'captions on: the browser language first');
r = run('captions', d);
check(en.mode === 'disabled' && r.cap === 'off', 'captions off');
r = run('captions', d);
check(en.mode === 'showing', 'captions on again: the last one');
r = run('captrack', d);
check(en.mode === 'disabled' && de.mode === 'disabled' && r.cap === 'off', 'track cycle: past the last is off');
r = run('captrack', d);
check(de.mode === 'showing' && r.cap === 'Deutsch', 'track cycle: the first');
r = run('captrack', d);
check(de.mode === 'disabled' && en.mode === 'showing' && r.cap === 'English' && chap.mode === 'disabled', 'track cycle: the next (chapters skipped)');
r = run('captions', d);
check(r.cap === 'off', 'off');
r = run('captions', d);
check(en.mode === 'showing', 'on: remembers the cycled track');
r = run('info', d);
check(r.cap === 'English', 'info reports the caption state');
v = video({ textTracks: [] });
d = doc({ videos: [v] });
check(run('captions', d).out === 'key', 'no tracks: the old c key');
check(run('captrack', d).out === 'key', 'no tracks: track cycle sends c too');
check(run('info', d).cap === '', 'no tracks: no caption state');

// --- audio tracks ---
const a1 = { label: 'English', language: 'en', enabled: true }, a2 = { label: '', language: 'es', enabled: false };
v = video({ audioTracks: [a1, a2] });
d = doc({ videos: [v] });
r = run('audio', d);
check(!a1.enabled && a2.enabled && r.aud === 'es' && r.out === 'acted', 'audio: next track');
r = run('audio', d);
check(a1.enabled && !a2.enabled && r.aud === 'English', 'audio: wraps');
check(run('info', d).aud === 'English', 'info reports the audio track');
v = video({ audioTracks: [a1] });
d = doc({ videos: [v] });
r = run('audio', d);
check(r.out === 'none' && r.note === 'noaudio' && r.aud === '', 'one audio track: nothing to switch');

// --- YouTube: its own keys stay, the player API for the rest ---
function ytPlayer(o = {}) {
    const P = Object.assign({ state: 1, t: 100, d: 600, seeks: [], caps: [], track: {}, audio: null, audioList: [],
        tracklist: [{ languageCode: 'en', displayName: 'English', vss_id: '.en' }, { languageCode: 'fr', displayName: 'French', vss_id: '.fr' }] }, o);
    P.getPlayerState = () => P.state;
    P.getCurrentTime = () => P.t;
    P.getDuration = () => P.d;
    P.seekTo = (t) => { P.seeks.push(t); P.t = t; };
    P.loadModule = () => {};
    P.unloadModule = () => { P.track = {}; P.caps.push('unload'); };
    P.getOption = (m, k) => k === 'tracklist' ? P.tracklist : P.track;
    P.setOption = (m, k, val) => { P.track = val; P.caps.push(val.languageCode || '{}'); };
    P.getAvailableAudioTracks = () => P.audioList;
    P.getAudioTrack = () => P.audio;
    P.setAudioTrack = (t) => { P.audio = t; };
    return P;
}
v = video({ paused: false, currentTime: 100 });
let P = ytPlayer();
const ccButton = { getAttribute: (n) => n === 'aria-pressed' ? 'true' : null };
d = doc({ videos: [v], ids: { movie_player: P }, sel: { '.ytp-subtitles-button': ccButton } });
r = run('toggle', d, 'www.youtube.com');
check(r.out === 'key' && !v.paused && r.yt === '1' && r.cap === 'on', 'YouTube: Square stays k (nothing done by the script)');
for (const n of ['back10', 'fwd10', 'left', 'right', 'captions', 'mute']) {
    const before = [v.currentTime, v.muted, P.seeks.length];
    r = run(n, d, 'www.youtube.com');
    check(r.out === 'key' && v.currentTime === before[0] && v.muted === before[1] && P.seeks.length === before[2], 'YouTube: ' + n + ' stays its key');
}
r = run('fwd60', d, 'www.youtube.com');
check(r.out === 'acted' && P.seeks[P.seeks.length - 1] === 160, 'YouTube: R2 + R1 seeks through the player');
P.t = 580; run('fwd60', d, 'www.youtube.com');
check(P.seeks[P.seeks.length - 1] === 599.5, 'YouTube: clamped');
r = run('framefwd', d, 'www.youtube.com');
check(r.out === 'key' && v.paused, 'YouTube: frame step pauses, then its "." key');
r = run('captrack', d, 'www.youtube.com');
check(r.out === 'acted' && P.track.languageCode === 'en' && r.cap === 'English', 'YouTube: caption track cycle, first');
r = run('captrack', d, 'www.youtube.com');
check(P.track.languageCode === 'fr' && r.cap === 'French', 'YouTube: caption track cycle, next');
r = run('captrack', d, 'www.youtube.com');
check(P.caps[P.caps.length - 1] === 'unload' && r.cap === 'off', 'YouTube: caption track cycle, off');
P.tracklist = [];
check(run('captrack', d, 'www.youtube.com').out === 'key', 'YouTube without a track list: the c key');
r = run('audio', d, 'www.youtube.com');
check(r.out === 'none' && r.note === 'noaudio', 'YouTube: one audio track');
const yA = { id: 'en.4', getLanguageInfo: () => ({ getName: () => 'English original' }) }, yB = { id: 'de.3', audioTrack: { displayName: 'Deutsch' } };
P.audioList = [yA, yB]; P.audio = yA;
r = run('audio', d, 'www.youtube.com');
check(P.audio === yB && r.aud === 'Deutsch' && r.out === 'acted', 'YouTube: audio track next');
r = run('audio', d, 'www.youtube.com');
check(P.audio === yA && r.aud === 'English original', 'YouTube: audio track wraps');
// youtube host without the player object (e.g. the mobile site): still its keys
d = doc({ videos: [video({ paused: false })] });
check(run('toggle', d, 'm.youtube.com').yt === '1', 'youtube host is YouTube');
check(run('toggle', d, 'notyoutube.com').yt === '0', 'a look-alike host is not');
check(run('toggle', d, 'www.youtube-nocookie.com').out === 'key', 'youtube-nocookie embeds keep their keys');

// --- the resume add-on's prompt ---
v = video({ paused: true, currentTime: 0, duration: 3000 });
let box = resumeBox('12:05');
d = doc({ videos: [v], box, active: box.yes });
r = run('info', d);
check(r.resume === '12:05\tyes', 'prompt reported with its focus');
r = run('right', d);
check(r.out === 'key' && v.currentTime === 0, 'D-pad with the prompt focused: its arrow key');
d.activeElement = box.no;
r = run('confirm', d);
check(box.no.clicks === 1 && box.yes.clicks === 0 && r.note === 'over' && r.out === 'acted', 'Cross: the focused button');
d.activeElement = null;
r = run('right', d);
check(r.out === 'acted' && v.currentTime === 5 && r.resume === '12:05\t-', 'prompt up but not focused: D-pad seeks');
r = run('confirm', d);
check(box.yes.clicks === 1 && r.note === 'resume', 'Cross, prompt not focused: Resume');
d.box = null;
r = run('confirm', d);
check(r.out === 'key' && r.resume === '', 'Cross without the prompt: the click at the pointer');
box = resumeBox('1:02:03');
d = doc({ videos: [v], box, active: box.yes });
check(run('info', d).resume === '1:02:03\tyes', 'hours in the prompt');

// --- robustness ---
v = video({ paused: false });
Object.defineProperty(v, 'currentTime', { get: () => 42, set: () => { throw new Error('InvalidStateError'); } });
d = doc({ videos: [v] });
r = run('fwd10', d);
check(r.out === 'key' && r.note === 'error', 'a throwing seek: the old key');
v = video({ paused: false, textTracks: [track('subtitles', 'Line\none\ttab', 'xx')] });
d = doc({ videos: [v] });
r = run('captions', d);
check(r.cap === 'Line one tab', 'labels: newlines and tabs flattened');
r = run('speed', d);
check(r.out === 'acted' && r.rate === '1.00', 'touchpad reads the speed');

console.log(checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
