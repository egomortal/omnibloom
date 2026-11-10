#!/bin/bash
# omni-launch EBOOT (combined launch candidate title, PPSA99732) = s3.5-hdr (HDR10 output, setting Off/Auto/On)
#   + OMNI_GPU_VERIFY10_V1 (omni-hdr-verify10, OmniGpuVideo.cpp)      + OMNI_ABR_SWITCH_V1 (omni-abr, OmniHwService.cpp)
#   + OMNI_JANK_V1 / OMNI_PAINT_HOLD_V1 title side (omni-jank)       + OMNI_ACK_V1 title side (omni-ack)
#   + OMNI_HDR_PRESENT10_V1 (omni-hdr-present10, src-title/OmniGpuPresent.cpp; rc2)
# Folder-level media merge (verify10 + ABR) is done and proven order-independent in omni-launch/merge-work (REPORT.md).
# Tree-level patches that share engine/entry/OmniBrowser.cpp (OMNI_HDR_CAPS_V1 vs jank/paint-hold) are applied here in
# TWO orders, on two private overlays of /home/builder/s3, and the resulting sources compared byte for byte before
# anything is compiled. Every feature keeps its own flag / kill switch. The child is linked first from the unpatched
# tree and must be 7b810ea5 (title only). SOURCE_DATE_EPOCH=1793793600. Own lock /tmp/omni-launch-eboot.lock, own
# overlay uppers /home/builder/launche-up-<uid> (order A, build) and /home/builder/launcheb-up-<uid> (order B, proof),
# own objects /home/builder/launchobjs (seeded by COPYING s35objs), own /tmp names. Never writes another build's tree.
# Startup/bootstrap code untouched. Build only: never deploys, never touches the console.
# Progress: outputs/omni-launch/eboot/build-steps.txt. The empty folder outputs/omni-launch-eboot-bind is only a mount point.
O='/path/to/workspace/outputs'; N="$O/omni-launch/eboot"
cat > /tmp/launche-inner-$$.sh <<'IN'
#!/bin/bash
O='/path/to/workspace/outputs'; N="$O/omni-launch-eboot-bind"; B="$O/omni-native-s3.1c"
# N is a bind mount (private namespace) of outputs/omni-launch/eboot directly under outputs/: the inherited tools
# locate their sibling folders (omni-jit-fix, omni-native-s1c, codex-ui, ../baseline, ../nxe-ps5) as N.parent
J="$O/omni-jank"; A="$O/omni-ack"; R="$O/omni-abr"; D4="$O/omni-native-s3.4d"; H5="$O/omni-native-s3.5-hdr"
VKH='/path/to/workspace/nxe-ps5/bigapp/private/av2/upstream/PS5_Mesa/include'
NR="$V_NREAL"   # the real outputs/omni-launch/eboot: progress is mirrored there, results are copied there at the end
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$N/build-steps.txt" >> "$NR/build-steps.txt"; }
export OMNI_SECLIBS=/home/builder/omni-seclibs/stage/user/homebrew/lib
export SOURCE_DATE_EPOCH=1793793600
TA=/home/builder/s1; TB=/home/builder/launcheb-mnt; MA="$N/merge/orderA"; MB="$N/merge/orderB"
[ -e $TA/.launche-marker ] || { st "overlay A missing: refusing to build in the shared s1 tree"; exit 1; }
[ -e $TB/.launcheb-marker ] || { st "overlay B missing: stopping"; exit 1; }
st "build start (A = $TA, B = $TB: private overlays of s3; SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH)"
mkdir -p "$N/hosttest/wsl" "$MA/patches-jank" "$MA/patches-ack" "$MB/patches-jank" "$MB/patches-ack"
[ "$(sha256sum "$N/radv/libvulkan_radeon-hdr-wsi.a" | cut -d' ' -f1)" = 2bb567dab75d52ae30f0ba157d701f60b368a2f1d451bdd358dc837b5e8a704e ] || { st "radv archive is not 2bb567da"; exit 1; }
spirv-val --target-env vulkan1.1 "$N/shader/omni_yuv_to_rgb_v10.spv" > /dev/null 2>&1 || { st "V10 SPIR-V does not validate"; exit 1; }
python3 "$N/tools/spv_to_header.py" "$N/shader/omni_yuv_to_rgb_v10.spv" /tmp/launche-hdr-$$.h kOmniYuvToRgbSpv omni_yuv_to_rgb_v10.comp && sed -i 's#^// Generated from omni_yuv_to_rgb_v10.comp#// OMNI_GPU_VERIFY10_V1. Generated from omni_yuv_to_rgb_v10.comp#' /tmp/launche-hdr-$$.h \
  && cmp -s /tmp/launche-hdr-$$.h "$N/engine/media/OmniGpuVideoShaderV10.h" || { st "OmniGpuVideoShaderV10.h is not the V10 .spv"; exit 1; }; rm -f /tmp/launche-hdr-$$.h
# the folder merge must still be what merge-work proved
[ "$(sha256sum "$N/engine/media/OmniHwService.cpp" | cut -c1-16)" = e51d07464b4073b2 ] || { st "OmniHwService.cpp is not the proven HDR+ABR merge e51d0746: stopping"; exit 1; }
[ "$(sha256sum "$N/engine/media/OmniGpuVideo.cpp" | cut -c1-16)" = ef35f691428ab73f ] || { st "OmniGpuVideo.cpp is not the proven verify10 text ef35f691: stopping"; exit 1; }
[ "$(sha256sum "$N/src-title/OmniGpuPresent.cpp" | cut -c1-8)" = 97b39628 ] || { st "src-title/OmniGpuPresent.cpp is not the proven present10 text 97b39628: stopping"; exit 1; }
st "radv 2bb567da; V10 shader header = .spv; media = OmniHwService e51d0746 (HDR+ABR) + OmniGpuVideo ef35f691 (HDR+V10)"
# 0p. OMNI_HDR_PRESENT10_V1: the stack's OmniGpuPresent.cpp carries the patch; its embedded SPIR-V = shader/omni_pq_runs.spv =
# glslang 15.1 of shader/omni_pq_runs.comp (spirv-val clean); the -DOMNI_HDR_PRESENT10_DISABLE build compiles clean
mkdir -p "$N/hosttest/wsl"
grep -q OMNI_HDR_PRESENT10_V1 "$N/src-title/OmniGpuPresent.cpp" || { st "src-title/OmniGpuPresent.cpp lacks OMNI_HDR_PRESENT10_V1 (apply_present10.py not run)"; exit 1; }
H=$(mktemp -d /tmp/launche-spv-XXXXXX)
GL=$(command -v glslangValidator || command -v glslang); GLS="no glslang in WSL: the .spv (glslang 15.1, pinned 37bdb248 by apply_present10.py) is not recompiled here"
if [ -n "$GL" ]; then "$GL" -V --target-env vulkan1.1 "$N/shader/omni_pq_runs.comp" -o "$H/r.spv" > "$H/glslang.log" 2>&1 && cmp -s "$H/r.spv" "$N/shader/omni_pq_runs.spv" \
  || { st "P10 SPIR-V: $GL output differs from shader/omni_pq_runs.spv ($(tail -2 "$H/glslang.log" | tr '\n' ' '))"; exit 1; }; GLS="recompiled by $("$GL" --version 2>/dev/null | head -1) = the .spv"; fi
