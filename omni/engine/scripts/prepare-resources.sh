#!/usr/bin/env bash
# Prepare the resources referenced by OmniResources.cpp on Ubuntu.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HERE/resources"
FONTS="${OMNI_FONT_DIR:-/usr/share/fonts/truetype/dejavu}"
mkdir -p "$DEST"
for font in DejaVuSans.ttf DejaVuSans-Bold.ttf DejaVuSerif.ttf DejaVuSansMono.ttf; do
  [ -s "$FONTS/$font" ] || {
    echo "Missing $FONTS/$font. Install Ubuntu package fonts-dejavu-core." >&2
    exit 1
  }
  cp "$FONTS/$font" "$DEST/$font"
done
curl --fail --location --proto '=https' --tlsv1.2 https://curl.se/ca/cacert.pem -o "$DEST/cacert.pem.tmp"
grep -q 'BEGIN CERTIFICATE' "$DEST/cacert.pem.tmp"
mv "$DEST/cacert.pem.tmp" "$DEST/cacert.pem"
if [ -f /usr/share/doc/fonts-dejavu-core/copyright ]; then
  cp /usr/share/doc/fonts-dejavu-core/copyright "$DEST/FONT-LICENSE.txt"
fi
echo "Fonts and CA bundle prepared. This does not compile the browser."
