<p align="center">
  <img src="assets/icon/omni-icon-128.png" alt="Omni Browser icon" width="128">
</p>

# Omni Browser: Features and Status

Status as of the **v105** checkpoint (October 2026). v105 is installed and
hash-verified in both Omni launch locations. The v106 and v107 experiments were
rejected and rolled back.

**Legend**

- ✅ **Working**: tested on a real PS5
- 🧪 **Built or tested off-console**: compiled or passed desktop/host tests, but not yet confirmed on a console
- 🚧 **In progress**: partly working, with known problems
- 📋 **Planned**
- ⛔ **Not possible or not supported**

---

## Browser engine

| Feature | Status | Notes |
| --- | --- | --- |
| JavaScriptCore (JS engine) for PS5 | ✅ | Self-test passes 25/25 on a 13.60 console (checksum `247239`, benchmark 177 ms), matching a reference engine |
| Full WebKit build for PS5 | ✅ | WebCore, WebKit, Skia (CPU), and curl/OpenSSL networking. `WebProcess` and `NetworkProcess` are 122 MB each, stripped (8,285 build steps) |
| Multi-process architecture | ✅ | Own `ProcessLauncher` (elfldr spawn with `SCM_RIGHTS` socket hand-off), host-tested with ASan/UBSan |
| JavaScript interpreter (LLInt) | ✅ | Runs without JIT |
| JIT compilation | 📋 | Only possible if the console allows executable memory for homebrew. Not yet probed |
| Rendering | ✅ | Skia paints on the CPU. Output goes through Mesa EGL/GLES (Zink + RADV) |
| HTTPS / TLS | ✅ | Standard certificate validation, origin rules, and console DNS are kept intact |

## Interface and controls

| Feature | Status | Notes |
| --- | --- | --- |
| Tabs | ✅ | |
| Controller-driven pointer | ✅ | DualSense |
| On-screen keyboard | ✅ | |
| Keyboard dismissal | 🧪 | B/Circle, Back/View, Escape, or Cancel close the keyboard without submitting. Typed text and focus are kept so you can pick suggestions. Go/Enter still submits. Physical controller test pending |
| Home-screen tile | ✅ | Launch from the Omni icon. The shortcut may need Back to reveal Omni |
| Resolution setting | ✅ | Settings > Resolution: 1080p / 1440p / 4K SDR (restart required) |
| Startup recovery | ✅ | If startup doesn't finish, Omni falls back to 1080p |
| Cookie persistence | ✅ | Survives restarts (since v38) |
| Bookmarks and history | 🚧 | Full persistent bookmarks/history not yet established |

## Video and media

| Feature | Status | Notes |
| --- | --- | --- |
| Hardware video decoding | ✅ | PS5 hardware decoder with software (FFmpeg) fallback. Bit-exact on 9/9 tested formats: H.264, HEVC 8/10-bit, VP9 profile 0/2, 720p to 4K |
| MediaSource Extensions (MSE) | ✅ | Enabled. Needed for YouTube-style streaming |
| 1080p60 playback | ✅ | 0–1 dropped frames per ~5 s steady window after the v100 timing fix. No audio underruns |
| 4K30 playback (SDR) | ✅ | 420 steady frames with zero drops, audio underruns, or native errors |
| 4K60 playback (SDR) | 🚧 | Fullscreen steady drops cut from 13.2% to 1.04% in v105 (1,250 shown / 18 dropped). Startup stalls and drop bursts remain |
| Fullscreen enter/exit | ✅ | Including Back to exit |
| Embedded YouTube player | ✅ | Plays with audio submitted and no native errors |
| Full YouTube website | 🚧 | Still unreliable |
| HDR | 📋 | Not implemented yet. 4K output is currently SDR only |
| Physical audio output | 🧪 | Audio is submitted with no underruns, but whether it is audible hasn't been confirmed by ear |
| DRM video (Netflix, Disney+, etc.) | ⛔ | Widevine/PlayReady are closed by Sony |

## Built-in ad and tracker blocking (uBlock)

| Feature | Status | Notes |
| --- | --- | --- |
| Network request blocking | ✅ | uBlock's network filtering engine is integrated. This is not the full desktop extension |
| Default filter lists | 🧪 | EasyList, EasyPrivacy, uBlock filters/privacy/badware/unbreak/quick-fixes, and Peter Lowe's list: 140,985 network rules (up from ~3,500). Installed on the console. First full run pending |
| WebKit content blocker | ✅ | WebKit's native content-extension engine (the one behind Safari blockers and uBO Lite) is turned on. Sony ships it off |
| Cosmetic filtering | 🧪 | Site-specific, generic, and procedural element hiding via uBO Lite content scripts |
| Scriptlets | 🧪 | Injected as WebKit user scripts |
| Per-site on/off switch | 🧪 | |
| Annoyance lists | 🧪 | Cookie notices, newsletter popups, notification prompts, chat widgets |
| Popup blocking | 🧪 | Requires a user gesture and honours `$popup` filters. Covers URL-path rules, opener/popup domains, first/third-party, `important`, `match-case`, `badfilter`, and regex rules. 75,890/75,890 cases agree with the real uBlock engine |
| Link skipping | 🧪 | uBlock `$urlskip` plus Omni's redirector list skip tracking/redirect pages |
| URL cleaning | 🧪 | `$removeparam` strips tracking parameters |

Desktop test results: 599 + 599 (interpreter) + 893 checks with 0 failures.
Network sample: 800/800 ad requests blocked and 69/69 everyday resources allowed.

## Downloads

| Feature | Status | Notes |
| --- | --- | --- |
| JDownloader integration | 📋 | Listed in the README. No status in the current notes |
| yt-dlp integration | 📋 | Listed in the README. No status in the current notes |

## Development and safety tooling

- **Hash-verified installs**: every deploy is checked by SHA256 in both launch locations
- **Rollback**: earlier tested builds (v38, v97, v100, v104) are kept with restore scripts
- **Transactional staging** for console installs
- **Self-test payload**: `omni-jsc-selftest.elf` reports results as a console notification and writes a log to `/data/omni/jsc-selftest.txt`
- **Hardware-decode probe**: `tools/vdec-probe/` checks decoding bit-for-bit against FFmpeg
- **Console access** through websrv (8080), FTP (2121), and the app loader (9021)

---

## Known issues

- Startup and fullscreen-transition stalls (dropped frames in the first seconds of playback)
- 4K60 still drops frames in bursts
- JavaScript reports the wrong screen size to pages (1920×1080 at DPR 3)
- The full YouTube site is unreliable
- Error 232403 on a third-party video site (refused playlist request; cause not yet known)

## Next up

1. Reduce startup and fullscreen-transition stalls
2. Profile 4K60 separately
3. Fix JavaScript screen metrics
4. Longer and site-specific playback tests
5. HDR output
6. Probe whether JIT is possible
