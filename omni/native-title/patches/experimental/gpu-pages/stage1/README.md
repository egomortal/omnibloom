# Experimental: GPU page drawing, stage 1 ("layers")

> **Opt-in and off by default.** Shipped inside the v0.5.1 launch build (`../../../launch/rc6/README.md`), but nothing
> here runs unless you create `/data/omni/gpu-pages-stage1.flag`. Source only: no build outputs, logs or binaries.

Omni normally draws web pages on the CPU and only video goes to the GPU. Stage 1 turns on WebKit's own accelerated
compositing in the page process:
- Page layers are composited on the GPU with GLES from **Zink** on **RADV**.
- Rasterisation stays on the CPU (CPU tiles).
- The title keeps sole ownership of the GPU. The page process is a client of the title's GPU broker, and the composited
  frame is read back once per frame and shown through Omni's normal path.

The story of what broke along the way, and the general lessons for other PS5 ports, is in
[`docs/research/gpu-page-layers-ps5.md`](../../../../../../docs/research/gpu-page-layers-ps5.md). The feasibility study is
[`../REPORT.md`](../REPORT.md).

## Switches (all files in `/data/omni/`; checked once when Omni starts)

| File | Effect |
|---|---|
| `gpu-pages-stage1.flag` | turns layers **on** (title and page process) |
| `gpu-pages-stage1-off.flag` | kill switch: layers off even if the flag above exists |
| `gpu-pages-host-mib.txt` | host-visible GPU memory for the page process, in MiB (64 to 1024, default 384) |
| `gpu-pages-async.flag` / `gpu-pages-async-off.flag` | stage 1b: also allow WebKit's async scrolling (off by default) |

Diagnostic switches, for tests only:

| File | Effect |
|---|---|
| `gpu-pages-child-off.flag` | title side only; the page process stays on CPU drawing |
| `gpu-pages-nopace.flag` | don't pace the compositor to the 1/60 s frame interval |
| `gpu-pages-hangdog-off.flag` | turn off the compositor heartbeat / stall watchdog |
| `gpu-pages-sampler.flag` / `gpu-pages-sampler-off.flag` | 500 ms main-thread sampling profiler (opt-in) |
| `gpu-pages-noreserve.flag` | skip reserving the host memory window |
| `gpu-pages-nodladdr.flag` | skip the start-up `dladdr` file-name fix-up |
| `gpu-pages-noraise.flag` | don't raise thread stack sizes in the page process |

If anything fails at start, the page process leaves accelerated compositing off and draws on the CPU as before.

## What's here

| Path | What |
|---|---|
| `src/ogp-s1-child.c` | page-process start-up: flags, the scoped `dladdr` fix-up, host window reservation, broker bind |
| `src/ogp-s1-drawingarea.inc`, `ogp-s1-surface.inc`, `ogp-s1-policy.h` | compositor hooks (`OMNI_GPUPAGES_RAF_V1`: always send "frame done" after a composited frame), pacing (`PACE_V1`), one bounding-box read-back per frame (`TILES_V3`) |
| `src/ogp-s1b-async.inc` | stage 1b async-scrolling gate |
| `src/ogp-s1-tcprobe.inc` | compositor event counters, read by the heartbeat; they found the animation-frame bug |
| `src/ogp_dri_nodrm_stubs_weak.c`, `ogp_payload_libc_weak.c` | weak stubs so Mesa links without DRM and against the payload libc |
| `src-title/OmniGpuPagesService.cpp` | title side: starts the GPU broker early (`EAGER`) with a 384 MiB host budget (`HOSTMEM_V1`) |
| `broker/` | the PS5_Vulkan GPU broker, with one Omni change (below) |
| `cp2-client/` | the RADV PS5 winsys files (by Mihawk, MIT) the page-process client is built with |
| `tools/apply_gpupages_child.py`, `apply_gpupages_async.py` | anchored, idempotent WebKit patches for the page process |
| `tools/patch_child_build.py`, `s1_link_inputs.py`, `patch_title_build.py` | add the stage-1 objects to the child and title links |
| `tools/add_lazy_graphics.py` | `OMNI_LAZY_GPUPAGES_V1`: lazy forwarders for the 13 EGL/GL functions stage 1 calls, so the title still starts where they are missing |
| `tools/apply_media_health_fix.py` | `OMNI_MEDIA_HEALTH_V2`, the Media downloads shortcut fix (also in `launch/title/`) |
| `tools/apply_yttl_scroll.py` | test-only scroll driver for the YouTube timeline harness; inert without its config line |
| `tools/switch_state.py`, `ident.py` | build-tree helpers: switch a tree between source states and prove which sources a binary was built from |

## Build

1. Child: `../../../build/build-omni-gpupages-launch-s1b-rc6.sh`.
2. Title: `../../../build/build-omni-gpupages-rc6-title.sh`. It checks that its stage-1 sources match the child's.

Both scripts expect:
- **PS5_Mesa at commit `1ba9874f`** (Mesa 26.2.0, the RADV the title already links), with the two patches in
  `../prototype/mesa-patches/` (Zink takes Vulkan from the statically linked RADV ICD; Zink's DRI/EGL frontend builds
  without DRM).
- A checkout of **PS5_Vulkan** (set `UPV`), whose `tooling/gpu-broker` headers the client is compiled against.

Paths in the scripts are written as `/path/to/...` and `/home/builder/...`; point them at your own trees.

## Licences

- `broker/`: from PS5_Vulkan by Mihawk-99 (`tooling/gpu-broker`, compared against commit `f410e67`), **LGPL-2.1-or-later**, with its notices kept.
  - Omni changes one line in `server.cpp` (`OMNI_GPUPAGES_MEMSPLIT_V1`): a page process may hold 1 GiB of device-local memory, and 3 GiB always stay with the title for video.
  - Upstream offered 8 GiB with a 1 GiB floor, which let a page starve the video decoder.
- Mesa (Zink, RADV, EGL) and `cp2-client/`: **MIT**.
- Everything else here: the repository's licence.

## Console results (2026-11-13)

Same console and session, back-to-back, about 4.5 minutes of HDR YouTube per run:
- Layers on: video started in 14.47 s and 12.88 s, a steady 59.94 fps, HDR intact, no stall.
- Layers off: 14.35 s.

The 60-second stalls seen earlier came from YouTube's PO-token cutoff in a test title that lacked the rc5 guard, not
from layers. Mesa's shader cache cannot work in this static build, so the first full page draw still spends about
1.5 to 3 s compiling shaders.

**Status:** works, and stays opt-in. It is not faster than CPU drawing yet: stage 2 (Skia GPU rasterisation) is where
the gain is expected.
