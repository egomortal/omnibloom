# Omni s3.4 (s3.4 → s3.4d): console results, 2026-11-05 (lock OMNI_S34)

**Status:** s3.4d is the candidate. Every automated gate passes on s3.4c (s3.4d = s3.4c + one dark-mode script change, re-checked on s3.4d below) except one strict media hitch (see "Open"). 4K60 passes. **The console is back on s3.1c** (verified, see "End state"). Nothing was installed for real; that waits for the user's OK.

## 1. The YouTube stall (step 1): cause found on s3.1c, fixed title-side

| Run (installed s3.1c, JIT off, user's settings) | Result |
|---|---|
| watch `aqz-KE-bpKQ` (yt-timeline) | **stalled**: MSE time 0.0145 s for the whole run, no hole, no pacing |
| Shorts | **stalled** the same way |
| same watch URL, only `youtube.com` taken out of `/data/omni/site-dark.txt` (restored after, hash verified) | **plays**: 13.97 s in a 30 s window, hole on, shell-paced |

- **Cause:** the user's "Dark pages: always" for youtube.com. Omni's dark script (`OmniDarkPages.h`, shell) puts `filter: invert(1) hue-rotate(180deg)` on `<html>`. The child's `holeGeometry()` refuses any video with a filter above it ("opacity, filter, mask… on the way up"). The frozen child's start gate ("V133: no timeout may silently bypass the startup gate") then waits forever for a plane that is never claimed. This is not the old start-gap bug (`skipped a 0.015 s gap` is logged) and not s3.3's GPU path. It also explains why the user sees videos play: fullscreen already turned the filter off, and YouTube pages measured dark were never filtered.
- **Fix (title only, the child stays 7b810ea5):**
  - `OMNI_DARK_VIDEO_PLANE_V1`: the filter steps aside while a playing video covers ≥ 20% of the viewport (the existing fullscreen rule, extended), and comes back on pause/end.
  - `OMNI_DARK_STANDARD_V1` (user-approved): the page's own dark theme comes first and the filter is the last resort (dark background, or no background plus color-scheme / meta / `prefers-color-scheme` rules). The page is measured again on theme-attribute and appearance changes and at load +1.5/4/8 s. The Dark Reader hook is `<html data-omni-dark-addon="on">`, which turns the filter off.
  - `OMNI_DARK_APPEARANCE_EMU_V1`: see the console finding in §3.
- **Not used:** Astra's startup fallback is the general fix for any filtered or opacity'd video, but it lives in `OmniMSEPlayer.cpp`, so in the child. Per the rule it is not applied; it stays a child-rebuild proposal. The 4K60 helper's patch 04 (also a dark step-aside) is not used, because ours covers it.
- **After (s3.4c, youtube.com still "always dark"):**
  - watch: currentTime **75.3 s at the 90 s snapshot**, hole on, paced, `hole.eligible=true`, `dark.filter=false` while playing;
  - Shorts: playing (2907 frames in the 60 s run; the Short loops, so currentTime is small);
  - 20-min soak: **1181 s played, 0 stalls**.

## 2. Builds (title only; every child link = 7b810ea5, checked by each build)
| Build | Adds | eboot.bin (package) |
|---|---|---|
| s3.4 | s3.3 V2 video stack + pointer-cross + Astra CLEAN4 `integration.diff` (native quick bar/Options/Apps, stats + HDR-preference bridge, downloads C-1 fcntl→FIONBIO + card port, files C-2 card port, MC 0.4.4 label) + `OMNI_DARK_VIDEO_PLANE_V1` + SDL import cache + region reuse (presenter 3-way merge) + YTTL fps probe + final pages (1192 files) | `2f4e44c0a334c9280e74c874ba18a299d7157dbce35888b013c1b8523cf1f1f4` |
| s3.4b | + `OMNI_DARK_STANDARD_V1` + YTTL `dark` field | `eac7d741c6489b94964e99f6bc1d705b4bd10364985d8a94dd745a1f6e6458e3` |
| s3.4c | + omni-video-4k60 01–03 + 05 (`OMNI_GPU_VIDEO_V3` in-place read + shared RADV device, `OMNI_GPU_PRESENT_V3` queue lock/share/FPS_V2, merged 3-way with the CLEAN4 presenter; hole-eligibility probe) | `015c8e6cdb4c54659a946949fbeedcc82a35ed5d621d41068e0a29ecd707f6b0` (readback e01f5727…) |
| **s3.4d** | + `OMNI_DARK_APPEARANCE_EMU_V1` | **`ca22b2e491a89be5ba69471070df6d3c657829ac40eb9f92f39bf8f0d7d26a41`** |

Folders `outputs/omni-native-s3.4{,b,c,d}/` (each with `SHA256SUMS.txt`, `build-steps.txt`, `checks.txt`). Build scripts `outputs/build-omni-native-s34{,b,c,d}.sh`, modelled on s3.1c/s3.3 (private overlay, frozen trees untouched). Other artefacts:
- `omni-files.elf` s3.4 = audit FB-01 source + C-2: `eaa86c6439cd84b58f2076848b420afeede5e7274cfaa9600e5971337bd7df9d` (`omni-files-broker/s34/`, 41/41 host checks).
- Worker files + cards/receipts: `omni-native-s3.4/services/`.

**Host tests (all pass):**
- sec-connect 17/17, vault OS-002 59/59 (51 when run as root: the permission cases are skipped), vault suite 103/103, SDK compile;
- GPU on lavapipe (V3): video 23 PASS, fallback, shared-device, present, present fallback, pair-cache;
- pointer-cross 41/41 on the s3.4 files (two wiring strings updated for D1's `omniMqPointerTakeover()`);
- dark: video-plane 12/12, standard 11/11, emu 6/6. Negative controls: the unpatched script fails 3/12, and the v1-only script fails 4/11;
- Astra's suites rerun: D1 746 (quick-access 68, group 38, panel 640), fps probe 15, analyzer 11.

**Security review of `integration.diff`:** no change to the child, its allowlist, OmniHubCards' page rules, JIT, vault or Bloom Core. The new downloads card (8765, public `/`, `/downloads`, `/assets/`; `/api/` own page only) makes 8765 *stricter* for other pages than the legacy no-card rule. files-broker 8767 stays in `neverForPages`. Ports are unchanged (8765/8767), so the child's fixed allowlist still matches. The portblock gate passed with the cards installed (65 rows, sink no hits).

## 3. Console gates (runner `omni-jit2/run_s34.py`, wrapping run_jit2.py; log `omni-jit2/S34-STATUS.md`; evidence `omni-jit2/gates-s34c/`, `gates-s34d/`, `gates-s34d-load/`, base runs `gates-s34-base/`, `gates-s34-ab/`)
Installed for the pass:
- s3.4c eboot + the s3.4 pages, each file hash-checked;
- omni-files.elf eaa86c64;
- worker `console_worker.py`/`worker.py`/`suite_port.py`;
- downloads (8765) and files-broker (8767) cards + receipts, labelled "s3.4 console test, not Setup";
- Master Control card/receipt 0.4.3 → 0.4.4 (D-3).

Every replaced file was backed up first (PC `omni-jit2/s34-backup/`, console `*.before-s34`). Bloom Core and Master Control were started through 9021 for the pass.

| Gate (JIT off unless noted) | s3.4c | s3.4d | Notes |
|---|---|---|---|
| install: child readback | 7b810ea5 MATCH | same (eboot-only swap) | eboot readbacks e01f5727 / a9169ddb |
| status.json | PASS | | downloads 8765, files-broker 8767, master-control 0.4.4 all verified; MC `/api/health` 0.4.4 |
| feature | PASS 1104 ms | PASS 1079 ms | standing Cloudflare row as in s3.1b |
| scroll | PASS 65.3 fps p95 16 | | |
| input, gamepad, padctl | PASS | | |
| media (HLS fullscreen 40 s) | **FAIL**: one 135 ms hitch, 24/4799 dropped | **PASS ×2**: 0 hitches, 14/4791 and 0-hitch rerun | zero-hitch rule; the s3.4c miss did not repeat |
| portblock | PASS, sink no hits | | with the new cards installed |
| apps (Bloom Core, Apps panel) | PASS | | |
| downloads worker | PASS | | started by Omni's own route (websrv `/hbldr`); bound 8765 from its card, published `/data/hub/runtime/downloads.json`; Bloom Core: verified + up. The title's "Send to Downloads" button needs the user check (§5) |
| YouTube watch, 90 s, youtube.com dark ON | **PASS** 75.3 s | **PASS** 68.3 s | hole on + shell-paced; probe `eligible=true`, `dark=false` while playing |
| YouTube Shorts 60 s | PASS (2907 frames, looping) | | the runner's clock threshold was wrong for a looping Short (logged FAIL); judged by frames |
| 20-min YouTube soak | **PASS** 1181/1200 s played, 0 stalls | | qualities hd1440/hd2160 |
| dark: YouTube home | | filter ON (fallback), page `matchMedia(dark)`=true | see §3a |
| dark: example.com (not in the dark list) | | untouched (no filter) | |

### 3a. Dark mode the standard way (user-approved item)
- **Console finding:** the shell's `WKPageSetUseDarkAppearanceForTesting` does **not** reach pages in this engine. On s3.4c the YouTube page saw `matchMedia('(prefers-color-scheme: dark)')` = false. The place to honour it is the child, which stays unchanged.
- **s3.4d** adds `OMNI_DARK_APPEARANCE_EMU_V1`. A page-world document-start script answers `matchMedia(prefers-color-scheme)` from Dark mode (`<html data-omni-dark-want>`), and listeners fire on change. On the console: `appearance=true` on YouTube.
- **But YouTube still stayed light** (signed-out; YouTube picks its theme server-side, from its own setting/cookie, not from matchMedia). So it gets the invert filter, and the video step-aside keeps playback on the fast path. A CSS `@media (prefers-color-scheme)` can't be faked by script.
- **To get YouTube dark with no filter:** choose YouTube's own Appearance → Dark theme once (YouTube remembers it). Omni then measures a dark page and never applies the filter.
- **Dark Reader hook ready:** the add-on sets `<html data-omni-dark-addon="on">` and the filter goes off.
- Not done: a console test of a site that has CSS-only dark rules.

## 4. 4K60 (omni-video-4k60 TEST-PLAN on s3.4c; user's dark setting kept; native `video-fps.log` is the measure)
| Gate | Result |
|---|---|
| 1 cause check, no GPU flags, 60 s | hole eligible, not dark, MSE time 43.5 s / currentTime 44.5 s |
| **2 4K60 fullscreen GPU, 300 s window** | **PASS. Median 59.94 fps (p10 59.84, min 32.88 once). Dropped 30 of 17,761 = 0.17%. 14 intervals > 25 ms.** path=gpu, 3840x2160 out, FIFO, shared_device=1, 17,947 pictures all read in place, 0 ring copies. Source 3840x2160 (2560x1440 at the start). Video clock 0.999× real time. Verify frames exact; shutdown: video freed before present teardown, live objects 0. HDR off |
| 3 inline, 150 s | 59.94 median, 0.22% dropped, GPU in place, shared |
| 5a failsetup (both flags) | falls back to the SDL path, plays: 59.94 median, 0.21% dropped |
| 5b sharing disabled | own device, 59.94, 0 dropped |
| 4a/4b 1080p60 / 1440p60 | not run (no fixed test URLs); the inline runs played 1440p at 59.94 |

- HTML playback counters report about 120 frames/s for 60 fps video (the child counts each frame twice), so they are not used for fps.
- HDR untouched; no profile switch.
- Gate 2 is a TV-side "looks smooth" claim only once the user confirms it.

## 5. YouTube load breakdown (s3.4d, 2 runs each, median; ms from navigation; youtube.com dark ON as the user has it)
| Page | s2 (Nov 3, 1 run) | s3.1b JIT off | **s3.4d JIT off** | s3.1b JIT on | **s3.4d JIT on** |
|---|---|---|---|---|---|
| Home cold: fcp / first tile | 4036 / 6343 | 3455 / 5778 | **3656 / 6148** | 3505 / 5759 | **3264 / 6221** |
| Home warm: fcp / tile / all thumbs | 1201 / 2894 / 5026 | 1200 / 2957 / 5134 | **1335 / 3413 / 5337** | 1714 / 3000 / 4354 | **2041 / 2725 / 4348** |
| Search: fcp / tile | 1190 / 3673 | 1012 / 3616 | **2042 / 4351** | 1305 / 2952 | **1250 / 4532** |
| Shorts: fcp / tile / video | 2865 / 5766 / 6915 | 2723 / 6012 / none in 8 s | **1097 / 4927 / 6299** | 1165 / 4627 / 6510 | **1361 / 4552 / 5729** |
| Main-thread busy, warm home (of 8 s) | 6.25 s | 6.52 s | **6.46 s** | 4.98 s | **5.06 s** |

Raw runs (fcp, tile, all thumbs, video, busy):
- **OFF:** cold (3787, 6260, -, -, 3824) (3525, 6035, -, -, 4005); warm (1351, 3260, 5093, -, 6275) (1318, 3566, 5581, -, 6642); search (2420, 4011, 4350, -, 5120) (1664, 4690, 4690, -, 6204); shorts (1078, 4984, -, 6695, 5377) (1115, 4869, -, 5902, 5409).
- **ON:** cold (3277, 5784, -, -, 3538) (3250, 6658, -, -, 4433); warm (3167, 3229, 4874, -, 4821) (914, 2220, 3822, -, 5296); search (1261, 4991, 5319, -, 6355) (1239, 4073, 4073, -, 6066); shorts (878, 5008, -, 5975, 5408) (1844, 4095, -, 5482, 4872).

Evidence: `omni-jit2/gates-s34d-load/`, computed with `omni-youtube/analyze.py`. Shell paint time (UI process) is 8–32 ms per 8 s page, so it is negligible.

**Reading:**
- s3.4d loads like s3.1b within the 2-run noise. Cold home is +0.2 s, search fcp is +1 s in one run (2420 vs 1664), and Shorts are faster. Shorts now show video at 5.7–6.3 s; s3.1b JIT off had none within 8 s.
- The JIT again cuts warm-home main-thread busy time by about 1.4 s per 8 s and brings all-thumbnails about 1 s sooner.
- **Main-thread busy is 5–6.5 s of every 8 s on the page itself. That is where YouTube's slowness is**, not the network (TTFB/response is about 2.2 s cold and well under 0.1 s warm) and not the shell's painting.
- **JS vs style/layout vs paint vs GC split: not measurable with the current probes.** The YTTL/fps probes give rAF gaps, long-task-free "busy" and paint entries only. A category split needs WebKit's own per-category timers (Inspector timeline or a `PerformanceObserver('longtask')` attribution build) in the WebProcess, which is the child engine and stays unchanged here. Astra's B1 analyzer reaches the same limit ("existing rAF gaps are not category timings; GC coverage absent").

## 6. User check (TV): **pending, morning**
s3.4d was left installed for the user's look, but the user had gone to sleep, so the console was restored without it. Still open:
- the quick bar / Options / Apps look (screenshots);
- the title's own "Send to Downloads" button (the worker side passed: launched by Omni's route, bound 8765, Bloom Core verified/up);
- the video statistics panel;
- "4K60 looks smooth on the TV".

Steps for the morning: install s3.4d (§8) or run `run_s34.py install` + keep, then the 5 steps given to main (Options → quick bar/Apps; YouTube → Send to Downloads; video stats; close via Options → Close game).

## 7. End state: **s3.1c restored, EVERYTHING VERIFIED** (07:48Z), lock released
- eboot readback `03dcfe19…` (= s3.1c package `e8ac0c9d…`), child `7b810ea5…`, s3.1c `pages/` back in place.
- omni-files.elf `d1532d12…`, worker `console_worker.py` `5c49aae7…` / `worker.py` `096b5915…`; MC card `956ff643…` / receipt `3a9608e8…` (0.4.3 label again).
- New files removed: suite_port.py, downloads/files-broker cards and receipts, runtime/downloads.json, the console `.before-s34` copies inside /data/hub.
- `site-dark.txt` unchanged (`61c21293…`). No GPU/fps/timeline/JIT flags left.
- Bloom Core and MC stopped (they were not running at the start; autoload starts them at the next boot). Hub/MC payload files were never changed (6a6d6f84 / 9b2de63b).
- Left in place:
  - `pages.s34-tested-024338`, `pages.new.s34-tested-215902` (renamed, nothing deleted);
  - console `*.before-s34` copies of omni-files.elf and the worker files;
  - **the `omni-media-worker` process started by the worker gate (pid 228) is still running** with the s3.4 code in memory (its files are restored). It is harmless and goes at the next reboot; I did not kill it.

## 8. Install s3.4d for real (on the user's OK)
1. In `outputs/omni-jit2/s34-cmd.txt` put two lines:
   - `install`
   - `JIT2_GATES=gates-s34-install S34_DIRNAME=omni-native-s3.4d S34_EBOOT_SHA=ca22b2e491a89be5ba69471070df6d3c657829ac40eb9f92f39bf8f0d7d26a41`

   Then drop `build-requests/<name>.req` containing `run-omni-s34.sh`. This:
   - takes the lock, waits for idle, and checks that the console is on s3.1c;
   - backs everything up (PC `s34-backup/` + console `*.before-s34`);
   - uploads the s3.4d pages (every file hash-checked; s3.1c pages kept as `pages.s31c-keep`);
   - swaps eboot (child untouched), and writes omni-files.elf eaa86c64, the worker files, the downloads + files-broker cards/receipts and the MC 0.4.4 card;
   - starts Bloom Core + MC and checks status.json.
2. Check with `state` (child 7b810ea5, eboot readback ≠ 03dcfe19). **Do not run `restore`.** Then `python3 console-lock.py release OMNI_S34`.
3. The cards/receipts are labelled "s3.4 console test, not Setup". For a permanent install, re-run Setup-next with the C-1/C-2 generator so that Setup owns them (same ports 8765/8767).
4. Recommended once: on YouTube choose Appearance → Dark theme. YouTube is then dark by itself and Omni never inverts it.
5. Rollback any time: `restore` (same cmd file) puts s3.1c back, verified.

## 9. Open / not done
- Astra's startup fallback (child) is the only general fix for a video under *any* filter or opacity. It is not applied because the child must stay unchanged.
- HDR: no HDR eboot had arrived from the HDR agent; nothing HDR was run and no profile was touched.
- 4K60 gates 4a/4b (1080p60/1440p60 test URLs) were not run.
- The media gate had one 135 ms hitch on s3.4c (did not repeat on s3.4d ×2).
- The category timing split for YouTube needs child-side timers (§5).
- OS-001 public-initiator cases are still open from s3.1b.
