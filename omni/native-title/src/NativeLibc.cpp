// omni-native-s0: libc functions the payload SDK's static libc.a gave Omni and that no system
// module (and no SDK platform ps5_ function) provides to a title. Explicit, minimal versions;
// all names are kept local to the title (build.py's local map). SPDX-License-Identifier: GPL-3.0-or-later
#include <cerrno>
#include <cstdio>
#include <ctime>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/filio.h>
#include <unistd.h>
extern "C" void omni_native_log(const char*, ...);
extern "C" int __mb_cur_max;
extern "C" {
// WTF::calculateLocalTimeOffset (DateMath.cpp). Days-from-civil (proleptic Gregorian), then
// gmtime_r (bound to the SDK platform's ps5_gmtime_r) normalises *tm as timegm does.
time_t timegm(struct tm* t)
{
    long long y = t->tm_year + 1900LL, m = t->tm_mon;
    y += m / 12; m %= 12; if (m < 0) { m += 12; --y; }
    long long yy = y - (m < 2);
    const long long era = (yy >= 0 ? yy : yy - 399) / 400;
    const unsigned yoe = unsigned(yy - era * 400);
    const unsigned mp = unsigned((m + 10) % 12); // March = 0
    const unsigned doy = (153 * mp + 2) / 5;
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    const long long days = era * 146097 + (long long)doe - 719468 + (t->tm_mday - 1);
    time_t r = time_t(days * 86400LL + t->tm_hour * 3600LL + t->tm_min * 60LL + t->tm_sec);
    gmtime_r(&r, t);
    return r;
}
// libiconv: MB_CUR_MAX is ___mb_cur_max() in FreeBSD's headers; the system libc exports the value.
int ___mb_cur_max(void) { return __mb_cur_max; }
// OpenSSL's ASYNC fibres (libcrypto async.c) only; Omni (curl) never starts an ASYNC job.
int _setjmp(void*) { return 0; }
[[noreturn]] void _longjmp(void*, int) { omni_native_log("libc: _longjmp called (OpenSSL ASYNC fibre): not available in the title"); abort(); }
unsigned int if_nametoindex(const char*) { errno = ENXIO; return 0; }
int mkostemp(char* path, int flags)
{
    int fd = mkstemps(path, 0); // the SDK platform's ps5_mkstemps (RADV link recipe)
    if (fd >= 0 && (flags & O_CLOEXEC)) fcntl(fd, F_SETFD, FD_CLOEXEC);
    return fd;
}
// fcntl(F_SETFL) is refused in a title (EACCES, PS5-HOMEBREW-PLATFORM-NOTES section 23): O_NONBLOCK
// falls back to ioctl(FIONBIO); if both are refused the call fails (no silently blocking pipe).
int pipe2(int fds[2], int flags)
{
    if (pipe(fds)) return -1;
    for (int i = 0; i < 2; ++i) {
        if (flags & O_CLOEXEC) fcntl(fds[i], F_SETFD, FD_CLOEXEC);
        if (flags & O_NONBLOCK) {
            int fl = fcntl(fds[i], F_GETFL);
            if (fl < 0 || fcntl(fds[i], F_SETFL, fl | O_NONBLOCK) < 0) {
                int on = 1, e = errno;
                if (ioctl(fds[i], FIONBIO, &on) < 0) {
                    static int logged = 0;
                    if (logged++ < 4) omni_native_log("libc: pipe2 O_NONBLOCK refused (fcntl errno %d, ioctl errno %d)", e, errno);
                    int saved = errno; close(fds[0]); close(fds[1]); errno = saved; return -1;
                }
            }
        }
    }
    return 0;
}
}

