#!/bin/sh
set -eu
ulimit -c 0
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d /tmp/omni-packet-test.XXXXXX)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
c++ -std=c++17 -O1 -g -fsanitize=address,undefined \
  "$here/../../media/OmniMP4Demuxer.cpp" "$here/../../media/OmniPacketDecoder.cpp" \
  "$here/packet-decoder-test.cpp" \
  $(pkg-config --cflags --libs libavformat libavcodec libavutil libswresample libswscale) \
  -o "$tmp/test"
python3 "$here/packet-bframes-fixture.py" "$tmp/bframes"
"$tmp/test" "$tmp/bframes" require-bframes
"$tmp/test" "$here/generated"
# v53: BGRA conversion must equal RGBA with red/blue exchanged.
c++ -std=c++17 -O1 -g -fsanitize=address,undefined \
  "$here/../../media/OmniMP4Demuxer.cpp" "$here/../../media/OmniPacketDecoder.cpp" \
  "$here/packet-pixel-order-test.cpp" \
  $(pkg-config --cflags --libs libavformat libavcodec libavutil libswresample libswscale) \
  -o "$tmp/pixel-order"
"$tmp/pixel-order" "$here/generated"
