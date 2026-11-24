// OMNI_INPROC_NET_WRAPS_V1 (2026-11-24): what WebKit's NetworkProcess (curl) needs to run INSIDE the title.
// Single-process plan, "network engine in the app". Console facts (OMNI_NET_PROBE_V1, gin26-gin28):
//  - fcntl(F_SETFL, O_NONBLOCK) on a socket -> EACCES in the title (ioctl FIONBIO too); setsockopt(SOL_SOCKET, 0x1200
//    SO_NBIO) works, and afterwards connect/poll/recv/send behave non-blocking (EINPROGRESS, EAGAIN).
//  - getaddrinfo in the title is the payload SDK stub (always EAI_FAIL). The engine child links the SDK libc version:
//    sceNetPoolCreate + sceNetResolverCreate + sceNetResolverStartNtoa (IPv4) from libSceNet. R2: the title cannot load
//    modules at runtime (dlsym found no sceKernelLoadStartModule, gin28), so it links libSceNet directly like the child
//    (-lSceNet; the five functions are ordinary imports, allowed by name in the recipe's import gate).
// libcurl (seclibs) calls fcntl for non-blocking and the threaded resolver (getaddrinfo on a thread), so these wraps
// are all it needs. Linked with --wrap=fcntl --wrap=getaddrinfo --wrap=freeaddrinfo (tools/apply_inproc_net_wraps.py).
// Every path that the console already allowed behaves exactly as before (the real call first).
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>

int __real_fcntl(int fd, int cmd, ...);
int sceNetPoolCreate(const char* name, int size, int flags);
int sceNetPoolDestroy(int pool);
int sceNetResolverCreate(const char* name, int pool, int flags);
int sceNetResolverStartNtoa(int rid, const char* host, struct in_addr* addr, int timeout, int retry, int flags);
int sceNetResolverDestroy(int rid);
int sceNetInit(void);   // R3: libSceNet init before its resolver (the child does it at startup)

#define OMNI_SO_NBIO 0x1200
#define OMNI_NB_FDS 8192
static unsigned char omni_nb[OMNI_NB_FDS];   // 1 = non-blocking set through SO_NBIO (F_GETFL reports O_NONBLOCK)

int __wrap_fcntl(int fd, int cmd, ...)
{
    va_list ap;
    va_start(ap, cmd);
    long arg = va_arg(ap, long);
    va_end(ap);
    int rc = __real_fcntl(fd, cmd, arg);
    if (cmd == F_GETFL && rc >= 0 && fd >= 0 && fd < OMNI_NB_FDS)
        return omni_nb[fd] ? (rc | O_NONBLOCK) : (rc & ~O_NONBLOCK);
    if (cmd != F_SETFL || fd < 0)
        return rc;
    const int want = (arg & O_NONBLOCK) ? 1 : 0;
    if (rc < 0 && errno == EACCES) {
        int saved = errno;
        int v = want;
        if (setsockopt(fd, SOL_SOCKET, OMNI_SO_NBIO, &v, sizeof v)) { errno = saved; return rc; }   // not a socket: as before
        (void)__real_fcntl(fd, F_SETFL, arg & ~(long)O_NONBLOCK);   // the other flags, if any
        if (fd < OMNI_NB_FDS) omni_nb[fd] = (unsigned char)want;
        return 0;
    }
    if (rc >= 0 && fd < OMNI_NB_FDS && omni_nb[fd] != want) {   // a socket of ours switched back (or a reused fd number)
        int v = want;
        if (!setsockopt(fd, SOL_SOCKET, OMNI_SO_NBIO, &v, sizeof v) || !want)
            omni_nb[fd] = (unsigned char)want;
    }
    return rc;
}

// One allocation per result: the addrinfo, then its sockaddr. omni_inproc_freeaddrinfo frees the chain.
static struct addrinfo* omni_ai_new(int family, const struct addrinfo* hints, const void* addr, uint16_t port_be)
{
    const size_t salen = family == AF_INET6 ? sizeof(struct sockaddr_in6) : sizeof(struct sockaddr_in);
    struct addrinfo* ai = calloc(1, sizeof *ai + salen);
    if (!ai) return NULL;
    struct sockaddr* sa = (struct sockaddr*)(ai + 1);
    if (family == AF_INET6) {
        struct sockaddr_in6* s6 = (struct sockaddr_in6*)sa;
        s6->sin6_len = sizeof *s6; s6->sin6_family = AF_INET6; s6->sin6_port = port_be;
        memcpy(&s6->sin6_addr, addr, sizeof s6->sin6_addr);
    } else {
        struct sockaddr_in* s4 = (struct sockaddr_in*)sa;
        s4->sin_len = sizeof *s4; s4->sin_family = AF_INET; s4->sin_port = port_be;
        memcpy(&s4->sin_addr, addr, sizeof s4->sin_addr);
    }
    ai->ai_family = family;
    ai->ai_socktype = hints && hints->ai_socktype ? hints->ai_socktype : SOCK_STREAM;
    ai->ai_protocol = hints ? hints->ai_protocol : 0;
    ai->ai_addrlen = (socklen_t)salen;
    ai->ai_addr = sa;
    return ai;
}

