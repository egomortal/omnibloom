#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# OMNI_DL_FFMPEG_V1: the Downloads worker's FFmpeg, minimal LGPL-2.1-or-later configuration.
#
# The console worker (python-worker.elf, CPython + the _omni_native module) cannot start child
# processes (no fork/exec of unsigned ELFs on the console), so FFmpeg is linked IN-PROCESS as static
# libavformat/libavcodec/libavutil. Only what stream-copy work needs is enabled: local files, the
# containers yt-dlp hands us, parsers and the bitstream filters the muxers insert by themselves.
# The AAC decoders are only there for probing: ADTS headers (HLS/MPEG-TS) don't give a trustworthy
# sample rate, so avformat_find_stream_info decodes one frame. No encoders (never re-encodes), no
# network, no GPL or nonfree parts, no external libraries except zlib (permissive).
#
# Builds two prefixes from the same signed source tarball and the same configure line:
#   $W/ps5   - PS5 (prospero-clang, ps5-payload-sdk), linked into python-worker.elf
#   $W/host  - WSL host (cc), for the binding's unit/smoke tests (tests/test_native_ffmpeg.py)
# Usage: build-ffmpeg-lgpl.sh [ps5|host|both]   (default both). Build only; never deploys.
set -eo pipefail
cd /
L=/tmp/omni-dl-ffmpeg.lock; ( umask 0; : >> "$L" ) 2>/dev/null; exec 9<"$L"
flock -n 9 || { echo "another omni-dl-ffmpeg build is running"; exit 0; }

FF=7.1.5
SRC=${FF_SRC:-$HOME/omni-seclibs/src/ffmpeg-$FF.tar.xz}
SHA=de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f   # signed by FFmpeg release key FCF986EA15E6E293
W=${FF_WORK:-$HOME/omni-dl-ffmpeg}
NASM=${NASM:-$HOME/omni-seclibs/tools/bin/nasm}
J=$(nproc)
echo "$SHA  $SRC" | sha256sum -c - >/dev/null || { echo "source tarball hash mismatch"; exit 2; }

# The one configure line (target-independent part). Recorded in THIRD-PARTY-NOTICES.md.
COMMON=(
  --disable-gpl --disable-version3 --disable-nonfree
  --enable-static --disable-shared --disable-programs --disable-doc --disable-debug
  --disable-autodetect --disable-network --disable-everything
  --disable-avdevice --disable-avfilter --disable-swscale --disable-swresample --disable-postproc
  --enable-zlib
  --enable-protocol=file
  --enable-demuxer=mov,matroska,mpegts,aac,mp3,ogg,flac,wav,ac3,eac3
  --enable-muxer=mp4,mov,ipod,matroska,matroska_audio,webm
  --enable-parser=h264,hevc,av1,vp8,vp9,mpeg4video,aac,aac_latm,opus,vorbis,mpegaudio,ac3,flac
  --enable-bsf=aac_adtstoasc,vp9_superframe,extract_extradata
  --enable-decoder=aac,aac_latm
)

build() {   # $1 = ps5|host
  local kind=$1 prefix=$W/$1 bld=$W/build-$1 extra=()
  rm -rf "$bld" "$prefix"; mkdir -p "$bld"
  tar xJf "$SRC" -C "$bld"; cd "$bld/ffmpeg-$FF"
  if [ "$kind" = ps5 ]; then
    source /opt/ps5-payload-sdk/toolchain/prospero.sh
    unset DESTDIR   # the SDK points DESTDIR at its own sysroot; install into our private prefix instead
    extra=(--enable-cross-compile --cross-prefix="$PS5_PAYLOAD_SDK/bin/prospero-" --arch=x86_64 --target-os=freebsd
           --cc="$CC" --cxx="$CXX" --nm="$NM" --strip="$STRIP" --ar="$AR" --ranlib="$RANLIB" --pkg-config="$PKG_CONFIG")
    MK=${MAKE:-make}
  else
    MK=make
  fi
  if [ -x "$NASM" ]; then extra+=(--x86asmexe="$NASM"); else extra+=(--disable-x86asm); fi
  echo "== $(date -u +%T) configure $kind"
  ./configure --prefix="$prefix" "${COMMON[@]}" "${extra[@]}" > ../configure.log 2>&1 || { tail -40 ffbuild/config.log; exit 3; }
  grep -E '^CONFIG_(GPL|VERSION3|NONFREE|NETWORK|ZLIB)=|^!CONFIG_(GPL|VERSION3|NONFREE|NETWORK)=' ffbuild/config.mak
  grep -q '^!CONFIG_GPL=yes' ffbuild/config.mak && grep -q '^!CONFIG_NONFREE=yes' ffbuild/config.mak \
    && grep -q '^!CONFIG_VERSION3=yes' ffbuild/config.mak || { echo "licence check failed: not LGPL-2.1+"; exit 5; }
  echo "== $(date -u +%T) make $kind"
  $MK -j"$J" > ../build.log 2>&1 || { tail -40 ../build.log; exit 4; }
  $MK install > ../install.log 2>&1
  grep -m1 FFMPEG_VERSION "$prefix/include/libavutil/ffversion.h"
  ls -l "$prefix"/lib/lib*.a
  cp ffbuild/config.mak "$prefix/config.mak"   # licence record for the package audit
  cd /
}

case "${1:-both}" in
  ps5) build ps5 ;;
  host) build host ;;
  both) build host; build ps5 ;;
  *) echo "usage: $0 [ps5|host|both]"; exit 64 ;;
esac
echo "== $(date -u +%T) done"
