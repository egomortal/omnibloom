# Omni ytprof: where YouTube's load time goes (2026-11-05, lock OMNI_YTPROF)

**End state:** the console is back on **s3.1c, verified** (eboot readback `03dcfe19…` = package `e8ac0c9d…`, child `7b810ea5…`, s3.1c `pages/`, omni-files `d1532d12…`, worker files, MC card 0.4.3; `raster-env.txt` restored byte-for-byte, no `ytprof.flag`, no JIT flag). Lock released (10:55Z). Test pages were renamed, not deleted: `pages.s34-tested-045409`, `pages.s34-tested-055122`. Nothing was installed for real.

## 1. Short answer
- **YouTube's main thread is 57% JavaScript.** With the JIT off, JS is 2.9–4.2 s of the first 8 s of each page. Next come bytecode compile (13%), painting (10%) and GC (8%). Style, layout, HTML/CSS parse, image decode and everything else together are about 12%.
- **Finding: with the JIT off, JavaScriptCore runs in "mini VM mode".** That is its low-memory mode for small devices: `VM::isInMiniMode()` is `!useJIT || forceMiniVMMode`. Every GC is a **full** collection (11–17 per page, 0 eden), sweeping is synchronous, the heap grows slowly, malloc runs in footprint mode, and compiled bytecode is thrown away. So warm pages recompile ~0.75 s of bytecode they already compiled.
- **Most effective fix: `OMNI_NO_MINI_MODE_V1`**, 5 one-line JSC changes in the child. Measured once (s3.4e candidate, JIT still off):
  - GC per page drops from 11–17 full collections to 1–3 (main-thread GC −65%);
  - warm/repeat-page compile drops by about 0.7 s (−90%);
  - first tile comes 0.4–0.8 s sooner on cold home, search and Shorts, thumbnails ~0.7 s sooner on search, and the Shorts video ~0.7 s sooner.
  - This is most of what turning the JIT on gives at load time, without RWX memory.
- **The JIT itself only cuts JS self time ~10% in the first 8 s** (baseline tier; DFG isn't built). Its big load-time gain was really leaving mini mode.
- **4K60 extras:** 1080p60 59.94 fps, 0.04% dropped. 1440p60 is 59.94 fps, 0.04% dropped while YouTube served 1440p. But YouTube dropped to a 30 fps 480p stream for 80 of the 120 s, so the whole-window median reads 39.98.

## 2. How it was measured
- **Diagnostic child `OMNI_YTPROF_V1`** (`child/omni-engine-child.elf`, sha `c5c7003e…`). It is built from exactly s3.4d's child tree; the same tree without the timers re-linked **byte-identical to 7b810ea5** (`child-base/`). The shell embeds `__DATE__`, so `SOURCE_DATE_EPOCH` is pinned.
  - Off unless `/data/omni/ytprof.flag` exists, checked once with a raw `open()`. The startup/bootstrap code (launcher-child, sec connect, OmniMain) is unchanged, and no header is changed.
  - Sink in `WTF/MainThread.cpp`: exclusive (self) main-thread time per category, so JS that forces a layout counts the layout as layout.
  - Hooks:
    - task = every RunLoop timer/dispatch, i.e. "other";
    - js = JSLock held, incl. the microtask drain;
    - compile = `generateUnlinkedCodeBlockImpl` / `generateUnlinkedFunctionCodeBlock`;
    - gc = `stopIfNecessarySlow` / `collectSync` / `acquireAccessSlow`;
    - sweep;
    - style = `Document::resolveStyle`;
    - layout = `LocalFrameViewLayoutContext::layout`;
    - paint = `LocalFrameView::paintContents`, plus raster (band replay);
    - decode = `ScalableImageDecoder::createFrameImageAtIndex`;
    - parse (HTML), cssparse;
    - rupd = `Page::updateRendering` own work.
  - Per main-frame commit it logs cumulative lines every 250 ms, timed from the navigation start (`DocumentLoadTiming::timeOrigin`), so they line up with YTTL's fcp/tile/thumbs.
- **`OMNI_YTPROF_V2`** (`child2/`, `61f56893…`) adds event lines: every GC start/end with scope, why and how long; GC requests; WebCore GC-controller calls; `deleteAllCode`; `releaseMemory`; the memory-pressure poll; and code-cache hits/misses for scripts ≥ 20 KB.
- **Runs:** s3.4d's eboot + pages/services (run_s34's install, so everything is backed up and restored), YTTL `ytload` (home cold, home warm, search, Shorts; 8 s each), 2 runs per mode, 4-minute settles. Runner: `run_ytprof.py` (wraps run_s34/run_jit2), analysis `analyze_ytprof.py`.
- **Overhead:** JIT off, warm-home rAF busy is 6.64 s against 6.46 s on s3.4d's stock child (+3%), and milestones are within run-to-run noise. Treat absolute JIT-on milestones with care: JIT-on pages had single paints of up to 1.7 s (warm-home rAF busy 6.8 s here vs 5.1 s on s3.4d's stock runs); the category split is the point here, and s3.4d's own JIT-on milestones stand.

