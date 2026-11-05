# omni-video-4k60: console test plan (for the s3.4 agent)

Build under test: `outputs/omni-video-4k60/out/PPSA99732/eboot.bin` `009c3339…2296a` (title only). Child: unchanged,
`out/child/omni-engine-child.elf` = s3.1c's `7b810ea5…fd717c64` (nothing to install for the child if 7b810ea5 is already there).
Or stack `patches/` on s3.4 with `apply_video4k60.py --folder <s3.4 folder> --tree /home/builder/s1` (04-05 after pointer-cross;
compile them for the TITLE link only, never relink the child from that tree).

## Rules (unchanged)
- `console-lock.py acquire`; console idle; 4 minutes between launches; close through Omni's Exit menu (never kill);
  read logs only after the last `Omni diagnostic build:` marker; restore the installed build and every flag afterwards.
- **Leave the user's `/data/omni/site-dark.txt` as it is** (youtube.com = always dark). That is the real-world case that
  blocked s3.3/s3.4; this build must play with it.
- Logs per gate: process logs, `boot.log`, `/data/omni/native/{video-fps,gpu-present,gpu-video}.log`, the `YTTL js run=` JSON
  (now carries `playback` = Astra's 1 s HTML counters, `hole` = the eligibility probe, `nativePageFullscreen`).
- yt-timeline: `seconds` is clamped to 2..360, `interval` to 100..2000 ms (use 2000: the frame captures are capped at 31
  but each one costs a 4K read; judge cadence after them). New option `fullscreen 1` (Astra's OMNI_YTTL_FULLSCREEN_V1):
  the normal f key once per watch URL after 8 s.

## Gates
| # | Gate | Flags | Page / yt-timeline | Pass |
|---|---|---|---|---|
| 1 | **cause fix, CPU path** | `yt-timeline` only (no GPU flags) | watch `aqz-KE-bpKQ`, 60 s, fullscreen 0 | `OMNI HOLEPUNCH: player hole on` + `paced by the shell`; MSE time advances past 30 s; `hole.now.eligible=true`, `hole.now.dark=false` while playing |
| 2 | **4K60 fullscreen, GPU, 300 s** | `gpu-present.flag`=`out=2160`, `gpu-video.flag` (empty), `video-fps.flag`, `yt-timeline` | watch `aqz-KE-bpKQ` (2160p60 VP9), `seconds 340`, `interval 2000`, `fullscreen 1` | over the 300 s after 40 s: video-fps.log `path=gpu out=3840x2160 mode=FIFO shared_device=1`; median fps >= 59; sum(dropped)/sum(decoded) <= 1%; `video_gpu_pictures` > 0 with `video_in_place` ~ `video_gpu_pictures` and `video_ring_copies` ~ 0; `intervals_over_25ms` rare; `playback` samples 3840x2160, nonDroppedFrameRate 59-61; gpu-video.log: `device SHARED with the GPU present`, `READY … the present's shared device`, `verify … (1:1)` x3, `now convert on the GPU`; gpu-present.log `device shared with the video conversion`; no `WATCHDOG`, `MISMATCH`, `OFF:` |
| 3 | **theater / inline** | as 2 | same URL, `seconds 150`, fullscreen 0 (default inline; then theater with the `t` key or a theater cookie if the runner has one) | hole on with the inline rect; `hole.now.eligible=true`; GPU `verify … (shrink)` x3 then GPU; fps/drops as gate 2 (report, not a hard gate) |
| 4a | **1080p60** | as 2 | a 1080p60-max VP9 watch URL, 150 s, fullscreen 1 | `verify … (enlarge)` x3 then GPU; fps >= 59, drops <= 1% |
| 4b | **1440p60** | as 2 | a 1440p60-max VP9 watch URL, 150 s, fullscreen 1 | as 4a |
| 5a | **fallback: set-up failure** | `gpu-present.flag`=`out=2160 failsetup`, `gpu-video.flag`=`failsetup`, `video-fps.flag` | as 2, 90 s | both logs `set-up failure forced`; fps lines `path=sdl`; hole on + paced, decoded > 0 (RC7's CPU 4K path plays) |
| 5b | **fallback: own device** | as 2 + `/data/omni/gpu-share-disabled.flag` | as 2, 90 s | gpu-present.log `device sharing refused`; gpu-video.log `device up on queue family` (V2 behaviour); conversions on the GPU; `shared_device=0` |
| 5c | **no flags** | none | watch, 60 s | as s3.1c + the cause fix (gate 1 without yt-timeline: check by eye) |
| 6 | **exit** | after gates 2 and 5b | Exit menu | gpu-video.log `shutdown: GPU objects freed (shared device left to the present)` BEFORE gpu-present.log `teardown (SDL_Quit …)`; live buffers/images/memory 0 |

Isolation if gate 2 fails: 5b (shared device off) → `gpu-video.flag`=`copy` (no imports) → `gpu-present.flag` without
`gpu-video.flag` → no GPU flags (gate 1). The fps line's `video_ring_copies` > 0 with `video_in_place` 0 means the
in-place import was refused (gpu-video.log `import … failed at …`): still correct, one extra copy per picture.

## User checks (TV)
Gate 2: smooth motion, no tearing, no black/stale video area under the controls; gate 3: page over the video correct.
HDR is not part of this plan (the HDR profile switch changes a system attribute and needs the user's OK first).
