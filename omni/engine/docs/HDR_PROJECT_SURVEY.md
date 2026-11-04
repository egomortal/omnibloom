# HDR implementation survey for Omni

Research date: 2026-10-22. Public sources only. Report only: no application changes, builds, dependency imports or console tests. This survey supplements [HDR_READINESS.md](HDR_READINESS.md); its earlier calendar estimate should remain provisional until the reuse and compatibility findings here are resolved.

## Findings

**HDR10 decoding, presentation, SDR UI conversion and mode transitions have already been implemented elsewhere. Omni should study those implementations rather than invent the color pipeline.** The closest references are PS5 native applications using VideoDec2, AGC and VideoOut. They establish useful platform precedent, but none of the reviewed evidence demonstrates the entire HDR path in Omni's current CPU-composited SDL launch environment.

The remaining question is not whether PS5 can produce HDR10. It is which of these existing contracts are available and appropriate in Omni's exact runtime, and how to preserve precision and UI correctness without regressing its presentation timing.

Evidence categories below:

- **Source inspected:** implementation was read; this is not independent runtime verification.
- **Project-reported hardware result:** authors publish console observations; not reproduced here.
- **Design reference:** useful cross-platform architecture, not a PS5 compatibility claim.
- **Unverified:** no matching evidence located in this survey; not proof of impossibility.

## 1. PS5 projects: closest precedents

### EVO Player

