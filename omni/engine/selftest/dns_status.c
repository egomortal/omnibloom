// Read-only hostname resolution diagnostics; does not change console networking.
#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <poll.h>
#include <unistd.h>
#include <errno.h>
int main(void) {
    FILE* out = fopen("/data/omni/dns-status.txt", "w");
    if (!out) return 1;
    const char* names[] = {"www.google.com", "www.gstatic.com", "www.recaptcha.net", "www.youtube.com", "youtube.com", "m.youtube.com", "i.ytimg.com", "www.youtube-nocookie.com"};
    for (unsigned i=0; i<sizeof(names)/sizeof(names[0]); ++i) {
        struct addrinfo hints = {0}, *result = NULL;
        hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM;
        int code = getaddrinfo(names[i], "443", &hints, &result);
        fprintf(out, "%s status=%d\n", names[i], code);
        if (code) continue;
        for (struct addrinfo* p=result; p; p=p->ai_next) {
            char host[NI_MAXHOST] = {0};
            int status = getnameinfo(p->ai_addr, p->ai_addrlen, host, sizeof(host), NULL, 0, NI_NUMERICHOST);
            fprintf(out, "  family=%d address=%s status=%d\n", p->ai_family, host, status);
            // Bounded TCP handshake only: no HTTP, TLS bypass, or DNS changes.
            int fd = socket(p->ai_family, SOCK_STREAM, 0);
            if (fd < 0) { fprintf(out, "  socket errno=%d\n", errno); continue; }
            int flags = fcntl(fd, F_GETFL, 0);
            if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
                fprintf(out, "  nonblocking errno=%d\n", errno); close(fd); continue;
            }
            int connected = connect(fd, p->ai_addr, p->ai_addrlen);
            int error = connected ? errno : 0;
            if (connected && error == EINPROGRESS) {
                struct pollfd waiting = { fd, POLLOUT, 0 };
                int ready = poll(&waiting, 1, 3000);
                socklen_t length = sizeof(error);
                if (ready > 0) {
                    if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &length)) error = errno;
                } else error = ready == 0 ? ETIMEDOUT : errno;
            }
            fprintf(out, "  tcp443 errno=%d\n", error);
            fflush(out);
            close(fd);
        }
        freeaddrinfo(result);
    }
    fclose(out); return 0;
}
