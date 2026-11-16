# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DOWNLOAD_ALL_V1: many file links at once (Omni's page menu "Download all...").

The Downloads GUI posts the confirmed list to POST /api/jobs/batch {urls, request_id[, referer]} with the session
token (no token: 403, like every write). Up to MAX_BATCH links; each is checked as a job's URL. They wait in the
held list and become direct-file jobs while the queue has room (MAX_PENDING); /api/jobs/held/clear drops the rest;
/api/status reports how many wait. The queue is held in these tests, so nothing is downloaded.

Run: python3 -m unittest tests/test_download_all.py   (from the downloads folder)
"""
import http.client
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import worker  # noqa: E402

RID = 'a' * 32


def links(n, base='https://files.example.com/f'):
    return ['%s%03d.pdf' % (base, i) for i in range(n)]


class BatchJobs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='dl-all-'))
        self.jobs = worker.Jobs(self.tmp, str(self.tmp / 'history.json'), done_file=None)
        self.jobs.set_paused(True)   # nothing runs: jobs stay queued

    def tearDown(self):
        self.jobs.close(timeout=1)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def queued(self):
        with self.jobs.lock:
            return [j for j in self.jobs.jobs.values() if j['state'] == 'queued']

    def test_fills_the_queue_and_holds_the_rest(self):
        r = self.jobs.add_batch(links(20), RID, 'https://example.com/page')
        self.assertEqual(r, {'accepted': 20, 'skipped': 0, 'held': 20 - worker.MAX_PENDING, 'replayed': False})
        jobs = self.queued()
        self.assertEqual(len(jobs), worker.MAX_PENDING)
        for job in jobs:
            self.assertTrue(job['direct'])
            self.assertFalse(job['demo'])
            self.assertEqual(job['referer'], 'https://example.com/page')
            self.assertIsNone(job['container'])
        self.assertEqual(sorted(j['url'] for j in jobs), links(20)[:worker.MAX_PENDING])   # in page order

    def test_duplicates_and_known_links_are_skipped(self):
        first = links(3)
        self.jobs.add_batch(first, RID)
        r = self.jobs.add_batch(first + first[:1] + ['https://files.example.com/new.zip'], 'b' * 32)
        self.assertEqual((r['accepted'], r['skipped']), (1, 4))
        self.assertEqual(len(self.queued()), 4)

    def test_same_request_id_is_a_replay(self):
        self.jobs.add_batch(links(10), RID)
        r = self.jobs.add_batch(links(10), RID)
        self.assertTrue(r['replayed'])
        self.assertEqual(r['accepted'], 10)
        self.assertEqual(len(self.queued()) + len(self.jobs.held), 10)

    def test_whole_batch_refused_on_one_bad_link(self):
        for bad in ('javascript:alert(1)', 'https://user:pw@example.com/a.zip', 'ftp://example.com/a.zip',
                    'https://example.com/a b.zip', 'https://example.com/' + 'x' * 4100, 7, None):
            with self.assertRaises(ValueError, msg=bad):
                self.jobs.add_batch(links(2) + [bad], RID)
        self.assertEqual(self.queued(), [])
        self.assertEqual(len(self.jobs.held), 0)

    def test_limits(self):
        with self.assertRaises(ValueError):
            self.jobs.add_batch([], RID)
        with self.assertRaises(ValueError):
            self.jobs.add_batch(links(worker.MAX_BATCH + 1), RID)
        with self.assertRaises(ValueError):
            self.jobs.add_batch(links(2), 'not-hex')
        with self.assertRaises(ValueError):
            self.jobs.add_batch(links(2), RID, 'javascript:1')
        with self.assertRaises(ValueError):
            self.jobs.add_batch('https://example.com/a.zip', RID)
        self.jobs.add_batch(links(200, 'https://a.example.com/'), '1' * 32)
        self.jobs.add_batch(links(200, 'https://b.example.com/'), '2' * 32)
        with self.assertRaisesRegex(ValueError, 'Too many links'):
            self.jobs.add_batch(links(200, 'https://c.example.com/'), '3' * 32)

    def test_promote_after_a_slot_frees(self):
        self.jobs.add_batch(links(10), RID)
        first = self.queued()[0]['id']
        self.jobs.cancel(first)
        self.jobs.promote()   # the dispatcher may have taken it first: either way one link moved
        self.assertEqual(len(self.queued()), worker.MAX_PENDING)
        self.assertEqual(len(self.jobs.held), 1)

    def test_dispatcher_promotes_on_its_own(self):
        self.jobs.add_batch(links(9), RID)
        self.jobs.cancel(self.queued()[0]['id'])
        deadline = time.monotonic() + 5
        while (self.jobs.held or len(self.queued()) < worker.MAX_PENDING) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(len(self.jobs.held), 0)
        self.assertEqual(len(self.queued()), worker.MAX_PENDING)

    def test_clear_and_close(self):
        self.jobs.add_batch(links(15), RID)
        self.assertEqual(self.jobs.clear_held(), 15 - worker.MAX_PENDING)
        self.assertEqual(self.jobs.clear_held(), 0)
        self.jobs.add_batch(links(15, 'https://other.example.com/'), 'c' * 32)
        self.jobs.close(timeout=1)
        self.assertEqual(len(self.jobs.held), 0)
        with self.assertRaises(ValueError):
            self.jobs.add_batch(links(1, 'https://late.example.com/'), 'd' * 32)

    def test_history_full_of_paused_jobs_keeps_links_held(self):
        with self.jobs.lock:
            for i in range(worker.MAX_JOBS):
                key = '%016x' % i
                self.jobs.jobs[key] = dict(id=key, url='https://p.example.com/%d' % i, demo=False, audio=False,
                                           state='paused', cancel=False, engine='ytdlp')
        r = self.jobs.add_batch(links(3), RID)
        self.assertEqual((r['accepted'], r['held']), (3, 3))   # create() said "Queue is full": the links wait


class BatchApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dl-all-api-')
        cls.server = worker.make_server(0, cls.tmp, Path(cls.tmp) / 'history.json')
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.server.jobs.set_paused(True)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server.jobs.close(timeout=1)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def tearDown(self):
        jobs = self.server.jobs
        jobs.clear_held()
        for job in jobs.snapshot():
            if job['state'] not in worker.TERMINAL:
                jobs.cancel(job['id'])

    def call(self, method, path, body=None, token=True, raw=None, host=None):
        port = self.server.server_port
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {'Host': host or '127.0.0.1:%d' % port, 'Content-Type': 'application/json'}
        if token:
            headers['X-Omni-Token'] = self.server.token
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read() or b'null')
        finally:
            connection.close()

    def test_needs_the_token_and_host(self):
        body = {'urls': links(2, 'https://token.example.com/'), 'request_id': RID}
        before = len(self.server.jobs.snapshot())
        self.assertEqual(self.call('POST', '/api/jobs/batch', body, token=False)[0], 403)
        self.assertEqual(self.call('POST', '/api/jobs/batch', body, host='evil.example:80')[0], 403)
        self.assertEqual(self.call('POST', '/api/jobs/held/clear', {'clear': True}, token=False)[0], 403)
        self.assertEqual((len(self.server.jobs.held), len(self.server.jobs.snapshot())), (0, before))

    def test_large_batch_over_the_plain_body_limit(self):
        urls = links(200, 'https://files.example.com/' + 'd' * 60 + '/')
        body = {'urls': urls, 'request_id': '4' * 32, 'referer': 'https://example.com/list'}
        self.assertGreater(len(json.dumps(body)), worker.MAX_BODY_BYTES)
        code, value = self.call('POST', '/api/jobs/batch', body)
        self.assertEqual(code, 200)
        self.assertEqual(value, {'accepted': 200, 'skipped': 0, 'held': 200 - worker.MAX_PENDING, 'replayed': False})
        code, status = self.call('GET', '/api/status')
        self.assertEqual((code, status['held']), (200, 200 - worker.MAX_PENDING))
        self.assertEqual(self.call('POST', '/api/jobs/held/clear', {'clear': True}), (200, {'cleared': 200 - worker.MAX_PENDING}))
        self.assertEqual(self.call('GET', '/api/status')[1]['held'], 0)

    def test_other_routes_keep_the_small_limit(self):
        big = {'url': 'https://example.com/' + 'x' * 9000, 'demo': True}
        self.assertEqual(self.call('POST', '/api/jobs', big)[0], 400)

    def test_body_over_the_batch_limit(self):
        raw = b'{"urls":["' + b'a' * worker.BATCH_BODY_BYTES + b'"],"request_id":"' + RID.encode() + b'"}'
        try:
            code = self.call('POST', '/api/jobs/batch', raw=raw)[0]
        except (BrokenPipeError, ConnectionResetError):
            code = 400   # the worker answered 400 and closed before the whole body was sent
        self.assertEqual(code, 400)
        self.assertEqual(len(self.server.jobs.held), 0)

    def test_shape_checks(self):
        self.assertEqual(self.call('POST', '/api/jobs/batch', {'urls': links(1)})[0], 400)
        self.assertEqual(self.call('POST', '/api/jobs/batch', {'urls': links(1), 'request_id': RID, 'demo': True})[0], 400)
        self.assertEqual(self.call('POST', '/api/jobs/batch', {'urls': links(1), 'request_id': RID, 'referer': 'nope'})[0], 400)
        self.assertEqual(self.call('POST', '/api/jobs/held/clear', {'clear': False})[0], 400)
        self.assertEqual(self.call('POST', '/api/jobs/held/clear', {'clear': True, 'x': 1})[0], 400)


if __name__ == '__main__':
    unittest.main()
