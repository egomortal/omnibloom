"""downloader-5 probe tests: local fixture server, no outside network.

Run: python3 -m unittest tests/test_probe.py   (from the downloader-5 folder)
"""
# dl6 copy: expectations updated for R3-043, which removed the unrestricted /best fallback on purpose.
import http.server
import json
import socket
import struct
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import probe  # noqa: E402


# ---- fixture media ----------------------------------------------------------------------
def box(kind, payload):
    return struct.pack('>I4s', 8 + len(payload), kind.encode()) + payload


def full(kind, version, payload):
    return box(kind, bytes([version, 0, 0, 0]) + payload)


def mp4_moov(duration_s=125, timescale=1000, width=1920, height=1080, video='avc1', audio='mp4a'):
    mvhd = full('mvhd', 0, struct.pack('>IIII', 0, 0, timescale, duration_s * timescale) + bytes(80))
    tkhd = full('tkhd', 0, bytes(72) + struct.pack('>II', width << 16, height << 16))

    def trak(handler, fourcc, with_tkhd):
        stsd = full('stsd', 0, struct.pack('>I', 1) + struct.pack('>I4s', 16, fourcc.encode()) + bytes(8))
        hdlr = full('hdlr', 0, struct.pack('>I4s', 0, handler.encode()) + bytes(12))
        mdia = box('mdia', hdlr + box('minf', box('stbl', stsd)))
        return box('trak', (tkhd if with_tkhd else b'') + mdia)
    return box('moov', mvhd + trak('vide', video, True) + trak('soun', audio, False))


FTYP = box('ftyp', b'isom' + bytes(4) + b'isomavc1')
MDAT = box('mdat', bytes(300 * 1024))
MP4_START = FTYP + mp4_moov() + MDAT
MP4_END = FTYP + MDAT + mp4_moov(duration_s=61, width=1280, height=720)
MP4_ENC = FTYP + mp4_moov(video='encv') + MDAT


def ebml(element_id, payload):
    size = len(payload)
    return element_id + bytes([0x01]) + size.to_bytes(7, 'big') + payload


WEBM = (ebml(b'\x1a\x45\xdf\xa3', ebml(b'\x42\x82', b'webm'))
        + ebml(b'\x18\x53\x80\x67',
               ebml(b'\x15\x49\xa9\x66', ebml(b'\x2a\xd7\xb1', (1_000_000).to_bytes(3, 'big')) + ebml(b'\x44\x89', struct.pack('>f', 90000.0)))
               + ebml(b'\x16\x54\xae\x6b',
                      ebml(b'\xae', ebml(b'\x83', b'\x01') + ebml(b'\x86', b'V_VP9') + ebml(b'\xe0', ebml(b'\xb0', (2560).to_bytes(2, 'big')) + ebml(b'\xba', (1440).to_bytes(2, 'big'))))
                      + ebml(b'\xae', ebml(b'\x83', b'\x02') + ebml(b'\x86', b'A_OPUS')))
               + ebml(b'\x1f\x43\xb6\x75', bytes(64))))

MASTER = """#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",LANGUAGE="en",NAME="English",DEFAULT=YES,URI="a-en.m3u8"
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",LANGUAGE="es",NAME="Espanol",DEFAULT=NO,URI="a-es.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",LANGUAGE="en",NAME="English",URI="s-en.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=6000000,AVERAGE-BANDWIDTH=5000000,RESOLUTION=1920x1080,FRAME-RATE=59.940,CODECS="avc1.640028,mp4a.40.2",AUDIO="aud"
v1080.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720,FRAME-RATE=30.000,CODECS="avc1.64001f,mp4a.40.2",AUDIO="aud"
v720.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=854x480,CODECS="avc1.4d401e,mp4a.40.2",AUDIO="aud"
v480.m3u8
"""
MEDIA = '#EXTM3U\n#EXT-X-TARGETDURATION:6\n' + ''.join('#EXTINF:6.000,\nseg%d.ts\n' % i for i in range(125)) + '#EXT-X-ENDLIST\n'
LIVE = '#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\na.ts\n#EXTINF:6.0,\nb.ts\n'
AES = '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n#EXTINF:10.0,\na.ts\n#EXTINF:10.0,\nb.ts\n#EXT-X-ENDLIST\n'
DRM_MASTER = ('#EXTM3U\n#EXT-X-SESSION-KEY:METHOD=SAMPLE-AES,URI="skd://x",KEYFORMAT="com.apple.streamingkeydelivery"\n'
              '#EXT-X-STREAM-INF:BANDWIDTH=1000,RESOLUTION=640x360\nv.m3u8\n')
