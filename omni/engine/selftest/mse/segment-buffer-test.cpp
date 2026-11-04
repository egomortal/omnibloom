// SPDX-License-Identifier: GPL-3.0-or-later
#include "../../media/OmniMP4SegmentBuffer.h"

#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <initializer_list>
#include <iterator>
#include <string>
#include <vector>

using OmniMedia::MP4SegmentBuffer;
using Bytes = std::vector<uint8_t>;

static Bytes readFile(const std::filesystem::path& path)
{
    std::ifstream file(path, std::ios::binary);
    assert(file && "fixture not found; pass the mse/generated directory");
    return Bytes(std::istreambuf_iterator<char>(file), {});
}

static Bytes box(const char* type, Bytes payload = {})
{
    const uint32_t size = static_cast<uint32_t>(payload.size() + 8);
    Bytes result{uint8_t(size >> 24), uint8_t(size >> 16), uint8_t(size >> 8), uint8_t(size),
                 uint8_t(type[0]), uint8_t(type[1]), uint8_t(type[2]), uint8_t(type[3])};
    result.insert(result.end(), payload.begin(), payload.end());
    return result;
}

static Bytes join(std::initializer_list<Bytes> parts)
{
    Bytes result;
    for (const auto& part : parts) result.insert(result.end(), part.begin(), part.end());
    return result;
}

static Bytes mediaBoxes(const Bytes& fixture)
{
    for (size_t offset = 0; offset + 8 <= fixture.size();) {
        uint32_t size = uint32_t(fixture[offset]) << 24 | uint32_t(fixture[offset + 1]) << 16 |
                        uint32_t(fixture[offset + 2]) << 8 | fixture[offset + 3];
        if (size < 8 || size > fixture.size() - offset) break;
        if (fixture[offset + 4] == 'm' && fixture[offset + 5] == 'o' &&
            fixture[offset + 6] == 'o' && fixture[offset + 7] == 'f')
            return Bytes(fixture.begin() + offset, fixture.end());
        offset += size;
    }
    assert(false && "fixture has no moof box");
    return {};
}

static void append(MP4SegmentBuffer& buffer, const Bytes& bytes)
{
    assert(buffer.append(bytes));
}

static MP4SegmentBuffer::Segment take(MP4SegmentBuffer& buffer)
{
    MP4SegmentBuffer::Segment segment;
    assert(buffer.next(segment) == MP4SegmentBuffer::Result::Ready);
    return segment;
}

static void testRealFixtures(const std::filesystem::path& dir)
{
    auto init = readFile(dir / "init-0.mp4");
    auto first = readFile(dir / "segment-0-00001.m4s");
    auto second = readFile(dir / "segment-0-00002.m4s");
    auto expectedFirst = mediaBoxes(first);
    auto expectedSecond = mediaBoxes(second);

    // Feed each real fixture at every possible single split point.
    for (const Bytes* fixture : {&init, &first, &second}) {
        for (size_t split = 0; split < fixture->size(); ++split) {
            MP4SegmentBuffer buffer;
            if (fixture != &init) {
                append(buffer, init);
                auto initial = take(buffer);
                assert(initial.kind == MP4SegmentBuffer::Segment::Kind::Initialization);
                assert(initial.bytes == init);
            }
            append(buffer, Bytes(fixture->begin(), fixture->begin() + split));
            MP4SegmentBuffer::Segment partial;
            assert(buffer.next(partial) == MP4SegmentBuffer::Result::NeedMore);
            append(buffer, Bytes(fixture->begin() + split, fixture->end()));
            auto segment = take(buffer);
            assert(segment.bytes == (fixture == &init ? *fixture : mediaBoxes(*fixture)));
            assert(segment.kind == (fixture == &init ? MP4SegmentBuffer::Segment::Kind::Initialization
                                                      : MP4SegmentBuffer::Segment::Kind::Media));
        }
    }

    MP4SegmentBuffer buffer;
    append(buffer, init);
    assert(take(buffer).bytes == init);
    append(buffer, join({first, second}));
    assert(take(buffer).bytes == expectedFirst);
    assert(take(buffer).bytes == expectedSecond);
    MP4SegmentBuffer::Segment output;
    assert(buffer.next(output) == MP4SegmentBuffer::Result::NeedMore);
}

static void testBytewiseAndOutOfOrder()
{
    auto ftyp = box("ftyp");
    auto moov = box("moov");
    auto moof = box("moof");
    auto mdat = box("mdat", {1, 2, 3});
    MP4SegmentBuffer buffer;
    auto stream = join({ftyp, moov, moof, mdat, moof, mdat});
    size_t emitted = 0;
    for (uint8_t byte : stream) {
        append(buffer, Bytes{byte});
        MP4SegmentBuffer::Segment output;
        auto result = buffer.next(output);
        if (result == MP4SegmentBuffer::Result::Ready) {
            ++emitted;
            assert(output.kind == MP4SegmentBuffer::Segment::Kind::Initialization ||
                   output.kind == MP4SegmentBuffer::Segment::Kind::Media);
        } else
            assert(result == MP4SegmentBuffer::Result::NeedMore);
    }
    assert(emitted == 3);

    buffer.reset();
    append(buffer, moof);
    MP4SegmentBuffer::Segment output;
    assert(buffer.next(output) == MP4SegmentBuffer::Result::Error);
    assert(!buffer.error().empty());
}

