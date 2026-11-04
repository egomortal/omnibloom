// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace OmniMedia {
struct AudioChunk {
    double seconds = 0;
    // Interleaved signed 16-bit stereo, 48000 Hz. At most maxChunkFrames.
    std::vector<int16_t> samples;
};
// Complete, already-fetched single-audio-track MP4/WebM only. No networking,
// append, seeking or MSE integration. Independent of the existing VideoDecoder.
class AudioDecoder {
public:
    static constexpr size_t maxInputBytes = 32 * 1024 * 1024;
    static constexpr int maxChunkFrames = 32768;
    enum class Result { Chunk, Again, End, Error };
    AudioDecoder();
    ~AudioDecoder();
    AudioDecoder(const AudioDecoder&) = delete;
    AudioDecoder& operator=(const AudioDecoder&) = delete;
    bool open(std::vector<uint8_t>);
    Result next(AudioChunk&);
    const std::string& error() const;
private:
    struct State;
    std::unique_ptr<State> state;
};
}
