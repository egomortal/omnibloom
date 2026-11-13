# GPU page drawing ("layers") on the PS5: what broke and how we found it

*Research notes from Omnibloom's experimental GPU page drawing. Written for anyone porting WebKit, Mesa or another
GPU-heavy program to a jailbroken PS5. Status: experimental and off by default; shipped as an opt-in in v0.5.1.*

## The short version

Omnibloom normally draws web pages on the CPU. "Layers" is an experiment that draws them on the PS5's GPU instead,
using Mesa (Zink on top of RADV) inside the browser's page process, talking to the GPU through the main app.

Getting it to *work* was the easy part. Getting it to work *as well as the CPU path* took a night of measuring. The
problems we found were mostly not where we expected, and several of them apply to any similar port:

1. **A small helper function slowed startup by 5–9 seconds** and broke other code in the same process.
2. **The PS5's WebKit compositor could stop delivering animation frames to the page** (`requestAnimationFrame`),
   which made YouTube stop loading video after a while.
3. **Mesa's shader cache silently does nothing** in this kind of build.
4. **Without pacing, the compositor ran at 85–230 frames a second** and starved video of GPU time.
5. **Reading the page back from the GPU in many small pieces jammed the GPU queue** shared with video.
6. **The default GPU memory budget (128 MiB) was too small**, which crashed the page process.

Each one is explained below in plain terms, with what fixed it.

---

## 1. The `dladdr` helper that slowed everything down

**What it is.** `dladdr()` is a standard function a program calls to ask "which file and which function does this
address belong to?". Mesa uses it once, while starting up, to build a cache ID from the driver's file name and
modification time. On the PS5 that file name is a bare relative name that can't be looked up, so Mesa refuses to
start ("cannot generate UUID").

**What we did first.** We replaced `dladdr()` for the whole process with a version that, when the real file name
couldn't be looked up, substituted a path that could.

**What went wrong.** Our replacement ran on *every* `dladdr()` call in the page process, for its whole life, and:

- checked up to four file paths each time (several system calls per call), and
- wiped the rest of the answer (load address, function name), keeping only the substituted file name.

Other code in the same process uses `dladdr()` too. With the helper on, the page process took **5–9 seconds longer
to start** (most of it inside font loading), and Omni's video watchdog logged an image base of 0 instead of the real
one.

**How we found it.** Not by reading code. We turned features on and off one at a time:

| Test | Start of video | Result |
|---|---|---|
| Layers off | 13–15 s | plays fully |
| Only the main app's GPU side on | 14.6 s | plays fully |
| Page-process helpers on, GPU drawing off | 21–22 s | stalls |
| Same, with the `dladdr` helper off | 14.4 s | plays fully |

**Fix.** The replacement now only acts during the ~0.3 seconds when Mesa starts up, and only changes the file name,
leaving the rest of the answer intact. Startup went back to normal: page loading begins after 0.9 s (was 8–17 s), and
video starts in 14.6–20 s.

**Lesson for other ports.** If you wrap a libc function with `--wrap`, it applies to the *whole* program, not just
the library you were fixing. Scope it as narrowly as you can, in time and in what it touches.

## 2. Animation frames stop reaching the page

**Symptom.** With GPU drawing on, YouTube often stopped loading video after 12–60 seconds. The video element froze
"waiting for data" while the GPU kept drawing normally.

**What we measured.** A test script inside the page counts its own animation-frame callbacks. With layers off it
reached 1,300–1,800 over a run. With layers on it stopped at 65–80 *in every run*, including the runs that happened
to play fine. YouTube's player uses those callbacks to decide when to fetch more video.

**Why.** This is in the PlayStation port of WebKit's threaded compositor, a code path the normal CPU-drawn browser
never uses:

- When the page hands a new frame to the compositor, it sets a "waiting for the renderer" flag.
- The flag is cleared only when the compositor sends a "frame done, you may draw again" notification back.
- The compositor sends that notification only if the page asked for an animation frame, or if it saw layer changes
  at the moment it drew.
