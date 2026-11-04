// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniMP4SegmentBuffer.h"
#include <cstring>
#include <utility>

namespace OmniMedia {
static uint32_t read32(const uint8_t* p)
{
    return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3];
}
bool MP4SegmentBuffer::fail(const char* reason)
{
    failure = reason;
    std::vector<uint8_t>().swap(pending);
    std::vector<uint8_t>().swap(assembling);
    offset = 0;
    return false;
}
bool MP4SegmentBuffer::append(std::span<const uint8_t> bytes)
{
    if (!failure.empty()) return false;
    if (ended) return fail("Append after end of stream");
    if (bytes.size() > maxBufferedBytes - bufferedBytes())
        return fail("Fragment buffer quota exceeded");
    if (offset) {
        pending.erase(pending.begin(), pending.begin() + offset);
        offset = 0;
    }
    pending.insert(pending.end(), bytes.begin(), bytes.end());
    return true;
}
MP4SegmentBuffer::Result MP4SegmentBuffer::next(Segment& output)
{
    if (!failure.empty()) return Result::Error;
    auto invalid = [this](const char* reason) { fail(reason); return Result::Error; };
    for (;;) {
        size_t available = pending.size() - offset;
        if (!available) {
            if (!ended) return Result::NeedMore;
            if (phase != Phase::Idle) return invalid("Incomplete segment at end of stream");
            return Result::End;
        }
        if (available < 8)
            return ended ? invalid("Truncated box header") : Result::NeedMore;
        const uint8_t* box = pending.data() + offset;
        uint64_t size = read32(box);
        size_t header = 8;
        if (size == 1) {
            if (available < 16)
                return ended ? invalid("Truncated extended box header") : Result::NeedMore;
            size = uint64_t(read32(box + 8)) << 32 | read32(box + 12);
            header = 16;
        }
        if (!size) return invalid("Open-ended boxes are unsupported");
        if (size < header) return invalid("Invalid box size");
        if (size > maxBufferedBytes || size > maxBufferedBytes - assembling.size())
            return invalid("Declared segment size exceeds quota");
        if (size > available)
            return ended ? invalid("Truncated box payload") : Result::NeedMore;
        auto type = [box](const char* value) { return !memcmp(box + 4, value, 4); };
        bool emit = false;
        Segment::Kind kind = Segment::Kind::Media;
        if (type("ftyp")) {
            if (phase != Phase::Idle) return invalid("Unexpected initialization start");
            phase = Phase::Initialization;
        } else if (type("moov")) {
            if (phase != Phase::Initialization) return invalid("Initialization missing ftyp");
            kind = Segment::Kind::Initialization;
            emit = true;
        } else if (type("moof")) {
            if (!initialized || phase != Phase::Idle) return invalid("Unexpected media fragment");
            phase = Phase::Media;
        } else if (type("mdat")) {
            if (phase != Phase::Media) return invalid("Media payload missing moof");
            emit = true;
        } else if (type("free") || type("skip") || type("styp") || type("sidx") || type("emsg") || type("prft")) {
            // Baseline does not expose timed metadata. Keep auxiliary boxes
            // within a fragment for the demuxer; discard standalone metadata.
            if (phase == Phase::Idle) { offset += size_t(size); continue; }
        } else if (phase == Phase::Idle && (type("mfra") || type("udta") || type("meta") || type("uuid"))) {
            // OMNI_CODEC_OPUS_V1: whole fragmented files appended as-is end with 'mfra' (FFmpeg,
            // MP4Box, Bento4 all write it); Chrome and Safari ignore it. Before, it was
            // "Unsupported top-level box" -> decode error at the very end of the file.
            offset += size_t(size);
            continue;
        } else return invalid("Unsupported top-level box");
        if (phase == Phase::Initialization && size > maxInitializationBytes - assembling.size())
            return invalid("Initialization segment exceeds quota");
        assembling.insert(assembling.end(), box, box + size_t(size));
        offset += size_t(size);
        if (emit) {
            output.kind = kind;
            output.bytes = std::move(assembling);
            assembling = {};
            // OMNI_WEBM_V1 rev3: all input consumed: free it now, not at the next append
            // (one fewer fragment-sized copy while the segment is demuxed).
            if (offset == pending.size()) { std::vector<uint8_t>().swap(pending); offset = 0; }
            if (kind == Segment::Kind::Initialization) initialized = true;
            phase = Phase::Idle;
            return Result::Ready;
        }
    }
}
void MP4SegmentBuffer::reset()
{
    std::vector<uint8_t>().swap(pending);
    std::vector<uint8_t>().swap(assembling);
    offset = 0;
    phase = Phase::Idle;
    initialized = ended = false;
    failure.clear();
}
}
