// SPDX-License-Identifier: GPL-3.0-or-later
// omni-video-4k60 host test: the hole-punch eligibility on YouTube-like layouts, in headless Chromium.
//  - OMNI_HOLE_ELIGIBILITY_PROBE_V1 (OmniBrowser.cpp's yt-timeline script) applies the WebProcess player's holeGeometry rules
//    (opacity / filter / backdrop-filter / mask / clip-path / blend / reflection on the way up, rotation, empty rect, hidden page);
//  - OMNI_DARK_VIDEO_V1 (OmniDarkPages.h): a forced-dark site keeps its dark look but a playing video loses every filter on
//    its way up (the cause of the s3.3/s3.4 stall); the baseline script is run too, to reproduce the cause.
// The JS under test is extracted from the C++ sources byte for byte. Usage: node eligibility_test.cjs <OmniBrowser.cpp> <OmniDarkPages.h> [<baseline OmniDarkPages.h>]
'use strict';
const fs = require('fs'), http = require('http');
const puppeteer = require('/opt/npm-tools/node_modules/puppeteer-core');
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
function raw(file, delim) {
    const t = fs.readFileSync(file, 'utf8'), a = t.indexOf('R"' + delim + '('), b = t.indexOf(')' + delim + '"', a);
    if (a < 0 || b < 0) throw new Error('no R"' + delim + '( in ' + file);
    return t.slice(a + delim.length + 3, b);
}
const holeJs = raw(process.argv[2], 'OMNIHOLE'), darkJs = raw(process.argv[3], 'JS'), darkOld = process.argv[4] ? raw(process.argv[4], 'JS') : null;
// YouTube-like watch page (desktop layout: masthead, rounded player with controls overlay, recommendations column)
function page(o) {
    const pageBg = o.lightPage ? '#fff' : (o.transparentRoot ? 'transparent' : '#0f0f0f');
    const playerW = o.theater ? '100%' : '1305px', playerH = o.theater ? '82vh' : '734px';
    return `<!doctype html><html style="background:${pageBg}"><head><meta charset=utf-8><style>
body{margin:0;background:${pageBg};color:${o.lightPage ? '#000' : '#fff'};font:14px sans-serif}
ytd-app{display:block;background:${o.transparentRoot ? '#0f0f0f' : 'transparent'};min-height:100vh}
#masthead{height:56px;position:sticky;top:0;background:inherit;z-index:3}
#columns{display:flex;gap:24px;padding:${o.theater ? '0' : '24px'}}
#primary{flex:0 0 auto;width:${playerW}}#secondary{flex:1;min-width:300px}
#ytd-player{display:block;position:relative;width:${playerW};height:${playerH};border-radius:${o.theater ? 0 : 12}px;overflow:hidden;background:#000;
  ${o.ancestorOpacity ? 'opacity:' + o.ancestorOpacity + ';' : ''}${o.rotate ? 'transform:rotate(' + o.rotate + 'deg);' : ''}${o.clipPath ? 'clip-path:inset(1px);' : ''}}
.html5-video-container{position:absolute;inset:0}video{width:100%;height:100%;object-fit:contain;background:#000}
.ytp-chrome-bottom{position:absolute;left:12px;right:12px;bottom:0;height:48px;opacity:.9;backdrop-filter:blur(6px);background:rgba(0,0,0,.4)}
.ytp-overlay{position:absolute;inset:0;pointer-events:none;background:linear-gradient(transparent 70%,rgba(0,0,0,.6));mix-blend-mode:multiply}
.thumb{height:94px;margin:0 0 8px;background:#3a3a3a;border-radius:8px}
</style></head><body><ytd-app><div id=masthead>YouTube</div><div id=columns><div id=primary>
<ytd-player id=ytd-player><div id=movie_player class="html5-video-player"><div class=html5-video-container><video class="video-stream html5-main-video" muted playsinline></video></div>
<div class=ytp-overlay></div><div class=ytp-chrome-bottom>controls</div></div></ytd-player><h1>Big Buck Bunny 60fps 4K</h1></div>
<div id=secondary>${'<div class=thumb></div>'.repeat(8)}</div></div></ytd-app>
<script>
window.__startVideo=async function(){const c=document.createElement('canvas');c.width=640;c.height=360;const x=c.getContext('2d');let n=0;
setInterval(function(){x.fillStyle='hsl('+(n++%360)+',60%,50%)';x.fillRect(0,0,640,360)},16);
const v=document.querySelector('video');v.srcObject=c.captureStream(60);v.muted=true;await v.play();
for(let i=0;i<100&&v.readyState<2;i++)await new Promise(r=>setTimeout(r,20));return v.readyState};
${o.hidden ? "Object.defineProperty(document,'visibilityState',{get:function(){return 'hidden'}});" : ''}
</script></body></html>`;
}
const cases = [
    { name: 'inline watch (default view, rounded player, sidebar)', o: {}, want: true },
    { name: 'theater view', o: { theater: true }, want: true },
    { name: 'fullscreen (#movie_player)', o: {}, fullscreen: true, want: true },
    { name: 'overlay over the video (controls with opacity + backdrop-filter, blend overlay: siblings)', o: {}, want: true },
    { name: 'hidden page', o: { hidden: true }, want: false, why: /page hidden/ },
    { name: 'negative: opacity 0.99 on the player', o: { ancestorOpacity: 0.99 }, want: false, why: /^opacity/ },
    { name: 'negative: rotated player', o: { rotate: 3 }, want: false, why: /rotated/ },
    { name: 'negative: clip-path on the player', o: { clipPath: true }, want: false, why: /clip-path/ },
];
const darkCases = [
    // forced dark on a LIGHT page: inverted while paused (filter: ineligible), filter off while the video plays
    { name: 'dark forced, light page', o: { lightPage: true }, paused: { dark: true, eligible: false }, playing: { dark: false, eligible: true }, after: { dark: true } },
    // forced dark on YouTube's own dark theme with transparent <html>/<body> (the centre element is dark): never inverted
    { name: 'dark forced, dark page (transparent html/body)', o: { transparentRoot: true }, paused: { dark: false, eligible: true }, playing: { dark: false, eligible: true }, after: { dark: false } },
];
(async () => {
    const server = http.createServer((q, r) => { const id = q.url.slice(1); const c = [...cases, ...darkCases][+id]; r.writeHead(200, { 'content-type': 'text/html' }); r.end(page(c ? c.o : {})); });
    await new Promise(r => server.listen(0, '127.0.0.1', r));
    const base = 'http://127.0.0.1:' + server.address().port + '/';
    const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'] });
    let bad = 0;
    const out = (ok, line) => { console.log(line + ' -> ' + (ok ? 'PASS' : 'FAIL')); if (!ok) bad++; };
    async function open(i, scripts) {
        const p = await browser.newPage(); await p.setViewport({ width: 1920, height: 1080 });
        for (const s of scripts) await p.evaluateOnNewDocument(s);
        await p.goto(base + i, { waitUntil: 'load' }); return p;
    }
    for (let i = 0; i < cases.length; ++i) {
        const c = cases[i], p = await open(i, [holeJs]);
        await p.evaluate(() => window.__startVideo());
        if (c.fullscreen) { await p.evaluate(() => document.querySelector('#movie_player').requestFullscreen().catch(e => String(e))); await new Promise(r => setTimeout(r, 300)); }
        const h = await p.evaluate(() => window.__omniHoleProbe.dump().now);
        const ok = h.eligible === c.want && (!c.why || c.why.test(h.why || '')) && (!c.fullscreen || h.fullscreen);
        out(ok, `ELIG ${c.name}: eligible=${h.eligible} why="${h.why}" rect=${JSON.stringify(h.rect)} onScreen=${h.onScreen}${c.fullscreen ? ' fullscreen=' + h.fullscreen : ''}`);
        await p.close();
    }
    const cfg = `window.__omniDarkCfg={v:1,g:0,on:['127.0.0.1'],off:[]};`;
    for (const [label, js] of [['OMNI_DARK_VIDEO_V1', darkJs], ...(darkOld ? [['baseline (s3.3)', darkOld]] : [])]) {
        for (let k = 0; k < darkCases.length; ++k) {
            const c = darkCases[k], p = await open(cases.length + k, [cfg, js, holeJs]);
            await p.evaluate(() => new Promise(r => setTimeout(r, 1700)));   // the script's load + 1.5 s pass
            const st = async () => p.evaluate(() => ({ dark: document.documentElement.hasAttribute('data-omnidark'), eligible: window.__omniHoleProbe.dump().now.eligible, why: window.__omniHoleProbe.dump().now.why }));
            const s0 = await st();
            await p.evaluate(() => window.__startVideo()); await new Promise(r => setTimeout(r, 400));
            const s1 = await st();
            await p.evaluate(() => document.querySelector('video').pause()); await new Promise(r => setTimeout(r, 400));
            const s2 = await st();
            const line = `DARK [${label}] ${c.name}: paused dark=${s0.dark} eligible=${s0.eligible} ("${s0.why}") | playing dark=${s1.dark} eligible=${s1.eligible} ("${s1.why}") | paused again dark=${s2.dark}`;
            if (label === 'OMNI_DARK_VIDEO_V1') out(s0.dark === c.paused.dark && s0.eligible === c.paused.eligible && s1.dark === c.playing.dark && s1.eligible === c.playing.eligible && s2.dark === c.after.dark, line);
            else console.log(line + (s1.eligible ? '' : '  <- the s3.3/s3.4 cause: a playing video under the dark filter is never eligible for the hole-punch'));
            await p.close();
        }
    }
    await browser.close(); server.close();
    console.log('ELIGIBILITY RESULT ' + (bad ? 'FAIL (' + bad + ')' : 'PASS'));
    process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
