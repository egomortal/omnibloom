# omni-video-4k60: why YouTube never reached the GPU path, and the title-side patch set

2026-11-05. Host-side only: **the console was not used** (the s3.4 agent owns it). Title only; the child stays
`7b810ea5…fd717c64`. No JIT, security, vault or PROT_EXEC change. Host figures are lavapipe (CPU Vulkan), not PS5 figures.

## The cause (found, and confirmed on the console by the s3.4 agent's A/B)
- **OmniDarkPages (shell, title) put a CSS filter on the video.** The user has `youtube.com` set to "Always dark" in
  `/data/omni/site-dark.txt`. The dark script then sets `filter: invert(1) hue-rotate(180deg)` on `<html>` and again on
  every `<video>`. Its "page already dark?" check reads only `<html>`/`<body>` backgrounds; YouTube's are transparent and
  its `color-scheme` is not `dark`, so the filter stays on even over YouTube's own dark theme.
- **The WebProcess player's `holeGeometry()` refuses any video with a filter on itself or an ancestor** ("opacity, filter,
  mask, clip-path, blend or reflection on the way up"). So the watch page and Shorts were never eligible: no hole frames,
  no claim, no pacing, `video_gpu_pictures=0` (OmniGpuVideo only converts hole-punch pictures), and the 1080p paint path
  instead.
- **The stall at 0.0145 s is the same cause.** The child's V133 start gate waits for presenter readiness, which only a
  claimed, paced plane can give; with an ineligible plane it waits forever (no timeout: Astra's reading was right).
  That's why CPU and GPU runs stalled alike, why the pacing-disabled run played, and why the yt-soak embed page (no dark
  setting on its own page) always worked.
- **Evidence:** `omni-jit2/S34-STATUS.md` 02:05-02:10Z: with youtube.com removed from site-dark.txt: `hole_on True paced
  True`, MSE time 13.97 s in 30 s; with it: 0.0145 s, hole_on False. Host repro: `hosttest/eligibility_test.cjs` runs the
  s3.3 dark script on a YouTube-like page (transparent html/body, dark app): inverted, video ineligible while playing.
- Checked and not the cause: `OMNI_MSE_START_GAP_V1/V2` is present and fires (`skipped a 0.015 s gap at 0.000`); the
  pacing gate itself; GPU present (2.4 ms CPU / 0.44 ms GPU per 4K present).

