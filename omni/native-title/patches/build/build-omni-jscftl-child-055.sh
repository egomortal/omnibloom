#!/bin/bash
# 2026-11-26 vss3n: = vss3m + apply_audio_mp2.py (OMNI_AUDIO_MP2_V1: MPEG Layer II audio in HLS TS)
# 2026-11-25 vss3m: = vss3l + apply_audio_ac3_mp3.py (OMNI_AUDIO_AC3_MP3_V1: AC-3 / E-AC-3 / MP3 audio in MP4 and HLS TS)
# 2026-11-25 vss3l: = vss3k + apply_hls_h264_large.py (OMNI_HLS_H264_LARGE_V1: native HLS H.264 variants above 1080p on the hardware)
# 2026-11-25 vss3k: = vss3j without OMNI_MSE_PUMP_DIAG_V1 (release child for Bloom Preview 6). vss3j: = vss3i + OMNI_MSE_TRACK_QUOTA_V1. vss3i: = vss3h + probe fix + MSE fail log + pump diag. vss3h: = vss3 + apply_mse_h264_large.py (OMNI_MSE_H264_LARGE_V1: movy 2600x1080 H.264)
# 2026-11-21 vss3: = vss2 + apply_compositor_frame_guard.py (OMNI_COMPOSITOR_FRAME_GUARD_V1: late frame-done after invalidate)
# 2026-11-21 vss2: = vss + apply_stack_min.py (OMNI_STACK_MIN_2M_V1: 2 MiB thread stack minimum, was 8) + apply_trace_lazy.py
#   (OMNI_TRACE_LAZY_V1: 24 MiB trace buffer only when tracing) + memmap child V2 (map thread starts on the first frame)
# 2026-11-20 vss: = pasremap + the FIXED memory-extra.h (cost-free sceKernelReserveVirtualRange reservations, OMNI v62)
#   bind-mounted over /opt/omni-build/.../memory-extra.h INSIDE this build's private mount namespace only (the shared
#   /opt copy is the old mmap(PROT_NONE) one: every WebKit reservation charged the page-table pool). OMNI_VSS_BIND_V1
# 2026-11-20 pasremap: = mm + apply_pas_decommit_remap.py (OMNI_PAS_DECOMMIT_REMAP_V1: libpas decommit returns page tables)
# 2026-11-20 mm: = lvs + apply_memmap_child.py (OMNI_MEMMAP_CHILD_V1, memmap-child.flag only)
# 2026-11-20 lvs: = pagecap + apply_layers_video_sleep.py (OMNI_LAYERS_VIDEO_SLEEP_V1)
# 2026-11-20 pagecap: = crfix + apply_pt_4k_pagecap.py (OMNI_PT_4K_PAGECAP_V1)
# 2026-11-19: = build-omni-jscftl-child-ldo.sh + apply_compositor_suspend_fix.py (tab-close crash) + apply_hwclient_size_guard.py (video abort)
# OMNI_JSCFTL_CHILD_V1 (2026-11-17): the launch child (a5083735, omni-gpupages-ls1b/out-rc6-a5083735) rebuilt with
# JavaScriptCore's DFG and FTL tiers compiled in (-DENABLE_DFG_JIT=ON -DENABLE_FTL_JIT=ON), plus
#   P1 OMNI_JSC_DFGFTL_V1         tiers per flag file (jsc-dfg.flag / jsc-ftl.flag), polling traps, 1+1 compiler threads,
#                                 pool MB from jsc-jit-pool-mb.txt (default 64)         omni-jit-ftl/tools/apply_jscftl_tiers.py
#   P2 OMNI_JSC_UCONTEXT_V1       registersFromUContext() at +64 on this firmware      .../apply_jscftl_ucontext.py
#   P3 OMNI_JSC_COMPILER_STACK_V1 2 MB JIT compiler-thread stacks                      .../apply_jscftl_compiler_stack.py
#   P4 OMNI_JSC_JIT_STATS_V1      10 s "jit stats:" line (DFG flag or jsc-jit-stats.flag) .../apply_jscftl_jit_stats.py
# Without jsc-dfg.flag the child runs exactly rc6's tiers (baseline + regexp). Study: omni-jit-ftl/FEASIBILITY.md.
#
# Sources = a5083735's recipe (build-omni-gpupages-child-relink.sh, the 2026-11-15T20:24Z run):
#   state C (tree B upper /home/builder/ogp-ls1b-upB-0 over s3: the rc6 child units + stage 1 + async/MSE/probes),
#   + the stage-1 .inc files from omni-gpu-pages/stage1/src, + OMNI_UBLOCK_MISSING_V1 + OMNI_UBLOCK_REFINE_V1.
#   State C is SNAPSHOTTED (copied to /home/builder/jscftl-src) while briefly holding /tmp/omni-gpupages-ls1b.lock, after
#   proving tree A's sources equal tree B's (A is not mid title-build) and that B has no file newer than that relink.
# Isolation: everything runs in a PRIVATE mount namespace (unshare -m). There, /home/builder/s1 is an overlay
#   lowerdir=/home/builder/jscftl-src:/home/builder/s3, upperdir=/home/builder/jscftl-up-0, and /home/builder/s1/build is a
#   bind of /home/builder/jscftl-build (own CMake configure). Other sessions keep seeing the real s1. Never written:
#   s1, s3, ogp-*, launchc-*, other outputs. Own: jscftl-{src,up-0,work-0,build,cws,link,seclibs}, /tmp/omni-jscftl.lock.
# Gates: snapshot A==B, CMake cache = tree A's except ENABLE_DFG_JIT/ENABLE_FTL_JIT, cmakeconfig (DFG 1, FTL 1, async 1),
#   patch marker audit, changed-file set, generated IPC = the title's da4a75622a0a473f, weak-ref, re-strip, elfguard and
#   launch keys vs a5083735, DFG/FTL/B3 symbols present, new markers present.
# Output: omni-jit-ftl/out/child/omni-engine-child.elf (+ unstripped, receipt.json), omni-jit-ftl/steps.txt, logs/.
# Build only: never deploys, never touches the console. Full rebuild first time (~3-4 h at -j4); later runs reuse
# /home/builder/jscftl-build incrementally (FRESH=1 starts over).  Run:  wsl -u root -e bash <this script>
# DIAG=1 (OMNI_JSCFTL_DIAG_V1): the same child + P6 OMNI_YTPROF_V1/OMNI_YTPROF_WIN_V1 (omni-jit-ftl/tools/apply_jscftl_ytprof.py:
#   main-thread category timers, "OMNI YTPROF w/long/page/nav/t" stderr lines, all no-ops without /data/omni/ytprof.flag).
#   Output omni-jit-ftl/out-diag/child/ (+ out-diag/checks.txt), steps-diag.txt ([jscftl-diag]), logs-diag/, native-build-diag.log.
#   Shares jscftl-build with the default: the build dir carries a variant stamp (.omni-jscftl-variant); a default build after a
#   DIAG one deletes the objects that depend on the 16 ytprof files first, and the default child is gated to lack the ytprof strings.
O='/path/to/workspace/outputs'; X="$O/omni-jit-ftl"
[ "$(id -u)" = 0 ] || { echo "run as root: wsl -u root -e bash \"$0\""; exit 1; }
DIAG=${DIAG:-0}; [ "$DIAG" = 1 ] && SFX=-diag || { DIAG=0; SFX=; }
mkdir -p "$X/logs$SFX" && chown builder:builder "$X" "$X/logs$SFX" 2>/dev/null
IN_=/tmp/jscftl-inner-$$.sh; OUT_=/tmp/jscftl-outer-$$.sh
cat > "$IN_" <<'IN'
#!/bin/bash
# ---------------------------------------------------------------- inner: user builder, inside the private namespace
set -u
O='/path/to/workspace/outputs'; X="$O/omni-jit-ftl"; L="$X/logs"; TOOLS="$X/tools"
P="$O/omni-gpupages-ls1b"; S1="$O/omni-gpu-pages/stage1"; LA="$O/omni-launch"
H=/home/builder; T=$H/s1; B=$T/build; UP=$H/jscftl-up-0; NC=$H/jscftl-cws; LK=$H/jscftl-link; SECL=$H/jscftl-seclibs
W=$H/ogp; MB="$W/build-ps5-zink"; CP2="$W/cp2"; SRCM="$W/mesa-1ba9874f478657ccf6da72ce55f0260164cc0bd0-ogp"; PSDK=/opt/ps5-payload-sdk
UPV='/path/to/workspace/nxe-ps5/bigapp/private/av2/upstream/PS5_Vulkan'
LL=/usr/lib/llvm-21/bin; REFCACHE=$H/ogp-ls1b-up-0/build/CMakeCache.txt
BASE="$P/out-rc6-a5083735/child/omni-engine-child.elf"; BASEU="$P/out-rc6-a5083735/child/omni-engine-child-unstripped.elf"
# OMNI_JSCFTL_DIAG_V1: DIAG=1 adds P6 (ytprof) with its own logs/steps/output; the default keeps every path and gate
DIAG=${DIAG:-0}; [ "$DIAG" = 1 ] || DIAG=0
if [ "$DIAG" = 1 ]; then L="$X/logs-diag"; TAG=jscftl-diag; STEPS="$X/steps-diag.txt"; else TAG=jscftl; STEPS="$X/steps.txt"; fi
YTP_FILES="webkit/Source/WTF/wtf/MainThread.cpp webkit/Source/WTF/wtf/generic/RunLoopGeneric.cpp webkit/Source/JavaScriptCore/runtime/JSLock.cpp
  webkit/Source/JavaScriptCore/heap/Heap.cpp webkit/Source/JavaScriptCore/heap/IncrementalSweeper.cpp webkit/Source/JavaScriptCore/runtime/CodeCache.cpp
  webkit/Source/JavaScriptCore/bytecode/UnlinkedFunctionExecutable.cpp webkit/Source/WebCore/dom/Document.cpp webkit/Source/WebCore/page/LocalFrameViewLayoutContext.cpp
  webkit/Source/WebCore/page/LocalFrameView.cpp webkit/Source/WebCore/platform/image-decoders/ScalableImageDecoder.cpp webkit/Source/WebCore/page/Page.cpp
  webkit/Source/WebCore/html/parser/HTMLDocumentParser.cpp webkit/Source/WebCore/css/StyleSheetContents.cpp webkit/Source/WebCore/loader/FrameLoader.cpp
  webkit/Source/WebKit/WebProcess/WebPage/CoordinatedGraphics/DrawingAreaCoordinatedGraphics.cpp"
