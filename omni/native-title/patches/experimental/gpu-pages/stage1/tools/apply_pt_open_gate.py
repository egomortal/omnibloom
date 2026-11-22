#!/usr/bin/env python3
"""OMNI_PT_OPEN_GATE_V1 (2026-11-20, owner: "go all the way" - page-table governor, the decoder gate).

g9k (2026-11-20 03:49Z) hung although its backstop worked (it read 6723 via the engine starter and capped the queue):
the climb past the line came from the 4K decoder (gpu + cpu_gpu + input + 8 output frames = 820 MB ~= 410 page tables)
and the web process. YouTube ignores "no" answers for 3840x2160 (isTypeSupported / decodingInfo), so the gate sits
where the stream starts: the title's decoder open (both call sites: handleConfigure and the configure worker).

Cost of an open, measured 2026-11-19 (memtrace): 2160p10 820 MB, 1440p10 426 MB, 1080p10 278 MB ->
  cost ~= 410 * pixels / (3840*2160) + 40 page tables.
Refused (logged "OMNI PT GATE: ...", the open fails like any decoder failure) when the current count + cost reaches
  - the line (omniPtLine(), default 6,400) for streams above 2560x1440, or
  - 6,700 (where hangs begin) for any stream.
Reads the count fresh (the engine starter when the direct call is missing). Off with /data/omni/pt-backstop-off.flag
(the line is 0 then). Needs OMNI_PT_BACKSTOP_V5 (apply_pt_backstop.py) in the same file first.
Patches engine/media/OmniHwService.cpp; must run BEFORE prep_launch.py. usage: apply_pt_open_gate.py <$NE>"""
import sys
from pathlib import Path

MARK = 'OMNI_PT_OPEN_GATE_V1'
p = Path(sys.argv[1]) / 'engine/media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
if 'OMNI_PT_BACKSTOP_V5' not in s:
    sys.exit('needs OMNI_PT_BACKSTOP_V5 first')

GATE = ('// ' + MARK + ': refuse a decoder open that would push the kernel page-table pool into the hang zone\n'
        'static int omniPtOpenGate(int w, int h, std::string& stage)\n'
        '{\n'
        '    const int line = omniPtLine();\n'
        '    if (!line || w <= 0 || h <= 0) return 0;\n'
        '    if (!omniPtDirect()) omniPtAskStarter();\n'
        '    int total = 0;\n'
        '    const int used = omniPtUsed(&total);\n'
        '    if (used < 0) return 0;   // unknown: as before\n'
        '    const int cost = int(410.0 * double(w) * h / (3840.0 * 2160.0)) + 40;\n'
        '    const bool big = int64_t(w) * h > int64_t(2560) * 1440;\n'
        '    const int limit = big ? line : std::max(line, 6700);\n'
        '    if (used + cost < limit) return 0;\n'
        '    fprintf(stderr, "OMNI PT GATE: %dx%d decoder refused: %d/%d page tables + ~%d would reach %d\\n", w, h, used, total, cost, limit);\n'
        '    fflush(stderr);\n'
        '    stage = "page-table gate";\n'
        '    return -1;\n'
        '}\n')
A1 = 'void handleConfigure(Channel& c, const Message& in)\n{\n'
B1 = '    int rc = c.decoder.open(codec, int(in.b), depth, w, h, stage);\n'
N1 = '    int rc = omniPtOpenGate(w, h, stage);   // ' + MARK + '\n    if (!rc) rc = c.decoder.open(codec, int(in.b), depth, w, h, stage);\n'
B2 = '        const int rc = c->decoder.open(v5Codec(in), int(in.b), in.c > 8 ? 10 : 8, int(in.d), int(in.e), stage);\n'
N2 = ('        int rc = omniPtOpenGate(int(in.d), int(in.e), stage);   // ' + MARK + '\n'
      '        if (!rc) rc = c->decoder.open(v5Codec(in), int(in.b), in.c > 8 ? 10 : 8, int(in.d), int(in.e), stage);\n')
for o in (A1, B1, B2):
    if s.count(o) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(o), o.strip()[:70]))
# the gate must be defined before both call sites: put it before the first of them
first = min(s.index(B2), s.index(A1))
line_start = s.rfind('\n\n', 0, first) + 2
s = s[:line_start] + GATE + '\n' + s[line_start:]
s = s.replace(B1, N1, 1).replace(B2, N2, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
