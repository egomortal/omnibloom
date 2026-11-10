// omni-native-s0 native-title adapters (from omni-browser/tools/native-title/NativePosix.cpp).
// Unsupported operations fail explicitly so callers take their normal fallback; never a raw
// syscall instruction. readlink/link/symlink are bound by the RADV link recipe to the SDK
// platform's ps5_ versions when it has them; otherwise build.py binds them to the
// omni_enosys_ functions here (--defsym). All names here are kept local (native-local.map).
#include <errno.h>
#include <stdarg.h>
#include <sys/types.h>
#include <sys/mount.h>
#include <unistd.h>
extern "C" int __sys_rdup(pid_t, int);
extern "C" int syscall(int number, ...) {
    if (number != 0x25b) { errno = ENOSYS; return -1; }
    va_list args; va_start(args, number);
    pid_t pid = va_arg(args, int); int fd = va_arg(args, int);
    va_end(args); return __sys_rdup(pid, fd);
}
extern "C" ssize_t omni_enosys_readlink(const char*, char*, size_t) { errno = ENOSYS; return -1; }
extern "C" int omni_enosys_link(const char*, const char*) { errno = ENOSYS; return -1; }
extern "C" int omni_enosys_symlink(const char*, const char*) { errno = ENOSYS; return -1; }
extern "C" int omni_enosys_fchown(int, uid_t, gid_t) { errno = ENOSYS; return -1; }
#include <sys/socket.h>
#include <stdio.h>
#include <fcntl.h>
extern "C" int __real_connect(int, const struct sockaddr*, socklen_t);
extern "C" int __wrap_connect(int fd, const struct sockaddr* address, socklen_t length) {
 int rc=__real_connect(fd,address,length);int saved=errno;
 fprintf(stderr,"native connect fd=%d family=%d result=%d errno=%d\n",fd,address?address->sa_family:-1,rc,saved);errno=saved;return rc;
}
// OMNI_NATIVE_SHM_V1: the platform dup first; for WebKit's shared memory (anonymous shm, whose
// dup the title refuses) open the same named object again (NativeShm.cpp).
extern "C" int __wrap_dup(int fd) {
 omniNativeDiagDup(fd); // OMNI_NATIVE_DIAG_V1
 omniShmProbeDup();
 int rc=__real_dup(fd);int saved=errno;const char* how="dup";
 if(rc<0){int copy=omniShmReopen(fd);if(copy>=0){rc=copy;saved=0;how="shm reopen";}else if(copy==-1){saved=errno;how="shm reopen";}}
 fprintf(stderr,"native dup fd=%d result=%d via %s errno=%d\n",fd,rc,how,saved);fflush(stderr);errno=saved;return rc;
}
