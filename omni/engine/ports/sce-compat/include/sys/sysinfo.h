/* Omni Engine: minimal Linux-style <sys/sysinfo.h> for the PS5 homebrew libc.
 * WTF only needs totalram * mem_unit. SPDX-License-Identifier: BSD-2-Clause */
#ifndef OMNI_SYS_SYSINFO_H
#define OMNI_SYS_SYSINFO_H
#include <stddef.h>
#include <string.h>
#include <sys/types.h>
#include <sys/sysctl.h>

struct sysinfo {
    unsigned long totalram;
    unsigned long freeram;
    unsigned int mem_unit;
};

static inline int sysinfo(struct sysinfo *info)
{
    unsigned long mem = 0;
    size_t len = sizeof(mem);
    memset(info, 0, sizeof(*info));
    if (sysctlbyname("hw.physmem", &mem, &len, NULL, 0) || !mem)
        mem = 4UL << 30; /* conservative fallback: 4 GiB */
    info->totalram = mem;
    info->freeram = mem / 2;
    info->mem_unit = 1;
    return 0;
}
#endif