st(){ echo "$(date -u +%FT%TZ) [$TAG] $*" | tee -a "$STEPS"; }
fail(){ st "FAILED: $*"; exit 1; }
export SOURCE_DATE_EPOCH=1793793600
# 0. we must be in our own overlay (never the shared s1)
[ -e "$T/.jscftl-marker" ] && grep -q " $T overlay .*upperdir=$UP," /proc/self/mounts && grep -q " $T/build " /proc/self/mounts \
  || fail "the jscftl overlay is not mounted on $T in this namespace: refusing"
[ "$(sha256sum "$BASE" | cut -c1-64)" = a5083735d94744d3d0507b7ec89101cdab8f256d26eb05df99a99ed92d9e552e ] || fail "reference child a5083735 missing or changed"
# 1. a5083735's recipe on state C (build-omni-gpupages-child-relink.sh step 2)
CG=webkit/Source/WebKit/WebProcess/WebPage/CoordinatedGraphics; CHANGED=""
for f in ogp-s1-surface.inc ogp-s1-drawingarea.inc ogp-s1-policy.h ogp-s1-tcprobe.inc ogp-s1b-async.inc; do
  [ -f "$S1/src/$f" ] && [ -f "$T/$CG/$f" ] || continue
  cmp -s "$S1/src/$f" "$T/$CG/$f" || { cp "$S1/src/$f" "$T/$CG/$f" && CHANGED="$CHANGED $CG/$f"; } || fail "stage-1 copy $f"
