# Feature guides

Each section answers three questions: which files and markers implement the feature, how it works, and how to
change it safely.

Most of Omni's browser code is in the engine shell's `engine/entry/` folder. In this repository you will find
it in several copies:

- `omni/engine/entry/`: an older shell, before the s3.4 patches. Good for reading, but not what ships.
- `omni/native-title/patches/s34/s34-entry/`: the s3.4 files.
- `omni/native-title/patches/launch/title/s34-entry/`: the release (launch) copies.

When you change a feature, change the **launch** copy through a patch script (see
[omni-title-build.md](omni-title-build.md)). Search all copies for the marker first:

```sh
git grep -n OMNI_SHOULDER_DOWNLOADS_V1
```

Markers listed as **v0.5.2** belong to the next title. Their patch scripts are not in this repository yet.

---

## Controller shortcuts

The user-facing tables are in `FEATURES.md` ("Browsing", the keyboard and fullscreen sections). When you add or
change a shortcut, update that table too.

### Media downloads (L1+R1)

Press L1 and R1 together on a page with a video. Omni sends the page's media link to the Downloads worker.

**Where:**

| Part | File | Marker |
|---|---|---|
| L1+R1 chord | `omni/native-title/patches/s34/s34-entry/OmniBrowser.cpp` (search `OmniShoulderChord`) | `OMNI_SHOULDER_DOWNLOADS_V1` |
| link review | `omni/engine/entry/OmniNativeLinkReview.inc` | `OMNI_LINK_REVIEW_V1`, `OMNI_NET_GRABBER_V1` |
| starter and health check | `omni/native-title/patches/s34/s34-entry/OmniMediaDownloads.h` (the launch copy is identical) | `OMNI_MEDIA_HEALTH_V2` |
| glue to the browser | `OmniMediaDownloadsHooks.inc`, `OmniMediaSection.h` (same folder) | |

**How it works:**

1. **The chord.** The chord only works while `/data/omni/media-downloads-enabled.flag` exists. Otherwise L1 and
   R1 keep their normal job. With the flag, the chord calls `omniGrabBegin(2)`, or opens Media downloads directly.
2. **Link review.** Before any URL leaves the page, `omniLinkContext` checks privacy (no private tabs) and that
   the page owns the link. `omniLinkReviewBegin` reads the page in a separate script world. `omniLinkDeliver`
   sends the result to one of three places: the saved view (0), share (1) or the Media section (2).
3. **The health check.** `ensureReady` in `OmniMediaDownloads.h` calls `GET /healthz` on the worker's port,
   loopback only, with a 4000 ms timeout. The answer must be exactly
   `{"service":"omni-media-worker","api_version":1}`, and `HealthReader` rejects anything else.
4. **The starter.** If the connection is **refused** (nothing is listening), Omni starts the worker through
   websrv: `GET /hbldr?path=/data/omni-downloader/python-worker.elf&args=omni-media-worker&daemon=1&pipe=0` on
   port 8080. It then waits up to 30 s for `/healthz`. A slow answer is retried, not relaunched, and there is a
   cooldown between launches.
5. **No UI freeze.** `Starter` runs all of this on one detached thread. The UI loop only polls it.

**The port.** `OmniMediaSection::assignedPort()` reads the port from the `downloads` ID card and accepts only
8761-8899. Port 8765 is the old default (`omni/native-title/child-src/OmniHubCards.h`, `legacyDownloadsPort`).

**v0.5.2:**

- `OMNI_MEDIA_SWITCH_V1`: once the worker is ready, Omni switches to Media downloads if you are still on the same
  tab, with the same privacy, and not newly in fullscreen. A URL change no longer cancels it.
- `OMNI_MEDIA_DIAG_V1`: writes each step to `/data/omni/media-downloads.log` (see
  [troubleshooting.md](troubleshooting.md)).

**Change it safely:**

- Never let a page see the worker's token or reach the worker's write APIs. The token stays in the worker's own
  page (`downloads/worker/worker.py`).
