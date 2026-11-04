#!/usr/bin/env python3
"""Host-only generated audio fixtures, no downloads or production build edits."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='omni-audio-decoder-') as directory:
    tmp = Path(directory)
    paths = []
    for name, rate, codec, extra in (
        ('aac.m4a', 44100, 'aac', []),
        ('fragmented.mp4', 48000, 'aac', ['-movflags', 'frag_keyframe+empty_moov']),
        ('opus.webm', 48000, 'libopus', []),
    ):
        path = tmp / name
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
            f'sine=frequency=440:sample_rate={rate}:duration=1', '-ac', '2',
            '-c:a', codec, *extra, str(path)], check=True)
        paths.append(str(path))
    flags = subprocess.check_output(['pkg-config', '--cflags', '--libs',
        'libavformat', 'libavcodec', 'libswresample', 'libavutil'], text=True).split()
    executable = tmp / 'test'
    subprocess.run(['c++', '-std=c++17', '-O1', '-g', '-fsanitize=address,undefined',
        str(root / 'media/OmniAudioDecoder.cpp'), str(root / 'selftest/audio_decoder_test.cpp'),
        *flags, '-o', str(executable)], check=True)
    subprocess.run([str(executable), *paths], check=True)
