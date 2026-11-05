// Hardware decode service: runs in Omni's UI (big-app) process and decodes for
// WebProcess clients over OmniHwProtocol. SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <string>

namespace OmniMedia::Hw {
// UI diagnostics share the bounded background writer; no file flush on the UI thread.
void shellLog(const char* message);

// Initialise the decoder module and start the service thread. Idempotent.
// Call early in the UI process, only when flagEnabled(). False + detail when
// hardware decode is unavailable; clients then use software decoding.
bool serviceStart(std::string& detail);
// Stops the thread and removes the rendezvous file (tests and shutdown).
void serviceStop();
// Before the app exits (or from the crash handler with fromSignal): stops the
// thread (waiting at most waitMs), deletes every decoder and releases the
// compute queue. Runs once; later calls return true.
bool serviceShutdownForExit(int waitMs, bool fromSignal);

// OMNI_HOLEPUNCH_V1: the shell's video plane. One hardware-decoded video can be shown
// under the page instead of being painted into it: the WebProcess leaves a transparent
// hole where the video is and sends Present(slot, rect); the service thread converts the
// slot (one swscale pass, to the on-screen size) and the shell blends the page over it.
// All four functions are for the shell's main thread.
//
// Once, after the canvas exists: the canvas pixel layout (32-bit, R/G/B shifts). False
// (and every video keeps the paint path) for other layouts, a build without swscale,
// or when /data/omni/holepunch-disabled.flag exists.
bool holePunchAttach(int bytesPerPixel, int redShift, int greenShift, int blueShift);
// True while a video uses the plane. The page buffer must then be cleared to transparent
// before WKPagePaint, which draws the page over the buffer's old contents.
bool holePunchActive();
// OMNI_FAST_PAGE_V1: the page view is painted at 1/scale of the canvas; video rects arrive in view pixels.
void holePunchSetViewScale(double canvasPerViewPixel);
// True when the plane changed since the last holePunchCompose (new picture, moved,
// shown or hidden): the shell should draw again.
bool holePunchPoll();
// Call right after the page was blitted onto the canvas at (pageX, pageY). Redraws the
// part of the page area the video covers: video below, page (premultiplied BGRA, as
// WKPagePaint writes it) blended over it. No-op while holePunchActive() is false.
void holePunchCompose(uint8_t* canvas, int canvasPitch, int canvasWidth, int canvasHeight,
    int pageX, int pageY, const uint8_t* page, int pagePitch, int pageWidth, int pageHeight);

// OMNI_HOLEPUNCH_V4: frame pacing. A paced video's frames are queued here with their media
// times and shown by the player's clock at the vblank each composed canvas reaches. Call
// holePunchVblank() from the presenter thread right after every flip returns (REQ-4): the
// flip times give the vblank phase; without them it is estimated from the 60 Hz cadence.
// holePunchPoll() also turns true when a queued frame becomes due.
void holePunchVblank(bool successful = true);
struct HolePacingStats {
    bool pacing = false, clockValid = false, vblankReported = false;
    uint64_t shown = 0, dropped = 0, late = 0;
    unsigned waiting = 0;                  // converted, not shown yet
    int64_t currentMediaUs = INT64_MIN;    // media time of the frame on screen (INT64_MIN: none / not paced)
    int64_t clockUs = 0;                   // the playback clock now
};
// Diagnostics and tests (shell main thread).
HolePacingStats holePunchPacingStats();
// Production HUD: sampled from existing state; never starts diagnostics or performs I/O.
struct PlaybackStats {
    uint64_t completed = 0, repeats = 0, drops = 0, decoderErrors = 0;
    int64_t completionUs = 0;
    int width = 0, height = 0, codec = -1;
    bool active = false, decoderFailed = false;
};
// Bounded service-thread metadata sample; freshness is publication time, not completionUs.
struct PlaybackMetadata {
    int width=0, height=0, codec=-1;
    bool active=false, decoderFailed=false, fresh=false;
};
void playbackStatsRequest();
PlaybackMetadata playbackMetadata();
void playbackStatsEnable(bool);
PlaybackStats playbackStats();


// OMNI_HOLEPUNCH_V7_REFLIP (presenter thread): while the shell's main thread is busy (no tick for
// 25 ms or more), the presenter shows the newest due video picture itself, on the last presented
// frame. holePunchReflipWaitMs(): how long the presenter may wait for the next canvas before it
// asks again (just before the next vblank); -1: wait for a canvas as before (no paced video
// playing, or V7 off: /data/omni/holepunch-v7-disabled.flag). holePunchReflip(): with the
// presenter's own buffer (the last presented frame, owned by the presenter meanwhile): true when
// it put a newer picture into the video's pixels there, which the presenter then flips. Only the
// pixels the last compose took from the video change (and translucent page pixels over it are
// blended again); the page, and anything the shell drew over the video after holePunchCompose,
// stay as they were.
int holePunchReflipWaitMs();
bool holePunchReflip(uint8_t* frame, int pitch, int width, int height);
// OMNI_HOLEPUNCH_V7_REV2 (shell main thread, patch-shell-holepunch-v7-rev2.py): the finished canvas
// is about to become the presenter's frame (omniPresentFrame, under its lock, the presenter idle):
// which video pixels it still holds. A re-flip needs it (it no longer reads the frame). V7 off: nothing.
void holePunchPrepareHandOff(const uint8_t* canvas, int pitch, int width, int height);
void holePunchHandOff(const uint8_t* canvas, int pitch, int width, int height);
// OMNI_HOLEPUNCH_V7_REV2 (any shell thread): one complete log line (with its newline). V7 on: queued
// for the engine's log writer thread, never waited for; off: fputs + fflush here (v90).
void holePunchLogLine(const char* line);
// OMNI_HOLEPUNCH_V8_CADENCE (presenter thread, patch-shell-holepunch-v8.py): about to flip the canvas the
// main thread handed off (screen->pixels): the picture due at the vblank this flip reaches goes into
// the video's pixels first. V7 or V8 off: nothing.
void holePunchBeforeFlip(uint8_t* frame, int pitch, int width, int height);
// OMNI_HOLEPUNCH_V7_REFLIP (shell main thread, patch-shell-stalltrace-v7.py): what the main thread
// is doing from now on, for the stall log ("pacing V7 stall:"): 0 outside tick() (the run loop:
// WebKit's IPC and callbacks, other timers), 1 tick() itself, 2 uBlock (omniBlockerPoll), 3 input
// (SDL events), 4 the page copy (WKPagePaint), 5 draw() (compose, shell, present).
void holePunchShellPhase(int phase);

// OMNI_PERF_B_V2 (shell main thread): true while the presenter puts every new picture of a paced video that covers
// the whole canvas into the frames by itself (V8 before-flip / re-flips, the frame on screen described by its mask).
// The shell then needs no draw for a picture, and nothing it hides in fullscreen (spinner, progress bar) needs one;
// holePunchPoll() still asks for the draws the video needs (rect, owner, poster, a stale mask). Turns false when the
// plane is released, the video is resized or another owner shows, until the next hand-off. Kill switch:
// /data/omni/perf-b-v2-disabled.flag (always false).
bool holePunchPresenterOwnsVideo();

// Diagnostic-only bounded memory trace; no scheduling or rendering policy changes.
void diagnosticTraceStart();
void diagnosticTrace(int64_t event, int64_t a=0, int64_t b=0, int64_t c=0, int64_t d=0);
void diagnosticTraceDump();

// OMNI_TAB_MEDIA_RELEASE_V1 (any shell thread): hardware decoders open now (channels with a stream)
// and, in sharedBytes when given, the shared memory their slots use. Diagnostics (tab memory log).
int openDecoderCount(size_t* sharedBytes = nullptr);
}
