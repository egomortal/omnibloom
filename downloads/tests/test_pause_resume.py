# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_RESUME_V1: pause, resume and retry.

A local HTTP fixture stands in for a public file server ('localhost' is allowed by the test resolver and served from
127.0.0.1, as in test_download_egress.py), so every request still goes through the egress guard. It honours Range
requests (206 + Content-Range) unless a route says otherwise. No outside network.

Run: python -m unittest tests/test_pause_resume.py   (from the downloads folder)
"""
import http.server
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import adapters  # noqa: E402
import egress_guard  # noqa: E402
import probe  # noqa: E402
import worker  # noqa: E402

try:
    import yt_dlp  # noqa: F401
except ImportError:  # pragma: no cover
    yt_dlp = None

BODY = bytes(range(256)) * 4096          # 1 MiB, every offset recognisable
REQUESTS = []                            # (path, Range header, If-Range header)
MODE = {'etag': '"v1"', 'slow': 0.0}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _head(self, code, length, extra=()):
        self.send_response(code)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(length))
        self.send_header('ETag', MODE['etag'])
        self.send_header('Accept-Ranges', 'bytes')
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()

    def _body(self, data):
        step = 16 * 1024
        for i in range(0, len(data), step):
            self.wfile.write(data[i:i + step])
            if MODE['slow']:
                self.wfile.flush()
                time.sleep(MODE['slow'])

    def do_GET(self):
        rng, if_range = self.headers.get('Range'), self.headers.get('If-Range')
        REQUESTS.append((self.path.split('?')[0], rng, if_range))
        path = self.path.split('?')[0]
        try:
            if path == '/drop.bin' and not rng:
                # Announces the whole file, sends 300 KiB and closes: a lost connection mid-file.
                self._head(200, len(BODY))
                self.wfile.write(BODY[:300 * 1024])
                self.wfile.flush()
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            if path in ('/file.bin', '/drop.bin', '/norange.bin', '/badrange.bin', '/video.mp4') and rng:
                start = int(rng.split('=')[1].split('-')[0])
                if path == '/norange.bin' or (if_range and if_range != MODE['etag']):
                    self._head(200, len(BODY))           # whole file again (no ranges, or it changed)
                    return self._body(BODY)
                if start >= len(BODY):
                    self._head(416, 0, [('Content-Range', 'bytes */%d' % len(BODY))])
                    return
                wrong = start + 1 if path == '/badrange.bin' else start   # lies about where its bytes start
                part = BODY[start:]
                self._head(206, len(part), [('Content-Range', 'bytes %d-%d/%d' % (wrong, len(BODY) - 1, len(BODY)))])
                return self._body(part)
            if path in ('/file.bin', '/norange.bin', '/badrange.bin', '/video.mp4'):
                self._head(200, len(BODY), [('Content-Type', 'video/mp4')] if path == '/video.mp4' else ())
                return self._body(BODY)
            self._head(404, 0)
        except (ConnectionError, OSError):
            pass


def resolver(host, port):
    if host == 'localhost':
        return (socket.AF_INET, '127.0.0.1', port)
    raise probe.Refused('Local or private address')


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.daemon_threads = True
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_port
        cls.saved = probe.public_address
        probe.public_address = resolver
        egress_guard._guard = None

    @classmethod
    def tearDownClass(cls):
        probe.public_address = cls.saved
        if egress_guard._guard is not None:
            egress_guard._guard.close()
            egress_guard._guard = None
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        REQUESTS.clear()
        MODE.update(etag='"v1"', slow=0.0)
        self.folder = Path(tempfile.mkdtemp(prefix='dl-resume-'))

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def url(self, path):
        return 'http://localhost:%d%s' % (self.port, path)


def pause_after(nbytes):
    def hook(data):
        if data.get('status') == 'downloading' and (data.get('downloaded_bytes') or 0) >= nbytes:
            raise adapters.Paused('Paused')
    return hook


class DirectRangeResume(Base):
    """DirectFileAdapter keeps its part file on pause and continues it with a verified Range request."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(adapters.DirectFileAdapter, 'CHUNK', 64 * 1024)
        patcher.start()
        self.addCleanup(patcher.stop)

    def pause_once(self, path):
        with self.assertRaises(adapters.Paused):
            adapters.DirectFileAdapter().download(self.url(path), self.folder, pause_after(200 * 1024))
        part = self.folder / adapters.DirectFileAdapter.PART
        self.assertTrue(part.is_file(), os.listdir(self.folder))
        self.assertTrue((self.folder / adapters.DirectFileAdapter.META).is_file())
        size = part.stat().st_size
        self.assertTrue(0 < size < len(BODY), size)
        self.assertEqual(part.read_bytes(), BODY[:size])
        side = (self.folder / adapters.DirectFileAdapter.META).read_text()
        self.assertNotIn('localhost', side, 'the side file keeps a hash of the link, never the link')
        return size

    def finish(self, path):
        seen = []
        out = adapters.DirectFileAdapter().download(self.url(path), self.folder, lambda d: seen.append(d))
        self.assertEqual(Path(out['filepath']).read_bytes(), BODY)
        self.assertEqual(sorted(os.listdir(self.folder)), [Path(out['filepath']).name], 'part and side files are gone')
        return out, seen

    def test_pause_then_resume_continues_with_range(self):
        size = self.pause_once('/file.bin')
        REQUESTS.clear()
        out, seen = self.finish('/file.bin')
        self.assertEqual(REQUESTS, [('/file.bin', 'bytes=%d-' % size, '"v1"')])
        self.assertEqual(out['resumed_from'], size)
        self.assertEqual(seen[0]['downloaded_bytes'], size + 64 * 1024, 'progress counts the bytes already saved')
        self.assertEqual(seen[-1]['downloaded_bytes'], len(BODY))

    def test_server_without_ranges_restarts_cleanly(self):
        self.pause_once('/norange.bin')
        REQUESTS.clear()
        out, _ = self.finish('/norange.bin')
        self.assertEqual(len(REQUESTS), 1)      # the 200 answer itself is used from the start
        self.assertEqual(out['resumed_from'], 0)

    def test_wrong_content_range_restarts_cleanly(self):
        size = self.pause_once('/badrange.bin')
        REQUESTS.clear()
        out, _ = self.finish('/badrange.bin')
        self.assertEqual(REQUESTS, [('/badrange.bin', 'bytes=%d-' % size, '"v1"'), ('/badrange.bin', None, None)])
        self.assertEqual(out['resumed_from'], 0)

    def test_changed_file_is_downloaded_again(self):
        self.pause_once('/file.bin')
        MODE['etag'] = '"v2"'                   # If-Range no longer matches: the server sends the whole file
        REQUESTS.clear()
        out, _ = self.finish('/file.bin')
        self.assertEqual(len(REQUESTS), 1)
        self.assertEqual(out['resumed_from'], 0)

    def test_part_of_another_link_is_not_continued(self):
        self.pause_once('/file.bin')
        REQUESTS.clear()
        out, _ = self.finish('/norange.bin')
        self.assertEqual(REQUESTS, [('/norange.bin', None, None)])
        self.assertEqual(out['resumed_from'], 0)

    def test_cancel_removes_the_part_file(self):
        with self.assertRaises(InterruptedError):
            adapters.DirectFileAdapter().download(self.url('/file.bin'), self.folder, cancelled=lambda: True)
        self.assertEqual(os.listdir(self.folder), [])

    def test_lost_connection_keeps_the_part_for_a_retry(self):
        with self.assertRaises(RuntimeError):
            adapters.DirectFileAdapter().download(self.url('/drop.bin'), self.folder)
        size = (self.folder / adapters.DirectFileAdapter.PART).stat().st_size
        self.assertGreater(size, 0)
        REQUESTS.clear()
        out, _ = self.finish('/drop.bin')
        self.assertEqual(REQUESTS[0][1], 'bytes=%d-' % size)
        self.assertEqual(out['resumed_from'], size)

    def test_content_range_parser(self):
        parse = adapters.DirectFileAdapter._content_range
        self.assertEqual(parse('bytes 10-99/100'), (10, 99, 100))
        self.assertEqual(parse('bytes 10-99/*'), (10, 99, None))
        for bad in ('bytes 10-9/100', 'bytes 10-100/100', 'items 1-2/3', '', None, 'bytes -1-2/3'):
            self.assertIsNone(parse(bad), bad)