done
UB=engine/entry/OmniUBlock.cpp
grep -q 'OMNI_UBLOCK_MISSING_V1\|OMNI_UBLOCK_REFINE_V1' "$T/$UB" || CHANGED="$CHANGED $UB"
grep -q OMNI_UBLOCK_MISSING_V1 "$T/$UB" || { python3 "$S1/tools/apply_ublock_missing.py" --ublock "$T/$UB" > "$L/apply_ublock_missing.log" 2>&1 || fail "ublock missing: $(tail -1 "$L/apply_ublock_missing.log")"; }
grep -q OMNI_UBLOCK_REFINE_V1 "$T/$UB" || { python3 "$S1/tools/apply_ublock_refine.py" --ublock "$T/$UB" > "$L/apply_ublock_refine.log" 2>&1 || fail "ublock refine: $(tail -1 "$L/apply_ublock_refine.log")"; }
grep -q OMNI_UBLOCK_MISSING_V1 "$T/$UB" && grep -q OMNI_UBLOCK_REFINE_V1 "$T/$UB" || fail "ublock markers missing after apply"
# layers default on (2026-11-18, OMNI_LAYERS_DEFAULT_ON_V1 tool): the child tree's async + surface .inc copies (not $S1/src);
# always listed as changed files (the gate below expects them in the upper)
python3 -I "$S1/tools/apply_layers_default_on.py" inc "$T/$CG" > "$L/apply_layers_default_on_inc.log" 2>&1 || fail "layers default on (inc): $(tail -1 "$L/apply_layers_default_on_inc.log")"
CHANGED="$CHANGED $CG/ogp-s1b-async.inc $CG/ogp-s1-surface.inc"
# latest frame (2026-11-18, apply_latest_frame.py): one waiting async-readback frame at most, its memory reused
python3 -I "$S1/tools/apply_latest_frame.py" "$T/$CG" > "$L/apply_latest_frame.log" 2>&1 || fail "latest frame: $(tail -1 "$L/apply_latest_frame.log")"
# OMNI_COMPOSITOR_SUSPEND_FIX_V1 (2026-11-19): tab-close crash (cross-thread stop of the armed compositor update timer)
python3 -I "$S1/tools/apply_compositor_suspend_fix.py" "$T/$CG" > "$L/apply_compositor_suspend_fix.log" 2>&1 || fail "compositor suspend fix: $(tail -1 "$L/apply_compositor_suspend_fix.log")"
CHANGED="$CHANGED $CG/CompositingRunLoop.cpp"
# OMNI_HWCLIENT_SIZE_GUARD_V1 (2026-11-19): video client drops a picture with a bogus size instead of aborting
python3 -I "$S1/tools/apply_hwclient_size_guard.py" "$T/engine" > "$L/apply_hwclient_size_guard.log" 2>&1 || fail "hwclient size guard: $(tail -1 "$L/apply_hwclient_size_guard.log")"
CHANGED="$CHANGED engine/media/OmniHwClient.cpp"
# OMNI_GPUPAGES_VIDEO_TRIM_V1 (2026-11-19): the layers readback ring is released while a 1440p+ hardware video plays
python3 -I "$S1/tools/apply_video_trim.py" "$T/$CG" "$T/engine" > "$L/apply_video_trim.log" 2>&1 || fail "video trim: $(tail -1 "$L/apply_video_trim.log")"
# OMNI_LAYERS_4K_CAP_V1 (2026-11-19): decodingInfo says no above 1440p while page layers are on (page-table pool)
python3 -I "$S1/tools/apply_layers_4k_cap.py" "$T/engine" > "$L/apply_layers_4k_cap.log" 2>&1 || fail "layers 4k cap: $(tail -1 "$L/apply_layers_4k_cap.log")"
CHANGED="$CHANGED engine/entry/OmniMSEPlayer.cpp engine/entry/OmniMSESource.h"
# OMNI_RUNLOOP_STOP_FIX_V1 (2026-11-19): RunLoop::TimerBase::stop from another thread = start()'s locked stop, no crash
python3 -I "$S1/tools/apply_runloop_stop_fix.py" "$T" > "$L/apply_runloop_stop_fix.log" 2>&1 || fail "runloop stop fix: $(tail -1 "$L/apply_runloop_stop_fix.log")"
CHANGED="$CHANGED webkit/Source/WTF/wtf/generic/RunLoopGeneric.cpp"
# OMNI_PT_4K_PAGECAP_V1 (2026-11-20): YouTube kept at 1440p while a 2160p decoder open would cross the page-table line
python3 -I "$S1/tools/apply_pt_4k_pagecap.py" "$T/engine" > "$L/apply_pt_4k_pagecap.log" 2>&1 || fail "pt 4k pagecap: $(tail -1 "$L/apply_pt_4k_pagecap.log")"
CHANGED="$CHANGED engine/entry/OmniBrowser.cpp"
# OMNI_LAYERS_VIDEO_SLEEP_V1 (2026-11-20): page layers off while a 1440p+ hardware video plays (~265 page tables at 4K)
python3 -I "$S1/tools/apply_layers_video_sleep.py" "$T/$CG" > "$L/apply_layers_video_sleep.log" 2>&1 || fail "layers video sleep: $(tail -1 "$L/apply_layers_video_sleep.log")"
CHANGED="$CHANGED $CG/DrawingAreaCoordinatedGraphics.cpp"
# OMNI_MEMMAP_CHILD_V1 (2026-11-20): engine-child memory map, test-only (memmap-child.flag)
python3 -I "$S1/tools/apply_memmap_child.py" "$T/engine" > "$L/apply_memmap_child.log" 2>&1 || fail "memmap child: $(tail -1 "$L/apply_memmap_child.log")"
# OMNI_PAS_DECOMMIT_REMAP_V1 (2026-11-20): libpas decommit re-reserves (page tables back), commit maps again
python3 -I "$S1/tools/apply_pas_decommit_remap.py" "$T" > "$L/apply_pas_decommit_remap.log" 2>&1 || fail "pas decommit remap: $(tail -1 "$L/apply_pas_decommit_remap.log")"
CHANGED="$CHANGED webkit/Source/bmalloc/libpas/src/libpas/pas_page_malloc.c"
# OMNI_TRACE_LAZY_V1 (2026-11-21): media trace buffer allocated only when tracing (12 page tables per process)
python3 -I "$S1/tools/apply_trace_lazy.py" "$T/engine" > "$L/apply_trace_lazy.log" 2>&1 || fail "trace lazy: $(tail -1 "$L/apply_trace_lazy.log")"
CHANGED="$CHANGED engine/media/OmniHwService.cpp"
# OMNI_COMPOSITOR_FRAME_GUARD_V1 (2026-11-21): frameComplete/displayUpdateFired return once the compositor is invalidated
python3 -I "$S1/tools/apply_compositor_frame_guard.py" "$T/$CG" > "$L/apply_compositor_frame_guard.log" 2>&1 || fail "compositor frame guard: $(tail -1 "$L/apply_compositor_frame_guard.log")"
# OMNI_MSE_H264_LARGE_V1 (2026-11-25): MSE H.264 above 1080p to 3840x2160 on the hardware (movy 2600x1080)
python3 -I "$S1/tools/apply_mse_h264_large.py" "$T" > "$L/apply_mse_h264_large.log" 2>&1 || fail "mse h264 large: $(tail -1 "$L/apply_mse_h264_large.log")"
st "OMNI_MSE_H264_LARGE_V1: $(tail -1 "$L/apply_mse_h264_large.log")"
# 2026-11-25 vss3i: OMNI_MSE_H264_PROBE_V1 (fragment probe opens large H.264) + OMNI_MSE_FAIL_LOG_V1 + OMNI_MSE_PUMP_DIAG_V1 (diagnostic)
python3 -I "$S1/tools/apply_mse_h264_probe.py" "$T" > "$L/apply_mse_h264_probe.log" 2>&1 || fail "mse h264 probe: $(tail -1 "$L/apply_mse_h264_probe.log")"
st "OMNI_MSE_H264_PROBE_V1: $(tail -1 "$L/apply_mse_h264_probe.log")"
python3 -I "$S1/tools/apply_mse_fail_log.py" "$T" > "$L/apply_mse_fail_log.log" 2>&1 || fail "mse fail log: $(tail -1 "$L/apply_mse_fail_log.log")"
st "OMNI_MSE_FAIL_LOG_V1: $(tail -1 "$L/apply_mse_fail_log.log")"
# 2026-11-25 vss3j: OMNI_MSE_TRACK_QUOTA_V1 (per-track sample limit: muxed audio no longer starves video; movy frozen picture)
python3 -I "$S1/tools/apply_mse_track_quota.py" "$T" > "$L/apply_mse_track_quota.log" 2>&1 || fail "mse track quota: $(tail -1 "$L/apply_mse_track_quota.log")"
st "OMNI_MSE_TRACK_QUOTA_V1: $(tail -1 "$L/apply_mse_track_quota.log")"
# 2026-11-25 vss3l: OMNI_HLS_H264_LARGE_V1 (native HLS picks H.264 variants to 3840x2160 when the hardware decodes)
python3 -I "$S1/tools/apply_hls_h264_large.py" "$T" > "$L/apply_hls_h264_large.log" 2>&1 || fail "hls h264 large: $(tail -1 "$L/apply_hls_h264_large.log")"
st "OMNI_HLS_H264_LARGE_V1: $(tail -1 "$L/apply_hls_h264_large.log")"
python3 -I "$S1/tools/apply_audio_ac3_mp3.py" "$T" > "$L/apply_audio_ac3_mp3.log" 2>&1 || fail "audio ac3 mp3: $(tail -1 "$L/apply_audio_ac3_mp3.log")"
st "OMNI_AUDIO_AC3_MP3_V1: $(tail -1 "$L/apply_audio_ac3_mp3.log")"
python3 -I "$S1/tools/apply_audio_mp2.py" "$T" > "$L/apply_audio_mp2.log" 2>&1 || fail "audio mp2: $(tail -1 "$L/apply_audio_mp2.log")"
st "OMNI_AUDIO_MP2_V1: $(tail -1 "$L/apply_audio_mp2.log")"
CHANGED="$CHANGED $CG/ThreadedCompositorPlayStation.cpp"
st "a5083735 recipe on state C: stage-1 files changed:${CHANGED:- none}; OMNI_UBLOCK_MISSING_V1 + OMNI_UBLOCK_REFINE_V1 present"
# 2. P1-P4 (backups outside the tree) + marker audit
export OMNI_PATCH_BACKUP_DIR="$L/backups"
for s in tiers default_on ucontext compiler_stack jit_stats; do   # default_on: OMNI_JSC_DFGFTL_DEFAULT_ON_V1
  python3 -I "$TOOLS/apply_jscftl_$s.py" "$T" > "$L/apply_$s.log" 2>&1 || fail "apply_jscftl_$s: $(tail -1 "$L/apply_$s.log")"
