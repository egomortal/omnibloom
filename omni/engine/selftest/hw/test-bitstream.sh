#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d /tmp/omni-hw-bitstream.XXXXXX); trap 'rm -rf "$tmp"' EXIT HUP INT TERM
src="-f lavfi -i testsrc2=size=320x240:rate=30 -frames:v 60"
ffmpeg -v error $src -c:v libx264 -bf 3 -g 24 "$tmp/avc.mp4"
ffmpeg -v error $src -c:v libx264 -bf 0 -g 12 -movflags +frag_keyframe+empty_moov "$tmp/avc-frag.mp4"
ffmpeg -v error $src -c:v libx265 -x265-params log-level=error:keyint=24 -tag:v hvc1 "$tmp/hevc.mp4"
ffmpeg -v error $src -c:v libx265 -pix_fmt yuv420p10le -profile:v main10 -x265-params log-level=error "$tmp/hevc10.mp4"
ffmpeg -v error $src -c:v libvpx-vp9 -b:v 4M -deadline realtime -cpu-used 8 -auto-alt-ref 1 -lag-in-frames 16 -g 60 -row-mt 1 "$tmp/vp9.webm"
ffmpeg -v error $src -c:v libvpx-vp9 -b:v 4M -pix_fmt yuv420p10le -profile:v 2 -deadline realtime -cpu-used 8 -auto-alt-ref 1 -lag-in-frames 16 -g 60 -row-mt 1 "$tmp/vp9p2.mp4"
c++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all \
  "$here/../../media/OmniHwBitstream.cpp" "$here/bitstream-test.cpp" \
  $(pkg-config --cflags --libs libavformat libavcodec libavutil) -o "$tmp/test"
"$tmp/test" "$tmp/avc.mp4" "$tmp/avc-frag.mp4" "$tmp/hevc.mp4" "$tmp/hevc10.mp4" "$tmp/vp9.webm" "$tmp/vp9p2.mp4"
