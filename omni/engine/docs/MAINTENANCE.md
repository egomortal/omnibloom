# Omni maintainer entry point

Updated 2026-10-22. Read this before modifying playback or running an old deployment helper. This is a personal browser project; describe its real implementation and limitations accurately.

## Current state and source of truth

v147 is installed on both `/data/omni/omni-engine.elf` and `/data/homebrew/Omni/eboot.elf`, SHA-256 `4cc5ef633e0fad999980d3fde0c8f78a0043943fe6ce05b5393d3ff07f72e8c8`. Both were read back and verified. Remote v119 fallback is preserved; local v139 remains a rollback artifact. Installation verification is not a post-install playback test.

v147 adds the lightweight, session-only stats overlay to the reduced-copy lineage. Settings → Playback stats or F8; default OFF. Output remains SDR, so HDR: OFF is intentional. Do not infer HDR from a 10-bit source or 4K resolution.

Evidence, relative to the repository root:

- [Installation record](../../../outputs/stats-overlay-v145/installation.json).
- [Six-run overlay comparison](../../../outputs/stats-overlay-v145/RESULTS.md).
- [Historical rendering validation](../../../outputs/release-candidate-v139/README.md).
- [Queue-wait experiment](../../../outputs/queue-reuse-v143/README.md).

A version label is not evidence of what is currently installed. Before console work, read the latest installation record and check actual state. Older v141–v146 staging helpers restore v139; some older helpers restore v119. Those instructions are historical and must not silently downgrade v147. Never install a temporary validation harness as a release.

## Reading order

1. [Decisions and causal evidence](MAINTENANCE_DECISIONS.md): what was proved and why each fix exists.
2. [Architecture](ARCHITECTURE.md) and [video pipeline](VIDEO_PIPELINE.md): processes, frame ownership and the reduced-copy path.
3. [Startup sequence](STARTUP_SEQUENCE.md), [threads and locks](THREADS_AND_LOCKS.md), [timing model](TIMING_MODEL.md).
4. [Queue reuse](QUEUE_REUSE.md): distinguish empty-queue repeats, clock eligibility and deadline misses.
5. [Performance findings](PERFORMANCE_FINDINGS.md) and [history](4K60_HISTORY.md): measurements and limits, not universal guarantees.

## Non-negotiable invariants

- Keep the generation-matched readiness gate and held-clock poster path. A full raw queue alone does not establish presentation readiness.
- Reset the playing anchor after the hold-release path returns. Do not charge blocked release work to elapsed playback.
- Keep mask preparation outside `omniPresentLock`; publication and buffer ownership remain protected. Do not replace safe ownership with a raw borrowed pointer.
- Keep `omniPresentLock`, `v7ComposeLock`, and `plane.lock` conceptually separate. Condition-variable sleep is not mutex contention.
- Direct tiling consumes the converted RGBA layer synchronously while composition ownership protects it and the overlay mask. Consume each prepared SDL marker only once for the matching surface.
- Preserve opaque UI, premultiplied translucent overlays, validation, epoch checks, store ordering and the copy fallback. Unsupported layouts may legitimately use fallback.
- Keep `empty-queue-wait-test.flag` disabled. Its benefit was not demonstrated.
- Do not alter wake timing, selection policy, decoder settings or capability reporting to improve a benchmark without a demonstrated cause.

## Find code by symbol, not old line number

| Concern | Source / symbols |
|---|---|
| Hold/release and playing anchor | `entry/OmniMSEPlayer.cpp`: `v5HoldTick`, `startupReady`, `m_anchor` |
| UI/presenter publication and shutdown | `entry/OmniBrowser.cpp`: `omniPresentFrame`, `omniPresenterMain`, `omniStopPresenter`, `omniPresentLock` |
| Selection, clocks and direct path | `media/OmniHwService.cpp`: `holePaceSelect`, `holePunchBeforeFlip`, `holePunchVblank`, `v139Direct`, `v8WriteLive` |
| Queue wait, opt-in only | `media/OmniHwService.cpp`: `v143WaitEmptyQueue` |
| Fused tile helper | `outputs/reduced-copy-v139/compose-tile.c`: `PS5_OmniComposeTile` |
| SDL integration | `outputs/patch-sdl-v139.py`, `outputs/build-sdl-v139.sh` |
| Production HUD | `entry/OmniPlaybackHud.h`; service `playbackStats`; relay `relayHudUnderruns` |

Source paths above are relative to `omni-browser/engine`, except explicitly prefixed `outputs/`, which are relative to the project root. Building browser source alone does not reproduce the paired SDL implementation. Build scripts patch and restore shared WSL sources: never run variant builds concurrently.

## How to investigate the next regression

Record the installed hash, built hash, source snapshot, fixture, display mode, enabled flags and exact reporting window before interpreting a result. First establish which stage is wrong. Match frame sequence, epoch and PTS through selection → handoff/preparation → submission → successful completion. A decode count is not a presentation count.

Use the same fixture, binary and instrumentation for a controlled comparison, changing only the relevant condition. Keep startup, uninterrupted playback and interactive transitions as separate workloads. Preserve failed runs and raw evidence. Historical unknowns remain unknown; new events with matching symptoms do not retrospectively prove their cause.

Use bounded diagnostic detail only when authorized. The production stats overlay must not enable tracing, per-frame logging, disk access, new threads or timing probes. Its text updates once per second with fixed storage and a reused surface. Three approved event counters cover completed flips, repeated identities and the existing decoder error handler. FPS and repeats are different metrics; an on-time flip can show the same picture twice.

Before accepting a rendering change, check completed-flip intervals and repeats, errors/underruns, startup, multiple fixtures, seeks, fullscreen transitions, overlays, ordinary pages and endurance. Report missing coverage. Physical visibility/audibility is not verified by counters or by a linear-canvas screenshot.

## What the next agent should do

Maintain and validate the installed candidate; no new architectural optimization is requested. The final v147 production binary still needs its own post-install smoke test. The unchanged overlay had three ON/three OFF validation runs: mean completions 2996 ON / 2997 OFF per ~50 seconds, repeat totals 5 ON / 9 OFF, late-refresh totals 1 each. CPU and exact wake-to-submit were not retained with tracing disabled: do not claim those were measured or that overhead is literally zero.

For any new issue, write the observed failure and evidence first, then a narrow experiment. Do not reopen the accepted startup/lock/anchor fixes merely because a later queue discard occurs. Do not promise perfect 4K60 on arbitrary sites.
