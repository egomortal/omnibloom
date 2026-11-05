#!/usr/bin/env python3
"""omni-jit2 OMNI_NO_VIEW_TRANSITION_V1 (WebCore, on the tree given as argv[1]).
The 4K YouTube watch-page WebProcess death (SIGTRAP at child offset 0x9ab81, captured by OMNI_CRASH_V2 2026-11-04):
document.startViewTransition() -> Document::setActiveViewTransition() -> RenderLayerCompositor::enableCompositingMode()
-> DrawingAreaCoordinatedGraphics::enterAcceleratedCompositingMode() -> AcceleratedSurface -> PlatformDisplay::sharedDisplay()
RELEASE_ASSERT: Omni turns accelerated compositing off and its WebProcess has no shared display, but a view transition
forced compositing mode on anyway. Fix: with accelerated compositing off, a view transition is skipped the way the spec
skips one for a hidden document (the update callback still runs; the page sees a rejected `ready`), and
setActiveViewTransition never forces compositing mode. Idempotent; each anchor must match once."""
import sys
from pathlib import Path
p = Path(sys.argv[1]) / 'webkit/Source/WebCore/dom/Document.cpp'
raw = p.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; s = raw.replace('\r\n', '\n')
if 'OMNI_NO_VIEW_TRANSITION_V1' in s: print('already applied'); sys.exit(0)
def sub(old, new):
    global s
    n = s.count(old)
    if n != 1: sys.exit(f'anchor matched {n} times: {old[:80]!r}')
    s = s.replace(old, new)
sub('''            if (hasViewTransition)
                protect(view->compositor())->enableCompositingMode();''',
    '''            if (hasViewTransition && settings().acceleratedCompositingEnabled())   // OMNI_NO_VIEW_TRANSITION_V1
                protect(view->compositor())->enableCompositingMode();''')
sub('''    if (hidden()) {
        viewTransition->skipViewTransition(Exception { ExceptionCode::InvalidStateError, "View transition was skipped because document visibility state is hidden."_s });
        return viewTransition;
    }
''', '''    if (hidden()) {
        viewTransition->skipViewTransition(Exception { ExceptionCode::InvalidStateError, "View transition was skipped because document visibility state is hidden."_s });
        return viewTransition;
    }

    // OMNI_NO_VIEW_TRANSITION_V1: no accelerated compositing (Omni's WebProcess has no shared display): skip, as for hidden.
    if (!settings().acceleratedCompositingEnabled()) {
        viewTransition->skipViewTransition(Exception { ExceptionCode::InvalidStateError, "View transition was skipped because accelerated compositing is off."_s });
        return viewTransition;
    }
''')
p.write_bytes((s.replace('\n', '\r\n') if crlf else s).encode('utf-8')); print('patched', p)
