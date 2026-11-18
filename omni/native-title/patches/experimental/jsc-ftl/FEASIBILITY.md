# Omni JSC: DFG and FTL tiers on the PS5 (feasibility study, 2026-11-17)

**Scope.** Read-only. Nothing was built, configured or installed, and the console was not touched. The only experiment
was one throwaway compiler preprocessor run in `/tmp/jscftl-probe`, which has since been deleted. Source evidence is
from `/home/builder/s3/webkit` (the base every child overlay sits on), tree A's upper `/home/builder/ogp-ls1b-up-0`
(the current rc6/ls1b child sources), `/home/builder/s1/build/CMakeCache.txt` and the Omni patch scripts in `outputs/`.

## Verdict

**Feasible with patches.** No hard blocker turned up. The things DFG and FTL need beyond the baseline JIT are:
- the same executable pool and the same `performJITMemcpy` write path, which V4 already redirects;
- worker threads, which baseline already uses;
- one signal-based mechanism, VM traps. On this OS it would misread the register context. A runtime option
  (`usePollingTraps=true`) avoids it, and a small patch fixes it properly.

Every other risk is about sizing: compiler-thread stacks, pool size, compile memory. The cost is a **full engine
rebuild**, about 3–4 h of machine time at -j4, against about 15 min for an incremental child. It also needs **four
small patches**, plus whatever compile fixes the first ever PlayStation DFG/FTL build turns up (expected to be few:
see §1).

---

## 1. Port support (CMake and WTF)

- **`Source/cmake/OptionsPlayStation.cmake:178-181`**:
  ```
  # Turn off JIT
  WEBKIT_OPTION_DEFAULT_PORT_VALUE(ENABLE_JIT PRIVATE OFF)
  WEBKIT_OPTION_DEFAULT_PORT_VALUE(ENABLE_FTL_JIT PRIVATE OFF)
  WEBKIT_OPTION_DEFAULT_PORT_VALUE(ENABLE_DFG_JIT PRIVATE OFF)
  ```
  - These are **only port defaults**, and the comment gives no technical reason. Sony's retail WebKit can't map
    executable memory, so the port ships with no JIT at all.
  - The same mechanism already lets Omni override `ENABLE_JIT=ON` with `-D` (CMake cache line 501). DFG and FTL can be
    overridden the same way, with no edit to the port file.
- **`Source/cmake/WebKitFeatures.cmake`**:
  - **Generic x86_64 defaults (`:112-118`):** JIT on, FTL on, C_LOOP off, SAMPLING_PROFILER on.
  - **Dependencies (`:364-367`):**
    - `ENABLE_DFG_JIT` depends on `ENABLE_JIT`;
    - `ENABLE_FTL_JIT` depends on `ENABLE_DFG_JIT`;
    - `ENABLE_WEBASSEMBLY_BBQJIT` and `_OMGJIT` depend on `ENABLE_FTL_JIT`. Their default is `ENABLE_FTL_DEFAULT`
      (`:316-317`), so **keep `-DENABLE_WEBASSEMBLY_BBQJIT=OFF -DENABLE_WEBASSEMBLY_OMGJIT=OFF` explicit**. The current
      configure command already does.
  - **Conflicts (`:354-357`):** JIT, SAMPLING_PROFILER and WEBASSEMBLY each conflict with C_LOOP. C_LOOP is already OFF
    and the other three are already ON, so nothing else flips.
