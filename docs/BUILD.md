# Build and check this PC/UI source package

This package covers built-in pages, bundled add-on source, docs and desktop Setup source. Native engine, vault and performance work belong to the native maintainer. The historical engine-only driver is not included.

## Check the source

Use Python3.11 or newer. From the Omnibloom folder containing SOURCE-MANIFEST.json, run:

```sh
python tools/build_release.py
```

Use `python3` where appropriate. No additional Python packages are required. The default command verifies every listed file/hash, rejects unlisted files and symlinks, and parses Python/JSON without executing application code. Failure exits2. Success verifies this source snapshot, not native features or every UI path. Local outputs belong outside the source tree. The tool never updates the manifest automatically; changes require review and a new manifest.

## Build a source archive

Choose a new filename outside the source tree with an existing parent directory:

```sh
python tools/build_release.py --source-zip ../omnibloom-source-candidate.zip
```

The driver validates first, archives only listed files plus the manifest, and reports SHA-256. Fixed order/timestamps/permissions make repeated builds identical with the same Python/zlib implementation. Existing output is refused. A completed archive is published from an owned sibling temporary file using non-overwriting Windows rename or an exclusive POSIX hard link; unsupported filesystems stop safely. Failed construction removes only that temporary file and leaves no candidate ZIP. The source ZIP is a local review artifact, not an approved release. No compiled executables/libraries, system modules, keys or model weights are listed. Fonts, images and PDF character maps are retained application resources with notices. `.git` and Python bytecode caches are never archived.

## Optional desktop Setup packaging

Use a separate development environment on the target operating system; this is not a cross-compiler. Windows Python needs working Tk. Install your reviewed/pinned PyInstaller distribution yourself, optionally from an offline wheelhouse. The checked-in historical Setup recipe requested PyInstaller6.16 or newer. The driver never downloads dependencies.

```sh
python -m PyInstaller --version
python tools/build_release.py --setup ../setup-build-candidate
```

The destination must be new and outside the source tree. The driver verifies the source/assets, checks PyInstaller is installed and invokes the existing spec with explicit external dist/work paths. Failed packaging or absent output stops the command. Artifact hashes are reported; no executable is started and no devices are discovered. Packaging is not a functional/native installation test. Keep generated binaries outside the source package.

The handoff tests process ordering and failures with mocks; it does not claim a new PyInstaller build or platform runtime result. Use separately recorded Setup reviews before distribution.

## Release checksums and manifest

After the release assets are built (console packages, Setup executables, source ZIP), put them in one new folder outside the source tree and run:

```sh
python tools/build_release.py --release-assets ../release-assets --tag v1.2.3 --commit <40-hex commit>
```

The driver verifies the source first, then writes `<asset>.sha256` for each asset (an existing one must agree), `SHA256SUMS` and `RELEASE-MANIFEST.json` (tag, source commit, SOURCE-MANIFEST.json hash, and every asset's name, size and SHA-256). It never overwrites. Upload all of them with the release: Setup refuses a downloaded package unless the manifest, its `.sha256` file and the download agree, and refuses a package placed next to Setup without a matching `.sha256` file. These are integrity and provenance checks on the same channel, not a publisher signature.

## Pages and docs

`omni/pages/bundle-r46/` and `docs/site/` are buildless HTML/CSS/JavaScript. A desktop server does not provide omnibloomHost; fixture behavior is not native acceptance. Do not run provider/install flows merely to inspect a layout. New Universe art, pending Sleeve code and Arrange localization are not silently merged here. Preserve action IDs, protocol values, user text and controller focus.

## Native handoff and release gates

The native app uses a title/startup process and browser child processes. Engine/toolchain, linked libraries, source preparation, signing/system-module handling and console validation remain with the native maintainer. Request the exact accepted source/input manifest; the old private-layout s1 scripts are not a current reproducible build recipe. The metadata display label is Omni; identity/version are unchanged.

This selection was compared with main commit 6f5227ad39ee754170d673a9c4dc36b8360585d4; README and FEATURES pairing credit is preserved. Complete reviewed Master Control selection and rights/provenance checks before publication. Piper captions/voice metadata are included; encoded media/model-output rights are separate pending selection. `sourceVerified` never means `releaseApproved`.
