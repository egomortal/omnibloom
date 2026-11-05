# omni-native-s3.5-hdr: console test plan

**Build under test:** `outputs/omni-native-s3.5-hdr/out/PPSA99732/eboot.bin` `59433d64e9fc7625ce86a61dc9e6ccce7f61190c22cdfddf0780efa88b4dbe0d` (title only).
- **The child is unchanged:** `child/omni-engine-child.elf` = `7b810ea5…fd717c64`, so there is nothing to install for it.
- **The package is unchanged too:** `param.json` (`354f191d…`, attribute 0x62000000, which already declares HDR) and `libc.prx` are as in s3.4d.

## Rules (unchanged)
- `console-lock.py acquire`, and the console must be idle.
- Wait 4 minutes between launches.
- Close through Omni's Exit menu, never by killing it.
- Read logs only after the last `Omni diagnostic build:` marker.
- **Back up before the first launch, and restore at the end:**
  - the installed eboot;
  - every flag file;
  - the user's **`/data/omni/video-hdr-preference.txt`**, which may be missing (if so, delete it again at the end).
- Leave `/data/omni/site-dark.txt` as it is.
- **Logs for each step:**
  - boot.log;
  - `/data/omni/native/{video-fps,gpu-present,gpu-video}.log`;
  - the hole-punch log (the `GPU HDR decision` lines);
  - the YTTL JSON;
  - stderr's `OMNI_HDR_CAPS_V1:` line.
- **Note the PS5's own HDR setting first** (Settings > Screen and Video > Video Output > HDR: "On When Supported" or "Always On"). It decides whether the TV's HDR badge means anything (see step 3).

