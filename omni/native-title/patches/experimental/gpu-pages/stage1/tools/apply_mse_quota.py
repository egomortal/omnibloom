"""OMNI_MSE_QUOTA_V1 (2026-11-14): make Omni's MediaSource (MSE) buffer quota a setting (was a fixed 32 MiB).

Why: YouTube 4K HDR (VP9.2, ~25-40 Mbit/s) fills 32 MiB in ~7-10 s. Console diagnostics (OMNI_YT_MSE_DIAG_V1, runs
uaX-232414 / uaX-233147) show `appendBuffer` throwing QuotaExceededError at ~45 MB appended. Early in a video the player
has nothing already played to evict, so it stops requesting media: the "freeze at ~11 s" (readyState 2, buffered 0-11.6 s,
0 requests) that Omni's YouTube guard then "fixes" by reloading = part of the owner's "replay". The 32 MiB cap dates
from OMNI_WEBM_V1 rev3 (sized for 1080p, ~30 s); 4K output + HDR made YouTube serve streams it can't hold.
128 MiB ~ 25-40 s of 4K HDR (WebKit's own default is 304 MB; desktop Chrome ~150 MB video). Child memory peaked at
~1.3 GB in 20-min YouTube soaks; the owner pre-approved Omni-scale limits.

Edits engine/entry/OmniMSESource.cpp (the page process's MSE). Anchored, once, idempotent.
usage: apply_mse_quota.py <engine tree>
"""
import sys
from pathlib import Path

MARK = 'OMNI_MSE_QUOTA_V1'
p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniMSESource.cpp'
raw = p.read_bytes(); nl = '\r\n' if b'\r\n' in raw else '\n'; s = raw.decode('utf-8')
if MARK in s:
    print('already'); sys.exit(0)
old = '    size_t platformMaximumBufferSize() const final { return 32 * 1024 * 1024; }' + nl
new = ('    // OMNI_MSE_QUOTA_V1: was a fixed 32 MiB (= ~10 s of 4K HDR). Now /data/omni/mse-quota-mb.txt (4-512, read once),' + nl +
       '    // default 64 MiB; logged once as "OMNI MSEQUOTA". Lets the quota be tested (small = provoke, big = fix) without a rebuild.' + nl +
       '    size_t platformMaximumBufferSize() const final {' + nl +
       '        static const size_t quota = [] {' + nl +
       '            unsigned mb = 64;' + nl +
       '            if (FILE* f = fopen("/data/omni/mse-quota-mb.txt", "r")) { unsigned v = 0; if (fscanf(f, "%u", &v) == 1 && v >= 4 && v <= 512) mb = v; fclose(f); }' + nl +
       '            fprintf(stderr, "OMNI MSEQUOTA: %u MiB per SourceBuffer (OMNI_MSE_QUOTA_V1; /data/omni/mse-quota-mb.txt)\\n", mb);' + nl +
       '            return static_cast<size_t>(mb) * 1024 * 1024;' + nl +
       '        }();' + nl +
       '        return quota;' + nl +
       '    }' + nl)
if s.count(old) != 1:
    sys.exit('OmniMSESource.cpp: anchor found %d times' % s.count(old))
p.write_bytes(s.replace(old, new, 1).encode('utf-8'))
print('applied')
