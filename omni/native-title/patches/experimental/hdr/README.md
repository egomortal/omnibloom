# Experimental: HDR10 output on the 4K60 GPU path (s3.5-hdr)

> **Not yet console-tested. Not part of any release build.** Built and host-tested on 2026-11-05; the console run in
> `TEST-PLAN.md` (steps 2-4 need someone looking at the TV) has not happened yet.

**s3.5-hdr** = s3.4d + real HDR10 output (title `eboot.bin` `59433d64…8b4dbe0d`; child unchanged, `7b810ea5…fd717c64`).
With no HDR setting saved it behaves exactly like s3.4d (SDR). Full design and results: [`REPORT.md`](REPORT.md).

- **Video:** `OmniGpuVideo` V4 converts 10-bit VP9.2 / HEVC Main10 in one compute pass into the usual RGBA8 layer plus a
  PQ layer (A2B10G10R10). HDR10 is passed through as is; HLG is converted to PQ (BT.2100 OOTF).
- **Present:** `OMNI_GPU_PRESENT_V4` picks an A2B10G10R10 / `HDR10_ST2084` swapchain when the HDR setting and the display
  allow it; the page is drawn in PQ with SDR white at 203 nits and video runs come straight from the PQ layer.
- **Pages:** `OMNI_HDR_CAPS_V1` (`tools/apply_hdr_caps.py`) tells pages the truth about HDR support.
- **Package:** `param.json` already declares HDR (attribute `0x62000000`); `build.py` asserts it, nothing is changed.

## Not in this repository: the private RADV archive

The build links **Ex-Box's private RADV archive** `libvulkan_radeon-hdr-wsi.a` (sha256
`2bb567dab75d52ae30f0ba157d701f60b368a2f1d451bdd358dc837b5e8a704e`): the shared PS5 RADV build (`1f53ac68…`) with one
member replaced, `wsi_common_videoout.c.o`, Ex-Box's HDR VideoOut WSI (adds `A2B10G10R10_UNORM_PACK32` +
`VK_COLOR_SPACE_HDR10_ST2084_EXT`). It is a binary from Ex-Box's private tree, so it is **not committed**, and neither
are its WSI diff and notices. `build.py` refuses to link unless `radv/libvulkan_radeon-hdr-wsi.a` next to it has exactly
that hash, so without the archive this folder documents the change but does not build.

## Files

| Path | What |
|---|---|
| `build/build-omni-native-s35-hdr.sh` | the s34d recipe + the HDR host test, `apply_hdr_caps.py` and `prep_s35.py` (private overlay, title only) |
| `build.py`, `tools/prep_s35.py`, `tools/apply_hdr_caps.py` | title build (with the RADV hash check), source prep, the page-side caps patch |
| `engine/media/`, `src-title/`, `shader/` | the changed video/presenter sources and the compute shaders (`OmniGpuVideoShader.h` is generated from `shader/omni_yuv_to_rgb.comp`) |
| `diffs/` | the same changes as diffs against s3.4d |
| `hosttest/` | `hdr_test.cpp` (19/19 on lavapipe in WSL: PQ layer within 1 code of a double-precision reference, no per-frame allocation, HDR10 present), `hdr_caps_test.cjs` (26/26, node) |
| `REPORT.md`, `TEST-PLAN.md`, `SHA256SUMS.txt`, `checks.txt` | build report, the console plan, hashes and string/symbol checks (paths scrubbed) |

The other host tests (`gpuvideo_test.cpp`, `pair_test.cpp`, `eligibility_test.cjs`, …) are the s3.4 copies in `../../s34/hosttest/`.
