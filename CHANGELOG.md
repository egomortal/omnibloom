# Changelog

## v0.5.3

Console package: Omni 0.5.3 (title f16ff5d6, engine a5083735, engine starter a3853c3a); Bloom Core, Downloads
(downloader-9) and USB Files unchanged. Tested: 4 + 4 console launches plus a 20-launch soak with layers off and Master Control 0.4.5.

### Less memory while a page loads
- **Omni's own engine starter** (`omni/native-title/starter/`, `/data/omni/native/omni-starter.elf`, 127.0.0.1:9031)
  starts the engine processes instead of the payload loader, which kept ~240 MB (up to ~420 MB) after every start.
  It maps the engine file and relocates it in 16 MB pieces. Falls back to the payload loader when it isn't there.
- **No idle spare engine** by default (`OMNI_SPARE_LAZY_V1`); `/data/omni/spare-reserve.flag` brings it back.
- Low-memory warnings in our launch tests: 15 of 16 launches before, 0 of 15 after.

### Refinement pass (code review of every part)
- **Engine starter V3:** never listens anywhere but 127.0.0.1 (if it can't take its port it now exits; before, it
  could end up listening on every network interface); checks each engine file before loading it (a cut-off or
  damaged file is refused instead of crashing the starter); answers a `version` request, so Omni replaces an older
  starter that is still running; tells Omni when a request is refused or fails; never leaves a half-started process.
- **Omni only sends its own engine files to the starter**; anything else goes to the payload loader as before.
- **Ad block** (`OMNI_UBLOCK_REFINE_V1`): one request the uBlock engine can't judge is blocked on its own, instead of
  switching every page to "Filtering failed" until Omni restarts; the popup filter's wildcard matcher is linear (a
  crafted popup address could freeze the UI for seconds); the private-network guard reads IPv6 addresses by their
  bytes (IPv4-mapped addresses in hex, like `[::ffff:7f00:1]`, and `[::]` got through to the console and LAN); a
  damaged or unreadable rule file counts as a failure, not as "not installed"; the missing-rules notice says what is
  still on.
- **Shortcuts:** a failed save (full disk) no longer replaces the saved shortcuts with a cut-off file.
- **Setup:** ad block rule sets are judged file by file against every set Setup knows (a set replaced by hand after
  a Setup install is kept; a half-finished update is finished); resuming an interrupted install finds the original
  file even when its backup was never made; undoing an interrupted first install also removes the title files;
  files already identical are not rewritten (no more `.prev-*` pile-up); diagnostics keep log times (an IPv6 pattern
  wiped every `12:34:56`) and no longer read the Quick access buttons; a JDownloader step error no longer aborts a
  finished install; CI runs every Setup test.
- **Downloads worker** (in the source; the console package still carries downloader-9, so these reach the console with the
  next Downloads build): a JDownloader fallback no longer reports a finished
  download as failed; one failed connection accept no longer stops every later download until a restart; a progress
  report without a byte count no longer aborts the download.

### Ad block rules can be updated
- Rule sets are versioned (`omni/engine/resources/ublock-rules.json`) and built by `omni/engine/tools/ublock-lists/`.

### Known issues
- With the experimental GPU page drawing ("layers") on, a video can stop with data buffered (3 of 23 test runs; none
  with layers off). Layers stays off by default.

## v0.5.2 (November 15, 2026)