- Keep the starter off the UI thread.
- Only launch on "connection refused". A slow worker that is already starting must not get a second copy.
- Known gap: `OmniNativeLinkReview.inc` still names `http://127.0.0.1:8765/downloads` in its clear script. If a card
  moves the worker to another port, that line will not match.
- There are no host tests for the starter or link review yet. Test on a console with the diagnostics log on.

### L2 chords (v0.5.2, `OMNI_L2_CHORDS_V1`)

| Press | Does |
|---|---|
| L2 tap | saved links (as before), but now on **release**, so it can be part of a chord |
| L2 + Square | copy: the selection, else the link under the pointer, else the page URL (max 8 KB) |
| L2 + Triangle | paste into the focused field |
| L2 + Cross | open the Quick bar |

- **Files:** `OmniBrowser.cpp` and `OmniBrowserSettings.h`.
- **When it works:** only while browsing; not in the keyboard, Settings, a panel or fullscreen video.
- **Held and released:** the L2 axis counts as held at 20000 or more, and as released at 8000 or less. While L2 is
  held, the face button's press and release are swallowed, so the page never sees half a chord.
- **Change it safely:** keep the press/release swallowing. Without it, a page gets a Cross press with no matching
  release.

### The Create button (v0.5.2, `OMNI_SETTINGS_CREATE_V1`)

Create opens Browser settings. Pressing it again closes them (`OmniBrowser.cpp`).

---

## The quick-access row and the Quick bar

**The quick-access row** is the row of buttons at the top of the menu: uBlock, Dark mode, Apps and Add-ons.

- **File:** `omni/native-title/patches/s34/s34-entry/OmniMqQuickAccess.h`.
- **Marker:** `OMNI_MQ_NATIVE_V1`.
- **Functions:** `omniMqHit` (hit test), `omniMqButton` (D-pad and Cross), `omniMqDraw` (drawing).

**The Quick bar** is the "Options" panel.

- **File:** `OmniQuickMenu.h` (same folder), `omniFxQuickMenuShow`.
- **Groups:** Browse, Quick toggles, Apps, Settings, More.
- **Opens with:** Options/START, Esc, or (v0.5.2) L2+Cross.

**v0.5.2, `OMNI_QA_CUSTOM_V1`:** the user chooses the row's buttons.

- The choice is saved in `/data/omni/quick-access.txt`, one key per line, up to 6 keys.
- Unknown or duplicate keys are ignored. With no file, the row shows the four default buttons.
- The editor is in Browser settings, under "Quick access buttons...".

**Change it safely:**

- Add a new button as a new key in the catalog. Never renumber existing keys, because users' files store them.
- Buttons that only make sense on a web page (Dark mode, Copy, Paste) must be disabled on built-in pages.

---

## Dark mode

**Base file:** `OmniDarkPages.h`. The pre-patch copy is `omni/engine/entry/OmniDarkPages.h`. Per-site choices are
stored in `/data/omni/site-dark.txt`.

Three patches make dark mode work the standard way. They are applied in this order
(`omni/native-title/patches/README.md`, s3.4d):

| # | Script (`patches/s34/tools/`, launch copies in `patches/launch/title/tools/`) | Marker | What it does |
|---|---|---|---|
| 1 | `apply_dark_video.py` | `OMNI_DARK_VIDEO_PLANE_V1` | the invert filter steps aside while a video covers 20% or more of the screen, so video keeps its fast plane |
| 2 | `apply_dark_standard.py` | `OMNI_DARK_STANDARD_V1` | the site's own dark theme first; the invert filter only as a last resort; add-on hook `<html data-omni-dark-addon="on">` |
| 3 | `apply_dark_emu.py` | `OMNI_DARK_APPEARANCE_EMU_V1` | answers `matchMedia('(prefers-color-scheme: dark)')` from Omni's setting, because the engine's own dark appearance does not reach pages |

**v0.5.2, `OMNI_DARK_CHOICE_V1`:** one setting with three values, stored in `/data/omni/dark-style.txt`.

