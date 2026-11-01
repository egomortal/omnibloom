<p align="center">
  <img src="assets/icon/omni-icon-128.png" alt="Omni Browser icon" width="128">
</p>

# What Omni Can Do

*Last updated: November 1, 2026 (build 56c)*

Omni is a web browser for the PS5, built on WebKit, the same engine that powers
Safari. You control everything with a DualSense controller. It's designed for
watching video and browsing without ads.

This page lists what works today, what's being tested, and what's still coming.
Developers: see [DEVELOPERS.md](DEVELOPERS.md).

| Symbol | Meaning |
| :---: | --- |
| ✅ | **Works.** Tested on a real PS5. |
| 🧪 | **Built and tested on a PC,** but not yet confirmed on a PS5. |
| 🚧 | **Experimental.** Being worked on. |
| 📋 | **Planned.** Not built yet. |
| ❌ | **Not available.** See the notes for why. |

---

## 🌐 Browsing

| Feature | Status | Details |
| --- | :---: | --- |
| Modern website support | ✅ | Runs a full version of WebKit, Safari's engine, ported to the PS5. |
| Smooth scrolling | ✅ | Scrolls at about 60 fps, with no noticeable hitches. |
| Tabs | ✅ | Up to 8 tabs open, with 6 kept loaded in memory. |
| Bookmarks and shortcuts | ✅ | Press **L3** to save the current site to your shortcuts grid. |
| Translate pages | ✅ | Press the **touchpad** to translate the page. |
| Stay logged in | ✅ | Your logins are remembered after you close Omni. |
| Secure connections (HTTPS) | ✅ | Websites are security-checked the same way any normal browser does. |
| Password saving and autofill | ❌ | Left out on purpose. |
| Location, camera, microphone, notifications, video calls | ❌ | Not included in this version of Omni. |

## 📺 Video

| Feature | Status | Details |
| --- | :---: | --- |
| 4K at 60 fps | ✅ | Smooth. In a 10-minute test, only 50 of nearly 36,000 frames were skipped. |
| HDR | ✅ | Turns on automatically for HDR videos when your TV supports it. |
| Hardware video decoding | ✅ | Uses the PS5's built-in video chip. Supports H.264, HEVC and VP9, including 10-bit. |
| Background tabs free up memory | ✅ | A video in a hidden tab pauses and frees its memory after 1.5 seconds, then picks up again when you come back. You can keep more video tabs open this way. |
| Fullscreen controls | ✅ | See [Controls](#-controls) below. |
| Higher than 4K (e.g. 8K) | ❌ | The PS5's video hardware is the limit, not Omni. |
| Netflix, Disney+ and other protected services | ❌ | These need copy-protection software that Sony doesn't make available to homebrew apps. |
| The full YouTube website | 🚧 | Has been unreliable in the past. YouTube videos embedded on other sites play fine. |

## 🛡️ Ad Blocking

Omni has ad blocking built in and **turned on by default**. It uses the same
filter lists and rules as **uBlock Origin**, the popular ad-blocking extension.
You don't need to install anything.

| Feature | Status | Details |
| --- | :---: | --- |
| Block ads and trackers | ✅ | Stops ads and tracking scripts from loading. |
| Hide leftover ad boxes | ✅ | Removes the empty spaces and banners that ads leave behind, without hiding real page content. |
| Fast per-site rules | ✅ | Omni loads only the rules each site needs, so pages load faster than with the full rule set. |
| Fix sites that fight ad blockers | 🧪 | Uses uBlock's small page fixes to defeat "please disable your ad blocker" walls. |
| Hide annoyances | 🧪 | Hides cookie banners, newsletter popups, notification requests and chat bubbles. |
| Block pop-ups | 🧪 | New windows only open when you click something, and known pop-up ads are always blocked. |
| Skip redirect pages | 🧪 | Jumps past the "you are being redirected…" pages that track your clicks. |
| Clean up links | 🧪 | Strips tracking codes from web addresses. |

## ⬇️ Downloads

| Feature | Status | Details |
| --- | :---: | --- |
| Link grabber | ✅ | Finds video and media links on the page, including ones hidden inside embedded players that most link grabbers miss. Found links show up in the Downloads dialog and on the Launch page. |
| Privacy | ✅ | Only runs when **Media Downloads** is turned on, never in private tabs, and keeps no browsing history. |
| JDownloader and yt-dlp support | 📋 | Planned. |

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
| Touchpad | Open the edit row |
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

If your controller's stick drifts, go to **Browser Settings** and set the
**Dead zone** to Small, Medium, Large or Extra large. It smooths out the pointer,
scrolling and keyboard navigation. If you leave the controller alone, the
pointer also gets out of the way after 3 seconds.

## 🖥️ Display

| Feature | Status | Details |
| --- | :---: | --- |
| Choose a resolution | ✅ | **Settings > Resolution:** 1080p, 1440p or 4K. Takes effect after a restart. |
| Safe fallback | ✅ | If Omni fails to start at your chosen resolution, it switches back to 1080p on its own. |

---

## ⚠️ Known Limits

- **No Netflix, Disney+ or other copy-protected video.**
- **Nothing above 4K.**
- **Some JavaScript-heavy sites run slower** than on a PC or phone, because the PS5 doesn't let Omni use the speed boost (JIT) that desktop browsers use.
- **No location, camera, microphone, notifications or video calls.**
- **No password saving,** on purpose.
- **The PS5's graphics chip isn't used yet.** Everything runs on the processor plus the PS5's video chip. This is being worked on.

## 🔜 What's Next

- **Using the PS5's graphics chip for video.** Early tests are promising. If it works, video could get faster and more efficient.
- **JDownloader and yt-dlp support** for downloads.

---

## 🔒 Safety Built In

- Every update keeps a backup of the previous version, so a bad update can always be undone.
- Omni doesn't weaken the PS5's security or website security checks.
