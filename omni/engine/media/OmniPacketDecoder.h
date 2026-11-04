// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "OmniMP4Demuxer.h"
#include <memory>
#include <algorithm> // OMNI_VIDEO_TARGET_V1
#include <cmath>
namespace OmniMedia {
namespace Hw { class HoleFrame; } // OMNI_HOLEPUNCH_V1
struct DecodedOutput {
    enum class Kind { Video, Audio } kind = Kind::Video;
    int64_t timestamp = 0;
    DemuxTimeBase timeBase;
    bool hasTimestamp = false;
    // Decode dependencies are retained, but caller must not render/queue this.
    bool nonDisplaying = false;
    // True only when the decoded source format has no alpha channel.
    bool opaque = false;
    int width = 0, height = 0;
    // OMNI_VIDEO_TARGET_V1: the picture's own size when the pixels above were
    // scaled for display (0 = same as width/height).
    int sourceWidth = 0, sourceHeight = 0;
    // Four bytes per pixel, alpha last. Channel order is RGBA unless bgra is
    // set (see PacketDecoder::setVideoPixelOrder); the field name is historical.
    bool bgra = false;
    std::vector<uint8_t> rgba;
    // Stereo signed16 at48000Hz. Audio timestamps use {1,48000}.
    std::vector<int16_t> pcm;
    // OMNI_HOLEPUNCH_V1: hardware video in hole-punch mode. Set instead of rgba: the picture
    // is still in the decode service's shared slot (see OmniHwClient.h, HoleFrame).
    std::shared_ptr<Hw::HoleFrame> hole;
};
// ---- OMNI_MSE_SWITCH_HANDOFF_V1 -------------------------------------------------------------
// A configuration change (ABR quality switch: a new initialization segment) drains the decoder
// and configures it again, which closes the hardware stream. While the shell paces the video,
// that stream's decoded pictures (V5: up to ~3.5 s ahead of the playhead) are queued in the UI
// process and would go with it, and the new stream's pictures begin only at the switch point:
// nothing new on screen until the playhead gets there, and the player's safety net turned pacing
// off for the rest of the load. The source configures the new stream once the shell has shown
// the old one's pictures. Pure logic, shared with the host simulation.
struct ShellQueue {
    bool paced = false;        // the shell shows and paces this hardware stream
    unsigned waiting = 0;      // its decoded pictures queued in the shell, not shown yet (last report)
    double reportAgeMs = -1;   // since that report
};
struct SwitchHandoff {
    static constexpr double leadSeconds = 0.05;    // configure this close to the switch point
    static constexpr double staleReportMs = 600;   // the shell reports every 100-250 ms while it paces
    static constexpr double maxWaitMs = 30000;     // paused meanwhile, or a playhead that never gets there
    // The new stream, opened ahead, decodes its first samples meanwhile (into output slots: fewer
    // than Wire::outputSlots, 6; nothing waits in its input): its first pictures are ready at the
    // switch point, for the player's paint path until the shell paces the new stream.
    static constexpr unsigned prerollSamples = 5;
    // True: configure now (`why` says why). playhead, switchPoint: seconds (switchPoint < 0: unknown).
    static bool ready(const ShellQueue& q, double playhead, double switchPoint, double waitedMs, const char*& why)
    {
        why = !q.paced ? "not paced by the shell"
            : q.reportAgeMs < 0 || q.reportAgeMs > staleReportMs ? "no recent report from the shell"
            : !q.waiting ? "the shell showed the old pictures"
            : switchPoint < 0 || !std::isfinite(playhead) || playhead >= switchPoint - leadSeconds ? "the playhead reached the switch point"
            : waitedMs >= maxWaitMs ? "waited 30 s" : nullptr;
        return why != nullptr;
    }
    // The kill switch, /data/omni/mse-switch-handoff-disabled.flag (host: OMNI_MSE_SWITCH_HANDOFF=0):
    // v96 behaviour (configure at once; HolePunchController and the player as before).
    static bool enabled();
};
// One persistent codec per track, no IO/SDL or internal packet/output queue.
// On NeedOutput, retain and retry the same packet AFTER receiving output.
class PacketDecoder {
public:
    enum class Submit { Accepted, NeedOutput, Error };
    enum class Receive { Output, NeedInput, End, Error };
    static constexpr size_t maxPacketBytes = 8 * 1024 * 1024;
    static constexpr int maxPixels = 1920 * 1080, maxAudioFrames = 32768;
    // OMNI_WEBM_V1: VP9 above maxPixels decodes on the hardware only (Hw::Client limit).
    // Converted output stays within maxPixels (videoOutputSize).
    static constexpr int maxHardwarePixels = 3840 * 2160;
    // OMNI_WEBM_V1: would configure() take this track? (metadata limits, decoder present,
    // hardware-only VP9 needs the service). Checks a changed initialization before use.
    static bool acceptable(const DemuxTrack&, std::string& why);
    PacketDecoder();
    ~PacketDecoder();
    PacketDecoder(const PacketDecoder&) = delete;
    PacketDecoder& operator=(const PacketDecoder&) = delete;
    // Converted video channel order. Choose the compositor's native order
    // (Skia N32) to avoid a per-pixel swizzle at draw time. Survives configure().
    enum class PixelOrder { RGBA, BGRA };
    void setVideoPixelOrder(PixelOrder order) { pixelOrder = order; }
    // OMNI_VIDEO_TARGET_V1: size the video is shown at, in device pixels (0 = unknown).
    // Converted frames come out at that size. Survives configure().
    void setVideoTargetSize(int width, int height);
    // OMNI_HOLEPUNCH_V1: hardware video frames come out as DecodedOutput::hole (no
    // conversion) while on. Survives configure().
    void setHolePunch(bool on);
    // OMNI_HOLEPUNCH_V3: hardware stream only: wait up to `ms` for decode progress.
    void waitForProgress(int ms);
    bool configure(const DemuxTrack&);
    Submit submit(const DemuxPacket&);
    Submit drain();
    Receive receive(DecodedOutput&);
    // Seek/discontinuity: drops buffered codec/resampler output; config survives.
    void flush();
    const std::string& error() const;
    // True while this stream decodes on the PS5 hardware (UI-process service).
    bool usingHardware() const;
    // OMNI_MSE_SWITCH_HANDOFF_V1: this stream's pictures in the shell's pacing queue (see above).
    ShellQueue shellQueue() const;
    // OMNI_MSE_SWITCH_HANDOFF_V1: configure() opens the hardware stream only when a decode channel is
    // free now (no 2 s wait; else software, as when none is available). Survives configure().
    void setHardwareNoWait(bool on) { hardwareNoWait = on; }
    // OMNI_MSE_SWITCH_HANDOFF_V1: exchange everything (both decoders' streams, settings).
    void swap(PacketDecoder&);
    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h): a background tab's video gives its hardware
    // decoder back. releaseHardware(): closes this stream's decode channel (the UI process deletes the
    // decoder and its shared memory at once); the configuration and the software decoder (if any)
    // stay. True: a hardware stream was open. While released the caller must not submit, drain or
    // receive (flush() is safe).
    bool releaseHardware();
    bool hardwareReleased() const;
    // Opens the hardware stream again, only if a decode channel is free now. True: hardware again (or
    // nothing was released); the caller restarts the stream at a keyframe (a seek). False: nothing changed.
    bool reacquireHardware();
    // No channel came free: the software decoder from the next keyframe (a hardware-only stream fails).
    void abandonHardware();
private:
    void hwFallback();
    bool configureHardware(bool video); // OMNI_WEBM_V1
    struct State;
    std::unique_ptr<State> state;
    PixelOrder pixelOrder = PixelOrder::RGBA;
    int targetWidth = 0, targetHeight = 0;
    bool holePunch = false; // OMNI_HOLEPUNCH_V1
    bool hardwareNoWait = false; // OMNI_MSE_SWITCH_HANDOFF_V1
};
// OMNI_VIDEO_TARGET_V1: output size for a w x h picture shown at tw x th device pixels
// (0 = unknown: keep the source size). Never more than maxPixels.
inline void videoOutputSize(int w, int h, int tw, int th, int& ow, int& oh)
{
    ow = w; oh = h;
    if (tw > 0 && th > 0 && tw <= 4096 && th <= 4096) { ow = tw; oh = th; }
    if (int64_t(ow) * oh > PacketDecoder::maxPixels) {
        double k = std::sqrt(double(PacketDecoder::maxPixels) / (double(ow) * oh));
        ow = std::max(2, int(ow * k)); oh = std::max(2, int(oh * k));
    }
}
}
