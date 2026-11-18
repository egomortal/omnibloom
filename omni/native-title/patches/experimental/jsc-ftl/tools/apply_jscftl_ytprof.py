#!/usr/bin/env python3
"""OMNI_YTPROF_V1 (DIAG=1 jscftl child only): main-thread category timers, the omni-ytprof diagnostic ported to the
jscftl tree, plus OMNI_YTPROF_WIN_V1 output for long-lived pages (movy.sx): a per-category window line every 5 s and
one line per long (>= 100 ms) top-level main-thread task. Every hook is a no-op unless /data/omni/ytprof.flag exists
when the process first asks (checked once, raw open()). No header is changed: each patched .cpp gets the shared
declaration block (jscftl-ytprof-common.inc, #ifndef-guarded for unified bundles) before its first `namespace X {`.

  WTF/wtf/MainThread.cpp                         the sink (jscftl-ytprof-sink.inc), appended; lines to fd 2:
      OMNI YTPROF on   pid=N (...)
      OMNI YTPROF nav  seq=N navAgo=<ms> url=...
      OMNI YTPROF t    seq=N ms=<since nav> busy=<ms> <cat>=<self ms>/<n> ...   cumulative, every >= 250 ms, first 30 s
      OMNI YTPROF page seq=N dur=<ms> busy=<ms> <cat>=<ms>/<n> ... off:<cat>=<ms>/<n> gc=<eden>/<full> url=...  (next commit)
      OMNI YTPROF w    seq=N ms=<since nav> win=<ms> busy=<ms> tasks=N long50=N long100=N max=<ms> gcn=E/F <cat>=<ms>/<n> ...
      OMNI YTPROF long seq=N ms=<since nav> dur=<ms> top=<cat> <non-zero cat>=<ms>/<n> ...
      categories: task(= other) js compile gc sweep style layout paint raster decode parse cssparse rupd
  WTF/wtf/generic/RunLoopGeneric.cpp             task: every run-loop task / performWork
  JavaScriptCore/runtime/JSLock.cpp              js: JSLock held by the main thread (incl. microtasks)
  JavaScriptCore/heap/Heap.cpp                   gc: stopIfNecessarySlow, collectSync, acquireAccessSlow; sweep:
                                                 sweepSynchronously; eden/full counts at collection end
  JavaScriptCore/heap/IncrementalSweeper.cpp     sweep: doSweep
  JavaScriptCore/runtime/CodeCache.cpp           compile: bytecode generation (global/eval/module code)
  JavaScriptCore/bytecode/UnlinkedFunctionExecutable.cpp   compile: bytecode generation (functions)
  WebCore/dom/Document.cpp                       style: Document::resolveStyle
  WebCore/page/LocalFrameViewLayoutContext.cpp   layout
  WebCore/page/LocalFrameView.cpp                paint: paintContents
  WebCore/platform/image-decoders/ScalableImageDecoder.cpp   decode
  WebCore/page/Page.cpp                          rupd: Page::updateRendering (count per window = rendering updates)
  WebCore/html/parser/HTMLDocumentParser.cpp     parse: pumpTokenizer
  WebCore/css/StyleSheetContents.cpp             cssparse
  WebCore/loader/FrameLoader.cpp                 page mark at main-frame commit (times from navigation start)
  WebKit/.../CoordinatedGraphics/DrawingAreaCoordinatedGraphics.cpp   raster: the non-composited display

usage: apply_jscftl_ytprof.py <tree root containing webkit/>   every anchor of every file checked before any write;
per-file idempotent ("already" for files carrying the marker).
Backups: $OMNI_PATCH_BACKUP_DIR/<relpath>.before-<MARK> if set, else <file>.before-<MARK>.
"""
import os, sys
from pathlib import Path

MARK = 'OMNI_YTPROF_V1'
HERE = Path(__file__).resolve().parent
COMMON = (HERE / 'jscftl-ytprof-common.inc').read_text(encoding='utf-8').replace('\r\n', '\n')
SINK = (HERE / 'jscftl-ytprof-sink.inc').read_text(encoding='utf-8').replace('\r\n', '\n')
assert MARK in COMMON and MARK in SINK and 'OMNI_YTPROF_WIN_V1' in SINK