### New in Omni
- **Controller shortcuts, hold L2** (`OMNI_L2_CHORDS_V1`): L2 + Square copies (selected text, else the link under the
  pointer, else the page's address), L2 + Triangle pastes into the focused text box, L2 + Cross opens the Quick bar,
  L2 + Circle opens Browser settings. A tap of L2 still opens saved links (it now fires on release). Only while
  browsing: not in the keyboard, settings, a panel or fullscreen video.
- **Dark mode: Off / Natural / Forced** (`OMNI_DARK_CHOICE_V1`, `/data/omni/dark-style.txt`). Natural asks every
  site for dark (`prefers-color-scheme`); Forced also darkens pages that stay light. The old "Dark pages (all sites)"
  setting carries over.
- **Quick access row:** choose its buttons and their order, up to 6 (`OMNI_QA_CUSTOM_V1`, `/data/omni/quick-access.txt`).
- **Hide the bars:** the quick-access row and the bottom button bar can each be hidden (`OMNI_BARS_HIDE_V1`,
  `/data/omni/ui-bars.txt`); the page gets the space.
- **Create button** opens Browser settings (`OMNI_SETTINGS_CREATE_V1`).
- **11 add-ons built in** (Dark Reader, SponsorBlock, ClearURLs, video speed, YouTube comfort, subtitle style, link
  hints, image zoom, audio tools, cookie-banner reject, auto theme); Omni loads up to 40 add-ons, was 24
  (`OMNI_ADDON_CAP_40_V1`).
- **Starts on a fresh install** (`OMNI_FIRST_RUN_V1`): the title no longer needs `/data/omni/omni-engine.elf` and
  `browser-mode.flag`.

### YouTube
- **Video buffer 64 MiB per stream, was 32 MiB** (`OMNI_MSE_QUOTA_V1`, on by default). 4K HDR filled 32 MiB in
  about 10 s; YouTube's player then stopped asking for media ("freeze at ~11 s") and Omni's guard reloaded the page.
  `/data/omni/mse-quota-mb.txt` (4-512) changes it.
- The desktop user agent can be set in `/data/omni/ua-desktop.txt` (`OMNI_UA_OVERRIDE_V1`).

### Media downloads
- The shortcut switches to the Media downloads tab even when YouTube rewrote the page's address meanwhile
  (`OMNI_MEDIA_SWITCH_V1`).
- Its requests to the worker fall back to a blocking socket when the non-blocking one fails at once, as it did on
  the console (`OMNI_MEDIA_HTTP_V3`); every step is logged to `/data/omni/media-downloads.log` (`OMNI_MEDIA_DIAG_V1`).

### Fixed: every page failed with "Filtering failed ... (error 1)" after a fresh install
- **What happened:** Setup switched on Omni's built-in ad blocker (`ublock-native.flag`) but never installed its rule
  files. Omni's ad blocker refuses to let anything through when it can't start, so on a fresh console every site failed.
- **Setup:** Install, Repair and the one-button install now copy the rule files (`ublock-engine.js`,
  `ublock-compiled.txt`, `public-suffix-list.dat`, `ublock-popup-rules.txt`) to `/data/omni/`. A working set is never
  replaced; old files are moved aside, never deleted. They are written with Unix line endings: with Windows ones Omni
  loaded the rules but blocked nothing.
- **Omni (`OMNI_UBLOCK_MISSING_V1`):** if the rule files are missing, pages load without ad blocking, the shield turns
  red and Omni says "Ad block is off: its rule files are missing. Run Omnibloom Setup > Repair." Any other ad blocker
  failure still blocks everything, as before.

### Lower memory use while a page loads
- Omni keeps one engine process ready for the next tab. That spare used to start right after the first page started
  loading, at the moment the console's memory is fullest. It now starts 30 seconds later (`OMNI_SPARE_DEFER_V1`;
  old behaviour: `/data/omni/spare-defer-off.flag`).

### Experimental: faster GPU page scrolling (off by default)
- Building on v0.5.1's opt-in GPU page drawing ("layers"), three more opt-in steps. On the YouTube home page with
  all of them on, scrolling went from 8 fps to about 52 fps (median).
  - `gpu-pages-async.flag`: scrolling on its own thread.
  - `gpu-pages-asyncread.flag`: the GPU copies each frame without making the page wait.
  - `gpu-pages-zerocopy.flag`: the frame goes straight from the page's GPU memory to the screen (HDR, no video yet).
- Each needs `gpu-pages-stage1.flag` too. Known: parts of a page can show blank for the first seconds of a scroll.
- Design notes: `omni/native-title/patches/experimental/gpu-pages/`.

### Known issue: the console can restart after many Omni launches
- The console's free memory gets very low each time Omni starts a page (its engine processes and the payload loader
  use most of it), and after many launches in one session the console can restart, or another game can crash. The
  exact trigger is still being investigated; using less memory at launch is the work in progress.
- **Workaround:** fully restart the console (not rest mode) now and then if you open and close Omni a lot.

## v0.5.1 (November 13, 2026)

### JavaScript JIT on by default (launch build rc6, proven on the console)
- **What changed:** the JIT makes script-heavy sites much faster but was opt-in ("faster, less safe"), because its
  code memory stayed writable and runnable at the same time. Now the same memory is mapped twice: one view runs code,
  a separate view is the only place it can be written (`OMNI_JSC_JIT_V4`). Permissions are set once and never
  changed, which also keeps it clear of the firmware 13.60 permission-change stalls.
