#!/bin/bash
# OMNI_GPUPAGES_RC6_V1 (2026-11-12): copy of build-omni-gpupages-ls1b-titlefix.sh that also applies the rc6 TITLE units after PROOF 1:
# OmniYtGuard.h + the 4-anchor OmniBrowser.cpp edit (OMNI_YT_ATTEST_GUARD_V1 v2 + OMNI_NC_RESET_V1, ship mode, from build-omni-ytguard-title.sh)
# and omni-jit-fix/apply_jit_default_on.py --title. The import gate allows exactly the 2 imports stage 1 adds (sceKernelUsleep,
# sceVideoOutIsFlipPending). Logs in omni-gpupages-ls1b/titlefix-rc6/, output out-titlefix-rc6/; tools still from titlefix/.
# omni-gpu-pages ls1b: TITLE-ONLY rebuild with OMNI_LAZY_GPUPAGES_V1 (2026-11-10, after console gate s1a0y).
# Console: title d983581f exited at start: "[import] missing eglGetError ... checked=456 missing=6, exit status=3".
# Cause: stage 1's WebProcess code calls 6 EGL/GL functions that the title's OmniLazyGraphics.cpp has no forwarder for,
# so the title linked them as direct imports from libEGL/libGLESv2, which the console does not have at start.
# Fix: add forwarders for exactly those 6 (omni-gpupages-ls1b/titlefix/add_lazy_graphics.py), relink the title only.
# The child 60937efe (rc4-based, static Mesa, no OmniLazyGraphics) is unchanged and stays the pair's child.
# Steps (one shared build tree A = /home/builder/s1 over upper ogp-ls1b-up-0, now in child state C(rc4)):
#   1. state T sources rebuilt in a fresh source-only overlay (ogp-ls1b-upT-0): the same base + launch title units as
#      build-omni-gpupages-launch-s1b2.sh, PROOF 1 against the launch title tree, then stage 1 + async gate
#   2. A switched to state T (switch_state.py), lazy forwarders added, ninja OmniEngine (incremental)
#   3. title linked in the ext4 eboot workspace, GATE: the title's dynamic imports = the launch title rc2's, exactly
#   4. copied to omni-gpupages-ls1b/out-titlefix/ and compared; A switched back to state C(rc4) and compared
# Own lock /tmp/omni-gpupages-ls1b.lock, private mount namespace, nice 19, SOURCE_DATE_EPOCH=1793793600. Build only.
O='/path/to/workspace/outputs'; P="$O/omni-gpupages-ls1b"; F="$P/titlefix-rc6"; FT="$P/titlefix"; mkdir -p "$F"
cat > /tmp/ogptf-inner-$$.sh <<'IN'
#!/bin/bash
O='/path/to/workspace/outputs'; P="$O/omni-gpupages-ls1b"; F="$P/titlefix-rc6"; FT="$P/titlefix"
NE="$O/omni-gpupages-ls1b-eboot-bind"; J="$O/omni-jank"; A="$O/omni-ack"; L="$O/omni-launch"; S1="$O/omni-gpu-pages/stage1"
T=/home/builder/s1; TT=/home/builder/ogp-ls1b-T-mnt; TB=/home/builder/ogp-ls1b-B-mnt; B=$T/build; LL=/usr/lib/llvm-21/bin
SDKI=/opt/ps5-payload-sdk/target/user/homebrew/include
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$F/steps.txt"; }
export OMNI_SECLIBS=/home/builder/omni-seclibs/stage/user/homebrew/lib SOURCE_DATE_EPOCH=1793793600
mkdir -p "$F/logs/T" "$F/merge/title/patches-jank" "$F/merge/title/patches-ack" "$F/patches-gpupages-T"
st "TITLE-FIX build start (A = $T, state T sources in $TT, state C(rc4) sources in $TB); load $(cut -d' ' -f1-3 /proc/loadavg)"
cd "$NE" || exit 1
# ---- 1. state T sources in TT (same commands as build-omni-gpupages-launch-s1b2.sh)
LT_="$F/logs/T"; TM="$F/merge/title"
python3 "$NE/tools/apply_s3_webkit.py" "$TT" > "$LT_/apply-webkit.log" 2>&1 && python3 "$NE/tools/apply_s31_pna.py" "$TT" > "$LT_/apply-pna.log" 2>&1 \
  && for f in "$NE"/engine-patches/entry/*; do cp "$f" "$TT/engine/entry/" || exit 1; done \
  && python3 "$NE/tools/apply_viewtransition.py" "$TT" > "$LT_/apply_vt.log" 2>&1 && python3 "$NE/tools/apply_yt.py" "$TT" > "$LT_/apply_yt.log" 2>&1 \
  && python3 "$NE/tools/apply_soak_read.py" "$TT" > "$LT_/apply_soak.log" 2>&1 || { st "T base FAILED"; exit 1; }
python3 "$NE/tools/apply_pointer_cross.py" $TT "$NE/patches/pointer-cross.diff" > "$LT_/apply_pointer_cross.log" 2>&1 || { st "pointer-cross FAILED"; exit 1; }
python3 "$NE/tools/apply_s34_entry.py" $TT > "$LT_/apply_s34_entry.log" 2>&1 || { st "s34 entry FAILED"; exit 1; }
for x in apply_dark_video apply_dark_standard apply_dark_emu; do python3 "$NE/tools/$x.py" $TT > "$LT_/$x.log" 2>&1 || { st "$x FAILED"; exit 1; }; done
(cd $TT && patch -p1 --forward --no-backup-if-mismatch < "$NE/patches/hwservice-stats-tree.diff") > "$LT_/apply_hwservice_tree.log" 2>&1 || { st "hwservice FAILED"; exit 1; }
[ "$(sed 's/\r$//' $TT/engine/entry/OmniBrowser.cpp | sha256sum | cut -d' ' -f1)" = "$(sed 's/\r$//' "$NE/s34-entry/OmniBrowser.cpp" | sha256sum | cut -d' ' -f1)" ] || { st "baseline OmniBrowser.cpp is not s3.4d's"; exit 1; }
python3 "$NE/tools/apply_hdr_caps.py" $TT > "$LT_/apply_hdr_caps.log" 2>&1 || { st "HDR caps FAILED"; exit 1; }
OMNI_JANK_SRC="$J/src" OMNI_JANK_PATCHES="$TM/patches-jank" python3 "$NE/tools/apply_paint_hold.py" $TT > "$LT_/apply_paint_hold.log" 2>&1 \
  && OMNI_JANK_SRC="$J/src" OMNI_JANK_PATCHES="$TM/patches-jank" python3 "$NE/tools/apply_jank.py" $TT > "$LT_/apply_jank.log" 2>&1 || { st "title jank FAILED"; exit 1; }
OMNI_ACK_SRC="$A/src" OMNI_ACK_PATCHES="$TM/patches-ack" python3 "$A/tools/apply_ack_title.py" $TT > "$LT_/apply_ack_title.log" 2>&1 || { st "title ack FAILED"; exit 1; }
python3 /home/builder/ogp-ls1b-link/ident.py "$V_UPT" "$L/eboot/merge/order-compare.txt" "state T(fix) vs the launch title tree" > "$F/merge/identity-T.txt" 2>&1 || { st "PROOF 1 FAILED: $(grep -hE '^(DIFF|MISSING)' "$F/merge/identity-T.txt" | head -4 | tr '\n' ' ')"; exit 1; }
X2=$(sed 's/\r$//' $TT/engine/entry/OmniBrowser.cpp | sha256sum | cut -c1-64)
[ "$X2" = 2a4064054adfea3b95e212477ee64153adba47b5370a73fc413ef5e6d8d76eec ] || { st "state T OmniBrowser.cpp is not the launch title's 2a406405: stopping"; exit 1; }
st "PROOF 1: $(tail -1 "$F/merge/identity-T.txt"); OmniBrowser.cpp = launch title 2a406405"
OGP_S1_PATCHES="$F/patches-gpupages-T" python3 "$S1/tools/apply_gpupages_child.py" "$TT" > "$LT_/apply_gpupages.log" 2>&1 || { st "stage-1 patches FAILED: $(tail -3 "$LT_/apply_gpupages.log" | tr '\n' ' ')"; exit 1; }
python3 "$S1/tools/apply_gpupages_async.py" "$TT" > "$LT_/apply_async.log" 2>&1 || { st "async gate FAILED"; exit 1; }
[ "$(sed 's/\r$//' $TT/engine/entry/OmniBrowser.cpp | sha256sum | cut -c1-64)" = "$X2" ] || { st "stage 1 changed OmniBrowser.cpp: stopping"; exit 1; }
# ---- rc6 title units (after PROOF 1 and the stage-1 check, so both proofs still compare against their recorded trees)
cp "$O/omni-ytattest/OmniYtGuard.h" "$TT/engine/entry/OmniYtGuard.h" || { st "guard header copy FAILED"; exit 1; }
python3 - "$TT/engine/entry/OmniBrowser.cpp" > "$LT_/apply_guard.log" 2>&1 <<'PY' || { st "guard apply FAILED: $(tail -1 "$LT_/apply_guard.log")"; exit 1; }
import sys
p = sys.argv[1]; b = open(p, 'rb').read(); nl = b'\r\n' if b'\r\n' in b else b'\n'
a1 = b'static void omniDialogsInstall(WKPageUIClientV19& ui)' + nl + b'{' + nl
a2 = b'        omniHdrCapsInstall(); // OMNI_HDR_CAPS_V1: what pages are told about HDR (test modes too: the fps runs measure real pages)' + nl
a3 = b'        omniDialogRequest(omniModalPrompt, page, OmniTest::toStd(text), OmniTest::toStd(value), origin, listener);' + nl
a4 = b'    WKWebsiteDataStoreConfigurationSetNetworkCacheDirectory(storeConfig.get(), pathString("/NetworkCache").get());' + nl
for a in (a1, a2, a3, a4):
    if b.count(a) != 1: sys.exit('anchor count %d: %r' % (b.count(a), a[:60]))
b = b.replace(a1, b'#include "OmniYtGuard.h" // OMNI_YT_ATTEST_GUARD_V1: YouTube attestation guard, off with /data/omni/ytguard-off.flag' + nl + a1, 1)
b = b.replace(a2, a2 + b'        omniYtGuardInstall(); // OMNI_YT_ATTEST_GUARD_V1' + nl, 1)
b = b.replace(a3, b'        if (omniYtGuardPrompt(page, text, value, listener)) return; // OMNI_YT_ATTEST_GUARD_V1: its report/reload channel' + nl + a3, 1)
b = b.replace(a4, b'    omniNcResetOnce(profile); // OMNI_NC_RESET_V1: once, the old (bodiless) HTTP cache is set aside before the store is configured' + nl + a4, 1)
open(p, 'wb').write(b); print('applied (4 anchors, mode ship)')
PY
python3 "$O/omni-jit-fix/apply_jit_default_on.py" --title "$TT" > "$LT_/apply_jitdef.log" 2>&1 && grep -q "^applied" "$LT_/apply_jitdef.log" || { st "JIT default-on (title) FAILED: $(tail -1 "$LT_/apply_jitdef.log")"; exit 1; }
st "rc6 title units on T: guard v2 + NC reset ($(tail -1 "$LT_/apply_guard.log")), JIT default-on ($(tail -1 "$LT_/apply_jitdef.log"))"
python3 "$S1/tools/apply_yttl_scroll.py" "$TT/engine/entry/OmniBrowser.cpp" > "$LT_/apply_yttl_scroll.log" 2>&1 || { st "YTTL scroll test hook FAILED: $(tail -1 "$LT_/apply_yttl_scroll.log")"; exit 1; }
st "OMNI_YTTL_SCROLL_V1 (test-only, inert without scroll N): $(tail -1 "$LT_/apply_yttl_scroll.log")"
python3 "$S1/tools/apply_media_health_fix.py" "$TT/engine/entry/OmniMediaDownloads.h" > "$LT_/apply_media_health.log" 2>&1 || { st "media health fix FAILED: $(tail -1 "$LT_/apply_media_health.log")"; exit 1; }
st "OMNI_MEDIA_HEALTH_V2: $(tail -1 "$LT_/apply_media_health.log")"
CGT=$TT/webkit/Source/WebKit/WebProcess/WebPage/CoordinatedGraphics; CGB=$TB/webkit/Source/WebKit/WebProcess/WebPage/CoordinatedGraphics
for f in ogp-s1-drawingarea.inc ogp-s1-surface.inc ogp-s1-policy.h ogp-s1b-async.inc; do
  cmp -s "$CGT/$f" "$CGB/$f" && echo "same-as-child $f $(sha256sum "$CGT/$f" | cut -c1-8)" || echo "DIFF-from-child $f T $(sha256sum "$CGT/$f" | cut -c1-8) C $(sha256sum "$CGB/$f" | cut -c1-8)"
  if [ -f "$P/patches-gpupages-T/$f" ]; then cmp -s "$CGT/$f" "$P/patches-gpupages-T/$f" && echo "same-as-shipped-title $f" || echo "newer-than-shipped-title $f"; fi
done > "$F/merge/stage1-inc-compare.txt"
grep -q '^DIFF-from-child' "$F/merge/stage1-inc-compare.txt" && { st "state T stage-1 .inc files differ from the child's (rc4 pair): stopping ($(grep '^DIFF' "$F/merge/stage1-inc-compare.txt" | tr '\n' ' '))"; exit 1; }
st "stage 1 + async on T: .inc files = the child 60937efe's ($(grep -c '^same-as-child' "$F/merge/stage1-inc-compare.txt")/4); vs the shipped title: $(grep -c '^same-as-shipped' "$F/merge/stage1-inc-compare.txt") same, $(grep -c '^newer' "$F/merge/stage1-inc-compare.txt") newer"
# ---- 2. switch A to state T, add the forwarders, build
python3 "$FT/switch_state.py" "$V_UPA" "$V_UPT" "$T" "$TT" "state T(fix)" > "$F/merge/switch-to-T.txt" 2>&1 || { st "switch to T FAILED: $(tail -1 "$F/merge/switch-to-T.txt")"; exit 1; }
st "switched A to state T: $(tail -1 "$F/merge/switch-to-T.txt")"
python3 "$FT/add_lazy_graphics.py" "$SDKI" "$T/engine/entry/OmniLazyGraphics.cpp" > "$F/logs/add_lazy.log" 2>&1 || { st "lazy forwarders FAILED: $(tail -1 "$F/logs/add_lazy.log")"; exit 1; }
cp "$T/engine/entry/OmniLazyGraphics.cpp" "$F/OmniLazyGraphics.cpp"; (diff -u /home/builder/s3/engine/entry/OmniLazyGraphics.cpp "$F/OmniLazyGraphics.cpp" > "$F/OmniLazyGraphics.cpp.diff"; true)
st "OMNI_LAZY_GPUPAGES_V1: $(tail -1 "$F/logs/add_lazy.log")"
CC=$(find "$B" -maxdepth 3 -name cmakeconfig.h | head -1)
grep -q "define ENABLE_ASYNC_SCROLLING 1" "$CC" || { st "build tree lost the async configuration: stopping"; exit 1; }
nice -n 19 ionice -c3 ninja -k 0 -C "$B" -j4 OmniEngine > "$F/logs/ninja-T.log" 2>&1 || { st "ninja (state T) FAILED: $(grep -m12 -E 'error:|FAILED' "$F/logs/ninja-T.log" | tr '\n' ' ' | cut -c1-2500)"; exit 1; }
IPCT=$(find "$B" -path '*DerivedSources*' \( -name '*MessageReceiver.cpp' -o -name '*Messages.h' -o -name 'GeneratedSerializers.cpp' -o -name 'GeneratedSerializers.h' \) -type f -exec sha256sum {} + 2>/dev/null | sort -k2 | sha256sum | cut -c1-16)
st "ninja state T ok: $(grep -c '^\[' "$F/logs/ninja-T.log") steps, $(grep -c 'warning:' "$F/logs/ninja-T.log") warnings; IPC generated code $IPCT"
case "$IPCT" in da4a7562*) ;; *) st "IPC generated code $IPCT is not the pair's da4a7562: the title would not match child 60937efe: stopping"; exit 1;; esac
# ---- 3. title link (launch recipe + stage-1 title sources) and the import gate
python3 "$NE/make_link_command.py" > "$F/logs/link-command-title.log" 2>&1 || { st "title link command FAILED"; exit 1; }
python3 "$NE/tools/prep_launch.py" > "$F/logs/prep.log" 2>&1 || { st "prep FAILED: $(tail -2 "$F/logs/prep.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
OGP_BRK="$O/omni-gpupages-ls1b/broker-mem" python3 "$S1/tools/patch_title_build.py" "$NE/build.py" "$S1/src-title" > "$F/logs/patch-title-build.log" 2>&1 || { st "stage-1 title sources FAILED"; exit 1; }
rm -rf "$NE/build" "$NE/out"
nice -n 19 python3 "$NE/build.py" > "$F/logs/title-build.log" 2>&1 || { st "title FAILED: $(grep -o 'undefined symbol: .*' "$F/logs/title-build.log" | sort -u | head -6 | tr '\n' ' ') $(tail -3 "$F/logs/title-build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
$LL/llvm-nm -D --undefined-only "$NE/build/llvm-pie.elf" | awk '{print $NF}' | sort -u > "$F/merge/imports-new.txt"
$LL/llvm-nm -D --undefined-only "$L/eboot/build/llvm-pie.elf" | awk '{print $NF}' | sort -u > "$F/merge/imports-launch.txt"
comm -23 "$F/merge/imports-new.txt" "$F/merge/imports-launch.txt" > "$F/merge/imports-added.txt"; comm -13 "$F/merge/imports-new.txt" "$F/merge/imports-launch.txt" > "$F/merge/imports-dropped.txt"
$LL/llvm-nm -D --undefined-only "$P/out/title/llvm-pie.elf" | awk '{print $NF}' | sort -u | comm -23 - "$F/merge/imports-launch.txt" > "$F/merge/imports-added-by-d983581f.txt"
grep -vxE "sceKernelUsleep|sceVideoOutIsFlipPending" "$F/merge/imports-added.txt" > "$F/merge/imports-added-unexpected.txt"
[ -s "$F/merge/imports-added-unexpected.txt" ] && { st "IMPORT GATE FAILED: imports beyond the launch title and the 2 stage-1 ones: $(tr '\n' ' ' < "$F/merge/imports-added-unexpected.txt" | cut -c1-600)"; exit 1; }
st "IMPORT GATE PASS: $(wc -l < "$F/merge/imports-new.txt") dynamic imports, none beyond the launch title rc2's ($(wc -l < "$F/merge/imports-dropped.txt") fewer); d983581f had added: $(tr '\n' ' ' < "$F/merge/imports-added-by-d983581f.txt")"
grep -o 'layout check[^;]*PASSED' "$F/logs/title-build.log" | head -1 | grep -q PASSED || { st "layout check did not PASS: stopping"; exit 1; }
st "TITLE built: eboot.bin $(sha256sum "$NE/out/PPSA99732/eboot.bin" | cut -c1-64); layout check PASSED"
grep -q -a "OMNI_YTGUARD_V1" "$NE/build/llvm-pie.elf" && grep -q -a "OMNI NCRESET" "$NE/build/llvm-pie.elf" && grep -q -a "JavaScript JIT (faster pages)" "$NE/build/llvm-pie.elf" && ! grep -q -a "faster, less safe" "$NE/build/llvm-pie.elf" || { st "rc6 text gates FAILED (guard / nc reset / JIT default)"; exit 1; }
grep -q -a "OMNI_YTATTEST_V1" "$NE/build/llvm-pie.elf" && { st "probe text present in a ship title: stopping"; exit 1; }
st "rc6 text gates PASS: guard, NC reset, JIT default-on present; no probe"
# ---- 4. copy out + compare, then A back to state C(rc4)
D="$P/out-titlefix-rc6"; rm -rf "$D"; mkdir -p "$D/title"
cp -r "$NE/out/PPSA99732" "$D/title/" && cp "$NE/build/eboot.elf" "$NE/build/llvm-pie.elf" "$D/title/" || { st "copy FAILED"; exit 1; }
( cd "$NE/out/PPSA99732" && find . -type f -exec sha256sum {} + | sort -k2 ) > "$F/merge/pkg-ext4.sha256"; ( cd "$D/title/PPSA99732" && find . -type f -exec sha256sum {} + | sort -k2 ) > "$F/merge/pkg-copy.sha256"
cmp -s "$F/merge/pkg-ext4.sha256" "$F/merge/pkg-copy.sha256" && cmp -s "$NE/build/llvm-pie.elf" "$D/title/llvm-pie.elf" || { st "COPY MISMATCH"; exit 1; }
st "copied to out-titlefix-rc6/ and compared: $(wc -l < "$F/merge/pkg-copy.sha256") package files identical"
python3 "$FT/switch_state.py" "$V_UPA" "$V_UPB" "$T" "$TB" "state C(rc4)" > "$F/merge/switch-back-to-C4.txt" 2>&1 || { st "switch back to C(rc4) FAILED: $(tail -1 "$F/merge/switch-back-to-C4.txt")"; exit 1; }
st "A back in state C(rc4) sources: $(tail -1 "$F/merge/switch-back-to-C4.txt") (objects are state T; the next child build recompiles them)"
st "DONE: title-fix eboot $(sha256sum "$D/title/PPSA99732/eboot.bin" | cut -c1-64) rc6+stage 1, pairs with out-rc6/child (IPC $IPCT)"
IN
cat > /tmp/ogptf-outer-$$.sh <<'OUT2'
#!/bin/bash
cd /
LKF=/tmp/omni-gpupages-ls1b.lock; ( umask 0; : >> "$LKF" ) 2>/dev/null; exec 9<"$LKF"; flock -n 9 || { echo "another ls1b build is running"; exit 0; }
O='/path/to/workspace/outputs'; F="$O/omni-gpupages-ls1b/titlefix"
st(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$F/steps.txt"; }
UP=/home/builder/ogp-ls1b-up-0; WK=/home/builder/ogp-ls1b-work-0; UPB=/home/builder/ogp-ls1b-upB-0; WKB=/home/builder/ogp-ls1b-workB-0; MNB=/home/builder/ogp-ls1b-B-mnt
UPT=/home/builder/ogp-ls1b-upT-0; WKT=/home/builder/ogp-ls1b-workT-0; MNT=/home/builder/ogp-ls1b-T-mnt; EW=/home/builder/ogp-ls1b-ews
for d in /home/builder/s3/.s3-marker "$UP/.ogpls1b-marker" "$UPB" "$EW/build.py"; do [ -e "$d" ] || { st "missing $d: stopping"; exit 1; }; done
rm -rf "$UPT" "$WKT" "$WK" "$WKB"; mkdir -p "$UPT" "$WKT" "$WK" "$WKB" "$MNT" "$MNB"
# ownership BEFORE mounting: a recursive chown through a mounted overlay copies every lower file up
chown -R builder:builder "$UPT" "$WKT" "$WK" "$WKB"; chown builder:builder "$MNT" "$MNB"
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UP,workdir=$WK" /home/builder/s1 || { st "overlay A failed"; exit 1; }
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UPB,workdir=$WKB" "$MNB" || { st "overlay B failed"; exit 1; }
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UPT,workdir=$WKT" "$MNT" || { st "overlay T failed"; exit 1; }
touch "$MNT/.s34d-marker" "$MNT/.launche-marker"; chown builder:builder "$MNT/.s34d-marker" "$MNT/.launche-marker"
mount --bind "$EW" "$O/omni-gpupages-ls1b-eboot-bind" || { st "bind mount failed"; exit 1; }
st "overlays: A on /home/builder/s1 ($UP), B on $MNB ($UPB, state C(rc4) sources), T on $MNT ($UPT, fresh); eboot workspace $EW bound"
export V_UPA="$UP" V_UPB="$UPB" V_UPT="$UPT"
exec runuser -u builder -- bash "$V_INNER"
OUT2
sed -i 's/\r$//' /tmp/ogptf-inner-$$.sh /tmp/ogptf-outer-$$.sh; chmod 755 /tmp/ogptf-inner-$$.sh /tmp/ogptf-outer-$$.sh
V_INNER=/tmp/ogptf-inner-$$.sh unshare -m --propagation private bash /tmp/ogptf-outer-$$.sh > "$F/native-build.log" 2>&1 < /dev/null
echo "title-fix build finished: exit $? (see $F/steps.txt)"
