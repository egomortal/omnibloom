# Omni Engine — WebKit for PS5 configured to run homebrew applications

For current verified build results, see [BUILD-STATUS.md](../BUILD-STATUS.md).
The milestone table and feature promises below are inherited project notes.
The new engine test now links, but console rendering and uBO parity are unverified.

Our own copy of WebKit inside the Omni app, separate from the system browser.
Owning the engine is what makes **uBlock-Origin-grade blocking built in**
possible. Upstream WebKit's content-blocker compiler (the engine behind Safari
content blockers and uBO Lite) runs inside the page loader, so it covers HTTPS
paths and element hiding, not just hostnames.

**It never touches the PlayStation's own browser.** It's a separate binary
with its own cache, cookies and settings under the Omni title's storage.

## Approach

We build upstream WebKit's **PlayStation port** (Sony maintains it upstream,
uses curl networking, and runs JS without a JIT) with the homebrew
**ps5-payload-sdk** instead of Sony's official SDK. The gaps are filled by
small, documented shims:

| Piece | What it replaces | File |
|---|---|---|
| `memory-extra` | Sony's private VSS memory API (reserve/commit/protect) → `mmap`/`mprotect` | `ports/memory-extra/` |
| `omni-sce-compat.h` | Sony libc dialect: `pthread_setname_np(name)`, `pthread_get_name_np(t,buf)`, `clock_gettime_np`, 6-arg `_umtx_op`, `getenv_np`, `SO_NBIO` | `ports/sce-compat/include/` |
| `sys/sysinfo.h`, `malloc.h` | Linux-isms WTF expects; RAM size via `sysctl hw.physmem` | `ports/sce-compat/include/` |
| `PlayStationModule.cmake`, `Sign.cmake` | Sony SDK CMake modules (we link statically, homebrew is fake-signed later) | `cmake/` |
| `omni-clang(++)` + `omni-ps5.cmake` | SDK wrapper bug: it appended `crt1.o` to `-E` runs, which hung CMake | `toolchain/` |
| `webkit-requirements` | Sony's private package: process launcher, child-process init, WebKit extension-bundle loader, TLS trust store (Mozilla CA bundle) + CMake config | `ports/webkit-requirements/` |
| `OmniChildProcessMain.cpp` | Sony's Web/Network/GPU entry points (which `dlopen` Sony system modules) | `entry/` |
| `apply-patches.py` | Guarded CMake edits (`OMNI_HOMEBREW`) + 4 upstream bug fixes in the PlayStation path (WKRunLoop filename case, Skia GL accessors, `hardwareAccelerationEnabled`, `SkiaPaintingEngine::create`) + content-blocker store fix | `scripts/` |

ICU 78.3 is cross-built from source (`-DU_STATIC_IMPLEMENTATION`, because the
PS5 clang target honours `dllexport`). Host: clang/LLVM **21** (needed by
current WebKit; the SDK picks it up automatically via `prospero-llvm-config`).

## Milestones

| # | Milestone | State |
|---|---|---|
| 1 | **JavaScriptCore for PS5**: `jsc` shell + `omni-jsc-selftest.elf` | ✅ **verified on a 13.60 console: 25/25, checksum 247239, bench 177 ms** |
| 2a | **Full WebKit compiles + links for PS5**: WebCore, WebKit, Skia (CPU), curl/OpenSSL networking, content extensions ON. `WebProcess` + `NetworkProcess` (122 MB each, stripped) | ✅ builds (8,285 steps) |
| 2b | UI host: Omni process drives a WKView/WKPage (C API) and renders a page offscreen → PNG for a hardware test | next |
| 3 | Own `ProcessLauncher` (elfldr spawn + `SCM_RIGHTS` socket hand-off) | ✅ written, host-tested (ASan/UBSan). ⏳ console run |
| 4 | Present via EGL/GLES (ps5-opengl), DualSense input, OSK, tabs, inside the Omni app | planned |
| 5 | **Built-in blocking**: Omni Shield converts uBO lists → WebKit content-blocker JSON, compiled at list update. Plus uBO cosmetic CSS and scriptlets applied through WebKit user scripts | planned |
| 6 | Media: WebKit `MediaPlayerPrivate` backed by FFmpeg (MSE for YouTube-on-web) | planned |

Known hard limits: no DRM (Widevine/PlayReady are Sony-closed, so no
Netflix/Disney+), and no JIT unless the console allows executable memory for
homebrew (probe later; LLInt interpreter works without it).

## Build

```sh
# once: LLVM 21 (apt.llvm.org), ps5-payload-sdk at /opt/ps5-payload-sdk
engine/scripts/build-icu.sh            # ICU 78.3 host tools + PS5 static libs -> $WORK/sysroot
engine/scripts/build-jsc.sh            # sparse WebKit checkout, patch, configure, ninja jsc
engine/scripts/build-selftest.sh       # -> $WORK/build-jsc/bin/omni-jsc-selftest.elf
# full WebKit: needs PacBrew sysroot in $SDK/target/user/homebrew, hb-icu, libwpe,
# ports/webkit-requirements installed into $WORK/sysroot (see notes below)
engine/scripts/build-webkit.sh         # -> $WORK/build-webkit/bin/{WebProcess,NetworkProcess}
```

`WORK` defaults to `/work/engine`. A full JSC build is ~2,700 ninja steps.

## Running the self-test on a console

```sh
nc -q0 <ps5-ip> 9021 < omni-jsc-selftest.elf
```

Expect a notification like `Omni Engine JSC: 25/25 passed, bench [ms,checksum] = [...]`.
The full log is at `/data/omni/jsc-selftest.txt` (FTP). The benchmark checksum
must be `247239`. The same tests give 25/25 and that checksum on a reference
engine.

## Notes from the full WebKit bring-up

* **Deps**: PacBrew prebuilt sysroot v0.41.1 (curl 8.18, OpenSSL 3.5, FreeType, HarfBuzz 9,
  fontconfig, libpng/jpeg/webp, libxml2, SQLite, libpsl, Mesa EGL/GLES via Zink + RADV).
  Built from source: ICU 78.3, `hb-icu` (HarfBuzz ICU bridge), libwpe 1.16.3 (static).
  Host tools: clang/LLVM 21, gperf, ruby, perl, python3.
* **Content extensions** (WebKit's native content blocker, the engine of Safari blockers
  and uBO Lite) are OFF in Sony's defaults. Omni turns them ON. That's our built-in uBO.
* **Memory**: WebCore's unified sources need ~3 GB per compile job. Use `-j` ≤ RAM/4 GB.
* **Graphics at runtime**: Skia paints on the CPU (Sony's GL can't do per-thread
  contexts). Presentation uses PacBrew Mesa EGL/GLES (~45 MB of `.so` in
  `/user/homebrew/lib` on the console).