- **On by default** (`OMNI_JIT_DEFAULT_ON_V1`). Turn it off in **Settings > JavaScript JIT** or with
  `/data/omni/jsc-jit-off.flag`.
- **Results:** same speed as the old JIT on six sites, a 20-minute YouTube soak with 0 stalls, a 9-minute JavaScript
  soak with 0 errors. Sources: `omni/native-title/patches/launch/rc6/`.

### GPU page drawing ("layers"), opt-in experiment
- Omni can now composite web pages on the PS5's graphics chip (Zink on RADV, through the title's GPU broker). It is
  in the launch build but **off unless you create `/data/omni/gpu-pages-stage1.flag`**.
- Fixed on the way: a too-broad `dladdr` helper that slowed start-up by 5-9 s, animation frames that stopped reaching
  the page (YouTube stopped fetching video), an unpaced compositor, a jammed GPU queue from many small read-backs, and
  a GPU memory budget that was too small.
- **Results:** three back-to-back YouTube runs on the console, layers on and off, all passed at 59.94 fps with
  video starting in 12.9-14.5 s. It isn't faster than normal drawing yet.
- Sources: `omni/native-title/patches/experimental/gpu-pages/stage1/`; the write-up is
  [`docs/research/gpu-page-layers-ps5.md`](docs/research/gpu-page-layers-ps5.md).

### Setup (updated after the release)
- **Collect diagnostics…**: a button (and `--cli diagnostics`) that saves the PS5's technical logs, with web
  addresses, site names, video IDs, IP and e-mail addresses and passwords removed, to your Downloads folder for bug
  reports. Nothing is uploaded.
- **A little fun while it works:** morph calls from across the seasons show up during installs, repairs and waits.
  `--plain` turns them off.
- **Bloom Core and Master Control now start after a reboot.** Setup used to add them to Payload Manager's
  start list as bare file names (`hub.elf`), which Payload Manager v0.6.3 doesn't start. It now writes full paths
  (`/data/pldmgr/payloads/BloomCore/hub.elf`), replaces bare entries left by an older Setup, and **Repair** puts back
  any required entry that's missing.
- **Omni starts after a fresh install.** Setup now creates `/data/omni/omni-engine.elf` (a small placeholder) and
  `/data/omni/browser-mode.flag` when they're missing. Omni v0.5.1 needs both before it starts the browser; without
  them it said "upload omni-engine.elf to /data/omni first", or ran its engine self-test and closed. Existing files
  are never replaced. **Install** and **Repair** both do it.

### Downloads
- **Media downloads shortcut (LT / double bumper) no longer says "unavailable" while the worker is running.** Omni
  gave the worker 0.8 s to answer; it now waits up to 4 s and retries within 30 s (`OMNI_MEDIA_HEALTH_V2`).
- **YouTube links work with a DNS blocker on the console (downloader-9).** Some jailbreak setups block YouTube's
  addresses in DNS to protect the exploit. The worker now asks public DNS (1.1.1.1, 8.8.8.8) itself when the
  console's answer is blocked or fails, and prefers IPv4. Every answer still goes through the public-address check.
  Tested on a PC with the block simulated (the old worker failed, the new one found 47 formats); the console retest
  is pending.
- **The Downloads page is fully original.** Only the 15 original Universes remain, the leftover game-themed code is
  gone, and the support files the page loads are all included (no more missing files). New bloom favicon.

## v0.5.0: launch build (November 9-11, 2026)

Released as v0.5.0 on November 11. "Proven" means tested on the console; "built" means it passes its PC tests and
was waiting for its console test.

### YouTube no longer stops after a minute (launch build rc5, proven on the console, November 11)
- **What was wrong:** YouTube played about a minute and then stopped. Two causes, both in Omni:
  - **Omni's web cache never kept a large file.** On the PS5 the hard-link step reports success but creates
    nothing, so YouTube's player script, its security scripts, fonts and big images were re-downloaded on every
    visit. A cache built that way also stopped YouTube's player from ever making its playback token.
  - **YouTube rejects about half of the tokens Omni makes**, even with nothing extra in the page.
- **The fix:**
  - The cache checks that each large file really exists and copies it if not (`OMNI_NC_BLOB_COPY_V3`), so repeat
    visits load YouTube's player from the cache.
  - The old, broken cache is set aside once on first start, never deleted (`OMNI_NC_RESET_V1`).
  - When YouTube rejects a token, Omni reloads the page at the same position so a fresh one is made, up to 5
    times per video (`OMNI_YT_ATTEST_GUARD_V1`, off with `/data/omni/ytguard-off.flag`).