## 3. The breakdown (s3.4d + diagnostic child; median of 2 runs; ms of main-thread self time in the first 8 s)
**JIT off (the default)**
| Page | fcp | first tile | all thumbs | video | busy | JS | compile | GC+sweep | style | layout | paint | decode | parse | rendering upd. | other |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Home cold | 3498 | 6472 | – | – | 4806 | 2909 | 816 | 290 | 161 | 43 | 175 | 0 | 242 | 31 | 140 |
| Home warm | 1015 | 3232 | 5406 | – | 7068 | 4071 | 746 | 639 | 338 | 238 | 689 | 15 | 68 | 110 | 153 |
| Search | 1254 | 4404 | 4823 | – | 6896 | 4166 | 807 | 517 | 149 | 110 | 746 | 5 | 177 | 53 | 168 |
| Shorts | 1296 | 5552 | – | 7100 | 6272 | 3146 | 1007 | 521 | 147 | 57 | 928 | 2 | 56 | 115 | 294 |
| **Share** | | | | | 25.0 s | **57%** | **13%** | **8%** | 3% | 2% | **10%** | 0% | 2% | 1% | 3% |

**JIT on**
| Page | fcp | first tile | all thumbs | video | busy | JS | compile | GC+sweep | style | layout | paint | decode | parse | rendering upd. | other |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Home cold | 3884 | 6339 | – | – | 4359 | 2557 | 820 | 94 | 158 | 96 | 219 | 0 | 249 | 4 | 160 |
| Home warm | 1164 | 3549 | 5427 | – | 5597 | 2986 | 124 | 182 | 245 | 163 | 1670 | 9 | 64 | 49 | 105 |
| Search | 1106 | 3814 | 4097 | – | 6781 | 4025 | 75 | 269 | 212 | 203 | 1693 | 4 | 47 | 167 | 86 |
| Shorts | 964 | 6046 | – | 7378 | 5924 | 3293 | 820 | 132 | 134 | 48 | 892 | 2 | 49 | 123 | 429 |
| **Share** | | | | | 22.7 s | 57% | 8% | 3% | 3% | 2% | **20%** | 0% | 2% | 2% | 3% |

- **Before the first tile** (JIT off; cumulative at the tile time): JS 1.4–2.2 s, compile 0.4–0.8 s, GC 0.17–0.30 s, paint 0.08–0.29 s, everything else < 0.25 s each. On cold home, 2.4 s of the 6.5 s is network before the commit (`navAgo`).
- **Image decode is not a cost** (≤ 20 ms per page on the main thread, none off it), and neither are style/layout (≤ 0.6 s together). Content-visibility, style-invalidation or lazy-decode work would buy little here.
- **Painting** is 25–90 ms per paint, plus rare 0.9–1.7 s single paints. With 4 raster threads (`raster-env.txt`, one run), band replay is only 174 ms against 2159 ms of recording. **The cost is WebCore's paint walk, not pixels**, so more raster threads don't help (answers census item W3). With the JIT on, pages repaint more often while loading, so paint doubles to ~20%. That is where paint-hold (C-003-R2) would pay.
- **Compared with earlier builds** (JIT off; fcp / first tile / thumbs):
  - Warm home: s3.1b 1200/2957/5134; s3.4d stock 1335/3413/5337; this run 1015/3232/5406.
  - Cold home: s3.1b 3455/5778; s3.4d 3656/6148; this run 3498/6472.
  - Search: s3.1b 1012/3616; s3.4d 2042/4351; this run 1254/4404.
  - Shorts: s3.1b 2723/6012/no video; s3.4d 1097/4927/video 6299; this run 1296/5552/video 7100.
  - Same picture within noise. Warm-home busy: s3.1b 6.52 s, s3.4d 6.46 s, here 6.64 s (rAF measure).

