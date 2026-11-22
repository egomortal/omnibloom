#!/usr/bin/env python3
"""OMNI_LAYERS_4K_CAP_V1 (2026-11-19, owner: "go all the way" - part 1 of the page-table governor).

Measured (g9f, 4K HDR YouTube, kernel "page table CPU" peaks; the console hangs at ~6,700-6,950 of 8,192):
  layers ON  + 2160p: 6,880 peak; hung on 2026-11-18 22:07Z and 2026-11-19 21:36Z (even with the video trim)
  layers OFF + 2160p: 6,528 peak; never hung
A 2160p stream costs ~1,000 page tables more than a 1440p one in the title alone (decoder 820 MB + pace queue ~1 GiB vs
426 MB + ~1 GiB at 1440p), so while page layers are on, Omni answers navigator.mediaCapabilities.decodingInfo for video
above 2560x1440 with supported=false. YouTube (and other players that ask) then pick 1440p, which still plays in HDR.
Nothing else changes: layers off (gpu-pages-stage1-off.flag) answers as before; /data/omni/layers-4k.flag lifts the
cap for tests. Each refusal is logged ("OMNI MEDIACAPS ... (4K paused: page layers on ...)", first 48 lines).
Patches engine/entry/OmniMSEPlayer.cpp (no backup: the child recipe's changed-file gate).
usage: apply_layers_4k_cap.py <engine dir holding entry/>"""
import sys
from pathlib import Path

MARK = 'OMNI_LAYERS_4K_CAP_V1'
p = Path(sys.argv[1]) / 'entry' / 'OmniMSEPlayer.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
OLD = '    Answer answer = decide(query);\n'
NEW = ('    Answer answer = decide(query);\n'
       '    // ' + MARK + ': above 1440p a stream does not fit the kernel page-table pool next to page layers (hangs measured)\n'
       '    if (answer.supported && query.video && int64_t(query.video->width) * query.video->height > int64_t(2560) * 1440) {\n'
       '        static const bool layersOn = access("/data/omni/gpu-pages-stage1-off.flag", F_OK) != 0;\n'
       '        static const bool allow4k = access("/data/omni/layers-4k.flag", F_OK) == 0;\n'
       '        if (layersOn && !allow4k)\n'
       '            answer = refuse("4K paused: page layers on (page-table headroom)");\n'
       '    }\n')
if s.count(OLD) != 1:
    sys.exit('%s: anchor found %d times' % (p.name, s.count(OLD)))
s = s.replace(OLD, NEW, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)

# V2 (2026-11-19 23:45Z): YouTube ignored decodingInfo's "no" and opened 3840x2160 anyway (g9h runs): it asks
# MediaSource.isTypeSupported('video/webm; codecs="vp09..."; width=3840; height=2160'), which goes through
# omniMSETypeSupport (OmniMSESource.h, also addSourceBuffer) and never looked at width/height. Same rule there.
MARK2 = 'OMNI_LAYERS_4K_CAP_V2'
h = Path(sys.argv[1]) / 'entry' / 'OmniMSESource.h'
raw = h.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK2 in s:
    print('already', h.name); sys.exit(0)
OLD2 = '    auto container = type.containerType().utf8();\n'
NEW2 = ('    {   // ' + MARK2 + ': width=/height= above 2560x1440 while page layers are on -> not supported (page-table pool)\n'
        '        auto ws = type.parameter("width"_s).utf8(), hs = type.parameter("height"_s).utf8();\n'
        '        const long long w = ws.length() ? std::atoll(reinterpret_cast<const char*>(ws.data())) : 0;\n'
        '        const long long h = hs.length() ? std::atoll(reinterpret_cast<const char*>(hs.data())) : 0;\n'
        '        if (w * h > 2560LL * 1440) {\n'
        '            static const bool layersOn = access("/data/omni/gpu-pages-stage1-off.flag", F_OK) != 0;\n'
        '            static const bool allow4k = access("/data/omni/layers-4k.flag", F_OK) == 0;\n'
        '            if (layersOn && !allow4k) {\n'
        '                static unsigned logged;\n'
        '                if (logged++ < 8) { fprintf(stderr, "OMNI MEDIACAPS: isTypeSupported %lldx%lld -> no (4K paused: page layers on)\\n", w, h); fflush(stderr); }\n'
        '                return OmniMedia::Caps::Support::No;\n'
        '            }\n'
        '        }\n'
        '    }\n'
        '    auto container = type.containerType().utf8();\n')
if s.count(OLD2) != 1:
    sys.exit('%s: anchor found %d times' % (h.name, s.count(OLD2)))
s = s.replace(OLD2, NEW2, 1)
if '#include <unistd.h>' not in s:
    s = s.replace('#include <string>\n', '#include <string>\n#include <unistd.h> // ' + MARK2 + '\n#include <cstdio> // ' + MARK2 + '\n#include <cstdlib> // ' + MARK2 + '\n', 1)
h.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', h.name)