- **`Source/WTF/wtf/PlatformEnable.h`** (the compile-time consequences):
  - **`:784-795`:** DFG is auto-enabled on x86_64 for `OS(FREEBSD)`. The toolchain defines `__FreeBSD__ 9`,
    `__PROSPERO__`, `__x86_64__` (checked with `omni-clang++ -dM -E`), so PS5 counts as FreeBSD x86_64, an upstream-supported DFG target.
  - **`:803-805`:** `ENABLE_CONCURRENT_JS` is already 1 (it follows JIT).
  - **`:817-824`:** `ENABLE_B3_JIT` = FTL. B3 and Air on x86_64 are the same backend GTK and WPE ship on Linux x86_64.
    It is pure C++ (no LLVM) and needs nothing from the OS.
  - **`:937-939`:** `ENABLE_SIGNAL_BASED_VM_TRAPS` turns **on automatically** with DFG, because `HAVE(MACHINE_CONTEXT)`
    is true for FreeBSD x86_64 (`PlatformHave.h:235`). This is the one new OS-facing feature; see §2b.
  - **`:798-800`:** `ENABLE_DFG_DOES_GC_VALIDATION` only applies with asserts on, which they aren't (Release).
  - **`PlatformEnablePlayStation.h:38-42`:** Omni's `ENABLE_MPROTECT_RX_TO_RWX 1` is unchanged. V3 already made its
    write window a no-op, and V4 returns before that window is reached.
- **Runtime consequence (`runtime/Options.cpp:653-654`):** `#if !ENABLE(SIGNAL_BASED_VM_TRAPS)` sets
  `Options::usePollingTraps() = true`. **Today's build forces polling traps. A DFG build stops forcing them.** That is
  why a runtime option (or patch P2) is mandatory.
- **What flips in `cmakeconfig.h`:** `ENABLE_DFG_JIT 0→1` and `ENABLE_FTL_JIT 0→1`. Nothing else changes; the derived
  macros (B3_JIT, SIGNAL_BASED_VM_TRAPS) come from the WTF headers.
- **Build config to copy:** tree A's cache differs from `configure-cmd.json` / s3 only in
  `ENABLE_ASYNC_SCROLLING:BOOL=ON` (diff of the `ENABLE_*`/`USE_*`/`OMNI_*` cache entries). The new build has to carry
  that option too, because the rc6 relink stops if it is missing.

## 2. Runtime mechanisms DFG and FTL need beyond baseline

