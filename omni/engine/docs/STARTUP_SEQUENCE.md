# Accepted startup sequence

> Current maintenance state: v147 is installed; v139 references below describe its rendering lineage or historical experiments. Read [MAINTENANCE.md](MAINTENANCE.md) before builds, tests or restoration. Older staging helpers can downgrade the installed candidate.

Preserve the readiness gate and first-clock fix. Current work classifies first-ten-second discard events without assuming they represent recurrence of the solved startup stall.

1. Decode and queue while the initial playback clock remains held.
2. Continue page updates, IPC and presenter activity during the hold.
3. Permit the initial held-clock poster frame; otherwise a future frame and a held clock could wait on each other indefinitely.
4. Require pacing active, presenter awake and a valid sequenced handoff for the current generation. The readiness flags must equal 7 and the generation must match.
5. Release the initial hold only after that evidence. Do not silently bypass the gate on its old timeout.
6. After the hold-release path returns, reset the playback anchor to the current monotonic time. Time spent in release work must not be interpreted as elapsed playback.
7. Deliver the playing clock and continue ordinary selection/presentation.

## Evidence and boundaries

The gate experiment reduced startup queue discards 51 -> 7 and pre-first-flip discards 23 -> 0. The anchor experiment reduced the release-based startup count to zero; first delivered position changed from 150.610 ms to 4.653 ms despite approximately 154 ms delivery after release. The original release logging cost remained; resetting the anchor excluded it from media time.

The historical zero count uses first decode through release +10 s. A different ten-second clock-origin window included two selection skips just beyond that boundary. Queue discards, selected frames lacking completion, and completed-flip gaps are distinct populations. Do not replace one metric with another.

Evidence: `outputs/presentation-chain-audit/STARTUP-GATE-RESULT.md` and `STARTUP-ANCHOR-RESULT.md`. Current source: `entry/OmniMSEPlayer.cpp` and `media/OmniHwService.cpp`. Keep the same definitions when reporting new validation.

Later runs contain selection skips within the first-ten-second reporting window. v141 has six at release +9.480–9.732 s, but none before its first completed flip. v142 adds scoped diagnostic coverage for media positions 0–12 s without changing startup behavior. Media PTS windows and release-relative reporting windows are not interchangeable.

## Release documentation checkpoint: 2026-10-22

The reduced-copy v139 path remains the primary candidate. Five additional v143/v144 validation runs preserve the renderer and accepted startup/clock/lock fixes. An optional bounded empty-queue wait was tested but not promoted: improvements were inconsistent and no eligible wait was captured in the focused follow-up. Its two later gaps were application refresh-target misses, not decoder errors. Keep the wait disabled and retain the copy fallback. Exact results and remaining limitations are in `outputs/queue-reuse-v143/README.md`; the complete documentation index is `outputs/release-candidate-v139/README.md`. No new architectural or wake-margin optimization was made.
