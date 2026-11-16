# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. Collects the page's `<img>` elements (displayed or
natural size at least 200 x 150, or lazy images with `data-src` / `data-srcset` / `data-lazy-src` / `data-original`),
takes the largest `srcset` candidate, skips SVG and non-http(s) sources, dedupes and caps the list at 300. The overlay
keeps only the shown picture and the next one loaded (the others have no `src`), so memory stays bounded. The images
are fetched by the page's own `<img>` loading, as when the page shows them; nothing else is sent. Checked 2026-11-16.
