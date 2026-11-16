// OMNI_IMAGE_VIEWER_V1: the image viewer's page scripts (OmniImageViewer::kLibrary / kProbe) on a mock DOM.
//   node test_image_viewer_js.cjs <tree>/engine/entry/OmniImageViewer.h [emit dir from test_image_viewer --emit]
// The scripts are taken from the header exactly as the shell sends them (whole raw strings, nothing trimmed); with an
// emit dir, the assembled scripts the C++ builders produce are syntax-checked and the open script is run too.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const header = fs.readFileSync(process.argv[2], 'utf8');
function raw(name) {
    const m = new RegExp('static const char\\* const ' + name + ' = R"JS\\(([\\s\\S]*?)\\)JS";').exec(header);
    if (!m) throw new Error(name + ' not found in ' + process.argv[2]);
    return m[1];
}
const LIB = raw('kLibrary'), PROBE = raw('kProbe');
let checks = 0, failures = 0;
function check(ok, what) { ++checks; if (!ok) { ++failures; console.error('FAIL ' + what); } }
function eq(a, b, what) { check(a === b, what + ': got ' + JSON.stringify(a) + ' want ' + JSON.stringify(b)); }

// --- mock DOM ---------------------------------------------------------------------------------------------------------
function env(opts) {
    opts = opts || {};
    const sizes = opts.sizes || {}, created = [], listeners = {};
    class Style { constructor() { this.p = {}; } setProperty(k, v, pr) { this.p[k] = v; this.pr = pr; } getPropertyValue(k) { return this.p[k] || ''; } }
    class Node {
        constructor(tag) { this.tagName = String(tag).toUpperCase(); this.style = new Style(); this.children = []; this.parentNode = null; this.textContent = ''; }
        appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.children.push(c); return c; }
        removeChild(c) { const i = this.children.indexOf(c); if (i < 0) throw new Error('not a child'); this.children.splice(i, 1); c.parentNode = null; return c; }
        get isConnected() { let n = this; for (;;) { if (n === docEl) return true; if (n.parentNode) n = n.parentNode; else if (n.host) n = n.host; else return false; } }
        attachShadow(o) { const r = new Node('#shadow'); r.host = this; r.mode = o.mode; this.shadow = r; return r; }
    }
    class Img extends Node {
        constructor() { super('img'); this._src = ''; this.complete = false; this.naturalWidth = 0; this.naturalHeight = 0; this.loads = 0; }
        set src(v) { this._src = v; this.loads++; const s = sizes[v]; this.complete = true; this.naturalWidth = s ? s[0] : 0; this.naturalHeight = s ? s[1] : 0; }
        get src() { return this._src; }
    }
    const docEl = new Node('html'), body = docEl.appendChild(new Node('body'));
    const images = (opts.images || []).map(o => ({ currentSrc: o.current || '', src: o.src || '', naturalWidth: o.nw || 0, naturalHeight: o.nh || 0,
        getBoundingClientRect() { if (o.throws) throw new Error('x'); return { width: o.w || 0, height: o.h || 0 }; } }));
    const document = {
        baseURI: opts.base || 'https://example.com/dir/page.html', contentType: opts.contentType || 'text/html', images,
        documentElement: docEl, body,
        createElement(t) { const e = t === 'img' ? new Img() : new Node(t); created.push(e); return e; },
    };
    const window = { innerWidth: opts.w || 1280, innerHeight: opts.h || 720, document, URL,
        addEventListener(t, f) { listeners[t] = f; } };
    window.window = window;
    const ctx = vm.createContext(window);
    return { ctx, window, document, docEl, created, listeners,
        run(src) { return vm.runInContext(src, ctx); },
        host() { return docEl.children.find(c => c.tagName === 'OMNI-IMAGE-VIEWER'); },
        img() { return created.filter(e => e.tagName === 'IMG').pop(); },
        msg() { return created.filter(e => e.tagName === 'DIV').pop(); } };
}
function tf(e) { return e.img().style.getPropertyValue('transform'); }

// --- probe: WebKit's ImageDocument ---------------------------------------------------------------------------------
{
    const a = env({ contentType: 'image/jpeg', images: [{ src: 'https://cdn.example.com/a.jpg' }] });
    eq(a.run(PROBE), 'https://cdn.example.com/a.jpg', 'probe: image document');
    const b = env({ contentType: 'text/html', images: [{ src: 'https://cdn.example.com/a.jpg' }] });
    eq(b.run(PROBE), '', 'probe: html page');
    const c = env({ contentType: 'image/svg+xml', images: [] });
    eq(c.run(PROBE), '', 'probe: svg document (no <img>)');
    const d = env({ contentType: 'IMAGE/PNG', images: [{ current: 'https://x/c.png', src: 'https://x/s.png' }] });
    eq(d.run(PROBE), 'https://x/c.png', 'probe: currentSrc first, any case');
    const e = env({ contentType: 'image/png', images: [{ src: 'a' }, { src: 'b' }] });
    eq(e.run(PROBE), '', 'probe: two images is a page');
}