done
ALOGS=("$L"/apply_tiers.log "$L"/apply_default_on.log "$L"/apply_ucontext.log "$L"/apply_compiler_stack.log "$L"/apply_jit_stats.log); NAUD=10
if [ "$DIAG" = 1 ]; then   # P6 OMNI_YTPROF_V1 (+ OMNI_YTPROF_WIN_V1): 16 file reports
  python3 -I "$TOOLS/apply_jscftl_ytprof.py" "$T" > "$L/apply_ytprof.log" 2>&1 || fail "apply_jscftl_ytprof: $(tail -1 "$L/apply_ytprof.log")"
  ALOGS+=("$L/apply_ytprof.log"); NAUD=26
fi
AUD=0
while read -r state mark rel; do
  grep -q "$mark" "$T/$rel" && echo "ok $state $mark $rel" || { echo "MISSING $state $mark $rel"; AUD=1; }
done < <(grep -h -E '^(applied|already) OMNI_[A-Z0-9_]+ ' "${ALOGS[@]}") > "$L/marker-audit.txt"
# 9 file reports: P1 OmniMain; P2 PlatformRegisters.h; P3 Threading.cpp; P4 ExecutableAllocator/JITPlan/DFGOSRExit/FTLOSRExitCompiler/CodeBlock/OmniMain
[ "$AUD" = 0 ] && [ "$(grep -c '^ok' "$L/marker-audit.txt")" = $NAUD ] || fail "marker audit: $(grep -v '^ok' "$L/marker-audit.txt" | head -3 | tr '\n' ' ') ($(grep -c '^ok' "$L/marker-audit.txt")/$NAUD ok)"
st "P1-P4$( [ "$DIAG" = 1 ] && echo ' + P6 ytprof'): $(grep -h -E '^(applied|already)$' "${ALOGS[@]}" | paste -sd' '); marker audit $NAUD/$NAUD"
# changed-file gate: the overlay upper holds exactly the recipe files and the P1-P4 files
(cd "$UP" && find . -path ./build -prune -o -type f ! -name '.*' ! -name link-command.json -print | sed 's#^\./##' | sort) > "$L/upper-files.txt"
printf '%s\n' engine/entry/OmniMain.cpp webkit/Source/WTF/wtf/PlatformRegisters.h webkit/Source/WTF/wtf/Threading.cpp \
  webkit/Source/JavaScriptCore/jit/ExecutableAllocator.cpp webkit/Source/JavaScriptCore/jit/JITPlan.cpp webkit/Source/JavaScriptCore/dfg/DFGOSRExit.cpp \
  webkit/Source/JavaScriptCore/ftl/FTLOSRExitCompiler.cpp webkit/Source/JavaScriptCore/bytecode/CodeBlock.cpp engine/media/OmniMP4Demuxer.cpp engine/media/OmniMediaCaps.h engine/media/OmniPacketDecoder.cpp engine/media/OmniHlsSession.cpp engine/media/OmniMP4Demuxer.h engine/media/OmniHlsSegment.cpp engine/entry/OmniMSESource.cpp $CHANGED $( [ "$DIAG" = 1 ] && echo $YTP_FILES) | sort -u > "$L/upper-expected.txt"
