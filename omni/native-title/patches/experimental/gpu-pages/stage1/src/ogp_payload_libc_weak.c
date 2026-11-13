/* omni-gpu-pages stage 1 copy: every stand-in WEAK (a real definition wins; never a duplicate).
 * omni-gpu-pages stage 2: the few libc/compiler-runtime pieces the PAYLOAD SDK does not have but
 * Mesa references. The native-title SDK has them (libSceLibcInternal), so this file is linked only
 * into the CP-2 loader-child client. Each stand-in logs once if it is reached, so a console run says
 * whether anything needed it.
 * SPDX-License-Identifier: MIT */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void ogp_hit(const char *name)
{
    static const char *seen[8]; int i;
    for (i = 0; i < 8 && seen[i]; i++) if (seen[i] == name) return;
    if (i < 8) seen[i] = name;
    fprintf(stderr, "ogp: payload libc stand-in reached: %s\n", name);
}

/* open_memstream: Mesa writes shader disassembly and other debug text into one. The payload SDK's
 * libc has neither open_memstream nor funopen/fopencookie, so there is no way to make a real one
 * without a FILE implementation of our own. Every Mesa caller is a debug or log path, and each
 * checks for NULL, so this reports failure and says so once. */
__attribute__((weak)) FILE *open_memstream(char **bufp, size_t *sizep)
{
    ogp_hit("open_memstream");
    if (bufp) *bufp = NULL;
    if (sizep) *sizep = 0;
    errno = ENOSYS;
    return NULL;
}

#ifndef OGP_HAVE_BUILTINS
/* compiler-rt's CPU feature table, which __builtin_cpu_supports reads. The payload SDK link does
 * not pull in libclang_rt.builtins, and Mesa chooses its SSE4.1 paths with its own CPUID code
 * (util/u_cpu_detect.c), not this. Layout is compiler-rt's struct __processor_model; all zero means
 * "no feature detected", which is the safe answer. Replaced by the real archive when the build
 * finds it (-DOGP_HAVE_BUILTINS). */
struct ogp_processor_model {
    unsigned int vendor, type, subtype, features[1];
} __cpu_model __attribute__((weak)) = { 0, 0, 0, { 0 } };
unsigned int __cpu_features2[4] __attribute__((weak)) = { 0, 0, 0, 0 };
#endif