[ "$(sha256sum "$N/shader/omni_pq_runs.spv" | cut -d' ' -f1)" = 37bdb24861105e39e738274f7256788aebc2af851a3bc402689400c697bcc3b0 ] && spirv-val --target-env vulkan1.1 "$N/shader/omni_pq_runs.spv" > /dev/null 2>&1 \
  || { st "P10 SPIR-V: not 37bdb248 or spirv-val FAILED"; exit 1; }
python3 - "$N/shader/omni_pq_runs.spv" "$N/src-title/OmniGpuPresent.cpp" <<'PY' || { st "P10 SPIR-V embedded in OmniGpuPresent.cpp differs from shader/omni_pq_runs.spv"; exit 1; }
import re, struct, sys
spv = open(sys.argv[1], 'rb').read(); src = open(sys.argv[2]).read()
body = src.split('kOmniPqRunsSpv[] = {', 1)[1].split('};', 1)[0]
words = [int(w, 16) for w in re.findall(r'0x([0-9a-f]{8})u', body)]
sys.exit(0 if words == list(struct.unpack('<%dI' % (len(spv) // 4), spv)) else 1)
PY
rm -rf "$H"
VKHP='/path/to/workspace/nxe-ps5/bigapp/private/av2/upstream/PS5_Mesa/include'
clang++ -std=c++17 -fsyntax-only -Wall -Wextra -DOMNI_HDR_PRESENT10_DISABLE -isystem "$VKHP" -I"$N/src-title" "$N/src-title/OmniGpuPresent.cpp" > "$N/hosttest/wsl/p10-disable-syntax.log" 2>&1 \
  && clang++ -std=c++17 -fsyntax-only -Wall -Wextra -isystem "$VKHP" -I"$N/src-title" "$N/src-title/OmniGpuPresent.cpp" > "$N/hosttest/wsl/p10-console-syntax.log" 2>&1 \
  || { st "P10 console-path syntax check FAILED: $(grep -m3 error "$N"/hosttest/wsl/p10-*-syntax.log | tr '\n' ' ' | cut -c1-500)"; exit 1; }
st "P10: OmniGpuPresent.cpp $(sha256sum "$N/src-title/OmniGpuPresent.cpp" | cut -c1-16) has OMNI_HDR_PRESENT10_V1; omni_pq_runs.spv $(sha256sum "$N/shader/omni_pq_runs.spv" | cut -c1-16) = the embedded words, spirv-val clean ($GLS); console path and DISABLE build compile clean ($(cat "$N"/hosttest/wsl/p10-*-syntax.log | grep -c warning:) warnings)"
# ---------------------------------------------------------------- 0. host suites that need no tree (fail fast)
CRYPTO=-lcrypto; [ -e /usr/lib/x86_64-linux-gnu/libcrypto.so ] || CRYPTO=-l:libcrypto.so.3
H=$(mktemp -d /tmp/launche-h-XXXXXX)
clang++ -std=c++17 -O1 -g -U_FORTIFY_SOURCE -fsanitize=address,undefined -fno-omit-frame-pointer -I"$N/child-src" -DOMNI_HUB_DIR='"/tmp/no-hub"' \
  "$N/hosttest/sec_connect_test.cpp" "$N/child-src/omni-sec-connect.cpp" -o "$H/sec" -pthread > "$N/hosttest/wsl/sec-build.log" 2>&1 && "$H/sec" > "$N/hosttest/wsl/sec-connect.log" 2>&1 \
  || { st "SEC (OS-001) host test FAILED: $(tail -2 "$N/hosttest/wsl/sec-connect.log" "$N/hosttest/wsl/sec-build.log" | tr '\n' ' ' | cut -c1-400)"; exit 1; }
clang++ -std=c++17 -O1 -g -U_FORTIFY_SOURCE -fsanitize=address,undefined -fno-omit-frame-pointer -I"$N/engine-patches/entry" "$N/hosttest/vault_os002_test.cpp" -o "$H/vos" $CRYPTO > "$N/hosttest/wsl/vault-build.log" 2>&1 \
  && (cd "$H" && ./vos) > "$N/hosttest/wsl/vault-os002.log" 2>&1 || { st "VAULT OS-002 host test FAILED: $(tail -2 "$N/hosttest/wsl/vault-os002.log" | tr '\n' ' ')"; exit 1; }
tar --no-same-owner -C "$H" -xzf "$O/omni-native-s3/s3-hosttest.tgz" && clang++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -I"$N/engine-patches/entry" \
  "$H/s3t/tests/vault_test.cpp" -o "$H/vt" $CRYPTO > "$N/hosttest/wsl/vault-suite-build.log" 2>&1 && "$H/vt" > "$N/hosttest/wsl/vault-suite.log" 2>&1 \
  || { st "VAULT suite FAILED: $(tail -2 "$N/hosttest/wsl/vault-suite.log" | tr '\n' ' ')"; exit 1; }
/opt/ps5-payload-sdk/bin/prospero-clang++ -std=c++17 -O2 -Wall -Wextra -Werror -c "$N/child-src/omni-sec-connect.cpp" -o "$H/sec.o" > "$N/hosttest/wsl/sec-sdk-compile.log" 2>&1 \
  || { st "omni-sec-connect.cpp SDK compile FAILED"; exit 1; }
st "host: $(tail -1 "$N/hosttest/wsl/sec-connect.log"); $(tail -1 "$N/hosttest/wsl/vault-os002.log"); $(tail -1 "$N/hosttest/wsl/vault-suite.log"); SDK compile ok"
# jank gates (title side)
clang++ -std=c++17 -O1 -Wall -Wextra -Werror -I"$J/src" "$N/hosttest/jank_hist_test.cpp" -o "$H/jht" > "$N/hosttest/wsl/jank-hist-build.log" 2>&1 \
  && "$H/jht" > "$N/hosttest/wsl/jank-hist.log" 2>&1 || { st "jank histogram gate FAILED: $(tail -3 "$N/hosttest/wsl/jank-hist.log" "$N/hosttest/wsl/jank-hist-build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
clang++ -std=c++17 -O1 -Wall -Wextra -Werror -I"$J/src" "$N/hosttest/reveal_input_test.cpp" -o "$H/rit" > "$N/hosttest/wsl/reveal-input-build.log" 2>&1 \
  && "$H/rit" > "$N/hosttest/wsl/reveal-input.log" 2>&1 || { st "reveal-input gate FAILED: $(tail -3 "$N/hosttest/wsl/reveal-input.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
st "jank gates: $(tail -1 "$N/hosttest/wsl/jank-hist.log"); $(tail -1 "$N/hosttest/wsl/reveal-input.log")"
# ABR: accounting/pool (the shipped header) + wiring of the MERGED OmniHwService.cpp; the wiring test's "untouched
# functions" reference is the pre-ABR file of THIS stack (s3.5-hdr's; verify10 does not touch it)
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -I"$N/engine/media" \
  "$R/hosttest/abr_switch_test.cpp" -o "$H/abr" -pthread > "$N/hosttest/wsl/abr-build.log" 2>&1 \
  && "$H/abr" > "$N/hosttest/wsl/abr-switch.log" 2>&1 || { st "ABR switch test FAILED: $(grep -h FAIL "$N/hosttest/wsl/abr-switch.log" | head -3 | tr '\n' ' '; tail -3 "$N/hosttest/wsl/abr-build.log" | tr '\n' ' ' | cut -c1-400)"; exit 1; }
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer "$R/hosttest/abr_wiring_test.cpp" -o "$H/abrw" > "$N/hosttest/wsl/abr-wiring-build.log" 2>&1 \
  || { st "ABR wiring test build FAILED"; exit 1; }
"$H/abrw" "$N/engine/media/OmniHwService.cpp" "$H5/engine/media/OmniHwService.cpp" > "$N/hosttest/wsl/abr-wiring.log" 2>&1 \
  || { st "ABR wiring test FAILED: $(grep -h FAIL "$N/hosttest/wsl/abr-wiring.log" | head -3 | tr '\n' ' ' | cut -c1-500)"; exit 1; }
"$H/abrw" "$O/omni-native-s3.4-abr/engine/media/OmniHwService.cpp" "$D4/engine/media/OmniHwService.cpp" > "$N/hosttest/wsl/abr-wiring-s34abr-control.log" 2>&1 || true
st "ABR: $(tail -1 "$N/hosttest/wsl/abr-switch.log"); wiring on the merged file $(tail -1 "$N/hosttest/wsl/abr-wiring.log")"
rm -rf "$H"
# verify10 suite (real FFmpeg 7.1.5 swscale + lavapipe)
FF="$O/omni-hdr-verify10/ffmpeg-7.1.5-host"; H=$(mktemp -d /tmp/launche-v10-XXXXXX); T="$N/hosttest"; LVP=/usr/share/vulkan/icd.d/lvp_icd.json
DRM=-l:libdrm.so.2; [ -e /usr/lib/x86_64-linux-gnu/libdrm.so ] && DRM=-ldrm
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_VIDEO_HOST_TEST -isystem "$VKH" -isystem "$FF/include" -I"$N/engine/media" -I"$T" "$T/verify10_test.cpp" "$N/engine/media/OmniGpuVideo.cpp" \
  -o "$H/v10" "$FF/lib/libswscale.a" "$FF/lib/libavutil.a" -l:libvulkan.so.1 $DRM -lm -pthread > "$T/wsl/verify10-build.log" 2>&1 || { st "verify10 test build FAILED: $(grep -m3 error "$T/wsl/verify10-build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
cp -r "$T/data" "$H/data"; (cd "$H" && VK_ICD_FILENAMES=$LVP timeout 3000 "$H/v10" all) > "$T/wsl/verify10-test.log" 2>&1; VT=$?
st "VERIFY10 suite: exit $VT, $(tail -1 "$T/wsl/verify10-test.log")"
[ "$VT" = 0 ] || { st "VERIFY10 suite FAILED: $(grep -- '-> FAIL' "$T/wsl/verify10-test.log" | head -3 | tr '\n' ' ' | cut -c1-600)"; exit 1; }
rm -rf "$H"
# GPU video / present / shared / pair (V10 off: these suites' expectations are V4's), HDR suite V10 off and on
export OMNI_GPU_VERIFY10=0
H=$(mktemp -d /tmp/launche-gpu-XXXXXX)
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_VIDEO_HOST_TEST -isystem "$VKH" -I"$N/engine/media" "$T/gpuvideo_test.cpp" "$N/engine/media/OmniGpuVideo.cpp" \
  -o "$H/gvt" -l:libvulkan.so.1 -lswscale -lavutil -pthread > "$T/wsl/gpuvideo-build.log" 2>&1 || { st "gpuvideo test build FAILED"; exit 1; }
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_VIDEO_HOST_TEST -DOMNI_GPU_PRESENT_HOST_TEST -DOMNI_SHARED_TEST -isystem "$VKH" -I"$N/engine/media" -I"$N/src-title" "$T/gpuvideo_test.cpp" \
  "$N/engine/media/OmniGpuVideo.cpp" "$N/src-title/OmniGpuPresent.cpp" -o "$H/gvs" -l:libvulkan.so.1 -lswscale -lavutil -pthread > "$T/wsl/shared-build.log" 2>&1 || { st "shared-device test build FAILED"; exit 1; }
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_PRESENT_HOST_TEST -isystem "$VKH" -I"$N/src-title" "$T/present_test.cpp" "$N/src-title/OmniGpuPresent.cpp" \
  -o "$H/pt" -l:libvulkan.so.1 -pthread > "$T/wsl/present-build.log" 2>&1 || { st "present test build FAILED"; exit 1; }
clang++ -std=c++17 -O2 -g -DOMNI_GPU_PRESENT_HOST_TEST -isystem "$VKH" -I"$N/src-title" -I"$T" "$T/pair_test.cpp" "$N/src-title/OmniGpuPresent.cpp" \
  -o "$H/pair" -l:libvulkan.so.1 -pthread > "$T/wsl/pair-build.log" 2>&1 || { st "pair test build FAILED"; exit 1; }
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_VIDEO_HOST_TEST -DOMNI_GPU_PRESENT_HOST_TEST -isystem "$VKH" -I"$N/engine/media" -I"$N/src-title" -I"$T" "$T/hdr_test.cpp" \
  "$N/engine/media/OmniGpuVideo.cpp" "$N/src-title/OmniGpuPresent.cpp" -o "$H/hdr" -l:libvulkan.so.1 -pthread > "$T/wsl/hdr-build.log" 2>&1 || { st "hdr test build FAILED"; exit 1; }
mkdir -p "$H/run" && cd "$H/run" || exit 1
{ echo "# OmniGpuVideo host test, $(date -u +%FT%TZ), ICD $LVP"; VK_ICD_FILENAMES=$LVP timeout 2400 "$H/gvt" all 10000; } > "$T/wsl/gpuvideo-test.log" 2>&1; GV=$?
{ echo "# fallback"; VK_ICD_FILENAMES=/nonexistent.json timeout 120 "$H/gvt" F && VK_ICD_FILENAMES=$LVP timeout 120 "$H/gvt" W; } > "$T/wsl/gpuvideo-fallback.log" 2>&1; GF=$?
{ echo "# shared device"; VK_ICD_FILENAMES=$LVP timeout 900 "$H/gvs" S; } > "$T/wsl/shared-test.log" 2>&1; GS=$?
VK_ICD_FILENAMES=$LVP timeout 2400 "$H/pt" all 10000 > "$H/pt.out" 2>&1; PT=$?; grep -v '^gpu-present:' "$H/pt.out" > "$T/wsl/present-test.log"
VK_ICD_FILENAMES=/nonexistent.json timeout 120 "$H/pt" F > "$H/pf.out" 2>&1; grep -v '^gpu-present:' "$H/pf.out" > "$T/wsl/present-fallback.log"
PF=$(grep -c 'F no Vulkan ICD.*PASS' "$T/wsl/present-fallback.log")
VK_ICD_FILENAMES=$LVP timeout 600 "$H/pair" > "$H/pair.out" 2>&1; PR=$?; grep -v '^gpu-present:' "$H/pair.out" > "$T/wsl/pair-test.log"
cd "$H" && (VK_ICD_FILENAMES=$LVP timeout 3000 "$H/hdr" all 3000) > "$H/hdr.out" 2>&1; HT=$?; grep -v '^gpu-present:\|\[note\]' "$H/hdr.out" > "$T/wsl/hdr-test.log"
(cd "$H" && rm -f gpu-video.pipeline-cache && OMNI_GPU_VERIFY10=1 VK_ICD_FILENAMES=$LVP timeout 3000 "$H/hdr" all 3000) > "$H/hdr10.out" 2>&1; HT10=$?; grep -v '^gpu-present:\|\[note\]' "$H/hdr10.out" > "$T/wsl/hdr-test-v10on.log"
cd / ; rm -rf "$H"
# 0p2. OMNI_HDR_PRESENT10_V1 host gates (lavapipe): hdr_test with P10 OFF (V4's per-run copies, its own expectations: the
# default runs above have P10 ON), then p10_test (V1 == V4 byte for byte, counters, no per-frame allocation, SDR untouched)
# and its kill-switch run twice (flag file in the working directory; OMNI_HDR_PRESENT10=0). Any failure stops the build.
H=$(mktemp -d /tmp/launche-p10-XXXXXX)
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_VIDEO_HOST_TEST -DOMNI_GPU_PRESENT_HOST_TEST -isystem "$VKH" -I"$N/engine/media" -I"$N/src-title" -I"$T" "$T/hdr_test.cpp" \
  "$N/engine/media/OmniGpuVideo.cpp" "$N/src-title/OmniGpuPresent.cpp" -o "$H/hdr" -l:libvulkan.so.1 -pthread > "$T/wsl/hdr-p10off-build.log" 2>&1 || { st "hdr test (P10 off) build FAILED"; exit 1; }
(cd "$H" && OMNI_HDR_PRESENT10=0 VK_ICD_FILENAMES=$LVP timeout 3000 "$H/hdr" all 3000) > "$H/hdrp.out" 2>&1; HTP=$?; grep -v '^gpu-present:\|\[note\]' "$H/hdrp.out" > "$T/wsl/hdr-test-p10off.log"
st "HDR host test with P10 OFF: exit $HTP, $(grep -c ' -> PASS' "$T/wsl/hdr-test-p10off.log") PASS / $(grep -c ' -> FAIL' "$T/wsl/hdr-test-p10off.log") FAIL"
[ "$HTP" = 0 ] || { st "HDR host test (P10 off) FAILED: $(grep FAIL "$T/wsl/hdr-test-p10off.log" | head -3 | tr '\n' ' ' | cut -c1-600)"; exit 1; }
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_PRESENT_HOST_TEST -isystem "$VKH" -I"$N/src-title" -I"$T" "$T/p10_test.cpp" "$N/src-title/OmniGpuPresent.cpp" \
  -o "$H/p10" -l:libvulkan.so.1 -pthread > "$T/wsl/p10-build.log" 2>&1 || { st "p10 test build FAILED: $(grep -m3 error "$T/wsl/p10-build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
clang++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -DOMNI_GPU_PRESENT_HOST_TEST -isystem "$VKH" -I"$N/src-title" -I"$T" "$T/p10_test.cpp" "$N/src-title/OmniGpuPresent.cpp" \
  -o "$H/p10asan" -l:libvulkan.so.1 -pthread > "$T/wsl/p10-asan-build.log" 2>&1 || { st "p10 test (ASan) build FAILED"; exit 1; }
mkdir -p "$H/k1" "$H/k2" && touch "$H/k1/hdr-present10-disabled.flag"
(cd "$H" && VK_ICD_FILENAMES=$LVP timeout 3000 "$H/p10" all 3000) > "$H/p10.out" 2>&1; PA=$?
(cd "$H" && ASAN_OPTIONS=detect_leaks=0 VK_ICD_FILENAMES=$LVP timeout 3000 "$H/p10asan" all 200) > "$H/p10asan.out" 2>&1; PS=$?
(cd "$H/k1" && VK_ICD_FILENAMES=$LVP timeout 600 "$H/p10" K) > "$H/k1.out" 2>&1; PK1=$?
(cd "$H/k2" && OMNI_HDR_PRESENT10=0 VK_ICD_FILENAMES=$LVP timeout 600 "$H/p10" K) > "$H/k2.out" 2>&1; PK2=$?
{ echo "# OMNI_HDR_PRESENT10_V1 host test, $(date -u +%FT%TZ), ICD $LVP"; grep -v '^gpu-present:' "$H/p10.out"; echo "# ASan+UBSan run (200 presents in C)"; grep -v '^gpu-present:' "$H/p10asan.out" | grep -E 'PASS|FAIL|ERROR|runtime error|SUMMARY'; \
  echo "# kill switch: hdr-present10-disabled.flag"; grep -v '^gpu-present:' "$H/k1.out"; echo "# kill switch: OMNI_HDR_PRESENT10=0"; grep -v '^gpu-present:' "$H/k2.out"; } > "$T/wsl/p10-test.log"
grep -h 'OMNI_HDR_PRESENT10_V1' "$H/gpu-present.log" "$H/k1/gpu-present.log" "$H/k2/gpu-present.log" > "$T/wsl/p10-gpu-present.log" 2>/dev/null
st "P10 host test (lavapipe): all exit $PA ($(tail -1 "$H/p10.out")), ASan+UBSan exit $PS, kill switch file exit $PK1, env exit $PK2; $(grep -c ' -> PASS' "$T/wsl/p10-test.log") PASS / $(grep -c ' -> FAIL' "$T/wsl/p10-test.log") FAIL"
[ "$PA" = 0 ] && [ "$PS" = 0 ] && [ "$PK1" = 0 ] && [ "$PK2" = 0 ] && ! grep -q -E 'runtime error|ERROR: AddressSanitizer' "$H/p10asan.out" || { st "P10 host test FAILED: $(grep -h -- '-> FAIL\|runtime error\|AddressSanitizer' "$H"/*.out | head -3 | tr '\n' ' ' | cut -c1-600)"; exit 1; }
rm -rf "$H"
unset OMNI_GPU_VERIFY10
st "GPU suites: video exit $GV ($(grep -c PASS "$T/wsl/gpuvideo-test.log") PASS lines), fallback $GF, shared $GS, present $PT, present-fallback $PF, pair $PR; HDR V10-off exit $HT ($(grep -c ' -> PASS' "$T/wsl/hdr-test.log") PASS/$(grep -c ' -> FAIL' "$T/wsl/hdr-test.log") FAIL), V10-on exit $HT10 ($(grep -c ' -> PASS' "$T/wsl/hdr-test-v10on.log") PASS/$(grep -c ' -> FAIL' "$T/wsl/hdr-test-v10on.log") FAIL)"
[ "$GV" = 0 ] && [ "$GF" = 0 ] && [ "$GS" = 0 ] && [ "$PT" = 0 ] && [ "$PF" = 1 ] && [ "$PR" = 0 ] && [ "$HT" = 0 ] && [ "$HT10" = 0 ] || { st "GPU/HDR suites FAILED: $(grep -h FAIL "$T"/wsl/*-test*.log "$T"/wsl/*-fallback.log | head -5 | tr '\n' ' ' | cut -c1-600)"; exit 1; }
# ---------------------------------------------------------------- 1. the s3.4d base steps, on BOTH trees
base_steps(){ # $1 tree, $2 log dir
  local t="$1" L="$2"; mkdir -p "$L"
  python3 "$N/tools/apply_s3_webkit.py" "$t" > "$L/apply-webkit.log" 2>&1 || return 1
  python3 "$N/tools/apply_s31_pna.py" "$t" > "$L/apply-pna.log" 2>&1 || return 2
  for f in "$N"/engine-patches/entry/*; do cp "$f" "$t/engine/entry/" || return 3; done
  python3 "$N/tools/apply_viewtransition.py" "$t" > "$L/apply_vt.log" 2>&1 || return 4
  python3 "$N/tools/apply_yt.py" "$t" > "$L/apply_yt.log" 2>&1 || return 5
  python3 "$N/tools/apply_soak_read.py" "$t" > "$L/apply_soak.log" 2>&1 || return 6
}
title_base(){ # the s3.4d title-source steps (pointer-cross, CLEAN4 integration, dark x3, tree stats diff)
  local t="$1" L="$2"
  python3 "$N/tools/apply_pointer_cross.py" "$t" "$N/patches/pointer-cross.diff" > "$L/apply_pointer_cross.log" 2>&1 || return 11
  python3 "$N/tools/apply_s34_entry.py" "$t" > "$L/apply_s34_entry.log" 2>&1 || return 12
  python3 "$N/tools/apply_dark_video.py" "$t" > "$L/apply_dark_video.log" 2>&1 || return 13
  python3 "$N/tools/apply_dark_standard.py" "$t" > "$L/apply_dark_standard.log" 2>&1 || return 14
  python3 "$N/tools/apply_dark_emu.py" "$t" > "$L/apply_dark_emu.log" 2>&1 || return 15
  (cd "$t" && patch -p1 --forward --no-backup-if-mismatch < "$N/patches/hwservice-stats-tree.diff") > "$L/apply_hwservice_tree.log" 2>&1 || return 16
}
U_HDR(){ python3 "$N/tools/apply_hdr_caps.py" "$1" > "$2/apply_hdr_caps.log" 2>&1; }
U_JANK(){ OMNI_JANK_SRC="$J/src" OMNI_JANK_PATCHES="$3/patches-jank" python3 "$N/tools/apply_paint_hold.py" "$1" > "$2/apply_paint_hold.log" 2>&1 \
  && OMNI_JANK_SRC="$J/src" OMNI_JANK_PATCHES="$3/patches-jank" python3 "$N/tools/apply_jank.py" "$1" > "$2/apply_jank.log" 2>&1; }
U_ACK(){ OMNI_ACK_SRC="$A/src" OMNI_ACK_PATCHES="$3/patches-ack" python3 "$A/tools/apply_ack_title.py" "$1" > "$2/apply_ack_title.log" 2>&1; }
base_steps $TA "$MA" || { st "order A base steps FAILED (rc $?)"; exit 1; }
base_steps $TB "$MB" || { st "order B base steps FAILED (rc $?)"; exit 1; }
st "tree base (s3.4d child step) on A and B: $(ls "$N"/engine-patches/entry | wc -l) shell files, vt/yt/soak"
cd "$N" || exit 1
# ---------------------------------------------------------------- 2. the child from the UNPATCHED tree A: must be 7b810ea5
nice -n 5 ninja -k 0 -C $TA/build -j6 OmniEngine > "$N/ninja-child.log" 2>&1 || { st "ninja (child tree) FAILED: $(grep -m20 -E 'error:|FAILED' "$N/ninja-child.log" | tr '\n' ' ' | cut -c1-3000)"; exit 1; }
python3 "$N/make_link_command.py" > "$N/link-command-child.log" 2>&1 || { st "link command (child) FAILED"; exit 1; }
python3 "$N/child_build.py" > "$N/child-build.log" 2>&1 || { st "child FAILED: $(tail -3 "$N/child-build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
CH=$(sha256sum "$N/child/omni-engine-child.elf" | cut -d' ' -f1)
st "child from the unpatched tree: $CH"
[ "$CH" = 7b810ea5b5cdcbc899828635b329da42595b540ff51998513b7e8b21fd717c64 ] || { st "child is NOT 7b810ea5: stopping"; exit 1; }
# ---------------------------------------------------------------- 3. title sources: base, then the units in two orders
title_base $TA "$MA" || { st "order A title base FAILED (rc $?)"; exit 1; }
title_base $TB "$MB" || { st "order B title base FAILED (rc $?)"; exit 1; }
SH=$(sed 's/\r$//' $TA/engine/entry/OmniBrowser.cpp | sha256sum | cut -d' ' -f1); WANT=$(sed 's/\r$//' "$N/s34-entry/OmniBrowser.cpp" | sha256sum | cut -d' ' -f1)
[ "$SH" = "$WANT" ] || { st "baseline OmniBrowser.cpp ($SH) is not s3.4d's ($WANT): stopping"; exit 1; }
st "baseline OmniBrowser.cpp = s3.4d's ${WANT:0:12} on A; pointer-cross/s34/dark x3/stats applied on A and B"
# order A: HDR caps -> jank (paint-hold, jank) -> ack     order B: ack -> jank -> HDR caps
U_HDR $TA "$MA" || { st "A: OMNI_HDR_CAPS_V1 FAILED: $(tail -2 "$MA/apply_hdr_caps.log" | tr '\n' ' ')"; exit 1; }
U_JANK $TA "$MA" "$MA" || { st "A: jank FAILED: $(tail -2 "$MA"/apply_paint_hold.log "$MA"/apply_jank.log | tr '\n' ' ')"; exit 1; }
U_ACK $TA "$MA" "$MA" || { st "A: ack FAILED: $(tail -2 "$MA/apply_ack_title.log" | tr '\n' ' ')"; exit 1; }
U_ACK $TB "$MB" "$MB" || { st "B: ack FAILED: $(tail -2 "$MB/apply_ack_title.log" | tr '\n' ' ')"; exit 1; }
U_JANK $TB "$MB" "$MB" || { st "B: jank FAILED: $(tail -2 "$MB"/apply_paint_hold.log "$MB"/apply_jank.log | tr '\n' ' ')"; exit 1; }
U_HDR $TB "$MB" || { st "B: OMNI_HDR_CAPS_V1 FAILED: $(tail -2 "$MB/apply_hdr_caps.log" | tr '\n' ' ')"; exit 1; }
# compare every file either overlay changed (uppers, build/ excluded) between the two trees, byte for byte
: > "$N/merge/order-compare.txt"; NDIFF=0; NF=0
for f in $( (cd "$V_UPA" && find . -type f ! -path './build/*' ! -name '.launche*' ! -name 'link-command.json'; cd "$V_UPB" && find . -type f ! -path './build/*' ! -name '.launche*' ! -name 'link-command.json') | sort -u); do
  NF=$((NF+1)); a=$(sha256sum "$TA/$f" 2>/dev/null | cut -c1-64); b=$(sha256sum "$TB/$f" 2>/dev/null | cut -c1-64)
  if [ "$a" = "$b" ]; then echo "same $a $f" >> "$N/merge/order-compare.txt"; else echo "DIFF A=$a B=$b $f" >> "$N/merge/order-compare.txt"; NDIFF=$((NDIFF+1)); fi
done
for f in patches-jank/OmniBrowser.cpp.jank.diff patches-ack/ack-update.inc; do cmp -s "$MA/$f" "$MB/$f" && echo "same-inc $f" >> "$N/merge/order-compare.txt" || echo "DIFF-inc $f (diff context differs by base; informational)" >> "$N/merge/order-compare.txt"; done
st "ORDER PROOF (title tree): $NF changed files compared between order A (hdr,jank,ack) and order B (ack,jank,hdr): $NDIFF differ"
[ "$NDIFF" = 0 ] || { st "the title tree is NOT order-independent: stopping (see merge/order-compare.txt)"; exit 1; }
cp $TA/engine/entry/OmniBrowser.cpp "$N/merge/OmniBrowser-launch.cpp"; cp $TA/engine/entry/OmniDarkPages.h "$N/hosttest/wsl/OmniDarkPages.h"
cp $TA/webkit/Source/WebKit/UIProcess/CoordinatedGraphics/DrawingAreaProxyCoordinatedGraphics.cpp "$N/hosttest/wsl/"
# OmniBrowser.cpp = jank's text + exactly HDR caps' change: apply HDR caps to a copy of the jank build's file
HC=$(mktemp -d /tmp/launche-hc-XXXXXX); mkdir -p "$HC/engine/entry"; cp "$N/jank-OmniBrowser.cpp" "$HC/engine/entry/OmniBrowser.cpp"
python3 "$N/tools/apply_hdr_caps.py" "$HC" > "$N/merge/hdrcaps-on-jank.log" 2>&1 || { st "HDR caps on the jank build's OmniBrowser.cpp FAILED"; exit 1; }
X1=$(sed 's/\r$//' "$HC/engine/entry/OmniBrowser.cpp" | sha256sum | cut -c1-64); X2=$(sed 's/\r$//' $TA/engine/entry/OmniBrowser.cpp | sha256sum | cut -c1-64); rm -rf "$HC"
[ "$X1" = "$X2" ] || { st "OmniBrowser.cpp is not (jank build's file + OMNI_HDR_CAPS_V1): $X2 vs $X1: stopping"; exit 1; }
python3 "$J/tools/check_detector.py" $TA/engine/entry/OmniBrowser.cpp "$J/src/painthold-detector.js" > "$N/hosttest/wsl/detector.log" 2>&1 || { st "detector check FAILED"; exit 1; }
grep -q 'Video found — L2 to review' $TA/engine/entry/OmniBrowser.cpp || { st "the 'Video found —' string was corrupted: stopping"; exit 1; }
st "OmniBrowser.cpp ${X2:0:12} = jank build's file + OMNI_HDR_CAPS_V1 exactly (both orders); detector ok; ack: $(tail -1 "$MA/apply_ack_title.log" | cut -c1-80)"
# ---------------------------------------------------------------- 4. gates on the text that will be compiled
H=$(mktemp -d /tmp/launche-g-XXXXXX); : > "$H/jank.flag"
clang++ -std=c++17 -O1 -Wall -Wextra -Werror -I"$A/src" -I"$MA/patches-ack" -DOMNI_ACK_OFF_FLAG_PATH="\"$H/off.flag\"" -DOMNI_ACK_DIAG_FLAG_PATH="\"$H/jank.flag\"" \
  "$N/hosttest/ack_order_test.cpp" -o "$H/order" > "$N/hosttest/wsl/ack-order-build.log" 2>&1 || { st "ack order gate build FAILED"; exit 1; }
"$H/order" > "$N/hosttest/wsl/ack-order.log" 2>&1 || { st "ack order gate FAILED: $(tail -3 "$N/hosttest/wsl/ack-order.log" | tr '\n' ' ')"; exit 1; }
: > "$H/off.flag"; "$H/order" off > "$N/hosttest/wsl/ack-order-killswitch.log" 2>&1 || { st "ack order gate (kill switch) FAILED"; exit 1; }; rm -f "$H/off.flag"
python3 "$A/analyze_ack.py" --selftest > "$N/hosttest/wsl/analyze-ack-selftest.log" 2>&1 || { st "analyze_ack selftest FAILED"; exit 1; }
E=$TA/engine/entry; cp "$E/OmniFeaturesPanel.h" "$N/hosttest/wsl/" 2>/dev/null
clang++ -std=c++17 -O1 -g -Wall -Wextra -Wno-unused-function -fsanitize=address,undefined -fno-omit-frame-pointer -I"$E" "$N/hosttest/pointer_cross_test_s34.cpp" -o "$H/pct" > "$N/hosttest/wsl/pointer-cross-s34-build.log" 2>&1 \
  && "$H/pct" "$E/OmniBrowser.cpp" "$E/OmniFeaturesPanel.h" > "$N/hosttest/wsl/pointer-cross-s34.log" 2>&1
grep -q ": PASS$" "$N/hosttest/wsl/pointer-cross-s34.log" || { st "pointer-cross gate on the merged files FAILED"; exit 1; }
rm -rf "$H"
st "gates: ack order $(tail -1 "$N/hosttest/wsl/ack-order.log"); kill switch $(tail -1 "$N/hosttest/wsl/ack-order-killswitch.log"); pointer-cross $(tail -1 "$N/hosttest/wsl/pointer-cross-s34.log"); node gates (dark x3, hdr_caps) run on the PC from hosttest/wsl copies"
# ---------------------------------------------------------------- 5. the title
nice -n 5 ninja -k 0 -C $TA/build -j6 OmniEngine > "$N/ninja.log" 2>&1 || { st "ninja FAILED: $(grep -m20 -E 'error:|FAILED' "$N/ninja.log" | tr '\n' ' ' | cut -c1-3000)"; exit 1; }
st "ninja ok: $(grep -c '^\[' "$N/ninja.log") steps, $(grep -c 'warning:' "$N/ninja.log") warnings; ack/jank/hdr warnings: $(grep -E 'omniAck|OmniAck|OmniJank|OmniPaintHold|HDR_CAPS' "$N/ninja.log" | grep -c 'warning:')"
python3 "$N/make_link_command.py" > "$N/link-command.log" 2>&1 || { st "link command FAILED"; exit 1; }
python3 "$N/tools/prep_launch.py" > "$N/prep.log" 2>&1 || { st "prep FAILED: $(tail -2 "$N/prep.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "prep ok: $(grep -E '^compiled|^link command' "$N/prep.log" | tr '\n' ' ' | cut -c1-300); warnings OmniHwService $(grep -c 'warning:' "$N/compile-OmniHwService.cpp.log"), OmniGpuVideo $(grep -c 'warning:' "$N/compile-OmniGpuVideo.cpp.log")"
nice -n 5 python3 "$N/build.py" > "$N/build.log" 2>&1 || { st "title FAILED: $(tail -4 "$N/build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "title ok: $(grep -o 'eboot.bin [0-9a-f]*' "$N/build.log" | tail -1); $(grep -o 'pages packaged: [0-9]* files' "$N/build.log")"
st "packaging guards: $(grep -E 'layout check|import check|LOAD|exec' "$N/build.log" | tr '\n' ' ' | cut -c1-500)"
# ---------------------------------------------------------------- 6. checks + union proof
C="$N/child/omni-engine-child.elf"; T="$N/build/eboot.elf"; : > "$N/checks.txt"
while IFS= read -r k; do [ -n "$k" ] && printf "title  %-44s %s\n" "$k" "$(grep -c -a -- "$k" "$T")" >> "$N/checks.txt"; done < "$O/omni-launch/tools/keys-title.txt"
/usr/lib/llvm-21/bin/llvm-nm "$N/build/llvm-pie.elf" 2>/dev/null | grep -E " [tTwW] (__wrap_SDL_FreeSurface|__wrap_SDL_Init|omni_gpu_present_forget|omni_hw_video_counters|omni_gpu_video_preinit|omni_gpu_video_stats|__emutls_get_address|omni_gpu_present_hdr_state|omni_gpu_present_stage_video_hdr|omni_gpu_video_stats3|exbox_presenter_probe)$" >> "$N/checks.txt"
grep -E "param.json attribute|HDR bit|layout check|layout \(llvm" "$N/build.log" >> "$N/checks.txt"
python3 -c "import json,sys; a=json.load(open(sys.argv[1]))['attribute']; print('package param.json attribute 0x%08x HDR bit %s' % (a, 'SET' if a & 0x20000000 else 'MISSING'))" "$N/out/PPSA99732/sce_sys/param.json" >> "$N/checks.txt"
echo "child (unpatched tree) = 7b810ea5: $CH" >> "$N/checks.txt"; echo "OmniBrowser.cpp = jank build's + OMNI_HDR_CAPS_V1: $X2" >> "$N/checks.txt"
sha256sum "$N/out/PPSA99732/eboot.bin" "$T" "$N/build/llvm-pie.elf" "$C" "$N/out/PPSA99732/sce_sys/param.json" "$N/out/PPSA99732/sce_module/libc.prx" >> "$N/checks.txt" 2>&1
# union: launch = s3.4d + (ack - s3.4d) + (abr - s3.4d) + (hdr-p10 - s3.4d)   [ack = s3.4d + jank + ack; hdr-p10 = s3.5-hdr + verify10 + present10]
python3 "$O/omni-launch/tools/additivity.py" --label title --keys "$O/omni-launch/tools/keys-title.txt" --out "$N/union" \
  --target "$N/build/llvm-pie.elf" --base "$D4/build/llvm-pie.elf" \
  --plus "$O/omni-ack-eboot/build/llvm-pie.elf" --plus "$O/omni-native-s3.4-abr/build/llvm-pie.elf" --plus "$O/omni-native-s3.5-hdr-p10/build/llvm-pie.elf" \
  --minus "$D4/build/llvm-pie.elf" --minus "$D4/build/llvm-pie.elf" --minus "$D4/build/llvm-pie.elf" > "$N/union/additivity-title.log" 2>&1; UR=$?
st "UNION (title): $(grep '^RESULT' "$N/union/additivity-title.log") (exit $UR)"
# copy everything back into omni-launch/eboot and compare the shipped/linked files byte for byte
rm -rf "$NR/build" "$NR/out" "$NR/child" && cp -a "$N/." "$NR/" 2>/dev/null; CB=0
for f in out/PPSA99732/eboot.bin build/eboot.elf build/llvm-pie.elf child/omni-engine-child.elf out/PPSA99732/sce_sys/param.json; do cmp -s "$N/$f" "$NR/$f" || CB=$((CB+1)); done
st "results copied from the ext4 workspace into omni-launch/eboot: $CB of 5 shipped/linked files differ after the copy"
[ "$CB" = 0 ] || { st "the copy in outputs differs from the ext4 build: do NOT use it"; exit 1; }
st "checks written: eboot.bin $(sha256sum "$NR/out/PPSA99732/eboot.bin" | cut -c1-64)"
IN
sed -i 's/\r$//' /tmp/launche-inner-$$.sh; chmod 755 /tmp/launche-inner-$$.sh
cat > /tmp/launche-outer-$$.sh <<'OUT'
#!/bin/bash
cd /
L=/tmp/omni-launch-eboot.lock; ( umask 0; : >> "$L" ) 2>/dev/null; exec 9<"$L"; flock -n 9 || { echo "another omni-launch eboot build is running"; exit 0; }
N='/path/to/workspace/outputs/omni-launch/eboot'
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$N/build-steps.txt"; }
U=${V_REAL_UID:-$(id -u)}
UPA=/home/builder/launche-up-$U; WKA=/home/builder/launche-work-$U; UPB=/home/builder/launcheb-up-$U; WKB=/home/builder/launcheb-work-$U; MB=/home/builder/launcheb-mnt
[ -e /home/builder/s3/.s3-marker ] || { st "/home/builder/s3 missing: stopping"; exit 1; }
rm -rf "$UPA" "$WKA" "$UPB" "$WKB"; mkdir -p "$UPA" "$WKA" "$UPB" "$WKB" "$MB" /home/builder/launchobjs
if [ -z "$(ls -A /home/builder/launchobjs 2>/dev/null)" ] && [ -d /home/builder/s35objs ]; then cp -a /home/builder/s35objs/. /home/builder/launchobjs/; st "objects: launchobjs seeded by copying s35objs (s35objs only read)"; fi
[ -n "$V_AS_BUILDER" ] && chown -R builder:builder "$UPA" "$WKA" "$UPB" "$WKB" "$MB" /home/builder/launchobjs
st "disk: $(df -h /home/builder | tail -1 | awk '{print $4" free"}')"
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UPA,workdir=$WKA" /home/builder/s1 2>/tmp/launche-ovl-$U.err || { st "overlay A failed ($(cat /tmp/launche-ovl-$U.err)): stopping"; exit 1; }
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UPB,workdir=$WKB" "$MB" 2>/tmp/launcheb-ovl-$U.err || { st "overlay B failed ($(cat /tmp/launcheb-ovl-$U.err)): stopping"; exit 1; }
st "overlays mounted: A on /home/builder/s1 (changes in $UPA), B on $MB (changes in $UPB); s3 read-only"
touch /home/builder/s1/.launche-marker "$MB/.launcheb-marker" || { st "trees not writable"; exit 1; }
# the build works in an ext4 copy of omni-launch/eboot (large links written straight onto /mnt/c have come back
# corrupted for another build); the copy is bound at outputs/omni-launch-eboot-bind so the inherited tools still find
# their sibling folders, and the results are copied back into omni-launch/eboot and compared at the end
WS=/home/builder/launche-ws-$U; rm -rf "$WS"; mkdir -p "$WS" && cp -a "$N/." "$WS/" || { st "ext4 workspace copy failed: stopping"; exit 1; }
rm -rf "$WS/build" "$WS/out" "$WS/child"; : > "$WS/build-steps.txt"; [ -n "$V_AS_BUILDER" ] && chown -R builder:builder "$WS"
BIND='/path/to/workspace/outputs/omni-launch-eboot-bind'; mkdir -p "$BIND"
mount --bind "$WS" "$BIND" || { st "bind mount of the workspace failed: stopping"; exit 1; }
st "workspace: ext4 copy $WS of omni-launch/eboot, bound at outputs/omni-launch-eboot-bind (this namespace only)"
export V_NREAL="$N"
export V_UPA="$UPA" V_UPB="$UPB"
if [ -n "$V_AS_BUILDER" ]; then exec runuser -u builder -- bash "$V_INNER"; fi
bash "$V_INNER"
OUT
sed -i 's/\r$//' /tmp/launche-outer-$$.sh; chmod 755 /tmp/launche-outer-$$.sh
mkdir -p "$N/merge" "$N/union"
cd /
if [ "$(id -u)" = 0 ]; then
  V_REAL_UID=0 V_AS_BUILDER=1 V_INNER=/tmp/launche-inner-$$.sh setsid nohup unshare -m --propagation private bash /tmp/launche-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
else
  V_REAL_UID=$(id -u) V_INNER=/tmp/launche-inner-$$.sh setsid nohup unshare -Urm --propagation private bash /tmp/launche-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
fi
echo "omni-launch eboot build started pid $!"
