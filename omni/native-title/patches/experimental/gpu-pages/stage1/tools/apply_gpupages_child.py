#!/usr/bin/env python3
"""omni-gpu-pages stage 1 (OMNI_GPU_PAGES_STAGE1_V1): patch the WebProcess side into a tree that already carries
the omni-ack diagnostic child's patches. Two WebKit .cpp files, no header. Anchored, exactly-once, idempotent;
writes a unified diff of each file into $OGP_S1_PATCHES.

  DrawingAreaCoordinatedGraphics.cpp  - include ogp-s1-drawingarea.inc; in updatePreferences, turn compositing on
      (forced) when this process got its GL display; never send EnterAcceleratedCompositingMode in stage 1 (the UI
      process stays in backing-store mode); mark the page composited / not; treat DisplayDidRefresh while
      composited as the ack for a composited frame.
  AcceleratedSurfacePlayStation.cpp   - include ogp-s1-surface.inc; record the page at construction; render
      into our offscreen framebuffer; read back, deliver, frameDone at once; free GL objects with the context.
usage: apply_gpupages_child.py <tree root, e.g. /home/builder/s1>"""
import difflib, os, shutil, sys
from pathlib import Path

MARK = 'OMNI_GPU_PAGES_STAGE1_V1'
HERE = Path(__file__).resolve().parent
SRC = HERE.parent / 'src'
root = Path(sys.argv[1])
CG = root / 'webkit/Source/WebKit/WebProcess/WebPage/CoordinatedGraphics'
OUT = Path(os.environ.get('OGP_S1_PATCHES', HERE.parent / 'patches-child'))
OUT.mkdir(parents=True, exist_ok=True)

def edit(path, pairs, include):
    raw = path.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; t = raw.replace('\r\n', '\n')
    if MARK in t:
        print(f'already {path.name}'); return
    before = t
    first = 'namespace WebKit {\n'
    if t.count(first) != 1: sys.exit(f'{path.name}: "namespace WebKit {{" is not there exactly once ({t.count(first)})')
    t = t.replace(first, include + first, 1)
    for anchor, replacement in pairs:
        n = t.count(anchor)
        if n != 1: sys.exit(f'{path.name}: anchor not found exactly once ({n}): {anchor[:90]!r}')
        t = t.replace(anchor, replacement, 1)
    path.write_bytes((t.replace('\n', '\r\n') if crlf else t).encode('utf-8'))
    (OUT / f'{path.name}.gpupages.diff').write_text(''.join(difflib.unified_diff(
        before.splitlines(True), t.splitlines(True), f'a/{path.name}', f'b/{path.name}')))
    print(f'patched {path.name}: {len(pairs)} hooks + include')

for f in ('ogp-s1-policy.h', 'ogp-s1-drawingarea.inc', 'ogp-s1-surface.inc', 'ogp-s1-tcprobe.inc'):
    shutil.copyfile(SRC / f, CG / f); shutil.copyfile(SRC / f, OUT / f)   # the shipped text, beside the diffs

edit(CG / 'DrawingAreaCoordinatedGraphics.cpp', [
    ('    m_alwaysUseCompositing = settings.acceleratedCompositingEnabled() && settings.forceCompositingMode();\n',
     f'    if (OmniGpuPagesS1::ensureDisplay()) {{   // {MARK}: composited on the GPU here, raster stays on the CPU\n'
     '        settings.setAcceleratedCompositingEnabled(true);\n'
     '        settings.setForceCompositingMode(true);\n'
     '        settings.setAcceleratedCompositingForFixedPositionEnabled(true);\n'
     '    }\n'
     '    m_alwaysUseCompositing = settings.acceleratedCompositingEnabled() && settings.forceCompositingMode();\n'),
    ('    m_layerTreeHost->setRootCompositingLayer(graphicsLayer);\n\n    if (m_shouldSendEnterAcceleratedCompositingMode)\n        sendEnterAcceleratedCompositingModeIfNeeded();\n',
     '    m_layerTreeHost->setRootCompositingLayer(graphicsLayer);\n'
     f'    if (omniGpuPagesProcessReady())   // {MARK}\n'
     '        OmniGpuPagesS1::setComposited(*this, true);\n\n'
     '    if (m_shouldSendEnterAcceleratedCompositingMode)\n        sendEnterAcceleratedCompositingModeIfNeeded();\n'),
    ('void DrawingAreaCoordinatedGraphics::sendEnterAcceleratedCompositingModeIfNeeded()\n{\n',
     'void DrawingAreaCoordinatedGraphics::sendEnterAcceleratedCompositingModeIfNeeded()\n{\n'
     f'    if (omniGpuPagesProcessReady()) {{   // {MARK}: the UI process stays in backing-store mode; composited frames arrive as Updates\n'
     '        m_shouldSendEnterAcceleratedCompositingMode = false;\n'
     '        return;\n'
     '    }\n'),
    ('void DrawingAreaCoordinatedGraphics::exitAcceleratedCompositingMode()\n{\n    if (m_alwaysUseCompositing)\n        return;\n',
     'void DrawingAreaCoordinatedGraphics::exitAcceleratedCompositingMode()\n{\n    if (m_alwaysUseCompositing)\n        return;\n'
     f'    if (omniGpuPagesProcessReady())   // {MARK}\n'
     '        OmniGpuPagesS1::setComposited(*this, false);\n'),
    ('    // entered accelerated compositing mode. Ignore them.\n    if (m_layerTreeHost)\n        return;\n',
     '    // entered accelerated compositing mode. Ignore them.\n    if (m_layerTreeHost) {\n'
     f'        if (omniGpuPagesProcessReady())   // {MARK}: in stage 1 these are the acks for composited frames sent as Updates\n'
     '            OmniGpuPagesS1::didRefresh(*this, m_webPage.get());\n'
     '        return;\n'
     '    }\n'),
], f'// {MARK}: GPU compositing in this process, frames delivered as Updates (off unless its flag)\n'
   '#define OGP_S1_POLICY_H "ogp-s1-policy.h"\n#include "ogp-s1-drawingarea.inc"\n\n')

