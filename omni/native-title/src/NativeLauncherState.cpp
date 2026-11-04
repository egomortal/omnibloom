// omni-native-s0: UI-side launcher state for the native title (from the 2026-10-20
// omni-browser/tools/native-title/NativeLauncherState.cpp, OMNI_NATIVE_LAUNCHER_V1).
// Differences: omni_child_bootstrap() answers OMNI_ROLE_FIRST (the title is always the UI process),
// so Omni's unchanged main() takes its UI path; children stay the /data/omni/omni-engine.elf payload.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "launcher-common.h"
extern "C" void omni_native_log(const char*, ...);
namespace { std::string directory; }
std::string& omni_launcher_dir_ref() { return directory; }
extern "C" void omni_launcher_set_dir(const char* value) { directory = value ? value : ""; }
extern "C" void omni_launcher_set_socket_path(const char*) { }
extern "C" int omni_launcher_listen() { omni_launcher_dir_ensure(); return 0; }
namespace PlayStation { int getConnectionIdentifier() { return -1; } }
extern "C" int omni_child_bootstrap(char**, int, int* count) { if (count) *count = 0; omni_launcher_dir_ensure(); return OMNI_ROLE_FIRST; }
#include "NativeDiagnostics.cpp" // OMNI_NATIVE_DIAG_V1
#include "NativeShm.cpp" // OMNI_NATIVE_SHM_V1
#include "NativePosix.cpp"
// Native startup owns a single loader socket and transfers it to the drain
// thread after writing the request. No descriptor duplication is required.
#include <atomic>
#include <new>
#include <pthread.h>
#include <arpa/inet.h>
#include <string.h>
#include <dirent.h>
#include <time.h>
struct NativeDrain { int fd; std::atomic<bool> ready{false}; };
static void* nativeDrain(void* value) {
 auto* state=static_cast<NativeDrain*>(value);
 while(!state->ready.load(std::memory_order_acquire)) usleep(1000);
 int fd=state->fd;delete state;char buffer[1024];
 for(;;){ssize_t n=read(fd,buffer,sizeof(buffer));if(n<0&&errno==EINTR)continue;if(n<=0)break;fwrite(buffer,1,n,stderr);fflush(stderr);}
 close(fd);return nullptr;
}
// s0b: set once the title starts leaving; no child is started after that.
static std::atomic<bool> g_childrenStopped{false};
// s0c: the title's children run the native child engine copy (OMNI_NATIVE_CHILD_V1: never a UI
// process, leaves when the title is gone or closing) when it is installed; the big-app keeps
// /data/omni/omni-engine.elf.
static const char* nativeChildPath(const char* path) {
 static const char kChild[]="/data/omni/native/omni-engine-child.elf";
 static std::atomic<int> logged{0};
 bool use=path&&!strcmp(path,"/data/omni/omni-engine.elf")&&access(kChild,F_OK)==0;
 if(!logged.exchange(1))omni_native_log("children: engine %s",use?kChild:(path?path:"(null)"));
 return use?kChild:path;
}
static int nativeSpawn(const char* path) {
 path=nativeChildPath(path);
 if(g_childrenStopped.load(std::memory_order_acquire)){omni_native_log("children: spawn %s refused: title is leaving",path);return -ECANCELED;}
 char request[512];int count=snprintf(request,sizeof(request),"file:%s\n",path);
 if(count<0||count>=static_cast<int>(sizeof(request)))return -ENAMETOOLONG;
 int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return -errno;
 sockaddr_in address{};address.sin_family=AF_INET;address.sin_port=htons(9021);address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
 if(connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))){int e=errno;close(fd);omni_native_log("children: loader connect failed errno=%d",e);return -e;}
 auto* state=new(std::nothrow) NativeDrain;if(!state){close(fd);return -ENOMEM;}state->fd=fd;
 pthread_attr_t attr;int e=pthread_attr_init(&attr);if(e){delete state;close(fd);return -e;}
 e=pthread_attr_setstacksize(&attr,128*1024);if(!e)e=pthread_attr_setdetachstate(&attr,PTHREAD_CREATE_DETACHED);
 pthread_t thread;if(!e)e=pthread_create(&thread,&attr,nativeDrain,state);pthread_attr_destroy(&attr);
 if(e){delete state;close(fd);return -e;}
 int sent=0;while(sent<count){ssize_t n=write(fd,request+sent,count-sent);if(n<0&&errno==EINTR)continue;if(n<=0){e=n<0?errno:EIO;break;}sent+=static_cast<int>(n);}
 shutdown(fd,e?SHUT_RDWR:SHUT_WR);state->ready.store(true,std::memory_order_release);
 omni_native_log("children: spawn %s -> %d",path,e?-e:0);
 return e?-e:0;
}
__attribute__((constructor)) static void installNativeSpawner(){omni_launcher_set_spawner(nativeSpawn);}

// s0b: called on every route out of the title before LoadExec. 1) refuse further spawns (the
// launcher's refill goes through nativeSpawn). 2) wait (bounded) until every ticket this process
// wrote is consumed: "spare-<pid>-<seq>.t" disappears when its child has loaded (it then waits as a
// spare and _exit()s within 0.5 s of this title's end); "req-<pid>-<seq>.t" when a child took the
// request. A child still loading when the title has gone would find its parent dead, delete its
// spare ticket and start as a UI process (a second browser), which is what s0's run c left behind.
static int ownTickets(int pid)
{
 const std::string& dir=omni_launcher_dir();DIR* d=opendir(dir.c_str());if(!d)return 0;
 char spare[32],req[32];snprintf(spare,sizeof(spare),"spare-%d-",pid);snprintf(req,sizeof(req),"req-%d-",pid);
 int n=0;while(struct dirent* e=readdir(d)){if((!strncmp(e->d_name,spare,strlen(spare))||!strncmp(e->d_name,req,strlen(req)))&&strstr(e->d_name,".t"))n++;}
 closedir(d);return n;
}
extern "C" void omni_native_children_stop(int maxMs)
{
 if(g_childrenStopped.exchange(true,std::memory_order_acq_rel))return;
 timespec t0,t;clock_gettime(CLOCK_MONOTONIC,&t0);
 int pid=static_cast<int>(getpid()),n=ownTickets(pid),first=n;
 omni_native_log("exit: children: refill stopped; %d of this title's tickets still pending",n);
 double ms=0;
 while(n>0){usleep(50000);clock_gettime(CLOCK_MONOTONIC,&t);ms=(t.tv_sec-t0.tv_sec)*1e3+(t.tv_nsec-t0.tv_nsec)/1e6;n=ownTickets(pid);if(ms>=maxMs)break;}
 if(first)omni_native_log("exit: children: %d pending after %.0f ms%s",n,ms,n?" (giving up; those children may start on their own)":" (all loaded; spares end with the title)");
}
