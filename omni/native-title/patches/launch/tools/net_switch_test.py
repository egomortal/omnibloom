#!/usr/bin/env python3
"""omni-launch host gate for the shipped omni_net_off(): extracts omniNetOffNames[] and omni_net_off() verbatim from the
tree's CurlContext.cpp, points "/data/omni/" at a scratch folder, compiles it with g++, and checks one process per flag
set (flags are read once per process): default (jscache off, every other fix on), net-on-jscache.flag (jscache on),
net-on + net-off-jscache (off), net5-off.flag (all off), one net-off-<name> (only that one off).
usage: net_switch_test.py <CurlContext.cpp> <scratch dir> [rc3|rc2] [CurlRequest.cpp for the rc4 hdrbuf opt-in]   -> prints PASS/FAIL lines, exit 1 on any FAIL"""
import os, re, subprocess, sys
src, tmp = sys.argv[1], sys.argv[2]; MODE = sys.argv[3] if len(sys.argv) > 3 else 'rc3'; os.makedirs(tmp, exist_ok=True); flags = os.path.join(tmp, 'flags/')
t = open(src).read().replace('\r\n', '\n')
names = re.search(r'static const char\* const omniNetOffNames\[\] = \{[^}]*\};', t)[0]
f = t[t.index('bool omni_net_off(int id)'):]; f = f[:f.index('\n}\n') + 3]
code = ('#include <atomic>\n#include <stdio.h>\n#include <string.h>\n#include <unistd.h>\n' + names + '\n' + f).replace('/data/omni/', flags)
code += r'''
int main() { int n = sizeof(omniNetOffNames) / sizeof(omniNetOffNames[0]); for (int i = 0; i < n; ++i) printf("%s=%d\n", omniNetOffNames[i], (int)omni_net_off(i)); return 0; }
'''
open(os.path.join(tmp, 't.cpp'), 'w').write(code)
r = subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', os.path.join(tmp, 't.cpp'), '-o', os.path.join(tmp, 't')], capture_output=True, text=True)
if r.returncode: print('FAIL compile: ' + r.stderr[-600:]); sys.exit(1)
ids = re.findall(r'"([a-z0-9]+)"', names); bad = 0
def run(set_):
    os.makedirs(flags, exist_ok=True)
    for x in os.listdir(flags): os.unlink(flags + x)
    for x in set_: open(flags + x, 'w').close()
    out = subprocess.run([os.path.join(tmp, 't')], capture_output=True, text=True)
    return {k: int(v) for k, v in (l.split('=') for l in out.stdout.split())}, out.stderr
def ck(label, set_, want):
    global bad
    got, err = run(set_); ok = got == want; bad += not ok
    print(('PASS ' if ok else 'FAIL ') + f'{label}: off = {sorted(k for k, v in got.items() if v)}' + ('' if ok else f'  want {sorted(k for k, v in want.items() if v)}'))
off = lambda *ks: {k: int(k in ks) for k in ids}
J = ('jscache',) if MODE == 'rc3' else ()      # rc3: the JS bytecode cache is opt-in; rc2: every fix on by default
ck('default (no flags)', [], off(*J))
if MODE == 'rc3':
    ck('net-on-jscache.flag', ['net-on-jscache.flag'], off())
    ck('net-on-jscache + net-off-jscache', ['net-on-jscache.flag', 'net-off-jscache.flag'], off('jscache'))
    ck('net5-off + net-on-jscache', ['net5-off.flag', 'net-on-jscache.flag'], off(*ids))
ck('net5-off.flag', ['net5-off.flag'], off(*ids))
ck('net-off-castore.flag', ['net-off-castore.flag'], off('castore', *J))
# rc4: OMNI_NET_HDRBUF_OPTIN_V1 in CurlRequest.cpp's omniHdrBufOff() (argv[4] = CurlRequest.cpp)
if len(sys.argv) > 4:
    r = open(sys.argv[4]).read().replace('\r\n', '\n')
    g = r[r.index('bool omniHdrBufOff()'):]; g = g[:g.index('\n}\n') + 3]
    hc = ('#include <atomic>\n#include <stdio.h>\n#include <unistd.h>\n' + g).replace('/data/omni/', flags)
    hc += 'int main() { printf("%d\\n", (int)omniHdrBufOff()); return 0; }\n'
    open(os.path.join(tmp, 'h.cpp'), 'w').write(hc)
    r2 = subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', os.path.join(tmp, 'h.cpp'), '-o', os.path.join(tmp, 'h')], capture_output=True, text=True)
    if r2.returncode: print('FAIL hdrbuf compile: ' + r2.stderr[-400:]); bad += 1
    else:
        for label, set_, want in (('hdrbuf default', [], 1), ('hdrbuf net-on-hdrbuf', ['net-on-hdrbuf.flag'], 0), ('hdrbuf net-on + net-off-hdrbuf', ['net-on-hdrbuf.flag', 'net-off-hdrbuf.flag'], 1)):
            run(set_); out = subprocess.run([os.path.join(tmp, 'h')], capture_output=True, text=True)
            ok = out.stdout.strip() == str(want); bad += not ok
            print(('PASS ' if ok else 'FAIL ') + f'{label}: omniHdrBufOff() = {out.stdout.strip()} (want {want}) {out.stderr.strip()[:80]}')
print('NET SWITCH TEST', 'PASS' if not bad else f'FAIL ({bad})'); sys.exit(1 if bad else 0)
