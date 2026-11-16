# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_LIBRARY_V1: Library listing, signed streaming with Range, trash/restore/delete.
Local temp folders only; USB drives are simulated by patching save_places.mounted."""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import files_library  # noqa: E402
import save_places  # noqa: E402
import worker  # noqa: E402

CAN_LINK = hasattr(os, 'symlink')


def symlink(src, dst, directory=False):
    try:
        os.symlink(src, dst, target_is_directory=directory)
        return True
    except (OSError, NotImplementedError):
        return False


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='dl-lib-'))
        self.internal = self.tmp / 'downloads'
        self.saved = self.internal / 'Saved'
        (self.saved / 'Music').mkdir(parents=True)
        self.usb = tuple(str(self.tmp / ('usb%d' % i)) for i in range(8))
        self.outside = self.tmp / 'secret.txt'
        self.outside.write_bytes(b'top secret')
        self.files = {}
        stamp = int(time.time()) - 1000
        for n, (rel, data) in enumerate([('old.mp4', b'v' * 100), ('Music/song.mp3', b'a' * 50), ('doc.pdf', b'%PDF-1.4'),
                                          ('pic.png', b'\x89PNG'), ('notes.bin', b'x'), ('new.webm', bytes(range(256)) * 4)]):
            path = self.saved / rel
            path.write_bytes(data)
            os.utime(path, (stamp + n * 10, stamp + n * 10))
            self.files[rel] = path
        # Never listed: hidden files, work folders, part files, the job folder outside Saved.
        (self.saved / '.hidden.mp4').write_bytes(b'h')
        (self.saved / '.omni-work').mkdir()
        (self.saved / '.omni-work' / 'x.mp4').write_bytes(b'w')
        (self.internal / 'jobkey').mkdir()
        (self.internal / 'jobkey' / 'raw.mp4').write_bytes(b'r')
        self.lib = files_library.Library(self.internal, 'token-abc', self.usb)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def names(self, **kw):
        return [f['name'] for f in self.lib.listing(**kw)['files']]


class Listing(Fixture):
    def test_newest_first_and_only_inside_saved(self):
        self.assertEqual(self.names(), ['new.webm', 'notes.bin', 'pic.png', 'doc.pdf', 'song.mp3', 'old.mp4'])

    def test_filters(self):
        self.assertEqual(self.names(kind='video'), ['new.webm', 'old.mp4'])
        self.assertEqual(self.names(kind='audio'), ['song.mp3'])
        self.assertEqual(self.names(kind='other'), ['notes.bin', 'pic.png', 'doc.pdf'])
        with self.assertRaises(ValueError):
            self.lib.listing(kind='../etc')
        with self.assertRaises(ValueError):
            self.lib.listing(area='/')

    def test_row_fields(self):
        row = next(f for f in self.lib.listing()['files'] if f['name'] == 'song.mp3')
        self.assertEqual((row['folder'], row['place'], row['place_label'], row['size'], row['kind'], row['mime']),
                         ('Music', 'internal', 'Console storage', 50, 'audio', 'audio/mpeg'))
        self.assertRegex(row['id'], r'^[0-9a-f]{32}$')
        self.assertNotIn(str(self.tmp), json.dumps(self.lib.listing()))   # no paths go to the GUI

    def test_paging(self):
        first = self.lib.listing(offset=0, limit=4)
        second = self.lib.listing(offset=4, limit=4)
        self.assertEqual((first['total'], len(first['files']), len(second['files'])), (6, 4, 2))
        self.assertEqual([f['name'] for f in second['files']], ['song.mp3', 'old.mp4'])
        for bad in (dict(limit=0), dict(limit=101), dict(offset=-1), dict(offset='1')):
            with self.assertRaises(ValueError):
                self.lib.listing(**bad)

    def test_ids_are_stable_and_opaque(self):
        a = {f['name']: f['id'] for f in self.lib.listing()['files']}
        b = {f['name']: f['id'] for f in self.lib.listing()['files']}
        self.assertEqual(a, b)
        other = files_library.Library(self.internal, 'another-session', self.usb)
        c = {f['name']: f['id'] for f in other.listing()['files']}
        self.assertTrue(all(a[n] != c[n] for n in a))   # a new session voids old ids
        with self.assertRaises(files_library.NotFound):
            other.resolve(a['old.mp4'])

    def test_job_title_is_attached(self):
        jobs = [dict(id='a' * 16, state='completed', demo=False, filepath=str(self.files['old.mp4']), title='Holiday clip')]
        row = next(f for f in self.lib.listing(jobs=jobs)['files'] if f['name'] == 'old.mp4')
        self.assertEqual(row['job_title'], 'Holiday clip')

    def test_usb_root_only_while_mounted(self):
        usb_root = Path(self.usb[2]) / 'Omni Downloads'
        usb_root.mkdir(parents=True)
        (usb_root / 'film.mkv').write_bytes(b'm')
        self.assertNotIn('film.mkv', self.names())
        with mock.patch.object(save_places, 'mounted', lambda root: root == self.usb[2]):
            row = next(f for f in self.lib.listing()['files'] if f['name'] == 'film.mkv')
            self.assertEqual((row['place'], row['place_label']), ('usb2', 'USB drive 3'))
            fid = row['id']
            self.assertEqual(self.lib.resolve(fid)[0], 'usb2')
        with self.assertRaises(files_library.NotFound):   # drive pulled
            self.lib.resolve(fid)

    def test_missing_saved_folder_lists_nothing(self):
        shutil.rmtree(self.saved)
        self.assertEqual(self.lib.listing()['total'], 0)

    def test_scan_budget_marks_truncated(self):
        with mock.patch.object(files_library, 'MAX_SCAN', 3):
            self.assertTrue(self.lib.listing()['truncated'])


@unittest.skipUnless(CAN_LINK, 'symbolic links unavailable')
class Symlinks(Fixture):
    def test_symlinked_file_and_folder_are_not_listed_or_served(self):
        if not symlink(self.outside, self.saved / 'leak.txt') or not symlink(self.tmp, self.saved / 'up', True):
            self.skipTest('cannot create symbolic links here')
        names = self.names()
        self.assertNotIn('leak.txt', names)
        self.assertFalse(any('secret' in n for n in names))
        # An entry forced into the index still cannot be resolved through a link.
        for rel in ('leak.txt', 'up/secret.txt'):
            fid = self.lib.file_id('internal', 'files', rel)
            with self.assertRaises(files_library.NotFound):
                self.lib.resolve(fid)

    def test_file_swapped_for_a_link_after_listing(self):
        fid = next(f['id'] for f in self.lib.listing()['files'] if f['name'] == 'doc.pdf')
        self.files['doc.pdf'].unlink()
        if not symlink(self.outside, self.files['doc.pdf']):
            self.skipTest('cannot create symbolic links here')
        with self.assertRaises(files_library.NotFound):
            self.lib.open(fid)

    def test_folder_swapped_for_a_link_after_listing(self):
        fid = next(f['id'] for f in self.lib.listing()['files'] if f['name'] == 'song.mp3')
        shutil.rmtree(self.saved / 'Music')
        elsewhere = self.tmp / 'elsewhere'
        elsewhere.mkdir()
        (elsewhere / 'song.mp3').write_bytes(b'not yours')
        if not symlink(elsewhere, self.saved / 'Music', True):
            self.skipTest('cannot create symbolic links here')
        with self.assertRaises(files_library.NotFound):
            self.lib.resolve(fid)

    def test_saved_root_that_is_a_link_is_ignored(self):
        shutil.rmtree(self.saved)
        other = self.tmp / 'other'
        other.mkdir()
        (other / 'x.mp4').write_bytes(b'x')
        if not symlink(other, self.saved, True):
            self.skipTest('cannot create symbolic links here')
        self.assertEqual(self.lib.listing()['total'], 0)


class Traversal(Fixture):
    def test_crafted_index_entries_never_escape(self):
        for rel in ('../secret.txt', '../../secret.txt', '/etc/passwd', 'Music/../../secret.txt', '.omni-work/x.mp4',
                    '.hidden.mp4', '', 'a//b', 'Music\\..\\..\\secret.txt', 'x\0y'):
            fid = self.lib.file_id('internal', 'files', rel)
            with self.assertRaises(files_library.NotFound, msg=rel):
                self.lib.resolve(fid)
        fid = self.lib.file_id('internal', 'trash', '../old.mp4')
        with self.assertRaises(files_library.NotFound):
            self.lib.resolve(fid)

    def test_raw_paths_and_bad_ids_are_refused(self):
        for bad in (str(self.files['old.mp4']), 'old.mp4', '../secret.txt', 'A' * 32, '0' * 31, None, 5, '0' * 32):
            with self.assertRaises(files_library.NotFound, msg=repr(bad)):
                self.lib.resolve(bad)

    def test_job_outside_the_save_roots_is_refused(self):
        job = dict(id='b' * 16, state='completed', demo=False, filepath=str(self.internal / 'jobkey' / 'raw.mp4'))
        with self.assertRaises(files_library.NotFound):
            self.lib.id_for_job(job)
        job['filepath'] = str(self.saved / '..' / 'jobkey' / 'raw.mp4')
        with self.assertRaises(files_library.NotFound):
            self.lib.id_for_job(job)
        for job in (None, dict(state='failed', filepath=str(self.files['old.mp4'])),
                    dict(state='completed', demo=True, filepath=str(self.files['old.mp4']))):
            with self.assertRaises(files_library.NotFound):
                self.lib.id_for_job(job)
        good = dict(state='completed', demo=False, filepath=str(self.files['Music/song.mp3']))
        self.assertEqual(self.lib.describe(self.lib.id_for_job(good))['name'], 'song.mp3')


class Ranges(unittest.TestCase):
    def test_parse_range(self):
        p = files_library.parse_range
        self.assertIsNone(p(None, 100))
        self.assertEqual(p('bytes=0-9', 100), (0, 9))
        self.assertEqual(p('bytes=90-', 100), (90, 99))
        self.assertEqual(p('bytes=90-500', 100), (90, 99))
        self.assertEqual(p('bytes=-10', 100), (90, 99))
        self.assertEqual(p('bytes=-1000', 100), (0, 99))
        self.assertEqual(p('bytes=99-99', 100), (99, 99))
        self.assertEqual(p(' bytes = 5 - 6 ', 100), (5, 6))
        for ignored in ('bytes=0-1,5-6', 'items=0-1', 'bytes=5-2', 'bytes=-', 'bytes=abc', 'bytes=1-2-3', 'bytes=' + '9' * 30 + '-'):
            self.assertIsNone(p(ignored, 100), ignored)
        for unsat in ('bytes=100-', 'bytes=100-200', 'bytes=-0'):
            with self.assertRaises(files_library.Unsatisfiable, msg=unsat):
                p(unsat, 100)
        with self.assertRaises(files_library.Unsatisfiable):
            p('bytes=0-', 0)
        with self.assertRaises(files_library.Unsatisfiable):
            p('bytes=-5', 0)

    def test_open_ended_range_is_capped(self):
        size = files_library.MAX_RANGE_BYTES * 3
        self.assertEqual(files_library.parse_range('bytes=0-', size), (0, files_library.MAX_RANGE_BYTES - 1))
        self.assertEqual(files_library.parse_range('bytes=10-', size), (10, files_library.MAX_RANGE_BYTES + 9))

    def test_kinds(self):
        for name, kind, mime in (('a.MP4', 'video', 'video/mp4'), ('a.webm', 'video', 'video/webm'), ('a.mkv', 'video', 'video/x-matroska'),
                                 ('a.m4a', 'audio', 'audio/mp4'), ('a.mp3', 'audio', 'audio/mpeg'), ('a.pdf', 'pdf', 'application/pdf'),
                                 ('a.png', 'image', 'image/png'), ('a.JPG', 'image', 'image/jpeg'), ('a.svg', 'other', 'application/octet-stream'),
                                 ('a.html', 'other', 'application/octet-stream'), ('noext', 'other', 'application/octet-stream')):
            self.assertEqual(files_library.kind_of(name), (kind, mime), name)

    def test_quote_name(self):
        self.assertEqual(files_library.quote_name('My clip (2).mp4'), 'My%20clip%20%282%29.mp4')
        self.assertNotIn('\r', files_library.quote_name('a\r\nSet-Cookie: x'))
        self.assertEqual(files_library.quote_name('é.mp3'), '%C3%A9.mp3')


class Signatures(Fixture):
    def test_links(self):
        fid = self.lib.listing()['files'][0]['id']
        url, exp = self.lib.link(fid)
        q = dict(part.split('=') for part in url.split('?')[1].split('&'))
        self.assertTrue(self.lib.check_link(q['id'], q['exp'], q['sig']))
        other = self.lib.listing()['files'][1]['id']
        self.assertFalse(self.lib.check_link(other, q['exp'], q['sig']))                     # another file
        self.assertFalse(self.lib.check_link(fid, str(int(q['exp']) + 1), q['sig']))         # exp changed
        self.assertFalse(self.lib.check_link(fid, q['exp'], q['sig'][:-1] + ('0' if q['sig'][-1] != '0' else '1')))
        self.assertFalse(self.lib.check_link(fid, q['exp'], q['sig'].upper()))
        self.assertFalse(self.lib.check_link(fid, '-1', q['sig']))
        self.assertFalse(self.lib.check_link(fid, None, q['sig']))
        self.assertFalse(files_library.Library(self.internal, 'other-token', self.usb).check_link(fid, q['exp'], q['sig']))
        with mock.patch.object(self.lib, 'now', lambda: exp + 1):
            self.assertFalse(self.lib.check_link(fid, q['exp'], q['sig']))                   # expired
        far = int(time.time()) + files_library.LINK_TTL * 10
        self.assertFalse(self.lib.check_link(fid, str(far), self.lib.sign(fid, far)))         # too far ahead


class Trash(Fixture):
    def test_trash_restore_delete(self):
        fid = next(f['id'] for f in self.lib.listing()['files'] if f['name'] == 'song.mp3')
        with self.assertRaises(ValueError):
            self.lib.delete(fid)                                   # not in the trash yet
        self.assertTrue(self.files['Music/song.mp3'].exists())
        tid = self.lib.trash(fid)['id']
        self.assertTrue((self.saved / '.trash' / 'Music' / 'song.mp3').is_file())
        self.assertNotIn('song.mp3', self.names())
        self.assertEqual(self.names(area='trash'), ['song.mp3'])
        with self.assertRaises(files_library.NotFound):
            self.lib.resolve(fid)
        with self.assertRaises(ValueError):
            self.lib.trash(tid)
        rid = self.lib.restore(tid)['id']
        self.assertTrue(self.files['Music/song.mp3'].is_file())
        self.assertFalse((self.saved / '.trash' / 'Music').exists())   # emptied folders are pruned
        self.assertEqual(self.lib.describe(rid)['name'], 'song.mp3')
        tid = self.lib.trash(rid)['id']
        self.assertEqual(self.lib.delete(tid), dict(deleted=True))
        self.assertFalse((self.saved / '.trash' / 'Music' / 'song.mp3').exists())
        self.assertNotIn('song.mp3', self.names() + self.names(area='trash'))

    def test_trash_never_overwrites(self):
        one = next(f['id'] for f in self.lib.listing()['files'] if f['name'] == 'old.mp4')
        self.lib.trash(one)
        self.files['old.mp4'].write_bytes(b'second')
        two = next(f['id'] for f in self.lib.listing()['files'] if f['name'] == 'old.mp4')
        self.lib.trash(two)
        self.assertEqual(sorted(self.names(area='trash')), ['old (2).mp4', 'old.mp4'])
        restored = next(f['id'] for f in self.lib.listing(area='trash')['files'] if f['name'] == 'old.mp4')
        self.files['old.mp4'].write_bytes(b'third')
        self.lib.restore(restored)
        self.assertTrue((self.saved / 'old (2).mp4').exists() and self.files['old.mp4'].read_bytes() == b'third')

    @unittest.skipUnless(CAN_LINK, 'symbolic links unavailable')
    def test_trash_folder_that_is_a_link_is_refused(self):
        if not symlink(self.tmp, self.saved / '.trash', True):
            self.skipTest('cannot create symbolic links here')
        fid = next(f['id'] for f in self.lib.listing()['files'] if f['name'] == 'old.mp4')
        with self.assertRaises(ValueError):
            self.lib.trash(fid)
        self.assertTrue(self.files['old.mp4'].exists())
        self.assertEqual(self.lib.listing(area='trash')['total'], 0)


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='dl-lib-http-'))
        cls.server = worker.make_server(0, cls.tmp, cls.tmp / 'history.json')
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.server.jobs.set_paused(True)
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.saved = self.tmp / 'Saved'
        shutil.rmtree(self.saved, ignore_errors=True)
        (self.saved / 'Clips').mkdir(parents=True)
        self.body = bytes(range(256)) * 40          # 10240 bytes
        (self.saved / 'Clips' / 'clip.mp4').write_bytes(self.body)
        (self.saved / 'tune.m4a').write_bytes(b'm4a!')
        (self.saved / 'empty.txt').write_bytes(b'')
        (self.saved / 'page.html').write_bytes(b'<script>alert(1)</script>')

    def request(self, method, path, body=None, token=True, headers=None, host=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        h = {'Host': host or '127.0.0.1:%d' % self.port}
        if token:
            h['X-Omni-Token'] = self.server.token
        if body is not None:
            body = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, dict((k.lower(), v) for k, v in response.getheaders()), data

    def listing(self, query=''):
        status, _, data = self.request('GET', '/api/files' + query)
        self.assertEqual(status, 200, data)
        return {f['name']: f for f in json.loads(data)['files']}

    def link(self, fid):
        status, _, data = self.request('POST', '/api/files/link', {'id': fid})
        self.assertEqual(status, 200, data)
        return json.loads(data)

    def test_listing_needs_the_token_and_clean_parameters(self):
        self.assertEqual(self.request('GET', '/api/files', token=False)[0], 403)
        self.assertEqual(self.request('GET', '/api/files', host='evil.example')[0], 403)
        for query in ('?path=/etc', '?kind=video&kind=audio', '?offset=-1', '?limit=1000', '?limit=x', '?area=../..', '?kind=exe'):
            self.assertEqual(self.request('GET', '/api/files' + query)[0], 400, query)
        rows = self.listing('?kind=video&limit=10')
        self.assertEqual(list(rows), ['clip.mp4'])
        self.assertEqual(rows['clip.mp4']['folder'], 'Clips')

    def test_link_and_full_stream(self):
        fid = self.listing()['clip.mp4']['id']
        info = self.link(fid)
        self.assertEqual((info['name'], info['kind'], info['mime'], info['size']), ('clip.mp4', 'video', 'video/mp4', len(self.body)))
        self.assertRegex(info['url'], r'^/api/files/stream\?id=[0-9a-f]{32}&exp=\d+&sig=[0-9a-f]{64}$')
        status, h, data = self.request('GET', info['url'], token=False)
        self.assertEqual((status, data, h['content-type'], h['accept-ranges'], h['content-length']),
                         (200, self.body, 'video/mp4', 'bytes', str(len(self.body))))
        self.assertIn('nosniff', h['x-content-type-options'])
        self.assertIn('sandbox', h['content-security-policy'])
        self.assertEqual(h['content-disposition'], "inline; filename*=UTF-8''clip.mp4")

    def test_ranges(self):
        url = self.link(self.listing()['clip.mp4']['id'])['url']
        n = len(self.body)
        status, h, data = self.request('GET', url, token=False, headers={'Range': 'bytes=100-199'})
        self.assertEqual((status, h['content-range'], data), (206, 'bytes 100-199/%d' % n, self.body[100:200]))
        status, h, data = self.request('GET', url, token=False, headers={'Range': 'bytes=-16'})
        self.assertEqual((status, h['content-range'], data), (206, 'bytes %d-%d/%d' % (n - 16, n - 1, n), self.body[-16:]))
        status, h, data = self.request('GET', url, token=False, headers={'Range': 'bytes=10000-'})
        self.assertEqual((status, data), (206, self.body[10000:]))
        status, h, data = self.request('GET', url, token=False, headers={'Range': 'bytes=%d-' % n})
        self.assertEqual((status, h['content-range'], data), (416, 'bytes */%d' % n, b''))
        status, h, data = self.request('GET', url, token=False, headers={'Range': 'bytes=0-1,5-9'})
        self.assertEqual((status, data), (200, self.body))
        with mock.patch.object(files_library, 'MAX_RANGE_BYTES', 1000):
            status, h, data = self.request('GET', url, token=False, headers={'Range': 'bytes=0-'})
        self.assertEqual((status, h['content-range'], len(data)), (206, 'bytes 0-999/%d' % n, 1000))
        with mock.patch.object(files_library, 'CHUNK', 7):
            status, h, data = self.request('GET', url, token=False, headers={'Range': 'bytes=3-5000'})
        self.assertEqual((status, data), (206, self.body[3:5001]))
        status, h, data = self.request('HEAD', url, token=False, headers={'Range': 'bytes=0-9'})
        self.assertEqual((status, h['content-length'], data), (206, '10', b''))

    def test_empty_file(self):
        url = self.link(self.listing()['empty.txt']['id'])['url']
        status, h, data = self.request('GET', url, token=False)
        self.assertEqual((status, h['content-length'], data), (200, '0', b''))
        self.assertEqual(self.request('GET', url, token=False, headers={'Range': 'bytes=0-'})[0], 416)

    def test_stream_refusals(self):
        rows = self.listing()
        fid, other = rows['clip.mp4']['id'], rows['tune.m4a']['id']
        url = self.link(fid)['url']
        q = url.split('?')[1]
        sig = q.split('sig=')[1]
        exp = q.split('exp=')[1].split('&')[0]
        bad = ['/api/files/stream?id=%s' % fid,                                            # no token, no signature
               '/api/files/stream?id=%s&exp=%s&sig=%s' % (other, exp, sig),               # signature of another file
               '/api/files/stream?id=%s&exp=%d&sig=%s' % (fid, int(exp) + 5, sig),        # exp changed
               '/api/files/stream?id=%s&exp=%s&sig=%s' % (fid, exp, '0' * 64),
               url + '&extra=1', url + '&id=' + fid,
               '/api/files/stream?path=/etc/passwd', '/api/files/stream?id=../../secret',
               '/api/files/stream']
        for path in bad:
            self.assertEqual(self.request('GET', path, token=False)[0], 403, path)
        self.assertEqual(self.request('GET', url, token=False, host='attacker.example:%d' % self.port)[0], 403)
        self.assertEqual(self.request('HEAD', url, token=False, host='attacker.example')[0], 404)
        # With the token header, the bare id works (and only a known id).
        status, _, data = self.request('GET', '/api/files/stream?id=%s' % fid)
        self.assertEqual((status, data), (200, self.body))
        self.assertEqual(self.request('GET', '/api/files/stream?id=%s' % ('f' * 32))[0], 404)
        self.assertEqual(self.request('POST', '/api/files/link', {'id': 'f' * 32})[0], 404)
        self.assertEqual(self.request('POST', '/api/files/link', {'path': '/etc/passwd'})[0], 400)
        self.assertEqual(self.request('POST', '/api/files/link', {'id': fid}, token=False)[0], 403)
        # Expired link.
        with mock.patch.object(self.server.library, 'now', lambda: time.time() + files_library.LINK_TTL + 5):
            self.assertEqual(self.request('GET', url, token=False)[0], 403)
        # The file is removed after the link was made.
        (self.saved / 'Clips' / 'clip.mp4').unlink()
        self.assertEqual(self.request('GET', url, token=False)[0], 404)

    def test_html_is_never_served_as_html(self):
        info = self.link(self.listing()['page.html']['id'])
        self.assertEqual(info['kind'], 'other')
        status, h, data = self.request('GET', info['url'], token=False)
        self.assertEqual((status, h['content-type']), (200, 'application/octet-stream'))
        self.assertTrue(h['content-disposition'].startswith('attachment;'))

    def test_trash_flow_over_http(self):
        fid = self.listing()['tune.m4a']['id']
        self.assertEqual(self.request('POST', '/api/files/delete', {'id': fid})[0], 400)       # trash first
        self.assertEqual(self.request('POST', '/api/files/trash', {'id': fid}, token=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/files/trash', {'id': fid, 'path': 'x'})[0], 400)
        status, _, data = self.request('POST', '/api/files/trash', {'id': fid})
        self.assertEqual(status, 200, data)
        self.assertTrue((self.saved / '.trash' / 'tune.m4a').is_file())
        self.assertNotIn('tune.m4a', self.listing())
        tid = self.listing('?area=trash')['tune.m4a']['id']
        self.assertEqual(self.request('POST', '/api/files/trash', {'id': fid})[0], 404)
        status, _, data = self.request('POST', '/api/files/delete', {'id': tid})
        self.assertEqual((status, json.loads(data)), (200, {'deleted': True}))
        self.assertFalse((self.saved / '.trash' / 'tune.m4a').exists())
        self.assertEqual(self.listing('?area=trash'), {})

    def test_job_link(self):
        key = 'c' * 16
        path = self.saved / 'Clips' / 'clip.mp4'
        with self.server.jobs.lock:
            self.server.jobs.jobs[key] = dict(id=key, state='completed', demo=False, filepath=str(path), title='Clip')
        try:
            status, _, data = self.request('POST', '/api/files/link', {'job': key})
            self.assertEqual(status, 200, data)
            self.assertEqual(json.loads(data)['name'], 'clip.mp4')
            self.assertEqual(self.listing()['clip.mp4']['job_title'], 'Clip')
            with self.server.jobs.lock:
                self.server.jobs.jobs[key]['filepath'] = str(self.tmp / 'history.json')
            self.assertEqual(self.request('POST', '/api/files/link', {'job': key})[0], 404)
            self.assertEqual(self.request('POST', '/api/files/link', {'job': 'd' * 16})[0], 404)
        finally:
            with self.server.jobs.lock:
                del self.server.jobs.jobs[key]

    def test_player_page_and_assets(self):
        status, h, data = self.request('GET', '/player', token=False)
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), data)
        self.assertNotIn(b'__TOKEN__', data)
        self.assertIn("frame-ancestors 'self'", h['content-security-policy'])
        for asset in ('/assets/player.js', '/assets/player.css', '/assets/files-library.js', '/assets/files-library.css'):
            self.assertEqual(self.request('GET', asset, token=False)[0], 200, asset)
        self.assertEqual(self.request('GET', '/player?x=1', token=False)[0], 403)


if __name__ == '__main__':
    unittest.main()
