# Omnibloom on the PS5: the hard problems, and what we did about them

*An engineering deep-dive for people porting browsers, media stacks or GPU code to a jailbroken PS5, and for
Omnibloom users who want to know why things behave the way they do. Written November 2026.*

Omnibloom's main app, **Omni**, is a WebKit browser. On the console it runs as a normal app process (the
**title**, which owns the screen, the controller and the video service) plus engine processes started beside it:
the **page process** (WebKit's web process, one per tab) and the **network process**. On top of that it has
hardware video decode for YouTube (VP9, up to 4K and HDR), optional GPU page drawing ("layers", Mesa Zink on
RADV), a built-in uBlock engine, a JavaScript JIT, and helper programs (Master Control, the hub, and our own engine
starter).

This page collects every significant problem from the v0.5.x cycle: what users saw, the cause, how we found it,
the change (each carries a marker name such as `OMNI_STACK_MIN_2M_V1`, findable in the patch tools), and where it
stands. Most of them were not where we first looked.

**Status (November 21, 2026):** the console-hang problem with layers on is understood and mostly fixed in test
builds. 4K HDR YouTube with layers on now plays. Two problems are still open (a 4K quality switch that can be
refused, and an experimental memory saving that stalls video), and YouTube's token checks still cause occasional
reloads. Layers stay **off by default** in releases.

Earlier GPU-drawing problems (the `dladdr` helper, missing animation frames, the shader cache, pacing, read-back,
GPU memory budget) are covered in [GPU page drawing ("layers") on the PS5](gpu-page-layers-ps5.md) and are only
summarised here.
---

## The short version

1. **The kernel has one shared pool of CPU page tables (8,192 of them), and every app and payload draws from it.**
   When it runs low, the whole console hangs. Omni was spending up to ~1,900 of them; the console itself uses
   ~5,100 at idle. Finding what costs a page table, and what gives one back, was most of November.
2. **Two parts of the title submitted GPU work without talking to each other.** With layers on that hung the
   console about 2 runs in 10. One lock fixed it (20 of 20 runs clean afterwards).
3. **The payload loader kept 240 MB after starting each engine**, and a spare engine was started right on top of
   the page-load peak. Our own small starter and no standing spare cut the low-memory warnings from 15 of 16
   launches to 0 of 15 with layers off.
4. **Master Control crashed the console at boot** by cancelling a Bluetooth inquiry on the chip the system shares.
5. **The page process ran out of memory with 8 GB free**: a frame read-back queue had no upper bound.
6. **Several WebKit compositor paths the PlayStation port never used before** crashed once layers turned them on.
7. **Scrolling with layers went from 8 fps to 52 fps** after we found async scrolling had never actually been on.
8. **YouTube stopped every video at one minute.** The cause was the PS5's hard-link call, which reports success
   and creates nothing, so Omni's HTTP cache never stored large files.
9. **YouTube rejects a share of the tokens Omni's player mints.** We can't change YouTube's decision; we make the
   recovery quick and quiet, and we now keep a record of what works.
10. **The "replay" users saw on YouTube** was mostly a 32 MiB media buffer limit sized for 1080p.
11. **uBlock failed closed on fresh installs** (missing rule files) and costs real start time on YouTube.
12. **The JIT needs a write alias**, and the faster tiers (DFG/FTL) needed two small port fixes.
13. **The title cannot use non-blocking sockets.** `O_NONBLOCK` fails with `EACCES` (errno 13).
14. **10-bit HDR** had a colour mismatch in our GPU check and a 17 ms per-frame present cost; both are fixed.

---

## 1. The shared page-table pool (console hangs)

*The earlier measurements and ruled-out ideas are in [4K video memory and kernel page tables on PS5](ps5-4k-memory-page-tables.md); this section adds what we found after it (2026-11-20/21).*

**Symptom.** With layers on and 4K HDR YouTube, the console would sometimes stop answering: ports accepted
connections but nothing behind them responded, and only a power cycle helped. No crash report was written. Early on
it looked random (scrolling tests, video tests, a few with no test at all; those were a different cause, section 4).

**How we found it.** We wrote a tiny read-only payload that streams the kernel log to the PC, and kept it running
during every test. Every hang ended the same way: a "LOW FMEM" warning or a memory dump from the shell, and a
counter called **page table CPU** climbing fast towards its total of **8,192**. The console sits at about **5,100–5,200**
with Omni closed. Hangs happened with the last logged reading between roughly **6,680 and 7,000**; some runs
survived 7,219. It is not a hard line, but the risk rises sharply from about 6,700.

We then measured what moves that number, one thing at a time:

- **JIT pool size** (64/48/32 MB, FTL on/off): no effect; every arm sat at ~6,450–6,550 on 4K video.
- **GPU display, GPU video, JIT on/off** (layers off): no switch moved it more than run-to-run noise.
- **Memory-map walkers** in the title and in each engine process (`OMNI_MEMMAP_V1`, `OMNI_MEMMAP_CHILD_V1`): they
  list every mapping with its size, kind and the code address that created it, so each region can be named.
- **Small console probes** (payloads that map memory in different ways and read the pool before and after).

### What costs a page table on the PS5

| What | Cost in the shared pool |
|---|---|
| Flexible (ordinary `mmap`) memory, **mapped**, touched or not, any protection (even `PROT_NONE`) | 1 table per 2 MiB |
| 2 MiB alignment, `MAP_ALIGNED`, `MAP_ALIGNED_SUPER` | no saving: no large pages for this memory |
| `madvise(MADV_FREE / MADV_DONTNEED)`, `mprotect`, `MAP_FIXED` remap, unmap-then-remap | gives **nothing** back |
| `munmap` | gives the tables back |
| Re-reserving the range with `sceKernelReserveVirtualRange` (fixed address) | gives back 100%, and the address range stays yours |
| Address space that is only reserved | 0 |
| Direct memory in the title (GPU, decoder, video buffers) | 0 |
| Thread stacks of 64–512 KiB | about 0 |

Two more facts mattered. The title and the engine processes all draw from the **same** pool (we measured each
process starting), and processes started by a payload loader get **no direct memory** at all, so everything they
hold is flexible memory. Adding page-table size settings to the app's parameters had no measurable effect for us.

### Where Omni's tables went

Per engine process, before the fixes:

- the engine program itself, 244 MB, copied into each process by the loader: ~123 tables;
- two 128 MB address reservations made with `mmap(PROT_NONE)`: 128 tables, although nothing lives there;
- libpas (WebKit's memory allocator): up to ~290 tables on 4K YouTube, and it **never shrinks**;
- thread stacks: 76–132 tables (25–30 threads at 8 MiB each);
- the JIT pool, mapped twice (see section 12): 64 tables in the page process.

**Root cause 1.** Our build compiled an **old copy** of a small memory header that reserves address space with
`mmap(PROT_NONE)`. The newer version uses `sceKernelReserveVirtualRange`, which costs nothing, but it never reached
the compiler. **Root cause 2.** libpas "decommits" unused pages with `madvise(MADV_FREE)`, which returns no tables
on the PS5. **Root cause 3.** The GPU-drawing code raised every engine thread's stack to 8 MiB, because one Mesa
function has a ~99 KB stack frame.

### Fixes

| Marker | Change | Measured |
|---|---|---|
| `OMNI_VSS_BIND_V1` | build against the cost-free reservation header | 128 tables per process back |
| `OMNI_PAS_DECOMMIT_REMAP_V1` | libpas decommit = re-reserve the range; commit = map it again | the page process shrinks again |
| `OMNI_STACK_MIN_2M_V1` | engine thread stack minimum 8 → 2 MiB (still ~20x the Mesa frame) | stacks 76–132 → 22–26 tables per process |
| `OMNI_TRACE_LAZY_V1` | a 24 MiB diagnostic trace buffer is allocated only when tracing is on | 12 tables per process |
| `OMNI_PT_OPEN_GATE_V1` + `OMNI_PT_GATE_RECAL_V1` | the title refuses a video decoder open that would push the pool past a line; the 4K cost estimate recalibrated from ~450 to ~260 tables | prevents the last step into the hang zone |
| `OMNI_PT_WATCHDOG_V1` | safety net: at 6,600 the title stops the shown tab's page process, which then reloads once | last resort only |
| `OMNI_LAYERS_VIDEO_SLEEP_V1` | GPU page layers are dropped while a large video plays | fewer page-process buffers during video |

Things we tried and dropped: a smaller decoded-picture queue (saved ~20 tables, cost smoothness and once stopped
playback from starting), and telling YouTube that 4K is "not supported" (YouTube asked, got "no", and played 4K
anyway; a capability answer cannot force the resolution).

**Result.** 4K HDR YouTube with layers on now plays, with pool peaks of about **6,094–6,203**. Before these fixes the
same test peaked at **7,001** and never played. A near-empty page fell from a plateau of 6,178 to 5,777.

**Status: mostly fixed** in test builds; the decoder gate still refuses some 4K quality switches (see "What's still
open").

## 2. Two GPU submitters in one process (layers hangs)

**Symptom.** Before the page-table work, layers-on runs hung the console about **2 in 10**, often ~15 s after the
app started, with no low-memory warning first.

**Cause.** In layers mode the page process draws through a GPU broker inside the title. The title then had two
independent GPU submitters: the broker thread and the title's own RADV presenter. Both submitted command buffers
and both set global GPU state, with no lock between them. A community report on the PS5 RADV port describes the
same class of failure (a GPU stall that sometimes takes the whole console down).

**Fix.** `OMNI_GPU_ONE_SUBMITTER_V1`: the title's five GPU driver imports (submit, suspend point, and three state
setters) are wrapped into one process-wide lock shared by RADV and the broker. Title only, no new imports.

**Result.** Counters showed both submitters really did want the GPU at the same moment (15–213 contended waits per
run, at most 3.2 ms of waiting). With the lock: **20 of 20** layers-on runs clean (at the old rate, 20 clean by luck
is about 1%). One later hang *with* the lock in place had the page-table signature, which is what led to section 1.

**Status: fixed** (shipped in Bloom Preview 3, v0.5.4.2).

## 3. The launch memory crunch: the loader and the spare engine

**Symptom.** The kernel log showed "LOW FMEM" warnings at almost every Omni launch (15 of 16), with free system
memory dropping to single-digit pages.

**How found.** The shell's per-process memory dumps at each warning. The payload loader held **240 MB** after
starting Omni's engines (up to ~420 MB while starting two): it reads the 196 MB engine file and keeps a full-size
relocation copy in its heap. And a "reserve spare" engine (~244 MB) was started 30 s after launch, right on top of
the page-load peak.

**Fix.** `OMNI_STARTER_V1`–`V3`: our own small starter, based on the GPL elfldr code, loads engines in 16 MB pieces
from a read-only file mapping and keeps about 3 MB. `OMNI_SPARE_LAZY_V1`: no reserve spare (an engine starts in
0.6–1.8 s when needed). The first version of the starter forgot to reap finished engines, which left zombies; V2
fixed that.

**Result.** Loader 240 MB → ~3–5 MB. Launches with LOW FMEM: 15/16 → 4/5 (starter) → 2/4 (starter + no spare),
and **0 of 15** in a layers-off soak. The v0.5.3 release passed a 20-launch soak on this setup.

**Status: fixed** (v0.5.3). Each engine still carries its own 244 MB copy of the program; sharing code pages
between processes would be the next big saving.

## 4. Master Control and the boot crash

**Symptom.** Kernel panics during boot with payload autoload on, and two console drops with no test running.

**Cause.** Master Control (our controller helper) opens the PS5's own Bluetooth chip alongside the system and ran
inquiries every ~10 s. In 11 of 13 logged sessions that started unpaired, the console died at the end of the 60 s
pairing window, exactly when Master Control sent **HCI Inquiry Cancel**.

**Fix.** Master Control 0.4.5: no Inquiry Cancel (inquiries end by themselves), back-off, no USB before 90 s
uptime, no automatic pairing at boot. Later, a separate boot crash turned out to be crowding: 13 payloads started
5 s apart. Each one was fine when loaded by hand. Loading Master Control last and spacing payloads 10 s apart fixed
the boot.

**Status: fixed.** The two no-test drops were never tied to Master Control with certainty.

## 5. Out of memory with 8 GB free

**Symptom.** With layers, async scrolling and async read-back on, a 4K YouTube page process died (`pas_panic_on_out_of_memory_error`)
at only 1.42 GB.

**How found.** Our libpas patch logs the failing request: the kernel refused a **32 MiB** `mmap` with `ENOMEM` while
8.47 GB of flexible memory was free. 32 MiB is exactly one 4K frame (3840 × 2160 × 4 bytes). Turning features off
one at a time put the extra memory on the async read-back (up to +370 MB, depending on how far the main thread
fell behind).

**Cause.** Each read-back frame got a **new** 32 MiB bitmap and its own main-thread task, with no limit. When the
main thread was busy, the backlog grew.

**Fix.** `OMNI_GPUPAGES_LATEST_FRAME_V1`: a mailbox that holds at most one waiting frame and reuses its memory.

**Result.** 4K YouTube page-process peaks 1,065–1,440 MB → 1,047–1,177 MB; scrolling unchanged.
**Status: fixed.** (In hindsight, the refused 32 MiB mapping was probably the page-table pool as well.)

## 6. Compositor paths the port had never run

Layers switch on WebKit's threaded compositor, which the CPU-drawn PlayStation browser never used. Four bugs
surfaced:

- **Tab switch crash.** Showing a tab again made the main thread stop a timer owned by the compositor thread, which
  trips a release assertion. Our first fix (`OMNI_COMPOSITOR_SUSPEND_FIX_V1`) guarded only one caller; the real fix,
  `OMNI_RUNLOOP_STOP_FIX_V1`, lets the timer be stopped from any thread under its lock, as starting it already was.
  The first fix looked good in real use (13 tab closes, no crash) until the crash came back the same day, which is
  how we found the second caller. **Fixed** in test builds.- **Frame done after invalidate.** When layers went to sleep for a video (section 1), `invalidate()` cleared the
  display update timer, and a frame-done callback already queued then used it (a null pointer). It crashed in 9 of 9
  runs that took that path; it had been hidden because big videos never got that far before.
  `OMNI_COMPOSITOR_FRAME_GUARD_V1` returns early when the timer is gone. **Fixed.**
- **Exit abort.** The zero-copy page pipeline (section 7) was not destroyed before the Vulkan device, so the title
  aborted at close. **Fixed.**
- **Video size underflow.** A negative size in the video client's picture conversion asked the allocator for
  ~18 exabytes and aborted the page. `OMNI_HWCLIENT_SIZE_GUARD_V1` skips pictures with sizes outside 1–8,192.
  **Fixed.**

## 7. Layers scrolling: 8 fps to 52 fps

The first layers build matched the CPU path for video ([details](gpu-page-layers-ps5.md)), but scrolling YouTube's
home page dropped from ~14.6 fps (CPU path) to **8.1 fps**. A paint probe showed the whole viewport (~55 tiles) being
repainted on the CPU every frame.

**Cause.** Async scrolling had **never been on**: the PlayStation preferences force threaded scrolling off, and our
switch was checked after that, so it was never read. `OMNI_GPU_PAGES_ASYNC_V2` fixed the check.

| Step | Median fps |
|---|---|
| Main-thread scrolling | 8.2 |
| + async scrolling | 38–40 |
| + async read-back, 3 fenced buffers (`OMNI_GPUPAGES_ASYNCREAD_V1`) | 45.4 |
| + zero copy: the title composes the page straight from shared GPU memory | **51.6** |

A coverage probe showed brief unpainted tiles in the first 2–6 s of a scroll, then none. **Status:** working, layers
still opt-in; zero copy covers HDR canvases only so far.

## 8. YouTube stopped at one minute: the hard link that lies

**Symptom.** YouTube videos stopped after about one minute, on a long-used profile but not on a fresh one.

**How found.** YouTube serves about a minute of media and then withholds it unless the player has a trusted
**PO token**. The player was never minting one. Setting Omni's HTTP cache aside fixed it. Bisecting the cache's
6,181 records was not reliable (it is partly chance), but the cache had **0** stored large bodies.

**Cause.** On the PS5's data partition, the hard-link call **reports success and creates nothing**. The C++
`copy_file` fails there too. So the cache never stored a large body.

**Fix.** `OMNI_NC_BLOB_COPY_V3` checks that the file really exists with the right size after a "successful" link
and copies it with plain POSIX calls if not. `OMNI_NC_RESET_V1` sets the old, broken cache aside once.

**Result.** 0 → 44 stored bodies; YouTube's player script now loads from cache in 46–114 ms instead of ~235 ms.
**Status: fixed** (v0.5.0).

## 9. YouTube "not attested": PO tokens

**Symptom.** After the cache fix, YouTube still rejected about half of the tokens Omni's player minted. A rejected
token means a cut at ~60 s.

**What we ruled out**, each with console A/B runs: the user agent (Safari 17 vs 18: no difference over 11 runs),
`navigator.platform`, uBlock, the bundled add-ons, the remote inspector (compiled out), native HLS, and the JIT (a
3/3 clean JIT-off batch turned out to be luck). A November 4 build showed the same rejection rate in the same hours,
so it did not start with our changes. The rate swings by the hour and with how much the IP has been testing.

**What we built.**
- `OMNI_YT_ATTEST_GUARD_V1` (v0.5.0): a page script reads YouTube's stream-protection status from each media
  response and reloads on a rejection (up to 5 times per video), resuming at the same position. Later versions show
  a "Reconnecting to YouTube…" overlay, jump buffered gaps, and use a normal reload instead of a cache-bypassing one,
  which came back rejected more often.
- An in-page "rescue" that runs BotGuard again and swaps the new token into the player's requests. The swap worked,
  but YouTube rejected **5 of 5** of our own tokens, while a page reload gets a trusted run about half the time.
- `OMNI_YT_POTOKEN_V1` (in test): records each token's outcome by length (lengths 87–89 and 93–94 bytes were always
  accepted in our probes, 90, 91, 95 and 96 never), acts early on a length class that is almost always rejected,
  limits re-mints, and writes one daily summary line. Only a hash of the visitor identity is logged. Its R2 fixed a
  counter bug: the visitor data carries a timestamp, so the first version counted a "new identity" on every page.

**Status: mitigated, not solved.** The cheapest real improvement is signing in to YouTube in Omni: a public report
saw 0 of 19 failures signed in vs 5 of 23 signed out.

## 10. The YouTube "replay" with layers on

Users saw videos restart. That was the guard reloading. Three causes:

- **The MSE buffer limit.** Omni's MediaSource capped each buffer at **32 MiB**, sized for 1080p. A 4K HDR chunk is
  12–14 MB, so early in a video the player could hold about two, had nothing to evict, and stopped requesting media
  (frozen at ~11 s). Dose-response test: 16 MiB froze 3 of 6 runs, 64 MiB 0 of 6, with no memory cost.
  `OMNI_MSE_QUOTA_V1` makes it a setting, **64 MiB** by default (v0.5.2).
- **A too-early rule.** The guard reloaded if no token had been minted after 20 s; with layers on, minting took
  ~19 s. Guard v3 waits 40 s and only if no token request has answered.
- **Gaps after a reload.** The first buffered range could start a few seconds ahead of the playhead, and Omni's MSE
  doesn't jump gaps. `OMNI_YTGUARD_GAPJUMP_V1` does.

**Status: fixed**, apart from real token rejections (section 9).

## 11. uBlock: failing closed, and its cost

**"Filtering failed (error 1)" on fresh installs.** Setup turned the engine on but never installed its rule files,
and the engine fails closed, so every request was blocked. A second trap: rule files with Windows line endings load
without error and match **nothing**. Setup now installs and normalises the files, and `OMNI_UBLOCK_MISSING_V1` lets
pages load with a red shield and one notice if they are missing. **Fixed** (v0.5.2).

**Start-time cost.** Measured against the same site allowlisted: first paint on a busy site 0.4 → ~2.2 s (the network
engine loads 6.3 MB of rules on the first request), and YouTube video start ~5 → 12–15 s. A bisect of YouTube's
scriptlets put ~6 s on one group: the ones that blank the player's ad fields. Scrolling is not slower. We first
"measured" a big scrolling cost too; it turned out our test arms with a flag file did not scroll at all, so the
comparison was invalid. **Status: open by choice.** Blocking YouTube ads fully is kept; a faster rule-engine start is
on the list.

## 12. The JIT

- **W^X.** The PS5 won't give a process memory that is writable and executable at once. `OMNI_JSC_JIT_V4` maps one
  64 MB shared-memory object twice, read+execute for running and read+write for writing; all of JavaScriptCore's
  code writes already go through one function (`performJITMemcpy`), which writes through the alias. Probe: 5,000 of
  5,000 write-then-run cycles. Direct memory for the pool was refused. On by default since v0.5.1.
- **DFG and FTL tiers.** Two port fixes were needed: the register offsets in the signal context (otherwise VM traps
  read the wrong instruction pointer), and 2 MB compiler-thread stacks (Omni capped threads at 512 KB). A JS
  benchmark went 2.7x faster (geomean); YouTube's 4K watch page main thread went from 19.0 to 11.2 s busy. On by
  default since Bloom Preview 3.
- **The pool and page tables.** The dual mapping costs page tables twice (64 per page process). Shrinking the pool to
  32 MB made no difference to the 4K peak and slowed start by ~2 s, so it stays at 64 MB.

**Status: fixed / shipping.**

## 13. Non-blocking sockets

**Symptom.** The L1+R1 "send to Downloads" shortcut always said the Downloads app was unavailable, although it was
running. **Cause:** in the title, setting `O_NONBLOCK` on a socket fails with `EACCES` (errno 13), so every
connection using non-blocking connect and `poll` failed immediately. Blocking loopback connections worked.
**Fix:** `OMNI_MEDIA_HTTP_V3` falls back to a blocking socket with `SO_SNDTIMEO`/`SO_RCVTIMEO` timeouts. **Fixed.**

## 14. HDR and 10-bit video

- **Our GPU colour check failed on real 10-bit video.** The CPU reference (libswscale's general scaler) interpolates
  chroma vertically on even rows; our shader keeps each chroma sample for its 2×2 block. 8-bit matched only because
  swscale has a special path for it. `OMNI_GPU_VERIFY10_V1` fixes the comparison. **Fixed.**
- **17 ms of CPU per HDR frame.** Each visible run of video was copied as its own image region, and RADV records every
  region as a full draw (~1.9 µs each); 4K 10-bit HDR copies ~3,650 runs twice. `OMNI_HDR_PRESENT10_V1` does it in one
  compute dispatch: **17 ms → 0.17 ms**. **Fixed.**
- **A "10-bit stall" at exactly 60.000 s of media** was not ours: the page simply stopped feeding data. It was the same
  one-minute YouTube cutoff as section 8.
## 15. First-run and packaging

Fresh installs did not start, or capped YouTube at 720p, because they lacked files and switches that only our test
console had from older setups. Setup now writes them and `OMNI_FIRST_RUN_V1` makes browser mode the default.
**Fixed** (v0.5.1/v0.5.2).

---

## What's still open

- **A 4K quality switch can be refused.** YouTube opens the new decoder while the old stream is still being released.
  At pools of 6,146–6,267 the gate refused the 4K open in 3 of 13 4K runs; Omni then fell back to software decoding,
  which stalls at 0 s. Waiting up to 3 s for the old stream (`OMNI_PT_GATE_WAIT_V1`) did not help: nothing is released
  in that window. In progress: `OMNI_PT_GATE_4K_LINE_V1` gives 4K opens their own line, 6,400 → 6,550 (4K plays at
  ~6,200; the hang zone starts near 6,770). A better long-term answer is stepping down to 1440p in hardware instead
  of falling back to software.
- **Lazy picture slots stall video.** `OMNI_SHM_LAZY_SLOTS_V1` maps each stream's decoded-picture area only on first
  use (saving ~128 tables per 4K stream). With it on, every stream stalled at 0.01 s. A bisect put the fault in the
  title; the lazy mapping code was never even reached. Cause unknown; **off by default**.
- **YouTube token rejections** (section 9): mitigated, not solved.
- **uBlock start cost** on YouTube (~6 s), kept by choice for full ad blocking.
- **Layers by default.** Waiting on the two items above and a long soak.
- **Engine program copies.** Each engine process holds its own 244 MB copy (~123 page tables).

## Lessons for other PS5 porters

1. **Watch the page-table pool, not just free memory.** Read it during every test. On this system, mapped flexible
   memory costs 1 table per 2 MiB whether you touch it or not, and `madvise` gives nothing back.
2. **Reserve address space with `sceKernelReserveVirtualRange`, not `mmap(PROT_NONE)`.** Return memory by
   re-reserving or unmapping it. Check which header your build *actually* compiles.
3. **Put big buffers in direct memory where you can.** It cost 0 page tables in our title. Payload-started processes
   get none.
4. **Look at every allocator's "decommit".** libpas, and probably others, assume `madvise` releases resources.
5. **Big thread stacks add up.** 8 MiB × 30 threads is 120 tables per process.
6. **One GPU submitter per process,** or a lock around every submit and state change.
7. **Don't trust success codes from the filesystem.** Check that the hard link (or copy) really exists.
8. **Don't use `O_NONBLOCK` sockets in the title;** use blocking sockets with timeouts.
9. **The Bluetooth chip is shared with the system.** Cancelling an inquiry from outside can panic the kernel.
10. **Enabling a code path the port never shipped will find latent bugs.** Check which file the port really
    compiles (our first compositor probe patched a file the build doesn't use: zero build steps).
11. **The title can't import symbols the console lacks at start,** and the link needs every import in the SDK
    stubs. A new GL call in shared code broke the title build twice.
12. **Two causes with one symptom look like one.** Keep exactly one difference between a test and its control, and
    run them back to back: YouTube's rejection rate changes by the hour.

## How we measure

- **Kernel log capture.** A small read-only payload streams the kernel log to the PC during tests; the page-table
  count, LOW FMEM warnings and per-process memory dumps come from there. Later, the engine starter answers a "pt"
  request with the pool count from the kernel's page-table statistics call, so the title can read it too.
- **Pool sampler.** A payload samples the pool every 250 ms, which shows each process's share as it starts.
- **Memory-map walkers.** `OMNI_MEMMAP_V1/V2` (title) and `OMNI_MEMMAP_CHILD_V1/V2` (engines) write every mapping with
  size, kind, protection and the creating code address, symbolized afterwards. `OMNI_MEMTRACE_V1` wraps the
  direct-memory calls to name their callers.
- **Probes.** Single-purpose payloads answer one question each: does `madvise` return tables, does 2 MiB alignment
  help, what do stacks cost.
- **On-console A/B arms.** A test harness installs a build, launches a fixed scenario (4K HDR YouTube, a page scroll,
  a near-empty page), records fps, playback, memory peaks and crashes, and restores the everyday build afterwards.
  Arms differ by one flag file; arms are interleaved in one session; anything that changes a default gets a soak (20
  launches) before a release.
- **In-process diagnostics** (flag-gated, off by default): a main-thread watchdog, a signal-based sampling
  profiler, compositor counters, paint and tile-coverage probes.