## 4. Why GC and compile are so big with the JIT off: mini VM mode (V2 events)
| Per YouTube page (JIT off) | mini mode (today) | no mini mode (s3.4e candidate) |
|---|---|---|
| GC collections | **11–17, all full** (gcstart: generational on, shouldDoFull=0, so full only because of mini mode) | 1–3 (1–2 eden + ≤ 1 full) |
| GC wall time (collector) | 0.57–1.19 s | 0.07–0.31 s |
| GC + sweep on the main thread | 0.29–0.64 s | 0.07–0.25 s |
| Bytecode compile, warm home / search | 0.75 / 0.81 s | 0.12 / 0.08 s |
| JS heap after GC | ≤ 73 MB | up to 120–210 MB |

- The 10.5 MB main YouTube script hits JSC's code cache on warm home, but its function bytecode was jettisoned (mini mode), so it is compiled again. On search it misses, because the cache's 16 MB working set was pruned by the other page's 2.6 MB script.
- The memory-pressure handler is blind on this console: `memoryFootprint()` reads 0 (FreeBSD sysctl), with thresholds 1014/1536 MB. It never fires, in either mode.

## 5. s3.4e candidate: `OMNI_NO_MINI_MODE_V1` (measured once, 2 runs, JIT off, s3.4d eboot)
- **Change:** 5 lines in `.cpp` files only (`tools/apply_nomini.py`). Mini mode now follows only `Options::forceMiniVMMode()` at these sites:
  - `Collector::decideCollectionScope` (always-full GC);
  - `proportionalHeapSize` (mini growth factor);
  - `Heap::shouldSweepSynchronously`;
  - `InitializeThreading` (`fastEnableMiniMode`);
  - the marked-block warm-up.
  - Unlinked-code jettisoning is header-inline (`VM.h`) and was left as is. Changing that header means a near-full rebuild.
- **Measured** (diagnostic build `child3/`, `be6418dc…`; medians; ms):

| Page | today: tile / thumbs / video | no-mini: tile / thumbs / video | JIT on: tile / thumbs / video |
|---|---|---|---|
| Home cold | 6472 | **5635** | 6339 |
| Home warm | 3232 / 5406 | 3646 / 6316 (one run had a 2 s HTML-parse stall; other run 3066 / 6255) | 3549 / 5427 |
| Search | 4404 / 4823 | **3852 / 4114** | 3814 / 4097 |
| Shorts | 5552 / – / 7100 | **5113 / – / 6423** | 6046 / – / 7378 |

  - Main-thread GC −65%, warm/search compile −90%. The freed time is spent on more of YouTube's own JS (the page gets further in 8 s).
  - No crash, no FATAL, no WebProcess restart in the 2 runs. The non-mini GC/heap path is the same one JIT-on mode has run in every soak.
- **Clean candidate child built, not installed:** `s3.4e-child/omni-engine-child.elf` `178a478b77be381db7e0ca227841be541b300a1a452a468f599f66a691a85a80` = the 7b810ea5 tree + `OMNI_NO_MINI_MODE_V1`, no timers. Pair it with s3.4d's eboot.
  - Before it ships: a 20-minute YouTube soak, the media/scroll gates, and a memory watch (JS heap now grows to ~200 MB on YouTube).

