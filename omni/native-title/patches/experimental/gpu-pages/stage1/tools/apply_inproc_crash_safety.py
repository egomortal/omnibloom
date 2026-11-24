#!/usr/bin/env python3
"""OMNI_INPROC_CRASH_SAFETY_V1 (2026-11-24): crash safety for the in-app page engine. Owner decision 2026-11-24 ("do 1
and 3"): (1) a page crash restarts Omni automatically and restores the tabs, with a small note; (3) a site that crashed
opens in the separate-process mode from then on.

With the WebProcess inside the title, a page crash ends the title. OmniCrash.h's fatal() released the hardware decoder
only for SIGILL/SIGABRT/SIGTRAP; memory faults re-raised WITHOUT the release, and exiting with the decoder held took the
console down once (2026-10-19). Only while an in-process role runs (omni_inproc_main_spin, weak: 0/absent otherwise):

OmniCrash.h fatal(), after the report, for every signal:
  - crash-loop guard: no restart if the last crash marker is younger than 60 s (normal exit as before),
  - marker /data/omni/run/inproc-crash.txt = "<epoch> <signal>" (raw open/write: signal-safe),
  - the decoder/audio release (beforeExit = omniHwReleaseOnCrash),
  - relaunch: the system sceSystemServiceLoadExec("/app0/eboot.bin") via the title's dlsym table; if it returns, the
    original path continues.
OmniBrowser.cpp omniEverydayStart() (tabs always come back from session.txt anyway):
  - a marker younger than 15 min -> the selected tab's site is added to /data/omni/inproc-unsafe-sites.txt, the
    notice says "A page crashed - Omni restarted and restored your tabs", and the marker becomes .seen (its time keeps
    feeding the loop guard),
  - restored tabs whose site is on that list open in an ISOLATED context: same data store (cookies, logins, storage),
    its own single web process, which the launcher starts as a child (only the first WebProcess runs in the title).
Limit (V1): a listed site opened later from the address bar or a link still uses the in-app engine.
usage: apply_inproc_crash_safety.py <tree root with engine/entry>"""
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_CRASH_SAFETY_V1'
root = Path(sys.argv[1])
out = []


