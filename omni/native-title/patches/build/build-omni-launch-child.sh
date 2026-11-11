#!/bin/bash
# omni-launch CHILD (omni-engine-child.elf). Base: s3.4d's child tree; the base child is relinked first from the same
# tree and must be 7b810ea5. Every feature has a FLAG-FILE kill switch that reaches the child (raster-env.txt passes only
# OMNI_RASTER_* keys to the child, so environment names otherwise are dead there; flag files are read with access()):
#   VARIANT=clean (outputs/omni-launch/child, the launch child):
#     s3.4g JS (OMNI_NO_MINI_MODE_V1 + OMNI_HEAP_CAP_V1 + OMNI_MALLOC_MINI_V1) + OMNI_S34G_SWITCH_V1  [s34g-off.flag]
#     omni-net 5 fixes --no-diag + OMNI_NET5_SWITCH_V1 [net5-off.flag; each net-off-<name>.flag]; linked h2-capable,
#       HTTP/2 OFF unless net-on-h2.flag; OMNI_NET_HDRBUF_V1 (fix B) [net-off-hdrbuf.flag]
#     OMNI_SWDEC_PAD_V1 (memory-safety fix, no switch: off = another child)
#     OMNI_PAINT_RECTS_V1 fix-only + OMNI_PAINT_RECTS_V2 (omni-mem-paint) [paint-rects-off.flag | OMNI_RASTER_PAINT_RECTS=0]
#     OMNI_ACK_V1 child + OMNI_ACK_SWITCH_V1 [ack-pace-off.flag | OMNI_RASTER_ACK_PACE=0]
#     OMNI_MEMPRESSURE_V1 (omni-mem-paint) [mempressure-off.flag]
#   VARIANT=rc3 (outputs/omni-launch/child-rc3): clean + OMNI_NET_JSCACHE_OPTIN_V1 -- the JS bytecode cache is OFF unless
#     /data/omni/net-on-jscache.flag (the console bisect convicted it). The diag twin follows rc3; VARIANT=clean keeps rc2.
#   VARIANT=rc4 (outputs/omni-launch/child-rc4): rc3 + OMNI_NET_HDRBUF_OPTIN_V1 (hdrbuf OFF unless net-on-hdrbuf.flag) +
#     OMNI_MEMPRESSURE_V2 (omni-launch/mempaint-rc4: no ramSize/4 clamp, floors 1536/1792 MiB, one line per transition).
#     The diag twin follows rc4.
#   VARIANT=fallback (outputs/omni-launch/child-fallback): the same WITHOUT net5 and WITHOUT s3.4g; stock (h1-only)
#     libcurl link, so HTTP/2 cannot turn on; hdrbuf still applies to HTTP/1.1.
#   VARIANT=diag (outputs/omni-launch/child-diag): clean + OMNI_YTPROF_V1 (ytprof.flag) + OMNI_JANK_PAGE_V1 (jank.flag)
#     + the omni-net per-request diagnostic (netprof.flag).
# Units sharing files are applied in TWO orders on two private overlays and every changed file is compared byte for byte.
# Links go to ext4 (/home/builder/launchc-<variant>-out) and are copied into outputs and compared (a 1.4 GB lld output
# written straight onto /mnt/c came back corrupted for another build). SOURCE_DATE_EPOCH=1793793600. Own lock, overlays,
# seclibs copy and /tmp names per variant. Never writes another build's tree (the s3.4g appliers are this folder's
# copies). Startup/bootstrap code untouched. Build only: never deploys, never touches the console.
VARIANT=${VARIANT:-clean}; case "$VARIANT" in diag) SUB=child-diag;; fallback) SUB=child-fallback;; rc3) SUB=child-rc3;; rc4) SUB=child-rc4;; rc5) SUB=child-rc5;; rc5np) SUB=child-rc5np;; rc6) SUB=child-rc6;; *) VARIANT=clean; SUB=child;; esac
O='/path/to/workspace/outputs'; N="$O/omni-launch/$SUB"
cat > /tmp/launchc-$VARIANT-inner-$$.sh <<'IN'
#!/bin/bash
O='/path/to/workspace/outputs'; N="$O/omni-launch-$VARIANT-bind"; NR="$V_NREAL"
J="$O/omni-jank"; A="$O/omni-ack"; M="$O/omni-crash-memloop"; NET="$O/omni-net"; MP="$O/omni-mem-paint"; L="$O/omni-launch"
MPS="$MP/src"; MPH="$MP/hosttest"; RC4=0; case "$VARIANT" in rc4|rc5|rc5np|rc6|diag) RC4=1; MPS="$L/mempaint-rc4/src"; MPH="$L/mempaint-rc4/hosttest";; esac
st(){ echo "$(date -u +%FT%TZ) [$VARIANT] $*" | tee -a "$N/build-steps.txt"; }
export OMNI_SECLIBS=/home/builder/omni-seclibs/stage/user/homebrew/lib
export SOURCE_DATE_EPOCH=1793793600
TA=/home/builder/s1; TB=/home/builder/launchcb-$VARIANT-mnt; MA="$N/merge/orderA"; MB="$N/merge/orderB"; LOUT=/home/builder/launchc-$VARIANT-out
[ -e $TA/.launchc-marker ] && [ -e $TB/.launchcb-marker ] || { st "overlays missing: refusing to build in the shared s1 tree"; exit 1; }
rm -rf "$N/merge" "$N/wsl" "$N/patches-nomini" "$N/patches-heapcap" "$N/patches-mallocmini" "$N/patches" "$N/patches-h2fix" "$N/patches-ytprof"; mkdir -p "$N/wsl" "$MA" "$MB"
rm -rf "$LOUT"; mkdir -p "$LOUT"
cpv(){ local i; for i in 1 2 3 4; do cp "$@" 2>> "$N/wsl/copy-errors.log" && return 0; echo "copy attempt $i failed: $*" >> "$N/wsl/copy-errors.log"; sleep 10; done; return 1; }
st "build start (A = $TA, B = $TB: private overlays of s3; links on ext4 $LOUT; SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH)"
for t in apply_nomini apply_heapcap apply_mallocmini; do cmp -s "$N/tools/$t.py" "$O/omni-ytprof/tools/$t.py" || { st "tools/$t.py is not omni-ytprof's: stopping"; exit 1; }; done
# ---------------------------------------------------------------- 0. host suites that need no tree
H=$(mktemp -d /tmp/launchc-h-XXXXXX); : > "$H/jank.flag"
g++ -std=c++20 -O1 -Wall -Wextra -Wno-unused-parameter -I"$N/src" -o "$H/hdrbuf" "$N/hdrbuf_test.cpp" > "$N/wsl/hdrbuf-build.log" 2>&1 || { st "hdrbuf test build FAILED"; exit 1; }
"$H/hdrbuf" > "$N/wsl/hdrbuf-test.log" 2>&1; HB=$?; grep -qE "FAILURES|FAILED" "$N/wsl/hdrbuf-test.log" && HB=1
if : > /data/omni/net-off-hdrbuf.flag 2>/dev/null; then "$H/hdrbuf" offcheck > "$N/wsl/hdrbuf-offcheck.log" 2>&1 || HB=1; rm -f /data/omni/net-off-hdrbuf.flag; else echo "SKIPPED: /data/omni not writable on this host (the shipped kill-switch path is fixed)" > "$N/wsl/hdrbuf-offcheck.log"; fi
st "NET hdrbuf unit: exit $HB, $(grep -cE '^ *ok ' "$N/wsl/hdrbuf-test.log") ok lines; kill switch: $(tail -1 "$N/wsl/hdrbuf-offcheck.log" | cut -c1-80)"
[ "$HB" = 0 ] || { st "NET hdrbuf unit FAILED"; exit 1; }
CXX="clang++ -std=c++17 -O1 -Wall -Wextra -Werror -pthread"
$CXX -DOMNI_MEM_HOSTTEST -DOMNI_MEM_OFF_FLAG="\"$H/off.flag\"" -I"$MPS" "$MPH/mempressure_test.cpp" -o "$H/mpt" > "$N/wsl/mempressure-build.log" 2>&1 || { st "mempressure gate build FAILED"; exit 1; }
"$H/mpt" > "$N/wsl/mempressure-test.log" 2> "$N/wsl/mempressure-test.stderr" || { st "mempressure gate FAILED"; exit 1; }
: > "$H/off.flag"; "$H/mpt" killswitch > "$N/wsl/mempressure-killswitch.log" 2>&1 || { st "mempressure kill-switch gate FAILED"; exit 1; }; rm -f "$H/off.flag"
st "MEM gate: $(tail -1 "$N/wsl/mempressure-test.log"); $(tail -1 "$N/wsl/mempressure-killswitch.log")"
if [ "$VARIANT" = diag ]; then
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror -I"$N/src" -DOMNI_JANK_FLAG_PATH="\"$H/jank.flag\"" "$N/jank_sink_test.cpp" -o "$H/jst" > "$N/wsl/jank-sink-build.log" 2>&1 \
    && "$H/jst" > "$N/wsl/jank-sink.log" 2>&1 || { st "jank sink gate FAILED"; exit 1; }
  st "jank sink gate: $(tail -1 "$N/wsl/jank-sink.log")"
