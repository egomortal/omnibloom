// OMNI_PAGE_INFO_V1: node test of the Page info script (OmniPageInfo::script()) on small fake pages.
//   ./t script.js   (tools/test_page_info.cpp writes it)   then   node --check script.js && node test_page_info_js.cjs script.js
'use strict';
const fs = require('fs');
const vm = require('vm');
const file = process.argv[2];
if (!file) { console.error('usage: node test_page_info_js.cjs <script.js>'); process.exit(2); }
const SRC = fs.readFileSync(file, 'utf8');
let fails = 0, checks = 0;
function eq(a, b, what) { ++checks; if (JSON.stringify(a) !== JSON.stringify(b)) { ++fails; console.error('FAIL ' + what + '\n  got  ' + JSON.stringify(a) + '\n  want ' + JSON.stringify(b)); } }

function el(text) { return { innerText: text, textContent: text }; }
function run(page) {
    const document = {
        documentElement: page.lang === undefined ? null : { getAttribute: n => (n === 'lang' ? page.lang : null) },
        body: page.body === undefined ? el('') : page.body,
        querySelectorAll: () => page.mains || [],
    };
    Object.defineProperty(document, 'cookie', { get() { if (page.cookieThrows) throw new Error('SecurityError'); return page.cookie || ''; } });
    const window = {};
    Object.defineProperty(window, 'localStorage', { get() { if (page.lsThrows) throw new Error('SecurityError'); return { length: page.ls || 0 }; } });
    Object.defineProperty(window, 'sessionStorage', { get() { return { length: page.ss || 0 }; } });
    window.performance = page.performance;
    const ctx = vm.createContext({ document, window });
    const out = vm.runInContext(SRC, ctx);
    const r = {};
    if (typeof out !== 'string' || out.indexOf('omni-page-info;') !== 0) return { bad: out };
    for (const kv of out.slice('omni-page-info;'.length).split(';')) { const i = kv.indexOf('='); r[kv.slice(0, i)] = kv.slice(i + 1); }
    return r;
}

// an article page with navigation timing
let r = run({
    lang: 'en-GB',
    body: el('Menu Home About\n' + 'word '.repeat(300) + '\nFooter'),
    mains: [el('word '.repeat(300))],
    cookie: 'a=1; b=2;  ; c=3',
    ls: 4, ss: 1,
    performance: { getEntriesByType: t => (t === 'navigation' ? [{ loadEventEnd: 2430.6, domContentLoadedEventEnd: 1100.2, responseStart: 120.4, type: 'reload', transferSize: 49152 }] : []) },
});
eq([r.lang, r.w, r.c, r.ck, r.ls, r.ss, r.ld, r.dcl, r.fb, r.nt, r.tb], ['en-GB', '300', '0', '3', '4', '1', '2431', '1100', '120', '1', '49152'], 'article page');

// a small main element (a teaser): the body is counted; punctuation-only tokens aren't words
r = run({ lang: 'fr', body: el('un deux trois quatre cinq six sept huit -- ... !'), mains: [el('un')], performance: { getEntriesByType: () => [] } });
eq([r.lang, r.w, r.ld, r.nt, r.tb], ['fr', '8', '-1', '-1', '-1'], 'body text, no navigation entry');

// CJK text, lang with junk, cookies / storage not readable, still loading, from cache
r = run({
    lang: 'ja;x=1<b>', body: el('\u65e5\u672c\u8a9e\u306e\u6587\u7ae0\u3067\u3059\u3002 Omni 5'),
    cookieThrows: true, lsThrows: true,
    performance: { getEntriesByType: () => [{ loadEventEnd: 0, domContentLoadedEventEnd: 800, responseStart: 0, type: 'navigate', transferSize: 0 }] },
});
eq([r.lang, r.c, r.w, r.ck, r.ls, r.ld, r.dcl, r.fb, r.nt, r.tb], ['jax1b', '8', '2', '-1', '-1', '-1', '800', '-1', '0', '0'], 'CJK, unreadable storage, loading');

// old WebKit: performance.timing only; no lang; no body
r = run({
    body: null,
    performance: { timing: { navigationStart: 1000, loadEventEnd: 3500, domContentLoadedEventEnd: 2000, responseStart: 1100 }, navigation: { type: 2 } },
});
eq([r.lang, r.w, r.c, r.ld, r.dcl, r.fb, r.nt], ['', '0', '0', '2500', '1000', '100', '2'], 'performance.timing fallback');

// no performance at all; getAttribute missing root
r = run({ lang: undefined, body: el('one two'), performance: undefined });
eq([r.lang, r.w, r.ld], ['', '2', '-1'], 'no performance, no root');

// a long page is cut at 3 M characters (the script stays fast)
r = run({ lang: 'en', body: el('ab '.repeat(1100000)), performance: undefined });
eq(r.w, '1000000', '3 M character cap');

console.log(checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
