# 4K60 investigation history

> Current maintenance state: v147 is installed; v139 references below describe its rendering lineage or historical experiments. Read [MAINTENANCE.md](MAINTENANCE.md) before builds, tests or restoration. Older staging helpers can downgrade the installed candidate.

This is an evidence history, not a stable-4K60 certification. Version labels identify experiments; they do not imply installed versions.

| Stage | Finding and action | Evidence |
|---|---|---|
| v129-v131 | Handoff ownership blocked the presenter. Prepare masks outside the lock and exchange compatible buffers under it. | LOCK-RESULT.md |
| v132-v134 | Playback release preceded presentation readiness. Generation-matched readiness gate reduced 51 startup discards to 7. | STARTUP-GATE-RESULT.md |
| v136-v137 | Anchor captured before blocking release work caused a stale playing position. Reset after return; release-based startup count became zero. | STARTUP-ANCHOR-RESULT.md |
| v137 later analysis | 18 later gaps: 17 preparation-margin cases and one clock deferral. | LATER-18-GAPS-RESULT.md |
| v138 | Intermediate 33 MB video copy consumed 99.67% of preparation time; next SDL tiling was an additional transfer. | COPY-PATH-RESULT.md |
| v139 | Flag-gated direct RGBA-to-tiled output, preserving overlays and fallback. Same-binary A/B reduced 16 later gaps to one. | reduced-copy-v139/README.md |

Historical audit files are under `outputs/presentation-chain-audit/`; v139 files under `outputs/reduced-copy-v139/`. v105 is an old historical baseline, not the current installation assertion. The v119 installation was the pre-experiment state. v139 was subsequently installed experimentally on canonical and tile paths, with a separate v119 fallback. Diagnostic builds are temporary; use the latest restoration manifest for current installation.

Keep accepted startup, clock and lock fixes. Do not reopen decoder or unrelated rendering work to explain a presentation gap without new evidence. Promotion requires repeated and broader validation, not a version-number increase.

## Validation follow-up

Two independent repeats and two additional synthetic 4K60 clips retained the v139 speedup. v140 adds only opt-in validation controls, not a rendering optimization. Four fullscreen cycles and two seeks passed; overlays exercised direct and fallback paths. The ten-minute session reached 590.632 s of media time, with no decoder errors/audio underruns, but repeated frames and discard bursts remain. Default promotion was withheld at that stage under the earlier strict policy. See outputs/reduced-copy-v139/VALIDATION.md for the full result and limits.

## Current validation and release policy

v141 adds scoped diagnostic windows; v142 additionally traces media positions 0–12 s and runs grid endurance and motion/seek/overlay workloads. Neither changes rendering or startup behavior. Missing historical events remain archived, not release gates. Current defects, practical impact and bounded known limitations control the release decision. See `outputs/release-candidate-v139/` for event chains, maintenance notes and release documentation.

## Release documentation checkpoint: 2026-10-22

The reduced-copy v139 path remains the primary candidate. Five additional v143/v144 validation runs preserve the renderer and accepted startup/clock/lock fixes. An optional bounded empty-queue wait was tested but not promoted: improvements were inconsistent and no eligible wait was captured in the focused follow-up. Its two later gaps were application refresh-target misses, not decoder errors. Keep the wait disabled and retain the copy fallback. Exact results and remaining limitations are in `outputs/queue-reuse-v143/README.md`; the complete documentation index is `outputs/release-candidate-v139/README.md`. No new architectural or wake-margin optimization was made.