MPD = """<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT10M0S">
 <Period>
  <AdaptationSet mimeType="video/mp4" codecs="avc1.640028">
   <Representation id="v1" width="1920" height="1080" frameRate="30000/1001" bandwidth="4000000"/>
   <Representation id="v2" width="1280" height="720" frameRate="30000/1001" bandwidth="2000000"/>
  </AdaptationSet>
  <AdaptationSet mimeType="audio/mp4" lang="en" codecs="mp4a.40.2"><Representation id="a1" bandwidth="128000"/></AdaptationSet>
  <AdaptationSet mimeType="audio/mp4" lang="de" codecs="mp4a.40.2"><Representation id="a2" bandwidth="96000"/></AdaptationSet>
 </Period>
</MPD>"""
MPD_DRM = MPD.replace('<AdaptationSet mimeType="video/mp4" codecs="avc1.640028">',
                      '<AdaptationSet mimeType="video/mp4" codecs="avc1.640028"><ContentProtection schemeIdUri="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"/>')
MPD_LIVE = MPD.replace('type="static"', 'type="dynamic"')


class Fixture(http.server.BaseHTTPRequestHandler):
    routes = {}

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        self.server.seen.append((path, self.headers.get('Referer'), self.headers.get('Range')))
        if path == '/forbidden':
            return self._send(403, b'no', 'text/plain')
        if path == '/gone':
            return self._send(404, b'gone', 'text/plain')
        if path == '/redir-local':
            return self._redirect(f'http://127.0.0.1:{self.server.server_port}/start.mp4')
        if path == '/redir-ok':
            return self._redirect('/start.mp4')
        if path not in self.routes:
            return self._send(404, b'', 'text/plain')
        body, ctype = self.routes[path]
        if isinstance(body, str):
            body = body.encode()
        rng = self.headers.get('Range')
        if rng and rng.startswith('bytes=') and path.endswith(('.mp4', '.webm', '.bin')):
            a, b = rng[6:].split('-', 1)
            a = int(a)
            b = min(int(b) if b else len(body) - 1, len(body) - 1)
            if a >= len(body):
                return self._send(416, b'', ctype)
            self.send_response(206)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Range', f'bytes {a}-{b}/{len(body)}')
            self.send_header('Content-Length', str(b - a + 1))
            self.end_headers()
            return self.wfile.write(body[a:b + 1])
        self._send(200, body, ctype)

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, where):
        self.send_response(302)
        self.send_header('Location', where)
        self.send_header('Content-Length', '0')
        self.end_headers()


