#!/bin/bash
# s3.1 = omni-native-s3 + audit fixes (OS-001 OMNI_SEC_PNA_CONNECT_V1: WebKit curl opensocket tag + child connect() rule;
# OS-002: OmniVault.h read errors fail closed) + omni-jit2 build 4 (OMNI_EMUTLS_ROUNDS_V1 NativeEmutls.cpp in the title,
# OMNI_CRASH_V2 OmniCrash.h, boot.log O_APPEND). Title AND child.
# PRIVATE overlay: /home/builder/s3 is the read-only lower layer, changes go to /home/builder/s31-up-<uid>, mounted on
# /home/builder/s1 in a private mount namespace (as omni-jit2 does). s3, s2, s1 and their objects are never written;
# GPU objects go to /home/builder/s31objs. Build only: never deploys, never touches the console.
# Progress: outputs/omni-native-s3.1/build-steps.txt
O='/path/to/workspace/outputs'; N="$O/omni-native-s3.1"
cat > /tmp/s31-inner-$$.sh <<'IN'
#!/bin/bash
O='/path/to/workspace/outputs'; N="$O/omni-native-s3.1"
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$N/build-steps.txt"; }
export OMNI_SECLIBS=/home/builder/omni-seclibs/stage/user/homebrew/lib
[ -e /home/builder/s1/.s31-marker ] || { st "overlay missing: refusing to build in the shared s1 tree"; exit 1; }
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
rm -rf "$H"
st "host tests: $(tail -1 "$N/hosttest/wsl/sec-connect.log"); $(tail -1 "$N/hosttest/wsl/vault-os002.log"); $(tail -1 "$N/hosttest/wsl/vault-suite.log"); SDK compile ok"
# 1. WebKit: s3's patches (already in the lower tree: idempotent) + OMNI_SEC_PNA_CONNECT_V1
python3 "$N/tools/apply_s3_webkit.py" /home/builder/s1 > "$N/apply-webkit.log" 2>&1 || { st "s3 webkit apply FAILED: $(tail -3 "$N/apply-webkit.log" | tr '\n' ' ')"; exit 1; }
python3 "$N/tools/apply_s31_pna.py" /home/builder/s1 > "$N/apply-pna.log" 2>&1 || { st "PNA webkit apply FAILED: $(tail -3 "$N/apply-pna.log" | tr '\n' ' ')"; exit 1; }
st "webkit: s3 $(grep -c '^already' "$N/apply-webkit.log") already / $(grep -c '^patched' "$N/apply-webkit.log") patched; PNA $(grep -c '^patched' "$N/apply-pna.log") patched, $(grep -c '^already' "$N/apply-pna.log") already"
# 2. shell sources: s3's engine-patches + s3.1's OmniVault.h (OS-002) + jit2's OmniCrash.h (OMNI_CRASH_V2)
for f in "$N"/engine-patches/entry/*; do cp "$f" /home/builder/s1/engine/entry/ || { st "copy FAILED $f"; exit 1; }; done
st "shell sources copied: $(ls "$N"/engine-patches/entry | wc -l) files; OmniCrash.h $(sha256sum /home/builder/s1/engine/entry/OmniCrash.h | cut -c1-16), OmniVault.h $(sha256sum /home/builder/s1/engine/entry/OmniVault.h | cut -c1-16)"
cd "$N" || exit 1
nice -n 5 ninja -k 0 -C /home/builder/s1/build -j6 OmniEngine > "$N/ninja.log" 2>&1 || { st "ninja FAILED: $(grep -m20 -E 'error:|FAILED' "$N/ninja.log" | tr '\n' ' ' | cut -c1-3000)"; exit 1; }
st "ninja ok: $(grep -c '^\[' "$N/ninja.log") steps, $(grep -c 'warning:' "$N/ninja.log") warnings"
python3 "$N/make_link_command.py" > "$N/link-command.log" 2>&1 || { st "link command FAILED"; exit 1; }
python3 "$N/tools/prep_s31.py" > "$N/prep.log" 2>&1 || { st "prep FAILED: $(tail -2 "$N/prep.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "prep ok: $(grep -E '^compiled|^link command' "$N/prep.log" | tr '\n' ' ' | cut -c1-300)"
python3 "$N/child_build.py" > "$N/child-build.log" 2>&1 || { st "child FAILED: $(tail -3 "$N/child-build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "child ok: $(python3 -c "import json;r=json.load(open('$N/child/receipt.json'));print(r['engine_sha256'][:16], r['engine_bytes'])")"
nice -n 5 python3 "$N/build.py" > "$N/build.log" 2>&1 || { st "title FAILED: $(tail -4 "$N/build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
st "title ok: $(grep -o 'eboot.bin [0-9a-f]*' "$N/build.log" | tail -1); $(grep -o 'pages packaged: [0-9]* files' "$N/build.log")"
C="$N/child/omni-engine-child.elf"; T="$N/build/eboot.elf"; : > "$N/checks.txt"
for k in "OMNI_SEC_PNA_CONNECT_V1" "OMNI_CRASH_V2" "FATAL end of report" "OMNI_JSC_JIT_V3" "no runtime permission changes" "jit: off (interpreter)" "OMNI_HUB_CARDS_V1 request filter" "OMNI_SEC_REDIRECT_V1" "OMNI_SEC_PNA_V1" "OMNI_SEC_LOCALHOST_V1" "close-events.log" "OpenSSL 3.5.9" "8.23.0" "nghttp2"; do
  printf "child  %-40s %s\n" "$k" "$(grep -c -a -- "$k" "$C")" >> "$N/checks.txt"; done
for k in "OMNI_EMUTLS_ROUNDS_V1" "OMNI_CRASH_V2" "FATAL end of report" "can't be read" "OMNI_PAGES_V1" "omni://pages" "omnibloomHost" "OMNI_ADDONS_V1 ready" "OMNI_VAULT_V2" "vault.v2" "experimental: faster, less safe" "OMNI_HUB_CARDS_V1" "OMNI_GPU_PRESENT_V1" "Bloom Core is not running" "PADCTL TEST PASS" "Ad block" "192.0.2.10"; do
  printf "title  %-40s %s\n" "$k" "$(grep -c -a -- "$k" "$T")" >> "$N/checks.txt"; done
/usr/lib/llvm-21/bin/llvm-nm "$N/build/llvm-pie.elf" 2>/dev/null | grep -E " [tTwWrR] (__emutls_get_address|emutls_key_destructor|omni_emutls_marker)$" >> "$N/checks.txt"
/usr/lib/llvm-21/bin/llvm-nm "$N/child/omni-engine-child-unstripped.elf" 2>/dev/null | grep -E " [tTwW] (__wrap_connect|omniSecConnectContext)$|omniOpenSocket" >> "$N/checks.txt"
grep -E "layout check|layout \(llvm" "$N/build.log" >> "$N/checks.txt"
sha256sum "$N/out/PPSA99732/eboot.bin" "$T" "$C" >> "$N/checks.txt"
st "checks written"
IN
sed -i 's/\r$//' /tmp/s31-inner-$$.sh; chmod 755 /tmp/s31-inner-$$.sh
cat > /tmp/s31-outer-$$.sh <<'OUT'
#!/bin/bash
cd /
L=/tmp/omni-s31.lock; ( umask 0; : >> "$L" ) 2>/dev/null; exec 9<"$L"; flock -n 9 || { echo "another s3.1 build is running"; exit 0; }
N='/path/to/workspace/outputs/omni-native-s3.1'
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$N/build-steps.txt"; }
U=${V_REAL_UID:-$(id -u)}; UP=/home/builder/s31-up-$U; WK=/home/builder/s31-work-$U
[ -e /home/builder/s3/.s3-marker ] || { st "/home/builder/s3 missing: stopping"; exit 1; }
rm -rf "$UP" "$WK"; mkdir -p "$UP" "$WK" /home/builder/s31objs;   # every build starts from s3 plus this folder's changes only
 [ -n "$V_AS_BUILDER" ] && chown builder:builder "$UP" "$WK" /home/builder/s31objs
st "disk: $(df -h /home/builder | tail -1 | awk '{print $4" free"}')"
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UP,workdir=$WK" /home/builder/s1 2>/tmp/s31-ovl-$U.err || { st "overlay failed ($(cat /tmp/s31-ovl-$U.err)): stopping (no full copy)"; exit 1; }
st "overlay mounted (s3 read-only, changes in $UP)"
touch /home/builder/s1/.s31-marker || { st "tree not writable"; exit 1; }
if [ -n "$V_AS_BUILDER" ]; then exec runuser -u builder -- bash "$V_INNER"; fi
bash "$V_INNER"
OUT
sed -i 's/\r$//' /tmp/s31-outer-$$.sh; chmod 755 /tmp/s31-outer-$$.sh
cd /
if [ "$(id -u)" = 0 ]; then
  V_REAL_UID=0 V_AS_BUILDER=1 V_INNER=/tmp/s31-inner-$$.sh setsid nohup unshare -m --propagation private bash /tmp/s31-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
else
  V_REAL_UID=$(id -u) V_INNER=/tmp/s31-inner-$$.sh setsid nohup unshare -Urm --propagation private bash /tmp/s31-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
fi
echo "omni-native-s3.1 build started pid $!"
