# Omni WebProcess SIGBUS in the memloop: heap overflow in the software video path (2026-11-05)

Host-side only; the console was not touched (lock OMNI_S34E belongs to the other agent).

## 1. Short answer
- **It is a real bug, not memory exhaustion and not a stack guard.** It is a **heap buffer overflow** in
  `OmniMedia::VideoDecoder::next()` (`engine/media/OmniVideoDecoder.cpp`, the software progressive-video path).
  - Each software-decoded frame is converted with `sws_scale` into a `std::vector` of exactly `w*h*4` bytes, stride `w*4`.
  - FFmpeg 7.1.5's x86 4:2:0 to RGB converters write whole 16-pixel groups. They write **up to 32 bytes past the end** of that buffer.
  - Those bytes are opaque RGBA pixels, and they land on the next libc heap chunk's header.
  - The next `malloc`/`free` that walks that chunk uses a non-canonical "pointer" made of pixels. That causes a general-protection fault, which the kernel reports as SIGBUS code 3.
- **The trigger is reddit.com** (memloop pages 16 and 34). Its feed starts many small autoplay H.264 files at once. The hardware decode service runs out of instances (`service open failed rc=0x811d0100 at CreateDecoder`). The remaining files fall back to the software player, the only path that converts into an unpadded buffer.
- **Fix: `OMNI_SWDEC_PAD_V1`.** The software path now converts into rows padded to 16 pixels (+64 bytes) and packs them afterwards, as `OmniPacketDecoder` and `OmniHwClient` already do. It is proven on the host, and a candidate child is built: `child-swpad/` (`10509c9c…`). It needs a console check.

## 2. The crash record (OMNI_CRASH_V2), decoded
6 fatal records over 3 memloop runs (s3.4e child, stock `7b810ea5`, s3.4f child). Every one is in a WebProcess, and every time the page is reddit.

| Run | pid | thread | rip (module 0x8_0000_0000 + off) | chunk-header word (pixels) |
|---|---|---|---|---|
| e | 417 | worker | +0xb283e | `0xff0094ddff7874b9` |
| e | 420 | worker | +0xb283e | `0xff0094ddff6f43b9` |
| stock | 430 | **main** | +0xb3933 | `0xff8099e3ff8099e3` |
| stock | 433 | worker | +0xb283e | `0xff0094ddff75ecb9` |
| f | 455 | **main** | +0xb283e | `0xff0099e3ff7f0281` |
| f | 457 | worker | +0xb283e | `0xff0094ddff7854b9` |

**Context layout.** The handler printed "layout not found", but the raw words are a FreeBSD amd64 `mcontext` starting at word 8:
- rdi = w9, rsi = w10, rdx = w11, rcx = w12, r8 = w13, r9 = w14, rax = w15, rbx = w16, rbp = w17;
- r10–r15 = w18–w23;
- **trapno = low half of w24 = 9 (T_PROTFLT)**; mc_addr = w25 = 0; err = w27 = 0;
- **rip = w28**, cs = 0x43, rflags = w30, **rsp = w31**.

**What the registers show:**
- **trapno 9 is a #GP.** FreeBSD turns a #GP into SIGBUS / BUS_OBJERR (code 3) with si_addr = rip. That is why "address == rip", and why mc_addr is 0 (so the handler's `mc_addr == si_addr` match fails).
- **The fault is not a page fault.** An mmap'd page that can't be backed (direct/flexible memory exhaustion) would give trapno 12 with a real data address. A stack-guard hit would show rsp at a guard page. Here rsp is normal (`0x7ee…`).
- **The faulting code is the libc allocator.** Every record has the global `0x80025f7b8` (the allocator state) in rdi, rbx or r14. The module at `0x8_0000_0000` is a system sprx (libkernel or libSceLibcInternal), and this tree has no symbols for it.
- **The free path (pid 430).** rsi = chunk, r9 = chunk + 0x10 (the user pointer). rdx = the chunk's size word = `0xff8099e3ff8099e3`, which is two opaque pixels. rcx = rdx & `0xff00fffffffffff8` (mask in r8).
- **The malloc path (+0xb283e, 5 of 6 records).** rax = a chunk-header word made of pixels (low tag bit set); r14 = rax & ~1; r9/r10/r11 = the allocator's flag masks.
  - The e/f runs also have `rsi = 0xaf`, `rdx = 0xafafafafafafafaf`, and rcx = a return address inside the module: the allocator's fill of a new chunk.
  - In the stock run r12 = `0x205012731`, which symbolises (anchor − nm(anchor), `addr2line` on `omni-ytprof/child-base/omni-engine-child-unstripped.elf`) to **`av_malloc` + 0x31**, just after `call posix_memalign`. So that allocation was FFmpeg's (anchor `0x2009b1090` = `runChild(int, char**)`).
