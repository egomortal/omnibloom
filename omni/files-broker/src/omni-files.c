/* omni-files: the native Omni title's USB / extended-storage broker (OMNI_FILES_BROKER_V1).
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Why: a native title (PPSA99732) only sees /data, /mnt/disc and the system fonts. This payload runs
 * outside the sandbox (started by the title through the ELF loader on 9021, like its WebKit children)
 * and serves /mnt/usb0..7 and /mnt/ext0..1 over loopback TCP, so Omni's file picker can upload from
 * a USB drive and the Downloads page can copy a file to one. Same idea as Ex-Box's companion feed.
 *
 * Wire (blocking sockets: a title cannot set O_NONBLOCK), one request per connection:
 *   "OFB1\t<token>\t<verb>\t<hex path>\t<a>\t<b>\n"
 *   verbs: hello | places | stat p | list p | read p off len | write p off len new(1/0) | mkdir p
 *   reply: "OK\t<n>\n" + n bytes, or "ERR\t<errno>\n". For write, the client sends `len` bytes after
 *   its request line and gets "OK\t<len>\n" when they are on disk.
 *   entry lines: "<d|f>\t<size>\t<mtime>\t<hex name>\n"; places: "<hex root>\t<total>\t<free>\n".
 * Rules: loopback only; a per-start random token in /data/omni/native/broker.token (0600, owned by the
 * title's uid); only the roots above (ofb_paths.h); no delete, no rename, no truncate; read/write at
 * most 8 MiB per request, listings at most 10000 entries / 4 MiB; at most 4 clients at once.
 * Lifetime: exits when the title's pid is gone or /data/omni/native/closing-<pid> appears (s0c).
 */
#include "ofb_paths.h"
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <dirent.h>
#include <time.h>
#if defined(__linux__)
#include <sys/vfs.h>
#else
#include <sys/param.h>
#include <sys/mount.h>
#endif

#define OFB_PORT 8767
#define OFB_DIR "/data/omni/native"
#define OFB_MAX_IO (8u << 20)
#define OFB_MAX_LIST_BYTES (4u << 20)
#define OFB_MAX_ENTRIES 10000
#define OFB_MAX_CLIENTS 4

static char ofb_token[33];
static int ofb_parent = -1;
static volatile int ofb_clients = 0;
static char ofb_dir[1100] = OFB_DIR;

static void ofb_log(const char* fmt, ...)
{
    char path[1200];
    snprintf(path, sizeof path, "%s/omni-files.log", ofb_dir);
    FILE* f = fopen(path, "a");
    if (!f) return;
    time_t now = time(NULL);
    struct tm tm;
    localtime_r(&now, &tm);
    fprintf(f, "%02d:%02d:%02d ", tm.tm_hour, tm.tm_min, tm.tm_sec);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fputc('\n', f);
    fclose(f);
}

/* ---------------------------------------------------------------- hex */
static int ofb_unhex(const char* in, char* out, size_t cap)
{
    size_t n = strlen(in);
    if (n % 2 || n / 2 >= cap) return -1;
    for (size_t i = 0; i < n; i += 2) {
        int v = 0;
        for (int k = 0; k < 2; k++) {
            char c = in[i + k];
            int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
            if (d < 0) return -1;
            v = v * 16 + d;
        }
        if (v == 0) return -1;
        out[i / 2] = (char)v;
    }
    out[n / 2] = 0;
    return 0;
}
static void ofb_hex(const char* in, char* out)
{
    static const char d[] = "0123456789abcdef";
    for (; *in; in++) { unsigned char c = (unsigned char)*in; *out++ = d[c >> 4]; *out++ = d[c & 15]; }
    *out = 0;
}

/* ---------------------------------------------------------------- socket helpers */
static int ofb_send_all(int fd, const void* buf, size_t n)
{
    const char* p = buf;
    while (n) {
        ssize_t w = send(fd, p, n, 0);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) return -1;
        p += w; n -= (size_t)w;
    }
    return 0;
}
static int ofb_recv_all(int fd, void* buf, size_t n)
{
    char* p = buf;
    while (n) {
        ssize_t r = recv(fd, p, n, 0);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return -1;
        p += r; n -= (size_t)r;
    }
    return 0;
}
static void ofb_err(int fd, int e) { char b[32]; int n = snprintf(b, sizeof b, "ERR\t%d\n", e ? e : EIO); (void)ofb_send_all(fd, b, (size_t)n); }
static int ofb_ok(int fd, uint64_t n) { char b[48]; int k = snprintf(b, sizeof b, "OK\t%llu\n", (unsigned long long)n); return ofb_send_all(fd, b, (size_t)k); }

