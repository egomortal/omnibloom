# Help & troubleshooting page: sources and notices

## Text

Written for this page from the project's own documents: `KNOWN-ISSUES.md`, `FEATURES.md`, `README.md` and the
Omni / Setup feature notes (crash panel choices, Lite mode, Data saver, Reload without cache, Setup's
"Reset Omni settings"). Original text, GPL-3.0-or-later like the rest of the pages bundle. The page is fully offline:
the texts are bundled in `model.js` and nothing is fetched (CSP `connect-src 'none'`).

## QR codes

The QR codes are drawn on the console at runtime from the public docs addresses in `model.js` (the project's GitHub
repository). The encoder is reused, not copied: the page loads `../share/vendor/qrcodegen.js`, which the Share page
already ships.

- **Project Nayuki QR Code generator library v1.8.0**, MIT License, Copyright (c) Project Nayuki,
  <https://www.nayuki.io/page/qr-code-generator-library>. Provenance, checksums and the compile command are in
  `../share/THIRD-PARTY-NOTICES.md`; the full notice is at the top of `../share/vendor/qrcodegen.js`.

MIT License text (as in the original source):

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
> documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
> rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
> persons to whom the Software is furnished to do so, subject to the following conditions:
> - The above copyright notice and this permission notice shall be included in all copies or substantial portions of
>   the Software.
> - The Software is provided "as is", without warranty of any kind, express or implied, including but not limited to
>   the warranties of merchantability, fitness for a particular purpose and noninfringement. In no event shall the
>   authors or copyright holders be liable for any claim, damages or other liability, whether in an action of contract,
>   tort or otherwise, arising from, out of or in connection with the Software or the use or other dealings in the
>   Software.

MIT is compatible with the project's GPL-3.0 distribution. Tests: `node tools/test_help_page.cjs` (decodes a code
with an independent reader written in the test, checks every "Open it" link against `routes.json` and every docs
anchor against the local Markdown headings).
