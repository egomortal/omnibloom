#!/usr/bin/env python3
"""OMNI_TRACE_LAZY_V1 (2026-11-21, page-table pool): the media pipeline trace buffer (OmniHwService.cpp, 524,288 x 48 B
records = 24 MiB + 512 KiB ready flags) is a static array, so every process that links the file (title, both engine
children) maps it - 12 kernel page tables each (the pool is charged per mapped 2 MiB, touched or not; START-HERE
2026-11-21). It is only written while /data/omni/pipeline-trace.flag tracing is on. Now it is allocated in
diagnosticTraceStart() right before tracing is enabled; every reader/writer is behind traceEnabled, so nothing else changes.
usage: apply_trace_lazy.py <engine dir holding media/OmniHwService.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_TRACE_LAZY_V1'
p = Path(sys.argv[1]) / 'media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:90]))
    s = s.replace(old, new, 1)


rep('TraceRecord traceRecords[traceCapacity];\nstd::atomic<bool> traceReady[traceCapacity] {};\n',
    'TraceRecord* traceRecords = nullptr;   // ' + MARK + ': allocated only when tracing starts (was 24 MiB static)\n'
    'std::atomic<bool>* traceReady = nullptr;   // ' + MARK + '\n')
rep('traceEnabled.store(true); diagnosticTrace(1,getpid(),traceCapacity); }',
    'if (!traceRecords) { traceRecords = new TraceRecord[traceCapacity]; traceReady = new std::atomic<bool>[traceCapacity](); }   /* ' + MARK + ' */'
    ' traceEnabled.store(true); diagnosticTrace(1,getpid(),traceCapacity); }')
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
