#!/bin/bash
# s3.4d = s3.4c + OMNI_DARK_APPEARANCE_EMU_V1 (the page sees prefers-color-scheme: dark through matchMedia when Dark mode
# is on for it; the real WebKit setting does not reach the page in this engine).
# s3.4c = s3.4b + omni-video-4k60 patches 01-03 + 05 (OMNI_GPU_VIDEO_V3 in-place read + shared RADV device,
# OMNI_GPU_PRESENT_V3 queue lock/share/FPS_V2 merged 3-way with the CLEAN4 presenter, OMNI_HOLE_ELIGIBILITY_PROBE_V1 in
# the YTTL dump); its 04 (dark) is not used: OMNI_DARK_VIDEO_PLANE_V1 + OMNI_DARK_STANDARD_V1 cover it.
# s3.4b = s3.4 + OMNI_DARK_STANDARD_V1 (Dark mode the standard way: the page's own dark theme first, the invert filter
# last, the Dark Reader add-on hook) + a "dark" field in the YTTL snapshot. s3.4 = s3.3 (s3.2-video's V2 video stack + OMNI_POINTER_CROSS_V1) + Astra's CLEAN4 integration (integration.diff's
# engine/entry + engine/media + src-title parts: native quick bar/Options/Apps, media stats + HDR-preference bridge,
# downloads readiness C-1, card ports C-2) + OMNI_DARK_VIDEO_PLANE_V1 (the YouTube start stall: the dark-page filter
# steps aside while a large video plays) + the two-entry SDL import cache and region reuse (presenter) + the YTTL fps
# probe (OmniBrowser 3-way merge) + Astra's final pages. TITLE ONLY: the child is linked from the unpatched tree first
# and must be byte-identical to s3.1b/s3.1c's 7b810ea5 (checked; the build stops otherwise). PRIVATE overlay:
# /home/builder/s3 read-only lower, changes in /home/builder/s34d-up-<uid>, mounted on /home/builder/s1 in a private mount
# namespace; GPU objects go to /home/builder/s34dobjs. s3, s3.1c, s3.3 and their objects are never written. Build only:
# never deploys, never touches the console. Progress: outputs/omni-native-s3.4d/build-steps.txt
O='/path/to/workspace/outputs'; N="$O/omni-native-s3.4d"
cat > /tmp/s34d-inner-$$.sh <<'IN'
#!/bin/bash
O='/path/to/workspace/outputs'; N="$O/omni-native-s3.4d"; B="$O/omni-native-s3.1c"
VKH='/path/to/workspace/nxe-ps5/bigapp/private/av2/upstream/PS5_Mesa/include'
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$N/build-steps.txt"; }
export OMNI_SECLIBS=/home/builder/omni-seclibs/stage/user/homebrew/lib
[ -e /home/builder/s1/.s34d-marker ] || { st "overlay missing: refusing to build in the shared s1 tree"; exit 1; }
st "build start (tree /home/builder/s1 = private overlay of s3)"
# 0. host regression tests first (clang, ASan+UBSan): fail fast
CRYPTO=-lcrypto; [ -e /usr/lib/x86_64-linux-gnu/libcrypto.so ] || CRYPTO=-l:libcrypto.so.3
H=$(mktemp -d); mkdir -p "$N/hosttest/wsl"
clang++ -std=c++17 -O1 -g -U_FORTIFY_SOURCE -fsanitize=address,undefined -fno-omit-frame-pointer -I"$N/child-src" -DOMNI_HUB_DIR='"/tmp/no-hub"' \
  "$N/hosttest/sec_connect_test.cpp" "$N/child-src/omni-sec-connect.cpp" -o "$H/sec" -pthread > "$N/hosttest/wsl/sec-build.log" 2>&1 && "$H/sec" > "$N/hosttest/wsl/sec-connect.log" 2>&1 \
  || { st "OS-001 host test FAILED: $(tail -2 "$N/hosttest/wsl/sec-connect.log" "$N/hosttest/wsl/sec-build.log" | tr '\n' ' ' | cut -c1-400)"; exit 1; }
