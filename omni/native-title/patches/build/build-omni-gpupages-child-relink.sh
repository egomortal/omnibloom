#!/bin/bash
# OMNI_GPUPAGES_CHILD_RELINK_V1 (2026-11-15): rebuild the ls1b/rc6 CHILD from the kept tree A (state C, exactly as child
# #4 43593684 was built at 2026-11-14T13:28Z), with the current stage-1 sources, WITHOUT the rc6 recipe workspace.
# Why: outputs/omni-launch/child-rc6 (the recipe workspace build-omni-gpupages-launch-s1b-rc6.sh copies into
# /home/builder/ogp-ls1b-cws4) was deleted in the 2026-11-14 disk clean-up, and that build's first step then removed
# the WSL copy. Tree A (/home/builder/ogp-ls1b-up-0 over /home/builder/s3) still holds state C, so only the changed
# stage-1 files need copying in, then ninja + the same link as the full script.
#   - link driver: child_build.py / make_link_command.py / child-src from /home/builder/ogp-ls1b-cws (the rc3-era copy;
#     the transcripts show no later edits to child_build.py);
#   - instead of the rc6-baseline gates (their inputs were deleted), a SYMBOL GATE against child #4: every function
#     must keep its size except those in the files this run changed (AcceleratedSurfacePlayStation's TU).
# Run as root (mounts): wsl -u root -e bash build-omni-gpupages-child-relink.sh
set -u
O='/path/to/workspace/outputs'; P="$O/omni-gpupages-ls1b"
S1="$O/omni-gpu-pages/stage1"; L="$O/omni-launch"
W=/home/builder/ogp; MB="$W/build-ps5-zink"; CP2="$W/cp2"; SRCM="$W/mesa-1ba9874f478657ccf6da72ce55f0260164cc0bd0-ogp"; PSDK=/opt/ps5-payload-sdk
UPV='/path/to/workspace/nxe-ps5/bigapp/private/av2/upstream/PS5_Vulkan'
T=/home/builder/s1; B=$T/build; LK=/home/builder/ogp-ls1b-link4; LL=/usr/lib/llvm-21/bin
UP=/home/builder/ogp-ls1b-up-0; WK=/home/builder/ogp-ls1b-work-0; NC=/home/builder/ogp-ls1b-cws-relink
BASE="$P/out-rc6-43593684/child/omni-engine-child-unstripped.elf"
L4="$P/logs-relink"; mkdir -p "$L4"
st(){ echo "$(date -u +%FT%TZ) [relink] $*" | tee -a "$P/steps.txt"; }
LKF=/tmp/omni-gpupages-ls1b.lock; ( umask 0; : >> "$LKF" ) 2>/dev/null; exec 9<"$LKF"; flock -n 9 || { st "another ls1b build is running"; exit 1; }
[ -d "$UP/webkit" ] && [ -f "$BASE" ] || { st "tree A upper or child #4 baseline missing: stopping"; exit 1; }
CG=webkit/Source/WebKit/WebProcess/WebPage/CoordinatedGraphics
# 1. tree A, mounted as the full build mounts it
rm -rf "$WK"; mkdir -p "$WK"; chown builder:builder "$WK"
mountpoint -q "$T" || mount -t overlay overlay -o "lowerdir=/home/builder/s3,upperdir=$UP,workdir=$WK" "$T" || { st "overlay A failed"; exit 1; }
trap 'cd /; umount "$T" 2>/dev/null' EXIT
# 2. the stage-1 files this run changes (only the surface file differs from child #4's sources)
CHANGED=""
for f in ogp-s1-surface.inc ogp-s1-drawingarea.inc ogp-s1-policy.h ogp-s1-tcprobe.inc ogp-s1b-async.inc; do
  [ -f "$S1/src/$f" ] && [ -f "$T/$CG/$f" ] || continue
  cmp -s "$S1/src/$f" "$T/$CG/$f" || { cp "$S1/src/$f" "$T/$CG/$f" && chown builder:builder "$T/$CG/$f" && CHANGED="$CHANGED $f"; }
done
# OMNI_UBLOCK_MISSING_V1 (2026-11-15): the network filter loads pages when its rule files are missing (engine/entry/OmniUBlock.cpp)
if ! grep -q OMNI_UBLOCK_MISSING_V1 "$T/engine/entry/OmniUBlock.cpp"; then
  python3 "$S1/tools/apply_ublock_missing.py" --ublock "$T/engine/entry/OmniUBlock.cpp" >> "$L4/apply_ublock_missing.log" 2>&1 && chown builder:builder "$T/engine/entry/OmniUBlock.cpp" && CHANGED="$CHANGED OmniUBlock.cpp" || { st "ublock missing patch FAILED: $(tail -1 "$L4/apply_ublock_missing.log")"; exit 1; }