| Value | Meaning |
|---|---|
| Off | no dark mode |
| Natural | ask the site for its own dark theme (patches 2 and 3); no invert filter |
| Forced | Natural, plus the invert filter for sites with no dark theme |

If `dark-style.txt` is missing, the old "Dark pages (all sites)" switch carries over: on becomes Forced, off
becomes Off. Sites marked "Always dark" still get the filter.

**Tests (node, no console):**

```sh
node omni/native-title/patches/s34/hosttest/dark_video_test.js    <path to OmniDarkPages.h>
node omni/native-title/patches/s34/hosttest/dark_standard_test.js <path to OmniDarkPages.h>
node omni/native-title/patches/s34/hosttest/dark_emu_test.js      <path to OmniDarkPages.h>
```

The README reports 12/12, 11/11 and 6/6.

**Change it safely:**

- Never let the filter sit on a playing video. It knocks YouTube off its fast video plane and the video stalls.
- Keep the add-on hook, so a dark add-on can turn Omni's filter off.
- Run all three tests after any change to `OmniDarkPages.h`.

---

## Add-ons

Add-ons are small bundles of JavaScript and CSS that Omni injects into matching pages.

### Where they are

| Path | What |
|---|---|
| `addons/bundled/<id>/` | the source of each bundled add-on: `manifest.json`, JS, `addon.css`, `LICENSE`, `CREDITS.md` or `SOURCES` |
| `addons/bundled-r45.json` | the bundle index: id, origin, licence, `default_on`, `hosts`, `matches`, size |
| `omni/pages/bundle-clean4/addons/` | the built-in Add-ons page |

`omni/native-title/build.py` copies the Add-ons page into the title package under `pages/addons`, which is
`/app0/pages/addons` on the console. The v0.5.2 notes say the add-on bundles also ship read-only inside the title
(`/app0/addons`).

### The manifest (`OMNI_ADDONS_V1`)

Example, from `addons/bundled/omni-video-speed/manifest.json` (shortened):

```json
{
  "manifest_version": 1,
  "id": "omni-video-speed",
  "name": "Video speed",
  "version": "1.0.0",
  "licence": "MIT",
  "matches": ["*://*/*"],
  "excludes": [],
  "js": ["controls.js", "core.js", "runtime.js"],
  "css": ["addon.css"],
  "run_at": "document_end",
  "all_frames": false,
  "default_on": false,
  "private_safe": false,
  "quick_switch": true,
  "live_toggle": true,
  "css_level": "user",
  "hosts": [],
  "settings": [{"key": "step", "type": "choice", "label": "Speed step", "default": "0.25",
                "choices": ["0.1", "0.25", "0.5"]}]
}
```

| Field | Meaning |
|---|---|
| `id` | stable id; also the name of the add-on's script world `omni-addon-<id>` |
| `matches` / `excludes` | URL patterns where it runs / never runs |
| `js` / `css` | files, injected in the order listed |
| `run_at`, `all_frames` | when it is injected and whether it is injected into frames too |
| `default_on` | on for new users |
| `private_safe` | may run in private tabs |
| `quick_switch`, `live_toggle` | can be switched from the Quick bar; can be switched without a reload |
| `hosts` | the only hosts `omniAddon.fetch` may reach |
| `settings[]` | `bool`, `choice`, `range` or `text`, each with `key`, `label`, `default` |

### The `window.omniAddon` API

Inside its own world, each add-on sees `window.omniAddon`. The members used by the bundled add-ons are:

| Member | Use |
|---|---|
| `id`, `top`, `active` | who am I, am I in the top frame, am I on |
| `settings.get(key)`, `settings.all()`, `settings.set(key, value)` | the user's settings |
| `storage.get(key)`, `storage.set(key, value)` | small saved values (returns promises) |
| `onEnable(fn)`, `onDisable(fn)`, `onSettings(fn)` | live switch and settings changes |
| `fetch(url)` | network access, only to `hosts` |
| `toast(text)` | a short message |

The engine side is in `omni/native-title/patches/engine-entry/OmniBlocker.cpp` (search `OMNI_ADDONS_V1`).
Each add-on gets its own script world and message handler (`webkit.messageHandlers.omniAddon`). Private tabs use a
separate content controller, so a normal add-on never sees a private page.

