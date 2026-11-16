# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_ALREADY_V1 (D10): "Already in the Library" fingerprints and the POST /api/library/check route.

Run: python -m unittest tests/test_library_seen.py   (from the downloads folder)
"""
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import library_seen  # noqa: E402
import worker  # noqa: E402

ID = 'dQw4w9WgXcQ'


class Identity(unittest.TestCase):
    def test_youtube_forms_share_one_identity(self):
        forms = ['https://www.youtube.com/watch?v=%s' % ID, 'https://youtube.com/watch?feature=share&v=%s&t=42' % ID,
                 'https://m.youtube.com/watch?v=%s' % ID, 'https://youtu.be/%s?si=abc' % ID,
                 'https://www.youtube.com/shorts/%s' % ID, 'https://www.youtube-nocookie.com/embed/%s' % ID,
                 'https://music.youtube.com/watch?v=%s&list=x' % ID]
        self.assertEqual({library_seen.identity(u) for u in forms}, {'yt:' + ID})

    def test_other_addresses_drop_tracking_order_www_and_fragment(self):
        a = library_seen.identity('https://www.example.com/v/clip.mp4?b=2&utm_source=x&a=1#t=3')
        b = library_seen.identity('http://example.com/v/clip.mp4?a=1&b=2&fbclid=zz')
        self.assertEqual(a, b)
        self.assertNotEqual(a, library_seen.identity('https://example.com/v/clip.mp4?a=1&b=3'))
        self.assertNotEqual(a, library_seen.identity('https://example.com:8443/v/clip.mp4?a=1&b=2'))

    def test_look_alikes_and_junk(self):
        self.assertTrue(library_seen.identity('https://youtube.com.evil.example/watch?v=%s' % ID).startswith('u:'))
        self.assertTrue(library_seen.identity('https://www.youtube.com/watch?v=short').startswith('u:'))
        for bad in (None, 5, '', 'ftp://x/y', 'javascript:alert(1)', 'https://', 'https://x/' + 'a' * 5000):
            self.assertIsNone(library_seen.identity(bad))


class SeenStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='dl-seen-'))
        self.path = self.tmp / 'library-seen.json'
        self.files = set()
        self.seen = library_seen.Seen(self.path, exists=lambda f: f in self.files)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_record_then_check_and_audio_is_separate(self):
        url = 'https://youtu.be/%s' % ID
        self.files.add('/data/Saved/Song.mp4')
        self.assertTrue(self.seen.record(url, False, '/data/Saved/Song.mp4'))
        self.assertEqual(self.seen.check('https://www.youtube.com/watch?v=%s' % ID, False), {'already': True, 'name': 'Song.mp4'})
        self.assertEqual(self.seen.check(url, True), {'already': False, 'name': ''})

    def test_no_address_on_disk_and_key_survives_reload(self):
        url = 'https://example.com/private/talk.mp4?token=zzsecretzz'
        self.files.add('/data/Saved/talk.mp4')
        self.seen.record(url, False, '/data/Saved/talk.mp4')
        raw = self.path.read_text('utf-8')
        for leak in ('example.com', 'talk.mp4?token', 'zzsecretzz', 'private'):   # never hex-only words: the stored key is hex
            self.assertNotIn(leak, raw.replace('/data/Saved/talk.mp4', ''))
        again = library_seen.Seen(self.path, exists=lambda f: f in self.files)
        self.assertEqual(again.check(url, False)['already'], True)

    def test_missing_file_is_forgotten(self):
        url = 'https://example.com/a.mp4'
        self.seen.record(url, False, '/data/Saved/a.mp4')   # not in self.files
        self.assertEqual(self.seen.check(url, False), {'already': False, 'name': ''})
        self.assertEqual(json.loads(self.path.read_text('utf-8'))['items'], {})

    def test_cap_drops_the_oldest(self):
        t = [0]
        seen = library_seen.Seen(self.path, exists=lambda f: True, clock=lambda: t[0])
        for n in range(library_seen.MAX_ITEMS + 5):
            t[0] = n
            seen.record('https://example.com/%d.mp4' % n, False, '/f/%d.mp4' % n)
        self.assertEqual(len(seen.items), library_seen.MAX_ITEMS)
        self.assertFalse(seen.check('https://example.com/0.mp4', False)['already'])
        self.assertTrue(seen.check('https://example.com/%d.mp4' % (library_seen.MAX_ITEMS + 4), False)['already'])

    def test_corrupt_store_starts_fresh(self):
        self.path.write_text('{not json', 'utf-8')
        fresh = library_seen.Seen(self.path)
        self.assertEqual(fresh.items, {})
        self.assertEqual(fresh.check('https://example.com/a.mp4', False)['already'], False)

    def test_bad_inputs(self):
        self.assertFalse(self.seen.record('ftp://x/y', False, '/f'))
        self.assertFalse(self.seen.record('https://example.com/a', 'yes', '/f'))
        self.assertFalse(self.seen.record('https://example.com/a', False, ''))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dl-seen-api-')
        cls.server = worker.make_server(0, cls.tmp, Path(cls.tmp) / 'history.json')
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def request(self, path, body, token=True):
        port = self.server.server_port
        headers = {'Content-Type': 'application/json', 'Host': '127.0.0.1:%d' % port}
        if token:
            headers['X-Omni-Token'] = self.server.token
        request = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), data=json.dumps(body).encode(),
                                         headers=headers, method='POST')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_check_route(self):
        saved = Path(self.tmp) / 'Film.mp4'
        saved.write_bytes(b'x')
        self.server.jobs.seen.record('https://youtu.be/%s' % ID, False, str(saved))
        self.assertEqual(self.request('/api/library/check', {'url': 'https://www.youtube.com/watch?v=%s' % ID, 'audio': False}),
                         (200, {'already': True, 'name': 'Film.mp4'}))
        self.assertEqual(self.request('/api/library/check', {'url': 'https://example.com/other.mp4', 'audio': False}),
                         (200, {'already': False, 'name': ''}))
        self.assertEqual(self.request('/api/library/check', {'url': 'https://youtu.be/%s' % ID, 'audio': False}, token=False)[0], 403)
        for body in ({'url': 'https://example.com/a'}, {'url': 'https://example.com/a', 'audio': 'no'},
                     {'url': 'ftp://x/y', 'audio': False}, {'url': 'https://example.com/a', 'audio': False, 'x': 1}):
            self.assertEqual(self.request('/api/library/check', body)[0], 400, body)


if __name__ == '__main__':
    unittest.main()
