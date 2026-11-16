// OMNI_UBLOCK_FRAMES_V1 browser check (desktop Edge through Playwright; no console needed).
// Runs the scripts Omni injects into a CROSS-ORIGIN iframe and checks that they work there:
//   * <host>.isolated.js (site CSS of the frame's own host, built by OmniUBlockSite.h) hides that host's ad elements,
//   * <host>.main.js (scriptlets) defuses the player's ad config (set-constant),
//   * lite.js (OmniUBlockFrames::highlyGenericScript, the subframe generic CSS) hides a highly generic match and
//     leaves the top frame alone,
//   * the trusted-site gate (top page's host in ALLOW) turns all of it off inside the frame,
//   * ordinary content stays visible.
// WebKit's per-frame choice (allowlist *://host/*, all frames) is emulated with a hostname check around each script.
//   node test_ublock_frames.cjs <dir with lite.js, googleads.g.doubleclick.net.isolated.js, www.youtube-nocookie.com.main.js>
// Make them with: ./site-harness site-index.txt <dir> googleads.g.doubleclick.net www.youtube-nocookie.com
//                 ./t always-generic.js <dir>/lite.js            (test_ublock_frames.cpp)
// playwright-core: from require() or PLAYWRIGHT_CORE=<path to its folder>.
'use strict';
const fs = require('fs');
const http = require('http');
const path = require('path');
let playwright;
try { playwright = require(process.env.PLAYWRIGHT_CORE || 'playwright-core'); } catch (e) { console.log('SKIP: playwright-core not found'); process.exit(0); }

const dir = process.argv[2];
const read = f => fs.readFileSync(path.join(dir, f), 'utf8');
const lite = read('lite.js');
const adIsolated = read('googleads.g.doubleclick.net.isolated.js');
const ytMain = read('www.youtube-nocookie.com.main.js');

// One simple selector of the highly generic list ('[href*="..."]', a link to an ad network) to plant in the frame.
const literal = lite.match(/^const H = (".*");$/m)[1];
const highly = new Function('return ' + literal)().split(',\n');
const simple = highly.find(s => /^\[href\*="[^"]+"\]$/.test(s));
if (!simple) { console.log('FAIL: no [href*="..."] selector in the highly generic list'); process.exit(1); }
const plant = `href="https://ads.example${simple.slice(8, -2)}"`;

const AD = 'googleads.g.doubleclick.net', YT = 'www.youtube-nocookie.com', TOP = 'top.omni.test';
const pages = {
  [TOP]: `<!doctype html><title>top</title><a ${plant} id2="top-generic">top generic match (must stay: the top frame has the full generic script)</a>
<iframe id="ad" src="http://${AD}:PORT/frame"></iframe><iframe id="yt" src="http://${YT}:PORT/frame"></iframe>`,
  [AD]: `<!doctype html><div id="abgc">site css: #abgc</div><div id="ads">site css: #ads</div><a ${plant} data-t="generic">highly generic</a><p id="content">content</p>`,
  [YT]: `<!doctype html><script>window.ytInitialPlayerResponse = { adPlacements: [1], videoDetails: { id: 1 } };</script><p id="content">player</p>`,
};
const server = http.createServer((req, res) => {
  const host = (req.headers.host || '').split(':')[0];
  res.writeHead(200, { 'content-type': 'text/html' });
  res.end((pages[host] || '').replace(/PORT/g, server.address().port));
});

// documentStart: run now; documentEnd: run at DOMContentLoaded (as WebKit's document end).
const forHost = (host, source, end) => `if (location.hostname === ${JSON.stringify(host)}) {${end
  ? `(() => { const f = () => { ${source} }; document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', f) : f(); })();`
  : source}}`;
const anyFrame = (source, end) => end
  ? `(() => { const f = () => { ${source} }; document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', f) : f(); })();`
  : source;
const withAllow = (source, allow) => source.replace(/const ALLOW = \[\];/, `const ALLOW = ${JSON.stringify(allow)};`);

async function run(browser, port, allow) {
  const context = await browser.newContext();
  await context.addInitScript(forHost(AD, withAllow(adIsolated, allow), false));
  await context.addInitScript(forHost(YT, withAllow(ytMain, allow), false));
  await context.addInitScript(anyFrame(withAllow(lite, allow), true));
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(`http://${TOP}:${port}/`);
  await page.waitForLoadState('load');
  const ad = page.frame({ url: new RegExp(`^http://${AD.replace(/\./g, '\\.')}`) });
  const yt = page.frame({ url: new RegExp(`^http://${YT.replace(/\./g, '\\.')}`) });
  const shown = (frame, sel) => frame.evaluate(s => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none'; }, sel);
  const crossOrigin = await page.evaluate(() => { try { void document.getElementById('ad').contentWindow.document; return false; } catch { return true; } });
  const r = {
    crossOrigin,
    adSiteCss: !(await shown(ad, '#abgc')) && !(await shown(ad, '#ads')),
    adGeneric: !(await shown(ad, '[data-t="generic"]')),
    adContent: await shown(ad, '#content'),
    ytScriptlet: await yt.evaluate(() => window.ytInitialPlayerResponse && window.ytInitialPlayerResponse.adPlacements === undefined && window.ytInitialPlayerResponse.videoDetails.id === 1),
    ytContent: await shown(yt, '#content'),
    topUntouched: await shown(page.mainFrame(), '[id2="top-generic"]'),
    errors,
  };
  await context.close();
  return r;
}

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  let browser;
  try {
    browser = await playwright.chromium.launch({ channel: 'msedge', headless: true,
      args: [`--host-resolver-rules=MAP ${TOP} 127.0.0.1, MAP ${AD} 127.0.0.1, MAP ${YT} 127.0.0.1`] });
  } catch (e) { console.log('SKIP: Edge could not start: ' + e.message.split('\n')[0]); server.close(); process.exit(0); }
  let fails = 0;
  const check = (name, ok) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}`); if (!ok) ++fails; };
  try {
    const on = await run(browser, port, []);
    console.log(`highly generic selector planted: ${simple}`);
    check('iframes are cross-origin', on.crossOrigin);
    check('frame host site CSS hides its ads (#abgc, #ads) inside the iframe', on.adSiteCss);
    check('subframe highly generic CSS hides a generic match inside the iframe', on.adGeneric);
    check('iframe content stays visible', on.adContent);
    check('frame host scriptlet (set-constant ytInitialPlayerResponse.adPlacements) works inside the iframe', on.ytScriptlet);
    check('player content stays visible', on.ytContent);
    check('top frame is left to its own generic script (lite.js skips it)', on.topUntouched);
    check('no script errors', on.errors.length === 0);
    if (on.errors.length) console.log(on.errors.join('\n'));
    const trusted = await run(browser, port, [TOP]);
    check('trusted top site: nothing hidden in its iframes', !trusted.adSiteCss && !trusted.adGeneric && trusted.adContent);
    check('trusted top site: no scriptlets in its iframes', !trusted.ytScriptlet);
  } finally {
    await browser.close();
    server.close();
  }
  console.log(fails ? `FAIL: ${fails}` : 'PASS');
  process.exit(fails ? 1 : 0);
})();
