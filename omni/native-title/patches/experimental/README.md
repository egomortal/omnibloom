# Experimental Omni native work (not console-tested, not shipped)

Everything in this folder is **built or prototyped but not yet proven on the console**. None of it is in the current
build (s3.4d, `../README.md`). Each folder says what it is, what was tested on the host, and what is still missing.

| Folder | What | State |
|---|---|---|
| [`hdr/`](hdr/README.md) | s3.5-hdr: real HDR10 output on the 4K60 GPU path (title only) | **Built, testing.** Host tests pass; the console run needs a look at the TV. Needs Ex-Box's private RADV archive, which is not in this repository. |
| [`jsc-heap/`](jsc-heap/README.md) | JavaScriptCore without "mini mode" plus `OMNI_HEAP_CAP_V1` (child engine) | **Don't ship yet: warm-load stall.** Faster cold loads, memory back to stock, but the repeat YouTube home stalls. |
| [`swdec-pad/`](swdec-pad/README.md) | `OMNI_SWDEC_PAD_V1`: the software video decoder's heap overflow (child engine) | **Fix pending console test.** Proven on the host; explains the reddit.com page crashes. |
| [`gpu-pages/`](gpu-pages/README.md) | Drawing pages on the GPU: Zink + EGL prototype | **Prototype.** Passes on the host (lavapipe) and links for the PS5; never run on the console. |

The `jsc-heap` and `swdec-pad` changes are in the **child** engine. Release builds keep the child byte-identical to
`7b810ea5…fd717c64`, so either one needs a deliberate child rebuild (with `SOURCE_DATE_EPOCH` pinned, see `hdr/REPORT.md`).
