<p align="center">
  <img src="assets/icon/omni-icon-128.png" alt="Omnibloom icon" width="128">
</p>

# What Omnibloom Can Do

*Last updated: November 16, 2026 (release rows: native build s3.4d; plus the [dev branch](#-on-the-dev-branch-not-yet-in-a-release) section)*

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
| Tabs | ✅ | Up to 8 tabs open by default, with 6 kept loaded in memory; Browser settings > Tab limit goes up to 16. |
| Bookmarks and shortcuts | ✅ | Press **L3** to save the current site to your shortcuts grid. |
| Translate pages | ✅ | Press the **touchpad** to translate the page. Uses Google Translate's website proxy: the page's address (including its query string) is sent to Google, which loads and translates the page; nothing is sent until you press. On the dev branch it asks first, never sends addresses with passwords or local-network hosts, and has per-site Offer / Always / Never. |
| Dark mode | 🧪 | **Uses the site's own dark theme first.** Omni tells pages you prefer dark (`prefers-color-scheme: dark`), so sites that have a dark theme switch to it. Only if a page stays light does Omni darken it with a colour filter, and the filter steps aside while a large video plays so video stays smooth. Works with the Dark Reader add-on. Tip: on YouTube, choose YouTube's own **Appearance > Dark theme** once. |
| Quick bar and Options menu | 🧪 | Redesigned: a quick bar of the things you use most, a grouped **Options** menu, and an **Apps** row with tiles and status for the suite's apps. |
| Stay logged in | ✅ | Your logins are remembered after you close Omni. |
| Secure connections (HTTPS) | ✅ | Websites are security-checked the same way any normal browser does. |
| Saved passwords | 🧪 | **Present, but manual.** You add logins yourself on the Passwords page, and Omni fills one in only when you ask. Omni never watches login forms and never offers to "save this password". Saved passwords are scrambled on the console, not truly encrypted: anyone who can read the console's files can read them. |
| Form autofill | 🧪 | One profile (name, email, address and so on) that you fill in under Settings. Omni writes it into a form only when you pick **Fill form**. |
| Choose your pointer | 🧪 | Pick the pointer's style, size and colour from a set of free Kenney cursors and crosshairs. |
| Open and save files on USB drives | 🧪 | Upload a file from a USB drive, or save to one. Omni can only reach USB drives, and can't delete or overwrite files. |
| Faster JavaScript (JIT) | ✅ | **On by default** since v0.5.1. Script-heavy sites run much faster. The JIT's code memory is now never writable and runnable at the same time (W^X), so it no longer costs safety. Turn it off under **Settings > JavaScript JIT**. |
| GPU page drawing ("layers") | 🧪 | **Opt-in test, off by default.** Composites web pages on the PS5's graphics chip instead of the processor. Turn it on by creating `/data/omni/gpu-pages-stage1.flag`. Video plays at full speed with it on, but it isn't faster than normal drawing yet. Details: `omni/native-title/patches/experimental/gpu-pages/stage1/`. |
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
| yt-dlp | 🧪 | The downloads worker uses yt-dlp for video sites. If your console's DNS blocker hides YouTube (as some jailbreak setups do), the worker looks the address up itself, and it prefers IPv4. |
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

## 🌱 On the dev branch (not yet in a release)

Everything in this section is on the **dev branch only, not yet in a release**. It is built and
tested on a PC; most of it has not been tested on a PS5 yet, so it is marked 🧪. Settings named
below are in **Browser settings** unless another place is given.

### Tabs

| Feature | Status | Details |
| --- | :---: | --- |
| Pinned tabs | 🧪 | In the **Tabs** panel, press **D-pad left / right** on a tab row to pin or unpin it. You can also hold **Cross** on a page and pick **Pin this tab**. Pinned tabs come first and show as small tiles at the start of the tab strip that never scroll away. Closing a pinned tab asks once: press **Square** (Tabs panel) or **R3** again within 4 seconds. Pinned tabs are unloaded from memory last and stay pinned after a restart. Up to 6. Private tabs can't be pinned. Tab groups are not part of this. |
| Tab audio and mute | 🧪 | A speaker icon shows on tabs that play sound, and a crossed speaker on tabs you muted. Press **Triangle** on a tab row in the **Tabs** panel to mute or unmute it, or use **Mute this tab** in the hold-**Cross** menu or **Options > Quick toggles**. Muting lasts until you unmute or close the tab; it is not saved. |
| Saved tab sessions | 🧪 | In the **Tabs** panel, **Save these tabs as a session...** saves the open tabs under a name you type ("Movie night"). **Sessions...** lists them: **Cross** opens (replace the open tabs, or add to them), **Triangle** renames, **Square** twice deletes. Only the tab you see loads at first; the others load when you switch to them. Up to 30 sessions of up to 16 tabs. Private tabs are never saved. |
| Open link in background tab | 🧪 | Hold **Cross** on a link, then press **Cross**: **Open in background tab** is now the first row of that menu. The tab limit still applies. |

### Pages and sites

| Feature | Status | Details |
| --- | :---: | --- |
| Zoom per site | 🧪 | Omni remembers a zoom level for each site (50% to 200%). Hold **L2** and press **D-pad up / down** to zoom in or out while browsing, or use the **Zoom (this site)** row in **Options** (**D-pad left / right** change it, **Cross** resets). A short notice shows the new level. |
| Save page for later (reading list) | 🧪 | Hold **Cross** on a page and pick **Save page for later**, or use **Options > Browse**. The page is saved on the console as it looks now and can be read offline: **Cross** opens the saved copy, **Triangle** the live page, **Square** deletes. Images and styles from other sites, video and fonts are not kept offline, and the page's scripts never run in the saved copy. Up to 200 pages / 500 MB (the oldest go first). Private tabs are never saved. |
| Page screenshots | 🧪 | Hold **L2** and press **R3** while browsing to save the visible page as a PNG in the Downloads app's **Saved > Screenshots** folder. The Screenshot rows in the menus save there too. Video drawn by the video hardware comes out white. Off in private tabs. |
| Clear data for this site | 🧪 | **Options > Site settings > Clear data for this site** deletes the site's cookies (sign-ins included, for the site and its subdomains) and the current page's own storage, then reloads the page. It asks first, and you may be signed out. Storage of the site's other addresses (for example the bare domain when you are on `www.`) is kept, and the shared web cache is not touched. |
| Autoplay | 🧪 | **Autoplay: Allow** (default, same as before) / **Block sound** / **Block all**. **Site settings > Autoplay on this site** sets one site. With a blocking choice, YouTube, Twitch, Vimeo and Dailymotion are still allowed unless you set them yourself. Applies to pages loaded after the change. |
| Continue watching | 🧪 | A **Continue watching** row on the start page with up to 6 videos you left part-way (after 2 minutes watched, until 95%). **Cross** opens one, **Square** on a tile removes it. Needs the Resume videos add-on 1.1.0 (built in). Private tabs are never recorded. Turn it off with **Continue watching on start page**. |
| YouTube TV mode | 🧪 | **Off by default.** **YouTube: Normal / TV mode** opens YouTube's TV app (youtube.com/tv) instead of the desktop site for home and watch pages. On the TV app the **D-pad** moves, **Cross** selects and **Circle** goes back. Search, channel and settings pages open as usual. |

### Privacy and security

| Feature | Status | Details |
| --- | :---: | --- |
| HTTPS-only mode | 🧪 | **Off by default.** When on, an `http://` address is opened as `https://`. If the site has no secure version, Omni asks: **Cross** continues to the http site (until Omni closes), **Circle** goes back. **Site settings > HTTPS-only on this site** can always allow http for one site. Local addresses, your home network and Omni's own apps are never changed. |
| Ask sites not to sell or share my data | 🧪 | **Off by default.** Turns on Global Privacy Control: pages see `navigator.globalPrivacyControl` and secure requests carry `Sec-GPC: 1`. |
| Tell sites this is Omni | 🧪 | **Off by default.** Adds " Omni/<version>" to the browser's user agent. Off because some sites (YouTube among them) treat unusual user agents with suspicion. |
| Ad blocking inside embedded frames | 🧪 | **On by default.** uBlock's page fixes and element hiding now also run inside embedded frames (for example a video player from another site), matched by the frame's own site. Network blocking already covered frames. |

### Video and sound

| Feature | Status | Details |
| --- | :---: | --- |
| Now playing | 🧪 | While a tab plays video or sound, **Options** shows a **Now playing** tile, even when that tab is in the background. It opens play / pause, previous / next track, back / forward 10 seconds, mute and go to tab. Next / previous use the site's own buttons where Omni knows them (YouTube, YouTube Music, Spotify, SoundCloud). Players inside frames from another site can't be reached. Nothing is stored. |
| Sleep timer | 🧪 | **Options > Sleep timer**: press **Cross** to step Off / 15 / 30 / 60 / 90 minutes. A minute before the end Omni warns you, then pauses playback in every tab. Not kept after a restart. |

### Typing and search

| Feature | Status | Details |
| --- | :---: | --- |
| Word suggestions on the keyboard | 🧪 | Up to 3 word completions above the on-screen keyboard. Press **D-pad up** from the top row of keys to reach them, **left / right** to pick and **Cross** to use one. Never in password, email, address or number fields. **Word suggestions** is on by default and uses a built-in English list. **Learn words I type** is **off by default**; when on, it keeps your words on the console (never from private tabs or sign-in fields). **Clear learned words** deletes them. |
| Search shortcuts | 🧪 | Type `yt lofi beats` in the address bar to search YouTube. Built in: `yt` YouTube, `w` Wikipedia, `r` Reddit, `g` Google, `d` DuckDuckGo, `a` Amazon, `m` Google Maps. You can set your own in `/data/omni/search-shortcuts.txt`. |
| Most-visited tiles | 🧪 | Empty shortcut slots (the keyboard's tile page and the new-tab page) show your most visited sites from the last 30 days, dimmed and marked "Suggested". Press **Square** on one (or **L3** on the page) to keep it. |
| Better history | 🧪 | The History panel groups visits by day (Today, Yesterday...). **Triangle** searches. **Square** deletes one visit, **R3** every visit to that site (asks first). **Clear history...** offers Last hour / Today / All time. **D-pad left / right** jump a day, **L1 / R1** a page. |
| Send a link from your phone | 🧪 | **Off by default.** **Send links from your phone** opens a small page on your home network (the address and a 6-digit code are shown in Omni). Send a link from a phone or PC and it opens in a new tab. Only `http(s)` links; 5 wrong codes lock it for a minute. |

### Small things

| Feature | Status | Details |
| --- | :---: | --- |
| Controller battery | 🧪 | A small battery icon in the top bar for wireless controllers. Hidden when wired or unknown. |
| Downloaded notice | 🧪 | With **Media Downloads** on, Omni shows "Downloaded: <title>" when a download finishes (not while the Downloads tab is in front). |

### Downloads and Setup

| Feature | Status | Details |
| --- | :---: | --- |
| File downloads go to Downloads | 🧪 | With **Media Downloads** on, a normal file download on a page (PDF, ZIP, image, attachment) is sent to the Downloads app and saved as the original file. Pages that show a PDF or image themselves are unchanged. Private tabs keep the browser's own download. |
| Pause, resume, retry | 🧪 | Downloads can be paused, resumed and retried. Paused downloads survive a restart of the downloads worker. |
| Library | 🧪 | A **Library** view in the Downloads app lists saved files. Play saved media in a controller-friendly player, open PDFs and images, and delete files (two steps, through a trash folder). |
| Back up and restore Omni | 🧪 | Setup (on the PC) saves Omni's settings to one zip, plus bookmarks, history, reading list, add-on data, Downloads lists and pointers only if you tick them. Saved passwords, cookies and sign-ins, the open tabs, caches, logs, screenshots and downloads are never included. A restore checks the whole zip before writing anything and keeps the old files. |

### New controls

| Button | Action |
| --- | --- |
| **L2 + D-pad up / down** | Zoom this site in / out |
| **L2 + R3** | Save a screenshot of the page |
| **D-pad left / right** (Tabs panel) | Pin / unpin the tab |
| **Triangle** (Tabs panel) | Mute / unmute the tab |

---

## ⚠️ Known limits

Current problems and their workarounds are in [KNOWN-ISSUES.md](KNOWN-ISSUES.md).

- **No Netflix, Disney+ or other copy-protected video.**
- **Nothing above 4K.**
- **Some JavaScript-heavy sites run slower** than on a PC or phone, even with the JIT on.
- **Saved passwords are only scrambled, not encrypted,** because the console has no secure storage Omni can use.
- **No location, camera, microphone, notifications or video calls.**
- **No HDR video yet.** HDR videos play, but as SDR (HDR output is built and being tested).
- **YouTube sometimes doesn't start playing.** Reload the page if it happens. See [KNOWN-ISSUES.md](KNOWN-ISSUES.md) for this and other current problems, with workarounds.

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
