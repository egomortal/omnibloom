# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. One capturing click listener: a primary-button
click on an `a[href]` whose target is `_blank`, `_new` or a name that is not a frame on the page, with an http(s)
address, no `download` attribute and no modifier key, is turned into `location.assign()` of the same address in this
tab. Script-opened windows (`window.open`) are not touched. Nothing is fetched or sent. Checked 2026-11-16.
