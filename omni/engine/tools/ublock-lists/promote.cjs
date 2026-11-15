// Make a compiled rule set the one Omnibloom ships. SPDX-License-Identifier: GPL-3.0-or-later
//   node promote.cjs <version> "<what the lists are>"        e.g. node promote.cjs 2026-11-20.1 "uBlock Origin default lists"
// Copies out/ublock-compiled-full.txt to engine/resources/ublock-compiled.txt (Unix line endings) and rewrites
// engine/resources/ublock-rules.json: the version, the description and the SHA-256 of every rule file Setup installs.
// The previous version's core hashes go into "replaces", so Setup updates consoles that have the set it installed
// before; a set Setup didn't install is never replaced (setup/omnibloom_setup/installer.py ensure_omni_ublock_files).
'use strict';
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const [version, lists] = process.argv.slice(2);
if (!version || !/^\d{4}-\d{2}-\d{2}\.\d+$/.test(version) || !lists) {
  console.error('usage: node promote.cjs <YYYY-MM-DD.N> "<what the lists are>"');
  process.exit(2);
}
const res = path.resolve(__dirname, '../../resources');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const lf = b => Buffer.from(b.toString('latin1').replace(/\r\n/g, '\n'), 'latin1');
const compiled = lf(fs.readFileSync(path.join(__dirname, 'out/ublock-compiled-full.txt')));
if (compiled.length > 8 * 1024 * 1024) throw new Error('over the 8 MiB limit Omni reads (OmniUBlock.cpp readAsset)');
const manifestPath = path.join(res, 'ublock-rules.json');
const previous = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : null;
if (previous && !(version > previous.version)) throw new Error(`version ${version} is not newer than ${previous.version}`);
fs.writeFileSync(path.join(res, 'ublock-compiled.txt'), compiled);
const core = ['ublock-engine.js', 'ublock-compiled.txt', 'public-suffix-list.dat'];
const files = {};
for (const n of [...core, 'ublock-popup-rules.txt']) files[n] = sha(lf(fs.readFileSync(path.join(res, n))));
const replaces = previous ? [...(previous.replaces || []), Object.fromEntries(core.map(n => [n, previous.files[n]]))] : [];
const doc = { schema: 'omni-ublock-rules/v1', version, lists, files, replaces };
fs.writeFileSync(manifestPath, JSON.stringify(doc, null, 2) + '\n');
console.log(`promoted ${version}: ublock-compiled.txt ${compiled.length} bytes; ${replaces.length} older set(s) will be updated by Setup`);