fi
st "start: tree A state C (child #4's); changed stage-1 files:${CHANGED:- none}"
[ -n "$CHANGED" ] || [ "${FORCE:-0}" = 1 ] || { st "nothing changed: no build"; exit 0; }   # FORCE=1: rebuild anyway (e.g. ogp-s1-child.c changed, or A came back to state C with the file)
# 3. link-driver workspace from the rc3-era copy
rm -rf "$NC"; cp -a /home/builder/ogp-ls1b-cws "$NC" && chown -R builder:builder "$NC" || { st "link workspace copy FAILED"; exit 1; }
cat > /tmp/ogp-relink-inner.sh <<IN
set -u
O='$O'; P='$P'; S1='$S1'; L='$L'; MB='$MB'; CP2='$CP2'; SRCM='$SRCM'; PSDK='$PSDK'; UPV='$UPV'; B='$B'; LK='$LK'; LL='$LL'; NC='$NC'; L4='$L4'
st(){ echo "\$(date -u +%FT%TZ) [relink] \$*" | tee -a "\$P/steps.txt"; }
nice -n 19 ninja -k 0 -C "\$B" -j4 OmniEngine > "\$L4/ninja.log" 2>&1 || { st "ninja FAILED: \$(grep -m12 -E 'error:|FAILED' "\$L4/ninja.log" | tr '\n' ' ' | cut -c1-2500)"; exit 1; }
CC=\$(find "\$B" -maxdepth 3 -name cmakeconfig.h | head -1); grep -q "define ENABLE_ASYNC_SCROLLING 1" "\$CC" || { st "lost the async configuration: stopping"; exit 1; }
IPCC=\$(find "\$B" -path '*DerivedSources*' \( -name '*MessageReceiver.cpp' -o -name '*Messages.h' -o -name 'GeneratedSerializers.cpp' -o -name 'GeneratedSerializers.h' \) -type f -exec sha256sum {} + 2>/dev/null | sort -k2 | sha256sum | cut -c1-16)
[ "\$IPCC" = da4a75622a0a473f ] || { st "generated IPC code \$IPCC differs from the title's: stopping"; exit 1; }
st "ninja ok: \$(grep -c '^\[' "\$L4/ninja.log") steps, \$(grep -c 'warning:' "\$L4/ninja.log") warnings; IPC = the title's"
cd "\$NC" || exit 1
python3 "\$NC/make_link_command.py" > "\$L4/link-command-child.log" 2>&1 || { st "child link command FAILED"; exit 1; }
CF=(-std=c11 -O2 -Wall -Wextra -Wno-unused-parameter -fPIC "-I\$SRCM/include" "-I\$UPV/tooling/gpu-broker"); mkdir -p "\$LK/s1obj"
for x in ogp-s1-child ogp_dri_nodrm_stubs_weak ogp_payload_libc_weak; do "\$PSDK/bin/prospero-clang" "\${CF[@]}" -c "\$S1/src/\$x.c" -o "\$LK/s1obj/\$x.o" >> "\$L4/s1obj.log" 2>&1 || { st "compile \$x FAILED"; exit 1; }; done
OGP_S1_MAP="\$LK/child.map" python3 "\$S1/tools/s1_link_inputs.py" "\$LK/s1-link-inputs.json" "\$MB" "\$CP2" "\$LK/s1obj" > "\$L4/s1-link-inputs.log" 2>&1 || { st "link inputs FAILED"; exit 1; }
python3 "\$S1/tools/patch_child_build.py" "\$NC/child_build.py" > "\$L4/patch-child-build.log" 2>&1 || { st "child_build patch FAILED"; exit 1; }
SECL=/home/builder/ogp-ls1b-seclibs; rm -rf "\$SECL"; mkdir -p "\$SECL" && cp -dR --preserve=mode,timestamps /home/builder/omni-seclibs/stage/user/homebrew/lib/*.a "\$SECL"/ \
  && rm -f "\$SECL/libcurl.a" && cp /home/builder/yt-libs/seclibs/libcurl.a "\$SECL/libcurl.a" || { st "h2 seclibs FAILED"; exit 1; }
PL=/home/builder/yt-libs/stage/user/homebrew/lib; EXTRA="\$PL/libnghttp2.a:\$PL/libbrotlidec.a:\$PL/libbrotlicommon.a"
rm -rf "\$LK/child"
OMNI_SECLIBS="\$SECL" OMNI_NET_EXTRA_LIBS="\$EXTRA" OMNI_NET_LABEL="omni-launch-rc6-gpupages" OMNI_CHILD_OUT="\$LK/child" OGP_S1_LINK=1 OGP_S1_LINK_INPUTS="\$LK/s1-link-inputs.json" \
  python3 "\$NC/child_build.py" > "\$L4/child-build.log" 2>&1 || { st "child link FAILED: \$(grep -o 'undefined symbol: .*\|duplicate symbol: .*' "\$LK/child/link.log" 2>/dev/null | sort -u | head -8 | tr '\n' ' ' | cut -c1-1200)"; exit 1; }
\$LL/llvm-nm -u "\$LK/child/omni-engine-child-unstripped.elf" | awk '{print \$NF}' | sort -u > "\$LK/child-undef.txt"; comm -12 "\$LK/child-undef.txt" "\$CP2/archive-defs.txt" > "\$L4/child-weakref-left.txt"
[ -s "\$L4/child-weakref-left.txt" ] && { st "child WEAK-REF GATE FAILED"; exit 1; }
/opt/ps5-payload-sdk/bin/llvm-strip "\$LK/child/omni-engine-child-unstripped.elf" -o "\$LK/restrip.elf" 2>/dev/null; cmp -s "\$LK/restrip.elf" "\$LK/child/omni-engine-child.elf" || { st "re-strip mismatch"; exit 1; }
st "linked: \$(sha256sum "\$LK/child/omni-engine-child.elf" | cut -c1-64); weak-ref 0; re-strip = shipped"
IN
runuser -u builder -- bash /tmp/ogp-relink-inner.sh || exit 1
# 4. SYMBOL GATE vs child #4: only functions from the changed TU may change size
NEW="$LK/child/omni-engine-child-unstripped.elf"
python3 - "$BASE" "$NEW" "$L4/symbol-gate.txt" <<'PY' || { st "SYMBOL GATE FAILED: $(tail -3 "$L4/symbol-gate.txt" | tr '\n' ' ' | cut -c1-600)"; exit 1; }
import subprocess, sys, collections
def syms(path):
    out = subprocess.run(['/usr/lib/llvm-21/bin/llvm-nm', '-S', '--defined-only', path], capture_output=True, text=True).stdout
    d = collections.defaultdict(list)
    for l in out.splitlines():
        p = l.split(None, 3)
        if len(p) == 4: d[p[3]].append(p[1])
    return {k: v[0] for k, v in d.items() if len(v) == 1}
a, b = syms(sys.argv[1]), syms(sys.argv[2])
changed = sorted(k for k in a.keys() & b.keys() if a[k] != b[k])
gone, added = sorted(a.keys() - b.keys()), sorted(b.keys() - a.keys())
dem = lambda names: subprocess.run(['/usr/lib/llvm-21/bin/llvm-cxxfilt'], input='\n'.join(names), capture_output=True, text=True).stdout.splitlines() if names else []
ok_word = ('OmniGpuPagesS1Surface', 'AcceleratedSurface::', 's_asyncBroken', 'omniGl', 'PlatformDisplay::eglDisplay',
           'glFenceSync', 'glClientWaitSync', 'glDeleteSync', 'glFlush', 'glMapBufferRange', 'glUnmapBuffer',
           # OMNI_UBLOCK_MISSING_V1 (OmniUBlock.cpp): exactly the four functions the patch changes or adds
           '(anonymous namespace)::readAsset(char const*)', 'omniUBlockShouldBlock', '(anonymous namespace)::filesMissing()',
           '(anonymous namespace)::initialize((anonymous namespace)::Engine&)')
bad = [n for n in dem(changed) + dem(added) + dem(gone) if not any(w in n for w in ok_word)]
with open(sys.argv[3], 'w') as f:
    f.write('unique names %d; size-changed %d; added %d; gone %d\n' % (len(a.keys() & b.keys()), len(changed), len(added), len(gone)))
    for n in dem(changed): f.write('changed ' + n[:200] + '\n')
    for n in dem(added): f.write('added ' + n[:200] + '\n')
    for n in dem(gone): f.write('gone ' + n[:200] + '\n')
    f.write('OUTSIDE THE CHANGED FILE: %d\n' % len(bad))
    for n in bad[:20]: f.write('  ' + n[:200] + '\n')
sys.exit(1 if bad else 0)
PY
st "symbol gate vs child #4: $(head -1 "$L4/symbol-gate.txt"); outside the changed file: 0"
D="$P/out-rc6/child"; mkdir -p "$D"; cp "$LK/child/omni-engine-child.elf" "$NEW" "$LK/child/receipt.json" "$D/" || { st "copy FAILED"; exit 1; }
cmp -s "$LK/child/omni-engine-child.elf" "$D/omni-engine-child.elf" || { st "COPY MISMATCH"; exit 1; }
st "RELINK CHILD ok: $(sha256sum "$D/omni-engine-child.elf" | cut -c1-64) (tree A state C + stage-1:$CHANGED)"
