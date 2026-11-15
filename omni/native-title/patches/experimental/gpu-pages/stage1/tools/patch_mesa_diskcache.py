#!/usr/bin/env python3
"""OMNI_MESA_DISKCACHE_V1 (2026-11-14): make Mesa's on-disk shader cache work on the PS5 (stage-1 "layers"), and say why
when it doesn't. Patches src/util/disk_cache.c and disk_cache_os.c of the ogp Mesa tree (1ba9874f). Idempotent.

Why: OMNI_GPUPAGES_SHADERCACHE_V1 (b50dba7f) set MESA_SHADER_CACHE_DIR, yet the cache dir stayed empty and every launch
paid ~1.3 s compiling TextureMapper shaders on the first page frame. Mesa turns the cache off silently on any setup
failure. On the PS5 the likely ones: the multi-file index is posix_fallocate()d and mmap()ed MAP_SHARED (both can be
refused there), and disk_cache_enabled() refuses when euid/egid differ from uid/gid.
  1. disk_cache_enabled(): skip the __normal_user() check on __PROSPERO__ (logged once when the ids differ).
  2. index: if posix_fallocate fails for any reason, try ftruncate; if mmap(MAP_SHARED) fails, use a private anonymous
     index (it only tracks size + a quick key lookup; entries are plain files read by name).
  3. "OMNI MESA CACHE:" stderr lines: why disk_cache_type_create gave up (line + errno), or "on <path> (type)"; first put,
     then every 25; hits/misses at 10, 50, 200 gets.
usage: patch_mesa_diskcache.py <mesa src root>
"""
import sys
from pathlib import Path

MARK = 'OMNI_MESA_DISKCACHE_V1'
root = Path(sys.argv[1]) / 'src' / 'util'


def patch(name, edits):
    p = root / name
    s = p.read_text(encoding='utf-8')
    if MARK in s:
        print('already', name)
        return
    for old, new, count in edits:
        n = s.count(old)
        if n != count:
            sys.exit('%s: anchor found %d times (want %d): %r' % (name, n, count, old[:70]))
        s = s.replace(old, new)
    p.write_text(s, encoding='utf-8')
    print('patched', name)


OS_EDITS = [
    ('bool\ndisk_cache_enabled()\n{\n   /* If running as a users other than the real user disable cache */\n   if (!__normal_user())\n      return false;\n',
     'bool\ndisk_cache_enabled()\n{\n   /* If running as a users other than the real user disable cache */\n'
     '#if defined(__PROSPERO__)\n'
     '   /* OMNI_MESA_DISKCACHE_V1: PS5 app processes can run with euid/egid != uid/gid; the cache is our own dir. */\n'
     '   if (!__normal_user()) {\n'
     '      static int said;\n'
     '      if (!said++) fprintf(stderr, "OMNI MESA CACHE: ids differ (uid %d euid %d gid %d egid %d): allowed on PS5\\n",\n'
     '                           (int)getuid(), (int)geteuid(), (int)getgid(), (int)getegid());\n'
     '   }\n'
     '#else\n'
     '   if (!__normal_user())\n      return false;\n'
     '#endif\n', 1),
    ('      int ret = posix_fallocate(fd, 0, size);\n      if (ret != 0) {\n         if (ret == EOPNOTSUPP) {\n            if (ftruncate(fd, size) == -1)\n               goto path_fail;\n         } else {\n            goto path_fail;\n         }\n      }\n',
     '      int ret = posix_fallocate(fd, 0, size);\n      if (ret != 0) {\n'
     '         /* OMNI_MESA_DISKCACHE_V1: any posix_fallocate failure (not only EOPNOTSUPP) falls back to ftruncate */\n'
     '         if (ftruncate(fd, size) == -1) {\n'
     '            fprintf(stderr, "OMNI MESA CACHE: index size: posix_fallocate %d, ftruncate errno %d\\n", ret, errno);\n'
     '            goto path_fail;\n'
     '         }\n'
     '      }\n', 1),
    ('   cache->index_mmap = mmap(NULL, size, PROT_READ | PROT_WRITE,\n                            MAP_SHARED, fd, 0);\n   if (cache->index_mmap == MAP_FAILED)\n      goto path_fail;\n',
     '   cache->index_mmap = mmap(NULL, size, PROT_READ | PROT_WRITE,\n                            MAP_SHARED, fd, 0);\n'
     '   if (cache->index_mmap == MAP_FAILED) {\n'
     '      /* OMNI_MESA_DISKCACHE_V1: a private anonymous index (per process) instead of no cache at all */\n'
     '      int e = errno;\n'
     '      cache->index_mmap = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);\n'
     '      fprintf(stderr, "OMNI MESA CACHE: index mmap(MAP_SHARED) failed (errno %d); %s\\n", e,\n'
     '              cache->index_mmap == MAP_FAILED ? "anonymous index failed too" : "using a private anonymous index");\n'
     '      if (cache->index_mmap == MAP_FAILED)\n'
     '         goto path_fail;\n'
     '   }\n', 1),
]