clang++ -std=c++17 -O1 -g -U_FORTIFY_SOURCE -fsanitize=address,undefined -fno-omit-frame-pointer -I"$N/engine-patches/entry" "$N/hosttest/vault_os002_test.cpp" -o "$H/vos" $CRYPTO > "$N/hosttest/wsl/vault-build.log" 2>&1 \
  && (cd "$H" && ./vos) > "$N/hosttest/wsl/vault-os002.log" 2>&1 || { st "OS-002 host test FAILED: $(tail -2 "$N/hosttest/wsl/vault-os002.log" | tr '\n' ' ')"; exit 1; }
tar --no-same-owner -C "$H" -xzf "$O/omni-native-s3/s3-hosttest.tgz" && clang++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -I"$N/engine-patches/entry" \
  "$H/s3t/tests/vault_test.cpp" -o "$H/vt" $CRYPTO > "$N/hosttest/wsl/vault-suite-build.log" 2>&1 && "$H/vt" > "$N/hosttest/wsl/vault-suite.log" 2>&1 \
  || { st "existing vault suite FAILED: $(tail -2 "$N/hosttest/wsl/vault-suite.log" | tr '\n' ' ')"; exit 1; }
/opt/ps5-payload-sdk/bin/prospero-clang++ -std=c++17 -O2 -Wall -Wextra -Werror -c "$N/child-src/omni-sec-connect.cpp" -o "$H/sec.o" > "$N/hosttest/wsl/sec-sdk-compile.log" 2>&1 \
  || { st "omni-sec-connect.cpp SDK compile FAILED: $(head -5 "$N/hosttest/wsl/sec-sdk-compile.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "host tests: $(tail -1 "$N/hosttest/wsl/sec-connect.log"); $(tail -1 "$N/hosttest/wsl/vault-os002.log"); $(tail -1 "$N/hosttest/wsl/vault-suite.log"); SDK compile ok"
# 0b. s3.2: the GPU video path on lavapipe (software Vulkan; host timings are not PS5 figures)
LVP=/usr/share/vulkan/icd.d/lvp_icd.json; H=$(mktemp -d); T="$N/hosttest"
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_VIDEO_HOST_TEST -isystem "$VKH" -I"$N/engine/media" "$T/gpuvideo_test.cpp" "$N/engine/media/OmniGpuVideo.cpp" \
  -o "$H/gvt" -l:libvulkan.so.1 -lswscale -lavutil -pthread > "$T/wsl/gpuvideo-build.log" 2>&1 || { st "gpuvideo test build FAILED: $(head -5 "$T/wsl/gpuvideo-build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_VIDEO_HOST_TEST -DOMNI_GPU_PRESENT_HOST_TEST -DOMNI_SHARED_TEST -isystem "$VKH" -I"$N/engine/media" -I"$N/src-title" "$T/gpuvideo_test.cpp" \
  "$N/engine/media/OmniGpuVideo.cpp" "$N/src-title/OmniGpuPresent.cpp" -o "$H/gvs" -l:libvulkan.so.1 -lswscale -lavutil -pthread > "$T/wsl/shared-build.log" 2>&1 || { st "shared-device test build FAILED: $(head -5 "$T/wsl/shared-build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
clang++ -std=c++17 -O2 -g -Wall -Wextra -DOMNI_GPU_PRESENT_HOST_TEST -isystem "$VKH" -I"$N/src-title" "$T/present_test.cpp" "$N/src-title/OmniGpuPresent.cpp" \
  -o "$H/pt" -l:libvulkan.so.1 -pthread > "$T/wsl/present-build.log" 2>&1 || { st "present test build FAILED: $(head -5 "$T/wsl/present-build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
clang++ -std=c++17 -O2 -g -DOMNI_GPU_PRESENT_HOST_TEST -isystem "$VKH" -I"$N/src-title" -I"$T" "$T/pair_test.cpp" "$N/src-title/OmniGpuPresent.cpp" \
  -o "$H/pair" -l:libvulkan.so.1 -pthread > "$T/wsl/pair-build.log" 2>&1 || { st "pair test build FAILED: $(head -5 "$T/wsl/pair-build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
mkdir -p "$H/run" && cd "$H/run" || exit 1
{ echo "# OmniGpuVideo V3 host test, $(date -u +%FT%TZ), $(uname -r), ICD $LVP"; VK_ICD_FILENAMES=$LVP timeout 2400 "$H/gvt" all 10000; } > "$T/wsl/gpuvideo-test.log" 2>&1; GV=$?
{ echo "# fallback (no Vulkan ICD; then the flag word failsetup on lavapipe)"; VK_ICD_FILENAMES=/nonexistent.json timeout 120 "$H/gvt" F && VK_ICD_FILENAMES=$LVP timeout 120 "$H/gvt" W; } > "$T/wsl/gpuvideo-fallback.log" 2>&1; GF=$?
{ echo "# shared device (present + video, one VkDevice)"; VK_ICD_FILENAMES=$LVP timeout 900 "$H/gvs" S; } > "$T/wsl/shared-test.log" 2>&1; GS=$?
VK_ICD_FILENAMES=$LVP timeout 2400 "$H/pt" all 10000 > "$H/pt.out" 2>&1; PT=$?; { echo "# OmniGpuPresent V3 host test, $(date -u +%FT%TZ)"; grep -v '^gpu-present:' "$H/pt.out"; } > "$T/wsl/present-test.log"
VK_ICD_FILENAMES=/nonexistent.json timeout 120 "$H/pt" F > "$H/pf.out" 2>&1; { echo "# OmniGpuPresent V3 fallback (no Vulkan ICD)"; grep -v '^gpu-present:' "$H/pf.out"; } > "$T/wsl/present-fallback.log"
PF=$(grep -c 'F no Vulkan ICD.*PASS' "$T/wsl/present-fallback.log")
VK_ICD_FILENAMES=$LVP timeout 600 "$H/pair" > "$H/pair.out" 2>&1; PR=$?; grep -v '^gpu-present:' "$H/pair.out" > "$T/wsl/pair-test.log"
cp -f "$H/run/gpu-video.log" "$T/wsl/gpu-video.log" 2>/dev/null; cp -f "$H/run/gpu-present.log" "$T/wsl/gpu-present.log" 2>/dev/null
cd / ; rm -rf "$H"
st "GPU host tests (lavapipe): video exit $GV ($(grep -c PASS "$T/wsl/gpuvideo-test.log") PASS lines), fallback exit $GF, shared exit $GS, present exit $PT, present fallback $PF, pair exit $PR"
[ "$GV" = 0 ] && [ "$GF" = 0 ] && [ "$GS" = 0 ] && [ "$PT" = 0 ] && [ "$PF" = 1 ] && [ "$PR" = 0 ] || { st "GPU host tests FAILED: $(grep -h FAIL "$T"/wsl/*-test.log "$T"/wsl/*-fallback.log | head -5 | tr '\n' ' ' | cut -c1-600)"; exit 1; }
# 1. WebKit: s3's patches (already in the lower tree: idempotent) + OMNI_SEC_PNA_CONNECT_V1
python3 "$N/tools/apply_s3_webkit.py" /home/builder/s1 > "$N/apply-webkit.log" 2>&1 || { st "s3 webkit apply FAILED: $(tail -3 "$N/apply-webkit.log" | tr '\n' ' ')"; exit 1; }
python3 "$N/tools/apply_s31_pna.py" /home/builder/s1 > "$N/apply-pna.log" 2>&1 || { st "PNA webkit apply FAILED: $(tail -3 "$N/apply-pna.log" | tr '\n' ' ')"; exit 1; }
st "webkit: s3 $(grep -c '^already' "$N/apply-webkit.log") already / $(grep -c '^patched' "$N/apply-webkit.log") patched; PNA $(grep -c '^patched' "$N/apply-pna.log") patched, $(grep -c '^already' "$N/apply-pna.log") already"
# 2. shell sources: s3's engine-patches + s3.1's OmniVault.h (OS-002) + jit2's OmniCrash.h (OMNI_CRASH_V2)
for f in "$N"/engine-patches/entry/*; do cp "$f" /home/builder/s1/engine/entry/ || { st "copy FAILED $f"; exit 1; }; done
st "shell sources copied: $(ls "$N"/engine-patches/entry | wc -l) files"
python3 "$N/tools/apply_viewtransition.py" /home/builder/s1 > "$N/apply_vt.log" 2>&1 || { st "view-transition patch FAILED: $(tail -1 "$N/apply_vt.log")"; exit 1; }
python3 "$N/tools/apply_yt.py" /home/builder/s1 > "$N/apply_yt.log" 2>&1 || { st "apply_yt FAILED: $(tail -2 "$N/apply_yt.log" | tr '\n' ' ')"; exit 1; }
python3 "$N/tools/apply_soak_read.py" /home/builder/s1 > "$N/apply_soak.log" 2>&1 || { st "soak-read patch FAILED: $(tail -1 "$N/apply_soak.log")"; exit 1; }
st "s3.1b engine changes: $(tail -1 "$N/apply_vt.log" | cut -c1-80); $(tail -1 "$N/apply_yt.log" | cut -c1-80); $(tail -1 "$N/apply_soak.log" | cut -c1-80)"
cd "$N" || exit 1
# 3. the child from the UNPATCHED tree (= s3.1b/s3.1c/s3.3's child 7b810ea5)
nice -n 5 ninja -k 0 -C /home/builder/s1/build -j6 OmniEngine > "$N/ninja-child.log" 2>&1 || { st "ninja (child tree) FAILED: $(grep -m20 -E 'error:|FAILED' "$N/ninja-child.log" | tr '\n' ' ' | cut -c1-3000)"; exit 1; }
python3 "$N/make_link_command.py" > "$N/link-command-child.log" 2>&1 || { st "link command (child) FAILED"; exit 1; }
python3 "$N/child_build.py" > "$N/child-build.log" 2>&1 || { st "child FAILED: $(tail -3 "$N/child-build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
CH=$(sha256sum "$N/child/omni-engine-child.elf" | cut -d' ' -f1); BH=$(sha256sum "$B/child/omni-engine-child.elf" | cut -d' ' -f1)
st "child ok (unpatched tree, ninja $(grep -c '^\[' "$N/ninja-child.log") steps): $CH; s3.1c child $BH: $([ "$CH" = "$BH" ] && echo IDENTICAL || echo DIFFERENT)"
[ "$CH" = "$BH" ] && [ "$CH" = 7b810ea5b5cdcbc899828635b329da42595b540ff51998513b7e8b21fd717c64 ] || { st "child is NOT 7b810ea5: stopping (the child must stay byte-identical)"; exit 1; }
# 4. OMNI_POINTER_CROSS_V1 + its host test (against the patched tree's files)
python3 "$N/tools/apply_pointer_cross.py" /home/builder/s1 "$N/patches/pointer-cross.diff" > "$N/apply_pointer_cross.log" 2>&1 || { st "pointer-cross patch FAILED: $(tail -3 "$N/apply_pointer_cross.log" | tr '\n' ' ')"; exit 1; }
st "OMNI_POINTER_CROSS_V1: $(tail -1 "$N/apply_pointer_cross.log")"
H=$(mktemp -d); E=/home/builder/s1/engine/entry; cp "$E/OmniBrowser.cpp" "$E/OmniFeaturesPanel.h" "$E/OmniPointerCross.h" "$N/hosttest/wsl/" 2>/dev/null
clang++ -std=c++17 -O1 -g -Wall -Wextra -Wno-unused-function -fsanitize=address,undefined -fno-omit-frame-pointer -I"$E" "$N/hosttest/pointer_cross_test.cpp" -o "$H/pct" > "$N/hosttest/wsl/pointer-cross-build.log" 2>&1 \
  && "$H/pct" "$E/OmniBrowser.cpp" "$E/OmniFeaturesPanel.h" > "$N/hosttest/wsl/pointer-cross.log" 2>&1 \
  || { st "pointer-cross host test FAILED: $(grep -h FAIL "$N/hosttest/wsl/pointer-cross.log" | head -3 | tr '\n' ' '; tail -3 "$N/hosttest/wsl/pointer-cross-build.log" | tr '\n' ' ' | cut -c1-400)"; exit 1; }
st "pointer-cross host test: $(tail -1 "$N/hosttest/wsl/pointer-cross.log")"
rm -rf "$H"
# 4b. s3.4: the CLEAN4 integration (each tree file must equal its pinned baseline first) + OMNI_DARK_VIDEO_PLANE_V1
python3 "$N/tools/apply_s34_entry.py" /home/builder/s1 > "$N/apply_s34_entry.log" 2>&1 || { st "s3.4 integration FAILED: $(tail -3 "$N/apply_s34_entry.log" | tr '\n' ' ')"; exit 1; }
python3 "$N/tools/apply_dark_video.py" /home/builder/s1 > "$N/apply_dark_video.log" 2>&1 || { st "dark-video patch FAILED: $(tail -2 "$N/apply_dark_video.log" | tr '\n' ' ')"; exit 1; }
python3 "$N/tools/apply_dark_standard.py" /home/builder/s1 > "$N/apply_dark_standard.log" 2>&1 || { st "dark-standard patch FAILED: $(tail -2 "$N/apply_dark_standard.log" | tr '\n' ' ')"; exit 1; }
python3 "$N/tools/apply_dark_emu.py" /home/builder/s1 > "$N/apply_dark_emu.log" 2>&1 || { st "dark-emu patch FAILED: $(tail -2 "$N/apply_dark_emu.log" | tr '\n' ' ')"; exit 1; }
cp /home/builder/s1/engine/entry/OmniDarkPages.h "$N/hosttest/wsl/OmniDarkPages.h"
# the in-tree link needs the integration's two stats entry points in the tree's own (s3) OmniHwService.cpp too; the
# title's real copy is still prep_s34's (V2 + integration, compiled from omni-native-s3.4d/engine/media)
(cd /home/builder/s1 && patch -p1 --forward --no-backup-if-mismatch < "$N/patches/hwservice-stats-tree.diff") > "$N/apply_hwservice_tree.log" 2>&1 || { st "tree OmniHwService stats patch FAILED: $(tail -3 "$N/apply_hwservice_tree.log" | tr '\n' ' ')"; exit 1; }
st "s3.4 sources: $(tail -1 "$N/apply_s34_entry.log"); $(tail -1 "$N/apply_dark_video.log" | cut -c1-60); $(tail -1 "$N/apply_dark_standard.log" | cut -c1-60); $(tail -1 "$N/apply_dark_emu.log" | cut -c1-60)"
if command -v node >/dev/null; then node "$N/hosttest/dark_video_test.js" "$N/hosttest/wsl/OmniDarkPages.h" > "$N/hosttest/wsl/dark-video.log" 2>&1 || { st "dark-video host test FAILED: $(grep FAIL "$N/hosttest/wsl/dark-video.log" | head -3 | tr '\n' ' ')"; exit 1; }
  st "dark-video host test: $(tail -1 "$N/hosttest/wsl/dark-video.log")"; else st "dark-video host test: node not in WSL (run on the PC: hosttest/pc/)"; fi
H=$(mktemp -d); E=/home/builder/s1/engine/entry; cp "$E/OmniBrowser.cpp" "$E/OmniFeaturesPanel.h" "$N/hosttest/wsl/" 2>/dev/null
clang++ -std=c++17 -O1 -g -Wall -Wextra -Wno-unused-function -fsanitize=address,undefined -fno-omit-frame-pointer -I"$E" "$N/hosttest/pointer_cross_test_s34.cpp" -o "$H/pct" > "$N/hosttest/wsl/pointer-cross-s34-build.log" 2>&1 \
  && "$H/pct" "$E/OmniBrowser.cpp" "$E/OmniFeaturesPanel.h" > "$N/hosttest/wsl/pointer-cross-s34.log" 2>&1
grep -q ": PASS$" "$N/hosttest/wsl/pointer-cross-s34.log" || { st "pointer-cross host test on the s3.4 files FAILED: $(grep FAIL "$N/hosttest/wsl/pointer-cross-s34.log" | head -3 | tr '\n' ' ')"; exit 1; }
st "pointer-cross host test on the s3.4 files: $(tail -1 "$N/hosttest/wsl/pointer-cross-s34.log" 2>/dev/null)"
rm -rf "$H"
# 5. the title from the patched tree
nice -n 5 ninja -k 0 -C /home/builder/s1/build -j6 OmniEngine > "$N/ninja.log" 2>&1 || { st "ninja FAILED: $(grep -m20 -E 'error:|FAILED' "$N/ninja.log" | tr '\n' ' ' | cut -c1-3000)"; exit 1; }
st "ninja ok: $(grep -c '^\[' "$N/ninja.log") steps, $(grep -c 'warning:' "$N/ninja.log") warnings; pointer-cross warnings: $(grep -E 'OmniPointerCross|OmniFeaturesPanel' "$N/ninja.log" | grep -c 'warning:')"
python3 "$N/make_link_command.py" > "$N/link-command.log" 2>&1 || { st "link command FAILED"; exit 1; }
python3 "$N/tools/prep_s34.py" > "$N/prep.log" 2>&1 || { st "prep FAILED: $(tail -2 "$N/prep.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "prep ok: $(grep -E '^compiled|^link command' "$N/prep.log" | tr '\n' ' ' | cut -c1-300); warnings OmniHwService $(grep -c 'warning:' "$N/compile-OmniHwService.cpp.log"), OmniGpuVideo $(grep -c 'warning:' "$N/compile-OmniGpuVideo.cpp.log")"
nice -n 5 python3 "$N/build.py" > "$N/build.log" 2>&1 || { st "title FAILED: $(tail -4 "$N/build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "title ok: $(grep -o 'eboot.bin [0-9a-f]*' "$N/build.log" | tail -1); $(grep -o 'pages packaged: [0-9]* files' "$N/build.log")"
C="$N/child/omni-engine-child.elf"; T="$N/build/eboot.elf"; : > "$N/checks.txt"
for k in "OMNI_POINTER_CROSS_V1" "accelerated compositing is off" "OMNI_SEC_PNA_CONNECT_V1" "OMNI_CRASH_V2" "FATAL end of report" "OMNI_JSC_JIT_V3" "jit: off (interpreter)" "OMNI_SEC_REDIRECT_V1" "OMNI_SEC_PNA_V1" "OMNI_SEC_LOCALHOST_V1" "close-events.log" "OpenSSL 3.5.9" "8.23.0"; do
  printf "child  %-44s %s\n" "$k" "$(grep -c -a -- "$k" "$C")" >> "$N/checks.txt"; done
for k in "mediaSoon" "OMNI_MQ_NATIVE_V1" "video-hdr-preference.txt" "OMNI_VIDEO_STATS_BRIDGE_V1" "HDR Auto pending source passthrough" "/data/hub/apps/" "OMNI_POINTER_CROSS_V1" "OMNI_GPU_VIDEO_V2" "OMNI_GPU_PRESENT_V2" "OMNI_VIDEO_FPS_V1" "/data/omni/native/video-fps.log" "preinit: RADV set-up now" "HDR self-test" "HDR10_ST2084" "the SDL window surface is freed" \
         "verify %d-bit %dx%d -> %dx%d (%s)" "layers imported once" "failsetup" "YTTL DONE" "OMNI_CRASH_V2" "FATAL end of report" "OMNI_PAGES_V1" "omni://pages" "OMNI_ADDONS_V1 ready" "OMNI_VAULT_V2" "OMNI_HUB_CARDS_V1" "Bloom Core is not running" "PADCTL TEST PASS" "Ad block"; do
  printf "title  %-44s %s\n" "$k" "$(grep -c -a -- "$k" "$T")" >> "$N/checks.txt"; done
/usr/lib/llvm-21/bin/llvm-nm "$N/build/llvm-pie.elf" 2>/dev/null | grep -E " [tTwW] (__wrap_SDL_FreeSurface|__wrap_SDL_Init|omni_gpu_present_forget|omni_hw_video_counters|omni_gpu_video_preinit|omni_gpu_video_stats|__emutls_get_address)$" >> "$N/checks.txt"
/usr/lib/llvm-21/bin/llvm-nm "$N/child/omni-engine-child-unstripped.elf" 2>/dev/null | grep -E " [tTwW] (__wrap_connect|omniSecConnectContext)$" >> "$N/checks.txt"
grep -E "layout check|layout \(llvm" "$N/build.log" >> "$N/checks.txt"
echo "child vs s3.1c: $CH / $BH $([ "$CH" = "$BH" ] && echo IDENTICAL || echo DIFFERENT)" >> "$N/checks.txt"
sha256sum "$N/out/PPSA99732/eboot.bin" "$T" "$C" "$N/out/PPSA99732/sce_sys/param.json" "$N/out/PPSA99732/sce_module/libc.prx" >> "$N/checks.txt" 2>&1
st "checks written"
IN
sed -i 's/\r$//' /tmp/s34d-inner-$$.sh; chmod 755 /tmp/s34d-inner-$$.sh
cat > /tmp/s34d-outer-$$.sh <<'OUT'
#!/bin/bash
cd /
L=/tmp/omni-s34d.lock; ( umask 0; : >> "$L" ) 2>/dev/null; exec 9<"$L"; flock -n 9 || { echo "another s3.4d build is running"; exit 0; }
N='/path/to/workspace/outputs/omni-native-s3.4d'
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$N/build-steps.txt"; }
U=${V_REAL_UID:-$(id -u)}; UP=/home/builder/s34d-up-$U; WK=/home/builder/s34d-work-$U
[ -e /home/builder/s3/.s3-marker ] || { st "/home/builder/s3 missing: stopping"; exit 1; }
rm -rf "$UP" "$WK"; mkdir -p "$UP" "$WK" /home/builder/s34dobjs;   # every build starts from s3 plus this folder's changes only
 [ -n "$V_AS_BUILDER" ] && chown builder:builder "$UP" "$WK" /home/builder/s34dobjs
st "disk: $(df -h /home/builder | tail -1 | awk '{print $4" free"}')"
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UP,workdir=$WK" /home/builder/s1 2>/tmp/s34d-ovl-$U.err || { st "overlay failed ($(cat /tmp/s34d-ovl-$U.err)): stopping (no full copy)"; exit 1; }
st "overlay mounted (s3 read-only, changes in $UP)"
touch /home/builder/s1/.s34d-marker || { st "tree not writable"; exit 1; }
if [ -n "$V_AS_BUILDER" ]; then exec runuser -u builder -- bash "$V_INNER"; fi
bash "$V_INNER"
OUT
sed -i 's/\r$//' /tmp/s34d-outer-$$.sh; chmod 755 /tmp/s34d-outer-$$.sh
cd /
if [ "$(id -u)" = 0 ]; then
  V_REAL_UID=0 V_AS_BUILDER=1 V_INNER=/tmp/s34d-inner-$$.sh setsid nohup unshare -m --propagation private bash /tmp/s34d-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
else
  V_REAL_UID=$(id -u) V_INNER=/tmp/s34d-inner-$$.sh setsid nohup unshare -Urm --propagation private bash /tmp/s34d-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
fi
echo "omni-native-s3.4d build started pid $!"