static void testReinitializationResetAndFinish()
{
    auto init = join({box("ftyp"), box("moov")});
    auto media = join({box("moof"), box("mdat")});
    MP4SegmentBuffer buffer;
    append(buffer, init);
    take(buffer);
    append(buffer, init);
    MP4SegmentBuffer::Segment output;
    assert(buffer.next(output) == MP4SegmentBuffer::Result::Ready);
    assert(output.kind == MP4SegmentBuffer::Segment::Kind::Initialization);
    assert(output.bytes == init);
    append(buffer, media);
    assert(buffer.next(output) == MP4SegmentBuffer::Result::Ready);
    assert(output.kind == MP4SegmentBuffer::Segment::Kind::Media);

    buffer.reset();
    append(buffer, join({box("ftyp"), box("moov"), box("moof")}));
    take(buffer);
    buffer.finish();
    assert(buffer.next(output) == MP4SegmentBuffer::Result::Error);
    assert(buffer.error().find("Incomplete") != std::string::npos);

    buffer.reset();
    append(buffer, join({init, media}));
    assert(take(buffer).kind == MP4SegmentBuffer::Segment::Kind::Initialization);
    assert(take(buffer).kind == MP4SegmentBuffer::Segment::Kind::Media);
    buffer.finish();
    assert(buffer.next(output) == MP4SegmentBuffer::Result::End);
}

static void testLimitsAndMalformedBoxes()
{
    MP4SegmentBuffer buffer;
    Bytes tooMuch(MP4SegmentBuffer::maxBufferedBytes + 1);
    assert(!buffer.append(tooMuch));
    MP4SegmentBuffer::Segment output;
    assert(buffer.next(output) == MP4SegmentBuffer::Result::Error);

    // Extended size of 2^64-1 must be rejected before waiting for its body.
    buffer.reset();
    Bytes extended{0, 0, 0, 1, 'f', 'r', 'e', 'e', 0xff, 0xff, 0xff, 0xff,
                   0xff, 0xff, 0xff, 0xff};
    append(buffer, extended);
    assert(buffer.next(output) == MP4SegmentBuffer::Result::Error);

    for (const auto& malformed : {Bytes{0, 0, 0, 0, 'f', 'r', 'e', 'e'},
                                  Bytes{0, 0, 0, 7, 'f', 'r', 'e', 'e'},
                                  box("zzzz")}) {
        buffer.reset();
        append(buffer, malformed);
        assert(buffer.next(output) == MP4SegmentBuffer::Result::Error);
    }

    buffer.reset();
    append(buffer, Bytes{0, 0, 0, 8, 'f', 't'});
    buffer.finish();
    assert(buffer.next(output) == MP4SegmentBuffer::Result::Error);
}

static void testDeterministicMalformedStreams()
{
    // Exercise size/type mutations and partial headers under sanitizers. This
    // checks bounded framing and termination, not semantic MP4 validity.
    uint32_t state = 0x4f4d4e49;
    auto random = [&]() { state ^= state << 13; state ^= state >> 17; state ^= state << 5; return state; };
    const auto valid = join({box("ftyp"), box("moov"), box("moof"), box("mdat", {1, 2, 3})});
    for (unsigned trial = 0; trial < 4000; ++trial) {
        auto bytes = valid;
        for (unsigned edits = 1 + random() % 8; edits; --edits)
            bytes[random() % bytes.size()] = static_cast<uint8_t>(random());
        if (trial % 3 == 0) bytes.resize(random() % bytes.size());
        MP4SegmentBuffer buffer;
        MP4SegmentBuffer::Segment output;
        bool failed = false;
        for (size_t offset = 0; offset < bytes.size() && !failed;) {
            size_t count = std::min(size_t(1 + random() % 17), bytes.size() - offset);
            if (!buffer.append(std::span<const uint8_t>(bytes.data() + offset, count))) break;
            offset += count;
            unsigned iterations = 0;
            for (;;) {
                assert(++iterations <= bytes.size() + 1);
                auto result = buffer.next(output);
                if (result == MP4SegmentBuffer::Result::Ready) {
                    assert(output.bytes.size() <= MP4SegmentBuffer::maxBufferedBytes);
                    continue;
                }
                failed = result == MP4SegmentBuffer::Result::Error;
                break;
            }
        }
        buffer.finish();
        unsigned iterations = 0;
        while (buffer.next(output) == MP4SegmentBuffer::Result::Ready)
            assert(++iterations <= bytes.size() + 1);
        buffer.reset();
        append(buffer, valid);
        assert(take(buffer).kind == MP4SegmentBuffer::Segment::Kind::Initialization);
        assert(take(buffer).kind == MP4SegmentBuffer::Segment::Kind::Media);
    }
}

int main(int argc, char** argv)
{
    assert(argc == 2 && "usage: segment-buffer-test <path-to-mse/generated>");
    const std::filesystem::path fixtures(argv[1]);
    testRealFixtures(fixtures);
    testBytewiseAndOutOfOrder();
    testReinitializationResetAndFinish();
    testLimitsAndMalformedBoxes();
    testDeterministicMalformedStreams();
    std::cout << "segment buffer tests passed\n";
}
