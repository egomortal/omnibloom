# 4K video memory and kernel page tables on PS5 (research, 2026-11-18/19)

Why this matters: with GPU page layers ("layers") on, 4K HDR YouTube can hang the console. The hang tracks the
kernel's page-table count, not free memory. This page collects what we measured, what we ruled out, and the tools.

## The constraint

- ShellCore logs `VM Stats ... page table CPU <n>/8192` every ~2 s in the kernel log. The pool is 8192 pages.
- The console idles at about 5,000-5,240. Hangs happened at about 6,700-6,950, together with low free memory.
- 4K HDR playback adds about +1,290-1,300 page tables with layers off and +1,630-1,720 with layers on.
- Free *flexible* memory is not the limit. A web-process crash logged
  `allocator mmap failed: bytes=33554432 errno=12` while 8.47 GB of flexible memory was still free.
  The kernel refused the mapping.

## One page-table page per 2 MiB, no large-page saving

Probe: `research/ptprobe.c`, a payload run with Omni closed. It maps 1 GiB in 32 MiB blocks, touches every 4 KiB page,
holds for 20 s, then releases.

| Phase | Page tables |
|---|---|
| baseline | 5018 |
| anonymous mmap, plain | 5514-5530 (+512) |
| anonymous mmap, 2 MiB aligned (`MAP_ALIGNED(21)`) | 5530 (+512) |
| after release | 5018 |

Direct memory with 64 KiB or 2 MiB alignment cost the same per byte. So the kernel spends exactly one page-table page
per 2 MiB of touched memory, whatever the alignment. Page tables only come down by keeping less memory mapped.

Nobody has published anything about this pool. We searched online for the PS5 kernel page-table limit, WebKit's MSE
buffer limits, and the RADV video-decode memory, and found no documented limit or tuning setting for any of them.

## Where the title's memory goes at 4K (memtrace)

`src-title/omni_memtrace.c` (applied by `tools/apply_memtrace.py`, test builds only) wraps
`sceKernelAllocateMainDirectMemory`, `sceKernelAllocateDirectMemory` and `sceKernelMapDirectMemory`. With
`/data/omni/memmap.flag` present it logs each call with its caller. `research/memtrace_group.py` groups the lines by
caller. Symbolize with `caller - 0x400000` (the title's load base) against the build's `llvm-pie.elf`.

4K HDR YouTube, layers off:

| Caller | What | Size |
|---|---|---|
| `Hw::Backend::allocDirect` (`media/OmniHwBackend.cpp`) | hardware decoder per stream: gpu + cpu_gpu (from `QueryDecoderMemoryInfo`, dpb AUTO), 4 x 8 MiB input, 8 output frames | 2160p10: 386 + 205 + 32 + 196 = **820 MB**; 1440p10: 185 + 120 + 32 + 88; 1080p10: 105 + 89 + 32 + 52 |
| `Hw::backendDirectAlloc` | the V5 pace queue of decoded pictures (`OmniAbrSwitch.h`: 1 GiB steady, 2 GiB during a quality switch, 320 MiB pool reserve) | about **1 GiB at every size**: 43 x 24.9 MB at 2160p, 94 x 11 MB at 1440p, 156 x 6.2 MB at 1080p |
| `radv_ps5_memory_alloc` | Mesa RADV device memory | 230 MB |
| `ps5p_heap_map` | heap | 144 MB |
| `PS5_VideoInit` (SDL) | display setup | 64 MB |
| `__wrap_pthread_create` | thread stacks | 30 MB |

## Tried and rejected: a smaller pace-queue limit

`tools/apply_abr_ceiling.py` (test only, `OMNI_ABR_CEILING_FLAG_V1`) makes the queue limits settable with
`/data/omni/abr-ceiling-<steadyMiB>-<switchMiB>-<reserveMiB>.flag`. Without the flag nothing changes.
4K HDR, layers on, one run each:

| Limit (steady/switch/reserve MiB) | Peak page tables | Playback |
|---|---|---|
| 1024/2048/320 (current) | 6816 | full video, ~58 fps (min 55), 6.5% dropped, no stall |
| 512/768/128 | 6794 | stalled at 51 s, fell to 480p |
| 256/384/32 | 6792 | played through, 11.6% dropped, min 35 fps |
| 384/512/64 | 6623 | never started |

A smaller limit saves only about 20 page tables. Pictures past the limit are copied to the heap instead ("direct
memory refused a queued picture ... heap copy"), so the memory moves instead of going away. It also hurts start and
smoothness. Rejected.

Not touched: the decoder's reference frames (VP9 needs its 8 reference slots) and its output frames (the GPU video
path reads them in place).

## Planned for the next Bloom Preview (not released yet)

- `apply_latest_frame.py` (`OMNI_GPUPAGES_LATEST_FRAME_V1`): the async read-back hands the main thread at most one
  waiting frame and reuses its memory. 4K YouTube web-process peak 1047-1177 MB, down from up to 1440 MB.
  Kill switch: `/data/omni/gpu-pages-latest-frame-off.flag`.

## Next candidates

- The layers-only share: +350-420 page tables over layers off at 4K.
- The web process at 4K (1.0-1.2 GB), for example dropping buffered MSE video earlier under memory pressure.