## 6. 4K60 extras on s3.4d (GPU path, stock child, `video-fps.log`, 120 s after a 40 s start)
| Gate | Source actually played | fps (median / min) | dropped | > 25 ms intervals | path |
|---|---|---|---|---|---|
| 4a 1080p60 (`AB9yQPOdghQ`, max 1080p60 VP9) | hd1080 1920x1080 the whole time | **59.94 / 57.94** | 3 / 7199 (0.04%) | 1 | gpu, 3840x2160 out, FIFO, shared device, all pictures in place, 0 ring copies |
| 4b 1440p60 (`AYDqLyXu2PA`, max 1440p60 VP9, 37 Mb/s) | hd1440 0–25 s and 105–165 s; YouTube switched to 480p (30 fps) at 25–105 s | 1440p seconds: **59.94 / 59.94**, 1 dropped of 2565; whole window 39.98 (the 30 fps 480p stretch) | 15 / 4827 (0.31%) | 1570 (all in the 480p stretch) | same |

- Both ran **inline**, not fullscreen: the `f` key at 8 s didn't take (YTTL `fullscreen:false`, rect 870x489). The video was scaled up to the 4K output.
- The quality drop to 480p was YouTube's ABR, not a decoder limit: 1440p decoded at 60/s both before and after. The 480p stretch presents ~40/s for 30 fps content: frames alternate 1 and 2 vsyncs, but each is shown 33 ms.

## 7. Recommendation (biggest cost first)
1. **JS (57%).** The only lever is executing YouTube's JS faster. The baseline JIT cuts JS self time only ~10% in the first 8 s, and DFG isn't built. **Do first: `OMNI_NO_MINI_MODE_V1`.**
   - It removes the mini-mode tax the interpreter pays (GC 8% → 3%, warm compile 0.75 → 0.1 s).
   - First tile is 0.4–0.8 s sooner and search thumbnails ~0.7 s sooner.
   - It is safe: no exec memory, the same GC path JIT-on mode already runs.
   - Estimated gain: **~1 s of main-thread time per warm page, 0.5–0.8 s to first content on cold/search/Shorts.**
2. **The JIT on by default:** once mini mode is gone it adds only ~10% JS. Keep it as the user's choice (RWX pool).
3. **Paint-hold (Astra's C-003-R2):**
   - paint is 10% with the JIT off and 20% with it on, made of many intermediate repaints during load plus rare 1–1.7 s paints;
   - fewer paints while loading would save an estimated 0.3–1 s;
   - more raster threads won't help (recording dominates).
4. **Cold compile (0.8 s per cold page and per Shorts):** a persistent bytecode cache. JSC already has `SourceProvider::cacheBytecode` hooks that WebCore doesn't use. Larger work; estimated −0.5 s on cold loads.
5. **Not worth it for load:** content-visibility, style invalidation, lazy/offscreen decode (≤ 0.6 s together, decode ≈ 0), GPU page drawing. The latter is still right for scrolling, as `omni-gpu-pages` says.

## 8. Files
- Builds (WSL, private overlays): `outputs/build-omni-ytprof.sh` (V1 + base check), `build-omni-ytprof2.sh` (V2), `build-omni-ytprof3.sh` (V2 + no-mini), `build-omni-ytprof-e.sh` (clean s3.4e child).
- Patches: `tools/apply_ytprof.py`, `apply_ytprof2.py`, `apply_nomini.py`; diffs in `patches-ytprof*/`, `patches-nomini/`; sink `src/`.
- Children: `child-base/` 7b810ea5, `child/` c5c7003e (V1), `child2/` 61f56893 (V2), `child3/` be6418dc (V2 + no-mini), `s3.4e-child/` 178a478b (fix only).
- Runner: `run_ytprof.py` (`all`, `e2`, `v2`, `restore`), `outputs/run-omni-ytprof.sh` + `ytprof-cmd.txt`, `run-omni-ytprof-ls.sh` → `end-state.txt`.
- Evidence:
  - `gates-4k/` (01 1080p60, 02 1440p60: video-fps/gpu logs);
  - `gates-load/` (01–02 JIT off, 03–04 JIT on);
  - `gates-e2/` (01 V2 mini, 02–03 no-mini, 04 raster threads 4);
  - `ytprof.json` per folder;
  - log `STATUS.md`, `run.log`.
- Reusable notes: `PLATFORM-NOTES-29.md` (for the platform-notes doc).
