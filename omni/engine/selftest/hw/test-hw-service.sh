#!/bin/sh
# Two-process hardware-decode test on a Linux host (ASan/UBSan). The service
# process runs the real OmniHwService/OmniHwBackend against an FFmpeg-backed
# libSceVideodec2 stand-in; the client process uses PacketDecoder/Hw::Client.
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
m="$here/../../media"
tmp=$(mktemp -d /tmp/omni-hw-service.XXXXXX); trap 'rm -rf "$tmp"' EXIT HUP INT TERM
san="-fsanitize=address,undefined -fno-sanitize-recover=all"
cc -O1 -g -shared -fPIC "$here/mock_videodec2.c" -o "$tmp/libSceVideodec2.sprx" $(pkg-config --cflags --libs libavcodec)
cc -O1 -g $san -c "$here/mock_kernel.c" -o "$tmp/mock_kernel.o"
c++ -std=c++17 -O1 -g $san -Wall -Wextra \
  "$m/OmniHwService.cpp" "$m/OmniHwBackend.cpp" "$m/OmniHwClient.cpp" "$m/OmniHwBitstream.cpp" \
  "$m/OmniPacketDecoder.cpp" "$m/OmniMP4Demuxer.cpp" "$here/hw-service-test.cpp" "$tmp/mock_kernel.o" \
  $(pkg-config --cflags --libs libavformat libavcodec libavutil libswresample libswscale) -ldl -lpthread -o "$tmp/test"
python3 "$here/../mse/packet-bframes-fixture.py" "$tmp/bframes"
src="-f lavfi -i testsrc2=size=640x360:rate=30 -frames:v 60"
ffmpeg -v error $src -c:v libx265 -x265-params log-level=error:keyint=24 -tag:v hvc1 "$tmp/hevc.mp4"
ffmpeg -v error $src -c:v libx265 -pix_fmt yuv420p10le -profile:v main10 -x265-params log-level=error "$tmp/hevc10.mp4"
ffmpeg -v error $src -c:v libvpx-vp9 -b:v 4M -deadline realtime -cpu-used 8 -auto-alt-ref 1 -lag-in-frames 16 -g 60 -row-mt 1 "$tmp/vp9.webm"
ffmpeg -v error $src -c:v libvpx-vp9 -b:v 4M -pix_fmt yuv420p10le -profile:v 2 -deadline realtime -cpu-used 8 -auto-alt-ref 1 -lag-in-frames 16 -g 60 -row-mt 1 "$tmp/vp9p2.webm"
mkdir "$tmp/rv"
OMNI_HW_DIR="$tmp/rv" LD_LIBRARY_PATH="$tmp" ASAN_OPTIONS=detect_leaks=0 timeout ${TEST_TIMEOUT:-600} \
  "$tmp/test" "$here/../mse/generated" "$tmp/bframes" "$tmp/hevc.mp4" "$tmp/hevc10.mp4" "$tmp/vp9.webm" "$tmp/vp9p2.webm"
