/* OMNI_GPU_ONE_SUBMITTER_V1: one process-wide lock around every AGC driver call of the title (see the header).
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Linked into the TITLE only, with --wrap=sceAgcDriverSubmitDcb,sceAgcSuspendPoint,sceAgcDriverSetTFRing,
 * sceAgcDriverSetHsOffchipParam,sceAgcInit (tools/apply_one_submitter.py build): __real_X is then the system import X,
 * and every reference to X in the title's objects and archives (the RADV archive's platform member, the broker) is a
 * reference to __wrap_X here. The import table does not change.
 *
 * Kept compilable as C and as C++ (the host test, tools/test_one_submitter.cpp, includes this text): GCC/Clang
 * __atomic builtins, no <stdatomic.h>, no thread_local (the title's TLS is emulated).
 *
 * Lock order: Mesa's queue submit_lock -> this; the broker's lock -> this. This lock is innermost: nothing here takes
 * another lock or waits on the GPU, and nobody waits on a fence while holding it. Hold time = the driver call (plus,
 * for the broker's bracket, its state sets and one SubmitDcb; its cache flush is made before the bracket). */
#include "omni_gpu_one_submitter.h"
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#ifdef __cplusplus
extern "C" {
#endif
struct ps5_agc_submit_description;
int32_t __real_sceAgcDriverSubmitDcb(struct ps5_agc_submit_description *description);
int32_t __real_sceAgcSuspendPoint(void);
int32_t __real_sceAgcDriverSetTFRing(uintptr_t address, uint32_t size);
int32_t __real_sceAgcDriverSetHsOffchipParam(uint32_t granularity, uint32_t buffering);
int32_t __real_sceAgcInit(uint32_t version);
#ifdef __cplusplus
}
#endif

#define OGS_HIDDEN __attribute__((visibility("hidden")))

static pthread_mutex_t ogs_mutex = PTHREAD_MUTEX_INITIALIZER;
/* The holder's id, 0 when free. Written only by the holder, read by anyone (relaxed): a thread compares it with its
 * own id, which only it can have stored. */
static uintptr_t ogs_owner;
/* Only the holder touches these (under ogs_mutex). */
static unsigned ogs_depth;
static int ogs_who;
static int ogs_last_submitter = -1;
static int ogs_first_said[2];
static uint64_t ogs_tf_address;
static uint32_t ogs_tf_size;
static int ogs_tf_who = -1;
static uint32_t ogs_oc_granularity, ogs_oc_buffering;
static int ogs_oc_who = -1;
static struct omni_gpu_one_submitter_stats ogs_stats;
static uint64_t ogs_next_wait_note[2] = {1, 1};
/* What to log once the lock is free again (bit 0 first submission, 1 waits, 2 conflict); written under the lock,
 * taken atomically by whoever leaves last. */
static unsigned ogs_pending;
static char ogs_note[160];

static uintptr_t ogs_self(void)
{
    pthread_t t = pthread_self();
    uintptr_t v = 0;
    memcpy(&v, &t, sizeof(t) < sizeof(v) ? sizeof(t) : sizeof(v));
    return v ? v : 1;
}

static uint64_t ogs_now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static const char *ogs_name(int who) { return who == OMNI_GPU_SUBMITTER_BROKER ? "broker" : "title"; }

static void ogs_say(void)
{
    char line[384];
    unsigned pending;
    pthread_mutex_lock(&ogs_mutex);
    pending = ogs_pending;
    ogs_pending = 0;
    snprintf(line, sizeof(line), "OMNI ONE SUBMITTER: %s | submits title=%llu broker=%llu switches=%llu waits title=%llu "
             "broker=%llu max_wait_us=%llu tf_conflicts=%llu offchip_conflicts=%llu\n", ogs_note,
             (unsigned long long)ogs_stats.submits[0], (unsigned long long)ogs_stats.submits[1],
             (unsigned long long)ogs_stats.switches, (unsigned long long)ogs_stats.waits[0],
             (unsigned long long)ogs_stats.waits[1], (unsigned long long)(ogs_stats.wait_ns_max / 1000),
             (unsigned long long)ogs_stats.tf_conflicts, (unsigned long long)ogs_stats.offchip_conflicts);
    pthread_mutex_unlock(&ogs_mutex);
    if (pending) {   /* outside the lock: a disk write never holds up a submission */
        fputs(line, stderr);
        fflush(stderr);
    }
}

static void ogs_note_set(unsigned bit, const char *text)
{
    ogs_pending |= bit;
    snprintf(ogs_note, sizeof(ogs_note), "%s", text);
}

OGS_HIDDEN void omni_gpu_one_submitter_enter(int who)
{
    const uintptr_t me = ogs_self();
    if (__atomic_load_n(&ogs_owner, __ATOMIC_RELAXED) == me) {
        ++ogs_depth;
        return;
    }
    if (pthread_mutex_trylock(&ogs_mutex) != 0) {
        const uint64_t t0 = ogs_now_ns();
        pthread_mutex_lock(&ogs_mutex);
        const uint64_t waited = ogs_now_ns() - t0;
        const int w = who == OMNI_GPU_SUBMITTER_BROKER;
        if (waited > ogs_stats.wait_ns_max) ogs_stats.wait_ns_max = waited;
        if (++ogs_stats.waits[w] == ogs_next_wait_note[w]) {
            ogs_next_wait_note[w] *= 10;
            char text[96];
            snprintf(text, sizeof(text), "%s waited for the other submitter (%llu times so far)", ogs_name(who),
                     (unsigned long long)ogs_stats.waits[w]);
            ogs_note_set(2, text);
        }
    }
    __atomic_store_n(&ogs_owner, me, __ATOMIC_RELAXED);
    ogs_depth = 1;
    ogs_who = who;
}

