# Launch build: title rc2 + engine child rc4 (2026-11-10), now rc5 (2026-11-11)

**The launch build is now rc5** (`rc5/README.md`): rc2 + the YouTube attestation guard and a one-time cache reset (title), rc4 + the network-cache blob copy (child). It fixes YouTube stopping at 1:00. Everything below describes rc2 + rc4, which rc5 is built on and which stays the rollback.

The Omni build for the November 12 release: **title rc2** (`eboot.bin`) with **launch child rc4**
(`omni-engine-child.elf`). Both are console-tested together (YouTube start 13.7 s, HDR10 on the GPU at 59.94 fps
with 0 dropped, 4K60 SDR 0.15% dropped, no crashes on the reddit loop, port-block 65/65).

| | sha256 |
|---|---|
| title rc2 `eboot.bin` | `100236b331988aeef6afd7f5b3dade756ee8982022edf9bcfb191ace92f51fc7` |
| launch child rc4 | `e48c0001a9f97c6abdf17631b0ae051fe77c1bb31c0c4b25ab18dd409df84a00` (165 414 800 B) |
| rollback: s3.4d title / child | `ca22b2e4…f7d26a41` / `7b810ea5…fd717c64` |

Every build uses `SOURCE_DATE_EPOCH=1793793600`. Children are linked on ext4, copied out and compared byte for byte;
a re-strip of the unstripped link equals the shipped child.

## What is in it

**Title** = s3.4d + s3.5 HDR10 output + `OMNI_GPU_VERIFY10_V1` + `OMNI_HDR_PRESENT10_V1` + `OMNI_ABR_SWITCH_V1` +
jank/paint-hold instrumentation + the title half of `OMNI_ACK_V1`.

**Child** = s3.4g JavaScriptCore (no mini mode, heap cap, malloc-mini) + the net5 network fixes + HTTP/2 off +
`OMNI_SWDEC_PAD_V1` + paint-rects V1/V2 + ack pacing + `OMNI_MEMPRESSURE_V2` + the switch layer
(`tools/apply_launch_switches.py`: `OMNI_ACK_SWITCH_V1`, `OMNI_NET5_SWITCH_V1`, `OMNI_S34G_SWITCH_V1`,
`OMNI_NET_SWITCH_LOG_V1`). rc4 compiles the JavaScript bytecode cache and the HTTP/2 header-buffering fix
**default-off** (`OMNI_NET_JSCACHE_OPTIN_V1`, `OMNI_NET_HDRBUF_OPTIN_V1`): both stalled YouTube on the console.

The `experimental/` HDR, `jsc-heap` and `swdec-pad` work is in this build. GPU page drawing (`experimental/gpu-pages`)
is not.

## Folders

| Folder | What |
|---|---|
| `title/` | The title workspace as built: `build.py`, `child_build.py`, `make_link_command.py`, title sources (`src/`, `src-title/`: GPU presenter, HDR policy, PQ shaders), `s34-entry/` + `s34-media/` (shell entry and media files), `engine-patches/`, `shader/`, `fetch/` (HDR headers), `radv/` (the RADV HDR scanout change; see its README), `sce_sys/param.json`, `tools/` |
| `webkit/00-omni-s3-base.patch` | Every Omni change to WebKit 539e0189f up to the s3 base tree (74 files) |
| `webkit/10-launch-title.patch` | The title build's changes on top of s3 (`engine/` and `webkit/`, 30 files) |
| `webkit/20-launch-child-rc4.patch` | The child rc4 build's changes on top of s3 (`engine/` and `webkit/`, 30 files) |
| `tools/` | The switch layer, `additivity.py` (union check), `elfguard.py` (packaging guard), `ack_switch_test.cpp` |
| `tests/` | Child unit tests: ack order/pace/sink, hdrbuf, jank sink, paint-rects |
| `rc5/` | The rc5 changes: `title/OmniYtGuard.h`, `child/apply_nc_blob_copy.py`, their tests, results |
| `../build/build-omni-launch-*.sh` | The build recipes: title (`eboot`), launch child, fallback child |

Patches 10 and 20 share the s3 base but use different versions of `OmniBrowser.cpp`, `OmniPages.h`,
`CurlContext.cpp` and `CurlRequest.cpp`, so apply each to its own copy of the tree.

## Switches (flag files in `/data/omni/`)

No flag files are needed for the launch defaults.

| Off switch | Turns off |
|---|---|
| `abr-switch-disabled.flag` | the ABR quality-switch queue (title) |
| `hdr-present10-disabled.flag` | the GPU 10-bit HDR present (back to the CPU path) |
| `ack-off.flag` / `ack-pace-off.flag` | the title / child half of the ack |
| `s34g-off.flag` | s3.4g (stock JavaScriptCore at all 7 sites) |
| `net5-off.flag`, `net-off-<name>.flag` | all / one of the net5 network fixes |
| `paint-rects-off.flag` | paint-rects V1 + V2 |
| `mempressure-off.flag` | memory-pressure handling |

Opt-in: `net-on-h2.flag` (HTTP/2), `net-on-jscache.flag`, `net-on-hdrbuf.flag`; `jank.flag`,
`paint-hold-experimental.flag`. `OMNI_SWDEC_PAD_V1` has no switch on purpose: it fixes a heap overflow.

HDR is a setting (`video-hdr-preference.txt`, Auto at install). `raster-env.txt` passes only `OMNI_RASTER_*` keys to
the child, so use flag files (or `OMNI_RASTER_ACK_*`) rather than other environment names.

## Not included

The prebuilt RADV archive (`libvulkan_radeon-hdr-wsi.a`, from Ex-Box's private toolchain), `libc.prx` and the
signing tool, as for s3.4.
