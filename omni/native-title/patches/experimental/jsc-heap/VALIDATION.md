# s3.4e validation (no JSC mini mode, JIT off): soak, memory, regressions (2026-11-05, lock OMNI_S34E)

## Verdict: DON'T SHIP YET
- **s3.4e (`178a478b`) as built: needs a cap.** The 20-minute YouTube soak passes, but the WebProcess grows to **1.3 GB** (stock: 0.59 GB). The console then pages other processes out: the NetworkProcess drops from 247 to 48 MB resident, the spare from 213 to 32 MB.
- **s3.4f (`f379bffc`) = s3.4e + `OMNI_HEAP_CAP_V1` (built and tested): the memory problem is fixed.** In the soak, memory now matches stock: 597 MB peak and 450 MB at the end, against 589/462 MB. All gates pass. Cold home, search and Shorts load **0.55–1.0 s faster**.
- **But both builds without mini mode stall on the warm (repeat) YouTube home.**
  - s3.4f: first paint at about 4.8 s, or nothing at all within 8 s, in **3 of 4 runs**.
  - Stock: about 1.8 s in 3 of 3 runs. The ytprof agent's no-mini runs also showed a 2 s HTML-parse stall in 1 of 2.
  - So warm home got 1.2 s *slower* to the first tile, and up to 3+ s slower to the first paint.
- Diagnose this before shipping: run the V2 diagnostic child on warm home and look for a blocking full GC/sweep of the previous page's heap, or the code-cache path. Only then call s3.4f safe.

## Root cause of the memory growth (and why the cap is needed)
- `USE_MEMORY_FOOTPRINT_API` is 1 on this port, and `WTF::memoryFootprint()` reads 0 (FreeBSD sysctl). Two things follow:
  - `Heap::proportionalHeapSize()` always takes the "small heap" branch. The next-GC target is therefore always **2x the live heap**, with no upper bound.
  - `overCriticalMemoryThreshold()` (`percentAvailableMemoryInUse() = 0`) never trips.
- Mini mode (1.2x growth) used to hide this. With mini mode removed, nothing limits growth. The memory-pressure handler is blind for the same reason.
- **`OMNI_HEAP_CAP_V1`** (`tools/apply_heapcap.py`, diff in `patches-heapcap/Heap.cpp.diff`) changes Heap.cpp only, in 2 edits.
  - Once the 2x target passes **256 MB**, the target becomes max(256 MB, 1.2x live), which is mini-mode growth.
  - Smaller heaps keep the fast generational behaviour.
  - Eden/full scope, sweeping and malloc are unchanged.
- Built like s3.4e (`build-omni-s34f.sh`, private overlay, `SOURCE_DATE_EPOCH=1793793600`, startup/bootstrap untouched). Output: `s3.4f-child/omni-engine-child.elf` `f379bffc88cca4e44aa402231ea9574d28eafdba97b1cf7f88668bc56649f3ce`.
- An alternative is to fix `memoryFootprint()` for the PS5 (rusage or a sceKernel call). That would make the growth rule and the pressure handler work on their own. It is a larger change and not tried here.

## 1. Soaks (s3.4d eboot `ca22b2e4`, JIT off)
| | 20-min YouTube soak | WebProcess MB: peak / end (per-minute max range) | 9-min JS soak (rounds, median/p95 ms) | WebProcess MB peak |
|---|---|---|---|---|
| stock 7b810ea5 | PASS, played 1187 s, 0 stalls | **589 / 462** (401–589, flat) | PASS 4286, 127/147 | 808 |
| s3.4e 178a478b | PASS, played 1187 s, 0 stalls (some hd720/1080 samples) | **1305 / 1045** (458 → 1305 by min 10, plateau ~1050) | PASS 4245, 129/149 | 810 |
| s3.4f f379bffc | PASS, played 1188 s, 0 stalls, longest stall 0 ms | **597 / 450** (458–597, flat) | PASS 4332, 126/146 | 817 |
- Memory here is pldmgr's per-process `memory` (MB), sampled every 5 s. An idle spare engine process reads 213 MB, which is the mapped 165 MB engine plus libraries. So read the 448 MiB budget against the figures **above** that baseline.
- The JS soak grows to about 800 MB in **all three**, stock included. It is not a mini-mode effect.

## 2. Browse loop (18 heavy pages x 2 passes, 20 s each, one tab)
- Pages:
  - YouTube home, search x2, watch x2, Shorts and home;
  - cnn, bbc/news, theguardian, theverge, nytimes;
  - amazon, ebay, bestbuy;
  - en.wikipedia "United States", github, reddit.

| child | WebProcess per-minute max (MB) | peak |
|---|---|---|
| stock 7b810ea5 | 425–654 | **654** |
| s3.4e | 730–977 | **977** |
| s3.4f | 564–859 | **859** |
- **No build keeps growing:** pass 2 is not above pass 1.
- s3.4f still sits about 200 MB above stock while browsing. Heaps under the cap still grow at 2x, and malloc runs without mini mode. If parity is wanted, lower the cap (e.g. 192 MB) or put back `fastEnableMiniMode` for malloc only.
- **Pre-existing, not caused by this change:** reddit.com crashes the WebProcess on **every** build, stock included (SIGBUS, si_code 3, at `0x8000b283e` in a system library, outside the engine image, 2 of 2 visits). Omni recovers and goes on. Worth its own ticket.

