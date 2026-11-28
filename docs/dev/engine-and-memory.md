# In-app engine, memory guard and media buffer

This page covers Omni's newest work on how pages run and how memory is kept safe:

| Feature | Marker | Status (2026-11-28) |
|---|---|---|
| [In-app page engine](#in-app-page-engine) | `OMNI_INPROC_NET_V1` and the `OMNI_INPROC_*` patches | **on by default** in the owner's daily build since 2026-11-26 |
| [Page-table guard](#page-table-guard) | `OMNI_PT_WATCHDOG_V1`, `OMNI_PT_GENTLE_V1` | **on** in the daily build |
| [Bigger media buffer](#bigger-media-buffer) | `OMNI_MEDIA_BUFFER_V1` | built and measured on the console |
| [In-app network engine](#in-app-network-engine-experimental) | `OMNI_INPROC_NET_V1` (network role) | **experimental, off by default** |

Start with [The two page-table pools](#the-two-page-table-pools): it explains why these features matter.

For each feature: what it does, why it exists, how to turn it off and where the code is.

**Where the code is.** Each feature is a patch script (`apply_*.py`) that edits the engine tree (see
[omni-title-build.md](omni-title-build.md)). These scripts belong to the GPU-pages stage-1 patch set. They are not in
this repository yet and will be added with the release that ships them. Each script's header comment is the full
technical description; this page is the plain version.

**Switches.** All switch files live in `/data/omni/` on the console. Omni reads most of them once, at start, so restart
Omni after changing one.

---

## The two page-table pools

Page tables are the kernel's records of which memory belongs to which program. Every program needs some, and big pages
(4K video, heavy sites) need more. All numbers below were **measured on the console** (2026-11-27 and 28).

The PS5 has **two kinds** of page-table pools:

| Pool | Size | Who uses it | What happens when it fills |
|---|---|---|---|
| **An app's own pool** | 16,384 page tables (64 MB), one pool per app | each app launched normally from the home screen. Omni is one. | that app runs out of room; the console keeps going |
| **The system pool** | 8,192 page tables, shared | the PS5's own processes, and helper programs started outside an app: homebrew payloads, and Omni's separate engine processes | **the whole console freezes**, at about 6,770 in use |

What we measured during 4K YouTube:

- **Omni's own pool:** from 834 to 2,152 of 16,384 (13%).
- **The system pool:** flat, at about 5,010 of 8,192.

So the memory Omni uses for itself never touches the pool that freezes the console. What Omni adds to the system pool
comes from its **helper processes**: the separate page engine and network engine, when they run as their own programs.

This is why the [in-app page engine](#in-app-page-engine) made such a difference. With the page engine inside Omni, its
memory moved out of the system pool and into Omni's own pool, which has plenty of room.

### Things that do not work

So nobody spends time on them again:

- **Raising the pool in the app's settings file** (`kernel.cpuPageTableSize` in the title's parameters) does not change
  the system pool. Omni's own pool already has plenty of room, so there is nothing to gain there either.
- **Making the system pool bigger** would mean patching the PS5's kernel, which the hypervisor protects.

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
- **The console stays far from freezing.** A separate page engine is a helper process, so its page tables come from
  the shared system pool, the one that freezes the console when it fills (see
  [The two page-table pools](#the-two-page-table-pools)). In-app, the page engine's memory counts against Omni's own,
  much larger pool instead. Measured on the same 4K HDR YouTube video: with the separate engine, the system pool reached
  6,221 to 6,718, close to the freeze point of about 6,770. In-app, normal 4K use sits about 1,200 below it.
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

It watches one number, the page-table count of the console's **system pool**, and steps in before the console
freezes.

The system pool holds 8,192 page tables and is shared by the PS5's own processes and by helper programs started
outside an app (see [The two page-table pools](#the-two-page-table-pools)). When more than about 6,770 are in use,
the whole console freezes (the lowest freeze seen was at 6,771). Omni's own pool is separate, and much larger, so the
guard does not need to watch it.

With the in-app page engine, normal 4K use sits about 1,200 below the freeze point (measured), so the guard rarely
has to act. It is still the safety net for heavy pages, and for the separate engine, which uses the system pool.

### Why

Earlier fixes each closed one road to the freeze: a gate on opening video decoders, a queue ceiling, a 1440p cap on
YouTube. The freeze kept finding another road. So the guard now watches the number itself, whatever the cause.

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
| `/data/omni/pt-watchdog-off.flag` | turns the watchdog off completely. **Not recommended:** the console can freeze |

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

**Status: built and measured on the console.**

### What it does

It gives the title's video players one memory **budget** for buffering video ahead: up to 1 GB by default, and up to
20 minutes ahead where Omni does the downloading itself (plain video files and HLS streams Omni plays itself).

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

What we measured:

- **Where Omni downloads:** an HLS stream was fetched 20 minutes ahead within 30 seconds, with no extra page tables.
- **Sites with their own player** (YouTube included) still choose how far ahead they fetch. The budget no longer cuts
  them short, but it cannot make them ask for more. YouTube fetches about 17 seconds ahead at 4K. YouTube's servers
  set this, and it is the same in every browser. Another site stopped at about 30 seconds.

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

**Experimental and off by default.** It is documented here only so you know what the switch is. Do not turn it on for
normal use. In-app, the network engine shares Omni's main thread with the rest of the browser, so it can drop video
frames during heavy video.

Besides pages, WebKit runs the network (downloads, cookies, storage) in another process. This experiment moves that
role into the title too, through the same launcher seam as the in-app page engine (`apply_inproc_net.py`).

| Switch | Effect |
|---|---|
| `/data/omni/inproc-net.flag` | turns it **on** (test only). Without it, the network stays in the separate engine child |
