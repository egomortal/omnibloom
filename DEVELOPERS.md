<p align="center">
  <img src="assets/icon/omni-icon-128.png" alt="Omni Browser icon" width="128">
</p>

# Omni for Developers

*Status as of v105 (October 2026). For the user-facing feature list, see [FEATURES.md](FEATURES.md).*

This page lists the parts of Omni you can reuse in your own PS5 homebrew
project. For each part it gives how mature it is, where it lives, and what to
watch out for.

> **Note:** The paths below are from the Omni engine source tree. Code is being
> published to this repository step by step, so some paths may not be here yet.

## Maturity levels

| Level | Meaning |
| --- | --- |
| **Console-verified** | Runs on real PS5 hardware with recorded test results |
| **Host-verified** | Passes tests on desktop or WSL, not yet run on a console |
| **Experimental** | Partly working, with known defects |
| **Planned** | Design only |

---

## Reusable components

### JavaScriptCore for PS5: Console-verified

A standalone JSC port: the `jsc` shell and a self-test payload.

- **Results:** 25/25 tests pass on a 13.60 console. Benchmark checksum `247239`, 177 ms. A reference engine gives identical results.
- **Execution:** LLInt interpreter only. JIT is untested because it depends on whether homebrew can map executable memory.
- **Build:** `engine/scripts/build-icu.sh`, then `engine/scripts/build-jsc.sh` (about 2,700 ninja steps).
- **Use it for:** embedding a scripting engine in a homebrew app without the rest of WebKit.

### Full WebKit port: Console-verified (in Omni)

WebCore and WebKit with Skia on the CPU, curl/OpenSSL networking, and content extensions turned on.

- **Output:** `WebProcess` and `NetworkProcess`, each 122 MB stripped (8,285 build steps).
- **Build:** `engine/scripts/build-webkit.sh` → `$WORK/build-webkit/bin/`
- **Rendering:** Skia paints on the CPU because Sony's GL can't do per-thread contexts. Frames are presented through PacBrew Mesa EGL/GLES (Zink + RADV), which needs about 45 MB of `.so` files in `/user/homebrew/lib`.
- **Memory:** WebCore's unified sources need about 3 GB per compile job, so keep `-j` at or below RAM ÷ 4 GB.

### ProcessLauncher: Host-verified, used in Omni

WebKit's multi-process model (UI, Web and Network processes) on PS5: processes are spawned through elfldr and IPC sockets are handed over with `SCM_RIGHTS`.

- **Tests:** clean under ASan and UBSan on the host. The dedicated console run is still pending, though Omni runs on it.
- **Use it for:** any homebrew app that needs to spawn and talk to child processes.

### Hardware video decoding: Console-verified

Uses the PS5's hardware decoder, with software (FFmpeg) fallback when it isn't available.

- **Formats:** H.264, HEVC 8/10-bit and VP9 profile 0/2, from 720p to 4K. All 9 tested formats are bit-exact against FFmpeg.
- **Speed:** about 2,100 fps decoding 1080p H.264.
- **Source:** `engine/media/OmniHw*`. `PacketDecoder` tries hardware first. The decode service runs in the UI process and is enabled by `/data/omni/hw-decode.flag`.
- **Caveat:** in testing, hardware decode only worked when launched through the **websrv** homebrew route. Other projects report it being refused from other loader routes.
- **Standalone probe:** `tools/vdec-probe/` (`python run-probe.py`) checks what your console allows and compares output with FFmpeg.

### Media playback in WebKit: Console-verified, with limits

WebKit's `MediaPlayerPrivate` backed by FFmpeg, with MediaSource Extensions enabled.

| Test | Result |
| --- | --- |
| 1080p60 | 0–1 dropped frames per ~5 s steady window, no audio underruns |
| 4K30 SDR | 420 steady frames, zero drops |
| 4K60 SDR fullscreen | 1,250 shown / 18 dropped (1.04%). Startup stalls remain |
| HDR | Not implemented |

### Ad blocking (uBlock integration): Mostly host-verified

| Part | Status | Notes |
| --- | --- | --- |
| Network filtering engine | Console-verified | uBlock's network engine, not the full desktop extension |
| WebKit content extensions | Console-verified | Off in Sony's defaults, turned on in Omni |
| Default lists, 140,985 rules | Installed, first full run pending | EasyList, EasyPrivacy, uBlock lists, Peter Lowe's list. File: `filters/ublock-compiled-default-lists.txt` |
| Cosmetic filters and scriptlets | Host-verified | uBO Lite compiled content scripts, injected as WebKit user scripts |
| Popup matcher | Host-verified | Native matcher. 75,890/75,890 cases agree with real uBlock. Regex rules use a small JSC context of about 12 MiB, created on first need. Rules: `engine/resources/ublock-popup-rules.txt` |
| `$urlskip`, `$removeparam` | Host-verified | Link skipping and URL cleaning |

- **Desktop suite:** 599 + 599 (interpreter) + 893 checks, 0 failures. Network sample: 800/800 blocked, 69/69 everyday resources allowed.
- **Docs:** `docs/UBLOCK-INTEGRATION.md`, `docs/UBLOCK-TESTING.md`.

### Browser shell: Console-verified

Tabs, a controller pointer, an on-screen keyboard, a 1080p/1440p/4K resolution setting with automatic fallback to 1080p after a failed start, and cookie persistence across restarts.

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

- **No DRM.** Widevine and PlayReady are closed by Sony, so Netflix and Disney+ can't work.
- **No JIT yet.** It depends on executable memory for homebrew, which hasn't been probed.
- **Skia on the CPU.** Sony's GL can't do per-thread contexts.
- **HDR** isn't implemented.

## Open problems (good places to contribute)

- Startup and fullscreen-transition frame stalls
- 4K60 drop bursts
- JavaScript screen metrics are wrong: pages see 1920×1080 at DPR 3
- Full YouTube site compatibility
- Error 232403 on one third-party video site (a refused playlist request)
- A JIT feasibility probe
- HDR output

See the "Contributions" section of the [README](README.md) for how contributions are handled.
