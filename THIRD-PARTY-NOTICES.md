> CLEAN PC/UI source selection: historical native/runtime/media sections below retain attribution context; inclusion is determined by SOURCE-MANIFEST.json, not by these descriptions. No native engine, vault, runtime or narrated audio is packaged here. Rights/provenance gaps remain release gates.

# Third-party notices

Omnibloom's own code is licensed under the GNU General Public License v3.0 or later (see
[LICENSE](LICENSE)). It includes, links against or is built from the projects below. Each
keeps its own licence and copyright, and they're listed here with thanks.

Where a licence text ships in this repository, the path is given. Otherwise the text is in the
upstream project's source, at the version named.

## The browser engine

| Project | Version | Licence | Notes |
| --- | --- | --- | --- |
| WebKit (WebCore, WebKit, WTF) | upstream commit 539e0189f (2026-10-17) plus the patches in `omni/webkit/` | LGPL-2.1-or-later and BSD-2-Clause (per file) | <https://webkit.org>. Omni's changes are in `omni/webkit/patches/` and `omni/webkit/overlay/`. |
| JavaScriptCore | as WebKit | LGPL-2.1-or-later and BSD-2-Clause (per file) | Part of WebKit. |
| Skia | as pinned by WebKit | BSD-3-Clause | Bundled with WebKit. |
| libwpe | 1.16.3 | BSD-2-Clause | <https://github.com/WebPlatformForEmbedded/libwpe> |
| ICU | 78.3 | Unicode License v3 | <https://icu.unicode.org> |
| HarfBuzz | 9.x | MIT ("Old MIT") | <https://harfbuzz.github.io> |
| FreeType | from the PacBrew sysroot | FreeType License (FTL) | <https://freetype.org> |
| fontconfig | from the PacBrew sysroot | MIT-style | <https://www.freedesktop.org/wiki/Software/fontconfig/> |
| SQLite | from the PacBrew sysroot | Public domain | <https://sqlite.org> |
| SDL2 | from the PS5 Payload SDK | zlib License | <https://libsdl.org> |
| Mesa (RADV, Zink, EGL) | from the PacBrew sysroot | MIT | <https://mesa3d.org> |
| zlib | from the PacBrew sysroot | zlib License | <https://zlib.net> |

## Networking, media and image libraries

| Project | Version | Licence | Notes |
| --- | --- | --- | --- |
| OpenSSL | 3.5.9 | Apache-2.0 | <https://openssl.org> |
| curl / libcurl | 8.23.0 | curl License (MIT-style) | <https://curl.se> |
| nghttp2 (libnghttp2, HTTP/2 for curl) | 1.64.0 | MIT | <https://github.com/nghttp2/nghttp2> |
| Brotli (decoder/common, `br` content encoding for curl) | 1.1.0 | MIT | <https://github.com/google/brotli> |
| FFmpeg (libavcodec, libavformat, libavutil, libswresample, libswscale) | 7.1.5 historical sec-job1 recipe | GPL-3.0-or-later configuration: GPL and version3 enabled, including libx264 | <https://ffmpeg.org>; recipe and build log record CONFIG_GPL=yes, CONFIG_VERSION3=yes and CONFIG_LIBX264=yes. This identifies that recipe, not an uninspected future binary. Retain corresponding source and all linked-library notices. |
| libpng | 1.6.59 | libpng License | <http://www.libpng.org> |
| libxml2 | 2.13.9 | MIT | <https://gitlab.gnome.org/GNOME/libxml2> |
| libjpeg-turbo, libwebp | from the PacBrew sysroot | IJG / BSD-3-Clause; BSD-3-Clause | |
| libpsl | from the PacBrew sysroot | MIT | |
| Public Suffix List | `omni/engine/resources/public-suffix-list.dat` | MPL-2.0 | <https://publicsuffix.org> |
| Mozilla CA certificate bundle | `omni/engine/resources/cacert.pem` | MPL-2.0 | Via curl's <https://curl.se/docs/caextract.html> |

## Ad blocking

