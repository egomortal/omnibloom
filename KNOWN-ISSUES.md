# Known issues and workarounds

*Last updated November 13, 2026 (v0.5.1). Tested on one PS5, firmware 13.60.*

If something here affects you, the workaround is listed with it. If you hit a problem that isn't listed, please
[open an issue](https://github.com/egomortal/omnibloom/issues) and say which version and firmware you're on.

## Open issues

### YouTube stops at 720p, uBlock doesn't block, no HDR (fresh installs)
- **What happens:** on a console that never had an older Omni, YouTube only offers up to 720p, video can stutter, ads aren't blocked, HDR stays off and Media downloads says it's disabled.
- **Why:** Omni v0.5.1 switches these features on with small files in `/data/omni/`, and Setup didn't create them. The consoles Omni was tested on had them from earlier versions:
  - `mse-preview.flag`: Media Source Extensions, which YouTube needs for anything above 720p;
  - `hw-decode.flag`: hardware video decoding;
  - `media-preview.flag`: the video player for normal video files;
  - `ublock-native.flag`: uBlock Origin's built-in blocker;
  - `hdr-auto.flag`: HDR;
  - `media-downloads-enabled.flag`: Media downloads.
- **Fix:** download Omnibloom Setup again from the [v0.5.1 release](https://github.com/egomortal/omnibloom/releases/tag/v0.5.1), open **Installed apps…** and press **Repair** next to Omni (or install again). Setup creates any missing switch and never changes one you already have. Then restart Omni.
- **By hand (FTP):** create each file above in `/data/omni/`, containing `1`, and restart Omni.
- **Status:** fixed in the current Setup; the next Omni version turns these on by default.

### Omni won't start: "Omni Engine: upload omni-engine.elf to /data/omni first"
- **What happens:** after a fresh install, opening Omni shows that notification and nothing else.
- **Why:** Omni checks for two files from older test setups before it starts the browser: `/data/omni/omni-engine.elf` and `/data/omni/browser-mode.flag`. It doesn't run that file; it starts its page engine from `/data/omni/native/omni-engine-child.elf`, which Setup installs. Consoles that had an older Omni already have the file, so the check never showed up in testing. Setup doesn't create it.
- **Workaround (two files, both in `/data/omni/`):**
  1. With an FTP client, copy `/data/omni/native/omni-engine-child.elf` to `/data/omni/omni-engine.elf` (same folder level as `native`, not inside it).
  2. Create a small text file `/data/omni/browser-mode.flag` containing `1`. Without it, Omni starts its engine self-test, not the browser.

  Then open Omni again.
- **Status:** fixed in the current Setup: download it again from the [v0.5.1 release](https://github.com/egomortal/omnibloom/releases/tag/v0.5.1) and press **Repair** (or Install). It creates both files when they're missing and never replaces existing ones. The next Omni version won't need them at all.

### YouTube sometimes doesn't start playing
- **What happens:** the video page opens but the video never starts, or Omni reloads the page a few times first.
- **Why:** YouTube checks a playback token from its player before it streams. On the PS5 it rejects about half of the tokens Omni's player makes.
  - Omni's YouTube guard notices a rejected token and reloads the page at the same spot to get a new one, up to 5 times per video. That usually fixes it on its own.
  - In one console test, YouTube rejected three tokens in a row. The fourth was accepted, but the video still didn't start.
- **Workaround:** reload the page (or open the video again). If it keeps happening, close Omni and open it again.
- **Status:** being worked on. The fix will make Omni notice "token accepted but nothing playing" and recover by itself.

### "Media downloads unavailable" (LT / double bumper)
- **What happens:** the Media downloads shortcut says it's unavailable, even though the downloads worker is installed.
- **Why:** Omni finds the downloads worker through **Bloom Core**. If Bloom Core isn't running, Omni can't find it.
  - Before v0.5.1's Setup update, Setup added Bloom Core and Master Control to Payload Manager's start list as bare file names (`hub.elf`).
  - Payload Manager v0.6.3 doesn't start bare names, so after a reboot Bloom Core never came up.
- **Workaround:** download the current **Omnibloom Setup** from the [v0.5.1 release](https://github.com/egomortal/omnibloom/releases/tag/v0.5.1) and press **Repair**. It rewrites the start list with full paths.
  - Or edit `/data/pldmgr/autoload.txt` yourself and change the lines to:
    ```
    /data/pldmgr/payloads/BloomCore/hub.elf
    /data/pldmgr/payloads/master-control/master-control.elf
    ```
  - Then reboot and run your jailbreak.
- **Status:** fixed in the Setup apps now attached to v0.5.1. If Bloom Core is running and it still says unavailable, the worker may be slow to answer. v0.5.1 now gives it up to 4 seconds and keeps trying for 30 seconds.

### YouTube links fail in Downloads with "points to a local or private address"
- **What happens:** Downloads refuses YouTube links.
- **Why:** some jailbreak setups run a DNS blocker (for example nanoDNS) that hides YouTube's addresses to protect the exploit. The worker got `0.0.0.0` back and, correctly, refused it.
- **Workaround:** none needed from v0.5.1 (downloader-9). When the console's own lookup is blocked or fails, the worker asks public DNS (1.1.1.1, 8.8.8.8) itself, and every address still has to pass the public-address check.
- **Status:** fixed and tested on a PC with the block simulated. It hasn't been tested on a console yet.

### GPU page drawing ("layers") is experimental
- **What happens:** with layers turned on, pages aren't faster than normal drawing yet, and the first full page takes about 1.5 to 3 seconds of shader compiling. Mesa's shader cache can't work in this build.
- **Workaround:** layers is **off by default**. If you turned it on and something looks wrong, delete `/data/omni/gpu-pages-stage1.flag` or create `/data/omni/gpu-pages-stage1-off.flag`, then restart Omni.
- **Status:** video plays at full speed with layers on. The speed-up is expected to come from drawing the page content itself on the GPU, which is the next stage.

### A site misbehaves with the JavaScript JIT on
- **What happens:** the JIT is on by default since v0.5.1. If a site crashes or acts oddly, the JIT is worth ruling out.
- **Workaround:** **Settings > JavaScript JIT** turns it off. Creating `/data/omni/jsc-jit-off.flag` does the same.
- **Status:** no site is known to break with it. Please report one if you find it.

### HDR video
- **What happens:** HDR videos may be shown as SDR.
- **Status:** HDR10 output is built and passes its tests. It's still being checked on real TVs, see [FEATURES.md](FEATURES.md).

## Limits (by design or not possible yet)

- **No Netflix, Disney+ or other copy-protected video.** Omni never bypasses copy protection.
- **Nothing above 4K.**
- **Some JavaScript-heavy sites run slower** than on a PC or phone, even with the JIT on.
- **Saved passwords are only scrambled, not encrypted,** because the console has no secure storage Omni can use.
- **No location, camera, microphone, notifications or video calls.**
- **Only firmware 13.60 is tested.** Others may work. See [personal notes](personal%20notes.md).
- **JDownloader 2 isn't included.** Setup uses your own copy from [jdownloader.org](https://jdownloader.org/jdownloader2).

## Setup checklist (most install problems)

Setup needs these running on the PS5 before it can install:
- **An FTP server** (for example ftpsrv) on port 2121.
- **A payload loader** (elfldr) on port 9021.
- **ShadowMountPlus** and **kstuff** in your Payload Manager start list.

If Setup says your PS5 was found but FTP isn't running, load your FTP payload from Payload Manager. Setup carries
on by itself as soon as FTP answers.

## Fixed recently

- **Reddit-style pages with many small videos crashed** (v0.5.0). The software video player wrote past its picture buffer for some video widths. Fixed and tested for 20 minutes on the console.
- **YouTube stopped after about a minute** (v0.5.0). Fixed by a cache fix and the YouTube guard.
- **Setup's start list used bare names** (v0.5.1 Setup update). Covered above.
