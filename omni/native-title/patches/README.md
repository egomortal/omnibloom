# Omni native title: patch sets (s3.1c, s3.4c, s3.4d)

Experimental, not-yet-console-tested work (HDR10 output, the JSC heap change, the software-video overflow fix, GPU page
drawing) is kept apart in [`experimental/`](experimental/README.md). None of it is part of a release build.

## s3.4d: Dark mode uses the site's own dark theme first (current build, 2026-11-05)

**s3.4d** = s3.4c + `OMNI_DARK_APPEARANCE_EMU_V1` (title `eboot.bin` `ca22b2e4…f7d26a41`; child unchanged, `7b810ea5…fd717c64`).
The dark-mode standard is now three title-side patches, applied in this order:

| Marker | Script | What it does |
|---|---|---|
| `OMNI_DARK_VIDEO_PLANE_V1` | `s34/tools/apply_dark_video.py` | the dark-page invert filter steps aside while a playing video covers >= 20% of the viewport, so YouTube keeps its fast video plane (the 0.0145 s start stall) |
| `OMNI_DARK_STANDARD_V1` | `s34/tools/apply_dark_standard.py` | the page's own dark theme first, the invert filter only as the last resort; Dark Reader add-on hook (`<html data-omni-dark-addon="on">`) |
| `OMNI_DARK_APPEARANCE_EMU_V1` | `s34/tools/apply_dark_emu.py` | the shell's dark appearance does not reach pages in this engine, so a page-world document-start script answers `matchMedia('(prefers-color-scheme: dark)')` from Dark mode and fires change listeners. Sites that choose their theme in script go dark on their own; CSS-only `@media (prefers-color-scheme)` sites still get the filter |

- Build: `build/build-omni-native-s34d.sh` (= the s3.4c order below, plus step 7b `apply_dark_emu.py` right after step 7).
  `s34/build.py` and `s34/tools/prep_s34.py` are now the s3.4d copies (label and overlay marker `.s34d-marker`); the
  s3.4c copies are in this repository's history at `45790c6`.
- Host tests: dark video-plane 12/12, standard 11/11, emu 6/6 (`s34/hosttest/dark_emu_test.js`, node); the rest as s3.4c.
- Console (2026-11-05, s3.4d): feature PASS, media PASS twice (0 hitches), YouTube watch with youtube.com dark ON 68.3 s in
  90 s, `matchMedia(dark)` = true on YouTube, example.com untouched. Signed-out YouTube still picks its theme server-side,
  so it gets the filter unless YouTube's own Appearance is set to Dark once.
- Checks: `s34/checks-s34d.txt`. Summary of the whole s3.4 to s3.4d pass: `s34/REPORT.md`.

| # | s3.4d order (as `build/build-omni-native-s34d.sh` applies it) | Marker |
|---|---|---|
| 0-5 | as s3.4c below (host tests, s3.1c steps, child `7b810ea5`, pointer-cross, CLEAN4 entry) | |
| 6 | `s34/tools/apply_dark_video.py <tree>` | `OMNI_DARK_VIDEO_PLANE_V1` |
| 7 | `s34/tools/apply_dark_standard.py <tree>` | `OMNI_DARK_STANDARD_V1` |
| 7b | `s34/tools/apply_dark_emu.py <tree>` (checks `OmniDarkPages.h` is the `OMNI_DARK_STANDARD_V1` result first) | `OMNI_DARK_APPEARANCE_EMU_V1` |
| 8-9 | as s3.4c below (stats diff, pointer-cross on the s3.4 files, ninja, `prep_s34.py`, `build.py`) | |

---

## s3.4c: 4K60 SDR on the GPU video path (console-proven 2026-11-05)

