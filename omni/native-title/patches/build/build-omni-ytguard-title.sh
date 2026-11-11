#!/bin/bash
# Guard title = launch title rc2 + OMNI_YT_ATTEST_GUARD_V1 (omni-ytattest/OmniYtGuard.h, on unless /data/omni/ytguard-off.flag);
# MODE=test also adds OMNI_YT_ATTEST_PROBE_V1 (inert without /data/omni/ytattest.flag). Output omni-ytattest/out-guard-$MODE.
# Derived from build-omni-ytattest-diag-title.sh. Incremental build in the launch title's own tree (overlay upper launche-up-0) and an ext4
# copy of its workspace; afterwards the probe is taken out again, OmniBrowser.cpp is verified back at rc2's 2a406405 and
# ninja brings the objects back to rc2. Gates: imports = the launch title's exactly; probe string present.
# Own lock /tmp/omni-ytattest.lock, private mount namespace, SOURCE_DATE_EPOCH=1793793600. Build only, console untouched.
MODE=${MODE:-test}; case "$MODE" in test|ship) ;; *) echo 'MODE=test|ship'; exit 2;; esac; export MODE
O='/path/to/workspace/outputs'; Y="$O/omni-ytattest"; mkdir -p "$Y/logs-guard-$MODE"
cat > /tmp/ytguard-inner-$$.sh <<'IN'
#!/bin/bash
O='/path/to/workspace/outputs'; Y="$O/omni-ytattest"; N="$O/omni-launch-eboot-bind"; L="$O/omni-launch"
T=/home/builder/s1; E=$T/engine/entry; LL=/usr/lib/llvm-21/bin
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$Y/steps-guard.txt"; }
export OMNI_SECLIBS=/home/builder/omni-seclibs/stage/user/homebrew/lib SOURCE_DATE_EPOCH=1793793600
X=$(sed 's/\r$//' "$E/OmniBrowser.cpp" | sha256sum | cut -c1-64)
[ "$X" = 2a4064054adfea3b95e212477ee64153adba47b5370a73fc413ef5e6d8d76eec ] || { st "OmniBrowser.cpp is not the launch title's 2a406405 ($X): stopping"; exit 1; }
[ -e "$E/OmniYtAttestProbe.h" ] || [ -e "$E/OmniYtGuard.h" ] && { st "a probe/guard header is already in the tree: stopping"; exit 1; }
cp -p "$E/OmniBrowser.cpp" /tmp/ytguard-OmniBrowser.cpp.orig || exit 1
revert(){ cp -p /tmp/ytguard-OmniBrowser.cpp.orig "$E/OmniBrowser.cpp"; rm -f "$E/OmniYtAttestProbe.h" "$E/OmniYtGuard.h"
  R=$(sed 's/\r$//' "$E/OmniBrowser.cpp" | sha256sum | cut -c1-64)
  [ "$R" = 2a4064054adfea3b95e212477ee64153adba47b5370a73fc413ef5e6d8d76eec ] && [ ! -e "$E/OmniYtAttestProbe.h" ] && [ ! -e "$E/OmniYtGuard.h" ] && st "REVERTED: OmniBrowser.cpp back at 2a406405, probe/guard headers removed" || st "REVERT CHECK FAILED ($R)"; }
trap revert EXIT
cp "$Y/OmniYtGuard.h" "$E/OmniYtGuard.h" || exit 1; [ "$MODE" = test ] && { cp "$Y/OmniYtAttestProbe.h" "$E/OmniYtAttestProbe.h" || exit 1; }
python3 - "$E/OmniBrowser.cpp" "$MODE" > "$Y/logs-guard-$MODE/apply.log" 2>&1 <<'PY' || { st "probe apply FAILED: $(tail -1 "$Y/logs-guard-$MODE/apply.log")"; exit 1; }
import sys
p = sys.argv[1]; b = open(p, 'rb').read(); nl = b'\r\n' if b'\r\n' in b else b'\n'
a1 = b'static void omniDialogsInstall(WKPageUIClientV19& ui)' + nl + b'{' + nl
a2 = b'        omniHdrCapsInstall(); // OMNI_HDR_CAPS_V1: what pages are told about HDR (test modes too: the fps runs measure real pages)' + nl
a3 = b'        omniDialogRequest(omniModalPrompt, page, OmniTest::toStd(text), OmniTest::toStd(value), origin, listener);' + nl
a4 = b'    WKWebsiteDataStoreConfigurationSetNetworkCacheDirectory(storeConfig.get(), pathString("/NetworkCache").get());' + nl
for a in (a1, a2, a3, a4):
    if b.count(a) != 1: sys.exit('anchor count %d: %r' % (b.count(a), a[:60]))
