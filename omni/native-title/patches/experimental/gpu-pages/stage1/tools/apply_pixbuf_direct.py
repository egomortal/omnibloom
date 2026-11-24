#!/usr/bin/env python3
"""OMNI_PIXBUF_DIRECT_V1 (2026-11-23): the hole-punch video layers' CPU pixel images on direct memory in the title.

OmniMedia::Hw::CpuPixelBuffer::ensure() (engine/media/OmniCpuPixelBuffer.h, used only by the decode service in the
title) maps each layer image with anonymous mmap = FLEXIBLE memory, 1 page table per 2 MiB. Console 2026-11-23
(OMNI_MEMMAP_V1, e1707bdf, YouTube 4K): "F:anon:<serviceMain -> holeConvert>" 253 MB in 8 regions, in the normal build
AND with the WebProcess in the title (~127 tables, a quarter of the title's flexible budget).

With /data/omni/vss-direct.flag (Phase 1's switch, read once with fopen), ensure() takes the buffer from direct memory
instead (sceKernelAllocateDirectMemory type 0 WB_ONION + sceKernelMapDirectMemory CPU read/write, 16 KiB granularity,
0 page tables), and frees it with munmap + sceKernelReleaseDirectMemory. If direct memory is refused it falls back to
the original mmap. Contents semantics unchanged (growth discards old pixels).
usage: apply_pixbuf_direct.py <engine/media/OmniCpuPixelBuffer.h>"""
import sys
from pathlib import Path

MARK = 'OMNI_PIXBUF_DIRECT_V1'
p = Path(sys.argv[1])
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:70]))
    s = s.replace(old, new, 1)


rep('#include <sys/mman.h>\n',
    '#include <sys/mman.h>\n'
    '#ifdef __PROSPERO__   // ' + MARK + '\n'
    '#include <cstdio>\n'
    'extern "C" {\n'
    'int sceKernelAllocateDirectMemory(int64_t searchStart, int64_t searchEnd, size_t len, size_t align, int type, int64_t* phys);\n'
    'int sceKernelMapDirectMemory(void** addr, size_t len, int prot, int flags, int64_t directStart, size_t align);\n'
    'int sceKernelReleaseDirectMemory(int64_t start, size_t len);\n'
    'int64_t sceKernelGetDirectMemorySize(void);\n'
    '}\n'
    '#endif\n')

rep('    uint8_t* pixels_ = nullptr;\n    size_t capacity_ = 0;\n',
    '    uint8_t* pixels_ = nullptr;\n    size_t capacity_ = 0;\n'
    '    int64_t direct_ = -1;   // ' + MARK + ': direct-memory start of pixels_, -1 = mmap\n'
    '    static bool directOn()\n'
    '    {\n'
    '#ifdef __PROSPERO__\n'
    '        static int on = -1;\n'
    '        // Bloom Preview 5: also /app0/vss-direct.flag (the package), unless /data/omni/vss-direct-off.flag.\n'
    '        if (on < 0) {\n'
    '            auto has = [](const char* n) { FILE* f = fopen(n, "r"); if (!f) return false; fclose(f); return true; };\n'
    '            on = (has("/data/omni/vss-direct.flag") || (has("/app0/vss-direct.flag") && !has("/data/omni/vss-direct-off.flag"))) ? 1 : 0;\n'
    '        }\n'
    '        return on == 1;\n'
    '#else\n'
    '        return false;\n'
    '#endif\n'
    '    }\n'
    '    void release()\n'
    '    {\n'
    '        if (!pixels_) return;\n'
    '        munmap(pixels_, capacity_);\n'
    '#ifdef __PROSPERO__\n'
    '        if (direct_ >= 0) sceKernelReleaseDirectMemory(direct_, capacity_);\n'
    '#endif\n'
    '        pixels_ = nullptr; capacity_ = 0; direct_ = -1;\n'
    '    }\n')

rep('    ~CpuPixelBuffer() { if (pixels_) munmap(pixels_, capacity_); }\n',
    '    ~CpuPixelBuffer() { release(); }\n')

rep('        void* mapped = mmap(nullptr, bytes, PROT_READ | PROT_WRITE,\n'
    '            MAP_PRIVATE | MAP_ANON, -1, 0);\n'
    '        if (mapped == MAP_FAILED) return false; // preserve the old buffer on failure\n'
    '        if (pixels_) munmap(pixels_, capacity_);\n'
    '        pixels_ = static_cast<uint8_t*>(mapped);\n'
    '        capacity_ = bytes;\n'
    '        return true;\n',
    '#ifdef __PROSPERO__\n'
    '        if (directOn()) {   // ' + MARK + ': direct memory, 0 page tables\n'
    '            const size_t len = (bytes + 0x3fff) & ~size_t(0x3fff);\n'
    '            int64_t phys = -1;\n'
    '            if (!sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), len, 0x4000, 0 /* WB_ONION */, &phys)) {\n'
    '                void* addr = nullptr;\n'
    '                if (!sceKernelMapDirectMemory(&addr, len, 0x03 /* CPU read+write */, 0, phys, 0x4000) && addr) {\n'
    '                    release();\n'
    '                    pixels_ = static_cast<uint8_t*>(addr); capacity_ = len; direct_ = phys;\n'
    '                    return true;\n'
    '                }\n'
    '                sceKernelReleaseDirectMemory(phys, len);\n'
    '            }\n'
    '        }\n'
    '#endif\n'
    '        void* mapped = mmap(nullptr, bytes, PROT_READ | PROT_WRITE,\n'
    '            MAP_PRIVATE | MAP_ANON, -1, 0);\n'
    '        if (mapped == MAP_FAILED) return false; // preserve the old buffer on failure\n'
    '        release();\n'
    '        pixels_ = static_cast<uint8_t*>(mapped);\n'
    '        capacity_ = bytes;\n'
    '        return true;\n')

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
