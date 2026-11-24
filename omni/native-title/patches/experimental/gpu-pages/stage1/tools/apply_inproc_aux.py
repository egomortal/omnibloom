#!/usr/bin/env python3
"""OMNI_INPROC_AUX_V1 (2026-11-23): single-process plan Phase 3 - let the UI side keep generating its identifiers when a
WebKit role runs INSIDE the title.

AuxiliaryProcess::initialize() turns on "generation protection" for PAL::SessionID and WebPageProxyIdentifier ("only the
UI process should ever be generating certain identifiers"). In a separate process that only binds the child. With the
WebProcess in the title (OMNI_INPROC_NET_V1 + inproc-web.flag) it is the SAME process as the UI side, so the switch
also bound the UI: YouTube registered a service worker, WebProcessProxy::enableRemoteWorkers() called
WebPageProxyIdentifier::generate() and hit RELEASE_ASSERT(!m_generationProtected) (console 2026-11-23, 20921780, Lytiw:
WTFCrashWithInfo ObjectIdentifier.h:81, 29 s in). Fix: skip the two calls while omni_inproc_main_spin is set (it is set
by the in-process start before WebProcessMain runs); a spawned child never has it set, so it keeps the protection.
usage: apply_inproc_aux.py <WebKit/Shared/AuxiliaryProcess.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_AUX_V1'
p = Path(sys.argv[1])
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)

old = ('    // In WebKit2, only the UI process should ever be generating certain identifiers.\n'
       '    PAL::SessionID::enableGenerationProtection();\n'
       '    WebPageProxyIdentifier::enableGenerationProtection();\n')
new = ('    // In WebKit2, only the UI process should ever be generating certain identifiers.\n'
       '    // ' + MARK + ': not when this role runs inside the title - the UI side is this same process.\n'
       '    if (!omni_inproc_main_spin) {\n'
       '        PAL::SessionID::enableGenerationProtection();\n'
       '        WebPageProxyIdentifier::enableGenerationProtection();\n'
       '    }\n')
if s.count(old) != 1:
    sys.exit('%s: anchor found %d times' % (p.name, s.count(old)))
s = s.replace(old, new, 1)

# R2 (2026-11-24, console gin34): with the NetworkProcess in the title too, its initialize() overwrote the PROCESS-WIDE
# identity (WTF auxiliary process type + WebCore::Process::identifier) after the WebProcess had set them. History items
# are stamped with Process::identifier(), so the UI's MESSAGE_CHECK(itemID->processIdentifier() ==
# process->coreProcessIdentifier()) in WebPageProxy::backForwardAddItemShared failed -> didReceiveInvalidMessage
# ("WebBackForwardList_BackForwardAddItem") -> the in-app WebProcess was terminated as a crash. The page engine's identity
# must win: an in-process NETWORK role leaves both globals alone.
old2 = ('#else\n'
        '    setAuxiliaryProcessType(parameters.processType);\n'
        '#endif\n'
        '\n'
        '    RELEASE_ASSERT_WITH_MESSAGE(parameters.processIdentifier, "Unable to initialize child process without a WebCore process identifier");\n'
        '    Process::setIdentifier(*parameters.processIdentifier);\n')
new2 = ('#else\n'
        '    const bool omniKeepIdentity = omni_inproc_main_spin && parameters.processType == WTF::AuxiliaryProcessType::Network;   // ' + MARK + ' R2\n'
        '    if (!omniKeepIdentity)\n'
        '        setAuxiliaryProcessType(parameters.processType);\n'
        '#endif\n'
        '\n'
        '    RELEASE_ASSERT_WITH_MESSAGE(parameters.processIdentifier, "Unable to initialize child process without a WebCore process identifier");\n'
        '#if !PLATFORM(COCOA)\n'
        '    if (!omniKeepIdentity)   // ' + MARK + ' R2: the in-app page engine\'s identity stays (history item IDs)\n'
        '#endif\n'
        '    Process::setIdentifier(*parameters.processIdentifier);\n')
if s.count(old2) != 1:
    sys.exit('%s: R2 anchor found %d times' % (p.name, s.count(old2)))
s = s.replace(old2, new2, 1)

# R3 (2026-11-24, console gin35, with OMNI_INPROC_SPIN_V7): the in-app PAGE ENGINE marks its connection to the UI, so
# the message holding applies to its connections only (holding the network engine's reordered the UI's allowed-site
# update behind a localStorage request: NetworkStorageManager's site check failed and the page engine was terminated).
old3 = '    Ref connection = IPC::Connection::createClientConnection(WTF::move(parameters.connectionIdentifier), connectionReceiveQueueQOS());\n'
new3 = (old3 +
        '    if (omni_inproc_main_spin && parameters.processType == WTF::AuxiliaryProcessType::WebContent)   // ' + MARK + ' R3\n'
        '        omni_spin_mark_web(connection.ptr());\n')
if s.count(old3) != 1:
    sys.exit('%s: R3 anchor found %d times' % (p.name, s.count(old3)))
s = s.replace(old3, new3, 1)

anchor = '#include "config.h"\n#include "AuxiliaryProcess.h"\n'
if s.count(anchor) != 1:
    sys.exit('%s: include anchor found %d times' % (p.name, s.count(anchor)))
s = s.replace(anchor, anchor + 'extern "C" volatile int omni_inproc_main_spin;   // ' + MARK + ' (defined in IPC/Connection.cpp, OMNI_INPROC_SPIN)\n'
              'extern "C" void omni_spin_mark_web(const void*);   // ' + MARK + ' R3 (IPC/Connection.cpp, OMNI_INPROC_SPIN_V7)\n', 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
