/* Omni probe: ticket file + spawned-child side.
 * SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "probe_platform.h"
#include "probe_priv.h"
#include <stdlib.h>
#include <time.h>

#define RUNDIR OUTDIR "/run"
#define TICKET RUNDIR "/ticket"
#define CHILD_TXT OUTDIR "/child.txt"

/* ticket: "<unix time> <mode> <parent pid> <fd>", valid 60 s, consumed on read */
static void write_ticket(const char *mode, int ppid, int fd) {
  FILE *f = fopen(TICKET, "w");
  if (f) {
    fprintf(f, "%ld %s %d %d\n", (long)time(NULL), mode, ppid, fd);
    fclose(f);
  }
}

static bool take_ticket(char *mode, int *ppid, int *fd) {
  FILE *f = fopen(TICKET, "r");
  if (!f) return false;
  long t = 0;
  int n = fscanf(f, "%ld %15s %d %d", &t, mode, ppid, fd);
  fclose(f);
  unlink(TICKET);
  long age = (long)time(NULL) - t;
  return n == 4 && age >= 0 && age <= 60;
}

/* mode "start": just prove we run. mode "rdup": pull the parent's socket. */
static int child_run(const char *mode, int ppid, int pfd) {
  FILE *f = fopen(CHILD_TXT, "w");
  if (f) {
    fprintf(f, "started pid %d mode %s\n", (int)getpid(), mode);
    fflush(f);
  }
  if (!strcmp(mode, "rdup")) {
    int fd = remote_dup(ppid, pfd);
    int e1 = errno, priv = 0;
    if (fd < 0) {
      priv = raise_privileges();
      fd = remote_dup(ppid, pfd);
    }
    if (f)
      fprintf(f, "rdup errno %d (%s); raise %d; fd %d errno %d\n", e1, strerror(e1), priv, fd,
              fd < 0 ? errno : 0);
    if (fd >= 0) {
      char msg[80];
      int n = snprintf(msg, sizeof(msg), "hello from child pid %d", (int)getpid());
      bool w = write(fd, msg, (size_t)n) == n;
      char ack[8] = {0};
      bool r = read(fd, ack, sizeof(ack) - 1) > 0;
      if (f) fprintf(f, "ipc write %d read %d\n", w, r);
    }
  }
  if (f) fclose(f);
  return 0;
}
