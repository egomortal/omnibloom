# Omni Engine: multi-call ELF (UI + WebProcess + NetworkProcess in one binary).
# Included at the end of Source/WebKit/CMakeLists.txt when OMNI_HOMEBREW is ON.
# SPDX-License-Identifier: GPL-3.0-or-later
set(_omni "${OMNI_ENGINE_DIR}")
if (USE_WPE_RENDERER OR USE_WPE_BACKEND_PLAYSTATION)
    message(FATAL_ERROR "OmniEngine currently requires the non-WPE-renderer PlayStation view path")
endif ()
# Keep the largest compilation units bounded even when lighter targets build
# with more parallel jobs. WebCore's unified sources can consume several GiB.
set(OMNI_WEBCORE_JOBS "2" CACHE STRING "Maximum parallel WebCore compilations")
set_property(GLOBAL APPEND PROPERTY JOB_POOLS omni_webcore=${OMNI_WEBCORE_JOBS})
set_property(TARGET WebCore PROPERTY JOB_POOL_COMPILE omni_webcore)

set(OmniEngine_SOURCES
    ${_omni}/entry/OmniMain.cpp
    ${_omni}/entry/OmniEngineSetup.cpp
    ${_omni}/entry/OmniEngineFlow.cpp
    ${_omni}/entry/OmniPng.cpp
    ${_omni}/entry/OmniResources.cpp
    ${_omni}/entry/OmniWpePlatform.cpp
    ${_omni}/entry/OmniLazyGraphics.cpp
    ${_omni}/entry/OmniBrowser.cpp
    ${_omni}/entry/OmniBlocker.cpp
    ${_omni}/entry/OmniUBlock.cpp
    ${_omni}/entry/OmniMediaPlayer.cpp
    ${_omni}/media/OmniVideoDecoder.cpp
    ${_omni}/media/OmniProgressive.cpp # OMNI_PROGRESSIVE_V1
    ${_omni}/entry/OmniProgressivePlayer.cpp
    ${_omni}/media/OmniAudioRelay.cpp # OMNI_AUDIO_RELAY_V1
    ${_omni}/selftest/timer_tree_test.cpp
)
set(OmniEngine_PRIVATE_INCLUDE_DIRECTORIES
    $<TARGET_PROPERTY:WebKit,INCLUDE_DIRECTORIES>
    ${_omni}/entry
)
if (ENABLE_MEDIA_SOURCE)
    list(APPEND OmniEngine_SOURCES
        ${_omni}/entry/OmniMSEPlayer.cpp
        ${_omni}/entry/OmniMSESource.cpp
        ${_omni}/entry/OmniMediaSample.cpp
        ${_omni}/media/OmniMP4SegmentBuffer.cpp
        ${_omni}/media/OmniMP4Demuxer.cpp
        ${_omni}/media/OmniWebMDemuxer.cpp # OMNI_WEBM_V1
        ${_omni}/media/OmniHlsPlaylist.cpp # OMNI_HLS_NATIVE_V1
        ${_omni}/media/OmniHlsSegment.cpp
        ${_omni}/media/OmniHlsSession.cpp
        ${_omni}/entry/OmniHlsPlayer.cpp
        ${_omni}/media/OmniPacketDecoder.cpp
        ${_omni}/media/OmniHwBitstream.cpp
        ${_omni}/media/OmniHwBackend.cpp
        ${_omni}/media/OmniHwService.cpp
        ${_omni}/media/OmniHwClient.cpp
    )
endif ()
set(OMNI_SDL_LIBRARY "SDL2" CACHE STRING "SDL library; isolated display builds may supply an absolute archive path")
set(OmniEngine_PRIVATE_LIBRARIES
    WebKit WebCore PAL JavaScriptCore WTF bmalloc Skia
    ${ProcessLauncher_LIBRARY}
    PNG::PNG sharpyuv
    SDL2_ttf ${OMNI_SDL_LIBRARY} freetype harfbuzz samplerate iconv
    avformat avcodec swscale swresample avutil x264 lzma bz2 ssl crypto
    SceSystemService SceSysmodule SceUserService ScePad SceAudioOut SceVideoOut SceKeyboard SceImeDialog
)
set(OmniEngine_DEFINITIONS OMNI_RES_DIR=${_omni}/resources)

WEBKIT_EXECUTABLE_DECLARE(OmniEngine)
WEBKIT_EXECUTABLE(OmniEngine)
target_link_options(OmniEngine PRIVATE "LINKER:--as-needed")
if (ENABLE_MEDIA_SOURCE)
    # Diagnostic-only forwarding wrapper; production MSE-off link is unchanged.
    target_link_options(OmniEngine PRIVATE "LINKER:--wrap=sceAudioOutInit")
endif ()
option(OMNI_CHECKED_PTR_TRACE "Trace checked-pointer assertion callers before the original crash" OFF)
if (OMNI_CHECKED_PTR_TRACE)
    target_sources(OmniEngine PRIVATE ${_omni}/entry/OmniCheckedPtrTrace.cpp)
    target_link_options(OmniEngine PRIVATE "LINKER:--wrap=_ZN3WTF21CanMakeCheckedPtrBaseINSt3__16atomicIjEEjNS2_IbEELNS_30CheckedPtrDeleteCheckExceptionE0EE32crashDueToCheckedPtrToDeadObjectEv")
endif ()
# .incbin reads these at assembly time: rebuild when they change
set_source_files_properties(${_omni}/entry/OmniResources.cpp PROPERTIES OBJECT_DEPENDS
    "${_omni}/resources/cacert.pem;${_omni}/resources/fonts.conf;${_omni}/resources/DejaVuSans.ttf;${_omni}/resources/DejaVuSans-Bold.ttf;${_omni}/resources/DejaVuSerif.ttf;${_omni}/resources/DejaVuSansMono.ttf")
