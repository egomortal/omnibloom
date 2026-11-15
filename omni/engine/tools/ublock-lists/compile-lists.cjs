// Compile Omni's network rule sets with the shipped upstream engine bundle.
// SPDX-License-Identifier: GPL-3.0-or-later
// Outputs:
//   out/ublock-compiled-full.txt          full network set (block, exceptions,
//                                          removeparam, urlskip, popup …) → promote.cjs
//                                          installs it as resources/ublock-compiled.txt
//   engine/resources/ublock-popup-compiled.txt  `$popup` filters only, for the
//                                          browser shell's popup check
// uBlock's own lists (and Omni's link-skip list) are compiled as trusted sources,
// matching upstream: trusted-only options such as urlskip are accepted only there.
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const root = path.resolve(__dirname, '../../..');   // omni/ (paths below are engine/resources/...); lists and inputs live next to this script
const HERE = __dirname;
const L = path.join(HERE, 'lists');   // fetch-lists.sh downloads uBlock Origin's lists here (not committed)
const TRUE = new Set(['ext_ublock']);
const evalCond = expr => { const js = expr.replace(/[A-Za-z_][A-Za-z0-9_]*/g, t => TRUE.has(t) ? 'true' : 'false'); if (!/^[truefals!&|() \t]*$/.test(js)) throw new Error('bad cond ' + expr); return Function('return (' + js + ')')(); };
function expand(file, seen = new Set()) {
  if (seen.has(file)) return ''; seen.add(file);
  const out = [], stack = [];
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    let m;
    if ((m = line.match(/^!#if\s+(.*)$/))) { stack.push({ on: evalCond(m[1].trim()) }); continue; }
    if (/^!#else\b/.test(line)) { stack[stack.length - 1].on = !stack[stack.length - 1].on; continue; }
    if (/^!#endif\b/.test(line)) { stack.pop(); continue; }
    if (!stack.every(s => s.on)) continue;
    if ((m = line.match(/^!#include\s+(\S+)/))) { const inc = path.join(path.dirname(file), m[1]); if (fs.existsSync(inc)) out.push(expand(inc, seen)); else console.error('missing include', m[1]); continue; }
    out.push(line);
  }
  return out.join('\n');
}
const LISTS = [
  // [file, trusted, group]
  ['ubo-filters.txt', true, 'ads'], ['ubo-privacy.txt', true, 'privacy'], ['ubo-badware.txt', true, 'malware'],
  ['ubo-unbreak.txt', true, 'unbreak'], ['ubo-quick-fixes.txt', true, 'ads'],
  ['ubo-annoyances-cookies.txt', true, 'annoyances'], ['ubo-annoyances-others.txt', true, 'annoyances'],
  ['easylist.txt', false, 'ads'], ['easyprivacy.txt', false, 'privacy'],
  ['easylist-cookies.txt', false, 'annoyances'], ['easylist-newsletters.txt', false, 'annoyances'],
  ['easylist-notifications.txt', false, 'annoyances'], ['easylist-annoyances.txt', false, 'annoyances'],
  ['easylist-chat.txt', false, 'annoyances'], ['ubo-privacy-removeparam.txt', false, 'privacy'],
];
const sources = LISTS.map(([f, trusted, group]) => ({ name: f, trusted, group, text: expand(path.join(L, f)) }));
sources.push({ name: 'peter-lowe-hosts.txt', trusted: false, group: 'ads', text: fs.readFileSync(path.join(HERE, 'peter-lowe-hosts.txt'), 'utf8') });
sources.push({ name: 'omni-link-skip.txt', trusted: true, group: 'links', text: fs.readFileSync(path.join(HERE, 'omni-link-skip.txt'), 'utf8') });

const bundle = fs.readFileSync(path.join(root, 'engine/resources/ublock-engine.js'), 'utf8');
const suffixes = fs.readFileSync(path.join(root, 'engine/resources/public-suffix-list.dat'), 'utf8');
const cc = vm.createContext({ URL, TextDecoder, setTimeout, clearTimeout, console });
vm.runInContext(bundle, cc);
let t0 = Date.now();
const full = cc.OmniUBlock.compileLists(sources.map(s => ({ text: s.text, trusted: s.trusted })));
console.log(`full: ${sources.length} lists, compile ${Date.now() - t0} ms, ${full.errors.length} errors, ${Buffer.byteLength(full.compiled)} bytes`);
if (full.errors.length) console.log(full.errors.slice(0, 5));
const isPopup = l => /\$(?:[^$]*,)?(?:popup|popunder)(?:[,=]|$)/.test(l) && !l.startsWith('!');
const popup = cc.OmniUBlock.compileLists(sources.map(s => ({ text: s.text.split('\n').filter(isPopup).join('\n'), trusted: s.trusted })));
console.log(`popup subset: ${popup.compiled.length} bytes, ${popup.errors.length} errors`);
// Validate in a bare runtime like the console's (no URL/atob globals).
for (const [name, c] of [['full', full.compiled], ['popup', popup.compiled]]) {
  const rt = vm.createContext({ TextDecoder, setTimeout: () => 0, clearTimeout() {} });
  vm.runInContext(bundle, rt);
  t0 = Date.now(); const info = rt.OmniUBlock.initialize(c, suffixes);
  console.log(`  ${name}: accepted ${info.accepted}, discarded ${info.discarded}, init ${Date.now() - t0} ms`);
}
if (Buffer.byteLength(full.compiled) > 8 * 1024 * 1024) throw new Error('full set exceeds the 8 MiB asset limit in OmniUBlock.cpp');
// Native popup rules for the browser shell (UI process). Format v2, one rule
// per line, tab-separated: kind, flags, pattern, opener domains, target domains.
//   kind: H `||host^`, P URL pattern (* ^ | ||), R regular expression
//   flags (or -): x exception, t third-party, f first-party, s strict3p,
//                 i important, c match-case
//   domains: uBlock `domain=`/`from=` (opener) and `to=` (popup) lists, | separated,
//            ~ negates, `name.*` matches any suffix; - when absent.
//   R rules add a sixth field: space-separated text every match contains (or -), checked
//   before the regular expression runs.
// `$popup` rules that also name other types (doc, frame, script…) still apply to
// popups. `badfilter` removes the rule it names. Rules with options the shell
// can't evaluate (popunder, denyallow, header…) are left out and counted.
const popupLines = [];
const seenPopup = new Set();
const popupSkipped = {};
const typeOptions = new Set(['doc', 'document', 'frame', 'subdocument', 'script', 'xhr', 'xmlhttprequest', 'image', 'stylesheet', 'css', 'object', 'media', 'font', 'ping', 'other', 'all']);
const parsePopup = (line) => {
  let exception = false, rule = line;
  if (rule.startsWith('@@')) { exception = true; rule = rule.slice(2); }
  const dollar = rule.lastIndexOf('$'); if (dollar < 0) return null;
  const pattern = rule.slice(0, dollar), options = rule.slice(dollar + 1).split(',').map(o => o.trim()).filter(Boolean);
  const r = { exception, pattern, flags: new Set(), domains: '-', to: '-', badfilter: false, popup: false, skip: null };
  for (const o of options) {
    const [name, value] = [o.split('=')[0].toLowerCase(), o.includes('=') ? o.slice(o.indexOf('=') + 1) : null];
    if (name === 'popup') r.popup = true;
    else if (name === 'third-party' || name === '3p' || name === '~first-party' || name === '~1p') r.flags.add('t');
    else if (name === 'first-party' || name === '1p' || name === '~third-party' || name === '~3p') r.flags.add('f');
    else if (name === 'strict3p' || name === 'strict-third-party') r.flags.add('s');
    else if (name === 'important') r.flags.add('i');
    else if (name === 'match-case') r.flags.add('c');
    else if (name === 'badfilter') r.badfilter = true;
    else if ((name === 'domain' || name === 'from') && value) r.domains = value.toLowerCase();
    else if (name === 'to' && value) r.to = value.toLowerCase();
    else if (typeOptions.has(name)) continue;
    else r.skip = r.skip || name;
  }
  return r;
};
// Literal pieces every match of a regular expression must contain (space-
// separated, 2+ characters each), so the shell can skip the JavaScript engine
// for URLs that can't match. Conservative: only top-level characters outside classes and
// groups, not followed by a quantifier; an alternation at top level gives none.
const requiredLiteral = (source, matchCase) => {
  const runs = []; let run = '', depth = 0;
  const flush = () => { if (run) runs.push(run); run = ''; };
  for (let i = 0; i < source.length; i++) {
    const c = source[i];
    if (c === '[') { flush(); i++; if (source[i] === '^') i++; if (source[i] === ']') i++; while (i < source.length && source[i] !== ']') { if (source[i] === '\\') i++; i++; } continue; }
    const quantifier = c === '{' ? source.slice(i).match(/^\{\d+(?:,\d*)?\}/) : null;
    if (quantifier) { flush(); i += quantifier[0].length - 1; continue; }
    if (c === '(') { flush(); depth++; continue; }
    if (c === ')') { flush(); depth--; continue; }
    if (depth > 0) { if (c === '\\') i++; continue; }
    if (c === '|') return '';
    let literal = null, next = i + 1;
    if (c === '\\') { const e = source[i + 1]; next = i + 2; if (e && /[\/.?*+()[\]{}|^$\\\-:=&%#@!,;'"~]/.test(e)) literal = e; }
    else if (!'^$.*+?{}'.includes(c)) literal = c;
    const q = source[next];
    if (literal === null) { flush(); i = next - 1; continue; }
    if (q === '?' || q === '*' || q === '{') { flush(); i = next - 1; continue; }
    run += literal;
    if (q === '+') flush();
    i = next - 1;
  }
  flush();
  const needed = [...new Set(runs.filter(r => r.length >= 2 && !/\s/.test(r)).map(r => matchCase ? r : r.toLowerCase()))];
  return needed.join(' ');
};
// Times an expression on long URLs built from the characters it accepts; the
// console's popup check passes at most 4,096 characters to a regex.
const slowRegex = (source, matchCase) => {
  let re; try { re = new RegExp(source, matchCase ? '' : 'i'); } catch (e) { return 'invalid'; }
  const pieces = ['a', 'A', '0', '.', '/', '-', '_', '=', '&', '?', '%', 'a.', 'a/', 'a0', 'ab', 'a=a&', '/a', '.a', 'aaaa.', '0/'];
  // Growing lengths, so exponential cases show up long before they hang the build.
  for (const length of [8, 12, 16, 20, 24, 32, 64, 256, 1024, 4095]) for (const prefix of ['https://', 'http://', 'about:blank', 'https://link1.']) for (const p of pieces) for (const tail of ['!', '', ' ', '\u0000']) {
    const text = (prefix + p.repeat(length)).slice(0, prefix.length + length) + tail;
    const t0 = process.hrtime.bigint(); re.test(text);
    const ms = Number(process.hrtime.bigint() - t0) / 1e6;
    if (ms > 20) return `${ms.toFixed(0)} ms on ${JSON.stringify(text.slice(0, 24))}…`;
  }
  return '';
};
// uBlock compares filters by their options regardless of order; `*` and an
// empty pattern are the same filter.
const popupKey = (r, domains = r.domains) => [r.exception ? '@@' : '', r.pattern === '' ? '*' : r.pattern, [...r.flags].sort().join(''), domains, r.to].join('\u0001');
const parsedPopup = [];
for (const src of sources) for (const raw of src.text.split('\n')) {
  const line = raw.trim();
  if (!isPopup(line) || line.startsWith('!') || line.includes('#')) continue;
  const r = parsePopup(line);
  if (!r) continue;
  if (!r.popup && !r.badfilter) { popupSkipped['popunder only'] = (popupSkipped['popunder only'] || 0) + 1; continue; }
  if (r.skip) { popupSkipped[r.skip] = (popupSkipped[r.skip] || 0) + 1; continue; }
  if (/\s/.test(r.pattern)) { popupSkipped.whitespace = (popupSkipped.whitespace || 0) + 1; continue; }
  parsedPopup.push(r);
}
const badPopup = new Set(parsedPopup.filter(r => r.badfilter).map(r => popupKey(r)));
// A badfilter naming some of a filter's domains removes just those domains
// (uBlock: `*$popup,3p,domain=voe.sx,badfilter` against a long EasyList entry).
const badDomains = new Map();
for (const r of parsedPopup) if (r.badfilter && r.domains !== '-') {
  const k = popupKey(r, '');
  if (!badDomains.has(k)) badDomains.set(k, new Set());
  for (const d of r.domains.split('|')) badDomains.get(k).add(d);
}
for (const r of parsedPopup) {
  if (r.badfilter || badPopup.has(popupKey(r))) continue;
  if (r.domains !== '-' && badDomains.has(popupKey(r, ''))) {
    const drop = badDomains.get(popupKey(r, '')), kept = r.domains.split('|').filter(d => !drop.has(d));
    if (kept.length === r.domains.split('|').length) { /* unrelated */ }
    else if (!kept.some(d => !d.startsWith('~'))) continue;
    else r.domains = kept.join('|');
  }
  const flags = [...r.flags].sort().join('') + (r.exception ? 'x' : '');
  let kind, pattern = r.pattern;
  if (pattern.length > 2 && pattern.startsWith('/') && pattern.endsWith('/')) { kind = 'R'; pattern = pattern.slice(1, -1); }
  else {
    const host = pattern.match(/^\|\|([a-z0-9.-]+\.[a-z0-9-]+)\^?$/i);
    if (host) { kind = 'H'; pattern = host[1].toLowerCase(); }
    else {
      kind = 'P';
      if (pattern === '' || pattern === '*') pattern = '*';
      else if (pattern.length < 3 && r.domains === '-' && r.to === '-') { popupSkipped['too short'] = (popupSkipped['too short'] || 0) + 1; continue; }
      if (!r.flags.has('c')) pattern = pattern.toLowerCase();
    }
  }
  if (/[\t\n]/.test(pattern)) continue;
  const fields = [kind, flags || '-', pattern, r.domains, r.to];
  if (kind === 'R') {
    // The shell runs these on its UI thread: leave out any expression that is
    // slow on long adversarial URLs (catastrophic backtracking).
    const slow = slowRegex(pattern, r.flags.has('c'));
    if (slow) { popupSkipped['slow regex'] = (popupSkipped['slow regex'] || 0) + 1; console.log(`  popup regex left out (${slow}): /${pattern}/`); continue; }
    fields.push(requiredLiteral(pattern, r.flags.has('c')) || '-');
  }
  if (fields.some(f => /\t/.test(f))) continue;
  const entry = fields.join('\t');
  if (!seenPopup.has(entry)) { seenPopup.add(entry); popupLines.push(entry); }
}
fs.writeFileSync(path.join(root, 'engine/resources/ublock-popup-rules.txt'), '# Omni native popup rules v2 (generated by compile-lists.cjs from uBlock $popup filters)\n' + popupLines.join('\n') + '\n');
const countKind = (k, x) => popupLines.filter(l => l[0] === k && (x === undefined || l.split('\t')[1].includes('x') === x)).length;
console.log(`native popup rules: ${popupLines.length} (${countKind('H')} hosts, ${countKind('P')} patterns, ${countKind('R')} regexes, ${popupLines.filter(l => l.split('\t')[1].includes('x')).length} exceptions, ${popupLines.filter(l => l.split('\t')[3] !== '-' || l.split('\t')[4] !== '-').length} domain-limited; ${badPopup.size} badfilters applied; left out: ${JSON.stringify(popupSkipped)})`);
fs.mkdirSync(path.join(HERE, 'out'), { recursive: true });
fs.writeFileSync(path.join(HERE, 'out/ublock-compiled-full.txt'), full.compiled);   // promote.cjs copies it into resources
fs.writeFileSync(path.join(root, 'engine/resources/ublock-popup-compiled.txt'), popup.compiled);
fs.writeFileSync(path.join(HERE, 'out/ublock-compiled-full.manifest.json'), JSON.stringify({
  generated: new Date().toISOString(),
  lists: sources.map(s => ({ name: s.name, trusted: s.trusted, group: s.group, lines: s.text.split('\n').length })),
  bytes: Buffer.byteLength(full.compiled), popupBytes: popup.compiled.length,
}, null, 1));
