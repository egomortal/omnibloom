// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <fcntl.h>
#include <sys/ioctl.h>
inline bool omniSocketNonBlocking(int fd)
{
    const int flags = fcntl(fd, F_GETFL, 0);
    if (flags >= 0 && fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0) return true;
    int enabled = 1;
    return ioctl(fd, FIONBIO, &enabled) == 0;
}