## The patch set (`patches/`, applied by `apply_video4k60.py`, marker-checked, stacks on s3.1c or s3.3/s3.4)
| Patch | Files | What |
|---|---|---|
| 00 | engine/media/*, src-title/OmniGpuPresent.cpp, OmniPqOutShader.h | s3.2-video's GPU V2 on s3.1c's title sources (skipped where `OMNI_GPU_VIDEO_V2` is already there) |
| 01 | OmniGpuVideo.{h,cpp} | **OMNI_GPU_VIDEO_V3**: (a) pace-queue pictures are **imported once and read in place** by the shader (no 12.4 MB/4K ring memcpy; cache of 288 picture imports = the whole V5 queue + spares; LRU per kind); anything else, or a refused import, still uses V2's persistent 3-slot ring; (b) **one RADV device**: adopts the GPU present's VkDevice/queue (`omni_gpu_present_share`), submissions under the present's queue lock; without the present it makes its own device as V2; (c) shared-device shutdown waits on its own fences and leaves the device to the present; (d) `stats2()` (in place / ring copies / shared) |
| 02 | OmniHwService.cpp (title copy only) | `PaceAlloc::deallocate` forgets the GPU import before the direct memory goes; `holeConvert` marks a paced picture `planesPersistent` only when it is a direct-memory pace buffer (`paceIsDirect`) |
| 03 | OmniGpuPresent.cpp | **OMNI_GPU_PRESENT_V3**: `omni_gpu_present_share()`; `g_queueLock` around every vkQueueSubmit / vkQueuePresentKHR / vkDeviceWaitIdle; teardown shuts the video down first; Astra's **two-entry SDL import cache** (OMNI_GPU_SURFACE_PAIR_V1: 329 re-imports/10 s before) and **region reuse** (no per-present vector); **OMNI_VIDEO_FPS_V2** line (+ `intervals_over_25ms`, `video_in_place`, `video_ring_copies`, `shared_device`, `mode`); kill switch `/data/omni/gpu-share-disabled.flag` |
| 04 | OmniDarkPages.h (shell) | **OMNI_DARK_VIDEO_V1 (the fix)**: a playing video >= 320x180 turns the dark filter off (like fullscreen already did) and it comes back on pause/end; a page whose centre element is dark (html/body transparent) is not inverted at all |
| 05 | OmniBrowser.cpp (shell, yt-timeline only) | Astra's 1 s HTML video counter probe (OMNI_VIDEO_FPS_PROBE_V1), **OMNI_HOLE_ELIGIBILITY_PROBE_V1** (the player's holeGeometry rules from the page: says which element/property blocks the hole), Astra's `fullscreen 1` normal-f-key option, `nativePageFullscreen` in the dump |

**Copies per 4K picture now:** decoder slot -> pace buffer (the one copy, service thread, required: V5 queues ~3 s and
the decoder's 8 output slots are rewritten) -> GPU reads it in place -> writes the imported layer -> the present copies
the runs on the GPU. Importing the decoder slot itself is not worth it while the 3 s queue exists (the slot is freed
long before the picture is shown).

**Pacing:** unchanged and deliberate: FIFO, one flip per vblank, blocking acquire; the V8 presenter picks the picture due
at the vblank the flip reaches (MAILBOX would break that; it stays a flag word). Nothing in the title blocks playback
start; the start gate lives in the child.

**Reused, not rewritten:** RC7's CPU 4K path (V5-V9 pacing, direct tiling, HDR port/Main10) is already in the s3 tree's
OmniHwService and SDL v5; it is this build's no-flag path and the fallback (s3.1b soak: paced 1440p, 300/300 shown, 0
dropped, 8.2 ms convert). Astra's surface-pair cache, region reuse, fps probe and fullscreen key are integrated as above.
**Not included (child):** Astra's guarded startup fallback (sound; see `child-optional/README.md`): it belongs to the next
child update, as a safety net for any other blocker (an add-on's filter, a clip-path). The HDR profile switch was not
touched.

## Host tests (all PASS; logs `hosttest/wsl/` from the build, `hosttest/container/` from a second Linux host)
- **Pixels (lavapipe):** 12 V2 cases + 5 new in-place cases: 2160->2160 8/10-bit, 1080p->2160, 1440p->2160 8/10-bit.
  In place = ring copy **bit-exact** (worst 0), = the shader model (worst 0), vs the title's CPU path mean <= 0.67.
- **No per-frame allocation:** 10 000 pictures through a 16-buffer pace queue with buffers freed/remapped: live Vulkan
  objects constant (21 -> 21), cache bounded, RSS +1 MiB, 9 799 in place, 0 ring copies. V2's 10k layer test and the
  present's 10k test (live 8/2/10 constant) still pass; pair cache: 120 alternating exact frames with no re-import.
- **Shared device:** one VkDevice; conversions and composes interleaved, then 300 + 300 on two threads at once: 0
  failures, 0 wrong pixels; teardown frees the video first, all live counts 0; also clean under ASan+UBSan.
- **Fallback:** no Vulkan ICD and `failsetup`: every picture on the CPU; present without Vulkan keeps SDL's present.
- **Eligibility (headless Chromium, the JS extracted from the C++ sources):** inline (rounded player + sidebar), theater,
  fullscreen, controls overlay with opacity/backdrop/blend over the video: eligible; hidden page, opacity 0.99, rotation,
  clip-path: ineligible with the right reason; forced dark on a light page: inverted while paused, eligible while playing,
  dark again after pause; forced dark on a YouTube-like dark page: never inverted. Baseline script: reproduces the stall cause.
- **Native:** the title links; layout check PASSED; OmniBrowser compiles without warnings; the only warning in the GPU
  objects is the existing `holeBlendPixel`.

## Hashes
| | |
|---|---|
| `out/PPSA99732/eboot.bin` | `009c333941373047fa63fe80af3c3b55b825d7facf8cde9da04775bbb1a2296a` |
| `build/eboot.elf` | `594b98980e6e12c8bd633dacdaf531745f0cb281fafe53e4af25b65f2fe3ac94` |
| child `out/child/omni-engine-child.elf` | `7b810ea5b5cdcbc899828635b329da42595b540ff51998513b7e8b21fd717c64` (s3.1c's file, not rebuilt) |
| param.json / libc.prx | `354f191d…` / `e6ff45d1…` (unchanged) |
| patches 00..05 | `d4f6825a…`, `911343f8…`, `57675b11…`, `0b94a24c…`, `4ebe713e…`, `59ebf040…` (full list in `checks.txt`) |

Build: `outputs/build-omni-video4k60.sh` (s33 recipe; GPU host tests first; patches 00-03 applied to s3.1c's sources,
04-05 to the tree after pointer-cross; the child is never relinked). Steps: `build-steps.txt`; checks: `checks.txt`.

## Not proven yet (console)
- In-place import of direct memory and the shared device are new on RADV/PS5 (each has a fallback: ring copy on a refused
  import; `gpu-share-disabled.flag`).
- 4K60 <= 1% drops over 300 s: only the console can say. Plan: `TEST-PLAN.md`.
- Old big-app bugs from the coordinator's notes (pacing off after a quality switch or a hidden-then-shown tab) live in the
  child's player; the eligibility probe and the fps log will show them if they recur.
