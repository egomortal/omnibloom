#!/bin/bash
# omni-files broker: host test, then the PS5 payload build (needs the PS5 Payload SDK in /opt/ps5-payload-sdk).
set -e
cd "$(dirname "$0")/.."   # omni/
B=files-broker
mkdir -p $B/dist
T=$(mktemp -d)
cc -O1 -Wall -Wextra -pthread -I$B/src $B/tests/test_broker.c -o "$T/test_broker"
"$T/test_broker" | tee $B/dist/host-test.log | tail -1
rm -rf "$T"
/opt/ps5-payload-sdk/bin/prospero-clang -O2 -Wall -Wextra -Werror -D__PS5__ -I$B/src -o $B/dist/omni-files.elf $B/src/omni-files.c
sha256sum $B/dist/omni-files.elf | tee $B/dist/omni-files.elf.sha256
