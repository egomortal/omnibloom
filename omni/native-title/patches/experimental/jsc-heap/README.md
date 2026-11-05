# Experimental: JavaScriptCore without mini mode + `OMNI_HEAP_CAP_V1` (child engine)

> **Verdict: don't ship yet: warm-load stall.** Not part of any release build. Tested on the console on 2026-11-05 as
> candidate children s3.4e / s3.4f; the installed build keeps the stock child `7b810ea5…fd717c64`.

**Why:** with the JIT off, JavaScriptCore runs in its low-memory "mini VM mode" (`VM::isInMiniMode()` = `!useJIT`): every
GC is a full collection, sweeping is synchronous, and compiled bytecode is thrown away. YouTube's main thread is 57%
JavaScript, and mini mode makes that worse ([`REPORT.md`](REPORT.md)).

| Patch | Marker | Change |
|---|---|---|
| `tools/apply_nomini.py` → `patches-nomini/` | `OMNI_NO_MINI_MODE_V1` | mini mode only when `forceMiniVMMode` is set (5 one-line changes in Heap, Collector, InitializeThreading, FastMallocAlignedMemoryAllocator) |
| `tools/apply_heapcap.py` → `patches-heapcap/` | `OMNI_HEAP_CAP_V1` | applied on top: once the next-GC target passes 256 MB it becomes max(256 MB, 1.2x live). Needed because `WTF::memoryFootprint()` reads 0 on this console, so the normal growth rule (2x live) is unbounded |

Usage: `python3 tools/apply_nomini.py <tree>` then `python3 tools/apply_heapcap.py <tree>`; both are idempotent and
only touch `webkit/Source`. Rebuild the child with `SOURCE_DATE_EPOCH` pinned.

## Console results ([`VALIDATION.md`](VALIDATION.md))

| | stock child | s3.4e (no mini mode) | s3.4f (+ heap cap) |
|---|---|---|---|
| 20-min YouTube soak | PASS, WebProcess 589 / 462 MB | PASS, but **1305 / 1045 MB** | PASS, **597 / 450 MB** |
| Cold home / search / Shorts (first tile) | baseline | faster | **0.55-1.0 s faster** |
| Warm (repeat) YouTube home | first paint ~1.8 s (3 of 3) | 2 s parse stall in 1 of 2 | **~4.8 s or no paint in 8 s, 3 of 4 runs** |
| Quick gates, 4K60 GPU | PASS | | PASS (0.19% dropped) |

**Before it can ship:** find the warm-load stall (run the diagnostic child on the warm home and look for a blocking full
GC/sweep of the previous page's heap, or the code-cache path), then re-run the soak, browse loop and load gates.
An alternative to the cap is a real `memoryFootprint()` for the PS5, which would also wake WebKit's memory-pressure handler.
