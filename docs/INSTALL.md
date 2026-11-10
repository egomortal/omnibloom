# Installing Omnibloom

Omnibloom runs on a jailbroken PS5 on **firmware 13.60**. Other firmware is untested.

## What you need first

- The jailbreak, with a payload loader listening on port **9021** (elfldr).
- **kstuff** (kstuff-lite works). It has to be loaded again after every restart or rest mode.
- **ShadowMountPlus**. It registers Omni as an app and launches it. It also has to be loaded again after every restart or rest mode. If the Omni tile does nothing, check that kstuff and ShadowMountPlus are both running.
- FTP access to the console (ftpsrv or similar), to copy files.

## The easy way: one button

1. Download **Omnibloom Setup** for your computer from the [latest release](https://github.com/egomortal/omnibloom/releases/latest)
   (Windows `.exe`, macOS or Linux) and open it.
2. Press **Install everything for me**. If you know your PS5's address (Settings > Network > Connection Status), type
   it next to the button; otherwise Setup looks for the PS5 on your home network and remembers it for next time.
3. Turn the PS5 on and run your jailbreak, then load kstuff and ShadowMountPlus. You can do this before or after
   pressing the button: Setup waits until the PS5 answers on its FTP port (2121) and payload loader port (9021), and
   carries on by itself.

Setup then does every step for you, one at a time, ticking off a checklist and saying what it's doing:

| Step | What Setup does |
| --- | --- |
| Get the apps | Downloads the release packages (or uses the zips next to Setup) and checks their hashes. |
| Find your PS5 | Waits for FTP (2121) and the payload loader (9021) to answer. |
| Check your PS5 | Read-only checks: the loader, kstuff, ShadowMountPlus. Then it takes Setup's lock on the PS5 (`/data/hub/setup-lock.json`) so two copies of Setup can't work at once. |
| Bloom Core | Installs the hub that lets the apps find each other, and adds `hub.elf` to the start list (a backup of `autoload.txt` comes first). |
| Omni | Installs the browser (title `PPSA99732`) and its engine (`omni-engine-child.elf`). If Omni or a game is open, Setup asks you to close it and waits; it never closes anything itself. After Omni's files change it waits for ShadowMountPlus to pick them up. |
| Downloads | Installs the downloads worker (port 8765). |
| USB file access | Installs `omni-files.elf`. |
| Master Control | Installs the controller app. It isn't added to the start list unless you ask (it takes PadBridge's or EeveeLution's place). |
| JDownloader 2 | Looks for **your own** JDownloader 2 on this computer (Windows: `%LOCALAPPDATA%`, `%APPDATA%`, Program Files, your user folder; macOS: `/Applications/JDownloader2.app`; Linux and others: `~/jd2`, `/opt/jd2`), or the folder you name. If it isn't there, Setup asks first, then opens the official page <https://jdownloader.org/jdownloader2> and waits while you install it and open it once. It doesn't download JDownloader itself: the official installers are on mega.nz behind encrypted links, and the page lists a SHA-256 for each one that you can check. Once found, after the apps, Setup copies it to the PS5 with the JDownloader 2 engine and runs a check on the PS5 before switching it on. **In this release this last part is held back** (JDownloader 2's own connections don't go through Omnibloom's private-address check yet), so Setup only reports what it found. If this step fails, nothing else is undone and yt-dlp downloads keep working. Omnibloom never ships JDownloader 2. |
| Settings | Sets Omni's HDR to **Auto** if you haven't chosen an HDR setting yet. A setting you chose is kept. |
| Start and confirm | Starts Bloom Core (and Master Control) and asks Bloom Core to confirm every app. |

Each app is checked file by file right after it's installed. Every file goes up as `<name>.omnibloom-new`, is read back,
and only then is moved into place; whatever was there before is kept as a backup. Nothing is ever deleted.

**If anything fails**, Setup stops, tells you what went wrong, and puts the PS5 back exactly as it was before you pressed
the button, newest change first. Nothing is started until every app has installed and checked out.

**Changed your mind?** Press **Undo this install** at the end (or run Setup again later and use the command below). It
puts back what that install replaced. A file you changed yourself since then is left alone and listed.

The same from a command line (`Omnibloom-Setup --cli …`, or `python run_setup.py --cli …` from `setup/`):

```
Omnibloom-Setup --cli oneclick                    # look for the PS5, then install everything
Omnibloom-Setup --cli oneclick --ip <ps5-address> # wait for that PS5
Omnibloom-Setup --cli undo --ip <ps5-address>     # undo the last one-button install
```

Options: `--wait-minutes 0` waits for the PS5 as long as it takes (default 30 minutes), `--no-master-control`,
`--autoload-master-control`, `--no-start-master-control`, `--hdr keep`, `--jd-folder <folder>`, `--get-jdownloader`
(open the JDownloader page without asking), `--no-jdownloader`. Undo covers the Omnibloom apps; JDownloader 2 on the
PS5 is removed with Installed apps > Uninstall. The steps below are the same install done by hand.

## Omni (the browser)

Omni is a native PS5 app with the title ID **PPSA99732**. On the console it shows as **Omni**.

1. Download the Omni package from the [releases page](https://github.com/egomortal/omnibloom/releases), or build it yourself (see [BUILD.md](BUILD.md)).
2. Copy the `PPSA99732` folder to `/data/homebrew/PPSA99732/` on the console:
   - `eboot.bin`
   - `sce_sys/param.json`
   - `sce_sys/icon0.png`
   - `sce_module/libc.prx`
3. Copy the child engine `omni-engine-child.elf` to `/data/omni/native/omni-engine-child.elf`. Omni starts it for each tab's web and network work, through the payload loader on port 9021.
4. Wait about 15 seconds for ShadowMountPlus to pick the app up. An **Omni** tile appears on the Home screen.
5. Open it like any other app. To close it, use **Options > Exit**, or press the PS button and close it from the Home screen.

Settings, logins and logs live in `/data/omni/`.

> `sce_module/libc.prx` is a console system module and is **not** in this repository. See [BUILD.md](BUILD.md).

## Downloads

The downloads worker gives Omni its Downloads page (`http://127.0.0.1:8765`) and checks links
before they're downloaded. It's optional: Omni works without it.

1. Copy the downloads worker package from the releases page to the console, as its README says.
2. In Omni, turn on **Settings > Media Downloads**.

## USB drives

`omni-files.elf` lets Omni open and save files on USB drives. Copy it to `/data/omni/native/omni-files.elf` and Omni
starts and stops it on its own. It can only reach `/mnt/usb0` to `/mnt/usb7` and
`/mnt/ext0` to `/mnt/ext1`, and it never deletes or overwrites a file.

## Master Control (controllers)

Master Control has its own repository and releases: <https://github.com/egomortal/master-control>.

1. Download `master-control.elf` from [its Releases page](https://github.com/egomortal/master-control/releases), then send it to the payload loader on port 9021 (`nc <console-ip> 9021 < master-control.elf`, or your payload manager's send button).
2. A notification says Master Control is ready. Its menu is at the address in the notification (the port is moving off 8095; see the Master Control README), and Omni can open it too.
3. To start it every time, add `master-control.elf` to your payload manager's autoload list. Don't autoload PadBridge or EeveeLution at the same time.

Master Control keeps its pairings and settings in `/data/mastercontrol/`. If you used PadBridge
before, your pairings are copied over the first time; PadBridge's own folder is never changed.

A DualShock 4 over USB is off by default. Create the empty file `/data/mastercontrol/ds4_usb` to
turn it on.

## Removing it

- Omni: delete `/data/homebrew/PPSA99732/` and `/data/omni/`, then restart ShadowMountPlus. Deleting `/data/omni/` also removes your settings, logins and saved passwords.
- Master Control: stop it from its menu, take it out of autoload, and delete `/data/mastercontrol/`.
