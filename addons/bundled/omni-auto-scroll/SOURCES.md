# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. Scrolls the page's scrolling element by whole
pixels per animation frame (the fraction is carried, frames longer than 250 ms are capped so a stall never jumps), at
one of eight speeds from 10 to 180 CSS px per second; stops at the end of the page, on any other key or on a click.
The speed is kept in the add-on's own storage. Nothing is fetched or sent. Checked 2026-11-16.
