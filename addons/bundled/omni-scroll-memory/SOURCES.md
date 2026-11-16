# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. Saves, 1.5 s after scrolling stops and when the
page is hidden, the scroll position as a fraction of the page height, only for long pages (at least three screens) read
past the first screen and not finished. The key is two FNV-1a hashes of origin + path (+ a few article-id query
parameters), so no address is stored; at most 300 pages, 30 days each, in the add-on's own storage. Not loaded in
private tabs (`private_safe: false`). Restores only when the user chooses "Continue reading". Checked 2026-11-16.
