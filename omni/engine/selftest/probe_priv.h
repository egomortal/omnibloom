/* Omni probe: privilege + cross-process fd helpers.
 * SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <errno.h>
#include <stdint.h>
#include <unistd.h>

#ifdef __PROSPERO__
#include <ps5/kernel.h>

/* Escape the sandbox jail, uid 0, all capabilities (what elfldr does for its
 * own children before it touches them). 0 on success. */
static int raise_privileges(void) {
  static const uint8_t caps[16] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
                                   0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
  pid_t me = getpid();
  intptr_t root = kernel_get_root_vnode();
  if (!root) return -1;
  if (kernel_set_proc_rootdir(me, root)) return -2;
  if (kernel_set_proc_jaildir(me, 0)) return -3;
  if (kernel_set_ucred_uid(me, 0)) return -4;
  if (kernel_set_ucred_caps(me, caps)) return -5;
  return 0;
}

/* Sony syscall 0x25b (used by elfldr's pt_rdup): duplicate descriptor `fd` of
 * process `pid` into the calling process. Returns the new fd or -1/errno. */
static int remote_dup(pid_t pid, int fd) { return syscall(0x25b, pid, fd); }

#else /* host build: emulate with pidfd_getfd (Linux >= 5.6) */
#include <sys/syscall.h>
static int raise_privileges(void) { return 0; }
static int remote_dup(pid_t pid, int fd) {
#if defined(SYS_pidfd_open) && defined(SYS_pidfd_getfd)
  int pfd = (int)syscall(SYS_pidfd_open, pid, 0);
  if (pfd < 0) return -1;
  int r = (int)syscall(SYS_pidfd_getfd, pfd, fd, 0);
  close(pfd);
  return r;
#else
  (void)pid; (void)fd;
  errno = ENOSYS;
  return -1;
#endif
}
#endif