OGS_HIDDEN void omni_gpu_one_submitter_leave(void)
{
    if (--ogs_depth) return;
    const unsigned pending = ogs_pending;
    __atomic_store_n(&ogs_owner, (uintptr_t)0, __ATOMIC_RELAXED);
    pthread_mutex_unlock(&ogs_mutex);
    if (pending) ogs_say();
}

/* A wrapped call: inside a bracket it belongs to the bracket's submitter, otherwise to the title's RADV. */
static int ogs_take(void)
{
    if (__atomic_load_n(&ogs_owner, __ATOMIC_RELAXED) == ogs_self()) {
        ++ogs_depth;
        return ogs_who;
    }
    omni_gpu_one_submitter_enter(OMNI_GPU_SUBMITTER_TITLE);
    return OMNI_GPU_SUBMITTER_TITLE;
}

OGS_HIDDEN int omni_gpu_one_submitter_tf_is(uint64_t address, uint32_t size)
{
    ogs_take();
    const int same = ogs_tf_who >= 0 && ogs_tf_address == address && ogs_tf_size == size;
    omni_gpu_one_submitter_leave();
    return same;
}

OGS_HIDDEN int omni_gpu_one_submitter_offchip_is(uint32_t granularity, uint32_t buffering)
{
    ogs_take();
    const int same = ogs_oc_who >= 0 && ogs_oc_granularity == granularity && ogs_oc_buffering == buffering;
    omni_gpu_one_submitter_leave();
    return same;
}

OGS_HIDDEN void omni_gpu_one_submitter_stats(struct omni_gpu_one_submitter_stats *out)
{
    ogs_take();
    *out = ogs_stats;
    omni_gpu_one_submitter_leave();
}

OGS_HIDDEN int32_t __wrap_sceAgcDriverSubmitDcb(struct ps5_agc_submit_description *description)
{
    const int who = ogs_take();
    const int32_t result = __real_sceAgcDriverSubmitDcb(description);
    if (result == 0) {
        ++ogs_stats.submits[who];
        if (ogs_last_submitter >= 0 && ogs_last_submitter != who) ++ogs_stats.switches;
        ogs_last_submitter = who;
        if (!ogs_first_said[who]) {
            ogs_first_said[who] = 1;
            ogs_note_set(1, who == OMNI_GPU_SUBMITTER_BROKER ? "first submission from the broker (engine child work)"
                                                             : "first submission from the title's RADV");
        }
    }
    omni_gpu_one_submitter_leave();
    return result;
}

OGS_HIDDEN int32_t __wrap_sceAgcSuspendPoint(void)
{
    ogs_take();
    const int32_t result = __real_sceAgcSuspendPoint();
    omni_gpu_one_submitter_leave();
    return result;
}

OGS_HIDDEN int32_t __wrap_sceAgcDriverSetTFRing(uintptr_t address, uint32_t size)
{
    const int who = ogs_take();
    if (ogs_tf_who >= 0 && ogs_tf_who != who && (ogs_tf_address != (uint64_t)address || ogs_tf_size != size)) {
        /* The other submitter's work may still use the ring it set: a lock cannot fix that, so say it. */
        if (++ogs_stats.tf_conflicts <= 8) {
            char text[150];
            snprintf(text, sizeof(text), "CONFLICT: %s sets TF ring 0x%llx/%u over %s's 0x%llx/%u", ogs_name(who),
                     (unsigned long long)address, size, ogs_name(ogs_tf_who), (unsigned long long)ogs_tf_address,
                     ogs_tf_size);
            ogs_note_set(4, text);
        }
    }
    const int32_t result = __real_sceAgcDriverSetTFRing(address, size);
    if (result == 0) {
        ogs_tf_address = address;
        ogs_tf_size = size;
        ogs_tf_who = who;
    }
    omni_gpu_one_submitter_leave();
    return result;
}

OGS_HIDDEN int32_t __wrap_sceAgcDriverSetHsOffchipParam(uint32_t granularity, uint32_t buffering)
{
    const int who = ogs_take();
    if (ogs_oc_who >= 0 && ogs_oc_who != who && (ogs_oc_granularity != granularity || ogs_oc_buffering != buffering)) {
        if (++ogs_stats.offchip_conflicts <= 8) {
            char text[150];
            snprintf(text, sizeof(text), "CONFLICT: %s sets HS offchip %u/%u over %s's %u/%u", ogs_name(who), granularity,
                     buffering, ogs_name(ogs_oc_who), ogs_oc_granularity, ogs_oc_buffering);
            ogs_note_set(4, text);
        }
    }
    const int32_t result = __real_sceAgcDriverSetHsOffchipParam(granularity, buffering);
    if (result == 0) {
        ogs_oc_granularity = granularity;
        ogs_oc_buffering = buffering;
        ogs_oc_who = who;
    }
    omni_gpu_one_submitter_leave();
    return result;
}

OGS_HIDDEN int32_t __wrap_sceAgcInit(uint32_t version)
{
    ogs_take();
    const int32_t result = __real_sceAgcInit(version);
    omni_gpu_one_submitter_leave();
    return result;
}
