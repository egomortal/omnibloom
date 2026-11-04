#!/usr/bin/env python3
"""Use the verified PS5 signal machine-context offset for suspended-thread GC.

Reference: mihawk-99/PS5_PayloadSDK platform/include/ps5platform/context.h.
Validated on this console by signal_context_probe.c: 100/100 saved-stack and
callee-saved-register checks; SDK offset 16 fails, console offset 64 passes.
"""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'Source/WTF/wtf/posix/ThreadingPOSIX.cpp'
text = path.read_text()
anchor = '''#if HAVE(MACHINE_CONTEXT)
    ucontext_t* userContext = static_cast<ucontext_t*>(ucontext);
    thread->m_platformRegisters = &registersFromUContext(userContext);'''
replacement = '''#if PLATFORM(PLAYSTATION) && HAVE(MACHINE_CONTEXT)
    // Omni: PS5 inserts 48 bytes before uc_mcontext relative to FreeBSD.
    // Preserve the actual saved registers; never clamp or omit GC roots.
    static_assert(offsetof(ucontext_t, uc_mcontext) == 16 || offsetof(ucontext_t, uc_mcontext) == 64);
    thread->m_platformRegisters = reinterpret_cast<PlatformRegisters*>(static_cast<char*>(ucontext) + 64);
#elif HAVE(MACHINE_CONTEXT)
    ucontext_t* userContext = static_cast<ucontext_t*>(ucontext);
    thread->m_platformRegisters = &registersFromUContext(userContext);'''
if anchor in text:
    assert text.count(anchor) == 1
    path.write_text(text.replace(anchor, replacement))
else:
    assert replacement in text
