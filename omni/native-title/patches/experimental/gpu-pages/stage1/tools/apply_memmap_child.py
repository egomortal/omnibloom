#!/usr/bin/env python3
"""OMNI_MEMMAP_CHILD_V1 (2026-11-20, owner: "no i need it gone forever"): the memory map of each ENGINE CHILD process
(web / network processes), like OMNI_MEMMAP_V1 does for the title.

Why: g9x showed the YouTube watch page alone takes the shared kernel page-table pool from ~5,125 to ~6,550 before any
video plays (hangs from ~6,770). The page process is the big grower. Before cutting, name what it maps.

With /data/omni/memmap-child.flag, a constructor in every engine-child process starts a detached thread that, 3 s in and
then every 10 s, walks this process's mappings (sceKernelVirtualQuery find-next) and writes
/data/omni/memmap-child-<pid>.txt (rewritten each pass; also the last pass is appended to ...-<pid>.log):
  pass N t=S pool U/T | total X MB in R regions, S 2MB-slots
  top 20 kind:name rows by slots           (kind D direct, F flexible, P pooled, S stack, - other)
  size histogram of anonymous flexible regions (<64K, <1M, <2M, 2M, 2-16M, 16M, >16M), count / MB / slots
  the 16 largest regions (address, MB, prot, kind:name)
No flag: one access() at process start, nothing else.
Patches engine/media/OmniHwClient.cpp (linked into the child).
usage: apply_memmap_child.py <engine dir holding media/OmniHwClient.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_MEMMAP_CHILD_V1'
p = Path(sys.argv[1]) / 'media/OmniHwClient.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)

BLOCK = r'''
// OMNI_MEMMAP_CHILD_V1: memory map of this engine-child process (memmap-child.flag only). tools/apply_memmap_child.py
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <algorithm>
#include <map>
#include <string>
#include <vector>
namespace omni_memmap_child {
typedef int (*VqFn)(const void*, int, void*, size_t);
typedef int (*PtFn)(int*, int*, int*, int*);
struct Row { uint64_t bytes = 0, slots = 0, regions = 0; };
struct Reg { uint64_t s, e; int prot; std::string key; };
static void walk(VqFn vq, PtFn pt, int pass, long secs)
{
    std::map<std::string, Row> rows; Row all; std::vector<Reg> regs;
    static const char* bucketName[7] = { "<64K", "<1M", "<2M", "=2M", "2-16M", "=16M", ">16M" };
    Row hist[7];
    uint64_t lastSlot = ~0ull; uintptr_t addr = 0;
    for (int guard = 0; guard < 400000; ++guard) {
        alignas(8) unsigned char info[128] = {};
        if (vq(reinterpret_cast<const void*>(addr), 1, info, 72) != 0) break;
        uintptr_t s = 0, e = 0; memcpy(&s, info, 8); memcpy(&e, info + 8, 8);
        if (e <= s || e <= addr) break;
        int32_t prot = 0; memcpy(&prot, info + 24, 4);
        const unsigned char bits = info[32];
        const unsigned char* nm = info + 33;
        if (!nm[0] && info[36] >= 0x20 && info[36] < 0x7f) nm = info + 36;
        char name[33]; memcpy(name, nm, 32); name[32] = 0;
        for (char* c = name; *c; ++c) if (*c < 0x20 || *c > 0x7e) *c = '?';
        const char kind = (bits & 4) ? 'S' : (bits & 2) ? 'D' : (bits & 8) ? 'P' : (bits & 1) ? 'F' : '-';
        std::string key = std::string(1, kind) + ":" + (name[0] ? name : "(anon)");
        const uint64_t first = uint64_t(s) >> 21, last = (uint64_t(e) - 1) >> 21;
        uint64_t slots = last - first + 1;
        if (first == lastSlot && slots) --slots;
        lastSlot = last;
        const uint64_t len = e - s;
        Row& r = rows[key]; r.bytes += len; r.slots += slots; ++r.regions;
        all.bytes += len; all.slots += slots; ++all.regions;
        if (kind == 'F' && !name[0]) {
            const int b = len < (64u << 10) ? 0 : len < (1u << 20) ? 1 : len < (2u << 20) ? 2 : len == (2u << 20) ? 3
                : len < (16u << 20) ? 4 : len == (16u << 20) ? 5 : 6;
            hist[b].bytes += len; hist[b].slots += slots; ++hist[b].regions;
        }
        regs.push_back({ uint64_t(s), uint64_t(e), prot, key });
        addr = e;
    }
    int t = 0, a = 0, gt = 0, ga = 0;
    const int used = (pt && pt(&t, &a, &gt, &ga) == 0) ? t - a : -1;
    char path[96]; snprintf(path, sizeof path, "/data/omni/memmap-child-%d.txt", int(getpid()));
    FILE* f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "pass %d t=%ld pool %d/%d | total %llu MB in %llu regions, %llu 2MB-slots (" "OMNI_MEMMAP_CHILD_V1)\n", pass, secs, used, t,
        (unsigned long long)(all.bytes >> 20), (unsigned long long)all.regions, (unsigned long long)all.slots);
    std::vector<std::pair<std::string, Row>> v(rows.begin(), rows.end());
    std::sort(v.begin(), v.end(), [](const auto& x, const auto& y) { return x.second.slots != y.second.slots ? x.second.slots > y.second.slots : x.second.bytes > y.second.bytes; });
    for (size_t i = 0; i < v.size() && i < 20; ++i)
        fprintf(f, "row %s: %llu MB, %llu slots, %llu regions\n", v[i].first.c_str(), (unsigned long long)(v[i].second.bytes >> 20),
            (unsigned long long)v[i].second.slots, (unsigned long long)v[i].second.regions);
    for (int b = 0; b < 7; ++b)
        fprintf(f, "anonF %s: %llu regions, %llu MB, %llu slots\n", bucketName[b], (unsigned long long)hist[b].regions,
            (unsigned long long)(hist[b].bytes >> 20), (unsigned long long)hist[b].slots);
    std::sort(regs.begin(), regs.end(), [](const Reg& x, const Reg& y) { return x.e - x.s > y.e - y.s; });
    for (size_t i = 0; i < regs.size() && i < 16; ++i)
        fprintf(f, "big %zu: %llu MB at %#llx prot %#x %s\n", i, (unsigned long long)((regs[i].e - regs[i].s) >> 20),
            (unsigned long long)regs[i].s, unsigned(regs[i].prot), regs[i].key.c_str());
    fclose(f);
    // keep a history of the pool + total per pass in one small log
    snprintf(path, sizeof path, "/data/omni/memmap-child-%d.log", int(getpid()));
    if (FILE* g = fopen(path, "a")) {
        fprintf(g, "pass %d t=%ld pool %d total %llu MB slots %llu", pass, secs, used, (unsigned long long)(all.bytes >> 20), (unsigned long long)all.slots);
        for (size_t i = 0; i < v.size() && i < 4; ++i) fprintf(g, " | %s %lluMB/%llu", v[i].first.c_str(), (unsigned long long)(v[i].second.bytes >> 20), (unsigned long long)v[i].second.slots);
        fprintf(g, "\n"); fclose(g);
    }
}
static void* run(void*)
{
    VqFn vq = reinterpret_cast<VqFn>(dlsym(RTLD_DEFAULT, "sceKernelVirtualQuery"));
    PtFn pt = reinterpret_cast<PtFn>(dlsym(RTLD_DEFAULT, "sceKernelGetPageTableStats"));
    char path[96]; snprintf(path, sizeof path, "/data/omni/memmap-child-%d.log", int(getpid()));
    if (FILE* g = fopen(path, "a")) { fprintf(g, "start pid %d vq %s pt %s\n", int(getpid()), vq ? "ok" : "MISSING", pt ? "ok" : "MISSING"); fclose(g); }
    if (!vq) return nullptr;
    sleep(3);
    const time_t t0 = time(nullptr);
    for (int pass = 1; pass < 100000; ++pass) { walk(vq, pt, pass, long(time(nullptr) - t0) + 3); sleep(10); }
    return nullptr;
}
// OMNI_MEMMAP_CHILD_V2: started on the first compositor frame, not from a static constructor (a thread created that
// early is the process's FIRST pthread_create, which stage 1 uses to detect the process role: g9y/g9z compositor crash)
void maybe_start()
{
    static int state = 0;   // 0 unknown, 1 started, -1 off
    if (state) return;
    state = access("/data/omni/memmap-child.flag", F_OK) ? -1 : 1;
    if (state < 0) return;
    pthread_t th; pthread_attr_t at; pthread_attr_init(&at); pthread_attr_setstacksize(&at, 512 * 1024);
    pthread_attr_setdetachstate(&at, PTHREAD_CREATE_DETACHED);
    pthread_create(&th, &at, run, nullptr);
    pthread_attr_destroy(&at);
}
}
extern "C" void omni_memmap_child_maybe_start(void) { omni_memmap_child::maybe_start(); }
'''
s = s.rstrip('\n') + '\n' + BLOCK
HOOK = 'extern "C" int omniHwBigVideoActive(void) { '
if s.count(HOOK) != 1:
    sys.exit('omniHwBigVideoActive anchor found %d times' % s.count(HOOK))
s = s.replace(HOOK, 'extern "C" void omni_memmap_child_maybe_start(void);   // OMNI_MEMMAP_CHILD_V2\n' + HOOK + 'omni_memmap_child_maybe_start(); ', 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
