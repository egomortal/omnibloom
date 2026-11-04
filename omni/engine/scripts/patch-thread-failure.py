#!/usr/bin/env python3
"""Record the requested thread name and callers only on thread creation failure."""
from pathlib import Path
import sys
p = Path(sys.argv[1]) / 'Source/WTF/wtf/Threading.cpp'
s = p.read_text()
if 'omni_thread_failure_frame' not in s:
    s = s.replace('#include "config.h"', '''#include "config.h"
#if PLATFORM(PLAYSTATION)
#include <unwind.h>
#include <stdio.h>
static _Unwind_Reason_Code omni_thread_failure_frame(_Unwind_Context* context, void* opaque)
{
    auto* depth = static_cast<unsigned*>(opaque);
    fprintf(stderr, "thread failure stack[%u]=%p\\n", *depth, reinterpret_cast<void*>(_Unwind_GetIP(context)));
    return ++*depth >= 20 ? _URC_END_OF_STACK : _URC_NO_REASON;
}
#endif''', 1)
    anchor = '        bool success = thread->establishHandle(context.get(), stackSpec, qos, schedulingPolicy);'
    assert s.count(anchor) == 1
    s = s.replace(anchor, anchor + '''
#if PLATFORM(PLAYSTATION)
        if (!success) {
            fprintf(stderr, "thread creation failed: name=%s\\n", name.characters());
            unsigned depth = 0;
            _Unwind_Backtrace(omni_thread_failure_frame, &depth);
            fflush(stderr);
        }
#endif''')
    p.write_text(s)

# Query the actual failing process, rather than inferring its pool from RSS.
s = p.read_text()
if 'omni thread failure flexible' not in s:
    s = s.replace('#include <stdio.h>', '#include <stdio.h>\nextern "C" int sceKernelAvailableFlexibleMemorySize(size_t*);', 1)
    anchor = '            unsigned depth = 0;'
    assert s.count(anchor) == 1
    s = s.replace(anchor, '''            size_t available = 0;
            int memoryResult = sceKernelAvailableFlexibleMemorySize(&available);
            fprintf(stderr, "omni thread failure flexible: result=%d available=%zu\\n", memoryResult, available);
''' + anchor)
    p.write_text(s)
