/* OMNI_GPU_ONE_SUBMITTER_V1 (2026-11-16): ONE submitter at the AGC driver level in the title process.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Why: with layers on, the title has two GPU submitters that knew nothing of each other: the gpu-broker owner
 * (broker-mem/server.cpp: client threads under the broker's lock -> broker_submit -> sceAgcDriverSubmitDcb, kick() ->
 * sceAgcSuspendPoint, radv_ps5_set_tess_factor_ring / radv_ps5_set_hs_offchip_param) and the title's own RADV
 * (the pinned archive libvulkan_radeon-hdr-wsi.a, winsys_ps5_radv_ps5_platform.c.o: radv_ps5_submit ->
 * sceAgcDriverSubmitDcb under ITS queue lock only, its kick thread -> sceAgcSuspendPoint with no lock, and
 * sceAgcDriverSetTFRing / sceAgcDriverSetHsOffchipParam / sceAgcInit). The PS5 winsys orders work only inside one
 * Mesa instance and has no concurrent-queue support.
 *
 * How: the title link wraps the five AGC driver functions (--wrap=sceAgc..., tools/apply_one_submitter.py build), so
 * EVERY call in the title (the RADV archive's and the broker's alike) goes through omni_gpu_one_submitter.c, which
 * holds one process-wide recursive mutex around the driver call only (never around a fence wait or a cache flush).
 * The broker additionally brackets "set shared state, then submit" (enter/leave) so no other submitter can change
 * the tessellation ring between the two, and asks the process-wide state (tf_is/offchip_is) rather than its own
 * memory of it. The engine child links its own Mesa with the broker CLIENT (no AGC import): it never takes this lock.
 */
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { OMNI_GPU_SUBMITTER_TITLE = 0, OMNI_GPU_SUBMITTER_BROKER = 1 };

/* Recursive: a thread that holds it may take it again (the broker's bracket, then the wrapped driver calls). Driver
 * calls made inside a bracket count as the bracket's submitter; calls outside any bracket count as the title's. */
void omni_gpu_one_submitter_enter(int who);
void omni_gpu_one_submitter_leave(void);

/* 1 when the process-wide value, as last set successfully through the wraps by anyone, is this one. */
int omni_gpu_one_submitter_tf_is(uint64_t address, uint32_t size);
int omni_gpu_one_submitter_offchip_is(uint32_t granularity, uint32_t buffering);

struct omni_gpu_one_submitter_stats {
    uint64_t submits[2];        /* sceAgcDriverSubmitDcb by title / broker */
    uint64_t waits[2];          /* times a thread of that submitter found the lock held by another thread */
    uint64_t wait_ns_max;       /* the longest such wait */
    uint64_t switches;          /* consecutive submissions from different submitters (they really interleave) */
    uint64_t tf_conflicts;      /* a TF ring set over a DIFFERENT ring the other submitter had set */
    uint64_t offchip_conflicts; /* the same for VGT_HS_OFFCHIP_PARAM */
};
void omni_gpu_one_submitter_stats(struct omni_gpu_one_submitter_stats *out);

#ifdef __cplusplus
}
#endif
