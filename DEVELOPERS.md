# Developing Omnibloom

Omni is the browser app in the Omnibloom suite. This candidate contains built-in pages, bundled add-on source, desktop Setup and docs. Native engine, vault and performance work are maintained separately. No installed console version or binary acceptance is asserted here.

The native title/startup process launches browser child processes. The browser shell connects navigation/input/platform services to WebKit; web pages use a native host bridge. Desktop rendering does not prove those native actions. Native process/engine source is outside this CLEAN PC/UI candidate. The display label is Omni; content identity/version are unchanged.

| Included source | Purpose | Limit |
| --- | --- | --- |
| omni/pages/bundle-clean4/ | Final CLEAN4 built-in pages (50 routes, 15 Universes, HDR and video stats), the pages of native builds s3.4c and s3.4d | Only the 4K60 SDR playback path is console-confirmed; all-route native acceptance remains open. |
| omni/pages/bundle-r46/ | Previous integrated built-in pages (r46) | Native acceptance and later proposals remain separate. |
| addons/bundled/ | Actual bundled payload source | Eleven manifests, not every proposed add-on installed. |
| setup/ | Desktop source/spec | No executable committed; packaging is not installation validation. |
| docs/site/ | Documentationv2 with reviewed content layers | Final release claims/links/language review remain required. |
| docs/tutorials/ | Piper captions/voice metadata | Media/model-output rights are a separate selection gate. |

JIT policy is an engine build/runtime matter, not a universal has/no-JIT promise. This package changes no engine policy. Master Control's full current source joins only after its review clears; attribution files do not constitute review clearance.

Dispatch through stable IDs/protocol values, never translated labels. Preserve user names, URLs and editable text. Test focus during async replies, failed operations, modal dismissal and restoration. Mock replies are local fixtures, not native success. Translation drafts require human review.

The actual baseline is bundle-r46. A029/Sleeve and new art are separately reviewed proposals, not silently integrated. Match source hashes and apply only the owned changes, retaining measured validation.

[BUILD.md](docs/BUILD.md) provides source checking, reproducible source archives and optional host-OS Setup packaging. It does not compile the engine or run an installer. Preserve [notices](THIRD-PARTY-NOTICES.md), authors and licence files. Keep credentials, device addresses, personal logs, system files and compiled outputs outside source contributions. Rights/corresponding-source findings remain gates.

## Developer flags and override files

Omni reads the files below from `/data/omni/` on the console, but no screen in Omni or Setup creates them. A flag works by existing (its content is ignored); a text file is read for its first line or its `KEY=VALUE` lines. Most are read once when Omni starts, so restart Omni after a change. Create or delete them with any FTP client connected to the console's FTP server (the same server Setup uses). Setup has no flag editor; its diagnostics bundle only lists the names of the `*.flag` files present (`omni/flags.txt`). Removing the file always restores the default. Other files in `/data/omni/` (settings Omni or Setup write, self-test flags, other experiments) are not covered here.

Kill switches (default on; the flag turns the feature off):

| File | What it changes | Without it | For | Risk |
| --- | --- | --- | --- | --- |
| ytguard-off.flag | Removes the YouTube attestation guard (reloads a /watch page once, at the current position, when YouTube stops attesting the session) | Guard installed | Debugging YouTube playback | YouTube may stop after about a minute again |
| nc-reset-off.flag | Skips the one-time move of an old-format HTTP cache aside (renamed, never deleted) | Moved once per profile | Debugging cache migration | Old cache with missing bodies stays in use |
| popup-gesture-off.flag | Allows new windows without a user press while the blocker is on | Popups need a real press/click | Debugging sites that open windows | Pop-up ads get through |
| ublock-frames-off.flag | uBlock site rules go back to top-frame only when `ubo-content-mainframe-only.flag` is set | Per-host rules also run in subframes | A/B of the frames change | Ads inside embedded players reappear |
| ubo-site-rules-disabled.flag | Per-site uBlock content scripts off; the full ~5.4 MB content bundle is registered instead | Per-site scripts | Experiments, fallback | Slower pages (interpreted JavaScript in every page) |
| ubo-content-disabled.flag | No uBlock cosmetic filtering or scriptlets at all | On | Debugging page breakage | Network blocking stays; on-page ads and anti-adblock walls return |
| pages-off.flag | Built-in `omni://pages` off; the old native new-tab page comes back | Built-in pages | Debugging | Start, welcome and info pages are gone |
| smooth-draw-disabled.flag | Returns 4K page drawing to the plain SDL paths (no AVX2 doubling/swap) | Fast draw path | A/B, debugging | Higher CPU per frame |
| perf-a-disabled.flag, perf-a-s1..s8-disabled.flag | All, or one, of the shell present optimisations: s1 paint back-off, s2 present only changed rows, s3 hashed overlay changes, s4 partial redraw, s5 draw from the half-size page, s6 transparent-row kernel, s7 deferred hand-off, s8 vblank timing | All on | A/B, debugging | More CPU and dropped frames |
| page-native-4k.flag | On a 4K display the page is painted at full resolution instead of half size and doubled | Half resolution | Experiments | Much slower page paint |
| playback-rate-disabled.flag | `playbackRate` always 1 (no time stretching) | 0.25x to 2x with pitch kept | Debugging audio | Speed controls on sites stop working |
| holepunch-v5-disabled.flag | Video playback falls back to V4 buffering (no deep input/decoded queues for 2-3 s stalls) | V5 | A/B | Stutter during main-thread stalls |
| holepunch-v7-disabled.flag | Turns off presenter re-flips that show a newer video picture when no new canvas arrives | V7 | A/B | More dropped video frames |
| c56-videofix-disabled.flag | Video on the plane no longer keeps the earlier page-paint/refresh cadence | Fix on | A/B | Video regressions of candidates 55/56 |
| c56-videofix2-disabled.flag | Fullscreen video no longer filters repeat mouse moves or parks the mouse after 3 s | Fix on | A/B | Fullscreen control bar may never fade |

