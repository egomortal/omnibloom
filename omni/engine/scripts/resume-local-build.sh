#!/usr/bin/env bash
# Resume the prepared Ubuntu build. No dependency downloads or console writes.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LLVM_CONFIG=/usr/bin/llvm-config-21
WORK="${OMNI_BUILD_ROOT:-/opt/omni-build}"
export OMNI_BUILD_JOBS="${OMNI_BUILD_JOBS:-4}"
bash "$WORK/omni-browser/engine/scripts/build-webkit.sh" "$WORK"
