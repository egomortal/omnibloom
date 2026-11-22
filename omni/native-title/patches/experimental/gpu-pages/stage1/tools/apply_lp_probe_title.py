#!/usr/bin/env python3
"""OMNI_LP_PROBE_TITLE_V1 (2026-11-20, owner: "do the long path" - lower the page-table cost in general).

Payload probe (outputs/omni-ptprobe/lpprobe.c) showed anonymous memory costs one kernel page-table page per 2 MiB with or
without 2 MiB alignment / MAP_ALIGNED_SUPER (+256 for 512 MiB each time), and payloads get no direct memory at all. The
decoder + pace queue use DIRECT memory (OmniHwBackend.cpp: type 12, align 0x4000, prot 0x33), so the 2 MiB question has
to be asked inside the title. With /data/omni/lpprobe.flag present, the video service's first start runs a thread that,
8 s in, maps 512 MiB of direct memory per variant and reads the page-table count (starter "pt" when the direct call is
missing): A align 16 KiB prot 0x33 (today) | B align 2 MiB prot 0x33 | C align 2 MiB prot 0x03 | D align 64 KiB
prot 0x33 | A2, B2 repeats. Results: /data/omni/lpprobe-title.txt + stderr ("OMNI LPPROBE ..."). No flag = nothing runs.
No new imports (the backend already imports these). Needs OMNI_PT_BACKSTOP_V5 in the same file.
usage: apply_lp_probe_title.py <$NE>   (before prep_launch.py, like apply_pt_backstop.py)"""
import sys
from pathlib import Path

MARK = 'OMNI_LP_PROBE_TITLE_V1'
p = Path(sys.argv[1]) / 'engine/media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
if 'OMNI_PT_BACKSTOP_V5' not in s:
    sys.exit('needs OMNI_PT_BACKSTOP_V5 first')
A = 'void* serviceMain(void*)\n{\n'
if s.count(A) != 1:
    sys.exit('anchor found %d times' % s.count(A))
FN = r'''// OMNI_LP_PROBE_TITLE_V1: does 2 MiB alignment make direct memory cheaper in kernel page tables? (lpprobe.flag only)
extern "C" {
int64_t sceKernelGetDirectMemorySize(void);
int sceKernelAllocateDirectMemory(int64_t, int64_t, size_t, size_t, int, int64_t*);
int sceKernelMapDirectMemory(void**, size_t, int, int, int64_t, size_t);
int sceKernelReleaseDirectMemory(int64_t, size_t);
int sceKernelMunmap(void*, size_t);
}
static int omniLpUsed() { if (!omniPtDirect()) omniPtAskStarter(); int t = 0; return omniPtUsed(&t); }
static void omniLpSay(FILE* f, const char* line) { fprintf(stderr, "%s\n", line); fflush(stderr); if (f) { fprintf(f, "%s\n", line); fflush(f); } }
static void omniLpVariant(FILE* f, const char* name, size_t align, int prot)
{
    const size_t len = size_t(512) << 20;
    char line[320];
    sleep(2);
    const int u0 = omniLpUsed();
    int64_t phys = -1; void* addr = nullptr;
    int rc = sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), len, align, 12, &phys);
    if (rc) { snprintf(line, sizeof line, "OMNI LPPROBE %s alloc rc=0x%x", name, unsigned(rc)); omniLpSay(f, line); return; }
    rc = sceKernelMapDirectMemory(&addr, len, prot, 0, phys, align);
    if (rc || !addr) { snprintf(line, sizeof line, "OMNI LPPROBE %s map rc=0x%x", name, unsigned(rc)); omniLpSay(f, line); sceKernelReleaseDirectMemory(phys, len); return; }
    volatile uint8_t* b = static_cast<volatile uint8_t*>(addr);
    if (prot & 2) for (size_t o = 0; o < len; o += 4096) b[o] = 1;
    sleep(3);
    const int u1 = omniLpUsed();
    sleep(2);
    const int u1b = omniLpUsed();
    sceKernelMunmap(addr, len);
    sceKernelReleaseDirectMemory(phys, len);
    sleep(3);
    const int u2 = omniLpUsed();
    snprintf(line, sizeof line, "OMNI LPPROBE %s 512MiB align=0x%zx prot=0x%x type 12 va=%p phys=0x%llx | cpu before %d mapped %d/%d after %d => +%d",
             name, align, prot, addr, (unsigned long long)phys, u0, u1, u1b, u2, u1 - u0);
    omniLpSay(f, line);
}
static void omniLpProbeMaybe()
{
    static std::atomic<bool> once { false };
    if (once.exchange(true) || access("/data/omni/lpprobe.flag", F_OK)) return;
    std::thread([] {
        sleep(8);
        FILE* f = fopen("/data/omni/lpprobe-title.txt", "w");
        char line[160]; snprintf(line, sizeof line, "OMNI LPPROBE start (title), cpu %d", omniLpUsed()); omniLpSay(f, line);
        omniLpVariant(f, "A-16k", 0x4000, 0x33);
        omniLpVariant(f, "B-2m", 0x200000, 0x33);
        omniLpVariant(f, "C-2m-cpu", 0x200000, 0x03);
        omniLpVariant(f, "D-64k", 0x10000, 0x33);
        omniLpVariant(f, "A2-16k", 0x4000, 0x33);
        omniLpVariant(f, "B2-2m", 0x200000, 0x33);
        omniLpSay(f, "OMNI LPPROBE done");
        if (f) fclose(f);
    }).detach();
}
'''
s = s.replace(A, FN + A + '    omniLpProbeMaybe();   // ' + MARK + '\n', 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