Current source inspected at revision `875f766dc9de762c1a1f608005d0afd1f25116f4`. Its README reports Main10/HDR playback and identifies a native AGC interface and title runtime; its stated development/testing environment differs from Omni's. Treat the feature table as the project's claim, not a new benchmark of Omni. Its older codec-support document identifies itself as v0.10.0 and differs from the newer README: do not silently merge their verification levels. [README](https://github.com/sainsaji/EVO-PLAYER-PS5), [versioned codec document](https://github.com/sainsaji/EVO-PLAYER-PS5/blob/875f766dc9de762c1a1f608005d0afd1f25116f4/docs/codec-support.md).

**Concrete code to study:**

- [`evo_agc_runtime.c`, `evo_agc_runtime_set_hdr_output`](https://github.com/sainsaji/EVO-PLAYER-PS5/blob/875f766dc9de762c1a1f608005d0afd1f25116f4/projects/evoplayer/media/src/evo_agc_runtime.c): rejects mid-frame changes, waits for existing writes, requests a registered-buffer attribute change with `sceVideoOutSubmitChangeBufferAttribute2`, updates target state, invalidates both old-format buffers and checks output status. Its comments document unregistering the visible set failing with RESOURCE_BUSY, subsequent registration failing with SLOT_OCCUPIED, and a blank/hung presentation. It retains SDR on refusal. This is strong source-level precedent for changing output without treating close/reopen as universally required; the ABI and permissions are not thereby verified for Omni.
- [`gen_hdr_ui_pipe.py`](https://github.com/sainsaji/EVO-PLAYER-PS5/blob/875f766dc9de762c1a1f608005d0afd1f25116f4/tools/gen_hdr_ui_pipe.py): maps authored sRGB UI through linear RGB and BT.709→BT.2020, uses 203-nit graphics white, then PQ encoding. It explicitly handles premultiplied texture alpha by converting straight color and premultiplying again. This is concrete SDR-over-HDR code, not proof of calibrated appearance on every display.
- [`video_yuv_p010_pq_out.pipe`](https://github.com/sainsaji/EVO-PLAYER-PS5/blob/875f766dc9de762c1a1f608005d0afd1f25116f4/projects/evoplayer/shaders/agc/video_yuv_p010_pq_out.pipe): identified as PQ video to HDR10 output. In contrast, [`video_yuv_p010_hdr.pipe`](https://github.com/sainsaji/EVO-PLAYER-PS5/blob/875f766dc9de762c1a1f608005d0afd1f25116f4/projects/evoplayer/shaders/agc/video_yuv_p010_hdr.pipe) implements HDR-to-SDR conversion with BT.2390-style range reduction. Choosing code by the substring “hdr” would select the wrong deliverable.

**Transferability:** lifecycle guards, format/state separation and UI color mapping are directly relevant designs. AGC commands, pipelines and native runtime plumbing are not drop-in replacements for Omni's SDL CPU tiler.

### ProsperoLight

Source tree inspected at `40f4a3debad75023298ce93c59688313fbc26caa`. [`ps5_videoout_formats.h`](https://github.com/LedyBacer/ProsperoLight/blob/40f4a3debad75023298ce93c59688313fbc26caa/include/ps5_videoout_formats.h) and [`native_agc_present.cpp`](https://github.com/LedyBacer/ProsperoLight/blob/40f4a3debad75023298ce93c59688313fbc26caa/src/native_agc_present.cpp) provide the PS5 ten-bit output and presenter reference. It uses a separate HDR rendering path and HDR-aware overlay resources.

Its [validation history](https://github.com/LedyBacer/ProsperoLight/blob/main/docs/VALIDATION.md) reports visible native HDR10 and a readable overlay. It also records three valuable failures: first frames arriving before asynchronous HDR state became authoritative; reusing an already relocated shader header for another shader; and larger Main10 modes inheriting 1080p texture geometry. Their repairs illustrate state ordering, immutable resource templates and resolution-dependent descriptor validation. These are author-reported observations, not fresh console tests. The same history distinguishes bounded visible acceptance from complete endurance/performance validation.

**Transferability:** closest integration reference for Main10, display formats, overlays and recovery. Its native AGC and streamed-desktop environment still differ from a browser with CPU-composited pages and video.

### PS5 hardware video decoding research

The [HDR study](https://raw.githubusercontent.com/blackbearreloaded/ps5-hardware-video-decoding-research/main/docs/hdr.md) reports a controlled Main10 BT.2020/PQ frame through AGC into ten-bit VideoOut. It documents low-aligned ten-bit words, runtime pitch/coded-height handling and packed A2B10G10R10 output. The study distinguishes completed presentation from calibrated colors/HDMI mastering metadata, and later operator-reported live acceptance from quantified endurance. These distinctions are useful acceptance criteria for Omni.

Its contract example is named `examples/hdr/surface_contract.cpp`; study it for layout tests if the repository is available. The live GitHub repository/API returned 404 during this survey, while the search/web service could retrieve cached raw README/HDR documents. Accordingly, these are **retrievable published/cached research claims, not a currently verified cloneable dependency**. No claim of sustained HDR 4K120 or exact-runtime compatibility follows from them. [Published research README](https://raw.githubusercontent.com/blackbearreloaded/ps5-hardware-video-decoding-research/main/README.md).

## 2. Other renderers and engines worth studying

| Project | Concrete material inspected | What is solved / useful | Applicability limit |
|---|---|---|---|
| Microsoft D3D12 HDR sample | [D3D12HDR.cpp](https://github.com/microsoft/DirectX-Graphics-Samples/blob/e5975f9b0744fc5096dd593ed72bf8f5c004164f/Samples/Desktop/D3D12HDR/src/D3D12HDR.cpp), [presentPS.hlsl](https://github.com/microsoft/DirectX-Graphics-Samples/blob/e5975f9b0744fc5096dd593ed72bf8f5c004164f/Samples/Desktop/D3D12HDR/src/presentPS.hlsl) | Explicit format/colorspace pairing; separate UI texture; compose in linear light, transform primaries and encode PQ at final output | DXGI/D3D calls cannot be reused on PS5; color math and reference-image tests can be studied |
| Microsoft MiniEngine | [BlendUIHDRPS.hlsl](https://github.com/microsoft/DirectX-Graphics-Samples/blob/e5975f9b0744fc5096dd593ed72bf8f5c004164f/MiniEngine/Core/Shaders/BlendUIHDRPS.hlsl) | Explicit UI-to-PQ conversion, paper-white scaling, alpha handling | Different from full linear-light scene/UI composition; evaluate blending semantics rather than copying blindly |
| mpv + libplacebo | [vo_gpu_next.c](https://github.com/mpv-player/mpv/blob/master/video/out/vo_gpu_next.c), [renderer.h](https://github.com/haasn/libplacebo/blob/master/src/include/libplacebo/renderer.h), [colorspace.h](https://github.com/haasn/libplacebo/blob/master/src/include/libplacebo/colorspace.h) | Frame, target and overlay color descriptions; hardware-frame rendering integration; separate storage depth, signal depth and bit shift; explicit alpha modes | Renderer is GPU-backed; useful as a design/reference implementation, not a small CPU library transplant |
| SDL3 | [swapchain compositions](https://wiki.libsdl.org/SDL3/SDL_GPUSwapchainComposition), [testcolorspace.c](https://github.com/libsdl-org/SDL/blob/main/test/testcolorspace.c) | Separate SDR, linear HDR and PQ ten-bit output; support query; HDR state, gradients, texture and blend test patterns | Omni uses a custom SDL2 PS5 backend; SDL3 feature existence does not enable that backend |
| Unity URP | [HDR output documentation](https://docs.unity3d.com/kr/Packages/com.unity.render-pipelines.universal%4015.0/manual/post-processing/hdr-output.html) | Paper white, display brightness limits, calibration and HDR debug views; warns reported display values may be inaccurate | Engine workflow reference; not public PS5 platform implementation source |
| Unreal Engine | [HDR display output](https://dev.epicgames.com/documentation/en-us/unreal-engine/high-dynamic-range-display-output-in-unreal-engine) | Separates scene-referred rendering from output transforms, output gamut and display device; HDR enable can recreate swapchain | Scene-rendering tone mapping is not automatically appropriate for already mastered PQ video |
| shadPS4 | [video_out.h](https://github.com/shadps4-emu/shadPS4/blob/main/src/core/libraries/videoout/video_out.h), [release history](https://github.com/shadps4-emu/shadPS4/releases) | Explicit PS4 PQ/BT.2020 ten-bit and float formats/capability state; release notes move HDR swapchain configuration to the present thread | Emulator running on host graphics APIs, not proof of PS4/PS5 homebrew output permissions or shared ABI |

No independently verified physical PS4 homebrew implementation matching Omni's CPU renderer was established in this bounded survey. shadPS4 is useful for conceptual comparison, not a substitute for PS5 API definitions.

## 3. Common patterns, with important alternatives

### Keep format and color meaning separate

“BGRA” or “RGBA” describes component arrangement, not the transfer curve, precision, gamut or HDR status. SDL's documented outputs distinguish eight-bit SDR, RGBA16F extended-linear HDR and packed ten-bit PQ/BT.2020. A BGRA8 UI texture can remain an input to an HDR renderer; it must be converted into the output's color representation. Reinterpreting its bytes as RGB10A2 is not conversion. [SDL format/colorspace combinations](https://wiki.libsdl.org/SDL3/SDL_GPUSwapchainComposition).

libplacebo explicitly models color depth separately from storage depth and bit shift, and does not infer BT.2020 merely because a picture is 4K. This fits Omni's need to distinguish low-aligned decoded samples, converted pixels and scanout packing. [Color representation model](https://github.com/haasn/libplacebo/blob/master/src/include/libplacebo/colorspace.h).

### Preserve video PQ when appropriate; linearize when performing light-based operations

For correctly signaled HDR10 video, normalized BT.2020 non-constant-luminance Y′CbCr conversion yields PQ-coded RGB. A pure passthrough path need not apply PQ a second time. That differs from scene-linear graphics, where PQ encoding belongs at the final output transform. SDR UI requires its own conversion. These are separate pipelines, not contradictory advice. [PS5 HDR study](https://raw.githubusercontent.com/blackbearreloaded/ps5-hardware-video-decoding-research/main/docs/hdr.md), [Microsoft presentation shader](https://github.com/microsoft/DirectX-Graphics-Samples/blob/e5975f9b0744fc5096dd593ed72bf8f5c004164f/Samples/Desktop/D3D12HDR/src/presentPS.hlsl).

The inspected examples do not all blend the same way. Microsoft's D3D12 sample combines UI and scene before PQ in linear light. MiniEngine's UI shader and EVO's UI generator instead produce premultiplied PQ-encoded UI for their output stages. PQ-domain blending is not mathematically equivalent to linear-light blending. For Omni, bright backgrounds, translucent captions and antialiased edges need reference comparisons before choosing either approach. This is a design assessment, not a new rendering change.

### Make mode changes a coordinated presentation operation

Output format, render-target interpretation, cached pixels and UI pipeline state must agree. EVO provides an actual in-place attribute-change precedent and refuses mid-frame changes; shadPS4's release history separately reinforces presentation-thread ownership of swapchain configuration. Do not assume successful HDR registration implies physical signal verification, or that a metadata value describing the display is source mastering metadata. [EVO transition implementation](https://github.com/sainsaji/EVO-PLAYER-PS5/blob/875f766dc9de762c1a1f608005d0afd1f25116f4/projects/evoplayer/media/src/evo_agc_runtime.c), [shadPS4 releases](https://github.com/shadps4-emu/shadPS4/releases).

### Treat overlays as independent color sources

libplacebo gives each overlay its own color representation and colorspace. Unity defines UI white through paper-white luminance rather than peak brightness. The reusable idea is to retain ordinary browser UI authoring while explicitly mapping it for the display target, not to let changing video metadata reinterpret all page bytes. [Overlay model](https://github.com/haasn/libplacebo/blob/master/src/include/libplacebo/renderer.h), [Unity UI brightness](https://docs.unity3d.com/kr/Packages/com.unity.render-pipelines.universal%4015.0/manual/post-processing/hdr-output.html).

## 4. Failure lessons relevant to Omni

| Mistake / failure | Source evidence | Lesson for a later implementation |
|---|---|---|
| Unregistering the displayed buffer set during an HDR switch | EVO runtime comments record resource-busy, occupied-slot and blank/hung output | Study the supported attribute-change lifecycle and preserve SDR on refusal |
| New format with old cached pixels | EVO invalidates both buffers and video/UI state after switching | Generation and cache invalidation must cover format as well as stream identity |
| Treating Main10 negotiation as active HDR | ProsperoLight validation documents asynchronous HDR-state ordering | Distinguish negotiated codec, source color state and confirmed output state |
| Reusing relocated shader data | ProsperoLight records a shader-creation failure | Preserve immutable resource templates |
| Larger video with stale 1080p descriptors | ProsperoLight validation records Main10 geometry failures | Derive all surface views and target geometry consistently |
| Selecting an “HDR” shader that actually produces SDR | EVO has separate `hdr` tone-map and `pq_out` shaders | Follow inputs and outputs, not filenames |
| Incorrect assumptions about alpha or display brightness | Microsoft shader alternatives and Unity calibration guidance | Validate translucent edges and reference white; do not equate UI white with peak nits |
| Treating emulator types as a PS5 ABI | shadPS4 exposes PS4 types and format definitions | Use as reference only; do not copy structures/constants into PS5 based on resemblance |

The first five rows are project-documented failures or lifecycle protections, not newly reproduced bugs. The remaining rows are implications drawn from inspected code and documentation.

## 5. Has HDR been demonstrated in a comparable environment?

| Comparison level | Conclusion |
|---|---|
| Same console family and hardware decoder services | Yes: PS5 project-reported Main10/HDR output exists |
| Main10 plus BT.2020/PQ plus ten-bit VideoOut | Yes: controlled research and public native renderer code provide precedent |
| SDR UI over HDR video | Yes: inspected conversion code and reported readable overlays; calibrated equivalence is a separate claim |
| Same FW 13.60, launch mode, CPU tiler, SDL backend and browser process model as installed Omni | **Not established by this survey** |
| Pure CPU HDR composition sustaining Omni's 4K60 target | **Not established** |
| Arbitrary source mastering metadata verified at HDMI in Omni | **Not established** |

Comparable pieces exist; an exact comparable end-to-end environment has not been demonstrated in the evidence reviewed. That narrows the unknowns substantially without pretending all integration work is solved.

## 6. Reuse-first assessment before any schedule

Study in this order: EVO output transitions and UI generator; ProsperoLight format/presenter lifecycle; Microsoft linear-composition and UI shaders as correctness references; libplacebo's metadata/overlay model; SDL's color test cases. Retain Omni's accepted startup, clock, lock and direct-tiling ownership constraints while evaluating those designs.

Likely reusable knowledge: sample layout validation, transfer/primary math, UI reference-white policy, source-versus-target metadata separation and transition state machines. Likely integration-specific work: Omni IPC fields, CPU precision and tiling, browser overlays, runtime output compatibility and performance validation. Existing libraries reduce design uncertainty; they do not establish a drop-in renderer or a CPU cost budget.

Do not derive a new calendar estimate from repository feature lists. First resolve whether the supported VideoOut HDR path and transition API are usable in Omni's exact context, then choose a color/composition design and measure its cost in a separately authorized phase. The earlier 3–6-week estimate is not a survey-backed commitment.

Source reuse requires checking the exact selected files' licenses and dependencies. Inspected Microsoft shaders carry MIT notices; libplacebo/selected mpv files carry LGPL notices; PS5 projects identify GPL licensing. These are source labels, not a conclusion that whole-project integration is automatically compatible. No code was copied into Omni.

## Research reproducibility and limitations

GitHub tree revisions read through the API: EVO `875f766dc9de762c1a1f608005d0afd1f25116f4`; ProsperoLight `40f4a3debad75023298ce93c59688313fbc26caa`; Microsoft graphics samples `e5975f9b0744fc5096dd593ed72bf8f5c004164f`. Pinned links are used where captured. Other links point to documentation or moving branches and should be rechecked before reuse. Source files were inspected as text; no external scripts were executed. The research repository's live availability issue and stale EVO codec document are explicitly retained above. No physical HDR observation, photometric measurement or sustained playback test was performed by this report.
