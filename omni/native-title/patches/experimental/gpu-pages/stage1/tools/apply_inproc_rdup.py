#!/usr/bin/env python3
"""OMNI_INPROC_RDUP_V1 (2026-11-23): single-process plan Phase 3 - hardware video/audio channels when the WebProcess
runs INSIDE the title.

OmniHwClient (video) and OmniAudioRelay (audio) claim a channel from the decode/audio service and copy its descriptors
out of the service process with omni_remote_dup(servicePid, fd) = Sony syscall 0x25b. The services already run in the
title; with the WebProcess in the title too, servicePid == getpid() and the syscall fails for our own process, so the
client dropped its claim and reported "decode service unreachable" (console 2026-11-23, gin18 Lytiwnv: software decode,
no playback).

Fix in omni-rdup.h: when pid is our own, copy the descriptor locally instead - dup() first (in the title it is wrapped:
named shared memory is reopened by name, OMNI_NATIVE_SHM_V1), and for sockets, which the title refuses to dup (EPERM),
pass it to ourselves with SCM_RIGHTS (the same method as OMNI_INPROC_NET_V1's omniInprocScmDup). A child never asks for
its own pid, so children are unchanged.
usage: apply_inproc_rdup.py <engine/ports/webkit-requirements/src/omni-rdup.h>"""
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_RDUP_V1'
p = Path(sys.argv[1])
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)

old = ('// Sony syscall 0x25b: duplicate descriptor `fd` of process `pid` into us.\n'
       'static inline int omni_remote_dup(pid_t pid, int fd)\n'
       '{\n'
       '    return syscall(0x25b, pid, fd);\n'
       '}\n')
new = ('// ' + MARK + ': a copy of one of OUR OWN descriptors (a service in this same process) - dup, else SCM_RIGHTS.\n'
       'static inline int omni_self_dup(int fd)\n'
       '{\n'
       '    int out = dup(fd);\n'
       '    if (out >= 0)\n'
       '        return out;\n'
       '    int sv[2];\n'
       '    if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv))\n'
       '        return -1;\n'
       '    char b = 0;\n'
       '    struct iovec io = { &b, 1 };\n'
       '    char cbuf[CMSG_SPACE(sizeof(int))];\n'
       '    memset(cbuf, 0, sizeof cbuf);\n'
       '    struct msghdr m;\n'
       '    memset(&m, 0, sizeof m);\n'
       '    m.msg_iov = &io; m.msg_iovlen = 1; m.msg_control = cbuf; m.msg_controllen = sizeof cbuf;\n'
       '    struct cmsghdr* c = CMSG_FIRSTHDR(&m);\n'
       '    c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS; c->cmsg_len = CMSG_LEN(sizeof(int));\n'
       '    memcpy(CMSG_DATA(c), &fd, sizeof fd);\n'
       '    if (sendmsg(sv[0], &m, 0) == 1) {\n'
       '        char rb = 0;\n'
       '        struct iovec ri = { &rb, 1 };\n'
       '        char rcbuf[CMSG_SPACE(sizeof(int))];\n'
       '        memset(rcbuf, 0, sizeof rcbuf);\n'
       '        struct msghdr r;\n'
       '        memset(&r, 0, sizeof r);\n'
       '        r.msg_iov = &ri; r.msg_iovlen = 1; r.msg_control = rcbuf; r.msg_controllen = sizeof rcbuf;\n'
       '        if (recvmsg(sv[1], &r, 0) == 1) {\n'
       '            struct cmsghdr* rc = CMSG_FIRSTHDR(&r);\n'
       '            if (rc && rc->cmsg_level == SOL_SOCKET && rc->cmsg_type == SCM_RIGHTS)\n'
       '                memcpy(&out, CMSG_DATA(rc), sizeof out);\n'
       '        }\n'
       '    }\n'
       '    close(sv[0]);\n'
       '    close(sv[1]);\n'
       '    return out;\n'
       '}\n'
       '\n'
       '// Sony syscall 0x25b: duplicate descriptor `fd` of process `pid` into us.\n'
       'static inline int omni_remote_dup(pid_t pid, int fd)\n'
       '{\n'
       '    if (pid == getpid())   // ' + MARK + ': the syscall refuses our own process (in-process WebProcess)\n'
       '        return omni_self_dup(fd);\n'
       '    return syscall(0x25b, pid, fd);\n'
       '}\n')
if s.count(old) != 1:
    sys.exit('%s: anchor found %d times' % (p.name, s.count(old)))
s = s.replace(old, new, 1)
inc = '#include <sys/socket.h>\n#include <pthread.h>\n'
if s.count(inc) != 1:
    sys.exit('%s: include anchor found %d times' % (p.name, s.count(inc)))
s = s.replace(inc, inc + '#include <sys/uio.h>   // ' + MARK + '\n', 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
