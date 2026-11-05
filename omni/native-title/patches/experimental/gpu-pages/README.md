# Experimental: GPU page drawing (Zink + EGL prototype)

> **Prototype only. Never run on the console**, not part of any release build, and nothing in the s3.4d tree uses it.
> Source only: no build outputs, logs or binaries are kept here.

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
