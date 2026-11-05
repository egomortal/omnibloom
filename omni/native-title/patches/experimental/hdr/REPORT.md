# omni-native-s3.5-hdr: real HDR10 output on the 4K60 GPU path (build only)

2026-11-05. Built from **s3.4d** (s3.4c + `OMNI_DARK_APPEARANCE_EMU_V1`; the GPU, media and title sources are byte-identical to s3.4c's).
- **The console was not used.** It is reserved for the scheduled run (`TEST-PLAN.md`).
- Host figures come from lavapipe (Vulkan on the CPU), so none of them is a PS5 figure.
- Nothing JIT-, security- or vault-related was changed.
- No system profile or other app's profile was touched.

## Status at a glance
| | |
|---|---|
| Title | `out/PPSA99732/eboot.bin` **`59433d64e9fc7625ce86a61dc9e6ccce7f61190c22cdfddf0780efa88b4dbe0d`** |
| `build/eboot.elf` | `565f628b40ea4efc00351449b5e9e411150110d9cd138d3e5432cd8bd73cbffc` |
| Child | `child/omni-engine-child.elf` **`7b810ea5…fd717c64`**, rebuilt and byte-identical (see the `__DATE__` note below) |
| `param.json` / `libc.prx` | `354f191d…` / `e6ff45d1…`, unchanged from s3.4d |
| Private RADV archive | `radv/libvulkan_radeon-hdr-wsi.a` `2bb567da…8a704e`: the shared `1f53ac68…` plus one replaced member, the HDR VideoOut WSI |
| Layout check | PASSED. LOAD sizes in MiB: 97.6, 66.3, 4.3, 49.5, 7.6 |
| Host tests | All pass (details below) |
| Default behaviour | The HDR setting defaults to **Off**, so with no setting saved the output is SDR exactly as in s3.4d. The one exception: pages are told the truth about HDR. A non-HDR display or setting now refuses HDR codec strings that WebKit already refused. |

**Build:** `outputs/build-omni-native-s35-hdr.sh`, run through the build helper.
- It is the s34d recipe plus the HDR host test, `apply_hdr_caps.py` and `prep_s35.py`.
- Progress goes to `build-steps.txt`; the string, symbol and param checks go to `checks.txt`.

## What I found first (these shaped the design)
1. **The HDR declaration in `param.json` is already in Omni's own file. Nothing needed changing.**
   - **The October test:** it changed only `"attribute": 1` → `536870913` (0x20000001), and only in the shared Homebrew Loader profile `/system_ex/app/FAKE00000/sce_sys/param.json` (`outputs/hdr-switch/param-before.json` vs `param-after.json`, `profiles.h`).
   - **What that bit means:** 0x20000000 is ATTRIBUTE flag 30, "This Application Supports HDR" (psdevwiki Param.sfo; the PS5 `attribute` field keeps the same bit).
   - **Omni's file:** `sce_sys/param.json` already has `"attribute": 1644167168` = **0x62000000**, so the bit is set.
   - **Result:** `prep_s35.py` makes `build.py` assert the bit, which `checks.txt` shows (`attribute 0x62000000 HDR bit SET`). The file itself is unchanged (`354f191d…`). No other profile was touched.
2. **The stock PS5 RADV cannot output HDR10.** `PS5_Mesa/src/vulkan/wsi/wsi_common_videoout.c` offers only B8G8R8A8 UNORM/SRGB in `SRGB_NONLINEAR`, and registers its buffers as `B8G8R8A8_SDR`.
   - **Ex-Box already solved this.** Its private WSI member (`nxe-ps5/bigapp/private/presenter-hdr-test-20261103`, `wsi-hdr.diff`) adds `A2B10G10R10_UNORM_PACK32` + `VK_COLOR_SPACE_HDR10_ST2084_EXT`, registered as VideoOut's RGB10A2 PQ format `0x8100070422000000`. Its buffer sets are cached per (size, format), and it exposes `exbox_presenter_probe()` for the output range.
   - **Proven on the console:** PPSA99736 console run 3 went SDR (format 44) → PQ (format 64, space 1000104008) → SDR, with a new swapchain each time, `oldSwapchain` and then destroy. It ended with a clean exit, and the owner saw the brightness change.
   - **What s3.5 does:** it links that exact archive (copied and hash-pinned; `radv/wsi-hdr.diff`, `scanout_policy.h`, `THIRD_PARTY.md` are copied alongside).
3. **The frozen child refuses HDR, and VP9 does not carry its transfer function.**
   - **The refusal:** `OmniMediaCaps.h` in the child returns false for `vp09.*` with transfer 16/18 ("PQ / HLG: no HDR output path"). `decodingInfo` refuses any HDR field.
   - **VP9's colour:** VP9's colour comes only from the keyframe colour space (`vp9KeyFrameColour`: BT.2020 → matrix 9, transfer unknown).
   - **The consequence:** both are handled title-side, because the child stays 7b810ea5 (sections 3 and 5 below).
4. **The child is only byte-identical on Nov 4.** The engine embeds `__DATE__` (rodata `"Nov  4 2026"`). The first build, on Nov 5, linked `5553dec9…`, which differed from 7b810ea5 only in that date. This was confirmed by comparing the two files: no input had changed since s3.4d (`hdr-probe/probe3.txt`).
   - **The fix:** the build compiles the child's objects with `SOURCE_DATE_EPOCH=2026-11-04 12:00Z`, and the child is 7b810ea5 again (checked by the build).
   - **Future child rebuilds need the same setting.** This affects every child rebuild from now on, not just this build.

## Design
```
VP9.2 / HEVC Main10 (hardware decode, 10-bit two-plane low-aligned) -> holeSplitPlanes (CPU, unchanged) -> planar 10-bit
   -> OmniGpuVideo V4, ONE compute pass: RGBA8 layer (as before, byte-identical) + PQ layer (A2B10G10R10, same stride)
        HDR10 (BT.2020 NCL + ST2084): R'G'B' kept as they are (already PQ; no second encode, no tone mapping)
        HLG (ARIB B67): inverse OETF -> BT.2100 OOTF (gamma 1.2 @ 1000 nits) -> PQ
   -> hole-punch stages both layers + a source-info word (bits | transfer | primaries | PQ valid)
page (Skia) -> SDL surface -> OmniGpuPresent V4:
   SDR output  : canvas -> blit -> BGRA8 swapchain (unchanged)
   HDR10 output: canvas -> PQ pass (sRGB -> BT.2020 PQ, SDR white 203 nits) -> opaque video runs overwritten from the
                 PQ layer (passthrough) -> blit -> A2B10G10R10 / HDR10_ST2084 swapchain
```

### 1. The HDR declaration
This is already in Omni's own `param.json` (see finding 1), and the build asserts it on every run.

### 2. HDR10 output (`OMNI_GPU_PRESENT_V4`, `src-title/OmniGpuPresent.cpp` + `OmniHdrPolicy.h`)
**Start-up log:** every surface format and colour space the surface offers is logged (as before). The HDR10 choice is deliberate:
- A2B10G10R10 first, then A2R10G10B10, both only in `HDR10_ST2084`;
- linear BLIT_SRC on the PQ image and BLIT_DST on the swapchain format;
- a UNORM SDR format, so one canvas serves both outputs;
- V2's PQ-pass self-check, which must be within 1 code.

When all of these pass, the log says `HDR: armed (on|auto): HDR10 format N …`. Otherwise it says why, and the output stays SDR.

**Swapchains:** they all go through `makeSwapchain()`, in Ex-Box's order: `oldSwapchain`, then destroy the old one.

**Fallback (`OmniHdrPolicy::switchOutput`):**
- A refused HDR10 swapchain is followed at once by an SDR one. Vulkan retires the old swapchain even when the new one fails, so a new SDR swapchain is always made.
- If the first HDR10 frame fails, the output also goes back to SDR and the first frame is presented again.
- Only an SDR refusal is fatal. That keeps s3.4's existing rule: the present fails, so Omni closes cleanly.
- The log says `HDR: the HDR10 output was refused (…): SDR output`, and HDR stays off for the run.
- The flag word `hdrfail` refuses HDR on purpose, for the console fallback test.

**Output range:** 30 presents after each swapchain change, the log records `VideoOut output range N` (1 SDR, 2 HDR), from the WSI member's `exbox_presenter_probe`.

**Memory:** the PQ scanout set is a second registered 4K set, about 160 MiB of direct memory. It exists only once HDR has been used. If it does not fit, the WSI refuses with OUT_OF_DEVICE_MEMORY and the output falls back to SDR.

### 3. The 10-bit source path (`OMNI_GPU_VIDEO_V4` + `OMNI_GPU_HDR_V1`)
**The shader:** `omni_yuv_to_rgb.comp` gains binding 2 (the PQ layer) and `hdrMode` / `hdrBase` / `hlgPeak`, in the old padding, so the push block stays 80 bytes.
- The RGBA8 output is unchanged, and the test checks this byte for byte.
- glslang 15.1, `spirv-val` clean; the header is in `engine/media/OmniGpuVideoShader.h`.

**When the PQ layer is made:** the hole-punch asks for it (`OmniHwService.cpp`, title copy only) for a 10-bit BT.2020-NCL source with transfer 16 or 18, while the present's HDR state is ≥ 1 (Auto armed, or HDR now).
- **VP9 without a transfer:** VP9's 10-bit BT.2020 with no transfer is treated as PQ. That is the web's VP9.2 HDR10, for example YouTube's `vp09.02.51.10.01.09.16.09`.
- **Kill switch** for that inference: `/data/omni/hdr-vp9-infer-disabled.flag`.
- **HEVC** carries its transfer in the VUI, so no inference is needed.

**Where it is written:**
- The layer goes into the layer's `hdrPx`, imported once. Its import is forgotten on growth and in the destructor, as for `px`.
- The verify pass of the first 3 pictures writes it too.
- With no GPU video (no `gpu-video.flag`, or a verify mismatch), there is no PQ layer, and HDR10 video is shown through the SDR mapping. **HDR passthrough needs `gpu-video.flag`.**

**Pipeline depth** is unchanged. The picture goes through one conversion on the pace thread, about 2.5 vblanks ahead, as in s3.4c.

### 4. The UI in HDR
The page and menus go through V2's checked PQ pass: the sRGB EOTF, the BT.709→BT.2020 matrix, then PQ at **203 nits** SDR white (BT.2408).

**What is copied over it:**
- The opaque video runs only, taken from the PQ layer (a buffer→image copy into the PQ image, using a retained region vector).
- Translucent "mix" pixels (controls over the video) keep the SDR mapping of the 8-bit video. This is a small, known approximation.
- **Where it lives:** `recordSourcePq()`. The design follows Astra's `20261104-gpu-source-pq`, with two changes:
  - the PQ layer is made on the GPU, not by the 7.8 ms CPU converter;
  - mix pixels no longer force the whole frame to SDR, so the video does not dim whenever the controls appear.

### 5. The setting (Off / Auto / On) and what sites are told
**The setting:** the mode comes from Astra's R3-084 file `/data/omni/video-hdr-preference.txt` (`<revision>\t<off|auto|on>\n`, `OmniHdrPreference`).
- **No saved setting:** Off. Legacy behaviour still works: the flag word `hdr` + `hdr-auto.flag` means On, and `hdrauto` means Auto.
- **A bug fixed on the way:** s3.4 computed `hdrWanted` before reading the preference, so a saved On never reached the swapchain.

**The modes:**
- **On:** HDR10 output from the first frame.
- **Auto:** SDR until a video with a PQ layer covers at least 90% of the canvas (a full-width 2.39:1 letterbox counts) for 0.5 s; then HDR10. Back to SDR 1.5 s after the last such frame. A 0.4 s gap, such as a short overlay or a seek, does not switch.
- **A setting change applies at the next start.**

**What sites are told (`OMNI_HDR_CAPS_V1`, shell, `tools/apply_hdr_caps.py`):** a document-start script in all frames. HDR counts as "capable" when `omni_gpu_present_hdr_state() >= 1` at start (On with HDR10 output, or Auto armed).

| API | When capable | When not |
|---|---|---|
| `matchMedia` `(dynamic-range: high)`, `(video-dynamic-range: high)`, `(color-gamut: p3 / rec2020)` | true | false |
| `screen.colorDepth` / `pixelDepth` | 30 | unchanged |
| `MediaSource.isTypeSupported`, `canPlayType` with `vp09.*` transfer 16/18, `av01…16/18`, or `eotf=` | the frozen child is asked about the same stream with transfer 01, and its answer is returned | false / `""` |
| `addSourceBuffer` / `changeType` | gets the transfer-01 form (the child would refuse 16/18) | unchanged (the child refuses, as before) |
| `mediaCapabilities.decodingInfo` with HDR fields | asked without them; `configuration` is returned as given | `supported: false` |

**How YouTube decides** (Mozilla bug 1751087, which quotes YouTube's player):
- the display check: `matchMedia('(dynamic-range: high)').matches || (screen.pixelDepth > 24 && matchMedia('(color-gamut: p3)').matches)`;
- then the codec check: `isTypeSupported('video/webm; codecs="vp09.02.51.10.01.09.16.09.00"')` (the Chrome HDR example uses the same form).

With s3.5 both checks succeed only when the output can really show HDR10.

### 6. HDR metadata: skipped
- `sceVideoOutSysSetHdrMetadata` has no ABI from public source.
- The WSI member has no metadata path.
- RADV's DRM-path default metadata does not apply to VideoOut.

As a result, no MaxCLL, MaxFALL or mastering display data is sent; the TV uses its own defaults for ST 2084. This is documented, not guessed.

### 7. Measurement (`OMNI_VIDEO_FPS_V3`)
`video-fps.log` keeps every V2 field and adds:

| Field | Meaning |
|---|---|
| `out_mode` | `SDR` or `HDR` |
| `src_tf` | `PQ`, `HLG`, `SDR`, or `-` when no video was staged in the last 1.5 s |
| `src_bits` | `8`, `10` or `-` |
| `hdr_setting` | `off`, `auto` or `on` |
| `hdr_switches` | Auto's swapchain switches so far |
| `pq_frames` | presents with passthrough runs, this second |
| `video_pq_layers` | PQ layers made on the GPU, this second |

The header line says `build=omni-native-s3.5-hdr OMNI_VIDEO_FPS_V3`.

## What was reused, and from where
| From | What |
|---|---|
| s3.4d (= s3.4c GPU/media/title sources) | everything; the diffs are in `diffs/` (present 532 lines, video 132+40, hwservice 107, shader 63) |
| Ex-Box `private/presenter-hdr-test-20261103` | the private RADV archive (HDR VideoOut WSI member: formats, PQ registration, per-format set cache, `exbox_presenter_probe`); the swapchain switch order. Copied, not edited. |
| Astra `codex-ui/20261104-gpu-source-pq` | the overwrite-runs-after-PQ-pass design (`recordSourcePq`), the hdrPx forget-on-growth rule |
| Astra `codex-ui/20261103-r3-084-hdr-ux` + CLEAN4 | the HDR setting file and its Off/Auto/On semantics (`OmniHdrPreference.h`, unchanged) |
| Omni `OmniHdrColour.h` (s3 tree) | the double reference `yuv10()` / `pack()` / `pqEncode` for the tests; the PQ constants |
| s3.2 V2 HDR phase 2 | the PQ pass, its self-test, the 203-nit white |

Licence: GPL-3.0-or-later. The WSI member is MIT (Mihawk), and its notice is kept in `radv/THIRD_PARTY.md`.

## Host tests (all pass)
### The new HDR test (`hosttest/hdr_test.cpp`, log `hosttest/wsl/hdr-test.log`, run by the build in WSL)
19 PASS, 0 FAIL.

**V: the PQ layer against a double-precision reference.** HDR10 is checked against `OmniHdrColour::yuv10`; HLG against BT.2100 in double. Every case is **worst 1 code**, and the RGBA8 layer is byte-identical to a pass without PQ.

| Case | Pixels off by 1 |
|---|---|
| 2160 1:1 | 487 / 8.3 M |
| 1080p → 2160 | 508 |
| 1440p → 2160 | 413 |
| 2160, from a two-plane 10-bit (P010-style, low-aligned) picture | 487 |
| 1080p two-plane → 2160 | 508 |
| 1080p full range | 37 / 2.1 M |
| HLG 2160 | 33,865 |
| HLG 1080p → 2160 | 34,432 |

**N: no per-frame allocation in the video path.** 3000 HDR conversions over 6 layers with remaps:
- live buffers 15 → 15 and memory 15 → 15;
- cache at most 12 of 16.

**P: the HDR10 present, 2160 and 1080 canvases:**
- the video runs equal the PQ layer **exactly** (passthrough);
- page pixels are within 1 code of the 203-nit SDR→PQ reference;
- **SDR white = PQ code 594 = 202.9 nits**;
- mix pixels and the frame without a PQ layer use the SDR mapping (the fallback).

**Q: no per-frame allocation in the present.** 3000 HDR presents:
- live buffers 6 → 6, images 2 → 2, memory 8 → 8;
- region vector capacity constant;
- every frame counted;
- teardown 0/0/0.

**L: the policy:**
- 9 setting cases;
- the format choice: the private WSI gives A2B10G10R10, the stock WSI gives none;
- the full-screen rule;
- Auto timing: on at 512 ms, off 1.5 s after the last frame, no switch on a 0.4 s gap;
- the swapchain fallback: HDR refused → SDR at start and at a switch; `hdrfail` keeps SDR; both refused → fatal.

### Other tests
- **The s3.4 suite, unchanged and all passing:**
  - GPU video: 23 PASS lines, fallback, shared device;
  - present P1–P4 and its fallback, plus pair;
  - SEC 17/17, VAULT OS-002 51/51, VAULT 103/103, the SDK `-Werror` compile;
  - pointer-cross 41/41.
- **`OMNI_HDR_CAPS_V1` (`hosttest/hdr_caps_test.cjs`, log `hosttest/wsl/hdr-caps.log`, run on the script extracted from the built `OmniBrowser.cpp`): 26/26.** It models the child's refusals and checks YouTube's own conclusion with the setting off and on.
- **Eligibility is unchanged.**
  - `OmniDarkPages.h` is byte-identical to s3.4d's (`9b95b93a…`), and the child is identical.
  - The headless Chromium `eligibility_test.cjs` gives 9/10, the same as s3.4d's file. Its one FAIL is the expectation of the unused 4k60 patch 04 (a dark page is never inverted). s3.4 chose `OMNI_DARK_VIDEO_PLANE_V1` instead, so this is not a regression.
- **Compilation:** in the title link, the only warning in the GPU objects is the existing `holeBlendPixel` one. Both new modules compile clean in their console form with `-Wall -Wextra`.

## Limits and risks (read before the console run)
- **Not yet shown on this console:** HDR10 through Omni's present, and Auto's runtime switching. Ex-Box proved the WSI and the switch order, but not with a 4K60 video load.
- **Destroying the old swapchain:** while its next image is acquired but not yet presented, the old swapchain is destroyed. Vulkan allows this, and Ex-Box destroyed the old one right after creating the new.
- **The extra scanout set:** about 160 MiB of direct memory, as above.
- **Mix pixels over HDR video are SDR-mapped:** a slightly dimmer gradient under translucent controls.
- **The HDR setting and the page capabilities are read at start.**
- **No HDR metadata** (section 6).
- **On the console's own HDR setting:**
  - With the PS5 set to HDR "Always On", VideoOut reports range 2 even for SDR (seen in Ex-Box run 3), so the TV's HDR badge may already be on in SDR. Brightness is then the visible difference.
  - With "On When Supported", the badge should appear only with HDR10 output.
- **YouTube must actually serve VP9.2:** this depends on the page script being installed and the child accepting the transfer-01 form. `GPU HDR decision … transfer 16 (inferred…)` in the hole-punch log and `src_tf=PQ src_bits=10` in the fps lines are the evidence.

## Files
- `engine/media/OmniGpuVideo.{h,cpp}`, `OmniGpuVideoShader.h`, `OmniHwService.cpp`
- `src-title/OmniGpuPresent.cpp`, `OmniHdrPolicy.h`
- `shader/omni_yuv_to_rgb.comp` (+ `.spv`)
- `tools/apply_hdr_caps.py`, `tools/prep_s35.py`
- `hosttest/hdr_test.cpp`, `OmniHdrColour.h`, `hdr_caps.js`, `hdr_caps_test.cjs`
- `radv/` (the archive and its provenance), `diffs/`, `TEST-PLAN.md`, `SHA256SUMS.txt`
- `../build-omni-native-s35-hdr.sh`
- `hdr-probe/` (the read-only tree probes)
