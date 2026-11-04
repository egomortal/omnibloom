// Platform shims for the hardware decode service/client (PS5 vs Linux host tests).
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "../ports/webkit-requirements/src/omni-rdup.h" // omni_remote_dup()
#include <cstdlib>
#include <fcntl.h>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#ifndef __PROSPERO__
#include <sys/syscall.h>
#endif

namespace OmniMedia::Hw {

// Anonymous shared memory that another process can map after duplicating the fd.
inline int shmCreate(size_t size)
{
#ifdef __PROSPERO__
    int fd = shm_open(SHM_ANON, O_RDWR | O_CREAT | O_CLOEXEC, 0600);
#else
    int fd = int(syscall(SYS_memfd_create, "omni-hw", 1 /* MFD_CLOEXEC */));
#endif
    if (fd < 0) return -1;
    if (ftruncate(fd, off_t(size))) { close(fd); return -1; }
    return fd;
}

inline std::string rendezvousDir()
{
    if (const char* env = getenv("OMNI_HW_DIR")) return env;
#ifdef __PROSPERO__
    return "/data/omni/run/hwdec";
#else
    return "/tmp/omni-hwdec";
#endif
}

// Hardware decode is opt-in until it has passed console testing.
inline bool flagEnabled()
{
    if (const char* env = getenv("OMNI_HW_DECODE")) return env[0] == '1';
#ifdef __PROSPERO__
    return !access("/data/omni/hw-decode.flag", F_OK);
#else
    return false;
#endif
}

// OMNI_HOLEPUNCH_V1: video shown under the page by the shell. On by default on the console;
// the kill switch is /data/omni/holepunch-disabled.flag. Host tests opt in with OMNI_HOLEPUNCH=1.
inline bool holePunchFlagEnabled()
{
    if (const char* env = getenv("OMNI_HOLEPUNCH")) return env[0] == '1';
#ifdef __PROSPERO__
    return access("/data/omni/holepunch-disabled.flag", F_OK) != 0;
#else
    return false;
#endif
}

// OMNI_HOLEPUNCH_V4: the shell paces hole-punched video itself (frames queued with their
// timestamps, shown per vblank by the playback clock). Kill switch, back to the V3 per-tick
// presents: /data/omni/holepunch-pacing-disabled.flag. Host tests: OMNI_HOLEPUNCH_PACING=0.
inline bool holePacingFlagEnabled()
{
    if (const char* env = getenv("OMNI_HOLEPUNCH_PACING")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/holepunch-pacing-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}

// OMNI_HOLEPUNCH_V5: playback that survives 2-3 s main-thread stalls (deep input ring while
// paced, a decoded queue by memory budget in direct memory, a 3 s audio ring, a playhead not
// clamped to 0.25 s per tick). Kill switch, back to V4: /data/omni/holepunch-v5-disabled.flag.
// Host tests: OMNI_HOLEPUNCH_V5=0.
inline bool holeV5FlagEnabled()
{
    if (const char* env = getenv("OMNI_HOLEPUNCH_V5")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/holepunch-v5-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}

inline double nowMs()
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e3 + ts.tv_nsec / 1e6;
}

inline void ensureDir(const std::string& d)
{
    for (size_t i = 1; i <= d.size(); i++)
        if (i == d.size() || d[i] == '/') mkdir(d.substr(0, i).c_str(), 0777);
}

}
