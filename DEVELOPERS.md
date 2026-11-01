<p align="center">
  <img src="assets/icon/omni-icon-128.png" alt="Omni Browser icon" width="128">
</p>

# Omni for Developers

*Status as of build 56c (November 1, 2026). For the user-facing feature list, see [FEATURES.md](FEATURES.md).*

This page lists the parts of Omni you can reuse in your own PS5 homebrew
project. For each part it gives how mature it is, where it lives, and what to
watch out for.

> **Note:** The paths below are from the Omni engine source tree. Code is being
> published to this repository step by step, so some paths may not be here yet.
>
> All console results come from a single PS5 on firmware 13.60. See
> [personal notes](personal%20notes.md).

## Maturity levels

| Level | Meaning |
| --- | --- |
| **Console-verified** | Runs on real PS5 hardware with recorded test results |
| **Host-verified** | Passes tests on desktop or WSL, not yet run on a console |
| **Experimental** | Partly working, with open questions |
| **Planned** | Design only |

---

## Current build

**Installed:** candidate **56c**, the performance/HDR fix line, with per-site
uBlock rules on. A GPU lazy-load variant, **56e**, has been tested separately on
top of it.

Every candidate has a rollback path: reinstall the previous build, or restore
it from the automatic `*.before-*` backup.

---

## Reusable components

### JavaScriptCore for PS5: Console-verified

A standalone JSC port: the `jsc` shell and a self-test payload.

