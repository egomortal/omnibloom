// SPDX-License-Identifier: GPL-3.0-or-later
#include "../media/OmniAudioDecoder.h"
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iterator>
using namespace OmniMedia;
int main(int argc, char** argv) {
    if (argc < 2) return 2;
    AudioDecoder decoder;
    AudioChunk chunk;
    for (int index = 1; index < argc; ++index) {
        std::ifstream file(argv[index], std::ios::binary);
        std::vector<uint8_t> bytes { std::istreambuf_iterator<char>(file), {} };
        for (int cycle = 0; cycle < 3; ++cycle) {
            if (!decoder.open(bytes)) { fprintf(stderr, "%s\n", decoder.error().c_str()); return 1; }
            size_t frames = 0; bool end = false, audible = false;
            double last = -100;
            for (int calls = 0; calls < 1000; ++calls) {
                auto r = decoder.next(chunk);
                if (r == AudioDecoder::Result::Error) { fprintf(stderr, "%s\n", decoder.error().c_str()); return 1; }
                if (r == AudioDecoder::Result::End) { end = true; break; }
                if (r == AudioDecoder::Result::Again) continue;
                if (!std::isfinite(chunk.seconds) || chunk.seconds + .001 < last
                    || chunk.samples.empty() || chunk.samples.size() % 2
                    || chunk.samples.size() > AudioDecoder::maxChunkFrames * 2) return 1;
                last = chunk.seconds; frames += chunk.samples.size() / 2;
                for (auto sample : chunk.samples) audible |= std::abs(int(sample)) > 100;
            }
            if (!end || !audible || frames < 47500 || frames > 51000) return 1;
            if (decoder.next(chunk) != AudioDecoder::Result::End || !chunk.samples.empty()) return 1;
            printf("PASS %s cycle=%d frames=%zu\n", argv[index], cycle, frames);
        }
    }
    if (decoder.open({}) || decoder.next(chunk) != AudioDecoder::Result::Error) return 1;
    if (decoder.open(std::vector<uint8_t>(1024, 0x7f))) return 1;
    if (decoder.open(std::vector<uint8_t>(AudioDecoder::maxInputBytes + 1))) return 1;
    puts("PASS invalid input, reset and bounded chunks");
}
