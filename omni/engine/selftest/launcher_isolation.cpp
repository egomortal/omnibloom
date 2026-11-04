// Exercise the production launcher without WebKit, graphics, or page loading.
#include "../ports/webkit-requirements/src/launcher-common.h"
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <string.h>

#ifdef OMNI_ISOLATION_EMBEDDED
static const char* root = "/data/omni/engine-startup-isolation";
static const char* self = "/data/omni/omni-engine.elf";
#elif defined(__PROSPERO__)
static const char* root = "/data/omni/launcher-isolation";
static const char* self = "/data/omni/omni-launcher-isolation.elf";
#else
static const char* root = "/tmp/omni-launcher-isolation";
static const char* self = "/proc/self/exe";
#endif

static void timeoutSocket(int fd)
{
    timeval timeout { 8, 0 };
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
}

#ifdef OMNI_ISOLATION_EMBEDDED
static int omniStartupIsolation()
#else
int main()
#endif
{
    mkdir(root, 0777);
    std::string directory = std::string(root) + "/tickets";
    omni_launcher_set_dir(directory.c_str());
    char path[256];
    snprintf(path, sizeof(path), "%s/process-%d.log", root, (int)getpid());
    if (!freopen(path, "a", stderr))
        return 10;
    setvbuf(stderr, nullptr, _IONBF, 0);
    omni_launcher_trace("isolation v1 pid=%d: before bootstrap\n", (int)getpid());
    char* args[16];
    int count = 0;
    int role = omni_child_bootstrap(args, 16, &count);
    omni_launcher_trace("bootstrap returned role=%d args=%d fd=%d\n", role, count, PlayStation::getConnectionIdentifier());
    if (role == OMNI_ROLE_ERROR)
        return 11;
    if (role == OMNI_ROLE_CHILD) {
        int fd = PlayStation::getConnectionIdentifier();
        timeoutSocket(fd);
        char message[16] = {};
        ssize_t n = read(fd, message, sizeof(message));
        bool pass = n == 4 && !memcmp(message, "ping", 4) && write(fd, "pong", 4) == 4;
        omni_launcher_trace("CHILD %s: received=%zd\n", pass ? "PASS" : "FAIL", n);
        close(fd);
        for (int i = 0; i < count; ++i)
            free(args[i]);
        return pass ? 0 : 12;
    }

    // A late child must never recursively become another parent.
    std::string guard = std::string(root) + "/started.lock";
    int guardFd = open(guard.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (guardFd < 0) {
        omni_launcher_trace("STOP: test already started; no recursive spawning\n");
        return 13;
    }
    close(guardFd);
    setenv("OMNI_SELF_PATH", self, 1);
    int sockets[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET, 0, sockets)) {
        omni_launcher_trace("FAIL socketpair errno=%d\n", errno);
        return 14;
    }
    timeoutSocket(sockets[0]);
    char identifier[] = "1001";
    char* launchArgs[] = { identifier, nullptr };
    omni_launcher_trace("parent: before launching one helper\n");
    int pid = PlayStation::launchProcess("/omni/IsolationChild", launchArgs, { sockets[1], 0 });
    close(sockets[1]);
    bool pass = false;
    if (pid > 0 && write(sockets[0], "ping", 4) == 4) {
        char reply[16] = {};
        ssize_t n = read(sockets[0], reply, sizeof(reply));
        pass = n == 4 && !memcmp(reply, "pong", 4);
    }
    close(sockets[0]);
    omni_launcher_trace("PARENT %s: helper pid=%d\n", pass ? "PASS" : "FAIL", pid);
    return pass ? 0 : 15;
}
