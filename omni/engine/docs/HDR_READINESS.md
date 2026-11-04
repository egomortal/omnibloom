> Implementation checkpoint: initial color conversion and color-metadata preservation are implemented and host-tested in the isolated `experiments/omni-hdr` checkout only (main SDR source restored); see [HDR implementation checkpoint](../../../outputs/hdr-implementation/README.md). Browser integration, console HDR playback, reliable profile activation, and performance qualification remain unfinished. Nothing was installed. The scalar ten-bit converter is not currently fast enough for a 4K60 claim.

# HDR readiness assessment

Assessment date: 2026-10-22. Follow-up console evidence: [controlled HDR declaration test](../../../outputs/hdr-feasibility/controlled-profile/README.md). The source assessment below originally preceded those tests. Scope: installed Omni v147 and its current CPU composition / SDL / VideoOut path. Report only: no implementation, build, capability changes, deployment or PS5 tests were performed.

## Decision

**Omni cannot currently output correct HDR10. It already has useful 10-bit decode infrastructure, but HDR presentation and metadata transport are incomplete.** HDR10 is demonstrably feasible in another public PS5 application; a later isolated A/B/A test also demonstrated HDR surface output through Omni's existing hbldr launch path when the host profile declared HDR. The original profile and SDR output were restored afterward. Do not interpret this as a definitive platform prohibition or as a ready-to-enable setting.

| Question | Assessment | Confidence / limit |
|---|---|---|
| HDR10 in installed Omni today? | No; current display pipeline is SDR | High, source inspection |
| HDR10 possible on PS5 applications generally? | Yes, upstream reports visible HDR10 in ProsperoLight | External project's evidence, different native renderer/runtime |
| HDR surface output possible from Omni's existing launch path? | Yes, in a later isolated test with the host HDR declaration | 180 synthetic 1080p HDR flips; not full HDR video, metadata or 4K60 validation |
| 10-bit decode paths already present? | Yes: HEVC Main10 and VP9 profile 2 | Implementation exists; decode support is not HDR presentation validation |
| Can HEVC Main10 be the decoder for HDR10? | Yes in principle, for supported 10-bit 4:2:0 streams | Main10 alone does not identify PQ/BT.2020 or guarantee all profiles/levels |
| HDR metadata propagated end to end today? | No | Current public frame/configuration structures omit essential fields |
| Small toggle or small patch? | No; medium-to-high complexity across several components | Remaining work includes precision, color handling, metadata, UI composition and performance validation |

## 1. Current output and the precision boundary

The inspected SDL source `/opt/omni-build/sdl-display-preview/src/video/ps5/SDL_ps5video.c` uses `SDL_PIXELFORMAT_ABGR8888` and registers the existing SDR buffer format `0x8000000022000000` with `sceVideoOutSetBufferAttribute2`. This is source inspection, not a newly measured HDMI signal. The v147 HUD explicitly sets `sample.hdr=false`, consistent with this path.

In `OmniHwService.cpp::holeConvert`, 10-bit planar input selects `AV_PIX_FMT_YUV420P10LE`, but output is `AV_PIX_FMT_RGBA` or `AV_PIX_FMT_BGRA`: eight bits per RGB channel. Matrix/range conversion through swscale is present. An HDR transfer-function transform, display-aware tone mapping and full gamut management are not present in this path. Selecting a BT.2020 YCbCr matrix does not itself convert PQ to SDR or establish correct HDR output.

Reduced-copy tiling consumes that already converted eight-bit layer. It avoids an intermediate video write; it does not preserve ten-bit precision lost earlier. The tile/composition helper also assumes eight-bit color channels and current UI alpha semantics. Changing the VideoOut format constant alone would misinterpret pixels rather than implement HDR.

Local evidence: [service conversion](../media/OmniHwService.cpp), [direct tile helper](../../../outputs/reduced-copy-v139/compose-tile.c), [HUD output state](../entry/OmniBrowser.cpp), [SDL build pairing](../../../outputs/build-sdl-v139.sh).

## 2. Existing ten-bit decode infrastructure

`Backend::open` configures HEVC profile 2 for depth greater than eight and VP9 profile 2 for ten-bit input. Decoded frame descriptions retain bit depth and pitch. The service handles two-byte samples and splits interleaved chroma into planar ten-bit YUV. The implementation documents low-aligned samples, not an assumption that every buffer is P010 with high-aligned ten-bit values.