| Mechanism | Needed by | Omni status | Evidence | Action |
|---|---|---|---|---|
| Concurrent compiler threads (`JITWorklist`, `ThreadType::Compiler`) | DFG and FTL plans | **Already in use.** Baseline plans run on the same `JITWorklist` threads (`jit/JITWorklist.cpp:49`, `numberOfBaselineCompilerThreads`), and passed the 20-min YouTube and 9-min JS soaks under V4 | `JITWorklistThread.cpp:82` | Cap the thread counts: `numberOfFTLCompilerThreads` defaults to up to 7 (`OptionsList.h:295`) |
| Compiler-thread stack | B3/Air and DFG phases on large functions (YouTube's player bundle) | **Risk.** Omni caps every default-stack thread at 512 KB (`ThreadingPOSIX.cpp:368-381`, `[omni-default-stack]`), and `stackSize()` gives a special size only to `ThreadType::JavaScript` (`Threading.cpp:113-115`). Upstream Linux compiler threads get 8 MB | | **P3:** 2 MB for `ThreadType::Compiler` on PlayStation |
| Signal-based VM traps | DFG/FTL termination and watchdog: inserts `hlt` into running optimized code and catches the fault | **Broken as is.** `jscSignalHandler` (`WTF/wtf/threads/Signals.cpp:503`) uses `registersFromUContext()` = `&ucontext->uc_mcontext` (`PlatformRegisters.h:81-90`). Omni already found that the PS5 puts `uc_mcontext` 48 bytes later than the SDK header (`ThreadingPOSIX.cpp:163-167`, the "+64" fix used for thread suspend), and `OmniCrash.h` says "The SDK ucontext layout does not match this firmware". The handler would read a garbage PC, return `NotHandled` (`VMTraps.cpp:215-226`) and fall back to the default action: **a silent SIGSEGV/SIGBUS death** (OmniCrash only hooks SIGILL/SIGABRT/SIGTRAP, `OmniCrash.h:116`) | `VMTraps.cpp:195-350` | **P1:** `JSC_usePollingTraps=true` (DFG/FTL then emit loop-head trap checks; small cost, no signals). **P2:** apply the same +64 to `registersFromUContext` on PlayStation, so a stray JSC fault handler is at least correct |
| Thread suspension (`Thread::suspend`, SIGUSR1) | VMTraps SignalSender (`sendMessage`), sampling profiler, conservative scan of other mutator threads | **Already works.** The suspend handler is Omni-patched (+64), it runs today for worker-thread stack scans, and the sampling profiler is already compiled in (`ENABLE_SAMPLING_PROFILER=1`). With polling traps the SignalSender is never created (`VMTraps.cpp:406-414`) | `ThreadingPOSIX.cpp:150-195, 594-640` | none |
| Concurrent GC | all tiers | Already on; DFG adds barrier code only, no new OS feature | `useConcurrentGC` | none |
| OSR entry / OSR exit | DFG, FTL | Pure code generation plus stack rewriting. Exit thunks are compiled lazily on the main thread through `LinkBuffer` (`dfg/DFGOSRExit.cpp:327`, `ftl/FTLOSRExitCompiler.cpp:644`), and exit sites are patched with `repatchJump`. Both go through `performJITMemcpy` (below). No mprotect, no signals | | none |
| Invalidation / jettison | DFG, FTL watchpoints | `replaceWithJump` / `replaceWithVMHalt` → `X86Assembler.h:6448, 6463` → `performJITMemcpy<jitMemcpyRepatch>` | | none |
| JIT memory | DFG/FTL code is larger per function. **OSR-exit thunks and FTL lazy slow paths are must-succeed** (`LinkBuffer` default effort; `FTLLazySlowPath.cpp:69`) | The pool is 64 MB (`OmniMain.cpp:196`, `JSC_jitMemoryReservationSize=67108864`). JSC keeps 25% back for must-succeed allocations (`ExecutableAllocator.cpp:126, 1214-1224`), so can-fail tier-ups stop at about 48 MB and fall back to baseline. Raises the tier-up threshold as the pool fills (`memoryPressureMultiplier`, `:1181-1193`). Upper bound `s_omniExecMaxBytes` = 256 MB (`OSAllocatorPlayStation.cpp:56`) | | **P1:** pool size from a file. Test 64 MB first, then 128 MB; jitprobe4 proved the V4 shm only at 64 MB. **P4:** log pool use |
| Executable allocator / W^X writes | every code write | **Covered by V4.** Every x86-64 write into the pool goes through `performJITMemcpy`. V4 sends it to `alias + (dst − pool)` (`apply_jit_v4.py`, step 3, in `ExecutableAllocator.h`). Write sites: `LinkBuffer.cpp:421, 431, 450, 454, 492` (copy and link), `X86Assembler.h:6448-6691` (`replaceWithHlt`/`Jump`/`AddressComputation`/`Load`, `revertJump*`, `fillNops` via `machineCodeCopy<jitMemcpyRepatch>`, `setPointer`/`setInt32`/`setInt8`/`setRel32`). DFG, FTL and B3 don't write to code directly: a grep of `dfg/ ftl/ b3/` finds no `memcpy`/`memset` into code (the hits are data buffers), and all their code goes through `LinkBuffer`. `startOfFixedWritableMemoryPool` is used only by V4 and by the Darwin-only `jitWriteThunk` path (`ExecutableAllocator.cpp:275-281`, under `HAVE(REMAP_JIT)`). A write that bypassed the alias would fault on the RX view, loudly, not silently | | none |
| `mprotect` / MAP_JIT-like APIs | — | DFG/FTL add none. The only `mprotect` is the `MPROTECT_RX_TO_RWX` window (`ExecutableAllocator.cpp:670`), and V3/V4 make it unreachable. Commit and decommit never change permissions (V3, `OSAllocatorPlayStation.cpp:177-222`) | | none |
| Instruction-cache coherence for the RW/RX alias | cross-thread patching | x86 snoops by physical address. jitprobe4 ran 5,000 write-through-RW / run-through-RX checks with 0 bad. Same model as upstream's RWX on Linux | rc6 README | none |
| WebAssembly fault handler | BBQ/OMG only | stays off (`useWasmFastMemory=false` on PlayStation, `Options.cpp:1043`; BBQ/OMG OFF) | | keep BBQ/OMG OFF |

**Omni patch assumptions that only hold for baseline:**
- `OmniMain.cpp:184-197` (tree A): hard-codes `JSC_useDFGJIT=false` and `JSC_useFTLJIT=false`. It runs **after**
  `jsc-env.txt` (`:169-182`), so that file can't turn the tiers on. Its log line also says "baseline + regexp". → P1.
- The 64 MB pool: fine for baseline, tight for DFG plus FTL (see the JIT memory row).
- `[omni-default-stack]` 512 KB: sized for baseline and the GC → P3.
- Nothing in V4 is tier-specific. The alias covers the whole pool, and the self-check and fallback to V3 are unchanged.

## 3. Rebuild size

- **Outside JavaScriptCore, there are zero `ENABLE(DFG_JIT|FTL_JIT|B3_JIT|SIGNAL_BASED_VM_TRAPS)` guards** in WebCore,
  WebKit or bmalloc. In WTF the only hit is `PlatformEnable.h`.
- **But it is still a full rebuild:**
  - `cmakeconfig.h` changes, and every translation unit includes it.
  - JSC headers that WebCore inlines change layout under `ENABLE(DFG_JIT)`. Examples: `runtime/VM.h`,
    `JSGlobalObject.h`, `bytecode/CodeBlock.h`, `JSCJSValue.h`; 237 JSC headers carry the guards.
  - So reusing WebCore objects would be an ODR/layout bug. **Don't try to keep them.**
- **Size:**
  - s3's last full build: **8,325 ninja steps, about 11 CPU-hours** (sum of the latest step durations in
    `s3/build/.ninja_log`; 8.0 of them are WebCore).
  - DFG/FTL/B3 add about 306 `Sources.txt` entries (`dfg/`, `ftl/`, `b3/`, `b3/air/`). They are compiled today as empty
    unified units, so the graph doesn't grow, but they become real code: roughly +1 CPU-hour (FTLLowerDFGToB3 and the
    B3 units are heavy).