def transform(rel, s, ops, ns, append):
    for kind, a, b in ops:
        n = s.count(a)
        if n != 1:
            sys.exit('%s: anchor found %d times: %r' % (rel, n, a[:100]))
        if kind == 'after':
            s = s.replace(a, a + b, 1)
        elif kind == 'replace':
            s = s.replace(a, b, 1)
        elif kind == 'scope':   # a = function signature start; the scope goes after the body's opening brace
            i = s.index(a); j = s.find('\n{\n', i)
            if j < 0 or j - i > 600:
                sys.exit('%s: body brace not within 600 chars of %r' % (rel, a[:60]))
            s = s[:j + 3] + '    OMNI_YTPROF_SCOPE(%s); // %s\n' % (b, MARK) + s[j + 3:]
    if ns:
        k = s.find('\nnamespace %s {\n' % ns)
        if k < 0:
            sys.exit('%s: no "namespace %s {" line' % (rel, ns))
        s = s[:k + 1] + COMMON + '\n' + s[k + 1:]
    if append:
        s = s.rstrip('\n') + '\n\n' + append
    return s

def patch_files(root, plan):
    todo, results = [], []
    for rel, ops, ns, append in plan:
        p = root / rel
        if not p.is_file():
            sys.exit('%s: file missing' % p)
        raw = p.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; s = raw.replace('\r\n', '\n')
        if MARK in s:
            results.append(('already', rel)); continue
        t = transform(rel, s, ops, ns, append)
        if MARK not in t:
            sys.exit('%s: patched text lacks the marker %s' % (rel, MARK))
        todo.append((rel, p, raw, t.replace('\n', '\r\n') if crlf else t))
    for rel, p, raw, t in todo:
        bdir = os.environ.get('OMNI_PATCH_BACKUP_DIR')
        b = (Path(bdir) / (rel + '.before-' + MARK)) if bdir else p.with_name(p.name + '.before-' + MARK)
        b.parent.mkdir(parents=True, exist_ok=True)
        if not b.exists():
            b.write_bytes(raw.encode('utf-8'))
        p.write_bytes(t.encode('utf-8'))
        results.append(('applied', rel))
    for state, rel in results:
        print('%s %s %s' % (state, MARK, rel))
    print('applied' if any(r[0] == 'applied' for r in results) else 'already')

if len(sys.argv) != 2:
    sys.exit(__doc__)
