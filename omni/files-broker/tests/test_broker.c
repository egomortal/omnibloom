/* Host test for omni-files (OMNI_FILES_BROKER_V1): path rules + a real loopback round trip.
 * Build: cc -O1 -Wall -Wextra -pthread -DOFB_TEST -I../src test_broker.c -o test_broker && ./test_broker
 */
#ifndef OFB_TEST
#define OFB_TEST
#endif
#include "../src/omni-files.c"
#include <assert.h>

static int fails = 0, checks = 0;
#define CHECK(c, what) do { checks++; if (!(c)) { fails++; printf("FAIL: %s\n", what); } else printf("ok   %s\n", what); } while (0)

static char base[512];

static int request(const char* tok, const char* verb, const char* path, const char* extra, const void* body, size_t blen, char* reply, size_t cap, long* status)
{
    int s = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in a; memset(&a, 0, sizeof a);
    a.sin_family = AF_INET; a.sin_port = htons(OFB_PORT); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(s, (struct sockaddr*)&a, sizeof a)) { close(s); return -1; }
    char hex[9000] = "";
    if (path) ofb_hex(path, hex);
    char line[9400];
    int n = snprintf(line, sizeof line, "OFB1\t%s\t%s\t%s%s%s\n", tok, verb, hex, extra ? "\t" : "", extra ? extra : "");
    ofb_send_all(s, line, (size_t)n);
    if (body && blen) ofb_send_all(s, body, blen);
    char head[64]; size_t u = 0;
    while (u < sizeof head - 1 && recv(s, head + u, 1, 0) == 1 && head[u] != '\n') u++;
    head[u] = 0;
    size_t got = 0;
    if (!strncmp(head, "OK\t", 3)) {
        *status = 0;
        size_t want = strtoull(head + 3, NULL, 10);
        while (got < want && got < cap) { ssize_t r = recv(s, reply + got, (want - got) < (cap - got) ? want - got : cap - got, 0); if (r <= 0) break; got += (size_t)r; }
    } else *status = strtol(head + 4, NULL, 10);
    if (got < cap) reply[got] = 0;
    close(s);
    return (int)got;
}
static void* server(void* x) { (void)x; ofb_main(); return NULL; }

