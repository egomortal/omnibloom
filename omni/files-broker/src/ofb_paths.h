/* omni-files broker (OMNI_FILES_BROKER_V1): path rules shared by the payload and its host test.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * The broker serves exactly these roots and nothing else: /mnt/usb0..7 and /mnt/ext0..1.
 * A request path must be absolute, at most 4096 bytes, with no empty, "." or ".." components,
 * no backslash and no NUL. It is walked component by component from a pinned root descriptor
 * with openat(O_NOFOLLOW), so neither ".." nor a symlink (even one swapped in between calls) can
 * leave the root. Symlinks are refused outright. Same approach as Ex-Box's companion
 * (nxe-ps5/bigapp/modules/system_data/server_files.hpp, the user's own code).
 */
#ifndef OFB_PATHS_H
#define OFB_PATHS_H
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/stat.h>

#define OFB_MAX_PATH 4096

/* Test builds point the roots at a temporary folder: "<prefix>/mnt/usb0" etc. */
static char ofb_prefix[1024] = "";

static const char* const ofb_roots[] = {
    "/mnt/usb0", "/mnt/usb1", "/mnt/usb2", "/mnt/usb3", "/mnt/usb4", "/mnt/usb5", "/mnt/usb6", "/mnt/usb7",
    "/mnt/ext0", "/mnt/ext1",
};
#define OFB_NROOTS (sizeof ofb_roots / sizeof ofb_roots[0])

static int ofb_valid_path(const char* p)
{
    size_t n = strlen(p);
    if (n == 0 || n > OFB_MAX_PATH || p[0] != '/' || strchr(p, '\\')) return 0;
    const char* s = p + 1;
    while (*s) {
        const char* e = strchr(s, '/');
        size_t len = e ? (size_t)(e - s) : strlen(s);
        if (len == 0) return 0;                                  /* "//" or a trailing "/" */
        if (len == 1 && s[0] == '.') return 0;
        if (len == 2 && s[0] == '.' && s[1] == '.') return 0;
        if (len > 255) return 0;
        s += len;
        if (*s == '/') { s++; if (!*s) return 0; }              /* trailing "/" */
    }
    return 1;
}

/* Index of the root `p` is inside (p == root or p starts with root + "/"), or -1. */
static int ofb_root_of(const char* p)
{
    if (!ofb_valid_path(p)) return -1;
    for (size_t i = 0; i < OFB_NROOTS; i++) {
        size_t n = strlen(ofb_roots[i]);
        if (!strncmp(p, ofb_roots[i], n) && (p[n] == 0 || p[n] == '/')) return (int)i;
    }
    return -1;
}

static int ofb_open_root(int idx)
{
    char local[1200];
    snprintf(local, sizeof local, "%s%s", ofb_prefix, ofb_roots[idx]);
    return open(local, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
}

/* Opens the directory that contains the last component of `p` (walking every directory component
 * with O_NOFOLLOW|O_DIRECTORY) and points *leaf at that component inside `p`. For p == root, *leaf
 * is "" and the root itself is returned. -1 with errno on failure (EACCES for paths outside). */
static int ofb_open_parent(const char* p, const char** leaf)
{
    int idx = ofb_root_of(p);
    if (idx < 0) { errno = EACCES; return -1; }
    int dir = ofb_open_root(idx);
    if (dir < 0) return -1;
    const char* s = p + strlen(ofb_roots[idx]);
    if (*s == '/') s++;
    for (;;) {
        const char* e = strchr(s, '/');
        if (!e) { *leaf = s; return dir; }
        char part[256];
        size_t len = (size_t)(e - s);
        memcpy(part, s, len); part[len] = 0;
        int next = openat(dir, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
        int saved = errno;
        close(dir);
        if (next < 0) { errno = saved; return -1; }
        dir = next;
        s = e + 1;
    }
}

/* Opens `p` for reading: a regular file or a directory, never a symlink, device or fifo. */
static int ofb_open_read(const char* p)
{
    const char* leaf;
    int dir = ofb_open_parent(p, &leaf);
    if (dir < 0) return -1;
    if (!*leaf) return dir;                                      /* the root itself */
    int fd = openat(dir, leaf, O_RDONLY | O_NOFOLLOW | O_NONBLOCK);
    int saved = errno;
    close(dir);
    if (fd < 0) { errno = (saved == EMLINK || saved == ELOOP) ? EACCES : saved; return -1; }
    struct stat st;
    if (fstat(fd, &st) || (!S_ISREG(st.st_mode) && !S_ISDIR(st.st_mode))) { close(fd); errno = EACCES; return -1; }
    int flags = fcntl(fd, F_GETFL);
    if (flags >= 0) (void)fcntl(fd, F_SETFL, flags & ~O_NONBLOCK);
    return fd;
}

/* Opens `p` for writing. create_new: O_CREAT|O_EXCL (a new file only); otherwise the file must
 * already exist and be a regular file. Never truncates, never follows a symlink. */
static int ofb_open_write(const char* p, int create_new)
{
    const char* leaf;
    int dir = ofb_open_parent(p, &leaf);
    if (dir < 0) return -1;
    if (!*leaf) { close(dir); errno = EISDIR; return -1; }
    int fd = openat(dir, leaf, O_WRONLY | O_NOFOLLOW | (create_new ? (O_CREAT | O_EXCL) : 0), 0666);
    int saved = errno;
    close(dir);
    if (fd < 0) { errno = (saved == EMLINK || saved == ELOOP) ? EACCES : saved; return -1; }
    struct stat st;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode)) { close(fd); errno = EACCES; return -1; }
    return fd;
}

/* Creates one directory `p` (its parent must exist inside a root). */
static int ofb_mkdir(const char* p)
{
    const char* leaf;
    int dir = ofb_open_parent(p, &leaf);
    if (dir < 0) return -1;
    if (!*leaf) { close(dir); errno = EEXIST; return -1; }
    int rc = mkdirat(dir, leaf, 0777);
    int saved = errno;
    close(dir);
    errno = saved;
    return rc;
}
#endif
