// Omni Engine: multi-call entry point. One ELF plays every WebKit role:
//   no launcher ticket  -> UI process (Omni engine test for now)
//   ticket ".../NetworkProcess" -> WebKit NetworkProcess
//   ticket ".../WebProcess"     -> WebKit WebProcess
// SPDX-License-Identifier: GPL-3.0-or-later
#include "config.h"
#include "NetworkProcessMain.h"
#include "WebProcessMain.h"

#include "OmniResources.h"
#include "OmniCrash.h"
#if ENABLE(MEDIA_SOURCE)
#include "../media/OmniHwPlatform.h"
#include "../media/OmniHwService.h"
#endif
#include "../media/OmniHwPlatform.h" // OMNI_AUDIO_RELAY_V1: rendezvousDir (also without MSE)
#include "../media/OmniAudioRelay.h"
#include <dlfcn.h>

#include <omni-launcher.h>
#include <process-launcher.h>
#include <stdio.h>
#include <string>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <unistd.h>
#include <fcntl.h>    // OMNI_ASYNC_LOG_V1
#include <pthread.h>
#include <errno.h>
#include <fontconfig/fontconfig.h>
#include <dirent.h> // OMNI_EXTRA_FONTS_V1
#include <cctype>

// Keep the production link intact while bypassing WebKit initialization during
// an explicitly selected startup-only hardware diagnostic.
#define OMNI_ISOLATION_EMBEDDED
#include "../selftest/launcher_isolation.cpp"
#undef OMNI_ISOLATION_EMBEDDED
// OMNI_PERF_D_T1: the parent side of the launcher, with early spares, is compiled here (see that file:
// it replaces the libWebKitRequirements.a member process-launcher.o, which omni_build.py cannot rebuild).
#include "../ports/webkit-requirements/src/omni-process-launcher-v2.inc"

int omniEngineTestMain(const char* outDir);
int omniBrowserMain();
int omniTimerTreeSelfTest();
#if ENABLE(MEDIA_SOURCE)
namespace WebCore { void omniInstallMediaCapabilities(); } // OMNI_MEDIACAPS_V1 (OmniMSEPlayer.cpp)
#endif

#ifdef __PROSPERO__
typedef struct {
    char useless1[45];
    char message[3075];
} omni_notify_request_t;
extern "C" int sceKernelSendNotificationRequest(int, omni_notify_request_t*, size_t, int);
void omniNotify(const char* msg)
{
    omni_notify_request_t req;
    memset(&req, 0, sizeof(req));
    snprintf(req.message, sizeof(req.message), "%s", msg);
    sceKernelSendNotificationRequest(0, &req, sizeof(req), 0);
}
static const char* const kOutDir = "/data/omni";
static const char* const kSelf[] = { "/data/omni/omni-engine.elf", nullptr };
#else
void omniNotify(const char* msg) { fprintf(stderr, "[notify] %s\n", msg); }
static const char* const kOutDir = "/tmp/omni-engine-out";
static const char* const kSelf[] = { "/proc/self/exe", nullptr };
#endif

static void setResourceEnv()
{
    static const std::string conf = std::string(kOutDir) + "/fonts.conf";
    static const std::string ca = std::string(kOutDir) + "/cacert.pem";
    setenv("FONTCONFIG_FILE", conf.c_str(), 1);
    setenv("OMNI_CA_BUNDLE", ca.c_str(), 1);
}