- **Results:** 4/4 test runs on a real profile played to the end, and 2/2 on the installed launch build. Sources:
  `omni/native-title/patches/launch/rc5/`.

### Setup, downloads and JDownloader 2
- **One-button install:** Setup waits for the PS5 to answer, then installs everything step by step and says what
  it is doing. It finds JDownloader 2 on the computer or points to its download page.
- **Downloads (downloader-8):** the download itself now goes through the public-address check, not just the link
  lookup.
- **JDownloader 2 (audit JD-03):** JDownloader's own connections (plugins, redirects, updates) are confined to
  public addresses by the bridge.
  - Setup switches JDownloader 2 on only when the bridge reports that policy from the PS5 itself.
  - Tested on the console: both checks passed, and the bridge reported `omni-public-only-v1`.
- **Setup fixes found on the console:**
  - A JDownloader session left open by a restart no longer blocks Setup.
  - The command-line installer shows progress during the long JDownloader copy.

### Fixed (proven on the console)
- **Reddit-style pages with many small videos no longer crash.** The software video player wrote up to 32 bytes past
  its picture buffer when a video's width was not a multiple of 16 (`OMNI_SWDEC_PAD_V1`). Before the fix the test
  page crashed after about 84 seconds; with it, 20.8 minutes and a full memory loop ran with no crash.

### HDR10 output (s3.5-hdr + fixes)
- SDR is unchanged with HDR support built in: 4K60 at 59.94 fps median, 0.12% of frames dropped.
- If the TV or system refuses HDR, Omni falls back to SDR and keeps playing (tested).
- **Fixed (proven on the console):** the graphics chip's self-check rejected its own 10-bit result on real HDR
  videos, so HDR videos fell back to the processor. The processor's reference blends chroma differently on
  alternate rows; the graphics chip now matches it exactly (`OMNI_GPU_VERIFY10_V1`, thresholds unchanged). A real
  HDR10 video then played 4.5 minutes at 59.93 fps median, 0.2% dropped, with the HDR layer made on the graphics chip.
- Checked on a TV: normal pages and video in HDR mode look normal; real HDR10 video looks like HDR.
- **Fixed (proven on the console):** sending 10-bit HDR frames to the screen cost 17 ms of processor time at 4K (thousands of one-row
  copies, twice per frame). One graphics-chip pass now does it (`OMNI_HDR_PRESENT10_V1`): 0.17 ms per frame on the console.
- Still to test: the TV switching into and out of HDR when a video enters and leaves fullscreen (Auto).

### Smoother pages (built, console A/B running)
- **Repaint only what changed.** Omni merged every changed area of a page into one big rectangle and repainted all
  of it; it now keeps the separate areas (`OMNI_PAINT_RECTS_V1`).
- **Found:** the page waits for a "frame shown" reply from the shell before drawing its next frame, and that round
  trip averages about 150 ms while a page loads. A fix is in progress.

### Faster, steadier loading (built)
- Network fixes for page loading, and a fix for the YouTube home page stalling on repeat visits (the memory
  allocator was giving memory back too eagerly).
- **Found in testing:** the new JavaScript bytecode cache made YouTube videos start 1-3 minutes late. It rewrote
  YouTube's 30 MB player code to disk on the main thread again and again (2.1 GB in 5 minutes) and never got a hit.
  It is off for launch; every other network fix tested clean.
- **Found in testing:** a header-buffering fix for HTTP/2 (`OMNI_NET_HDRBUF_V1`) stopped YouTube's player from starting
  when built with the HTTP/2-capable network library. It is off by default (HTTP/2 itself stays off for launch).
- **Launch candidate on the console:** YouTube starts in 13.7 s; HDR10 on the graphics chip at 59.94 fps with no
  dropped frames; 4K60 at 59.94 fps (0.15% dropped); no crashes on the reddit test loop; the port-block security test
  passes 65/65; no false low-memory events during 4K HDR.
- **Memory:** Omni's page process now measures its own memory use, so WebKit's low-memory cleanup can run
  (`OMNI_MEMPRESSURE_V1`, with an off switch). Before, it always reported zero.
