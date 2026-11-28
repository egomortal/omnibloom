# Troubleshooting for developers

You read these files from the console over FTP, port 2121: the same server Setup uses.
For the user-facing problems and their workarounds, see `KNOWN-ISSUES.md`.

## Where the logs are

| File | Written by | What is in it | Source |
|---|---|---|---|
| `/data/omni/native/boot.log` | Omni title | start-up, child spawns (`children: ...`), missing imports (`[import] missing ...`). Three generations: `boot.log`, `.1`, `.2` | `omni/native-title/src/OmniNativeTitle.cpp` |
| `/data/omni/native/crash.log` | Omni title and child | crash reports (`OMNI_CRASH_V2`). Never rotated, so delete it yourself after reading | `omni/native-title/patches/engine-entry/OmniCrash.h` |
| `/data/omni/native/gpu-present.log` | Omni title | GPU video presenter | `omni/native-title/src/OmniGpuPresent.cpp` |
| `/data/omni/native/close-events.log` | engine child | why a child process left | `omni/native-title/child-src/launcher-child.cpp` |
| `/data/omni/native/sec-blocked.txt` | engine child | connections a page tried to make to blocked local addresses | `omni/native-title/child-src/omni-sec-connect.cpp` |
| `/data/omni/native/omni-files.log` | USB files broker | broker start, requests, errors | `omni/files-broker/src/omni-files.c` |
| `/data/omni/media-downloads.log` | Omni title, **v0.5.2** (`OMNI_MEDIA_DIAG_V1`) | one line per Media downloads step: health checks (state, status, size, ms), starter answers, tab switch decisions, link review. Restarts past 256 KB | v0.5.2 patch, see [features.md](features.md#media-downloads-l1r1) |
| `/data/hub/status.json` | Bloom Core | the health of every app (below) | Setup reads it in `setup/omnibloom_setup/installer.py` (`read_status`) |
| JDownloader session `native.log`, `native-receipt.json` | JDownloader engine | engine start and exit | `downloads/worker/jd_lifecycle.py`; `jdownloader/engine/java_worker.cpp` |

The **Downloads worker writes no log** on purpose. It sends stdout and stderr to `/dev/null`, so no URLs or cookies
end up on disk (`downloads/worker/console_worker.py`). Use its `/healthz` and `/api/status`, or v0.5.2's
`media-downloads.log` on Omni's side.

Setup creates `/data/hub/logs/` and `/data/hub/crash/` for apps to use (`config.py`). `CONTRIBUTING.md` asks bug
reporters for them.

## Reading the hub status

`/data/hub/status.json` is rewritten about every 10 seconds. The useful parts:

```json
{
  "name": "Bloom Core", "version": "...", "pid": 1234, "port": 8760, "written_at": "...",
  "apps": [
    {"id": "downloads", "version": "...", "port": 8765, "verified": true, "status": "...", "why": "...", "up": false}
  ],
  "invalid": [{"file": "apps/foo.json", "reason": "..."}]
}
```

- `verified: false` means the card, the receipt or the files don't match. Run Setup's Repair.
- `invalid` lists cards Bloom Core refused, with the reason.
- `up` says whether the app answered its health check.
- A stale `written_at` means Bloom Core is not running. Check autoload (below).

`installer.explain_status` in `setup/omnibloom_setup/installer.py` turns these fields into plain sentences. It is a
good guide to what each one means. On the console itself, `GET http://127.0.0.1:8760/v1/apps` gives the live list.

## Flag files

Omni reads its switches from files in `/data/omni/`. Most are checked once when Omni starts, so restart Omni after
changing one.

| File | Effect | Source |
|---|---|---|
| `browser-mode.flag` | start the browser, not the engine self-test (titles up to v0.5.1) | `omni/engine/entry/OmniMain.cpp` |
| `prespawn-disabled.flag` | don't start the web and network processes early | `omni/native-title/src/OmniNativeTitle.cpp` |
| `media-downloads-enabled.flag` | turn on Media downloads (L1+R1) | `OmniMediaDownloads.h` |
| `jsc-jit-off.flag` | turn the JavaScript JIT off (it is on by default since rc6) | `omni/native-title/patches/launch/rc6/apply_jit_default_on.py` |
| `gpu-pages-stage1.flag` / `gpu-pages-stage1-off.flag` | GPU page drawing on / kill switch | `patches/experimental/gpu-pages/stage1/README.md` |
| `gpu-present.flag`, `gpu-video.flag` | GPU video path | `patches/video-4k60/TEST-PLAN.md` |
| `ytguard-off.flag`, `nc-reset-off.flag` | YouTube guard off / network cache reset off | `patches/launch/rc5/title/OmniYtGuard.h` |
| `crash-diagnostics.flag` | more crash detail | `omni/engine/entry/OmniMain.cpp` |
| `inproc-web-off.flag` | run pages in the separate engine process instead of the in-app page engine | [engine-and-memory.md](engine-and-memory.md#in-app-page-engine) |
| `pt-gentle-off.flag`, `pt-watchdog-line.txt` | page-table guard: gentle steps off / the line (default 6600) | [engine-and-memory.md](engine-and-memory.md#page-table-guard) |
| `media-buffer-mb.txt`, `media-buffer-off.flag` | video buffer budget (not in the daily build yet) | [engine-and-memory.md](engine-and-memory.md#bigger-media-buffer) |
| `video-hdr-preference.txt` | HDR Off / Auto / On | `setup/omnibloom_setup/config.py` (`OMNI_HDR_PREF`) |

(`patches/` above means `omni/native-title/patches/`.)

## Common problems

**Omni says "upload omni-engine.elf to /data/omni first", or opens and closes.**
The first-run files are missing (titles up to v0.5.1). Run Setup's Repair, or create `/data/omni/omni-engine.elf`
(any small file) and `/data/omni/browser-mode.flag` (`1`). See `KNOWN-ISSUES.md` and
[setup-internals.md](setup-internals.md#omnis-first-run-files).

**`boot.log` shows `[import] missing <name>` and the title exits.**
The title imports a function the console does not have. Fix the build so the import gate passes (see
[omni-title-build.md](omni-title-build.md#the-import-gate)).

**`boot.log` shows `children: loader connect failed`.**
The ELF loader is not listening on 9021. Start the user's elfldr payload.

**"Media downloads unavailable".**
Check, in order:

1. Is `/data/hub/status.json` fresh? If not, Bloom Core is not running. Check that `/data/pldmgr/autoload.txt` has
   full paths (`/data/pldmgr/payloads/BloomCore/hub.elf`), not bare names.
2. Does the `downloads` card exist in `/data/hub/apps/`, with a port in 8761-8899?
3. Does `/data/omni-downloader/python-worker.elf` exist? Is websrv's `/hbldr` (port 8080) running? Omni starts the
   worker through it.
4. On v0.5.2, read `/data/omni/media-downloads.log`. It shows which step failed.

**An app shows as not verified in the Apps menu.**
Omni checks the card against the receipt's `card_sha256` itself (`omni/native-title/child-src/OmniHubCards.h`).
Someone edited the card by hand, or Setup was interrupted. Run Repair.

**USB drives don't show up.**
Look in `/data/omni/native/omni-files.log`. "files-broker card has no assigned suite port" means the
`files-broker` card is missing or has no port. Reinstall it with Setup.

## Before you file a bug

- Remove personal data from logs: URLs you visited, your console's address, your user name.
- Say which title and child you ran. `boot.log` names them.