**s3.4c** is the build that played 2160p60 SDR YouTube on the console: 3840x2160, median 59.94 fps, 0.17% of frames
dropped over 300 s (title `eboot.bin` `015c8e6c…d707f6b0`; child unchanged, s3.1c's `7b810ea5…fd717c64`). It stacks on
s3.1c (this folder's s3.1c steps below) and is title-only: the child is linked from the unpatched tree first and the build
stops unless it is byte-identical to `7b810ea5`.

| Folder | What |
|---|---|
| `clean4/integration.diff` | Astra's canonical CLEAN4 selection (25 files, a normalized review tree): native quick bar, grouped Options and Apps tiles (`OMNI_MQ_NATIVE_V1`), media stats + HDR-preference bridge, downloads readiness C-1, assigned card ports C-2, the files-port migration and Setup metadata. Its userland parts are applied in this repository (`downloads/worker/`, `omni/files-broker/`, `setup/tools/make_package.py`); Setup's `ports.py`/`port_registry.py` are not (they need Setup-next modules this repository does not have). |
| `s34/s34-entry/`, `s34/s34-media/`, `s34/s34-entry-baseline.json` | the integration's `engine/entry` + `engine/media` files as the build copies them; `OmniBrowser.cpp` is the 3-way merge of the integration and Astra's fps diagnostics plus 4k60's patch 05 (`OMNI_HOLE_ELIGIBILITY_PROBE_V1`) |
| `s34/engine/media/`, `s34/src-title/` | the title's own media and presenter sources after 4k60's patches 01-03 (`OMNI_GPU_VIDEO_V3`, `OMNI_GPU_PRESENT_V3`, `OMNI_VIDEO_FPS_V2`), merged with the CLEAN4 presenter (two-entry SDL import cache, region reuse) |
| `s34/tools/` | the s3.4c tool set (`apply_s34_entry.py`, `apply_dark_video.py`, `apply_dark_standard.py`, `prep_s34.py`, the earlier `prep_s*`/`apply_*` the chain still calls) |
| `s34/hwservice-stats-tree.diff` | the integration's two stats entry points in the tree's own `OmniHwService.cpp` (the in-tree link needs them) |
| `s34/hosttest/` | GPU host tests (`gpuvideo_test.cpp`, `present_test.cpp`, `pair_test.cpp`, lavapipe), the dark-page tests (node), `pointer_cross_test_s34.cpp`, `eligibility_test.cjs` |
| `s34/SHA256SUMS.txt`, `s34/checks.txt` | the s3.4c build's own hashes and string/symbol checks (paths scrubbed) |
| `video-4k60/` | the omni-video-4k60 patch set: 00 (GPU V2 base, skipped where `OMNI_GPU_VIDEO_V2` is present), 01, 02, 03, 05, `apply_video4k60.py`, `REPORT.md` (the cause: the dark-page filter kept YouTube off the hole-punch plane), `TEST-PLAN.md`. Its 04 (dark) is not used: s3.4's `OMNI_DARK_VIDEO_PLANE_V1` + `OMNI_DARK_STANDARD_V1` cover it, so it is not in this folder. |
| `build/build-omni-native-s34*.sh` | s3.4, s3.4b, s3.4c and s3.4d |

### Order (as `build/build-omni-native-s34c.sh` applies it)

| # | Step | Marker |
|---|---|---|
| 0 | s3.1c's host tests (step 0 below), then the GPU host tests on lavapipe: video V3 (+ fallback, `failsetup`), shared device (one VkDevice for present + video), present V3 (+ fallback), surface-pair cache | |
| 1-3 | s3.1c steps 1-6 (WebKit s3 + PNA, `engine-entry/*`, view-transition, yt, soak read), then the **child** from that unpatched tree (must be `7b810ea5`) | |
| 4 | `tools/apply_pointer_cross.py <tree> shell/pointer-cross.diff` + `pointer_cross_test.cpp` (41/41) | `OMNI_POINTER_CROSS_V1` |
| 5 | `s34/tools/apply_s34_entry.py <tree>`: the CLEAN4 `engine/entry` + `engine/media` files; each tree file must equal its pinned baseline (`s34-entry-baseline.json`) first. It also checks each file against `codex-ui/20261104-suite-clean4-integration/proposed/` next to the workspace (= `clean4/integration.diff` applied) | `OMNI_MQ_NATIVE_V1`, `OMNI_VIDEO_STATS_BRIDGE_V1` |
| 6 | `s34/tools/apply_dark_video.py <tree>`: the dark-page filter steps aside while a playing video covers >= 20% of the viewport (the YouTube 0.0145 s start stall) | `OMNI_DARK_VIDEO_PLANE_V1` |
| 7 | `s34/tools/apply_dark_standard.py <tree>`: Dark mode the standard way (the page's own dark theme first, the invert filter last, the Dark Reader add-on hook) | `OMNI_DARK_STANDARD_V1` |
| 8 | `patch -p1 < s34/hwservice-stats-tree.diff` in the tree; `pointer_cross_test_s34.cpp` on the s3.4 files (41/41) | |
| 9 | ninja `OmniEngine`, `make_link_command.py`, `s34/tools/prep_s34.py` (compiles `s34/engine/media/OmniHwService.cpp` + `OmniGpuVideo.cpp`, swaps the GPU objects into the link, copies `s34/src-title/`), `build.py` (pages: the final CLEAN4 tree, `omni/pages/bundle-clean4/`) | `OMNI_GPU_VIDEO_V3`, `OMNI_GPU_PRESENT_V3` |

Build log of the console-proven build: host tests 17/17, 51/51, 103/103; GPU host tests all exit 0; child IDENTICAL;
pointer-cross 41/41 twice; ninja ok; layout check PASSED. Runtime flags (from `video-4k60/TEST-PLAN.md`):
`/data/omni/gpu-present.flag` (`out=2160`), `/data/omni/gpu-video.flag`, optional `video-fps.flag`; kill switch for the shared
device `/data/omni/gpu-share-disabled.flag`. HDR10 passthrough is not part of s3.4c (SDR only).

s3.4d (above) adds the third dark-mode patch on top of this order.

---

## s3.1c

This folder holds the changes that turn the **s3** native tree into the **s3.1c** build
(title `eboot.bin` `e8ac0c9d…69e498e2`, child `omni-engine-child.elf` `7b810ea5…fd717c64`).
The title's own sources (`../src/`, `../child-src/`, `../tools/`, `../build.py`, `../child_build.py`,
`../make_link_command.py`) and the host tests (`../hosttest/`) are the s3.1c copies.

It is **not** a complete engine tree. The s3 base tree (WebKit + engine shell, built in WSL) is not in this
repository; see "What is missing" below. `omni/engine/` in this repository is an older shell and is not the s3 base.

Paths in the scripts were changed to `/path/to/workspace` (the PC workspace) and `/home/builder` (the WSL home).
The console address seeded in `omni-sec-connect.cpp` is the documentation address `192.0.2.10`: replace it
(or, better, look the console's addresses up at run time) before a real build.

## Order (as `build/build-omni-native-s31c.sh` applies it)

Every step is idempotent (each patch carries a marker and refuses an anchor that does not match exactly once).
The build works on a private overlay of the read-only s3 tree.

| # | Step | What it changes | Marker |
|---|---|---|---|
| 0 | Host tests: `hosttest/sec_connect_test.cpp`, `hosttest/vault_os002_test.cpp`, the s3 vault suite, SDK `-Werror` compile of `omni-sec-connect.cpp` | nothing (fail fast) | |
| 1 | `tools/apply_s3_webkit.py <tree>` | s3's WebKit changes (JSC JIT pool RWX-once; no accelerated canvas without a shared display). Already in the s3 tree, so normally a no-op | `OMNI_JSC_JIT_V3`, `OMNI_NO_ACCEL_CANVAS_V1` |
| 2 | `tools/apply_s31_pna.py <tree>` | OS-001: curl opensocket callback tags each socket with its request URL and first-party site (8 files; the resulting diffs are `webkit/*.pna.diff`) | `OMNI_SEC_PNA_CONNECT_V1` |
| 3 | copy `engine-entry/*` over `<tree>/engine/entry/` | the s3.1b shell sources, including OS-002 `OmniVault.h` and jit2 build 4 `OmniCrash.h` (crash capture V2) | `OMNI_VAULT_V2`, `OMNI_CRASH_V2` |
| 4 | `tools/apply_viewtransition.py <tree>` | view-transition guard in WebCore `Document.cpp` (no forced compositing mode when accelerated compositing is off) | `OMNI_NO_VIEW_TRANSITION_V1` |
| 5 | `tools/apply_yt.py <tree>` | opt-in YouTube timeline measurement mode (`/data/omni/yt-timeline.flag`) | `OMNI_YT_TIMELINE_V1` |
| 6 | `tools/apply_soak_read.py <tree>` | the endurance self-test waits for the soak before reading results | `OMNI_SOAK_READ_V1` |
| 7 | ninja `OmniEngine`, `make_link_command.py`, `child_build.py` | the **child**, from the tree *before* step 8 (must equal s3.1b's child byte for byte) | |
| 8 | `tools/apply_pointer_cross.py <tree> shell/pointer-cross.diff` | Cross clicks at the pointer while the stick/mouse pointer leads (adds `OmniPointerCross.h`, edits `OmniBrowser.cpp`, `OmniFeaturesPanel.h`); host test `hosttest/pointer_cross_test.cpp` | `OMNI_POINTER_CROSS_V1` |
| 9 | ninja `OmniEngine`, `make_link_command.py`, `tools/prep_s31c.py`, `build.py` | the **title** (`NativeEmutls.cpp`: strong `__emutls_get_address`, the jit2 emutls fix; `boot.log` opened `O_APPEND` so crash reports survive) | `OMNI_EMUTLS_ROUNDS_V1` |

`shell/s3-shell.diff` is the s3 shell change set (reference for what s3 changed in `engine/entry`).
`build/build-omni-native-s31.sh` and `build-omni-native-s31b.sh` are the two earlier steps of the same chain
(s3.1 = s3 + OS-001 + OS-002 + jit2 build 4; s3.1b = s3.1 + view-transition guard + yt + soak read).

## Host tests

| Test | Needs | Result on the build PC |
|---|---|---|
| `sec_connect_test.cpp` + `../child-src/omni-sec-connect.cpp` | clang/gcc, `-DOMNI_HUB_DIR='"/tmp/no-hub"'` | 17/17 (ASan+UBSan) |
| `vault_os002_test.cpp`, `-I patches/engine-entry`, `-lcrypto` | OpenSSL | 59/59 (51/51 as root: the chmod case is skipped) |
| `pointer_cross_test.cpp` | the patched `OmniBrowser.cpp`/`OmniFeaturesPanel.h` from step 8 | 41/41 |
| `test_emutls.cpp`, `test_crash.cpp` | `hosttest/include-jit2/` | emutls 100/100, crash PASS |

## What is missing (not reachable from the PC side)

- The **s3 base tree** itself (WebKit source + engine shell + build directory) and its GPU objects.
- `omni-jit-fix/apply_jitfix.py` and `omni-4k-vp9/patches/webcore-accel-safety-net.diff`, which step 1 calls.
- The s3 vault test suite archive (`omni-native-s3/s3-hosttest.tgz`) used in step 0.
- The PS5 Payload SDK and the security libraries (`OMNI_SECLIBS`).
- RL-01 as written in the audit (`../../webkit/precost-overlay-MISSING.txt`) is still open.

No binaries (ELF, PRX, eboot) and no build or console logs are kept here.
