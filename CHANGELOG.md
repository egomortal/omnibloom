# Changelog

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