fi
SW=/tmp/omni-launch-swstest
if [ ! -f $SW/lib/libswscale.a ]; then
  rm -rf $SW; mkdir -p $SW/src && tar -xf /home/builder/omni-seclibs/src/ffmpeg-7.1.5.tar.xz -C $SW/src && cd $SW/src/ffmpeg-7.1.5 \
  && PATH=/home/builder/omni-seclibs/stage/host/bin:/home/builder/omni-seclibs/build/nasm-2.16.03:$PATH ./configure --prefix=$SW --disable-everything --disable-programs --disable-doc --disable-avcodec --disable-avformat --disable-avdevice --disable-avfilter --disable-swresample --disable-postproc --enable-swscale --disable-debug > $SW/configure.log 2>&1 \
  && make -j6 > $SW/make.log 2>&1 && make install > /dev/null 2>&1; cd /
fi
gcc -O1 -I$SW/include "$M/swstest/swstest.c" -o "$H/swstest" -L$SW/lib -lswscale -lavutil -lm -lpthread -Wl,--unresolved-symbols=ignore-all > "$N/wsl/swstest-build.log" 2>&1 && "$H/swstest" > "$N/wsl/swstest.txt" 2>&1; SWR=$?
python3 - "$N/wsl/swstest.txt" > "$N/wsl/swstest-verdict.txt" 2>&1 <<'PY'
import re, sys
sec = None; exact = padded = 0; npad = 0
for l in open(sys.argv[1]):
    if l.startswith('== PADDED'): sec = 'pad'
    elif l.startswith('== same-size'): sec = 'exact'
    m = re.search(r': (\d+)/(\d+) sizes overflow', l)
    if m and sec == 'exact': exact += int(m[1])
    if m and sec == 'pad': padded += int(m[1]); npad += 1
