# Licence and provenance

Original implementation, MIT. The article finder in core.js is written for Omni; it follows the general idea of paragraph scoring popularised by Arc90 Readability and Mozilla Readability (score text blocks, give their ancestors the points, discount link-heavy blocks, add related siblings) but contains no code from either. No remote code or downloaded rules execute.

The reader is drawn inside the page from a clean element tree (createElement and textContent only; links keep http(s) addresses, images keep http(s) sources). Page HTML is never re-parsed. Checked 2026-11-16.
