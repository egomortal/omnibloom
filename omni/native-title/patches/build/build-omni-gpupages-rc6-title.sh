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
python3 "$S1/tools/apply_l2_chords.py" "$TT" > "$LT_/apply_l2_chords.log" 2>&1 || { st "L2 chords FAILED: $(tail -1 "$LT_/apply_l2_chords.log")"; exit 1; }
st "OMNI_L2_CHORDS_V1: $(paste -sd' ' "$LT_/apply_l2_chords.log")"
python3 "$S1/tools/apply_media_switch.py" "$TT" > "$LT_/apply_media_switch.log" 2>&1 || { st "media switch fix FAILED: $(tail -1 "$LT_/apply_media_switch.log")"; exit 1; }
st "OMNI_MEDIA_SWITCH_V1: $(tail -1 "$LT_/apply_media_switch.log")"
python3 "$S1/tools/apply_dark_qa.py" "$TT" > "$LT_/apply_dark_qa.log" 2>&1 || { st "dark/quick access FAILED: $(tail -1 "$LT_/apply_dark_qa.log")"; exit 1; }
st "OMNI_DARK_CHOICE_V1 + OMNI_QA_CUSTOM_V1 + OMNI_SETTINGS_CREATE_V1: $(paste -sd' ' "$LT_/apply_dark_qa.log")"
python3 "$S1/tools/apply_addon_cap.py" "$TT" > "$LT_/apply_addon_cap.log" 2>&1 || { st "add-on cap FAILED: $(tail -1 "$LT_/apply_addon_cap.log")"; exit 1; }
st "OMNI_ADDON_CAP_40_V1: $(tail -1 "$LT_/apply_addon_cap.log")"
python3 "$S1/tools/apply_first_run.py" "$TT" > "$LT_/apply_first_run.log" 2>&1 || { st "first-run fix FAILED: $(tail -1 "$LT_/apply_first_run.log")"; exit 1; }
st "OMNI_FIRST_RUN_V1: $(tail -1 "$LT_/apply_first_run.log")"
python3 "$S1/tools/apply_media_diag.py" "$TT" > "$LT_/apply_media_diag.log" 2>&1 || { st "media diag FAILED: $(tail -1 "$LT_/apply_media_diag.log")"; exit 1; }
st "OMNI_MEDIA_DIAG_V1: $(paste -sd' ' "$LT_/apply_media_diag.log")"
python3 "$S1/tools/apply_media_http.py" "$TT" > "$LT_/apply_media_http.log" 2>&1 || { st "media http FAILED: $(tail -1 "$LT_/apply_media_http.log")"; exit 1; }
st "OMNI_MEDIA_HTTP_V3: $(tail -1 "$LT_/apply_media_http.log")"
python3 "$S1/tools/apply_bars_hide.py" "$TT" > "$LT_/apply_bars_hide.log" 2>&1 || { st "bars hide FAILED: $(tail -1 "$LT_/apply_bars_hide.log")"; exit 1; }
# OMNI_UA_OVERRIDE_V1: desktop user agent from /data/omni/ua-desktop.txt (YouTube BotGuard A/B tests)
python3 "$S1/tools/apply_ua_override.py" "$TT" > "$LT_/apply_ua_override.log" 2>&1 || { st "UA override FAILED: $(tail -1 "$LT_/apply_ua_override.log")"; exit 1; }
st "OMNI_BARS_HIDE_V1: $(paste -sd' ' "$LT_/apply_bars_hide.log")"
# OMNI_BARS_CLICK_V1 (2026-11-16): top-bar clicks 52 px low with the quick-access row hidden (needs OMNI_BARS_HIDE_V1)
python3 "$S1/tools/apply_bars_click.py" "$TT" > "$LT_/apply_bars_click.log" 2>&1 || { st "bars click FAILED: $(tail -1 "$LT_/apply_bars_click.log")"; exit 1; }
st "OMNI_BARS_CLICK_V1: $(tail -1 "$LT_/apply_bars_click.log")"
# OMNI_VIDEO_IMMERSIVE_V1 (2026-11-16): a site's own full-page video player keeps the bars away like fullscreen
python3 "$S1/tools/apply_video_immersive.py" "$TT" > "$LT_/apply_video_immersive.log" 2>&1 || { st "video immersive FAILED: $(tail -1 "$LT_/apply_video_immersive.log")"; exit 1; }
st "OMNI_VIDEO_IMMERSIVE_V1: $(paste -sd' ' "$LT_/apply_video_immersive.log")"
# ... and the eboot workspace's copy of the video service, which the title link compiles (tools/prep_launch.py)
python3 "$S1/tools/apply_video_immersive.py" "$NE" media > "$LT_/apply_video_immersive_ne.log" 2>&1 || { st "video immersive (eboot media) FAILED: $(tail -1 "$LT_/apply_video_immersive_ne.log")"; exit 1; }
st "OMNI_VIDEO_IMMERSIVE_V1 eboot media: $(paste -sd' ' "$LT_/apply_video_immersive_ne.log")"
python3 "$S1/tools/apply_video_enhance_media.py" "$NE" > "$LT_/apply_video_enhance_media.log" 2>&1 || { st "video enhance (eboot media) FAILED: $(tail -1 "$LT_/apply_video_enhance_media.log")"; exit 1; }
st "OMNI_VIDEO_ENHANCE_V1 eboot media: $(tail -1 "$LT_/apply_video_enhance_media.log")"
# OMNI_GRABBER_SUSPECTS_V1 (2026-11-16): playlists found by content (Downloads confirms), 6 playlist rows
python3 "$S1/tools/apply_grabber_suspects.py" "$TT" > "$LT_/apply_grabber_suspects.log" 2>&1 || { st "grabber suspects FAILED: $(tail -1 "$LT_/apply_grabber_suspects.log")"; exit 1; }
st "OMNI_GRABBER_SUSPECTS_V1: $(tail -1 "$LT_/apply_grabber_suspects.log")"
# 2026-11-16 browser batch (owner: "you can do all of it"): site zoom, file downloads, send link, quick actions, search tiles, small comforts
python3 "$S1/tools/apply_site_zoom.py" "$TT" > "$LT_/apply_site_zoom.log" 2>&1 || { st "OMNI_SITE_ZOOM_V1 FAILED: $(tail -1 "$LT_/apply_site_zoom.log")"; exit 1; }
st "OMNI_SITE_ZOOM_V1: $(paste -sd' ' "$LT_/apply_site_zoom.log")"
python3 "$S1/tools/apply_file_downloads.py" "$TT" > "$LT_/apply_file_downloads.log" 2>&1 || { st "OMNI_FILE_DOWNLOADS_V1 FAILED: $(tail -1 "$LT_/apply_file_downloads.log")"; exit 1; }
st "OMNI_FILE_DOWNLOADS_V1: $(paste -sd' ' "$LT_/apply_file_downloads.log")"
python3 "$S1/tools/apply_send_link.py" "$TT" > "$LT_/apply_send_link.log" 2>&1 || { st "OMNI_SEND_LINK_V1 FAILED: $(tail -1 "$LT_/apply_send_link.log")"; exit 1; }
st "OMNI_SEND_LINK_V1: $(paste -sd' ' "$LT_/apply_send_link.log")"
python3 "$S1/tools/apply_quick_actions.py" "$TT" > "$LT_/apply_quick_actions.log" 2>&1 || { st "OMNI_QUICK_ACTIONS_V1 FAILED: $(tail -1 "$LT_/apply_quick_actions.log")"; exit 1; }
st "OMNI_QUICK_ACTIONS_V1: $(paste -sd' ' "$LT_/apply_quick_actions.log")"
python3 "$S1/tools/apply_search_tiles.py" "$TT" > "$LT_/apply_search_tiles.log" 2>&1 || { st "OMNI_SEARCH_TILES_V1 FAILED: $(tail -1 "$LT_/apply_search_tiles.log")"; exit 1; }
st "OMNI_SEARCH_TILES_V1: $(paste -sd' ' "$LT_/apply_search_tiles.log")"
python3 "$S1/tools/apply_small_comforts.py" "$TT" > "$LT_/apply_small_comforts.log" 2>&1 || { st "OMNI_SMALL_COMFORTS_V1 FAILED: $(tail -1 "$LT_/apply_small_comforts.log")"; exit 1; }
st "OMNI_SMALL_COMFORTS_V1: $(paste -sd' ' "$LT_/apply_small_comforts.log")"
# 2026-11-16 overnight batch 2: uBlock content in subframes, YouTube TV mode + honest UA, reading list
python3 "$S1/tools/apply_ublock_frames.py" "$TT" > "$LT_/apply_ublock_frames.log" 2>&1 || { st "OMNI_UBLOCK_FRAMES_V1 FAILED: $(tail -1 "$LT_/apply_ublock_frames.log")"; exit 1; }
st "OMNI_UBLOCK_FRAMES_V1: $(paste -sd' ' "$LT_/apply_ublock_frames.log")"
python3 "$S1/tools/apply_youtube_tv.py" "$TT" > "$LT_/apply_youtube_tv.log" 2>&1 || { st "OMNI_YOUTUBE_TV_V1 FAILED: $(tail -1 "$LT_/apply_youtube_tv.log")"; exit 1; }
st "OMNI_YOUTUBE_TV_V1: $(paste -sd' ' "$LT_/apply_youtube_tv.log")"
python3 "$S1/tools/apply_reading_list.py" "$TT" > "$LT_/apply_reading_list.log" 2>&1 || { st "OMNI_READING_LIST_V1 FAILED: $(tail -1 "$LT_/apply_reading_list.log")"; exit 1; }
st "OMNI_READING_LIST_V1: $(paste -sd' ' "$LT_/apply_reading_list.log")"
python3 "$S1/tools/apply_tab_audio.py" "$TT" > "$LT_/apply_tab_audio.log" 2>&1 || { st "OMNI_TAB_AUDIO_V1 FAILED: $(tail -1 "$LT_/apply_tab_audio.log")"; exit 1; }
st "OMNI_TAB_AUDIO_V1: $(paste -sd' ' "$LT_/apply_tab_audio.log")"
python3 "$S1/tools/apply_history_plus.py" "$TT" > "$LT_/apply_history_plus.log" 2>&1 || { st "OMNI_HISTORY_PLUS_V1 FAILED: $(tail -1 "$LT_/apply_history_plus.log")"; exit 1; }
st "OMNI_HISTORY_PLUS_V1: $(paste -sd' ' "$LT_/apply_history_plus.log")"
python3 "$S1/tools/apply_yt_attest_log.py" "$TT" > "$LT_/apply_yt_attest_log.log" 2>&1 || { st "OMNI_YT_ATTEST_LOG_V1 FAILED: $(tail -1 "$LT_/apply_yt_attest_log.log")"; exit 1; }
st "OMNI_YT_ATTEST_LOG_V1: $(paste -sd' ' "$LT_/apply_yt_attest_log.log")"
python3 "$S1/tools/apply_tab_sessions.py" "$TT" > "$LT_/apply_tab_sessions.log" 2>&1 || { st "OMNI_TAB_SESSIONS_V1 FAILED: $(tail -1 "$LT_/apply_tab_sessions.log")"; exit 1; }
st "OMNI_TAB_SESSIONS_V1: $(paste -sd' ' "$LT_/apply_tab_sessions.log")"
python3 "$S1/tools/apply_kb_words.py" "$TT" > "$LT_/apply_kb_words.log" 2>&1 || { st "OMNI_KB_WORDS_V1 FAILED: $(tail -1 "$LT_/apply_kb_words.log")"; exit 1; }
st "OMNI_KB_WORDS_V1: $(paste -sd' ' "$LT_/apply_kb_words.log")"
python3 "$S1/tools/apply_continue_watching.py" "$TT" > "$LT_/apply_continue_watching.log" 2>&1 || { st "OMNI_CONTINUE_WATCHING_V1 FAILED: $(tail -1 "$LT_/apply_continue_watching.log")"; exit 1; }
st "OMNI_CONTINUE_WATCHING_V1: $(paste -sd' ' "$LT_/apply_continue_watching.log")"
python3 "$S1/tools/apply_autoplay.py" "$TT" > "$LT_/apply_autoplay.log" 2>&1 || { st "OMNI_AUTOPLAY_V1 FAILED: $(tail -1 "$LT_/apply_autoplay.log")"; exit 1; }
st "OMNI_AUTOPLAY_V1: $(paste -sd' ' "$LT_/apply_autoplay.log")"
python3 "$S1/tools/apply_https_only.py" "$TT" > "$LT_/apply_https_only.log" 2>&1 || { st "OMNI_HTTPS_ONLY_V1 FAILED: $(tail -1 "$LT_/apply_https_only.log")"; exit 1; }
st "OMNI_HTTPS_ONLY_V1: $(paste -sd' ' "$LT_/apply_https_only.log")"
python3 "$S1/tools/apply_media_controls.py" "$TT" > "$LT_/apply_media_controls.log" 2>&1 || { st "OMNI_MEDIA_CONTROLS_V1 FAILED: $(tail -1 "$LT_/apply_media_controls.log")"; exit 1; }
st "OMNI_MEDIA_CONTROLS_V1: $(paste -sd' ' "$LT_/apply_media_controls.log")"
python3 "$S1/tools/apply_pinned_tabs.py" "$TT" > "$LT_/apply_pinned_tabs.log" 2>&1 || { st "OMNI_PINNED_TABS_V1 FAILED: $(tail -1 "$LT_/apply_pinned_tabs.log")"; exit 1; }
st "OMNI_PINNED_TABS_V1: $(paste -sd' ' "$LT_/apply_pinned_tabs.log")"
python3 "$S1/tools/apply_site_clear.py" "$TT" > "$LT_/apply_site_clear.log" 2>&1 || { st "OMNI_SITE_CLEAR_V1 FAILED: $(tail -1 "$LT_/apply_site_clear.log")"; exit 1; }
st "OMNI_SITE_CLEAR_V1: $(paste -sd' ' "$LT_/apply_site_clear.log")"
python3 "$S1/tools/apply_tab_search.py" "$TT" > "$LT_/apply_tab_search.log" 2>&1 || { st "OMNI_TAB_SEARCH_V1 FAILED: $(tail -1 "$LT_/apply_tab_search.log")"; exit 1; }
st "OMNI_TAB_SEARCH_V1: $(paste -sd' ' "$LT_/apply_tab_search.log")"
python3 "$S1/tools/apply_sleep_timer.py" "$TT" > "$LT_/apply_sleep_timer.log" 2>&1 || { st "OMNI_SLEEP_TIMER_V1 FAILED: $(tail -1 "$LT_/apply_sleep_timer.log")"; exit 1; }
st "OMNI_SLEEP_TIMER_V1: $(paste -sd' ' "$LT_/apply_sleep_timer.log")"
python3 "$S1/tools/apply_site_css.py" "$TT" > "$LT_/apply_site_css.log" 2>&1 || { st "OMNI_SITE_TWEAKS_V1 FAILED: $(tail -1 "$LT_/apply_site_css.log")"; exit 1; }
st "OMNI_SITE_TWEAKS_V1: $(paste -sd' ' "$LT_/apply_site_css.log")"
python3 "$S1/tools/apply_qr_share.py" "$TT" > "$LT_/apply_qr_share.log" 2>&1 || { st "OMNI_QR_SHARE_V1 FAILED: $(tail -1 "$LT_/apply_qr_share.log")"; exit 1; }
st "OMNI_QR_SHARE_V1: $(paste -sd' ' "$LT_/apply_qr_share.log")"
python3 "$S1/tools/apply_screenshot_gallery.py" "$TT" > "$LT_/apply_screenshot_gallery.log" 2>&1 || { st "OMNI_SCREENSHOT_GALLERY_V1 FAILED: $(tail -1 "$LT_/apply_screenshot_gallery.log")"; exit 1; }
st "OMNI_SCREENSHOT_GALLERY_V1: $(paste -sd' ' "$LT_/apply_screenshot_gallery.log")"
python3 "$S1/tools/apply_playback_speed.py" "$TT" > "$LT_/apply_playback_speed.log" 2>&1 || { st "OMNI_PLAYBACK_SPEED_V1 FAILED: $(tail -1 "$LT_/apply_playback_speed.log")"; exit 1; }
st "OMNI_PLAYBACK_SPEED_V1: $(paste -sd' ' "$LT_/apply_playback_speed.log")"
python3 "$S1/tools/apply_tab_groups.py" "$TT" > "$LT_/apply_tab_groups.log" 2>&1 || { st "OMNI_TAB_GROUPS_V1 FAILED: $(tail -1 "$LT_/apply_tab_groups.log")"; exit 1; }
st "OMNI_TAB_GROUPS_V1: $(paste -sd' ' "$LT_/apply_tab_groups.log")"
python3 "$S1/tools/apply_bookmarks_manager.py" "$TT" > "$LT_/apply_bookmarks_manager.log" 2>&1 || { st "OMNI_BOOKMARKS_MANAGER_V1 FAILED: $(tail -1 "$LT_/apply_bookmarks_manager.log")"; exit 1; }
st "OMNI_BOOKMARKS_MANAGER_V1: $(paste -sd' ' "$LT_/apply_bookmarks_manager.log")"
python3 "$S1/tools/apply_controls_help.py" "$TT" > "$LT_/apply_controls_help.log" 2>&1 || { st "OMNI_CONTROLS_HELP_V1 FAILED: $(tail -1 "$LT_/apply_controls_help.log")"; exit 1; }
st "OMNI_CONTROLS_HELP_V1: $(paste -sd' ' "$LT_/apply_controls_help.log")"
python3 "$S1/tools/apply_popup_notice.py" "$TT" > "$LT_/apply_popup_notice.log" 2>&1 || { st "OMNI_POPUP_NOTICE_V1 FAILED: $(tail -1 "$LT_/apply_popup_notice.log")"; exit 1; }
st "OMNI_POPUP_NOTICE_V1: $(paste -sd' ' "$LT_/apply_popup_notice.log")"
python3 "$S1/tools/apply_offline_retry.py" "$TT" > "$LT_/apply_offline_retry.log" 2>&1 || { st "OMNI_OFFLINE_RETRY_V1 FAILED: $(tail -1 "$LT_/apply_offline_retry.log")"; exit 1; }
st "OMNI_OFFLINE_RETRY_V1: $(paste -sd' ' "$LT_/apply_offline_retry.log")"
python3 "$S1/tools/apply_save_image.py" "$TT" > "$LT_/apply_save_image.log" 2>&1 || { st "OMNI_SAVE_IMAGE_V1 FAILED: $(tail -1 "$LT_/apply_save_image.log")"; exit 1; }
st "OMNI_SAVE_IMAGE_V1: $(paste -sd' ' "$LT_/apply_save_image.log")"
python3 "$S1/tools/apply_kb_layouts.py" "$TT" > "$LT_/apply_kb_layouts.log" 2>&1 || { st "OMNI_KB_LAYOUTS_V1 FAILED: $(tail -1 "$LT_/apply_kb_layouts.log")"; exit 1; }
st "OMNI_KB_LAYOUTS_V1: $(paste -sd' ' "$LT_/apply_kb_layouts.log")"
python3 "$S1/tools/apply_settings_search.py" "$TT" > "$LT_/apply_settings_search.log" 2>&1 || { st "OMNI_SETTINGS_SEARCH_V1 FAILED: $(tail -1 "$LT_/apply_settings_search.log")"; exit 1; }
st "OMNI_SETTINGS_SEARCH_V1: $(paste -sd' ' "$LT_/apply_settings_search.log")"
python3 "$S1/tools/apply_clear_range.py" "$TT" > "$LT_/apply_clear_range.log" 2>&1 || { st "OMNI_CLEAR_RANGE_V1 FAILED: $(tail -1 "$LT_/apply_clear_range.log")"; exit 1; }
st "OMNI_CLEAR_RANGE_V1: $(paste -sd' ' "$LT_/apply_clear_range.log")"
python3 "$S1/tools/apply_pad_feedback.py" "$TT" > "$LT_/apply_pad_feedback.log" 2>&1 || { st "OMNI_PAD_FEEDBACK_V1 FAILED: $(tail -1 "$LT_/apply_pad_feedback.log")"; exit 1; }
st "OMNI_PAD_FEEDBACK_V1: $(paste -sd' ' "$LT_/apply_pad_feedback.log")"
python3 "$S1/tools/apply_night_light.py" "$TT" > "$LT_/apply_night_light.log" 2>&1 || { st "OMNI_NIGHT_LIGHT_V1 FAILED: $(tail -1 "$LT_/apply_night_light.log")"; exit 1; }
st "OMNI_NIGHT_LIGHT_V1: $(paste -sd' ' "$LT_/apply_night_light.log")"
python3 "$S1/tools/apply_text_cache_cap.py" "$TT" > "$LT_/apply_text_cache_cap.log" 2>&1 || { st "OMNI_TEXT_CACHE_CAP_V1 FAILED: $(tail -1 "$LT_/apply_text_cache_cap.log")"; exit 1; }
st "OMNI_TEXT_CACHE_CAP_V1: $(paste -sd' ' "$LT_/apply_text_cache_cap.log")"
python3 "$S1/tools/apply_magnifier.py" "$TT" > "$LT_/apply_magnifier.log" 2>&1 || { st "OMNI_MAGNIFIER_V1 FAILED: $(tail -1 "$LT_/apply_magnifier.log")"; exit 1; }
st "OMNI_MAGNIFIER_V1: $(paste -sd' ' "$LT_/apply_magnifier.log")"
python3 "$S1/tools/apply_high_contrast.py" "$TT" > "$LT_/apply_high_contrast.log" 2>&1 || { st "OMNI_HIGH_CONTRAST_V1 FAILED: $(tail -1 "$LT_/apply_high_contrast.log")"; exit 1; }
st "OMNI_HIGH_CONTRAST_V1: $(paste -sd' ' "$LT_/apply_high_contrast.log")"
python3 "$S1/tools/apply_start_custom.py" "$TT" > "$LT_/apply_start_custom.log" 2>&1 || { st "OMNI_START_CUSTOM_V1 FAILED: $(tail -1 "$LT_/apply_start_custom.log")"; exit 1; }
st "OMNI_START_CUSTOM_V1: $(paste -sd' ' "$LT_/apply_start_custom.log")"
python3 "$S1/tools/apply_dl_progress.py" "$TT" > "$LT_/apply_dl_progress.log" 2>&1 || { st "OMNI_DL_PROGRESS_V1 FAILED: $(tail -1 "$LT_/apply_dl_progress.log")"; exit 1; }
st "OMNI_DL_PROGRESS_V1: $(paste -sd' ' "$LT_/apply_dl_progress.log")"
python3 "$S1/tools/apply_site_list.py" "$TT" > "$LT_/apply_site_list.log" 2>&1 || { st "OMNI_SITE_LIST_V1 FAILED: $(tail -1 "$LT_/apply_site_list.log")"; exit 1; }
st "OMNI_SITE_LIST_V1: $(paste -sd' ' "$LT_/apply_site_list.log")"
python3 "$S1/tools/apply_quick_answers.py" "$TT" > "$LT_/apply_quick_answers.log" 2>&1 || { st "OMNI_QUICK_ANSWERS_V1 FAILED: $(tail -1 "$LT_/apply_quick_answers.log")"; exit 1; }
st "OMNI_QUICK_ANSWERS_V1: $(paste -sd' ' "$LT_/apply_quick_answers.log")"
python3 "$S1/tools/apply_caption_style.py" "$TT" > "$LT_/apply_caption_style.log" 2>&1 || { st "OMNI_CAPTION_STYLE_V1 FAILED: $(tail -1 "$LT_/apply_caption_style.log")"; exit 1; }
st "OMNI_CAPTION_STYLE_V1: $(paste -sd' ' "$LT_/apply_caption_style.log")"
python3 "$S1/tools/apply_tab_memory_view.py" "$TT" > "$LT_/apply_tab_memory_view.log" 2>&1 || { st "OMNI_TAB_MEMORY_VIEW_V1 FAILED: $(tail -1 "$LT_/apply_tab_memory_view.log")"; exit 1; }
st "OMNI_TAB_MEMORY_VIEW_V1: $(paste -sd' ' "$LT_/apply_tab_memory_view.log")"
python3 "$S1/tools/apply_find_plus.py" "$TT" > "$LT_/apply_find_plus.log" 2>&1 || { st "OMNI_FIND_PLUS_V1 FAILED: $(tail -1 "$LT_/apply_find_plus.log")"; exit 1; }
st "OMNI_FIND_PLUS_V1: $(paste -sd' ' "$LT_/apply_find_plus.log")"
python3 "$S1/tools/apply_text_select.py" "$TT" > "$LT_/apply_text_select.log" 2>&1 || { st "OMNI_TEXT_SELECT_V1 FAILED: $(tail -1 "$LT_/apply_text_select.log")"; exit 1; }
st "OMNI_TEXT_SELECT_V1: $(paste -sd' ' "$LT_/apply_text_select.log")"
python3 "$S1/tools/apply_dark_schedule.py" "$TT" > "$LT_/apply_dark_schedule.log" 2>&1 || { st "OMNI_DARK_SCHEDULE_V1 FAILED: $(tail -1 "$LT_/apply_dark_schedule.log")"; exit 1; }
st "OMNI_DARK_SCHEDULE_V1: $(paste -sd' ' "$LT_/apply_dark_schedule.log")"
python3 "$S1/tools/apply_tab_switcher.py" "$TT" > "$LT_/apply_tab_switcher.log" 2>&1 || { st "OMNI_TAB_SWITCHER_V1 FAILED: $(tail -1 "$LT_/apply_tab_switcher.log")"; exit 1; }
st "OMNI_TAB_SWITCHER_V1: $(paste -sd' ' "$LT_/apply_tab_switcher.log")"
python3 "$S1/tools/apply_tab_volume.py" "$TT" > "$LT_/apply_tab_volume.log" 2>&1 || { st "OMNI_TAB_VOLUME_V1 FAILED: $(tail -1 "$LT_/apply_tab_volume.log")"; exit 1; }
st "OMNI_TAB_VOLUME_V1: $(paste -sd' ' "$LT_/apply_tab_volume.log")"
python3 "$S1/tools/apply_history_keep.py" "$TT" > "$LT_/apply_history_keep.log" 2>&1 || { st "OMNI_HISTORY_KEEP_V1 FAILED: $(tail -1 "$LT_/apply_history_keep.log")"; exit 1; }
st "OMNI_HISTORY_KEEP_V1: $(paste -sd' ' "$LT_/apply_history_keep.log")"
python3 "$S1/tools/apply_web_apps.py" "$TT" > "$LT_/apply_web_apps.log" 2>&1 || { st "OMNI_WEB_APPS_V1 FAILED: $(tail -1 "$LT_/apply_web_apps.log")"; exit 1; }
st "OMNI_WEB_APPS_V1: $(paste -sd' ' "$LT_/apply_web_apps.log")"
python3 "$S1/tools/apply_colour_filter.py" "$TT" > "$LT_/colour_filter.log" 2>&1 || { st "OMNI_COLOUR_FILTER FAILED: $(tail -1 "$LT_/colour_filter.log")"; exit 1; }
st "OMNI_COLOUR_FILTER: $(paste -sd' ' "$LT_/colour_filter.log")"
# OMNI_GPUPAGES_ZEROCOPY_V1 (outputs/omni-gpu-pages/ZERO-COPY-DESIGN.md): the shell side (inert without /data/omni/gpu-pages-zerocopy.flag)
python3 "$S1/tools/apply_zerocopy_shell.py" "$TT/engine/entry/OmniBrowser.cpp" > "$LT_/apply_zerocopy_shell.log" 2>&1 || { st "zero-copy shell FAILED: $(tail -1 "$LT_/apply_zerocopy_shell.log")"; exit 1; }
st "OMNI_GPUPAGES_ZEROCOPY_V1 shell: $(tail -1 "$LT_/apply_zerocopy_shell.log")"
# OMNI_UBLOCK_MISSING_V1 (2026-11-15): missing uBlock rule files -> pages load + a notice, not "Filtering failed (error 1)" on every page
python3 "$S1/tools/apply_ublock_missing.py" --ublock "$TT/engine/entry/OmniUBlock.cpp" --blocker "$TT/engine/entry/OmniBlocker.cpp" --browser "$TT/engine/entry/OmniBrowser.cpp" > "$LT_/apply_ublock_missing.log" 2>&1 || { st "ublock missing FAILED: $(tail -1 "$LT_/apply_ublock_missing.log")"; exit 1; }
st "OMNI_UBLOCK_MISSING_V1: $(paste -sd' ' "$LT_/apply_ublock_missing.log")"
# OMNI_UBLOCK_REFINE_V1 (2026-11-15 refinement): per-request matcher failures, linear popup glob, IPv6 private-network check, unreadable vs missing rules
python3 "$S1/tools/apply_ublock_refine.py" --ublock "$TT/engine/entry/OmniUBlock.cpp" --browser "$TT/engine/entry/OmniBrowser.cpp" > "$LT_/apply_ublock_refine.log" 2>&1 || { st "ublock refine FAILED: $(tail -1 "$LT_/apply_ublock_refine.log")"; exit 1; }
st "OMNI_UBLOCK_REFINE_V1: $(paste -sd' ' "$LT_/apply_ublock_refine.log")"
python3 "$S1/tools/apply_data_saver.py" "$TT" > "$LT_/data_saver.log" 2>&1 || { st "OMNI_DATA_SAVER FAILED: $(tail -1 "$LT_/data_saver.log")"; exit 1; }
st "OMNI_DATA_SAVER: $(paste -sd' ' "$LT_/data_saver.log")"
python3 "$S1/tools/apply_bg_audio.py" "$TT" > "$LT_/bg_audio.log" 2>&1 || { st "OMNI_BG_AUDIO FAILED: $(tail -1 "$LT_/bg_audio.log")"; exit 1; }
st "OMNI_BG_AUDIO: $(paste -sd' ' "$LT_/bg_audio.log")"
python3 "$S1/tools/apply_scroll_plus.py" "$TT" > "$LT_/scroll_plus.log" 2>&1 || { st "OMNI_SCROLL_PLUS FAILED: $(tail -1 "$LT_/scroll_plus.log")"; exit 1; }
st "OMNI_SCROLL_PLUS: $(paste -sd' ' "$LT_/scroll_plus.log")"
python3 "$S1/tools/apply_tab_actions.py" "$TT" > "$LT_/tab_actions.log" 2>&1 || { st "OMNI_TAB_ACTIONS FAILED: $(tail -1 "$LT_/tab_actions.log")"; exit 1; }
st "OMNI_TAB_ACTIONS: $(paste -sd' ' "$LT_/tab_actions.log")"
python3 "$S1/tools/apply_clip_history.py" "$TT" > "$LT_/clip_history.log" 2>&1 || { st "OMNI_CLIP_HISTORY FAILED: $(tail -1 "$LT_/clip_history.log")"; exit 1; }
st "OMNI_CLIP_HISTORY: $(paste -sd' ' "$LT_/clip_history.log")"
python3 "$S1/tools/apply_kb_emoji.py" "$TT" > "$LT_/kb_emoji.log" 2>&1 || { st "OMNI_KB_EMOJI FAILED: $(tail -1 "$LT_/kb_emoji.log")"; exit 1; }
st "OMNI_KB_EMOJI: $(paste -sd' ' "$LT_/kb_emoji.log")"
python3 "$S1/tools/apply_image_viewer.py" "$TT" > "$LT_/image_viewer.log" 2>&1 || { st "OMNI_IMAGE_VIEWER FAILED: $(tail -1 "$LT_/image_viewer.log")"; exit 1; }
st "OMNI_IMAGE_VIEWER: $(paste -sd' ' "$LT_/image_viewer.log")"
python3 "$S1/tools/apply_highlights.py" "$TT" > "$LT_/highlights.log" 2>&1 || { st "OMNI_HIGHLIGHTS FAILED: $(tail -1 "$LT_/highlights.log")"; exit 1; }
st "OMNI_HIGHLIGHTS: $(paste -sd' ' "$LT_/highlights.log")"
python3 "$S1/tools/apply_link_preview.py" "$TT" > "$LT_/link_preview.log" 2>&1 || { st "OMNI_LINK_PREVIEW FAILED: $(tail -1 "$LT_/link_preview.log")"; exit 1; }
st "OMNI_LINK_PREVIEW: $(paste -sd' ' "$LT_/link_preview.log")"
python3 "$S1/tools/apply_reader_auto.py" "$TT" > "$LT_/reader_auto.log" 2>&1 || { st "OMNI_READER_AUTO FAILED: $(tail -1 "$LT_/reader_auto.log")"; exit 1; }
st "OMNI_READER_AUTO: $(paste -sd' ' "$LT_/reader_auto.log")"
python3 "$S1/tools/apply_pdf_viewer.py" "$TT" > "$LT_/pdf_viewer.log" 2>&1 || { st "OMNI_PDF_VIEWER FAILED: $(tail -1 "$LT_/pdf_viewer.log")"; exit 1; }
st "OMNI_PDF_VIEWER: $(paste -sd' ' "$LT_/pdf_viewer.log")"
python3 "$S1/tools/apply_startup_choice.py" "$TT" > "$LT_/startup_choice.log" 2>&1 || { st "OMNI_STARTUP_CHOICE FAILED: $(tail -1 "$LT_/startup_choice.log")"; exit 1; }
st "OMNI_STARTUP_CHOICE: $(paste -sd' ' "$LT_/startup_choice.log")"
python3 "$S1/tools/apply_ui_accent.py" "$TT" > "$LT_/ui_accent.log" 2>&1 || { st "OMNI_UI_ACCENT FAILED: $(tail -1 "$LT_/ui_accent.log")"; exit 1; }
st "OMNI_UI_ACCENT: $(paste -sd' ' "$LT_/ui_accent.log")"
python3 "$S1/tools/apply_js_trim_fix.py" "$TT" > "$LT_/js_trim_fix.log" 2>&1 || { st "OMNI_JS_TRIM_FIX FAILED: $(tail -1 "$LT_/js_trim_fix.log")"; exit 1; }
st "OMNI_JS_TRIM_FIX: $(paste -sd' ' "$LT_/js_trim_fix.log")"
python3 "$S1/tools/apply_yt_media_stop.py" "$TT" > "$LT_/yt_media_stop.log" 2>&1 || { st "OMNI_YT_MEDIA_STOP FAILED: $(tail -1 "$LT_/yt_media_stop.log")"; exit 1; }
st "OMNI_YT_MEDIA_STOP: $(paste -sd' ' "$LT_/yt_media_stop.log")"
python3 "$S1/tools/apply_ui_scale.py" "$TT" > "$LT_/ui_scale.log" 2>&1 || { st "OMNI_UI_SCALE FAILED: $(tail -1 "$LT_/ui_scale.log")"; exit 1; }
st "OMNI_UI_SCALE: $(paste -sd' ' "$LT_/ui_scale.log")"
python3 "$S1/tools/apply_button_map.py" "$TT" > "$LT_/button_map.log" 2>&1 || { st "OMNI_BUTTON_MAP FAILED: $(tail -1 "$LT_/button_map.log")"; exit 1; }
st "OMNI_BUTTON_MAP: $(paste -sd' ' "$LT_/button_map.log")"
python3 "$S1/tools/apply_ui_lang.py" "$TT" > "$LT_/ui_lang.log" 2>&1 || { st "OMNI_UI_LANG FAILED: $(tail -1 "$LT_/ui_lang.log")"; exit 1; }
st "OMNI_UI_LANG: $(paste -sd' ' "$LT_/ui_lang.log")"
python3 "$S1/tools/apply_perf_overlay.py" "$TT" > "$LT_/perf_overlay.log" 2>&1 || { st "OMNI_PERF_OVERLAY FAILED: $(tail -1 "$LT_/perf_overlay.log")"; exit 1; }
st "OMNI_PERF_OVERLAY: $(paste -sd' ' "$LT_/perf_overlay.log")"
python3 "$S1/tools/apply_search_engine.py" "$TT" > "$LT_/search_engine.log" 2>&1 || { st "OMNI_SEARCH_ENGINE FAILED: $(tail -1 "$LT_/search_engine.log")"; exit 1; }
st "OMNI_SEARCH_ENGINE: $(paste -sd' ' "$LT_/search_engine.log")"
python3 "$S1/tools/apply_parental.py" "$TT" > "$LT_/parental.log" 2>&1 || { st "OMNI_PARENTAL FAILED: $(tail -1 "$LT_/parental.log")"; exit 1; }
st "OMNI_PARENTAL: $(paste -sd' ' "$LT_/parental.log")"
python3 "$S1/tools/apply_pw_lock.py" "$TT" > "$LT_/pw_lock.log" 2>&1 || { st "OMNI_PW_LOCK FAILED: $(tail -1 "$LT_/pw_lock.log")"; exit 1; }
st "OMNI_PW_LOCK: $(paste -sd' ' "$LT_/pw_lock.log" | cut -c1-300)"
python3 "$S1/tools/apply_reading_progress.py" "$TT" > "$LT_/reading_progress.log" 2>&1 || { st "OMNI_READING_PROGRESS FAILED: $(tail -1 "$LT_/reading_progress.log")"; exit 1; }
st "OMNI_READING_PROGRESS: $(paste -sd' ' "$LT_/reading_progress.log")"
python3 "$S1/tools/apply_reduce_motion.py" "$TT" > "$LT_/reduce_motion.log" 2>&1 || { st "OMNI_REDUCE_MOTION FAILED: $(tail -1 "$LT_/reduce_motion.log")"; exit 1; }
st "OMNI_REDUCE_MOTION: $(paste -sd' ' "$LT_/reduce_motion.log")"
python3 "$S1/tools/apply_bf_list.py" "$TT" > "$LT_/bf_list.log" 2>&1 || { st "OMNI_BF_LIST FAILED: $(tail -1 "$LT_/bf_list.log")"; exit 1; }
st "OMNI_BF_LIST: $(paste -sd' ' "$LT_/bf_list.log")"
python3 "$S1/tools/apply_tab_sleep.py" "$TT" > "$LT_/tab_sleep.log" 2>&1 || { st "OMNI_TAB_SLEEP FAILED: $(tail -1 "$LT_/tab_sleep.log")"; exit 1; }
st "OMNI_TAB_SLEEP: $(paste -sd' ' "$LT_/tab_sleep.log")"
python3 "$S1/tools/apply_tips.py" "$TT" > "$LT_/tips.log" 2>&1 || { st "OMNI_TIPS FAILED: $(tail -1 "$LT_/tips.log")"; exit 1; }
st "OMNI_TIPS: $(paste -sd' ' "$LT_/tips.log")"
python3 "$S1/tools/apply_notice_history.py" "$TT" > "$LT_/notice_history.log" 2>&1 || { st "OMNI_NOTICE_HISTORY FAILED: $(tail -1 "$LT_/notice_history.log")"; exit 1; }
st "OMNI_NOTICE_HISTORY: $(paste -sd' ' "$LT_/notice_history.log")"
python3 "$S1/tools/apply_tab_thumbs.py" "$TT" > "$LT_/tab_thumbs.log" 2>&1 || { st "OMNI_TAB_THUMBS FAILED: $(tail -1 "$LT_/tab_thumbs.log")"; exit 1; }
st "OMNI_TAB_THUMBS: $(paste -sd' ' "$LT_/tab_thumbs.log" | cut -c1-300)"
python3 "$S1/tools/apply_spatial_nav.py" "$TT" > "$LT_/spatial_nav.log" 2>&1 || { st "OMNI_SPATIAL_NAV FAILED: $(tail -1 "$LT_/spatial_nav.log")"; exit 1; }
st "OMNI_SPATIAL_NAV: $(paste -sd' ' "$LT_/spatial_nav.log" | cut -c1-300)"
python3 "$S1/tools/apply_video_keys.py" "$TT" > "$LT_/video_keys.log" 2>&1 || { st "OMNI_VIDEO_KEYS FAILED: $(tail -1 "$LT_/video_keys.log")"; exit 1; }
st "OMNI_VIDEO_KEYS: $(paste -sd' ' "$LT_/video_keys.log" | cut -c1-300)"
python3 "$S1/tools/apply_pause_info.py" "$TT" > "$LT_/pause_info.log" 2>&1 || { st "OMNI_PAUSE_INFO FAILED: $(tail -1 "$LT_/pause_info.log")"; exit 1; }
st "OMNI_PAUSE_INFO: $(paste -sd' ' "$LT_/pause_info.log" | cut -c1-300)"
python3 "$S1/tools/apply_download_all.py" "$TT" > "$LT_/download_all.log" 2>&1 || { st "OMNI_DOWNLOAD_ALL FAILED: $(tail -1 "$LT_/download_all.log")"; exit 1; }
st "OMNI_DOWNLOAD_ALL: $(paste -sd' ' "$LT_/download_all.log" | cut -c1-300)"
python3 "$S1/tools/apply_notes.py" "$TT" > "$LT_/notes.log" 2>&1 || { st "OMNI_NOTES FAILED: $(tail -1 "$LT_/notes.log")"; exit 1; }
st "OMNI_NOTES: $(paste -sd' ' "$LT_/notes.log" | cut -c1-300)"
python3 "$S1/tools/apply_favicons.py" "$TT" > "$LT_/favicons.log" 2>&1 || { st "OMNI_FAVICONS FAILED: $(tail -1 "$LT_/favicons.log")"; exit 1; }
st "OMNI_FAVICONS: $(paste -sd' ' "$LT_/favicons.log" | cut -c1-300)"
python3 "$S1/tools/apply_start_icons.py" "$TT" > "$LT_/start_icons.log" 2>&1 || { st "OMNI_START_ICONS FAILED: $(tail -1 "$LT_/start_icons.log")"; exit 1; }
st "OMNI_START_ICONS: $(paste -sd' ' "$LT_/start_icons.log" | cut -c1-300)"
python3 "$S1/tools/apply_page_info.py" "$TT" > "$LT_/page_info.log" 2>&1 || { st "OMNI_PAGE_INFO FAILED: $(tail -1 "$LT_/page_info.log")"; exit 1; }
st "OMNI_PAGE_INFO: $(paste -sd' ' "$LT_/page_info.log" | cut -c1-300)"
python3 "$S1/tools/apply_site_search.py" "$TT" > "$LT_/site_search.log" 2>&1 || { st "OMNI_SITE_SEARCH FAILED: $(tail -1 "$LT_/site_search.log")"; exit 1; }
st "OMNI_SITE_SEARCH: $(paste -sd' ' "$LT_/site_search.log" | cut -c1-300)"
python3 "$S1/tools/apply_site_search_suggest.py" "$TT" > "$LT_/site_search_suggest.log" 2>&1 || { st "OMNI_SITE_SEARCH_SUGGEST FAILED: $(tail -1 "$LT_/site_search_suggest.log")"; exit 1; }
st "OMNI_SITE_SEARCH_SUGGEST: $(paste -sd' ' "$LT_/site_search_suggest.log" | cut -c1-300)"
python3 "$S1/tools/apply_saved_suggest.py" "$TT" > "$LT_/saved_suggest.log" 2>&1 || { st "OMNI_SAVED_SUGGEST FAILED: $(tail -1 "$LT_/saved_suggest.log")"; exit 1; }
st "OMNI_SAVED_SUGGEST: $(paste -sd' ' "$LT_/saved_suggest.log" | cut -c1-300)"
python3 "$S1/tools/apply_guest_mode.py" "$TT" > "$LT_/guest_mode.log" 2>&1 || { st "OMNI_GUEST_MODE FAILED: $(tail -1 "$LT_/guest_mode.log")"; exit 1; }
st "OMNI_GUEST_MODE: $(paste -sd' ' "$LT_/guest_mode.log" | cut -c1-300)"
python3 "$S1/tools/apply_pc_links.py" "$TT" > "$LT_/pc_links.log" 2>&1 || { st "OMNI_PC_LINKS FAILED: $(tail -1 "$LT_/pc_links.log")"; exit 1; }
st "OMNI_PC_LINKS: $(paste -sd' ' "$LT_/pc_links.log" | cut -c1-300)"
python3 "$S1/tools/apply_bookmarklets.py" "$TT" > "$LT_/bookmarklets.log" 2>&1 || { st "OMNI_BOOKMARKLETS FAILED: $(tail -1 "$LT_/bookmarklets.log")"; exit 1; }
st "OMNI_BOOKMARKLETS: $(paste -sd' ' "$LT_/bookmarklets.log" | cut -c1-300)"
python3 "$S1/tools/apply_translate_plus.py" "$TT" > "$LT_/translate_plus.log" 2>&1 || { st "OMNI_TRANSLATE_PLUS FAILED: $(tail -1 "$LT_/translate_plus.log")"; exit 1; }
st "OMNI_TRANSLATE_PLUS: $(paste -sd' ' "$LT_/translate_plus.log" | cut -c1-300)"
python3 "$S1/tools/apply_yt_guard_recover.py" "$TT" > "$LT_/yt_guard_recover.log" 2>&1 || { st "OMNI_YT_GUARD_RECOVER FAILED: $(tail -1 "$LT_/yt_guard_recover.log")"; exit 1; }
st "OMNI_YT_GUARD_RECOVER: $(paste -sd' ' "$LT_/yt_guard_recover.log" | cut -c1-300)"
python3 "$S1/tools/apply_auto_refresh.py" "$TT" > "$LT_/auto_refresh.log" 2>&1 || { st "OMNI_AUTO_REFRESH FAILED: $(tail -1 "$LT_/auto_refresh.log")"; exit 1; }
st "OMNI_AUTO_REFRESH: $(paste -sd' ' "$LT_/auto_refresh.log" | cut -c1-300)"
python3 "$S1/tools/apply_audio_bar.py" "$TT" > "$LT_/audio_bar.log" 2>&1 || { st "OMNI_AUDIO_BAR FAILED: $(tail -1 "$LT_/audio_bar.log")"; exit 1; }
st "OMNI_AUDIO_BAR: $(paste -sd' ' "$LT_/audio_bar.log" | cut -c1-300)"
python3 "$S1/tools/apply_cookie_policy.py" "$TT" > "$LT_/cookie_policy.log" 2>&1 || { st "OMNI_COOKIE_POLICY FAILED: $(tail -1 "$LT_/cookie_policy.log")"; exit 1; }
st "OMNI_COOKIE_POLICY: $(paste -sd' ' "$LT_/cookie_policy.log" | cut -c1-300)"
python3 "$S1/tools/apply_min_text.py" "$TT" > "$LT_/min_text.log" 2>&1 || { st "OMNI_MIN_TEXT FAILED: $(tail -1 "$LT_/min_text.log")"; exit 1; }
st "OMNI_MIN_TEXT: $(paste -sd' ' "$LT_/min_text.log" | cut -c1-300)"
python3 "$S1/tools/apply_one_sound.py" "$TT" > "$LT_/one_sound.log" 2>&1 || { st "OMNI_ONE_SOUND FAILED: $(tail -1 "$LT_/one_sound.log")"; exit 1; }
st "OMNI_ONE_SOUND: $(paste -sd' ' "$LT_/one_sound.log" | cut -c1-300)"
python3 "$S1/tools/apply_sleep_end.py" "$TT" > "$LT_/sleep_end.log" 2>&1 || { st "OMNI_SLEEP_END FAILED: $(tail -1 "$LT_/sleep_end.log")"; exit 1; }
st "OMNI_SLEEP_END: $(paste -sd' ' "$LT_/sleep_end.log" | cut -c1-300)"
python3 "$S1/tools/apply_kb_showpw.py" "$TT" > "$LT_/kb_showpw.log" 2>&1 || { st "OMNI_KB_SHOWPW FAILED: $(tail -1 "$LT_/kb_showpw.log")"; exit 1; }
st "OMNI_KB_SHOWPW: $(paste -sd' ' "$LT_/kb_showpw.log" | cut -c1-300)"
python3 "$S1/tools/apply_kb_fields.py" "$TT" > "$LT_/kb_fields.log" 2>&1 || { st "OMNI_KB_FIELDS FAILED: $(tail -1 "$LT_/kb_fields.log")"; exit 1; }
st "OMNI_KB_FIELDS: $(paste -sd' ' "$LT_/kb_fields.log" | cut -c1-300)"
python3 "$S1/tools/apply_kb_nextfield.py" "$TT" > "$LT_/kb_nextfield.log" 2>&1 || { st "OMNI_KB_NEXTFIELD FAILED: $(tail -1 "$LT_/kb_nextfield.log")"; exit 1; }
st "OMNI_KB_NEXTFIELD: $(paste -sd' ' "$LT_/kb_nextfield.log" | cut -c1-300)"
python3 "$S1/tools/apply_kb_snippets.py" "$TT" > "$LT_/kb_snippets.log" 2>&1 || { st "OMNI_KB_SNIPPETS FAILED: $(tail -1 "$LT_/kb_snippets.log")"; exit 1; }
st "OMNI_KB_SNIPPETS: $(paste -sd' ' "$LT_/kb_snippets.log" | cut -c1-300)"
python3 "$S1/tools/apply_yt_autocontinue.py" "$TT" > "$LT_/yt_autocontinue.log" 2>&1 || { st "OMNI_YT_AUTOCONTINUE FAILED: $(tail -1 "$LT_/yt_autocontinue.log")"; exit 1; }
st "OMNI_YT_AUTOCONTINUE: $(paste -sd' ' "$LT_/yt_autocontinue.log" | cut -c1-300)"
python3 "$S1/tools/apply_whatsnew.py" "$TT" > "$LT_/whatsnew.log" 2>&1 || { st "OMNI_WHATSNEW FAILED: $(tail -1 "$LT_/whatsnew.log")"; exit 1; }
st "OMNI_WHATSNEW: $(paste -sd' ' "$LT_/whatsnew.log" | cut -c1-300)"
python3 "$S1/tools/apply_dl_panel.py" "$TT" > "$LT_/dl_panel.log" 2>&1 || { st "OMNI_DL_PANEL FAILED: $(tail -1 "$LT_/dl_panel.log")"; exit 1; }
st "OMNI_DL_PANEL: $(paste -sd' ' "$LT_/dl_panel.log" | cut -c1-300)"
python3 "$S1/tools/apply_hard_reload.py" "$TT" > "$LT_/hard_reload.log" 2>&1 || { st "OMNI_HARD_RELOAD FAILED: $(tail -1 "$LT_/hard_reload.log")"; exit 1; }
st "OMNI_HARD_RELOAD: $(paste -sd' ' "$LT_/hard_reload.log" | cut -c1-300)"
python3 "$S1/tools/apply_fit_width.py" "$TT" > "$LT_/fit_width.log" 2>&1 || { st "OMNI_FIT_WIDTH FAILED: $(tail -1 "$LT_/fit_width.log")"; exit 1; }
st "OMNI_FIT_WIDTH: $(paste -sd' ' "$LT_/fit_width.log" | cut -c1-300)"
python3 "$S1/tools/apply_site_mute.py" "$TT" > "$LT_/site_mute.log" 2>&1 || { st "OMNI_SITE_MUTE FAILED: $(tail -1 "$LT_/site_mute.log")"; exit 1; }
st "OMNI_SITE_MUTE: $(paste -sd' ' "$LT_/site_mute.log" | cut -c1-300)"
python3 "$S1/tools/apply_site_volume.py" "$TT" > "$LT_/site_volume.log" 2>&1 || { st "OMNI_SITE_VOLUME FAILED: $(tail -1 "$LT_/site_volume.log")"; exit 1; }
st "OMNI_SITE_VOLUME: $(paste -sd' ' "$LT_/site_volume.log" | cut -c1-300)"
python3 "$S1/tools/apply_auto_fullscreen.py" "$TT" > "$LT_/auto_fullscreen.log" 2>&1 || { st "OMNI_AUTO_FULLSCREEN FAILED: $(tail -1 "$LT_/auto_fullscreen.log")"; exit 1; }
st "OMNI_AUTO_FULLSCREEN: $(paste -sd' ' "$LT_/auto_fullscreen.log" | cut -c1-300)"
python3 "$S1/tools/apply_link_qr.py" "$TT" > "$LT_/link_qr.log" 2>&1 || { st "OMNI_LINK_QR FAILED: $(tail -1 "$LT_/link_qr.log")"; exit 1; }
st "OMNI_LINK_QR: $(paste -sd' ' "$LT_/link_qr.log" | cut -c1-300)"
python3 "$S1/tools/apply_tab_autoclose.py" "$TT" > "$LT_/tab_autoclose.log" 2>&1 || { st "OMNI_TAB_AUTOCLOSE FAILED: $(tail -1 "$LT_/tab_autoclose.log")"; exit 1; }
st "OMNI_TAB_AUTOCLOSE: $(paste -sd' ' "$LT_/tab_autoclose.log" | cut -c1-300)"
python3 "$S1/tools/apply_crash_choices.py" "$TT" > "$LT_/crash_choices.log" 2>&1 || { st "OMNI_CRASH_CHOICES FAILED: $(tail -1 "$LT_/crash_choices.log")"; exit 1; }
st "OMNI_CRASH_CHOICES: $(paste -sd' ' "$LT_/crash_choices.log" | cut -c1-300)"
python3 "$S1/tools/apply_lite_mode.py" "$TT" > "$LT_/lite_mode.log" 2>&1 || { st "OMNI_LITE_MODE FAILED: $(tail -1 "$LT_/lite_mode.log")"; exit 1; }
st "OMNI_LITE_MODE: $(paste -sd' ' "$LT_/lite_mode.log" | cut -c1-300)"
python3 "$S1/tools/apply_zapper.py" "$TT" > "$LT_/zapper.log" 2>&1 || { st "OMNI_ZAPPER FAILED: $(tail -1 "$LT_/zapper.log")"; exit 1; }
st "OMNI_ZAPPER: $(paste -sd' ' "$LT_/zapper.log" | cut -c1-300)"
python3 "$S1/tools/apply_game_mode.py" "$TT" > "$LT_/game_mode.log" 2>&1 || { st "OMNI_GAME_MODE FAILED: $(tail -1 "$LT_/game_mode.log")"; exit 1; }
st "OMNI_GAME_MODE: $(paste -sd' ' "$LT_/game_mode.log" | cut -c1-300)"
python3 "$S1/tools/apply_access_input.py" "$TT" > "$LT_/access_input.log" 2>&1 || { st "OMNI_ACCESS_INPUT FAILED: $(tail -1 "$LT_/access_input.log")"; exit 1; }
st "OMNI_ACCESS_INPUT: $(paste -sd' ' "$LT_/access_input.log" | cut -c1-300)"
python3 "$S1/tools/apply_pad_test.py" "$TT" > "$LT_/pad_test.log" 2>&1 || { st "OMNI_PAD_TEST FAILED: $(tail -1 "$LT_/pad_test.log")"; exit 1; }
st "OMNI_PAD_TEST: $(paste -sd' ' "$LT_/pad_test.log" | cut -c1-300)"
python3 "$S1/tools/apply_pointer_tune.py" "$TT" > "$LT_/pointer_tune.log" 2>&1 || { st "OMNI_POINTER_TUNE FAILED: $(tail -1 "$LT_/pointer_tune.log")"; exit 1; }
st "OMNI_POINTER_TUNE: $(paste -sd' ' "$LT_/pointer_tune.log" | cut -c1-300)"
python3 "$S1/tools/apply_seek_pause.py" "$TT" > "$LT_/seek_pause.log" 2>&1 || { st "OMNI_SEEK_PAUSE FAILED: $(tail -1 "$LT_/seek_pause.log")"; exit 1; }
st "OMNI_SEEK_PAUSE: $(paste -sd' ' "$LT_/seek_pause.log" | cut -c1-300)"
python3 "$S1/tools/apply_notice_actions.py" "$TT" > "$LT_/notice_actions.log" 2>&1 || { st "OMNI_NOTICE_ACTIONS FAILED: $(tail -1 "$LT_/notice_actions.log")"; exit 1; }
st "OMNI_NOTICE_ACTIONS: $(paste -sd' ' "$LT_/notice_actions.log" | cut -c1-300)"
python3 "$S1/tools/apply_tab_group_site.py" "$TT" > "$LT_/tab_group_site.log" 2>&1 || { st "OMNI_TAB_GROUP_SITE FAILED: $(tail -1 "$LT_/tab_group_site.log")"; exit 1; }
st "OMNI_TAB_GROUP_SITE: $(paste -sd' ' "$LT_/tab_group_site.log" | cut -c1-300)"
python3 "$S1/tools/apply_oled_care.py" "$TT" > "$LT_/oled_care.log" 2>&1 || { st "OMNI_OLED_CARE FAILED: $(tail -1 "$LT_/oled_care.log")"; exit 1; }
st "OMNI_OLED_CARE: $(paste -sd' ' "$LT_/oled_care.log" | cut -c1-300)"
python3 "$S1/tools/apply_clear_on_exit.py" "$TT" > "$LT_/clear_on_exit.log" 2>&1 || { st "OMNI_CLEAR_ON_EXIT FAILED: $(tail -1 "$LT_/clear_on_exit.log")"; exit 1; }
st "OMNI_CLEAR_ON_EXIT: $(paste -sd' ' "$LT_/clear_on_exit.log" | cut -c1-300)"
python3 "$S1/tools/apply_video_enhance.py" "$TT" > "$LT_/video_enhance.log" 2>&1 || { st "OMNI_VIDEO_ENHANCE FAILED: $(tail -1 "$LT_/video_enhance.log")"; exit 1; }
st "OMNI_VIDEO_ENHANCE_V1 (Video upscaling row): $(tail -1 "$LT_/video_enhance.log")"
# OMNI_SPARE_DEFER_V1 (2026-11-15, reboot investigation): the reserve spare engine 30 s after a launch (off: spare-defer-off.flag)
python3 "$S1/tools/apply_spare_defer.py" "$TT" > "$LT_/apply_spare_defer.log" 2>&1 || { st "spare defer FAILED: $(tail -1 "$LT_/apply_spare_defer.log")"; exit 1; }
st "OMNI_SPARE_DEFER_V1: $(tail -1 "$LT_/apply_spare_defer.log")"
# OMNI_SPARE_LAZY_V1 (2026-11-15): no reserve spare engine unless /data/omni/spare-reserve.flag (the idle 244 MB spare sat on every launch peak)
python3 "$S1/tools/apply_spare_lazy.py" "$TT" > "$LT_/apply_spare_lazy.log" 2>&1 || { st "spare lazy FAILED: $(tail -1 "$LT_/apply_spare_lazy.log")"; exit 1; }
st "OMNI_SPARE_LAZY_V1: $(tail -1 "$LT_/apply_spare_lazy.log")"
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
# OMNI_GPU_PREPREP_V1 (2026-11-17): prep_launch.py COPIES $NE/engine/media into /home/builder/ogp-ls1b-objs/media and
# compiles it right there, and puts a fresh $NE/src/OmniGpuPresent.cpp in place. So the video-service halves of
# OMNI_GPU_DEFAULT_ON_V1 / OMNI_GPU_MIX_V1 must be applied BEFORE prep (g2-g6 compiled OmniHwService.cpp without the
# mix: "gpu mix check" absent from the g6 eboot), and the present halves again AFTER prep (the lines further down).
python3 "$S1/tools/apply_gpu_default_on.py" "$NE" > "$F/logs/apply_gpu_default_on_pre.log" 2>&1 || { st "gpu default on (pre-prep) FAILED: $(tail -1 "$F/logs/apply_gpu_default_on_pre.log")"; exit 1; }
python3 "$S1/tools/apply_gpu_mix.py" "$NE" > "$F/logs/apply_gpu_mix_pre.log" 2>&1 || { st "gpu mix (pre-prep) FAILED: $(tail -1 "$F/logs/apply_gpu_mix_pre.log")"; exit 1; }
# OMNI_MEMMAP_V1 (2026-11-17): test-only title memory map (memmap.flag), engine/media -> must be pre-prep
python3 "$S1/tools/apply_memmap.py" "$NE" > "$F/logs/apply_memmap.log" 2>&1 || { st "memmap FAILED: $(tail -1 "$F/logs/apply_memmap.log")"; exit 1; }
st "memmap (pre-prep): $(tail -1 "$F/logs/apply_memmap.log")"
st "pre-prep GPU patches: default-on $(tail -1 "$F/logs/apply_gpu_default_on_pre.log" | cut -c1-60); mix $(tail -1 "$F/logs/apply_gpu_mix_pre.log" | cut -c1-80)"
python3 "$NE/tools/prep_launch.py" > "$F/logs/prep.log" 2>&1 || { st "prep FAILED: $(tail -2 "$F/logs/prep.log" | tr '\n' ' ' | cut -c1-500)"; exit 1; }
# OMNI_PAGES_FROM_REPO_V1 (2026-11-16): the built-in pages come from the public repo's committed bundle (omni/pages/bundle-clean4 at
# its HEAD), not the 2026-11-04 codex-ui snapshot, which lacked every page added since (What's new, Help, timer, solitaire, ...).
# Runs after prep_launch.py (which rewrites build.py) and before build.py.
OMNIBLOOM='/path/to/omnibloom'; PG=/tmp/omni-pages-repo
rm -rf "$PG" && mkdir -p "$PG" && git -c safe.directory='*' -C "$OMNIBLOOM" archive HEAD omni/pages/bundle-clean4 | tar -x -C "$PG" || { st "pages export FAILED"; exit 1; }
python3 - "$NE/build.py" "$PG/omni/pages/bundle-clean4" > "$F/logs/pages-from-repo.log" 2>&1 <<'PY' || { st "pages source switch FAILED: $(tail -1 "$F/logs/pages-from-repo.log")"; exit 1; }
import sys
p, src = sys.argv[1], sys.argv[2]; s = open(p).read()
old = "OUTS / 'codex-ui/20261104-ui-clean4-final-pages/proposed/pages'"
if s.count(old) != 1 and src not in s: sys.exit('pages copy line not found once')
s = s.replace(old, 'Path(%r)' % src); open(p, 'w').write(s); print('pages source:', src)
PY
st "OMNI_PAGES_FROM_REPO_V1: pages from the repo at $(git -c safe.directory='*' -C "$OMNIBLOOM" rev-parse --short HEAD) ($(find "$PG" -type f | wc -l) files)"
python3 "$S1/tools/apply_zerocopy_present.py" "$NE/src" "$S1/src-title" > "$F/logs/apply_zerocopy_present.log" 2>&1 || { st "zero-copy present FAILED: $(tail -1 "$F/logs/apply_zerocopy_present.log")"; exit 1; }
st "OMNI_GPUPAGES_ZEROCOPY_V1 present: $(tail -1 "$F/logs/apply_zerocopy_present.log")"
python3 "$S1/tools/apply_night_light_present.py" "$NE/src" "$S1/src-title" > "$F/logs/apply_night_light_present.log" 2>&1 || { st "night light present FAILED: $(tail -1 "$F/logs/apply_night_light_present.log")"; exit 1; }
st "OMNI_NIGHT_LIGHT_V1 present: $(tail -1 "$F/logs/apply_night_light_present.log")"
python3 "$S1/tools/apply_colour_filter_present.py" "$NE/src" "$S1/src-title" > "$F/logs/apply_colour_filter_present.log" 2>&1 || { st "colour filter present FAILED: $(tail -1 "$F/logs/apply_colour_filter_present.log")"; exit 1; }
st "OMNI_COLOUR_FILTER_V1 present: $(tail -1 "$F/logs/apply_colour_filter_present.log")"
python3 "$S1/tools/apply_magnifier_present.py" "$NE/src" "$S1/src-title" > "$F/logs/apply_magnifier_present.log" 2>&1 || { st "magnifier present FAILED: $(tail -1 "$F/logs/apply_magnifier_present.log")"; exit 1; }
st "OMNI_MAGNIFIER_V1 present: $(tail -1 "$F/logs/apply_magnifier_present.log")"
# OMNI_STARTER_V1/V3 (2026-11-15): engine processes through Omni's own starter (outputs/omni-starter), elfldr as the fallback
python3 "$S1/tools/apply_starter.py" "$NE/src" > "$F/logs/apply_starter.log" 2>&1 || { st "starter launcher FAILED: $(tail -1 "$F/logs/apply_starter.log")"; exit 1; }
st "OMNI_STARTER_V3: $(tail -1 "$F/logs/apply_starter.log")"
# OMNI_GPU_DEFAULT_ON_V1 (2026-11-17, moved here): GPU present + GPU video conversion on by default (off switches
# gpu-present-off.flag / gpu-video-off.flag; headless self-tests keep the old flag rule). MUST run after prep_launch.py:
# it puts a fresh OmniGpuPresent.cpp into $NE/src every build (before the move, g1/g3 shipped without the present edit).
python3 "$S1/tools/apply_gpu_default_on.py" "$NE" > "$F/logs/apply_gpu_default_on.log" 2>&1 || { st "gpu default on FAILED: $(tail -1 "$F/logs/apply_gpu_default_on.log")"; exit 1; }
st "OMNI_GPU_DEFAULT_ON_V1: $(paste -sd' ' "$F/logs/apply_gpu_default_on.log")"
# check: the present source must carry the edit after this step (the title must not ship without it again)
grep -q "OMNI_GPU_DEFAULT_ON_V1_R2 reason" "$NE/src/OmniGpuPresent.cpp" || { st "gpu default on MISSING in src/OmniGpuPresent.cpp"; exit 1; }
# OMNI_GPU_MIX_V1 (2026-11-17): translucent page pixels over a full-screen video are blended on the GPU (one compute pass
# in the GPU present) instead of recorded per pixel and blended on the CPU (4K overlay bench: page-frame accept 53-82 ms).
# Off switch /data/omni/gpu-mix-off.flag. Must run LAST among the $NE patches (it changes lines others anchor on).
python3 "$S1/tools/apply_gpu_mix.py" "$NE" > "$F/logs/apply_gpu_mix.log" 2>&1 || { st "gpu mix FAILED: $(tail -1 "$F/logs/apply_gpu_mix.log")"; exit 1; }
st "OMNI_GPU_MIX_V1: $(tail -1 "$F/logs/apply_gpu_mix.log")"
# OMNI_PATCH_MARKER_AUDIT_V1 (2026-11-17): every marker a step of this build reported as applied/already must still be in
# the final sources (a re-copied file undid OMNI_GPU_DEFAULT_ON_V1 in g1/g3). Report-only; add --fatal after one clean run.
python3 "$S1/tools/audit_patch_markers.py" --fatal "$F/steps.txt" "$TT/engine" "$NE/src" /home/builder/ogp-ls1b-objs/media "$NE/shader" > "$F/logs/marker-audit.txt" 2>&1 || { st "PATCH MARKER AUDIT FAILED: $(grep -m8 '^MISSING' "$F/logs/marker-audit.txt" | cut -d' ' -f2 | paste -sd' ')"; exit 1; }
st "OMNI_PATCH_MARKER_AUDIT_V1: $(head -1 "$F/logs/marker-audit.txt") $(grep -m8 '^MISSING' "$F/logs/marker-audit.txt" | cut -d' ' -f2 | paste -sd' ')"
# OMNI_GPU_ONE_SUBMITTER_V1: a patched COPY of the broker owner (the shared broker-mem stays as it is), then the AGC
# wraps + the lock in the title link (stage1/tools/apply_one_submitter.py)
rm -rf "$F/broker-onesub" && cp -r "$O/omni-gpupages-ls1b/broker-mem" "$F/broker-onesub" \
  && python3 "$S1/tools/apply_one_submitter.py" broker "$F/broker-onesub/server.cpp" > "$F/logs/apply_one_submitter_broker.log" 2>&1 || { st "one submitter (broker) FAILED: $(tail -1 "$F/logs/apply_one_submitter_broker.log")"; exit 1; }
OGP_BRK="$F/broker-onesub" python3 "$S1/tools/patch_title_build.py" "$NE/build.py" "$S1/src-title" > "$F/logs/patch-title-build.log" 2>&1 || { st "stage-1 title sources FAILED"; exit 1; }
python3 "$S1/tools/apply_one_submitter.py" build "$NE/build.py" "$S1/src-title" > "$F/logs/apply_one_submitter_build.log" 2>&1 || { st "one submitter (title link) FAILED: $(tail -1 "$F/logs/apply_one_submitter_build.log")"; exit 1; }
st "one submitter (broker; title link): $(tail -1 "$F/logs/apply_one_submitter_broker.log"); $(tail -1 "$F/logs/apply_one_submitter_build.log")"
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
