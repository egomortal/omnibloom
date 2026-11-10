# RADV (Mesa Vulkan) with HDR scanout

The native app links a prebuilt RADV archive, `libvulkan_radeon-hdr-wsi.a` (not in this repository: it is a binary). It is Mesa RADV from the PS5_Mesa port, built with one changed member, `wsi_common_videoout.c`, which adds a 10-bit PQ (HDR10) scanout next to the 8-bit SDR one.

- `wsi-hdr.diff`: our change to `wsi_common_videoout.c` (MIT, Copyright 2026 Mihawk; notice kept).
- `scanout_policy.h`: the format/colour-space pairs the WSI accepts (GPL-3.0-or-later).

SDR scanout is BGRA8 (`0x8000000000000000`); PQ scanout is RGB10A2 (`0x8100070422000000`). The archive keeps the notices of its upstream Mesa components.
