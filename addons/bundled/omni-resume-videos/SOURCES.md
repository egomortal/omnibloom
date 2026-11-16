# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled.

Uses only the WHATWG HTML media element API (`currentTime`, `duration`, media events) and Omni's add-on storage. [Primary source](https://html.spec.whatwg.org/multipage/media.html). Checked 2026-11-16.

Stored data: one entry per long video, keyed by a hash of the cleaned page address (the address itself is not stored), holding position, duration and last-watched time. At most 200 entries; the oldest are dropped. Private tabs never run this add-on, and Omni refuses add-on storage writes from them. YouTube is excluded because YouTube keeps its own watch position.
