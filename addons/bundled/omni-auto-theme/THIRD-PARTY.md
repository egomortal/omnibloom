# Attribution and filtering review

Dark Reader 4.9.134 is MIT licensed. The full license is vendor/LICENSE. upstream/darkreader.js preserves the exact local source snapshot; vendor-provenance.json records byte hashes and darkreader-no-proxy.diff records both adaptations: a module-owned export namespace and removal of the inline main-world proxy. [Upstream project](https://github.com/darkreader/darkreader).

The original controls and two conservative newsletter rules are MIT licensed under LICENSE. No third-party filtering lists are redistributed. [uAssets](https://github.com/uBlockOrigin/uAssets) uses [GPL-3.0](https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/LICENSE); a future list integration belongs to the existing uBlock engine, with its license and update provenance retained. Current functionality does not equal complete uBlock annoyances coverage.

[Consent-O-Matic](https://consentomatic.au.dk/) publishes an [MIT license](https://raw.githubusercontent.com/cavi-au/Consent-O-Matic/master/LICENSE); no code was copied here. R5-040 consent-reject owns conservative reject-only decisions. [I don't care about cookies](https://www.i-dont-care-about-cookies.eu/) describes automatic acceptance in some cases; that behavior is unsuitable for this reject-only policy and is not implemented. Unknown consent dialogs remain untouched.

Standalone review pages use local Inter with its OFL notice in fonts/. No font is injected into public pages by the install payload.
