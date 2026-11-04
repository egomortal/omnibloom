# Omnibloom Setup: report (saved by Claude from the Setup agent's final message, 2026-11-03)

**Build:** `dist/Omnibloom-Setup.exe`, 13.6 MB, sha256 `b09b4814…7d72`. The Windows build passes its install/uninstall test against the fake console. Nothing was sent to the console or GitHub.

## What it does
- **Finds the PS5,** then runs read-only checks: FTP, loader, ShadowMountPlus (from the process list or its log growing), kstuff, a firmware note, and which apps are already installed.
- **Bloom Core is required and installed first.** You tick:
  - Omni, where Downloads and USB Files can be unticked;
  - Master Control: start now, with autoload opt-in. Autoload replaces PadBridge/EeveeLution in the start list.
  - Ex-Box 360 shows "Coming soon".
- **Writes** cards to `/data/hub/apps/<id>.json`, small receipts to `/data/hub/receipts/<id>.json` plus `receipts/details/<id>.json`, the logs and crash folders, and `settings.json` once.
- **Fetches packages** from egomortal/omnibloom and egomortal/master-control, or uses zips placed next to Setup.
- **Update, Repair and Uninstall** work per app from the receipts. Setup never deletes and never touches user data.

## Ports
- **Master Control's card** gets 8766. If that's taken, it moves to the next free port in 8761–8799, then 8800–8899.
- **Bloom Core** stays on 8760.
- **Downloads (8765) and USB Files (8767)** can't move until Omni reads ports from the cards.

## Tests (all pass)
- **Install/update tests:** 16 pass on Linux and on Windows (Python 3.14). They cover:
  - a full suite install, a reinstall that changes nothing, updating one package, and repairing one app;
  - removing only Master Control while the other four keep working and stay verified;
  - a single-app install, a release without Bloom Core, port clashes, and refusing bad packages;
  - a GitHub download, including one repo missing and a tampered zip.
- **The window:** a walk-through of every screen on Linux, with screenshots saved.
- **The built app:** the Linux and Windows builds both pass the install/uninstall run against the fake console.
- **Fake console:** it has a Bloom Core stub that follows the same card and receipt rules as hub-service/src/hub.c.

## Matching the real Bloom Core build
- **Receipts:** hub.c refuses receipts over 8 KiB, so receipts are split into a small receipt plus a details file.
- **Cards:** hub.c rejects null fields, so cards leave them out.
- **Port 8760:** hub.c refuses it on a card, so Bloom Core gets a receipt but no card.

## Open decisions
- **Omni's card is rejected:** hub.c requires a port on every card, and a title has none. The tests mark this as expected; fixed in standard v1.1, where the port is optional for titles.
- **Master Control 0.4.2 still listens on 8095,** and Omni only allows 8095, so the 8766 in the card does nothing until both read their cards. Don't package Master Control for Setup before then.

## JDownloader 2
- **How the console engine works:** it is NOT a GraalVM image. It's our `java-worker.elf` running JDownloader on the open-source OpenJDK 25 PS5 port (mateo-cogeanu/ps5-java25-homebrew), and it loads the user's own jars at run time.
- **What Setup does already:** finds the user's JDownloader 2 install, copies only the files the engine loads, and writes the pinned file list (tested).
- **Blockers:**
  - the source and build recipe for java-worker.elf aren't on the PC or in WSL;
  - the console self-check the engine requires isn't built;
  - the Java port repo has no top-level licence.
- **Result:** the step says "Coming soon".
- **Recommended route:**
  1. Publish java-worker.elf's source with its recipe (about ½ day).
  2. Ask the Java port's author for a licence, or have Setup fetch their release directly.
  3. Add the console check to Setup (about 1 day plus one console session).

## Ex-Box 360
"Coming soon". Its layout is moving (big-app plus companion on 7090, native-title work in flight), its 360 artwork has to come from the user's own backups, and its tile hard-codes 7090.

## Standard feedback
All 12 points were folded into SUITE-PLUGIN-STANDARD v1.1:
1. Make `port` optional for titles.
2. Bloom Core has no card.
3. The receipt/details split.
4. Live data goes in a separate runtime file, not in the card.
5. A `status.json` that Setup reads over FTP.
6. Autoload values and `started_by`.
7. ELF paths under `pldmgr/payloads`.
8. Pages separate from APIs.
9. Reserve the 8760–8799 range.
10. The token is readable over FTP.
11. Bloom Core can't be uninstalled while other apps remain.
12. Titles get no default health check.

## Real-console test (needs the lock)
1. Run `--cli check` (read-only).
2. Run a cards-only install with packages made from the builds already on the console, without Bloom Core or Master Control. Expect every file "up to date", new cards and receipts, and autoload unchanged.
3. Uninstall and reinstall USB Files.
4. Add Bloom Core once `hub.elf` is packaged, and confirm `/v1/apps` shows the apps as verified.
5. Walk through the window with the user.

## Not done
- No macOS test (CI builds it).
- No JDownloader console check.
- No Ex-Box package.

## Notes
- The workflow is in `ci/` because `.github` can't be written on the PC. Move it to `.github/workflows/` when publishing.
- Setup is copied to `github-release-staging/Omnibloom/setup/` (personal-info scan clean).
- Files: `omnibloom_setup/`, `run_setup.py`, `tests/`, `tools/`, `omnibloom-setup.spec`, `build-win.ps1`, `ci/github-workflow-omnibloom-setup.yml`, `screenshots/`, `jdsearch*.txt`, `win-build.txt`, `dist/Omnibloom-Setup.exe`.