## 3. Quick regressions (s3.4f, JIT off)
- **PASS:** feature (js timing 1100 ms total), scroll, media (HLS hls.js fullscreen 40 s), portblock, Shorts.
- **Watch** (aqz-KE-bpKQ, 90 s): first run FAIL, rerun PASS.
  - The FAIL: playback reached 60.07 s, then readyState 2 for about 12 s, then YouTube re-created the player (currentTime 0 at the end).
  - The rerun PASS reached 82.8 s. Stock PASS: 76.7 s.
  - An accidental 340 s inline watch on s3.4f (step 17, see Files) played to 326 s with no stall.
  - The same player reset hit **stock's** 4K run tonight, so this is a YouTube/network flake, not s3.4f.
- **4K60 fullscreen, GPU path, 300 s window: PASS.**
  - s3.4f: median 59.94 fps, p10 59.83, dropped 36/18972 (**0.19%**), 3840x2160 FIFO, shared device, all pictures in place, 0 ring copies, fullscreen.
  - One 1-second window read 6.9 fps, with 58 intervals over 25 ms. This morning's s3.4d stock run had 0.169% dropped, 14 intervals over 25 ms and a 32.9 fps minimum.
  - Tonight's stock 4K rerun is void: the YouTube player reset at about 56 s.

## 4. YouTube load (ytload, 8 s per page; medians; ms; s3.4d eboot)
| page | stock 7b810ea5 (n=3): fcp / tile / thumbs / video | s3.4f (n=4): fcp / tile / thumbs / video | delta (tile) |
|---|---|---|---|
| home cold | 3997 / 6475 / – / – | 3338 / 5661 / 7002 / – | **−0.8 s** |
| home warm | 1833 / 3652 / 5595 / – | **4761 / 4823 / 6668** / – | **+1.2 s (stall)** |
| search | 1118 / 3964 / 4370 / – | 1724 / 3386 / 3791 / – | −0.6 s (thumbs −0.6 s) |
| Shorts | 2488 / 5418 / – / 6840 | 1162 / 4863 / – / 5832 | −0.55 s (video −1.0 s) |
- **Warm home per run:**
  - s3.4f: no paint in 8 s (the response ended at 2.6 s and DCL never came); then 1291/2746; then 4788/4867; then 4761/4823.
  - Stock: 1687/3449, 1833/3652, 1945/3689.
- s3.4e has no load runs tonight. The ytprof agent's diagnostic no-mini child got cold 5635, search 3852/4114, Shorts 5113/6423, and warm 3646/6316 (one 2 s stall).

## End state
- **s3.1c restored and verified (18:17Z):**
  - eboot readback `03dcfe19…` (package `e8ac0c9d…`), child `7b810ea5…`;
  - omni-files `d1532d12…`, worker files and the MC card/receipt are back (each read back);
  - s3.1c `pages/` is back, and the tested s3.4d pages are kept as `pages.s34-tested-131259`;
  - no ytprof, JIT, yt-timeline, GPU or self-test flags are set, and `raster-env.txt` and `jsc-env.txt` were never touched.
- `run-omni-s34e-ls.sh` gives `s34e-end-state.txt`: `s3.1c`.
- Bloom Core and Master Control were **not running when the pass started**, so they were left stopped as found (autoload starts them at the next boot).
- The lock OMNI_S34E was released at 18:17:33Z. Another owner (OMNI_NET) holds it now.

## Files (outputs/omni-ytprof/)
- Runner: `run_s34e.py`, which wraps run_ytprof → run_s34 → run_jit2; none of those were edited.
  - Launcher: `../run-omni-s34e.sh` + `s34e-cmd.txt`. Stop-between-steps: `../run-omni-s34e-stop.sh`.
  - Analysis: `analyze_s34e.py`. Log: `S34E-STATUS.md`, `s34e-run.log`.
- Evidence: `gates-s34e/NN-<child>-<test>/`, holding `gates.json`, `mem.json` (every 5 s sample, roles from the process logs) and the process logs.
  - Step 17 is invalid as a load run. After the 4K step, `r2.yt_cfg` still held the 4K config, so it ran a 340 s watch. The runner now resets it before every step.
- s3.4f: `tools/apply_heapcap.py`, `patches-heapcap/`, `../build-omni-s34f.sh`, `build-f-steps.txt`, `checks-f.txt`, `s3.4f-child/`.
- Source look-ups: `s34e-grep.txt` and `s34e-grep2.txt` (Heap growth rule, `USE_MEMORY_FOOTPRINT_API`, `OMNI_JSC_ENV_V1` in OmniMain.cpp).
