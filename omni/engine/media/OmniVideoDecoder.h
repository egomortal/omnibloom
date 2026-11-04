// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "OmniMP4Demuxer.h" // OMNI_PROGRESSIVE_HOLEPUNCH_V1: DemuxTrack / DemuxPacket
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace OmniMedia {
struct VideoFrame {
    int width = 0, height = 0;
    double seconds = 0;
    std::vector<uint8_t> rgba;
};
// OMNI_PROGRESSIVE_V1: bytes the decoder reads as it goes (a range cache filled by WebKit's loader,
// OmniProgressive.h). read() may block (on the decoder's thread) until the bytes are there; the
// time it waited does not count against the decode time limit.
class ByteSource {
public:
    virtual ~ByteSource() = default;
    virtual int64_t size() const = 0;   // -1 while unknown
    // Up to `length` bytes at `offset`: > 0 bytes copied, 0 at the end, < 0 error / aborted.
    virtual int read(int64_t offset, uint8_t* buffer, int length, double& waitedSeconds) = 0;
};
// Decodes already-fetched bytes only. WebKit remains responsible for networking.
// This initial adapter is bounded, software video decoding, not MSE or DRM.
class VideoDecoder {
public:
    static constexpr size_t maxInputBytes = 32 * 1024 * 1024;
    static constexpr int maxPixels = 1920 * 1080;
    enum class Result { Frame, Again, End, Error };
    VideoDecoder();
    ~VideoDecoder();
    VideoDecoder(const VideoDecoder&) = delete;
    VideoDecoder& operator=(const VideoDecoder&) = delete;
    bool open(std::vector<uint8_t>);
    bool openSource(std::shared_ptr<ByteSource>);   // OMNI_PROGRESSIVE_V1: no size limit (the source bounds memory); not an open() overload (open({}) stays unambiguous)
    Result next(VideoFrame&);
    // OMNI_PROGRESSIVE_HOLEPUNCH_V1: packet mode, for the hardware decoder (PacketDecoder) and the
    // shell's hole-punch presentation. openSourcePackets() is openSource() except that, when the
    // file's video is H.264 or HEVC (with avcC/hvcC) or VP9, at most 3840x2160, the video is not
    // decoded here: nextPacket() hands its packets out (FFmpeg's demuxer, the stream's own time
    // base) while audio is decoded as before (takeAudio()). Any other video (VP8, larger, no
    // configuration): exactly openSource() (software decoding, next()). packetMode() says which.
    static constexpr int maxPacketPixels = 3840 * 2160;
    bool openSourcePackets(std::shared_ptr<ByteSource>);
    bool packetMode() const;
    const DemuxTrack& videoTrack() const;
    // Frame: `out` holds the next video packet. Again: an audio packet was decoded (take the PCM).
    Result nextPacket(DemuxPacket& out);
    bool seek(double seconds);
    double duration() const;
    bool hasAudio() const;
    // Signed 16-bit stereo at 48 kHz; drain regularly to keep buffering bounded.
    std::vector<int16_t> takeAudio();
    const std::string& error() const;
private:
    bool openStreams(); // OMNI_PROGRESSIVE_V1
    struct State;
    std::unique_ptr<State> state;
};
}