@unittest.skipIf(yt_dlp is None, 'yt-dlp not installed')
class YtdlpPartResume(Base):
    def test_ytdlp_continues_its_part_file(self):
        options = adapters.PythonYtdlpAdapter().options(self.folder, False, lambda _: None)
        self.assertIs(options['continuedl'], True)
        # yt-dlp wraps the hook's Paused in UnavailableVideoError; the worker tells it apart by the job's pause flag.
        with self.assertRaises(Exception):
            adapters.PythonYtdlpAdapter().download(self.url('/video.mp4'), self.folder, hook=pause_after(1))
        parts = [n for n in os.listdir(self.folder) if n.endswith('.part')]
        self.assertEqual(len(parts), 1, os.listdir(self.folder))
        size = (self.folder / parts[0]).stat().st_size
        self.assertGreater(size, 0)
        REQUESTS.clear()
        adapters.PythonYtdlpAdapter().download(self.url('/video.mp4'), self.folder)
        ranged = [r for r in REQUESTS if r[1]]
        self.assertTrue(ranged and ranged[-1][1].startswith('bytes=%d-' % size), REQUESTS)
        files = [n for n in os.listdir(self.folder) if not n.endswith('.part')]
        self.assertEqual(len(files), 1, os.listdir(self.folder))
        self.assertEqual((self.folder / files[0]).read_bytes(), BODY)


