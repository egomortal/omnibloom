# Setup internals

Omnibloom Setup is a Python desktop app. It installs Omnibloom's apps on a PS5 over the network.

| Path | What |
|---|---|
| `setup/run_setup.py` | starts the app |
| `setup/omnibloom_setup/config.py` | every path, port and rule in one place. **Read this first.** |
| `setup/omnibloom_setup/release.py` | finding, downloading and checking release packages (the catalog) |
| `setup/omnibloom_setup/installer.py` | install, Repair, Verify, Uninstall, ID cards, receipts, autoload |
| `setup/omnibloom_setup/oneclick.py` | the one-button flow |
| `setup/omnibloom_setup/ps5.py` | talking to the console (FTP and the ELF loader) |
| `setup/omnibloom_setup/ports.py` | picking a free port for an app |
| `setup/tools/make_package.py` | building a release package |
| `setup/tests/` | tests against a fake console |

## How Setup talks to the console

It needs the user's homebrew services (`config.py`):

| Port | Service | Setup uses it for |
|---|---|---|
| 2121 | FTP server (ftpsrv) | every file read and write |
| 9021 | ELF loader (elfldr) | starting ELFs (`ps5.send_payload` sends the raw ELF bytes) |
| 8084 | websrv `/processes_list` | optional: checking what is running |
| 8080 | websrv `/hbldr` | only for the JDownloader 2 check |

Setup is careful with files (`ps5.py`, `put_verified`):

1. It uploads `<file>.omnibloom-new`.
2. It reads it back and checks the hash.
3. Only then does it rename it into place.

Setup never deletes a user's files. A damaged file is renamed to `.damaged-<time>`, not removed.

## The catalog

The **catalog** is the list of apps Setup can install, built from release packages
(`release.py`, `class Catalog` and `load_catalog`).

1. Setup looks for packages next to itself first (offline zips, `find_offline_zips`).
2. Otherwise it downloads the latest GitHub release of each source in `config.SOURCES`:

   | Repository | Package prefix |
   |---|---|
   | egomortal/omnibloom | `omnibloom-console-` |
   | egomortal/master-control | `master-control-console-` |
   | (optional) | `omnibloom-jd-engine-` |

3. When two packages contain the same app, the newer version wins.

The apps themselves are defined in `APPS` in `setup/tools/make_package.py`. Each app has a `package`, a `name`,
`autoload` (`never`, `optional` or `required`), its install `roots`, a `port` (preferred, and whether it may move)
and its ID `card`. The `omnibloom` package holds `hub`, `omni`, `downloads` and `files-broker`.

## Packages

A package is a zip, `<prefix><version>.zip`, with a `<zip>.sha256` file beside it. Inside:

- `omnibloom-package.json`, with schema `omnibloom-package/v1` and the keys `schema`, `package`, `version`,
  `tested_firmware`, `apps` and `files`;
- `files/<console path>`, one entry per file.

Each row in `files` is `{app, src, dest, sha256, bytes}`.

When Setup opens a package, `Package.__init__` in `release.py` checks that:

- the schema is right and every app is valid;
- no two apps share a root;
- every `dest` is inside its app's roots;
- there are no duplicate destinations;
- every hash looks like a SHA-256.

`data()` re-hashes every file as it reads it.

**Download checks** (`download_release`). Setup refuses a package unless all of these agree:

1. the `<zip>.sha256` file (one line: `<hash>  <name>`);
2. the release's `RELEASE-MANIFEST.json`: schema `omnibloom-release-manifest/v1`, the same tag, and exactly one row
   for this file;
3. the bytes actually downloaded (hash and size).

A release without these files is refused. An offline zip needs a matching `.sha256` next to it.

## Install roots, and why they cannot widen

A release may only write inside these folders (`config.INSTALL_ROOTS`):

```text
/data/homebrew/PPSA99732/
/data/omni/native/
/data/omni/fonts/
/data/omni-downloader/
/data/pldmgr/payloads/
/data/hub/icons/
```

`release.check_dest` enforces this for every app and every file. `make_package.py` runs the same check when it
builds a package. Cards and receipts (`SETUP_OWNED`) can only be written by Setup itself, never by a package.

**Why you cannot add a root.** Each Setup has this list built in, and every Setup downloads the **latest**
release. Suppose a new release writes to a new folder. Every Setup already in users' hands would refuse it with
"Release wants to write outside Omnibloom's folders" (`release.check_dest`). So a new root means everyone must
first get a new Setup.

If a new version needs a file outside the roots, have **Setup code** create it, not the package. That is what
Setup does for Omni's first-run files in `/data/omni/` (see below).

## Autoload with full paths

Payload Manager starts the ELFs listed in `/data/pldmgr/autoload.txt` at boot (`config.AUTOLOAD_PATH`).

`installer.set_autoload` writes **absolute paths**, for example:

```text
/data/pldmgr/payloads/BloomCore/hub.elf
```

Payload Manager v0.6.3 did not start bare file names after a reboot. Then Bloom Core did not run, and Omni showed
"Media downloads unavailable" (`config.py` comment; `KNOWN-ISSUES.md`).

Rules:

