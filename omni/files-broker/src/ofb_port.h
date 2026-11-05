/* SPDX-License-Identifier: GPL-3.0-or-later
 * Files service port configuration. No sockets, launches or file operations on user data.
 */
#ifndef OFB_PORT_CONFIG_H
#define OFB_PORT_CONFIG_H
#include "hub_json.h"
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <time.h>

#ifndef OFB_CARD_PATH
#define OFB_CARD_PATH "/data/hub/apps/files-broker.json"
#endif
#ifndef OFB_RUNTIME_PATH
#define OFB_RUNTIME_PATH "/data/hub/runtime/files-broker.json"
#endif

static int ofb_card_port(const char* path)
{
    char buf[32769];
    FILE* f = fopen(path, "rb");
    if (!f) return 0;
    size_t n = fread(buf, 1, sizeof buf, f);
    int bad = ferror(f) || n >= sizeof buf;
    fclose(f);
    if (bad) return 0;
    hj_arena ar = {0};
    const char* err = NULL;
    const hj* value = hj_parse(buf, n, &ar, &err);
    const char* id = hj_getstr(value, "id");
    long port = hj_getint(value, "port", 8761, 8899);
    int out = value && value->t == HJ_OBJ && id && !strcmp(id, "files-broker")
        && hj_getint(value, "hub_api", 1, 1) == 1 && port >= 8761 ? (int)port : 0;
    hj_arena_free(&ar);
    return out;
}

static int ofb_runtime_write(const char* path, int port, long pid, long started_at)
{
    char tmp[1200], body[256];
    if (port < 8761 || port > 8899 || pid <= 0) return 0;
    int len = snprintf(tmp, sizeof tmp, "%s.%ld.new", path, pid);
    if (len < 0 || (size_t)len >= sizeof tmp) return 0;
    len = snprintf(body, sizeof body,
        "{\"id\":\"files-broker\",\"host\":\"127.0.0.1\",\"port\":%d,\"pid\":%ld,\"started_at\":%ld}\n",
        port, pid, started_at);
    if (len < 0 || (size_t)len >= sizeof body) return 0;
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return 0;
    int ok = write(fd, body, (size_t)len) == len && fsync(fd) == 0;
    if (close(fd) != 0) ok = 0;
    if (ok) ok = rename(tmp, path) == 0;
    if (!ok) unlink(tmp);
    return ok;
}

static void ofb_runtime_remove(const char* path, long pid)
{
    char buf[1024];
    FILE* f = fopen(path, "rb");
    if (!f) return;
    size_t n = fread(buf, 1, sizeof buf, f);
    int bad = ferror(f) || n == sizeof buf;
    fclose(f);
    if (bad) return;
    hj_arena ar = {0};
    const char* err = NULL;
    const hj* value = hj_parse(buf, n, &ar, &err);
    const char* id = hj_getstr(value, "id");
    if (id && !strcmp(id, "files-broker") && hj_getint(value, "pid", 1, 2147483647) == pid)
        unlink(path);
    hj_arena_free(&ar);
}
#endif
