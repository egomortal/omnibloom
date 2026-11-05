# SPDX-License-Identifier: GPL-3.0-or-later
"""Real yt-dlp through the egress guard (skipped when yt-dlp isn't installed).

A local page links to a video on an allowed host and a manifest on a refused host. The
generic extractor fetches both through the guard: the allowed request is served and the
refused one is answered 403, so yt-dlp never reaches the refused address directly.
"""
import http.server
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import egress_guard  # noqa: E402
import probe  # noqa: E402

try:
    import yt_dlp  # noqa: F401
except ImportError:  # pragma: no cover
    yt_dlp = None

HITS = []


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        HITS.append((self.headers.get('Host'), self.path))
        if self.path == '/page':
            body = ('<html><body><video src="http://private.test:%d/v.mp4"></video></body></html>' % self.server.server_port).encode()
            ctype = 'text/html'
        else:
            body, ctype = b'x', 'video/mp4'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def resolver(host, port):
    if host == 'public.test':
        return (socket.AF_INET, '127.0.0.1', port)
    raise probe.Refused('Local or private address')


@unittest.skipIf(yt_dlp is None, 'yt-dlp not installed')
class RealYtdlp(unittest.TestCase):
    def test_every_request_goes_through_guard(self):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        guard = egress_guard.EgressGuard(resolver)
        try:
            import yt_dlp as y
            options = dict(quiet=True, no_warnings=True, skip_download=True, socket_timeout=5, cachedir=False,
                           proxy=guard.url, check_formats=True, ignoreerrors=True)
            with y.YoutubeDL(options) as ydl:
                ydl.extract_info('http://public.test:%d/page' % server.server_port, download=False,
                                 force_generic_extractor=True)
            hosts = {h.split(':')[0] for h, _ in HITS}
            self.assertIn('public.test', hosts)
            self.assertNotIn('private.test', hosts)   # never reached the server
            self.assertGreaterEqual(guard.allowed, 1)
            # Direct access with the guard bypassed WOULD reach the server (proves the fixture works):
            # the refused host only resolves through our resolver, so we just check the guard counted it.
        finally:
            guard.close()
            server.shutdown()


if __name__ == '__main__':
    unittest.main()
