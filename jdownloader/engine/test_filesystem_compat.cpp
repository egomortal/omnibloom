/* Controlled kernel-result harness. It performs no filesystem syscalls. */
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
struct KernelResult {long value;unsigned char failed;};
extern "C" int __wrap_fstatat(int,const char*,struct stat*,int);
extern "C" int __wrap_mkdirat(int,const char*,mode_t);
extern "C" int __wrap_openat(int,const char*,int,...);
static KernelResult injected{};
static long observed[5]{};
extern "C" KernelResult omni_fs_test_syscall(long n,long a,long b,long c,long d) {
 observed[0]=n;observed[1]=a;observed[2]=b;observed[3]=c;observed[4]=d;return injected;
}
int main() {
 struct stat output{};const char* path="owned-path";unsigned assertions=0;
 injected={0,0};errno=77;
 assert(__wrap_fstatat(-100,path,&output,256)==0);assert(errno==77);
 assert(observed[0]==493&&observed[1]==-100&&observed[2]==reinterpret_cast<long>(path)&&observed[3]==reinterpret_cast<long>(&output)&&observed[4]==256);assertions+=3;
 injected={ENOENT,1};assert(__wrap_fstatat(8,path,&output,0)==-1);assert(errno==ENOENT);assertions+=2;
 injected={0,0};errno=88;assert(__wrap_mkdirat(9,path,0700)==0);assert(errno==88);assert(observed[0]==496&&observed[1]==9&&observed[3]==0700&&observed[4]==0);assertions+=3;
 injected={EEXIST,1};assert(__wrap_mkdirat(9,path,0700)==-1);assert(errno==EEXIST);assertions+=2;
 injected={42,0};errno=99;assert(__wrap_openat(10,path,O_RDONLY)==42);assert(errno==99);assert(observed[0]==499&&observed[1]==10&&observed[3]==O_RDONLY&&observed[4]==0);assertions+=3;
 injected={7,0};assert(__wrap_openat(11,path,O_WRONLY|O_CREAT|O_EXCL,0600)==7);assert(observed[4]==0600);assertions+=2;
 injected={EPERM,1};assert(__wrap_openat(11,path,O_RDONLY)==-1);assert(errno==EPERM);assertions+=2;
 injected={EEXIST,1};assert(__wrap_openat(11,path,O_WRONLY|O_CREAT|O_EXCL,0600)==-1);assert(errno==EEXIST);assertions+=2;
 // The carry bit, not sign/value, selects error. Values may coincide with errno.
 injected={ENOENT,0};errno=55;assert(__wrap_openat(1,path,O_RDONLY)==ENOENT);assert(errno==55);assertions+=2;
 std::printf("{\"passed\":true,\"assertions\":%u,\"actual_target_syscalls\":false}\n",assertions);
}