edit(CG / 'AcceleratedSurfacePlayStation.cpp', [
    ('        m_swapChain.initialize(webPage);\n#endif\n}\n',
     '        m_swapChain.initialize(webPage);\n#endif\n'
     f'    OmniGpuPagesS1Surface::created(this, webPage.identifier());   // {MARK}\n}}\n'),
    ('void AcceleratedSurface::willRenderFrame(const IntSize& size)\n{\n',
     'void AcceleratedSurface::willRenderFrame(const IntSize& size)\n{\n'
     f'    if (OmniGpuPagesS1Surface::willRender(this, size))   // {MARK}: our offscreen framebuffer\n'
     '        return;\n'),
    ('void AcceleratedSurface::didRenderFrame()\n{\n',
     'void AcceleratedSurface::didRenderFrame()\n{\n'
     f'    if (OmniGpuPagesS1Surface::didRender(this)) {{   // {MARK}: read back and handed to the main thread; the compositor goes on\n'
     '        RunLoop::currentSingleton().dispatch([protectedThis = Ref { *this }] { protectedThis->frameDone(); });\n'
     '        return;\n'
     '    }\n'),
    ('void AcceleratedSurface::willDestroyGLContext()\n{\n',
     'void AcceleratedSurface::willDestroyGLContext()\n{\n'
     f'    OmniGpuPagesS1Surface::destroyed(this);   // {MARK}\n'),
], f'#include "ogp-s1-surface.inc"   // {MARK}\n\n')

# OMNI_GPUPAGES_TCPROBE_V2 (diagnostic): event counts in the PlayStation ThreadedCompositor
TCPROBE_PAIRS = [('        m_attributes.clientRendersNextFrame = m_sceneState->layersDidChange();\n', "        // OMNI_GPUPAGES_RAF_V1: always notify the client after a composited frame. LayerTreeHost::commitSceneState() sets\n        // m_isWaitingForRenderer and only renderNextFrame() (reached through this notification) clears it; when a commit's\n        // frame rendered with layersDidChange() false and no rAF pending, the flag stayed set for good and every later\n        // rendering update (requestAnimationFrame, resize observers, YouTube's player loop) was swallowed.\n        m_attributes.clientRendersNextFrame = true;\n"), ('    if (m_suspendedCount > 0)\n        return;\n\n    if (!m_context || !m_context->makeContextCurrent())\n        return;\n\n#if !HAVE(DISPLAY_LINK)\n    m_display.updateTimer->stop();\n#endif\n', "    if (m_suspendedCount > 0) {\n        omniTcCount('S');\n        return;\n    }\n    omniTcCount('R');\n\n    if (!m_context || !m_context->makeContextCurrent()) {\n        omniTcCount('C');\n        return;\n    }\n\n#if !HAVE(DISPLAY_LINK)\n    m_display.updateTimer->stop();\n#endif\n"), ('    if (viewportSize.isEmpty())\n        return;\n\n    TransformationMatrix viewportTransform;', "    if (viewportSize.isEmpty()) {\n        omniTcCount('V');\n        return;\n    }\n\n    TransformationMatrix viewportTransform;"), ('    m_context->swapBuffers();\n\n    m_surface->didRenderFrame();\n', "    m_context->swapBuffers();\n\n    m_surface->didRenderFrame();\n    omniTcCount('W');\n"), ('void ThreadedCompositor::frameComplete()\n{\n', "void ThreadedCompositor::frameComplete()\n{\n    omniTcCount('F');\n"), ('void ThreadedCompositor::displayUpdateFired()\n{\n', "void ThreadedCompositor::displayUpdateFired()\n{\n    omniTcCount('D');\n"), ('void ThreadedCompositor::scheduleUpdate()\n{\n', "void ThreadedCompositor::scheduleUpdate()\n{\n    omniTcCount('U');\n")]
edit(CG / 'ThreadedCompositorPlayStation.cpp', TCPROBE_PAIRS, f'#include "ogp-s1-tcprobe.inc"   // {MARK}: OMNI_GPUPAGES_TCPROBE_V2\n\n')

# OMNI_GPUPAGES_TCPROBE_V3: LayerTreeHost counters (commit / renderNextFrame / blocked while waiting for the renderer)
LTH_PAIRS = [('void LayerTreeHost::commitSceneState()\n{\n', "void LayerTreeHost::commitSceneState()\n{\n    omni_tc_count('K');\n"), ('void LayerTreeHost::renderNextFrame(bool forceRepaint)\n{\n', "void LayerTreeHost::renderNextFrame(bool forceRepaint)\n{\n    omni_tc_count('N');\n"), ('    if (m_isWaitingForRenderer) {\n        m_scheduledWhileWaitingForRenderer = true;\n        return;\n    }\n', "    if (m_isWaitingForRenderer) {\n        omni_tc_count('B');\n        m_scheduledWhileWaitingForRenderer = true;\n        return;\n    }\n")]
edit(CG / 'LayerTreeHostPlayStation.cpp', LTH_PAIRS, f'// {MARK}: OMNI_GPUPAGES_TCPROBE_V3\nextern "C" void omni_tc_count(char);   // ThreadedCompositorPlayStation.cpp (ogp-s1-tcprobe.inc)\n\n')
print('stage 1 child patches done')
