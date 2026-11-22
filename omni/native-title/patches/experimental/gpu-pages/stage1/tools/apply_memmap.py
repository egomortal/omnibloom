#!/usr/bin/env python3
"""OMNI_MEMMAP_V1 (2026-11-17, page-table headroom for layers): a test-only map of the TITLE's own memory.

Why: the layers-on hang tracks the console's "page table CPU" count (11-15 hang at 6681/8192). The shell alone is ~5220;
a near-empty page costs the Omni title +720 (title 1.19 GB resident), 4K YouTube +1200-1570, and no switch (GPU display,
GPU video, JIT) moves it (ptattr test, START-HERE 2026-11-17). Before shrinking anything we need to know WHAT the title
maps. With /data/omni/memmap.flag a detached thread walks this process's mappings (sceKernelVirtualQuery, find-next)
5 s after the first shell phase and then every 20 s, and logs (OMNI HOLEPUNCH: memmap ...):
  memmap #N total X MB in R regions, S 2MB-slots (page-table-page estimate)
  memmap #N <kind>:<name>: X MB, S slots, R regions          (top 24 by slots; kind D direct, F flexible, P pooled,
                                                              S stack, - other)
Off (no flag): one access() on the first shell phase, nothing else. No allocation on any hot path.
Patches engine/media/OmniHwService.cpp; must run BEFORE prep_launch.py (prep copies engine/media into the objs dir).
usage: apply_memmap.py <$NE (holding engine/media)>   prints "applied" / "already"."""
import shutil
import sys
from pathlib import Path

MARK = 'OMNI_MEMMAP_V1'
p = Path(sys.argv[1]) / 'engine/media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')

MARK2 = 'OMNI_MEMMAP_V2'


def v2(s):
    """OMNI_MEMMAP_V2 (2026-11-18): also list every direct-memory region (biggest first, up to 40) on passes 1, 4, 7...
    so the non-GPU floor (524 MB on example.com) and the GPU paths' share (~289 MB) can be named by size."""
    if MARK2 in s:
        return s, False
    a0 = '    uintptr_t addr = 0;\n    for (int guard = 0; guard < 400000; ++guard) {\n'
    a1 = '        Row& r = rows[key];\n'
    a2 = '    holeNote("memmap #%d total %llu MB in %llu regions, %llu 2MB-slots (OMNI_MEMMAP_V1)", pass,\n'
    for a in (a0, a1, a2):
        if s.count(a) != 1:
            sys.exit('V2 anchor found %d times: %r' % (s.count(a), a[:60]))
    s = s.replace(a0, '    struct DReg { uint64_t s, e, off; int prot; };   // ' + MARK2 + '\n    std::vector<DReg> dregs;\n' + a0, 1)
    s = s.replace(a1, "        if (kind == 'D') { int64_t off = 0; int32_t prot = 0; memcpy(&off, info + 16, 8); memcpy(&prot, info + 24, 4);"
                      " dregs.push_back({uint64_t(s), uint64_t(e), uint64_t(off), prot}); }   // " + MARK2 + '\n' + a1, 1)
    s = s.replace(a2, '    if (pass % 3 == 1) {   // ' + MARK2 + ': each direct region, biggest first\n'
                      '        std::sort(dregs.begin(), dregs.end(), [](const DReg& a, const DReg& b) { return a.e - a.s > b.e - b.s; });\n'
                      '        for (size_t i = 0; i < dregs.size() && i < 40; ++i)\n'
                      '            holeNote("memmap #%d D region %zu: %llu KB at %#llx prot %#x direct offset %#llx", pass, i,\n'
                      '                (unsigned long long)((dregs[i].e - dregs[i].s) >> 10), (unsigned long long)dregs[i].s,'
                      ' unsigned(dregs[i].prot), (unsigned long long)dregs[i].off);\n'
                      '    }\n' + a2, 1)
    return s, True

if MARK in s:
    s, changed = v2(s)
    if not changed:
        print('already'); sys.exit(0)
    bak = p.with_name(p.name + '.before-memmap-v2')
    if not bak.exists():
        shutil.copy2(p, bak)
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    print('applied V2 (upgrade)')
    sys.exit(0)

ANCHOR_FN = 'void holePunchShellPhase(int phase)\n{\n    diagnosticTrace(28,phase);\n'
if s.count(ANCHOR_FN) != 1:
    sys.exit('anchor holePunchShellPhase found %d times' % s.count(ANCHOR_FN))