- **Wall time:** about **3–4 h at -j4** (`OMNI_WEBCORE_JOBS=4`; 15 GB RAM and 16 threads in WSL; the WebCore unified units
  are the limit). An incremental child is about 15 min, so this is roughly 15× one child cycle.
- **Binary:** the child grows by an estimated 10–20 MB of code (`OmniEngine` unstripped is 1.44 GB today).

## 4. Safe build procedure

**Never touches** `/home/builder/s1`, `/home/builder/s3`, `ogp-*`, `launchc-*` or `outputs/*` (except the new
`outputs/omni-jit-ftl`). All mounts live in a **private mount namespace**, as in `build-omni-gpupages-launch-s1b-rc6.sh`,
so other sessions keep seeing the real s1.

| Path | What |
|---|---|
| `/home/builder/jscftl-src` | **snapshot** of tree A's sources: `rsync -a --exclude=/build /home/builder/ogp-ls1b-up-0/ /home/builder/jscftl-src/`. Taken while holding `/tmp/omni-gpupages-ls1b.lock` (`flock -n`, a few seconds) so tree A isn't mid-switch. About 10 MB, no whiteouts (checked: 0 char devices). Record `sha256` of the copied files |
| `/home/builder/jscftl-up-0`, `/home/builder/jscftl-work-0` | overlay upper and work: the P1–P4 edits land here |
| `/home/builder/jscftl-build` | **fresh** ext4 build dir, bind-mounted on `/home/builder/s1/build` inside the namespace (hides s3's build) |
| `/home/builder/jscftl-cws` | `cp -a /home/builder/ogp-ls1b-cws` (link-driver workspace: `child_build.py`, `make_link_command.py`, `child-src`) |
| `/home/builder/jscftl-link`, `/home/builder/jscftl-seclibs` | link output (LK) and seclibs copy. **Not** `ogp-ls1b-seclibs`: the relink recipe `rm -rf`s that one |
| `/tmp/omni-jscftl.lock` | own lock (`flock -n`) |
| `outputs/omni-jit-ftl/{steps.txt,logs/,out/child/}` | logs and the final child |

**Steps.** One outer script, run as root, `setsid nohup unshare -m --propagation private`, then the inner part with
`runuser -u builder`:

1. Mount the overlay:
   `mount -t overlay overlay -o lowerdir=/home/builder/jscftl-src:/home/builder/s3,upperdir=/home/builder/jscftl-up-0,workdir=/home/builder/jscftl-work-0 /home/builder/s1`
   then `mount --bind /home/builder/jscftl-build /home/builder/s1/build`, and write a marker file. The build keeps the
   `/home/builder/s1/...` paths, so `child_build.py` and `make_link_command.py` work unchanged.
2. Apply P1–P4 (anchored, idempotent appliers, in the same style as `apply_jit_v4.py`).
3. Configure:
   - **Command:** the `configure-cmd.json` argument list with `/home/builder` → `/home/builder`, plus:
     ```
     cmake -S /home/builder/s1/webkit -B /home/builder/s1/build -G Ninja  <all args of configure-cmd.json>  \
       -DENABLE_ASYNC_SCROLLING:BOOL=ON \
       -DENABLE_DFG_JIT:BOOL=ON -DENABLE_FTL_JIT:BOOL=ON \
       -DENABLE_WEBASSEMBLY_BBQJIT:BOOL=OFF -DENABLE_WEBASSEMBLY_OMGJIT:BOOL=OFF
     ```
     The last line already matches the JSON; keep it explicit.
   - **Gate:** diff the `ENABLE_|USE_|OMNI_` entries of the new `CMakeCache.txt` against
     `/home/builder/ogp-ls1b-up-0/build/CMakeCache.txt`. **Exactly** DFG_JIT and FTL_JIT may differ.
   - **Gate:** `cmakeconfig.h` has `ENABLE_DFG_JIT 1`, `ENABLE_FTL_JIT 1` and `ENABLE_ASYNC_SCROLLING 1`.
4. Build: `nice -n 19 ionice -c3 ninja -k 0 -C /home/builder/s1/build -j4 OmniEngine`.
   - **Gate:** the generated IPC hash equals the title's `da4a75622a0a473f`, as in the relink recipe. The title stays
     as it is; only the child changes.
5. Link exactly as `build-omni-gpupages-child-relink.sh` step 3 does, with `NC=/home/builder/jscftl-cws`,
   `LK=/home/builder/jscftl-link` and `SECL=/home/builder/jscftl-seclibs`:
   - `make_link_command.py`;
   - stage-1 objects (`ogp-s1-child`, `ogp_dri_nodrm_stubs_weak`, `ogp_payload_libc_weak`);
   - `s1_link_inputs.py` (reads `/home/builder/ogp`, read-only);
   - `patch_child_build.py` applied to the **copy**;
   - `child_build.py` with `OMNI_NET_LABEL=omni-jitftl`.
6. Gates:
   - weak-ref gate (`comm` with `cp2/archive-defs.txt`);
   - re-strip equal to the shipped child;
   - `elfguard.py` against the current rc6 child;
   - keys compared with `omni-launch/tools/keys-child.txt` (all equal);
   - new strings present: `OMNI_JSC_TIERS_V1` and `OMNI_JSC_JIT_V4`;
   - `llvm-nm` finds `JSC::DFG::Plan`, `JSC::FTL::` and `JSC::B3::` symbols, which today's child doesn't have.
   - The relink's symbol gate does **not** apply, because every TU changes.
7. Copy to `outputs/omni-jit-ftl/out/child/` (link on ext4 first; `cmp` after copying, as earlier builds learned).
   Then `umount` and exit the namespace.

**Disk:** the build dir is about 9.5 GB (s3/build is 8.3 GB) and the link dir about 3 GB (unstripped 1.4 GB, stripped
copy, map). Upper and snapshot are under 50 MB. **Total about 13–15 GB**; 791 GB are free.

**Install** (as for the other child variants; the title is unchanged because IPC is equal):
- back up `/data/omni/native/omni-engine-child.elf` as `*.before-jitftl`, then copy the new child in;
- the run script always restores the backup and removes the tier flags at the end;
- rollback = put the backup back.

## 5. Runtime switches (one child, three modes)

**P1, `OMNI_JSC_TIERS_V1`** in `engine/entry/OmniMain.cpp`, inside the existing JIT-on branch (`:188-197`). It replaces
the two hard-coded `false` lines:
```cpp
// OMNI_JSC_TIERS_V1: optimizing tiers are opt-in per flag file (read at child start).
bool dfg = !access("/data/omni/jsc-dfg.flag", F_OK);
bool ftl = dfg && !access("/data/omni/jsc-ftl.flag", F_OK);
setenv("JSC_useDFGJIT", dfg ? "true" : "false", 1);
setenv("JSC_useFTLJIT", ftl ? "true" : "false", 1);
setenv("JSC_usePollingTraps", "true", 1);            // never the signal/hlt path (ucontext layout, see P2)
setenv("JSC_numberOfDFGCompilerThreads", "1", 1);
setenv("JSC_numberOfFTLCompilerThreads", "1", 1);
// pool: /data/omni/jsc-jit-pool-mb.txt, 64..256 (default 64; s_omniExecMaxBytes caps at 256)
setenv("JSC_jitMemoryReservationSize", poolBytes, 1);
fprintf(stderr, "jit: on (baseline%s%s + regexp, pool %u MB, polling traps) (OMNI_JSC_TIERS_V1)\n", dfg ? " + DFG" : "", ftl ? " + FTL" : "", poolMb);
```
- **Modes:**
  - A = no flag (exactly rc6 behaviour);
  - B = `jsc-dfg.flag`;
  - C = `jsc-dfg.flag` + `jsc-ftl.flag`.
- `jsc-jit-off.flag` still turns everything off.
- `jsc-env.txt` keeps working for keys P1 doesn't set: tier-up thresholds (`thresholdForOptimizeAfterWarmUp`,
  `thresholdForFTLOptimizeAfterWarmUp`), `maximumOptimizationCandidateBytecodeCost`, `maximumFTLCandidateBytecodeCost`,
  `useOSREntryToDFG` / `useOSREntryToFTL`, `useConcurrentJIT`.
