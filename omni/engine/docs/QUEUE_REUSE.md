# Queue reuse and remaining presentation events

The optional queue wait is disabled. Current evidence does not justify making it a release default. Preserve the startup, lock, anchor and direct-tiling fixes.

## Classify the stage before changing behavior

| Observation | Evidence needed | What it does not establish |
|---|---|---|
| Empty-queue reuse | Converted queue empty at selection; same sequence/epoch presented again | Slow decoding, because raw/decoded supply is a different queue |
| Clock-related repeat | Before/after clock values make the next PTS ineligible for the target | Every negative clock correction is harmful |
| Refresh-target miss | Submission-return time exceeds the applicable predicted refresh target | Exact hardware latch timing or a hardware defect |
| Late wake | Intended wake, actual wake, then matched preparation/submission | The upstream scheduler cause without further evidence |
| Historical unknown | Missing state or event outside captured windows | Cadence, success, or failure of a particular fix |

A normal ~16.7 ms completion interval can repeat content. A ~33.4 ms interval can complete a new picture. Report both metrics and their intersection. Queue discard counts, repeated picture identities and long completion intervals must not be summed as one loss count.

Exactly 60.000 fps content against ~59.940 Hz requires rate reconciliation, roughly one frame per 16.7 seconds. That arithmetic does not classify individual events, explain a burst, or prove invisibility.

## Bounded-wait experiment and why it remains disabled

`v143WaitEmptyQueue` only considers an already completed matching frame identity/epoch, compatible full-frame direct layout, active playing/pacing, valid startup state, no ready/poster replacement and an empty converted queue. It reserves the existing preparation margin; sleeps release both composition and plane locks and revalidate state after reacquisition. It must not delay the first poster or a new unpresented handoff.

Four same-binary A/B runs: original fixture repeats 1 OFF / 2 ON; grid fixture repeats 14 OFF / 3 ON. Completion-gap counts did not improve. Focused detail did not capture a wait execution, so the repeat reduction was not attributable to waiting. The 14-repeat grid cluster recurred approximately every 50 ms over ~0.65 seconds; whole-run averages should not hide its possible visibility.

The v144 follow-up had zero repeats and two long intervals, but zero eligible waits in 448 captured checks. Most checks saw a nonempty converted queue; many also had a changed handoff identity. The previous cluster did not recur. This is evidence against claiming a demonstrated wait benefit, not a reason to remove guards.

One later gap had 3.739 ms direct tiling against 3.521 ms available lead and returned 281 microseconds after the application target. Another returned 433 microseconds late with incomplete internal breakdown. Neither justifies reopening decoder, startup or handoff-lock investigations without new evidence.

## Reporting and safe next steps

Use release +15 to +65 seconds for comparable uninterrupted short tests, with explicit exceptions for other fixtures. Report startup and seeks/fullscreen/overlay transitions separately. Identify the current installed build and instrumentation mode. Record counts, worst clusters and measurement coverage; do not certify harmlessness without user-visible evidence.

If a current reproducible repeat needs further work, capture the queue head/depth, selected identity, before/after clock values, target, preparation, submission and completion for that event window. Preserve unknowns when detail is missing. Do not expand production HUD instrumentation to obtain these diagnostics: its no-tracing/no-new-probe contract is separate.

[Full experiment and captured events](../../../outputs/queue-reuse-v143/README.md). [Timing model](TIMING_MODEL.md). [Maintainer entry point](MAINTENANCE.md).
