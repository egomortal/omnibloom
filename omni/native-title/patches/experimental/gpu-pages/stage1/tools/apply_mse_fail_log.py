#!/usr/bin/env python3
"""OMNI_MSE_FAIL_LOG_V1 (2026-11-25): log WHY an MSE source failed.

movy.sx (HLS: fMP4, H.264 2603x1080 + AAC muxed in one init, through the site's own MSE player) never plays in Omni:
the player logs only "OMNI MSE: source-pump-failed ... width=0 height=0" at time 0. Every rejection in OmniMSESource
(initialization unsupported, decoder configuration failed, fragment demux rejected, packet unsupported or over quota,
sample timestamps rejected, media source ended with error, packet decode failed, ...) goes through
OmniMSESource::failed(), which stored the reason without printing it. Now the first reason is printed once per source:
  OMNI MSE: source failed: <reason>
usage: apply_mse_fail_log.py <tree root holding engine/entry>"""
import sys
from pathlib import Path

MARK = 'OMNI_MSE_FAIL_LOG_V1'
p = Path(sys.argv[1]) / 'engine/entry/OmniMSESource.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
old = 'void OmniMSESource::failed(const char* message) { if (m_error.empty()) m_error = message; changed(); }\n'
new = ('void OmniMSESource::failed(const char* message)\n{\n'
       '    if (m_error.empty()) { fprintf(stderr, "OMNI MSE: source failed: %s (' + MARK + ')\\n", message ? message : "?"); fflush(stderr); } // ' + MARK + '\n'
       '    if (m_error.empty()) m_error = message;\n'
       '    changed();\n}\n')
if s.count(old) != 1:
    sys.exit('%s: anchor found %d times' % (p.name, s.count(old)))
s = s.replace(old, new, 1)
if 'fprintf(stderr' not in s.replace(new, ''):
    sys.exit('%s: no fprintf in the file already; add stdio deliberately' % p.name)   # the file already prints (quality switch lines)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('mse fail log: patched', p.name)