HEVC uses a hardware-only route; there is no software HEVC fallback. HEVC configuration, hvcC parsing and Main/Main10 selection already exist. VP9 profile 2 follows a separate implemented ten-bit path. Neither implies that every resolution/frame-rate/profile combination has passed console playback validation. The backend currently uses pipeline depth 1 for ten-bit versus 4 for eight-bit; existing eight-bit VP9 4K60 results cannot certify ten-bit throughput or queue behavior.

The codec report records HEVC Main10 2160p tests using the service with a host stand-in. Those are useful correctness tests, not proof of an actual console HDR session. Main10 can carry SDR, PQ HDR10 or other transfer characteristics; choose treatment from signaled color information, not bit depth alone.

Local evidence: [backend](../media/OmniHwBackend.cpp), [bitstream configuration](../media/OmniHwBitstream.h), [hardware-only HEVC route](../media/OmniPacketDecoder.cpp), [codec test scope](../../../outputs/codecpkg/CODECS-REPORT.md).

## 3. External HDR10 evidence and its boundary

ProsperoLight's public validation records report visible HDR10 and a functioning overlay in a bounded native-app test. Its renderer uses AGC and VideoOut, so this is evidence of platform feasibility, not a drop-in demonstration for Omni's CPU renderer or current launch context. The validation also documents resolution-specific work and distinguishes partial results from visible acceptance. [Upstream validation](https://github.com/LedyBacer/ProsperoLight/blob/main/docs/VALIDATION.md).

The project's locally archived 2026-10-20 source identifies packed R10G10B10A2 output with BT.2020/PQ tagging and uses `sceVideoOutSetBufferAttribute2` followed by `sceVideoOutRegisterBuffers2`. The archived HDR format is `0x8100070422000000`. This is a reference, not an instruction to substitute it into Omni. Live fetches of those two upstream source files failed during this assessment; their precise implementation claims rely on the dated local snapshots. The upstream validation page was retrieved successfully.

A CPU-generated ten-bit scanout buffer is a plausible design if Omni's supported VideoOut configuration accepts it. This is an engineering inference, not a proven current capability. No GPU-access workaround, title migration or permission-changing investigation was performed or proposed as an implementation requirement.

Local snapshots: [format declaration](../../../outputs/engine-research-2026-10-20/ProsperoLight-include-ps5_videoout_formats.h), [native presenter](../../../outputs/engine-research-2026-10-20/ProsperoLight-src-native_agc_present.cpp).

## 4. Metadata: possible to add, not currently propagated

Current `VideoColour` retains only matrix and full-range values. `Configure.f` carries their packed representation; decoded-frame messages carry size, pitch, depth and PTS. `DemuxTrack`/`DemuxPacket` do not expose a complete typed HDR metadata record. Metadata may remain embedded in compressed bytes, but that is not the same as exposing it to the compositor and HDMI output layer.

A complete HDR10 path needs explicit handling of:

- Color primaries, transfer characteristics (PQ versus HLG/SDR), matrix coefficients and range.
- Mastering-display primaries/white point and minimum/maximum luminance when present.
- Content light levels MaxCLL/MaxFALL when present.
- Metadata validity, absence, stream generation and changes across seek, track switch, new initialization segment and SDR/HDR transition.

FFmpeg provides mastering-display and content-light side-data representations. Omni would need to copy validated values into its own stable protocol structures, rather than send FFmpeg structure layouts directly across its fixed-size IPC. Hardware decoding bypasses the software AVFrame path, so required container/bitstream metadata must be extracted and carried independently where necessary. Missing metadata needs a documented fallback policy; fabricated values must not be labeled source metadata. [FFmpeg metadata definitions](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavutil/mastering_display_metadata.h), [content-light fields](https://ffmpeg.org/doxygen/trunk/structAVContentLightMetadata.html).

The final output handoff is unverified. A dated local SDK stub snapshot lists `sceVideoOutSysSetHdrMetadata`, but the currently retrieved master stub did not contain that symbol. Neither listing establishes a usable signature, allowed calling context, correct structure layout or successful HDMI metadata transmission. The reviewed ProsperoLight snapshot establishes format selection, not proof that Omni can submit arbitrary source mastering metadata. Do not invent that ABI or assume a successful registration proves all metadata reached the TV. [Current SDK stub source](https://raw.githubusercontent.com/ps5-payload-dev/sdk/master/sce_stubs/libSceVideoOut.c), [dated local snapshot](../../../outputs/engine-research-2026-10-20/sdk-sce_stubs-libSceVideoOut.c).

Local metadata boundary: [VideoColour](../media/OmniHwBitstream.h), [wire protocol](../media/OmniHwProtocol.h), [demux structures](../media/OmniMP4Demuxer.h).

## 5. Blockers and engineering scope

| Work area | Current blocker | Complexity |
|---|---|---|
| Output eligibility | No evidence of HDR registration/signaling in Omni's exact launch environment; supported status/metadata API semantics need confirmation | High uncertainty; feasibility gate |
| Color transport | Transfer, primaries and static HDR data not carried end to end | Medium; demux/bitstream/IPC/epoch handling |
| Conversion | Current conversion truncates to eight-bit RGB and lacks HDR processing | High; precision, range and transfer correctness |
| Composition/tiling | Current fused path and alpha blending assume eight-bit SDR UI/video | High; retain lifetime and fallback invariants |
| UI in HDR | Browser pages, captions and HUD need a defined SDR reference-white mapping and correct blending space | High; simply blending SDR bytes into PQ is incorrect |
| Display lifecycle | SDR/HDR transitions, cancellation, failure recovery and return to SDR need a coordinated lifecycle | Mediumâ€“high; preserve startup and pacing protections |
| Capability reporting | HDR queries intentionally refused; VP9 PQ/HLG transfer codes rejected | Low code volume, high correctness risk if enabled prematurely |
| Validation | No Omni HDR optical/TV acceptance, ten-bit endurance or HDR performance baseline | High; required before release claims |

A packed RGB10A2 output still uses four bytes per pixel, so scanout storage need not double. But ten-bit YUV buffers use two-byte samples, higher-precision intermediates may add memory, and color-managed CPU conversion/composition adds work. There is no measured HDR 4K60 CPU budget here; the existing SDR performance result must not be reused as an HDR estimate.

HEVC Main10 decoding can provide HDR content samples, but present-day Omni does not correctly display that HDR content merely because decoding succeeds. Its current matrix conversion is not an HDR-to-SDR tone mapper. A separate project in this workspace has a still-image PQ-to-SDR helper; that is not integrated, not a video-performance result, and not evidence of HDR output readiness.

## 6. Planning estimate, conditional on output feasibility

These are judgment-based engineering estimates for an experienced maintainer with continuous device access, not measured delivery times or a commitment:

- Read-only API/format confirmation and a later separately authorized bounded output feasibility experiment: approximately 2â€“5 working days. If the current launch context cannot support the required output through available interfaces, the rest of this estimate does not apply.
- Metadata representation/extraction/transport and high-precision video/color integration: approximately 1â€“2 weeks.
- Correct UI composition, tile integration, SDR/HDR switching and recovery: approximately 1â€“2 weeks.
- Image correctness, display acceptance, repeated transitions and performance/endurance validation: approximately 1â€“2 weeks, possibly overlapping other work.

A credible integrated candidate is therefore roughly **3â€“6 engineering weeks after output feasibility is established**. High uncertainty remains. Correct CPU-only HDR at 4K60 is not promised by this estimate; it may need a different performance target or separately assessed rendering design. HDR-to-SDR tone mapping would be a different deliverable and must not be presented as HDR10 output.

## 7. Readiness criteria for a future implementation

Before advertising HDR, demonstrate: supported HDR output in Omni's actual runtime; validated ten-bit sample/packing order; correct PQ/BT.2020 treatment and metadata state; visible reference-pattern correctness; readable SDR UI at a defined brightness; clean SDRâ†”HDR transitions, seeking and fullscreen; decoder/audio stability; and matched presentation-performance measurements. A TV HDR indicator alone proves signaling, not correct luminance/color or metadata values.

Until then, retain HDR: OFF and existing HDR capability refusals. The assessment outcome is **partially prepared decoder infrastructure, substantial missing color/presentation integration, and an unverified output-context gate**.