- One entry per line. Setup keeps the file's CRLF or LF style, drops blank lines and ends with a newline.
- A bare entry for the same file name is replaced by the full path.
- Before writing, Setup saves `autoload.txt.before-omnibloom-<time>`. Afterwards it reads the file back, and
  restores the backup if the content does not match.
- Every change is recorded in the app's receipt (`autoload: {elf, changed, removed, backup}`), so Undo can reverse it.

Tests: `setup/tests/test_autoload_paths.py`.

## ID cards and receipts

For each app, Setup writes:

| File | Content |
|---|---|
| `/data/hub/apps/<id>.json` | the **ID card** (`installer.make_card`; null fields dropped) |
| `/data/hub/receipts/<id>.json` | the **receipt**, schema `hub-receipt/v1`, at most 8 KiB |
| `/data/hub/receipts/details/<id>.json` | the full file list and the full card |
| `/data/hub/receipts/details/<id>.install-journal-0` / `-1` | the install journal, so an interrupted install can be rolled back |

The small receipt holds `id`, `name`, `version`, `setup_version`, `installed_at`, `package`, `card_sha256`, `port`,
`autoload` and a short `history`. Bloom Core and Omni both check that `card_sha256` matches the card
(`omni/native-title/child-src/OmniHubCards.h`). So **any change to a card must also update the receipt**.

Bloom Core has a receipt but no card.

## Repair

`installer.repair_app` (Verify is the read-only twin, `verify_app`):

1. For each file in the receipt and the release, it re-hashes the file on the console. A missing or changed file
   is uploaded again; the old copy is kept as `.damaged-<time>`. `eboot.bin` and `.prx` files are only checked for
   existence, because the console shows them decoded.
2. It rewrites the ID card if its hash no longer matches the receipt.
3. It puts the full-path autoload entry back if the app needs one.
4. For Omni, it runs `ensure_omni_first_run` (below).

## Omni's first-run files

Omni up to v0.5.1 only starts the browser when two files exist (`config.OMNI_FIRST_RUN_FILES`):

| File | Content |
|---|---|
| `/data/omni/omni-engine.elf` | a short placeholder text. The title never runs it; it starts `/data/omni/native/omni-engine-child.elf`. |
| `/data/omni/browser-mode.flag` | `1` |

Without them, the title shows "upload omni-engine.elf to /data/omni first", or runs its engine self-test and
closes (`omni/engine/entry/OmniMain.cpp`; `KNOWN-ISSUES.md`).

`installer.ensure_omni_first_run` creates them **only when missing** and never replaces them, because an older
Omni may own a real file there. It runs from Install, Repair and the one-button flow.
Test: `setup/tests/test_first_run.py`.

v0.5.2's `OMNI_FIRST_RUN_V1` makes the title start without them. Setup keeps creating them for older titles.

## The one-button flow

`setup/omnibloom_setup/oneclick.py` (its docstring and `STEPS` describe the steps):

1. **Get the apps** and look for the user's JDownloader 2.
2. **Find the PS5.** Wait for the ELF loader (9021) and FTP (2121).
3. **Check and plan.** Take the lock `/data/hub/setup-lock.json` so two Setups cannot run at once.
   A record of the run goes to `<cache>/runs/<host>/<time>.jsonl`.
4. **Install each app** in this order: hub, omni, downloads, files-broker, master-control (`ORDER`).
   For each one, Setup:
   1. waits for Omni to close;
   2. runs `installer.install_app`;
   3. for Omni only, runs `ensure_omni_first_run`;
   4. waits for ShadowMountPlus to remount;
   5. runs `verify_app`.
5. **Settings.** Set HDR to Auto in `/data/omni/video-hdr-preference.txt` if the user has no setting yet.
6. **Finish.** Mark the run committed, set up JDownloader, then start Bloom Core and confirm each app in
   `/data/hub/status.json` (`start_and_confirm`).

If any step fails, `rollback` undoes the run. The lock is always released.

## Tests against a fake console

`setup/tests/fake_console.py` pretends to be a PS5. It runs on any computer and contains:

- an FTP server (pyftpdlib) with the real ftpsrv's quirks. For example, `DELE` is recorded, and `eboot.bin`
  reads back "decoded";
- an ELF loader stub that records which ELFs were sent;
- a websrv `/processes_list` stub and a ShadowMountPlus remount log line;
- a Bloom Core stub that checks cards and receipts the way the real `hub.c` does, and writes `status.json`.

Run the tests from `setup/` (needs `pyftpdlib`):

```sh
cd setup
python -m unittest tests.test_end_to_end tests.test_oneclick tests.test_discovery -v
```

That is what CI runs. Also run these when you touch their area:

```sh
python -m unittest tests.test_first_run tests.test_autoload_paths tests.test_install_journal tests.test_release_provenance -v
```

Other ways to try Setup:

- Against the fake console, with the real window: `python run_setup.py --fake-console`.
- The window walk-through on Linux: `xvfb-run -a python tests/gui_smoke.py shots`.
- The fake console alone: `python tests/fake_console.py <folder>`.

**Change Setup safely:**

1. Add a test that fails without your change, using the fake console.
2. If you change what the real console does, change the stub in `fake_console.py` to match.
3. Never widen `INSTALL_ROOTS` (see above).
4. Never delete user files. Rename them.
