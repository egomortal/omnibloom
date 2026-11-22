#!/usr/bin/env python3
"""OMNI_SHM_LAZY_SLOTS_V1 (2026-11-21, page-table pool): the title's video service maps each stream's whole shared block
at open (OmniHwService.cpp handleConfigureFinish: 24 MiB input ring + 6 decoded-picture slots; 4K HDR slot ~25 MiB ->
~174 MiB per stream; title memory map on g9u at 4K: 253 MiB = 128 kernel page tables, caller serviceMain). The pool is
charged per MAPPED 2 MiB, used or not. In GPU/hole-punch playback the slots are only a fallback (shell backlog return,
clock snapshots, the paint path); every slot write first calls freeSlot().

Now: the block's address range is reserved for free (sceKernelReserveVirtualRange), the input ring is mapped at open, and
the slot area is mapped (MAP_FIXED, same fd/offset, same addresses) the first time freeSlot() is called for the channel.
Pointer arithmetic, protocol and client are unchanged. Any failure falls back to the old full mapping.
DEFAULT OFF (2026-11-21: g9s/g9r stalled every stream with it on; bisect pending): on with /data/omni/shm-lazy-slots-on.flag (read once).
usage: apply_shm_lazy_slots.py <engine dir holding media/OmniHwService.cpp>   (title: $NE/engine, pre-prep)"""
import sys
from pathlib import Path

MARK = 'OMNI_SHM_LAZY_SLOTS_V1'
p = Path(sys.argv[1]) / 'media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:90]))
    s = s.replace(old, new, 1)


# 1. per-channel state
rep('    uint32_t slotOffset = 0, slotSize = 0;\n',
    '    uint32_t slotOffset = 0, slotSize = 0;\n    bool omniSlotsMapped = true;   // ' + MARK + ': false while only the input ring is mapped\n')

# 2. helpers before freeSlot + the hook in freeSlot
HELP = r'''// OMNI_SHM_LAZY_SLOTS_V1: map the decoded-picture slots only when first needed (see tools/apply_shm_lazy_slots.py)
extern "C" int sceKernelReserveVirtualRange(void**, size_t, int, size_t);
static bool omniShmLazyOn()
{
    static const bool on = access("/data/omni/shm-lazy-slots-on.flag", F_OK) == 0;   // default OFF until the g9s/g9r stall is understood
    return on;
}
static size_t omniShmSpan(size_t n) { return (n + 0x3fff) & ~size_t(0x3fff); }
// Maps the stream's block: lazily (ring now, slots later) when possible, else whole. Returns the base or MAP_FAILED.
static void* omniShmMap(Channel& c)
{
    c.omniSlotsMapped = true;
    if (omniShmLazyOn() && c.slotOffset && c.shmSize > c.slotOffset && !(c.slotOffset & 0x3fff)) {
        void* base = nullptr;
        if (!sceKernelReserveVirtualRange(&base, omniShmSpan(c.shmSize), 0, 0x4000) && base) {
            if (mmap(base, c.slotOffset, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, c.shmFd, 0) == base) {
                c.omniSlotsMapped = false;
                return base;
            }
            munmap(base, omniShmSpan(c.shmSize));
        }
    }
    return mmap(nullptr, c.shmSize, PROT_READ | PROT_WRITE, MAP_SHARED, c.shmFd, 0);
}
static bool omniShmMapSlots(Channel& c)
{
    if (c.omniSlotsMapped) return true;
    if (!c.shm || c.shmFd < 0) return false;
    uint8_t* at = c.shm + c.slotOffset;
    if (mmap(at, c.shmSize - c.slotOffset, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, c.shmFd, off_t(c.slotOffset)) != at) {
        holeNote("channel %d: picture slots could not be mapped (errno %d) (OMNI_SHM_LAZY_SLOTS_V1)", c.index, errno);
        return false;
    }
    c.omniSlotsMapped = true;
    holeNote("channel %d: picture slots mapped on first use, %zu bytes (OMNI_SHM_LAZY_SLOTS_V1)", c.index, c.shmSize - size_t(c.slotOffset));
    return true;
}

bool freeSlot(Channel& c, uint32_t& slot)
{
    if (!c.omniSlotsMapped && !omniShmMapSlots(c)) return false;   // OMNI_SHM_LAZY_SLOTS_V1
'''
rep('bool freeSlot(Channel& c, uint32_t& slot)\n{\n', HELP)

# 3. the open: use the helper
rep('        void* p = mmap(nullptr, c.shmSize, PROT_READ | PROT_WRITE, MAP_SHARED, c.shmFd, 0);\n',
    '        void* p = omniShmMap(c);   // ' + MARK + '\n')

# 4. the release: unmap the whole reserved span, reset the state
rep('    if (c.shm) { munmap(c.shm, c.shmSize); c.shm = nullptr; }\n',
    '    if (c.shm) { munmap(c.shm, c.omniSlotsMapped ? c.shmSize : ((c.shmSize + 0x3fff) & ~size_t(0x3fff))); c.shm = nullptr; }   // ' + MARK + '\n'
    '    c.omniSlotsMapped = true;\n')
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
