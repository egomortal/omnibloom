# Omnibloom developer guide

These pages explain how Omnibloom works, how it is built and how to change it safely.
You do not need to know the project's history to use them.

Every claim points at a file in this repository. If a page and the code disagree, the code wins.
Please fix the page in the same pull request.

## Pages

| Page | Read it when you want to... |
|---|---|
| [Architecture](architecture.md) | see the pieces (Omni, Bloom Core, Downloads, the USB files broker, Master Control, JDownloader, Setup) and how they talk |
| [Building the Omni title](omni-title-build.md) | understand how the PS5 title is built from an engine tree plus patch scripts, or write a new patch |
| [Feature guides](features.md) | change the controller shortcuts, the Quick bar, dark mode, add-ons, the YouTube guard or GPU page drawing |
| [Setup internals](setup-internals.md) | change Omnibloom Setup: catalog, packages, install roots, autoload, receipts, Repair, tests |
| [Release process](release-process.md) | cut a release: packages, `SOURCE-MANIFEST.json`, `RELEASE-MANIFEST.json`, the Setup CI |
| [Troubleshooting](troubleshooting.md) | find logs, flag files and status on the console |

## Words used in these pages

- **Omni**: the browser. A PS5 title (`PPSA99732`) plus an engine child ELF.
- **Bloom Core**: the background service `hub.elf`. It keeps track of the installed apps.
- **ID card**: a small JSON file in `/data/hub/apps/` that describes one app.
- **Receipt**: a small JSON file in `/data/hub/receipts/` that Setup writes after it installs an app.
- **Marker**: a unique text label such as `OMNI_DARK_STANDARD_V1`. A patch writes it into the code it changes.
- **Engine tree**: the WebKit and engine source that Omni is built from. It is not in this repository.

## What this repository does not contain

- The WebKit/engine base tree, the PS5 Payload SDK and the security libraries
  (`omni/native-title/patches/README.md`, "What is missing").
- Bloom Core's source (`hub.c`). Setup's tests contain a stub that behaves like it (`setup/tests/fake_console.py`).
- Master Control's source. It lives in its own repository, egomortal/master-control (`master-control/README.md`).
- Any compiled binary, console log or key.
