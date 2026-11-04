// Omni Engine launcher: shared helpers (launch directory, clock).
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "omni-launcher.h"
#include "omni-rdup.h"

#include <process-launcher.h>

#include <stdio.h>
#include <stdlib.h>
#include <string>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <stdarg.h>

inline void omni_launcher_trace(const char* format, ...)
{
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    fflush(stderr);
#ifdef __PROSPERO__
    fsync(fileno(stderr));
#endif
}

std::string& omni_launcher_dir_ref();

inline const std::string& omni_launcher_dir()
{
    std::string& d = omni_launcher_dir_ref();
    if (d.empty()) {
        const char* env = getenv("OMNI_LAUNCH_DIR");
#ifdef __PROSPERO__
        d = env ? env : "/data/omni/run/launch";
#else
        d = env ? env : "/tmp/omni-launch";
#endif
    }
    return d;
}

inline void omni_launcher_dir_ensure()
{
    const std::string& d = omni_launcher_dir();
    for (size_t i = 1; i <= d.size(); i++) {
        if (i == d.size() || d[i] == '/')
            mkdir(d.substr(0, i).c_str(), 0777);
    }
}

inline double omni_now_ms()
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e3 + ts.tv_nsec / 1e6;
}
