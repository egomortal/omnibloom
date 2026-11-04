# Omnibloom roadmap

This roadmap describes remaining integration, validation and design decisions. It has no delivery dates or compatibility promises. Reviewed prototypes are not automatically shipping features. Each feature is released only after its native behavior, accessibility, licensing and failure handling have been verified.

## Launch foundations

Prioritize trusted app metadata and the shared SDK, Setup diagnostics, crash/log tools, controller text entry, session recovery and accessible controls. Keep existing working behavior available throughout integration.

## Reliable setup and releases

- **Setup "Doctor" mode** (R3-017): Integrate and validate the reviewed implementation on the target platform.
- **Migration assistant** (R3-018): Integrate and validate the reviewed implementation on the target platform.
- **Setup translations** (R3-019): Integrate and validate the reviewed implementation on the target platform.
- **Offline bundle builder** (R3-020): Assemble the real offline release after the complete approved assets and provenance are available.
- **Fuzz harnesses** (R3-021): Parser test coverage remains pending a separate review; it is not release-certified.
- **Log viewer page** (R3-023): Integrate and validate the reviewed implementation on the target platform.
- **C payload template** (R3-056): Integrate and validate the reviewed implementation on the target platform.
- **Auto-update** (R3-061): Integrate and validate the reviewed implementation on the target platform.
- **Portable mode and CLI docs.** (R3-062): Integrate and validate the reviewed implementation on the target platform.
- **macOS and Linux polish** (R3-063): Verify native appearance and packaging on macOS and Linux; signing is a separate decision.

## Everyday browsing

- **On-screen keyboard v2** (R3-001): Integrate and validate the reviewed implementation on the target platform.
- **Address bar suggestions** (R3-002): Integrate and validate the reviewed implementation on the target platform.
- **New-tab speed dial** (R3-003): Integrate and validate the reviewed implementation on the target platform.
- **Tab groups and pinned tabs** (R3-004): Integrate and validate the reviewed implementation on the target platform.
- **Session restore UI** (R3-005): Integrate and validate the reviewed implementation on the target platform.
- **Context menu for links, images and video** (R3-006): Integrate and validate the reviewed implementation on the target platform.
- **QR code page** (R3-007): Integrate and validate the reviewed implementation on the target platform.
- **Scroll and pointer polish** (R3-008): Integrate and validate the reviewed implementation on the target platform.
- **Clean video player for direct media files** (R3-009): Integrate and validate the reviewed implementation on the target platform.
- **PDF viewer** (R3-010): Integrate and validate the reviewed implementation on the target platform.
- **Image viewer** (R3-011): Integrate and validate the reviewed implementation on the target platform.
- **Media Session controls** (R3-012): Integrate and validate the reviewed implementation on the target platform.
- **Site-fix library** (R3-013): Integrate and validate the reviewed implementation on the target platform.
- **Polyfill audit** (R3-014): Integrate and validate the reviewed implementation on the target platform.
- **Desktop/TV site toggle per site** (R3-015): Integrate and validate the reviewed implementation on the target platform.
- **Login helpers** (R3-016): Integrate and validate the reviewed implementation on the target platform.
- **Reading list / Watch later** (R3-030): Integrate and validate the reviewed implementation on the target platform.
- **Private browsing mode** (R3-031): Integrate and validate the reviewed implementation on the target platform.
- **Cookie and site-data manager** (R3-032): Integrate and validate the reviewed implementation on the target platform.
- **HTTPS-only mode** (R3-033): Integrate and validate the reviewed implementation on the target platform.
- **Tracker-blocking list manager** (R3-034): Integrate and validate the reviewed implementation on the target platform.
- **Permission prompts** (R3-035): Integrate and validate the reviewed implementation on the target platform.
- **Built-in TOTP 2FA code generator** (R3-036): Implement a reviewed encrypted vault before enabling enrollment or storing secrets.
- **Password generator and vault health** (R3-037): Integrate and validate the reviewed implementation on the target platform.
- **Notes app inside Omni** (R3-038): Integrate and validate the reviewed implementation on the target platform.
- **Translate page UI refresh** (R3-039): Integrate and validate the reviewed implementation on the target platform.

## Accessibility and language

- **Accessibility modes** (R3-040): Integrate and validate the reviewed implementation on the target platform.
- **RTL support** (R3-041): Apply and review RTL behavior across every native suite page.
- **More languages** (R3-042): Obtain native-speaker review and replace English-specific plural construction.
- **One-handed and accessibility layouts** (R3-054): Integrate and validate the reviewed implementation on the target platform.

