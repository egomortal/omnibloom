#!/usr/bin/env bash
# Link the JSC self-test payload against an existing JavaScriptCore build.
#   engine/scripts/build-selftest.sh [WORK_DIR]   -> $WORK/build-jsc/bin/omni-jsc-selftest.elf
# Reuses the exact link line of the `jsc` shell, swapping jsc.cpp.o for our object.
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${1:-/work/engine}"
B="$WORK/build-jsc"
SDK="${PS5_PAYLOAD_SDK:-/opt/ps5-payload-sdk}"
OBJ="$B/omni-selftest/jsc_selftest.o"
OUT="$B/bin/omni-jsc-selftest.elf"
mkdir -p "$(dirname "$OBJ")"

"$HERE/toolchain/omni-clang++" -std=c++20 -O2 -c \
  -I"$B/JavaScriptCore/Headers" -I"$HERE/ports/sce-compat/include" \
  -fno-exceptions -fno-rtti \
  "$HERE/selftest/jsc_selftest.cpp" -o "$OBJ"

cmd="$(ninja -C "$B" -t commands jsc | tail -1)"
cmd="${cmd//Source\/JavaScriptCore\/shell\/CMakeFiles\/jsc.dir\/__\/jsc.cpp.o/$OBJ}"
cmd="${cmd// -o bin\/jsc / -o $OUT }"
(cd "$B" && eval "$cmd")
"$SDK/bin/prospero-strip" "$OUT"
ls -l "$OUT"
