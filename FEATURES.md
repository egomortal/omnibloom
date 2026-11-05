<p align="center">
  <img src="assets/icon/omni-icon-128.png" alt="Omnibloom icon" width="128">
</p>

# What Omnibloom Can Do

*Last updated: November 5, 2026 (native build s3.4d)*

Omnibloom's browser, **Omni** (that's the name on the console), is a web browser for the PS5
built on WebKit, the same engine that powers Safari. It runs as its own app and you control
everything with a controller. It's designed for watching video and browsing without ads.

This page lists what works today, what's being tested and what's still coming.
Developers: see [DEVELOPERS.md](DEVELOPERS.md).

| Symbol | Meaning |
| :---: | --- |
| ✅ | **Works.** Tested on a real PS5. |
| 🧪 | **Built, and tested on a PC or partly on a PS5,** but not yet confirmed on a PS5. |
| 🚧 | **Experimental.** Being worked on. |
| 📋 | **Planned.** Not built yet. |
| ❌ | **Not available.** See the notes for why. |

---

## 🌐 Browsing

| Feature | Status | Details |
| --- | :---: | --- |
| Its own PS5 app | ✅ | Omni runs as its own app (tile), registered with ShadowMountPlus, instead of inside the system browser. |
| Modern website support | ✅ | Runs a full version of WebKit, Safari's engine, ported to the PS5. |
| Smooth scrolling | ✅ | Scrolls at about 60 fps, with no noticeable hitches. |
| Tabs | ✅ | Up to 8 tabs open, with 6 kept loaded in memory. |
| Bookmarks and shortcuts | ✅ | Press **L3** to save the current site to your shortcuts grid. |
| Translate pages | ✅ | Press the **touchpad** to translate the page. |
| Dark mode | 🧪 | **Uses the site's own dark theme first.** Omni tells pages you prefer dark (`prefers-color-scheme: dark`), so sites that have a dark theme switch to it. Only if a page stays light does Omni darken it with a colour filter, and the filter steps aside while a large video plays so video stays smooth. Works with the Dark Reader add-on. Tip: on YouTube, choose YouTube's own **Appearance > Dark theme** once. |
| Quick bar and Options menu | 🧪 | Redesigned: a quick bar of the things you use most, a grouped **Options** menu, and an **Apps** row with tiles and status for the suite's apps. |
| Stay logged in | ✅ | Your logins are remembered after you close Omni. |
| Secure connections (HTTPS) | ✅ | Websites are security-checked the same way any normal browser does. |
| Saved passwords | 🧪 | **Present, but manual.** You add logins yourself on the Passwords page, and Omni fills one in only when you ask. Omni never watches login forms and never offers to "save this password". Saved passwords are scrambled on the console, not truly encrypted: anyone who can read the console's files can read them. |
| Form autofill | 🧪 | One profile (name, email, address and so on) that you fill in under Settings. Omni writes it into a form only when you pick **Fill form**. |
| Choose your pointer | 🧪 | Pick the pointer's style, size and colour from a set of free Kenney cursors and crosshairs. |
| Open and save files on USB drives | 🧪 | Upload a file from a USB drive, or save to one. Omni can only reach USB drives, and can't delete or overwrite files. |
| Faster JavaScript (JIT) | 🧪 | **Settings > JavaScript JIT (faster, less safe).** Off by default. Makes script-heavy sites faster, at some cost to safety. |
| Controllers on web pages | 🧪 | Browser games and other pages can read your controller (the web Gamepad API). Only the tab you're looking at gets the input. You can turn it off in Settings. |
| Location, camera, microphone, notifications, video calls | ❌ | Not included in this version of Omni. |

## 📺 Video

