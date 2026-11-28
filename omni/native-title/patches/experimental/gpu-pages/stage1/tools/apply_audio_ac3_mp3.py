#!/usr/bin/env python3
"""OMNI_AUDIO_AC3_MP3_V1 (2026-11-25, owner: "is there any types we might be missing").

Page video and native HLS took AAC and Opus audio only: a stream whose audio is AC-3 (Dolby Digital, "ac-3" /
mp4a.a5), E-AC-3 (Dolby Digital Plus, "ec-3" / mp4a.a6) or MP3 (mp4a.6b / mp4a.69 / HLS mp4a.40.34) was refused
(isTypeSupported "no", "Unsupported track codec", "no H.264 or AAC in the segment"), so sites that offer only
those (IPTV-style HLS in MPEG-TS, some film sites' Dolby tracks) played no audio or nothing at all. The FFmpeg 7.1.5
in Omni (omni-seclibs) already has the ac3, eac3 and mp3 decoders and parsers; PacketDecoder resamples any layout
(5.1 / 7.1 included) to 48 kHz stereo, so only the demuxers and the capability answers change:
  media/OmniMP4Demuxer.h      DemuxCodec AC3 / EAC3 / MP3 (appended) + the kill switch
  media/OmniMP4Demuxer.cpp    fMP4 / MP4 (MSE, HLS EXT-X-MAP): 'ac-3' / 'ec-3' / '.mp3' tracks (no codec config)
  media/OmniHlsSegment.cpp    MPEG-TS segments: AC-3 / E-AC-3 / MP3 PES (rate, channels, frame sizes read here)
  media/OmniPacketDecoder.cpp FFmpeg ids; these three need no codec configuration
  media/OmniMediaCaps.h       MSE isTypeSupported for video/mp4 + audio/mp4
  media/OmniHlsSession.cpp    HLS variants listing these codecs are playable
  entry/OmniMSESource.cpp     track descriptions
Kill switch: /data/omni/audio-ac3-mp3-off.flag (everything back to AAC / Opus only).
Apply after OMNI_HLS_H264_LARGE_V1 (independent edits; order only matters for the recipes' logs).
usage: apply_audio_ac3_mp3.py <tree root holding engine/media and engine/entry>"""
import sys
from pathlib import Path

MARK = 'OMNI_AUDIO_AC3_MP3_V1'
root = Path(sys.argv[1]) / 'engine'
FLAG = '/data/omni/audio-ac3-mp3-off.flag'