- **The header words are pixels.** Every word has 0xff in every 4th byte (alpha), across 3 runs and 3 builds. The same tones recur (`…0094dd…`, `…0099e3…`), consistent with the same reddit videos.
- **No frames.** The handler found no register layout, so it did not scan the stack ("stack scan from/to" equal). So there are no frames to give beyond rip, the registers and `av_malloc` from r12.

## 3. Correlation with process, page and memory samples
- **Only the processes that ran the software video player crashed.** Each crashed WebProcess logged 6–15 lines of "the hardware decoder did not open … the load starts again on the software player", plus software `OMNI PROGRESSIVE: first frame` lines.
  - No other process in the 15 s34e steps logged either (ytsoak, jssoak, feature, scroll, media, watch, shorts, portblock: 0).
  - All 6 crashed processes did (6/6).
- **The page is reddit both times.** The title log puts both deaths at `YTTL run 16/34: https://www.reddit.com/` (~370 s and ~770 s, once per pass). That gives the regular "10–14 minutes": it is the second pass reaching reddit.
- **The crash comes right after reddit's media starts.** The last child lines before each FATAL are reddit's progressive H.264 starts: sizes 170x96, 96x170, 96x166, 96x120, 96x112 and 360x424, plus a 4.5 MB file. Software fallback was chosen for most of them.
- **RSS was not near any budget.**

  | Run | Crashed WebProcess | RSS at death | Its peak |
  |---|---|---|---|
  | stock | 430 | 499 MB | 532 MB |
  | stock | 433 | 590 MB | 654 MB |
  | e | 417 | 941 MB | 977 MB |
  | e | 420 | 641 MB | 894 MB |
  | f | 455 | 554 MB | 859 MB |
  | f | 457 | 636 MB | 849 MB |

  - The same builds' **ytsoak WebProcess ran 20 min at up to 1305 MB without a crash.** So the ~448 MiB figure is not a hard kill line, and size is not what kills the process.
  - The title process (shell/hole-punch) peaks at 2.3–3.1 GB during 4K YouTube and returns to ~993 MB after each page. That release works, and the title never crashed.
  - The `net` process falls from 280 MB to 65 MB.

## 4. Proof on the host: FFmpeg 7.1.5 swscale overruns an exact buffer
`swstest/swstest.c` (`build-omni-memloop-swstest.sh`) is built against a host build of the **same FFmpeg 7.1.5 tarball**, with the same x86 asm switches as the PS5 build (`HAVE_X86ASM`, `MMXEXT_INLINE`, `SSSE3/AVX2_EXTERNAL`). It converts with the decoder's exact call: same size, `SWS_BILINEAR`, stride `w*4`, buffer `w*h*4`, followed by a guard band. Full output: `swstest-summary.txt`.

| Source format | Exact buffer (today) | Padded stride (fix) |
|---|---|---|
| yuv420p / yuvj420p / yuv422p → RGBA or BGRA | **996 of 3535 sizes overflow, by up to 32 bytes** (e.g. 360x424 +32, 170x96 +24, 1080x1920 +32, 639x360 +4) | 0 of 3535 |
| yuv420p10le, yuv444p, nv12 | 0 | 0 |

- H.264 frames are yuv420p or yuvj420p. So every reddit video whose width is not a multiple of 16 overruns on every frame.
- A 24–32-byte overrun is exactly "the next chunk's header plus 16 bytes", which is what the registers show.
- `OmniHwClient::convert` and `OmniPacketDecoder` already pad to 16 pixels (`OMNI_HOLEPUNCH_COLOUR_V1`, written for the under-write side of the same quirk). The software progressive path (`OmniVideoDecoder.cpp`, unchanged since s1; s1 == s3) was never given that padding.

