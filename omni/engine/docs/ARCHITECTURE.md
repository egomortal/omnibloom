# Omni release-candidate architecture

> Current maintenance state: v147 is installed; v139 references below describe its rendering lineage or historical experiments. Read [MAINTENANCE.md](MAINTENANCE.md) before builds, tests or restoration. Older staging helpers can downgrade the installed candidate.

This describes the v139 reduced-copy candidate, not a new architecture. The working source may contain later diagnostics and opt-in experiments; match every measurement to its artifact hash. The experimental v143 empty-queue wait is disabled unless its startup flag is present and is not part of the accepted v139 binary.

## Process and data boundaries

WebKit's WebProcess runs page content. The NetworkProcess handles network resources. Omni's UI process contains browser controls, the media service, conversion and presentation. A UI-process CPU figure excludes the separate WebProcess and NetworkProcess.

For the measured MSE fixtures, page media data reaches the media/service path through the existing protocol. Decoded frames become converted linear RGBA layers. Frame selection uses the service clock and predicted refresh. UI handoff publishes a canvas and generation-matched video state. The presenter prepares the output, submits it through SDL/VideoOut and observes the completion-event wait.

Keep these stages distinct: decoded, converted, selected, handed off, prepared, submitted and completion-observed are not interchangeable. The software completion observation is not an optical measurement of the television.

## Reduced-copy output

For supported large full-frame layers, `media/OmniHwService.cpp::v139Direct` invokes the synchronous SDL direct-tiling helper. It writes converted video directly into registered tiled output, restores opaque UI gaps and blends translucent UI. This removes the intermediate full-frame video write into the linear presentation surface. Decode, color conversion, tiling and the allocated UI surface still exist.

Unsupported layouts, dimensions, offsets, masks or missing helper support retain the existing copy path. Preserve this path for windowed playback and transitions. The flag `reduced-copy-test.flag` is read at process startup; changing it in a live process is not a supported mode switch.

## Ownership

- `omniPresentLock`: UI-to-presenter publication and shutdown coordination. Mask preparation stays outside this short critical section.
- `v7ComposeLock`: selected-layer and live-mask lifetime through synchronous preparation. Never defer use of borrowed pointers past this ownership.
- `plane.lock`: queue, selection and clock state. It is not the UI handoff mutex.

The accepted handoff change exchanges compatible SDL-owned surface pointers instead of copying the whole frame while holding the handoff mutex. Incompatible surfaces retain their transfer fallback. Stop the presenter before SDL teardown.

## Preserved protections

The initial held-clock poster permits presentation before playing time advances. Playback release requires pacing, an awake presenter and a valid generation-matched handoff. Capture the initial playing anchor after hold-release work, so blocking release work does not become elapsed media time. Later service-clock corrections remain distinct from this first-clock protection.

See [STARTUP_SEQUENCE.md](STARTUP_SEQUENCE.md), [THREADS_AND_LOCKS.md](THREADS_AND_LOCKS.md), [VIDEO_PIPELINE.md](VIDEO_PIPELINE.md), [TIMING_MODEL.md](TIMING_MODEL.md) and [4K60_HISTORY.md](4K60_HISTORY.md).

## Release boundary

v139 is the primary candidate, installed as experimental at the last verified restoration. It is not certified flawless on every website. The release evidence distinguishes uninterrupted playback from combined seek/fullscreen/overlay stress. Keep the v119 recovery artifact and the v139 copy fallback; do not replace the installed candidate with a diagnostic build merely because it compiled.
