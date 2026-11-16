// OMNI_YT_MEDIA_STOP_V1: runs the title's playback sampler (the OMNIFPS raw string of a PATCHED OmniBrowser.cpp) in a fake DOM.
//   node test_yt_media_stop_js.mjs <patched tree>/engine/entry/OmniBrowser.cpp
// Checks: per-sample `ad` (#movie_player.ad-showing) and `bufEnd` (end of the last buffered range), media() = the latest
// sample "<time> <ad>", '' before any video, the title's poll script (OmniYtMediaStop.h kPollScript) works against it,
// missing / throwing APIs do not break the sampler, and the sampler's own epoch / interval logic is unchanged.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';

const cpp = fs.readFileSync(process.argv[2], 'utf8');
const m = /R"OMNIFPS\(([\s\S]*?)\)OMNIFPS"/.exec(cpp);
if (!m) { console.log('FAIL: no OMNIFPS raw string in ' + process.argv[2]); process.exit(1); }
const src = m[1];
const hdr = fs.readFileSync(path.join(path.dirname(process.argv[2]), 'OmniYtMediaStop.h'), 'utf8');
const pm = /kPollScript =\s*"((?:[^"\\]|\\.)*)"/.exec(hdr);
const pollScript = pm ? JSON.parse('"' + pm[1] + '"') : null;
let fails = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };
check(src.includes('OMNI_YT_MEDIA_STOP_V1') && src.includes('__omniPlaybackProbe'), 'sampler is the patched one');
check(pollScript !== null, 'poll script found in OmniYtMediaStop.h');

function env() {
  let now = 0, timer = null;
  const player = { classList: { set: new Set(), contains(c) { return this.set.has(c); } } };
  const video = { videoWidth: 1920, videoHeight: 1080, currentTime: 0, paused: false, seeking: false, playbackRate: 1, readyState: 4,
    error: null, currentSrc: 'blob:x', frames: 0, ranges: [[0, 10]],
    getVideoPlaybackQuality() { return { totalVideoFrames: this.frames, droppedVideoFrames: 0 }; },
    get buffered() { const r = this.ranges; if (r === 'throw') throw new Error('no'); return { length: r.length, start: (i) => r[i][0], end: (i) => r[i][1] }; } };
  const st = { video: null, player: null, throwQuery: false };
  const document = { visibilityState: 'visible', querySelector(s) {
    if (s === 'video') return st.video;
    if (s === '#movie_player') { if (st.throwQuery) throw new Error('boom'); return st.player; }
    return null; } };
  const ctx = { document, performance: { now: () => now }, setInterval: (f) => { timer = f; return 1; }, clearInterval: () => { timer = null; },
    isFinite, Math, String, Number, Object, Error };
  ctx.window = ctx; ctx.top = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return { ctx, st, player, video, step(ms = 1000) { now += ms; if (timer) timer(); } };
}

const e = env();
const P = e.ctx.__omniPlaybackProbe;
check(P && typeof P.media === 'function', 'probe has media()');
check(P.media() === '', "media() '' before any video sample");
check(vm.runInContext(pollScript, e.ctx) === '', 'poll script answers \'\' before any video');
e.st.video = e.video; e.step();
let d = P.dump(), s = d.samples[d.samples.length - 1].video;
check(s.ad === false && s.bufEnd === 10, 'no #movie_player: ad false, bufEnd 10');
check(P.media() === '0.000 0', "media() '0.000 0' got " + P.media());
e.st.player = e.player; e.player.classList.set.add('ad-showing'); e.video.currentTime = 4.25; e.video.frames = 30; e.video.ranges = [[0, 5], [8, 21.5]];
e.step();
d = P.dump(); s = d.samples[d.samples.length - 1].video;
check(s.ad === true && s.bufEnd === 21.5, 'ad-showing: ad true, bufEnd = end of the LAST range');
check(P.media() === '4.250 1', "media() '4.250 1' got " + P.media());
check(vm.runInContext(pollScript, e.ctx) === '4.250 1', 'the title poll script returns media()');
e.player.classList.set.delete('ad-showing'); e.video.currentTime = 5.25; e.video.frames = 60; e.video.ranges = [];
e.step();
d = P.dump(); s = d.samples[d.samples.length - 1].video;
check(s.ad === false && s.bufEnd === null, 'ad gone, no buffered ranges: bufEnd null');
check(d.samples[d.samples.length - 1].interval && d.samples[d.samples.length - 1].interval.frames === 30, 'interval logic unchanged');
check(P.media() === '5.250 0', 'media() after the ad');
e.st.throwQuery = true; e.video.ranges = 'throw'; e.video.currentTime = 6.25;
e.step();
d = P.dump(); s = d.samples[d.samples.length - 1].video;
check(s.ad === false && s.bufEnd === null && s.time === 6.25, 'throwing querySelector / buffered: sampler goes on');
e.st.video = null; e.step();
check(P.media() === '', "video gone: media() ''");
check(d.schema === 1 && d.samplingMs === 1000, 'dump format unchanged');
const noProbe = vm.createContext({});
check(vm.runInContext(pollScript, noProbe) === '', "poll script on a page without the probe: ''");
console.log(`${checks} checks, ${fails} failed`);
process.exit(fails ? 1 : 0);