- HTTP/2 stays off for launch, behind a switch. The cause is understood (a paused response froze its stream) and
  a fix is built for after launch.

### 4K video (built)
- **Seamless quality switches.** Switching from 1440p to 4K mid-video set up the new 4K picture queue one buffer
  at a time on the thread that feeds the screen, costing about half a second of frames. Buffers are now handed
  from the old quality to the new one and prepared ahead, inside a real memory limit (`OMNI_ABR_SWITCH_V1`,
  with a switch to turn it off).

### Experimental: drawing pages with the graphics chip (not in the launch build)
- Test app results on the console: the GL-on-Vulkan driver (Zink) runs on the PS5's graphics chip inside a
  PS5 app, and Omni's page process can borrow the graphics chip through the main app, run real GPU work and get a
  working OpenGL ES 3.2 context, and draw through it (all 8 drawing tests pass on the console). Compositing layers
  and threaded scrolling are built on top of the launch build, off by default, and waiting for their console test.
- This is the foundation for compositing layers and scrolling that doesn't wait for a page's JavaScript.

### Downloads
- The "Send to Downloads" fix (since s3.4) is in; it gets a final test from the in-browser button.
- **Scheduled downloads use the console's local time.** Start windows were read as UTC; they now use the console's
  own clock (Omni passes the UTC offset to the worker). Without a valid offset, nothing starts on a schedule. The
  scheduler is still off by default and has no settings page yet. Installed on the console on November 10.

### Source
- The launch build's sources (title rc2 + engine child rc4: build recipes, WebKit patches, switches and tests) are in
  `omni/native-title/patches/launch/`. It includes the HDR10, JavaScript heap and software-video work from
  `experimental/`; GPU page drawing stays experimental.

## Unreleased: Omni native build s3.4d (November 5, 2026)

### Changed
- **Dark mode uses the site's own dark theme first.** Omni now tells pages that you prefer dark
  (`prefers-color-scheme: dark`), so sites that pick their theme in script switch to their own dark theme. The
  colour-inverting filter is only the last resort, and it still steps aside while a large video plays.
  Tested on the console: YouTube plays with dark mode on, and pages not in your dark list are untouched.

### Known issues
- **Reddit-style pages with many small videos can crash the page process.** Omni recovers and the page can be
  reloaded. Cause: the software video player (used when the hardware decoder is busy) writes past the end of its
  picture buffer for some video sizes. A fix is built and pending a console test
  (`omni/native-title/patches/experimental/swdec-pad/`).
- Signed-out YouTube chooses its theme on its own servers, so it still gets the filter; choose YouTube's
  **Appearance > Dark theme** once to avoid it.

### Experimental (built, not yet console-tested)
- **HDR10 output** to HDR TVs (s3.5-hdr): built, host tests pass, waiting for the console test and a look at the TV.
- **Faster JavaScript without the JIT** (JavaScriptCore without "mini mode" plus a heap cap): faster first loads and
  normal memory, but repeat visits to the YouTube home page stall, so it is **not shipping yet**.
- **GPU page drawing** prototype (Zink + EGL): passes on the PC, never run on the console.

Source: `omni/native-title/patches/` (s3.4d order in its README) and `omni/native-title/patches/experimental/`.

## Unreleased: Omni native build s3.4c (November 5, 2026)

### Added
- **YouTube in 4K at 60 fps (SDR).** Tested on the console: a 2160p60 YouTube video at 3840x2160, median 59.94 fps,
  0.17% of frames dropped over 300 seconds.
- **Video on the PS5's graphics chip.** The graphics chip reads each decoded picture in place (no extra copy) and shares
  one device with the screen presenter. If it can't be used, video falls back to the processor.
- **Send to Downloads** works: the downloads worker starts on its own assigned port and tells Omni when it is ready.
- **Quick bar, grouped Options menu and Apps tiles** (built; not yet confirmed on the console).
- **Video statistics** in the video menu and an **HDR** settings page (HDR video itself is still coming).
- The final built-in pages: 50 pages and all fifteen Universe layouts (`omni/pages/bundle-clean4/`).

### Fixed
- **YouTube videos stuck at the start** when dark mode was on for youtube.com: the dark-page filter now steps aside while
  a large video plays, and dark mode uses the page's own dark theme first.

### Known limits
- HDR videos play as SDR; HDR passthrough is coming.
- The new quick bar and Options menu still need console confirmation.

Source: `omni/native-title/patches/` (s3.4c order in its README).
