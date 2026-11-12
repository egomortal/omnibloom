<p align="center">
  <img src="assets/icon/omni-icon-256.png" alt="Omnibloom icon" width="256">
</p>

<h1 align="center">Omnibloom</h1>
<p align="center"><em>potential birth from possibility</em></p>

Omnibloom is a web browser and controller suite for jailbroken PlayStation 5 consoles. It is
built on WebKit, the engine behind Safari, and runs as its own app on the console. On the
console it shows as **Omni**.

It is a hobby project by one developer, built with a lot of help from AI tools, including
Claude and Astra.

Repository: <https://github.com/egomortal/omnibloom> (the old `omni-browser` links redirect here).

> Not affiliated with Omni Browser (Android, RebelRoot), The Omni Group / OmniWeb, or OmniPad-PS5.

## What's in it

| Part | What it is | Folder |
| --- | --- | --- |
| **Omni** (the browser) | WebKit browser as a native PS5 app (title PPSA99732): 4K60 video with HDR and hardware decoding, built-in ad blocking with uBlock Origin rules, tabs, translation, full DualSense control | [`omni/`](omni) |
| **Downloads** | A link grabber that checks each link's real file type and quality before you download it, with a quality picker | [`downloads/`](downloads) |
| **Master Control** | A controller app: pair Xbox and other Bluetooth pads (plug an Xbox pad in, unplug it, and it pairs wirelessly by itself), use Switch-mode, 8BitDo, HORI and other USB pads, remap buttons. Runs in the background with its own menu. Its own repository | [egomortal/master-control](https://github.com/egomortal/master-control) |
| **USB files broker** | A small helper that lets Omni open and save files on USB drives, and nowhere else | [`omni/files-broker/`](omni/files-broker) |
| **JDownloader 2 engine** (optional) | Runs **your own** JDownloader 2 on the PS5, inside Omni's downloads, on the [PS5 Java 25 port by mateo-cogeanu](https://github.com/mateo-cogeanu/ps5-java25-homebrew). JDownloader 2 itself is never shipped; Setup copies yours | [`jdownloader/`](jdownloader) |
| **Omnibloom Setup** | One file for your computer: one button waits for the PS5 and installs everything in order, telling you each step; also updates, repairs, undoes and sets up JDownloader 2 | [`setup/`](setup) |

- **Using it?** See [FEATURES.md](FEATURES.md) for what works, what's being tested and what's coming.
- **Developer?** See [DEVELOPERS.md](DEVELOPERS.md) and [docs/BUILD.md](docs/BUILD.md).
- **Before asking for a feature or firmware support,** please read my [personal notes](personal%20notes.md).

## Requirements

- A jailbroken PS5 on **firmware 13.60**. That is the only firmware I can test on. Others may work, but I can't promise anything.
- **ShadowMountPlus**, to register and launch Omni as an app.
- **kstuff** (kstuff-lite works), for the kernel patches homebrew apps need.
- A payload loader listening on port 9021 (elfldr) for the downloads worker, the files broker and Master Control.

The easy way: download **Omnibloom Setup**, open it and press **Install the full package (recommended)** (or
**Customize…** to pick what goes on). It waits for your PS5,
installs each part in order, checks it and tells you what it is doing; if anything fails it puts the PS5 back as it
was. Details and the manual steps are in [docs/INSTALL.md](docs/INSTALL.md).

## Philosophy

Omnibloom is meant to be a one-stop shop. You should be able to browse, watch, download,
organize and customize without juggling a pile of separate tools.

The web should be usable without being buried in ads, so ad blocking is a core part of it.
No ads, no paywalls, no premium tiers. If you want to support development you can
[buy me a coffee](https://buymeacoffee.com/egomortal), but it's never required.

## AI acknowledgment

This project was made with substantial help from AI tools. That is not a licence requirement
and nobody has to agree with me about it. I'd only ask that you recognize the part AI plays in
modern software, rather than dismissing it outright.

## Security notice

Omni uses the same standard HTTPS protections as any modern browser. It also blocks web pages
from reaching the console's own services and your home network. No software can fully protect
you from malicious actors, though.

Forks, modified versions and third-party builds are trusted only as far as you trust the people
who make them. Review code when you can, and only install builds from sources you trust. The
project and its contributors are not responsible for damage, loss or security problems caused
by third-party modifications, forks or redistributed versions.

## Licence

Omnibloom is free software under the **GNU General Public License v3.0 or later**. See
[LICENSE](LICENSE). Third-party components keep their own licences, listed in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## Contributions

Contributions are welcome: bug fixes, performance work, features and documentation. I review
and moderate them to keep the project's quality and direction.

## Credits

> **JDownloader 2 on the PS5 is possible thanks to [mateo-cogeanu's PS5 Java 25 port](https://github.com/mateo-cogeanu/ps5-java25-homebrew).**
> Omnibloom's JDownloader 2 engine is built from it, on the FreeBSD OpenJDK fork. Its OpenJDK parts are GPLv2 with the Classpath
> Exception, and the source is at the port's repo; our build recipe and patches are in [`jdownloader/`](jdownloader).

Omnibloom stands on decades of open-source work. See [credits and gratitude](credits%20and%20gratitude)
and [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Master Control builds on PadBridge, AnyPad-PS5,
ps5-wireless-pads and Ghost-Control; their authors are credited in
[Master Control's own notices](https://github.com/egomortal/master-control/blob/main/THIRD-PARTY-NOTICES.md).

## Final note

Omnibloom exists because I wanted something better. If it helps you, awesome. If you fork it
and build something even cooler, that's awesome too. Respect the work, help each other out and
have fun building.