def patch(rel, edits):
    p = root / rel
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    s = raw.replace('\r\n', '\n')
    if MARK in s:
        out.append('already ' + rel); return
    for old, new in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (rel, s.count(old), old[:70]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    out.append('applied ' + rel)


CRASH_HELPERS = r'''// OMNI_INPROC_CRASH_SAFETY_V1: restart Omni after a crash while the page engine runs in the title (signal-safe parts only)
extern "C" __attribute__((weak)) volatile int omni_inproc_main_spin;
static long omniCrashMarkerTime(const char* path)
{
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    char b[32];
    ssize_t n = read(fd, b, sizeof(b) - 1);
    close(fd);
    long v = 0;
    for (ssize_t i = 0; i < n && b[i] >= '0' && b[i] <= '9'; ++i) v = v * 10 + (b[i] - '0');
    return v;
}
static void omniCrashRestart(int signal)
{
    if (!&omni_inproc_main_spin || !omni_inproc_main_spin) return;   // not the in-app page engine: as before
    struct timespec ts {};
    clock_gettime(CLOCK_REALTIME, &ts);
    const long now = long(ts.tv_sec);
    const long last1 = omniCrashMarkerTime("/data/omni/run/inproc-crash.txt"), last2 = omniCrashMarkerTime("/data/omni/run/inproc-crash.seen");
    const long last = last1 > last2 ? last1 : last2;
    Line line;
    if (last && now - last < 60) { line.str("FATAL in-app engine crash again within 60 s: no automatic restart (loop guard)"); emit(line); return; }
    int fd = open("/data/omni/run/inproc-crash.txt", O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0666);
    if (fd >= 0) {
        char b[40]; char* p = b + sizeof(b); *--p = '\n';
        long s = signal; do { *--p = char('0' + s % 10); s /= 10; } while (s);
        *--p = ' ';
        long t = now; do { *--p = char('0' + t % 10); t /= 10; } while (t);
        (void)!write(fd, p, size_t(b + sizeof(b) - p));
        fsync(fd); close(fd);
    }
    if (void (*cleanup)() = beforeExit) { beforeExit = nullptr; cleanup(); }   // decoder + compute queue first
    using LoadExec = int (*)(const char*, const char**);
    LoadExec relaunch = reinterpret_cast<LoadExec>(dlsym(RTLD_DEFAULT, "sceSystemServiceLoadExec"));
    line.str("FATAL in-app engine crash: marker written, decoder released, relaunching Omni (" "OMNI_INPROC_CRASH_SAFETY_V1)"); emit(line);
    if (relaunch) relaunch("/app0/eboot.bin", nullptr);
    line.str("FATAL relaunch did not happen; leaving as before"); emit(line);
}
'''

patch('engine/entry/OmniCrash.h', [
    ('#include <pthread.h>\n', '#include <pthread.h>\n#include <time.h>   // ' + MARK + '\n'),
    ('static void fatal(int signal, siginfo_t* info, void* context)\n{\n',
     CRASH_HELPERS + 'static void fatal(int signal, siginfo_t* info, void* context)\n{\n'),
    ('    reporting = 1;\n    report(signal, info, context);\n',
     '    reporting = 1;\n    report(signal, info, context);\n    omniCrashRestart(signal);   // ' + MARK + ': returns only when no restart happens\n'),
])

BROWSER_HELPERS = r'''// OMNI_INPROC_CRASH_SAFETY_V1: crashed sites run in their own (child) web process; see tools/apply_inproc_crash_safety.py
static WKRetainPtr<WKContextRef> omniIsolatedContext;
static std::vector<std::string> omniUnsafeSites;
static uint32_t omniCrashTestExitAt = 0;   // TEST ONLY: set when the crash test's relaunch starts
static void omniUnsafeSitesLoad()
{
    omniUnsafeSites.clear();
    if (FILE* f = fopen("/data/omni/inproc-unsafe-sites.txt", "r")) {
        char line[512];
        while (fgets(line, sizeof(line), f)) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' ')) s.pop_back();
            if (!s.empty()) omniUnsafeSites.push_back(s);
        }
        fclose(f);
    }
}
static bool omniUnsafeSite(const std::string& url)
{
    const std::string host = omniBlockerHostOf(url);
    if (host.empty()) return false;
    for (auto& h : omniUnsafeSites) if (h == host) return true;
    return false;
}
static Tab* omniCrashSafeNewTab(const std::string& url)
{
    if (url == "newtab" || !omniUnsafeSite(url)) return newTab();
    if (!omniIsolatedContext) {
        auto cconfig = adoptWK(WKContextConfigurationCreate());
        WKContextConfigurationSetUserId(cconfig.get(), -1);
        omniIsolatedContext = adoptWK(WKContextCreateWithConfiguration(cconfig.get()));
        WKContextSetPrimaryWebsiteDataStore(omniIsolatedContext.get(), websiteDataStore.get());   // same cookies, logins, storage
        WKContextSetUsesSingleWebProcess(omniIsolatedContext.get(), true);
        log("crash safety: isolated web process for sites that crashed in the app (OMNI_INPROC_CRASH_SAFETY_V1)");
    }
    auto config = adoptWK(WKPageConfigurationCreate());
    WKPageConfigurationSetContext(config.get(), omniIsolatedContext.get());
    WKPageConfigurationSetPreferences(config.get(), preferences.get());
    WKPageConfigurationSetWebsiteDataStore(config.get(), websiteDataStore.get());
    return newTab(config.get());
}
static bool omniCrashRestartNotice()   // true once after an automatic restart; records the crashed site
{
    long when = 0;
    if (FILE* f = fopen("/data/omni/run/inproc-crash.txt", "r")) { if (fscanf(f, "%ld", &when) != 1) when = 0; fclose(f); }
    else return false;
    rename("/data/omni/run/inproc-crash.txt", "/data/omni/run/inproc-crash.seen");   // its time keeps the loop guard
    const long now = long(time(nullptr));
    return when && now - when < 15 * 60;
}
static void omniUnsafeSiteAdd(const std::string& url)
{
    const std::string host = omniBlockerHostOf(url);
    if (host.empty() || omniUnsafeSite(url)) return;
    if (FILE* f = fopen("/data/omni/inproc-unsafe-sites.txt", "a")) { fprintf(f, "%s\n", host.c_str()); fclose(f); }
    omniUnsafeSites.push_back(host);
    log(("crash safety: " + host + " will open in its own web process from now on").c_str());
}
'''

patch('engine/entry/OmniBrowser.cpp', [
    ('static bool omniEverydayStart()\n{\n',
     BROWSER_HELPERS + 'static bool omniEverydayStart()\n{\n'),
    ('    if (saved.empty()) saved.emplace_back("newtab", "New tab");\n    omniF3Restoring = true;   // OMNI_FEATURES_V3_FIX1\n',
     '    if (saved.empty()) saved.emplace_back("newtab", "New tab");\n'
     '    omniUnsafeSitesLoad();   // ' + MARK + '\n'
     '    const bool omniCrashed = omniCrashRestartNotice();\n'
     '    if (omniCrashed) omniUnsafeSiteAdd(saved[size_t(std::clamp(sel, 0, int(saved.size()) - 1))].first);\n'
     '    omniF3Restoring = true;   // OMNI_FEATURES_V3_FIX1\n'),
    # the build's OmniBrowser.cpp (after the feature patches; OMNI_PW_LOCK_V1 holds a blank tab behind the start PIN)
    ('        if (!tab) tab = newTab();\n',
     '        if (!tab) tab = omniCrashSafeNewTab(url);   // ' + MARK + '\n'),
    ('    if (saved.size() > 1 || saved[0].first != "newtab") notice(',
     '    if (omniCrashed) notice("A page crashed - Omni restarted and restored your tabs");   // ' + MARK + '\n'
     '    if (omniCrashed && !access("/data/omni/run/crashtest-relaunch", F_OK)) {   // TEST ONLY: the crash test\'s relaunch closes itself\n'
     '        unlink("/data/omni/run/crashtest-relaunch");\n'
     '        omniCrashTestExitAt = SDL_GetTicks() + 90000;\n'
     '        log("crash safety: crash-test relaunch, closing by itself in 90 s");\n'
     '    }\n'
     '    else if (saved.size() > 1 || saved[0].first != "newtab") notice('),
    ('static void omniEverydayTick()\n{\n',
     'static void omniEverydayTick()\n{\n'
     '    if (omniCrashTestExitAt && SDL_GetTicks() >= omniCrashTestExitAt) { omniCrashTestExitAt = 0; log("crash safety: crash-test relaunch closing"); running = false; }   // ' + MARK + '\n'),
])
print('\n'.join(out))
print('applied' if any(o.startswith('applied') for o in out) else 'already')