diff "$L/upper-expected.txt" "$L/upper-files.txt" > "$L/upper-diff.txt" || fail "changed files differ from the expected set: $(tr '\n' ' ' < "$L/upper-diff.txt" | cut -c1-400)"
(cd "$UP" && sha256sum $(cat "$L/upper-files.txt")) > "$L/upper-sha256.txt"
# 3. configure (once; later runs are incremental) + cache-diff and cmakeconfig gates
if [ ! -f "$B/build.ninja" ]; then
  python3 -I - "$T/configure-cmd.json" > "$L/cmake-args.txt" <<'PY' || fail "cmake args"
import json, sys
a = json.load(open(sys.argv[1]))
assert a[0] == 'cmake' and a[a.index('-S') + 1] == '/home/builder/s1/webkit' and a[a.index('-B') + 1] == '/home/builder/s1/build', a[:6]
want = {'-DENABLE_ASYNC_SCROLLING:BOOL=': 'ON', '-DENABLE_DFG_JIT:BOOL=': 'ON', '-DENABLE_FTL_JIT:BOOL=': 'ON',
        '-DENABLE_WEBASSEMBLY_BBQJIT:BOOL=': 'OFF', '-DENABLE_WEBASSEMBLY_OMGJIT:BOOL=': 'OFF'}
out, seen = [], set()
for x in a[1:]:
    for k, v in want.items():
        if x.startswith(k): x = k + v; seen.add(k)
    out.append(x)
out += [k + v for k, v in want.items() if k not in seen]
print('\n'.join(out))
PY
  mapfile -t ARGS < "$L/cmake-args.txt"
  st "configure: cmake with $(grep -c '' "$L/cmake-args.txt") args (configure-cmd.json + ASYNC_SCROLLING=ON + DFG_JIT=ON + FTL_JIT=ON)"
  nice -n 19 cmake "${ARGS[@]}" > "$L/configure.log" 2>&1 || fail "cmake: $(grep -m3 -i 'error' "$L/configure.log" | tr '\n' ' ' | cut -c1-600)"
fi
python3 -I - "$B/CMakeCache.txt" "$REFCACHE" > "$L/cache-diff.txt" <<'PY' || fail "CMake cache differs from tree A's beyond DFG/FTL: $(grep '^DIFF' "$L/cache-diff.txt" | head -6 | tr '\n' ' ' | cut -c1-600)"
import re, sys
pat = re.compile(r'^((?:ENABLE|USE|OMNI)_[A-Z0-9_]+|PORT|CMAKE_BUILD_TYPE|CMAKE_TOOLCHAIN_FILE|CMAKE_FIND_ROOT_PATH|CMAKE_PREFIX_PATH|'
                 r'CMAKE_CXX_STANDARD_LIBRARIES|CMAKE_(?:C|CXX)_FLAGS(?:_RELEASE)?|ICU_ROOT|WEBKIT_LIBRARIES_DIR|MEMORY_EXTRA_[A-Z_]+):[A-Z]+=(.*)$')
def load(p):
    d = {}
    for l in open(p):
        m = pat.match(l.rstrip('\n'))
        if m: d[m[1]] = m[2]
    return d
new, ref = load(sys.argv[1]), load(sys.argv[2])
diff = sorted(k for k in new.keys() | ref.keys() if new.get(k) != ref.get(k))
for k in diff: print('DIFF %s new=%r treeA=%r' % (k, new.get(k), ref.get(k)))
ok = set(diff) == {'ENABLE_DFG_JIT', 'ENABLE_FTL_JIT'} and new['ENABLE_DFG_JIT'] == new['ENABLE_FTL_JIT'] == 'ON'
print('RESULT %d entries compared, %d differ: %s' % (len(new.keys() | ref.keys()), len(diff), 'only DFG/FTL (OK)' if ok else 'UNEXPECTED'))
sys.exit(0 if ok else 1)
PY
CC=$(find "$B" -maxdepth 3 -name cmakeconfig.h | head -1)
for d in "ENABLE_DFG_JIT 1" "ENABLE_FTL_JIT 1" "ENABLE_ASYNC_SCROLLING 1" "ENABLE_JIT 1" "ENABLE_WEBASSEMBLY_BBQJIT 0" "ENABLE_WEBASSEMBLY_OMGJIT 0"; do
  grep -q "define $d" "$CC" || fail "cmakeconfig.h lacks '#define $d'"
done
st "cache gate: $(tail -1 "$L/cache-diff.txt"); cmakeconfig: DFG 1, FTL 1, ASYNC_SCROLLING 1, Wasm BBQ/OMG 0"
# 4. build
# variant stamp (OMNI_JSCFTL_DIAG_V1): the overlay upper is rebuilt every run, so after a DIAG build the 16 ytprof files come
# back from the lower dirs with mtimes OLDER than their DIAG objects and ninja would keep the ytprof code. A default build
# after a DIAG one therefore deletes every object whose recorded deps include one of those files (ninja -t deps).
VST="$B/.omni-jscftl-variant"
if [ "$DIAG" = 1 ]; then echo diag > "$VST" || fail "variant stamp"
elif [ "$(cat "$VST" 2>/dev/null)" = diag ]; then
  ninja -C "$B" -t deps > "$L/ninja-deps.txt" 2>&1 || fail "ninja -t deps"
  python3 -I - "$L/ninja-deps.txt" "$B" "$T" $YTP_FILES > "$L/variant-switch.txt" <<'PY' || fail "variant switch: $(tail -1 "$L/variant-switch.txt")"
import os, sys
deps, b, t, rels = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
want = {os.path.join(t, r) for r in rels}; outs, seen, cur = set(), set(), None
for l in open(deps, errors='replace'):
    if l[:1] not in ' \t' and ': #deps' in l: cur = l.split(': #deps')[0]
    elif cur and l.strip():
        d = os.path.normpath(os.path.join(b, l.strip()))
        if d in want: outs.add(cur); seen.add(d)
for o in sorted(outs):
    p = os.path.join(b, o)
    if os.path.exists(p): os.remove(p)
    print('removed', o)
