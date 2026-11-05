# Third-party notices

PDF.js / pdfjs-dist 6.5.438, Mozilla and individual contributors: Apache License 2.0, preserved in vendor/pdfjs/LICENSE. The unmodified legacy display and worker builds are paired from the exact npm tarball. Source: https://github.com/mozilla/pdf.js/tree/v6.5.438 . Package: https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.5.438.tgz . Hashes and npm integrity are in vendor-manifest.json. No source-map, WASM or Node canvas dependency is shipped.

Adobe CMaps: BSD-style redistribution terms, retained verbatim in vendor/pdfjs/cmaps/LICENSE. These are character mappings, not font software.

The package's Foxit and older Liberation standard fonts were deliberately not bundled: this project requires OFL font assets. The renderer uses embedded document font paths or available system fallback. Do not copy the excluded fonts into release assets without revisiting that requirement.

Interface fonts: Inter and Rajdhani under SIL OFL, supplied by sibling 20261103-design-system-fix/fonts with notices. sample.pdf is an unchanged copy of the project's original round2 user manual, with embedded OFL Inter/Rajdhani, original project artwork and mock screenshots. Viewer code and original manual content are GPL-3.0-or-later. PDF.js retains its Apache-2.0 licence.
