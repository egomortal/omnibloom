# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. On YouTube watch, live and shorts pages it finds
the player's own captions button (`.ytp-subtitles-button`, which YouTube hides for videos without captions) and, when its
`aria-pressed` is `false`, presses it once per video id; a video whose captions are switched off again is left alone.
Re-checks after YouTube's in-page navigation and player changes (700 ms debounce). Nothing is fetched or sent.
Checked 2026-11-16.
