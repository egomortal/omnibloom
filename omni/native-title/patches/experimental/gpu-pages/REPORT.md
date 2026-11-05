# Omni: GPU page drawing (omni-gpu-pages), feasibility and first prototype

2026-11-05. Host-side work only: nothing was sent to the console, installed or deployed. The Nov 12 launch build is
untouched: no file in the s3.4c/s3.5 trees, `omni-native-*`, `/home/builder/s1`, `/home/builder/s3` or the av2 RADV
build directory was written. Work lives in `outputs/omni-gpu-pages/` (Windows side) and `/home/builder/ogp/` (WSL).

## 1. Short answer

- **Chosen route: (C), the upstream WPE/GTK model, run through a GPU broker owned by the title.** The WebProcess
  draws and composites pages on the GPU itself (Skia GPU tiles, WebKit's threaded compositor, async scrolling).
  It reaches the GPU as a *client* of the title. The title already owns AGC/RADV and keeps sole ownership; it
  submits the client's command buffers and gets finished page frames back as shared images. That
  owner/client shape is what PS5_Vulkan's `tooling/gpu-broker` already does. The child never calls `sceAgcInit`,
  so no platform protection is worked around.
- **First deliverable: (D) done the upstream way, as stage 1 of (C).** Turn on accelerated compositing: CPU-rastered
  tiles, GPU compositing, and async scrolling in WebKit's own CoordinatedGraphics path. Stage 2 turns on Skia GPU
  raster. (D) done as a home-made layer compositor in the title is a dead end.
- **GL translation: one layer, Zink**, from the same PS5_Mesa commit as the title's RADV (1ba9874f, Mesa 26.2.0).
  WebKit keeps using ANGLE only as its WebGL front end, as all WebKit ports do. ANGLE can later switch to its Vulkan
  backend, and Zink can be dropped if WebKit's Skia ever uses Vulkan or Graphite.
- **Prototype status (host):** Zink + EGL surfaceless + GLES 3.2, built from the pinned PS5_Mesa, **passes all 8 steps
  on lavapipe**, including the run with **no Vulkan loader at all**. The same tree builds **for the PS5 target**
  (prospero-clang, static) with RADV in one Mesa build. The probe **links into a single console ELF with 0
  undefined and 0 duplicate symbols.** It is not packaged as a title and has not been run on the console.
- **The decision probe for later (console):** can a loader-spawned child be a gpu-broker client of our title on 13.60?
  If it can, (C) goes ahead. If it can't, the fallback is to host the GPU-side WebKit work inside the title
  (option A1 below) on the same GPU stack.

## 2. What exists today (prior art)

| Who | How pages reach the GPU | Relevance |
|---|---|---|
| **WPE / WebKitGTK** (Igalia, upstream) | Skia since 2.46. Layers are recorded as SkPicture on the main thread and replayed into 512x512 tiles on GPU (or CPU) worker threads. A threaded TextureMapper compositor and async scrolling run **in the WebProcess**. Frames go to the UI process as DMA-BUF plus an explicit fence fd. The **GPU process is used only for WebGL**; "media and layers rendering" may move there "at some point", and WebProcess rendering stays as the fallback. [Igalia, Apr 2025](https://blogs.igalia.com/carlosgc/?p=1041), [docs.webkit.org graphics](https://docs.webkit.org/Ports/WebKitGTK%20and%20WPE%20WebKit/Graphics.html), [webkit-dev Jul 2025](https://lists.webkit.org/pipermail/webkit-dev/2025-July/032775.html) | The most active, production-used non-Apple path. This is what (C) copies. |
| **WebKit PlayStation port** (Sony, upstream, our tree 539e0189f) | Default build: `USE_COORDINATED_GRAPHICS` + TextureMapper on Sony's system EGL/GLES (in the same library as EGL), via the libwpe PlayStation backend (`AcceleratedSurfacePlayStation`, `ThreadedCompositorPlayStation`). **Skia GL is compiled out with coordinated graphics** because "the PlayStation OpenGL implementation does not dispatch to the context bound to the current thread" (`PlatformDisplaySkia.cpp`). The GPU process is OFF ("implementation not present"). When it is on, it switches to `USE_GRAPHICS_LAYER_WC` (the Windows WC layer tree). | Omni's base. Mesa does dispatch per thread (our probe's `threads` step passes), so the reason for that `#if` does not apply to us. |
| **WebKit GPU process (WC: Win/PlayStation)** | The WebProcess sends a layer tree (`GraphicsLayerWC`) and paints tiles into shareable bitmaps, or into display lists when `shouldUseRemoteRenderingFor(DOM)` is set. The GPU process composites with TextureMapper into a native window. Sony called it "experimental, far from production quality" ([webkit-dev 2022](https://lists.webkit.org/archives/list/webkit-dev@lists.webkit.org/thread/3URU23QFUDEANXKUDTFK6GRBT7WTNLTU)). [Bug 259351](https://bugs.webkit.org/show_bug.cgi?id=259351) and [Bug 261055](https://lists.webkit.org/pipermail/webkit-unassigned/2023-September/1120036.html) ("Hook in rendering to GPU Process") are still open. **The Win and PlayStation GPU-process configurations enable no async scrolling** (`ENABLE_SCROLLING_THREAD` is only set on the non-GPU-process branch of `OptionsPlayStation.cmake`; `OptionsWin.cmake` has no async scrolling). | Upstream, but a side branch. Scrolling would stay tied to the WebProcess main thread. |
| **Apple (Cocoa)** | All DOM, canvas and WebGL drawing happens in the GPU process (`RemoteRenderingBackend`, IOSurface). | Upstream's long-term idea for every port. The Linux ports are blocked on a shared-buffer mechanism, and our broker's shm images are one. |
| **Chromium** | GPU process + Viz compositor. Skia Graphite on Dawn (Vulkan/Metal/D3D12) is replacing Ganesh; ANGLE (Vulkan backend on Android/Linux) handles GL/WebGL ([Phoronix on Graphite](https://www.phoronix.com/news/Chromium-Skia-Graphite)). | Shows that "Vulkan underneath, GL only through one translation layer" is the industry direction. |
| **Firefox WebRender** (general knowledge, not re-checked today) | A GPU renderer/compositor on GL (ANGLE/D3D11 on Windows), a GPU process on Windows, and Software WebRender as the fallback. | Same split: a GPU compositor, with CPU fallback kept. |
| **Console/handheld browsers** (general knowledge) | Xbox Edge = Chromium (D3D via ANGLE). Steam Deck = desktop Linux on Mesa RADV. Switch = NetFront NX (WebKit), with little public detail. | Nothing reusable beyond the above. |
| **PS5 homebrew** | **PS5_Mesa/PS5_Vulkan** (RADV on AGC, Vulkan 1.4, CTS running; validated on 6.02 and 12.70 per its PLATFORM_NOTES; **our own title already runs it on 13.60**, s2/s3.4c). **PS5_Vulkan `gpu-broker`**: "trusted native clients use a title's GPU". Clients run their own RADV, and the owner submits and presents. It is LGPL-2.1+. A WGL/Zink build passed an OpenGL 4.6 offscreen probe through it (PS5_Proton; firmware not stated), and its README says "**native PS5 EGL/OpenGL support is not implemented**". **ps5-opengl** (Mesa/Gallium on AGC, GL 4.6; 0.3.0 on Mesa 26.2.0, Sept 2026; tested on 6.02 per our notes). **ProsperoEden** (OpenGL, 6.02/12.70). | **No public project runs Zink + EGL on PS5 FW 13.x.** P2/P3 below are, as far as we found, the first build of it. |

## 3. Feasibility table

YouTube numbers are from the CPU census (`outputs/GPU-ROUTE-2026-10-28.md` §3): UI-side `WKPagePaint` takes **4.1 ms per frame**
while scrolling (≈650 ms/s on the main thread with page+bg 3.4 ms and chrome 3.2 ms). WebProcess raster takes **1.97 ms per
display**. YouTube's WebProcess main thread is **busy 6.2–6.6 s of every 8 s** with the JIT off (platform notes §26).
**No GPU route makes YouTube load faster:** it is JavaScript-bound. The win is smooth scrolling and animation while JS runs,
less UI-thread copying, working accelerated canvas and View Transitions, and a 4K page that is affordable.

| Option | What it needs | Main risks | Expected gain (YouTube) | Effort | Verdict |
|---|---|---|---|---|---|
| **(A) GPU process hosted in the title** (WC) | `ENABLE_GPU_PROCESS` + `USE_GRAPHICS_LAYER_WC` (the PlayStation port's own GPU-process configuration). A PS `GPUProcessMain` (Omni already has an `OMNI_PROCESS_GPU` multi-call hook). An offscreen `WCSceneContext` (today it renders to a native window). Zink/EGL in the title. Running GPUProcess *inside* the title process (A1) is not supported upstream: its singleton and main-RunLoop assumptions clash with the UI process. Stage 2: remote DOM display lists. | WC is experimental with open upstream bugs. **No async scrolling**, so scrolling still waits for YouTube's busy main thread. A GPU-side crash takes down the UI (A1). Every draw is serialised over IPC. | GPU compositing, then GPU raster. The UI copy (≈4.1 ms/frame) goes. Scroll jank stays. | Large | **Fallback only (A1)**, used if children can't be broker clients. It shares the whole GPU stack with (C). |
| **(B) WebProcess inside the title** | An in-process WebProcess. WebKit2 no longer supports running its WebProcess in-process, so Omni's launcher and IPC would need forking. | One page crash kills the title. The JIT/exec rules (no concurrent PROT_EXEC) would then cover the UI. The title and web content share memory budgets. It gives up the process isolation upstream relies on. | The same rendering as (C). | Large, with continuing fights against upstream | **Dead end.** |
| **(C) Child GPU access, legitimately: title-owned GPU broker** *(chosen)* | Title = broker owner (PS5_Vulkan `gpu-broker/server.cpp`, on its existing RADV device). WebProcess = trusted client (`client.a`: its own RADV userland building command streams in shm; the title submits). Zink + Mesa EGL surfaceless in the WebProcess (**P1–P3 done**). WebKit: the port's default CoordinatedGraphics path; lift the `PLAYSTATION && COORDINATED_GRAPHICS` `#if` around `SkiaGLContext`; a surfaceless PlatformDisplay without epoxy; `ENABLE_ASYNC_SCROLLING` ON; AC on in the shell; an AcceleratedSurface whose target is a broker image the title imports into `OmniGpuPresent`. | **Unproven: a 9021-loader child as a broker client on 13.60** (console probe CP-2). The broker is "not an untrusted GPU command sandbox": a compromised WebProcess could reach GPU-visible title memory. That is a change to the trust boundary for the user to accept, and is weaker than Linux's per-process GPU VM. A GPU hang in client work stalls the title's queue, so it needs a watchdog plus a kill switch with CPU fallback. Client memory counts against the title's budget (default host limit 128 MiB, raisable to 4 GiB). | Async scrolling: **60 fps scrolling while the main thread is busy**. The UI-side `WKPagePaint` 4.1 ms + page+bg 3.4 ms copies are replaced by a texture import (≈400–650 ms/s of title main thread freed while scrolling). Raster (≈2 ms/display, ×4 at 4K) moves to GPU workers. Accelerated canvas works again (it fixes the canvas-crash class for real) and View Transitions run composited. A 4K page output becomes affordable. | Large, done in stages; each stage is shippable behind a flag | **Chosen.** It is the upstream Linux model, and it moves into a GPU process unchanged if upstream goes there. |
| **(D) CPU raster + GPU compositing** | **(D-upstream)** = stage 1 of (C): CoordinatedGraphics with Skia CPU workers, a GPU TextureMapper compositor and async scrolling. It needs a GL context in the WebProcess (via the broker), but no Skia GL and no display lists. **(D-title)** = a home-made compositor in the title for CPU-rastered layers. | D-upstream: the same broker risk as (C). D-title: forks WebKit's layer model and would be thrown away. | D-upstream: smooth scrolling and animations now; raster stays on the CPU. | D-upstream: medium. D-title: medium | **D-upstream is a stepping stone (do it first). D-title is a dead end.** |

Why not (A) as the main route, even though the PlayStation port's own GPU-process switch points at WC: it has no async
scrolling. It is the least-developed configuration upstream, and the GTK/WPE ports, which get the most non-Apple graphics work,
keep rendering in the WebProcess and use the GPU process only for WebGL. Every piece built for (C) still applies if upstream
later moves layers into a GPU process: Zink/EGL, the broker client, the image hand-off and the title compositor.
Only the process that holds the GL context changes.

## 4. How it scales (longevity check)

- **Upstream tracking:** (C) uses `CoordinatedGraphics`, `SkiaPaintingEngine`, `ThreadedCompositor`, `ScrollingThread` and
  `PlatformDisplaySurfaceless`, which are the files the GTK/WPE maintainers keep improving. Omni's port-specific code is small: the
  AcceleratedSurface target and the PlatformDisplay. Updating WebKit stays a rebase.
- **One GL layer:** Zink, from the same PS5_Mesa pin as RADV (one dependency, one version). WebGL later goes through WebKit's
  bundled ANGLE on top of Zink's GLES 3.2 / EGL, the same arrangement as on Linux desktops. A later swap to ANGLE's Vulkan
  backend, or to Skia Vulkan/Graphite, takes Zink out without touching the broker or the title.
- **WebGL, accelerated canvas, View Transitions:** they all need a GL context plus compositing, which (C) provides. GTK/WPE run WebGL
  in their GPU process, and that can follow later on the same broker.
- **4K/HDR pages:** tiles are GPU-rastered, so a 2160p page is the same work spread over more tiles. The title compositor already
  does 4K present (5.2 ms CPU + 1.0 ms GPU). Skia supports F16/PQ surfaces for HDR pages later.

## 5. Prototype (Task 2): Zink + EGL surfaceless on the pinned PS5_Mesa

Source: `nxe-ps5/bigapp/private/av2/upstream/PS5_Mesa` @ **1ba9874f** (Mesa 26.2.0), the RADV the title links,
exported by `git archive` to `/home/builder/ogp/`. Probe: `prototype/egl-probe/ogp_egl_probe.c`. It runs 8 steps, and each one
prints PASS/FAIL:
client extensions → surfaceless display → GLES 3 context with no surface → FBO clear + full readback → GLSL ES 3.00 draw →
**two threads with their own current contexts at once** (the property Sony's GL lacks) → a texture shared across contexts →
teardown.

| Step | Where | Result | Evidence |
|---|---|---|---|
| **P1** host build: Zink + EGL (surfaceless) + GLES, Linux x86-64 | WSL, `build-omni-gpupages-zink-host.sh` | **PASS 8/8** on lavapipe: `OpenGL ES 3.2 Mesa 26.2.0`, renderer `zink Vulkan 1.4(llvmpipe)`, max texture 16384, MSAA 4 | `prototype/host/probe-lavapipe.log` |
| **P1b** the same, with patch 1 (Zink takes the driver's ICD entry point directly; **no Vulkan loader**, `VK_ICD_FILENAMES=/nonexistent`) | `build-omni-gpupages-zink-p2.sh` | **PASS 8/8**. Control: with the ICD entry pointing at a missing library, it **fails at `display`** as expected. One harmless log line: `vkEnumerateInstanceLayerProperties failed` (layers are a loader feature). | `prototype/host/p1b-probe-noloader.log` |
| **P2** PS5-target Mesa: Zink + EGL + GLES + **RADV (ps5 winsys)** in one build, prospero-clang, static | same script | **Configured and compiled: 1388/1391 edges.** The only failure is the *shared* `libgallium-26.2.0.so` link, which a title doesn't use. 30 static archives + EGL/GLES objects produced. Needed patch 3 (see below). | `prototype/ps5/steps.txt`, `ninja.log`, `archives.txt` |
| **P3** link check: console probe + EGL + GLES + Zink + gallium + **RADV whole archive**, using PS5_Vulkan's `radv-link.sh` recipe and the av2 title-smoke CRT and AGC stubs | `build-omni-gpupages-p3-link.sh` | **Links: 0 undefined, 0 duplicate**. `llvm-pie.elf` (155 MB unstripped debugoptimized) has 290 imports, all served by system stubs except one weak TLS wrapper (`_ZTH23_mesa_glapi_tls_Context`), which s2's packager already binds to 0. `readlink` (libkernel_sys) is already ENOSYS-bound by s2's packager. | `prototype/ps5/p3/steps.txt`, `imports-by-stub.txt` |

Mesa changes (`prototype/mesa-patches/apply_ogp_mesa_patches.py`, diff in `ogp-mesa.diff`; all are compiled out unless their
macro or option is set, so a plain build of the tree is unchanged):
1. `OGP_ZINK_STATIC_ICD=<symbol>` (zink_screen.c): Zink takes `vkGetInstanceProcAddr` from the statically linked
   driver (`vk_icdGetInstanceProcAddr`, the way the title already calls RADV) instead of `dlopen("libvulkan.so.1")`.
   `vkGetDeviceProcAddr` comes through a trampoline on Zink's single instance. Host-verified (P1b).
2. `OGP_SURFACELESS_ZINK_NO_DRM` (platform_surfaceless.c): with no DRM nodes, EGL's own "retry with Zink" loads Zink in
   **hardware** mode on the first Vulkan device (RADV) instead of requiring `LIBGL_ALWAYS_SOFTWARE`, which would make
   Zink look for a CPU device. It compiles for the PS5. **It can't be exercised on the host** (lavapipe is a CPU device), so the
   console probe is its first real test.
3. `meson.build`: let Zink's DRI frontend (and so EGL) build without DRM when `radv-winsys=ps5` on a non-Linux host,
   the same exception upstream already makes for macOS and KGSL.
Plus `prototype/egl-probe/ogp_dri_nodrm_stubs.c`: link stand-ins for 11 DRM-only DRI frontend functions (`dri2.c` isn't
built without DRM) and SysV `shm*`. Each one logs once if it is ever reached. The proper fix is a Mesa build change, to do before
WebKit integration.

**Not done yet (needs no console):** packaging P3 as a test title with s2-gpu's pipeline (import check, ps5-native-tool, FSELF,
`--strip-debug`, release Mesa). That needs **a test title ID other than PPSA99732**, which the user or the console owner picks.
After that come the broker client archive (`PS5_Vulkan/tools/build-gpu-broker-client.sh`) and a host check of owner and client
(`check-gpu-broker.sh`, ASan/UBSan).

## 6. Console probe plan (for whoever holds the console later; one reservation, nothing installed over Omni)

All probes go in a **separate test title** (not PPSA99732). Files are swapped by upload-then-rename (SMP rule, notes §26).
Logs go to `/data/omni/gpu-pages/`. Each probe has a 10 s watchdog and exits on any failed init. None of them flips
PROT_EXEC or runs exec-flip stress.

| Probe | What it runs | Pass | Decides |
|---|---|---|---|
| **CP-1 title EGL** | P3's probe as the title's only code: RADV → Zink (patch 1+2) → EGL surfaceless → 8 steps, offscreen, no VideoOut. | `RESULT PASS`, `GL_RENDERER` names RADV, no `ogp: no-DRM stand-in reached` lines, clean exit. | That Zink/EGL works on RADV on 13.60, which nobody has shown publicly. |
| **CP-2 broker coexistence** *(the decision probe)* | The test title runs the broker owner. It starts the probe built against `client.a` **through the 9021 loader** (as Omni starts its WebProcess) and passes the endpoint fd with `0x25b`. The client draws, the owner reads the client's image back and checks its pixels, and the client exits. | Client `RESULT PASS`, owner pixel check exact, no orphan process (parent-gone net), fences drained. | **(C) goes ahead**, or fall back to A1 (GPU work inside the title). |
| **CP-3 with video** | CP-2 while the title's hardware decoder + GPU video (s3.4c's shared RADV device) play 4K VP9. | As CP-2, no decoder errors, no Agc refusal. | Coexistence with the "decoder holds pipe 0/queue 0" rule. |
| **CP-4 WebKit stage 1** | A WebProcess with AC on, CPU tiles, GPU compositor and async scrolling as a broker client, on `scroll-bench*.html` and a YouTube browse page. | Scroll fps steady while the main thread is busy; title main-thread ms/frame below the census. | Ship stage 1 behind a flag. |

## 7. Licences (all compatible with GPL-3.0-or-later)

| Component | Licence | Use |
|---|---|---|
| Mesa (Zink, EGL, glapi, gallium, NIR, util) | MIT | linked into the probe / later the WebProcess |
| PS5_Mesa RADV ps5 winsys | MIT (SPDX in files) | already linked by the title |
| PS5_Vulkan tools/recipes (`radv-link.sh`, `ps5-cross.ini`) | GPL-3.0-or-later | build recipe |
| PS5_Vulkan `gpu-broker` (owner/client) | LGPL-2.1-or-later | planned (CP-2) |
| zlib (Mesa subproject 1.3.1) | zlib | in RADV archive |
| ANGLE (later, WebGL front end) | BSD-3-Clause | planned |
| Skia, WebKit | BSD-3 / LGPL-2.1 + BSD | already used |
| Our probe and stubs | GPL-3.0-or-later (probe), MIT (Mesa-side stubs and patches) | new |
No third-party prebuilt binary goes to the console. Everything is built from source here. The host test uses the system
lavapipe (Ubuntu Mesa 25.2.8) **on the PC only**.

## 8. Files

- `outputs/omni-gpu-pages/REPORT.md` (this file), `survey/` (WebKit tree reads: GPU process, WC, PlayStation options, PlatformDisplaySkia)
- `prototype/egl-probe/ogp_egl_probe.c`, `ogp_host_icd.c` (host only), `ogp_dri_nodrm_stubs.c`
- `prototype/mesa-patches/apply_ogp_mesa_patches.py`, `ogp-mesa.diff`
- `prototype/host/` (P1, P1b logs + host probe binary), `prototype/ps5/` (P2), `prototype/ps5/p3/` (link check, imports, ELF)
- Build scripts (helper-run, detached, `flock`-guarded, writing only the paths above and `/home/builder/ogp`):
  `outputs/build-omni-gpupages-{survey,survey2,find,zink-host,zink-p2,p3-link,p3-imports}.sh`

## 9. For the reusable platform notes (proposed, not yet added)

- Zink + Mesa EGL surfaceless from PS5_Mesa 1ba9874f builds for the PS5 target statically alongside RADV. Three things are needed:
  Zink taking the static ICD entry instead of dlopen'ing a loader, a no-DRM surfaceless path in hardware mode, and a meson
  exception like macOS/KGSL. 11 DRM-only DRI functions and `shm*` are unresolved without stand-ins.
- In one PS5 Mesa build, RADV's whole archive already carries xmlconfig and the Vulkan dispatch tables. Leave out
  `libxmlconfig.a`, and leave Zink's own `vk_dispatch_table` object out of `libzink.a`, or the link reports 27 duplicates.
- The WebKit PlayStation port disables Skia GL with coordinated graphics only because Sony's GL doesn't dispatch per thread.
  Mesa does: two contexts current on two threads at once passed 200/200 each.
- **Both WSL build helpers (root and user) picked up the same requests again.** `flock` stopped the second build, but a
  root helper can't overwrite a `/tmp` script that the user helper created, and then it ran the **stale** copy. Name inner
  scripts `/tmp/<name>-$$.sh`.
