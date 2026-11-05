// OMNI_HDR_CAPS_V1 host test: runs the shell's page script (extracted from the C++ source, or hdr_caps.js) against a
// model of the child's answers (OmniMediaCaps.h: vp09 with transfer 16/18 refused; decodingInfo with HDR fields refused;
// WebKit's own matchMedia: dynamic-range high false) and checks what a site such as YouTube concludes.
const fs = require('fs'), vm = require('vm');
let src = process.argv[2] ? fs.readFileSync(process.argv[2], 'utf8') : fs.readFileSync(__dirname + '/hdr_caps.js', 'utf8');
const m = /R"OMNIHDRJS\(([\s\S]*?)\)OMNIHDRJS"/.exec(src); if (m) src = m[1];
let pass = 0, fail = 0; const ok = (c, n) => { if (c) pass++; else { fail++; console.log('FAIL ' + n); } };
function engineVp9(t) { const r = /vp09\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)/.exec(t); if (!r) return /vp9|avc1|mp4a|opus/.test(t); return !(r[6] === '16' || r[6] === '18') && (r[1] === '00' || r[1] === '02'); }
function make(cap) {
  const added = [];
  class MediaSource { static isTypeSupported(t) { return engineVp9(t); } addSourceBuffer(t) { if (!engineVp9(t)) throw new Error('NotSupportedError'); added.push(t); return {}; } }
  class SourceBuffer { changeType(t) { if (!engineVp9(t)) throw new Error('NotSupportedError'); added.push('ct:' + t); } }
  class HTMLMediaElement { canPlayType(t) { return engineVp9(t) ? 'probably' : ''; } }
  class Screen {} Object.defineProperty(Screen.prototype, 'colorDepth', { configurable: true, get() { return 24; } }); Object.defineProperty(Screen.prototype, 'pixelDepth', { configurable: true, get() { return 24; } });
  const evalMQ = q => { const parts = q.split(/\s+and\s+/); return parts.every(p => { p = p.trim(); if (p === '(min-width:0px)' || p === 'screen') return true; if (/^\(max-width:0px\)$/.test(p)) return false; if (/^\(min-width:1px\)$/.test(p)) return true; if (/dynamic-range:\s*high|color-gamut:\s*(p3|rec2020)/.test(p)) return false; return true; }); };
  const win = { MediaSource, SourceBuffer, HTMLMediaElement, Screen, screen: new Screen(), Promise, Object, String, RegExp,
    navigator: { mediaCapabilities: { decodingInfo(c) { const v = c.video || {}; const hdr = !!(v.hdrMetadataType || (v.colorGamut && v.colorGamut !== 'srgb') || (v.transferFunction && v.transferFunction !== 'srgb')); return Promise.resolve({ supported: !hdr && engineVp9(v.contentType), smooth: true, powerEfficient: true }); } } },
    matchMedia(q) { return { matches: evalMQ(q), media: q }; } };
  win.window = win; vm.createContext(win); vm.runInContext(src.replace('__CAP__', String(cap)).replace('%d', String(cap)), win);
  return { win, added };
}
const HDR = 'video/webm; codecs="vp09.02.51.10.01.09.16.09.00"', HLG = 'video/webm; codecs="vp09.02.51.10.01.09.18.09.00"', SDR10 = 'video/webm; codecs="vp09.02.51.10.01.01.01.01.00"', SDR8 = 'video/webm; codecs="vp09.00.51.08.01.01.01.01.00"';
(async () => {
  for (const cap of [0, 1]) {
    const { win, added } = make(cap), W = s => vm.runInContext(s, win);
    const ytHdr = W(`window.matchMedia('(dynamic-range: high)').matches || (window.screen.pixelDepth > 24 && window.matchMedia('(color-gamut: p3)').matches)`);
    ok(ytHdr === !!cap, `cap=${cap}: YouTube's display check says HDR=${ytHdr}`);
    ok(W(`window.matchMedia('(video-dynamic-range: high)').matches`) === !!cap, `cap=${cap}: video-dynamic-range`);
    ok(W(`window.matchMedia('(dynamic-range: standard)').matches`) === true, `cap=${cap}: dynamic-range standard`);
    ok(W(`window.matchMedia('screen and (dynamic-range: high)').media`) === 'screen and (dynamic-range: high)', `cap=${cap}: media string kept`);
    ok(W(`MediaSource.isTypeSupported(${JSON.stringify(HDR)})`) === !!cap, `cap=${cap}: isTypeSupported VP9.2 PQ`);
    ok(W(`MediaSource.isTypeSupported(${JSON.stringify(HLG)})`) === !!cap, `cap=${cap}: isTypeSupported VP9.2 HLG`);
    ok(W(`MediaSource.isTypeSupported(${JSON.stringify(SDR10)})`) === true && W(`MediaSource.isTypeSupported(${JSON.stringify(SDR8)})`) === true, `cap=${cap}: SDR types unchanged`);
    ok(W(`MediaSource.isTypeSupported('video/webm; codecs="vp09.03.51.10.01.09.16.09.00"')`) === false, `cap=${cap}: profile 3 still refused by the engine`);
    ok(W(`new window.HTMLMediaElement().canPlayType(${JSON.stringify(HDR)})`) === (cap ? 'probably' : ''), `cap=${cap}: canPlayType`);
    ok(W(`window.screen.colorDepth`) === (cap ? 30 : 24), `cap=${cap}: colorDepth`);
    let threw = false; try { W(`new MediaSource().addSourceBuffer(${JSON.stringify(HDR)})`); } catch (e) { threw = true; }
    ok(threw === !cap && (!cap || added[0] === 'video/webm; codecs="vp09.02.51.10.01.09.01.09.00"'), `cap=${cap}: addSourceBuffer (engine gets ${added[0]})`);
    const r = await W(`navigator.mediaCapabilities.decodingInfo({type:'media-source',video:{contentType:${JSON.stringify(HDR)},width:3840,height:2160,bitrate:2e7,framerate:60,hdrMetadataType:'smpteSt2086',colorGamut:'rec2020',transferFunction:'pq'}})`);
    ok(r.supported === !!cap && r.configuration.video.transferFunction === 'pq', `cap=${cap}: decodingInfo HDR -> ${r.supported}`);
    const r2 = await W(`navigator.mediaCapabilities.decodingInfo({type:'media-source',video:{contentType:${JSON.stringify(SDR8)},width:3840,height:2160,bitrate:2e7,framerate:60}})`);
    ok(r2.supported === true, `cap=${cap}: decodingInfo SDR unchanged`);
  }
  console.log(`OMNI_HDR_CAPS_V1 host test: ${pass} passed, ${fail} failed: ${fail ? 'FAIL' : 'PASS'}`);
  process.exit(fail ? 1 : 0);
})();
