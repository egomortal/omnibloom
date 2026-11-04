# Measured presentation performance

> Current maintenance state: v147 is installed; v139 references below describe its rendering lineage or historical experiments. Read [MAINTENANCE.md](MAINTENANCE.md) before builds, tests or restoration. Older staging helpers can downgrade the installed candidate.

## Initial same-binary v139 A/B

Identical fixture and release +15 to +65 second window, more than 65 seconds of playback each, no trace overflow.

| Metric | Fallback | Direct tiling |
|---|---:|---:|
| Completed flips | 2981 | 2996 |
| Completion gaps >25 ms | 16 | 1 |
| Median wake-to-submission-return | 7.079 ms | 2.280 ms |
| p99 wake-to-submission-return | 9.423 ms | 3.247 ms |
| Maximum wake-to-submission-return | 10.272 ms | 3.851 ms |
| Process CPU core-equivalents | 2.112 | 1.745 |
| Fullscreen entry/exit | PASS | PASS |
| Decoder errors / audio underruns | 0 / 0 | 0 / 0 |

Median preparation was 4.613 ms before and 2.247 ms after, but the old figure excludes subsequent tiling while the new figure includes fused tiling. Use wake-to-submission-return for the comparable end-to-end metric. CPU is process CPU-seconds / measured wall-seconds and excludes separate browser child processes.

Direct tiling was active on all 2996 experimental flips. The single 33.366 ms completion gap occurred at release +39.819217 s. It has not been shown to be expected cadence. A 60.00 fps source on a 59.94 Hz output necessarily needs rate reconciliation, but that does not explain every long completion interval.

The whole-run legacy strict counter check was false in both runs. Report this legacy strict result separately from functional success and the current known-limitation release assessment. Successful VideoOut completion is a software presentation proxy, not optical scanout verification or proof of physical audibility.

## Reproduction and promotion

Use unique run tags, preserve raw trace and process logs, and analyze the same window. `outputs/reduced-copy-v139/analyze_ab.py` accepts tag/PID pairs and writes analysis files plus comparison.json. Preserve the original comparison before invoking it for another pair.

Validate multiple repeats and different 4K60 sources, seeks, repeated fullscreen transitions, overlays, ordinary pages and long sessions. Record untested cases as pending. Retain diagnostics and the copy fallback. Evaluate release using current behavior, reproducibility, severity, growth and compatibility. Document tolerable residual events as known limitations; missing historical state is not an independent blocker.

## Repeat validation update

Two additional identical-fixture runs completed 65.724 and 65.043 seconds. In the fixed later window they completed 2995 and 2994 direct flips, with 2 and 3 gaps respectively. Wake-to-submit medians were 2.317 and 2.287 ms; CPU was 1.760 and 1.753 core-equivalents. Fullscreen passed, decoder errors and audio underruns were zero, and trace overflow was zero. Gap timestamps differed between runs: the original single gap is not a fixed reproducible event.

A trace audit also found 2, 1 and 1 selection-skip records in the release-based startup window for the original direct run and the two repeats. The earlier v137 zero count must not be carried forward as a measured v139 guarantee. Accepted startup code remains intact; this is a validation result, not a reason to silently change those fixes.

The additional motion-pattern clip completed 65.953 seconds and 2995 later direct flips, with two later completion gaps and median wake-to-submit 2.284 ms. Its whole-run pacing counters include a 14-discard bucket even though only two later completed-flip gaps were counted. Display repetitions and queue discards are different metrics; the favorable completion count does not erase that burst. Promotion remained pending at that stage.

Raw results and all per-flip rows are in outputs/reduced-copy-v139/; repeat-summary.json preserves the startup records. All clips tested so far are controlled fixtures, not broad streaming-site coverage.

The distinct-frame audit found 13 repeated prepared PTS values in the motion clip and six in the grid clip within their fixed later windows. Thus completed flips alone overstate unique-frame delivery in those runs. The combined seek/fullscreen/overlay test passed its functional checks but failed pacing acceptance. These findings previously withheld promotion under the strict policy. They remain measured observations to assess for current visible impact; no rendering optimization was introduced during validation.

## First endurance session

The bounded ten-minute fullscreen session completed and exited normally. The page confirmed 590.632 seconds of actual media progression at 3840x2160. The fixed release +15 to +590 second window contains 34,432 completed flips, all direct, and 34,412 distinct prepared PTS values (20 consecutive repeats). There are 34 completion gaps over 25 ms; the maximum is 33.383 ms. Median wake-to-submit is 2.359 ms. Fullscreen entry/exit passed; decoder errors and audio underruns were zero. No trace overflow (327,472 records).

This is repeated-content endurance using continuous timestamp offsets, not unique footage. The filtered endurance trace is intentionally different from short-run diagnostics, so its CPU measurement is not a controlled comparison. The legacy strict pacing check fails, including two 12-discard buckets and one four-discard bucket. Do not label every remaining gap expected cadence without a demonstrated causal chain. Full results and per-flip identities: endurance-analysis.json and endurance-flips.json.

## Current release assessment

Reduced copy is the primary candidate. Preserve its fallback and all accepted startup, clock and lock fixes. Judge current reproducible defects and estimated or observed user-visible impact, with per-event causes and clustering reported separately from averages. Infrequent, non-growing residual events may be documented as limitations. Nonzero counters and historical unknowns are not automatic vetoes; logs alone cannot prove invisibility. Actual corruption, crashes, audio failure, broken controls or materially growing hitch patterns require a named limitation or focused resolution.

Latest results and release documentation: `outputs/release-candidate-v139/RELEASE_NOTES.md`, `VALIDATION_CHECKLIST.md`, and per-run `*-polish.json`. No architectural optimization is part of this validation batch.

## Release documentation checkpoint: 2026-10-22

The reduced-copy v139 path remains the primary candidate. Five additional v143/v144 validation runs preserve the renderer and accepted startup/clock/lock fixes. An optional bounded empty-queue wait was tested but not promoted: improvements were inconsistent and no eligible wait was captured in the focused follow-up. Its two later gaps were application refresh-target misses, not decoder errors. Keep the wait disabled and retain the copy fallback. Exact results and remaining limitations are in `outputs/queue-reuse-v143/README.md`; the complete documentation index is `outputs/release-candidate-v139/README.md`. No new architectural or wake-margin optimization was made.