ok = exact > 0 and npad > 0 and padded == 0
print(f'exact-buffer overflows {exact} (the bug, reproduced); padded-stride overflows {padded} over {npad} format pairs -> ' + ('PASS' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
PY
SWV=$?
st "SWDEC host model (FFmpeg 7.1.5 swscale): $(tail -1 "$N/wsl/swstest-verdict.txt" | cut -c1-200)"
[ "$SWR" = 0 ] && [ "$SWV" = 0 ] || { st "SWDEC model FAILED"; exit 1; }
rm -rf "$H"
# ---------------------------------------------------------------- 1. base tree on A and B
base_steps(){ local t="$1" D="$2"
  python3 "$N/tools/apply_s3_webkit.py" "$t" > "$D/apply-webkit.log" 2>&1 || return 1
  python3 "$N/tools/apply_s31_pna.py" "$t" > "$D/apply-pna.log" 2>&1 || return 2
  for f in "$N"/engine-patches/entry/*; do cp "$f" "$t/engine/entry/" || return 3; done
  python3 "$N/tools/apply_viewtransition.py" "$t" > "$D/apply_vt.log" 2>&1 || return 4
  python3 "$N/tools/apply_yt.py" "$t" > "$D/apply_yt.log" 2>&1 || return 5
  python3 "$N/tools/apply_soak_read.py" "$t" > "$D/apply_soak.log" 2>&1 || return 6; }
base_steps $TA "$MA" || { st "A base steps FAILED (rc $?)"; exit 1; }
base_steps $TB "$MB" || { st "B base steps FAILED (rc $?)"; exit 1; }
cd "$N" || exit 1
# ---------------------------------------------------------------- 2. the BASE child (link on ext4, copy, compare): must be 7b810ea5
nice -n 5 ninja -k 0 -C $TA/build -j6 OmniEngine > "$N/ninja-base.log" 2>&1 || { st "ninja (base) FAILED"; exit 1; }
python3 "$N/make_link_command.py" > "$N/link-command-base.log" 2>&1 || { st "link command (base) FAILED"; exit 1; }
OMNI_NET_LABEL=launch-base OMNI_CHILD_OUT="$LOUT/child-base" python3 "$N/child_build.py" > "$N/child-base-build.log" 2>&1 || { st "base child FAILED: $(tail -3 "$N/child-base-build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
rm -rf "$N/child-base"; mkdir -p "$N/child-base"; cpv "$LOUT/child-base/omni-engine-child.elf" "$LOUT/child-base/omni-engine-child-unstripped.elf" "$LOUT/child-base/receipt.json" "$N/child-base/" || { st "copying the base child FAILED"; exit 1; }
cmp -s "$LOUT/child-base/omni-engine-child.elf" "$N/child-base/omni-engine-child.elf" || { st "base child copy differs from the link: stopping"; exit 1; }
BH=$(sha256sum "$LOUT/child-base/omni-engine-child.elf" | cut -d' ' -f1); st "base child: $BH (linked on ext4, copy compared)"
[ "$BH" = 7b810ea5b5cdcbc899828635b329da42595b540ff51998513b7e8b21fd717c64 ] || { st "the base child is NOT 7b810ea5: stopping"; exit 1; }
# ---------------------------------------------------------------- 3. the units, in two orders
U_S34G(){ python3 "$N/tools/apply_nomini.py" "$1" > "$2/apply_nomini.log" 2>&1 && python3 "$N/tools/apply_heapcap.py" "$1" > "$2/apply_heapcap.log" 2>&1 \
  && python3 "$N/tools/apply_mallocmini.py" "$1" > "$2/apply_mallocmini.log" 2>&1 \
  && python3 "$L/tools/apply_launch_switches.py" "$1" --s34g --check-stock=/home/builder/s3 > "$2/apply_switch_s34g.log" 2>&1; }
NETARGS=--no-diag; [ "$VARIANT" = diag ] && NETARGS=; [ "$VARIANT" = rc5np ] && NETARGS=   # rc5np: + OMNI_NETPROF_V1 (netprof.flag)
JSCOPT=; [ "$VARIANT" = clean ] && JSCOPT=--no-jscache-optin   # rc2 recipe stays reproducible
U_NET(){ python3 "$N/tools/apply_net.py" "$1" $NETARGS > "$2/apply_net.log" 2>&1 && python3 "$L/tools/apply_launch_switches.py" "$1" --net $JSCOPT > "$2/apply_switch_net.log" 2>&1; }
U_H2B(){ python3 "$N/tools/apply_h2fix.py" "$1" > "$2/apply_h2fix.log" 2>&1 && { [ "$RC4" = 0 ] || python3 "$L/tools/apply_launch_switches.py" "$1" --hdrbuf-optin > "$2/apply_switch_hdrbuf.log" 2>&1; }; }
U_SWPAD(){ python3 "$M/tools/apply_swdec_pad.py" "$1" > "$2/apply_swdec_pad.log" 2>&1; }
U_PRECTS(){ mkdir -p "$2/patches-jank"; if [ "$VARIANT" = diag ]; then OMNI_JANK_SRC="$N/src" OMNI_JANK_PATCHES="$2/patches-jank" python3 "$J/tools/apply_jank_page.py" "$1" > "$2/apply_jank_page.log" 2>&1
  else OMNI_JANK_FIX_ONLY=1 OMNI_JANK_SRC="$N/src" OMNI_JANK_PATCHES="$2/patches-jank" python3 "$J/tools/apply_jank_page.py" "$1" > "$2/apply_jank_page.log" 2>&1; fi; }
U_ACK(){ mkdir -p "$2/patches-ack"; OMNI_ACK_SRC="$A/src" OMNI_ACK_PATCHES="$2/patches-ack" python3 "$A/tools/apply_ack_child.py" "$1" > "$2/apply_ack_child.log" 2>&1 \
  && python3 "$L/tools/apply_launch_switches.py" "$1" --ack --ack-inc="$2/patches-ack" > "$2/apply_switch_ack.log" 2>&1; }
U_MEM(){ mkdir -p "$2/patches-mem"; OMNI_MEMPAINT_SRC="$MPS" OMNI_MEMPAINT_PATCHES="$2/patches-mem" python3 "$MP/tools/apply_mempaint.py" "$1" > "$2/apply_mempaint.log" 2>&1; }
U_NCB(){ python3 "$O/omni-nc-blob/apply_nc_blob_copy.py" "$1/webkit" > "$2/apply_nc_blob.log" 2>&1 && grep -q 'applied at 2 sites' "$2/apply_nc_blob.log"; }
U_NAVP(){ python3 "$O/omni-navplatform/apply_nav_platform.py" "$1/webkit" > "$2/apply_nav_platform.log" 2>&1 && grep -q '^applied' "$2/apply_nav_platform.log"; }
U_JITV4(){ python3 "$O/omni-jit-fix/apply_jit_v4.py" "$1/webkit" > "$2/apply_jit_v4.log" 2>&1 && grep -q '^applied' "$2/apply_jit_v4.log"; }
U_YTPROF(){ python3 "$N/tools/apply_ytprof.py" "$1" > "$2/apply_ytprof.log" 2>&1; }
run_units(){ local t="$1" D="$2"; shift 2; for u in "$@"; do "U_$u" "$t" "$D" || { echo "$u"; return 1; }; done; }
# declared dependencies kept in both orders (everything else is swapped): apply_h2fix runs AFTER apply_net (its own
# documented contract: with H2B first the two insert into CurlRequest.cpp in the other order, see REPORT.md; the
# fallback child, which has no apply_net, proves hdrbuf applies on its own); the switch layer follows its component
# inside the same unit; diag: OMNI_JANK_PAGE_V1 needs OMNI_YTPROF_V1 first.
case "$VARIANT" in
  clean|rc3|rc4) ORDA="S34G NET H2B SWPAD PRECTS ACK MEM";        ORDB="MEM ACK PRECTS SWPAD NET H2B S34G";;
  rc5|rc5np) ORDA="S34G NET H2B SWPAD PRECTS ACK MEM NCB";    ORDB="NCB MEM ACK PRECTS SWPAD NET H2B S34G";;   # = shipped rc5-v3 (NAVP tested, not shipped)
  rc6)      ORDA="S34G NET H2B SWPAD PRECTS ACK MEM NCB JITV4"; ORDB="JITV4 NCB MEM ACK PRECTS SWPAD NET H2B S34G";;   # rc5 + OMNI_JSC_JIT_V4 (W^X JIT pool)
  fallback) ORDA="H2B SWPAD PRECTS ACK MEM";                 ORDB="MEM ACK PRECTS SWPAD H2B";;
  diag)     ORDA="YTPROF S34G NET H2B SWPAD PRECTS ACK MEM"; ORDB="MEM ACK S34G NET H2B SWPAD YTPROF PRECTS";;
esac
F=$(run_units $TB "$MB" $ORDB) || { st "order B ($ORDB) FAILED at unit $F: $(tail -3 "$MB"/apply_*.log | tr '\n' ' ' | cut -c1-600)"; exit 1; }
F=$(run_units $TA "$MA" $ORDA) || { st "order A ($ORDA) FAILED at unit $F: $(tail -3 "$MA"/apply_*.log | tr '\n' ' ' | cut -c1-600)"; exit 1; }
: > "$N/merge/order-compare.txt"; NDIFF=0; NF=0
for f in $( (cd "$V_UPA" && find . -type f ! -path './build/*' ! -name '.launchc*' ! -name 'link-command.json'; cd "$V_UPB" && find . -type f ! -path './build/*' ! -name '.launchc*' ! -name 'link-command.json') | sort -u); do
  NF=$((NF+1)); a=$(sha256sum "$TA/$f" 2>/dev/null | cut -c1-64); b=$(sha256sum "$TB/$f" 2>/dev/null | cut -c1-64)
  if [ "$a" = "$b" ]; then echo "same $a $f" >> "$N/merge/order-compare.txt"; else echo "DIFF A=$a B=$b $f" >> "$N/merge/order-compare.txt"; NDIFF=$((NDIFF+1)); fi
done
for f in patches-ack/ack-policy.inc patches-ack/ack-sink.inc patches-jank/paint-rects.inc patches-jank/paint-rects-fix-only.inc patches-mem/mempressure.inc patches-mem/paint-rects-v2.inc; do [ -e "$MA/$f" ] || continue
  cmp -s "$MA/$f" "$MB/$f" && echo "same-inc $f" >> "$N/merge/order-compare.txt" || { echo "DIFF-inc $f" >> "$N/merge/order-compare.txt"; NDIFF=$((NDIFF+1)); }; done
st "ORDER PROOF (child tree): $NF changed files compared, order A ($ORDA) vs order B ($ORDB): $NDIFF differ"
# diag only, documented resolution: OMNI_YTPROF_V1 and OMNI_JANK_PAGE_V1 each insert a self-contained declaration
# preamble (include-guarded externs + one RAII macro) after the same #include block of DrawingAreaCoordinatedGraphics.cpp
# that OMNI_ACK_V1 also follows, so the two orders place that block before or after ACK's block. Accepted only when it
# is the ONLY differing file, both orders hold the same multiset of lines, B is A with exactly one contiguous block moved,
# the block is the ytprof/jank declaration preamble, and nothing between the two positions uses it. A is built.
if [ "$VARIANT" = diag ] && [ "$NDIFF" = 1 ] && grep -q '^DIFF .*/CoordinatedGraphics/DrawingAreaCoordinatedGraphics.cpp$' "$N/merge/order-compare.txt"; then
  F=webkit/Source/WebKit/WebProcess/WebPage/CoordinatedGraphics/DrawingAreaCoordinatedGraphics.cpp
  python3 - "$TA/$F" "$TB/$F" > "$N/merge/diag-resolution.txt" 2>&1 <<'PY'
import collections, difflib, re, sys
a = open(sys.argv[1], encoding='utf-8').read().split('\n'); b = open(sys.argv[2], encoding='utf-8').read().split('\n')
ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != 'equal']
ok1 = collections.Counter(a) == collections.Counter(b)
ok2 = len(ops) == 2 and {ops[0][0], ops[1][0]} == {'delete', 'insert'}
d = next(o for o in ops if o[0] == 'delete'); i = next(o for o in ops if o[0] == 'insert')
block = a[d[1]:d[2]]; between = a[d[2]:i[1]] if d[1] < i[1] else a[i[1]:d[1]]
ok3 = collections.Counter(block) == collections.Counter(b[i[3]:i[4]]) and any(l.startswith('// OMNI_YTPROF_V1') for l in block) and any(l.startswith('// OMNI_JANK_PAGE_V1') for l in block)
names = set(re.findall(r'\b(omni_(?:ytprof|jank)_\w+|OmniYtprofScope|OMNI_YTPROF_SCOPE|OMNI_YP_\w+)\b', '\n'.join(block)))
used = sorted(n for n in names if any(n in l for l in between)); ok4 = not used
print(f'same line multiset {ok1}; one block moved {ok2} ({d[2]-d[1]} lines, A lines {d[1]+1}-{d[2]}); block is the ytprof/jank declaration preamble {ok3}; '
      f'names of the block used between the two positions: {used or "none"}')
print('RESOLUTION', 'ACCEPTED: order A built' if all((ok1, ok2, ok3, ok4)) else 'REJECTED')
sys.exit(0 if all((ok1, ok2, ok3, ok4)) else 1)
PY
  [ $? = 0 ] && { st "order proof: 1 file differs only by the placement of the self-contained diagnostic declaration block; $(tail -1 "$N/merge/diag-resolution.txt") ($(head -1 "$N/merge/diag-resolution.txt" | cut -c1-220))"; NDIFF=0; }
fi
[ "$NDIFF" = 0 ] || { st "the child tree is NOT order-independent: stopping (merge/order-compare.txt)"; exit 1; }
WK=$TA/webkit/Source; DA=$WK/WebKit/WebProcess/WebPage/CoordinatedGraphics
cp $DA/DrawingAreaCoordinatedGraphics.cpp $DA/DrawingAreaCoordinatedGraphics.h $TA/engine/media/OmniVideoDecoder.cpp $WK/WebCore/platform/network/curl/CurlRequest.cpp "$N/wsl/"
[ "$VARIANT" != fallback ] && cp $WK/WebCore/platform/network/curl/CurlContext.cpp $WK/JavaScriptCore/heap/Heap.cpp "$N/wsl/"
st "units: $(for f in "$MA"/apply_*.log; do printf "%s: %s; " "$(basename "$f" .log)" "$(tail -1 "$f" | cut -c1-70)"; done)"
# ---------------------------------------------------------------- 4. gates on the shipped text
H=$(mktemp -d /tmp/launchc-g-XXXXXX)
if [ "$VARIANT" != fallback ]; then
  grep -q 'S34G SWITCH CHECK PASS' "$MA/apply_switch_s34g.log" || { st "s34g-off.flag projection check FAILED: $(grep FAIL "$MA/apply_switch_s34g.log" | head -3 | tr '\n' ' ')"; exit 1; }
  st "S34G switch: $(grep -c '^PASS' "$MA/apply_switch_s34g.log") checks: s34g-off.flag present -> every s3.4g site's stock s3 condition, heap cap -> stock target"
  # the tree's JSC text = s3.4g's own appliers + the switch on clean s3 copies (diag: Heap.cpp also carries ytprof hooks)
  X="$H/x"; mkdir -p "$X/webkit/Source/JavaScriptCore/heap" "$X/webkit/Source/JavaScriptCore/runtime"
  for f in JavaScriptCore/heap/Collector.cpp JavaScriptCore/heap/Heap.cpp JavaScriptCore/heap/FastMallocAlignedMemoryAllocator.cpp JavaScriptCore/runtime/InitializeThreading.cpp; do cp "/home/builder/s3/webkit/Source/$f" "$X/webkit/Source/$f"; done
  python3 "$N/tools/apply_nomini.py" "$X" > /dev/null 2>&1 && python3 "$N/tools/apply_heapcap.py" "$X" > /dev/null 2>&1 && python3 "$N/tools/apply_mallocmini.py" "$X" > /dev/null 2>&1 \
    && python3 "$L/tools/apply_launch_switches.py" "$X" --s34g > /dev/null 2>&1 || { st "s3.4g + switch re-apply on s3 copies FAILED"; exit 1; }
  S4=0; : > "$N/wsl/s34g-identity.txt"; for f in JavaScriptCore/heap/Collector.cpp JavaScriptCore/heap/FastMallocAlignedMemoryAllocator.cpp JavaScriptCore/runtime/InitializeThreading.cpp JavaScriptCore/heap/Heap.cpp; do
    if cmp -s "$X/webkit/Source/$f" "$WK/$f"; then echo "identical: $f" >> "$N/wsl/s34g-identity.txt"; else echo "differs: $f" >> "$N/wsl/s34g-identity.txt"; S4=$((S4+1)); fi; done
  st "s3.4g + switch: JSC files vs a clean apply on s3 copies: $S4 differ ($( [ "$VARIANT" = diag ] && echo '<=1 expected: Heap.cpp also has ytprof hooks' || echo '0 expected'))"
  { [ "$VARIANT" = diag ] && [ "$S4" -le 1 ]; } || [ "$S4" = 0 ] || { st "s3.4g text in the tree is not s3.4g's: stopping"; exit 1; }
  # s3.4g's own host unit test, run from this folder's tool copies (writes only $N/S34G-HOSTTEST.txt)
  sed -e "s#N=\"\$O/omni-ytprof\"#N=\"$N\"#" "$O/build-omni-s34g-hosttest.sh" > "$H/s34g.sh"
  grep -q "omni-launch-$VARIANT-bind" "$H/s34g.sh" || { st "could not point the s3.4g host test at this folder: stopping"; exit 1; }
  bash "$H/s34g.sh" > "$N/wsl/s34g-run.log" 2>&1; S4R=$?
  st "S34G host test: exit $S4R; $(grep -cE '^PASS' "$N/S34G-HOSTTEST.txt") PASS / $(grep -cE '^FAIL' "$N/S34G-HOSTTEST.txt") FAIL"
  [ "$S4R" = 0 ] && ! grep -qE '^FAIL' "$N/S34G-HOSTTEST.txt" || { st "S34G host test FAILED"; exit 1; }
  grep -q 'OMNI_NET5_SWITCH_V1' $WK/WebCore/platform/network/curl/CurlContext.cpp && grep -q 'net5-off.flag' $WK/WebCore/platform/network/curl/CurlContext.cpp || { st "net5-off.flag switch missing: stopping"; exit 1; }
  NSM=rc3; [ "$VARIANT" = clean ] && NSM=rc2
  HB4=; [ "$RC4" = 1 ] && HB4=$WK/WebCore/platform/network/curl/CurlRequest.cpp
  python3 "$L/tools/net_switch_test.py" $WK/WebCore/platform/network/curl/CurlContext.cpp "$H/netsw" $NSM $HB4 > "$N/wsl/net5-switch.txt" 2>&1 || { st "net switch gate FAILED: $(grep FAIL "$N/wsl/net5-switch.txt" | tr '\n' ' ' | cut -c1-400)"; exit 1; }
  st "NET switches (shipped omni_net_off compiled, one process per flag set): $(grep -c ^PASS "$N/wsl/net5-switch.txt") PASS; $(tail -1 "$N/wsl/net5-switch.txt"); default off: $(grep "default (no flags)" "$N/wsl/net5-switch.txt" | sed "s/.*off = //")"
fi
grep -q 'OMNI_SWDEC_PAD_V1' $TA/engine/media/OmniVideoDecoder.cpp || { st "OMNI_SWDEC_PAD_V1 missing"; exit 1; }
JP="$MA/patches-jank"; AP="$MA/patches-ack"; MM="$MA/patches-mem"
if [ "$VARIANT" != diag ]; then diff <(grep -v omni_jank "$JP/paint-rects.inc") "$JP/paint-rects-fix-only.inc" > "$N/wsl/fix-only.diff" 2>&1 || { st "fix-only paint-rects is not the diagnostic minus its reporting calls"; exit 1; }
  grep -q omni_jank $DA/DrawingAreaCoordinatedGraphics.cpp && { st "a jank reporting call is in the non-diagnostic tree: stopping"; exit 1; }; fi
clang++ -std=c++17 -O1 -Wall -Wextra -Werror -I"$JP" "$N/paint_rects_test.cpp" -o "$H/prt" > "$N/wsl/paint-rects-build.log" 2>&1 && "$H/prt" > "$N/wsl/paint-rects-tight.log" 2>&1 \
  && OMNI_PAINT_RECTS=0 "$H/prt" > "$N/wsl/paint-rects-upstream.log" 2>&1 || { st "paint-rects V1 gate FAILED"; exit 1; }
clang++ -std=c++17 -O1 -Wall -Wextra -Werror -I"$AP" "$N/ack_pace_test.cpp" -o "$H/apt" > "$N/wsl/ack-pace-build.log" 2>&1 || { st "ack pace gate build FAILED: $(head -5 "$N/wsl/ack-pace-build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
"$H/apt" > "$N/wsl/ack-pace-default.log" 2>&1 && OMNI_ACK_PACE=0 "$H/apt" > "$N/wsl/ack-pace-killswitch.log" 2>&1 && OMNI_ACK_CREDITS=3 OMNI_ACK_HZ=30 "$H/apt" > "$N/wsl/ack-pace-c3hz30.log" 2>&1 \
  && OMNI_ACK_CREDITS=99 OMNI_ACK_HZ=5 "$H/apt" > "$N/wsl/ack-pace-absurd.log" 2>&1 || { st "ack pace gate FAILED"; exit 1; }
clang++ -std=c++17 -O1 -Wall -Wextra -Werror -I"$AP" -DOMNI_ACK_PACE_OFF_FLAG="\"$H/ack-pace-off.flag\"" "$L/tools/ack_switch_test.cpp" -o "$H/asw" > "$N/wsl/ack-switch-build.log" 2>&1 || { st "ack switch gate build FAILED: $(head -5 "$N/wsl/ack-switch-build.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
{ env -u OMNI_ACK_PACE "$H/asw" on && OMNI_RASTER_ACK_PACE=0 "$H/asw" off && OMNI_ACK_PACE=0 "$H/asw" off && OMNI_RASTER_ACK_CREDITS=3 OMNI_RASTER_ACK_HZ=30 "$H/asw" c3hz30 \
  && : > "$H/ack-pace-off.flag" && "$H/asw" off && rm -f "$H/ack-pace-off.flag"; } > "$N/wsl/ack-switch.log" 2>&1 || { st "ack switch gate FAILED: $(grep FAIL "$N/wsl/ack-switch.log" | tr '\n' ' ')"; exit 1; }
: > "$H/jank.flag"
clang++ -std=c++17 -O1 -Wall -Wextra -Werror -I"$AP" -DOMNI_ACK_FLAG_PATH="\"$H/jank.flag\"" "$N/ack_sink_test.cpp" -o "$H/ast" > "$N/wsl/ack-sink-build.log" 2>&1 && "$H/ast" > "$N/wsl/ack-sink.log" 2>&1 || { st "ack sink gate FAILED"; exit 1; }
python3 "$A/analyze_ack.py" --selftest > "$N/wsl/analyze-ack-selftest.log" 2>&1 || { st "analyze_ack selftest FAILED"; exit 1; }
# mem-paint gates on the shipped text (the extracted JSC functions see s3.4g's text with the switch's flag absent)
python3 - "$MM/mempressure.inc" $WK/WTF/wtf/generic/MemoryFootprintGeneric.cpp "$MM/paint-rects-v2.inc" $DA/DrawingAreaCoordinatedGraphics.cpp <<'PY' || { st "the tree does not carry the shipped mempressure/paint text verbatim"; exit 1; }
import sys
for inc, src in ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4])):
    if open(inc).read() not in open(src).read().replace('\r\n', '\n'): sys.exit('not verbatim: ' + inc)
PY
python3 "$MP/tools/extract_for_tests.py" $TA "$H/gen" > "$N/wsl/extract.log" 2>&1 || { st "extracting the shipped text FAILED: $(tail -2 "$N/wsl/extract.log" | tr '\n' ' ')"; exit 1; }
cp -r "$H/gen" "$N/wsl/extracted"
$CXX -DOMNI_MEM_HOSTTEST -DOMNI_MEM_OFF_FLAG="\"$H/off.flag\"" -I"$MM" "$MPH/mempressure_test.cpp" -o "$H/mpt2" > "$N/wsl/mempressure2-build.log" 2>&1 && "$H/mpt2" > "$N/wsl/mempressure2-test.log" 2>/dev/null || { st "mempressure gate (shipped) FAILED"; exit 1; }
# fallback: no s3.4g, so the extracted stock proportionalHeapSize() asks VM::isInMiniMode(); on the console (JIT off) that is
# true, so the shim answers true (stock behaviour on this console)
printf 'struct VM { static bool isInMiniMode() { return true; } };\n' > "$H/vm-shim.h"; SHIM=; [ "$VARIANT" = fallback ] && SHIM="-include $H/vm-shim.h"
$CXX -DOMNI_MEM_HOSTTEST -DOMNI_MEM_OFF_FLAG="\"$H/off.flag\"" '-DomniS34gOff()=false' -DOMNI_STOCK_MINI=false $SHIM -I"$MM" -I"$H/gen" "$MPH/mph_policy_test.cpp" -o "$H/mph" > "$N/wsl/mph-build.log" 2>&1 || { st "policy gate build FAILED: $(grep -m6 error "$N/wsl/mph-build.log" | tr '\n' ' ' | cut -c1-900)"; exit 1; }
"$H/mph" > "$N/wsl/mph-test.log" 2> "$N/wsl/mph-test.stderr" || { st "policy gate FAILED: $(grep FAIL "$N/wsl/mph-test.log" | head -5 | tr '\n' ' ')"; exit 1; }
: > "$H/off.flag"; "$H/mph" killswitch > "$N/wsl/mph-killswitch.log" 2>&1 || { st "policy kill-switch gate FAILED"; exit 1; }; rm -f "$H/off.flag"
# diag ships the diagnostic decision function; the V2 gate compares against the fix-only text, which is that function
# minus its omni_jank reporting calls (the identity the clean build asserts), so derive it for the gate
PJ="$JP"; if [ ! -f "$JP/paint-rects-fix-only.inc" ]; then PJ="$H/pj"; mkdir -p "$PJ"; grep -v omni_jank "$JP/paint-rects.inc" > "$PJ/paint-rects-fix-only.inc"; fi
$CXX -DOMNI_PR_TEST_CLOCK -DOMNI_PR_OFF_FLAG="\"$H/prflag\"" -I"$MM" -I"$PJ" "$MPH/paint_v2_test.cpp" -o "$H/pv2" > "$N/wsl/paint-v2-build.log" 2>&1 || { st "paint V2 gate build FAILED"; exit 1; }
"$H/pv2" > "$N/wsl/paint-v2-tight.log" 2>&1 && OMNI_PAINT_RECTS=0 "$H/pv2" > "$N/wsl/paint-v2-envoff.log" 2>&1 && OMNI_RASTER_PAINT_RECTS=0 "$H/pv2" > "$N/wsl/paint-v2-rasterenv.log" 2>&1 \
  && : > "$H/prflag" && "$H/pv2" > "$N/wsl/paint-v2-flag.log" 2>&1 || { st "paint V2 gate FAILED"; exit 1; }
rm -rf "$H"
st "gates: paint-rects V1 $(tail -1 "$N/wsl/paint-rects-tight.log" | cut -c1-40); ack pace $(tail -1 "$N/wsl/ack-pace-default.log" | cut -c1-60), off $(tail -1 "$N/wsl/ack-pace-killswitch.log" | cut -c1-50); ACK SWITCH $(grep -c '^PASS' "$N/wsl/ack-switch.log")/5 (default on; OMNI_RASTER_ACK_PACE=0, OMNI_ACK_PACE=0, ack-pace-off.flag -> off; OMNI_RASTER_ACK_CREDITS/HZ read); ack sink $(tail -1 "$N/wsl/ack-sink.log" | cut -c1-40)"
st "mem-paint gates: $(tail -1 "$N/wsl/mempressure2-test.log" | cut -c1-60); $(tail -1 "$N/wsl/mph-test.log" | cut -c1-60); $(tail -1 "$N/wsl/mph-killswitch.log" | cut -c1-50); paint V2 $(tail -1 "$N/wsl/paint-v2-tight.log" | cut -c1-50) / env $(tail -1 "$N/wsl/paint-v2-envoff.log" | cut -c1-30) / raster-env $(tail -1 "$N/wsl/paint-v2-rasterenv.log" | cut -c1-30) / flag $(tail -1 "$N/wsl/paint-v2-flag.log" | cut -c1-30)"
# ---------------------------------------------------------------- 5. the candidate child (ext4 link, copy, compare)
nice -n 5 ninja -k 0 -C $TA/build -j6 OmniEngine > "$N/ninja.log" 2>&1 || { st "ninja FAILED: $(grep -m14 -E 'error:|FAILED' "$N/ninja.log" | tr '\n' ' ' | cut -c1-3500)"; exit 1; }
st "ninja ok: $(grep -c '^\[' "$N/ninja.log") steps, $(grep -c 'warning:' "$N/ninja.log") warnings; in Omni code: $(grep 'warning:' "$N/ninja.log" | grep -iE 'omni|jank|ack|hdrbuf' | sed 's#.*/##' | cut -c1-90 | sort | uniq -c | tr '\n' ';' | cut -c1-400)"
python3 "$N/make_link_command.py" > "$N/link-command.log" 2>&1 || { st "link command FAILED"; exit 1; }
if [ "$VARIANT" = fallback ]; then SECL=/home/builder/omni-seclibs/stage/user/homebrew/lib; EXTRA=; st "link: stock seclibs (HTTP/1.1-only libcurl, no nghttp2/brotli)"
else
  SECL=/home/builder/launchc-$VARIANT-seclibs; rm -rf "$SECL"; mkdir -p "$SECL" && cp -dR --preserve=mode,timestamps /home/builder/omni-seclibs/stage/user/homebrew/lib/*.a "$SECL"/ \
    && rm -f "$SECL/libcurl.a" && cp /home/builder/yt-libs/seclibs/libcurl.a "$SECL/libcurl.a" || { st "h2 seclibs FAILED"; exit 1; }
  P=/home/builder/yt-libs/stage/user/homebrew/lib; EXTRA="$P/libnghttp2.a:$P/libbrotlidec.a:$P/libbrotlicommon.a"
  st "link: h2-capable libcurl $(sha256sum "$SECL/libcurl.a" | cut -c1-16) (net6-h2b's stock h2 curl, no fix A) + nghttp2 + brotli; HTTP/2 off unless net-on-h2.flag"
fi
OMNI_SECLIBS="$SECL" OMNI_NET_EXTRA_LIBS="$EXTRA" OMNI_NET_LABEL="omni-launch-$VARIANT" OMNI_CHILD_OUT="$LOUT/child" python3 "$N/child_build.py" > "$N/child-build.log" 2>&1 || { st "child FAILED: $(tail -3 "$N/child-build.log" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
/opt/ps5-payload-sdk/bin/llvm-strip "$LOUT/child/omni-engine-child-unstripped.elf" -o "$LOUT/restrip.elf" 2>/dev/null; RS=$(cmp -s "$LOUT/restrip.elf" "$LOUT/child/omni-engine-child.elf" && echo yes || echo NO)
rm -rf "$N/child"; mkdir -p "$N/child"; cpv "$LOUT/child/omni-engine-child.elf" "$LOUT/child/omni-engine-child-unstripped.elf" "$LOUT/child/receipt.json" "$N/child/" || { st "copying the child FAILED"; exit 1; }
for i in 1 2 3; do cmp -s "$LOUT/child/omni-engine-child.elf" "$N/child/omni-engine-child.elf" && cmp -s "$LOUT/child/omni-engine-child-unstripped.elf" "$N/child/omni-engine-child-unstripped.elf" && break
  echo "copy compare $i failed; copying again" >> "$N/wsl/copy-errors.log"; cpv "$LOUT/child/omni-engine-child.elf" "$LOUT/child/omni-engine-child-unstripped.elf" "$N/child/"; done
cmp -s "$LOUT/child/omni-engine-child.elf" "$N/child/omni-engine-child.elf" && cmp -s "$LOUT/child/omni-engine-child-unstripped.elf" "$N/child/omni-engine-child-unstripped.elf" || { st "the copy in outputs differs from the ext4 link: stopping"; exit 1; }
st "linked on ext4, copied, compared: identical; re-strip of the unstripped link == shipped child: $RS"
[ "$RS" = yes ] || { st "re-strip mismatch: stopping"; exit 1; }
C="$N/child/omni-engine-child.elf"; CU="$N/child/omni-engine-child-unstripped.elf"; BASE="$N/child-base/omni-engine-child.elf"
python3 "$L/tools/elfguard.py" "$C" "$BASE" > "$N/wsl/elfguard.log" 2>&1; EG=$?
st "packaging guard (LOAD overlap, LOAD flags, exec sections vs 7b810ea5): $(tail -1 "$N/wsl/elfguard.log")"
[ "$EG" = 0 ] || { st "packaging guard FAILED: $(grep FAIL "$N/wsl/elfguard.log" | tr '\n' ' ' | cut -c1-400)"; exit 1; }
: > "$N/checks.txt"
while IFS= read -r k; do [ -n "$k" ] && printf "child  %-34s %s (base %s)\n" "$k" "$(grep -c -a -- "$k" "$C")" "$(grep -c -a -- "$k" "$BASE")" >> "$N/checks.txt"; done < "$L/tools/keys-child.txt"
/usr/lib/llvm-21/bin/llvm-nm "$CU" 2>/dev/null | grep -E " [tTwW] (__wrap_connect|omni_net_[a-z_]+|nghttp2_session_new|BrotliDecoderDecompressStream|omni_jank_[a-z]+|omni_ytprof_[a-z]+|omni_mem_[a-z_]+|_ZN9OmniMedia12VideoDecoder4next[A-Za-z0-9_]*)$" >> "$N/checks.txt"
echo "base child = 7b810ea5: $BH" >> "$N/checks.txt"; sha256sum "$C" "$CU" "$BASE" >> "$N/checks.txt"
# union: each component enters as (its build - the build it was made from); MEM = omni-mem-paint's child minus the launch
# clean child it was built on (rc0, kept in omni-launch/child-rc0-7df41962). The switch layer is listed separately.
NT="$NET"; R0="$L/child-rc0-7df41962/omni-engine-child.elf"; MPC="$MP/child/omni-engine-child.elf"
u(){ echo "$1=${1%omni-engine-child.elf}omni-engine-child-unstripped.elf"; }
case "$VARIANT" in
  fallback) ARGS=(--plus "$NT/net6-h2b/omni-engine-child.elf" --minus "$NT/net4-diag/omni-engine-child.elf" --plus "$M/child-swpad/omni-engine-child.elf" --minus "$BASE"
                  --plus "$O/omni-ack-child-clean/child/omni-engine-child.elf" --minus "$BASE" --plus "$MPC" --minus "$R0");;
  *) ARGS=(--plus "$NT/net5-cand/omni-engine-child.elf" --minus "$NT/net4-base/omni-engine-child.elf" --plus "$NT/net4-cand-h2/omni-engine-child.elf" --minus "$NT/net4-cand/omni-engine-child.elf"
           --plus "$NT/net6-h2b/omni-engine-child.elf" --minus "$NT/net4-diag/omni-engine-child.elf" --plus "$M/child-swpad/omni-engine-child.elf" --minus "$BASE"
           --plus "$O/omni-ack-child-clean/child/omni-engine-child.elf" --minus "$BASE" --plus "$MPC" --minus "$R0")
     [ "$VARIANT" = diag ] && ARGS+=(--plus "$O/omni-ack-child/child/omni-engine-child.elf" --minus "$O/omni-ack-child-clean/child/omni-engine-child.elf" --plus "$NT/net4-diag/omni-engine-child.elf" --minus "$NT/net4-cand-h2/omni-engine-child.elf");;
esac
NMS=(); for x in "$C" "$BASE" "$R0" "$MPC" "$NT"/{net5-cand,net4-base,net4-cand-h2,net4-cand,net6-h2b,net4-diag}/omni-engine-child.elf "$M/child-swpad/omni-engine-child.elf" "$O/omni-ack-child-clean/child/omni-engine-child.elf" "$O/omni-ack-child/child/omni-engine-child.elf"; do NMS+=(--nm "$(u "$x")"); done
mkdir -p "$N/union"; python3 "$L/tools/additivity.py" --label "child-$VARIANT" --keys "$L/tools/keys-child.txt" --out "$N/union" --target "$C" --base "$BASE" "${ARGS[@]}" "${NMS[@]}" \
  --allow 'omniS34gOff|OMNI_STOCK_MINI|omniAckEnv|ack-pace-off|net5-off|s34g-off|OMNI_RASTER_%s|omni_net_announce|omni_net_note|kill switch|requested %d|preconnect: first|OMNI NET cache model|jscache: off by default|net-on-jscache|hdrbuf: off by default|net-on-hdrbuf' --strings-only > "$N/union/additivity.log" 2>&1; UR=$?
st "UNION ($VARIANT): $(grep '^RESULT' "$N/union/additivity.log") (exit $UR); switch-layer lines: $(grep -c '^SWITCH' "$N/union/additivity-child-$VARIANT.txt")"
st "candidate child ok: $(sha256sum "$C" | cut -c1-64) ($(stat -c %s "$C") bytes)"
IN
sed -i 's/\r$//' /tmp/launchc-$VARIANT-inner-$$.sh; chmod 755 /tmp/launchc-$VARIANT-inner-$$.sh
cat > /tmp/launchc-$VARIANT-outer-$$.sh <<'OUT'
#!/bin/bash
cd /
L=/tmp/omni-launch-child-$VARIANT.lock; ( umask 0; : >> "$L" ) 2>/dev/null; exec 9<"$L"; flock -n 9 || { echo "another omni-launch $VARIANT child build is running"; exit 0; }
st(){ echo "$(date -u +%FT%TZ) [$VARIANT] $*" | tee -a "$N/build-steps.txt"; }
U=${V_REAL_UID:-$(id -u)}
UPA=/home/builder/launchc-$VARIANT-up-$U; WKA=/home/builder/launchc-$VARIANT-work-$U; UPB=/home/builder/launchcb-$VARIANT-up-$U; WKB=/home/builder/launchcb-$VARIANT-work-$U; MB=/home/builder/launchcb-$VARIANT-mnt
[ -e /home/builder/s3/.s3-marker ] || { st "/home/builder/s3 missing: stopping"; exit 1; }
rm -rf "$UPA" "$WKA" "$UPB" "$WKB" /home/builder/launchc-$VARIANT-out; mkdir -p "$UPA" "$WKA" "$UPB" "$WKB" "$MB" /home/builder/launchc-$VARIANT-out
[ -n "$V_AS_BUILDER" ] && chown builder:builder "$UPA" "$WKA" "$UPB" "$WKB" "$MB" /home/builder/launchc-$VARIANT-out
st "disk: $(df -h /home/builder | tail -1 | awk '{print $4" free"}')"
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UPA,workdir=$WKA" /home/builder/s1 2>/tmp/launchc-$VARIANT-ovl.err || { st "overlay A failed ($(cat /tmp/launchc-$VARIANT-ovl.err)): stopping"; exit 1; }
mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UPB,workdir=$WKB" "$MB" 2>/tmp/launchcb-$VARIANT-ovl.err || { st "overlay B failed ($(cat /tmp/launchcb-$VARIANT-ovl.err)): stopping"; exit 1; }
touch /home/builder/s1/.launchc-marker "$MB/.launchcb-marker" || { st "trees not writable"; exit 1; }
BIND="/path/to/workspace/outputs/omni-launch-$VARIANT-bind"; mkdir -p "$BIND"
mount --bind "$N" "$BIND" || { st "bind mount failed: stopping"; exit 1; }
st "overlays mounted: A on /home/builder/s1 ($UPA), B on $MB ($UPB); $N bound at outputs/omni-launch-$VARIANT-bind"
export V_UPA="$UPA" V_UPB="$UPB" V_NREAL="$N" VARIANT
if [ -n "$V_AS_BUILDER" ]; then exec runuser -u builder -- bash "$V_INNER"; fi
bash "$V_INNER"
OUT
sed -i 's/\r$//' /tmp/launchc-$VARIANT-outer-$$.sh; chmod 755 /tmp/launchc-$VARIANT-outer-$$.sh
mkdir -p "$N"
cd /
export VARIANT N
if [ "$(id -u)" = 0 ]; then
  V_REAL_UID=0 V_AS_BUILDER=1 V_INNER=/tmp/launchc-$VARIANT-inner-$$.sh setsid nohup unshare -m --propagation private bash /tmp/launchc-$VARIANT-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
else
  V_REAL_UID=$(id -u) V_INNER=/tmp/launchc-$VARIANT-inner-$$.sh setsid nohup unshare -Urm --propagation private bash /tmp/launchc-$VARIANT-outer-$$.sh > "$N/native-build.log" 2>&1 < /dev/null &
fi
echo "omni-launch $VARIANT child build started pid $!"
