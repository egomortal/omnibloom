/* Omni Engine - hardware probe v3.
 *   A storage | B SCM_RIGHTS in-process | C Unix socket files (sandboxed)
 *   C2 Unix socket files after raising privileges
 *   D elfldr "file:" spawn starts a 2nd process
 *   G remote_dup handover (child pulls its socket from the parent, talks back)
 *   F largest PROT_NONE reservation
 * Results: notification + /data/omni/probe.txt (+ child.txt).
 * SPDX-License-Identifier: GPL-3.0-or-later */
#include "probe_child.h"
#include "probe_tests.h"

#include <stdarg.h>
#include <sys/mman.h>
#include <sys/time.h>

static FILE *logf;
static int passed, total;
static char failed[256];

static void logline(const char *fmt, ...) {
  if (!logf) return;
  va_list ap;
  va_start(ap, fmt);
  vfprintf(logf, fmt, ap);
  va_end(ap);
  fputc('\n', logf);
  fflush(logf);
}

static void result(const char *name, bool ok, const char *fmt, ...) {
  char d[500] = "";
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(d, sizeof(d), fmt, ap);
  va_end(ap);
  total++;
  if (ok) passed++;
  else snprintf(failed + strlen(failed), sizeof(failed) - strlen(failed), " %s", name);
  logline("%s  %-18s %s", ok ? "PASS" : "FAIL", name, d);
}

static double now_ms(void) {
  struct timeval tv;
  gettimeofday(&tv, NULL);
  return tv.tv_sec * 1e3 + tv.tv_usec / 1e3;
}

static void slurp_child(char *out, size_t cap) {
  out[0] = 0;
  FILE *cf = fopen(CHILD_TXT, "r");
  if (!cf) { snprintf(out, cap, "(no child.txt)"); return; }
  size_t n = fread(out, 1, cap - 1, cf);
  out[n] = 0;
  for (char *p = out; *p; p++) if (*p == '\n') *p = ';';
  fclose(cf);
}

/* spawn ourselves; wait up to ms for child.txt. 0 ok, else -errno or 1 timeout */
static int spawn_and_wait(const char *self, double ms) {
  struct stat st;
  int sp = spawn_self(self);
  if (sp) return sp;
  double t0 = now_ms();
  while (now_ms() - t0 < ms && stat(CHILD_TXT, &st)) usleep(100000);
  return stat(CHILD_TXT, &st) ? 1 : 0;
}

int main(int, char **) {
  char mode[16], d[600];
  int ppid = 0, pfd = -1;
  mkdir(OUTDIR, 0777);
  mkdir(RUNDIR, 0777);
  if (take_ticket(mode, &ppid, &pfd)) return child_run(mode, ppid, pfd);

  logf = fopen(OUTDIR "/probe.txt", "w");
  notify("Omni probe v3: running...");
  logline("Omni probe v3");

  result("A storage", logf != NULL, "%s", OUTDIR);
  bool b = scm_local(d, sizeof(d));
  result("B SCM_RIGHTS", b, "%s", d);
  int c1 = unix_sock_scan(d, sizeof(d));
  result("C unix sock", c1 > 0, "%s", d);
  int pr = raise_privileges();
  int c2 = unix_sock_scan(d, sizeof(d));
  result("C2 unix sock+priv", c2 > 0, "raise=%d %s", pr, d);

  const char *self = NULL;
  struct stat st;
  for (int i = 0; SELF_CANDIDATES[i]; i++)
    if (!stat(SELF_CANDIDATES[i], &st)) { self = SELF_CANDIDATES[i]; break; }

  bool spawned = false;
  if (!self) {
    result("D spawn", false, "no saved omni-probe.elf in /data/omni or /data/homebrew");
  } else {
    unlink(CHILD_TXT);
    write_ticket("start", 0, -1);
    double t0 = now_ms();
    int r = spawn_and_wait(self, 15000);
    spawned = r == 0;
    unlink(TICKET);
    result("D spawn", spawned, "%s: %s (%.0f ms)", self,
           r < 0 ? strerror(-r) : r ? "no child after 15 s" : "child started", now_ms() - t0);
  }

  if (spawned) {
    int sp[2];
    socketpair(AF_UNIX, SOCK_SEQPACKET, 0, sp);
    unlink(CHILD_TXT);
    write_ticket("rdup", (int)getpid(), sp[1]);
    double t0 = now_ms();
    spawn_self(self);
    struct timeval tv = {15, 0};
    setsockopt(sp[0], SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    char buf[120] = {0};
    bool got = read(sp[0], buf, sizeof(buf) - 1) > 0 && strstr(buf, "hello from child");
    if (got && write(sp[0], "ack", 3) != 3) got = false;
    usleep(500000);
    char ct[400];
    slurp_child(ct, sizeof(ct));
    result("G rdup handover", got, "%.0f ms, got '%s' | child: %s", now_ms() - t0,
           got ? buf : "-", ct);
    unlink(TICKET);
    close(sp[0]);
    close(sp[1]);
  } else {
    result("G rdup handover", false, "skipped: needs D");
  }

  size_t best = 0;
  const size_t sizes[] = {(size_t)64 << 30, (size_t)16 << 30, (size_t)4 << 30,
                          (size_t)1 << 30, (size_t)256 << 20};
  for (size_t s : sizes) {
    void *p = mmap(NULL, s, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (p == MAP_FAILED) continue;
    bool ok = !mprotect(p, 1 << 20, PROT_READ | PROT_WRITE);
    if (ok) memset(p, 0xab, 1 << 20);
    munmap(p, s);
    if (ok) { best = s; break; }
  }
  result("F max reserve", best >= ((size_t)1 << 30), "%zu MiB", best >> 20);

  char summary[400];
  snprintf(summary, sizeof(summary), "Omni probe v3: %d/%d passed%s%s", passed, total,
           failed[0] ? " | FAILED:" : "", failed);
  logline("%s", summary);
  if (logf) fclose(logf);
  notify(summary);
  return passed == total ? 0 : 1;
}
