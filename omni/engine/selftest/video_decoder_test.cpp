// SPDX-License-Identifier: GPL-3.0-or-later
#include "../media/OmniVideoDecoder.h"
#include <cstdio>
#include <fstream>
#include <iterator>
#include <limits>
#include <random>
#include <unistd.h>
using OmniMedia::VideoDecoder;
int main(int argc, char** argv) {
#ifdef OMNI_CONSOLE_TEST
    freopen("/data/omni/media-decoder-test.txt", "w", stdout);
    const char* inputs[] = {"/data/omni/media-test.mp4", "/data/omni/media-test.webm"};
#else
    if (argc != 3) return 2;
    const char* inputs[] = {argv[1], argv[2]};
#endif
    int failures = 0;
    auto check = [&](bool ok, const char* name) {
        printf("%s: %s\n", ok ? "PASS" : "FAIL", name);
        fflush(stdout); fsync(fileno(stdout)); if (!ok) ++failures;
    };
    for (const char* input : inputs) {
        std::ifstream file(input, std::ios::binary);
        std::vector<uint8_t> bytes{std::istreambuf_iterator<char>(file), {}};
        VideoDecoder decoder;
        bool opened = decoder.open(bytes);
        check(opened, input);
        if (!opened) { printf("%s\n", decoder.error().c_str()); continue; }
        OmniMedia::VideoFrame frame;
        int frames = 0; double last = -1; bool ordered = true, sizes = true, ended = false;
        size_t audioSamples = 0; bool audibleSamples = false;
        for (int i = 0; i < 1000; ++i) {
            auto result = decoder.next(frame);
            auto pcm = decoder.takeAudio(); audioSamples += pcm.size();
            for (auto sample : pcm) audibleSamples |= sample > 100 || sample < -100;
            if (result == VideoDecoder::Result::End) { ended = true; break; }
            if (result == VideoDecoder::Result::Error) break;
            if (result == VideoDecoder::Result::Again) continue;
            ++frames; ordered &= frame.seconds >= last; last = frame.seconds;
            sizes &= frame.width == 320 && frame.height == 180 && frame.rgba.size() == 320 * 180 * 4;
        }
        printf("decoded=%d duration=%.3f last=%.3f\n", frames, decoder.duration(), last);
        check(ended && frames == 30 && ordered && sizes, "all frames, timestamps and buffer sizes");
        printf("audio=%d samples=%zu\n",decoder.hasAudio(),audioSamples);
        if (decoder.hasAudio()) check(audioSamples >= 172800 && audioSamples <= 211200 && audibleSamples, "decoded stereo audio duration and signal");
        else check(!audioSamples, "video-only source has no audio output");
        check(!decoder.seek(-1) && !decoder.seek(std::numeric_limits<double>::infinity())
            && !decoder.seek(std::numeric_limits<double>::quiet_NaN())
            && !decoder.seek(decoder.duration() + 1), "invalid seeks rejected");
        check(decoder.seek(0), "rewind");
        check(decoder.next(frame) == VideoDecoder::Result::Frame && frame.seconds < 0.1, "frame after rewind");
        decoder.takeAudio();
        check(decoder.seek(1), "seek to one second");
        check(decoder.next(frame) == VideoDecoder::Result::Frame && frame.seconds >= 1 && frame.seconds < 1.1, "nonzero seek discards earlier keyframe pictures");
        check(!decoder.open({}) && decoder.next(frame) == VideoDecoder::Result::Error,
            "failed reopen invalidates the previous decoder");
        check(decoder.open(bytes) && decoder.next(frame) == VideoDecoder::Result::Frame,
            "valid reopen recovers after failure");
        bytes.resize(std::min<size_t>(bytes.size(), 32));
        VideoDecoder truncated;
        check(!truncated.open(std::move(bytes)), "truncated container rejected");
    }
    VideoDecoder invalid;
    check(!invalid.open({}), "empty input rejected");
    check(!invalid.open(std::vector<uint8_t>(VideoDecoder::maxInputBytes + 1)), "oversized input rejected");
    std::string playlist = "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nfile:///data/omni/controller-style.txt\n#EXT-X-ENDLIST\n";
    check(!invalid.open({playlist.begin(), playlist.end()}), "playlist and external file source rejected");
    std::mt19937 random(0x4f4d4e49);
    bool malformedRejected = true;
    for (int i = 0; i < 64; ++i) {
        std::vector<uint8_t> bytes(64 + i * 37);
        for (auto& byte : bytes) byte = uint8_t(random());
        malformedRejected &= !invalid.open(std::move(bytes));
    }
    check(malformedRejected, "64 deterministic malformed inputs rejected");
    printf("MEDIA TEST %s failures=%d\n", failures ? "FAIL" : "PASS", failures);
    fflush(stdout); return failures ? 1 : 0;
}