Opt-in (default off; the flag turns the feature on):

| File | What it changes | Without it | For | Risk |
| --- | --- | --- | --- | --- |
| yt-attest-log.flag | Logs YouTube BotGuard/player/videoplayback request metadata (host, path, status, sizes; no ids, tokens or cookies) to the process log | Nothing logged | Debugging YouTube attestation | Log volume only |
| ubo-content-mainframe-only.flag | uBlock content scripts in the top document only; network blocking still covers every frame | Every frame | Performance experiments | Less cosmetic filtering in iframes |
| ubo-content-pageworld.flag | uBlock content scripts run in the page's own JavaScript world instead of an isolated one | Isolated world | Experiments | Pages can see and interfere with the scripts |
| ubo-site-debug.flag | One counter line per per-site script build in the log (no host names) | Silent | Debugging | None known |
| ubo-site-generic-top-only.flag | Generic per-site scripts (`always-generic.js`) top frame only | Follows the main-frame setting | Experiments | Less generic filtering in iframes |
| pages-dev.flag | Built-in pages load from `/data/omni/pages-dev/` (needs `start/index.html` there) instead of the packaged ones | Packaged pages | Page development | Broken or old pages if the folder is stale |
| paint-hold-experimental.flag | Paint-hold experiment (`OMNI_PAINT_HOLD_V1`) on https YouTube hosts only, never in test modes or private tabs | Off | Experiments | Experimental; effect on current builds unclear |
| perf-a-s8-align.flag | Lets s8 restart the refresh timer to line up with vblank | Timer runs at the display period | Experiments | A timer that is not re-armed stops the shell |
| gpu-pages-zerocopy.flag, gpu-pages-zerocopy-off.flag | Experimental GPU-pages builds only: page frames go to the screen without a CPU copy (needs the async-read flag); `-off` wins over the on flag | CPU path | Experiments | Experimental build path; can make pages fail to show |
| tab-media-keep-audible.flag | A background tab's video keeps playing if it is audible (its hardware decoder is still released) | Paused after a short grace time | Users who want background audio | Background tabs keep using CPU and audio. Newer builds also offer this as the Background audio setting |

Override text files:

| File | What it changes | Without it | For | Risk |
| --- | --- | --- | --- | --- |
| ua-desktop.txt | First line (20-400 printable ASCII) replaces the desktop user agent | Built-in Safari 17 string | Site-compatibility tests | Sites may serve broken or blocked pages |
| ua-youtube-tv.txt | First line replaces the user agent used on youtube.com/tv | Built-in Cobalt-style TV string | YouTube TV A/B | TV app may refuse to load |
| jsc-env.txt | Up to 32 `JSC_<option>=VALUE` lines set JavaScriptCore options (GC tuning); cannot turn the JIT on | JSC defaults | Experiments | Can make pages slow or crash |
| raster-env.txt | `OMNI_RASTER_*=VALUE` lines set the page process's threaded-raster settings; other keys are ignored | Built-in raster settings | Experiments | Can make pages paint wrongly or slowly |
| video-quality.txt | Video frame scaling: `low` (bilinear, no mipmaps), `none` (nearest), `direct` (purpose unclear) | Prescaled bilinear | Debugging video paint | Lower picture quality |
| display-hz.txt | Display rate used to lock video clocks (e.g. `59.94`) | 60000/1001 Hz | Experiments on other refresh rates | Wrong value adds drops or audio pitch shift |

Unclear: `addons-dev.flag` and `yt-media-stop.txt` (a test-harness file) appear in an audit of console builds, but nothing in this source tree reads them, so their effect is not documented here.
