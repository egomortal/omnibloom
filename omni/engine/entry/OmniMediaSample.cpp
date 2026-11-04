// SPDX-License-Identifier: GPL-3.0-or-later
#include "config.h"
#include "OmniMediaSample.h"
#include <limits>
#include <numeric>

namespace WebCore {
static bool exact(const MediaTime& t)
{ return t.isValid() && t.isFinite() && !t.hasDoubleValue() && !t.hasBeenRounded() && t.timeScale(); }

OmniMediaSample::OmniMediaSample(std::shared_ptr<const OmniMedia::DemuxPacket> packet,
    TrackID track, FloatSize size, MediaTime pts, MediaTime dts, MediaTime duration, bool nonDisplaying)
    : m_packet(std::move(packet)), m_track(track), m_size(size), m_pts(pts), m_dts(dts),
      m_duration(duration), m_nonDisplaying(nonDisplaying) { }

RefPtr<OmniMediaSample> OmniMediaSample::create(OmniMedia::DemuxPacket&& packet, TrackID track, FloatSize size)
{
    if (packet.timeBase.numerator <= 0 || packet.timeBase.denominator <= 0 || packet.duration <= 0 || packet.bytes.empty())
        return nullptr;
    auto pts = MediaTime(packet.pts, packet.timeBase.denominator) * packet.timeBase.numerator;
    auto dts = MediaTime(packet.dts, packet.timeBase.denominator) * packet.timeBase.numerator;
    auto duration = MediaTime(packet.duration, packet.timeBase.denominator) * packet.timeBase.numerator;
    if (!exact(pts) || !exact(dts) || !exact(duration))
        return nullptr;
    return adoptRef(*new OmniMediaSample(std::make_shared<const OmniMedia::DemuxPacket>(std::move(packet)), track, size, pts, dts, duration));
}
void OmniMediaSample::offsetTimestampsBy(const MediaTime& offset) { m_pts = m_pts + offset; m_dts = m_dts + offset; }
void OmniMediaSample::setTimestamps(const MediaTime& pts, const MediaTime& dts) { m_pts = pts; m_dts = dts; }
Ref<MediaSample> OmniMediaSample::createNonDisplayingCopy() const
{ return adoptRef(*new OmniMediaSample(m_packet, m_track, m_size, m_pts, m_dts, m_duration, true)); }
Ref<MediaSample> OmniMediaSample::createCopyWithAdjustedStartTime(const MediaTime& requested) const
{
    auto offset = requested;
    if (!exact(offset) || offset < MediaTime::zeroTime()) offset = MediaTime::zeroTime();
    if (offset > m_duration) offset = m_duration;
    return adoptRef(*new OmniMediaSample(m_packet, m_track, m_size, m_pts + offset, m_dts + offset, m_duration - offset, m_nonDisplaying));
}
MediaSample::SampleFlags OmniMediaSample::flags() const
{ return static_cast<SampleFlags>(HasSyncInfo | (m_packet->keyFrame ? IsSync : None) | (m_nonDisplaying ? IsNonDisplaying : None)); }
std::optional<OmniMedia::DemuxPacket> OmniMediaSample::copyPacketForDecode() const
{
    if (!exact(m_pts) || !exact(m_dts) || !exact(m_duration) || m_duration < MediaTime::zeroTime()) return std::nullopt;
    uint64_t scale = 1;
    for (const auto& time : { m_pts, m_dts, m_duration }) {
        scale = (scale / std::gcd(scale, static_cast<uint64_t>(time.timeScale()))) * time.timeScale();
        if (scale > static_cast<uint64_t>(std::numeric_limits<int>::max())) return std::nullopt;
    }
    auto convert = [scale](const MediaTime& time, int64_t& output) {
        __int128 value = static_cast<__int128>(time.timeValue()) * (scale / time.timeScale());
        if (value < std::numeric_limits<int64_t>::min() || value > std::numeric_limits<int64_t>::max()) return false;
        output = static_cast<int64_t>(value); return true;
    };
    int64_t pts, dts, duration;
    if (!convert(m_pts, pts) || !convert(m_dts, dts) || !convert(m_duration, duration)) return std::nullopt;
    auto packet = *m_packet;
    packet.nonDisplaying = m_nonDisplaying;
    packet.pts = pts; packet.dts = dts; packet.duration = duration;
    packet.timeBase = { 1, static_cast<int>(scale) };
    return packet;
}
}