- The title needs no change for testing. A Settings row can come later, the way `apply_jit_default_on.py --title` did.

## 6. Console test plan

**Bench page `jsftl-bench.html`:**
- **Shape:** inline, no network, started by the staged harness (`window.omniStartMediaTest`, like
  `omni-jit-fix/js-soak.html`). It posts JSON results to `#out`.
- **Kernels** (Octane/JetStream-style, about 1–3 s each at baseline):
  - Richards (object/method dispatch);
  - DeltaBlue (polymorphic calls);
  - NavierStokes (Float64Array loops);
  - a raytracer (object allocation plus float math);
  - Splay (GC pressure);
  - crypto-style 32-bit int arithmetic;
  - regexp plus string building;
  - JSON round trip;
  - a closure/Map-heavy "tokenizer" over a 2 MB generated string (stands in for framework code).
- **Per kernel:**
  - first-iteration time (includes compile and tier-up);
  - median of 5 steady iterations;
  - a checksum, so a mis-optimization **fails** instead of just being fast.
- **Whole page:** a total and an `errors` count.

**Order:**
- each mode starts from a fresh child launch, because the flags are read at child start;
- interleave A B C C B A, each with 4-min settles, as the jitfix gates do;
- in every mode, run the bench page twice, then the existing YouTube load/YTTL gate and a 5-min `yt-soak.html` (1080p).
- About 1.5–2 h of console time.