| Feature | Status | Details |
| --- | :---: | --- |
| 4K at 60 fps | ✅ | Smooth. In a 10-minute test, only 50 of nearly 36,000 frames were skipped. |
| YouTube in 4K at 60 fps (SDR) | ✅ | A 2160p60 YouTube video plays at full 3840x2160: median 59.94 fps, with only 0.17% of frames dropped over a 300-second test on the console. |
| Video on the PS5's graphics chip | ✅ | The PS5's graphics chip converts and shows each video frame (it reads the decoded picture in place, with no extra copy). This is the path behind the 4K60 YouTube result. If the graphics chip can't be used, Omni falls back to the processor on its own. |
| Video statistics | 🧪 | **Stats for nerds** in the video menu: resolution, frame rate, dropped frames and the video path in use. |
| HDR | 🚧 | **Built, testing.** HDR10 output to HDR TVs is built and passes its PC tests; it is waiting for its first test on the console and a look at the TV. Until then HDR video is shown as SDR (the 4K60 result above is SDR). |
| Hardware video decoding | ✅ | Uses the PS5's built-in video chip. Supports H.264, HEVC and VP9, including 10-bit. |
| Background tabs free up memory | ✅ | A video in a hidden tab pauses and frees its memory after 1.5 seconds, then picks up again when you come back. |
| Fullscreen controls | ✅ | See [Controls](#-controls) below. |
| Higher than 4K (e.g. 8K) | ❌ | The PS5's video hardware is the limit, not Omni. |
| Netflix, Disney+ and other protected services | ❌ | These need copy-protection software that isn't available to homebrew apps. |
| The full YouTube website | 🧪 | Videos on YouTube's own watch pages now start and play in 4K60 (above), including with dark mode on for YouTube. The rest of the site is still being tested. YouTube videos embedded on other sites play fine. |

## 🛡️ Ad blocking

Omni has ad blocking built in and **turned on by default**. It uses the same filter lists and
rules as **uBlock Origin**. You don't need to install anything.

| Feature | Status | Details |
| --- | :---: | --- |
| Block ads and trackers | ✅ | Stops ads and tracking scripts from loading. |
| Hide leftover ad boxes | ✅ | Removes the empty spaces and banners ads leave behind, without hiding real page content. |
| Fast per-site rules | ✅ | Omni loads only the rules each site needs, so pages load faster than with the full rule set. |
| Fix sites that fight ad blockers | 🧪 | Uses uBlock's small page fixes to defeat "please disable your ad blocker" walls. |
| Hide annoyances | 🧪 | Hides cookie banners, newsletter popups, notification requests and chat bubbles. |
| Block pop-ups | 🧪 | New windows only open when you click something, and known pop-up ads are always blocked. |
| Skip redirect pages | 🧪 | Jumps past the "you are being redirected…" pages that track your clicks. |
| Clean up links | 🧪 | Strips tracking codes from web addresses. |

## ⬇️ Downloads

| Feature | Status | Details |
| --- | :---: | --- |
| Send to Downloads | ✅ | Send a link from Omni to the downloads worker, which starts on its own assigned port and tells Omni when it's ready. |
| Link grabber | ✅ | Finds video and media links on the page, including ones hidden inside embedded players. Found links show up in the Downloads dialog and on the Launch page. |
| Know what you're getting | 🧪 | Each link is checked before you download it: real file type, resolution, bitrate and size where the site gives them, best first. Links that won't work say why: copy-protected (never bypassed), live stream, dead link, sign-in needed. |
| Quality picker | 🧪 | Choose the quality you want when a link offers more than one. |
| yt-dlp | 🧪 | The downloads worker uses yt-dlp for video sites. |
| JDownloader | 🚧 | The worker can drive JDownloader for file hosts, but JDownloader itself is not part of this release. |
| Privacy | ✅ | Only runs when **Media Downloads** is turned on, never in private tabs, and keeps no browsing history. |

## 🎮 Master Control

Master Control is the controller app that comes with Omnibloom. It runs in the background,
has its own tile and menu, and Omni can open its menu too.

| Feature | Status | Details |
| --- | :---: | --- |
| Bluetooth pads | ✅ | Pair Xbox Series X\|S and other Bluetooth controllers to the PS5. |
| Plug in, unplug, go wireless | ✅ | Plug an Xbox controller in by USB, then unplug it: Master Control opens a 60-second Bluetooth search by itself. Hold the pair button once and it reconnects wirelessly from then on. No phone or menu needed. Our own feature (from PadBridge). |
| Wired pads | 🧪 | Switch Pro, 8BitDo and Manba in Switch mode, HORI and XIM over USB. DualShock 4 over USB is opt-in. |
| Remap buttons | 🧪 | Per-controller button remapping. |
| Menu inside Omni | 🧪 | Open Master Control's menu from Omni and drive it with the controller. |

## 🎮 Controls

### Browsing

| Button | Action |
| --- | --- |
| Left stick | Move the pointer (it snaps to the nearest link) |
| Right stick | Scroll in any direction |
| **Cross** | Click. Hold for half a second for the right-click menu |
| **Circle** | Go back |
| **Square** | New tab |
| **Triangle** | Address bar |
| **L1 / R1** | Switch tabs |
| **R3** | Close tab |
| **L3** | Save site to shortcuts |
| D-pad up / down | Scroll |
| D-pad left / right | Back / forward |
| Touchpad | Translate page |
| **Create** | Settings |
| **Options** | Quick menu (**Exit** is in the last row) |

### On-screen keyboard

| Button | Action |
| --- | --- |
| **L1 / R1** | Move the cursor |
| **L2 / R2** | Move the cursor a whole word |
| **Square** | Delete |
| **Triangle** | Space |
| **L3** | Shift |
| **R3** | Symbols |
| Touchpad | Open the edit row (this is also where **Fill saved login** and **Fill form** are) |
| **Options** | Go |

### Fullscreen video

| Button | Action |
| --- | --- |
| **Square** | Pause / play |
| **L1 / R1** | Skip back / forward 10 seconds |
| **Triangle** | Captions |
| **L3** | Mute |
| **Circle** | Exit fullscreen |

### Stick drift fix

If your controller's stick drifts, go to **Browser Settings** and set the **Dead zone** to
Small, Medium, Large or Extra large. It smooths out the pointer, scrolling and keyboard
navigation. If you leave the controller alone, the pointer also gets out of the way after
3 seconds.

## 🖥️ Display

| Feature | Status | Details |
| --- | :---: | --- |
| Choose a resolution | ✅ | **Settings > Resolution:** 1080p, 1440p or 4K. Takes effect after a restart. |
| Safe fallback | ✅ | If Omni fails to start at your chosen resolution, it switches back to 1080p on its own. |

---

## ⚠️ Known limits

- **No Netflix, Disney+ or other copy-protected video.**
- **Nothing above 4K.**
- **Some JavaScript-heavy sites run slower** than on a PC or phone. The optional JIT setting helps, but it's off by default.
- **Saved passwords are only scrambled, not encrypted,** because the console has no secure storage Omni can use.
- **No location, camera, microphone, notifications or video calls.**
- **No HDR video yet.** HDR videos play, but as SDR (HDR output is built and being tested).
- **Known issue: pages with many small videos can crash.** On Reddit-style feeds where lots of small videos autoplay at once, the page's process can crash; Omni recovers and you can reload the page. The cause is found and a fix is pending (it still needs a console test).

## 🔜 What's next

- **HDR video** on HDR TVs (built, being tested).
- **The fix for the Reddit-style page crash** (pending a console test).
- **JDownloader** for file-host downloads.

---

## 🔒 Safety built in

- Every update keeps a backup of the previous version, so a bad update can always be undone.
- Omni doesn't weaken the PS5's security or website security checks.
- Web pages can't reach the console's own services (the payload loader, FTP and so on) or devices on your home network.
- Security fixes from Safari's latest updates are applied to Omni's copy of WebKit where the fixes are public.
