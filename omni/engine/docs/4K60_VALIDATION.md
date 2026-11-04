> Update: v139 is now installed experimentally by explicit user request. [Event attribution and fallback instructions](../../../outputs/reduced-copy-v139/EVENT_ATTRIBUTION.md). Stable-release classification remains incomplete; the earlier restoration/withholding decision below is historical.

# Reduced-copy validation documentation

- [Video pipeline](VIDEO_PIPELINE.md)
- [Startup sequence](STARTUP_SEQUENCE.md)
- [Threads, locks and wake timing](THREADS_AND_LOCKS.md)
- [4K60 history](4K60_HISTORY.md)
- [Performance findings](PERFORMANCE_FINDINGS.md)
- [Complete validation report](../../../outputs/reduced-copy-v139/VALIDATION.md)
- [Reproduction instructions](../../../outputs/reduced-copy-v139/REPRODUCE.md)

Decision: retain the reduced-copy candidate, but do not promote it yet. Broader validation still finds frame repetitions and discard bursts. Diagnostics and fallback remain intact. The pre-test v119 installation was restored and hash-verified on both console paths; no validation flags or running browser remain. See outputs/reduced-copy-v139/final-validation-console-state.json for evidence.