## Downloads and local media

- **Download presets** (R3-043): Integrate and validate the reviewed implementation on the target platform.
- **Playlist and channel downloads UI,** (R3-044): Integrate and validate the reviewed implementation on the target platform.
- **Scheduler and bandwidth limit UI** (R3-045): Integrate and validate the reviewed implementation on the target platform.
- **Library with metadata from the files themselves** (R3-046): Integrate and validate the reviewed implementation on the target platform.
- **Send-to-USB with progress,** (R3-047): Integrate and validate the reviewed implementation on the target platform.
- **Subtitle tools** (R3-048): Integrate and validate the reviewed implementation on the target platform.
- **Music** (R3-072): Validate actual USB audio and queue behavior; measure gapless feasibility separately.
- **Podcasts / RSS reader** (R3-073): Integrate and validate the reviewed implementation on the target platform.
- **Screenshot and clip gallery** (R3-078): Validate lawful capture access and viewer behavior without assuming internal paths.

## Controller tools

- **Profile v2** (R3-049): Integrate and validate the reviewed implementation on the target platform.
- **Gyro and touchpad mapping UI,** (R3-050): Integrate and validate the reviewed implementation on the target platform.
- **Macro recorder UI** (R3-051): Integrate and validate the reviewed implementation on the target platform.
- **Controller info page** (R3-052): Integrate and validate the reviewed implementation on the target platform.
- **Haptics and rumble test page.** (R3-053): Integrate and validate the reviewed implementation on the target platform.

## Suite platform and small apps

- **bloom.js SDK** (R3-055): Integrate and validate the reviewed implementation on the target platform.
- **Notifications centre** (R3-058): Integrate and validate the reviewed implementation on the target platform.
- **App catalog page** (R3-059): Integrate and validate the reviewed implementation on the target platform.
- **Shared themes** (R3-060): Integrate and validate the reviewed implementation on the target platform.
- **Files** (R3-070): Integrate bounded file capabilities; deletion remains a design decision, not an enabled feature.
- **System Monitor** (R3-071): Connect only verified metrics; unavailable temperatures remain unavailable.
- **Weather and clock widgets** (R3-074): Integrate and validate the reviewed implementation on the target platform.
- **Ambient screen** (R3-075): Integrate and validate the reviewed implementation on the target platform.
- **Homebrew catalog** (R3-076): Integrate and validate the reviewed implementation on the target platform.
- **Couch utilities** (R3-077): Integrate and validate the reviewed implementation on the target platform.
- **WebAssembly status** (R3-082): Verify WebAssembly behavior and workload performance in the actual browser build.
- **HDR UX** (R3-084): Bind settings to confirmed HDR capabilities and reviewed tone mapping.
- **Security review** (R3-114): Review the threat model and integrate bounded support-export changes; unresolved risks remain open.

## Art, learning and community

- **Sound pack** (R3-090): Validate audio backend and volume; sounds remain off by default.
- **Universes 21–30** (R3-091): Review ten new universe concepts and integrate selected navigation designs.
- **Omnibloom mascot exploration** (R3-094): Choose whether to adopt the optional mascot; keep essential feedback text-first.
- **Animated tile (pic1) concepts** (R3-095): Verify current title artwork formats; static Shell assets and in-app motion remain distinct.
- **Docs site v2** (R3-097): Review the documentation build and publish only through the normal release process.
- **Performance dashboard page** (R3-099): Connect measured CI results and preserve unknown/interrupted states honestly.

## Platform decisions and evidence

- **WebKit rebase** (R3-080): choose a pinned newer target and execute the reviewed migration plan without mixing process versions.
- **GPU rendering** (R3-081): qualify the host-tested offscreen EGL/GLES probe on the native RADV stack, then integrate GPU raster, compositing and WebGL.
- **AV1 software decoding** (R3-083): collect comparable measurements, then validate full playback rather than decoder throughput alone.
- **Extensions** (R3-085): ship bounded reviewed site fixes first; decide whether a larger extension model is justified.
- **Local transfer** (R3-086): begin with reviewed file export/import; encrypted exports or LAN pairing need a separate complete design.

## How work moves forward

A proposal becomes an implementation only when its scope and dependencies are clear. A tested local prototype becomes a release candidate after native integration and target-platform checks. Publication follows licensing, source, asset and documentation review. Missing evidence stays visible; no unsupported feature is advertised as available.

Keep the roadmap grouped by user needs. Close an item only with reproducible evidence and update its documentation at the same time. Community contributions should start with the bounded tasks in the contributor guide, not with unreviewed privileged services or release packaging.
