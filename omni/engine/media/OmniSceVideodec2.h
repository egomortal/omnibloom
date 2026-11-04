/*
 * sce_videodec2.h - libSceVideodec2 (PS5 hardware H.264/HEVC/VP9 decode) ABI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Layouts and call sequence transcribed from GPL-3.0 projects that run them on
 * hardware: EVO-PLAYER-PS5 (projects/evoplayer/media/include/sce/sce_videodec2.h,
 * itself from ProsperoLight) and OpenNOW-PS5 (src/stream/native/videodec2_api.hpp,
 * adapted from Kodi PS5). The two independent transcriptions agree field for
 * field; the static_asserts below pin the sizes both projects assert.
 * Nothing is linked: the module is dlopen()ed and symbols resolved at run time.
 */
#ifndef OMNI_SCE_VIDEODEC2_H
#define OMNI_SCE_VIDEODEC2_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
#define OMNI_STATIC_ASSERT static_assert
#else
#define OMNI_STATIC_ASSERT _Static_assert
#endif

#define SCE_SYSMODULE_VIDEODEC2        0x00CF   /* 207 */
#define SCE_VIDEODEC2_RESOURCE_COMPUTE 1u
#define SCE_VIDEODEC2_CODEC_AVC        1u
#define SCE_VIDEODEC2_CODEC_HEVC       974921u  /* 0x000EE049 */
#define SCE_VIDEODEC2_CODEC_VP9        2382845u /* 0x00245BFD */
#define SCE_VIDEODEC2_AUTO_FRAMES      (-1)

typedef struct {
    uint64_t size;
    uint32_t resource_type, codec_type, profile, max_level;
    int32_t  max_width, max_height, max_dpb_frames;
    uint32_t pipeline_depth;
    uint64_t compute_queue, cpu_affinity;
    int32_t  cpu_priority;
    uint32_t optimize_progressive, check_memory_type, reserved;
} SceVideodec2DecoderConfigInfo;

typedef struct {
    uint64_t size, cpu_size;
    void    *cpu;
    uint64_t gpu_size;
    void    *gpu;
    uint64_t cpu_gpu_size;
    void    *cpu_gpu;
    uint64_t max_frame_size;
    uint32_t frame_alignment, reserved;
} SceVideodec2DecoderMemoryInfo;

typedef struct {
    uint64_t size;
    uint16_t pipe_id, queue_id;
    uint8_t  check_memory_type, reserved0;
    uint16_t reserved1;
} SceVideodec2ComputeConfigInfo;

typedef struct {
    uint64_t size, cpu_gpu_size;
    void    *cpu_gpu;
} SceVideodec2ComputeMemoryInfo;

typedef struct {
    uint64_t size;
    void    *au;
    uint64_t au_size, pts, dts, attached;
} SceVideodec2InputData;

typedef struct {
    uint64_t size;
    void    *buffer;
    uint64_t buffer_size;
    uint32_t accepted, reserved;
} SceVideodec2FrameBuffer;

typedef struct {
    uint64_t size;
    uint8_t  valid, error, picture_count,
             not_displayed; /* was 'padding': 1 on VP9 hidden-frame outputs (console-verified 2026-10-19) */
    uint32_t codec, width, pitch, height, reserved;
    void    *buffer;
    uint64_t buffer_size;
    uint32_t frame_format, pitch_bytes;
} SceVideodec2OutputInfo;

OMNI_STATIC_ASSERT(sizeof(SceVideodec2DecoderConfigInfo) == 72, "config");
OMNI_STATIC_ASSERT(sizeof(SceVideodec2DecoderMemoryInfo) == 72, "memory");
OMNI_STATIC_ASSERT(sizeof(SceVideodec2ComputeConfigInfo) == 16, "compute config");
OMNI_STATIC_ASSERT(sizeof(SceVideodec2ComputeMemoryInfo) == 24, "compute memory");
OMNI_STATIC_ASSERT(sizeof(SceVideodec2InputData) == 48, "input");
OMNI_STATIC_ASSERT(sizeof(SceVideodec2FrameBuffer) == 32, "frame");
OMNI_STATIC_ASSERT(sizeof(SceVideodec2OutputInfo) == 56, "output");
OMNI_STATIC_ASSERT(offsetof(SceVideodec2OutputInfo, buffer) == 32, "output.buffer");

typedef int32_t (*PFN_QueryComputeMemoryInfo)(SceVideodec2ComputeMemoryInfo *);
typedef int32_t (*PFN_AllocateComputeQueue)(const SceVideodec2ComputeConfigInfo *,
                                            const SceVideodec2ComputeMemoryInfo *, void **);
typedef int32_t (*PFN_ReleaseComputeQueue)(void *);
typedef int32_t (*PFN_QueryDecoderMemoryInfo)(const SceVideodec2DecoderConfigInfo *,
                                              SceVideodec2DecoderMemoryInfo *);
typedef int32_t (*PFN_CreateDecoder)(const SceVideodec2DecoderConfigInfo *,
                                     const SceVideodec2DecoderMemoryInfo *, void **);
typedef int32_t (*PFN_DeleteDecoder)(void *);
typedef int32_t (*PFN_Reset)(void *);
typedef int32_t (*PFN_Decode)(void *, SceVideodec2InputData *, SceVideodec2FrameBuffer *,
                              SceVideodec2OutputInfo *);
typedef int32_t (*PFN_Flush)(void *, SceVideodec2FrameBuffer *, SceVideodec2OutputInfo *);
#endif
