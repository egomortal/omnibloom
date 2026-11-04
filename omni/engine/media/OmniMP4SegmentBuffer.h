// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace OmniMedia {
// Framing only: validates bounded top-level boxes, NOT codec/sample semantics.
// Consumer must validate initialization/tracks and demux each emitted fragment.
// Baseline accepts ftyp+moov and moof+mdat; zero-sized/open-ended boxes are rejected.
class MP4SegmentBuffer {
public:
    // OMNI_WEBM_V1 rev3: 32 MiB, the SourceBuffer quota (platformMaximumBufferSize). 10 s
    // 1080p HLS fragments from hls.js are 11-13 MB; the old 8 MiB refused them.
    static constexpr size_t maxBufferedBytes = 32 * 1024 * 1024;
    static constexpr size_t maxInitializationBytes = 1024 * 1024;
    enum class Result { Ready, NeedMore, End, Error };
    struct Segment {
        enum class Kind { Initialization, Media } kind;
        std::vector<uint8_t> bytes;
    };
    bool append(std::span<const uint8_t>);
    Result next(Segment&);
    void finish() { ended = true; }
    void reset();
    size_t bufferedBytes() const { return pending.size() - offset + assembling.size(); }
    const std::string& error() const { return failure; }
private:
    bool fail(const char*);
    std::vector<uint8_t> pending, assembling;
    size_t offset = 0;
    enum class Phase { Idle, Initialization, Media } phase = Phase::Idle;
    bool initialized = false, ended = false;
    std::string failure;
};
}
