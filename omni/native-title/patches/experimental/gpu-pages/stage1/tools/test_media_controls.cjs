// OMNI_MEDIA_CONTROLS_V1: runs the "Now playing" scripts (OmniMediaControls::script, written by
// `./t --emit <dir>` of test_media_controls.cpp) against a small fake DOM and checks what they do and answer.
//   node test_media_controls.cjs <dir>
// Not a browser: WebKit specifics (play() promise, seekable ranges, selector support) are modelled, not exercised.
'use strict';
const fs = require('fs');
const path = require('path');
const dir = process.argv[2];
if (!dir) { console.log('usage: node test_media_controls.cjs <dir>'); process.exit(2); }

let checks = 0, fails = 0;
function check(ok, what) { ++checks; if (!ok) { ++fails; console.log('FAIL ' + what); } }

function media(o) {
    const m = Object.assign({ paused: true, ended: false, readyState: 4, currentTime: 0, duration: 200, currentSrc: '',
        srcObject: null, seekable: null, played: 0 }, o);
    m.play = function () { this.paused = false; this.played++; return Promise.resolve(); };
    m.pause = function () { this.paused = true; };
    return m;
}
function button(rects = 1, attrs = {}) {
    return { disabled: false, clicks: 0, click() { this.clicks++; }, getAttribute(n) { return n in attrs ? attrs[n] : null; },
        getClientRects() { return { length: rects }; } };
}
function doc(o) {
    const d = { title: o.title || '', media: o.media || [], frames: o.frames || [], buttons: o.buttons || {}, keys: [] };
    d.body = { dispatchEvent(e) { d.keys.push(e.type + ':' + e.key + ':' + e.keyCode); return true; } };
    d.activeElement = null;
    d.querySelectorAll = (sel) => sel === 'video,audio' ? d.media : sel === 'iframe,frame' ? d.frames : [];
    d.querySelector = (sel) => d.buttons[sel] || null;
    return d;
}
class KeyboardEvent { constructor(type, init) { this.type = type; Object.assign(this, init); } }

function run(name, document, navigator = {}) {
    const src = fs.readFileSync(path.join(dir, 'np-' + name + '.js'), 'utf8');
    const f = new Function('document', 'navigator', 'KeyboardEvent', 'return ' + src + ';');
    const out = f(document, navigator, KeyboardEvent);
    const parts = String(out).split('\n');
    check(parts.length === 11 && parts[0] === 'omni-np1', name + ': answer format (' + JSON.stringify(out).slice(0, 120) + ')');
    return { state: parts[1], pos: parts[2], dur: parts[3], prev: parts[4], next: parts[5], did: parts[6], src: parts[7],
        title: parts[8], artist: parts[9], doc: parts[10] };
}

// probe: no media
let d = doc({ title: 'Plain page' });
let r = run('probe', d);
check(r.state === 'none' && r.doc === 'Plain page' && r.did === '0', 'probe without media');

// probe: playing video picked over a paused one; metadata from mediaSession when present
const paused = media({ currentSrc: 'http://192.0.2.10/a.mp4', currentTime: 50 });
const playing = media({ currentSrc: 'http://192.0.2.10/b.mp4', paused: false, currentTime: 65.25, duration: 240 });
d = doc({ title: 'Doc\ntitle', media: [paused, playing] });
r = run('probe', d, { mediaSession: { metadata: { title: 'Song\r\nName', artist: 'Band' } } });
check(r.state === 'playing' && r.pos === '65.3' && r.dur === '240.0' && r.src === 'http://192.0.2.10/b.mp4', 'probe picks the playing element');
check(r.title === 'Song Name' && r.artist === 'Band' && r.doc === 'Doc title', 'probe metadata, newlines flattened');

// toggle pauses the playing one, then plays it again (S pins the element read at open)
r = run('toggle', d);
check(playing.paused && r.state === 'paused' && r.did === '1', 'toggle pauses');
r = run('toggle-src', d);   // S = b.mp4
check(!playing.paused && playing.played === 1 && r.state === 'playing', 'toggle with src plays the same element');
check(paused.paused, 'the other element is untouched');

