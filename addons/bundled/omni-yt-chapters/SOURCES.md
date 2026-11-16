# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. Reads YouTube's chapter markers
(`ytd-macro-markers-list-item-renderer`) or, without them, the description's timestamp list under YouTube's published
rules for description chapters (first at 0:00, at least three, ascending, each at least 10 seconds). Seeks the page's own
`<video>` by setting `currentTime`. Nothing is fetched or sent. Checked 2026-11-16.