/* ---------------------------------------------------------------- verbs */
static int ofb_entry_line(char* out, size_t cap, const char* name, const struct stat* st)
{
    char hex[600];
    if (strlen(name) > 255) return -1;
    ofb_hex(name, hex);
    return snprintf(out, cap, "%c\t%llu\t%lld\t%s\n", S_ISDIR(st->st_mode) ? 'd' : 'f',
                    (unsigned long long)(st->st_size > 0 ? st->st_size : 0), (long long)st->st_mtime, hex);
}

static void ofb_places(int fd)
{
    char out[4096]; size_t used = 0;
    for (size_t i = 0; i < OFB_NROOTS; i++) {
        int d = ofb_open_root((int)i);
        if (d < 0) continue;
#ifndef OFB_TEST
        /* /mnt/usbN exists even with no drive: a drive is there only when the folder is a mount
           point, i.e. on another device than /mnt itself. */
        struct stat rs, ms;
        if (fstat(d, &rs) || stat("/mnt", &ms) || rs.st_dev == ms.st_dev) { close(d); continue; }
#endif
        unsigned long long total = 0, avail = 0;
        struct statfs sf;
        if (!fstatfs(d, &sf)) { total = (unsigned long long)sf.f_blocks * sf.f_bsize; avail = (unsigned long long)sf.f_bavail * sf.f_bsize; }
        close(d);
        if (!total) continue;                                    /* an empty mount point, no drive */
        char hex[64];
        ofb_hex(ofb_roots[i], hex);
        used += (size_t)snprintf(out + used, sizeof out - used, "%s\t%llu\t%llu\n", hex, total, avail);
    }
    if (ofb_ok(fd, used) == 0) (void)ofb_send_all(fd, out, used);
}

static void ofb_list(int fd, const char* path)
{
    int d = ofb_open_read(path);
    if (d < 0) { int e = errno; ofb_log("refused list errno=%d", e); ofb_err(fd, e); return; }
    struct stat st;
    if (fstat(d, &st) || !S_ISDIR(st.st_mode)) { close(d); ofb_err(fd, ENOTDIR); return; }
    DIR* dir = fdopendir(d);
    if (!dir) { int e = errno; close(d); ofb_err(fd, e); return; }
    size_t cap = 1 << 16, used = 0; int count = 0;
    char* out = malloc(cap);
    if (!out) { closedir(dir); ofb_err(fd, ENOMEM); return; }
    struct dirent* e;
    while ((e = readdir(dir))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        struct stat es;
        if (fstatat(dirfd(dir), e->d_name, &es, AT_SYMLINK_NOFOLLOW)) continue;
        if (!S_ISREG(es.st_mode) && !S_ISDIR(es.st_mode)) continue;   /* symlinks, devices: never listed */
        if (++count > OFB_MAX_ENTRIES) { free(out); closedir(dir); ofb_err(fd, EFBIG); return; }
        if (cap - used < 700) {
            if (cap >= OFB_MAX_LIST_BYTES) { free(out); closedir(dir); ofb_err(fd, EFBIG); return; }
            char* grown = realloc(out, cap * 2);
            if (!grown) { free(out); closedir(dir); ofb_err(fd, ENOMEM); return; }
            out = grown; cap *= 2;
        }
        int n = ofb_entry_line(out + used, cap - used, e->d_name, &es);
        if (n > 0) used += (size_t)n;
    }
    closedir(dir);
    if (ofb_ok(fd, used) == 0) (void)ofb_send_all(fd, out, used);
    free(out);
}

static void ofb_stat(int fd, const char* path)
{
    int f = ofb_open_read(path);
    if (f < 0) { ofb_err(fd, errno); return; }
    struct stat st;
    int rc = fstat(f, &st);
    close(f);
    if (rc) { ofb_err(fd, errno); return; }
    const char* name = strrchr(path, '/') + 1;
    char line[700];
    int n = ofb_entry_line(line, sizeof line, *name ? name : path, &st);
    if (n < 0) { ofb_err(fd, ENAMETOOLONG); return; }
    if (ofb_ok(fd, (uint64_t)n) == 0) (void)ofb_send_all(fd, line, (size_t)n);
}