### Limits

- The number of add-ons is capped in `OmniAddonsCore.h` (`maxAddons`). It is 24 today. v0.5.2 raises it to 40
  (`OMNI_ADDON_CAP_40_V1`). `OmniAddonsCore.h` is part of the engine tree and is not in this repository.
- Keep stored values small. `addons/bundled/dark-reader/adapter.js` notes a 64 KB limit per value.

### Add a bundled add-on

1. Make `addons/bundled/<id>/` with a manifest like the one above, your JS and CSS, a `LICENSE` and a credits file.
2. Use original code or a compatible licence. Credit the source in `CREDITS.md`.
3. Ask only for the `hosts` you need. Leave `private_safe` false unless the add-on never stores or sends anything.
4. Add a row to `addons/bundled-r45.json`.
5. Refresh `SOURCE-MANIFEST.json` (see [release-process.md](release-process.md)).

---

## The YouTube guard

Without it, YouTube can stop playing after about one minute. This happens when YouTube does not accept the
player's proof-of-origin token.

- **File:** `omni/native-title/patches/launch/rc5/title/OmniYtGuard.h`.
- **Marker:** `OMNI_YT_ATTEST_GUARD_V1`. The binary contains the text `OMNI_YTGUARD_V1`.
- **Build:** `omni/native-title/patches/build/build-omni-ytguard-title.sh` (`MODE=test|ship`). The rc6 title script
  applies it too.

**How it works:**

1. A script runs at document start on `youtube.com/watch` pages. It wraps `fetch` and XHR, and reads only one
   field of the video responses: the stream protection status.
2. If YouTube rejects the token, the guard asks Omni to reload the page (`WKPageReload`).
3. If the status says the stream is blocked, or the rejection lasts 20 s, it asks for a full reload from origin
   and keeps the `t=` position.
4. It talks to Omni through `window.prompt('\x01OMNI_YTGUARD_V1...')`, which `omniYtGuardPrompt` handles. The
   number of reloads is capped (`MAXR`).

The same file also has `OMNI_NC_RESET_V1`, which moves the old network cache aside once per profile.

- **Off switches:** `/data/omni/ytguard-off.flag` and `/data/omni/nc-reset-off.flag`.
- **Tests (node):** `omni/native-title/patches/launch/rc5/tests/guard_ump_test.js` and `guard_sim_test.js`.
- **Change it safely:** run both tests. Keep the guard read-only: it must never change YouTube's requests. A
  ship title must not contain the probe text `OMNI_YTATTEST_V1`, and the rc6 build script checks this.

---

## GPU page drawing ("layers")

Read `omni/native-title/patches/experimental/gpu-pages/stage1/README.md` first. In short:

- Omni normally draws pages on the CPU. Only video uses the GPU.
- Stage 1 turns on WebKit's accelerated compositing in the page process. Page **layers** are composited on the GPU
  (GLES through Zink on RADV). Rasterisation stays on the CPU.
- The title keeps sole ownership of the GPU. The page process is a client of the title's GPU broker (`broker/`).
  The finished frame is read back once per frame.
- The broker keeps 3 GiB for video and gives a page at most 1 GiB (`OMNI_GPUPAGES_MEMSPLIT_V1`).

**It is opt-in.** Nothing runs unless `/data/omni/gpu-pages-stage1.flag` exists.
`gpu-pages-stage1-off.flag` is the kill switch. `gpu-pages-host-mib.txt` sets the memory budget (64 to 1024 MiB,
default 384). The README lists the diagnostic flags.

**Status (README, 2026-11-13):** works, with steady 59.94 fps HDR video, but it is not faster than CPU drawing
yet. Stage 2 (GPU rasterisation) is where the gain is expected.

**Change it safely:**

- If anything fails at start, the page process must fall back to CPU drawing.
- The title must still start on a console without the EGL/GL libraries. That is why `tools/add_lazy_graphics.py`
  exists, and why the import gate is there.
