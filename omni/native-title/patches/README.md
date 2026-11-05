# Omni native title: s3.1c patch set

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
