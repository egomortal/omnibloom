# Video presentation pipeline

> Current maintenance state: v147 is installed; v139 references below describe its rendering lineage or historical experiments. Read [MAINTENANCE.md](MAINTENANCE.md) before builds, tests or restoration. Older staging helpers can downgrade the installed candidate.

Status: v139 reduced-copy is the primary release candidate, with the copy fallback preserved. Judge the remaining events by current stability, reproducibility, growth and user-visible impact. Historical missing trace state does not independently block release; decoder counters alone do not certify presentation quality.

## Data flow

Decode -> queued decoded frame -> converted linear RGBA layer -> frame selection -> synchronous composition -> registered tiled output -> VideoOut submission -> completion.

The fallback writes selected video pixels into the linear SDL presentation surface, preserving opaque and translucent UI, then tiles that surface. At 3840x2160 the intermediate video write measured 33,159,572 bytes, followed by a full 33,177,600-byte tiled write. These are two presentation transfers; upstream decoding and color conversion are separate.

The v139 helper tiles directly from the converted RGBA layer. It restores opaque UI gaps and blends premultiplied translucent UI pixels directly in tiled storage. The linear UI surface remains allocated. This is reduced-copy presentation, not decoder-to-display zero-copy.

## Ownership and fallback

`media/OmniHwService.cpp::v139Direct` calls `omniSDLDirectTile` synchronously while existing composition ownership protects the selected layer and live mask. Do not retain borrowed pointers in a deferred callback. The SDL update consumes a prepared output once, avoiding its normal second tiling pass.

The candidate requires the explicit `/data/omni/reduced-copy-test.flag` at process startup and the linked SDL helper. Full-frame RGBA, matching epoch, valid masks, large planes and aligned supported widths are required. Partial/windowed layouts, incompatible dimensions or failed helper validation retain the old copy path. Keep this fallback when promoting.

Implementation and build scripts: `outputs/reduced-copy-v139/compose-tile.c`, `outputs/patch-sdl-v139.py`, `outputs/build-sdl-v139.sh`, `outputs/build-hwdec-v139.sh` (paths relative to project root).

## Verification

Host byte-equivalence covers 512x128, 1920x1080 and 3840x2160, channel mappings, padded pitches, opaque and translucent overlays, and malformed-mask rejection. Initial console A/B verified 2,996 direct flips, each with one fused tile pass and no intermediate copy event. This does not establish arbitrary website or long-session correctness. See PERFORMANCE_FINDINGS.md and the validation matrix.

## Expanded functional validation

The v140 harness completed four fullscreen entry/exit cycles, a three-second backward seek and a two-second forward seek, with resumed playback. It recorded 2183 successful direct helper calls containing translucent pixels, and exercised the copy fallback during the combined transition workload. No decoder errors or audio underruns occurred. The combined overlay/seek/transition workload still failed the strict performance check; functionality and smoothness must remain separate findings.

The saved linear canvas screenshot shows overlay placement, but is not a readback of the registered tiled output. Do not use its alpha appearance to claim final scanout correctness. Host byte equivalence verifies parity with the old composition path, not physical TV output. Details: outputs/reduced-copy-v139/matrix-summary.json.

The legacy strict pacing check is retained as a measurement, not an automatic release veto. Latest compatibility and known limitations: `outputs/release-candidate-v139/RELEASE_NOTES.md`.

## Release documentation checkpoint: 2026-10-22

The reduced-copy v139 path remains the primary candidate. Five additional v143/v144 validation runs preserve the renderer and accepted startup/clock/lock fixes. An optional bounded empty-queue wait was tested but not promoted: improvements were inconsistent and no eligible wait was captured in the focused follow-up. Its two later gaps were application refresh-target misses, not decoder errors. Keep the wait disabled and retain the copy fallback. Exact results and remaining limitations are in `outputs/queue-reuse-v143/README.md`; the complete documentation index is `outputs/release-candidate-v139/README.md`. No new architectural or wake-margin optimization was made.
