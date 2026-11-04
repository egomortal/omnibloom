# Installing Omnibloom

Omnibloom runs on a jailbroken PS5 on **firmware 13.60**. Other firmware is untested.

## What you need first

- The jailbreak, with a payload loader listening on port **9021** (elfldr).
- **kstuff** (kstuff-lite works). It has to be loaded again after every restart or rest mode.
- **ShadowMountPlus**. It registers Omni as an app and launches it. It also has to be loaded again after every restart or rest mode. If the Omni tile does nothing, check that kstuff and ShadowMountPlus are both running.
- FTP access to the console (ftpsrv or similar), to copy files.

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