## 5. The fix and the candidate
**Change: `tools/apply_swdec_pad.py`** (one edit in `engine/media/OmniVideoDecoder.cpp`, child only; CRLF preserved):
```
const size_t row = size_t(w) * 4, stride = (size_t(w) + 15) / 16 * 16 * 4;
output.rgba.resize(stride * size_t(h) + 64);
... sws_scale(..., planes, {int(stride)}) ...
if (stride != row) for (r = 1..h-1) memmove(dst + r*row, dst + r*stride, row);
output.rgba.resize(row * size_t(h));
```
- The player's `rgba.size() == w*h*4` checks still hold.
- Capacity is only up to 15 pixels per row larger.

**Candidate: `child-swpad/omni-engine-child.elf`, sha `10509c9c229ea434…`** (165,005,200 bytes; unstripped copy alongside).
- **Built by:** `build-omni-memloop-fix.sh`, a private overlay of s3. It is the exact s3.4d child step that reproduces `7b810ea5`, plus `OMNI_SWDEC_PAD_V1` only.
- **Unchanged:** no mini-mode change; `launcher-child.cpp` and sec-connect unchanged; `SOURCE_DATE_EPOCH=1793793600`.
- **Build:** ninja ran 26 steps (0 new warnings), then the link.
- **Checks (`checks.txt`):**
  - CRASH_V2, PNA, LOCALHOST, JIT_V3 and close-events strings match the base;
  - `VideoDecoder::next` now calls `memmove` after `sws_scale`.
- **On s3.4f:** the same `apply_swdec_pad.py` can be applied on top of the s3.4e/f no-mini-mode tree. It is independent of that change.

Not deployed. Nothing on the console was changed.

## 6. Console repro plan (shorter than 14 min), for whoever holds the lock
1. **Deterministic fixture (about 2 min per child).**
   - Serve a local page with 8–12 muted, looping, autoplay `<video>` elements: H.264 yuv420p mp4 at 170x96, 360x424 and 639x360 (widths not multiple of 16).
     - Generate with `ffmpeg -f lavfi -i testsrc2=s=170x96:r=30 -t 20 -c:v libx264 -pix_fmt yuv420p -movflags +faststart`.
   - Put `progressive-holepunch-disabled.flag` in place, so every file takes the software player (no dependence on the decoder being busy).
   - **Expect:** stock `7b810ea5` dies with the same `FATAL … 0x0a … code=3` (rip module+0xb283e/0xb3933) within a minute or two. `child-swpad` plays for 10 minutes.
2. **Real site (about 6 min).** lannav with reddit only: `MEMURLS=['https://www.reddit.com/']`, MEMSEC 30, MEMPASS 10. `run_s34e.py` hard-codes the list, so it needs a one-line env override.
   - The stock child crashed on reddit in both passes of all 3 memloops.
3. **Full memloop on `child-swpad`** (and on f + pad). Pass = no FATAL and `webprocess_crashed` null.

## 7. Other findings (not the cause, worth doing)
- **Crash handler, for diagnostics.** When no `mc_addr == si_addr` match is found, also match `mc_rip == si_addr` (a #GP or misaligned SIGBUS gives si_addr = rip and mc_addr = 0). With that, it would print the registers and walk the stack, which here would have given the 32 frames directly.
  - The layout is the one above: mcontext at word 8, rip at word 28, rsp at word 31, trapno in word 24.
  - This is in the crash setup that runs at startup, so it is left for a separate, reviewed change.
- **Memory-pressure handler.** WebKit's handler is still blind (`memoryFootprint()` = 0, ytprof REPORT §4), so caches only shrink by their own limits. A working reading is worth doing, but this crash happened at 0.5–0.9 GB while 1.3 GB ran clean, so it would not have prevented it.
- **The software fallback itself.** When the decode service is out of instances, a page full of autoplay previews falls back to CPU decode plus RGBA conversion per video. Once safe, consider capping concurrent software progressive decoders (e.g. only visible videos, or at most 2–3).

## Files
- `REPORT.md` (this file).
- `swstest/swstest.c`, `swstest.txt`, `swstest-summary.txt`: host overflow proof.
- `tools/apply_swdec_pad.py`, `child-swpad/`, `build-steps.txt`, `checks.txt`, `ninja.log`, `child-build.log`: the candidate.
- `src-s3/`: read-only copies of the sources inspected. `grep1-5.txt`: look-up output.
- Build scripts in `outputs/`: `build-omni-memloop-grep1..5.sh`, `build-omni-memloop-swstest.sh`, `build-omni-memloop-fix.sh`.