**Measure:**
- kernel medians and first iterations, and the speed-up ratios B/A and C/A;
- YouTube: video-start time, played seconds, fps median/p10, stalls (existing gate output);
- the child's flexible-memory and `OMNI_MEMPRESSURE` lines;
- **P4** line every 10 s:
  - JIT pool bytes allocated / reserved;
  - DFG and FTL compiles finished / failed;
  - OSR exits;
  - jettisons and reoptimizations.
- Optional, one run only: `JSC_reportCompileTimes=true` through `jsc-env.txt` (noisy).

**Pass:** no `FATAL` line, no silent child death, checksums equal in all modes, YouTube passes the rc6 rules, and B/C are
not slower than A on the YouTube gate.

**Failure signs:**
- **Crash on the first tier-up:** death within seconds of the bench warm-up (around 1,000 executions = DFG threshold).
  - `FATAL ... SIGILL`/`SIGTRAP`: a JSC assert or `ud2`/`int3`.
  - Silent death: a fault in JIT code, a compiler-thread stack overflow (→ P3), or a JSC fault handler misreading the
    ucontext (→ P2; this shouldn't happen with polling traps).
- **OSR exit loops:** the exit or jettison counters keep climbing for a page that is already warm, and the steady
  medians in B/C are *slower* than A. Fix with lower `maximumOptimizationCandidateBytecodeCost`, or disable
  `useOSREntryToFTL`.
- **Pool exhaustion:** allocated bytes near 48 of 64 MB, and compile failures rising. A must-succeed failure is a
  `RELEASE_ASSERT` crash. Next step: the 128 MB pool, after checking that the V4 line still says "W^X" and not
  "using V3".
- **Memory:** child RSS or flexible memory jumps during FTL compiles (B3 on large functions), a
  `thread creation failed: name=...` / `omni thread failure flexible` line (`Threading.cpp:291-299`), or
  mempressure transitions that don't show up in mode A.
- **Hangs:** a page that can't be stopped (a busy loop in DFG code). Polling traps should prevent this; check that
  navigating away from a busy page still works.
- **Correctness:** checksum mismatches, or YouTube player errors only in B/C.

## 7. Patches expected

| # | Patch | Where | Need |
|---|---|---|---|
| P1 | `OMNI_JSC_TIERS_V1`: flag-file tier switches, `usePollingTraps=true`, 1+1 compiler threads, pool size from `jsc-jit-pool-mb.txt`, honest log line | `engine/entry/OmniMain.cpp` (child) | required |
| P2 | `OMNI_UCONTEXT_V1`: `registersFromUContext()` uses `(char*)ucontext + 64` on PlayStation, the same fix as `ThreadingPOSIX.cpp:163-167` | `WTF/wtf/PlatformRegisters.h` | required before ever allowing `usePollingTraps=false`; recommended now (defensive) |
| P3 | `OMNI_COMPILER_STACK_V1`: `ThreadType::Compiler` → 2 MB on PlayStation | `WTF/wtf/Threading.cpp:113` | strongly recommended (the 512 KB cap is untested with B3) |
| P4 | `OMNI_JIT_STATS_V1`: every 10 s, one stderr line with pool bytes and DFG/FTL compile, OSR-exit and jettison counters (atomic counters in `DFG::Plan` finalize, `CodeBlock::jettison`, `OSRExit` compile) | JSC + OmniMain timer | recommended (test only, inert without a flag) |
| P5 | CMake: `-DENABLE_DFG_JIT=ON -DENABLE_FTL_JIT=ON` on the command line (no `OptionsPlayStation.cmake` edit) | configure | required |
| P6 | Compile fixes the first PlayStation DFG/FTL build needs (unknown; likely few, because the FreeBSD/x86_64 paths in `MachineContext.h` already compile for the sampling profiler) | JSC | expect 0–2 incremental rounds (about 15–30 min each) |

**Effort:**
- **My work:** about 1 h for P1–P4 plus the build script.
- **Build:** one full build (3–4 h machine time, -j4) plus link (about 10 min), plus 0–2 incremental fix rounds.
- **Console:** about 2 h for the A/B/C comparison.
- **Expected gain is unmeasured:**
  - DFG typically beats baseline by 2–4× on hot compute kernels, and FTL adds more on long-running loops.
  - The YouTube main thread is 57% JS, and baseline only cut JS self time by about 10%. So DFG is the tier that could
    move it. That has to be measured; it can't be assumed.
