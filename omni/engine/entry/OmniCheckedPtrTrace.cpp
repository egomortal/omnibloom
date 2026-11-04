// Diagnostic only: retain the original fatal assertion after logging callers.
// SPDX-License-Identifier: GPL-3.0-or-later
#include <cstdio>
#include <unistd.h>
#include <unwind.h>

static _Unwind_Reason_Code traceCaller(_Unwind_Context* context, void* opaque)
{
    auto& depth = *static_cast<unsigned*>(opaque);
    char line[96];
    int length = snprintf(line, sizeof(line), "checked-pointer stack[%u]=%p\n", depth, reinterpret_cast<void*>(_Unwind_GetIP(context)));
    if (length > 0) write(2, line, static_cast<size_t>(length) < sizeof(line) ? static_cast<size_t>(length) : sizeof(line) - 1);
    return ++depth >= 24 ? _URC_END_OF_STACK : _URC_NO_REASON;
}

// Exact symbol from the pinned WebKit/libc++ build. --wrap redirects callers;
// __real resolves back to the unchanged upstream assertion. Not a signal handler.
extern "C" [[noreturn]] void originalCheckedPtrCrash() asm("__real__ZN3WTF21CanMakeCheckedPtrBaseINSt3__16atomicIjEEjNS2_IbEELNS_30CheckedPtrDeleteCheckExceptionE0EE32crashDueToCheckedPtrToDeadObjectEv");
extern "C" [[noreturn]] void tracedCheckedPtrCrash() asm("__wrap__ZN3WTF21CanMakeCheckedPtrBaseINSt3__16atomicIjEEjNS2_IbEELNS_30CheckedPtrDeleteCheckExceptionE0EE32crashDueToCheckedPtrToDeadObjectEv");
extern "C" [[noreturn]] void tracedCheckedPtrCrash()
{
    if (!access("/data/omni/crash-diagnostics.flag", F_OK)) {
        unsigned depth = 0;
        _Unwind_Backtrace(traceCaller, &depth);
    }
    originalCheckedPtrCrash();
}
