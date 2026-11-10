# Omnibloom Setup

One download that puts the Omnibloom apps on a jailbroken PS5 from your computer: **Bloom Core**
(required, installed first), **Omni** (the web browser, with downloads and USB file access) and
**Master Control** (controllers). Ex-Box 360 shows as "coming soon".

## For users
1. Download `Omnibloom-Setup` for your computer from the latest release (Windows `.exe`, macOS, Linux).
2. On the PS5: run your jailbreak so the payload loader and FTP server are up, and load ShadowMountPlus and kstuff.
3. Open Omnibloom Setup and press **Install everything for me**. Setup waits for the PS5 to answer, then installs
   Bloom Core, Omni, Downloads, USB file access and Master Control one at a time, checks each, sets Omni's HDR to Auto
   (unless you chose a setting), starts Bloom Core and asks it to confirm, telling you every step. If anything fails it
   puts the PS5 back as it was. **Undo this install** does the same afterwards.
   (Or press **Next** to find the PS5, check it, tick apps and install them yourself.)
4. Run it again any time: **Installed apps…** has Update, Repair and Uninstall for each app.

Command line: `--cli oneclick [--ip <ps5>]` is the same button; `--cli undo --ip <ps5>` undoes the last one. Each
one-button run's list of changes is kept on this computer (`<local app data>/Omnibloom/Setup/runs/`), which is what
Undo uses, even after Setup was closed.

Setup never deletes anything on the PS5. Replaced files are kept as backups; Uninstall puts them back and
leaves your browsing data, downloads, controller pairings and shared settings alone.

No internet on the computer? Put the console packages (`omnibloom-console-<v>.zip`,
`master-control-console-<v>.zip`) next to Setup and it uses those.

## What it writes on the PS5 (Omnibloom plug-in standard, `hub_api` 1)
- App files, each into the app's own folders only.
- `/data/hub/apps/<id>.json`: the app's ID card, with the port Setup picked.
- `/data/hub/receipts/<id>.json`: what was installed, backups, the card's hash, the autoload change.
- `/data/hub/logs/<id>/`, `/data/hub/crash/<id>/`, and `/data/hub/settings.json` (created once; then it's yours).
- `/data/pldmgr/autoload.txt`: Bloom Core always; Master Control only if you tick it. A backup copy comes first.
- One-button install only: `/data/hub/setup-lock.json` (one Setup at a time; `{"owner": null}` when free) and
  `/data/omni/video-hdr-preference.txt` (HDR Auto, only when there is no setting yet).

## For developers
```
python run_setup.py                    # the window
python run_setup.py --cli --help       # command line
python run_setup.py --fake-console     # the window against a fake PS5 on this computer (needs pyftpdlib)
python -m unittest tests.test_end_to_end tests.test_oneclick -v
xvfb-run -a python tests/gui_smoke.py shots     # walks every screen, saves screenshots
python tools/make_package.py --package omnibloom --stage <tree> --version <v> --out dist
pyinstaller omnibloom-setup.spec       # one-file app
```
`.github/workflows/omnibloom-setup.yml` builds Windows, macOS and Linux files on each release.

Licence: GPL-3.0-or-later.
