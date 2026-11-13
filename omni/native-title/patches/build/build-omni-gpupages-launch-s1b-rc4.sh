#!/bin/bash
# omni-gpu-pages launch + stage 1/1b: REBASE the child on rc4 (incremental), title d983581f unchanged.
# Reuses the two-state build's tree A (/home/builder/ogp-ls1b-up-<uid>: objects + state C rc3 sources) and the eboot
# workspace; rebuilds overlay B from scratch with state C' = s3.4d base + the omni-launch rc4 CHILD units (order A of
# build-omni-launch-child.sh VARIANT=rc4: rc3 + OMNI_NET_HDRBUF_OPTIN_V1 via apply_launch_switches --hdrbuf-optin, and
# OMNI_MEMPRESSURE_V2 from omni-launch/mempaint-rc4/src) + stage 1 + async gate; proves B = rc4's recorded tree before
# stage 1; switches A to B; incremental ninja; generated IPC code must equal the title's (da4a7562); relinks the child
# with rc4's recipe + the stage-1 link; same gates; keys/additivity against rc4 e48c0001.
# Same lock (/tmp/omni-gpupages-ls1b.lock), nice 19, ionice idle, -j4. Output: outputs/omni-gpupages-ls1b/out-rc4/child.
O='/path/to/workspace/outputs'; P="$O/omni-gpupages-ls1b"
cat > /tmp/ogpls1b4-inner-$$.sh <<'IN'
#!/bin/bash
O='/path/to/workspace/outputs'; P="$O/omni-gpupages-ls1b"
NE="$O/omni-gpupages-ls1b-eboot-bind"; NC="$O/omni-gpupages-ls1b-child-bind"
J="$O/omni-jank"; A="$O/omni-ack"; M="$O/omni-crash-memloop"; MP="$O/omni-mem-paint"; L="$O/omni-launch"; S1="$O/omni-gpu-pages/stage1"
W=/home/builder/ogp; MB="$W/build-ps5-zink"; CP2="$W/cp2"; SRCM="$W/mesa-1ba9874f478657ccf6da72ce55f0260164cc0bd0-ogp"; PSDK=/opt/ps5-payload-sdk
UPV='/path/to/PS5_Vulkan'   # a checkout of PS5_Vulkan (Mihawk-99), for tooling/gpu-broker
T=/home/builder/s1; TB=/home/builder/ogp-ls1b-B-mnt; B=$T/build; LK=/home/builder/ogp-ls1b-link4; LL=/usr/lib/llvm-21/bin
R4="$L/child-rc4"; L4="$P/logs4"; M4="$P/merge4"
st(){ echo "$(date -u +%FT%TZ) [rc4] $*" | tee -a "$P/steps.txt"; }
export OMNI_SECLIBS=/home/builder/omni-seclibs/stage/user/homebrew/lib SOURCE_DATE_EPOCH=1793793600
[ -e $T/.ogpls1b-marker ] && [ -e $TB/.ogpls1bB-marker ] || { st "overlays missing: refusing"; exit 1; }
rm -rf "$LK" "$L4" "$M4" "$P/out-rc4" "$P/patches-gpupages-C4"; mkdir -p "$LK" "$L4/C" "$M4/patches-jank" "$M4/patches-ack" "$M4/patches-mem"
st "rebase on rc4 start: A keeps title-built objects; B rebuilt from s3 with the rc4 child units; load $(cut -d' ' -f1-3 /proc/loadavg)"
cd "$NE" || exit 1
python3 "$NE/tools/apply_s3_webkit.py" $TB > "$L4/C/apply-webkit.log" 2>&1 && python3 "$NE/tools/apply_s31_pna.py" $TB > "$L4/C/apply-pna.log" 2>&1 || { st "B base FAILED"; exit 1; }
for f in "$NE"/engine-patches/entry/*; do cp "$f" "$TB/engine/entry/" || { st "copy FAILED"; exit 1; }; done
for x in apply_viewtransition apply_yt apply_soak_read; do python3 "$NE/tools/$x.py" $TB > "$L4/C/$x.log" 2>&1 || { st "$x FAILED"; exit 1; }; done
cd "$NC" || exit 1
python3 "$NC/tools/apply_nomini.py" $TB > "$L4/C/apply_nomini.log" 2>&1 && python3 "$NC/tools/apply_heapcap.py" $TB > "$L4/C/apply_heapcap.log" 2>&1 \
  && python3 "$NC/tools/apply_mallocmini.py" $TB > "$L4/C/apply_mallocmini.log" 2>&1 \
  && python3 "$L/tools/apply_launch_switches.py" $TB --s34g --check-stock=/home/builder/s3 > "$L4/C/apply_switch_s34g.log" 2>&1 || { st "S34G unit FAILED"; exit 1; }
grep -q 'S34G SWITCH CHECK PASS' "$L4/C/apply_switch_s34g.log" || { st "s34g-off projection check FAILED"; exit 1; }
python3 "$NC/tools/apply_net.py" $TB --no-diag > "$L4/C/apply_net.log" 2>&1 && python3 "$L/tools/apply_launch_switches.py" $TB --net > "$L4/C/apply_switch_net.log" 2>&1 || { st "NET unit FAILED"; exit 1; }
python3 "$NC/tools/apply_h2fix.py" $TB > "$L4/C/apply_h2fix.log" 2>&1 && python3 "$L/tools/apply_launch_switches.py" $TB --hdrbuf-optin > "$L4/C/apply_switch_hdrbuf.log" 2>&1 || { st "H2B unit (rc4: hdrbuf opt-in) FAILED: $(tail -2 "$L4/C/apply_switch_hdrbuf.log")"; exit 1; }
python3 "$M/tools/apply_swdec_pad.py" $TB > "$L4/C/apply_swdec_pad.log" 2>&1 || { st "SWPAD unit FAILED"; exit 1; }
OMNI_JANK_FIX_ONLY=1 OMNI_JANK_SRC="$NC/src" OMNI_JANK_PATCHES="$M4/patches-jank" python3 "$J/tools/apply_jank_page.py" $TB > "$L4/C/apply_jank_page.log" 2>&1 || { st "PRECTS unit FAILED"; exit 1; }
OMNI_ACK_SRC="$A/src" OMNI_ACK_PATCHES="$M4/patches-ack" python3 "$A/tools/apply_ack_child.py" $TB > "$L4/C/apply_ack_child.log" 2>&1 \
  && python3 "$L/tools/apply_launch_switches.py" $TB --ack --ack-inc="$M4/patches-ack" > "$L4/C/apply_switch_ack.log" 2>&1 || { st "ACK unit FAILED"; exit 1; }
OMNI_MEMPAINT_SRC="$L/mempaint-rc4/src" OMNI_MEMPAINT_PATCHES="$M4/patches-mem" python3 "$MP/tools/apply_mempaint.py" $TB > "$L4/C/apply_mempaint.log" 2>&1 || { st "MEM unit (rc4 V2) FAILED: $(tail -2 "$L4/C/apply_mempaint.log")"; exit 1; }
python3 - "$V_UPB" "$R4/merge/order-compare.txt" > "$M4/identity-C4.txt" 2>&1 <<'PY'
import hashlib, os, sys
up, rec_path = sys.argv[1:3]
rec = {}
for l in open(rec_path):
    x = l.split()
    if x and x[0] == 'same': rec[x[-1]] = x[1]
ok = bad = 0; out = []
for root, dirs, files in os.walk(up):
    rel = os.path.relpath(root, up)
    if rel == 'build' or rel.startswith('build/'): dirs[:] = []; continue
    for f in files:
        p = './' + os.path.normpath(os.path.join(rel, f))
        if os.path.basename(p).startswith('.') or p.endswith('link-command.json'): continue
        h = hashlib.sha256(open(os.path.join(up, p), 'rb').read()).hexdigest()
        if rec.get(p) == h: ok += 1; out.append(f'same {h} {p}')
        else: bad += 1; out.append(f'DIFF {h} {p} (recorded {rec.get(p)})')
for p in rec:
    if not os.path.exists(os.path.join(up, p)): bad += 1; out.append(f'MISSING {p}')
print('\n'.join(sorted(out))); print(f'RESULT state C(rc4) vs the rc4 child tree: {ok} changed files = the recorded text, {bad} not')
sys.exit(1 if bad else 0)
PY
RC=$?; st "PROOF 1: $(tail -1 "$M4/identity-C4.txt")"
[ "$RC" = 0 ] || { st "state C(rc4) is NOT rc4's tree: stopping ($(grep -E '^(DIFF|MISSING)' "$M4/identity-C4.txt" | head -4 | tr '\n' ' ' | cut -c1-600))"; exit 1; }
IPC=$(cd "$V_UPB" && find . -path ./build -prune -o -type f \( -name '*.messages.in' -o -name '*.serialization.in' \) -print)
[ -z "$IPC" ] || { st "an rc4 unit changes an IPC definition ($IPC): stopping"; exit 1; }
mkdir -p "$P/patches-gpupages-C4"
OGP_S1_PATCHES="$P/patches-gpupages-C4" python3 "$S1/tools/apply_gpupages_child.py" $TB > "$L4/C/apply_gpupages.log" 2>&1 || { st "stage-1 patches FAILED on rc4: $(tail -3 "$L4/C/apply_gpupages.log" | tr '\n' ' ')"; exit 1; }
python3 "$S1/tools/apply_gpupages_async.py" $TB > "$L4/C/apply_async.log" 2>&1 || { st "async gate FAILED"; exit 1; }
st "stage 1 + async applied on state C(rc4) ($(grep -c '^patched' "$L4/C/apply_gpupages.log") files; drawingarea.inc $(sha256sum "$TB/webkit/Source/WebKit/WebProcess/WebPage/CoordinatedGraphics/ogp-s1-drawingarea.inc" | cut -c1-8))"
# switch A to B (state C rc4)
python3 - "$V_UPA" "$V_UPB" "$T" "$TB" > "$M4/switch-to-C4.txt" 2>&1 <<'PY'
import os, shutil, sys
upa, upb, ta, tb = sys.argv[1:5]
def changed(up):
    s = set()
    for root, dirs, files in os.walk(up):
        rel = os.path.relpath(root, up)
        if rel == 'build' or rel.startswith('build/'): dirs[:] = []; continue
        for f in files:
            p = os.path.normpath(os.path.join(rel, f))
            if os.path.basename(p).startswith('.') or p.endswith('link-command.json'): continue
            s.add(p)
    return s
paths = sorted(changed(upa) | changed(upb)); n = {'copied': 0, 'removed': 0, 'same': 0}
for p in paths:
    a, b = os.path.join(ta, p), os.path.join(tb, p)
    if os.path.exists(b):
        if os.path.exists(a) and open(a, 'rb').read() == open(b, 'rb').read(): n['same'] += 1; continue
        os.makedirs(os.path.dirname(a), exist_ok=True); shutil.copyfile(b, a); n['copied'] += 1; print('copied', p)
    elif os.path.exists(a): os.remove(a); n['removed'] += 1; print('removed', p)
bad = [p for p in paths if os.path.exists(os.path.join(tb, p)) != os.path.exists(os.path.join(ta, p))
       or (os.path.exists(os.path.join(tb, p)) and open(os.path.join(ta, p), 'rb').read() != open(os.path.join(tb, p), 'rb').read())]
print(f"RESULT {n['copied']} copied, {n['removed']} removed, {n['same']} already equal; after the switch {len(paths) - len(bad)}/{len(paths)} changed paths equal state C(rc4), {len(bad)} differ")
sys.exit(1 if bad else 0)
PY
[ $? = 0 ] || { st "switch FAILED: $(tail -1 "$M4/switch-to-C4.txt")"; exit 1; }
st "switched A to state C(rc4): $(tail -1 "$M4/switch-to-C4.txt") [$(grep '^copied\|^removed' "$M4/switch-to-C4.txt" | sed 's#.*/##' | tr '\n' ' ' | cut -c1-300)]"
CC=$(find "$B" -maxdepth 3 -name cmakeconfig.h | head -1)
nice -n 19 ionice -c3 ninja -k 0 -C "$B" -j4 OmniEngine > "$L4/ninja-C4.log" 2>&1 || { st "ninja FAILED: $(grep -m12 -E 'error:|FAILED' "$L4/ninja-C4.log" | tr '\n' ' ' | cut -c1-2500)"; exit 1; }
grep -q "define ENABLE_ASYNC_SCROLLING 1" "$CC" || { st "lost the async configuration: stopping"; exit 1; }
IPCC=$(find "$B" -path '*DerivedSources*' \( -name '*MessageReceiver.cpp' -o -name '*Messages.h' -o -name 'GeneratedSerializers.cpp' -o -name 'GeneratedSerializers.h' \) -type f -exec sha256sum {} + 2>/dev/null | sort -k2 | sha256sum | cut -c1-16)
[ "$IPCC" = da4a75622a0a473f ] || { st "generated IPC code $IPCC differs from the title's da4a75622a0a473f: stopping"; exit 1; }
st "incremental ninja ok: $(grep -c '^\[' "$L4/ninja-C4.log") steps, $(grep -c 'warning:' "$L4/ninja-C4.log") warnings; generated IPC code = the title's (da4a7562)"
cd "$NC" || exit 1
python3 "$NC/make_link_command.py" > "$L4/link-command-child.log" 2>&1 || { st "child link command FAILED"; exit 1; }
CF=(-std=c11 -O2 -Wall -Wextra -Wno-unused-parameter -fPIC "-I$SRCM/include" "-I$UPV/tooling/gpu-broker"); mkdir -p "$LK/s1obj"
for x in ogp-s1-child ogp_dri_nodrm_stubs_weak ogp_payload_libc_weak; do "$PSDK/bin/prospero-clang" "${CF[@]}" -c "$S1/src/$x.c" -o "$LK/s1obj/$x.o" >> "$L4/s1obj.log" 2>&1 || { st "compile $x FAILED"; exit 1; }; done
OGP_S1_MAP="$LK/child.map" python3 "$S1/tools/s1_link_inputs.py" "$LK/s1-link-inputs.json" "$MB" "$CP2" "$LK/s1obj" > "$L4/s1-link-inputs.log" 2>&1 || { st "link inputs FAILED"; exit 1; }
python3 "$S1/tools/patch_child_build.py" "$NC/child_build.py" > "$L4/patch-child-build.log" 2>&1 || { st "child_build patch FAILED"; exit 1; }
SECL=/home/builder/ogp-ls1b-seclibs; rm -rf "$SECL"; mkdir -p "$SECL" && cp -dR --preserve=mode,timestamps /home/builder/omni-seclibs/stage/user/homebrew/lib/*.a "$SECL"/ \
  && rm -f "$SECL/libcurl.a" && cp /home/builder/yt-libs/seclibs/libcurl.a "$SECL/libcurl.a" || { st "h2 seclibs FAILED"; exit 1; }
PL=/home/builder/yt-libs/stage/user/homebrew/lib; EXTRA="$PL/libnghttp2.a:$PL/libbrotlidec.a:$PL/libbrotlicommon.a"
OMNI_SECLIBS="$SECL" OMNI_NET_EXTRA_LIBS="$EXTRA" OMNI_NET_LABEL="omni-launch-rc4-gpupages" OMNI_CHILD_OUT="$LK/child" OGP_S1_LINK=1 OGP_S1_LINK_INPUTS="$LK/s1-link-inputs.json" \
  python3 "$NC/child_build.py" > "$L4/child-build.log" 2>&1 || { st "child link FAILED: $(grep -o 'undefined symbol: .*\|duplicate symbol: .*' "$LK/child/link.log" 2>/dev/null | sort -u | head -8 | tr '\n' ' ' | cut -c1-1200)"; exit 1; }
$LL/llvm-nm -u "$LK/child/omni-engine-child-unstripped.elf" | awk '{print $NF}' | sort -u > "$LK/child-undef.txt"; comm -12 "$LK/child-undef.txt" "$CP2/archive-defs.txt" > "$M4/child-weakref-left.txt"
[ -s "$M4/child-weakref-left.txt" ] && { st "child WEAK-REF GATE FAILED"; exit 1; }
/opt/ps5-payload-sdk/bin/llvm-strip "$LK/child/omni-engine-child-unstripped.elf" -o "$LK/restrip.elf" 2>/dev/null; cmp -s "$LK/restrip.elf" "$LK/child/omni-engine-child.elf" || { st "re-strip mismatch"; exit 1; }
python3 "$L/tools/elfguard.py" "$LK/child/omni-engine-child.elf" "$R4/child-base/omni-engine-child.elf" > "$L4/elfguard.log" 2>&1; EG=$?
st "CHILD (state C rc4) linked on ext4: $(sha256sum "$LK/child/omni-engine-child.elf" | cut -c1-64); weak-ref 0; re-strip = shipped; $(tail -1 "$L4/elfguard.log" | cut -c1-60) (exit $EG)"
[ "$EG" = 0 ] || exit 1
D="$P/out-rc4/child"; mkdir -p "$D"; cp "$LK/child/omni-engine-child.elf" "$LK/child/omni-engine-child-unstripped.elf" "$LK/child/receipt.json" "$D/" || { st "copy FAILED"; exit 1; }
cmp -s "$LK/child/omni-engine-child.elf" "$D/omni-engine-child.elf" && cmp -s "$LK/child/omni-engine-child-unstripped.elf" "$D/omni-engine-child-unstripped.elf" || { st "COPY MISMATCH"; exit 1; }
C="$D/omni-engine-child.elf"; RCH="$R4/child/omni-engine-child.elf"
S1K="$M4/keys-stage1.txt"; printf '%s\n' "OMNI GPUPAGES" "/data/omni/gpu-pages-stage1.flag" "/data/omni/gpu-pages-stage1-off.flag" "/data/omni/gpu-pages-async.flag" "/data/omni/gpu-pages-async-off.flag" \
  "OMNI GPUPAGES async scrolling" "is not stat()able" "/user/homebrew/lib/libEGL.so.1" "cannot resolve real graphics function" "mq-boundary" "OMNI_HDR_CAPS_V1" "net-on-hdrbuf.flag" > "$S1K"
{ echo "== child: launch keys, new vs rc4"; while IFS= read -r k; do [ -n "$k" ] || continue; a=$(grep -c -a -- "$k" "$C"); b=$(grep -c -a -- "$k" "$RCH"); printf "%-6s %-44s new %s rc4 %s\n" "$([ "$a" = "$b" ] && echo same || echo DIFF)" "$k" "$a" "$b"; done < "$L/tools/keys-child.txt"
  echo "== layer keys (new / rc4)"; while IFS= read -r k; do printf "%-44s %s / %s\n" "$k" "$(grep -c -a -- "$k" "$C")" "$(grep -c -a -- "$k" "$RCH")"; done < "$S1K"; } > "$M4/keys-compare.txt" 2>&1
cat "$L/tools/keys-child.txt" "$S1K" > "$M4/keys-child-plus-s1.txt"
python3 "$L/tools/additivity.py" --label child-rc4 --keys "$M4/keys-child-plus-s1.txt" --out "$M4" --target "$C" --base "$RCH" \
  --plus "$O/omni-gpupages-s1-child/child/omni-engine-child.elf" --minus "$O/omni-ack-child/child/omni-engine-child.elf" --strings-only > "$M4/additivity-child.log" 2>&1
st "keys vs rc4: $(grep -c '^same' "$M4/keys-compare.txt") same, $(grep -c '^DIFF' "$M4/keys-compare.txt") differ; UNION: $(grep '^RESULT' "$M4/additivity-child.log" | cut -c1-120); mismatches: $(grep '^MISMATCH' "$M4/additivity-child.log" | awk '{$1=""; print}' | cut -c1-60 | tr '\n' ';' | cut -c1-400)"
{ sha256sum "$C" "$D/omni-engine-child-unstripped.elf" "$RCH"; stat -c '%s %n' "$C"; echo "pairs with title eboot.bin d983581f (generated IPC da4a7562)"; } > "$P/checks-rc4.txt"
st "LAUNCH(rc4)+S1B CHILD ok: $(sha256sum "$C" | cut -c1-64) (pairs with eboot.bin d983581f)"
IN
sed -i 's/\r$//' /tmp/ogpls1b4-inner-$$.sh; chmod 755 /tmp/ogpls1b4-inner-$$.sh
cat > /tmp/ogpls1b4-outer-$$.sh <<'OUT2'
#!/bin/bash
cd /
LKF=/tmp/omni-gpupages-ls1b.lock; ( umask 0; : >> "$LKF" ) 2>/dev/null; exec 9<"$LKF"; flock -n 9 || { echo "another ls1b build is running"; exit 0; }
O='/path/to/workspace/outputs'; P="$O/omni-gpupages-ls1b"
st(){ echo "$(date -u +%FT%TZ) [rc4] $*" | tee -a "$P/steps.txt"; }
U=${V_REAL_UID:-$(id -u)}; UP=/home/builder/ogp-ls1b-up-$U; WK=/home/builder/ogp-ls1b-work-$U; UPB=/home/builder/ogp-ls1b-upB-$U; WKB=/home/builder/ogp-ls1b-workB-$U; MNB=/home/builder/ogp-ls1b-B-mnt
EW=/home/builder/ogp-ls1b-ews; CW=/home/builder/ogp-ls1b-cws4
[ -d "$UP" ] && [ -d "$EW" ] || { st "the two-state build's tree/workspace is gone: run build-omni-gpupages-launch-s1b2.sh first"; exit 1; }
rm -rf "$WK" "$UPB" "$WKB" "$CW"; mkdir -p "$WK" "$UPB" "$WKB" "$MNB" "$CW"
for x in "$O/omni-launch/child-rc4"/*; do b=$(basename "$x"); case " child child-base merge union wsl " in *" $b "*) continue;; esac; case "$b" in *.log|build-steps.txt|checks.txt|S34G-HOSTTEST.txt) continue;; esac; cp -a "$x" "$CW/" || { st "rc4 workspace copy FAILED: $b"; exit 1; }; done
[ -n "$V_AS_BUILDER" ] && chown -R builder:builder "$WK" "$UPB" "$WKB" "$MNB" "$CW"
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UP,workdir=$WK" /home/builder/s1 2>/tmp/ogpls1b4-ovl.err || { st "overlay A failed ($(cat /tmp/ogpls1b4-ovl.err))"; exit 1; }
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UPB,workdir=$WKB" "$MNB" 2>/tmp/ogpls1b4B-ovl.err || { st "overlay B failed ($(cat /tmp/ogpls1b4B-ovl.err))"; exit 1; }
touch /home/builder/s1/.ogpls1b-marker "$MNB/.ogpls1bB-marker" || { st "trees not writable"; exit 1; }
mount --bind "$EW" "$O/omni-gpupages-ls1b-eboot-bind" && mount --bind "$CW" "$O/omni-gpupages-ls1b-child-bind" || { st "bind mounts failed"; exit 1; }
st "A kept ($UP); B fresh ($UPB); rc4 child recipe workspace $CW"
export V_UPA="$UP" V_UPB="$UPB"
if [ -n "$V_AS_BUILDER" ]; then exec runuser -u builder -- bash "$V_INNER"; fi
bash "$V_INNER"
OUT2
sed -i 's/\r$//' /tmp/ogpls1b4-outer-$$.sh; chmod 755 /tmp/ogpls1b4-outer-$$.sh
cd /
if [ "$(id -u)" = 0 ]; then
  V_REAL_UID=0 V_AS_BUILDER=1 V_INNER=/tmp/ogpls1b4-inner-$$.sh setsid nohup unshare -m --propagation private bash /tmp/ogpls1b4-outer-$$.sh > "$P/native-build-rc4.log" 2>&1 < /dev/null &
else
  V_REAL_UID=$(id -u) V_INNER=/tmp/ogpls1b4-inner-$$.sh setsid nohup unshare -Urm --propagation private bash /tmp/ogpls1b4-outer-$$.sh > "$P/native-build-rc4.log" 2>&1 < /dev/null &
fi
echo "rc4 rebase started pid $!"
