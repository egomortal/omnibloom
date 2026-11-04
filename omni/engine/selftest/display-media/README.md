# Isolated display chart

This is local diagnostic preparation, not a production browser change. The
chart and digit glyphs are original project code; there are no downloaded media
assets. It links the existing isolated SDL static library, retaining SDL's zlib
license and existing alteration notices.

Run in WSL from any directory:

```sh
bash engine/selftest/display-media/build.sh /path/to/outputs/display-media
```

The host ASan/UBSan check validates three sizes, edge pixels and pitched-buffer
padding. The native executable renders 2160p for two seconds, closes SDL,
reinitializes 1080p for two seconds and uses the foreground system exit route.
It writes `/data/omni/display-chart.txt`. It neither reads nor changes browser
test flags, console DNS, update protections or system display settings.

Do not deploy automatically. This candidate links an original diagnostic-only
`--wrap=sceKernelWaitEqueue` adapter, replacing SDL's indefinite flip wait with
at most 500,000 microseconds per call. A zero-event result is a failure. Existing
shorter timeouts and polling semantics are retained. No SDL source or archive is
modified; the build verifies the archive hash before/after linking. A successful
build is not console acceptance, and other driver/initialization calls are not
given a total-process watchdog by this change.
If a flip returns an error, the diagnostic retains its buffers and requests
foreground process exit instead of freeing potentially in-flight scanout memory.
SDL's nominal dimensions/Hz are logged honestly: actual HDMI timing is not
queried because the current public SDK/backend exposes no verified declaration
to this probe. Reinitializing 1080p is not proof of restoring the original HDMI
mode. No private ABI guesses are used.

For visual review: all four corner markers and the thin white border should be
visible; red/green/blue/white corners distinguish orientation. Alternating
single-pixel stripes reveal scaling, and large center digits show width/height.
Check the entire TV frame and actual console/output status separately. This
does not validate browser rendering or video decoding at 4K.

Build checkpoint (2026-10-18): native compilation and host ASan/UBSan checks
passed. `outputs/display-media/chart-2160.png` was visually inspected: all four
markers, border, eight color bars and readable dimensions are present. This PNG
is generated on the host, not a console screenshot.

## Finite-wait evidence

Console checkpoint after reconnect: `outputs/display-media/console-result.txt`
records successful 3840x2160 submission, successful 1920x1080 reinitialization
and submission, and sequence status 0. The launch request completed normally.
No timeout occurred, so this does not test the timeout branch on hardware.
Actual HDMI timing and visual correctness were not independently measured, and
this remains an isolated chart, not proof of full-browser 4K performance.

[ProsperoLight native_agc_present.cpp at 1b3fc2c](https://github.com/blackbearreloaded/ProsperoLight/blob/1b3fc2c24ca89fb462d6f7aca8855916277326be/src/native_agc_present.cpp)
declares `unsigned int *timeout_us`, calls `sceKernelWaitEqueue` with a finite
2,000-microsecond value, and identifies timeout as `0x8002003c`. Its presenter
checks flip status separately; we do not inherit that presenter's acceptance or
borrow its code. Our separate static SDL diagnostic makes one submission per
new queue and exits on any wait failure, without recycling buffers. The installed
isolated SDL header independently declares the same pointer parameter.

`bounded_flip_wait_test.c` tests the wrapper against an explicit fake OS call:
indefinite-input replacement, upper clamp, shorter timeout, zero-time poll,
no-event rejection and original-error propagation. Native C compilation verifies
the wrapper's toolchain compatibility. Linker wrapping is intentionally confined
to this diagnostic ELF, so re-running the build performs no source patch and is
repeatable. The timeout's actual hardware response remains unverified; retain
external console supervision for first use.

Two consecutive native builds and both host tests passed, and the linked ELF
contains `__wrap_sceKernelWaitEqueue`; SDL's archive stayed unchanged. The two
native ELF hashes differed, so byte-for-byte reproducible binaries are **not**
claimed. `first-build.sha256` and `display-chart.sha256` preserve that evidence.
