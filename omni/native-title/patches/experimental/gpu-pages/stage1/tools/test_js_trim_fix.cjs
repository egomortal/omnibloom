// OMNI_JS_TRIM_FIX_V1: the pointer-snap hit-test script of a patched OmniPointerFeel.h, assembled the way the patched
// omniFxSnapRequest does it (head + template minus its trailing "()" / "(" + "(X,Y,R);})()"), syntax-checked and run on
// a mock DOM. Also shows the old assembly (template minus 2 chars) is a syntax error, i.e. what shipped never ran.
//   node test_js_trim_fix.cjs <tree>/engine/entry/OmniPointerFeel.h
'use strict';
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').replace(/\r\n/g, '\n');

let fails = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++fails; console.log('FAIL ' + what); } };
const parses = (js) => { try { new Function(js); return true; } catch (e) { return false; } };

// the patched C++ (exactly these three lines replace the old js.replace(js.size() - 2, ...) one)
check(src.includes('OMNI_JS_TRIM_FIX_V1'), 'marker present');
check(!src.includes('js.replace(js.size() - 2, 2, "(X,Y,R);})()");'), 'old cut gone');
check(src.includes('    if (js.size() >= 2 && js.compare(js.size() - 2, 2, "()") == 0) js.resize(js.size() - 2);')
    && src.includes("    else if (!js.empty() && js.back() == '(') js.pop_back();\n    js += \"(X,Y,R);})()\";"), 'patched lines');

const m = /omniFxSnapScript = R"JS\(([\s\S]*?)\)JS"/.exec(src);
check(!!m, 'template found');
const tpl = m[1];
check(tpl.endsWith('})('), 'template ends "})(" (raw delimiter ate the last ")")');
const head = (x, y, r) => '(function(){var X=' + x.toFixed(1) + ',Y=' + y.toFixed(1) + ',R=' + r.toFixed(1) + ';return ';

// old assembly: the shipped bug
check(!parses(head(1, 2, 36) + tpl.slice(0, -2) + '(X,Y,R);})()'), 'old assembly is a syntax error');

// new assembly
let body = tpl;
if (body.endsWith('()')) body = body.slice(0, -2); else if (body.endsWith('(')) body = body.slice(0, -1);
const assemble = (x, y, r) => head(x, y, r) + body + '(X,Y,R);})()';
check(parses(assemble(100, 200, 36)), 'new assembly parses');
if (process.argv[3]) fs.writeFileSync(process.argv[3], assemble(100, 200, 36));   // for `node --check`

// mock DOM: a page 1280x720, one link box at (200..300, 100..130); the body everywhere else
const body0 = { tagName: 'BODY' }, html = { tagName: 'HTML' };
function box(l, t, w, h) { return { left: l, top: t, width: w, height: h, right: l + w, bottom: t + h }; }
const link = { tagName: 'A', rect: box(200, 100, 100, 30), getBoundingClientRect() { return this.rect; },
  closest(s) { return this; }, contains(c) { return c === this; } };
const document = { body: body0, documentElement: html,
  elementFromPoint(x, y) { const r = link.rect; return x >= r.left && x < r.right && y >= r.top && y < r.bottom ? link : body0; } };
body0.closest = () => null;
const run = (x, y, r) => new Function('document', 'innerWidth', 'innerHeight', 'return ' + assemble(x, y, r))(document, 1280, 720);

check(run(250, 115, 36) === 'in', 'on the link: in');
const near = run(250, 145, 36);   // 15 px below the link
check(near !== 'none' && near !== 'in', 'near: snaps (' + near + ')');
if (near && near[0] === '{') { const p = JSON.parse(near); check(p.x === 250 && p.y >= 100 && p.y < 130, 'near: onto the link ' + near); }
check(run(800, 600, 36) === 'none', 'far: none');

console.log((fails ? 'FAILED ' : 'ok ') + (checks - fails) + '/' + checks + ' OMNI_JS_TRIM_FIX_V1 pointer snap');
process.exit(fails ? 1 : 0);
