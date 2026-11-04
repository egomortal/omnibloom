/* Private SDK0.42 POSIX at-function adapters. SPDX-License-Identifier: MIT
 * FreeBSD/PS5 syscall failure is carry-set with a positive errno in RAX.
 * The pinned SDK stubs return raw RAX and do not publish errno. Keep that
 * hardware failure signal intact; never infer failure from result's sign.
 */
#include <cerrno>
#include <cstdarg>
#include <cstdint>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>

struct KernelResult { long value; unsigned char failed; };
#if defined(OMNI_FS_HOST_TEST)
extern "C" KernelResult omni_fs_test_syscall(long,long,long,long,long);
#endif

static KernelResult kernel_at(long number,long a0,long a1,long a2,long a3) {
#if defined(OMNI_FS_HOST_TEST)
 return omni_fs_test_syscall(number,a0,a1,a2,a3);
#else
 KernelResult result{};
 register long r10 __asm__("r10")=a3;
 __asm__ volatile("syscall\n\tsetc %1"
  : "=a"(result.value),"=qm"(result.failed)
  : "0"(number),"D"(a0),"S"(a1),"d"(a2),"r"(r10)
  : "rcx","r11","memory","cc");
 return result;
#endif
}

static int posix_result(KernelResult result) {
 if(result.failed) {errno=static_cast<int>(result.value);return -1;}
 return static_cast<int>(result.value);
}

extern "C" int __wrap_fstatat(int directory,const char* path,struct stat* output,int flags) {
 return posix_result(kernel_at(493,directory,reinterpret_cast<long>(path),reinterpret_cast<long>(output),flags));
}
extern "C" int __wrap_mkdirat(int directory,const char* path,mode_t mode) {
 return posix_result(kernel_at(496,directory,reinterpret_cast<long>(path),mode,0));
}
extern "C" int __wrap_openat(int directory,const char* path,int flags,...) {
 mode_t mode=0;
 if(flags&O_CREAT) {
  va_list args;va_start(args,flags);mode=static_cast<mode_t>(va_arg(args,int));va_end(args);
 }
 return posix_result(kernel_at(499,directory,reinterpret_cast<long>(path),flags,mode));
}
