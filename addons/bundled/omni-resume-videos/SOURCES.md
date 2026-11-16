# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled.

Uses only the WHATWG HTML media element API (`currentTime`, `duration`, media events) and Omni's add-on storage. [Primary source](https://html.spec.whatwg.org/multipage/media.html). Checked 2026-11-16.

Stored data: one entry per long video, keyed by a hash of the cleaned page address (the address itself is not stored), holding position, duration and last-watched time. At most 200 entries; the oldest are dropped. Private tabs never run this add-on, and Omni refuses add-on storage writes from them. YouTube is excluded because YouTube keeps its own watch position.

Continue watching (since 1.1.0): for videos watched for at least 2 minutes and not yet 95 % through, a second entry (`w:` + the same hash) keeps the page address (tracking and start-time parameters removed), the page title, its `og:image` address, position, duration and last-watched time, so Omni's start page can list them and reopen the page. At most 30 such entries; finished videos are removed. Omni's start page can remove one (Square). The same private-tab rules apply.
