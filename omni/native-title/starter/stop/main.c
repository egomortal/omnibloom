/* omni-starter-stop (OMNI_STARTER_V2 upgrade helper). SPDX-License-Identifier: GPL-3.0-or-later
Ends the old omni-starter.elf (V1 has no "quit" request). Its zombie children are then reaped by init.
The process list's layout on the console doesn't match the SDK's kinfo_proc, so the pid comes from
/data/omni/native/starter-stop.pid (written over FTP from the console's own process list), and the process is
ended only if it is listening on the starter's port 9031 (checked by connecting to 127.0.0.1:9031 before and
after). Loaded once through elfldr; logs to /data/omni/native/starter.log and exits. */
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static int port_open(void)
{
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) return 0;
    struct sockaddr_in sa;
    memset(&sa, 0, sizeof sa);
    sa.sin_family = AF_INET; sa.sin_port = htons(9031); sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    int ok = !connect(s, (struct sockaddr*)&sa, sizeof sa);
    close(s);
    return ok;
}

int main(void)
{
    int lf = open("/data/omni/native/starter.log", O_WRONLY | O_CREAT | O_APPEND, 0666);
    if (lf >= 0) { dup2(lf, 1); dup2(lf, 2); close(lf); }
    setvbuf(stdout, 0, _IONBF, 0);
    FILE* f = fopen("/data/omni/native/starter-stop.pid", "r");
    int pid = 0;
    if (!f || fscanf(f, "%d", &pid) != 1 || pid <= 1) { printf("omni-starter-stop: no pid file\n"); return 1; }
    fclose(f);
    unlink("/data/omni/native/starter-stop.pid");
    if (!port_open()) { printf("omni-starter-stop: nothing on 9031; nothing to do\n"); return 0; }
    int r = kill(pid, SIGKILL);
    usleep(300000);
    printf("omni-starter-stop: kill %d -> %d; 9031 now %s\n", pid, r ? errno : 0, port_open() ? "STILL OPEN" : "free");
    return 0;
}
