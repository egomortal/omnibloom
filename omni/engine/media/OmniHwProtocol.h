// Wire protocol between the WebProcess decode client and the UI-process decode
// service. SPDX-License-Identifier: GPL-3.0-or-later
//
// Why two processes: Omni's WebProcess is started through the ELF loader and
// such processes get ~48 MiB of direct memory; the hardware decoder needs
// ~200-270 MB at 1080p. The UI process (big-app budget) owns the decoder.
//
// Transport: one stream socket per channel (fixed-size messages below) plus one
// shared-memory region per configured stream. The client copies both file
// descriptors out of the service process with omni_remote_dup() (Sony syscall
// 0x25b), the same mechanism Omni's launcher uses; Unix socket files are not
// available to ELF-loader processes.
//
// Rendezvous directory (OMNI_HW_DIR, default <launch dir>/../hwdec):
//   service            text: "omni-hw 1\npid P\nchannel I GEN FD\n..." (atomic rename)
//   claim-I            created O_EXCL by a client before using channel I
// Ordering on the socket is the synchronisation: a Flushed reply follows every
// Frame sent before it, so the client discards frames that precede it.
#pragma once
#include <cstdint>

namespace OmniMedia::Hw::Wire {

constexpr uint32_t magic = 0x4f4d4857; // "OMHW"
constexpr uint32_t version = 3;   // OMNI_HOLEPUNCH_V5: input ring, cumulative Consumed (V4: 2, V1-V3: 1)
constexpr uint32_t maxChannels = 4;
// OMNI_HOLEPUNCH_V5: the input region is one ring of variable-size access units (V4: 12 fixed
// 1.25 MB slots). While the shell paces a video the client keeps up to ~3.5 s of access units
// in flight, so the service keeps decoding through a 2-3 s stall of the WebProcess main thread;
// otherwise at most inputInFlightV4 (V4's depth). An access unit may be as large as the
// decoder's input buffer (OmniHwBackend: 8 MiB), e.g. a 4K VP9 keyframe of a WebM packet.
constexpr uint32_t inputRingBytes = 24u << 20;
constexpr uint32_t inputMaxAu = 8u << 20;
constexpr uint32_t inputMaxInFlight = 1024;   // access units (submits not yet Consumed)
constexpr uint32_t inputInFlightV4 = 12;
constexpr uint32_t outputSlots = 6;

enum class Type : uint32_t {
    // client -> service
    Hello = 1, Configure, ShmMapped, Submit, Release, Drain, Flush, Close,
    Present,                                                  // OMNI_HOLEPUNCH_V1
    HoleClock,                                                // OMNI_HOLEPUNCH_V4
    // service -> client
    HelloAck = 100, Configured, Consumed, Frame, Drained, Flushed, Error,
    HoleState,                                                // OMNI_HOLEPUNCH_V1
    HoleShown,                                                // OMNI_HOLEPUNCH_V2
    HolePacing,                                               // OMNI_HOLEPUNCH_V4
};

constexpr uint32_t Hidden = 1, NonDisplaying = 2, KeyFrame = 4;   // Submit flags
constexpr uint32_t FrameNonDisplaying = 1;                        // Frame flags
constexpr uint32_t FrameSnapshot = 2;                             // OMNI_HOLEPUNCH_V4
constexpr uint32_t clockPaced = 1, clockPlaying = 2, clockSnapshot = 4, clockDiscard = 8, clockLimit = 16; // HoleClock.a (V4)
constexpr uint32_t presentKeep = 0xfffffffeu, presentHide = 0xffffffffu; // Present.a (OMNI_HOLEPUNCH_V1)
constexpr int holeMaxSide = 4096;                       // Present rect limits; a bigger
constexpr int64_t holeMaxPixels = int64_t(3840) * 2160; // bounded native 4K SDR plane (31.64 MiB RGBA)

struct Message {
    uint32_t magic = Wire::magic;
    Type type = Type::Hello;
    int32_t status = 0;       // 0 ok, else rc
    uint32_t a = 0, b = 0, c = 0, d = 0, e = 0, f = 0, g = 0;
    int64_t pts = 0;
    char text[48] = {};       // failing stage / short detail, NUL terminated
};
static_assert(sizeof(Message) == 96, "fixed-size wire message");

// Field use per type (unlisted fields are zero):
//  Hello       a=client pid, b=channel generation, c=protocol version
//  HelloAck    status
//  Configure   a=codec(0 H264,1 HEVC,2 VP9) b=profile c=bitDepth d=width e=height
//              f=colour (OMNI_HOLEPUNCH_COLOUR_V1, OmniHwBitstream.h colourWord): 0x100 set,
//              low byte = H.273 matrix the conversions use, 0x200 = full range
//  Configured  status, text=stage; a=shm fd (in the service), b=shm size,
//              c=input offset, d=slot offset, e=slot size, f=slot count
//  ShmMapped   (client dup'ed + mapped the shm; service closes its fd copy)
//  Submit      a=ring offset of the access unit (input region), b=size, c=SubmitFlags, pts
//              (OMNI_HOLEPUNCH_V5; a + b <= inputRingBytes, b <= inputMaxAu)
//  Consumed    a=Submits consumed so far, counted from the stream's Configure or last Flushed
//              (OMNI_HOLEPUNCH_V5: cumulative and coalesced, sent without waiting when the
//              socket has room; the service consumes Submits in the order they were sent, so
//              the client frees its ring oldest first)
//  Frame       a=output slot, b=width, c=coded height, d=pitch bytes,
//              e=bit depth, f=FrameFlags, pts
//  Release     a=output slot
//  Drain/Drained, Flush/Flushed, Close: no fields
//  Error       status=rc, text=stage; the stream must fall back to software
//  Present     OMNI_HOLEPUNCH_V1 (video shown under the page by the shell):
//              a=output slot to show, presentKeep (claim the plane / move it, no
//              new picture) or presentHide (give the plane back);
//              b,c,d,e = video rect x,y,w,h in view pixels (int32 bit patterns);
//              pts. Present(slot) hands the slot to the service: the client never
//              sends Release for it. The service thread reads the slot once,
//              converts it, and frees it before it handles the next message.
//  HoleState   status 0 = the shell shows this channel's video, else refused;
//              text = reason. Sent when the answer for the channel changes.
//  HoleShown   OMNI_HOLEPUNCH_V2: a=pictures of this channel converted for the
//              shell so far, pts = the last one. One per accepted Present(slot):
//              the player's proof that the shell really has its frames.
//  HoleState   OMNI_HOLEPUNCH_V4: a=1 when the service can also pace this channel's frames.
//  HoleClock   OMNI_HOLEPUNCH_V4 (client -> service), the player's playback clock:
//              a=clock flags: clockPaced (the service queues this channel's decoded frames
//              and shows each one at its time; no Frame/slot reaches the client), clockPlaying,
//              clockSnapshot (send the frame on screen once as a Frame with FrameSnapshot),
//              clockDiscard (drop frames before text[0..7]), clockLimit (the clock stops at
//              text[8..15]); b=generation (changes after every seek/flush; frames queued
//              before a Flush are dropped and the clock is invalid until a new generation);
//              c=rate * 65536; d,e=wall-clock anchor in microseconds (CLOCK_MONOTONIC, low and
//              high word); f,g=time base of the frame pts; pts=position at the anchor, us.
//              text[0..7] and text[8..15] are int64 microseconds (memcpy), not text.
//              V136 diagnostic text[16..47]: eight int32 microsecond offsets from the send anchor
//              (INT32_MIN missing): release, fprintf end, fflush end, hold return, pre-audio-ring,
//              pump begin/end, clock construction. Measurement only; clock semantics unchanged.
//              Sent when it changes and every 250 ms while pacing.
//  HolePacing  OMNI_HOLEPUNCH_V4 (service -> client): status 0 pacing, -1 refused/stopped
//              (text = reason); a=frames shown by the shell, b=dropped (never shown),
//              c=late (shown a vblank or more after they were due), d=frames waiting,
//              e=frames decoded while pacing (queued or discarded), f=queue capacity;
//              pts=media us of the frame on
//              screen. When pacing starts or stops, when shown changes (at most every 100 ms)
//              and every 250 ms while pacing: the player's proof that the shell has its frames.
//  Frame       OMNI_HOLEPUNCH_V4: f=FrameSnapshot: a copy of the frame on screen (for canvas
//              readers and the paint path after the hole); released as any other slot.
// OMNI_HOLEPUNCH_V5: HolePacing f = queue capacity in frames (by memory budget, not a fixed 8).
// OMNI_HOLEPUNCH_V5_REV2: HolePacing g = decoded media queued ahead of the clock, ms.
// V133 HolePacing text[16..19]=uint32 readiness bits (1 paced, 2 presenter awake, 4 valid handoff),
// text[20..23]=uint32 clock generation. The reason at text[0] remains a terminated string.
// Bits 2/4 are acknowledged together by the presenter before flipping a valid handed-off frame.
// OMNI_HOLEPUNCH_V2: neither side blocks on a full socket for long. The client waits
// at most 500 ms per message, then falls back to software decoding; rect-only Presents
// never wait (dropped, sent again next tick). The service waits at most 200 ms, then
// closes that channel.

}