// --- single image, fit, zoom, pan ---------------------------------------------------------------------------------
{
    const e = env({ sizes: { 'https://example.com/big.jpg': [2000, 1000] } });
    e.run(LIB);
    const api = e.window.__omniImv;
    check(api && api.v === 1, 'library installs window.__omniImv v1');
    eq(e.run(LIB), undefined, 'second install is a no-op');
    check(e.window.__omniImv === api, 'same object after a second install');
    eq(api.alive(), '0', 'not alive before open');
    eq(api.input(1, 0, 0), '0', 'input before open: 0');
    eq(api.open('', 0), '{}', 'open with nothing');
    const r = JSON.parse(api.open('/big.jpg', 0));
    eq(r.n, 1, 'single: n'); eq(r.i, 0, 'single: i'); eq(r.src, 'https://example.com/big.jpg', 'single: absolute src');
    const host = e.host();
    check(!!host, 'element appended to <html>');
    eq(host.style.getPropertyValue('position'), 'fixed', 'host fixed');
    eq(host.style.getPropertyValue('z-index'), '2147483647', 'host on top');
    eq(host.style.getPropertyValue('background'), '#000', 'black');
    eq(host.style.pr, 'important', 'styles important');
    check(host.shadow && host.shadow.mode === 'closed', 'closed shadow root');
    check(host.shadow.children.includes(e.img()), 'picture inside the shadow root');
    eq(e.img().style.getPropertyValue('visibility'), 'visible', 'loaded picture shown');
    eq(e.img().style.getPropertyValue('width'), '2000px', 'natural width');
    // fit: min(1280/2000, 720/1000) = 0.64 -> 1280 x 640, centred
    eq(tf(e), 'translate(0.00px,40.00px) scale(0.640000)', 'fit');
    eq(api.alive(), '1', 'alive');
    eq(api.input(Math.log(2), 0, 0), '1', 'zoom 2x');
    eq(tf(e), 'translate(-640.00px,-280.00px) scale(1.280000)', 'zoomed about the centre');
    api.input(0, 10000, -10000);   // far right / up: kept inside the picture
    eq(tf(e), 'translate(-1280.00px,0.00px) scale(1.280000)', 'pan clamped to the edges');
    api.input(Math.log(2), 0, 0);   // 4x keeps the same picture point at the centre
    eq(tf(e), 'translate(-3200.00px,-360.00px) scale(2.560000)', 'zoom keeps the centre point (offset doubles, then kept inside)');
    api.input(-20, 0, 0);
    eq(tf(e), 'translate(0.00px,40.00px) scale(0.640000)', 'zoom out stops at fit, centred again');
    api.input(50, 0, 0);
    eq(tf(e), 'translate(-4480.00px,-2200.00px) scale(5.120000)', 'zoom in stops at 8x fit');
    api.input('x', 'y', NaN);
    eq(tf(e), 'translate(-4480.00px,-2200.00px) scale(5.120000)', 'junk numbers change nothing');
    eq(api.toggle(), '1', 'toggle');
    eq(tf(e), 'translate(0.00px,40.00px) scale(0.640000)', 'toggle from zoomed: fit');
    api.toggle();   // 1 / 0.64 = 1.5625 >= 1.5: actual size
    eq(tf(e), 'translate(-360.00px,-140.00px) scale(1.000000)', 'toggle from fit: actual size');
    eq(JSON.parse(api.go(1)).e, 1, 'go past the only image: e 1');
    eq(JSON.parse(api.go(-1)).e, 1, 'go before the only image: e 1');
    e.window.innerWidth = 1000; e.window.innerHeight = 1000;
    api.toggle(); e.listeners.resize();
    eq(tf(e), 'translate(0.00px,250.00px) scale(0.500000)', 'resize: fit again');
    e.window.innerWidth = 1280; e.window.innerHeight = 720;
    eq(api.close(), '1', 'close');
    check(!e.host(), 'element removed');
    eq(api.alive(), '0', 'closed: alive 0'); eq(api.input(1, 1, 1), '0', 'closed: input 0'); eq(api.go(1), '{}', 'closed: go {}');
    eq(api.toggle(), '0', 'closed: toggle 0'); eq(api.close(), '1', 'close twice is fine');
    // open again after close: a fresh element
    JSON.parse(api.open('https://example.com/big.jpg', 0));
    check(!!e.host(), 'reopen builds a new element');
    // the page drops the element itself
    e.docEl.removeChild(e.host());
    eq(api.alive(), '0', 'page removed it: alive 0');
    eq(api.input(0.1, 0, 0), '0', 'page removed it: input 0');
    JSON.parse(api.open('https://example.com/big.jpg', 0));
    eq(e.docEl.children.filter(c => c.tagName === 'OMNI-IMAGE-VIEWER').length, 1, 'reopen after removal: one element');
}

