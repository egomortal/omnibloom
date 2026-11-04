#!/usr/bin/env bash
# Build WebKit (WebCore + WebKit, Skia) for the PS5 with the homebrew SDK.
#
#   bash engine/scripts/build-webkit.sh [WORK_DIR]
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
BUILD="$WORK/build-webkit"
WEBKIT_REV="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["webkit"]["commit"])' "$HERE/build-lock.json")"

for resource in cacert.pem fonts.conf DejaVuSans.ttf DejaVuSans-Bold.ttf DejaVuSerif.ttf DejaVuSansMono.ttf; do
  [ -s "$HERE/resources/$resource" ] || {
    echo "Missing engine/resources/$resource. Run bash engine/scripts/prepare-resources.sh first." >&2
    exit 1
  }
done

[ -d "$WEBKIT/Source/JavaScriptCore" ] || {
  echo "==> fetching WebKit"
  git clone --depth 1 --filter=blob:none --sparse https://github.com/WebKit/WebKit.git "$WEBKIT"
  git -C "$WEBKIT" fetch --depth 1 origin "$WEBKIT_REV"
  git -C "$WEBKIT" checkout --detach "$WEBKIT_REV"
  git -C "$WEBKIT" sparse-checkout set --no-cone /CMakeLists.txt /Source/cmake/ \
    /Source/CMakeLists.txt /Source/WTF/ /Source/bmalloc/ /Source/JavaScriptCore/ /Tools/Scripts/ \
    /Source/ThirdParty/unifdef/ /Source/WebGPU/
}
[ "$(git -C "$WEBKIT" rev-parse HEAD)" = "$WEBKIT_REV" ] || {
  echo "WebKit revision differs from engine/build-lock.json; use a separate matching checkout." >&2
  exit 1
}
# The original script fetched only JavaScriptCore, so a fresh full-engine build
# lacked WebCore, WebKit and Skia. Include the full source tree and build tools.
git -C "$WEBKIT" sparse-checkout set --no-cone /CMakeLists.txt /Source/ /Tools/ /WebKitLibraries/
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
python3 "$HERE/scripts/patch-thread-default.py" "$WEBKIT"
python3 "$HERE/scripts/patch-ps5-signal-context.py" "$WEBKIT"
python3 "$HERE/scripts/patch-timer-tree-lifetime.py" "$WEBKIT"
python3 "$HERE/scripts/patch-content-rule-memory.py" "$WEBKIT"
python3 "$HERE/scripts/patch-keyboard-text.py" "$WEBKIT"
python3 "$HERE/scripts/patch-custom-user-agent.py" "$WEBKIT"
python3 "$HERE/scripts/patch-widget-dns.py" "$WEBKIT"
python3 "$HERE/scripts/patch-allocation-diagnostics.py" "$WEBKIT"
python3 "$HERE/scripts/patch-aligned-mapping.py" "$WEBKIT"
python3 "$HERE/scripts/patch-thread-failure.py" "$WEBKIT"
python3 "$HERE/scripts/patch-ipc-monitor.py" "$WEBKIT"
python3 "$HERE/scripts/patch-ublock-network.py" "$WEBKIT"
python3 "$HERE/scripts/patch-ublock-site.py" "$WEBKIT"
python3 "$HERE/scripts/patch-user-script-world.py" "$WEBKIT"
python3 "$HERE/scripts/patch-ublock-rewrite.py" "$WEBKIT"
python3 "$HERE/scripts/patch-media-engine.py" "$WEBKIT"
python3 "$HERE/scripts/patch-fullscreen.py" "$WEBKIT"

# Reconfigure even when build.ninja exists, to pick up recovered target changes.
{
  echo "==> configuring"
  cmake -S "$WEBKIT" -B "$BUILD" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$HERE/toolchain/omni-ps5.cmake" \
    -DCMAKE_FIND_ROOT_PATH="$SYSROOT;$HERE/ports/memory-extra;$SDK/target/user/homebrew" -DCMAKE_PREFIX_PATH="$SYSROOT;$SDK/target/user/homebrew" -DWEBKIT_LIBRARIES_DIR="$SYSROOT" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS_RELEASE="-O2 -DNDEBUG -g0" \
    -DCMAKE_CXX_FLAGS_RELEASE="-O2 -DNDEBUG -g0" \
    -DDEBUG_FISSION=OFF \
    -DOMNI_WEBCORE_JOBS="${OMNI_WEBCORE_JOBS:-2}" \
    -DCMAKE_CXX_STANDARD_LIBRARIES="-lexpat -liconv -lbz2 -lzstd" \
    -DCMAKE_C_FLAGS="-I$HERE/ports/sce-compat/include -include omni-sce-compat.h" \
    -DCMAKE_CXX_FLAGS="-I$HERE/ports/sce-compat/include -include omni-sce-compat.h" \
    -DPORT=PlayStation \
    -DOMNI_HOMEBREW=ON -DOMNI_ENGINE_DIR="$HERE" \
    -DENABLE_WEBCORE=ON -DENABLE_WEBKIT=ON -DENABLE_WEBKIT_LEGACY=OFF -DUSE_SKIA=ON -DUSE_SKIA_ENCODERS=ON -DENABLE_MINIBROWSER=OFF -DENABLE_CONTENT_EXTENSIONS=ON -DENABLE_RESOURCE_USAGE=OFF \
    -DENABLE_REMOTE_INSPECTOR=OFF -DENABLE_STATIC_JSC=ON -DENABLE_TOOLS=OFF -DENABLE_API_TESTS=OFF \
    -DDEVELOPER_MODE=OFF \
    -DICU_ROOT="$SYSROOT" \
    -DMEMORY_EXTRA_INCLUDE_DIR="$HERE/ports/memory-extra/include" \
    -DMEMORY_EXTRA_LIB="$HERE/ports/memory-extra/lib/libMemoryExtra.a" \
    -DCMAKE_VERBOSE_MAKEFILE=OFF
}

echo "==> building OmniEngine"
ninja -C "$BUILD" -j "${OMNI_BUILD_JOBS:-2}" WebCore/DerivedSources/ModernMediaControls.js WebCore/DerivedSources/ModernMediaControls.css
python3 "$HERE/scripts/patch-media-controls.py" "$WEBKIT" "$BUILD"
ninja -C "$BUILD" -j "${OMNI_BUILD_JOBS:-2}" "${NINJA_TARGET:-OmniEngine}"
