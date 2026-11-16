// OMNI_AUTO_FULLSCREEN_V1: the page script on fake DOMs.
//   ./t s.mjs && node --check s.mjs && node test_auto_fullscreen_js.mjs s.mjs
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const mod = await import(pathToFileURL(path.resolve(process.argv[2])).href);
let failures = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++failures; console.log('FAIL', what); } };

function video(o) {
  return Object.assign({ paused: false, ended: false, muted: false, volume: 1, readyState: 4, w: 640, h: 360, calls: 0,
    getBoundingClientRect() { return { width: this.w, height: this.h }; } }, o);
}
function doc(videos, extra = {}) {
  return Object.assign({ fullscreenElement: null, getElementsByTagName: t => (t === 'video' ? videos : []) }, extra);
}
const run = (d, timer = setTimeout) => mod.run(d, timer);

{   // the largest playing audible video, promise resolves
  const small = video({ w: 100, h: 50, requestFullscreen() { this.calls++; return Promise.resolve(); } });
  const big = video({ w: 1280, h: 720, requestFullscreen() { this.calls++; return Promise.resolve(); } });
  const muted = video({ muted: true, w: 4000, h: 4000, requestFullscreen() { this.calls++; return Promise.resolve(); } });
  const r = await run(doc([small, muted, big]));
  check(r === 'omni-autofs;ok' && big.calls === 1 && small.calls === 0 && muted.calls === 0, 'largest ' + r);
}
{   // refused
  const v = video({ requestFullscreen() { return Promise.reject(Object.assign(new Error('x'), { name: 'NotAllowedError' })); } });
  const r = await run(doc([v]));
  check(r === 'omni-autofs;fail:NotAllowedError', 'reject ' + r);
}
{   // throws synchronously
  const v = video({ requestFullscreen() { throw new TypeError('no'); } });
  const r = await run(doc([v]));
  check(r === 'omni-autofs;fail:TypeError', 'throw ' + r);
}
{   // prefixed API without a promise
  const v = video({ webkitRequestFullscreen() { this.calls++; } });
  const r = await run(doc([v]));
  check(r === 'omni-autofs;sent' && v.calls === 1, 'prefixed ' + r);
}
{   // promise never settles: answers "sent" after the wait
  const v = video({ requestFullscreen() { return new Promise(() => {}); } });
  const fast = (f) => setTimeout(f, 5);
  const r = await run(doc([v]), fast);
  check(r === 'omni-autofs;sent', 'pending ' + r);
}
{   // nothing playing / paused / muted / not decoded / no API / already fullscreen
  check(await run(doc([])) === 'omni-autofs;novideo', 'none');
  check(await run(doc([video({ paused: true }), video({ volume: 0 }), video({ readyState: 1 }), video({ ended: true })])) === 'omni-autofs;novideo', 'skipped');
  check(await run(doc([video({})])) === 'omni-autofs;fail:noapi', 'noapi');
  check(await run(doc([video({})], { fullscreenElement: {} })) === 'omni-autofs;already', 'already');
  check(await run(doc([video({})], { webkitFullscreenElement: {} })) === 'omni-autofs;already', 'already webkit');
}
{   // a zero-size playing video still counts when it is the only one
  const v = video({ w: 0, h: 0, requestFullscreen() { this.calls++; return Promise.resolve(); } });
  check(await run(doc([v])) === 'omni-autofs;ok' && v.calls === 1, 'zero size');
}
console.log(`${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
