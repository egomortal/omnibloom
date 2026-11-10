#!/usr/bin/env python3
"""omni-launch: "the merged binary is the union of its components' changes, nothing else".

  additivity.py --label NAME --keys KEYS.txt --out DIR --target T.elf --base B.elf
                [--plus X.elf ...] [--minus Y.elf ...] [--nm NM.elf=UNSTRIPPED.elf ...]

For every check string in KEYS.txt (one per line) and for every defined symbol name (llvm-nm --defined-only of the
unstripped ELFs), the target's count must equal  base + sum(plus) - sum(minus).  Each component enters as its own build
minus the build it was made from, so the expected value is exactly "s3.4d plus each component's own delta".
Strings are counted as byte occurrences in the stripped/linked ELF. Symbol names are normalised only for compiler-made
local suffixes (.llvm.<n>, .cold/.part.<n>, __unnamed_<n>, the per-file counters of __cxx_global_array_dtor.<n> / __cxx_global_var_init.<n>), which change with layout, never with source.
Writes DIR/additivity-NAME.txt and exits 1 on any mismatch. Reads only; writes only DIR."""
import argparse, collections, re, subprocess, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--label', required=True); ap.add_argument('--keys', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--target', required=True); ap.add_argument('--base', required=True)
ap.add_argument('--plus', action='append', default=[]); ap.add_argument('--minus', action='append', default=[])
ap.add_argument('--nm', action='append', default=[], help='ELF=UNSTRIPPED mapping used for the symbol table')
ap.add_argument('--strings-only', action='store_true', help='skip the symbol tables (unstripped ELFs not available)')
ap.add_argument('--allow', default=None, help='regex: names/keys that belong to omni-launch\'s own switch layer (reported, not counted)')
a = ap.parse_args()
NM = '/usr/lib/llvm-21/bin/llvm-nm'
unstr = dict(x.split('=', 1) for x in a.nm)
keys = [k for k in Path(a.keys).read_text().splitlines() if k.strip()]
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
rep = []
def say(s): rep.append(s); print(s, flush=True)

def strings(p):
    b = Path(p).read_bytes()
    return {k: b.count(k.encode()) for k in keys}
NORM = [(re.compile(r'\.llvm\.\d+$'), ''), (re.compile(r'\.(cold|part|isra|constprop)\.\d+$'), ''), (re.compile(r'__unnamed_\d+'), '__unnamed_N'), (re.compile(r'^(__cxx_global_array_dtor|__cxx_global_var_init)\.\d+$'), r'\1.N')]
def symbols(p):
    q = unstr.get(p, p)
    r = subprocess.run([NM, '--defined-only', '--format=just-symbols', q], capture_output=True, text=True)
    if r.returncode: sys.exit(f'nm failed on {q}: {r.stderr[-300:]}')
    c = collections.Counter()
    for s in r.stdout.split():
        for rx, rep_ in NORM: s = rx.sub(rep_, s)
        c[s] += 1
    return c

terms = [(1, a.base)] + [(1, x) for x in a.plus] + [(-1, x) for x in a.minus]
say(f'# additivity {a.label}: target {a.target}')
say('# expected = ' + ' '.join(('+ ' if s > 0 else '- ') + x for s, x in terms))
bad = 0
S = {p: strings(p) for p in {a.target, *[x for _, x in terms]}}
say(f'\n## check strings ({len(keys)} keys, byte occurrences)')
for k in keys:
    exp = sum(s * S[p][k] for s, p in terms); got = S[a.target][k]
    flag = 'ok' if exp == got else ('SWITCH' if a.allow and re.search(a.allow, k) else 'MISMATCH'); bad += flag == 'MISMATCH'
    say(f'{flag:8} {k[:60]:60} target {got:4}  expected {exp:4}  (base {S[a.base][k]})')
if a.strings_only:
    say('\n## symbols: NOT CHECKED (--strings-only: the components\' unstripped ELFs are no longer on disk)')
    say(f'\nRESULT {a.label}: ' + ('STRINGS UNION EXACT (symbols not checked)' if bad == 0 else f'{bad} MISMATCHES') + (' + the omni-launch switch layer only' if a.allow else ''))
    (out / f'additivity-{a.label}.txt').write_text('\n'.join(rep) + '\n'); sys.exit(1 if bad else 0)
Y = {p: symbols(p) for p in {a.target, *[x for _, x in terms]}}
names = set().union(*[set(c) for c in Y.values()])
mism = []
for n in sorted(names):
    exp = sum(s * Y[p][n] for s, p in terms); got = Y[a.target][n]
    if exp != got: mism.append((n, got, exp))
added = sorted(n for n in names if Y[a.target][n] > Y[a.base][n]); removed = sorted(n for n in names if Y[a.target][n] < Y[a.base][n])
say(f'\n## symbols: target {sum(Y[a.target].values())} defined, base {sum(Y[a.base].values())}; '
    f'{len(added)} names gained and {len(removed)} lost vs base; {len(mism)} names off the expected union (switch layer listed separately)')
sw = [m for m in mism if a.allow and re.search(a.allow, m[0])]; mism = [m for m in mism if m not in sw]
for n, got, exp in sw: say(f'SWITCH   symbol {n}  target {got}  expected {exp}  (omni-launch switch layer)')
for n, got, exp in mism[:200]: say(f'MISMATCH symbol {n}  target {got}  expected {exp}')
(out / f'symbols-{a.label}-delta.txt').write_text('\n'.join(['# gained vs base'] + added + ['# lost vs base'] + removed) + '\n')
bad += len(mism)
say(f'\nRESULT {a.label}: ' + ('UNION EXACT (strings and symbols)' if bad == 0 else f'{bad} MISMATCHES') + (' + the omni-launch switch layer only' if a.allow else ''))
(out / f'additivity-{a.label}.txt').write_text('\n'.join(rep) + '\n')
sys.exit(1 if bad else 0)
