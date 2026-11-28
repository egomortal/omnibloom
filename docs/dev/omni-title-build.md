# How the Omni title is built from patches

Omni is not a fork that lives in this repository. It is built in three steps:

1. Start from a **base engine tree**: WebKit plus Omni's engine shell. It is **not** in this repository
   (`omni/native-title/patches/README.md`, "What is missing").
2. Apply **patch scripts** (`apply_*.py`) and copy in Omni's own files. Each change carries an `OMNI_*_V1` marker.
3. Compile, link and package with the recipes in `omni/native-title/` and the scripts in
   `omni/native-title/patches/build/`.

This page explains each step and how to write a new patch.

## What gets built

| Output | Recipe | What it is |
|---|---|---|
| Title `PPSA99732` (`eboot.bin`) | `omni/native-title/build.py` | the WebKit UI process |
| `/data/omni/native/omni-engine-child.elf` | `omni/native-title/child_build.py` | the web and network processes, started through the ELF loader on port 9021 |

`build.py` describes its own steps in its docstring:

1. Compile the native sources.
2. Link pass 1.
3. Generate the import check (`tools/gen_import_check.py`) from pass 1.
4. Link pass 2, then check the exports and the undefined symbols.
5. Link with `ps5-native-tool`.
6. Run the layout guard (`tools/check_native_layout.py`). The build refuses to package if it fails.
7. Sign and package to `out/PPSA99732`.

`make_link_command.py` asks ninja for the engine's link command (`ninja -t commands OmniEngine`) and saves it as
`link-command.json`. Both recipes reuse that command.

## Where the patches live

| Folder | What is in it |
|---|---|
| `omni/native-title/tools/` | the oldest patches (s3.1 chain): `apply_s31_pna.py`, `apply_viewtransition.py`, `apply_yt.py`, ... |
| `omni/native-title/patches/engine-entry/` | whole files copied over `<tree>/engine/entry/` |
| `omni/native-title/patches/s34/` | the s3.4 set: 4K60 video, the CLEAN4 entry files, the three dark-mode patches, host tests |
| `omni/native-title/patches/launch/` | **the release build** (read `launch/README.md`); `rc5/` adds the YouTube guard, `rc6/` is v0.5.1 (JIT on by default) |
| `omni/native-title/patches/experimental/` | opt-in work: GPU page drawing, HDR, JSC heap, software video |
| `omni/native-title/patches/build/` | the shell scripts that apply everything in order and build |

`omni/native-title/patches/README.md` lists each set, its order and its markers. Start there.

## The build scripts

Each script in `omni/native-title/patches/build/` is one complete, ordered recipe. The newest pair (v0.5.1, rc6 plus
opt-in GPU page drawing) is:

1. Child: `build-omni-gpupages-launch-s1b-rc6.sh`
2. Title: `build-omni-gpupages-rc6-title.sh`

(as `omni/native-title/patches/experimental/gpu-pages/stage1/README.md`, "Build", says).

What `build-omni-gpupages-rc6-title.sh` does, in order:

1. **Prepare the sources (state T).** In a fresh overlay it applies the base patches. Each one stops the build on
   failure. The order is: `apply_s3_webkit`, `apply_s31_pna`, the `engine-entry` copy, `apply_viewtransition`,
   `apply_yt`, `apply_soak_read`, `apply_pointer_cross`, `apply_s34_entry`, the three dark patches, and the
   stats diff. Then it applies the launch title units, the GPU page patches and the rc6 units (`OmniYtGuard.h`,
   `apply_jit_default_on.py --title`).
2. **Prove the sources.** `ident.py` compares the tree with the recorded launch tree ("PROOF 1"), and
   `OmniBrowser.cpp` must have a known hash.
3. **Switch and compile.** `switch_state.py` switches the build tree to state T (see below), then `ninja OmniEngine`.
   The hash of WebKit's generated IPC code must match the child's. If it doesn't, the title and child would not
   understand each other.
4. **Link and run the gates.** `make_link_command.py`, `prep_launch.py`, `patch_title_build.py`, `build.py`, then
   the import gate, the layout check and the text gates.
5. **Copy out and switch back.** It copies the package out, compares every file's SHA-256, and switches the build
   tree back to the child's state.

Paths in the scripts are placeholders (`/path/to/workspace`, `/home/builder`). Point them at your own trees.

