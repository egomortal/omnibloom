/* Omni probe v2: platform glue (PS5 vs host test build).
 * SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#ifdef __PROSPERO__
#define OUTDIR "/data/omni"
static const char *const SELF_CANDIDATES[] = {
    "/data/omni/omni-probe.elf", "/data/homebrew/omni-probe.elf", NULL};
static const char *const SOCK_DIRS[] = {"/data/omni/run", "/tmp", "/user/temp", "/data", NULL};
typedef struct {
  char useless1[45];
  char message[3075];
} notify_request_t;
extern "C" int sceKernelSendNotificationRequest(int, notify_request_t *, size_t, int);
static void notify(const char *msg) {
  notify_request_t req;
  memset(&req, 0, sizeof(req));
  snprintf(req.message, sizeof(req.message), "%s", msg);
  sceKernelSendNotificationRequest(0, &req, sizeof(req), 0);
}
/* ask elfldr (127.0.0.1:9021) to start a saved ELF; 0 or -errno */
static int spawn_self(const char *path) {
  int s = socket(AF_INET, SOCK_STREAM, 0);
  if (s < 0) return -errno;
  struct sockaddr_in sa;
  memset(&sa, 0, sizeof(sa));
  sa.sin_family = AF_INET;
  sa.sin_port = htons(9021);
  sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (connect(s, (struct sockaddr *)&sa, sizeof(sa))) {
    int e = errno;
    close(s);
    return -e;
  }
  char line[300];
  int n = snprintf(line, sizeof(line), "file:%s\n", path);
  int ok = write(s, line, (size_t)n) == n;
  close(s);
  return ok ? 0 : -EIO;
}
#else
#include <sys/wait.h>
#define OUTDIR "/tmp/omni-probe-out"
static const char *const SELF_CANDIDATES[] = {"/proc/self/exe", NULL};
static const char *const SOCK_DIRS[] = {"/tmp/omni-probe-out/run", "/tmp", NULL};
static void notify(const char *msg) { fprintf(stderr, "[notify] %s\n", msg); }
static int spawn_self(const char *path) {
  pid_t p = fork();
  if (p < 0) return -errno;
  if (!p) {
    execl(path, path, (char *)NULL);
    _exit(127);
  }
  return 0;
}
#endif
