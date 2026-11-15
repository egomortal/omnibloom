"""OMNI_ADDON_CAP_40_V1 (2026-11-13): Omni loads up to 40 add-ons (was 24). 26 now ship in the title (/app0/addons),
and the manager keeps room for the user's own. Astra's capacity review (codex-ui/20261103-addon-main-capacity) tested
the loader and both managers at 40; this changes only the constant the loader checks.

usage: apply_addon_cap.py <engine tree>   (edits engine/entry/OmniAddonsCore.h; anchored, idempotent)
"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniAddonsCore.h'
raw = p.read_bytes()
nl = b'\r\n' if b'\r\n' in raw else b'\n'
OLD, NEW = b'constexpr size_t maxAddons = 24;', b'constexpr size_t maxAddons = 40; // OMNI_ADDON_CAP_40_V1 (was 24)'
if NEW in raw:
    print('already'); sys.exit(0)
if raw.count(OLD) != 1:
    sys.exit('anchor found %d times' % raw.count(OLD))
p.write_bytes(raw.replace(OLD, NEW, 1))
print('applied OMNI_ADDON_CAP_40_V1')