// --- small picture: fit enlarges, toggle goes to 2.5x ----------------------------------------------------------------
{
    const e = env({ sizes: { 'https://example.com/s.png': [300, 300] } });
    e.run(LIB);
    const api = e.window.__omniImv;
    api.open('https://example.com/s.png', 0);
    eq(tf(e), 'translate(280.00px,0.00px) scale(2.400000)', 'small picture fitted (enlarged)');
    api.toggle();
    eq(tf(e), 'translate(-260.00px,-540.00px) scale(6.000000)', 'small picture: toggle to 2.5x');
    api.input(10, 0, 0);
    eq(tf(e), 'translate(-2240.00px,-2520.00px) scale(19.200000)', 'small picture: max 8x fit');
}

// --- huge picture: max zoom reaches 4x its own pixels ---------------------------------------------------------------
{
    const e = env({ sizes: { 'https://example.com/h.jpg': [12800, 7200] } });
    e.run(LIB);
    const api = e.window.__omniImv;
    api.open('https://example.com/h.jpg', 0);
    eq(tf(e), 'translate(0.00px,0.00px) scale(0.100000)', 'huge: fit');
    api.input(20, 0, 0);
    eq(tf(e), 'translate(-24960.00px,-14040.00px) scale(4.000000)', 'huge: max is 4x its pixels');
}

// --- the page's pictures: collected once, order, size rule, start ----------------------------------------------------
{
    const sizes = { 'https://example.com/a.jpg': [800, 600], 'https://cdn.example.com/c.jpg': [250, 400], 'https://example.com/small.png': [100, 100],
        'https://example.com/dir/rel.jpg': [640, 480] };
    const images = [
        { src: 'https://example.com/a.jpg', nw: 800, nh: 600 },
        { src: 'https://example.com/small.png', nw: 100, nh: 100, w: 100, h: 100 },
        { current: 'https://cdn.example.com/c.jpg', src: 'https://cdn.example.com/c-fallback.jpg', w: 250, h: 400 },   // not loaded yet: shown size
        { src: 'https://example.com/a.jpg', nw: 800, nh: 600 },          // the same again
        { src: 'javascript:alert(1)', nw: 900, nh: 900 },
        { src: 'https://example.com/wide.jpg', nw: 1500, nh: 150 },       // too thin
        { src: 'rel.jpg', nw: 640, nh: 480 },                             // relative: absolute on the page's base
        { src: 'https://example.com/t.jpg', throws: true, nw: 300, nh: 300 },
        { src: '' },
    ];
    const e = env({ sizes, images });
    e.run(LIB);
    const api = e.window.__omniImv;
    let r = JSON.parse(api.open('https://cdn.example.com/c.jpg', 1));
    eq(r.n, 4, 'collected: a, c, rel, t'); eq(r.i, 1, 'start among them'); eq(r.src, 'https://cdn.example.com/c.jpg', 'start src');
    r = JSON.parse(api.go(1)); eq(r.i, 2, 'next'); eq(r.src, 'https://example.com/dir/rel.jpg', 'relative made absolute'); eq(r.e, 0, 'next: e 0');
    eq(tf(e), 'translate(160.00px,0.00px) scale(1.500000)', 'next picture fitted');
    r = JSON.parse(api.go(1)); eq(r.src, 'https://example.com/t.jpg', 'next again');
    eq(e.img().style.getPropertyValue('visibility'), 'hidden', 'no size known for t.jpg: hidden until it loads');
    eq(api.input(1, 5, 5), '1', 'input while not loaded: still alive');
    e.img().onerror();
    eq(e.msg().style.getPropertyValue('display'), 'block', 'error message shown');
    eq(e.msg().textContent, "Couldn't load this image", 'error text');
    r = JSON.parse(api.go(1)); eq(r.e, 1, 'past the last: e 1'); eq(r.i, 3, 'stays on the last');
    r = JSON.parse(api.go(-3)); eq(r.i, 2, 'go(-3) is one step back');
    r = JSON.parse(api.go(-1)); r = JSON.parse(api.go(-1)); eq(r.i, 0, 'first'); eq(r.src, 'https://example.com/a.jpg', 'first src');
    eq(e.msg().style.getPropertyValue('display'), 'none', 'message hidden again on the next picture');
    eq(JSON.parse(api.go(-1)).e, 1, 'before the first: e 1');
    // a late load of an earlier picture does not take over
    const img = e.img(), oldLoad = img.onload;
    api.go(1);
    img.naturalWidth = 5; img.naturalHeight = 5; oldLoad();
    eq(e.img().style.getPropertyValue('width'), '250px', 'stale onload ignored');
    // start not among them (small or a background image): added first
    r = JSON.parse(api.open('https://example.com/small.png', 1));
    eq(r.n, 5, 'start added'); eq(r.i, 0, 'start first'); eq(r.src, 'https://example.com/small.png', 'start src');
    r = JSON.parse(api.open('https://example.com/bg.jpg', 1));
    eq(r.i, 0, 'background start first'); eq(r.n, 5, 'list rebuilt each opening');
    eq(e.docEl.children.filter(c => c.tagName === 'OMNI-IMAGE-VIEWER').length, 1, 'one element across openings');
    // at most 400
    const many = []; for (let k = 0; k < 450; ++k) many.push({ src: 'https://example.com/m' + k + '.jpg', nw: 300, nh: 300 });
    const m = env({ images: many });
    m.run(LIB);
    eq(JSON.parse(m.window.__omniImv.open('https://example.com/m10.jpg', 1)).n, 400, 'at most 400');
    eq(JSON.parse(m.window.__omniImv.open('https://example.com/m420.jpg', 1)).n, 400, 'at most 400 with an added start');
}

