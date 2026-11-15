# The story so far

Omnibloom went from no browser at all to a full WebKit browser running as its own PS5 app in under three months:
the Omni title was first packaged in late August 2026, and v0.5.2 shipped on November 15, 2026. It's a hobby project
by one developer, built with a lot of help from AI tools.

## How it got here

- **Late August 2026: a browser engine on the console.** Omni started as a WebKit engine loaded as a payload
  (`omni-engine.elf`). That's why older installs still had files like `/data/omni/omni-engine.elf` and
  `browser-mode.flag` lying around.
- **Then: Omni becomes its own app.** The browser moved into a native PS5 title (PPSA99732)
  with its engine processes started beside it. Over several build stages it gained drawing on the graphics chip,
  hardware video decoding, add-ons, tabs, HDR output and 4K video.
- **November 9-11: v0.5.0, the launch.** YouTube no longer stopped after a minute, 4K with HDR10 played on the
  hardware decoder, and Omnibloom Setup, Downloads and JDownloader 2 support shipped together.
- **November 13: v0.5.1.** JavaScript JIT on by default. Its code memory is mapped twice (one view runs, another
  writes), so the speed doesn't cost the old safety trade-off. GPU page drawing arrived as an opt-in experiment.
- **November 15: v0.5.2.** Controller shortcuts, a dark mode choice, a quick-access row you can arrange, 11
  built-in add-ons and a bigger YouTube buffer. Fresh installs work out of the box, and an opt-in GPU scrolling
  path takes the YouTube home page from about 8 to about 52 fps.

## What made it hard

Almost nothing about running a full browser engine on this console is documented, so most of the work was finding
out how things really behave by testing on the console itself:

- **Memory.** The console's system memory is tight while Omni loads a page, and running out can restart it. A lot of
  work goes into measuring and cutting memory use.
- **The graphics chip.** Omni's engine processes draw through the title's own GPU connection, so pages and video
  can be composited on the graphics chip without a second owner of the GPU.
- **Starting processes.** Omni's engine processes are started next to the app, which brings its own limits and
  quirks.
- **YouTube.** The player checks a lot about the browser it runs in. Getting long 4K HDR videos to play without
  stalling took many rounds of console tests.

## What's next

The short version: make it dependable. Use less memory so repeated use never restarts the console, make YouTube
playback steadier, keep the ad-block lists up to date, and make every install carry everything Omni needs. The
details live in [ROADMAP.md](../ROADMAP.md), and every release is in the [CHANGELOG](../CHANGELOG.md).