for w in sorted(want - seen): print('NO-DEPS', w)
print('RESULT %d objects depending on the %d ytprof files removed (%d files without a recorded dependent)' % (len(outs), len(want), len(want - seen)))
sys.exit(0 if seen == want else 1)
PY
  st "variant switch diag -> default: $(tail -1 "$L/variant-switch.txt")"
fi
st "ninja start (-j4, nice 19, ionice idle); load $(cut -d' ' -f1-3 /proc/loadavg); free $(df -BG --output=avail /home | tail -1 | tr -d ' ')"
nice -n 19 ionice -c3 ninja -k 0 -C "$B" -j4 OmniEngine > "$L/ninja.log" 2>&1 || fail "ninja: $(grep -m12 -E 'error:|FAILED' "$L/ninja.log" | tr '\n' ' ' | cut -c1-2500)"
IPCC=$(find "$B" -path '*DerivedSources*' \( -name '*MessageReceiver.cpp' -o -name '*Messages.h' -o -name 'GeneratedSerializers.cpp' -o -name 'GeneratedSerializers.h' \) -type f -exec sha256sum {} + 2>/dev/null | sort -k2 | sha256sum | cut -c1-16)
[ "$IPCC" = da4a75622a0a473f ] || fail "generated IPC code $IPCC differs from the title's da4a75622a0a473f"
st "ninja ok: $(grep -c '^\[' "$L/ninja.log") steps, $(grep -c 'warning:' "$L/ninja.log") warnings; IPC = the title's (da4a7562)"
[ "$DIAG" = 1 ] || rm -f "$VST"
# 5. link (build-omni-gpupages-child-relink.sh step 3, own folders)
cd "$NC" || fail "no link workspace"
python3 "$NC/make_link_command.py" > "$L/link-command-child.log" 2>&1 || fail "child link command"
rm -rf "$LK"; mkdir -p "$LK/s1obj"
CF=(-std=c11 -O2 -Wall -Wextra -Wno-unused-parameter -fPIC "-I$SRCM/include" "-I$UPV/tooling/gpu-broker")
mkdir -p "$LK/ldo" && cp "$S1/src/ogp-s1-child.c" "$LK/ldo/" && python3 -I "$S1/tools/apply_layers_default_on.py" child "$LK/ldo" > "$L/apply_layers_default_on_child.log" 2>&1 || fail "layers default on (child ctor)"
python3 -I "$S1/tools/apply_stack_min.py" "$LK/ldo/ogp-s1-child.c" > "$L/apply_stack_min.log" 2>&1 || fail "stack min: $(tail -1 "$L/apply_stack_min.log")"
grep -q OMNI_STACK_MIN_2M_V1 "$LK/ldo/ogp-s1-child.c" || fail "stack min marker missing"
for x in ogp-s1-child ogp_dri_nodrm_stubs_weak ogp_payload_libc_weak; do
  xs="$S1/src/$x.c"; [ "$x" = ogp-s1-child ] && xs="$LK/ldo/ogp-s1-child.c"   # layers default on: the patched copy
  "$PSDK/bin/prospero-clang" "${CF[@]}" "-I$S1/src" -c "$xs" -o "$LK/s1obj/$x.o" >> "$L/s1obj.log" 2>&1 || fail "compile $x"