- **Results:** 25/25 tests pass. Benchmark checksum `247239`, 177 ms. A reference engine gives identical results.
- **Execution:** LLInt interpreter only, with no JIT (see [Hard limits](#hard-limits)).
- **Build:** `engine/scripts/build-icu.sh`, then `engine/scripts/build-jsc.sh` (about 2,700 ninja steps).
- **Use it for:** embedding a scripting engine in a homebrew app without the rest of WebKit.

### Full WebKit port: Console-verified

WebCore and WebKit with Skia on the CPU, curl/OpenSSL networking, and content extensions turned on.

- **Output:** `WebProcess` and `NetworkProcess`, each 122 MB stripped (8,285 build steps).
- **Build:** `engine/scripts/build-webkit.sh` → `$WORK/build-webkit/bin/`
- **Compiled out:** geolocation, camera, microphone, push notifications and WebRTC.
- **Memory:** WebCore's unified sources need about 3 GB per compile job, so keep `-j` at or below RAM ÷ 4 GB.

| Browsing benchmark | Result |
| --- | --- |
| Scrolling | 59.4–59.9 fps. Worst frame 30–35 ms, none over 50 ms |
| Page draw time | 6.3 ms (down from 11.7 ms) |
| Tab stress test (16 tabs) | No crashes. Free memory recovers to ~500 MiB once background tabs release their decoders |

The shipped tab limit is 8 open with 6 loaded.

### ProcessLauncher: Console-verified (in Omni)

WebKit's multi-process model (UI, Web and Network processes) on PS5: processes are spawned through elfldr and IPC sockets are handed over with `SCM_RIGHTS`.

- **Tests:** clean under ASan and UBSan on the host. It runs Omni's helper processes on the console.
- **Bonus:** a process spawned this way **can get GPU access** even though the foreground app can't (see [GPU work](#gpu-work)).
- **Use it for:** any homebrew app that needs to spawn and talk to child processes.

### Hardware video decoding: Console-verified

Uses the PS5's fixed-function decode block, with software (FFmpeg) fallback when it isn't available.

- **Formats:** H.264, HEVC 8/10-bit and VP9 profile 0/2, from 720p to 4K. All 9 tested formats are bit-exact against FFmpeg.
- **Source:** `engine/media/OmniHw*`. `PacketDecoder` tries hardware first.
- **Background-tab release:** a hidden tab's decoder pauses after 1.5 s and frees its hardware decode channel (~117 MB per 1080p stream), then resumes when the tab is shown again.
- **Caveat:** in testing, hardware decode only worked when launched through the **websrv** homebrew route.
- **Standalone probe:** `tools/vdec-probe/` (`python run-probe.py`) checks what your console allows and compares output with FFmpeg.

### Media playback and HDR: Console-verified

WebKit's `MediaPlayerPrivate` backed by FFmpeg, with MediaSource Extensions enabled and a PQ/HDR fast path.

| Test | Result |
| --- | --- |
| 4K60 SDR, 10 min | 35,921 frames shown / 50 dropped |
| HDR, 10 min (build 56c) | Back to normal drop levels |
| Plain video, 100 s | 2,961 shown / 14 dropped |

**The HDR regression, and what it teaches.** HDR went from 22 dropped / 3 late
(candidate 54) to 429 dropped (55) and 641 dropped (56), then back to normal in
56c. The cause was stick drift pinning the virtual pointer at a screen edge.
That sent WebKit a steady stream of `mousemove` events, which kept the video's
on-screen controls visible and held Omni on the slow, non-HDR compositing path.

The fix has two parts:
1. Drop repeated `mousemove` events at the same position.
2. Park the pointer after 3 s idle.

**Lesson for other ports:** any always-visible overlay over video can knock you
off a fast path. Filter out input noise before it reaches the page.

### Ad blocking (uBlock integration): Console-verified core

| Part | Status | Notes |
| --- | --- | --- |
| Network filtering engine | Console-verified | uBlock's network engine, not the full desktop extension |
| WebKit content extensions | Console-verified | Off in Sony's defaults, turned on in Omni |
| Per-site rule generation | Console-verified, **default** | Rules are generated per site and loaded instead of the full bundle |
| Cosmetic filtering | Console-verified | 5/5 on test pages with per-site rules, same as the full bundle, with no real page elements lost |
| Scriptlets, annoyance lists | Host-verified | uBO Lite compiled content scripts, injected as WebKit user scripts |
| Popup matcher | Host-verified | Native matcher. 75,890/75,890 cases agree with real uBlock. Rules: `engine/resources/ublock-popup-rules.txt` |
| `$urlskip`, `$removeparam` | Host-verified | Link skipping and URL cleaning |

**Cost per iframe:**

| Setup | Cost |
| --- | --- |
| Full filter bundle | 34–41 ms |
| Per-site rules (default) | 14–16 ms |
| Per-site, generic rules in the top frame only | 11–12 ms |

The full lists add up to 140,985 network rules (EasyList, EasyPrivacy, uBlock
lists and Peter Lowe's list).

- **Docs:** `docs/UBLOCK-INTEGRATION.md`, `docs/UBLOCK-TESTING.md`.

### Link grabber: Console-verified

Detects media links in two ways:

1. **On the page**, by scanning the DOM.
2. **At the network level**, by watching actual requests, including requests inside cross-origin frames. This catches HLS manifests and MP4s that page scanners miss.

- **Output:** grabbed links appear as rows in the downloads dialog and on the Launch page.
- **Privacy:** it only runs when Media Downloads is on and the tab isn't private. It logs no browsing history.

### Controller input layer: Console-verified

- **Pointer:** link snapping, a configurable dead zone (Small / Medium / Large / Extra large), and idle parking after 3 s.
- **Drift handling:** the dead zone is applied to the pointer, right-stick scrolling and keyboard navigation, so drift doesn't count as stick activity.
- **Extras:** an on-screen keyboard with cursor/word navigation, and fullscreen media controls.

The full button map is in [FEATURES.md](FEATURES.md#-controls).

---

## GPU work

**The PS5 refuses GPU access to Omni's foreground process.** This is a
hardware-level restriction, and Omni does not try to get around it. All
rendering currently runs on the CPU (Skia) plus the hardware decode block.

**The route that works:** a separate background process, spawned the same way
Omni spawns its helpers, *can* get GPU access and runs compute shaders
successfully.

| Step | Status |
| --- | --- |
| Background process runs compute shaders | Done |
| GPU driver loaded lazily at first video decode instead of at startup (build 56e) | Done. Runs alongside Omni with hardware decode on |
| GPU worker and **actual video playback** at the same time | **Untested. This is the next open question** |
| GPU shader for NV12/P010 → RGBA conversion at 4K | Planned if the step above works |

**Fallback:** package Omni as a real installed PS5 title, which can own the GPU
and screen outright. That isn't viable on the current firmware, so it stays a
future option.

---

## Build environment

**Toolchain:** clang/LLVM 21 (apt.llvm.org), with `ps5-payload-sdk` at `/opt/ps5-payload-sdk`. Host tools: gperf, ruby, perl and python3.

**Dependencies:**

- **Prebuilt (PacBrew sysroot v0.41.1):** curl 8.18, OpenSSL 3.5, FreeType, HarfBuzz 9, fontconfig, libpng/jpeg/webp, libxml2, SQLite, libpsl, Mesa EGL/GLES
- **Built from source:** ICU 78.3, `hb-icu`, libwpe 1.16.3 (static)

```sh
engine/scripts/build-icu.sh        # ICU host tools + PS5 static libs -> $WORK/sysroot
engine/scripts/build-jsc.sh        # sparse WebKit checkout, patch, configure, build jsc
engine/scripts/build-selftest.sh   # -> $WORK/build-jsc/bin/omni-jsc-selftest.elf
engine/scripts/build-webkit.sh     # -> $WORK/build-webkit/bin/{WebProcess,NetworkProcess}
```

`WORK` defaults to `/work/engine`.

## Running on a console

```sh
nc -q0 <ps5-ip> 9021 < omni-jsc-selftest.elf
```

You should get a notification like `Omni Engine JSC: 25/25 passed`. The full
log is at `/data/omni/jsc-selftest.txt`, which you can fetch over FTP.

| Port | Service |
| --- | --- |
| 9021 | ELF loader |
| 8080 | websrv (needed for hardware decode) |
| 2121 | FTP |

---

## Hard limits

- **No DRM.** Widevine and PlayReady are closed by Sony.
- **No JIT.** JavaScript runs on the LLInt interpreter only.
- **No foreground GPU.** Omni's own process is refused GPU access.
- **Nothing above 4K60.** The decode block and bus bandwidth set the ceiling, not Omni's code.
- **Compiled out:** geolocation, camera, microphone, push notifications and WebRTC.
- **No password capture or autofill**, on purpose.

## Open problems (good places to contribute)

- Running the GPU worker during actual video playback
- An NV12/P010 → RGBA compute shader at 4K
- Full YouTube site compatibility
- JDownloader and yt-dlp integration

See the "Contributions" section of the [README](README.md) for how contributions are handled.
