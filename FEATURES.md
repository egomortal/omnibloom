<p align="center">
  <img src="assets/icon/omni-icon-128.png" alt="Omni Browser icon" width="128">
</p>

# What Omni Can Do

*Last updated: October 2026 (version 105)*

Omni is a web browser for the PS5, built on WebKit, the same engine that powers
Safari. It's designed for watching video and browsing without ads.

This page lists what works today, what's being tested, and what's still coming.

| Symbol | Meaning |
| :---: | --- |
| ✅ | **Works.** Tested on a real PS5. |
| 🧪 | **Built and tested on a PC,** but not yet confirmed on a PS5. |
| 🚧 | **Partly works.** Usable, but with known problems. |
| 📋 | **Planned.** Not built yet. |
| ❌ | **Not possible.** See the notes for why. |

---

## 🌐 Browsing

| Feature | Status | Details |
| --- | :---: | --- |
| Modern website support | ✅ | Runs a full version of WebKit, Safari's engine, ported to the PS5. |
| JavaScript | ✅ | Passes all 25 of its self-tests on the PS5. |
| Secure connections (HTTPS) | ✅ | Websites are security-checked the same way any normal browser does. |
| Tabs | ✅ | Open several pages at once. |
| Stay logged in | ✅ | Your logins are remembered after you close Omni. |
| Bookmarks and history | 🚧 | Not fully saved between sessions yet. |
| Faster JavaScript (JIT) | 📋 | Might be possible later, depending on what the PS5 allows. |

## 🎮 Controls

| Feature | Status | Details |
| --- | :---: | --- |
| Controller pointer | ✅ | Move a cursor around the page with the DualSense. |
| On-screen keyboard | ✅ | Type into search bars and forms. |
| Closing the keyboard | 🧪 | Press **Circle** or **Back** to close the keyboard. What you typed stays put so you can pick a suggestion. **Enter** still submits. |
| Home-screen tile | ✅ | Launch Omni from its own icon. You may need to press **Back** to see it. |

## 📺 Video

| Feature | Status | Details |
| --- | :---: | --- |
| Hardware video decoding | ✅ | Uses the PS5's built-in video chip for smooth playback. Supports H.264, HEVC and VP9, including 10-bit, from 720p up to 4K. |
| Streaming video | ✅ | Supports the streaming technology that sites like YouTube use. |
| 1080p at 60 fps | ✅ | Smooth playback with almost no skipped frames. |
| 4K at 30 fps | ✅ | Smooth, with no skipped frames once playback gets going. |
| 4K at 60 fps | 🚧 | Much smoother in version 105: about 1 in 100 frames skipped, down from 13 in 100. There's still stutter when a video starts. |
| Full screen | ✅ | Enter and exit full screen. Press **Back** to leave. |
| YouTube videos embedded on other sites | ✅ | Plays with sound. |
| The YouTube website itself | 🚧 | Doesn't work reliably yet. |
| Sound | 🧪 | The audio plays without errors, but nobody has confirmed by ear yet that it comes out of the speakers. |
| HDR | 📋 | Not built yet. 4K is standard color (SDR) for now. |
| Netflix, Disney+ and other protected services | ❌ | These need copy-protection software that Sony doesn't make available to homebrew apps. |

## 🖥️ Display

| Feature | Status | Details |
| --- | :---: | --- |
| Choose a resolution | ✅ | **Settings > Resolution:** 1080p, 1440p or 4K. Takes effect after a restart. |
| Safe fallback | ✅ | If Omni fails to start at your chosen resolution, it switches back to 1080p on its own. |

## 🛡️ Ad Blocking

Omni has ad blocking built in, powered by the same filter lists and rules as
**uBlock Origin**, the popular ad-blocking extension. You don't need to install
anything.

| Feature | Status | Details |
| --- | :---: | --- |
| Block ads and trackers | ✅ | Stops ads and tracking scripts from loading. |
| Full filter lists | 🧪 | About 141,000 blocking rules, up from about 3,500. Includes EasyList, EasyPrivacy, Peter Lowe's list and uBlock's own lists. Installed on the PS5 and waiting for its first full test. |
| Hide leftover ad boxes | 🧪 | Removes the empty spaces and banners that ads leave behind. |
| Fix sites that fight ad blockers | 🧪 | Uses uBlock's small page fixes to defeat "please disable your ad blocker" walls. |
| Hide annoyances | 🧪 | Hides cookie banners, newsletter popups, notification requests and chat bubbles. |
| Block pop-ups | 🧪 | New windows only open when you click something. Known pop-up ads are always blocked. Matched uBlock's decision in all 75,890 test cases. |
| Skip redirect pages | 🧪 | Jumps past the "you are being redirected…" pages that track your clicks. |
| Clean up links | 🧪 | Strips tracking codes from web addresses. |
| Turn blocking off for a site | 🧪 | Switch blocking off for a site that breaks, without turning it off everywhere. |

**Test results so far:** In PC testing, all 800 sample ads were blocked and all
69 everyday page elements, like images and fonts, still loaded. Over 2,000
other checks passed with no failures.

## ⬇️ Downloads

| Feature | Status | Details |
| --- | :---: | --- |
| JDownloader support | 📋 | Planned. |
| yt-dlp support | 📋 | Planned. |

---

## ⚠️ Known Problems

- **Stutter when a video starts or goes full screen.** It usually smooths out after a few seconds.
- **4K at 60 fps** still skips some frames.
- **Websites see the wrong screen size.** Omni tells pages the screen is 1080p even when running at 4K.
- **The YouTube website** isn't reliable yet. Embedded YouTube videos work fine.
- **One video site shows error 232403.** The cause hasn't been found yet.

## 🔜 What's Next

1. Fix the stutter when videos start and go full screen
2. Make 4K at 60 fps fully smooth
3. Report the correct screen size to websites
4. Test longer videos and more websites
5. Add HDR
6. Find out whether faster JavaScript (JIT) is possible on the PS5

---

## 🔒 Safety Built In

- Every update is checked to make sure the files weren't damaged or changed.
- Earlier working versions are kept, so a bad update can always be undone.
- Omni doesn't weaken the PS5's security or website security checks.
