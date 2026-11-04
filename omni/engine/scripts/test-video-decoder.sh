#!/usr/bin/env bash
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
root="$(cd "$(dirname "$0")/../.." && pwd)"
out="${1:?Provide an output directory}"
mkdir -p "$out"
if [ "${2:-video}" = audio ]; then
    ffmpeg -hide_banner -loglevel error -y -f lavfi -i 'testsrc2=size=320x180:rate=15' -f lavfi -i 'sine=frequency=440:sample_rate=48000' -t 2 -c:a aac -c:v libx264 -pix_fmt yuv420p "$out/media-test.mp4"
    ffmpeg -hide_banner -loglevel error -y -f lavfi -i 'testsrc2=size=320x180:rate=15' -f lavfi -i 'sine=frequency=440:sample_rate=48000' -t 2 -c:a libopus -c:v libvpx -b:v 300k "$out/media-test.webm"
else
    ffmpeg -hide_banner -loglevel error -y -f lavfi -i 'testsrc2=size=320x180:rate=15' -t 2 -an -c:v libx264 -pix_fmt yuv420p "$out/media-test.mp4"
    ffmpeg -hide_banner -loglevel error -y -f lavfi -i 'testsrc2=size=320x180:rate=15' -t 2 -an -c:v libvpx -b:v 300k "$out/media-test.webm"
fi
g++ -std=c++20 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$root/engine/media/OmniVideoDecoder.cpp" "$root/engine/selftest/video_decoder_test.cpp" \
    $(pkg-config --cflags --libs libavformat libavcodec libswscale libswresample libavutil) -o "$out/video-decoder-test"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
    "$out/video-decoder-test" "$out/media-test.mp4" "$out/media-test.webm"