C_EDITS = [
    # failure reasons in disk_cache_type_create: every 'goto path_fail;' / 'goto fail;' inside it gets a note
    ('disk_cache_type_create(const char *gpu_name,\n',
     '/* OMNI_MESA_DISKCACHE_V1 */\nstatic void omni_dc_note(int line, const char *what) { fprintf(stderr, "OMNI MESA CACHE: off at disk_cache.c:%d (%s, errno %d)\\n", line, what, errno); }\n'
     'disk_cache_type_create(const char *gpu_name,\n', 1),
    ('   if (!disk_cache_enabled())\n      goto path_fail;\n',
     '   if (!disk_cache_enabled()) {\n      omni_dc_note(__LINE__, "disabled");\n      goto path_fail;\n   }\n', 1),
    ('      disk_cache_generate_cache_dir(local, gpu_name, driver_id, cache_dir_name, cache_type, true);\n   if (!path)\n      goto path_fail;\n',
     '      disk_cache_generate_cache_dir(local, gpu_name, driver_id, cache_dir_name, cache_type, true);\n   if (!path) {\n      omni_dc_note(__LINE__, "no cache dir");\n      goto path_fail;\n   }\n', 1),
    ('   if (!disk_cache_mmap_cache_index(local, cache))\n      goto path_fail;\n',
     '   if (!disk_cache_mmap_cache_index(local, cache)) {\n      omni_dc_note(__LINE__, "index");\n      goto path_fail;\n   }\n', 1),
    ('   if (!disk_cache_init_queue(cache))\n      goto fail;\n\n   cache->path_init_failed = false;\n',
     '   if (!disk_cache_init_queue(cache)) {\n      omni_dc_note(__LINE__, "queue");\n      goto fail;\n   }\n\n   cache->path_init_failed = false;\n'
     '   fprintf(stderr, "OMNI MESA CACHE: on %s (type %d, max %llu MB, gpu %s)\\n", cache->path, (int)cache_type,\n'
     '           (unsigned long long)(max_size >> 20), gpu_name ? gpu_name : "?");\n', 1),
]


def put_get_edits(s):
    """Counters in disk_cache_put / disk_cache_get (located by their signatures)."""
    out = []
    a = 'disk_cache_put(struct disk_cache *cache, const cache_key key,\n'
    i = s.index(a)
    j = s.index('{\n', i) + 2
    out.append((s[i:j], s[i:j] + '   { /* OMNI_MESA_DISKCACHE_V1 */ static int n; n++; if (n == 1 || n % 25 == 0) fprintf(stderr, "OMNI MESA CACHE: put #%d\\n", n); }\n', 1))
    return out


s = (root / 'disk_cache_os.c').read_text(encoding='utf-8')
patch('disk_cache_os.c', OS_EDITS)
c = (root / 'disk_cache.c').read_text(encoding='utf-8')
if MARK not in c:
    edits = C_EDITS + put_get_edits(c)
    # gets: wrap the return value of disk_cache_get by renaming it and adding a counting wrapper at the end of the file
    edits.append(('disk_cache_get(struct disk_cache *cache, const cache_key key, size_t *size)\n{',
                  'omni_disk_cache_get_real(struct disk_cache *cache, const cache_key key, size_t *size)\n{', 1))
    patch('disk_cache.c', edits)
    p = root / 'disk_cache.c'
    p.write_text(p.read_text(encoding='utf-8') + '''
/* OMNI_MESA_DISKCACHE_V1: hit/miss counts */
void *
disk_cache_get(struct disk_cache *cache, const cache_key key, size_t *size)
{
   static int gets, hits;
   void *r = omni_disk_cache_get_real(cache, key, size);
   gets++; if (r) hits++;
   if (gets == 10 || gets == 50 || gets == 200) fprintf(stderr, "OMNI MESA CACHE: %d gets, %d hits\\n", gets, hits);
   return r;
}
''', encoding='utf-8')
else:
    print('already disk_cache.c')
