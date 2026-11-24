#!/usr/bin/env python3
"""OMNI_INPROC_SHMCHECK_V1 (2026-11-23, TEST BUILDS): diagnose the in-process WebProcess crash on YouTube 4K.

Console 2026-11-23 (19c23cdf, Lytiw, 64 s in): SIGSEGV code 2 err 4 (page not present) in libc memcpy on a WebKit IPC
receive thread: IPC::Connection::processMessage() -> Decoder::create() copying a 0x4030-byte OUT-OF-LINE message body
from its read-only shared-memory mapping, at the mapping's first page. Out-of-line bodies are sent as a shared-memory
fd (SCM_RIGHTS). In the title, shm_open(SHM_ANON) is wrapped (OMNI_NATIVE_SHM_V1, NativeShm.cpp): each object gets a name
and is shm_unlink'ed when the last TRACKED descriptor closes. With the WebProcess in the title, sender and receiver are
the same process, so this is new ground; earlier out-of-line messages worked (intermittent).

This adds, only while omni_inproc_main_spin is set (in-process role active), before the receiver maps the body: fstat()
of the received fd. The first 6 out-of-line receives and every 500th are logged (fd, st_size, mode, body size) to see the
normal values; a receive whose object is smaller than the body is logged with "SHORT" and treated like a failed mapping
(processMessage returns false -> the connection closes) instead of crashing in memcpy.
usage: apply_inproc_shmcheck.py <WebKit/Platform/IPC/unix/ConnectionUnix.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_SHMCHECK_V1'
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


rep('#include <wtf/UniStdExtras.h>\n',
    '#include <wtf/UniStdExtras.h>\n'
    '#include <sys/stat.h>   // ' + MARK + '\n'
    '#include <atomic>\n'
    'extern "C" volatile int omni_inproc_main_spin;   // ' + MARK + ' (IPC/Connection.cpp, OMNI_INPROC_SPIN)\n')

rep('        auto handle = WebCore::SharedMemory::Handle { WTF::move(fd), messageInfo.bodySize() };\n'
    '        oolMessageBody = WebCore::SharedMemory::map(WTF::move(handle), WebCore::SharedMemory::Protection::ReadOnly);\n',
    '        if (omni_inproc_main_spin) {   // ' + MARK + '\n'
    '            static std::atomic<unsigned> omniOol { 0 };\n'
    '            unsigned omniN = ++omniOol;\n'
    '            struct stat omniSt;\n'
    '            int omniRc = fstat(fd.value(), &omniSt);\n'
    '            bool omniShort = omniRc || static_cast<size_t>(omniSt.st_size) < messageInfo.bodySize();\n'
    '            if (omniShort || omniN <= 6 || !(omniN % 500))\n'
    '                WTFLogAlways("OMNI SHMCHECK %s n=%u fd=%d fstat=%d errno=%d st_size=%lld mode=0%o body=%zu conn=%p", omniShort ? "SHORT" : "ok", omniN, fd.value(), omniRc, omniRc ? errno : 0, omniRc ? -1LL : (long long)omniSt.st_size, omniRc ? 0u : (unsigned)omniSt.st_mode, (size_t)messageInfo.bodySize(), this);\n'
    '            if (omniShort)\n'
    '                return false;   // like a failed mapping, instead of memcpy from a missing page\n'
    '        }\n'
    '        auto handle = WebCore::SharedMemory::Handle { WTF::move(fd), messageInfo.bodySize() };\n'
    '        oolMessageBody = WebCore::SharedMemory::map(WTF::move(handle), WebCore::SharedMemory::Protection::ReadOnly);\n')

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