## The import gate

The PS5 refuses to start a title that imports a function the console does not have. A missing import shows up at
start as `[import] missing <name>`, and the title exits.

The **import gate** catches this at build time (`build-omni-gpupages-rc6-title.sh`, step 3):

```sh
llvm-nm -D --undefined-only new/llvm-pie.elf    | sort -u > imports-new.txt
llvm-nm -D --undefined-only launch/llvm-pie.elf | sort -u > imports-launch.txt
comm -23 imports-new.txt imports-launch.txt > imports-added.txt
# only sceKernelUsleep and sceVideoOutIsFlipPending may be new; anything else: "IMPORT GATE FAILED", exit 1
```

In words: the new title may import only what the last console-proven title imported, plus an explicit allow-list.
The script's header explains why. A title once exited at start because it imported six EGL/GL functions directly.

Other variants:

- `build-omni-gpupages-ls1b-titlefix.sh` allows no new imports at all.
- `build-omni-ytguard-title.sh` requires the import list to be identical (`cmp`).

There is also a run-time check. `omni/native-title/tools/gen_import_check.py` generates `import_check.cpp`,
which logs every missing import to `boot.log` at start.

**If you add a call to a new system function**, you must add it to the gate's allow-list on purpose. Say why
in the commit, and test the title on a console.

## The overlay states A, T and C

The scripts never edit the base tree. They stack writable overlays on top of the read-only base:

| State | What it is |
|---|---|
| **A** | the shared build tree, which holds the compiled objects (`/home/builder/s1` in the scripts) |
| **T** | a source-only overlay with the **title's** sources |
| **C** | the **child's** sources (C(rc4) in the rc6 scripts) |

Title and child need slightly different sources but share one expensive build directory.
`omni/native-title/patches/experimental/gpu-pages/stage1/tools/switch_state.py` makes A's sources equal to
T's or C's:

```text
switch_state.py UPPER_A UPPER_S MERGED_A MERGED_S LABEL
```

- It looks at every path changed in either overlay, skipping `build/`, dotfiles and `link-command.json`.
- Each such path is copied so that it is byte-identical in A, or removed from A if S doesn't have it.
- It prints `RESULT n copied, n removed, n already equal; ... n differ` and exits 1 if anything still differs.

The title script switches A to T before it compiles, and back to C at the end. After the switch back, A still
holds state-T objects, so the next child build recompiles them. `ident.py` (same folder) proves which sources a
build used.

## The marker convention

Every change to the engine tree carries a **marker**: a unique string written into the changed code as a
comment, for example `// OMNI_DARK_STANDARD_V1`.

- **Name:** `OMNI_<FEATURE>_V<n>`, in capitals. Change the meaning, change the number (`OMNI_MEDIA_HEALTH_V2`
  replaced the 800 ms health check with 4000 ms).
- **Idempotent:** if the marker is already in the file, the script prints `already` (or `already applied`) and
  exits 0. Running a script twice is safe.
- **Anchored:** the script finds the code to change by an exact text **anchor**. If the anchor matches
  anything other than exactly once, it stops with an error and changes nothing.
- **Line endings kept:** scripts read bytes, note CRLF or LF, and write back the same.
- **One way to fail:** `sys.exit("<message>")` prints to stderr and exits 1. The build scripts stop on any
  non-zero exit, and some also check the log for a line starting with `applied`.
- **Text gates:** some build scripts check that a marker string is in the final binary
  (`grep -a OMNI_YTGUARD_V1 llvm-pie.elf`). They also check that test-only strings are absent.

`omni/native-title/patches/README.md` states the rule: "Every step is idempotent (each patch carries a marker and
refuses an anchor that does not match exactly once)."

There is **no shared helper module**. Every script carries its own few lines. Two known exceptions in
`patches/experimental/gpu-pages/stage1/tools/`: `apply_media_health_fix.py` and `apply_yttl_scroll.py` have no marker
check, so a second run fails with "anchor count 0" instead of printing "already". Run them once, on a fresh tree.

## How to write a new patch

Use `omni/native-title/tools/apply_viewtransition.py` as the model. It is short and complete.

