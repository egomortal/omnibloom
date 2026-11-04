#!/usr/bin/env python3
"""Generate original four-second separate-track H.264/AAC fMP4 fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60).stdout


def generate(output, width, height, level, video_bitrate):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise RuntimeError(f'Refusing to overwrite nonempty fixture directory: {output}')
    level_tenths = round(float(level) * 10)
    if (not width or not height or width % 2 or height % 2 or
            level_tenths < 10 or level_tenths > 62):
        raise ValueError('Width/height must be positive even numbers and H.264 level must be 1.0–6.2.')

    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
         '-f', 'lavfi', '-i', f'testsrc2=size={width}x{height}:rate=30',
         '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
         '-t', '4', '-map', '0:v', '-map', '1:a',
         '-c:v', 'libx264', '-profile:v', 'baseline', '-level:v', level,
         '-pix_fmt', 'yuv420p', '-g', '30', '-keyint_min', '30', '-sc_threshold', '0',
         '-b:v', video_bitrate, '-c:a', 'aac', '-b:a', '64k', '-ac', '2',
         '-f', 'dash', '-seg_duration', '1', '-use_template', '1', '-use_timeline', '1',
         '-adaptation_sets', 'id=0,streams=v id=1,streams=a',
         '-init_seg_name', 'init-$RepresentationID$.mp4',
         '-media_seg_name', 'segment-$RepresentationID$-$Number%05d$.m4s',
         str(output / 'stream.mpd')])

    manifest = {'duration': 4, 'originalContent': 'FFmpeg testsrc2 and 440 Hz sine',
                'tracks': [], 'ffmpegVersion': run(['ffmpeg', '-version']).splitlines()[0],
                'generation': {'width': width, 'height': height,
                               'h264Level': level, 'videoBitrate': video_bitrate}}
    for ident, kind, codec in [('0', 'video', 'avc1.42c01e'), ('1', 'audio', 'mp4a.40.2')]:
        init = output / f'init-{ident}.mp4'
        segments = sorted(output.glob(f'segment-{ident}-*.m4s'))
        assert 3 <= len(segments) <= 6, (kind, len(segments))
        files = [init] + segments
        blob = b''.join(path.read_bytes() for path in files)
        assert len(blob) < 4 * 1024 * 1024
        with tempfile.NamedTemporaryFile(suffix='.mp4') as joined:
            joined.write(blob)
            joined.flush()
            probe = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                   '-of', 'json', joined.name]))
        stream = probe['streams'][0]
        assert len(probe['streams']) == 1 and stream['codec_type'] == kind
        assert stream['codec_name'] == ('h264' if kind == 'video' else 'aac')
        assert 3.9 <= float(probe['format']['duration']) <= 4.2
        track_probe = {'codec': stream['codec_name'], 'duration': probe['format']['duration']}
        if kind == 'video':
            assert (stream['width'], stream['height'], stream['level']) == (width, height, level_tenths)
            data = init.read_bytes()
            offset = data.index(b'avcC') + 4
            actual = f'avc1.{data[offset + 1:offset + 4].hex()}'
            codec = actual
            track_probe.update({'width': stream['width'], 'height': stream['height'],
                                'level': stream['level']})
        manifest['tracks'].append({'kind': kind, 'mime': f'{kind}/mp4; codecs="{codec}"',
                                   'init': init.name, 'segments': [path.name for path in segments],
                                   'files': {path.name: {'bytes': path.stat().st_size,
                                                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                                             for path in files},
                                   'probe': track_probe})
    manifest_path = output / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    total_bytes = sum(path.stat().st_size for path in output.iterdir() if path.is_file())
    if total_bytes >= 8 * 1024 * 1024:
        raise RuntimeError(f'Fixture directory exceeds 8 MiB quota: {total_bytes} bytes')
    print(json.dumps({'result': 'PASS', 'tracks': len(manifest['tracks']),
                      'width': width, 'height': height, 'h264Level': level_tenths,
                      'bytes': total_bytes}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'generated')
    parser.add_argument('--width', type=int, default=320)
    parser.add_argument('--height', type=int, default=180)
    parser.add_argument('--level', default='3.0')
    parser.add_argument('--video-bitrate', default='350k')
    args = parser.parse_args(argv)
    generate(args.output, args.width, args.height, args.level, args.video_bitrate)


if __name__ == '__main__':
    main()
