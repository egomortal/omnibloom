# Separate-track MSE smoke fixture

Local preparation only; no production feature flag, media backend, or PS5
deployment changes. Current Omni reports MediaSource absent; this page will
report **UNSUPPORTED**, never PASS, in that state.

Generate with `python3 generate.py` on a host with FFmpeg/libx264 and ffprobe.
The script creates four seconds of original 320x180 testsrc2 video and 440 Hz
stereo sine audio, separately fragmented into MP4 tracks. No downloaded media.
Generated files total approximately 210 KB. `generated/manifest.json` records
MIME codec strings, per-file SHA256/size, FFmpeg version and ffprobe verification.
The AVC codec string is extracted from the actual init segment, not assumed.

Serve this directory through a loopback HTTP server, open `index.html` in a
browser, and press Run. The page tests sequential initialization/media appends,
rejection of concurrent appends, buffered-range removal, endOfStream, seeking,
muted decoded playback progress and pause/detach/object-URL cleanup. Operations
have finite waits. SourceBuffer errors also take the cleanup path. The machine
readable result is `window.omniMSEResult` with READY/RUNNING/UNSUPPORTED/PASS/FAIL.

The timer limits bound waiting by this harness, not OS/browser decoder calls.
This is a narrow smoke test, **not** the W3C conformance suite. It does not test
adaptive bitrate switching, quota eviction, malformed-bitstream resilience,
audible output, synchronization quality, long streams, DRM or YouTube itself.

Validation on 2026-10-18: generation and ffprobe checks passed for both tracks.
`node harness-test.cjs` checks missing-MSE classification and HTTP-error cleanup
using an explicitly mocked DOM. Browser execution could not be performed: the
computer-use browser inventory is empty and the in-app browser unavailable.
Do not treat mock tests or successful fixture generation as actual MSE playback.

The independent host framer test reads the generated video init and first two
media segments. From WSL Ubuntu 24.04, build and run it with sanitizers:

```sh
root="/path/to/downloads/"
ulimit -c 0
c++ -std=c++20 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined \
  -fno-omit-frame-pointer "$root/engine/media/OmniMP4SegmentBuffer.cpp" \
  "$root/engine/selftest/mse/segment-buffer-test.cpp" -o /tmp/segment-buffer-test
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  /tmp/segment-buffer-test "$root/engine/selftest/mse/generated"
```

The host test covers every two-chunk split of real fixture bytes, byte-at-a-time
input, back-to-back output, quota and 64-bit extended-size rejection, finish
truncation, ordering, reinitialization, reset, and malformed boxes. The parent
agent ran this command successfully with ASan/UBSan after correcting a test
expectation: a complete new initialization segment is permitted while idle.
The lower-cost test agent's restricted WSL launch had initially been denied;
that is superseded by this successful host run. Core dumps are disabled.

`OmniMP4SegmentBuffer` is framing only, not an MSE backend or semantic MP4
validator. It emits ftyp+moov initialization and moof+mdat fragments, accepts
partial box headers/payloads, and rejects unsupported/open-ended top-level boxes.
It limits buffered logical bytes to 8 MiB and initialization to 1 MiB. Vector
capacity, emitted caller-owned buffers and downstream demux/decoder allocations
are additional memory; callers must budget them separately. It does not validate
tracks, timestamps, codec bytes or encryption. Reset releases its stored buffers.

All chart/tone content is generated locally. Existing FFmpeg tooling is invoked,
not redistributed by this fixture directory. Keep its installed license notices.

## Independent finite-fragment demux prerequisite

`engine/media/OmniMP4Demuxer.{h,cpp}` accepts already-fetched init bytes and one
complete moof/mdat fragment. It uses FFmpeg custom memory IO only, a mov demuxer
allowlist, H.264/AAC codec allowlist, no protocols, denied external IO, at most
two tracks, 8 MiB input/output ceilings, 64 KiB codec metadata per track, 4096
packets, and a three-second interrupt deadline. Requested limits can only lower
hard maxima. The interrupt is cooperative, not hard preemption of every FFmpeg
operation. FFmpeg metadata probing may internally decode a small sample, with
one decoder thread, pixel/sample caps, and the same deadline. Linked system
FFmpeg libraries themselves are not sanitizer-rebuilt.

Output carries original track IDs, codec metadata, packet bytes and integer
PTS/DTS/duration with rational time bases. AAC priming (`SKIP_SAMPLES`) is
preserved with a finite-fragment correction: MOV reapplies the initialization
edit-list leading skip on each reopen. For validated single, non-empty,
unit-rate edit lists, leading skip is limited to samples before presentation
time zero; later fragment leading skip becomes zero while trailing discard
and reason bytes remain intact. Complex edit-list priming is rejected. This
matches [MOV's start-pad initialization](https://github.com/FFmpeg/FFmpeg/blob/n6.1/libavformat/mov.c).
Persistent decoder tests now produce 192512 stereo PCM frames across all five
AAC fragments, matching independent FFmpeg decoding of the concatenated stream.
The prior repeated trim lost 4096 samples; a regression checks later-fragment
leading skips and rejects an unsupported multi-edit initialization.

FFmpeg 6.1.1 reports the first generated AAC packet at DTS -1024 with
missing duration. The adapter first asks FFmpeg's documented
`av_get_audio_frame_duration2(codecpar, packetSize)` for codec sample duration
after bounded metadata probing. A positive result is converted exactly into
track ticks only if the rational conversion has no remainder; no AAC sample
constant is guessed. `durationSource=AudioCodecSamples` preserves the fact that
the packet duration was absent and supplied by codec metadata. This handles
both the generated first AAC packet and its single-packet tail. Encoded frame
duration does not independently establish presentation trimming/gaplessness.

If codec duration is still unavailable, a later same-track DTS can supply a
clearly marked fallback (`durationSource=NextTrackDTS`,
`durationFromNextDTS=true`). This fallback is an inference, not a universal
guarantee of sample duration. A final missing duration without codec evidence
is rejected. Missing PTS/DTS are always rejected. See the
[FFmpeg audio duration API](https://ffmpeg.org/doxygen/6.1/codec__par_8h.html).

Encrypted sample-entry tags, top-level pssh and packet encryption side data are
rejected; this is not a comprehensive protected-MP4 semantic validator. No DRM
support exists. Initial container framing is checked, but full semantic parsing
is delegated to FFmpeg. Track IDs must later be scoped per SourceBuffer: separate
audio/video init segments can each legitimately use ID 1.

Run `bash test-demux.sh /path/to/small-output-directory`. Host ASan/UBSan tests
passed for all four video and five audio fragments, exact cross-fragment DTS,
120 video packets and 189 AAC packets total, priming metadata, codec-derived
first/tail durations, malformed/truncated framing and all budget knobs. The
complete-stream ffprobe output independently matches the final AAC packet DTS
191488 and duration 1024 at time base 1/48000. All generated fragments now demux;
this is still not playback or semantic MSE conformance.
Evidence: workspace `outputs/mse-demux/host-test.txt`. These results cover the
finite demux prerequisite only. A separate experimental SourceBuffer/player
integration is now being compiled, with no linked candidate or console MSE pass
at the current checkpoint. See
[the current MSE handoff](../../../docs/MSE-EXPERIMENT-HANDOFF.md). Host demux
results do not establish browser SourceBuffer conformance or YouTube playback.
