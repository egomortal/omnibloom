/* Exercise the actual pinned header with intercepted file IO; no target IO. */
#include <fcntl.h>
#include <unistd.h>
#include <cstring>
#include <cerrno>
#include <cstdio>
#include <pthread.h>
#include <cstdint>
#include <cassert>
static unsigned opened=0,writes=0,closed=0;
static char captured[8192];static size_t captured_size=0;
static int probe_open(const char*,int,...){++opened;errno=91;return 42;}
static ssize_t probe_write(int fd,const void* bytes,size_t size){assert(fd==42);assert(captured_size+size<sizeof(captured));std::memcpy(captured+captured_size,bytes,size);captured_size+=size;++writes;return static_cast<ssize_t>(size);}
static int probe_close(int fd){assert(fd==42);++closed;errno=92;return 0;}
#define open probe_open
#define write probe_write
#define close probe_close
#include "ps5StartupTrace.hpp"
#undef open
#undef write
#undef close
int main() {
 ps5_vm_set_metadata_interval(1000);assert(*ps5_vm_metadata_interval()==1000);
 for(unsigned i=0;i<10000;++i){errno=37;ps5_vm_trace(i%2?"DONE: ordinary":"ENTER: ordinary");assert(errno==37);}
 assert(opened==10&&closed==10&&writes==20);
 assert(!std::strcmp(ps5_vm_last_stage(),"DONE: ordinary"));
 errno=38;ps5_vm_trace("ENTER: newest-unsampled-stage");assert(errno==38&&opened==10);
 assert(!std::strcmp(ps5_vm_last_stage(),"ENTER: newest-unsampled-stage"));
 ps5_vm_trace("SIGNAL: preserved fault");assert(opened==11);
 assert(!std::strcmp(ps5_vm_last_stage(),"ENTER: newest-unsampled-stage"));
 ps5_vm_trace("CALL: preserved call");assert(opened==12);
 assert(!std::strcmp(ps5_vm_last_stage(),"ENTER: newest-unsampled-stage"));
 ps5_vm_signal_trace_active()=true;ps5_vm_trace("ENTER: fault recovery context");ps5_vm_signal_trace_active()=false;assert(opened==13);
 ps5_vm_trace_hex("SIGNAL: register=",0x12345678);assert(opened==14);
 ps5_vm_trace("NATIVE TERMINATION: retained");assert(opened==15);
 ps5_vm_set_metadata_interval(1);ps5_vm_trace("ENTER: full logging");assert(opened==16);
 ps5_vm_set_metadata_interval(0);ps5_vm_trace("DONE: full logging");assert(opened==17);
 assert(opened==closed&&writes==opened*2);
 captured[captured_size]=0;assert(std::strstr(captured,"SIGNAL: preserved fault")&&std::strstr(captured,"NATIVE TERMINATION: retained")&&std::strstr(captured,"0000000012345678"));
 std::printf("{\"passed\":true,\"routine_events\":10000,\"sample_interval\":1000,\"routine_disk_opens\":10,\"fault_signal_call_termination_preserved\":true,\"last_unsampled_stage_retained\":true,\"errno_preserved\":true,\"host_io_intercepted\":true}\n");
}
