#!/bin/bash
# s3.1c = s3.1b + OMNI_POINTER_CROSS_V1 (patches/pointer-cross.diff, applied by tools/apply_pointer_cross.py): while the
# stick/mouse pointer leads, Cross is a click at the pointer in every native panel and page (Options/fx menus, Browser
# tools, History, modals, settings, built-in pages, the Master Control page); the D-pad hands the lead back; hovering
# highlights the row. Shell only (engine/entry), so the TITLE changes; the child is linked BEFORE the patch is applied and
# must be byte-identical to s3.1b's child (checked). PRIVATE overlay as s3.1b: /home/builder/s3 is the read-only lower
# layer, changes go to /home/builder/s31c-up-<uid>, mounted on /home/builder/s1 in a private mount namespace. s3, s3.1b
# and their objects are never written; GPU objects go to /home/builder/s31cobjs. Build only: never deploys, no console.
# Progress: outputs/omni-native-s3.1c/build-steps.txt
O='/path/to/workspace/outputs'; N="$O/omni-native-s3.1c"
cat > /tmp/s31c-inner-$$.sh <<'IN'
#!/bin/bash
O='/path/to/workspace/outputs'; N="$O/omni-native-s3.1c"; B="$O/omni-native-s3.1b"
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$N/build-steps.txt"; }
export OMNI_SECLIBS=/home/builder/omni-seclibs/stage/user/homebrew/lib
[ -e /home/builder/s1/.s31c-marker ] || { st "overlay missing: refusing to build in the shared s1 tree"; exit 1; }
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
# 1. WebKit: s3's patches (already in the lower tree: idempotent) + OMNI_SEC_PNA_CONNECT_V1
python3 "$N/tools/apply_s3_webkit.py" /home/builder/s1 > "$N/apply-webkit.log" 2>&1 || { st "s3 webkit apply FAILED: $(tail -3 "$N/apply-webkit.log" | tr '\n' ' ')"; exit 1; }
python3 "$N/tools/apply_s31_pna.py" /home/builder/s1 > "$N/apply-pna.log" 2>&1 || { st "PNA webkit apply FAILED: $(tail -3 "$N/apply-pna.log" | tr '\n' ' ')"; exit 1; }
st "webkit: s3 $(grep -c '^already' "$N/apply-webkit.log") already / $(grep -c '^patched' "$N/apply-webkit.log") patched; PNA $(grep -c '^patched' "$N/apply-pna.log") patched, $(grep -c '^already' "$N/apply-pna.log") already"
# 2. shell sources (s3.1b's) + the s3.1b engine changes
for f in "$N"/engine-patches/entry/*; do cp "$f" /home/builder/s1/engine/entry/ || { st "copy FAILED $f"; exit 1; }; done
st "shell sources copied: $(ls "$N"/engine-patches/entry | wc -l) files"
python3 "$N/tools/apply_viewtransition.py" /home/builder/s1 > "$N/apply_vt.log" 2>&1 || { st "view-transition patch FAILED: $(tail -1 "$N/apply_vt.log")"; exit 1; }
python3 "$N/tools/apply_yt.py" /home/builder/s1 > "$N/apply_yt.log" 2>&1 || { st "apply_yt FAILED: $(tail -2 "$N/apply_yt.log" | tr '\n' ' ')"; exit 1; }
python3 "$N/tools/apply_soak_read.py" /home/builder/s1 > "$N/apply_soak.log" 2>&1 || { st "soak-read patch FAILED: $(tail -1 "$N/apply_soak.log")"; exit 1; }
st "s3.1b engine changes: $(tail -1 "$N/apply_vt.log" | cut -c1-80); $(tail -1 "$N/apply_yt.log" | cut -c1-80); $(tail -1 "$N/apply_soak.log" | cut -c1-80)"
cd "$N" || exit 1
# 3. the child from the UNPATCHED tree (= s3.1b's child)
nice -n 5 ninja -k 0 -C /home/builder/s1/build -j6 OmniEngine > "$N/ninja-child.log" 2>&1 || { st "ninja (child tree) FAILED: $(grep -m20 -E 'error:|FAILED' "$N/ninja-child.log" | tr '\n' ' ' | cut -c1-3000)"; exit 1; }
python3 "$N/make_link_command.py" > "$N/link-command-child.log" 2>&1 || { st "link command (child) FAILED"; exit 1; }
python3 "$N/child_build.py" > "$N/child-build.log" 2>&1 || { st "child FAILED: $(tail -3 "$N/child-build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
CH=$(sha256sum "$N/child/omni-engine-child.elf" | cut -d' ' -f1); BH=$(sha256sum "$B/child/omni-engine-child.elf" | cut -d' ' -f1)
st "child ok (unpatched tree, ninja $(grep -c '^\[' "$N/ninja-child.log") steps): $CH; s3.1b child $BH: $([ "$CH" = "$BH" ] && echo IDENTICAL || echo DIFFERENT)"
# 4. OMNI_POINTER_CROSS_V1 + its host test (against the patched tree's files)
python3 "$N/tools/apply_pointer_cross.py" /home/builder/s1 "$N/patches/pointer-cross.diff" > "$N/apply_pointer_cross.log" 2>&1 || { st "pointer-cross patch FAILED: $(tail -3 "$N/apply_pointer_cross.log" | tr '\n' ' ')"; exit 1; }
st "OMNI_POINTER_CROSS_V1: $(tail -1 "$N/apply_pointer_cross.log")"
E=/home/builder/s1/engine/entry; cp "$E/OmniBrowser.cpp" "$E/OmniFeaturesPanel.h" "$E/OmniPointerCross.h" "$N/hosttest/wsl/" 2>/dev/null
clang++ -std=c++17 -O1 -g -Wall -Wextra -Wno-unused-function -fsanitize=address,undefined -fno-omit-frame-pointer -I"$E" "$N/hosttest/pointer_cross_test.cpp" -o "$H/pct" > "$N/hosttest/wsl/pointer-cross-build.log" 2>&1 \
  && "$H/pct" "$E/OmniBrowser.cpp" "$E/OmniFeaturesPanel.h" > "$N/hosttest/wsl/pointer-cross.log" 2>&1 \
  || { st "pointer-cross host test FAILED: $(grep -h FAIL "$N/hosttest/wsl/pointer-cross.log" | head -3 | tr '\n' ' '; tail -3 "$N/hosttest/wsl/pointer-cross-build.log" | tr '\n' ' ' | cut -c1-400)"; exit 1; }
clang++ -std=c++17 -O1 -Wno-unused-function -DOMNI_PTR_CROSS_BEFORE -I"$E" "$N/hosttest/pointer_cross_test.cpp" -o "$H/pctb" > /dev/null 2>&1 && "$H/pctb" "$B/engine-patches/entry/OmniBrowser.cpp" "$H/none" > "$N/hosttest/wsl/pointer-cross-before.log" 2>&1
st "pointer-cross host test: $(tail -1 "$N/hosttest/wsl/pointer-cross.log"); s3.1b routing (expected to fail): $(tail -1 "$N/hosttest/wsl/pointer-cross-before.log")"
rm -rf "$H"
# 5. the title from the patched tree
nice -n 5 ninja -k 0 -C /home/builder/s1/build -j6 OmniEngine > "$N/ninja.log" 2>&1 || { st "ninja FAILED: $(grep -m20 -E 'error:|FAILED' "$N/ninja.log" | tr '\n' ' ' | cut -c1-3000)"; exit 1; }
st "ninja ok: $(grep -c '^\[' "$N/ninja.log") steps, $(grep -c 'warning:' "$N/ninja.log") warnings; pointer-cross warnings: $(grep -E 'OmniPointerCross|OmniFeaturesPanel' "$N/ninja.log" | grep -c 'warning:')"
python3 "$N/make_link_command.py" > "$N/link-command.log" 2>&1 || { st "link command FAILED"; exit 1; }
python3 "$N/tools/prep_s31c.py" > "$N/prep.log" 2>&1 || { st "prep FAILED: $(tail -2 "$N/prep.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "prep ok: $(grep -E '^compiled|^link command' "$N/prep.log" | tr '\n' ' ' | cut -c1-300)"
nice -n 5 python3 "$N/build.py" > "$N/build.log" 2>&1 || { st "title FAILED: $(tail -4 "$N/build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "title ok: $(grep -o 'eboot.bin [0-9a-f]*' "$N/build.log" | tail -1); $(grep -o 'pages packaged: [0-9]* files' "$N/build.log")"
C="$N/child/omni-engine-child.elf"; T="$N/build/eboot.elf"; : > "$N/checks.txt"
for k in "OMNI_POINTER_CROSS_V1" "accelerated compositing is off" "OMNI_SEC_PNA_CONNECT_V1" "OMNI_CRASH_V2" "FATAL end of report" "OMNI_JSC_JIT_V3" "no runtime permission changes" "jit: off (interpreter)" "OMNI_HUB_CARDS_V1 request filter" "OMNI_SEC_REDIRECT_V1" "OMNI_SEC_PNA_V1" "OMNI_SEC_LOCALHOST_V1" "close-events.log" "OpenSSL 3.5.9" "8.23.0" "nghttp2"; do
  printf "child  %-40s %s\n" "$k" "$(grep -c -a -- "$k" "$C")" >> "$N/checks.txt"; done
for k in "OMNI_POINTER_CROSS_V1" "YTTL DONE" "OMNI_EMUTLS_ROUNDS_V1" "OMNI_CRASH_V2" "FATAL end of report" "can't be read" "OMNI_PAGES_V1" "omni://pages" "omnibloomHost" "OMNI_ADDONS_V1 ready" "OMNI_VAULT_V2" "vault.v2" "experimental: faster, less safe" "OMNI_HUB_CARDS_V1" "OMNI_GPU_PRESENT_V1" "Bloom Core is not running" "PADCTL TEST PASS" "Ad block" "192.0.2.10"; do
  printf "title  %-40s %s\n" "$k" "$(grep -c -a -- "$k" "$T")" >> "$N/checks.txt"; done
/usr/lib/llvm-21/bin/llvm-nm "$N/build/llvm-pie.elf" 2>/dev/null | grep -E " [tTwWrR] (__emutls_get_address|emutls_key_destructor|omni_emutls_marker)$" >> "$N/checks.txt"
/usr/lib/llvm-21/bin/llvm-nm "$N/child/omni-engine-child-unstripped.elf" 2>/dev/null | grep -E " [tTwW] (__wrap_connect|omniSecConnectContext)$|omniOpenSocket" >> "$N/checks.txt"
grep -E "layout check|layout \(llvm" "$N/build.log" >> "$N/checks.txt"
echo "child vs s3.1b: $CH / $BH $([ "$CH" = "$BH" ] && echo IDENTICAL || echo DIFFERENT)" >> "$N/checks.txt"
sha256sum "$N/out/PPSA99732/eboot.bin" "$T" "$C" "$N/out/PPSA99732/sce_sys/param.json" "$N/out/PPSA99732/sce_module/libc.prx" >> "$N/checks.txt" 2>&1
st "checks written"
IN
sed -i 's/\r$//' /tmp/s31c-inner-$$.sh; chmod 755 /tmp/s31c-inner-$$.sh
cat > /tmp/s31c-outer-$$.sh <<'OUT'
#!/bin/bash
cd /
L=/tmp/omni-s31c.lock; ( umask 0; : >> "$L" ) 2>/dev/null; exec 9<"$L"; flock -n 9 || { echo "another s3.1c build is running"; exit 0; }
N='/path/to/workspace/outputs/omni-native-s3.1c'
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$N/build-steps.txt"; }
U=${V_REAL_UID:-$(id -u)}; UP=/home/builder/s31c-up-$U; WK=/home/builder/s31c-work-$U
[ -e /home/builder/s3/.s3-marker ] || { st "/home/builder/s3 missing: stopping"; exit 1; }
rm -rf "$UP" "$WK"; mkdir -p "$UP" "$WK" /home/builder/s31cobjs;   # every build starts from s3 plus this folder's changes only
 [ -n "$V_AS_BUILDER" ] && chown builder:builder "$UP" "$WK" /home/builder/s31cobjs
st "disk: $(df -h /home/builder | tail -1 | awk '{print $4" free"}')"
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UP,workdir=$WK" /home/builder/s1 2>/tmp/s31c-ovl-$U.err || { st "overlay failed ($(cat /tmp/s31c-ovl-$U.err)): stopping (no full copy)"; exit 1; }
st "overlay mounted (s3 read-only, changes in $UP)"
touch /home/builder/s1/.s31c-marker || { st "tree not writable"; exit 1; }
if [ -n "$V_AS_BUILDER" ]; then exec runuser -u builder -- bash "$V_INNER"; fi
bash "$V_INNER"
OUT
sed -i 's/\r$//' /tmp/s31c-outer-$$.sh; chmod 755 /tmp/s31c-outer-$$.sh
cd /
if [ "$(id -u)" = 0 ]; then
  V_REAL_UID=0 V_AS_BUILDER=1 V_INNER=/tmp/s31c-inner-$$.sh setsid nohup unshare -m --propagation private bash /tmp/s31c-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
else
  V_REAL_UID=$(id -u) V_INNER=/tmp/s31c-inner-$$.sh setsid nohup unshare -Urm --propagation private bash /tmp/s31c-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
fi
echo "omni-native-s3.1c build started pid $!"
