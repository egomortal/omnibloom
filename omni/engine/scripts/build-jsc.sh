#!/usr/bin/env bash
# Build JavaScriptCore (the `jsc` shell) for the PS5 with the homebrew SDK.
#
#   engine/scripts/build-jsc.sh [WORK_DIR]
#
# WORK_DIR (default /work/engine) holds: webkit/ checkout, sysroot/ (ICU), build-jsc/
# Re-runnable: each step skips work that is already done. Ninja resumes.
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"          # omni-browser/engine
WORK="${1:-/work/engine}"
SDK="${PS5_PAYLOAD_SDK:-/opt/ps5-payload-sdk}"
WEBKIT="$WORK/webkit"
SYSROOT="$WORK/sysroot"
BUILD="$WORK/build-jsc"

[ -d "$WEBKIT/Source/JavaScriptCore" ] || {
  echo "==> fetching WebKit (sparse, JSC only)"
  git clone --depth 1 --filter=blob:none --sparse https://github.com/WebKit/WebKit.git "$WEBKIT"
  git -C "$WEBKIT" sparse-checkout set --no-cone /CMakeLists.txt /Source/cmake/ \
    /Source/CMakeLists.txt /Source/WTF/ /Source/bmalloc/ /Source/JavaScriptCore/ /Tools/Scripts/ \
    /Source/ThirdParty/unifdef/ /Source/WebGPU/
}
[ -f "$SYSROOT/lib/libicuuc.a" ] || { echo "ICU missing: run engine/scripts/build-icu.sh first"; exit 1; }

# memory-extra is header-only; WebKit still wants an archive to link.
MX="$HERE/ports/memory-extra"
if [ ! -f "$MX/lib/libMemoryExtra.a" ]; then
  mkdir -p "$MX/lib"
  "$SDK/bin/prospero-clang" -c "$MX/shim.c" -o "$MX/lib/shim.o"
  "$SDK/bin/prospero-ar" rcs "$MX/lib/libMemoryExtra.a" "$MX/lib/shim.o"
  rm -f "$MX/lib/shim.o"
fi

echo "==> applying homebrew patches"
python3 "$HERE/scripts/apply-patches.py" "$WEBKIT"

if [ ! -f "$BUILD/build.ninja" ]; then
  echo "==> configuring"
  cmake -S "$WEBKIT" -B "$BUILD" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$HERE/toolchain/omni-ps5.cmake" \
    -DCMAKE_FIND_ROOT_PATH="$SYSROOT;$HERE/ports/memory-extra" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="-I$HERE/ports/sce-compat/include -include omni-sce-compat.h" \
    -DCMAKE_CXX_FLAGS="-I$HERE/ports/sce-compat/include -include omni-sce-compat.h" \
    -DPORT=PlayStation \
    -DOMNI_HOMEBREW=ON \
    -DENABLE_WEBCORE=OFF -DENABLE_WEBKIT=OFF -DENABLE_WEBKIT_LEGACY=OFF \
    -DENABLE_REMOTE_INSPECTOR=OFF -DENABLE_STATIC_JSC=ON -DENABLE_TOOLS=OFF -DENABLE_API_TESTS=OFF \
    -DDEVELOPER_MODE=OFF \
    -DICU_ROOT="$SYSROOT" \
    -DMEMORY_EXTRA_INCLUDE_DIR="$HERE/ports/memory-extra/include" \
    -DMEMORY_EXTRA_LIB="$HERE/ports/memory-extra/lib/libMemoryExtra.a" \
    -DCMAKE_VERBOSE_MAKEFILE=OFF
fi

echo "==> building jsc"
ninja -C "$BUILD" "${NINJA_TARGET:-jsc}"
