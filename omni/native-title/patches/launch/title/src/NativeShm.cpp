// Native-title shared memory without descriptor duplication (OMNI_NATIVE_SHM_V1).
// Included by NativeLauncherState.cpp; linked with --wrap=shm_open --wrap=close (build-native.py).
//
// Why (console, 2026-10-20, native UI PID 144): WebKit's SharedMemory::createHandle duplicates
// its descriptor (WTF::dupCloseOnExec -> dup) for every handle it sends to another process
// (first: VisitedLinkStore::sendStoreHandleToProcess). Inside the title, dup of that
// descriptor (an anonymous shm object: shm_open(SHM_ANON), fstat type "file", mode 0600)
// fails with EPERM, F_DUPFD with EINVAL, dup2 with EPERM.
//
// What this does, only in the native UI executable: an anonymous shm_open becomes a named
// object (/omni-ui-shm.<pid>.<n>). When dup() of such a descriptor fails, the same object is
// opened again by name, which gives a new descriptor for the same memory with no duplication.
// The name is removed (shm_unlink) when the last of its descriptors in this process closes,
// like an anonymous object; descriptors already handed to other processes and existing
// mappings stay valid (POSIX unlink semantics). Named shm failing falls back to SHM_ANON.
// SPDX-License-Identifier: GPL-3.0-or-later
#include <atomic>
#include <errno.h>
#include <fcntl.h>
#include <initializer_list>
#include <mutex>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <unistd.h>

extern "C" int __real_shm_open(const char*, int, mode_t);
extern "C" int __real_close(int);
extern "C" int __real_dup(int);

namespace {
struct OmniShmEntry { int fd; int name; };      // name: index into names, -1 = free
struct OmniShmName { char path[48]; int refs; };
constexpr int kOmniShmSlots = 4096, kOmniShmNames = 2048; // WebKit allocates shared memory per update
std::mutex omniShmLock;
OmniShmEntry omniShmFds[kOmniShmSlots];
OmniShmName omniShmNames[kOmniShmNames];
std::atomic<int> omniShmLive { 0 };              // descriptors tracked (fast path for close)
std::atomic<unsigned> omniShmSerial { 0 };
bool omniShmInitialized = false;
int omniShmLogs = 0, omniShmFallbacks = 0;

void omniShmInit()
{
    if (omniShmInitialized) return;
    for (auto& e : omniShmFds) { e.fd = -1; e.name = -1; }
    for (auto& n : omniShmNames) { n.path[0] = 0; n.refs = 0; }
    omniShmInitialized = true;
}

bool omniShmTrack(int fd, int name)   // lock held
{
    for (auto& e : omniShmFds) if (e.fd < 0) { e.fd = fd; e.name = name; omniShmNames[name].refs++; omniShmLive++; return true; }
    return false;
}

int omniShmNameOf(int fd)             // lock held
{
    for (auto& e : omniShmFds) if (e.fd == fd) return e.name;
    return -1;
}
}

extern "C" int __wrap_shm_open(const char* path, int flags, mode_t mode)
{
    if (path != SHM_ANON) return __real_shm_open(path, flags, mode);
    std::lock_guard<std::mutex> lock(omniShmLock);
    omniShmInit();
    int slot = -1;
    for (int i = 0; i < kOmniShmNames; ++i) if (!omniShmNames[i].path[0]) { slot = i; break; }
    if (slot >= 0) {
        OmniShmName& n = omniShmNames[slot];
        snprintf(n.path, sizeof(n.path), "/omni-ui-shm.%d.%u", static_cast<int>(getpid()), omniShmSerial++);
        int fd = __real_shm_open(n.path, (flags | O_CREAT | O_EXCL) & ~O_TRUNC, mode ? mode : 0600);
        if (fd >= 0 && omniShmTrack(fd, slot)) {
            if (omniShmLogs++ < 4) { fprintf(stderr, "native shm: anonymous object created as %s fd=%d\n", n.path, fd); fflush(stderr); }
            return fd;
        }
        int saved = errno;
        if (fd >= 0) { __real_close(fd); shm_unlink(n.path); }
        if (omniShmFallbacks++ < 4 || !(omniShmFallbacks % 1000)) { fprintf(stderr, "native shm: named object %s failed (errno %d); using SHM_ANON\n", n.path, saved); fflush(stderr); }
        n.path[0] = 0; n.refs = 0;
    }
    return __real_shm_open(SHM_ANON, flags, mode);
}

// dup() for a tracked shm descriptor: open the same object again by name.
static int omniShmReopen(int fd)
{
    std::lock_guard<std::mutex> lock(omniShmLock);
    if (!omniShmInitialized) return -2;
    int name = omniShmNameOf(fd);
    if (name < 0) return -2;
    int copy = __real_shm_open(omniShmNames[name].path, O_RDWR, 0);
    if (copy < 0) return -1;
    if (!omniShmTrack(copy, name)) { __real_close(copy); errno = EMFILE; return -1; }
    return copy;
}

extern "C" int __wrap_close(int fd)
{
    if (omniShmLive.load(std::memory_order_relaxed) > 0) {
        std::lock_guard<std::mutex> lock(omniShmLock);
        for (auto& e : omniShmFds) {
            if (e.fd != fd) continue;
            OmniShmName& n = omniShmNames[e.name];
            e.fd = -1; e.name = -1; omniShmLive--;
            if (--n.refs == 0) { shm_unlink(n.path); n.path[0] = 0; }
            break;
        }
    }
    return __real_close(fd);
}

// One-time check, logged at the first dup(): which descriptor kinds the title can duplicate.
static void omniShmProbeDup()
{
    static bool done = false;
    if (done) return;
    done = true;
    int pair[2] = { -1, -1 };
    int sp = socketpair(AF_UNIX, SOCK_STREAM, 0, pair);
    int sd = sp ? -1 : __real_dup(pair[0]); int se = errno;
    int anon = __real_shm_open(SHM_ANON, O_CREAT | O_RDWR, 0600);
    int ad = anon < 0 ? -1 : __real_dup(anon); int ae = errno;
    char name[48]; snprintf(name, sizeof(name), "/omni-ui-probe.%d", static_cast<int>(getpid()));
    int named = __real_shm_open(name, O_CREAT | O_EXCL | O_RDWR, 0600); int ne = errno;
    int again = named < 0 ? -1 : __real_shm_open(name, O_RDWR, 0); int re = errno;
    fprintf(stderr, "native shm probe: socket dup=%d (errno %d); SHM_ANON fd=%d dup=%d (errno %d); named open=%d (errno %d) reopen=%d (errno %d)\n",
        sd, sd < 0 ? se : 0, anon, ad, ad < 0 ? ae : 0, named, named < 0 ? ne : 0, again, again < 0 ? re : 0);
    fflush(stderr);
    for (int fd : { sd, ad, anon, again, named, pair[0], pair[1] }) if (fd >= 0) __real_close(fd);
    if (named >= 0) shm_unlink(name);
}
