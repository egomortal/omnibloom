# In-app engine, memory guard and media buffer

This page covers Omni's newest work on how pages run and how memory is kept safe:

| Feature | Marker | Status (2026-11-27) |
|---|---|---|
| [In-app page engine](#in-app-page-engine) | `OMNI_INPROC_NET_V1` and the `OMNI_INPROC_*` patches | **on by default** in the owner's daily build since 2026-11-26 |
| [Page-table guard](#page-table-guard) | `OMNI_PT_WATCHDOG_V1`, `OMNI_PT_GENTLE_V1` | **on** in the daily build |
| [Bigger media buffer](#bigger-media-buffer) | `OMNI_MEDIA_BUFFER_V1` | built and tested, **not** in the daily build yet (the owner has not decided) |
| [In-app network engine](#in-app-network-engine-experimental) | `OMNI_INPROC_NET_V1` (network role) | **experimental, off by default, not working yet** |

For each feature: what it does, why it exists, how to turn it off and where the code is.

**Where the code is.** Each feature is a patch script (`apply_*.py`) that edits the engine tree (see
[omni-title-build.md](omni-title-build.md)). These scripts belong to the GPU-pages stage-1 patch set. They are not in
this repository yet and will be added with the release that ships them. Each script's header comment is the full
technical description; this page is the plain version.

**Switches.** All switch files live in `/data/omni/` on the console. Omni reads most of them once, at start, so restart
Omni after changing one.

---

## In-app page engine

### What it does

A web browser normally runs each page in a separate **page process** (WebKit calls it the WebProcess). Until now Omni
did the same. The title started a second program, `omni-engine-child.elf`, through the ELF loader, and pages ran in
there (see [architecture.md](architecture.md#omni-the-browser)).

With the in-app page engine, the page engine runs **inside the title itself**, on the title's main thread. There is no
separate page process. The title and the page engine still talk over WebKit's normal message channel. Both ends of that
channel are now in the same program.

### Why

- **Less memory.** A separate engine process is a whole loaded copy of the engine. The in-app engine needs no spare
  copies waiting in reserve.
- **More headroom before the console hangs.** On the same 4K HDR YouTube video, the separate engine reached 6,221 to
  6,718 page tables. In-app stayed under 6,000, which is at least about 770 below the hang point (see
  [Page-table guard](#page-table-guard)).
- **Fewer moving parts.** There is no child process to start, wait for, or lose.

### How to turn it off

| Switch | Effect |
|---|---|
| `/app0/inproc-web.flag` (inside the title's folder) | turns it **on**; this is how the build ships it |
| `/data/omni/inproc-web.flag` | turns it **on** (for tests) |
| `/data/omni/inproc-web-off.flag` | turns it **off**: back to the separate page process. It beats the `/app0` switch but not the `/data/omni` one |

Why the `/app0` switch: Setup may only write inside its install roots, and `/data/omni/*.flag` is not one of them (see
[setup-internals.md](setup-internals.md#install-roots-and-why-they-cannot-widen)). So the package ships the switch in the
title's own folder, and the user can still turn it off from `/data/omni`.

### Where the code is

It takes five patches, because WebKit assumes each role has a process of its own:

| Script | Marker | Edits | What it fixes |
|---|---|---|---|
| `apply_inproc_net.py` | `OMNI_INPROC_NET_V1` | `process-launcher.cpp` (the launcher seam, both roles) | When WebKit asks to launch a page (or network) process, Omni starts that role's main function as a task on the title's main thread instead. The message channel stays the same. Reads the switches above. |
| `apply_inproc_spin.py` | `OMNI_INPROC_SPIN_V7` | `WebKit/Platform/IPC/Connection.cpp` | When one side waits for a reply, the title's main loop keeps serving. Messages for the waiting side are held until its wait ends, and are then delivered in order. Without this, the app froze, or a page's "load" message arrived before the page existed and was dropped. |
| `apply_inproc_aux.py` | `OMNI_INPROC_AUX_V1` | `WebKit/Shared/AuxiliaryProcess.cpp` | A child process locks itself out of making certain IDs that only the UI side may make. In-app, that lock also hit the UI side and crashed it (YouTube's service worker set it off). The lock is skipped in-app. |
| `apply_inproc_auxmain.py` | `OMNI_INPROC_AUXMAIN_V1` | `WebKit/Shared/AuxiliaryProcessMain.h` | Each role normally ends by running its own main loop forever. In-app, the title's loop already serves everything, so the role sets itself up and returns. Its main object is kept in static storage so it stays valid. |
| `apply_inproc_webenv.py` | `OMNI_INPROC_WEBENV_V1` | `engine/entry/OmniMain.cpp` | JavaScript's JIT settings are read once per process, and the title turned them off for itself. The in-app page engine was therefore interpreter-only, and YouTube rejected its playback tokens. This turns on the baseline and regexp JIT when in-app mode is on. |

All five do nothing unless in-app mode is on. They check an internal "in-app role is running" switch, which a separate
child process never sets, so the child build is unchanged.

### Change it safely

- Never let an in-app role stop the **main** run loop or exit. In-app, the main loop is the whole title.
- Never block the main thread waiting for a reply without the spin patch. The other end of the reply may need that
  same thread.
- Keep every change behind the in-app switch, so the separate-engine path stays exactly as it was and stays a working
  fallback.
- Test both modes: in-app, and with `inproc-web-off.flag`.

### Known limit

Seen in tests on 2026-11-26: when one video page closes and the next opens at once, the old page's hardware decoder
may not be released in time. The next video then plays with the software decoder. A later load gets hardware again.

---

## Page-table guard

### What it does

It watches one number, the console's **page-table count**, and steps in before the console hangs.

Page tables are the kernel's records of which memory belongs to which program. The console has a fixed pool of 8,192.
When more than about 6,770 are in use, the whole console hangs (the lowest hang seen was 6,771). Big pages, such as
4K YouTube, can push the count there.

### Why

Earlier fixes each closed one road to the hang: a gate on opening video decoders, a queue ceiling, a 1440p cap on
YouTube. The hang kept finding another road. So the guard now watches the number itself, whatever the cause.

### How it works

1. A background thread asks the engine starter for the count once a second. The UI thread never waits on it.
2. If the count is at or over the **line** (6,600 by default), the guard takes **one step every 6 seconds**, the
   gentlest first:
   1. **Discard a background tab.** Omni picks a tab with a loaded web page, silent tabs before tabs playing sound. It
      frees that tab's memory, and the tab loads its page again when you go back to it.
   2. **Shown tab, separate page process:** stop its page process. Omni's normal crash recovery reloads the page once,
      with a notice. A second stop on the same site within 5 minutes shows a panel instead, so it never loops. There
      are at least 20 s between stops.
   3. **Shown tab, in-app page engine** (there is no process to stop): run JavaScript garbage collection and lower
      YouTube's quality by one step (2160p to 1440p to 1080p to 720p ...). If the count is still over the line after
      two such steps, the tab shows a blank page for 4 s and then loads its page again, with a notice. This happens at
      most once a minute.
3. Once the count is 150 under the line, the steps reset.

Every action is written to the title's log as `OMNI PT WATCHDOG: ...` (see [troubleshooting.md](troubleshooting.md)).

The watchdog also installs YouTube's 1440p page cap from the title, where the browser shell actually runs. Under
pressure, it presets YouTube's own remembered quality to 1440p, so the first pick is already safe.

### How to turn it off

| Switch | Effect |
|---|---|
| `/data/omni/pt-watchdog-line.txt` | the line, from 6000 to 7200 (default 6600) |
| `/data/omni/pt-gentle-off.flag` | turns off the gentle steps; the first watchdog version (stop the shown tab only) runs instead |
| `/data/omni/pt-watchdog-off.flag` | turns the watchdog off completely. **Not recommended:** the console can hang |

### Where the code is

| Script | Marker | Edits |
|---|---|---|
| `apply_pt_watchdog.py` | `OMNI_PT_WATCHDOG_V1` | the title's `engine/entry` (the count thread, the stop step, the YouTube 1440p cap) |
| `apply_pt_gentle.py` | `OMNI_PT_GENTLE_V1` | the same files; needs the watchdog patch first |

### Change it safely

- Never make the UI thread wait for the count.
- Keep the step spacing (6 s between steps, 20 s between process stops). Memory takes a moment to come back after a
  step.
- Don't raise the default line closer to 6,770.

---

## Bigger media buffer

**Status: built and tested on the console, but not in the daily build yet. The owner has not decided.**

### What it does

It gives the title's video players one memory **budget** for buffering video ahead.

Before, the in-app video player kept only 32 MiB per stream, about 10 s of 4K HDR. Every small network dip could cause
a stall. Now:

| Player | Before | Now |
|---|---|---|
| Streaming video (YouTube and most sites) | 32 MiB per stream | the budget shared among the playing video streams (at least 32 MiB each); 64 MiB for audio |
| Plain video files | 16 MiB cache, 6 MiB ahead | half the budget; reads ahead 7/8 of it |
| Native HLS streams | 30 s / 48 MiB ahead | up to 20 minutes ahead, at most half the budget |

The default budget is **1024 MiB**.

It also works with the [page-table guard](#page-table-guard). Over the line, the guard first **halves the video
budget**, up to 3 times, before it touches any tab. The budget grows back one step a minute once the count is 300
under the line.

### Why

Small buffers stall on every network dip. A bigger buffer rides them out.

Note: the site's own player decides how far ahead it asks for. In tests, YouTube stopped at about 17 s ahead and
another site at about 30 s, whatever the budget. The budget no longer cuts them short, but 20 minutes ahead needs the
player itself to ask for that much.

### How to turn it off or change it

| Switch | Effect |
|---|---|
| `/data/omni/media-buffer-mb.txt` | the budget in MiB, from 64 to 4096 (default 1024) |
| `/data/omni/media-buffer-off.flag` | off: 64 MiB per stream, files and HLS as before |

The title's log shows `OMNI MEDIABUF: budget ...` once at start, `OMNI MEDIABUF: video N s ahead, ...` every 10 s while
video loads, and `OMNI PT PEAK: N page tables` at each new high of the page-table count.

### Where the code is

`apply_media_buffer.py`, marker `OMNI_MEDIA_BUFFER_V1`. It edits the title's `engine/` tree only; the separate engine
child is unchanged.

---

## In-app network engine (experimental)

**Experimental, off by default and not working yet: YouTube stalls.** It is documented here only so you know what the
switch is. Do not turn it on for normal use.

Besides pages, WebKit runs the network (downloads, cookies, storage) in another process. This experiment moves that
role into the title too, through the same launcher seam as the in-app page engine (`apply_inproc_net.py`).

| Switch | Effect |
|---|---|
| `/data/omni/inproc-net.flag` | turns it **on** (test only). Without it, the network stays in the separate engine child |
