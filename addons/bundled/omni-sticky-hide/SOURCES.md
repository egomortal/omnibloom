# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. Finds elements whose computed `position` is
`fixed` or `sticky`, at least 60% of the window wide and at most 30% high, touching the top or bottom edge (never
dialogs, videos or Omni's own add-on UI), marks them with a `data-omni-sticky` attribute and slides them out with a
user-level `transform` while the page scrolls down (24 px dead zone; back after 12 px up or near the top). Rescans
after DOM changes (600 ms debounce). Nothing is fetched or sent. Checked 2026-11-16.