// nothing playing: the most advanced element with a source is used
const idle1 = media({ currentSrc: '', currentTime: 0 });
const idle2 = media({ currentSrc: 'http://10.0.0.4/c.mp3', currentTime: 12, duration: 100 });
d = doc({ media: [idle1, idle2] });
r = run('toggle', d);
check(!idle2.paused && r.src === 'http://10.0.0.4/c.mp3', 'toggle resumes the paused element with progress');

// seeking: clamped to [0, duration - 0.5]
const v = media({ currentSrc: 'x', paused: false, currentTime: 5, duration: 100 });
d = doc({ media: [v] });
run('back', d); check(v.currentTime === 0, 'back clamps at 0');
v.currentTime = 50; run('forward', d); check(v.currentTime === 60, 'forward +10');
v.currentTime = 95; run('forward', d); check(v.currentTime === 99.5, 'forward clamps before the end');
// live: duration Infinity, seekable window
const live = media({ currentSrc: 'live', paused: false, currentTime: 300, duration: Infinity,
    seekable: { length: 1, start: () => 250, end: () => 305 } });
d = doc({ media: [live] });
r = run('forward', d); check(live.currentTime === 305 && r.dur === 'live', 'live forward clamps to the seekable end');
live.currentTime = 255; run('back', d); check(live.currentTime === 250, 'live back clamps to the seekable start');

// next / previous: the site's button first, else the media key
const next = button(), prev = button();
const track = media({ currentSrc: 's', paused: false, currentTime: 2, duration: 180 });
d = doc({ media: [track], buttons: { '.ytp-next-button': next, '.ytp-prev-button': prev } });
r = run('next', d); check(next.clicks === 1 && r.did === '2' && r.next === '1' && r.prev === '1', 'next clicks the site button');
r = run('prev', d); check(prev.clicks === 1 && r.did === '2', 'prev at the start clicks the previous button');
track.currentTime = 30; r = run('prev', d); check(track.currentTime === 0 && prev.clicks === 1 && r.did === '1', 'prev later restarts');
const hidden = button(0), disabled = button(1, { 'aria-disabled': 'true' });
d = doc({ media: [media({ currentSrc: 's', paused: false })], buttons: { '.ytp-next-button': hidden, 'button[aria-label^="Next" i]': disabled } });
r = run('next', d);
check(hidden.clicks === 0 && disabled.clicks === 0 && r.did === '3' && r.next === '0', 'hidden / disabled buttons are skipped');
check(d.keys.join(',') === 'keydown:MediaTrackNext:176,keyup:MediaTrackNext:176', 'next sends the media key');
const spotify = button();
d = doc({ media: [], buttons: { '[data-testid="control-button-skip-forward"]': spotify } });
r = run('next', d); check(spotify.clicks === 1 && r.state === 'none', 'next works without a reachable element');
d = doc({});
r = run('prev', d); check(d.keys[0] === 'keydown:MediaTrackPrevious:177' && r.did === '3', 'prev key without media');

// same-origin frames are searched; cross-origin ones (contentDocument throws) are skipped
const inner = media({ currentSrc: 'inner', paused: false });
const frameDoc = doc({ media: [inner] });
const crossFrame = {}; Object.defineProperty(crossFrame, 'contentDocument', { get() { throw new Error('SecurityError'); } });
d = doc({ frames: [crossFrame, { contentDocument: frameDoc }] });
r = run('toggle', d); check(inner.paused && r.src === 'inner', 'element in a same-origin frame');

// a page that throws from play() / currentTime still answers
const evil = media({ currentSrc: 'e' }); evil.play = () => { throw new Error('NotAllowed'); };
d = doc({ media: [evil] });
r = run('toggle', d); check(r.state === 'paused', 'play() throwing still answers');

// escaping: the src literal survives quotes, backslashes, newlines, </script>, U+2028
const esc = media({ currentSrc: 'a"b\\c\n</script> ', paused: true });
const other = media({ currentSrc: 'z', paused: false });
d = doc({ media: [other, esc] });
r = run('escape', d);
check(r.src === 'a"b\\c </script> ', 'escaped src matched the element exactly (' + JSON.stringify(r.src) + ')');

console.log(checks - fails + '/' + checks + ' checks passed');
process.exit(fails ? 1 : 0);
