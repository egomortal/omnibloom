#!/usr/bin/env python3
"""OMNI_INPROC_TRACE_V1 (2026-11-22): trace lines along the page-load path, to find where an in-process WebProcess stops.

Phase 3 (c0a89b4b): the WebProcess runs on the title main thread without deadlock, but the page never leaves "loading".
WebKit's RELEASE_LOG is compiled out on PlayStation (no OS_LOG / journald), so this adds WTFLogAlways() lines (always
compiled, stderr) at the start of the functions a first navigation passes through, plus the GetNetworkProcessConnection
reply. Each line carries the pid and whether it runs on the main thread. TEST BUILDS ONLY: the recipe applies this for
one ninja run and restores the originals (mode: apply <src> <backupdir> | restore <src> <backupdir>).
<src> = .../webkit/Source/WebKit"""
import shutil
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_TRACE_V1'
mode, src, bak = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
T = 'WTFLogAlways("OMNI TRACE %s pid=%%d main=%%d", (int)getpid(), (int)isMainThread()); // ' + MARK

# (file, exact function signature line, label)
FUNCS = [
    ('WebProcess/WebProcess.cpp', 'void WebProcess::initializeWebProcess(WebProcessCreationParameters&& parameters, CompletionHandler<void(ProcessIdentity)>&& completionHandler)', 'WebProcess::initializeWebProcess'),
    ('WebProcess/WebProcess.cpp', 'void WebProcess::createWebPage(PageIdentifier pageID, WebPageCreationParameters&& parameters)', 'WebProcess::createWebPage'),
    ('WebProcess/WebProcess.cpp', 'NetworkProcessConnection& WebProcess::ensureNetworkProcessConnection()', 'WebProcess::ensureNetworkProcessConnection'),
    ('WebProcess/WebPage/WebPage.cpp', 'void WebPage::loadRequest(LoadParameters&& loadParameters)', 'WebPage::loadRequest'),
    ('WebProcess/Network/WebLoaderStrategy.cpp', 'void WebLoaderStrategy::scheduleLoad(ResourceLoader& resourceLoader, CachedResource* resource, bool shouldClearReferrerOnHTTPSToHTTPRedirect)', 'WebLoaderStrategy::scheduleLoad'),
    ('UIProcess/WebProcessProxy.cpp', 'void WebProcessProxy::getNetworkProcessConnection(CompletionHandler<void(NetworkProcessConnectionInfo&&)>&& reply)', 'UI WebProcessProxy::getNetworkProcessConnection'),
    ('UIProcess/WebProcessProxy.cpp', 'void WebProcessProxy::didFinishLaunching(ProcessLauncher* launcher, IPC::Connection::Identifier&& connectionIdentifier)', 'UI WebProcessProxy::didFinishLaunching'),
    ('UIProcess/Network/NetworkProcessProxy.cpp', 'void NetworkProcessProxy::getNetworkProcessConnection(WebProcessProxy& webProcessProxy, CompletionHandler<void(NetworkProcessConnectionInfo&&)>&& reply)', 'UI NetworkProcessProxy::getNetworkProcessConnection'),
    ('UIProcess/WebPageProxy.cpp', 'RefPtr<API::Navigation> WebPageProxy::loadRequest(WebCore::ResourceRequest&& request, ShouldOpenExternalURLsPolicy shouldOpenExternalURLsPolicy, NavigationUpgradeToHTTPSBehavior navigationUpgradeToHTTPSBehavior, std::unique_ptr<NavigationActionData>&& lastNavigationAction, API::Object* userData, bool isRequestFromClientOrUserInput)', 'UI WebPageProxy::loadRequest'),
]
UISTACK = ('{ void** omniFp = (void**)__builtin_frame_address(0); for (int omniI = 0; omniI < 16 && omniFp; ++omniI) { '
           'WTFLogAlways("OMNI TRACE  ui-stack %d %p", omniI, omniFp[1]); void** omniNext = (void**)omniFp[0]; '
           'if (omniNext <= omniFp) break; omniFp = omniNext; } } ')
