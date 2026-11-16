# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. Uses Twitch's own buttons only (found by their
`data-a-target` test ids and accessible names) and presses them as the user would: theatre mode once per channel visit,
the right-column collapse button for chat, and the "Claim Bonus" button inside the points summary when that setting is
on (rate-limited: one per 10 s, 60 per hour). Nothing is fetched or sent by the add-on. Checked 2026-11-16.
