# Presentation threads and ownership

> Current maintenance state: v147 is installed; v139 references below describe its rendering lineage or historical experiments. Read [MAINTENANCE.md](MAINTENANCE.md) before builds, tests or restoration. Older staging helpers can downgrade the installed candidate.

## Accepted handoff fix

`entry/OmniBrowser.cpp` owns `omniPresentLock`. Acquirers are UI main (`omniPresentFrame`), presenter (`omniPresenterMain`, including condition-variable reacquisition), and shutdown (`omniStopPresenter`). Intentional condition-variable sleep is not lock contention.

Mask preparation moved before the handoff critical section. Publication still checks the frame pin and epoch. Compatible SDL-owned CPU buffers exchange pointers rather than copying the entire screen under the lock. External, locked, RLE, mismatched and smaller surfaces retain the copy fallback.

Measured maximum UI hold fell from 11.777 ms to 0.053 ms; protected pixel transfer averaged 2.720 ms before versus 0.005 ms after. These are historical single-run measurements, not general guarantees. Evidence: `outputs/presentation-chain-audit/LOCK-RESULT.md` and its per-owner CSV files.

## Direct tiling lifetime

The service's composition ownership protects the selected RGBA layer and overlay mask until synchronous tiling completes. `plane.lock` protects shared plane/clock state; it is distinct from the browser handoff mutex. Do not replace these lifetimes with an unpinned pointer handed to another thread. The candidate introduces no asynchronous borrowed-frame ownership.

The presenter performs selection, preparation, submission and completion observation. Decode/service production and page/UI updates remain separate. CPU measurements include UI/service/presenter threads in one process; separate WebProcess and NetworkProcess are excluded.

## Wake policy

Wake margin uses measured lead, handoff and reflip costs plus 0.5 ms. The existing minimum is 3 ms; smaller planes retain the 3.8 ms maximum, while large planes may use up to one refresh period minus 2 ms. If the preparation deadline has passed but refresh is still ahead, wake promptly (at least 1 ms), rather than skip a whole refresh opportunity. Integer waits round down on the paced path to avoid consuming the margin.

Direct tiling was compared without changing this policy. Its fused tiling is part of preparation, so do not add that duration again when estimating total work. The previously proposed 11 ms fixed lead was not applied.

## Release documentation checkpoint: 2026-10-22

The reduced-copy v139 path remains the primary candidate. Five additional v143/v144 validation runs preserve the renderer and accepted startup/clock/lock fixes. An optional bounded empty-queue wait was tested but not promoted: improvements were inconsistent and no eligible wait was captured in the focused follow-up. Its two later gaps were application refresh-target misses, not decoder errors. Keep the wait disabled and retain the copy fallback. Exact results and remaining limitations are in `outputs/queue-reuse-v143/README.md`; the complete documentation index is `outputs/release-candidate-v139/README.md`. No new architectural or wake-margin optimization was made.
