/* Omni probe: in-process socket tests.
 * SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "probe_platform.h"
#include <sys/stat.h>
#include <sys/un.h>

/* fd passing over a socketpair inside one process */
static bool scm_local(char *d, size_t cap) {
  int sp[2], pp[2];
  if (socketpair(AF_UNIX, SOCK_STREAM, 0, sp) || pipe(pp)) {
    snprintf(d, cap, "socketpair/pipe errno %d", errno);
    return false;
  }
  char b = 'x', ctl[CMSG_SPACE(sizeof(int))] = {0};
  struct iovec iov = {&b, 1};
  struct msghdr m;
  memset(&m, 0, sizeof(m));
  m.msg_iov = &iov;
  m.msg_iovlen = 1;
  m.msg_control = ctl;
  m.msg_controllen = sizeof(ctl);
  struct cmsghdr *c = CMSG_FIRSTHDR(&m);
  c->cmsg_level = SOL_SOCKET;
  c->cmsg_type = SCM_RIGHTS;
  c->cmsg_len = CMSG_LEN(sizeof(int));
  memcpy(CMSG_DATA(c), &pp[1], sizeof(int));
  bool ok = sendmsg(sp[0], &m, 0) == 1;
  char ctl2[CMSG_SPACE(sizeof(int))] = {0};
  m.msg_control = ctl2;
  m.msg_controllen = sizeof(ctl2);
  ok = ok && recvmsg(sp[1], &m, 0) == 1;
  int got = -1;
  for (c = CMSG_FIRSTHDR(&m); ok && c; c = CMSG_NXTHDR(&m, c))
    if (c->cmsg_type == SCM_RIGHTS) memcpy(&got, CMSG_DATA(c), sizeof(int));
  char r[3] = {0};
  ok = ok && got >= 0 && write(got, "ok", 2) == 2 && read(pp[0], r, 2) == 2;
  snprintf(d, cap, "fd %d -> %d", pp[1], got);
  return ok;
}

/* bind+listen+connect a Unix socket file in dir. 0 or errno */
static int unix_sock_test(const char *dir) {
  char path[200];
  mkdir(dir, 0777);
  snprintf(path, sizeof(path), "%s/omni-test.sock", dir);
  unlink(path);
  int s = socket(AF_UNIX, SOCK_STREAM, 0), e = 0;
  struct sockaddr_un sa;
  memset(&sa, 0, sizeof(sa));
  sa.sun_family = AF_UNIX;
  if (strlen(path) >= sizeof(sa.sun_path)) {
    if (s >= 0) close(s);
    return ENAMETOOLONG;
  }
  memcpy(sa.sun_path, path, strlen(path) + 1);
  if (s < 0 || bind(s, (struct sockaddr *)&sa, sizeof(sa)) || listen(s, 1)) e = errno ? errno : -1;
  int c = e ? -1 : socket(AF_UNIX, SOCK_STREAM, 0);
  if (!e && connect(c, (struct sockaddr *)&sa, sizeof(sa))) e = errno;
  if (c >= 0) close(c);
  if (s >= 0) close(s);
  unlink(path);
  return e;
}

/* run unix_sock_test over all candidate dirs; returns number that worked */
static int unix_sock_scan(char *d, size_t cap) {
  int ok = 0;
  d[0] = 0;
  for (int i = 0; SOCK_DIRS[i]; i++) {
    int e = unix_sock_test(SOCK_DIRS[i]);
    if (!e) ok++;
    snprintf(d + strlen(d), cap - strlen(d), "%s:%s ", SOCK_DIRS[i], e ? strerror(e) : "ok");
  }
  return ok;
}
