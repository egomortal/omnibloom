#!/usr/bin/env python3
"""OMNI_GPUPAGES_LATEST_FRAME_V1 (2026-11-18, owner: "make it leaner without any downside"): the async readback hands the
main thread at most ONE waiting frame, and reuses that frame's memory when a newer one replaces it.

Why: with layers + async scrolling + async readback (OMNI_GPUPAGES_ASYNCREAD_V1) every delivered frame was a NEW
ShareableBitmap (3840x2160x4 = a 32 MiB block at 4K) dispatched to the main thread with no bound. When the main thread
falls behind (4K video, page JS) those tasks pile up; on 2026-11-18 a web process died with
"allocator mmap failed: bytes=33554432 errno=12" while 8.47 GB of flexible memory was free (the kernel refused the next
32 MiB mapping; s1a2y runs on 11-1x failed the same way). Web-process peak on 4K YouTube: 1423 MB with asyncread vs
1053 MB without (memsplit.sh).
No visible change: these are always FULL frames, and omniGpuPagesDeliverFrame() already clears its queue on every full
frame, so a full frame superseded before the main thread took it would have been discarded there anyway.
  - a mailbox per surface (shared with the main-thread task): the newest untaken frame
  - before allocating, the untaken frame's bitmap (same size) is taken back and overwritten: no new 32 MiB block
  - one main-thread task at a time takes whatever is newest
  - counters reused= / replaced= in the existing 2 s asyncread report
Off switch: /data/omni/gpu-pages-latest-frame-off.flag (the previous one-task-per-frame behaviour).
Patches the ENGINE CHILD tree's ogp-s1-surface.inc copy (like apply_layers_default_on.py inc). No backup file (the child
recipe's changed-file gate counts files in the tree). usage: apply_latest_frame.py <dir holding ogp-s1-surface.inc>"""
import sys
from pathlib import Path

MARK = 'OMNI_GPUPAGES_LATEST_FRAME_V1'
p = Path(sys.argv[1]) / 'ogp-s1-surface.inc'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)

EDITS = [
    # 1. the mailbox type, before State
    ('struct State {\n    explicit State(WebCore::PageIdentifier pageID) : page(pageID) { }   // PageIdentifier has no default\n',
     '// ' + MARK + ': the newest read-back frame the main thread has not taken yet (shared with its task)\n'
     'struct OmniFrameBox {\n'
     '    Lock lock;\n'
     '    RefPtr<WebCore::ShareableBitmap> bitmap;\n'
     '    WebCore::IntSize size;\n'
     '    double ms { 0 };\n'
     '    bool scheduled { false };\n'
     '    uint64_t reused { 0 }, replaced { 0 };\n'
     '};\n'
     'static bool omniLatestFrameOn() { static const bool on = access("/data/omni/gpu-pages-latest-frame-off.flag", F_OK) != 0; return on; }\n'
     'struct State {\n    explicit State(WebCore::PageIdentifier pageID) : page(pageID) { }   // PageIdentifier has no default\n'),
    # 2. the mailbox in State
    ('    double asyncCopyMs { 0 }, asyncLastReport { 0 };\n};\n',
     '    double asyncCopyMs { 0 }, asyncLastReport { 0 };\n'
     '    std::shared_ptr<OmniFrameBox> box { std::make_shared<OmniFrameBox>() };   // ' + MARK + '\n};\n'),
    # 3. reuse the untaken frame's bitmap instead of a new 32 MiB block
    ('    RefPtr bitmap = WebCore::ShareableBitmap::create(configuration);\n    glBindBuffer(OMNI_GL_PIXEL_PACK_BUFFER, slot.pbo);\n',
     '    RefPtr<WebCore::ShareableBitmap> bitmap;\n'
     '    if (omniLatestFrameOn()) {   // ' + MARK + ': the frame the main thread never took is overwritten in place\n'
     '        Locker locker { s.box->lock };\n'
     '        if (s.box->bitmap && s.box->size == slot.size) { bitmap = WTF::move(s.box->bitmap); ++s.box->reused; }\n'
     '    }\n'
     '    if (!bitmap) bitmap = WebCore::ShareableBitmap::create(configuration);\n'
     '    glBindBuffer(OMNI_GL_PIXEL_PACK_BUFFER, slot.pbo);\n'),
    # 4. counters in the existing report
    ('        s.asyncLastReport = nowMs();\n    }\n    Vector<WebCore::IntRect> rects; rects.append(bounds);\n',
     '        if (omniLatestFrameOn()) {   // ' + MARK + '\n'
     '            Locker locker { s.box->lock };\n'
     '            fprintf(stderr, "OMNI GPUPAGES latest-frame pid=%d: reused=%llu replaced=%llu\\n", getpid(), (unsigned long long)s.box->reused, (unsigned long long)s.box->replaced);\n'
     '        }\n'
     '        s.asyncLastReport = nowMs();\n    }\n'
     '    if (omniLatestFrameOn()) {   // ' + MARK + ': one waiting frame at most; one main-thread task takes the newest\n'
     '        bool schedule = false;\n'
     '        {\n'
     '            Locker locker { s.box->lock };\n'
     '            if (s.box->bitmap) ++s.box->replaced;   // an older untaken frame of another size: superseded\n'
     '            s.box->bitmap = WTF::move(bitmap); s.box->size = slot.size; s.box->ms = copyMs;\n'
     '            if (!s.box->scheduled) { s.box->scheduled = true; schedule = true; }\n'
     '        }\n'
     '        if (schedule)\n'
     '            RunLoop::mainSingleton().dispatch([page = s.page, box = s.box]() mutable {\n'
     '                RefPtr<WebCore::ShareableBitmap> b; WebCore::IntSize size; double ms = 0;\n'
     '                { Locker locker { box->lock }; b = WTF::move(box->bitmap); size = box->size; ms = box->ms; box->scheduled = false; }\n'
     '                if (!b) return;\n'
     '                WebCore::IntRect frameBounds(0, 0, size.width(), size.height());\n'
     '                Vector<WebCore::IntRect> frameRects; frameRects.append(frameBounds);\n'
     '                omniGpuPagesDeliverFrame(page, b.releaseNonNull(), size, frameBounds, WTF::move(frameRects), true, ms);\n'
     '            });\n'
     '        return true;\n'
     '    }\n'
     '    Vector<WebCore::IntRect> rects; rects.append(bounds);\n'),
]
for old, _ in EDITS:
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old.strip()[:90]))
for old, new in EDITS:
    s = s.replace(old, new, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
