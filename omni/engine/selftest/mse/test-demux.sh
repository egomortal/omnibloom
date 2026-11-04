#!/usr/bin/env bash
set -eu
ulimit -c 0
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?Provide output directory}
mkdir -p "$out"
c++ -std=c++17 -Wall -Wextra -Werror -g -fsanitize=address,undefined \
 "$here/demux-test.cpp" "$here/../../media/OmniMP4Demuxer.cpp" \
 $(pkg-config --cflags --libs libavformat libavcodec libavutil) -o "$out/mp4-demux-test"
ASAN_OPTIONS=detect_leaks=1 "$out/mp4-demux-test" "$here/generated"
