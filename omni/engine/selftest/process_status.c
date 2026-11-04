// Read-only process diagnostics for Omni; no process state is changed.
#include <sys/types.h>
#include <sys/proc.h>
#include <sys/user.h>
#include <sys/sysctl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
int main(void) {
    FILE* out = fopen("/data/omni/process-status.txt", "w");
    if (!out) return 1;
    int mib[] = { CTL_KERN, KERN_PROC, KERN_PROC_PROC, 0 };
    size_t size = 0;
    if (sysctl(mib, 4, NULL, &size, NULL, 0)) return 2;
    char* buffer = malloc(size);
    if (!buffer || sysctl(mib, 4, buffer, &size, NULL, 0)) return 3;
    fprintf(out, "PID PPID state threads resident-pages command\n");
    for (char* p = buffer; p < buffer + size;) {
        struct kinfo_proc* process = (struct kinfo_proc*)p;
        if (!process->ki_structsize) break;
        p += process->ki_structsize;
        if (strstr(process->ki_comm, "omni") || strstr(process->ki_comm, "websrv")) {
            fprintf(out, "%d %d %d %d %ld %s\n", process->ki_pid, process->ki_ppid, process->ki_stat,
                process->ki_numthreads, (long)process->ki_rssize, process->ki_comm);
            fprintf(out, "  xstat=%u flags=%lx flags2=%x tdflags=%lx pending=", process->ki_xstat, process->ki_flag, process->ki_flag2, process->ki_tdflags);
            for (int sig = 1; sig < NSIG; ++sig) if (sigismember(&process->ki_siglist, sig) == 1) fprintf(out, "%d,", sig);
            fputc('\n', out);
        }
    }
    free(buffer); fclose(out); return 0;
}
