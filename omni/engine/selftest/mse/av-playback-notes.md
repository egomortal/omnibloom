# Unmuted separate-track baseline

Serve `av-playback.html` alongside `generated/`. Start via the button or
`window.omniStartMediaTest()`. Read `window.omniAVPlaybackResult` and
`window.omniFeatureResults`. Overall timeout25s fits the staged30s harness;
the ended event must occur within10s of play. Fixtures are original generated
content, appended sequentially without remove/seek operations.

JavaScript PASS requires positive decoded-frame progression, timeline progress
past3.5s, ended, and unmuted positive-volume state. This is insufficient to claim
audio output: additionally inspect the same run's native process log for
`OMNI MSE:` records with `pcmSubmittedFrames > 0`, `pcmChunks > 0`, `errors=0`,
and an ended record. PCM submission means data reached the SDL queue, not that
the TV/speakers made sound. Physical audibility is always marked NOT_VERIFIED.
Autoplay rejection is a reported failure; there is no muted fallback hiding it.

Host checks:

```sh
node --check av-playback.js
node av-playback-harness-test.cjs
```

Mock checks passed for success, unsupported API, HTTP failure, play rejection,
unchanged frame counts, playback timeout, duplicate calls and cleanup. They do
not execute a real MSE decoder or establish console compatibility. Existing
smoke.js and its mutation/seek test are unchanged.

The explicit deployment runner is `outputs/run-mse-baseline.py --av` from the
workspace root; its default mode remains the original smoke test. AV mode stages
these HTML/JS files, preserves previous assets/flags, and reports AV PASS only
when both the matching JavaScript result and fresh native ended/positive PCM
counters agree with zero errors. It accepts the console's `browser: [...]`
result format; FEATURE DIAG numeric counts alone cannot pass. Logs/results use
the `mse-av-baseline-` prefix. `outputs/test-run-mse-baseline.py` tests parsing,
freshness, negative audio evidence and both mocked stage/restore modes without
network access. Those four tests passed; the runner was not executed on-console
as part of this change.
