// HLS media segments -> Omni demux packets (OMNI_HLS_NATIVE_V1). SPDX-License-Identifier: GPL-3.0-or-later
//
// One whole segment in memory at a time (no I/O here):
//   * MPEG-TS (RFC 8216 3.2): H.264 (Annex B) + AAC (ADTS), through libavformat's mpegts demuxer
//     with no protocols and no stream probing. H.264 becomes avcC + 4-byte length-prefixed NAL
//     units (what PacketDecoder and the hardware client take, as from MP4); AAC loses its ADTS
//     headers and gets an AudioSpecificConfig. Times: {1, 90000}, raw 33-bit PTS/DTS.
//   * Packed audio (3.4): ADTS frames, optionally after an ID3 tag carrying the
//     com.apple.streaming.transportStreamTimestamp PRIV frame. Same output as TS audio.
//   * Fragmented MP4 (3.3): the EXT-X-MAP init + the segment's moof/mdat pairs, through
//     OmniMP4SegmentBuffer + demuxMP4Fragment (codecs and limits as for MSE).
// AES-128 (4.3.2.4): whole-segment CBC with PKCS#7 padding.
#pragma once
#include "OmniMP4Demuxer.h"
#include <cstdint>
#include <string>
#include <vector>

namespace OmniMedia::Hls {

enum class Container { TransportStream, PackedAudio, Fmp4, Unknown };
Container sniff(const std::vector<uint8_t>&);

struct Demuxed {
    std::vector<DemuxTrack> tracks;      // TS / packed audio: id 1 = video, 2 = audio
    std::vector<DemuxPacket> packets;    // decode order per track
    std::string error;
    bool timestamped = true;             // packed audio without an ID3 timestamp: false (starts at 0)
};

bool demuxTransportStream(const std::vector<uint8_t>& bytes, Demuxed&);
bool demuxPackedAudio(const std::vector<uint8_t>& bytes, Demuxed&);
bool demuxFmp4(const std::vector<uint8_t>& init, const std::vector<uint8_t>& segment, Demuxed&);

// In place; false on a bad length or padding.
bool decryptAes128(std::vector<uint8_t>& data, const uint8_t key[16], const uint8_t iv[16]);

// Helpers, public for the tests.
// Annex B access unit -> 4-byte length-prefixed NAL units (AUD and filler dropped).
std::vector<uint8_t> annexBToLengthPrefixed(const uint8_t*, size_t);
// avcC from the first SPS / PPS of an Annex B access unit; empty if it has none.
std::vector<uint8_t> avcCFromAnnexB(const uint8_t*, size_t);
// ADTS header: AudioSpecificConfig, sample rate, channels, header and frame length.
struct Adts { int objectType = 0, sampleRate = 0, channels = 0, headerLength = 0, frameLength = 0, rawBlocks = 1; std::vector<uint8_t> asc; };
bool parseAdts(const uint8_t*, size_t, Adts&);

}
