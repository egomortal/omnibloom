"""OMNI_MEDIA_SWITCH_V1 (2026-11-13, owner: "save media download working but then it doesn't switch screens").

When the downloads worker answers "ready", Omni switched to the Media downloads tab only if the page you asked from
was still EXACTLY the same: same tab, same document, same address. YouTube rewrites its address while a video plays,
and OMNI_MEDIA_HEALTH_V2 lets the worker take up to 30 s to answer, so the check failed and Omni only said "Media
downloads is ready. Open it again when you want it." while you stayed on the page.

Now Omni switches whenever you're still on the same tab, with the same privacy, and you didn't go into fullscreen
video meanwhile. The link that's shared was taken when you pressed the shortcut, so a later address change doesn't
matter. If you did move to another tab, the notice now says which buttons open it.

usage: apply_media_switch.py <engine tree>   (edits engine/entry/OmniMediaDownloadsHooks.inc; anchored, idempotent)
"""
import sys
from pathlib import Path

MARK = 'OMNI_MEDIA_SWITCH_V1'
p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniMediaDownloadsHooks.inc'
raw = p.read_bytes()
nl = '\r\n' if b'\r\n' in raw else '\n'
s = raw.decode('utf-8')
if MARK in s:
    print('already'); sys.exit(0)
OLD = '''    if (!active() || active()->omniMediaIdentity != omniMediaOriginIdentity
        || active()->omniSavedDocument != omniMediaOriginDocument || active()->omniPrivate != omniMediaOriginPrivate
        || (!omniMediaOriginPrivate && active()->url != omniMediaOriginURL)
        || (pageFullscreen && !omniMediaOriginFullscreen)) {
        notice("Media downloads is ready. Open it again when you want it.");
        return;
    }'''
NEW = '''    // OMNI_MEDIA_SWITCH_V1: switch whenever you're still on the tab you asked from (same privacy, no new fullscreen).
    // The page's address/document may change meanwhile (YouTube rewrites its URL while it plays, and the worker can
    // take up to 30 s to answer since OMNI_MEDIA_HEALTH_V2); that used to cancel the switch.
    if (!active() || active()->omniMediaIdentity != omniMediaOriginIdentity || active()->omniPrivate != omniMediaOriginPrivate
        || (pageFullscreen && !omniMediaOriginFullscreen)) {
        notice("Media downloads is ready: press L1 + R1 to open it.");
        return;
    }'''
OLD, NEW = OLD.replace('\n', nl), NEW.replace('\n', nl)
if s.count(OLD) != 1:
    sys.exit('anchor found %d times' % s.count(OLD))
p.write_bytes(s.replace(OLD, NEW, 1).encode('utf-8'))
print('applied OMNI_MEDIA_SWITCH_V1')
