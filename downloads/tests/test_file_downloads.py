# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_FILE_DOWNLOADS_V1: regular files (PDF, ZIP, images, attachments) that Omni hands to Downloads.

probe.py reports them as kind 'file' with plain=True; a job with direct=True saves the original file with the
direct file download, without yt-dlp and without a file type (container). Local fixtures and fakes only: no
outside network, yt_dlp is not needed.

Run: python3 -m unittest tests/test_file_downloads.py   (from the downloads folder)
"""
import http.server
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import probe  # noqa: E402
import save_places  # noqa: E402
import worker  # noqa: E402

PDF = b'%PDF-1.7\n' + b'\x00' * 3000
ZIP = b'PK\x03\x04' + b'\x00' * 3000
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 3000
MP4 = b'\x00\x00\x00\x18ftypisom' + b'\x00' * 3000

ROUTES = {
    '/docs/manual.pdf': (PDF, 'application/pdf', None),
    '/get?id=7': (ZIP, 'application/octet-stream', 'attachment; filename="game saves.zip"'),
    '/pic.png': (PNG, 'image/png', None),
    '/blob': (b'\x00' * 3000, 'application/x-unknown', 'attachment; filename*=UTF-8\'\'report%202026.xlsx'),
    '/unknown.bin': (b'\x00' * 3000, 'application/x-unknown', None),
    '/movie': (b'\x00' * 3000, 'application/x-unknown', 'attachment; filename="movie.mp4"'),
    '/clip.mp4': (MP4, 'video/mp4', None),
    '/page.html': (b'<!doctype html><html></html>', 'text/html', 'attachment; filename="x.html"'),
}


class Fixture(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path not in ROUTES:
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        body, kind, disposition = ROUTES[self.path]
        self.send_response(200)
        self.send_header('Content-Type', kind)
        if disposition:
            self.send_header('Content-Disposition', disposition)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class PlainFileProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f'http://files.test:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def p(self, path):
        def resolver(host, port):
            if host == 'files.test':
                return (socket.AF_INET, '127.0.0.1', port)
            raise probe.Refused('test')
        return probe.probe_url(self.base + path, resolver=resolver)

    def test_pdf_by_type(self):
        r = self.p('/docs/manual.pdf')
        self.assertEqual((r['status'], r['kind'], r['container'], r['plain'], r['title']), ('ok', 'file', 'PDF', True, 'manual.pdf'))
        self.assertEqual(r['size'], len(PDF))

    def test_zip_attachment_served_as_octet_stream(self):
        r = self.p('/get?id=7')
        self.assertEqual((r['status'], r['container'], r['plain'], r['title']), ('ok', 'ZIP', True, 'game saves.zip'))

    def test_image(self):
        r = self.p('/pic.png')
        self.assertEqual((r['status'], r['container'], r['plain']), ('ok', 'PNG', True))

    def test_unknown_type_attachment_uses_the_extension(self):
        r = self.p('/blob')
        self.assertEqual((r['status'], r['container'], r['plain'], r['title']), ('ok', 'XLSX', True, 'report 2026.xlsx'))

    def test_unknown_without_attachment_is_unchanged(self):
        self.assertEqual(self.p('/unknown.bin')['status'], 'unsupported')

    def test_media_is_never_plain(self):
        r = self.p('/clip.mp4')
        self.assertEqual((r['status'], r['container'], r['plain']), ('ok', 'MP4', False))
        r = self.p('/movie')   # an attachment named like a video is left to the media route
        self.assertFalse(r['plain'])

    def test_pages_stay_pages(self):
        self.assertEqual(self.p('/page.html')['status'], 'page')


class FakeDirect:
    """Stands in for adapters.DirectFileAdapter: writes the 'downloaded' file, reports progress."""
    calls = []

    def __init__(self, validate=None, timeout=20, referer=None):
        self.referer = referer

    def download(self, url, folder, hook=lambda _: None, metadata=lambda _: None, cancelled=lambda: False):
        type(self).calls.append((url, Path(folder), self.referer))
        metadata({'title': 'manual.pdf'})
        hook({'status': 'downloading', 'downloaded_bytes': 4, 'total_bytes': 8})
        hook({'status': 'finished', 'downloaded_bytes': 8, 'total_bytes': 8})
        Path(folder).mkdir(parents=True, exist_ok=True)
        out = Path(folder) / 'manual.pdf'
        out.write_bytes(b'%PDF-1.7')
        return dict(title='manual.pdf', filepath=str(out), direct=True)


class NoYtdlp:
    def __init__(self, *a, **kw):
        raise AssertionError('yt-dlp must not be used for an original file')


class DirectJobs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.jobs = worker.Jobs(self.tmp, str(self.tmp / 'history.json'))
        self.jobs.ytdlp_adapter = lambda: NoYtdlp
        self.jobs.set_paused(True)   # the test runs each job itself
        FakeDirect.calls = []

    def tearDown(self):
        self.jobs.close()

    def run_job(self, **kw):
        key = self.jobs.create('https://example.com/docs/manual.pdf', False, auto_fallback=False, direct=True, **kw)
        with self.jobs.lock:
            job = dict(self.jobs.jobs[key])
        destination = save_places.work_folder(job.get('save_place') or 'internal', self.tmp, key)
        destination.mkdir(parents=True, exist_ok=True)
        # yt-dlp is not installed: an original file must still download.
        with mock.patch.object(worker, 'DirectFileAdapter', FakeDirect), \
                mock.patch('importlib.util.find_spec', return_value=None):
            self.jobs._route(key, job, destination)
        with self.jobs.lock:
            return dict(self.jobs.jobs[key])

    def test_direct_job_skips_ytdlp_and_completes(self):
        job = self.run_job(referer='https://example.com/')
        self.assertEqual(job['state'], 'completed')
        self.assertTrue(job['direct'])
        self.assertIsNone(job['container'])
        self.assertIn('direct file download', job['note'])
        self.assertEqual(FakeDirect.calls[0][0], 'https://example.com/docs/manual.pdf')
        self.assertEqual(FakeDirect.calls[0][2], 'https://example.com/')
        self.assertTrue(Path(job['filepath']).is_file())

    def test_direct_job_keeps_save_place_and_name(self):
        job = self.run_job(save_place='internal', save_folder='Documents', save_name='Manual')
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(Path(job['filepath']), self.tmp / 'Saved' / 'Documents' / 'Manual.pdf')

    def test_create_refuses_media_options_for_original_files(self):
        url = 'https://example.com/a.zip'
        for kw in ({'container': 'mp4'}, {'audio': True}, {'quality': {'height': 1080}}, {'preset': 'audio-m4a'}):
            with self.assertRaises(ValueError, msg=kw):
                self.jobs.create(url, False, direct=True, **kw)
        with self.assertRaises(ValueError):
            self.jobs.create(url, False, direct='yes')

    def test_direct_without_ytdlp_is_accepted_with_fallback_off(self):
        with mock.patch('importlib.util.find_spec', return_value=None):
            key = self.jobs.create('https://example.com/a.zip', False, auto_fallback=False, direct=True)
        self.assertTrue(self.jobs.jobs[key]['direct'])

    def test_request_id_replay_tells_direct_apart(self):
        rid = 'a' * 32
        self.jobs.create('https://example.com/a.zip', False, request_id=rid, direct=True)
        with self.assertRaises(ValueError):
            self.jobs.create('https://example.com/a.zip', False, request_id=rid)

    def test_old_jobs_are_not_direct(self):
        key = self.jobs.create('https://example.com/v', False)
        self.assertFalse(self.jobs.jobs[key]['direct'])


if __name__ == '__main__':
    unittest.main()
