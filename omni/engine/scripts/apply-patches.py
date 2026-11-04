#!/usr/bin/env python3
"""Apply Omni Engine's homebrew changes to a WebKit checkout.

Upstream's PlayStation port targets Sony's official SDK. The homebrew
ps5-payload-sdk differs in a few places; every change is guarded by the CMake
variable OMNI_HOMEBREW so the upstream behaviour is untouched when it's unset.

Idempotent: running it twice is a no-op.
SPDX-License-Identifier: BSD-2-Clause
"""
import pathlib
import sys

MARK = "# [omni-homebrew]"


def patch(path: pathlib.Path, edits):
    text = path.read_text()
    if "[omni-homebrew]" in text:
        print(f"  already patched: {path}")
        return
    for old, new in edits:
        if old not in text:
            sys.exit(f"patch anchor not found in {path}:\n{old}")
        text = text.replace(old, new, 1)
    path.write_text(text)
    print(f"  patched: {path}")


def main(root: str):
    wk = pathlib.Path(root)
    # Open stand-ins for Sony SDK CMake modules (WebKit resets CMAKE_MODULE_PATH).
    here = pathlib.Path(__file__).resolve().parent.parent / "cmake"
    for mod in ("PlayStationModule.cmake", "Sign.cmake"):
        dst = wk / "Source/cmake" / mod
        dst.write_text((here / mod).read_text())
        print(f"  installed: {dst}")
    opts = wk / "Source/cmake/OptionsPlayStation.cmake"
    patch(opts, [
        (
            "# Set the standard libary version\n"
            "WEBKIT_PREPEND_GLOBAL_COMPILER_FLAGS(-sce-stdlib=v2)\n",
            f"{MARK} Sony-SDK-only compiler flag\n"
            "if (NOT OMNI_HOMEBREW)\n"
            "# Set the standard libary version\n"
            "WEBKIT_PREPEND_GLOBAL_COMPILER_FLAGS(-sce-stdlib=v2)\n"
            "endif ()\n",
        ),
        (
            "if (ENABLE_STATIC_JSC)\n    set(JavaScriptCore_LIBRARY_TYPE OBJECT)\n",
            "if (ENABLE_STATIC_JSC AND OMNI_HOMEBREW)\n"
            "    # static archive: pulls in LowLevelInterpreterLib objects without the\n"
            "    # $<TARGET_OBJECTS> genex that CMake can't propagate through OBJECT libs\n"
            "    set(JavaScriptCore_LIBRARY_TYPE STATIC)\n"
            "elseif (ENABLE_STATIC_JSC)\n    set(JavaScriptCore_LIBRARY_TYPE OBJECT)\n",
        ),
        (
            "set(WebKit_LIBRARY_TYPE SHARED)\n",
            "# Homebrew links everything statically into each process executable.\n"
            "if (OMNI_HOMEBREW)\n"
            "    set(WebKit_LIBRARY_TYPE OBJECT)\n"
            "else ()\n"
            "    set(WebKit_LIBRARY_TYPE SHARED)\n"
            "endif ()\n",
        ),
        (
            "function(add_executable target)\n"
            "    _add_executable(${ARGV})\n"
            "    target_link_options(${target} PRIVATE \"LINKER:--wrap=mmap\")\n"
            "endfunction()\n",
            "# Sony wraps mmap for memory accounting; the homebrew libc has no\n"
            "# __wrap_mmap, so only do it with the official SDK.\n"
            "function(add_executable target)\n"
            "    _add_executable(${ARGV})\n"
            "    if (NOT OMNI_HOMEBREW)\n"
            "        target_link_options(${target} PRIVATE \"LINKER:--wrap=mmap\")\n"
            "    endif ()\n"
            "endfunction()\n",
        ),
        (
            "    if (\"${type}\" STREQUAL \"SHARED\")\n"
            "        target_link_options(${target} PRIVATE \"LINKER:--wrap=mmap\")\n",
            "    if (\"${type}\" STREQUAL \"SHARED\" AND NOT OMNI_HOMEBREW)\n"
            "        target_link_options(${target} PRIVATE \"LINKER:--wrap=mmap\")\n",
        ),
        (
            "    add_dependencies(${_target} playstation_tools_copy)\n",
            "    if (NOT OMNI_HOMEBREW)\n"
            "        add_dependencies(${_target} playstation_tools_copy)\n"
            "    endif ()\n",
        ),
    ])
    shell = wk / "Source/JavaScriptCore/shell/PlatformPlayStation.cmake"
    patch(shell, [
        (
            "list(REMOVE_ITEM jsc_SOURCES ../jsc.cpp)\n",
            f"{MARK} homebrew: stock jsc.cpp main(), no Sony test harness\n"
            "if (NOT OMNI_HOMEBREW)\n"
            "list(REMOVE_ITEM jsc_SOURCES ../jsc.cpp)\n",
        ),
        (
            "    list(APPEND jsc_LIBRARIES ${LIBTESTWRAPPERS})\nendif ()\n",
            "    list(APPEND jsc_LIBRARIES ${LIBTESTWRAPPERS})\nendif ()\n"
            "endif () # OMNI_HOMEBREW\n",
        ),
    ])
    # Homebrew: our own child-process entry points (no Sony module dlopen chain).
    entry = pathlib.Path(__file__).resolve().parent.parent / "entry" / "OmniChildProcessMain.cpp"
    wkp0 = wk / "Source/WebKit/PlatformPlayStation.cmake"
    t = wkp0.read_text()
    if "[omni-homebrew] entry points" not in t:
        for proc, sony in (("WebProcess", "WebProcess/EntryPoint/playstation/WebProcessMain.cpp"),
                           ("NetworkProcess", "NetworkProcess/EntryPoint/playstation/NetworkProcessMain.cpp"),
                           ("GPUProcess", "GPUProcess/EntryPoint/playstation/GPUProcessMain.cpp")):
            define = {"WebProcess": "OMNI_PROCESS_WEB", "NetworkProcess": "OMNI_PROCESS_NETWORK",
                      "GPUProcess": "OMNI_PROCESS_GPU"}[proc]
            # top-level libraries only: their sub-targets' objects come along
            objs = " ".join(("WebCore", "PAL", "JavaScriptCore", "WTF", "bmalloc", "Skia"))
            t += (f"\n# [omni-homebrew] entry points: {proc}\n"
                  "if (OMNI_HOMEBREW)\n"
                  f"    list(REMOVE_ITEM {proc}_SOURCES {sony})\n"
                  f"    list(APPEND {proc}_SOURCES {entry})\n"
                  f"    list(APPEND {proc}_DEFINITIONS {define})\n"
                  "    # OBJECT libraries only contribute objects when linked directly\n"
                  f"    list(APPEND {proc}_PRIVATE_LIBRARIES {objs})\n"
                  "endif ()\n")
        wkp0.write_text(t)
        print(f"  patched: {wkp0} (entry points)")

    # Include Omni's recovered multi-process page-rendering test.
    wkc = wk / "Source/WebKit/CMakeLists.txt"
    text = wkc.read_text()
    if "[omni-homebrew] OmniEngine" not in text:
        text += ("\n# [omni-homebrew] OmniEngine multi-call ELF\n"
                 "if (OMNI_HOMEBREW AND OMNI_ENGINE_DIR)\n"
                 "    include(${OMNI_ENGINE_DIR}/cmake/OmniEngine.cmake)\n"
                 "endif ()\n")
        wkc.write_text(text)

    # Upstream filename case bug (harmless on Sony's case-insensitive Windows
    # build hosts, fatal on Linux): WKRunloop -> WKRunLoop.
    wkp = wk / "Source/WebKit/PlatformPlayStation.cmake"
    if wkp.exists():
        t = wkp.read_text()
        if "playstation/WKRunloop." in t:
            wkp.write_text(t.replace("playstation/WKRunloop.", "playstation/WKRunLoop."))
            print(f"  patched: {wkp} (WKRunLoop case)")
    # Upstream bug: with PLAYSTATION + COORDINATED_GRAPHICS the SkiaGLContext
    # class and s_skiaGLContext are compiled out, but six accessors below still
    # use them. Give them their "no GPU context" behaviour in that config.
    pds = wk / "Source/WebCore/platform/graphics/skia/PlatformDisplaySkia.cpp"
    if pds.exists():
        cond = "#if !(PLATFORM(PLAYSTATION) && USE(COORDINATED_GRAPHICS))"
        patch(pds, [
            (
                "void PlatformDisplay::setSkiaGLContextForCurrentThread(",
                "// [omni-homebrew] accessors need a fallback when SkiaGLContext is compiled out\n"
                f"{cond}\n"
                "void PlatformDisplay::setSkiaGLContextForCurrentThread(",
            ),
            (
                "void PlatformDisplay::clearSkiaGLContext()\n{\n    s_skiaGLContext = nullptr;\n}\n",
                "void PlatformDisplay::clearSkiaGLContext()\n{\n    s_skiaGLContext = nullptr;\n}\n"
                "#else\n"
                "void PlatformDisplay::setSkiaGLContextForCurrentThread(std::unique_ptr<GLContext>&&) { }\n"
                "GrDirectContext* PlatformDisplay::skiaGrContext() const { return nullptr; }\n"
                "unsigned PlatformDisplay::msaaSampleCount() const { return 0; }\n"
                "size_t PlatformDisplay::maxSkiaResourceCacheBytes() const { return 0; }\n"
                "void PlatformDisplay::skiaReleaseUnusedResources(WTF::Critical) { }\n"
                "void PlatformDisplay::clearSkiaGLContext() { }\n"
                "#endif\n",
            ),
        ])
    # Upstream bug: Page.cpp reads Settings::hardwareAccelerationEnabled() for
    # every Skia port except Win, but the preference only exists for GTK/WPE.
    page = wk / "Source/WebCore/page/Page.cpp"
    if page.exists():
        patch(page, [(
            "#if USE(SKIA) && !PLATFORM(WIN) && (!PLATFORM(WPE) || ENABLE(WPE_PLATFORM))\n"
            "    if (settings().hardwareAccelerationEnabled())",
            "// [omni-homebrew] preference does not exist on PlayStation\n"
            "#if USE(SKIA) && !PLATFORM(WIN) && !PLATFORM(PLAYSTATION) && (!PLATFORM(WPE) || ENABLE(WPE_PLATFORM))\n"
            "    if (settings().hardwareAccelerationEnabled())",
        )])
    # Upstream bitrot: SkiaPaintingEngine::create() now takes the GPU context;
    # PlayStation paints on the CPU, which is create(nullptr) (as LayerTreeHost.cpp does).
    lth = wk / "Source/WebKit/WebProcess/WebPage/CoordinatedGraphics/LayerTreeHostPlayStation.cpp"
    if lth.exists():
        patch(lth, [(
            "    , m_skiaPaintingEngine(SkiaPaintingEngine::create())\n",
            "    , m_skiaPaintingEngine(SkiaPaintingEngine::create(nullptr)) // [omni-homebrew] CPU painting\n",
        )])

    # Content extensions were never built for PlayStation upstream: make the
    # Latin-1 span -> NetworkCache::Data conversion unambiguous (as the UTF-16 branch does).
    crl = wk / "Source/WebKit/UIProcess/API/APIContentRuleListStore.cpp"
    if crl.exists():
        patch(crl, [(
            "writeToFile(WebKit::NetworkCache::Data(sourceJSON.span8()));",
            "writeToFile(WebKit::NetworkCache::Data(asBytes(sourceJSON.span8()))); // [omni-homebrew]",
        )])


    # Report pthread failures in release builds; LOG_ERROR is compiled out.
    threading = wk / "Source/WTF/wtf/posix/ThreadingPOSIX.cpp"
    if threading.exists() and '[omni-thread-diagnostic]' not in threading.read_text():
        patch(threading, [(
            "    int error = pthread_create(&threadHandle, &attr, wtfThreadEntryPoint, &context);\n",
            "    size_t omniStackSize = 0;\n"
            "    pthread_attr_getstacksize(&attr, &omniStackSize);\n"
            "    int error = pthread_create(&threadHandle, &attr, wtfThreadEntryPoint, &context);\n"
            "    if (error) { fprintf(stderr, \"omni pthread_create failed: error=%d stack=%zu\\n\", error, omniStackSize); fflush(stderr); fsync(fileno(stderr)); } // [omni-thread-diagnostic]\n",
        )])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "webkit")
