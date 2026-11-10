# SPDX-License-Identifier: GPL-3.0-or-later
"""downloader-8 (OMNI_EGRESS_GUARD_V2): the DOWNLOAD itself is confined to public addresses, not only the
deep check. Local fixtures only, no outside network.

'localhost' stands in for a public site (the test resolver allows it and serves it from 127.0.0.1);
the literal 127.0.0.1 stands in for a LAN/console address (refused, as probe.public_address refuses
private and loopback addresses). A test passes only if the refused address is never requested.

Run from a tree with the downloader-5 console-snapshot + downloader-7 worker + this adapters.py in
worker/:  python -m unittest tests/test_download_egress.py
"""
import http.server
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import adapters  # noqa: E402
import egress_guard  # noqa: E402
import probe  # noqa: E402

try:
    import yt_dlp  # noqa: F401
except ImportError:  # pragma: no cover
    yt_dlp = None

HITS = []
MEDIA = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 4000          # enough of an MP4 for the generic extractor
LOOKUPS = {}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _send(self, code, body=b'', kind='application/octet-stream', extra=()):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        HITS.append(self.path)
        port = self.server.server_port
        secret = 'http://127.0.0.1:%d/secret' % port
        if self.path.startswith('/secret'):
            return self._send(200, b'LAN SECRET ' * 100)
        if self.path == '/redirect-to-lan.mp4':
            return self._send(302, extra=[('Location', secret + '.mp4')])
        if self.path == '/page':
            return self._send(302, extra=[('Location', secret + '-page')])
        if self.path == '/video.mp4':
            return self._send(200, MEDIA, 'video/mp4')
        if self.path == '/file.bin':
            return self._send(200, b'public file ' * 50)
        if self.path == '/lan.m3u8':
            body = ('#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXT-X-MEDIA-SEQUENCE:0\n'
                    '#EXTINF:4.0,\n%s-seg0.ts\n#EXT-X-ENDLIST\n' % secret).encode()
            return self._send(200, body, 'application/vnd.apple.mpegurl')
        return self._send(404)


def resolver(host, port):
    """Allows 'localhost' (served locally) and 'flip.test' on its first lookup only; refuses the rest."""
    LOOKUPS[host] = LOOKUPS.get(host, 0) + 1
    if host == 'localhost' or (host == 'flip.test' and LOOKUPS[host] == 1):
        return (socket.AF_INET, '127.0.0.1', port)
    raise probe.Refused('Local or private address')


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_port
        cls.saved = probe.public_address
        probe.public_address = resolver
        egress_guard._guard = None                  # a fresh guard that uses the test resolver

    @classmethod
    def tearDownClass(cls):
        probe.public_address = cls.saved
        if egress_guard._guard is not None:
            egress_guard._guard.close()
            egress_guard._guard = None
        cls.server.shutdown()

    def setUp(self):
        HITS.clear()
        LOOKUPS.clear()
        self.folder = tempfile.mkdtemp(prefix='dl8-')

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def url(self, path, host='localhost'):
        return 'http://%s:%d%s' % (host, self.port, path)

    def assert_lan_untouched(self):
        self.assertFalse([h for h in HITS if h.startswith('/secret')], 'a refused address was requested: %s' % HITS)


class Options(Base):
    def test_every_ytdlp_download_goes_through_the_guard(self):
        opts = adapters.PythonYtdlpAdapter().options(self.folder, False, lambda _: None, referer='https://example.org/')
        self.assertEqual(opts['proxy'], egress_guard._guard.url)
        self.assertIsNone(opts['geo_verification_proxy'])
        self.assertEqual(opts['http_headers'], {'Referer': 'https://example.org/'})

    def test_per_request_proxy_header_is_dropped(self):
        opts = adapters.guard_options({'http_headers': {'Ytdl-Request-Proxy': 'http://10.0.0.1:3128', 'X': '1'}})
        self.assertEqual(opts['http_headers'], {'X': '1'})


class DirectFile(Base):
    def test_public_file_still_downloads(self):
        out = adapters.DirectFileAdapter().download(self.url('/file.bin'), self.folder)
        self.assertEqual(Path(out['filepath']).read_bytes(), b'public file ' * 50)

    def test_private_link_is_refused_before_any_request(self):
        with self.assertRaises(adapters.NoFallback) as ctx:
            adapters.DirectFileAdapter().download(self.url('/secret.bin', host='127.0.0.1'), self.folder)
        self.assertEqual(str(ctx.exception), adapters.PRIVATE_LINK)
        self.assertEqual(HITS, [])

    def test_redirect_into_the_lan_is_not_followed(self):
        with self.assertRaises(Exception):
            adapters.DirectFileAdapter().download(self.url('/redirect-to-lan.mp4'), self.folder)
        self.assertIn('/redirect-to-lan.mp4', HITS)
        self.assert_lan_untouched()
        self.assertEqual(os.listdir(self.folder), [])

    def test_dns_switch_after_the_check_is_caught_by_the_guard(self):
        """flip.test is public on the first lookup (the up-front check) and private after that: the guard
        does its own lookup and refuses, so nothing is fetched."""
        with self.assertRaises(Exception):
            adapters.DirectFileAdapter().download(self.url('/file.bin', host='flip.test'), self.folder)
        self.assertGreaterEqual(LOOKUPS.get('flip.test', 0), 2)
        self.assertEqual(HITS, [])


@unittest.skipIf(yt_dlp is None, 'yt-dlp not installed')
class YtDlpDownload(Base):
    def download(self, path, host='localhost'):
        return adapters.PythonYtdlpAdapter().download(self.url(path, host), self.folder)

    def test_public_media_still_downloads_through_the_guard(self):
        before = egress_guard._guard.allowed if egress_guard._guard else 0
        result = self.download('/video.mp4')
        files = [f for f in os.listdir(self.folder) if not f.endswith('.part')]
        self.assertTrue(files, result)
        self.assertEqual((Path(self.folder) / files[0]).read_bytes(), MEDIA)
        self.assertGreater(egress_guard._guard.allowed, before, 'the download went through the guard')

    def test_private_link_is_refused_before_any_request(self):
        with self.assertRaises(adapters.NoFallback):
            self.download('/secret.mp4', host='127.0.0.1')
        self.assertEqual(HITS, [])

    def test_redirect_into_the_lan_is_not_followed(self):
        with self.assertRaises(Exception):
            self.download('/page')
        self.assertIn('/page', HITS)
        self.assert_lan_untouched()

    def test_media_redirect_into_the_lan_is_not_followed(self):
        with self.assertRaises(Exception):
            self.download('/redirect-to-lan.mp4')
        self.assert_lan_untouched()

    def test_hls_segment_on_a_lan_address_is_not_fetched(self):
        with self.assertRaises(Exception):
            self.download('/lan.m3u8')
        self.assertIn('/lan.m3u8', HITS)
        self.assert_lan_untouched()


if __name__ == '__main__':
    unittest.main()