| Project | Licence | Notes |
| --- | --- | --- |
| uBlock Origin (Raymond Hill and contributors) | GPL-3.0 | Rules engine and page scripts in `omni/engine/resources/ubo-content/`. Licence: `omni/engine/resources/ubo-content/LICENSE.txt`. |
| EasyList, EasyPrivacy | GPL-3.0-or-later or CC BY-SA 3.0 | Compiled into `omni/engine/resources/ublock-*.txt`. |
| uBlock filters and uAssets | GPL-3.0 | As above. |

## Downloads

| Project | Licence | Notes |
| --- | --- | --- |
| yt-dlp | The Unlicense | <https://github.com/yt-dlp/yt-dlp>. Not bundled in this source tree. |
| CPython | PSF License | The downloads worker runs on CPython 3.12 on the console. Not bundled in this source tree. |
| QuickJS | MIT | Used by the downloads worker's runtime. Not bundled in this source tree. |

## Fonts

| Font | Licence | Licence text |
| --- | --- | --- |
| DejaVu Sans, Sans Mono, Serif | Bitstream Vera / DejaVu License | `omni/engine/resources/FONT-LICENSE.txt` |
| Noto Sans JP, KR, SC | SIL Open Font License 1.1 | `omni/engine/resources/fonts-extra/LICENSE-noto-sans-cjk.txt` |
| Noto Color Emoji | SIL Open Font License 1.1 | `omni/engine/resources/fonts-extra/LICENSE-noto-color-emoji.txt` |
| Inter (Rasmus Andersson and contributors) | SIL Open Font License 1.1 | `ui/design-system/fonts/OFL-Inter.txt` (also next to each copy in `docs/site/fonts/`) |
| Rajdhani (Indian Type Foundry) | SIL Open Font License 1.1 | `ui/design-system/fonts/OFL-Rajdhani.txt` |

## Art

| Art | Licence | Where |
| --- | --- | --- |
| Kenney Input Prompts 1.5 | CC0 1.0 | `omni/engine/resources/controller-icons/` (`LICENSE-KENNEY.txt`) |
| Kenney Cursor Pack 1.1, Crosshair Pack 1.1 | CC0 1.0 | `omni/engine/resources/pointer-art/` (`SOURCE.txt` and the licence files there) |
| Omnibloom icon (swirl and flower) | Owned by the project author, GPL-3.0-or-later with the rest of the project | `branding/`, `assets/icon/` |
| Original universe art, app icons, controller glyphs and UI design | Made for this project, GPL-3.0-or-later with the rest of the project | `downloads/worker/assets/art/`, `branding/apps/`, `ui/`, `docs/` |

## Master Control

Master Control (the controller app) is a separate repository with its own notices:
<https://github.com/egomortal/master-control>. It is built from AnyPad-PS5 (elmonomalvad0),
PadBridge PS5 (X-F1REBALL-X), ps5-wireless-pads (AngelLopezTorres) and Ghost-Control (StonedModder),
all GPL-3.0-or-later. Omnibloom doesn't include its code; Omni only talks to its local web API.

## Toolchain

| Project | Author | Licence |
| --- | --- | --- |
| PS5 Payload SDK | John Törnblom | GPL-3.0 (see the SDK for library exceptions) |
| PacBrew sysroot | PacBrew contributors | Per package |
| PS5_Vulkan RADV link recipe | Mihawk-99 (2026) | GPL-3.0-or-later; preserve source header and GPL text |
| PS5_Vulkan native startup / ps5-native-app-boilerplate | BlackBearReloaded (2026) | GPL-3.0-or-later; exact linked startup-object provenance remains required |
| AnyPad-PS5 (Master Control upstream) | elmonomalvad0, also credited as sinfiltros | GPL-3.0-or-later; preserve upstream AUTHOR/README and licence |

Omnibloom does not include or redistribute any Sony SDK, firmware, keys or system files.

## JDownloader 2 engine (release asset `omnibloom-jd-engine-<ver>.zip`, not in this source tree)

