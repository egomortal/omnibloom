#!/usr/bin/env bash
set -eu
ulimit -c 0
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?Provide an output executable path}
c++ -std=c++20 -Wall -Wextra -Werror -g -fsanitize=address,undefined \
  "$here/clock-test.cpp" -o "$out"
ASAN_OPTIONS=detect_leaks=1 "$out"
