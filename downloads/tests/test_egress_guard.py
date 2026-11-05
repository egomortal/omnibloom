# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_EGRESS_GUARD_V1 tests (audit DW-01/DW-02): local fixtures only, no outside network.

Run: python3 -m unittest tests/test_egress_guard.py   (from the downloader-6 folder)
"""
import http.server
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import egress_guard  # noqa: E402
import probe  # noqa: E402


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == '/redirect-private':
            self.send_response(302)
            self.send_header('Location', 'http://private.test:%d/secret' % self.server.server_port)
            self.end_headers()
            return
        body = ('ok ' + self.path + ' host=' + (self.headers.get('Host') or '') +
                ' proxyconn=' + str(self.headers.get('Proxy-Connection'))).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def fake_resolver(host, port):
    """'public.test' stands in for a public site (served locally); everything else is refused
    the way probe.public_address refuses private/loopback addresses."""
    if host == 'public.test':
        return (socket.AF_INET, '127.0.0.1', port)
    if host == 'slow.test':
        time.sleep(5)
    raise probe.Refused('Local or private address')


class GuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_port
        cls.guard = egress_guard.EgressGuard(fake_resolver, resolve_timeout=1.0)

    @classmethod
    def tearDownClass(cls):
        cls.guard.close()
        cls.server.shutdown()

    def opener(self):
        return urllib.request.build_opener(urllib.request.ProxyHandler({'http': self.guard.url, 'https': self.guard.url}))

    def test_allowed_host_pinned_and_hop_headers_stripped(self):
        body = self.opener().open('http://public.test:%d/hello' % self.port, timeout=5).read().decode()
        self.assertTrue(body.startswith('ok /hello'))
        self.assertIn('host=public.test', body)
        self.assertIn('proxyconn=None', body)

    def test_private_host_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.opener().open('http://private.test:%d/secret' % self.port, timeout=5)
        self.assertEqual(caught.exception.code, 403)

    def test_redirect_to_private_refused_on_the_hop(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.opener().open('http://public.test:%d/redirect-private' % self.port, timeout=5)
        self.assertEqual(caught.exception.code, 403)

    def test_connect_tunnel_checked(self):
        for host, expect in (('private.test', b'403'), ('127.0.0.1', b'403'), ('public.test', b'200')):
            s = socket.create_connection(('127.0.0.1', self.guard.port), 5)
            s.sendall(('CONNECT %s:%d HTTP/1.1\r\nHost: x\r\n\r\n' % (host, self.port)).encode())
            line = s.recv(64)
            s.close()
            self.assertIn(expect, line.split(b'\r\n')[0], host)

    def test_resolver_deadline(self):
        start = time.monotonic()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.opener().open('http://slow.test:%d/' % self.port, timeout=8)
        self.assertEqual(caught.exception.code, 504)
        self.assertLess(time.monotonic() - start, 4)

    def test_https_absolute_form_rejected(self):
        s = socket.create_connection(('127.0.0.1', self.guard.port), 5)
        s.sendall(b'GET https://public.test/ HTTP/1.1\r\nHost: public.test\r\n\r\n')
        self.assertIn(b'400', s.recv(64))
        s.close()

    def test_oversized_head_closed(self):
        s = socket.create_connection(('127.0.0.1', self.guard.port), 5)
        try:
            s.sendall(b'GET http://public.test/ HTTP/1.1\r\n' + b'X: ' + b'a' * 70000 + b'\r\n\r\n')
            data = s.recv(64)
        except OSError:
            data = b''
        s.close()
        self.assertNotIn(b'200', data)

    def test_resolve_within(self):
        self.assertEqual(egress_guard.resolve_within(lambda h, p: (1, 'x', p), 'h', 5, 1)[2], 5)
        with self.assertRaises(TimeoutError):
            egress_guard.resolve_within(lambda h, p: time.sleep(3), 'h', 5, 0.3)

    def test_site_probe_always_sets_guard_proxy(self):
        seen = {}

        class FakeYDL:
            def __init__(self, options):
                seen.update(options)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download=False):
                return None
        fake = type(sys)('yt_dlp')
        fake.YoutubeDL = FakeYDL
        sys.modules['yt_dlp'] = fake
        try:
            probe.site_probe('https://example.com/v', adapter_options={'proxy': ''})
        finally:
            del sys.modules['yt_dlp']
        self.assertTrue(seen.get('proxy', '').startswith('http://127.0.0.1:'))

    def test_site_probe_drops_per_request_proxy_overrides(self):
        # yt-dlp's geo verification proxy / Ytdl-Request-Proxy header replace the
        # global proxy for a request, so they must never reach YoutubeDL.
        seen = {}

        class FakeYDL:
            def __init__(self, options):
                seen.update(options)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download=False):
                return None
        fake = type(sys)('yt_dlp')
        fake.YoutubeDL = FakeYDL
        saved = sys.modules.get('yt_dlp')
        sys.modules['yt_dlp'] = fake
        try:
            probe.site_probe('https://example.com/v', adapter_options={
                'geo_verification_proxy': 'http://192.168.1.1:3128',
                'http_headers': {'Ytdl-Request-Proxy': 'http://10.0.0.1:1', 'Referer': 'https://example.com/'}})
        finally:
            if saved is None:
                del sys.modules['yt_dlp']
            else:
                sys.modules['yt_dlp'] = saved
        self.assertFalse(seen.get('geo_verification_proxy'))
        self.assertEqual(seen.get('http_headers'), {'Referer': 'https://example.com/'})
        self.assertTrue(seen.get('proxy', '').startswith('http://127.0.0.1:'))


if __name__ == '__main__':
    unittest.main()