static bool initializeBundledFonts()
{
    // Register our known font files before WebKit creates its font manager.
    // This avoids depending on a previously populated directory cache.
    FcConfig* fonts = FcConfigCreate();
    if (!fonts) return false;
    static const char aliases[] =
        "<fontconfig>"
        // OMNI_EXTRA_FONTS_V1: CJK and emoji fallbacks after DejaVu (used only when installed in fonts/extra)
        "<alias><family>sans-serif</family><prefer><family>DejaVu Sans</family><family>Noto Sans JP</family><family>Noto Sans SC</family><family>Noto Sans KR</family><family>Noto Color Emoji</family></prefer></alias>"
        "<alias><family>system-ui</family><prefer><family>DejaVu Sans</family><family>Noto Sans JP</family><family>Noto Sans SC</family><family>Noto Sans KR</family><family>Noto Color Emoji</family></prefer></alias>"
        "<alias><family>serif</family><prefer><family>DejaVu Serif</family><family>Noto Sans JP</family><family>Noto Sans SC</family><family>Noto Sans KR</family><family>Noto Color Emoji</family></prefer></alias>"
        "<alias><family>monospace</family><prefer><family>DejaVu Sans Mono</family><family>Noto Sans JP</family><family>Noto Sans SC</family><family>Noto Sans KR</family><family>Noto Color Emoji</family></prefer></alias>"
        "<alias><family>emoji</family><prefer><family>Noto Color Emoji</family></prefer></alias>"
        "</fontconfig>";
    if (!FcConfigParseAndLoadFromMemory(fonts, reinterpret_cast<const FcChar8*>(aliases), FcTrue)) {
        FcConfigDestroy(fonts);
        return false;
    }
    unsigned added = 0;
    for (const char* name : { "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSerif.ttf", "DejaVuSansMono.ttf" }) {
        std::string path = std::string(kOutDir) + "/fonts/" + name;
        if (FcConfigAppFontAddFile(fonts, reinterpret_cast<const FcChar8*>(path.c_str()))) ++added;
        else omni_launcher_trace("font registration failed: %s\n", path.c_str());
    }
    // OMNI_EXTRA_FONTS_V1: optional extra fonts (CJK, emoji, ...) in <out>/fonts/extra; the four
    // DejaVu fonts above stay required. Fontconfig picks these as fallbacks by glyph coverage.
    unsigned extra = 0;
    const std::string extraDir = std::string(kOutDir) + "/fonts/extra";
    if (DIR* dir = opendir(extraDir.c_str())) {
        while (dirent* entry = readdir(dir)) {
            std::string name = entry->d_name;
            auto dot = name.rfind('.');
            std::string ext = dot == std::string::npos ? "" : name.substr(dot);
            for (auto& c : ext) c = char(tolower(static_cast<unsigned char>(c)));
            if (ext != ".ttf" && ext != ".otf" && ext != ".ttc") continue;
            std::string path = extraDir + "/" + name;
            if (FcConfigAppFontAddFile(fonts, reinterpret_cast<const FcChar8*>(path.c_str()))) ++extra;
            else omni_launcher_trace("extra font registration failed: %s\n", path.c_str());
        }
        closedir(dir);
    }
    bool ready = added == 4 && FcConfigSetCurrent(fonts);
    omni_launcher_trace("bundled fonts: registered=%u extra=%u ready=%d\n", added, extra, ready);
    FcConfigDestroy(fonts);
    return ready;
}

