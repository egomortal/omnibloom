# Licence and provenance

Original implementation, MIT. The article finder in core.js is written for Omni; it follows the general idea of paragraph scoring popularised by Arc90 Readability and Mozilla Readability (score text blocks, give their ancestors the points, discount link-heavy blocks, add related siblings) but contains no code from either. No remote code or downloaded rules execute.

The reader is drawn inside the page from a clean element tree (createElement and textContent only; links keep http(s) addresses, images keep http(s) sources). Page HTML is never re-parsed. Checked 2026-11-16.

## 1.1.0 (2026-11-16)

Reading options on the reader's toolbar, original code (prefs.js and runtime.js): text size in five steps (A- / A+ and the options panel), line width (narrow / medium / wide), font (serif / sans / "Easy read"), colours (light / sepia / dark / black for OLED) and line spacing (compact / normal / relaxed). The choices are kept in the add-on's own storage under one key, so they apply on every site; a later change to Text size or Colours on the add-on settings page wins for that option. Private tabs cannot write add-on storage, so a change made there lasts only for that page. The reading time is shown above the title and counts down in the bar as you scroll.

Fonts: only the ones Omni ships in /data/omni/fonts (DejaVu Sans, Serif and Mono; Noto Sans JP/KR/SC). "Easy read" names OpenDyslexic, Atkinson Hyperlegible and Lexend first in case a later build adds them, then falls back to DejaVu Sans with wider letter and word spacing; no font is downloaded.

No "Read aloud": the WebKit build has ENABLE_SPEECH_SYNTHESIS off (omni/webkit/configure-cmd.json), so there is no speechSynthesis to use.

Controller: Omni's D-pad scrolls the page and goes back / forward instead of reaching page scripts, so the toolbar is made of large buttons for the pointer (left stick, Cross). A keyboard's arrow keys move between the buttons; Escape or Circle closes the options panel first, then the reader.
