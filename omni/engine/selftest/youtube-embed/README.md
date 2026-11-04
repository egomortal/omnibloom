# Official IFrame API diagnostic

Serve this directory over HTTP(S), open index.html, and initialize after document
load using the button or `window.omniStartMediaTest()`. Initialization never calls
playVideo. Only a trusted user click on Play does so; a script-generated JavaScript click
is intentionally ignored. If Omni's controller input produces untrusted clicks,
use the embedded player's own controls manually and record that limitation.

Based on Google's [official IFrame API reference](https://developers.google.com/youtube/iframe_api_reference),
including its public sample video M7lc1UVf-VE and onReady/onStateChange/onError/
onAutoplayBlocked callbacks. The origin parameter is supplied; no browser security
or network protections are disabled. Code does not solve challenges or inspect
the cross-origin iframe. The official sample's automatic playback is not used.

Readiness timeout is 30 seconds. Waiting-user is a distinct state with no pending
timer: embed readiness PASS is not playback PASS. After a user Play request there
is a separate 30-second start timeout. A playing event records only the API's
reported state, not verified picture/audio or completion. Logs contain bounded
event names/numeric codes and capability types, never URL/header/token/cookie
values. The API still makes normal external YouTube requests.

Use omniYouTubeDiagnostic.snapshot() and omniFeatureResults together; a generic
all-results-pass check alone cannot establish playback. Results cap at 32, events
at 64. Stop or navigation clears timers and destroys the player. Reload to retry.
This fixture is a diagnostic, not a YouTube fix. Console v42 passed the six-second
observation with 6.301 seconds of playback progress; native frame/PCM evidence
exists, but dropped frames remain substantial and physical sound is unverified.
See `docs/MSE-EXPERIMENT-HANDOFF.md` for exact log identifiers and deployment state.

Follow [the ordered picture/audio test plan](../../../docs/YOUTUBE-PLAYBACK-TEST-PLAN.md)
for local MSE prerequisites, real-user playback, error interpretation and current
codec/memory limits. A readiness or playing event alone is not verified picture
and sound.


## Authorized bounded selftest

`outputs/run-youtube-embed.py` stages this fixture with `window.omniYouTubeAutoTest=true`, enables the experimental MSE flag, launches the existing browser once, and restores previous flags/assets using the MSE runner safeguards. Only run it when a console diagnostic is intended. Default manual page behavior is unchanged.

Automatic mode invokes the official IFrame `playVideo()` once after ready; it does not synthesize trusted input or override activation policies. It records `AUTOPLAY_BLOCKED` when reported and completes within 25 seconds. No CAPTCHA interaction or retry occurs. Numeric state/error events are included in the final feature result. PASS requires at least 3 seconds of getCurrentTime advancement over a six-second observation and PLAYING state at completion. Seven numeric time/state samples and optional loaded fractions are retained. This does not prove rendered frames or audible sound. The runner captures fresh native MSE counters separately and rejects reported native errors; physical audibility remains unverified. Network/provider restrictions may prevent playback independently of local MSE fixture success.

Offline validation: `node harness-test.cjs` covers manual gating, explicit automatic request, duplicate-ready guard, blocked/error/timeout cleanup. These use an API stub, not real YouTube. The runner's restoration machinery is shared with the independently mocked MSE runner.
`--long` requests a 30-second observation with at least 15 seconds of time advancement, a 50-second fixture deadline, and a scoped long-media-selftest flag restored after the run. The native browser must support that flag (55-second result collection / 65-second hard stop); the hbldr request alone gets a 75-second timeout. Default short tests remain six seconds with a 25-second total deadline. The configurable window.omniYouTubeObservationSeconds accepts integers 6..30 only.