static int runChild(int argc, char** args)
{
    setResourceEnv();
    char connection[16];
    snprintf(connection, sizeof(connection), "%d", PlayStation::getConnectionIdentifier());
    char program[] = "omni";
    char* internalArgv[] = { program, argc > 1 ? args[1] : program, connection, nullptr };
    if (!access("/data/omni/crash-diagnostics.flag", F_OK))
        OmniCrash::install(reinterpret_cast<const void*>(&runChild));
    if (strstr(args[0], "NetworkProcess"))
        return WebKit::NetworkProcessMain(3, internalArgv);
    if (!initializeBundledFonts()) return 1;
    // Painting threads for WebKit's Skia CPU painting (WebKit reads
    // WEBKIT_SKIA_CPU_PAINTING_THREADS, 1..8; default half the cores). Optional
    // /data/omni/paint-threads.txt sets it so it can be tuned without a rebuild.
    if (FILE* f = fopen("/data/omni/paint-threads.txt", "r")) {
        int threads = 0;
        if (fscanf(f, "%d", &threads) == 1 && threads >= 1 && threads <= 8) {
            char value[4];
            snprintf(value, sizeof(value), "%d", threads);
            setenv("WEBKIT_SKIA_CPU_PAINTING_THREADS", value, 1);
        }
        fclose(f);
    }
    fprintf(stderr, "paint threads: setting=%s cores-online=%ld\n",
        getenv("WEBKIT_SKIA_CPU_PAINTING_THREADS") ? getenv("WEBKIT_SKIA_CPU_PAINTING_THREADS") : "default",
        sysconf(_SC_NPROCESSORS_ONLN));
    // OMNI_THREADED_RASTER_V1: optional /data/omni/raster-env.txt, one KEY=VALUE per line, sets
    // OMNI_RASTER_* settings for the page process's threaded raster (only OMNI_RASTER_ keys).
    if (FILE* f = fopen("/data/omni/raster-env.txt", "r")) {
        char line[128];
        while (fgets(line, sizeof(line), f)) {
            char* end = line + strcspn(line, "\r\n"); *end = 0;
            char* eq = strchr(line, '=');
            if (!eq || strncmp(line, "OMNI_RASTER_", 12)) continue;
            *eq = 0; setenv(line, eq + 1, 1);
            fprintf(stderr, "raster setting: %s=%s\n", line, eq + 1);
        }
        fclose(f);
    }
    // OMNI_JSC_ENV_V1: optional /data/omni/jsc-env.txt, one JSC_<option>=VALUE per line, for
    // JavaScriptCore options (garbage collector tuning). Only JSC_ keys, at most 32 lines;
    // JSC reads them from the environment when it initialises. Remove the file to undo.
    if (FILE* f = fopen("/data/omni/jsc-env.txt", "r")) {
        char line[160];
        int count = 0;
        while (count < 32 && fgets(line, sizeof(line), f)) {
            char* end = line + strcspn(line, "\r\n"); *end = 0;
            char* eq = strchr(line, '=');
            if (!eq || strncmp(line, "JSC_", 4) || eq == line + 4) continue;
            *eq = 0; setenv(line, eq + 1, 1); ++count;
            fprintf(stderr, "jsc setting: %s=%s\n", line, eq + 1);
        }
        fclose(f);
    }
    // OMNI_JSC_JIT_V1: this engine is built with JavaScriptCore's JIT (baseline + regular expressions; no DFG/FTL,
    // no WebAssembly JIT tiers). It runs only when /data/omni/jsc-jit.flag exists (setting "JavaScript JIT", off by
    // default); otherwise the interpreter only, as before. Decided here, after jsc-env.txt, so that file can't turn it on.
    if (!access("/data/omni/jsc-jit.flag", F_OK)) {
        setenv("JSC_useJIT", "true", 1);
        setenv("JSC_useBaselineJIT", "true", 1);
        setenv("JSC_useRegExpJIT", "true", 1);
        setenv("JSC_useDFGJIT", "false", 1);
        setenv("JSC_useFTLJIT", "false", 1);
        setenv("JSC_useBBQJIT", "false", 1);
        setenv("JSC_useOMGJIT", "false", 1);
        setenv("JSC_jitMemoryReservationSize", "67108864", 1);   // 64 MB executable pool (OSAllocatorPlayStation caps it at 256 MB)
        fprintf(stderr, "jit: on (baseline + regexp, 64 MB pool, pages flip RX<->RWX while writing code)\n");
    } else {
        setenv("JSC_useJIT", "false", 1);
        setenv("JSC_useRegExpJIT", "false", 1);
        fprintf(stderr, "jit: off (interpreter)\n");
    }
#if ENABLE(MEDIA_SOURCE)
    // OMNI_MEDIACAPS_V1: decodingInfo factory, installed before any page can ask.
    WebCore::omniInstallMediaCapabilities();
#endif
    return WebKit::WebProcessMain(3, internalArgv);
}

#if defined(__PROSPERO__) && ENABLE(MEDIA_SOURCE)
// The browser leaves through sceSystemServiceLoadExec("exit") (OmniBrowser.cpp).
// Exiting while the hardware decoder still held decoders and its compute queue
// took the whole console down (2026-10-19), so this definition, which the
// executable's own calls bind to, releases them first (EVO does the same
// teardown) and then calls the system function.
extern "C" int sceSystemServiceLoadExec(const char* path, const char** argv)
{
    OmniMedia::Hw::serviceShutdownForExit(2000, false);
    OmniMedia::Audio::relayStop(); // OMNI_AUDIO_RELAY_V1 (after the shell's SDL_Quit: no SDL call then)
    using Real = int (*)(const char*, const char**);
    static Real real = nullptr;
    if (!real) {
        if (void* module = dlopen("libSceSystemService.sprx", RTLD_LAZY))
            real = reinterpret_cast<Real>(dlsym(module, "sceSystemServiceLoadExec"));
        if (real == &sceSystemServiceLoadExec) real = nullptr;
    }
    if (!real) { fprintf(stderr, "exit: system LoadExec not found\n"); return -1; }
    return real(path, argv);
}

static void omniHwReleaseOnCrash() { OmniMedia::Hw::serviceShutdownForExit(300, true); }

