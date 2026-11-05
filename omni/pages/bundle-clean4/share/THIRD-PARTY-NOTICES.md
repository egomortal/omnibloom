# QR dependency provenance

Runtime generator: Project Nayuki QR Code generator **v1.8.0**, MIT. Official source: https://github.com/nayuki/QR-Code-generator/blob/v1.8.0/typescript-javascript/qrcodegen.ts . Project description/license: https://www.nayuki.io/page/qr-code-generator-library . The complete MIT notice remains at the top of the original TypeScript and compiled JavaScript. Original source SHA-256: c4749095a91bf9696e3a303998b9905e467094f53041e64393e65e6d887737fd. Compiled JavaScript SHA-256: 6e200897a80ff15a652a5d601667856d807cec60cfc81a3a351305d69cc9dbbd.

Compilation used TypeScript 5.9.3 (Apache-2.0), pinned in build-tools/package-lock.json. Command: `node build-tools/node_modules/typescript/bin/tsc --target ES2015 --lib ES2015,DOM --outFile vendor/qrcodegen.js --strict vendor/qrcodegen.ts`. No generator logic was modified.

Test-only decoder: jsQR **1.4.0**, Apache-2.0, published npm package linked to https://github.com/cozmo/jsQR . Vendored dist/jsQR.js SHA-256: bc40c8a15196236b2314db0856f72ca0b49980cd5413b8c852a7349f5fee0859. Full license in test-vendor/LICENSE-jsQR.txt. Independent decoder tests verify both encoder matrices and actual displayed SVG screenshots.

Test-only PNG reader: pngjs 7.0.0, MIT, pinned in build-tools/package-lock.json. It decodes Playwright screenshots for jsQR. Development packages are downloaded with lifecycle scripts disabled. Do not ship build-tools/node_modules, test-vendor or tests in the runtime bundle.

UI fonts: Inter and Rajdhani, OFL-1.1, license files in fonts/. Original component/model/rendering code: GPL-3.0-or-later. MIT and Apache-2.0 dependencies are compatible with the project's GPL-3.0 distribution.
