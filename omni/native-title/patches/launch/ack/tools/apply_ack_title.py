#!/usr/bin/env python3
"""OMNI_ACK_V1, title/UI-process half, on the PRIVATE tree given as argv[1].

The page's frame production is gated on DisplayDidRefresh. This half makes the shell's answer independent of
its own work with the update: the ack is sent before incorporateUpdate(), it is sent for every Update (so a
page can never wait for an ack that upstream swallowed), and the ExitAcceleratedCompositingMode update - for
which the child also waits - is answered too. Kill switch: /data/omni/ack-off.flag.

Every anchor must match exactly once; the applier is idempotent and writes a unified diff of what it did.
usage: apply_ack_title.py <tree root>"""
import difflib, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
N = HERE.parent
W = Path(sys.argv[1]) / 'webkit/Source'
SRC = Path(os.environ.get('OMNI_ACK_SRC') or (N / 'src'))
D = Path(os.environ.get('OMNI_ACK_PATCHES') or (N / 'patches-eboot'))
D.mkdir(parents=True, exist_ok=True)
MARK = 'OMNI_ACK_V1'
REL = 'WebKit/UIProcess/CoordinatedGraphics/DrawingAreaProxyCoordinatedGraphics.cpp'

BLOCK = (SRC / 'ack-title.inc').read_text()

NS_ANCHOR = 'namespace WebKit {\nusing namespace WebCore;\n'

ORIGINAL_UPDATE = '''void DrawingAreaProxyCoordinatedGraphics::update(uint64_t, UpdateInfo&& updateInfo)
{
    if (m_isWaitingForDidUpdateGeometry && updateInfo.viewSize != m_lastSentSize) {
        send(Messages::DrawingArea::DisplayDidRefresh(MonotonicTime::now()));
        return;
    }

    // FIXME: Handle the case where the view is hidden.

    incorporateUpdate(WTF::move(updateInfo));

    if (!m_isWaitingForDidUpdateGeometry)
        send(Messages::DrawingArea::DisplayDidRefresh(MonotonicTime::now()));
}
'''

NEW_UPDATE = '''void DrawingAreaProxyCoordinatedGraphics::update(uint64_t, UpdateInfo&& updateInfo)
{
    // OMNI_ACK_V1: answer the page first, then do this process's own work with the update. `stale` is
    // upstream's case of an update for a size this process no longer wants (dropped, acked). `swallowFixed`
    // is upstream's silent case: a geometry round trip in flight whose size matches, where the update was
    // incorporated and NO ack was sent, leaving a waiting page waiting.
    if (omniAckV1On()) {
        const bool stale = m_isWaitingForDidUpdateGeometry && updateInfo.viewSize != m_lastSentSize;
        const bool swallowFixed = m_isWaitingForDidUpdateGeometry && !stale;
        send(Messages::DrawingArea::DisplayDidRefresh(MonotonicTime::now()));
        const MonotonicTime omniAckedAt = MonotonicTime::now();
        if (!stale) {
            // FIXME: Handle the case where the view is hidden.
            incorporateUpdate(WTF::move(updateInfo));
        }
        omniAckShellUpdate(omniAckedAt, swallowFixed, stale);
        return;
    }

    if (m_isWaitingForDidUpdateGeometry && updateInfo.viewSize != m_lastSentSize) {
        send(Messages::DrawingArea::DisplayDidRefresh(MonotonicTime::now()));
        return;
    }

    // FIXME: Handle the case where the view is hidden.

    incorporateUpdate(WTF::move(updateInfo));

    if (!m_isWaitingForDidUpdateGeometry)
        send(Messages::DrawingArea::DisplayDidRefresh(MonotonicTime::now()));
}
'''

ORIGINAL_EXIT = '''void DrawingAreaProxyCoordinatedGraphics::exitAcceleratedCompositingMode(uint64_t, UpdateInfo&& updateInfo)
{
    exitAcceleratedCompositingMode();
    incorporateUpdate(WTF::move(updateInfo));
}
'''

NEW_EXIT = '''void DrawingAreaProxyCoordinatedGraphics::exitAcceleratedCompositingMode(uint64_t, UpdateInfo&& updateInfo)
{
    exitAcceleratedCompositingMode();
    // OMNI_ACK_V1: the child waits for an ack for this message too - its display() sends
    // ExitAcceleratedCompositingMode in place of Update and still sets m_isWaitingForDidUpdate - and
    // upstream never sends one, so the page's loop stops until something else forces an update.
    if (omniAckV1On()) {
        send(Messages::DrawingArea::DisplayDidRefresh(MonotonicTime::now()));
        const MonotonicTime omniAckedAt = MonotonicTime::now();
        incorporateUpdate(WTF::move(updateInfo));
        omniAckShellUpdate(omniAckedAt, false, false, true);
        return;
    }
    incorporateUpdate(WTF::move(updateInfo));
}
'''


def main():
    p = W / REL
    raw = p.read_bytes().decode('utf-8')
    crlf = '\r\n' in raw
    t = raw.replace('\r\n', '\n')
    if MARK in t:
        print('already', REL)
        return
    s = t
    for a, b in ((NS_ANCHOR, BLOCK + '\n' + NS_ANCHOR),
                 (ORIGINAL_UPDATE, NEW_UPDATE),
                 (ORIGINAL_EXIT, NEW_EXIT)):
        n = s.count(a)
        if n != 1:
            sys.exit('%s: anchor matched %d times: %r' % (REL, n, a[:120]))
        s = s.replace(a, b)
    # the exact text of the two patched functions, so the host gate compiles what ships
    (D / 'ack-update.inc').write_text(NEW_UPDATE + '\n' + NEW_EXIT)
    (D / (p.name + '.ack.diff')).write_text(
        ''.join(difflib.unified_diff(t.splitlines(True), s.splitlines(True), 'a/' + REL, 'b/' + REL)))
    p.write_bytes((s.replace('\n', '\r\n') if crlf else s).encode('utf-8'))
    print('patched', REL)
    print('OMNI_ACK_V1 (title): 1 file patched')


main()