// The system closing the app (PS button) or another launch replacing it can
// arrive as a termination signal. Release the decoder first, then let the signal
// do what it would have done (EVO saw a kernel panic when an app was killed with
// GPU work in flight). SA_RESETHAND: the re-raised signal takes the default path.
static void omniHwReleaseOnTerm(int signal)
{
    OmniMedia::Hw::serviceShutdownForExit(500, true);
    raise(signal);
}
#endif

// OMNI_ASYNC_LOG_V1: each process's stderr went straight to its log file on /data, unbuffered, and one line cost ~95 ms there
// (measured: a logged main-loop gap made the next tick 95 ms longer; the web process's OMNI DRAW line every 30 frames
// matched the 165 ms scroll stalls every ~640 ms). stderr now goes into a pipe; a writer thread copies it to the same file.
// /data/omni/log-sync.flag restores direct writes (for crash debugging: lines still in the pipe are lost if a process dies).
static int omniLogFile = -1, omniLogPipe = -1;
static void* omniLogWriter(void*)
{
    static char buffer[32768];
    for (;;) {
        const ssize_t n = read(omniLogPipe, buffer, sizeof buffer);
        if (n > 0) { for (ssize_t done = 0; done < n;) { const ssize_t w = write(omniLogFile, buffer + done, size_t(n - done)); if (w <= 0) { if (errno == EINTR) continue; break; } done += w; } }
        else if (n == 0 || errno != EINTR) break;
    }
    return nullptr;
}
static bool omniAsyncLog(const char* path)
{
    if (!access("/data/omni/log-sync.flag", F_OK)) return false;
    const int file = open(path, O_WRONLY | O_CREAT | O_APPEND, 0666);
    int ends[2];
    if (file < 0) return false;
    if (pipe(ends)) { close(file); return false; }
    fflush(stderr);
    // OMNI_ASYNC_LOG_V2: these processes start without standard streams, so freopen() may have put stderr on another
    // descriptor than 2 (V1 replaced descriptor 2 and stderr kept writing to the file directly).
    const int err = fileno(stderr);
    if (err < 0 || dup2(ends[1], err) < 0) { close(file); close(ends[0]); close(ends[1]); return false; }
    close(ends[1]);
    omniLogFile = file; omniLogPipe = ends[0];
    pthread_t writer;
    if (pthread_create(&writer, nullptr, omniLogWriter, nullptr)) {   // no writer: back to the file directly
        dup2(file, err); close(ends[0]); omniLogPipe = -1; return false;
    }
    pthread_detach(writer);
    return true;
}

