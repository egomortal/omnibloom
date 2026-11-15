#!/bin/sh
# Download uBlock Origin's lists (the ones compile-lists.cjs reads) into ./lists. GPL-3.0-or-later.
# The lists keep their own licences (uBlock Origin's: GPL-3.0; EasyList/EasyPrivacy: GPL-3.0 or CC BY-SA 3.0).
set -e
cd "$(dirname "$0")"
mkdir -p lists
cd lists
B=https://ublockorigin.github.io/uAssets
for f in easylist easyprivacy; do curl -fsSL -o $f.txt $B/thirdparties/$f.txt; done
for f in filters privacy badware unbreak quick-fixes annoyances-cookies annoyances-others; do curl -fsSL -o ubo-$f.txt $B/filters/$f.txt; done
for f in filters-general filters-mobile filters-2020 filters-2021 filters-2022 filters-2023 filters-2024 filters-2025 filters-2026 ubo-link-shorteners resource-abuse privacy-removeparam; do
  curl -fsSL -o $f.txt $B/filters/$f.txt || echo "optional list $f not found (skipped)"
done
[ -f privacy-removeparam.txt ] && mv privacy-removeparam.txt ubo-privacy-removeparam.txt
for f in easylist-cookies easylist-newsletters easylist-notifications easylist-annoyances easylist-chat; do
  curl -fsSL -o $f.txt "https://ublockorigin.github.io/uAssets/thirdparties/$f.txt" || echo "optional list $f not found (skipped)"
done
echo "lists in $(pwd): $(ls | wc -l) files"
