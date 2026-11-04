# Building Omnibloom

Everything is built on Linux (WSL works) with the **PS5 Payload SDK** (`prospero-clang`,
`prospero-lld`) by John Törnblom. The browser is the big job: a full WebKit build takes hours
and well over 100 GB of disk.

> The build scripts here are the ones the project actually uses. They still contain
> machine-specific paths (`/home/builder/...`, `/opt/omni-build/...`,
> `/opt/ps5-payload-sdk/...`). Edit them for your machine before running them.

## Layout

| Folder | What it builds |
| --- | --- |
| `omni/webkit/` | Patches against upstream WebKit commit **539e0189f** (2026-10-17). Apply them in order: `patches/01-omni-local-changes.patch`, then `02-security-cve-fixes.patch`, then copy `overlay/` over the tree. `03-jit-gamepad-network-block.diff` shows what the overlay changes. `configure-cmd.json` is the exact CMake configure line. |
| `omni/engine/` | Omni's own code: the browser shell (`entry/`), the video and audio pipeline (`media/`), PS5 compatibility shims (`ports/`), the toolchain file (`toolchain/omni-ps5.cmake`), build scripts (`scripts/`), resources (fonts, ad-block rules, controller icons, pointer art) and self-test pages (`selftest/`). |
| `omni/native-title/` | Turns the engine into the native PS5 app PPSA99732 (`build.py`), and the child engine the app starts for each tab (`child_build.py`). `tools/check_native_layout.py` rejects layouts that crash the console. |
| `omni/files-broker/` | `omni-files.elf`, the USB file helper. |
| `downloads/` | The downloads page and its Python worker (link checking, yt-dlp). |
| Master Control | Not in this repository: <https://github.com/egomortal/master-control> builds and releases `master-control.elf`. |

## Dependencies

- PS5 Payload SDK, with its homebrew sysroot (PacBrew).
- Built from source by the scripts in `omni/engine/scripts/`: ICU 78.3, HarfBuzz ICU bridge, libwpe 1.16.3.
- Security-updated libraries linked into the engine: OpenSSL 3.5.9, curl 8.23.0, libpng 1.6.59, libxml2 2.13.9, FFmpeg 7.1.5.
- `PS5_Vulkan`'s `app_crt` and `radv-link.sh` (in `omni/native-title/tools/`) for the native app's start-up code and memory setup.

## Not included

These files are needed to build or run the native app but can't be published here:

- **`sce_module/libc.prx`**: a console system module. Take it from your own console.
- The signing step uses `ps5-native-tool`, which is not part of this repository.

## Order

1. Build WebKit with the patches and the configure line (`ninja OmniEngine`).
2. `python3 omni/native-title/make_link_command.py`
3. `python3 omni/native-title/child_build.py`: the child engine.
4. `python3 omni/native-title/build.py`: the app package in `out/PPSA99732/`.
5. `omni/files-broker/build.sh`, separately. Master Control is built in its own repository.
