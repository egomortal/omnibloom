#!/usr/bin/env python3
"""OMNI_INPROC_SPIN_V7 (2026-11-23): single-process plan - keep the title's main thread serving while a role that runs
INSIDE the title waits for a synchronous IPC reply, without delivering the waiting role's own messages early.

History (console, 2026-11-22/23):
 V1 (c0a89b4b) RunLoop::cycle() between 5 ms waits in Connection::waitForSyncReply: no more deadlock, app responsive,
    but the in-process WebProcess never loaded a page.
 V2 (af4f349b) also deferred the waiting connection's dispatchIncomingMessages(): same result.
 Trace (36581ac0): "unhandled message WebPage_LoadRequest dest=25" - the LoadRequest reached the WebProcess while
    WebProcess::createWebPage was still inside WebPage::create (waiting in sendSync for the network connection), before
    the page was registered, and was dropped. It came through WebKit's while-waiting lane (SyncMessageState), which the
    UI process and the in-process WebProcess SHARE (one main run loop) - in two processes each has its own.
 V3 (09d776c9) held non-sync lane messages of a waiting connection in its own queue and flushed them when its wait
    ended: still dropped - the flush ran inside a LATER nested wait (WebPage::create waits again), still before the
    page was registered.
 V4: as V3, but held connections keep holding while ANY spin wait is active on the main thread, and the in-order flush
    is scheduled only when the last wait ends (and re-checks that no new wait began).
 V5: stack trace (0fad38c3) showed the early LoadRequest came through Connection::dispatchOneIncomingMessage() (one
    task per queued message, run by RunLoop::cycle() inside the wait), a second dispatch path V4 did not hold. Held too.
 V6: V5 (7b6c839d) got past the wait and created the page, then hit ud2 in dispatchIncomingMessages(): the flush called
    the batch path on a connection WITHOUT throttling (*m_incomingMessagesThrottlingLevel on an empty optional =
    hardened-libc++ trap). The flush now uses dispatchOneIncomingMessage() per queued message unless throttling is on.
Only with omni_inproc_main_spin (set by OMNI_INPROC_NET_V1's in-process start) and on the main run loop; otherwise the
original code runs. usage: apply_inproc_spin.py <WebKit/Platform/IPC/Connection.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_SPIN_V7'
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


# 1. flag + helpers near the top (the SyncMessageState struct below already needs them)
rep('#include <wtf/RunLoop.h>\n',
    '#include <wtf/RunLoop.h>\n'
    '#include <wtf/HashCountedSet.h>   // ' + MARK + '\n'
    '#include <wtf/HashMap.h>\n'
    '#include <wtf/HashSet.h>\n'
    '// ' + MARK + ': set by Omni when a WebKit role runs inside the title (see tools/apply_inproc_spin.py)\n'
    'extern "C" { volatile int omni_inproc_main_spin = 0; }\n'
    '// main thread only: connections spin-waiting for a sync reply, and connections whose messages are held for a flush\n'
    'static WTF::HashCountedSet<const IPC::Connection*>& omniSpinWaiting() { static WTF::NeverDestroyed<WTF::HashCountedSet<const IPC::Connection*>> s; return s; }\n'
    'static WTF::HashMap<const IPC::Connection*, WTF::RefPtr<IPC::Connection>>& omniSpinHold() { static WTF::NeverDestroyed<WTF::HashMap<const IPC::Connection*, WTF::RefPtr<IPC::Connection>>> s; return s; }\n'
    '// V7: holding applies only to the in-app PAGE ENGINE\'s connections (marked by it: AuxiliaryProcess::initialize and\n'
    '// NetworkProcessConnection, see apply_inproc_aux.py / apply_inproc_webconn.py). Holding the in-app network engine\'s\n'
    '// connections reordered the UI\'s allowed-site update behind a storage request (console gin35: storage MESSAGE_CHECK).\n'
    'static WTF::HashSet<const IPC::Connection*>& omniSpinWeb() { static WTF::NeverDestroyed<WTF::HashSet<const IPC::Connection*>> s; return s; }\n'
    'extern "C" void omni_spin_mark_web(const void* c) { if (omni_inproc_main_spin && WTF::RunLoop::isMain() && c) omniSpinWeb().add(static_cast<const IPC::Connection*>(c)); }\n'
    'static bool omniSpinHolding(const IPC::Connection* c) { return omni_inproc_main_spin && WTF::RunLoop::isMain() && omniSpinWeb().contains(c) && (omniSpinWaiting().contains(c) || omniSpinHold().contains(c)); }\n')

# 2. lane delivery: hold non-sync messages of a waiting/held connection in its own queue
rep('        void dispatch()\n'
    '        {\n'
    '            Ref { connection }->dispatchMessage(WTF::move(message));\n'
    '        }\n',
    '        void dispatch()\n'
    '        {\n'
    '            if (omniSpinHolding(connection.ptr()) && !message->isSyncMessage()) {   // ' + MARK + '\n'
    '                Ref held { connection };\n'
    '                {\n'
    '                    Locker locker { held->m_incomingMessagesLock };\n'
    '                    held->m_incomingMessages.append(WTF::move(message));\n'
    '                }\n'
    '                omniSpinHold().set(held.ptr(), held.ptr());\n'
    '                return;\n'
    '            }\n'
    '            Ref { connection }->dispatchMessage(WTF::move(message));\n'
    '        }\n')

# 3. the wait: count it, spin, and when the LAST wait on this thread ends schedule one in-order flush per held connection
rep('auto Connection::waitForSyncReply(SyncRequestID syncRequestID, MessageName messageName, Timeout timeout, OptionSet<SendSyncOption> sendSyncOptions) -> DecoderOrError\n{\n',
    'auto Connection::waitForSyncReply(SyncRequestID syncRequestID, MessageName messageName, Timeout timeout, OptionSet<SendSyncOption> sendSyncOptions) -> DecoderOrError\n{\n'
    '    const bool omniSpin = omni_inproc_main_spin && RunLoop::isMain();   // ' + MARK + '\n'
    '    if (omniSpin)\n'
    '        omniSpinWaiting().add(this);\n'
    '    auto omniSpinExit = makeScopeExit([this, omniSpin] {\n'
    '        if (!omniSpin)\n'
    '            return;\n'
    '        omniSpinWaiting().remove(this);\n'
    '        if (!omniSpinWaiting().isEmpty())\n'
    '            return;   // another wait is still active on this thread: keep holding\n'
    '        for (auto& held : copyToVector(omniSpinHold().values())) {\n'
    '            if (!held)\n'
    '                continue;\n'
    '            held->dispatcher()->dispatch([conn = Ref { *held }] {\n'
    '                if (!omniSpinWaiting().isEmpty())\n'
    '                    return;   // a new wait began meanwhile; its end schedules the flush again\n'
    '                omniSpinHold().remove(conn.ptr());   // flush: held messages go out in order now\n'
    '                if (conn->isIncomingMessagesThrottlingEnabled()) {\n'
    '                    conn->dispatchIncomingMessages();   // batch path: only valid with throttling (reads the level)\n'
    '                    return;\n'
    '                }\n'
    '                size_t n;   // one-message path (what unthrottled connections use): one call per queued message\n'
    '                {\n'
    '                    Locker locker { conn->m_incomingMessagesLock };\n'
    '                    n = conn->m_incomingMessages.size();\n'
    '                }\n'
    '                for (size_t i = 0; i < n; ++i)\n'
    '                    conn->dispatchOneIncomingMessage();   // a nested wait re-holds; the rest stay queued for its flush\n'
    '            });\n'
    '        }\n'
    '    });\n')

rep('        timedOut = !protect(m_syncState)->wait(timeout);\n',
    '        if (omniSpin) {   // ' + MARK + ': serve the UI side (and replies) meanwhile; held messages stay queued\n'
    '            RunLoop::cycle();\n'
    '            if (timeout.didTimeOut())\n'
    '                timedOut = true;\n'
    '            else\n'
    '                protect(m_syncState)->wait(Timeout(std::min(timeout.secondsUntilDeadline(), Seconds::fromMilliseconds(5))));\n'
    '        } else\n'
    '            timedOut = !protect(m_syncState)->wait(timeout);\n')

# 4. the normal queue: hold while this connection waits, or while it is held and any wait is active
rep('void Connection::dispatchIncomingMessages()\n{\n',
    'void Connection::dispatchIncomingMessages()\n{\n'
    '    if (omni_inproc_main_spin && RunLoop::isMain() && omniSpinWeb().contains(this)) {   // ' + MARK + ' (V7: page engine connections only)\n'
    '        if (omniSpinWaiting().contains(this) || (omniSpinHold().contains(this) && !omniSpinWaiting().isEmpty())) {\n'
    '            omniSpinHold().set(this, this);   // flushed in order once no wait is active\n'
    '            return;\n'
    '        }\n'
    '        omniSpinHold().remove(this);   // normal dispatch drains the held queue in order\n'
    '    }\n')

# 5. V5: the one-message path (one task per queued message, run by RunLoop::cycle() inside the wait): same hold,
#    the message stays queued and goes out with the in-order flush
rep('void Connection::dispatchOneIncomingMessage()\n{\n',
    'void Connection::dispatchOneIncomingMessage()\n{\n'
    '    if (omni_inproc_main_spin && RunLoop::isMain() && omniSpinWeb().contains(this)) {   // ' + MARK + ' (V7: page engine connections only)\n'
    '        if (omniSpinWaiting().contains(this) || (omniSpinHold().contains(this) && !omniSpinWaiting().isEmpty())) {\n'
    '            omniSpinHold().set(this, this);   // stays queued; flushed in order once no wait is active\n'
    '            return;\n'
    '        }\n'
    '        omniSpinHold().remove(this);\n'
    '    }\n')
# 6. V7: a destroyed connection leaves the page-engine set (main thread only; elsewhere a stale entry only means a
#    reused address would be held like before V7)
rep('Connection::~Connection()\n{\n',
    'Connection::~Connection()\n{\n'
    '    if (omni_inproc_main_spin && RunLoop::isMain())   // ' + MARK + '\n'
    '        omniSpinWeb().remove(this);\n')
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
