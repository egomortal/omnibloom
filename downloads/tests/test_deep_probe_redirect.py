"""Audit DW-01 regression (GPL-3.0-or-later): the deep probe (probe.site_probe ->
real yt-dlp) must not follow a redirect from an allowed host to a refused one.

'localhost' stands in for a public site (the test resolver allows it); the
literal 127.0.0.1 stands in for a LAN/console address (refused). Before the fix
yt-dlp follows the 302 straight to /secret; after it, the egress guard refuses
the hop and /secret is never requested. Skipped where yt-dlp isn't installed.
"""
import http.server
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
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
        HITS.append(self.path)
        if self.path == '/page':
            self.send_response(302)
            self.send_header('Location', 'http://127.0.0.1:%d/secret' % self.server.server_port)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        body = b'<html><body><video src="/v.mp4"></video></body></html>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_resolver(host, port):
    if host == 'localhost':
        return (socket.AF_INET, '127.0.0.1', port)
    raise probe.Refused('Local or private address')


@unittest.skipIf(yt_dlp is None, 'yt-dlp not installed')
class DeepProbeRedirect(unittest.TestCase):
    def test_redirect_to_refused_address_is_not_followed(self):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        saved = probe.public_address
        probe.public_address = test_resolver
        guard_module = sys.modules.get('egress_guard')
        if guard_module is not None:
            guard_module._guard = None          # a fresh guard that uses the test resolver
        try:
            try:
                probe.site_probe('http://localhost:%d/page' % server.server_port,
                                 adapter_options={'socket_timeout': 5})
            except Exception:  # noqa: BLE001 - yt-dlp reports the refused hop as an error
                pass
            self.assertIn('/page', HITS)
            self.assertNotIn('/secret', HITS)
        finally:
            probe.public_address = saved
            if guard_module is not None and guard_module._guard is not None:
                guard_module._guard.close()
                guard_module._guard = None
            server.shutdown()


if __name__ == '__main__':
    unittest.main()