S = 'webkit/Source/'
sc = lambda sig, cat: ('scope', sig, cat)
patch_files(Path(sys.argv[1]), [
    (S + 'WTF/wtf/MainThread.cpp', [], None, COMMON + '\n' + SINK),
    (S + 'WTF/wtf/generic/RunLoopGeneric.cpp', [
        ('replace', '            task->fired();\n', '            { OMNI_YTPROF_SCOPE(OMNI_YP_TASK); task->fired(); } // OMNI_YTPROF_V1\n'),
        ('replace', '        performWork();\n    }\n}\n', '        { OMNI_YTPROF_SCOPE(OMNI_YP_TASK); performWork(); } // OMNI_YTPROF_V1\n    }\n}\n')], 'WTF', None),
    (S + 'JavaScriptCore/runtime/JSLock.cpp', [
        ('after', '    m_vm->traps().notifyGrabAllLocks();\n', '    if (omni_ytprof_on()) omni_ytprof_push(OMNI_YP_JS); // OMNI_YTPROF_V1\n'),
        ('after', 'void JSLock::willReleaseLock()\n{\n',
         '    struct OmniYtprofPopJS { ~OmniYtprofPopJS() { if (omni_ytprof_on()) omni_ytprof_pop(OMNI_YP_JS); } } omniYtprofPopJS; // OMNI_YTPROF_V1\n')], 'JSC', None),
    (S + 'JavaScriptCore/heap/Heap.cpp', [
        sc('\nvoid Heap::stopIfNecessarySlow()\n', 'OMNI_YP_GC'),
        sc('\nvoid Heap::collectSync(', 'OMNI_YP_GC'),
        sc('\nvoid Heap::acquireAccessSlow()\n', 'OMNI_YP_GC'),
        sc('\nvoid Heap::sweepSynchronously()\n', 'OMNI_YP_SWEEP'),
        ('after', '    CollectionScope scope = *m_collectionScope;\n', '    omni_ytprof_gc(scope == CollectionScope::Full); // OMNI_YTPROF_V1\n')], 'JSC', None),
    (S + 'JavaScriptCore/heap/IncrementalSweeper.cpp', [sc('\nvoid IncrementalSweeper::doSweep(', 'OMNI_YP_SWEEP')], 'JSC', None),
    (S + 'JavaScriptCore/runtime/CodeCache.cpp', [sc('\nUnlinkedCodeBlockType* generateUnlinkedCodeBlockImpl(', 'OMNI_YP_COMPILE')], 'JSC', None),
    (S + 'JavaScriptCore/bytecode/UnlinkedFunctionExecutable.cpp', [sc('\nstatic UnlinkedFunctionCodeBlock* generateUnlinkedFunctionCodeBlock(', 'OMNI_YP_COMPILE')], 'JSC', None),
    (S + 'WebCore/dom/Document.cpp', [sc('\nvoid Document::resolveStyle(ResolveStyleType type)\n', 'OMNI_YP_STYLE')], 'WebCore', None),
    (S + 'WebCore/page/LocalFrameViewLayoutContext.cpp', [sc('\nvoid LocalFrameViewLayoutContext::layout(bool canDeferUpdateLayerPositions)\n', 'OMNI_YP_LAYOUT')], 'WebCore', None),
    (S + 'WebCore/page/LocalFrameView.cpp', [sc('\nvoid LocalFrameView::paintContents(GraphicsContext& context, const IntRect& dirtyRect, Node* subtreePaintRoot,', 'OMNI_YP_PAINT')], 'WebCore', None),
    (S + 'WebCore/platform/image-decoders/ScalableImageDecoder.cpp', [sc('\nPlatformImagePtr ScalableImageDecoder::createFrameImageAtIndex(', 'OMNI_YP_DECODE')], 'WebCore', None),
    (S + 'WebCore/page/Page.cpp', [sc('\nvoid Page::updateRendering()\n', 'OMNI_YP_RUPD')], 'WebCore', None),
    (S + 'WebCore/html/parser/HTMLDocumentParser.cpp', [sc('\nvoid HTMLDocumentParser::pumpTokenizer(SynchronousMode mode)\n', 'OMNI_YP_PARSE')], 'WebCore', None),
    (S + 'WebCore/css/StyleSheetContents.cpp', [
        sc('\nbool StyleSheetContents::parseAuthorStyleSheet(', 'OMNI_YP_CSSPARSE'),
        sc('\nbool StyleSheetContents::parseString(const String& sheetText)\n', 'OMNI_YP_CSSPARSE')], 'WebCore', None),
    (S + 'WebCore/loader/FrameLoader.cpp', [
        ('after', 'void FrameLoader::commitProvisionalLoad()\n{\n    RefPtr pdl = m_provisionalDocumentLoader;\n    Ref frame = m_frame.get();\n',
         '    if (omni_ytprof_on() && frame->isMainFrame() && pdl) // OMNI_YTPROF_V1: per-page totals, times from navigation start\n'
         '        omni_ytprof_mark(reinterpret_cast<const char*>(pdl->url().string().utf8().data()), (MonotonicTime::now() - pdl->timing().timeOrigin()).milliseconds());\n')],
        'WebCore', None),
    (S + 'WebKit/WebProcess/WebPage/CoordinatedGraphics/DrawingAreaCoordinatedGraphics.cpp', [
        ('after', '    auto omniRasterStart = MonotonicTime::now();\n', '    OMNI_YTPROF_SCOPE(OMNI_YP_RASTER); // OMNI_YTPROF_V1\n')], 'WebKit', None),
])
