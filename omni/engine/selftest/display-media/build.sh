#!/usr/bin/env bash
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?Provide an output directory}
mkdir -p "$out"
out=$(cd "$out" && pwd)
c++ -std=c++17 -Wall -Wextra -Werror -fsanitize=address,undefined -g "$here/chart_test.cpp" -o "$out/chart-test"
"$out/chart-test" "$out/chart-2160.ppm" > "$out/chart-test.txt"
ffmpeg -hide_banner -loglevel error -y -i "$out/chart-2160.ppm" -frames:v 1 "$out/chart-2160.png"
sdk=/opt/ps5-payload-sdk
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  "$here/bounded_flip_wait.c" "$here/bounded_flip_wait_test.c" -o "$out/bounded-flip-wait-test"
"$out/bounded-flip-wait-test" > "$out/bounded-flip-wait-test.txt"
"$sdk/bin/prospero-clang" -std=c11 -Wall -Wextra -Werror -c "$here/bounded_flip_wait.c" -o "$out/bounded-flip-wait.o"
sha256sum /opt/omni-build/build-sdl-display/libSDL2.a > "$out/sdl-before.sha256"
"$sdk/bin/prospero-clang++" -std=c++17 -Wall -Wextra -Werror \
  -I"$sdk/target/user/homebrew/include" "$here/display_chart.cpp" \
  -o "$out/omni-display-chart.elf" "$out/bounded-flip-wait.o" \
  -Wl,--wrap=sceKernelWaitEqueue /opt/omni-build/build-sdl-display/libSDL2.a \
  -L"$sdk/target/user/homebrew/lib" -liconv -lSceSystemService -lSceUserService \
  -lScePad -lSceAudioOut -lsamplerate -lSceVideoOut -lSceKeyboard -lSceImeDialog
sha256sum "$out/omni-display-chart.elf" > "$out/display-chart.sha256"
sha256sum -c "$out/sdl-before.sha256" > "$out/sdl-unchanged.txt"