probe = sys.argv[2] == 'test'
inc = b'#include "OmniYtGuard.h" // OMNI_YT_ATTEST_GUARD_V1: YouTube attestation guard, off with /data/omni/ytguard-off.flag' + nl
if probe: inc += b'#include "OmniYtAttestProbe.h" // OMNI_YT_ATTEST_PROBE_V1: diagnostic, off without /data/omni/ytattest.flag' + nl
b = b.replace(a1, inc + a1, 1)   # after the WKUserScript users, where its API is declared
ins = b'        omniYtGuardInstall(); // OMNI_YT_ATTEST_GUARD_V1' + nl + (b'        omniYtAttestInstall(); // OMNI_YT_ATTEST_PROBE_V1' + nl if probe else b'')
b = b.replace(a2, a2 + ins, 1)
hk = b'        if (omniYtGuardPrompt(page, text, value, listener)) return; // OMNI_YT_ATTEST_GUARD_V1: its report/reload channel' + nl
if probe: hk += b'        if (omniYtAttestPrompt(text, value, listener)) return; // OMNI_YT_ATTEST_PROBE_V1: report channel of the probe' + nl
b = b.replace(a3, hk + a3, 1)
b = b.replace(a4, b'    omniNcResetOnce(profile); // OMNI_NC_RESET_V1: once, the old (bodiless) HTTP cache is set aside before the store is configured' + nl + a4, 1)
open(p, 'wb').write(b); print('applied (4 anchors, mode %s)' % sys.argv[2])
PY
st "guard ($MODE) applied: $(tail -1 "$Y/logs-guard-$MODE/apply.log")"
nice -n 5 ninja -k 0 -C $T/build -j6 OmniEngine > "$Y/logs-guard-$MODE/ninja.log" 2>&1 || { st "ninja FAILED: $(grep -m12 -E 'error:|FAILED' "$Y/logs-guard-$MODE/ninja.log" | tr '\n' ' ' | cut -c1-2500)"; exit 1; }
st "ninja ok: $(grep -c '^\[' "$Y/logs-guard-$MODE/ninja.log") steps, $(grep -c 'warning:' "$Y/logs-guard-$MODE/ninja.log") warnings ($(grep -c 'OmniYtAttest' "$Y/logs-guard-$MODE/ninja.log") mention the probe)"
cd "$N" || exit 1
python3 "$N/make_link_command.py" > "$Y/logs-guard-$MODE/link-command.log" 2>&1 || { st "link command FAILED"; exit 1; }
python3 "$N/tools/prep_launch.py" > "$Y/logs-guard-$MODE/prep.log" 2>&1 || { st "prep FAILED: $(tail -2 "$Y/logs-guard-$MODE/prep.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
nice -n 5 python3 "$N/build.py" > "$Y/logs-guard-$MODE/build.log" 2>&1 || { st "title FAILED: $(grep -o 'undefined symbol: .*' "$Y/logs-guard-$MODE/build.log" | sort -u | head -5 | tr '\n' ' ') $(tail -3 "$Y/logs-guard-$MODE/build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
grep -o 'layout check[^;]*PASSED' "$Y/logs-guard-$MODE/build.log" | head -1 | grep -q PASSED || { st "layout check did not PASS"; exit 1; }
$LL/llvm-nm -D --undefined-only "$N/build/llvm-pie.elf" | awk '{print $NF}' | sort -u > "$Y/logs-guard-$MODE/imports-diag.txt"
$LL/llvm-nm -D --undefined-only "$L/eboot/build/llvm-pie.elf" | awk '{print $NF}' | sort -u > "$Y/logs-guard-$MODE/imports-launch.txt"
cmp -s "$Y/logs-guard-$MODE/imports-diag.txt" "$Y/logs-guard-$MODE/imports-launch.txt" || { st "IMPORT GATE FAILED: +[$(comm -23 "$Y/logs-guard-$MODE/imports-diag.txt" "$Y/logs-guard-$MODE/imports-launch.txt" | tr '\n' ' ')] -[$(comm -13 "$Y/logs-guard-$MODE/imports-diag.txt" "$Y/logs-guard-$MODE/imports-launch.txt" | tr '\n' ' ')]"; exit 1; }
K=$(grep -c -a 'OMNI_YTGUARD_V1' "$N/build/llvm-pie.elf"); [ "$K" -ge 1 ] || { st "guard text missing from the title"; exit 1; }
KR=$(grep -c -a 'OMNI NCRESET' "$N/build/llvm-pie.elf"); [ "$KR" -ge 1 ] || { st "nc reset text missing from the title"; exit 1; }
KP=$(grep -c -a 'OMNI_YTATTEST_V1' "$N/build/llvm-pie.elf"); { [ "$MODE" = test ] && [ "$KP" -ge 1 ]; } || { [ "$MODE" = ship ] && [ "$KP" = 0 ]; } || { st "probe text check failed ($MODE, $KP)"; exit 1; }
st "gates: imports = the launch title's $(wc -l < "$Y/logs-guard-$MODE/imports-launch.txt") exactly; layout check PASSED; guard text present, probe text $( [ "$MODE" = test ] && echo present || echo absent)"
D="$Y/out-guard-$MODE"; rm -rf "$D"; mkdir -p "$D"; cp -r "$N/out/PPSA99732" "$D/" && cp "$N/build/llvm-pie.elf" "$N/build/eboot.elf" "$D/" || { st "copy FAILED"; exit 1; }
( cd "$N/out/PPSA99732" && find . -type f -exec sha256sum {} + | sort -k2 ) > "$Y/logs-guard-$MODE/pkg-ext4.sha256"; ( cd "$D/PPSA99732" && find . -type f -exec sha256sum {} + | sort -k2 ) > "$Y/logs-guard-$MODE/pkg-copy.sha256"
cmp -s "$Y/logs-guard-$MODE/pkg-ext4.sha256" "$Y/logs-guard-$MODE/pkg-copy.sha256" || { st "COPY MISMATCH"; exit 1; }
st "GUARD TITLE ($MODE): eboot.bin $(sha256sum "$D/PPSA99732/eboot.bin" | cut -c1-64) ($(wc -l < "$Y/logs-guard-$MODE/pkg-copy.sha256") package files copied and compared)"
trap - EXIT; revert
nice -n 5 ninja -k 0 -C $T/build -j6 OmniEngine > "$Y/logs-guard-$MODE/ninja-revert.log" 2>&1 && st "objects back to rc2: ninja $(grep -c '^\[' "$Y/logs-guard-$MODE/ninja-revert.log") steps" || st "ninja after revert FAILED (tree sources are rc2; rebuild before the next launch title build)"
IN
cat > /tmp/ytguard-outer-$$.sh <<'OUT2'
#!/bin/bash
cd /
LKF=/tmp/omni-ytguard.lock; ( umask 0; : >> "$LKF" ) 2>/dev/null; exec 9<"$LKF"; flock -n 9 || { echo "another ytattest build is running"; exit 0; }
O='/path/to/workspace/outputs'; Y="$O/omni-ytattest"
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$Y/steps-guard.txt"; }
UP=/home/builder/launche-up-0; WK=/home/builder/launche-work-0; WS=/home/builder/ytattest-ws; SRCWS=/home/builder/launche-ws-0
[ -e "$UP/.launche-marker" ] && [ -e "$SRCWS/build.py" ] || { st "launch title tree or workspace missing: stopping"; exit 1; }
rm -rf "$WK" "$WS"; mkdir -p "$WK" "$WS"
cp -a "$SRCWS/." "$WS/" && rm -rf "$WS/build" "$WS/out" "$WS/child" || { st "workspace copy failed"; exit 1; }
chown -R builder:builder "$WK" "$WS"
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UP,workdir=$WK" /home/builder/s1 || { st "overlay failed"; exit 1; }
mkdir -p "$O/omni-launch-eboot-bind"; mount --bind "$WS" "$O/omni-launch-eboot-bind" || { st "bind failed"; exit 1; }
st "overlay: /home/builder/s1 = s3 + $UP (launch title tree); workspace $WS (copy of $SRCWS) bound at outputs/omni-launch-eboot-bind"
exec runuser -u builder -- bash "$V_INNER"
OUT2
sed -i 's/\r$//' /tmp/ytguard-inner-$$.sh /tmp/ytguard-outer-$$.sh
sed -i "2i MODE=$MODE" /tmp/ytguard-inner-$$.sh
V_INNER=/tmp/ytguard-inner-$$.sh unshare -m --propagation private bash /tmp/ytguard-outer-$$.sh > "$Y/native-build-guard-$MODE.log" 2>&1 < /dev/null
echo "ytguard title build ($MODE): exit $?"; tail -8 "$Y/steps-guard.txt"
