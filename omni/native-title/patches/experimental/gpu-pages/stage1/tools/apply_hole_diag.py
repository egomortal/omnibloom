#!/usr/bin/env python3
"""OMNI_HOLE_DIAG_V1 (2026-11-24, TEST ONLY - the release recipe never runs this): why does an MSE video in the
in-app page engine never claim the shell's video plane? (Bloom Preview 5 check: in-app YouTube stalled at 0.0145 s in
6 of 7 runs; no "OMNI HOLEPUNCH: player" line, audio ring playing=0, the V5 startup gate waits for pacing forever.)

OmniMSEPlayer.cpp:
  - every 2 s while a video is not paced by the shell: one HOLEDIAG line with every input of the hole decision
    (allowed, visible, eligible, onScreen, why, link, linkState, rect, frameDue, paused, position, hold reason);
  - every setPageIsVisible() call is logged (HOLEDIAG visible=...).
usage: apply_hole_diag.py <OmniMSEPlayer.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_HOLE_DIAG_V1'
p = Path(sys.argv[1])
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:70]))
    s = s.replace(old, new, 1)


rep('    void setPageIsVisible(bool value) final { m_visible = value; }\n',
    '    void setPageIsVisible(bool value) final\n'
    '    {\n'
    '        if (value != m_visible) { fprintf(stderr, "OMNI HOLEDIAG: visible %d -> %d (' + MARK + ')\\n", m_visible ? 1 : 0, value ? 1 : 0); fflush(stderr); }\n'
    '        m_visible = value;\n'
    '    }\n')
rep('        holePacingInput(in); // OMNI_HOLEPUNCH_V4\n',
    '        holePacingInput(in); // OMNI_HOLEPUNCH_V4\n'
    '        if (!m_holePunch.paced() && in.nowMs - m_holeDiagAtMs >= 2000) { // ' + MARK + ' (test)\n'
    '            m_holeDiagAtMs = in.nowMs;\n'
    '            fprintf(stderr, "OMNI HOLEDIAG: allowed=%d visible=%d hasVideo=%d eligible=%d onScreen=%d why=%s link=%d state=%d rect=%dx%d@%d,%d due=%d paused=%d pos=%.3f hold=%s pacing=%d active=%d presenting=%d\\n",\n'
    '                m_holeAllowed ? 1 : 0, m_visible ? 1 : 0, hasVideo() ? 1 : 0, in.eligible ? 1 : 0, in.onScreen ? 1 : 0, why ? why : "-",\n'
    '                in.link ? 1 : 0, in.linkState, in.rect.w, in.rect.h, in.rect.x, in.rect.y, in.frameDue ? 1 : 0, m_paused ? 1 : 0,\n'
    '                m_position, m_v5Hold ? m_v5HoldReason : "-", in.pacing ? 1 : 0, m_holePunch.holeActive() ? 1 : 0, m_holePunch.presenting() ? 1 : 0);\n'
    '            fflush(stderr);\n'
    '        }\n')
rep('    bool m_holeAllowed = false, m_holeHasFrame = false, m_holeLastOnScreen = false;\n',
    '    bool m_holeAllowed = false, m_holeHasFrame = false, m_holeLastOnScreen = false;\n'
    '    double m_holeDiagAtMs = 0; // ' + MARK + ' (test)\n')
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('hole diag: patched', p.name)
