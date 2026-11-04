#!/usr/bin/env python3
"""Add temporary thread diagnostics to an already patched WebKit checkout."""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
path = root / 'Source/WTF/wtf/Threading.cpp'
text = path.read_text()
anchor = '        bool success = thread->establishHandle(context.get(), stackSpec, qos, schedulingPolicy);'
if '[omni-thread-name]' not in text:
    assert anchor in text
    text = text.replace(anchor, '        fprintf(stderr, "omni thread request: %s\\n", name.characters()); fflush(stderr); // [omni-thread-name]\n' + anchor)
    path.write_text(text)

path = root / 'Source/WTF/wtf/posix/ThreadingPOSIX.cpp'
text = path.read_text()
if '[omni-thread-count]' not in text:
    text = text.replace('#include "config.h"', '#include "config.h"\n#include <sys/proc.h>\n#include <sys/user.h>\n#include <sys/sysctl.h>')
    anchor = '    int error = pthread_create(&threadHandle, &attr, wtfThreadEntryPoint, &context);'
    assert anchor in text
    text = text.replace(anchor, '''    // [omni-thread-count]
    int omniMib[] = { CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid() };
    struct kinfo_proc omniProcess = { };
    size_t omniProcessSize = sizeof(omniProcess);
    if (!sysctl(omniMib, 4, &omniProcess, &omniProcessSize, nullptr, 0))
        fprintf(stderr, "omni thread before create: threads=%d resident-pages=%ld stack=%zu\\n", omniProcess.ki_numthreads, (long)omniProcess.ki_rssize, omniStackSize);
''' + anchor)
    path.write_text(text)

if '[omni-thread-all-processes]' not in text:
    anchor = '    int omniMib[] = { CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid() };'
    assert anchor in text
    start = text.index(anchor)
    end = text.index('    int error = pthread_create', start)
    text = text[:start] + '''    // [omni-thread-all-processes]
    int omniMib[] = { CTL_KERN, KERN_PROC, KERN_PROC_PROC, 0 };
    size_t omniSize = 0;
    if (!sysctl(omniMib, 4, nullptr, &omniSize, nullptr, 0)) {
        char* omniBuffer = static_cast<char*>(malloc(omniSize));
        if (omniBuffer && !sysctl(omniMib, 4, omniBuffer, &omniSize, nullptr, 0)) {
            for (char* p = omniBuffer; p < omniBuffer + omniSize;) {
                auto* proc = reinterpret_cast<struct kinfo_proc*>(p);
                if (!proc->ki_structsize) break;
                p += proc->ki_structsize;
                if (proc->ki_pid == getpid())
                    fprintf(stderr, "omni thread before create: threads=%d resident-pages=%ld stack=%zu\\n", proc->ki_numthreads, (long)proc->ki_rssize, omniStackSize);
            }
        }
        free(omniBuffer);
    }
''' + text[end:]
    path.write_text(text)