EXTRA = [   # (file, exact line, inserted after it)
    # 2026-11-24 (gin32): why the UI decides an in-process WebProcess ended (reason + who called)
    ('UIProcess/WebProcessProxy.cpp', 'void WebProcessProxy::didClose(IPC::Connection& connection)',
     '#SKIP1#    WTFLogAlways("OMNI TRACE UI WebProcessProxy::didClose pid=%d", (int)getpid()); ' + UISTACK + '// ' + MARK),
    # gin33: the close came from didReceiveInvalidMessage (reason Crash, nothing crashed): which message, which argument
    ('UIProcess/WebProcessProxy.cpp', 'void WebProcessProxy::didReceiveInvalidMessage(IPC::Connection& connection, IPC::MessageName messageName, const Vector<uint32_t>& indexOfObjectFailingDecoding)',
     '#SKIP1#    WTFLogAlways("OMNI TRACE UI invalid message %s failing-args=%zu first=%d", IPC::description(messageName).characters(), '
     '(size_t)indexOfObjectFailingDecoding.size(), indexOfObjectFailingDecoding.isEmpty() ? -1 : (int)indexOfObjectFailingDecoding[0]); // ' + MARK),
    ('UIProcess/WebProcessProxy.cpp', 'void WebProcessProxy::processDidTerminateOrFailedToLaunch(ProcessTerminationReason reason)',
     '#SKIP1#    WTFLogAlways("OMNI TRACE UI processDidTerminateOrFailedToLaunch reason=%d", (int)reason); ' + UISTACK + '// ' + MARK),
    ('WebProcess/WebProcess.cpp', '        std::tie(connectionInfo) = sendResult.takeReply();',
     '        WTFLogAlways("OMNI TRACE getNetworkProcessConnection reply connection=%d pid=%d", (int)!!connectionInfo.connection, (int)getpid()); // ' + MARK),
    ('WebProcess/WebProcess.cpp', '    Ref page { addResult.iterator->value };',
     '    WTFLogAlways("OMNI TRACE createWebPage new=%d pages=%u", (int)addResult.isNewEntry, (unsigned)m_pageMap.size()); // ' + MARK),
    ('UIProcess/WebPageProxy.cpp', '        navigation->setIsLoadedWithNavigationShared(true);',
     '        WTFLogAlways("OMNI TRACE UI send LoadRequest launching=%d", (int)process->isLaunching()); // ' + MARK),
    ('Shared/AuxiliaryProcess.cpp', '    if (m_messageReceiverMap.dispatchMessage(connection, decoder))',
     '#SKIP1#    WTFLogAlways("OMNI TRACE unhandled message %s dest=%llu pid=%d", description(decoder.messageName()).characters(), (unsigned long long)decoder.destinationID(), (int)getpid()); '
     '{ void** omniFp = (void**)__builtin_frame_address(0); for (int omniI = 0; omniI < 24 && omniFp; ++omniI) { WTFLogAlways("OMNI TRACE  stack %d %p", omniI, omniFp[1]); void** omniNext = (void**)omniFp[0]; if (omniNext <= omniFp) break; omniFp = omniNext; } } // ' + MARK),
]
files = sorted({f for f, _, _ in FUNCS} | {f for f, _, _ in EXTRA})

if mode == 'restore':
    for f in files:
        b = bak / f.replace('/', '__')
        if b.exists():
            shutil.copy2(b, src / f)   # original bytes AND original mtime
    print('restored', len(files)); sys.exit(0)

bak.mkdir(parents=True, exist_ok=True)
done = 0
for f in files:
    p = src / f
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        continue
    shutil.copy2(p, bak / f.replace('/', '__'))
    nl = '\r\n' if '\r\n' in s else '\n'
    lines = s.replace('\r\n', '\n').split('\n')
    for ff, sig, label in FUNCS:
        if ff != f:
            continue
        idx = [i for i, l in enumerate(lines) if l == sig]
        if len(idx) != 1:
            sys.exit('%s: signature found %d times: %s' % (f, len(idx), sig[:60]))
        j = idx[0] + 1
        if lines[j] != '{':
            sys.exit('%s: no opening brace after %s' % (f, sig[:60]))
        lines.insert(j + 1, '    ' + T % label)
        done += 1
    for ff, line, ins in EXTRA:
        if ff != f:
            continue
        idx = [i for i, l in enumerate(lines) if l == line]
        if len(idx) != 1:
            sys.exit('%s: line found %d times: %s' % (f, len(idx), line[:60]))
        if ins.startswith('#SKIP1#'):
            lines.insert(idx[0] + 2, ins[len('#SKIP1#'):])
        else:
            lines.insert(idx[0] + 1, ins)
        done += 1
    body = '\n'.join(lines)
    if 'unistd.h' not in body:
        body = body.replace('#include "config.h"\n', '#include "config.h"\n#include <unistd.h> // ' + MARK + '\n', 1)
    p.write_bytes(body.replace('\n', nl).encode('utf-8'))
print('applied %d trace points in %d files' % (done, len(files)))
