# Experimental: GPU page drawing (Zink + EGL prototype)

> **Experimental, console-tested (v0.5.2-dev, 2026-11-15), off by default.** Not part of a release build yet: every
> piece below is behind its own `/data/omni/...` flag and kill switch. Source only: no build outputs, logs or binaries.
>
> **Where it stands (YouTube home page scrolled with layers on, PS5, HDR output):**
>
> | Step | Flag | Median fps | p10 |
> |---|---|---|---|
> | Layers, main-thread scrolling (stage 1) | `gpu-pages-stage1.flag` | 8.2 | ~4.9 |
> | + async scrolling (`OMNI_GPU_PAGES_ASYNC_V2`) | `gpu-pages-async.flag` | 38-40 | ~32 |
> | + pipelined readback (`OMNI_GPUPAGES_ASYNCREAD_V1`) | `gpu-pages-asyncread.flag` | 45.4 | 37-39 |
> | + zero copy to the title's GPU (`OMNI_GPUPAGES_ZEROCOPY_V1`) | `gpu-pages-zerocopy.flag` | **51.6** | **44.7** |
>
> - Async scrolling: the PlayStation UI process forces WebKit's `threadedScrollingEnabled` off, so the first async gate
>   never turned on; `stage1/tools/apply_gpupages_async_v2.py` lets the flag-gated drawing area decide.
> - Zero copy: the page frame stays in GPU-broker memory (mapped at the same address in the title) and the title's
>   present composites it under the shell's overlays; design and limits in
>   [`stage1/ZERO-COPY-DESIGN.md`](stage1/ZERO-COPY-DESIGN.md). V1 covers HDR-armed canvases without video; SDR and video
>   pages keep the CPU path.
> - Known: brief unpainted tiles in the first ~2-6 s of each scroll (async scrolling); unexplained whole-console reboots
>   under load are still being investigated (`stage1/klogsrv/` is the read-only kernel-log payload used for that).
> - Also here: `apply_mse_quota.py` (the YouTube 4K freeze fix), a Mesa shader disk cache patch, and the diagnostics
>   (`apply_paint_probe.py`, `apply_coverage_probe.py`).
>
> The original prototype notes follow.

Today Omni draws web pages on the CPU and only video goes to the GPU. [`REPORT.md`](REPORT.md) is the feasibility study
(prior art, options, licences, a console probe plan). The chosen route is the upstream WPE/GTK model: the page process
composites (and later rasters) on the GPU as a client of the title, which keeps sole ownership of the GPU. Stage 1 is
WebKit's own accelerated compositing with CPU tiles; stage 2 is Skia GPU raster. GL comes from **Zink** on the same
PS5_Mesa commit as the title's RADV.

| Path | What |
|---|---|
| `prototype/mesa-patches/apply_ogp_mesa_patches.py`, `ogp-mesa.diff` | two small Mesa patches, compiled out unless their macro is set: Zink takes Vulkan from the statically linked RADV ICD (`OGP_ZINK_STATIC_ICD`) instead of `dlopen`, and Zink's DRI/EGL frontend builds without DRM for the PS5 winsys (MIT) |
| `prototype/egl-probe/ogp_egl_probe.c` | the 8-step EGL surfaceless + GLES 3.2 probe (GPL-3.0-or-later) |
| `prototype/egl-probe/ogp_host_icd.c`, `ogp_dri_nodrm_stubs.c` | host ICD shim and the no-DRM stubs |

**Where it stands (host only):** all 8 probe steps pass on lavapipe, including with no Vulkan loader at all; the same
Mesa tree builds for the PS5 target and the probe links into one console ELF with 0 undefined and 0 duplicate symbols.
**Next:** the console probe in `REPORT.md` §6 (can a loader-spawned child be a GPU-broker client of our title on 13.60?).
