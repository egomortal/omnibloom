# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_LIBRARY_SEARCH_V1: Library search, sort and type chips (library and the token-protected /api/files)."""
import json
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import files_library  # noqa: E402
import test_files_library as base  # noqa: E402


class Categories(unittest.TestCase):
    def test_category_of(self):
        for name, cat in (('a.MP4', 'video'), ('a.flac', 'audio'), ('a.webp', 'image'), ('a.pdf', 'document'),
                          ('a.srt', 'document'), ('a.DOCX', 'document'), ('a.epub', 'document'), ('a.zip', 'archive'),
                          ('a.7z', 'archive'), ('a.tar.gz', 'archive'), ('a.rar', 'archive'), ('a.bin', 'other'),
                          ('a.html', 'other'), ('noext', 'other'), ('.zip', 'other')):
            self.assertEqual(files_library.category_of(name), cat, name)

    def test_parse_categories(self):
        self.assertEqual(files_library.parse_categories(''), ())
        self.assertEqual(files_library.parse_categories('video,archive'), ('video', 'archive'))
        for bad in ('exe', 'video,', ',video', 'video,video', 'Video', 'video audio', 'x' * 81, None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                files_library.parse_categories(bad)


class LibrarySearch(base.Fixture):
    def setUp(self):
        super().setUp()
        stamp = int(self.files['old.mp4'].stat().st_mtime)
        for n, (rel, data) in enumerate([('Packs/Bundle.ZIP', b'z' * 300), ('Books/Guide.epub', b'e' * 20),
                                          ('backup.tar.gz', b'g' * 7)]):
            path = self.saved / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            os.utime(path, (stamp - 100 - n, stamp - 100 - n))

    def test_defaults_unchanged(self):
        result = self.lib.listing()
        self.assertEqual(self.names()[:6], ['new.webm', 'notes.bin', 'pic.png', 'doc.pdf', 'song.mp3', 'old.mp4'])
        self.assertEqual((result['sort'], result['q'], result['categories']), ('newest', '', []))
        self.assertEqual({f['name']: f['category'] for f in result['files']}['Bundle.ZIP'], 'archive')

    def test_chips(self):
        self.assertEqual(self.names(categories=('image',)), ['pic.png'])
        self.assertEqual(self.names(categories=('document',)), ['doc.pdf', 'Guide.epub'])
        self.assertEqual(self.names(categories=('archive',)), ['Bundle.ZIP', 'backup.tar.gz'])
        self.assertEqual(self.names(categories=('other',)), ['notes.bin'])
        self.assertEqual(self.names(categories=('video', 'audio')), ['new.webm', 'song.mp3', 'old.mp4'])
        self.assertEqual(self.names(categories='image,other'), ['notes.bin', 'pic.png'])
        for bad in (('exe',), 'exe', ('video', 'nope'), 5):
            with self.assertRaises(ValueError):
                self.lib.listing(categories=bad)

    def test_search_name_and_title(self):
        self.assertEqual(self.names(q='SONG'), ['song.mp3'])
        self.assertEqual(self.names(q='  .mp  '), ['song.mp3', 'old.mp4'])   # trimmed, case-insensitive
        self.assertEqual(self.names(q='nothing here'), [])
        jobs = [dict(state='completed', filepath=str(self.files['old.mp4']), title='Holiday Film 2024')]
        self.assertEqual(self.names(q='holiday', jobs=jobs), ['old.mp4'])
        self.assertEqual(self.names(q='Music'), [])    # folder names are not searched
        self.assertEqual(self.names(q='bundle', categories=('video',)), [])
        self.assertEqual(self.names(q='bundle', categories=('archive',)), ['Bundle.ZIP'])
        for bad in ('x' * 101, 'a\nb', 'a\0b', 'a\x7fb', None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.lib.listing(q=bad)
        self.assertEqual(self.lib.listing(q='x' * 100)['total'], 0)

    def test_sorts(self):
        newest = self.names()
        self.assertEqual(self.names(sort='oldest'), newest[::-1])
        self.assertEqual(self.names(sort='name'), ['backup.tar.gz', 'Bundle.ZIP', 'doc.pdf', 'Guide.epub', 'new.webm',
                                                   'notes.bin', 'old.mp4', 'pic.png', 'song.mp3'])
        self.assertEqual(self.names(sort='size'), ['new.webm', 'Bundle.ZIP', 'old.mp4', 'song.mp3', 'Guide.epub',
                                                   'doc.pdf', 'backup.tar.gz', 'pic.png', 'notes.bin'])
        self.assertEqual(self.names(sort='type'), ['old.mp4', 'new.webm', 'song.mp3', 'pic.png', 'Guide.epub', 'doc.pdf',
                                                   'backup.tar.gz', 'Bundle.ZIP', 'notes.bin'])
        for bad in ('largest', '', None, 'NAME'):
            with self.assertRaises(ValueError):
                self.lib.listing(sort=bad)

    def test_paging_follows_the_sort_and_filter(self):
        first = self.lib.listing(sort='name', limit=2)
        second = self.lib.listing(sort='name', limit=2, offset=2)
        self.assertEqual([f['name'] for f in first['files'] + second['files']],
                         ['backup.tar.gz', 'Bundle.ZIP', 'doc.pdf', 'Guide.epub'])
        self.assertEqual(self.lib.listing(categories=('archive', 'document'), limit=1)['total'], 4)

    def test_trash_area_is_searched_too(self):
        fid = next(f['id'] for f in self.lib.listing()['files'] if f['name'] == 'Bundle.ZIP')
        self.lib.trash(fid)
        self.assertEqual(self.names(area='trash', q='bund', categories=('archive',)), ['Bundle.ZIP'])
        self.assertEqual(self.names(q='bund'), [])


class RouteSearch(unittest.TestCase):
    # The real worker, as in test_files_library.Http (its helpers reused; its own tests stay there).
    setUpClass = classmethod(base.Http.setUpClass.__func__)
    tearDownClass = classmethod(base.Http.tearDownClass.__func__)
    request = base.Http.request
    listing = base.Http.listing

    def setUp(self):
        base.Http.setUp(self)
        (self.saved / 'Pack.zip').write_bytes(b'z' * 5000)
        (self.saved / 'Ünïcode Song.mp3').write_bytes(b'u' * 2)

    def test_query_values(self):
        self.assertEqual(list(self.listing('?cats=archive')), ['Pack.zip'])
        self.assertEqual(list(self.listing('?cats=audio,archive&sort=name')), ['Pack.zip', 'tune.m4a', 'Ünïcode Song.mp3'])
        self.assertEqual(list(self.listing('?sort=size&limit=2')), ['clip.mp4', 'Pack.zip'])
        self.assertEqual(list(self.listing('?q=' + quote('ÜNÏCODE s'))), ['Ünïcode Song.mp3'])
        self.assertEqual(list(self.listing('?q=&cats=&sort=newest')), list(self.listing()))
        rows = self.listing('?cats=document')
        self.assertEqual(sorted(rows), ['empty.txt'])
        self.assertEqual(rows['empty.txt']['category'], 'document')
        self.assertEqual(self.listing('?q=pack&area=trash'), {})

    def test_bad_query_values_and_token(self):
        self.assertEqual(self.request('GET', '/api/files?q=pack', token=False)[0], 403)
        self.assertEqual(self.request('GET', '/api/files?sort=name', host='evil.example')[0], 403)
        for query in ('?cats=exe', '?cats=video&cats=audio', '?cats=video,video', '?sort=largest', '?sort=name&sort=size',
                      '?q=' + 'x' * 101, '?q=a%0Ab', '?q=a%00b', '?path=/etc&q=a', '?cats=..%2F..'):
            status, _, data = self.request('GET', '/api/files' + query)
            self.assertEqual(status, 400, query)
            self.assertIn('error', json.loads(data))


if __name__ == '__main__':
    unittest.main()
