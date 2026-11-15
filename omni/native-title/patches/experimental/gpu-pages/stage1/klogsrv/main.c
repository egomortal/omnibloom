/* OMNI_KLOGSRV_V1 (2026-11-14): read-only kernel log server for Omni console tests.
 *
 * Why: whole-console reboots during Omni tests leave nothing in crash.log; the last kernel messages before the reboot
 * are the only evidence. The console's FTP server returns /dev/klog as an empty file, so this payload streams it.
 *
 * What it does: opens /dev/klog (raising this process's ucred authid/caps only if the plain open is refused), listens
 * on TCP 3232, and copies new kernel log bytes to one connected client at a time. Nothing is written on the console
 * except the status file /data/omni/klogsrv.status. Load it once per boot through the payload loader (port 9021).
 */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include <netinet/in.h>
#include <sys/socket.h>

#include <ps5/kernel.h>

#define KLOG_PORT 3232
#define STATUS "/data/omni/klogsrv.status"

static void status(const char *fmt, ...) {
  FILE *f = fopen(STATUS, "a");
  if (!f) return;
  va_list ap; va_start(ap, fmt); vfprintf(f, fmt, ap); va_end(ap);
  fputc('\n', f); fclose(f);
}

static int open_klog(void) {
  int fd = open("/dev/klog", O_RDONLY);
  if (fd >= 0) { status("open /dev/klog: ok (no privilege change)"); return fd; }
  status("open /dev/klog: %s; raising authid/caps and retrying", strerror(errno));
  uint8_t caps[16]; memset(caps, 0xff, sizeof caps);
  pid_t pid = getpid();
  if (kernel_set_ucred_authid(pid, 0x4800000000010003l) || kernel_set_ucred_caps(pid, caps)) {
    status("raising privileges failed"); return -1;
  }
  fd = open("/dev/klog", O_RDONLY);
  status("open /dev/klog after raise: %s", fd >= 0 ? "ok" : strerror(errno));
  return fd;
}

int main(void) {
  signal(SIGPIPE, SIG_IGN);
  status("OMNI_KLOGSRV_V1 start pid=%d", getpid());
  int kfd = open_klog();
  if (kfd < 0) return 1;

  int srv = socket(AF_INET, SOCK_STREAM, 0);
  int one = 1; setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
  struct sockaddr_in a; memset(&a, 0, sizeof a);
  a.sin_family = AF_INET; a.sin_port = htons(KLOG_PORT); a.sin_addr.s_addr = htonl(INADDR_ANY);
  if (srv < 0 || bind(srv, (struct sockaddr *)&a, sizeof a) || listen(srv, 1)) {
    status("listen on %d failed: %s (already running?)", KLOG_PORT, strerror(errno)); return 1;
  }
  status("listening on %d", KLOG_PORT);

  char buf[8192];
  for (;;) {
    int c = accept(srv, NULL, NULL);
    if (c < 0) continue;
    for (;;) {
      ssize_t n = read(kfd, buf, sizeof buf);      /* blocks until the kernel logs something */
      if (n <= 0) { if (n < 0 && errno == EINTR) continue; break; }
      if (write(c, buf, (size_t)n) != n) break;     /* client gone: wait for the next one */
    }
    close(c);
  }
}
