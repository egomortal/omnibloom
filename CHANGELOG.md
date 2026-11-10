# Changelog

## Unreleased: launch build (in progress, November 9-10, 2026)

Everything below is going into one combined build for the November 12 release. "Proven" means tested on the
console; "built" means it passes its PC tests and is waiting for its console test.

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
