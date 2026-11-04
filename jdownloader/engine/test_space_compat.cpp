#include <cerrno>
#include <cassert>
#include <cstdio>
struct statfs;struct SpaceKernelResult{long value;unsigned char failed;};static long expected,seen;static SpaceKernelResult next;
extern "C" SpaceKernelResult omni_space_test_syscall(long n,long,long,long){seen=n;assert(n==expected);return next;}
extern "C" int __wrap_statfs(const char*,struct statfs*);extern "C" int __wrap_fstatfs(int,struct statfs*);extern "C" int __wrap_getfsstat(struct statfs*,long,int);
int main(){expected=396;next={0,0};assert(__wrap_statfs("/data",nullptr)==0&&seen==396);next={2,1};errno=0;assert(__wrap_statfs("missing",nullptr)==-1&&errno==2);expected=397;next={9,1};errno=0;assert(__wrap_fstatfs(-1,nullptr)==-1&&errno==9);next={0,0};assert(__wrap_fstatfs(3,nullptr)==0);expected=395;next={1061,0};errno=0;assert(__wrap_getfsstat(nullptr,0,2)==1061&&errno==0);next={78,1};assert(__wrap_getfsstat(nullptr,0,2)==-1&&errno==78);std::puts("{\"status\":\"SPACE_CARRY_ERRNO_TESTS_PASS\",\"cases\":6}");}
