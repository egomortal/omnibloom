#!/usr/bin/env python3
"""Serialize PS5 IPC reads with invalidation; avoid an extra thread per socket."""
from pathlib import Path
import sys
root = Path(sys.argv[1]) / 'Source/WebKit/Platform/IPC'
p = root / 'Connection.h'
s = p.read_text()
if 'm_socketMonitorTimer' not in s:
    assert s.count('    RefPtr<WTF::Thread> m_socketMonitor;') == 1
    s = s.replace('    RefPtr<WTF::Thread> m_socketMonitor;', '    std::unique_ptr<RunLoop::Timer> m_socketMonitorTimer;')
    s = s.replace('#pragma once', '#pragma once\n#include <wtf/RunLoop.h>', 1)
    p.write_text(s)

p = root / 'unix/ConnectionUnix.cpp'
s = p.read_text()
if '// omni serialized socket monitoring' not in s:
    old = '''    if (m_socketMonitor) {
        m_socketMonitor->detach();
        m_socketMonitor = nullptr;
    }'''
    assert s.count(old) == 1
    s = s.replace(old, '''    if (m_socketMonitorTimer) {
        m_socketMonitorTimer->stop();
        m_socketMonitorTimer = nullptr;
    }''')
    start = s.index('    m_socketMonitor = Thread::create("SocketMonitor"_s, [protectedThis] {')
    end = s.index('    return;\n#endif', start)
    s = s[:start] + '''    // omni serialized socket monitoring: existing queue owns reads and teardown.
    // Timer captures a raw owner, not a strong cycle; callbacks protect lifetime.
    m_connectionQueue->dispatch([protectedThis] {
        if (!protectedThis->m_isConnected)
            return;
        protectedThis->m_socketMonitorTimer = makeUnique<RunLoop::Timer>(
            Ref { RunLoop::currentSingleton() }, "IPC socket readiness"_s,
            [connection = protectedThis.get()] {
                Ref protect { *connection };
                if (connection->m_isConnected)
                    connection->readyReadHandler();
            });
        protectedThis->m_socketMonitorTimer->startRepeating(5_ms);
        protectedThis->readyReadHandler();
    });
''' + s[end:]
    old = '        ssize_t bytesRead = recvmsg(socketDescriptor, &message, MSG_NOSIGNAL);'
    assert s.count(old) == 1
    s = s.replace(old, '''#if PLATFORM(PLAYSTATION)
        ssize_t bytesRead = recvmsg(socketDescriptor, &message, MSG_NOSIGNAL | MSG_DONTWAIT);
#else
''' + old + '\n#endif')
    old = 'void Connection::readyReadHandler()\n{\n    while (true) {'
    assert s.count(old) == 1
    s = s.replace(old, '''void Connection::readyReadHandler()
{
#if PLATFORM(PLAYSTATION)
    // Yield to writes and invalidation even when a peer continuously sends.
    for (unsigned readBudget = 0; readBudget < 32; ++readBudget) {
#else
    while (true) {
#endif''')
    p.write_text(s)

# Reads and writes share a queue: never block that queue waiting for POLLOUT.
# UnixMessage's move constructor owns inline bytes and transfers attachments.
p = root / 'Connection.h'
s = p.read_text()
if 'm_pendingSocketMessage' not in s:
    anchor = '    std::unique_ptr<RunLoop::Timer> m_socketMonitorTimer;'
    assert s.count(anchor) == 1
    s = s.replace(anchor, anchor + '\n    std::unique_ptr<UnixMessage> m_pendingSocketMessage;')
    p.write_text(s)
p = root / 'unix/ConnectionUnix.cpp'
s = p.read_text()
if '// omni nonblocking output retry' not in s:
    anchor = '        m_socketMonitorTimer = nullptr;\n    }'
    assert s.count(anchor) == 1
    s = s.replace(anchor, anchor + '\n    m_pendingSocketMessage = nullptr;', 1)
    anchor = '''                if (connection->m_isConnected)
                    connection->readyReadHandler();'''
    assert s.count(anchor) == 1
    s = s.replace(anchor, anchor + '''
                if (connection->m_isConnected && connection->m_pendingSocketMessage) {
                    auto pending = std::exchange(connection->m_pendingSocketMessage, nullptr);
                    if (connection->sendOutputMessage(WTF::move(*pending)))
                        connection->sendOutgoingMessages();
                }''')
    anchor = 'bool Connection::platformCanSendOutgoingMessages() const\n{\n    return true;\n}'
    assert s.count(anchor) == 1
    s = s.replace(anchor, '''bool Connection::platformCanSendOutgoingMessages() const
{
#if PLATFORM(PLAYSTATION)
    return !m_pendingSocketMessage;
#else
    return true;
#endif
}''')
    anchor = '    while (sendmsg(socketDescriptor(), &message, MSG_NOSIGNAL) == -1) {'
    assert s.count(anchor) == 1
    s = s.replace(anchor, '''#if PLATFORM(PLAYSTATION)
    // omni nonblocking output retry: retain message and attachments in FIFO order.
    constexpr int sendFlags = MSG_NOSIGNAL | MSG_DONTWAIT;
#else
    constexpr int sendFlags = MSG_NOSIGNAL;
#endif
    while (sendmsg(socketDescriptor(), &message, sendFlags) == -1) {''')
    anchor = '''        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            struct pollfd pollfd;'''
    assert s.count(anchor) == 1
    s = s.replace(anchor, '''        if (errno == EAGAIN || errno == EWOULDBLOCK) {
#if PLATFORM(PLAYSTATION)
            RELEASE_ASSERT(!m_pendingSocketMessage);
            m_pendingSocketMessage = makeUnique<UnixMessage>(WTF::move(outputMessage));
            return false;
#else
            struct pollfd pollfd;''')
    anchor = '            poll(&pollfd, 1, -1);\n            continue;\n        }'
    assert s.count(anchor) == 1
    s = s.replace(anchor, '            poll(&pollfd, 1, -1);\n            continue;\n#endif\n        }')
    p.write_text(s)

