/* Real FreeBSD/PS5 filesystem ABI; carry-set returns positive kernel errno. */
#include <cerrno>
#include <sys/param.h>
#include <sys/mount.h>
struct SpaceKernelResult{long value;unsigned char failed;};
#if defined(OMNI_SPACE_HOST_TEST)
extern "C" SpaceKernelResult omni_space_test_syscall(long,long,long,long);
#endif
static SpaceKernelResult space_call(long number,long first,long second,long third=0){
#if defined(OMNI_SPACE_HOST_TEST)
 return omni_space_test_syscall(number,first,second,third);
#else
 SpaceKernelResult result{};__asm__ volatile("syscall\n\tsetc %1":"=a"(result.value),"=qm"(result.failed):"0"(number),"D"(first),"S"(second),"d"(third):"rcx","r11","memory","cc");return result;
#endif
}
static int space_result(SpaceKernelResult result){if(result.failed){errno=static_cast<int>(result.value);return -1;}return static_cast<int>(result.value);}
extern "C" int __wrap_statfs(const char* path,struct statfs* output){return space_result(space_call(396,reinterpret_cast<long>(path),reinterpret_cast<long>(output)));}
extern "C" int __wrap_fstatfs(int fd,struct statfs* output){return space_result(space_call(397,fd,reinterpret_cast<long>(output)));}
extern "C" int __wrap_getfsstat(struct statfs* output,long bytes,int flags){return space_result(space_call(395,reinterpret_cast<long>(output),bytes,flags));}