- If neither was true at that moment, the notification is skipped, the flag stays set **forever**, and every later
  request to update the page is silently dropped.

**Fix.** Always send the notification after a composited frame. It costs one small message per frame.

**What we got wrong first.** Some runs still stopped at about the one-minute mark after this fix. That turned out
to be a different problem: the test build lacked Omni's YouTube token guard (added in v0.5.0), so YouTube cut the
stream off when it rejected the player's token. Once the test build carried the guard, the stops went away. Two
causes with the same symptom looked like one, so check that your control and your test differ in one thing only.

**Lesson.** If you enable a rendering path a port has never shipped with, expect latent bugs in it, and measure
whether page-side callbacks still run, not just whether pixels appear.

## 3. Mesa's shader cache does nothing here

We turned on Mesa's on-disk shader cache to avoid compiling the same shaders on every launch. The cache folder
stayed empty after several launches. Mesa only enables its disk cache when it can identify its own build (a build
ID or a usable file timestamp), and this static build has neither, so it quietly skips the cache. The first full
page draw still takes about 1.4–2.9 seconds of shader compiling.

## 4. Pace the compositor

Our first version told the compositor "frame done" immediately after each frame. With nothing holding it back, the
compositor drew 85–230 frames a second, each including a GPU read-back, on the same GPU queue the video player uses.
Waiting out the rest of each 1/60-second interval fixed that.

## 5. Read back in one piece

To send a GPU-drawn page to the screen we read it back into memory. Reading only the changed tiles sounds efficient,
but doing it as one read per rectangle meant up to 48 small GPU jobs per frame, and they jammed the queue shared with
video (video dropped to under 2 fps). Comparing frames on the GPU in 16×16-pixel cells and then doing **one** read of
the bounding box per frame brought video back to a steady 59.94 fps.

## 6. Give the GPU enough memory

The page process gets GPU memory from the main app, with a default budget of 128 MiB. A 1080p page with its
textures needs more; allocations failed and the page process crashed. 384 MiB was enough in testing (adjustable with
a settings file).

---

## How we measured (reusable techniques)

- **One change per test, against a control in the same session.** Network caching alone changed video start by
  7 seconds between sessions, so every comparison ran the "off" version back-to-back with the "on" version.
- **A poor man's sampling profiler.** A helper thread sends the main thread a signal every 500 ms; the signal
  handler writes out the instruction pointer and the code addresses found on the stack. Symbolized afterwards
  against the unstripped binary, this showed exactly where startup time went (font loading inside a slow system call
  path).
- **A heartbeat.** Every 5 seconds the page process logs how many frames the compositor started and finished, how
  long the main thread takes to answer a ping, and the compositor's internal counters. That ruled out several wrong
  theories quickly (main-thread hang, memory pressure, the compositor stopping).
- **Monotonic timestamps everywhere.** All logs from the app, the page process and the video system use the same
  clock, so events can be lined up across processes.

## Status

| Problem | Status |
|---|---|
| Slow startup (`dladdr` helper) | Fixed and confirmed |
| Compositor not paced | Fixed |
| One read-back per frame | Fixed (video 59.94 fps) |
| GPU memory budget | Fixed (384 MiB) |
| Animation frames stop (YouTube stall) | Fixed and confirmed |
| Shader cache | Not possible in this build; first draw still costs ~1.5–3 s |

### Final console check (November 13, 2026)

Three back-to-back runs on the same console, about 4.5 minutes of HDR YouTube each:

| Run | Video started | Played (test length) | Frame rate | Result |
|---|---|---|---|---|
| Layers off | 14.35 s | 274 s (286 s) | 59.94 fps | pass |
| Layers on | 14.47 s | 251 s (286 s) | 59.94 fps | pass |
| Layers on | 12.88 s | 276 s (287 s) | 59.94 fps | pass |

Layers now matches the CPU path for video. It ships in v0.5.1 **off by default**, as an opt-in
(`/data/omni/gpu-pages-stage1.flag`), because it isn't faster yet: the next step is drawing the page itself on
the GPU (Skia GPU rasterisation), which is where the speed-up should come from.
