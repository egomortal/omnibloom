// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniHwBitstream.h"
#include <algorithm> // OMNI_HOLEPUNCH_COLOUR_V1

namespace OmniMedia::Hw {
namespace {
const uint8_t startCode[4] = { 0, 0, 0, 1 };

bool fail(std::string& error, const char* text) { error = text; return false; }

void appendNal(std::vector<uint8_t>& out, const uint8_t* nal, size_t size)
{
    out.insert(out.end(), startCode, startCode + 4);
    out.insert(out.end(), nal, nal + size);
}

int nalType(Codec codec, uint8_t firstByte)
{
    return codec == Codec::H264 ? (firstByte & 0x1f) : ((firstByte >> 1) & 0x3f);
}

// OMNI_HOLEPUNCH_COLOUR_V1: RBSP bit reader (emulation prevention bytes removed); reads past the
// end set `bad` and return 0.
struct Bits {
    std::vector<uint8_t> b;
    size_t pos = 0;
    bool bad = false;
    Bits(const uint8_t* d, size_t n)
    {
        int zeros = 0;
        for (size_t i = 0; i < n; i++) {
            if (zeros >= 2 && d[i] == 3) { zeros = 0; continue; }
            b.push_back(d[i]);
            zeros = d[i] ? 0 : zeros + 1;
        }
    }
    unsigned u(int n)
    {
        unsigned v = 0;
        while (n-- > 0) {
            if (pos >= b.size() * 8) { bad = true; return 0; }
            v = (v << 1) | ((b[pos >> 3] >> (7 - (pos & 7))) & 1u);
            pos++;
        }
        return v;
    }
    void skip(size_t n) { pos += n; if (pos > b.size() * 8) bad = true; }
    unsigned ue()
    {
        int zeros = 0;
        while (!u(1)) { if (bad || ++zeros > 31) { bad = true; return 0; } }
        return zeros ? (1u << zeros) - 1 + u(zeros) : 0;
    }
    int se() { const unsigned k = ue(); return k & 1 ? int((k + 1) / 2) : -int(k / 2); }
};

// VUI up to colour_description (identical prefix in H.264 E.1.1 and H.265 E.2.1).
VideoColour vuiColour(Bits& r)
{
    VideoColour c;
    if (r.u(1) && r.u(8) == 255) r.skip(32);       // aspect_ratio_info: idc, Extended_SAR
    if (r.u(1)) r.u(1);                            // overscan_info
    if (r.u(1)) {                                  // video_signal_type_present_flag
        r.u(3);                                    // video_format
        const int full = int(r.u(1));
        int matrix = -1;
        if (r.u(1)) { r.u(8); r.u(8); matrix = int(r.u(8)); }   // primaries, transfer, matrix_coefficients
        if (!r.bad) { c.fullRange = full; c.matrix = matrix; }
    }
    return r.bad ? VideoColour {} : c;
}

void scalingList(Bits& r, int size)                // H.264 7.3.2.1.1.1
{
    int last = 8, next = 8;
    for (int j = 0; j < size && !r.bad; j++) {
        if (next) next = (last + r.se() + 256) % 256;
        last = next ? next : last;
    }
}

VideoColour h264SpsColour(Bits& r)                 // H.264 7.3.2.1.1
{
    const unsigned profile = r.u(8);
    r.u(16); r.ue();                               // constraint flags + level, seq_parameter_set_id
    if (profile == 100 || profile == 110 || profile == 122 || profile == 244 || profile == 44 || profile == 83
        || profile == 86 || profile == 118 || profile == 128 || profile == 138 || profile == 139 || profile == 134 || profile == 135) {
        const unsigned chroma = r.ue();
        if (chroma == 3) r.u(1);
        r.ue(); r.ue(); r.u(1);                    // bit depths, qpprime_y_zero_transform_bypass
        if (r.u(1))
            for (int i = 0; i < (chroma != 3 ? 8 : 12) && !r.bad; i++)
                if (r.u(1)) scalingList(r, i < 6 ? 16 : 64);
    }
    r.ue();                                        // log2_max_frame_num_minus4
    const unsigned poc = r.ue();
    if (poc == 0) r.ue();
    else if (poc == 1) {
        r.u(1); r.se(); r.se();
        const unsigned n = r.ue();
        if (n > 255) return {};
        for (unsigned i = 0; i < n && !r.bad; i++) r.se();
    }
    r.ue(); r.u(1); r.ue(); r.ue();                // max_num_ref_frames, gaps, width, height in MBs
    if (!r.u(1)) r.u(1);                           // frame_mbs_only, mb_adaptive_frame_field
    r.u(1);                                        // direct_8x8_inference
    if (r.u(1)) { r.ue(); r.ue(); r.ue(); r.ue(); }   // frame_cropping
    if (r.bad || !r.u(1)) return {};               // vui_parameters_present_flag
    return vuiColour(r);
}

VideoColour hevcSpsColour(Bits& r)                 // H.265 7.3.2.2.1
{
    r.u(4);
    const unsigned maxSub = r.u(3);
    r.u(1);
    // profile_tier_level(1, maxSub): 96 bits of general profile/level, then sub-layers.
    r.skip(96);
    bool profilePresent[8] = {}, levelPresent[8] = {};
    for (unsigned i = 0; i < maxSub; i++) { profilePresent[i] = r.u(1); levelPresent[i] = r.u(1); }
    if (maxSub) for (unsigned i = maxSub; i < 8; i++) r.u(2);
    for (unsigned i = 0; i < maxSub; i++) { if (profilePresent[i]) r.skip(88); if (levelPresent[i]) r.u(8); }
    r.ue();                                        // sps_seq_parameter_set_id
    if (r.ue() == 3) r.u(1);                       // chroma_format_idc, separate_colour_plane
    r.ue(); r.ue();                                // pic width, height
    if (r.u(1)) { r.ue(); r.ue(); r.ue(); r.ue(); }   // conformance_window
    r.ue(); r.ue();                                // bit depths
    const unsigned pocBits = r.ue() + 4;           // log2_max_pic_order_cnt_lsb_minus4
    if (pocBits > 16) return {};
    for (unsigned i = r.u(1) ? 0 : maxSub; i <= maxSub && !r.bad; i++) { r.ue(); r.ue(); r.ue(); }
    r.ue(); r.ue(); r.ue(); r.ue(); r.ue(); r.ue();   // coding/transform block sizes and depths
    if (r.u(1) && r.u(1)) {                        // scaling_list_enabled, sps_scaling_list_data_present
        for (int size = 0; size < 4; size++)
            for (int m = 0; m < 6; m += size == 3 ? 3 : 1) {
                if (!r.u(1)) { r.ue(); continue; }    // scaling_list_pred_mode_flag
                const int coefs = std::min(64, 1 << (4 + (size << 1)));
                if (size > 1) r.se();
                for (int k = 0; k < coefs && !r.bad; k++) r.se();
            }
    }
    r.u(1); r.u(1);                                // amp, sample_adaptive_offset
    if (r.u(1)) { r.u(4); r.u(4); r.ue(); r.ue(); r.u(1); }   // pcm
    const unsigned sets = r.ue();
    if (sets > 64) return {};
    unsigned deltaPocs[65] = {};
    for (unsigned i = 0; i < sets && !r.bad; i++) {   // st_ref_pic_set(i), 7.3.7
        if (i && r.u(1)) {                            // inter_ref_pic_set_prediction_flag
            r.u(1); r.ue();                           // delta_rps_sign, abs_delta_rps_minus1
            unsigned count = 0;
            for (unsigned j = 0; j <= deltaPocs[i - 1] && !r.bad; j++) {
                const bool used = r.u(1);
                if (used || r.u(1)) count++;          // used_by_curr_pic_flag, use_delta_flag
            }
            deltaPocs[i] = count;
        } else {
            const unsigned neg = r.ue(), pos = r.ue();
            if (neg > 16 || pos > 16) return {};
            for (unsigned k = 0; k < neg + pos && !r.bad; k++) { r.ue(); r.u(1); }
            deltaPocs[i] = neg + pos;
        }
    }
    if (r.u(1)) {                                  // long_term_ref_pics_present
        const unsigned n = r.ue();
        if (n > 32) return {};
        for (unsigned i = 0; i < n && !r.bad; i++) { r.u(int(pocBits)); r.u(1); }
    }
    r.u(1); r.u(1);                                // temporal_mvp, strong_intra_smoothing
    if (r.bad || !r.u(1)) return {};               // vui_parameters_present_flag
    return vuiColour(r);
}
}

VideoColour spsColour(Codec codec, const uint8_t* nal, size_t size)   // OMNI_HOLEPUNCH_COLOUR_V1
{
    const size_t header = codec == Codec::HEVC ? 2 : 1;
    if (!nal || size <= header || codec == Codec::VP9) return {};
    Bits r(nal + header, size - header);
    return codec == Codec::H264 ? h264SpsColour(r) : hevcSpsColour(r);
}

bool parseAvcC(const uint8_t* d, size_t n, NalConfig& c, std::string& error)
{
    c = {};
    if (!d || n < 7 || d[0] != 1) return fail(error, "avcC header");
    c.profile = d[1]; c.level = d[3];
    c.lengthSize = (d[4] & 3) + 1;
    if (c.lengthSize == 3) return fail(error, "avcC length size 3");
    size_t p = 5;
    for (int set = 0; set < 2; set++) {
        if (p >= n) return fail(error, "avcC truncated count");
        unsigned count = set == 0 ? (d[p] & 0x1f) : d[p];
        p++;
        for (unsigned i = 0; i < count; i++) {
            if (p + 2 > n) return fail(error, "avcC truncated length");
            size_t len = (size_t(d[p]) << 8) | d[p + 1];
            p += 2;
            if (!len || len > n - p) return fail(error, "avcC parameter set bounds");
            appendNal(c.parameterSets, d + p, len);
            if (set == 0 && i == 0) c.colour = spsColour(Codec::H264, d + p, len);   // OMNI_HOLEPUNCH_COLOUR_V1
            p += len;
        }
        if (set == 0 && !count) return fail(error, "avcC has no SPS");
    }
    if (c.parameterSets.empty()) return fail(error, "avcC has no parameter sets");
    return true;
}

bool parseHvcC(const uint8_t* d, size_t n, NalConfig& c, std::string& error)
{
    c = {};
    if (!d || n < 23 || d[0] != 1) return fail(error, "hvcC header");
    c.profile = d[1] & 0x1f; c.level = d[12];
    c.bitDepth = (d[17] & 7) + 8;   // bitDepthLumaMinus8
    c.lengthSize = (d[21] & 3) + 1;
    if (c.lengthSize == 3) return fail(error, "hvcC length size 3");
    unsigned arrays = d[22];
    size_t p = 23;
    bool sps = false;
    for (unsigned a = 0; a < arrays; a++) {
        if (p + 3 > n) return fail(error, "hvcC truncated array");
        int type = d[p] & 0x3f;
        unsigned count = (unsigned(d[p + 1]) << 8) | d[p + 2];
        p += 3;
        for (unsigned i = 0; i < count; i++) {
            if (p + 2 > n) return fail(error, "hvcC truncated length");
            size_t len = (size_t(d[p]) << 8) | d[p + 1];
            p += 2;
            if (!len || len > n - p) return fail(error, "hvcC parameter set bounds");
            // VPS(32) SPS(33) PPS(34) only; SEI arrays are not needed to decode.
            if (type >= 32 && type <= 34) appendNal(c.parameterSets, d + p, len);
            if (type == 33 && !sps) c.colour = spsColour(Codec::HEVC, d + p, len);   // OMNI_HOLEPUNCH_COLOUR_V1
            sps |= type == 33;
            p += len;
        }
    }
    if (!sps) return fail(error, "hvcC has no SPS");
    return true;
}

bool looksLikeAnnexB(const uint8_t* d, size_t n)
{
    return n >= 4 && d[0] == 0 && d[1] == 0 && (d[2] == 1 || (d[2] == 0 && d[3] == 1));
}

bool lengthPrefixedToAnnexB(Codec codec, const NalConfig& c, const uint8_t* d, size_t n,
                            bool keyFrame, std::vector<uint8_t>& out, std::string& error)
{
    out.clear();
    if (codec == Codec::VP9) return fail(error, "VP9 has no NAL units");
    if (!d || !n) return fail(error, "empty sample");
    // First pass: validate framing and look for in-band SPS.
    bool hasSps = false;
    size_t nals = 0, payload = 0;
    for (size_t p = 0; p < n;) {
        if (n - p < size_t(c.lengthSize)) return fail(error, "truncated NAL length");
        size_t len = 0;
        for (int i = 0; i < c.lengthSize; i++) len = (len << 8) | d[p + i];
        p += size_t(c.lengthSize);
        if (!len || len > n - p) return fail(error, "NAL length out of bounds");
        int type = nalType(codec, d[p]);
        hasSps |= codec == Codec::H264 ? type == 7 : type == 33;
        nals++; payload += len;
        p += len;
    }
    const bool prepend = keyFrame && !hasSps;
    out.reserve((prepend ? c.parameterSets.size() : 0) + payload + nals * 4);
    if (prepend) out.insert(out.end(), c.parameterSets.begin(), c.parameterSets.end());
    for (size_t p = 0; p < n;) {
        size_t len = 0;
        for (int i = 0; i < c.lengthSize; i++) len = (len << 8) | d[p + i];
        p += size_t(c.lengthSize);
        appendNal(out, d + p, len);
        p += len;
    }
    return true;
}

namespace {
// VP9 uncompressed header prefix (spec 6.2): frame_marker, profile,
// show_existing_frame, frame_type, show_frame.
bool vp9Shown(const uint8_t* d, size_t n, bool& shown)
{
    if (n < 1) return false;
    unsigned bits = (unsigned(d[0]) << 8) | (n > 1 ? d[1] : 0);
    int i = 15;
    auto rd = [&] { return (bits >> i--) & 1u; };
    if (rd() != 1 || rd() != 0) return false;      // frame_marker
    unsigned profile = rd(); profile |= rd() << 1;
    if (profile == 3) rd();                        // reserved_zero
    if (rd()) { shown = true; return true; }       // show_existing_frame
    rd();                                          // frame_type
    shown = rd();                                  // show_frame
    return true;
}
}

bool splitVp9(const uint8_t* d, size_t n, std::vector<Vp9Frame>& frames, std::string& error)
{
    frames.clear();
    if (!d || !n) return fail(error, "empty VP9 packet");
    uint8_t marker = d[n - 1];
    if ((marker & 0xe0) == 0xc0) {
        size_t count = (marker & 7) + 1, bytes = ((marker >> 3) & 3) + 1;
        size_t index = 2 + count * bytes;
        if (n >= index && d[n - index] == marker) {
            size_t p = 0;
            for (size_t k = 0; k < count; k++) {
                size_t s = 0;
                for (size_t b = 0; b < bytes; b++) s |= size_t(d[n - index + 1 + k * bytes + b]) << (8 * b);
                if (!s || s > n - index - p) return fail(error, "VP9 superframe size out of bounds");
                Vp9Frame f { p, s, true };
                if (!vp9Shown(d + p, s, f.shown)) return fail(error, "VP9 frame header");
                frames.push_back(f);
                p += s;
            }
            if (p != n - index) return fail(error, "VP9 superframe sizes do not cover packet");
            return true;
        }
    }
    Vp9Frame f { 0, n, true };
    if (!vp9Shown(d, n, f.shown)) return fail(error, "VP9 frame header");
    frames.push_back(f);
    return true;
}

bool vp9KeyFrameInfo(const uint8_t* d, size_t n, int& profile, int& bitDepth)
{
    if (!d || n < 5) return false;
    size_t bit = 0;
    auto rd = [&]() -> unsigned { unsigned v = (d[bit >> 3] >> (7 - (bit & 7))) & 1u; bit++; return v; };
    if (rd() != 1 || rd() != 0) return false;           // frame_marker
    profile = int(rd()); profile |= int(rd()) << 1;
    if (profile == 3) rd();
    if (rd()) return false;                              // show_existing_frame
    if (rd() != 0) return false;                         // frame_type: 0 = KEY_FRAME
    rd(); rd();                                          // show_frame, error_resilient_mode
    if (n * 8 < bit + 24 + 1) return false;
    unsigned sync = 0;
    for (int i = 0; i < 24; i++) sync = (sync << 1) | rd();
    if (sync != 0x498342) return false;                  // frame_sync_code
    bitDepth = profile >= 2 ? (rd() ? 12 : 10) : 8;      // color_config ten_or_twelve_bit
    return true;
}

// OMNI_HOLEPUNCH_COLOUR_V1: VP9 color_config (spec 6.2.2): color_space, color_range.
bool vp9KeyFrameColour(const uint8_t* d, size_t n, VideoColour& c)
{
    int profile = 0, depth = 8;
    if (!vp9KeyFrameInfo(d, n, profile, depth)) return false;
    size_t bit = 2 + 2 + (profile == 3) + 1 + 1 + 1 + 1 + 24 + (profile >= 2);   // as read above
    if (n * 8 < bit + 4) return false;
    auto rd = [&]() -> unsigned { unsigned v = (d[bit >> 3] >> (7 - (bit & 7))) & 1u; bit++; return v; };
    unsigned space = rd() << 2; space |= rd() << 1; space |= rd();
    static const int toH273[8] = { -1, 6, 1, 6, 7, 9, -1, -1 };   // UNKNOWN, BT_601, BT_709, SMPTE_170, SMPTE_240, BT_2020, RESERVED, RGB
    c = {};
    c.matrix = toH273[space];
    if (space != 7) c.fullRange = int(rd());
    return true;
}

int hevcFirstVclType(const NalConfig& c, const uint8_t* d, size_t n)
{
    for (size_t p = 0; d && p < n;) {
        if (n - p < size_t(c.lengthSize)) return -1;
        size_t len = 0;
        for (int i = 0; i < c.lengthSize; i++) len = (len << 8) | d[p + i];
        p += size_t(c.lengthSize);
        if (!len || len > n - p) return -1;
        int type = (d[p] >> 1) & 0x3f;
        if (type < 32) return type;
        p += len;
    }
    return -1;
}

}
