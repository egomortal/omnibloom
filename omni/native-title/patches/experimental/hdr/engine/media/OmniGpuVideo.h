// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_GPU_VIDEO_V1 (GPU Stage A, omni-native-s2-gpu): converts the shell's video plane pictures
// (planar 4:2:0, 8-bit or 10-bit low-aligned) to the BGRA/RGBA layer on the GPU (RADV Vulkan, linked
// into the native title), scaled to the layer size. Same input and output as the swscale path in
// OmniHwService.cpp's holeConvert, so any failure falls back to the CPU path for that picture.
//
// Off unless /data/omni/gpu-video.flag exists. Words in the flag file (optional):
//   copy        staging buffers instead of importing the picture and layer memory
//   compute     use a compute-only queue (default: the general queue)
//   noverify    skip the GPU-vs-CPU comparison of the first pictures (not recommended)
//   notimer     no GPU timestamps
//   failsetup   (V2) fail the set-up on purpose: the console's fallback check (every picture stays on the CPU)
// Log: /data/omni/native/gpu-video.log (and the hole-punch log through the note callback).
//
// OMNI_GPU_VIDEO_V4 (omni-native-s3.5-hdr): Job::hdrDst asks for the picture's PQ layer too (HDR10 sources kept in PQ,
// HLG converted to PQ), written by the same dispatch into a second imported buffer; stats3() counts those pictures.
//
// OMNI_GPU_VIDEO_V3 (omni-video-4k60): zero extra copies and one RADV device.
//  - a picture whose planes live in memory that stays mapped until forget() (Job::planesPersistent: the hole-punch's
//    pace queue buffers, direct memory) is imported once and read in place by the shader: no ring copy. Anything else
//    (or a refused import) still goes through the persistent 3-slot ring (one copy, on the calling service thread);
//  - when the title's GPU present is up, its VkDevice and queue are shared (omni_gpu_present_share): no second RADV
//    device; submissions to the shared queue are serialised with the present's queue lock. Without the present (flag
//    off or its set-up failed) V3 creates its own device exactly as V2 did;
//  - stats2() adds the in-place pictures and the ring copies for the per-second fps line.
//
// OMNI_GPU_VIDEO_V2 (omni-native-s3.2-video): enlargements are converted with the CPU's integer-upscale rule and
// verified like 1:1 pictures (V1 never verified them, so a 2160 canvas never used the GPU); pictures go through a
// persistent 3-slot staging ring and layers are imported once (forget() before their memory goes); preinit() from
// the title's SDL_Init brings RADV up before any video decoder; stats() feeds the per-second fps line.
#pragma once
#include <cstddef>
#include <cstdint>

namespace OmniGpuVideo {

struct Job {
    const uint8_t* planes = nullptr; size_t planesBytes = 0;   // Y, U, V planes, tightly packed
    int srcW = 0, srcH = 0, bps = 1;                           // bytes per sample: 1 (8-bit) or 2 (10-bit in 16)
    uint8_t* dst = nullptr; size_t dstBytes = 0;               // layer pixels (stride * h bytes)
    int dstW = 0, dstH = 0, dstStride = 0;                     // pixels, pixels, bytes per row
    bool swapRB = false;                                       // R,G,B,A bytes (else B,G,R,A)
    int matrix = 1;                                            // H.273 matrix code (1 = BT.709, 5/6 = BT.601, 9 = BT.2020)
    bool fullRange = false;
    bool planesPersistent = false;                             // V3: planes stay mapped until forget(): import in place
    // V4 (omni-native-s3.5-hdr): the picture's PQ layer, written in the same pass (packed A2B10G10R10, R low, same stride
    // as dst). hdrMode 1: a BT.2020 NCL + ST 2084 source (R'G'B' kept as they are); 2: BT.2020 NCL + HLG (converted to PQ).
    uint8_t* hdrDst = nullptr; size_t hdrDstBytes = 0; int hdrMode = 0;
    bool* hdrDone = nullptr;                                   // set true when the PQ layer was written
};

enum Plan { kCpu = 0, kVerify = 1, kGpu = 2 };

// Service thread. The first call with the flag present starts the GPU set-up on its own thread
// and returns kCpu until it is ready. kVerify: convert on the CPU as usual, then call verify().
Plan plan(const Job&);
// kGpu: converts into job.dst. false = not done (the caller converts on the CPU).
bool convert(const Job&);
// kVerify: converts into a scratch buffer and compares it with job.dst (the CPU result).
// Too far apart = the GPU path is turned off for that bit depth for the rest of the run.
void verify(const Job&);
// Optional extra log sink (the hole-punch log). Called from the service thread and the set-up thread.
void setNote(void (*note)(const char*));
// V2: the memory at p (a layer's pixels) is about to be unmapped: drop its import. Any thread; never waits for a conversion.
void forget(const void* p);
// V2: set up now (synchronously) when the flag exists. The native title calls it from SDL_Init, before any decoder.
bool preinit();
// V2: totals since start (GPU conversions, their wall time and GPU time in microseconds).
void stats(uint64_t& pictures, uint64_t& wallUs, uint64_t& gpuUs);
// V3: pictures read in place (imported planes), pictures copied through the ring, and whether the device is shared.
void stats2(uint64_t& inPlace, uint64_t& ringCopies, int& sharedDevice);
// V4: pictures whose PQ layer was written on the GPU.
void stats3(uint64_t& hdrPictures);

}

// Exit route (native title): waits for a conversion in flight, then frees every GPU object.
extern "C" void omni_gpu_video_shutdown();
// V2, for the title (weak there): preinit, forget and stats as above.
extern "C" int omni_gpu_video_preinit();
extern "C" void omni_gpu_video_forget(const void* p);
extern "C" void omni_gpu_video_stats(uint64_t* pictures, uint64_t* wallUs, uint64_t* gpuUs);
extern "C" void omni_gpu_video_stats2(uint64_t* inPlace, uint64_t* ringCopies, int* sharedDevice);   // V3
extern "C" void omni_gpu_video_stats3(uint64_t* hdrPictures);   // V4

// V3: the device the title's GPU present shares with the video conversion (OmniGpuPresent.cpp fills it). Handles are
// Vulkan handles cast to void*; lock/unlock serialise vkQueueSubmit / vkQueuePresentKHR on the shared queue.
struct OmniGpuShare {
    void* instance; void* physical; void* device; void* queue;
    uint32_t family; uint32_t timestampBits; double timestampNs;
    uint64_t importAlign; int hostImport;
    void (*lock)(); void (*unlock)();
};
// extern "C" int omni_gpu_present_share(OmniGpuShare* out): 1 = shared device available. Defined by OmniGpuPresent.cpp,
// declared weak in OmniGpuVideo.cpp (absent in the big-app and the child engine: V3 then makes its own device).
