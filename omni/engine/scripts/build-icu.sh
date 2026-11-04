#!/usr/bin/env bash
# Cross-build ICU for the PS5 (static) into $WORK/sysroot.
#   engine/scripts/build-icu.sh [WORK_DIR]
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
WORK="${1:-/work/engine}"
VER="${ICU_VERSION:-78.3}"
SDK="${PS5_PAYLOAD_SDK:-/opt/ps5-payload-sdk}"
mkdir -p "$WORK" && cd "$WORK"

[ -d icu/source ] || {
  curl -fsSL -o icu4c-src.tgz \
    "https://github.com/unicode-org/icu/releases/download/release-${VER}/icu4c-${VER}-sources.tgz"
  tar xzf icu4c-src.tgz
}

# 1) host build: provides the data tools the cross build needs
if [ ! -f icu-host/bin/icupkg ]; then
  mkdir -p icu-host && (cd icu-host && ../icu/source/configure --disable-tests \
    --disable-samples --disable-extras && make -j"$(nproc)")
fi

# 2) PS5 build. The PS5 clang target honours dllexport, so ICU must be told
#    it is a static build (U_STATIC_IMPLEMENTATION) or its export macros break.
if [ ! -f sysroot/lib/libicuuc.a ]; then
  mkdir -p icu-ps5 && cd icu-ps5
  # shellcheck disable=SC1091
  source "$SDK/toolchain/prospero.sh"; unset DESTDIR PREFIX
  ../icu/source/configure --host=x86_64-unknown-freebsd --with-cross-build="$WORK/icu-host" \
    --prefix="$WORK/sysroot" --enable-static --disable-shared --disable-tests \
    --disable-samples --disable-extras --disable-tools --disable-dyload \
    --with-data-packaging=static CPPFLAGS="-DU_STATIC_IMPLEMENTATION" \
    CFLAGS="-O2 -fPIC" CXXFLAGS="-O2 -fPIC"
  make -j"$(nproc)" && make install
fi
ls -l "$WORK"/sysroot/lib/libicu*.a