int main(void)
{
    snprintf(base, sizeof base, "/tmp/ofb-test-%d", (int)getpid());
    char cmd[8192];
    snprintf(cmd, sizeof cmd, "rm -rf %s && mkdir -p %s/mnt/usb0/sub %s/mnt/usb1 %s/data %s/outside && echo secret > %s/outside/secret.txt"
             " && printf 'hello world' > %s/mnt/usb0/a.txt && ln -s %s/outside %s/mnt/usb0/escape && ln -s %s/outside/secret.txt %s/mnt/usb0/link.txt",
             base, base, base, base, base, base, base, base, base, base, base);
    assert(!system(cmd));
    snprintf(ofb_prefix, sizeof ofb_prefix, "%s", base);
    snprintf(ofb_dir, sizeof ofb_dir, "%s/data", base);

    /* path rules */
    CHECK(ofb_root_of("/mnt/usb0") == 0, "root itself allowed");
    CHECK(ofb_root_of("/mnt/usb0/a.txt") == 0, "file in root allowed");
    CHECK(ofb_root_of("/mnt/ext1/x") == 9, "ext1 allowed");
    CHECK(ofb_root_of("/mnt/usb8/x") < 0, "usb8 refused");
    CHECK(ofb_root_of("/mnt/usb0x/x") < 0, "usb0x prefix trick refused");
    CHECK(ofb_root_of("/mnt/usb0/../../user") < 0, "dotdot refused");
    CHECK(ofb_root_of("/mnt/usb0/./a.txt") < 0, "dot refused");
    CHECK(ofb_root_of("/mnt/usb0//a.txt") < 0, "empty component refused");
    CHECK(ofb_root_of("/mnt/usb0/a.txt/") < 0, "trailing slash refused");
    CHECK(ofb_root_of("/mnt/usb0\\..\\x") < 0, "backslash refused");
    CHECK(ofb_root_of("/user/home") < 0, "/user refused");
    CHECK(ofb_root_of("/system_data/priv") < 0, "/system_data refused");
    CHECK(ofb_root_of("/data/omni") < 0, "/data refused");
    CHECK(ofb_root_of("mnt/usb0") < 0, "relative refused");
    int fd = ofb_open_read("/mnt/usb0/escape/secret.txt"); CHECK(fd < 0, "symlinked directory not followed"); if (fd >= 0) close(fd);
    fd = ofb_open_read("/mnt/usb0/link.txt"); CHECK(fd < 0 && errno == EACCES, "symlinked file refused"); if (fd >= 0) close(fd);
    fd = ofb_open_write("/mnt/usb0/link.txt", 0); CHECK(fd < 0, "write through symlink refused"); if (fd >= 0) close(fd);
    fd = ofb_open_write("/mnt/usb0/a.txt", 1); CHECK(fd < 0 && errno == EEXIST, "create-new never overwrites"); if (fd >= 0) close(fd);
    CHECK(ofb_mkdir("/mnt/usb0/escape/new") < 0, "mkdir through symlink refused");

    /* FB-01: entries planted in the runtime folder before the broker starts must not redirect its writes */
    snprintf(cmd, sizeof cmd, "printf keep > %s/outside/victim && printf keep > %s/outside/victim-log"
             " && ln -s %s/outside/victim %s/data/broker.token.tmp && ln -s %s/outside/victim-log %s/data/omni-files.log",
             base, base, base, base, base, base);
    assert(!system(cmd));

    /* round trip */
    FILE* pf = fopen(strcat(strcpy(cmd, base), "/data/broker.parent"), "w");
    fprintf(pf, "%d %d\n", (int)getpid(), (int)getuid()); fclose(pf);
    pthread_t t; pthread_create(&t, NULL, server, NULL);
    usleep(300000);
    char tok[40] = "";
    FILE* tf = fopen(strcat(strcpy(cmd, base), "/data/broker.token"), "r");
    CHECK(tf && fread(tok, 1, 32, tf) == 32, "token file written"); if (tf) fclose(tf);
    struct stat ts; CHECK(!stat(cmd, &ts) && (ts.st_mode & 0777) == 0600, "token file is 0600");
    {
        char vp[700], got[16] = ""; struct stat ls;
        snprintf(vp, sizeof vp, "%s/outside/victim", base);
        FILE* v = fopen(vp, "r"); size_t vn = v ? fread(got, 1, sizeof got - 1, v) : 0; if (v) fclose(v); got[vn] = 0;
        CHECK(!strcmp(got, "keep"), "FB-01: planted broker.token.tmp link: target outside is untouched");
        snprintf(vp, sizeof vp, "%s/outside/victim-log", base);
        v = fopen(vp, "r"); vn = v ? fread(got, 1, sizeof got - 1, v) : 0; if (v) fclose(v); got[vn] = 0;
        CHECK(!strcmp(got, "keep"), "FB-01: planted omni-files.log link: target outside is untouched");
        snprintf(vp, sizeof vp, "%s/data/broker.token", base);
        CHECK(!lstat(vp, &ls) && S_ISREG(ls.st_mode) && ls.st_nlink == 1, "FB-01: published token is a regular file of its own");
    }
    char rep[70000]; long st = -1;
    request("00000000000000000000000000000000", "hello", NULL, NULL, NULL, 0, rep, sizeof rep, &st); CHECK(st == EACCES, "bad token refused");
    request(tok, "hello", NULL, NULL, NULL, 0, rep, sizeof rep, &st); CHECK(st == 0, "hello with token");
    request(tok, "places", NULL, NULL, NULL, 0, rep, sizeof rep, &st); CHECK(st == 0 && strstr(rep, "2f6d6e742f7573623") != NULL, "places lists the test usb roots");
    request(tok, "list", "/mnt/usb0", NULL, NULL, 0, rep, sizeof rep, &st);
    CHECK(st == 0 && strstr(rep, "612e747874") && !strstr(rep, "657363617065") && !strstr(rep, "6c696e6b2e747874"), "list shows a.txt, hides symlinks");
    request(tok, "read", "/mnt/usb0/a.txt", "6\t5", NULL, 0, rep, sizeof rep, &st); CHECK(st == 0 && !strcmp(rep, "world"), "ranged read");
    request(tok, "read", "/mnt/usb0/escape/secret.txt", "0\t100", NULL, 0, rep, sizeof rep, &st); CHECK(st != 0, "read via symlink escape refused");
    request(tok, "read", "/mnt/usb0/../outside/secret.txt", "0\t100", NULL, 0, rep, sizeof rep, &st); CHECK(st == EACCES, "read via dotdot refused");
    request(tok, "read", "/mnt/usb0/a.txt", "0\t99999999", NULL, 0, rep, sizeof rep, &st); CHECK(st == EFBIG, "oversized read refused");
    request(tok, "mkdir", "/mnt/usb1/Omni", NULL, NULL, 0, rep, sizeof rep, &st); CHECK(st == 0, "mkdir");
    request(tok, "write", "/mnt/usb1/Omni/f.bin", "0\t4\t1", "abcd", 4, rep, sizeof rep, &st); CHECK(st == 0, "write new");
    request(tok, "write", "/mnt/usb1/Omni/f.bin", "4\t3\t0", "efg", 3, rep, sizeof rep, &st); CHECK(st == 0, "append");
    request(tok, "write", "/mnt/usb1/Omni/f.bin", "0\t1\t1", "z", 1, rep, sizeof rep, &st); CHECK(st == EEXIST, "write-new on existing refused");
    request(tok, "read", "/mnt/usb1/Omni/f.bin", "0\t100", NULL, 0, rep, sizeof rep, &st); CHECK(st == 0 && !strcmp(rep, "abcdefg"), "written bytes read back");
    request(tok, "stat", "/mnt/usb1/Omni/f.bin", NULL, NULL, 0, rep, sizeof rep, &st); CHECK(st == 0 && rep[0] == 'f' && strstr(rep, "\t7\t"), "stat size 7");
    request(tok, "write", "/user/x", "0\t1\t1", "z", 1, rep, sizeof rep, &st); CHECK(st == EACCES, "write outside roots refused");
    request(tok, "delete", "/mnt/usb1/Omni/f.bin", NULL, NULL, 0, rep, sizeof rep, &st); CHECK(st == EINVAL, "no delete verb");

    /* lifetime: the closing marker ends the broker */
    snprintf(cmd, sizeof cmd, "%s/data/closing-%d", base, (int)getpid());
    FILE* m = fopen(cmd, "w"); fclose(m);
    pthread_join(t, NULL);
    snprintf(cmd, sizeof cmd, "%s/data/broker.token", base);
    CHECK(access(cmd, F_OK) != 0, "broker exits on the closing marker and removes its token");
    snprintf(cmd, sizeof cmd, "rm -rf %s", base); (void)!system(cmd);
    printf("%d/%d checks passed\n", checks - fails, checks);
    return fails ? 1 : 0;
}