// --- nothing else is touched -------------------------------------------------------------------------------------------
{
    const e = env({ sizes: { 'https://example.com/a.jpg': [800, 600] } });
    const before = Object.keys(e.window).sort().join(',');
    e.run(LIB);
    const after = Object.keys(e.window).sort().join(',');
    eq(after, before.split(',').concat('__omniImv').sort().join(','), 'only window.__omniImv added');
    e.window.__omniImv.open('https://example.com/a.jpg', 0);
    eq(e.document.body.children.length, 0, 'body untouched');
    eq(e.docEl.children.length, 2, '<html>: body + the viewer');
}

// --- the assembled scripts (C++ builders) -------------------------------------------------------------------------------
const dir = process.argv[3];
if (dir) {
    for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.js'))) {
        const src = fs.readFileSync(path.join(dir, f), 'utf8');
        let ok = true;
        try { new vm.Script(src, { filename: f }); } catch (err) { ok = false; console.error(f + ': ' + err.message); }
        check(ok, 'syntax ' + f);
    }
    const tricky = fs.readFileSync(path.join(dir, 'tricky.txt'), 'utf8');
    const want = new URL(tricky).href;
    const e = env({ sizes: { [want]: [1600, 900], 'https://example.com/one.png': [640, 360] },
        images: [{ src: 'https://example.com/x.jpg', nw: 400, nh: 400 }, { src: want, nw: 1600, nh: 900 }] });
    const r = JSON.parse(e.run(fs.readFileSync(path.join(dir, 'open.js'), 'utf8')));
    eq(r.src, want, 'open.js: the quoted address arrives intact');
    eq(r.n, 2, 'open.js: collected'); eq(r.i, 1, 'open.js: start found');
    eq(tf(e), 'translate(0.00px,0.00px) scale(0.800000)', 'open.js: fitted');
    eq(e.run(fs.readFileSync(path.join(dir, 'input.js'), 'utf8')), '1', 'input.js answers 1');
    eq(tf(e), 'translate(-665.00px,-350.00px) scale(1.600005)', 'input.js: 2x, moved 25 right / 10 up');
    eq(JSON.parse(e.run(fs.readFileSync(path.join(dir, 'go.js'), 'utf8'))).e, 1, 'go.js at the end');
    eq(e.run(fs.readFileSync(path.join(dir, 'toggle.js'), 'utf8')), '1', 'toggle.js');
    eq(e.run(fs.readFileSync(path.join(dir, 'alive.js'), 'utf8')), '1', 'alive.js');
    eq(e.run(fs.readFileSync(path.join(dir, 'close.js'), 'utf8')), '1', 'close.js');
    eq(e.run(fs.readFileSync(path.join(dir, 'alive.js'), 'utf8')), '0', 'alive.js after close');
    const f = env({ sizes: { 'https://example.com/one.png': [640, 360] } });
    eq(f.run(fs.readFileSync(path.join(dir, 'alive.js'), 'utf8')), '0', 'alive.js without the library: 0');
    eq(JSON.parse(f.run(fs.readFileSync(path.join(dir, 'open1.js'), 'utf8'))).n, 1, 'open1.js: single image');
    const g = env({ contentType: 'image/webp', images: [{ src: 'https://example.com/p.webp' }] });
    eq(g.run(fs.readFileSync(path.join(dir, 'probe.js'), 'utf8')), 'https://example.com/p.webp', 'probe.js');
}

console.log((failures ? 'FAIL' : 'PASS') + ': ' + checks + ' checks, ' + failures + ' failures');
process.exit(failures ? 1 : 0);