done
OGP_S1_MAP="$LK/child.map" python3 "$S1/tools/s1_link_inputs.py" "$LK/s1-link-inputs.json" "$MB" "$CP2" "$LK/s1obj" > "$L/s1-link-inputs.log" 2>&1 || fail "link inputs"
python3 "$S1/tools/patch_child_build.py" "$NC/child_build.py" > "$L/patch-child-build.log" 2>&1 || fail "child_build patch"
rm -rf "$SECL"; mkdir -p "$SECL" && cp -dR --preserve=mode,timestamps $H/omni-seclibs/stage/user/homebrew/lib/*.a "$SECL"/ \
  && rm -f "$SECL/libcurl.a" && cp $H/yt-libs/seclibs/libcurl.a "$SECL/libcurl.a" || fail "h2 seclibs"
PL=$H/yt-libs/stage/user/homebrew/lib; EXTRA="$PL/libnghttp2.a:$PL/libbrotlidec.a:$PL/libbrotlicommon.a"
OMNI_SECLIBS="$SECL" OMNI_NET_EXTRA_LIBS="$EXTRA" OMNI_NET_LABEL="omni-launch-rc6-gpupages+jscftl" OMNI_CHILD_OUT="$LK/child" OGP_S1_LINK=1 OGP_S1_LINK_INPUTS="$LK/s1-link-inputs.json" \
  python3 "$NC/child_build.py" > "$L/child-build.log" 2>&1 || fail "child link: $(grep -o 'undefined symbol: .*\|duplicate symbol: .*' "$LK/child/link.log" 2>/dev/null | sort -u | head -8 | tr '\n' ' ' | cut -c1-1200)"
NEW="$LK/child/omni-engine-child.elf"; NEWU="$LK/child/omni-engine-child-unstripped.elf"
# 6. gates
$LL/llvm-nm -u "$NEWU" | awk '{print $NF}' | sort -u > "$LK/child-undef.txt"; comm -12 "$LK/child-undef.txt" "$CP2/archive-defs.txt" > "$L/child-weakref-left.txt"
[ -s "$L/child-weakref-left.txt" ] && fail "child WEAK-REF GATE ($(head -3 "$L/child-weakref-left.txt" | tr '\n' ' '))"
$PSDK/bin/llvm-strip "$NEWU" -o "$LK/restrip.elf" 2>/dev/null; cmp -s "$LK/restrip.elf" "$NEW" || fail "re-strip mismatch"
python3 "$LA/tools/elfguard.py" "$NEW" "$BASE" > "$L/elfguard.log" 2>&1 || fail "elfguard: $(grep FAIL "$L/elfguard.log" | head -3 | tr '\n' ' ')"
KB=0; : > "$L/keys-compare.txt"
while IFS= read -r k; do [ -n "$k" ] || continue; a=$(grep -c -a -- "$k" "$NEW"); b=$(grep -c -a -- "$k" "$BASE")
  if [ "$DIAG" = 1 ] && [ "$a" != "$b" ] && [ "$a" -gt 0 ] && echo "$k" | grep -q -i ytprof; then echo "diag $k new $a a5083735 $b" >> "$L/keys-compare.txt"; continue; fi
  [ "$a" = "$b" ] && echo "same $k $a" >> "$L/keys-compare.txt" || { echo "DIFF $k new $a a5083735 $b" >> "$L/keys-compare.txt"; KB=1; }
done < "$LA/tools/keys-child.txt"
[ "$KB" = 0 ] || fail "launch keys differ from a5083735: $(grep '^DIFF' "$L/keys-compare.txt" | head -4 | tr '\n' ' ')"
for k in OMNI_JSC_DFGFTL_V1 OMNI_JSC_JIT_STATS_V1 OMNI_JSC_JIT_V4 "jit: on (baseline" /data/omni/jsc-dfg-off.flag /data/omni/jsc-ftl-off.flag /data/omni/jsc-jit-pool-mb.txt; do
  grep -q -a -- "$k" "$NEW" || fail "new child lacks the string '$k'"
done
if [ "$DIAG" = 1 ]; then   # P6 present (diag) / absent (default: guards the shared build dir)
  for k in OMNI_YTPROF_WIN_V1 "OMNI YTPROF w seq=" "OMNI YTPROF long seq=" "OMNI YTPROF page seq=" /data/omni/ytprof.flag; do
    grep -q -a -- "$k" "$NEW" || fail "diag child lacks the string '$k'"
  done
else grep -q -a -- OMNI_YTPROF_WIN_V1 "$NEW" && fail "default child carries the ytprof diagnostic (OMNI_YTPROF_WIN_V1): stale DIAG objects"; fi
$LL/llvm-nm -C --defined-only "$NEWU" > "$LK/new-syms.txt"; $LL/llvm-nm -C --defined-only "$BASEU" > "$LK/base-syms.txt"
SY=""; for ns in 'JSC::DFG::' 'JSC::FTL::' 'JSC::B3::'; do SY="$SY ${ns}new=$(grep -c -F "$ns" "$LK/new-syms.txt")/a5083735=$(grep -c -F "$ns" "$LK/base-syms.txt")"; done
echo "$SY" > "$L/tier-symbols.txt"
[ "$(grep -c -F 'JSC::FTL::' "$LK/new-syms.txt")" -gt 100 ] && [ "$(grep -c -F 'JSC::B3::' "$LK/new-syms.txt")" -gt 100 ] \
  && [ "$(grep -c -F 'JSC::DFG::' "$LK/new-syms.txt")" -gt "$(grep -c -F 'JSC::DFG::' "$LK/base-syms.txt")" ] || fail "DFG/FTL/B3 code is not in the child:$SY"
grep -q ' T omniJitStatsLine$' "$LK/new-syms.txt" || fail "omniJitStatsLine not defined in the child"
[ "$DIAG" = 1 ] && { grep -q ' T omni_ytprof_on$' "$LK/new-syms.txt" && grep -q ' T omni_ytprof_mark$' "$LK/new-syms.txt" || fail "omni_ytprof_on/mark not defined in the diag child"; }
st "gates: weak-ref 0; re-strip = shipped; $(tail -1 "$L/elfguard.log"); launch keys $(grep -c '^same' "$L/keys-compare.txt") same vs a5083735; markers present; tiers:$SY"
# 7. copy out (link was on ext4) and compare
if [ "$DIAG" = 1 ]; then D="$X/out-diag/child"; CHK="$X/out-diag/checks.txt"; else D="$X/out/child"; CHK="$X/checks.txt"; fi
rm -rf "$D"; mkdir -p "$D"; cp "$NEW" "$NEWU" "$LK/child/receipt.json" "$D/" || fail "copy"
cmp -s "$NEW" "$D/omni-engine-child.elf" && cmp -s "$NEWU" "$D/omni-engine-child-unstripped.elf" || fail "COPY MISMATCH"
{ sha256sum "$D/omni-engine-child.elf" "$D/omni-engine-child-unstripped.elf" "$BASE"; stat -c '%s %n' "$D/omni-engine-child.elf" "$BASE"
  echo "pairs with the rc6+stage-1 title (generated IPC da4a75622a0a473f); tiers: DFG + FTL ON by default (OMNI_JSC_DFGFTL_DEFAULT_ON_V1); off with /data/omni/jsc-dfg-off.flag / jsc-ftl-off.flag"
  [ "$DIAG" = 1 ] && echo "DIAG: + OMNI_YTPROF_V1/OMNI_YTPROF_WIN_V1 main-thread category timers, on only with /data/omni/ytprof.flag (stderr 'OMNI YTPROF w|long|page|nav|t' lines)"; } > "$CHK"
st "$( [ "$DIAG" = 1 ] && echo 'JSCFTL DIAG CHILD' || echo 'JSCFTL CHILD') ok: $(sha256sum "$D/omni-engine-child.elf" | cut -c1-64) ($(stat -c %s "$D/omni-engine-child.elf") bytes; a5083735 $(stat -c %s "$BASE"))"
IN
cat > "$OUT_" <<'OUT'
#!/bin/bash
# ---------------------------------------------------------------- outer: root, inside the private mount namespace
cd /
O='/path/to/workspace/outputs'; X="$O/omni-jit-ftl"; L="$X/logs"
if [ "${DIAG:-0}" = 1 ]; then L="$X/logs-diag"; TAG=jscftl-diag; STEPS="$X/steps-diag.txt"; else TAG=jscftl; STEPS="$X/steps.txt"; fi
st(){ echo "$(date -u +%FT%TZ) [$TAG] $*" | tee -a "$STEPS"; }
LKF=/tmp/omni-jscftl.lock; ( umask 0; : >> "$LKF" ) 2>/dev/null; exec 9<"$LKF"; flock -n 9 || { st "another jscftl build is running"; exit 1; }
H=/home/builder; T=$H/s1; S3=$H/s3; UPA=$H/ogp-ls1b-up-0; UPB=$H/ogp-ls1b-upB-0
SRC=$H/jscftl-src; UP=$H/jscftl-up-0; WK=$H/jscftl-work-0; BD=$H/jscftl-build; NC=$H/jscftl-cws
[ "$(readlink /proc/self/ns/mnt)" != "$(readlink /proc/1/ns/mnt)" ] || { st "not in a private mount namespace: refusing"; exit 1; }
AV=$(df -BG --output=avail /home | tail -1 | tr -dc 0-9); [ "${AV:-0}" -ge 30 ] || { st "only ${AV} GB free on /home (need 30): stopping"; exit 1; }
[ -d "$UPA/webkit" ] && [ -d "$UPB/webkit" ] && [ -d "$S3/webkit" ] && [ -d "$H/ogp-ls1b-cws" ] || { st "tree A/B/s3 or the link workspace is missing: stopping"; exit 1; }
st "start (root, private mount namespace $(readlink /proc/self/ns/mnt)); FRESH=${FRESH:-0}; ${AV} GB free"
# 1. snapshot state C while holding the ls1b lock (waits up to 1 h for a running ls1b build)
LS=/tmp/omni-gpupages-ls1b.lock; ( umask 0; : >> "$LS" ) 2>/dev/null; exec 8<"$LS"
flock -w 3600 8 || { st "the ls1b lock stayed busy for 1 h: stopping"; exit 1; }
python3 -I - "$UPA" "$UPB" "$S3" > "$L/snapshot-gate.txt" 2>&1 <<'PY'
import os, sys
upa, upb, s3 = sys.argv[1:4]
def files(up):
    s = set()
    for root, dirs, fs in os.walk(up):
        rel = os.path.relpath(root, up)
        if rel == 'build' or rel.startswith('build/'): dirs[:] = []; continue
        for f in fs:
            p = os.path.normpath(os.path.join(rel, f))
            if os.path.basename(p).startswith('.') or p.endswith('link-command.json'): continue
            s.add(p)
    return s
def view(up, p):
    for base in (up, s3):
        q = os.path.join(base, p)
        if os.path.lexists(q): return open(q, 'rb').read() if os.path.isfile(q) else b'<not a regular file>'
    return None
paths = sorted(files(upa) | files(upb))
bad = [p for p in paths if view(upa, p) != view(upb, p)]
for p in bad: print('DIFF', p)
print('RESULT %d changed paths: %d equal in tree A and tree B, %d differ' % (len(paths), len(paths) - len(bad), len(bad)))
sys.exit(1 if bad else 0)
PY
RC=$?
NEWER=$(find "$UPB" -type f -newermt '2026-11-15 20:24:17 UTC' | head -5)
WO=$(find "$UPB" \( -type c -o -type l \) | head -3)
if [ "$RC" != 0 ] || { [ -n "$NEWER" ] && [ "${ALLOW_NEWER_SOURCES:-0}" != 1 ]; } || [ -n "$WO" ]; then
  flock -u 8; st "snapshot gate FAILED: $(tail -1 "$L/snapshot-gate.txt"); newer than a5083735's relink: ${NEWER:-none}; whiteouts/links: ${WO:-none}"; exit 1
fi
rm -rf "$SRC" && mkdir -p "$SRC" && rsync -a --exclude=/build --exclude=/link-command.json "$UPB/" "$SRC/" || { flock -u 8; st "snapshot copy FAILED"; exit 1; }
flock -u 8; exec 8<&-
(cd "$SRC" && find . -type f | sort | xargs -d '\n' sha256sum) > "$L/snapshot-manifest.txt"
st "snapshot of state C: $(tail -1 "$L/snapshot-gate.txt"); $(grep -c '' "$L/snapshot-manifest.txt") files -> $SRC; ls1b lock released"
# 2. own folders, overlay, bind
rm -rf "$UP" "$WK" "$NC"; mkdir -p "$UP" "$WK"; [ "${FRESH:-0}" = 1 ] && rm -rf "$BD"; mkdir -p "$BD"
cp -a "$H/ogp-ls1b-cws" "$NC" || { st "link workspace copy FAILED"; exit 1; }
chown -R builder:builder "$SRC" "$UP" "$WK" "$NC"; chown builder:builder "$BD"
mount -t overlay overlay -o "lowerdir=$SRC:$S3,upperdir=$UP,workdir=$WK" "$T" 2>"$L/overlay.err" || { st "overlay failed ($(cat "$L/overlay.err"))"; exit 1; }
trap 'cd /; umount "$T/build" 2>/dev/null; umount "$T" 2>/dev/null' EXIT
mount --bind "$BD" "$T/build" || { st "build bind failed"; exit 1; }
# OMNI_VSS_BIND_V1: this namespace only; fresh mtime so ninja rebuilds every file that includes it
MXO=/opt/omni-build/omni-browser/engine/ports/memory-extra/include/memory-extra.h; MXN=/tmp/omni-vss-$$/memory-extra.h
mkdir -p "${MXN%/*}" && cp "$T/engine/ports/memory-extra/include/memory-extra.h" "$MXN" && touch "$MXN" && chmod 644 "$MXN" || { st "vss header copy failed"; exit 1; }
grep -q sceKernelReserveVirtualRange "$MXN" || { st "vss header is not the fixed one"; exit 1; }
mount --bind "$MXN" "$MXO" || { st "vss header bind failed"; exit 1; }
trap 'cd /; umount "$MXO" 2>/dev/null; umount "$T/build" 2>/dev/null; umount "$T" 2>/dev/null' EXIT
st "vss: fixed memory-extra.h bound over $MXO in this namespace ($(sha256sum "$MXO" | cut -c1-12))"
touch "$T/.jscftl-marker" && chown builder:builder "$T/.jscftl-marker" || { st "tree not writable"; exit 1; }
st "overlay $T = $SRC + s3 (upper $UP); build dir $BD ($( [ -f "$BD/build.ninja" ] && echo 'kept: incremental' || echo 'fresh: full build'))"
runuser -u builder -- env DIAG="${DIAG:-0}" bash "$V_INNER"
OUT
sed -i 's/\r$//' "$IN_" "$OUT_"; chmod 755 "$IN_" "$OUT_"
cd /
# FOREGROUND=1: run in the caller's session (a detached child dies when the launching wsl.exe exits)
if [ "${FOREGROUND:-0}" = 1 ]; then
  V_INNER="$IN_" FRESH="${FRESH:-0}" ALLOW_NEWER_SOURCES="${ALLOW_NEWER_SOURCES:-0}" DIAG="$DIAG" unshare -m --propagation private bash "$OUT_" > "$X/native-build$SFX.log" 2>&1 < /dev/null
  echo "jscftl$SFX child build finished: exit $? (progress: omni-jit-ftl/steps$SFX.txt)"; exit 0
fi
V_INNER="$IN_" FRESH="${FRESH:-0}" ALLOW_NEWER_SOURCES="${ALLOW_NEWER_SOURCES:-0}" DIAG="$DIAG" setsid nohup unshare -m --propagation private bash "$OUT_" > "$X/native-build$SFX.log" 2>&1 < /dev/null &
echo "jscftl$SFX child build started, pid $! (progress: omni-jit-ftl/steps$SFX.txt, log: omni-jit-ftl/native-build$SFX.log)"