int omni_inproc_getaddrinfo(const char* node, const char* service, const struct addrinfo* hints, struct addrinfo** res)
{
    if (!res) return EAI_FAIL;
    *res = NULL;
    const int family = hints ? hints->ai_family : AF_UNSPEC;
    uint16_t port = 0;
    if (service && *service) {
        char* end = NULL;
        long p = strtol(service, &end, 10);
        if (!end || *end || p < 0 || p > 65535) return EAI_SERVICE;   // curl passes numeric ports
        port = htons((uint16_t)p);
    }
    struct in_addr a4;
    struct in6_addr a6;
    if (!node) {   // passive/loopback request
        a4.s_addr = htonl((hints && (hints->ai_flags & AI_PASSIVE)) ? INADDR_ANY : INADDR_LOOPBACK);
        *res = omni_ai_new(AF_INET, hints, &a4, port);
        return *res ? 0 : EAI_MEMORY;
    }
    if (family != AF_INET6 && inet_pton(AF_INET, node, &a4) == 1) { *res = omni_ai_new(AF_INET, hints, &a4, port); return *res ? 0 : EAI_MEMORY; }
    if (family != AF_INET && inet_pton(AF_INET6, node, &a6) == 1) { *res = omni_ai_new(AF_INET6, hints, &a6, port); return *res ? 0 : EAI_MEMORY; }
    if (hints && (hints->ai_flags & AI_NUMERICHOST)) return EAI_NONAME;
    if (family == AF_INET6) return EAI_NONAME;   // Sony's resolver gives IPv4 only
    if (!strcmp(node, "localhost")) { a4.s_addr = htonl(INADDR_LOOPBACK); *res = omni_ai_new(AF_INET, hints, &a4, port); return *res ? 0 : EAI_MEMORY; }
    // R3 (gin30: curl "could not resolve host" in-app): log the first results, and sceNetInit() once if the pool or the
    // resolver is refused, then retry.
    static int logged = 0, inited = 0;
    static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
    int pool = sceNetPoolCreate("omni-dns", 0x4000, 0);
    if (pool < 0) {
        pthread_mutex_lock(&lock);
        if (!inited) { inited = 1; int ni = sceNetInit(); fprintf(stderr, "OMNI INPROC NET: pool refused %#x -> sceNetInit %#x\n", (unsigned)pool, (unsigned)ni); }
        pthread_mutex_unlock(&lock);
        pool = sceNetPoolCreate("omni-dns", 0x4000, 0);
    }
    if (pool < 0) { if (logged++ < 8) fprintf(stderr, "OMNI INPROC NET: getaddrinfo(%s) pool %#x\n", node, (unsigned)pool); return EAI_AGAIN; }
    int rid = sceNetResolverCreate("omni-dns", pool, 0);
    if (rid < 0) {
        pthread_mutex_lock(&lock);
        if (!inited) { inited = 1; int ni = sceNetInit(); fprintf(stderr, "OMNI INPROC NET: resolver refused %#x -> sceNetInit %#x\n", (unsigned)rid, (unsigned)ni); }
        pthread_mutex_unlock(&lock);
        rid = sceNetResolverCreate("omni-dns", pool, 0);
    }
    int rc = EAI_AGAIN;
    if (rid < 0 && logged++ < 8) fprintf(stderr, "OMNI INPROC NET: getaddrinfo(%s) resolver %#x\n", node, (unsigned)rid);
    if (rid >= 0) {
        memset(&a4, 0, sizeof a4);
        int r = sceNetResolverStartNtoa(rid, node, &a4, 0, 0, 0);
        if (logged++ < 8) { char t[32] = "?"; inet_ntop(AF_INET, &a4, t, sizeof t); fprintf(stderr, "OMNI INPROC NET: getaddrinfo(%s) pool %#x rid %#x ntoa %#x -> %s (OMNI_INPROC_NET_WRAPS_V1)\n", node, (unsigned)pool, (unsigned)rid, (unsigned)r, t); }
        if (!r && a4.s_addr) { *res = omni_ai_new(AF_INET, hints, &a4, port); rc = *res ? 0 : EAI_MEMORY; }
        else rc = EAI_NONAME;
        sceNetResolverDestroy(rid);
    }
    sceNetPoolDestroy(pool);
    return rc;
}

void omni_inproc_freeaddrinfo(struct addrinfo* ai)
{
    while (ai) {
        struct addrinfo* next = ai->ai_next;
        free(ai);
        ai = next;
    }
}