**Setting file format** (Astra's R3-084): `<revision>\t<mode>\n`, for example `printf '1\ton\n'`. If the user's file exists, write the next revision.

**Base flags for every step except 1b:**
- `/data/omni/gpu-present.flag` = `out=2160`;
- `/data/omni/gpu-video.flag` (empty);
- `/data/omni/video-fps.flag`;
- yt-timeline as in the 4k60 plan, with `interval 2000`.

## 1. SDR regression (no TV check needed)
**1a.** Base flags; HDR setting **off** (`1\toff`). Watch `aqz-KE-bpKQ` (2160p60 VP9 SDR) for 340 s, `fullscreen 1`.

**It passes as s3.4d did:**
- `path=gpu out=3840x2160 mode=FIFO shared_device=1 out_mode=SDR hdr_setting=off src_tf=SDR src_bits=8`;
- over 300 s: median fps ≥ 59, dropped ≤ 1%;
- `video_in_place` ≈ `video_gpu_pictures`.

**It also needs these log lines:**
- gpu-present.log: `HDR setting: off`, `swapchain: SDR output, format 44`, and no `HDR: armed`;
- stderr: `OMNI_HDR_CAPS_V1: pages are told HDR not capable`;
- YTTL / `video-hdr` must **not** show VP9.2.

**1b.** No flags at all: the same as s3.4d (gate 5c).

## 2. HDR On with an SDR video (**the user looks at the TV**)
Base flags; setting **on** (`2\ton`). The same SDR watch URL, 150 s, `fullscreen 1`.

**Logs:**
- gpu-present.log: `HDR setting: on (HDR setting (video-hdr-preference.txt))`;
- every `surface format N` line, which must include **format 64 with colour space 1000104008**;
- `HDR self-test … -> pass`, `HDR: armed (on): HDR10 format 64`, `swapchain: HDR10 (BT.2020 PQ) output, format 64`;
- `VideoOut output range 2`;
- the fps lines say `out_mode=HDR hdr=1 src_tf=SDR src_bits=8 pq_frames=0`, and median fps ≥ 59 (the PQ pass costs about 0.5 ms on the GPU; compare `present_gpu_ms` with step 1).

**The user checks:**
- The TV switches to HDR. If the PS5 is set to "On When Supported", the TV's HDR badge appears when Omni starts.
- The menus, text and page white look like normal SDR white: **not blinding, not grey**.
- The colours of the SDR video look normal: skin tones and sky are not oversaturated or washed out.
- Then open Omni's menus and a light page (example.com) and check them the same way.

## 3. An HDR10 YouTube video, 4K60, 300 s (**the user looks at the TV**)
Base flags; setting **on**.

**The video:**
- Use a known VP9.2 HDR10 2160p60 test video, for example "COSTA RICA IN 4K 60fps HDR (ULTRA HD)" (`LXb3EKWsInQ`), or any video YouTube labels "2160p60 HDR".
- **Confirm the stream first:** YouTube's quality menu shows "HDR", or stats-for-nerds shows `vp09.02.51.10.01.09.16.09.00` and `smpte2084 (PQ) / bt2020`. If it doesn't, try another HDR video before judging.
- Run with `seconds 340`, `fullscreen 1`.

**It passes when:**
- the fps lines over the 300 s after 40 s say `path=gpu out=3840x2160 out_mode=HDR src_tf=PQ src_bits=10 pq_frames≈60/s video_pq_layers≈60/s shared_device=1`;
- **the median fps is 59 or more**, dropped frames are at most 1%, and `intervals_over_25ms` is rare;
- the hole-punch log shows `GPU HDR decision: 10-bit src 3840x2160 -> 3840x2160 primaries 9 transfer 16 (inferred: VP9 BT.2020 10-bit) … -> PQ layer made (GPU)`;
- gpu-video.log shows `HDR: PQ layer written on the GPU (PQ (ST 2084) source …)`;
- there is no `WATCHDOG`, `MISMATCH`, `OFF:` or `PQ layer import failed`.

**Record for comparison with step 1:** fps, drops, `present_gpu_ms` and `video_gpu_ms` (the PQ layer is a second 33 MB write per picture).

**The user checks:**
- Highlights (sun, specular reflections) are clearly brighter than the page white, while the dark scenes keep their detail. It must look like HDR, not like washed-out SDR.
- Motion is smooth.
- The controls bar looks right. The video under the translucent gradient can look slightly dimmer, which is a known limit.
- **Is there an HDR badge?** With "On When Supported" the TV should show its HDR badge. With "Always On" the badge is on in every step, so the brightness of the highlights is the check.

## 4. Auto mode switching (**the user looks at the TV**)
Base flags; setting **auto** (`3\tauto`).

**Logs at start:**
- `HDR: armed (auto)`, `swapchain: SDR output`;
- stderr: `pages are told HDR capable`.

**The run:** the step-3 video, 240 s. Start inline (`fullscreen 0`), press f to go fullscreen at about 30 s, leave fullscreen at about 120 s, then fullscreen again at about 180 s. Use the runner's `fullscreen 1` option, or a key script.

**It passes when:**
- gpu-present.log shows `HDR Auto: HDR10 output on` about 0.5 s after each fullscreen, and `HDR Auto: back to SDR output` about 1.5 s after leaving;
- each switch is followed by `swapchain: …` and then `VideoOut output range …`;
- the fps lines' `out_mode` follows, and `hdr_switches` is 3;
- there is no present failure and no watchdog;
- dropped frames stay at most 1% outside the 2 s around each switch. Report the frames around each switch separately.

**The user checks:**
- The TV switches into and out of HDR. A short HDMI re-sync blank may happen; note how long it lasts.
- The inline page looks normal SDR.

**Optional:** open the controls overlay for a few seconds while fullscreen. The output must **not** switch: a gap under 0.3 s does not count, and the PQ layer keeps being staged.

## 5. The fallback (no TV check needed)
**5a.** `gpu-present.flag` = `out=2160 hdrfail`; setting **on**; step 1's URL, 90 s.
- gpu-present.log: `the HDR10 swapchain is refused on purpose (flag word hdrfail …)`, `HDR: the HDR10 output was refused (start-up): SDR output`, `swapchain: SDR output, format 44`.
- The fps lines say `out_mode=SDR`; the video plays at 4K60 as in step 1; Omni works normally.
- stderr: `pages are told HDR not capable`.

**5b.** `hdrfail` with setting **auto**, plus step 3's HDR video in fullscreen, 90 s:
- `HDR Auto: HDR10 output on (…)` once, then the refusal, then SDR, and **no further attempts**;
- the video keeps playing (`out_mode=SDR`, `src_tf=PQ`).

**5c (optional).** `gpu-video.flag` removed, setting on, step 3's video:
- `src_tf=PQ`, `video_pq_layers=0`, `pq_frames=0`, and the hole-punch log says `PQ layer NOT made (SDR mapping)`;
- it plays without crashing. HDR passthrough needs the GPU video path.

## 6. Exit (after steps 3 and 4)
Close through the Exit menu.
- gpu-video.log: `shutdown: … live buffers=0 memory=0` comes BEFORE gpu-present.log's `teardown (SDL_Quit …)`, which must show buffers, images and memory at 0.
- ShadowMountPlus shows a normal exit.

## Isolation if a step fails
**Step 2 or 3 shows no `format 64`:** the title did not link the private archive. Check `checks.txt` for `exbox_presenter_probe`, and the `wsi/videoout` strings.

**`vkCreateSwapchainKHR(HDR10 PQ, format 64) = -2` (out of device memory):** the extra 160 MiB scanout set did not fit. Report it; the output stays SDR, which is correct.

**HDR output but the video looks washed out:** look for these lines:
- `src_tf=PQ pq_frames=0`: the PQ layer was not staged. Check the `GPU HDR decision` line and `video_pq_layers`.
- `src_tf=SDR` on an HDR video: the transfer was not seen. Check `hdr-vp9-infer-disabled.flag`; YouTube may also have sent SDR (check the `OMNI_HDR_CAPS_V1` line and stats-for-nerds).

**Rollback:** delete the flags, restore the setting file, and reinstall the previous eboot (the runner's restore).