def patch(rel, edits):
    p = root / rel
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    s = raw.replace('\r\n', '\n')
    if MARK in s:
        return rel + ': already'
    for old, new in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (rel, s.count(old), old[:100]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    return rel + ': applied'


out = []
out.append(patch('media/OmniMP4Demuxer.h', [
    ('enum class DemuxCodec { H264, AAC, VP9, Opus, Vorbis, HEVC };\n',
     'enum class DemuxCodec { H264, AAC, VP9, Opus, Vorbis, HEVC, AC3, EAC3, MP3 }; // ' + MARK + ': + AC3, EAC3, MP3 (appended)\n'
     '// ' + MARK + ': AC-3 / E-AC-3 / MP3 audio (MP4, MPEG-TS); off with ' + FLAG + '\n'
     'inline bool omniExtraAudioEnabled() { static const bool on = access("' + FLAG + '", F_OK) != 0; return on; }\n'
     'inline bool omniNoConfigAudio(DemuxCodec c) { return c == DemuxCodec::AC3 || c == DemuxCodec::EAC3 || c == DemuxCodec::MP3; } // ' + MARK + '\n'),
]))
out.append(patch('media/OmniMP4Demuxer.cpp', [
    ('av_dict_set(&options,"codec_whitelist","h264,aac,opus,hevc",0);',
     'av_dict_set(&options,"codec_whitelist","h264,aac,opus,hevc,ac3,eac3,mp3,mp3float",0); /* ' + MARK + ': + ac3, eac3, mp3 */'),
    ('        }else return fail("Unsupported track codec");\n',
     '        }else if(parameters->codec_type==AVMEDIA_TYPE_AUDIO&&omniExtraAudioEnabled()&&(parameters->codec_id==AV_CODEC_ID_AC3||parameters->codec_id==AV_CODEC_ID_EAC3||parameters->codec_id==AV_CODEC_ID_MP3)){\n'
     '            // ' + MARK + ': \'ac-3\' (dac3) / \'ec-3\' (dec3) / MP3 sample entries; FFmpeg keeps no extradata for them.\n'
     '            track.codec=parameters->codec_id==AV_CODEC_ID_AC3?DemuxCodec::AC3:parameters->codec_id==AV_CODEC_ID_EAC3?DemuxCodec::EAC3:DemuxCodec::MP3;\n'
     '            track.sampleRate=parameters->sample_rate;track.channels=parameters->ch_layout.nb_channels;\n'
     '            if(track.sampleRate<8000||track.sampleRate>192000||track.channels<1||track.channels>8)return fail("Audio dimensions unsupported");\n'
     '        }else return fail("Unsupported track codec");\n'),
    ('        if(parameters->extradata_size<=0||size_t(parameters->extradata_size)>limits.extraDataBytes',
     '        if((parameters->extradata_size<=0&&!omniNoConfigAudio(track.codec))||parameters->extradata_size<0||size_t(parameters->extradata_size)>limits.extraDataBytes'),
    ('        if(track==out.tracks.end()||(track->codec!=DemuxCodec::AAC&&track->codec!=DemuxCodec::Opus))return fail("Packet duration missing");',
     '        if(track==out.tracks.end()||(track->codec!=DemuxCodec::AAC&&track->codec!=DemuxCodec::Opus&&!omniNoConfigAudio(track->codec)))return fail("Packet duration missing"); /* ' + MARK + ': AC-3/E-AC-3/MP3 take the next-DTS step too */'),
]))
out.append(patch('media/OmniPacketDecoder.cpp', [
    ('case DemuxCodec::HEVC: return AV_CODEC_ID_HEVC;',
     'case DemuxCodec::HEVC: return AV_CODEC_ID_HEVC; case DemuxCodec::AC3: return AV_CODEC_ID_AC3; case DemuxCodec::EAC3: return AV_CODEC_ID_EAC3; case DemuxCodec::MP3: return AV_CODEC_ID_MP3; /* ' + MARK + ' */'),
    ('(track.extraData.empty() && track.codec != DemuxCodec::VP9)',
     '(track.extraData.empty() && track.codec != DemuxCodec::VP9 && !omniNoConfigAudio(track.codec)) /* ' + MARK + ' */'),
]))

HDR = r'''// OMNI_AUDIO_AC3_MP3_V1: an AC-3 / E-AC-3 / MP3 PES payload (one or more frames): the first frame's rate and
// channels, and the samples of all its independent frames (E-AC-3 dependent substreams add none).
static bool omniCodedAudio(AVCodecID id, const uint8_t* d, size_t n, int& rate, int& channels, int64_t& samples)
{
    static const int acmodChannels[8] = { 2, 1, 2, 3, 3, 4, 4, 5 };
    auto frame = [&](const uint8_t* f, size_t left, int& fr, int& fc, int& fs, size_t& bytes, bool& counts) -> bool {
        size_t bit = 0;
        auto get = [&](int k) { unsigned v = 0; while (k--) { v = (v << 1) | (bit < left * 8 ? (f[bit >> 3] >> (7 - (bit & 7))) & 1 : 0); ++bit; } return v; };
        counts = true;
        if (id == AV_CODEC_ID_MP3) {
            if (left < 4 || f[0] != 0xFF || (f[1] & 0xE0) != 0xE0) return false;
            const unsigned ver = (f[1] >> 3) & 3, layer = (f[1] >> 1) & 3, bri = f[2] >> 4, sri = (f[2] >> 2) & 3, pad = (f[2] >> 1) & 1, mode = f[3] >> 6;
            if (ver == 1 || layer != 1 || bri == 0 || bri == 15 || sri == 3) return false;   // layer III only
            static const int rates[3] = { 44100, 48000, 32000 };
            static const int v1[15] = { 0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320 };
            static const int v2[15] = { 0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160 };
            fr = rates[sri] >> (ver == 3 ? 0 : ver == 2 ? 1 : 2);
            fc = mode == 3 ? 1 : 2; fs = ver == 3 ? 1152 : 576;
            bytes = size_t((ver == 3 ? 144 : 72) * (ver == 3 ? v1[bri] : v2[bri]) * 1000 / fr + pad);
            return bytes >= 4;
        }
        if (left < 7 || f[0] != 0x0B || f[1] != 0x77) return false;
        const unsigned bsid = (f[5] >> 3) & 0x1f;
        get(16);
        if (bsid <= 10) {   // AC-3
            get(16);
            const unsigned fscod = get(2), frmsizecod = get(6);
            if (fscod == 3 || frmsizecod > 37) return false;
            get(5); get(3);
            const unsigned acmod = get(3);
            if ((acmod & 1) && acmod != 1) get(2);
            if (acmod & 4) get(2);
            if (acmod == 2) get(2);
            const unsigned lfe = get(1);
            static const int kbps[19] = { 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640 };
            const int br = kbps[frmsizecod >> 1];
            bytes = 2 * (fscod == 0 ? size_t(2 * br) : fscod == 2 ? size_t(3 * br) : size_t(br * 320 / 147 + (frmsizecod & 1)));
            fr = fscod == 0 ? 48000 : fscod == 1 ? 44100 : 32000; fc = acmodChannels[acmod] + int(lfe); fs = 1536;
            return true;
        }
        if (bsid < 11 || bsid > 16) return false;   // E-AC-3
        const unsigned strmtyp = get(2); get(3);
        const unsigned frmsiz = get(11), fscod = get(2);
        unsigned numblkscod = 3;
        if (fscod == 3) { const unsigned fscod2 = get(2); if (fscod2 == 3) return false; fr = fscod2 == 0 ? 24000 : fscod2 == 1 ? 22050 : 16000; }
        else { numblkscod = get(2); fr = fscod == 0 ? 48000 : fscod == 1 ? 44100 : 32000; }
        const unsigned acmod = get(3), lfe = get(1);
        static const int blocks[4] = { 1, 2, 3, 6 };
        fc = acmodChannels[acmod] + int(lfe); fs = blocks[numblkscod] * 256; bytes = (size_t(frmsiz) + 1) * 2;
        counts = strmtyp != 1;   // a dependent substream belongs to the frame before it
        return true;
    };
    size_t at = 0;
    samples = 0; rate = 0; channels = 0;
    while (at < n) {
        int fr = 0, fc = 0, fs = 0; size_t bytes = 0; bool counts = true;
        if (!frame(d + at, n - at, fr, fc, fs, bytes, counts)) break;
        if (!rate) { rate = fr; channels = fc; }
        if (counts) samples += fs;
        at += bytes;
    }
    return rate >= 8000 && channels >= 1 && samples > 0;
}

'''
TS = r'''        } else if ((id == AV_CODEC_ID_AC3 || id == AV_CODEC_ID_EAC3 || id == AV_CODEC_ID_MP3) && omniExtraAudioEnabled()
                   && (audioIndex < 0 || audioIndex == pkt->stream_index) && pkt->size > 0) {   // OMNI_AUDIO_AC3_MP3_V1
            audioIndex = pkt->stream_index;
            int64_t pts = pkt->pts != AV_NOPTS_VALUE ? pkt->pts : pkt->dts;
            if (pts == AV_NOPTS_VALUE)
                for (size_t j = out.packets.size(); j-- > 0;)
                    if (out.packets[j].trackId == 2) { pts = out.packets[j].pts + out.packets[j].duration; break; }
            int rate = 0, channels = 0; int64_t samples = 0;
            if (pts != AV_NOPTS_VALUE && omniCodedAudio(id, pkt->data, size_t(pkt->size), rate, channels, samples)) {
                const DemuxCodec codec = id == AV_CODEC_ID_AC3 ? DemuxCodec::AC3 : id == AV_CODEC_ID_EAC3 ? DemuxCodec::EAC3 : DemuxCodec::MP3;
                const bool hadAudio = audio != nullptr;
                if (!audio) {
                    DemuxTrack t;
                    t.id = 2; t.codec = codec; t.timeBase = { 1, 90000 }; t.sampleRate = rate; t.channels = channels;
                    out.tracks.push_back(t);
                    audio = &out.tracks.back();
                } else if (audio->codec != codec) { av_packet_unref(pkt); cleanup(); return fail("audio codec changes inside a segment"); }
                DemuxPacket p;
                p.trackId = 2; p.timeBase = { 1, 90000 }; p.pts = p.dts = pts; p.keyFrame = true;
                p.duration = pkt->duration > 0 ? pkt->duration : (samples * 90000 + rate / 2) / rate;
                p.durationSource = DemuxDurationSource::AudioCodecSamples;
                p.bytes.assign(pkt->data, pkt->data + pkt->size);
                if (out.packets.size() >= maxPackets) { av_packet_unref(pkt); cleanup(); return fail("too many packets in a segment"); }
                out.packets.push_back(std::move(p));
                if (!hadAudio && audio && video) video = &out.tracks.front();
            }
        } else if (id == AV_CODEC_ID_AAC && (audioIndex < 0 || audioIndex == pkt->stream_index) && pkt->size > 0) {
'''
out.append(patch('media/OmniHlsSegment.cpp', [
    ('// One ADTS buffer (several frames) -> audio packets from `pts` on ({1,90000}).\n',
     HDR + '// One ADTS buffer (several frames) -> audio packets from `pts` on ({1,90000}).\n'),
    ('    av_dict_set(&options, "codec_whitelist", "h264,aac", 0);\n',
     '    av_dict_set(&options, "codec_whitelist", "h264,aac,ac3,eac3,mp3,mp3float", 0);   // ' + MARK + ': + ac3, eac3, mp3\n'),
    ('        } else if (id == AV_CODEC_ID_AAC && (audioIndex < 0 || audioIndex == pkt->stream_index) && pkt->size > 0) {\n', TS),
]))
out.append(patch('media/OmniMediaCaps.h', [
    ('#include <vector>\n',
     '#include <vector>\n#include <cstdio> // ' + MARK + ': fopen (kill switch)\n'),
    ('inline bool mp3InMp4(std::string_view codec) {',
     '// ' + MARK + ': AC-3 / E-AC-3 in MP4 (FFmpeg ac3 / eac3); off with ' + FLAG + '\n'
     'inline bool extraAudioOn() { static const bool on = [] { FILE* f = fopen("' + FLAG + '", "r"); if (f) { fclose(f); return false; } return true; }(); return on; }\n'
     'inline bool ac3Codec(std::string_view codec) { auto l = lowered(codec); return l == "ac-3" || l == "mp4a.a5"; }\n'
     'inline bool eac3Codec(std::string_view codec) { auto l = lowered(codec); return l == "ec-3" || l == "mp4a.a6"; }\n'
     'inline bool mp3InMp4(std::string_view codec) {'),
    ('    if (aacSupported(codec)) return container == "video/mp4" || container == "audio/mp4";\n    return container == "video/mp4" && avc1Supported(codec);\n',
     '    if (extraAudioOn() && (ac3Codec(codec) || eac3Codec(codec) || mp3InMp4(codec))) return container == "video/mp4" || container == "audio/mp4"; // ' + MARK + '\n'
     '    if (aacSupported(codec)) return container == "video/mp4" || container == "audio/mp4";\n    return container == "video/mp4" && avc1Supported(codec);\n'),
]))
out.append(patch('media/OmniHlsSession.cpp', [
    ('    if (Caps::opusCodec(codec)) return true;   // fMP4 \'Opus\' (FFmpeg\'s native decoder)\n',
     '    if (Caps::opusCodec(codec)) return true;   // fMP4 \'Opus\' (FFmpeg\'s native decoder)\n'
     '    if (Caps::extraAudioOn() && (Caps::ac3Codec(codec) || Caps::eac3Codec(codec) || Caps::mp3InMp4(codec) || low == "mp4a.40.34")) return true; // ' + MARK + '\n'),
]))
out.append(patch('entry/OmniMSESource.cpp', [
    (': codec == OmniMedia::DemuxCodec::HEVC ? "hvc1"_s : "vorb"_s)',
     ': codec == OmniMedia::DemuxCodec::HEVC ? "hvc1"_s : codec == OmniMedia::DemuxCodec::AC3 ? "ac-3"_s : codec == OmniMedia::DemuxCodec::EAC3 ? "ec-3"_s : codec == OmniMedia::DemuxCodec::MP3 ? "mp4a.6b"_s : "vorb"_s) /* ' + MARK + ' */'),
]))
print('; '.join(out), MARK)