| Project | Version | Licence | Notes |
| --- | --- | --- | --- |
| **PS5 Java 25 port** by mateo-cogeanu | commit `db3ac845fa090c64e2a737d6c4222dd37867d7fe` | as its notices say (its native app parts and the PS5 Payload SDK it builds on are GPL-3.0-or-later) | <https://github.com/mateo-cogeanu/ps5-java25-homebrew>. Thank you: JDownloader 2 runs on the PS5 because of this port. Its THIRD_PARTY_NOTICES.md and EMBEDDED-RUNTIME-NOTICES.md ship unchanged in the asset's `notices/`. |
| OpenJDK (FreeBSD fork) | 25.0.4+7, commit `b219cdec88ca2e165711f63b8158ab78303facc8` | GPL-2.0 with the Classpath Exception (per file) | <https://github.com/freebsd/openjdk>. LICENSE, ADDITIONAL_LICENSE_INFO and ASSEMBLY_EXCEPTION ship unchanged in `notices/openjdk/`; the third-party notices of each module are in the runtime image's `legal/`. Our changes are in `jdownloader/openjdk-patches/` and `jdownloader/recipe/`. |
| PS5 Payload SDK | v0.42 | GPL-3.0-or-later, except where otherwise indicated (BSD-licensed FreeBSD headers) | <https://github.com/ps5-payload-dev/sdk> |
| JDownloader 2 | the user's own copy | partly closed-source (AppWork GmbH) | **Not shipped.** Omnibloom Setup copies the user's install. `jdownloader/java/upstream-adapted/…/MyJDownloaderController.java` is adapted from JDownloader 2's open source (GPL-3.0). |

## Tutorial narration (docs/tutorials)

Narration generated with Piper (piper-tts 1.8.0, OHF-Voice/piper1-gpl, GPL-3.0-or-later); only the audio is published. Voice models from huggingface.co/rhasspy/piper-voices (MIT). Japanese and Korean are captions only.

| Language | Piper voice | Voice data | Licence |
| --- | --- | --- | --- |
| en | en_US-ljspeech-high | LJ Speech Dataset, Keith Ito (<https://keithito.com/LJ-Speech-Dataset/>) | public domain |
| es | es_ES-davefx-medium | davefx, OHF-Voice voice-datasets (<https://github.com/OHF-Voice/voice-datasets>) | CC0 |
| pt-BR | pt_BR-faber-medium | faber, OHF-Voice voice-datasets (<https://github.com/OHF-Voice/voice-datasets>) | CC0 |
| fr | fr_FR-siwis-medium | SIWIS French Speech Synthesis Database, Junichi Yamagishi, Pierre-Edouard Honnet, Philip Garner, Alexandros Lazaridis (University of Edinburgh / Idiap) (<https://datashare.is.ed.ac.uk/handle/10283/2353>) | CC BY 4.0 |
| de | de_DE-thorsten-high | Thorsten-Voice, Thorsten Müller (<https://github.com/thorstenMueller/Thorsten-Voice>) | CC0 |
| it | it_IT-paola-medium | Voice-Dataset-Italian, paolapersico1 (<https://huggingface.co/datasets/paolapersico1/Voice-Dataset-Italian>) | CC0 |

## Native startup and link-recipe attribution clarification

The reviewed native baseline `omni/native-title/tools/radv-link.sh` identifies Copyright (C) 2026 **Mihawk-99**, SPDX **GPL-3.0-or-later**. Preserve its header and GPL text. The separately required PS5_Vulkan `tooling/native/app_crt.cpp` identifies Copyright (C) 2026 **BlackBearReloaded**, SPDX **GPL-3.0-or-later**, under the name ps5-native-app-boilerplate. Do not attribute both files to the same author. The startup source/object is not included in this staged native-title tree; a release builder must provide its exact source revision, changes, and object provenance. A nearby checkout's licence is not proof that an older object was built from that checkout.

These corrections do not resolve the separate imported blocker/filter, adapted-source, narration and other provenance findings in the release licence audit. The existing tutorial paragraph describes historical Piper output; current Japanese/Korean narration and any newly restaged assets require their own exact model/output notices. Do not use this source-tree notice as approval to redistribute a new runtime or media package.
