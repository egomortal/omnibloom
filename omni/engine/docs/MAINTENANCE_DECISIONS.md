# Playback decisions and causal evidence

These are measured decisions, not suggestions to repeat old investigations. Values below describe specific historical comparisons. Current installation state is in [MAINTENANCE.md](MAINTENANCE.md).

## 1. Presentation readiness before playback release

**Observed:** a deep raw queue did not prevent startup losses. Media time advanced before pacing and presentation were ready. Raw frames still require conversion, selection, handoff and a display opportunity.

**Accepted change:** hold the initial playing clock until pacing is active, the presenter is awake, and a valid handoff is available for the current generation (`startupFlags == 7` plus the generation check). Keep the held-clock poster frame so presentation can establish readiness without requiring playback to advance first. The old timeout must not bypass this readiness check.

**Evidence:** startup queue discards 51 → 7; pre-first-completion discards 23 → 0. This proved the gate addressed the pre-presentation loss, not all startup loss.

**Regression trap:** waiting for a future due picture while holding the clock can deadlock progress. Releasing because the raw queue is full recreates the original ordering problem.

[Controlled gate result](../../../outputs/presentation-chain-audit/STARTUP-GATE-RESULT.md).

## 2. Short ownership transfer, not preparation under the handoff mutex

**Observed:** presenter wakeups followed release of `omniPresentLock`; UI ownership covered mask preparation and a full-screen copy. The three acquisition paths are UI publication, presenter/condition-variable reacquisition, and shutdown.

**Accepted change:** prepare the mask before the critical section. Recheck pin/epoch at publication. Exchange compatible SDL-owned buffers under protected ownership instead of copying the screen while holding the mutex. Keep copying for external, locked, RLE, incompatible and smaller surfaces.

**Evidence:** maximum UI hold 11.777 → 0.053 ms; average protected pixel transfer 2.720 → 0.005 ms. Startup discards still remained, so lock contention was not the sole cause of all losses.

**Regression trap:** moving work outside a mutex is correct only if object lifetime and mutation rights remain valid. `plane.lock` and `v7ComposeLock` are not interchangeable with the handoff mutex. A sleeping condition-variable waiter releases the mutex.

[Lock result and ownership measurements](../../../outputs/presentation-chain-audit/LOCK-RESULT.md).

## 3. Anchor after release work, not before it

**Observed:** a playing anchor captured before blocking release work was reused afterward. The first delivered clock jumped about 150 ms even though playback had been held. This looked like delayed IPC, but the measured send-to-handler was 26 microseconds and activation another 6 microseconds.

**Accepted change:** immediately after `v5HoldTick` releases the initial hold, set the anchor to current monotonic time. Keep the held media position; do not count release-path work as played media.

**Evidence:** first playing position 150.610 → 4.653 ms, despite clock arrival about 154 ms after release. The release path itself still cost about 150 ms. Baseline seven startup queue discards became zero in the original first-decode-through-release+10-second window.

**Boundary:** a window based on the first playing clock included two later selection skips. Later tests also had post-first-flip selection discards. That does not undo the proven anchor mechanism. Later clock corrections have their own eligibility effects and must be examined separately.

[Anchor experiment](../../../outputs/presentation-chain-audit/STARTUP-ANCHOR-RESULT.md).

## 4. Remove the intermediate video write; retain conversion and overlays

**Observed:** the ~33.16 MB intermediate video copy dominated preparation. Fallback then performed a second ~33.18 MB tiled-output write at 3840x2160. These are presentation transfers, not all memory movement in decoding.

**Accepted path:** converted linear RGBA → fused video/UI composition directly into tiled output. Opaque UI and premultiplied translucent UI remain. Upstream decode/color conversion and the linear UI allocation still exist. This is reduced-copy presentation, not decoder-to-display zero-copy.

**Ownership:** synchronous tiling completes before releasing selected-layer/mask lifetime protection. SDL consumes a matching prepared surface marker once and avoids tiling it again. Validation failure or unsupported layout uses the old copy path.

**Same-workload evidence:** completed flips 2981 → 2996; >25 ms completion gaps 16 → 1; median wake-to-submission-return 7.079 → 2.280 ms; process CPU 2.112 → 1.745 core-equivalents. The old preparation metric excluded subsequent tiling while the new metric included it; comparing those isolated values alone understates the difference in measured scope.

**Wake policy preserved:** measured lead/handoff/reflip costs plus 0.5 ms, 3 ms floor, 3.8 ms small-plane ceiling and up to refresh period minus 2 ms for large planes. Missed preparation deadline with a future refresh leads to a prompt wake rather than a whole-period skip. The proposed fixed 11 ms lead was not applied. Do not double-count fused tiling as both preparation and a later pass.

[Performance details](PERFORMANCE_FINDINGS.md), [pipeline ownership](VIDEO_PIPELINE.md).

## 5. Queue reuse is a distinct mechanism, not proof of decoder trouble

**Observed:** some completions repeated the same picture while completion timing remained normal. Scoped evidence distinguished empty converted queues, clock eligibility changes and application refresh-target misses. A high raw queue does not establish that a converted eligible replacement exists.

**Decision:** retain existing selection and clock protections. The optional bounded empty-queue wait was not promoted. In a focused follow-up all 448 captured checks rejected waiting; the earlier repeat cluster vanished without a wait executing. Lower repeats therefore did not demonstrate the experiment caused an improvement.

**Regression trap:** forcing a newer frame can break synchronization; waiting can consume the margin needed to present. Do not relax generation, identity, poster, layout or budget guards simply to make an experiment execute.

[Queue evidence and continuation rules](QUEUE_REUSE.md).