```python
#!/usr/bin/env python3
"""OMNI_MY_FEATURE_V1: what it changes and why (one paragraph). Idempotent; each anchor must match once."""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniBrowser.cpp'
raw = p.read_bytes().decode('utf-8')
crlf = '\r\n' in raw
s = raw.replace('\r\n', '\n')
if 'OMNI_MY_FEATURE_V1' in s:
    print('already'); sys.exit(0)

def sub(old, new):
    global s
    n = s.count(old)
    if n != 1:
        sys.exit(f'anchor matched {n} times: {old[:80]!r}')
    s = s.replace(old, new)

sub('    oldLine();\n', '    newLine(); // OMNI_MY_FEATURE_V1\n')

out = s.replace('\n', '\r\n') if crlf else s
p.write_bytes(out.encode('utf-8'))
print('applied OMNI_MY_FEATURE_V1')
```

Checklist:

1. **Pick anchors that are unique and stable.** Prefer a whole line or two over a single word.
2. **Write the marker into every changed spot** that a later patch might need to find.
3. **Say the order in the docstring** if your patch builds on another marker (for example, "run after the patch
   that adds `OMNI_DARK_STANDARD_V1`"). If it needs that marker, check for it and stop when it is missing.
4. **Run it twice** on a copy of the tree. The second run must print `already`.
5. **Add a host test** if the logic can run off the console. Examples: `omni/native-title/hosttest/`,
   `omni/native-title/patches/s34/hosttest/` (node tests for dark mode),
   `omni/native-title/patches/launch/rc5/tests/` (node tests for the YouTube guard).
6. **Add it to a build script.** Copy the newest `patches/build/*.sh`, add your step in order, and keep every gate.
7. **List it in the README** of its patch set, with the marker, the script and what it does.

## Patches coming in v0.5.2

The next title (v0.5.2) adds these markers. Their scripts are not in this repository yet and will be added
with the release. Each one follows the convention above.

| Marker | Changes | Summary |
|---|---|---|
| `OMNI_L2_CHORDS_V1` | `OmniBrowser.cpp`, `OmniBrowserSettings.h` | L2+Square copy, L2+Triangle paste, L2+Cross Quick bar |
| `OMNI_MEDIA_SWITCH_V1` | `OmniMediaDownloadsHooks.inc` | when the worker is ready, open Media downloads even if the page URL changed |
| `OMNI_DARK_CHOICE_V1` | `OmniDarkPages.h`, `OmniFeatures3.h` | one Dark mode setting: Off / Natural / Forced |
| `OMNI_QA_CUSTOM_V1` | `OmniMqQuickAccess.h`, `OmniBrowserSettings.h` | the user picks the quick-access buttons (up to 6) |
| `OMNI_SETTINGS_CREATE_V1` | `OmniBrowser.cpp` | the Create button opens and closes Browser settings |
| `OMNI_ADDON_CAP_40_V1` | `OmniAddonsCore.h` | the add-on limit goes from 24 to 40 |
| `OMNI_FIRST_RUN_V1` | `OmniMain.cpp` | a fresh install starts the browser without the placeholder files |
| `OMNI_MEDIA_DIAG_V1` | `OmniMediaDownloads.h`, `OmniMediaDownloadsHooks.inc`, `OmniNativeLinkReview.inc` | logs each Media downloads step to `/data/omni/media-downloads.log` |

Order rules: the dark/quick-access patch runs after `OMNI_L2_CHORDS_V1`. `OMNI_MEDIA_DIAG_V1` runs after
`OMNI_MEDIA_HEALTH_V2` and `OMNI_MEDIA_SWITCH_V1`.

## Host tests (no console needed)

| Test | Run | Source |
|---|---|---|
| secure connect | clang/gcc with `-DOMNI_HUB_DIR='"/tmp/no-hub"'` | `omni/native-title/hosttest/sec_connect_test.cpp` |
| vault | `-lcrypto` | `omni/native-title/hosttest/vault_os002_test.cpp` |
| pointer cross | the patched sources | `omni/native-title/hosttest/pointer_cross_test.cpp` |
| dark mode | `node <test> <OmniDarkPages.h>` | `omni/native-title/patches/s34/hosttest/dark_*_test.js` |
| YouTube guard | `node <test>` | `omni/native-title/patches/launch/rc5/tests/guard_*_test.js` |

The patch set READMEs list the expected counts (for example 41/41 for pointer cross).