Fixture.routes = {
    '/master.m3u8': (MASTER, 'application/vnd.apple.mpegurl'),
    '/v1080.m3u8': (MEDIA, 'application/vnd.apple.mpegurl'),
    '/media.m3u8': (MEDIA, 'application/x-mpegURL'),
    '/live.m3u8': (LIVE, 'application/vnd.apple.mpegurl'),
    '/aes.m3u8': (AES, 'application/vnd.apple.mpegurl'),
    '/drm.m3u8': (DRM_MASTER, 'application/vnd.apple.mpegurl'),
    '/video.mpd': (MPD, 'application/dash+xml'),
    '/drm.mpd': (MPD_DRM, 'application/dash+xml'),
    '/live.mpd': (MPD_LIVE, 'application/dash+xml'),
    '/start.mp4': (MP4_START, 'video/mp4'),
    '/end.mp4': (MP4_END, 'video/mp4'),
    '/enc.mp4': (MP4_ENC, 'video/mp4'),
    '/clip.webm': (WEBM, 'video/webm'),
    '/page.html': ('<!doctype html><html><body>hi</body></html>', 'text/html; charset=utf-8'),
    '/blob.bin': (b'\x00' * 2048, 'application/x-unknown'),
}


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        cls.server.seen = []
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f'http://media.test:{cls.server.server_port}'

        def resolver(host, port):
            if host == 'media.test':
                return (socket.AF_INET, '127.0.0.1', port)
            return probe.public_address(host, port)
        cls.resolver = staticmethod(resolver)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def p(self, path, referer=None):
        return probe.probe_url(self.base + path, referer, resolver=self.resolver)

    def test_hls_master(self):
        r = self.p('/master.m3u8', 'https://site.example/')
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(r['kind'], 'hls')
        self.assertEqual([v['height'] for v in r['variants']], [1080, 720, 480])
        self.assertEqual(r['variants'][0]['fps'], 60)
        self.assertEqual((r['variants'][0]['vcodec'], r['variants'][0]['acodec']), ('H.264', 'AAC'))
        self.assertEqual(r['duration'], 750.0)
        self.assertEqual(r['variants'][0]['size'], 5000000 * 750 // 8)
        self.assertTrue(r['size_estimated'])
        self.assertEqual([t['lang'] for t in r['audio_tracks']], ['en', 'es'])
        self.assertEqual(r['subtitles'][0]['lang'], 'en')
        self.assertIn(('/master.m3u8', 'https://site.example/', 'bytes=0-262143'), self.server.seen)

    def test_hls_media_aes_live_drm(self):
        r = self.p('/media.m3u8')
        self.assertEqual((r['status'], r['duration']), ('ok', 750.0))
        r = self.p('/aes.m3u8')
        self.assertEqual((r['status'], r['encrypted']), ('ok', 'aes-128'))
        self.assertEqual(self.p('/live.m3u8')['status'], 'live')
        r = self.p('/drm.m3u8')
        self.assertEqual((r['status'], r['encrypted']), ('protected', 'drm'))

    def test_dash(self):
        r = self.p('/video.mpd')
        self.assertEqual((r['status'], r['kind'], r['duration']), ('ok', 'dash', 600.0))
        self.assertEqual([v['height'] for v in r['variants']], [1080, 720])
        self.assertEqual(r['variants'][0]['fps'], 30)
        self.assertEqual(sorted(t['lang'] for t in r['audio_tracks']), ['de', 'en'])
        self.assertEqual(r['variants'][0]['size'], (4000000 + 128000) * 600 // 8)
        self.assertEqual(self.p('/drm.mpd')['status'], 'protected')
        self.assertEqual(self.p('/live.mpd')['status'], 'live')

    def test_mp4_moov_at_start_and_end(self):
        r = self.p('/start.mp4')
        self.assertEqual((r['status'], r['container'], r['duration'], r['size']), ('ok', 'MP4', 125.0, len(MP4_START)))
        self.assertEqual((r['video']['width'], r['video']['height'], r['video']['vcodec'], r['audio']['codec']), (1920, 1080, 'H.264', 'AAC'))
        r = self.p('/end.mp4')
        self.assertEqual((r['status'], r['duration'], r['video']['height']), ('ok', 61.0, 720))
        self.assertEqual(self.p('/enc.mp4')['status'], 'protected')

    def test_webm(self):
        r = self.p('/clip.webm')
        self.assertEqual((r['status'], r['container'], r['duration']), ('ok', 'WebM', 90.0))
        self.assertEqual((r['video']['width'], r['video']['height'], r['video']['vcodec'], r['audio']['codec']), (2560, 1440, 'VP9', 'Opus'))

    def test_errors_and_pages(self):
        self.assertEqual(self.p('/forbidden')['status'], 'blocked')
        self.assertEqual(self.p('/gone')['status'], 'dead')
        self.assertEqual(self.p('/page.html')['status'], 'page')
        self.assertEqual(self.p('/blob.bin')['status'], 'unsupported')

    def test_redirects(self):
        self.assertEqual(self.p('/redir-ok')['status'], 'ok')
        self.assertEqual(self.p('/redir-local')['status'], 'refused')

    def test_refuses_local_and_private(self):
        for url in ('http://127.0.0.1/x.mp4', 'http://localhost:9021/', 'http://192.0.2.10:8084/', 'http://10.0.0.1/',
                    'http://169.254.169.254/latest', 'http://[::1]/', 'http://[::ffff:127.0.0.1]/', 'http://100.64.0.1/',
                    'ftp://example.com/x', 'file:///etc/passwd', 'http://user:pw@example.com/'):
            self.assertEqual(probe.probe_url(url)['status'], 'refused', url)

    def test_quality_format(self):
        self.assertIsNone(probe.quality_format(None))
        self.assertEqual(probe.quality_format({'height': 720}), 'bestvideo[height<=720]+bestaudio/best[height<=720]')
        self.assertEqual(probe.quality_format({'height': 1080, 'fps': 60, 'audio_lang': 'es'}),
                         'bestvideo[height<=1080][fps<=61]+bestaudio[language^=es]/bestvideo[height<=1080][fps<=61]+bestaudio/best[height<=1080]')
        self.assertEqual(probe.quality_format({'audio_only': True}), 'bestaudio')
        self.assertEqual(probe.quality_format({'audio_only': True, 'audio_lang': 'en'}), 'bestaudio[language^=en]/bestaudio')
        for bad in ({'height': '720'}, {'height': 0}, {'height': 99999}, {'audio_lang': 'en]+x'}, {'format': 'x'}, {'audio_only': 1}, 'best'):
            with self.assertRaises(ValueError, msg=bad):
                probe.quality_format(bad)

    def test_prober_cache_and_site_states(self):
        calls = []
        prober = probe.Prober(resolver=self.resolver, site=lambda url: calls.append(url) or probe.result('ok', kind='page', source='yt-dlp'))
        a = prober.probe(self.base + '/start.mp4')
        b = prober.probe(self.base + '/start.mp4')
        self.assertEqual(a['status'], 'ok')
        self.assertTrue(b.get('cached'))
        self.assertEqual(prober.probe('http://127.0.0.1/', deep=True)['status'], 'refused')
        r = prober.probe(self.base + '/page.html', deep=True)
        self.assertEqual((r['status'], r['source']), ('ok', 'yt-dlp'))
        self.assertEqual(len(calls), 1)


class WorkerEndpointTests(unittest.TestCase):
    """POST /api/probe and the quality-aware /api/jobs through the real worker server."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        import worker
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = worker.make_server(0, cls.tmp.name, Path(cls.tmp.name) / 'history.json')
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def post(self, path, body, token=True):
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', data=json.dumps(body).encode(), method='POST',
                                         headers={'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{self.port}',
                                                  **({'X-Omni-Token': self.server.token} if token else {})})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b'{}')

    def test_probe_endpoint(self):
        status, body = self.post('/api/probe', {'url': 'http://127.0.0.1:9021/'})
        self.assertEqual((status, body['status']), (200, 'refused'))
        self.assertEqual(self.post('/api/probe', {'url': 'http://example.com/'}, token=False)[0], 403)
        self.assertEqual(self.post('/api/probe', {'url': 'http://example.com/', 'extra': 1})[0], 400)
        self.assertEqual(self.post('/api/probe', {'url': 'javascript:alert(1)'})[0], 400)
        self.assertEqual(self.post('/api/probe', {'url': 'http://example.com/', 'deep': 'yes'})[0], 400)

    def test_job_quality(self):
        status, body = self.post('/api/jobs', {'url': 'https://example.com/v.m3u8', 'demo': True, 'audio': False,
                                               'engine': 'ytdlp', 'quality': {'height': 720}, 'referer': 'https://site.example/'})
        self.assertEqual(status, 201, body)
        job = self.server.jobs.jobs[body['id']]
        self.assertEqual(job['format'], 'bestvideo[height<=720]+bestaudio/best[height<=720]')
        self.assertEqual(job['referer'], 'https://site.example/')
        self.assertEqual(self.post('/api/jobs', {'url': 'https://example.com/v.m3u8', 'demo': True, 'quality': {'height': 'x'}})[0], 400)
        self.assertEqual(self.post('/api/jobs', {'url': 'https://example.com/v.m3u8', 'demo': True, 'referer': 'file:///x'})[0], 400)
        status, body = self.post('/api/jobs', {'url': 'https://example.com/f.bin', 'demo': True, 'engine': 'jdownloader', 'quality': {'height': 720}})
        self.assertEqual(status, 201, body)
        self.assertIsNone(self.server.jobs.jobs[body['id']]['format'])


if __name__ == '__main__':
    unittest.main()
