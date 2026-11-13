# Launch build rc6 (2026-11-13): JavaScript JIT on by default

rc6 is the launch build for v0.5.1: **title rc6** on the rc5 title, and **child rc6** on the rc5 child (`../rc5/README.md`).
Both also carry the opt-in GPU page drawing experiment ("layers", `../../experimental/gpu-pages/stage1/README.md`),
which stays **off** unless you create its flag file.

| | sha256 |
|---|---|
| title rc6 `eboot.bin` | `486c30b25b899544a271cce23fe2fa3b07b541ffaceab79f424bcc7f004e45e1` |
| child rc6 `omni-engine-child.elf` | `6b9d86e4ba6419bc7277a82667d53ea0228963d07019acfee255c71dc62fb3ff` |
| rollback | title rc5 `2e2a06a9…` + child rc5 `5b92d840…` |

## What was wrong

JavaScriptCore's JIT makes heavy sites much faster, but until now it was opt-in and labelled "faster, less safe".
The JIT pool (child rc5's `OMNI_JSC_JIT_V3`) was mapped read+write+execute once, so it could never race on the
permission changes that stall or fail on firmware 13.60. The cost was W^X: any stray write into the pool
would land in executable memory for the whole life of the page process.

## What rc6 changes

**Child** (`child/apply_jit_v4.py`, `OMNI_JSC_JIT_V4`): a W^X JIT pool with no runtime permission changes.
- The pool is one anonymous shared-memory object mapped twice: read+execute where JavaScriptCore runs code, and read+write at a second, unrelated address.
- Only JavaScriptCore's JIT-copy routine (`performJITMemcpy`) writes through the RW view. A write that bypasses it now faults instead of landing in executable memory.
- If the second mapping can't be made or fails its self-check, the pool falls back to V3 exactly.
- `/data/omni/jsc-jit-v3.flag` forces V3.

**Title and child** (`apply_jit_default_on.py`, `OMNI_JIT_DEFAULT_ON_V1`): the JIT is **on by default**.
- To turn it off, create `/data/omni/jsc-jit-off.flag`, or use Settings > "JavaScript JIT", which writes and removes that flag.
- The old opt-in `/data/omni/jsc-jit.flag` is no longer needed and never turns the JIT off.

**Title, Media downloads shortcut** (`OMNI_MEDIA_HEALTH_V2` in `../title/s34-entry/OmniMediaDownloads.h`):
- LT / double-bumper said "Media downloads unavailable" while the downloads worker was running. Omni's start-up check gave the worker's `/healthz` only 800 ms, and a worker paged down in the background can be slower than that.
- The check now waits up to 4 s per request and retries a slow or failed answer within the existing 30 s window.
- It still never launches a second worker unless the port refuses.

The child is built by `../../build/build-omni-gpupages-launch-s1b-rc6.sh` and the title by
`../../build/build-omni-gpupages-rc6-title.sh` (child first: the title script checks the child's stage-1 sources).

## Console results

- **JIT V4 against V3** (2026-11-11): same speed on six sites.
  - 20-minute YouTube soak: 0 stalls.
  - 9-minute JavaScript soak: 0 errors.
  - A standalone probe made 5,000 random write-through-RW / run-through-RX checks: 5,000 ok, 0 bad.
- **rc6 as the launch build** (2026-11-12): installed and verified by readback; played YouTube 4K with the JIT on.
- **rc6 with and without layers** (2026-11-13), back-to-back on the same console, about 4.5 minutes of HDR YouTube each (1080p to 1440p):

| Run | Video started | Played | Frame rate (median / 10th percentile) | HDR |
|---|---|---|---|---|
| Layers off | 14.35 s | 274 s of 286 s | 59.94 / 59.94 | ok |
| Layers on | 14.47 s | 251 s of 286 s | 59.94 / 59.94 | ok |
| Layers on | 12.88 s | 276 s of 287 s | 59.94 / 59.94 | ok |

All three passed. "Played" stops when the test ends, not when the video does.

## Rollback

To go back to rc5, put the rc5 pair back: title `eboot.bin` and child `/data/omni/native/omni-engine-child.elf`.
To keep rc6 but run without the JIT, create `/data/omni/jsc-jit-off.flag`.