BLOCK = r'''// OMNI_MEMMAP_V1 (test only, /data/omni/memmap.flag): this process's mappings by name/type every 20 s. See
// omni-gpu-pages/stage1/tools/apply_memmap.py.
namespace {
void omniMemmapWalk(int (*vq)(const void*, int, void*, size_t), int pass)
{
    struct Row { uint64_t bytes = 0, slots = 0, regions = 0; };
    std::map<std::string, Row> rows;
    Row all;
    uint64_t lastSlot = ~0ull;
    uintptr_t addr = 0;
    for (int guard = 0; guard < 400000; ++guard) {
        alignas(8) unsigned char info[128] = {};
        if (vq(reinterpret_cast<const void*>(addr), 1, info, 72) != 0) break;   // 1 = find next
        uintptr_t s = 0, e = 0;
        memcpy(&s, info, 8); memcpy(&e, info + 8, 8);
        if (e <= s || e <= addr) break;
        const unsigned char bits = info[32];
        // SceKernelVirtualQueryInfo: name after a one-byte bit field (0x21); fall back to 0x24 if the SDK packed it in 4.
        const unsigned char* nm = info + 33;
        if (!nm[0] && info[36] >= 0x20 && info[36] < 0x7f) nm = info + 36;
        char name[33]; memcpy(name, nm, 32); name[32] = 0;
        for (char* c = name; *c; ++c) if (*c < 0x20 || *c > 0x7e) *c = '?';
        char kind = (bits & 4) ? 'S' : (bits & 2) ? 'D' : (bits & 8) ? 'P' : (bits & 1) ? 'F' : '-';
        std::string key = std::string(1, kind) + ":" + (name[0] ? name : "(anon)");
        const uint64_t first = uint64_t(s) >> 21, last = (uint64_t(e) - 1) >> 21;
        uint64_t slots = last - first + 1;
        if (first == lastSlot && slots) --slots;
        lastSlot = last;
        Row& r = rows[key];
        r.bytes += e - s; r.slots += slots; ++r.regions;
        all.bytes += e - s; all.slots += slots; ++all.regions;
        addr = e;
    }
    holeNote("memmap #%d total %llu MB in %llu regions, %llu 2MB-slots (OMNI_MEMMAP_V1)", pass,
        (unsigned long long)(all.bytes >> 20), (unsigned long long)all.regions, (unsigned long long)all.slots);
    std::vector<std::pair<std::string, Row>> v(rows.begin(), rows.end());
    std::sort(v.begin(), v.end(), [](const auto& a, const auto& b) { return a.second.slots != b.second.slots ? a.second.slots > b.second.slots : a.second.bytes > b.second.bytes; });
    for (size_t i = 0; i < v.size() && i < 24; ++i)
        holeNote("memmap #%d %s: %llu MB, %llu slots, %llu regions", pass, v[i].first.c_str(),
            (unsigned long long)(v[i].second.bytes >> 20), (unsigned long long)v[i].second.slots, (unsigned long long)v[i].second.regions);
}
void omniMemmapStart()
{
    auto vq = reinterpret_cast<int (*)(const void*, int, void*, size_t)>(dlsym(RTLD_DEFAULT, "sceKernelVirtualQuery"));
    if (!vq) { holeNote("memmap off: sceKernelVirtualQuery not found (OMNI_MEMMAP_V1)"); return; }
    holeNote("memmap on: every 20 s (OMNI_MEMMAP_V1)");
    std::thread([vq] { sleep(5); for (int pass = 1;; ++pass) { omniMemmapWalk(vq, pass); sleep(20); } }).detach();
}
}

'''
HOOK = ('    { static int omniMemmapState = 0; if (!omniMemmapState) { omniMemmapState = access("/data/omni/memmap.flag", F_OK) == 0 ? 1 : -1;'
        ' if (omniMemmapState == 1) omniMemmapStart(); } }   // OMNI_MEMMAP_V1\n')
s = s.replace(ANCHOR_FN, BLOCK + ANCHOR_FN + HOOK, 1)
bak = p.with_name(p.name + '.before-memmap')
if not bak.exists():
    shutil.copy2(p, bak)
s, _ = v2(s)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied (V1 + V2)')