static void ofb_read(int fd, const char* path, unsigned long long off, unsigned long long len)
{
    if (len > OFB_MAX_IO) { ofb_err(fd, EFBIG); return; }
    int f = ofb_open_read(path);
    if (f < 0) { int e = errno; ofb_log("refused read errno=%d", e); ofb_err(fd, e); return; }
    struct stat st;
    if (fstat(f, &st) || !S_ISREG(st.st_mode)) { close(f); ofb_err(fd, EISDIR); return; }
    unsigned long long size = (unsigned long long)st.st_size;
    unsigned long long n = off >= size ? 0 : (size - off < len ? size - off : len);
    if (ofb_ok(fd, n)) { close(f); return; }
    char* buf = malloc(65536);   /* heap: payload threads get small stacks (a 64 KiB stack buffer crashed the broker) */
    if (!buf) { close(f); return; }
    while (n) {
        size_t want = n < 65536 ? (size_t)n : 65536;
        ssize_t r = pread(f, buf, want, (off_t)off);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) break;                                       /* client sees a short body: an error */
        if (ofb_send_all(fd, buf, (size_t)r)) break;
        off += (unsigned long long)r; n -= (unsigned long long)r;
    }
    free(buf);
    close(f);
}

static void ofb_write(int fd, const char* path, unsigned long long off, unsigned long long len, int create_new)
{
    if (len > OFB_MAX_IO || (create_new && off)) { ofb_err(fd, EINVAL); return; }
    int f = ofb_open_write(path, create_new);
    if (f < 0) { int e = errno; ofb_log("refused write errno=%d", e); ofb_err(fd, e); return; }
    struct stat st;
    if (fstat(f, &st) || (unsigned long long)st.st_size < off) { close(f); ofb_err(fd, EINVAL); return; }
    char* buf = malloc(65536);
    if (!buf) { close(f); ofb_err(fd, ENOMEM); return; }
    unsigned long long left = len;
    int err = 0;
    while (left) {
        size_t want = left < 65536 ? (size_t)left : 65536;
        if (ofb_recv_all(fd, buf, want)) { err = EPIPE; break; }
        size_t done = 0;
        while (done < want) {
            ssize_t w = pwrite(f, buf + done, want - done, (off_t)(off + done));
            if (w < 0 && errno == EINTR) continue;
            if (w <= 0) { err = errno ? errno : ENOSPC; break; }
            done += (size_t)w;
        }
        if (err) break;
        off += want; left -= want;
    }
    free(buf);
    if (!err && fsync(f)) err = errno;
    close(f);
    if (err) { ofb_err(fd, err); return; }
    (void)ofb_ok(fd, len);
}

/* ---------------------------------------------------------------- one client */
static void ofb_serve(int fd)
{
    struct timeval tv = { 30, 0 };
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    char line[9300]; size_t used = 0;
    for (;;) {
        if (used >= sizeof line - 1) { ofb_err(fd, E2BIG); return; }
        ssize_t r = recv(fd, line + used, 1, 0);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return;
        if (line[used] == '\n') break;
        used++;
    }
    line[used] = 0;
    char* field[7] = { 0 }; int nf = 0;
    for (char* s = line; nf < 7; ) { field[nf++] = s; char* t = strchr(s, '\t'); if (!t) break; *t = 0; s = t + 1; }
    if (nf < 3 || strcmp(field[0], "OFB1") || strlen(field[1]) != 32 || memcmp(field[1], ofb_token, 32)) { ofb_log("refused: bad token or header"); ofb_err(fd, EACCES); return; }
    const char* verb = field[2];
    if (!strcmp(verb, "hello")) { (void)ofb_ok(fd, 0); return; }
    if (!strcmp(verb, "places")) { ofb_places(fd); return; }
    if (nf < 4) { ofb_err(fd, EINVAL); return; }
    char path[OFB_MAX_PATH + 1];
    if (ofb_unhex(field[3], path, sizeof path)) { ofb_err(fd, EINVAL); return; }
    unsigned long long a = nf > 4 ? strtoull(field[4], NULL, 10) : 0, b = nf > 5 ? strtoull(field[5], NULL, 10) : 0;
    if (!strcmp(verb, "stat")) ofb_stat(fd, path);
    else if (!strcmp(verb, "list")) ofb_list(fd, path);
    else if (!strcmp(verb, "read")) ofb_read(fd, path, a, b);
    else if (!strcmp(verb, "write")) ofb_write(fd, path, a, b, nf > 6 && !strcmp(field[6], "1"));
    else if (!strcmp(verb, "mkdir")) { if (ofb_mkdir(path)) ofb_err(fd, errno); else (void)ofb_ok(fd, 0); }
    else ofb_err(fd, EINVAL);
}
static void* ofb_client(void* arg)
{
    int fd = (int)(intptr_t)arg;
    ofb_serve(fd);
    close(fd);
    __atomic_sub_fetch(&ofb_clients, 1, __ATOMIC_SEQ_CST);
    return NULL;
}

