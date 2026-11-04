// PS5 hardware video decoder backend (libSceVideodec2), one decoder per instance.
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Console facts this relies on (tools/vdec-probe/RESULTS-2026-10-19.md):
//  - Works in a big-app process (websrv homebrew route). ELF-loader payload
//    processes get ~48 MiB direct memory, too little; flexible memory is
//    rejected by CreateDecoder (0x811d0100).
//  - ONE compute queue per process: releasing it and allocating another hung.
//    The queue is created on first use and kept for the process lifetime.
//  - Output: NV12 (8-bit) or low-aligned two-plane 16-bit (10-bit); UV plane
//    follows `codedHeight` luma rows at the same pitch.
//  - VP9 hidden frames still produce a picture, flagged `notDisplayed`.
// Not thread-safe; one owner thread per instance (the decode service).
#pragma once
#include "OmniHwBitstream.h"
#include <cstddef>
#include <cstdint>
#include <string>

namespace OmniMedia::Hw {

struct Picture {
    const uint8_t* data = nullptr;   // Y plane; UV at data + pitchBytes * codedHeight
    size_t size = 0;
    uint32_t width = 0, codedHeight = 0, pitchBytes = 0, bitDepth = 8;
    bool notDisplayed = false;
};

// Process-wide setup: load the decoder module and resolve symbols. Call once,
// early, from the big-app process. Returns 0 or an rc; `detail` explains.
int backendInitialize(std::string& detail);
bool backendAvailable();
// App exit only, after every Backend is closed: releases the compute queue and
// its memory; no queue can be allocated afterwards. 0 or rc (-2: lock busy).
int backendReleaseQueue(bool blocking);
// Diagnostics (hw-decode-mode.txt timeline); called by the service thread.
void backendDiagnosticTick(double sinceStartMs);
// OMNI_PERF_B_V5: true once the process's compute queue exists (a decoder can then be opened on another thread
// than the service's without the queue being allocated there).
bool backendQueueReady();
// OMNI_HOLEPUNCH_V5: CPU buffers in direct memory (type 12, prot 0x33, as the decoder's own
// frame buffers) for the service's queue of decoded pictures. Null when refused.
// OMNI_HOLEPUNCH_V5_REV2: rc / stage (if given) say why it was refused.
void* backendDirectAlloc(size_t size, int64_t& start, int* rc = nullptr, const char** stage = nullptr);
void backendDirectFree(void* addr, size_t size, int64_t start);
// The largest free block of direct memory (sceKernelAvailableDirectMemorySize); 0 when unknown.
size_t backendDirectAvailable();

// OMNI_DECODER_MEMORY_REPORT_V1: /data/omni/decoder-memory-report.flag (host tests:
// OMNI_DECODER_MEMORY_REPORT=1) asks for a report at hw-service start.
bool backendMemoryReportWanted();
// Logs ("OMNI HW MEMORY:") what QueryDecoderMemoryInfo answers for the 1080p and 2160p
// configurations Omni may open (H.264 L4.2/5.1/5.2, HEVC Main/Main10, VP9 profile 0/2), what
// opening each would take as Backend::open allocates (flexible / direct), and the process's
// available flexible memory, direct memory size and largest free direct block. Queries only:
// no decoder, no memory and no compute queue is allocated. The queue in use is passed when
// there is one; when the queries need one and there is none, the report runs again right
// after the first stream's open has allocated it (before that stream's own allocations).
void backendMemoryReport(const char* when);

class Backend {
public:
    Backend() = default;
    ~Backend();
    Backend(const Backend&) = delete;
    Backend& operator=(const Backend&) = delete;

    // Returns 0 or the failing rc; `stage` names the step.
    int open(Codec, int profile, int bitDepth, int width, int height, std::string& stage);
    // Submit one access unit. `got` set when a picture came out with it.
    int decode(const uint8_t* au, size_t size, uint64_t pts, Picture&, bool& got);
    // End of stream: one buffered picture per call until `got` is false.
    int flushOne(Picture&, bool& got);
    int reset();       // seek / discontinuity; keeps the decoder
    int close();       // releases the decoder and its memory (not the queue)
    bool isOpen() const { return decoder_; }
    int width() const { return width_; }
    int height() const { return height_; }
    Codec codec() const { return codec_; }
    int bitDepth() const { return bitDepth_; }

private:
    struct Mem { void* addr = nullptr; size_t size = 0; int64_t start = -1; };
    static int allocDirect(Mem&, size_t, int prot);
    static void freeDirect(Mem&);
    bool fill(const void* output, Picture&);
    void* decoder_ = nullptr;
    void* cpu_ = nullptr; size_t cpuSize_ = 0;
    Mem gpu_, cpuGpu_, input_, frames_;
    size_t frameSize_ = 0;
    unsigned ring_ = 0;
    int width_ = 0, height_ = 0, bitDepth_ = 8;
    Codec codec_ = Codec::H264;
};

}
