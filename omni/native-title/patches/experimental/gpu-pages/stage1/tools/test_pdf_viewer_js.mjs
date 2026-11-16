// OMNI_PDF_VIEWER_V1: tests of the PDF reader's page logic (pages bundle pdf/viewer-nav.mjs) and a static check of
// viewer.mjs / index.html wiring.   node test_pdf_viewer_js.mjs <bundle>/pdf/viewer-nav.mjs
import {readFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {pathToFileURL} from 'node:url';
const navPath = process.argv[2];
if (!navPath) { console.error('usage: node test_pdf_viewer_js.mjs <bundle>/pdf/viewer-nav.mjs'); process.exit(2); }
const {parseParams, docFetchPath, docAddress, decide, DOC_BASE} = await import(pathToFileURL(navPath).href);
let checks = 0, fails = 0;
const check = (ok, what) => { ++checks; if (!ok) { ++fails; console.error('FAIL', what); } };
const T = '0123456789abcdef0123456789abcdef';

// parameters from the shell's address
let p = parseParams('?doc=' + T + '&name=My%20Report.pdf&src=https%3A%2F%2Fa.b%2Fx.pdf');
check(p.doc === T && p.name === 'My Report.pdf' && p.src === 'https://a.b/x.pdf', 'params parsed');
check(parseParams('?doc=' + T.toUpperCase()).doc === '', 'upper-case token refused');
check(parseParams('?doc=../x').doc === '', 'path token refused');
check(parseParams('?doc=' + T + '&src=javascript%3Aalert(1)').src === '', 'javascript: src dropped');
check(parseParams('?src=https%3A%2F%2Fu%3Ap%40a.b%2F').src === '', 'credential src dropped');
check(parseParams('?name=a%0Ab').name === 'ab', 'control characters stripped from name');
check(parseParams('').doc === '' && parseParams(null).name === '', 'empty');
check(docFetchPath(T) === '../_user/pdf/' + T + '.pdf' && docFetchPath('x') === '', 'fetch path');
check(docAddress(T) === DOC_BASE + T + '.pdf' && DOC_BASE === 'omni://pages/_user/pdf/', 'doc address');

// controller decisions
const S = (o) => Object.assign({hasDoc: true, dialogOpen: false, inViewport: true, page: 2, pages: 5, top: 100, maxTop: 900, left: 0, maxLeft: 0, viewH: 700, viewW: 1200}, o);
const k = (a, o) => decide(a, S(o));
check(k('down').kind === 'scroll' && k('down').dy === 175, 'down scrolls a quarter');
check(k('up').kind === 'scroll' && k('up').dy === -175, 'up scrolls');
check(JSON.stringify(k('down', {top: 900})) === JSON.stringify({kind: 'page', delta: 1, edge: 'top'}), 'down at the end: next page');
check(JSON.stringify(k('up', {top: 0})) === JSON.stringify({kind: 'page', delta: -1, edge: 'bottom'}), 'up at the top: previous page end');
check(k('up', {top: 0, page: 1}).kind === 'base', 'up at the top of page 1: focus to the toolbar');
check(k('down', {top: 900, page: 5}).kind === 'none', 'down at the very end: used, nothing');
check(k('down', {maxTop: 0, top: 0}).kind === 'page', 'unscrollable page: down turns the page');
check(k('right').kind === 'page' && k('left').delta === -1, 'left / right turn pages when not zoomed wide');
check(k('right', {maxLeft: 500, left: 0}).kind === 'scroll' && k('right', {maxLeft: 500, left: 0}).dx === 300, 'right scrolls when wide');
check(k('left', {maxLeft: 500, left: 0}).kind === 'page', 'left at the left edge turns the page');
check(k('right', {page: 5}).kind === 'none', 'right on the last page: nothing');
check(k('r1').kind === 'page' && k('r1').delta === 1 && k('l1').delta === -1, 'L1 / R1 page');
check(k('r1', {page: 5}).kind === 'none' && k('l1', {page: 1}).kind === 'none', 'L1 / R1 at the ends');
check(k('r2').kind === 'zoom' && k('r2').delta > 0 && k('l2').delta < 0, 'R2 / L2 zoom');
check(k('square').kind === 'save', 'Square saves');
check(k('square', {hasDoc: false}).kind === 'ignore' && k('r2', {hasDoc: false}).kind === 'ignore', 'no document: Omni keeps Square / R2');
check(k('circle').kind === 'base' && k('cross').kind === 'base', 'Circle / Cross: shared controller (back, click)');
check(k('down', {dialogOpen: true}).kind === 'base' && k('square', {dialogOpen: true}).kind === 'base', 'dialog open: shared controller');
check(k('down', {inViewport: false}).kind === 'base' && k('r1', {inViewport: false}).kind === 'page', 'toolbar focus: D-pad moves focus, R1 still pages');
check(k('quick-access-boundary').kind === 'base', 'quick-access probe goes to the shared controller');

// static wiring
const dir = dirname(navPath);
const viewer = readFileSync(join(dir, 'viewer.mjs'), 'utf8'), html = readFileSync(join(dir, 'index.html'), 'utf8');
check(/import \{[^}]*decide[^}]*\} from '\.\/viewer-nav\.mjs'/.test(viewer), 'viewer imports viewer-nav');
check(viewer.includes("method:'pdf.save'") && viewer.includes("method:'navigation.open'"), 'viewer uses pdf.save / navigation.open');
check(viewer.includes('docFetchPath(openParams.doc)'), 'viewer fetches the same-origin document');
check(html.includes('id="open-original"') && html.includes('R2 / L2 · Zoom') && html.includes("connect-src 'self'"), 'index.html: Open original, hints, CSP unchanged');

console.log(checks + ' checks, ' + fails + ' failed');
process.exit(fails ? 1 : 0);
