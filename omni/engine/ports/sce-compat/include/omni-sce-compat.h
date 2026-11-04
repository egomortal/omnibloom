/* Omni Engine: Sony-libc dialect shims for the homebrew ps5-payload-sdk libc.
 *
 * WebKit's PlayStation port is written against Sony's libc, which differs
 * from the FreeBSD-derived homebrew libc in a few signatures. This header is
 * force-included (-include) in every WebKit translation unit so upstream
 * sources stay unmodified. Each shim dispatches on argument count so both
 * the Sony and the FreeBSD/Linux call forms keep compiling.
 *
 * SPDX-License-Identifier: BSD-2-Clause
 */
#ifndef OMNI_SCE_COMPAT_H
#define OMNI_SCE_COMPAT_H
#if defined(__PROSPERO__)

#include <pthread.h>
#include <pthread_np.h>
#include <sys/types.h>
#include <sys/umtx.h>
#include <time.h>

#define OMNI_SEL2(_1, _2, NAME, ...) NAME
#define OMNI_SEL3(_1, _2, _3, NAME, ...) NAME

/* pthread_setname_np: Sony/Darwin (name) vs Linux (thread, name) */
static inline int omni_setname1(const char *name)
{
    pthread_set_name_np(pthread_self(), name);
    return 0;
}
static inline int omni_setname2(pthread_t t, const char *name)
{
    pthread_set_name_np(t, name);
    return 0;
}
#define pthread_setname_np(...) \
    OMNI_SEL2(__VA_ARGS__, omni_setname2, omni_setname1, _)(__VA_ARGS__)

/* pthread_get_name_np: Sony (thread, buf) returning int vs FreeBSD
 * (thread, buf, len) returning void. Sony's buffer is >= 32 bytes. */
static inline int omni_getname2(pthread_t t, char *buf)
{
    (pthread_get_name_np)(t, buf, 32);
    return 0;
}
static inline int omni_getname3(pthread_t t, char *buf, size_t len)
{
    (pthread_get_name_np)(t, buf, len);
    return 0;
}
#define pthread_get_name_np(...) \
    OMNI_SEL3(__VA_ARGS__, omni_getname3, omni_getname2, _, _)(__VA_ARGS__)

/* Sony clock_gettime_np == clock_gettime */
#define clock_gettime_np(clk, ts) clock_gettime((clk), (ts))

/* Sony's _umtx_op takes an extra trailing argument */
#define _umtx_op(obj, op, val, a1, a2, ...) (_umtx_op)((obj), (op), (val), (a1), (a2))

/* Sony socket option for non-blocking I/O. The PS5 kernel implements it; the
 * homebrew headers just lack the constant (value as in OpenOrbis headers). */
#include <sys/socket.h>
#ifndef SO_NBIO
#define SO_NBIO 0x1200
#endif

/* Sony getenv_np(name, buf, size): copy env value, 0 on success. */
#include <stdlib.h>
#include <string.h>
static inline int getenv_np(const char *name, char *buf, size_t size)
{
    const char *v = getenv(name);
    if (!v || !size)
        return -1;
    strncpy(buf, v, size - 1);
    buf[size - 1] = 0;
    return 0;
}

#endif /* __PROSPERO__ */
#endif
