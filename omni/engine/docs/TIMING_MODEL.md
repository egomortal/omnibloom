# Presentation timing model and interpretation

> Current maintenance state: v147 is installed; v139 references below describe its rendering lineage or historical experiments. Read [MAINTENANCE.md](MAINTENANCE.md) before builds, tests or restoration. Older staging helpers can downgrade the installed candidate.

## Three clocks

Media PTS identifies content. The monotonic service clock determines which PTS is due. The predicted refresh grid determines the presentation opportunity. Never subtract media PTS directly from monotonic timestamps, or equate a preparation target with a measured hardware latch deadline.

A selected frame follows selection → handoff/preparation → submission → completion observation. Presenter selection can update the main thread's earlier handoff selection to suit the refresh it is actually approaching. Match sequence, epoch and PTS; a handoff is not itself proof that a frame was displayed.

## Existing preparation margin

The wake policy includes measured lead, handoff and reflip costs plus 0.5 ms. The minimum is 3 ms. Smaller planes retain a 3.8 ms ceiling; large planes can reserve up to a refresh period minus 2 ms. A passed preparation deadline should cause a prompt wake while refresh remains ahead, rather than automatically abandoning the opportunity. Paced integer waits round down to preserve preparation time.

Direct tiling was validated with this policy unchanged. Its tiling cost is already part of preparation. Do not add it twice. The earlier 11 ms fixed-lead proposal was not applied. Reducing the measured preparation work does not prove the scheduler or hardware must meet every deadline.

## Repeats and misses

| Classification | Required evidence | Interpretation |
| --- | --- | --- |
| Queue reuse | Empty converted queue at selection and completion of the current picture again | Supply was absent at that selection instant; not automatically slow decoding |
| Clock-correction repeat | Before/after clock values make the next queued frame ineligible | Preserve sync; do not simply force the next frame |
| Application refresh-deadline miss | Submission finishes after the applicable predicted target | Application missed its target; hardware latch timing remains unmeasured |
| Late wake | Wake occurs after the intended opportunity | Trace upstream scheduling before assigning a cause |
| Unknown | Necessary state outside the focused trace window or missing identity | Keep unknown; do not relabel as cadence |

A normal completion interval can repeat a picture. A long interval can contain a new picture. Report the overlap rather than adding the two counts. With exactly 60.000 fps content and 59.940 Hz output, a rate mismatch is expected, but arithmetic alone cannot classify a particular repeated picture, skipped frame or burst.

## Windows and visible impact

Uninterrupted short comparisons use release +15 through +65 seconds; endurance uses +15 through +590 seconds. First-ten-second discards use release through release +10 seconds in recent reports. Record the origin explicitly because older experiments used different origins.

Seeks, fullscreen changes and active overlays belong to a separate interactive workload. Do not call its 480 long intervals steady-playback failures, or conceal them in an endurance average. A roughly 33 ms interval may add a refresh of picture hold; clustered events and the measured approximately 117 ms interactive maximum can be noticeable. Physical visibility and audibility remain unverified.

## Narrow queue-wait experiment

v143 tests whether an early canvas wake can wait briefly for a converted frame before repeating an already completed picture. It requires matching completed sequence/epoch, active playing/pacing, a compatible direct layer, no pending ready/poster state and an empty converted queue. It uses the existing preparation margin, releases composition and plane locks while sleeping, and stops on queue arrival, state change or budget exhaustion.

This is an opt-in experiment (`empty-queue-wait-test.flag`), not a release default. It must not delay an unpresented new handoff or held-clock startup. Events 146/147 capture wait entry, deadline, identity, elapsed time and exit reason only within existing focused windows. A/B results, not the hypothesis, decide whether to retain or enable it. See `outputs/queue-reuse-v143/README.md` for current status.

The completed diagnostic follow-up recorded zero eligible waits in 448 focused checks. One later gap had 3.739 ms of direct tiling against 3.521 ms available lead; submission returned 281 us late. The other returned 433 us late but lacks the internal preparation breakdown. Both have approximately 33.37 ms completion intervals. This establishes application target misses without a new renderer or margin change. The optional wait remains disabled; lower repeat counts alone were not credited to it.
