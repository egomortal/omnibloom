// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <WebCore/MediaSample.h>
#include "../media/OmniMP4Demuxer.h"
#include <memory>
#include <optional>

namespace WebCore {
class OmniMediaSample final : public MediaSample {
public:
    static RefPtr<OmniMediaSample> create(OmniMedia::DemuxPacket&&, TrackID, FloatSize = { });
    static const OmniMediaSample* from(const MediaSample& sample)
    { return sample.type() == Type::OmniFFmpegSample ? static_cast<const OmniMediaSample*>(&sample) : nullptr; }
    MediaTime presentationTime() const final { return m_pts; }
    MediaTime decodeTime() const final { return m_dts; }
    MediaTime duration() const final { return m_duration; }
    TrackID trackID() const final { return m_track; }
    size_t sizeInBytes() const final { return m_packet->bytes.size() + m_packet->skipSamples.size(); }
    FloatSize presentationSize() const final { return m_size; }
    void offsetTimestampsBy(const MediaTime&) final;
    void setTimestamps(const MediaTime&, const MediaTime&) final;
    Ref<MediaSample> createNonDisplayingCopy() const final;
    Ref<MediaSample> createCopyWithAdjustedStartTime(const MediaTime&) const final;
    SampleFlags flags() const final;
    PlatformSample platformSample() const final { return PlatformSample { this }; }
    Type type() const final { return Type::OmniFFmpegSample; }
    // Copies encoded bytes only at the decoder boundary; timestamps reflect MSE offsets.
    // Rejects an inexact or overflowing rational conversion instead of rounding.
    std::optional<OmniMedia::DemuxPacket> copyPacketForDecode() const;
private:
    OmniMediaSample(std::shared_ptr<const OmniMedia::DemuxPacket>, TrackID, FloatSize,
        MediaTime, MediaTime, MediaTime, bool = false);
    std::shared_ptr<const OmniMedia::DemuxPacket> m_packet;
    TrackID m_track;
    FloatSize m_size;
    MediaTime m_pts, m_dts, m_duration;
    bool m_nonDisplaying;
};
}
