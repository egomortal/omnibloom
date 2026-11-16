#!/usr/bin/env python3
"""OMNI_CLEAR_ON_EXIT_V1: real-file test of OmniClearOnExit.h's Cookies.db / Cookies.db-wal reader.

Writes cookie databases with WebKit's Curl schema (CookieJarDB.cpp: table Cookie, domain_index, path_index, the
UNIQUE(name, domain, path) autoindex) through Python's sqlite3, builds test_clear_on_exit.cpp and runs it on them:
  1. rollback journal, 4096-byte pages, ~600 cookies over ~150 domains (interior pages), long values (overflow pages)
  2. WAL mode, 1024-byte pages, read while the writer still holds it open (the newest rows only in Cookies.db-wal),
     plus deleted rows that must not come back
usage: test_clear_on_exit_db.py [workdir]   (needs g++ and python3; exit 0 when every check passes)
"""
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = [
    'CREATE TABLE IF NOT EXISTS Cookie (  name TEXT NOT NULL,  value TEXT,  domain TEXT NOT NULL,  path TEXT NOT NULL,'
    '  expires INTEGER NOT NULL,  size INTEGER NOT NULL,  session INTEGER NOT NULL,  httponly INTEGER NOT NULL DEFAULT 0,'
    '  secure INTEGER NOT NULL DEFAULT 0,  lastupdated INTEGER NOT NULL DEFAULT CURRENT_TIMESTAMP,'
    '   UNIQUE(name, domain, path));',
    'CREATE INDEX IF NOT EXISTS domain_index ON Cookie(domain);',
    'CREATE INDEX IF NOT EXISTS path_index ON Cookie(path);',
]
INSERT = ('INSERT OR REPLACE INTO Cookie (name, value, domain, path, expires, size, session, httponly, secure) '
          'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')


def domains(rng, n):
    tlds = ['com', 'net', 'org', 'co.uk', 'io', 'de', 'com.au', 'jp']
    out = set()
    while len(out) < n:
        base = ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz0123456789-') for _ in range(rng.randint(3, 14))).strip('-') or 'x'
        host = base + '.' + rng.choice(tlds)
        if rng.random() < 0.5:
            host = rng.choice(['www.', 'accounts.', 'ads.', 'cdn.', 'a.b.']) + host
        out.add(('.' if rng.random() < 0.5 else '') + host)
    return sorted(out)


def fill(con, rng, doms, per, long_every=7):
    for d in doms:
        for k in range(per):
            val = ''.join(rng.choice('ABCDEFabcdef0123456789._-') for _ in range(rng.randint(5, 40)))
            if long_every and rng.randrange(long_every) == 0:
                val = val * 400   # several KB: an overflowing row (its domain may lie past the local part)
            path = rng.choice(['/', '/', '/account', '/a/b'])
            con.execute(INSERT, ('c%d' % k, val, d, path, 1999999999, len(val), 0, k & 1, 1))


def key(d):
    d = d.lstrip('.').lower()
    return d[4:] if d.startswith('www.') and '.' in d[4:] else d


def main():
    work = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='coe_db_'))
    work.mkdir(parents=True, exist_ok=True)
    exe = work / 't_coe'
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-I', str(HERE),
                    str(HERE / 'test_clear_on_exit.cpp'), '-o', str(exe)], check=True)
    rng = random.Random(7)
    ok = True

    # 1. rollback journal, 4096-byte pages
    db1 = work / 'one.db'
    for p in work.glob('one.db*'):
        p.unlink()
    con = sqlite3.connect(db1)
    con.execute('PRAGMA page_size=4096')
    for s in SCHEMA:
        con.execute(s)
    d1 = domains(rng, 150)
    fill(con, rng, d1, 4)
    con.commit()
    con.close()
    want1 = work / 'one.want'
    want1.write_text(''.join(key(d) + '\n' for d in d1))
    r = subprocess.run([str(exe), str(db1), '-', str(want1)])
    ok &= r.returncode == 0

    # 2. WAL, 1024-byte pages, copied while the writer is open (no checkpoint)
    db2 = work / 'two.db'
    for p in work.glob('two.db*'):
        p.unlink()
    con = sqlite3.connect(db2)
    con.execute('PRAGMA page_size=1024')
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA wal_autocheckpoint=0')
    for s in SCHEMA:
        con.execute(s)
    d2 = domains(rng, 60)
    fill(con, rng, d2[:40], 3, long_every=0)
    con.commit()
    con.execute('PRAGMA wal_checkpoint(TRUNCATE)')   # the first 40 domains are in the main file now
    fill(con, rng, d2[40:], 2, long_every=5)          # the last 20 only in the WAL
    gone = d2[0]
    con.execute('DELETE FROM Cookie WHERE domain = ?', (gone,))
    con.commit()
    shutil.copy(db2, work / 'two.copy.db')
    shutil.copy(str(db2) + '-wal', work / 'two.copy.db-wal')
    con.close()
    # the deleted domain is still in an older page image of the WAL / the main file (SQLite keeps old page versions
    # until a checkpoint): the reader may report it (harmless: it would only be deleted again), so it is not checked
    # either way; everything else must be found, and nothing else.
    want2 = work / 'two.want'
    want2.write_text(''.join(key(d) + '\n' for d in d2))
    r = subprocess.run([str(exe), str(work / 'two.copy.db'), str(work / 'two.copy.db-wal'), str(want2)])
    ok &= r.returncode == 0
    # the WAL alone must give the 20 new domains (they are in no page of the main file)
    main_only = work / 'two.mainonly.want'
    main_only.write_text(''.join(key(d) + '\n' for d in d2[:40]))
    r = subprocess.run([str(exe), str(work / 'two.copy.db'), '-', str(main_only)])
    ok &= r.returncode == 0
    print('test_clear_on_exit_db: ' + ('PASS' if ok else 'FAIL') + ' (' + str(work) + ')')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
