#!/usr/bin/env python3
"""OMNI_STARTER_V1 (2026-11-15, owner: "cut the spike"): the title starts its engine processes through Omni's own
engine starter (outputs/omni-starter, /data/omni/native/omni-starter.elf, 127.0.0.1:9031) instead of elfldr (9021).

Why: elfldr reads the ~196 MB engine ELF into memory and relocates it in a second full-size copy; its allocator keeps
that memory, so it held ~240 MB (up to ~420 MB while starting two engines) during every page load, when the console's
memory runs out (kernel "LOW FMEM", free pages down to 2-15; console restarts, games crash). The starter maps the ELF
file and relocates it in 16 MB pieces, then gives the memory back.

nativeSpawn() (NativeLauncherState.cpp) asks omniEnginePort() which loader to use:
  - /data/omni/starter-off.flag, or no /data/omni/native/omni-starter.elf: elfldr, as before;
  - the starter answers on 127.0.0.1:9031: the starter;
  - otherwise the title starts it once through elfldr (it is small) and waits up to 2 s for its port; if it doesn't
    come up, elfldr for the rest of this session.
A refused connect to the starter falls back to elfldr for that spawn. Idempotent; each anchor exactly once.
usage: apply_starter.py <title src dir (NativeLauncherState.cpp)>"""
import sys
from pathlib import Path

MARK = 'OMNI_STARTER_V1'
p = Path(sys.argv[1]) / 'NativeLauncherState.cpp'
raw = p.read_bytes().decode('utf-8')
crlf = '\r\n' in raw
t = raw.replace('\r\n', '\n')
if MARK in t:
    print('already ' + MARK)
    sys.exit(0)

HELPERS = r'''// OMNI_STARTER_V1 (outputs/omni-starter): Omni's own engine starter instead of elfldr for the engine processes.
#include <mutex>
static const char kOmniStarter[] = "/data/omni/native/omni-starter.elf";
static bool omniStarterUp()
{
 int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return false;
 sockaddr_in a{};a.sin_family=AF_INET;a.sin_port=htons(9031);a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
 bool ok=!connect(fd,reinterpret_cast<sockaddr*>(&a),sizeof(a));close(fd);return ok;   // the starter ignores an empty request
}
static int omniEnginePort()
{
 if(!access("/data/omni/starter-off.flag",F_OK)||access(kOmniStarter,F_OK))return 9021;
 static std::mutex m;static int state=0;   // 1 up, -1 gave up for this session
 std::lock_guard<std::mutex> lk(m);
 if(state<0)return 9021;
 if(omniStarterUp()){if(state!=1){state=1;omni_native_log("children: engine starter answering on 9031 (OMNI_STARTER_V1)");}return 9031;}
 // Start it once through elfldr. It moves its output to /data/omni/native/starter.log, which ends this connection.
 int fd=socket(AF_INET,SOCK_STREAM,0);
 if(fd>=0){
  sockaddr_in a{};a.sin_family=AF_INET;a.sin_port=htons(9021);a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
  char req[96];int n=snprintf(req,sizeof(req),"file:%s\n",kOmniStarter);
  if(!connect(fd,reinterpret_cast<sockaddr*>(&a),sizeof(a))&&write(fd,req,n)==n)shutdown(fd,SHUT_WR);
  close(fd);
 }
 for(int i=0;i<40;++i){usleep(50000);if(omniStarterUp()){state=1;omni_native_log("children: engine starter started (OMNI_STARTER_V1, %d ms)",(i+1)*50);return 9031;}}
 state=-1;omni_native_log("children: engine starter did not come up; elfldr for this session (OMNI_STARTER_V1)");
 return 9021;
}
'''

EDITS = [
    ('static int nativeSpawn(const char* path) {\n', HELPERS + 'static int nativeSpawn(const char* path) {\n'),
    (' int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return -errno;\n'
     ' sockaddr_in address{};address.sin_family=AF_INET;address.sin_port=htons(9021);address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);\n'
     ' if(connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))){int e=errno;close(fd);omni_native_log("children: loader connect failed errno=%d",e);return -e;}\n',
     ' int port=omniEnginePort();   // OMNI_STARTER_V1: 9031 = Omni\'s engine starter, 9021 = elfldr\n'
     ' int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return -errno;\n'
     ' sockaddr_in address{};address.sin_family=AF_INET;address.sin_port=htons(port);address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);\n'
     ' if(port==9031&&connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))){   // starter gone: elfldr for this spawn\n'
     '  omni_native_log("children: engine starter refused (errno=%d); elfldr",errno);close(fd);fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return -errno;\n'
     '  port=9021;address.sin_port=htons(port);\n'
     '  if(connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))){int e=errno;close(fd);omni_native_log("children: loader connect failed errno=%d",e);return -e;}\n'
     ' } else if(port==9021&&connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))){int e=errno;close(fd);omni_native_log("children: loader connect failed errno=%d",e);return -e;}\n'),
    (' omni_native_log("children: spawn %s -> %d",path,e?-e:0);\n',
     ' omni_native_log("children: spawn %s -> %d via %s",path,e?-e:0,port==9031?"omni-starter":"elfldr");\n'),
]
for old, new in EDITS:
    if t.count(old) != 1:
        sys.exit('NativeLauncherState.cpp: anchor found %d times: %r' % (t.count(old), old[:70]))
    t = t.replace(old, new, 1)
if crlf:
    t = t.replace('\n', '\r\n')
p.write_bytes(t.encode('utf-8'))
print('applied ' + MARK)
