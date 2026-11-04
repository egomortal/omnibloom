// Bitstream adaptation for the PS5 hardware decoder (libSceVideodec2).
// SPDX-License-Identifier: GPL-3.0-or-later
//
// The hardware takes one access unit per call:
//  - H.264 / HEVC: Annex-B (start codes) with parameter sets in band. MP4
//    stores length-prefixed NAL units and keeps SPS/PPS(/VPS) in avcC/hvcC,
//    so keyframes get the parameter sets prepended unless already present.
//  - VP9: one coded frame per call. Superframes are split; frames with
//    show_frame=0 are decoded for reference but must never be shown.
// Pure functions, no I/O; every length is bounds-checked.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniMedia::Hw {

enum class Codec { H264, HEVC, VP9 };

// OMNI_HOLEPUNCH_COLOUR_V1: colour signalled by the stream (ITU-T H.273 matrix_coefficients;
// -1 = not signalled). From the SPS VUI (H.264/HEVC) or a VP9 keyframe's color_config.
struct VideoColour { int matrix = -1, fullRange = -1; };

struct NalConfig {
    int lengthSize = 4;                   // bytes per NAL length prefix (1, 2 or 4)
    std::vector<uint8_t> parameterSets;   // Annex-B SPS/PPS (+VPS for HEVC)
    int profile = 0, level = 0, bitDepth = 8;
    VideoColour colour;                   // OMNI_HOLEPUNCH_COLOUR_V1: from the first SPS
};

// avcC (ISO/IEC 14496-15 5.2.4.1) / hvcC (8.3.3.1). False with `error` set on
// malformed input.
bool parseAvcC(const uint8_t* data, size_t size, NalConfig&, std::string& error);
bool parseHvcC(const uint8_t* data, size_t size, NalConfig&, std::string& error);

// Length-prefixed sample -> Annex-B access unit appended to `out` (cleared
// first). If `keyFrame` and the sample carries no SPS (H.264 type 7 / HEVC
// type 33) of its own, `config.parameterSets` is prepended.
bool lengthPrefixedToAnnexB(Codec, const NalConfig&, const uint8_t* data, size_t size,
                            bool keyFrame, std::vector<uint8_t>& out, std::string& error);

// True when a buffer begins with a start code. Only meaningful for streams
// known to be Annex-B: a length-prefixed sample whose first NAL unit is
// 256-511 bytes long also starts 00 00 01. Do not use it to classify MP4 samples.
bool looksLikeAnnexB(const uint8_t* data, size_t size);

// HEVC: nal_unit_type of the first VCL NAL (type < 32) in a length-prefixed
// sample, or -1. Used to drop RASL pictures (types 8, 9) after a random
// access at a CRA/BLA picture: they reference pictures before the access
// point and cannot be decoded (ITU-T H.265 8.1.3, NoRaslOutputFlag).
int hevcFirstVclType(const NalConfig&, const uint8_t* data, size_t size);

struct Vp9Frame { size_t offset = 0, size = 0; bool shown = true; };
// Split a VP9 packet into frames (Annex B superframe index) and classify each
// with the uncompressed header (show_existing_frame counts as shown).
bool splitVp9(const uint8_t* data, size_t size, std::vector<Vp9Frame>&, std::string& error);

// Profile and bit depth from a VP9 keyframe's uncompressed header (WebM
// carries neither reliably). False if the frame is not a keyframe.
bool vp9KeyFrameInfo(const uint8_t* data, size_t size, int& profile, int& bitDepth);

// ---- OMNI_HOLEPUNCH_COLOUR_V1 -------------------------------------------------------------
// The colour description of one SPS NAL unit (with its NAL header), H.264 or HEVC; fields stay
// -1 when the SPS has no VUI / no video signal type, or does not parse.
VideoColour spsColour(Codec, const uint8_t* nal, size_t size);
// color_space / color_range of a VP9 keyframe (mapped to H.273 codes). False if not a keyframe.
bool vp9KeyFrameColour(const uint8_t* data, size_t size, VideoColour&);
// What the YUV -> RGB conversions use: the signalled matrix when it is one swscale knows
// (1 BT.709, 4 FCC, 5/6 BT.601, 7 SMPTE 240M, 9/10 BT.2020), else BT.709 for pictures 720
// lines or taller and BT.601 below (the usual practice for untagged video); limited (studio)
// range unless the stream says full. As a word: Configure.f (OmniHwProtocol.h).
constexpr uint32_t colourKnown = 0x100, colourFull = 0x200;
inline uint32_t colourWord(const VideoColour& c, int height)
{
    const int m = c.matrix;
    const bool supported = m == 1 || m == 4 || m == 5 || m == 6 || m == 7 || m == 9 || m == 10;
    return colourKnown | uint32_t(supported ? m : height >= 720 ? 1 : 6) | (c.fullRange == 1 ? colourFull : 0);
}
// Matrix (H.273 code, also swscale's SWS_CS_* index) and range of a word; a word without
// colourKnown (an older client) gets the default for `height`.
inline int colourMatrix(uint32_t word, int height) { return word & colourKnown ? int(word & 0xff) : height >= 720 ? 1 : 6; }
inline bool colourFullRange(uint32_t word) { return (word & colourKnown) && (word & colourFull); }

}