/* ---------------------------------------------------------------- start-up */
static int ofb_make_token(int uid)
{
    unsigned char raw[16];
    int r = open("/dev/urandom", O_RDONLY);
    if (r < 0 || read(r, raw, sizeof raw) != (ssize_t)sizeof raw) { if (r >= 0) close(r); return -1; }
    close(r);
    static const char d[] = "0123456789abcdef";
    for (int i = 0; i < 16; i++) { ofb_token[2 * i] = d[raw[i] >> 4]; ofb_token[2 * i + 1] = d[raw[i] & 15]; }
    ofb_token[32] = 0;
    char tmp[1200], fin[1200];
    snprintf(tmp, sizeof tmp, "%s/broker.token.tmp", ofb_dir);
    snprintf(fin, sizeof fin, "%s/broker.token", ofb_dir);
    int f = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (f < 0) return -1;
    if (write(f, ofb_token, 32) != 32) { close(f); return -1; }
    if (uid > 0 && fchown(f, (uid_t)uid, (gid_t)-1)) ofb_log("token chown failed errno=%d", errno);           /* the title runs as uid 1 */
    (void)fchmod(f, 0600);
    fsync(f);
    close(f);
    return rename(tmp, fin);
}
static int ofb_parent_gone(void)
{
    if (ofb_parent <= 0) return 1;
    if (kill(ofb_parent, 0) == -1 && errno == ESRCH) return 1;
    char marker[1200];
    snprintf(marker, sizeof marker, "%s/closing-%d", ofb_dir, ofb_parent);
    return access(marker, F_OK) == 0;
}

int ofb_main(void)
{
    signal(SIGPIPE, SIG_IGN);
    char pf[1200];
    snprintf(pf, sizeof pf, "%s/broker.parent", ofb_dir);
    int uid = -1;
    FILE* p = fopen(pf, "r");
    if (!p || fscanf(p, "%d %d", &ofb_parent, &uid) < 1) { if (p) fclose(p); ofb_log("no broker.parent: exiting"); return 1; }
    fclose(p);
    if (ofb_parent_gone()) { ofb_log("parent %d already gone: exiting", ofb_parent); return 1; }
    int s = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET; a.sin_port = htons(OFB_PORT); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (s < 0 || bind(s, (struct sockaddr*)&a, sizeof a) || listen(s, 8)) {
        ofb_log("bind 127.0.0.1:%d failed errno=%d (another broker running?)", OFB_PORT, errno);
        return 1;
    }
    if (ofb_make_token(uid)) { ofb_log("token file failed errno=%d", errno); close(s); return 1; }
    ofb_log("omni-files OMNI_FILES_BROKER_V1 ready on 127.0.0.1:%d for title pid %d uid %d", OFB_PORT, ofb_parent, uid);
    for (;;) {
        struct pollfd pfd = { s, POLLIN, 0 };
        int n = poll(&pfd, 1, 500);
        if (ofb_parent_gone()) break;
        if (n <= 0) continue;
        int c = accept(s, NULL, NULL);
        if (c < 0) continue;
        if (__atomic_add_fetch(&ofb_clients, 1, __ATOMIC_SEQ_CST) > OFB_MAX_CLIENTS) {
            __atomic_sub_fetch(&ofb_clients, 1, __ATOMIC_SEQ_CST);
            ofb_err(c, EBUSY); close(c); continue;
        }
        pthread_t t;
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setstacksize(&attr, 512 * 1024);   /* explicit: the payload default is small */
        int prc = pthread_create(&t, &attr, ofb_client, (void*)(intptr_t)c);
        pthread_attr_destroy(&attr);
        if (prc) { __atomic_sub_fetch(&ofb_clients, 1, __ATOMIC_SEQ_CST); close(c); continue; }
        pthread_detach(t);
    }
    close(s);
    char tok[1200];
    snprintf(tok, sizeof tok, "%s/broker.token", ofb_dir);
    unlink(tok);
    ofb_log("title %d gone: exiting", ofb_parent);
    return 0;
}

#ifndef OFB_TEST
int main(void) { return ofb_main(); }
#endif
