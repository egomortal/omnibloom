# OMNI_GPUPAGES_ZEROCOPY_V1: page frames from the engine to the screen without the CPU

Owner, 2026-11-15: "do the long term fix like always" (the road to 60 fps scrolling with layers).

## Measured starting point (async scrolling on, 2026-11-14/15)

| Stage | Cost |
|---|---|
| Engine compositor thread: composite + tile uploads | p50 8.3 ms |
| Engine: synchronous readback (2 GPU waits per frame) | p50 6.1 ms, tails 50+ ms. Step 1 (OMNI_GPUPAGES_ASYNCREAD_V1) removes it: 40 -> 45.4 fps |
| Engine: PBO -> ShareableBitmap memcpy (asyncread) | 4.5 ms per frame (reading GPU-written memory) |
| UI process: WKPagePaint, bitmap -> half-size page buffer | ~4 ms (8 MB) |
| Shell: half-size page -> 4K canvas, rows doubled | ~33 MB of CPU writes per full frame |
| Title GPU present (import canvas, copy, PQ, flip) | 1.1 ms CPU + 0.9 ms GPU |

## Facts the design rests on (all checked in source)

- Broker host-visible client memory is a shared object mapped at the SAME virtual address in the title (owner) and the
  WebProcess (client), and GPU-granted in the title (`gpu-broker/server.cpp` allocate(): MAP_SHARED|MAP_FIXED at the
  range address; `protocol.h` windows 0x240000000 +512 MiB and 0x3000000000 +16 GiB).
- The title's RADV has VK_EXT_external_memory_host (`radv_ps5_buffer_from_ptr`: GPU reaches host memory at the CPU's
  address), and OmniGpuPresent already imports host memory (`importHost`, `cachedLayer`).
- The shell already marks "the GPU fills this" with alpha 0 (the video hole-punch: `clear = holePunchActive() ? 0 : ...`).
- The page is painted at half size (1920x1080, `omniPageScale < 1`) into a 4K canvas: the engine frame is that size.

## Design

Engine (WebProcess, `stage1/src/ogp-s1-surface.inc`):
1. Frames already go GPU -> ring of 3 pixel-pack buffers (asyncread). Their mapped CPU pointer is checked to lie inside
   the broker host windows; outside: zero-copy is not offered (logged once).
2. Control page `/data/omni/gpu-pages/zc-<pid>.ctl` (one 4 KiB page, MAP_SHARED, seqlock): the engine publishes
   {frame, slot, address, width, height, stride}; the title writes `consumer` (1 = GPU wants addresses, 0 = bitmaps) and
   `consumed` (the last frame it finished reading).
3. consumer == 1: no ShareableBitmap, no memcpy; the slot stays untouched until consumed >= its frame (bounded wait,
   then the bitmap path for that frame). consumer == 0 or no title: the bitmap path, exactly as asyncread today.

Title (shell `OmniBrowser.cpp` + `OmniGpuPresent.cpp`):
4. GPU page mode when: zero-copy flag, GPU present active, the active tab's process has a fresh control page with a frame
   of the page's half-size, and no hole-punch video. Then the shell skips WKPagePaint and the 4K row doubling, fills the
   page rect with 0x00000000 once (and wherever it changed), and draws bars, toasts and the pointer as usual (SDL's
   blend onto alpha 0 leaves premultiplied overlay colour with its alpha).
5. A new published frame (control page `frame` changed) makes the shell present even with no canvas change.
6. OmniGpuPresent: imports the published buffer (cached per address, at most 3), then a compute pass over the page rect:
   `out = canvas.rgb + page2x.rgb * (1 - canvas.a)` (page sampled at half resolution), before the PQ pass. After the
   present's fence: `consumed = frame`.
7. Leaving GPU page mode (video starts, overlay that needs the CPU page, any failure): consumer = 0, then WKPageForceRepaint
   so the UI process's copy of the page is current before the CPU path paints again.

Kill switches: no `/data/omni/gpu-pages-zerocopy.flag` = today's path; `gpu-pages-zerocopy-off.flag` wins; the asyncread
flag is required (zero-copy sits on its ring).

## Order of work
1. Engine side + control page (child relink, minutes) with a log of the PBO addresses (is it in the broker windows?).
2. Title side (title build, ~30 min).
3. Console: Lsc2bzhy (async scrolling + asyncread + zerocopy) vs Lsc2bahy, one run per call, stop on the first drop.