# A deferred last message must still prevent flushSentMessages from succeeding.
p = root / 'Connection.h'
s = p.read_text()
if 'm_socketWriteInProgress' not in s:
    s = s.replace('    std::unique_ptr<UnixMessage> m_pendingSocketMessage;',
        '    std::unique_ptr<UnixMessage> m_pendingSocketMessage;\n    bool m_socketWriteInProgress { false }; // guarded by m_outgoingMessagesLock')
    p.write_text(s)
p = root / 'Connection.cpp'
s = p.read_text()
if '// omni pending write flush' not in s:
    start = s.index('Error Connection::flushSentMessages(')
    end = s.index('void Connection::invalidate()', start)
    block = s[start:end]
    block = block.replace('        if (m_outgoingMessages.isEmpty())', '''#if PLATFORM(PLAYSTATION)
        // omni pending write flush
        if (m_outgoingMessages.isEmpty() && !m_socketWriteInProgress)
#else
        if (m_outgoingMessages.isEmpty())
#endif''')
    s = s[:start] + block + s[end:]
    anchor = '            message = m_outgoingMessages.takeFirst().moveToUniquePtr();'
    assert s.count(anchor) == 1
    s = s.replace(anchor, '''#if PLATFORM(PLAYSTATION)
            m_socketWriteInProgress = true;
#endif
''' + anchor)
    anchor = '''        if (!sendOutgoingMessage(makeUniqueRefFromNonNullUniquePtr(WTF::move(message))))
            break;'''
    assert s.count(anchor) == 1
    s = s.replace(anchor, '''        bool sent = sendOutgoingMessage(makeUniqueRefFromNonNullUniquePtr(WTF::move(message)));
#if PLATFORM(PLAYSTATION)
        if (!m_pendingSocketMessage) {
            Locker locker { m_outgoingMessagesLock };
            m_socketWriteInProgress = false;
            m_outgoingMessagesEmptyCondition.notifyAll();
        }
#endif
        if (!sent)
            break;''')
    p.write_text(s)
p = root / 'unix/ConnectionUnix.cpp'
s = p.read_text()
if '// omni complete deferred flush' not in s:
    anchor = '    m_pendingSocketMessage = nullptr;'
    assert s.count(anchor) == 1
    s = s.replace(anchor, anchor + '''
    {
        Locker locker { m_outgoingMessagesLock };
        m_socketWriteInProgress = false;
        m_outgoingMessagesEmptyCondition.notifyAll();
    }''', 1)
    anchor = '''                    if (connection->sendOutputMessage(WTF::move(*pending)))
                        connection->sendOutgoingMessages();'''
    assert s.count(anchor) == 1
    s = s.replace(anchor, '''                    bool sent = connection->sendOutputMessage(WTF::move(*pending));
                    // omni complete deferred flush
                    if (!connection->m_pendingSocketMessage) {
                        Locker locker { connection->m_outgoingMessagesLock };
                        connection->m_socketWriteInProgress = false;
                        connection->m_outgoingMessagesEmptyCondition.notifyAll();
                    }
                    if (sent)
                        connection->sendOutgoingMessages();''')
    p.write_text(s)


# The callback may destroy its own timer: use only the local Ref after acquiring it.
p = root / 'unix/ConnectionUnix.cpp'
s = p.read_text()
start = s.index('                Ref protect { *connection };')
end = s.index('            });', start)
s = s[:start] + s[start:end].replace('connection->', 'protect->') + s[end:]
if '// omni forced socket pressure' not in s:
    anchor = '    m_socketDescriptor = WTF::move(identifier.handle);'
    assert s.count(anchor) == 1
    s = s.replace(anchor, anchor + '''
#if PLATFORM(PLAYSTATION)
    // omni forced socket pressure: diagnostic flag only.
    if (!access("/data/omni/ipc-pressure-selftest.flag", F_OK)) {
        int bytes = 4096;
        setsockopt(socketDescriptor(), SOL_SOCKET, SO_SNDBUF, &bytes, sizeof(bytes));
    }
#endif''')
    anchor = '            RELEASE_ASSERT(!m_pendingSocketMessage);'
    s = s.replace(anchor, '''            if (!access("/data/omni/ipc-pressure-selftest.flag", F_OK))
                fprintf(stderr, "IPC pressure: deferred socket write\\n");
''' + anchor)
p.write_text(s)
