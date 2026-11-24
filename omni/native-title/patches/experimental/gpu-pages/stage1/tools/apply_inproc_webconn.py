#!/usr/bin/env python3
"""OMNI_INPROC_WEBCONN_V1 (2026-11-24): the in-app page engine marks its connection to the network engine as a
page-engine connection (OMNI_INPROC_SPIN_V7 holds messages only on those; see apply_inproc_spin.py / apply_inproc_aux.py
R3). Only while omni_inproc_main_spin is set; a child never calls it.
usage: apply_inproc_webconn.py <WebKit/WebProcess/Network/NetworkProcessConnection.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_WEBCONN_V1'
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


rep('    m_connection->open(*this);\n',
    '    m_connection->open(*this);\n'
    '    if (omni_inproc_main_spin)   // ' + MARK + '\n'
    '        omni_spin_mark_web(m_connection.ptr());\n')
rep('#include "config.h"\n',
    '#include "config.h"\n'
    'extern "C" volatile int omni_inproc_main_spin;   // ' + MARK + ' (IPC/Connection.cpp, OMNI_INPROC_SPIN)\n'
    'extern "C" void omni_spin_mark_web(const void*);\n')
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
