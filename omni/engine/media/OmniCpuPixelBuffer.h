// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
#include <limits>
#include <sys/mman.h>

namespace OmniMedia::Hw {
// CPU-only conversion destination. The service owns it exclusively while writing.
// Growth discards old pixels: swscale fills every visible pixel before publication.
// Reuse the capacity on size changes; never use this for partially updated images.
class CpuPixelBuffer {
    uint8_t* pixels_ = nullptr;
    size_t capacity_ = 0;
public:
    CpuPixelBuffer() = default;
    CpuPixelBuffer(const CpuPixelBuffer&) = delete;
    CpuPixelBuffer& operator=(const CpuPixelBuffer&) = delete;
    ~CpuPixelBuffer() { if (pixels_) munmap(pixels_, capacity_); }
    uint8_t* data() { return pixels_; }
    const uint8_t* data() const { return pixels_; }
    bool ensure(size_t bytes) {
        if (bytes <= capacity_) return true;
        if (bytes > size_t(std::numeric_limits<ptrdiff_t>::max())) return false;
        void* mapped = mmap(nullptr, bytes, PROT_READ | PROT_WRITE,
            MAP_PRIVATE | MAP_ANON, -1, 0);
        if (mapped == MAP_FAILED) return false; // preserve the old buffer on failure
        if (pixels_) munmap(pixels_, capacity_);
        pixels_ = static_cast<uint8_t*>(mapped);
        capacity_ = bytes;
        return true;
    }
};
}
