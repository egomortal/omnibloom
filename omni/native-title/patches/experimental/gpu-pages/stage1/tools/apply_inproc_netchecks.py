#!/usr/bin/env python3
"""OMNI_INPROC_NETCHECKS_V1 (2026-11-24): with the page engine AND the network engine inside the title, the network
engine's per-site trust checks against the page engine race and kill it.

Console gin35/gin36: page JavaScript read localStorage -> sync ConnectToStorageAreaSync to the in-app network engine;
NetworkStorageManager (its own work queue) ran STORAGE_MESSAGE_CHECK(canConnectionAccessSiteForWebStorage) before the
network engine's MAIN thread had handled the UI's allowed-site registration for that connection - the main thread was
busy running that very JavaScript (in two processes the network engine's main thread is idle, so the registration always
lands first). NetworkConnectionToWebProcess::didReceiveInvalidMessage then asked the UI to terminate the page engine
(reason RequestedByNetworkProcess).

These checks exist so a compromised PAGE PROCESS cannot reach other sites' cookies/storage across a process boundary.
With the page engine inside the title there is no boundary: it shares memory with everything. So, only while
omni_inproc_main_spin is set (an engine runs in the title; never in a child):
  NetworkStorageManager::canConnectionAccessSiteForWebStorage -> true
  NetworkProcess::allowsFirstPartyForCookies(id, domain)     -> Allow for a non-empty domain
  NetworkConnectionToWebProcess::didReceiveInvalidMessage    -> logged, no termination request
TEST BUILDS: applied for one ninja run and restored (mode: apply <src> <backupdir> | restore <src> <backupdir>),
<src> = .../webkit/Source/WebKit"""
import shutil
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_NETCHECKS_V1'
mode, src, bak = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
DECL = 'extern "C" volatile int omni_inproc_main_spin;   // ' + MARK + ' (IPC/Connection.cpp, OMNI_INPROC_SPIN)\n'
EDITS = {
    'NetworkProcess/storage/NetworkStorageManager.cpp': [
        ('bool NetworkStorageManager::canConnectionAccessSiteForWebStorage(IPC::Connection& connection, const WebCore::RegistrableDomain& site) const\n{\n',
         'bool NetworkStorageManager::canConnectionAccessSiteForWebStorage(IPC::Connection& connection, const WebCore::RegistrableDomain& site) const\n{\n'
         '    if (omni_inproc_main_spin)   // ' + MARK + ': the in-app page engine (no process boundary to enforce)\n'
         '        return true;\n'),
    ],
    'NetworkProcess/NetworkProcess.cpp': [
        ('auto NetworkProcess::allowsFirstPartyForCookies(WebCore::ProcessIdentifier processIdentifier, const RegistrableDomain& firstPartyDomain) -> AllowCookieAccess\n{\n',
         'auto NetworkProcess::allowsFirstPartyForCookies(WebCore::ProcessIdentifier processIdentifier, const RegistrableDomain& firstPartyDomain) -> AllowCookieAccess\n{\n'
         '    if (omni_inproc_main_spin && !firstPartyDomain.isEmpty())   // ' + MARK + '\n'
         '        return AllowCookieAccess::Allow;\n'),
    ],
    'NetworkProcess/NetworkConnectionToWebProcess.cpp': [
        ('void NetworkConnectionToWebProcess::didReceiveInvalidMessage(IPC::Connection&, IPC::MessageName messageName, const Vector<uint32_t>&)\n{\n',
         'void NetworkConnectionToWebProcess::didReceiveInvalidMessage(IPC::Connection&, IPC::MessageName messageName, const Vector<uint32_t>&)\n{\n'
         '    if (omni_inproc_main_spin) {   // ' + MARK + ': logged, the in-app page engine is not terminated\n'
         '        WTFLogAlways("OMNI INPROC NET: invalid message %s from the in-app page engine (logged only)", description(messageName).characters());\n'
         '        return;\n'
         '    }\n'),
    ],
}

if mode == 'restore':
    for f in EDITS:
        b = bak / f.replace('/', '__')
        if b.exists():
            shutil.copy2(b, src / f)   # original bytes and mtime
    print('restored', len(EDITS)); sys.exit(0)

bak.mkdir(parents=True, exist_ok=True)
done = 0
for f, edits in EDITS.items():
    p = src / f
    raw = p.read_bytes().decode('utf-8')
    if MARK in raw:
        continue
    shutil.copy2(p, bak / f.replace('/', '__'))
    nl = '\r\n' if '\r\n' in raw else '\n'
    s = raw.replace('\r\n', '\n')
    for old, new in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (f, s.count(old), old[:70]))
        s = s.replace(old, new, 1)
    if s.count('#include "config.h"\n') != 1:
        sys.exit('%s: config.h include found %d times' % (f, s.count('#include "config.h"\n')))
    s = s.replace('#include "config.h"\n', '#include "config.h"\n' + DECL, 1)
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    done += 1
print('applied %d files' % done)
