# Changelog

## Unreleased: launch build (in progress, November 9, 2026)

Everything below is going into one combined build for the November 12 release. "Proven" means tested on the
console; "built" means it passes its PC tests and is waiting for its console test.

### Fixed (proven on the console)
- **Reddit-style pages with many small videos no longer crash.** The software video player wrote up to 32 bytes past
  its picture buffer when a video's width was not a multiple of 16 (`OMNI_SWDEC_PAD_V1`). Before the fix the test
  page crashed after about 84 seconds; with it, 20.8 minutes and a full memory loop ran with no crash.

### HDR10 output (s3.5-hdr)
- SDR is unchanged with HDR support built in: 4K60 at 59.94 fps median, 0.12% of frames dropped.
- If the TV or system refuses HDR, Omni falls back to SDR and keeps playing (tested).
- **Found in testing:** on real HDR videos the graphics chip's self-check rejected its own 10-bit result by a small
  margin, which sent HDR videos to the processor (no HDR, dropped frames). A fix is in progress; HDR is not
  enabled until it passes, plus a check on the TV.

### Smoother pages (built, console A/B running)
- **Repaint only what changed.** Omni merged every changed area of a page into one big rectangle and repainted all
  of it; it now keeps the separate areas (`OMNI_PAINT_RECTS_V1`).
- **Found:** the page waits for a "frame shown" reply from the shell before drawing its next frame, and that round
  trip averages about 150 ms while a page loads. A fix is in progress.

### Faster, steadier loading (built)
- Network fixes for page loading, and a fix for the YouTube home page stalling on repeat visits (the memory
  allocator was giving memory back too eagerly).
- HTTP/2 stays off for launch, behind a switch. The cause is understood (a paused response froze its stream) and
  a fix is built for after launch.

### 4K video (built)
- **Seamless quality switches.** Switching from 1440p to 4K mid-video set up the new 4K picture queue one buffer
  at a time on the thread that feeds the screen, costing about half a second of frames. Buffers are now handed
  from the old quality to the new one and prepared ahead, inside a real memory limit (`OMNI_ABR_SWITCH_V1`,
  with a switch to turn it off).

### Downloads
- The "Send to Downloads" fix (since s3.4) is in; it gets a final test from the in-browser button.

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