// ------------------------------------------------------------------------------------------------
// Imports whose only SDK stub provider is libScePosixForWebKit / libkernel_sys. Those stubs give a
// title null imports for some names (RADV link recipe notes: strcasestr, mkstemp, readlink; Ex-Box
// Q7d/Q8: isatty, mkstemp). These are linked with --wrap: the system export is looked up in the
// loaded modules (sceKernelGetModuleList + sceKernelDlsym, as dlsym() does), else a local fallback.
#include <arpa/inet.h>
#include <fnmatch.h>
#include <netdb.h>
#include <netinet/in.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/socket.h>
extern "C" void* dlsym(void*, const char*);
namespace {
template<typename F> F optionalExport(const char* name)
{
    static_assert(sizeof(F) == sizeof(void*));
    void* p = dlsym(nullptr, name);
    F f; memcpy(&f, &p, sizeof f); return f;
}
// fnmatch without FNM_ flags beyond the basics: '*', '?', '[...]' (with '!'/'^' and ranges), '\\'.
bool globMatch(const char* p, const char* s)
{
    for (; *p; ++p, ++s) {
        if (*p == '*') { while (*p == '*') ++p; if (!*p) return true; for (; *s; ++s) if (globMatch(p, s)) return true; return false; }
        if (!*s) return false;
        if (*p == '?') continue;
        if (*p == '[') {
            const char* q = p + 1; bool neg = (*q == '!' || *q == '^'); if (neg) ++q;
            bool hit = false; bool first = true;
            for (; *q && (*q != ']' || first); ++q, first = false) {
                if (q[1] == '-' && q[2] && q[2] != ']') { if (*s >= *q && *s <= q[2]) hit = true; q += 2; }
                else if (*q == *s) hit = true;
            }
            if (*q != ']') { if (*s != '[') return false; continue; }
            if (hit == neg) return false;
            p = q; continue;
        }
        if (*p == '\\' && p[1]) ++p;
        if (*p != *s) return false;
    }
    return !*s;
}
}
extern "C" {
int __wrap_isatty(int fd)
{
    static auto f = optionalExport<int (*)(int)>("isatty");
    if (f) return f(fd);
    errno = ENOTTY; return 0;
}
int __wrap_mkstemp(char* path) { return mkstemps(path, 0); } // ps5_mkstemps
int __wrap_fstatfs(int fd, struct statfs* out)
{
    static auto f = optionalExport<int (*)(int, struct statfs*)>("fstatfs");
    if (f) return f(fd, out);
    errno = ENOSYS; return -1;
}
int __wrap_fnmatch(const char* pattern, const char* string, int flags)
{
    static auto f = optionalExport<int (*)(const char*, const char*, int)>("fnmatch");
    if (f) return f(pattern, string, flags);
    return globMatch(pattern, string) ? 0 : FNM_NOMATCH;
}
const char* __wrap_gai_strerror(int code)
{
    static auto f = optionalExport<const char* (*)(int)>("gai_strerror");
    if (f) return f(code);
    static char text[48]; snprintf(text, sizeof text, "name resolution error %d", code); return text;
}
int __wrap_getnameinfo(const struct sockaddr* sa, socklen_t salen, char* host, socklen_t hostlen, char* serv, socklen_t servlen, int flags)
{
    static auto f = optionalExport<int (*)(const struct sockaddr*, socklen_t, char*, socklen_t, char*, socklen_t, int)>("getnameinfo");
    if (f) return f(sa, salen, host, hostlen, serv, servlen, flags);
    // Numeric answers only (what curl asks for); names are not resolved here.
    if (!sa) return EAI_FAIL;
    const void* addr = nullptr; unsigned port = 0;
    if (sa->sa_family == AF_INET) { auto* in = reinterpret_cast<const sockaddr_in*>(sa); addr = &in->sin_addr; port = ntohs(in->sin_port); }
    else if (sa->sa_family == AF_INET6) { auto* in6 = reinterpret_cast<const sockaddr_in6*>(sa); addr = &in6->sin6_addr; port = ntohs(in6->sin6_port); }
    else return EAI_FAMILY;
    if (host && hostlen) { if (!(flags & NI_NUMERICHOST) && (flags & NI_NAMEREQD)) return EAI_NONAME; if (!inet_ntop(sa->sa_family, addr, host, hostlen)) return EAI_OVERFLOW; }
    if (serv && servlen) { if (snprintf(serv, servlen, "%u", port) >= int(servlen)) return EAI_OVERFLOW; }
    return 0;
}
}
