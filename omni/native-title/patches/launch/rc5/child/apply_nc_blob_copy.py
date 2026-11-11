#!/usr/bin/env python3
"""OMNI_NC_BLOB_COPY_V3: Omni's network cache keeps large bodies on the PS5.

WebKit's NetworkCache stores every body above the inline limit as a shared file in Blobs/<sha1> and hard-links it to
Records/.../<key>-blob. Hard links fail on the console's /data file system, so the link step failed for every large body:
the console cache (2026-11-10) had 6,181 records, 0 "-blob" link files and 16 orphaned blobs, i.e. no large response
(YouTube's 2.6 MB base.js, BotGuard's interpreter scripts, fonts, big images) was ever served from the cache.

V1 (2026-11-11) used WTF's FileSystem::hardLinkOrCopyFile; on the console that STILL produced 0 "-blob" files (rc5 child
3527660d, y10 runs: 194 files, 30 shared blobs, 0 links), i.e. std::filesystem::copy_file fails there as well. V2 replaces
both link sites with omniLinkOrCopy(): the hard link first (no change where links work), else a plain POSIX
open/read/write copy to <key>-blob (the path Storage reads), removed again if the copy fails. The first failure of each
kind is reported on stderr with errno. BlobStorage::synchronize already removes shared blobs nothing links to (link
count 1), so the copies cost no more disk than the bodies themselves. Read path unchanged; revert = this file.

Usage: apply_nc_blob_copy.py <webkit source root>   (anchored; idempotent)
"""
import sys
from pathlib import Path
root = Path(sys.argv[1])
p = root / 'Source/WebKit/NetworkProcess/cache/NetworkCacheBlobStorage.cpp'
s = p.read_text(encoding='utf-8')
MARK = 'OMNI_NC_BLOB_COPY_V3'
if MARK in s:
    print('already applied'); sys.exit(0)
old = 'if (!FileSystem::hardLink(blobPath, path))'
if s.count(old) != 2: sys.exit(f'expected 2 link sites, found {s.count(old)}')
ns = 'namespace WebKit {\nnamespace NetworkCache {\n'
if s.count(ns) != 1: sys.exit('namespace anchor not found exactly once')
helper = ns + r'''
// OMNI_NC_BLOB_COPY_V3: no working hard links on the PS5 /data file system: link if that really produced the record's
// <key>-blob (same size as the shared blob), else copy the shared blob there with plain POSIX I/O. V3 checks the link:
// V1 (hardLinkOrCopyFile) and V2 (link-or-copy) both left 0 "-blob" files on the console, i.e. the link call reported
// success without creating anything, so the copy never ran.
static void omniNcNote(const char* fmt, ...)
{
    struct stat st;
    if (!::stat("/data/omni/ncblob.log", &st) && st.st_size > 65536)
        return;
    FILE* f = ::fopen("/data/omni/ncblob.log", "a");
    if (!f)
        return;
    va_list ap;
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fputc(10, f);
    fclose(f);
}
static bool omniLinkOrCopy(const String& from, const String& to)
{
    static std::atomic<bool> linkReported { false }, copyReported { false }, ghostReported { false };
    static std::atomic<unsigned> linked { 0 }, copied { 0 }, failed { 0 };
    if (!((linked + copied + failed) % 50)) omniNcNote("OMNI NCBLOB V3 tally: linked %u copied %u failed %u", linked.load(), copied.load(), failed.load());
    auto f = from.utf8(), t = to.utf8();
    const char* fp = reinterpret_cast<const char*>(f.data());
    const char* tp = reinterpret_cast<const char*>(t.data());
    if (FileSystem::hardLink(from, to)) {
        struct stat a, b;
        if (!::stat(fp, &a) && !::stat(tp, &b) && a.st_size == b.st_size) {
            ++linked;
            return true;
        }
        if (!ghostReported.exchange(true))
            omniNcNote("OMNI NCBLOB: hard link reported success but the record blob is missing; copying instead (OMNI_NC_BLOB_COPY_V3)");
        ::unlink(tp);
    } else if (!linkReported.exchange(true))
        omniNcNote("OMNI NCBLOB: hard link failed (errno %d); copying blobs instead (OMNI_NC_BLOB_COPY_V3)", errno);
    int in = ::open(fp, O_RDONLY);
    if (in < 0) {
        if (!copyReported.exchange(true)) omniNcNote("OMNI NCBLOB: open blob failed (errno %d)", errno);
        ++failed;
        return false;
    }
    int out = ::open(tp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (out < 0) {
        if (!copyReported.exchange(true)) omniNcNote("OMNI NCBLOB: create record blob failed (errno %d) %s", errno, tp);
        ::close(in);
        ++failed;
        return false;
    }
    static constexpr size_t chunk = 64 * 1024;
    auto buffer = std::make_unique<char[]>(chunk);
    bool ok = true;
    while (ok) {
        ssize_t n = ::read(in, buffer.get(), chunk);
        if (!n)
            break;
        if (n < 0) {
            if (errno == EINTR) continue;
            ok = false;
            break;
        }
        for (ssize_t done = 0; done < n;) {
            ssize_t w = ::write(out, buffer.get() + done, n - done);
            if (w < 0) {
                if (errno == EINTR) continue;
                ok = false;
                break;
            }
            done += w;
        }
    }
    if (::close(out))
        ok = false;
    ::close(in);
    if (!ok) {
        if (!copyReported.exchange(true)) omniNcNote("OMNI NCBLOB: blob copy failed (errno %d)", errno);
        ::unlink(tp);
        ++failed;
    } else
        ++copied;
    return ok;
}
'''
s = s.replace(ns, helper, 1)
s = s.replace(old, 'if (!omniLinkOrCopy(blobPath, path)) // ' + MARK)
for inc in ('#include <atomic>', '#include <cerrno>', '#include <cstdarg>', '#include <cstdio>', '#include <memory>', '#include <sys/stat.h>'):
    if inc not in s:
        s = s.replace('#include <fcntl.h>\n', '#include <fcntl.h>\n' + inc + '\n', 1)
p.write_text(s, encoding='utf-8')
print('applied at 2 sites')