def wait_for(predicate, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError('timed out')


class JobStates(unittest.TestCase):
    """The Jobs state machine with demo jobs (no network)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='dl-jobs-'))
        self.history = self.tmp / 'history.json'
        self.jobs = worker.Jobs(self.tmp, str(self.history), done_file=None)

    def tearDown(self):
        self.jobs.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def state(self, key):
        with self.jobs.lock:
            return self.jobs.jobs[key]['state']

    def saved(self):
        return {r['id']: r for r in json.loads(self.history.read_text())['jobs']}

    def test_pause_running_job_lets_the_queue_move_on_then_resume(self):
        first = self.jobs.create('https://example.com/a.mp4', True)
        second = self.jobs.create('https://example.com/b.mp4', True)
        wait_for(lambda: self.jobs.jobs[first]['state'] == 'downloading' and (self.jobs.jobs[first]['progress'] or 0) >= 5)
        self.assertIn(self.jobs.pause(first), ('pausing', 'paused'))
        wait_for(lambda: self.state(first) == 'paused')
        held = self.jobs.jobs[first]['progress']
        self.assertLess(held, 100)
        wait_for(lambda: self.state(second) == 'completed')            # the queue moved on
        self.assertEqual(self.state(first), 'paused')
        self.assertEqual(self.saved()[first]['state'], 'paused')
        self.assertEqual(self.jobs.resume(first), 'queued')
        wait_for(lambda: self.state(first) == 'completed')
        job = self.jobs.jobs[first]
        self.assertEqual((job['attempt'], job['retries'], job['error']), (2, 0, ''))
        self.assertNotIn('url', self.saved()[first], 'finished records stay link-free')

    def test_pause_waiting_job_at_once_and_it_frees_its_queue_slot(self):
        self.jobs.set_paused(True)
        keys = [self.jobs.create('https://example.com/%d.mp4' % n, True) for n in range(8)]
        with self.assertRaises(ValueError):
            self.jobs.create('https://example.com/full.mp4', True)
        self.assertEqual(self.jobs.pause(keys[0]), 'paused')
        self.assertNotIn(keys[0], self.jobs.pending)
        self.jobs.create('https://example.com/room.mp4', True)          # a paused job holds no slot
        with self.assertRaises(ValueError) as ctx:
            self.jobs.resume(keys[0])                                    # ...so resuming needs a free one
        self.assertIn('Queue is full', str(ctx.exception))

    def test_rules(self):
        self.jobs.set_paused(True)
        key = self.jobs.create('https://example.com/a.mp4', True)
        for bad in ('x', 'A' * 16, 7, None):
            with self.assertRaises(ValueError):
                self.jobs.pause(bad)
        with self.assertRaises(ValueError):
            self.jobs.pause('0' * 16)                                    # unknown
        with self.assertRaises(ValueError):
            self.jobs.resume(key)                                        # queued: nothing to resume
        with self.assertRaises(ValueError):
            self.jobs.retry(key)
        self.jobs.pause(key)
        with self.assertRaises(ValueError):
            self.jobs.retry(key)                                         # retry is for failed jobs only
        self.jobs.cancel(key)
        self.assertEqual(self.state(key), 'cancelled')                   # a paused job cancels at once
        with self.assertRaises(ValueError):
            self.jobs.pause(key)
        with self.assertRaises(ValueError):
            self.jobs.resume(key)
        self.assertNotIn('url', self.saved()[key])
        self.assertEqual(worker.AUTO_RETRY_LIMIT, 0)

    def test_retry_failed_job_is_manual_with_a_fresh_attempt_counter(self):
        self.jobs.set_paused(True)
        key = self.jobs.create('https://example.com/a.mp4', True)
        with self.jobs.lock:
            self.jobs.pending.remove(key)
            self.jobs.jobs[key].update(state='failed', error='boom', attempt=3)
        time.sleep(0.2)
        self.assertEqual(self.state(key), 'failed')                      # never retried automatically
        self.jobs.retry(key)
        job = self.jobs.jobs[key]
        self.assertEqual((job['state'], job['attempt'], job['retries'], job['error']), ('queued', 1, 1, ''))
        self.assertIn(key, self.jobs.pending)

    def test_paused_job_survives_a_restart_as_paused(self):
        self.jobs.set_paused(True)
        key = self.jobs.create('https://example.com/a.mp4', True, save_place='internal', save_folder='Clips')
        other = self.jobs.create('https://example.com/b.mp4', True)
        self.jobs.pause(key)
        self.jobs.close()
        record = self.saved()[key]
        self.assertEqual((record['state'], record['url'], record['save_folder']), ('paused', 'https://example.com/a.mp4', 'Clips'))
        self.assertEqual(self.saved()[other]['state'], 'cancelled')      # close() still cancels waiting jobs
        self.assertNotIn('url', self.saved()[other])
        self.jobs = worker.Jobs(self.tmp, str(self.history), done_file=None)
        job = self.jobs.jobs[key]
        self.assertEqual((job['state'], job['url'], job['cancel'], job['save_place']), ('paused', 'https://example.com/a.mp4', False, 'internal'))
        self.jobs.resume(key)
        wait_for(lambda: self.state(key) == 'completed')

    def test_unfinished_job_loads_interrupted_and_resumable(self):
        self.jobs.set_paused(True)
        key = self.jobs.create('https://example.com/a.mp4', True)
        with self.jobs.lock:   # as if the worker died mid-download (no close)
            self.jobs.jobs[key].update(state='downloading', downloaded_bytes=50, total_bytes=200)
            self.jobs.history.save(self.jobs.jobs)
        restarted = worker.Jobs(self.tmp, str(self.history), done_file=None)
        try:
            job = restarted.jobs[key]
            self.assertEqual((job['state'], job['progress'], job['error']), ('interrupted', 25, 'Worker stopped; resume to continue.'))
            restarted.resume(key)
            self.assertEqual(restarted.jobs[key]['state'], 'queued')
        finally:
            restarted.close()

    def test_old_link_free_record_cannot_be_resumed(self):
        self.history.write_text(json.dumps({'version': 1, 'jobs': [dict(id='a' * 16, state='downloading', title='t')]}))
        jobs = worker.Jobs(self.tmp, str(self.history), done_file=None)
        try:
            self.assertEqual(jobs.jobs['a' * 16]['error'], 'Worker stopped; submit the link again.')
            with self.assertRaises(ValueError) as ctx:
                jobs.resume('a' * 16)
            self.assertIn('submit the link again', str(ctx.exception))
        finally:
            jobs.close()

    def test_tampered_history_is_checked_again_on_resume(self):
        record = dict(id='b' * 16, state='paused', title='t', url='http://127.0.0.1/x', save_place='usb5')
        self.history.write_text(json.dumps({'version': 1, 'jobs': [record]}))
        jobs = worker.Jobs(self.tmp, str(self.history), done_file=None)
        try:
            with self.assertRaises(ValueError):
                jobs.resume('b' * 16)          # USB drive 6 is not connected
            self.assertEqual(jobs.jobs['b' * 16]['state'], 'paused')
        finally:
            jobs.close()


class DirectJobPauseResume(Base):
    """A real direct-file job paused mid-file and resumed: the worker continues the same part file."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(adapters.DirectFileAdapter, 'CHUNK', 16 * 1024)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.jobs = worker.Jobs(self.folder, str(self.folder / 'history.json'), done_file=None)

    def tearDown(self):
        self.jobs.close()
        super().tearDown()

    def test_pause_and_resume_direct_job(self):
        MODE['slow'] = 0.01
        key = self.jobs.create(self.url('/file.bin'), False, auto_fallback=False, direct=True, save_place='internal', save_name='Saved file')
        wait_for(lambda: (self.jobs.jobs[key].get('downloaded_bytes') or 0) >= 128 * 1024)
        self.jobs.pause(key)
        wait_for(lambda: self.jobs.jobs[key]['state'] == 'paused')
        part = self.folder / key / adapters.DirectFileAdapter.PART
        size = part.stat().st_size
        self.assertTrue(0 < size < len(BODY))
        MODE['slow'] = 0.0
        REQUESTS.clear()
        self.jobs.resume(key)
        wait_for(lambda: self.jobs.jobs[key]['state'] in ('completed', 'failed'))
        job = self.jobs.jobs[key]
        self.assertEqual(job['state'], 'completed', job.get('error'))
        self.assertEqual(REQUESTS[0][1], 'bytes=%d-' % size)
        self.assertEqual(Path(job['filepath']), self.folder / 'Saved' / 'Saved file.bin')
        self.assertEqual(Path(job['filepath']).read_bytes(), BODY)

    @unittest.skipIf(yt_dlp is None, 'yt-dlp not installed')
    def test_pause_and_resume_ytdlp_job(self):
        MODE['slow'] = 0.01
        key = self.jobs.create(self.url('/video.mp4'), False, auto_fallback=False)
        wait_for(lambda: (self.jobs.jobs[key].get('downloaded_bytes') or 0) >= 64 * 1024, timeout=20)
        self.jobs.pause(key)
        wait_for(lambda: self.jobs.jobs[key]['state'] in ('paused', 'failed', 'completed'))
        self.assertEqual(self.jobs.jobs[key]['state'], 'paused', self.jobs.jobs[key].get('error'))
        parts = list((self.folder / key).glob('*.part'))
        self.assertEqual(len(parts), 1)
        size = parts[0].stat().st_size
        MODE['slow'] = 0.0
        REQUESTS.clear()
        self.jobs.resume(key)
        wait_for(lambda: self.jobs.jobs[key]['state'] in ('completed', 'failed'), timeout=20)
        job = self.jobs.jobs[key]
        self.assertEqual(job['state'], 'completed', job.get('error'))
        self.assertTrue(any(r[1] == 'bytes=%d-' % size for r in REQUESTS), (size, REQUESTS))
        self.assertEqual(Path(job['filepath']).read_bytes(), BODY)


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dl-api-')
        cls.server = worker.make_server(0, cls.tmp, Path(cls.tmp) / 'history.json')
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.server.jobs.set_paused(True)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def post(self, path, body, token=True):
        port = self.server.server_port
        data = json.dumps(body).encode()
        headers = {'Content-Type': 'application/json', 'Host': '127.0.0.1:%d' % port}
        if token:
            headers['X-Omni-Token'] = self.server.token
        request = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), data=data, headers=headers, method='POST')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_pause_resume_retry_endpoints(self):
        code, value = self.post('/api/jobs', {'url': 'https://example.com/a.mp4', 'demo': True})
        key = value['id']
        self.assertEqual(self.post('/api/jobs/pause', {'id': key}), (200, {'ok': True, 'id': key, 'state': 'paused'}))
        self.assertEqual(self.post('/api/jobs/pause', {'id': key}, token=False)[0], 403)
        self.assertEqual(self.post('/api/jobs/resume', {'id': key, 'extra': 1})[0], 400)
        self.assertEqual(self.post('/api/jobs/resume', {'id': 'nothex'})[0], 400)
        self.assertEqual(self.post('/api/jobs/retry', {'id': key})[0], 400)            # not failed
        self.assertEqual(self.post('/api/jobs/resume', {'id': key}), (200, {'ok': True, 'id': key, 'state': 'queued'}))
        self.assertEqual(self.post('/api/jobs/resume', {'id': key})[0], 400)           # already queued
        self.server.jobs.cancel(key)


if __name__ == '__main__':
    unittest.main()