int main(int, char**)
{
#ifdef __PROSPERO__
    if (!access("/data/omni/startup-only.flag", F_OK))
        return omniStartupIsolation();
    mkdir(kOutDir, 0777);
    char diagnosticPath[160];
    snprintf(diagnosticPath, sizeof(diagnosticPath), "%s/process-%d.log", kOutDir, (int)getpid());
    freopen(diagnosticPath, "a", stderr);
    fprintf(stderr, "log: stderr on descriptor %d, %s\n", fileno(stderr), omniAsyncLog(diagnosticPath) ? "background writer" : "direct");   // OMNI_ASYNC_LOG_V1/V2
    setvbuf(stderr, nullptr, _IONBF, 0);
    omni_launcher_trace("Omni diagnostic build: pid=%d entering bootstrap\n", (int)getpid());
    for (int resource : { RLIMIT_DATA, RLIMIT_AS, RLIMIT_STACK }) {
        struct rlimit limit {};
        if (!getrlimit(resource, &limit))
            omni_launcher_trace("resource limit: kind=%d soft=%llu hard=%llu\n", resource,
                static_cast<unsigned long long>(limit.rlim_cur), static_cast<unsigned long long>(limit.rlim_max));
    }
#endif
    // OMNI_JSC_JIT_V1: no process uses the JIT unless runChild() turns it on for a web process.
    setenv("JSC_useJIT", "false", 1);
    setenv("JSC_useRegExpJIT", "false", 1);
    char* args[16];
    int argc = 0;
    int role = omni_child_bootstrap(args, 16, &argc);
    omni_launcher_trace("bootstrap role=%d argc=%d connection=%d\n", role, argc, PlayStation::getConnectionIdentifier());
    for (int i = 0; i < argc; ++i)
        omni_launcher_trace("argument[%d]=%s\n", i, args[i]);
    if (role == OMNI_ROLE_CHILD && argc >= 2) {
        // OMNI_CHILD_LOG_OFF_V1 (diagnostic): /data/omni/child-log-off.flag sends the web and network processes' stderr to
        // /dev/null (tests whether their periodic log lines cause the 165 ms scroll stall every 30 frames).
        if (!access("/data/omni/child-log-off.flag", F_OK)) { fflush(stderr); const int null = open("/dev/null", O_WRONLY); if (null >= 0) { dup2(null, fileno(stderr)); close(null); } }
        return runChild(argc, args);
    }
    if (role != OMNI_ROLE_FIRST)
        return 1;

    // UI process
    // OMNI_PERF_D_T1: start the first WebProcess and NetworkProcess now, so the ELF loader works while
    // the shell starts (audio, decoder service, SDL, fonts, content rules) instead of while WebKit
    // waits for them on the UI thread (1.6-3.3 s frozen UI at every start). Browser mode only;
    // /data/omni/prespawn-disabled.flag restores the old behaviour.
    if (!access("/data/omni/browser-mode.flag", F_OK) && access("/data/omni/tls-selftest.flag", F_OK)
        && access("/data/omni/timer-tree-selftest.flag", F_OK) && access("/data/omni/prespawn-disabled.flag", F_OK)) {
        struct stat self {};
        for (int i = 0; kSelf[i]; i++) {
            if (!stat(kSelf[i], &self)) {
                setenv("OMNI_SELF_PATH", kSelf[i], 1);
                omni_launcher_prespawn(kSelf[i], 2);
                break;
            }
        }
    }
    // OMNI_AUDIO_RELAY_V1: every page's audio is played here (the system drops what a WebProcess's
    // own audio device plays). Opened now, on the main thread, before the shell's SDL calls; the
    // players fall back to their own output while it is off (audio-relay-disabled.flag) or absent.
    unlink((OmniMedia::Hw::rendezvousDir() + "/audio").c_str());
    if (OmniMedia::Audio::relayFlagEnabled()) {
        std::string detail;
        bool ok = OmniMedia::Audio::relayStart(detail);
        omni_launcher_trace("audio relay: %s (%s)\n", ok ? "running" : "unavailable", detail.c_str());
    }
#if ENABLE(MEDIA_SOURCE)
    // Hardware video decoding (docs/HW-DECODE-INTEGRATION-PLAN.md). The decoder
    // must live here: WebProcesses are ELF-loader processes with ~48 MiB of
    // direct memory. Start it before anything else allocates; a rendezvous file
    // left by an earlier run is removed first so WebProcesses never wait on it.
    unlink((OmniMedia::Hw::rendezvousDir() + "/service").c_str());
    if (OmniMedia::Hw::flagEnabled()) {
        std::string detail;
        bool ok = OmniMedia::Hw::serviceStart(detail);
        omni_launcher_trace("hardware decode service: %s (%s)\n", ok ? "running" : "unavailable", detail.c_str());
    }
#endif
    if (!access("/data/omni/crash-diagnostics.flag", F_OK))
        OmniCrash::install(reinterpret_cast<const void*>(&main));
#if defined(__PROSPERO__) && ENABLE(MEDIA_SOURCE)
    OmniCrash::beforeExit = omniHwReleaseOnCrash;
    {
        struct sigaction term {};
        sigemptyset(&term.sa_mask);
        term.sa_handler = omniHwReleaseOnTerm;
        term.sa_flags = SA_RESETHAND;
        for (int signal : { SIGTERM, SIGHUP, SIGINT }) sigaction(signal, &term, nullptr);
    }
#endif
    if (!access("/data/omni/timer-tree-selftest.flag", F_OK))
        return omniTimerTreeSelfTest();
    struct stat st;
    for (int i = 0; kSelf[i]; i++) {
        if (!stat(kSelf[i], &st)) {
            setenv("OMNI_SELF_PATH", kSelf[i], 1);
            break;
        }
    }
    if (!getenv("OMNI_SELF_PATH")) {
        omniNotify("Omni Engine: upload omni-engine.elf to /data/omni first");
        return 1;
    }
    int missing = omniInstallResources(kOutDir);
    setResourceEnv();
    char msg[128];
    snprintf(msg, sizeof(msg), "Omni Engine: starting WebKit (%s)", missing ? "resources incomplete" : "ready");
    omniNotify(msg);
    if (!access("/data/omni/browser-mode.flag", F_OK) && access("/data/omni/tls-selftest.flag", F_OK)) {
        return omniBrowserMain();
    }
    return omniEngineTestMain(kOutDir);
}
